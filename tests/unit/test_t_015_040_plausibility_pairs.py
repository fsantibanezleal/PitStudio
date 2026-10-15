# ruff: noqa: E501
"""T-015-040: the task-B pair set, the six corruption detectors and the rejection of pairs that fail confirmation.

Requirements: FR-015-33, FR-015-34, FR-015-35, P-015-10.

Spec: specs/015-vlm/spec.md
- FR-015-33: 100 pairs of 5-8 s clips (muck-pile formation, truck dump, bench collapse); each pair holds a calibrated clip and the same
  scene with exactly one corruption from {gravity x 0.3, friction set to 0, mass injection, time reversal, interpenetration, frozen
  particles}, 16 or 17 pairs per corruption, listed per `contracts/plausibility-pairs.schema.json`.
- FR-015-34: every corrupted clip is confirmed on its simulation state by the detector of its own corruption - fitted free-fall
  acceleration within +-5 % of 0.3 g; repose angle < 5 deg; total particle mass increase >= 5 % with no inflow boundary; frame order
  exactly reversed; >= 10 % of contacts with overlap > 50 % of the radius sum for >= 1 s; >= 5 % of particles with zero displacement
  for >= 1 s while neighbours within two radii move - and every calibrated clip triggers none of the six detectors.
- FR-015-35: a pair that fails FR-015-34, declares zero or more than one corruption, or whose clips differ in scene, camera, duration
  or frame count is excluded and replaced by a regenerated pair of the same corruption before any query.
- P-015-10: (MR1) time reversal is an involution; (MR2) the identity corruption (gravity x 1) reproduces the calibrated clip
  bit-exactly; (MR3) every corruption detector is invariant under permutation of particle ids.

Oracle: synthetic trajectories with known physics built in the test: ballistic fall z(t) = z0 + v0 t - a t^2 / 2 with a = ratio * g0
(g0 = 9.80665 m/s^2, the standard value; the fitted ratio is compared with the generating ratio), static particle pairs whose
centre distance is 2 r (1 - overlap) by construction, lattices with a frozen subset of known size, a mass table with known
additions, frame-order permutations; counts and fractions by hand (for example 10 deep pairs of 100 give 0.10). The contract
schema (`jsonschema`) decides the pair document rules.

Expected API of the implementation (package `pitstudio`, root environment, NumPy), `pitstudio.reason.plausibility`:
- A simulation state is a dict: `pos` float array (frames, particles, 3) in metres; `fps`; `radius` (particles,); `mass` (frames,
  particles) in kg (0 = absent); `frame_order` int array (frames,) with the source index shown at each output frame (identity unless
  time was reversed); `observables` with `repose_angle_deg` (the spec 005 measurement recorded by the physics stage); `inflow_boundary` bool.
- `CORRUPTIONS`: the six names of the contract, in the order of FR-015-33.
- `detect(sim) -> dict`: one entry per corruption, `{"triggered": bool, "statistic": str, "value": float, "sustained_s": float | None}`;
  statistics `fitted_g_ratio` (fitted free-fall acceleration / g0), `repose_angle_deg`, `mass_increase_pct`, `reversed_frame_fraction`,
  `deep_overlap_contact_fraction`, `frozen_particle_fraction`; `sustained_s` only for the last two.
- `reverse_time(sim) -> dict`: new state with frames and `frame_order` reversed.
- `make_corrupted(simulate, initial, corruption, *, scale=None) -> dict`: "gravity-x0.3" returns `simulate(initial, gravity_scale=scale)`
  (`scale` defaults to 0.3); "time-reversal" returns `reverse_time(simulate(initial, gravity_scale=1.0))`; any other name raises ValueError.
- `confirm_pair(calibrated, corrupted, corruption) -> dict`: the pair `confirmation` object of the contract.
- `check_pair(pair) -> list[str]`: reasons why a pair document is not acceptable (empty list = acceptable): schema violations, anything
  other than exactly one corruption, a failed confirmation, clips that differ in scene, camera, duration or frame count.
- `build_pair_set(candidates, *, regenerate, seed=0) -> PairSet` with `.pairs` (accepted pairs, same order, replacements in place),
  `.excluded` (list of `(pair_id, reasons)`) and `.to_document()` (the `plausibility-pairs` document); `regenerate(corruption, attempt)`
  returns a new candidate pair of that corruption (`attempt` counts from 1 per excluded slot).
"""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.reason import plausibility as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _p015_contracts as contracts
import _p015_kit as kit

G0 = 9.80665
CORR = ("gravity-x0.3", "zero-friction", "mass-injection", "time-reversal", "interpenetration", "frozen-particles")


# ------------------------------------------------------------------------------------------------ synthetic states
def _state(
    pos: np.ndarray,
    *,
    fps: float = 30.0,
    radius: float = 0.05,
    mass: np.ndarray | None = None,
    repose: float = 30.0,
    inflow: bool = False,
    order: np.ndarray | None = None,
) -> dict:
    t, n, _ = pos.shape
    return {
        "pos": pos,
        "fps": fps,
        "radius": np.full(n, radius),
        "mass": np.ones((t, n)) if mass is None else mass,
        "frame_order": np.arange(t) if order is None else order,
        "observables": {"repose_angle_deg": repose},
        "inflow_boundary": inflow,
    }


def free_fall(
    ratio: float, *, n: int = 40, frames: int = 60, fps: float = 30.0, seed: int = 0, noise: float = 0.0, **kw
) -> dict:
    """Ballistic fall under a = ratio * g0 from random heights and velocities; particles 2 m apart (no contacts)."""
    rng = np.random.default_rng(seed)
    t = np.arange(frames) / fps
    z0 = rng.uniform(60.0, 80.0, n)
    v0 = rng.uniform(-2.0, 2.0, n)
    pos = np.zeros((frames, n, 3))
    pos[:, :, 0] = (np.arange(n) % 8) * 2.0
    pos[:, :, 1] = (np.arange(n) // 8) * 2.0
    pos[:, :, 2] = z0[None, :] + v0[None, :] * t[:, None] - 0.5 * ratio * G0 * t[:, None] ** 2
    if noise:
        pos += rng.normal(0.0, noise, pos.shape)
    return _state(pos, fps=fps, **kw)


def calibrated(seed: int = 0) -> dict:
    return free_fall(1.0, seed=seed)


def contact_pairs(
    n_pairs: int,
    deep: set[int],
    *,
    deep_frames: int = 20,
    frames: int = 20,
    fps: float = 10.0,
    deep_overlap: float = 0.6,
    shallow: float = 0.05,
) -> dict:
    """Pairs of equal spheres (r = 0.1) in static contact, 5 m apart; `overlap` = (2r - d) / 2r, so d = 2r (1 - overlap).
    Pairs in `deep` overlap by `deep_overlap` in the first `deep_frames` frames and by `shallow` otherwise; the others always `shallow`."""
    r = 0.1
    pos = np.zeros((frames, 2 * n_pairs, 3))
    for k in range(n_pairs):
        pos[:, 2 * k, 0] = 5.0 * k
        for f in range(frames):
            ov = deep_overlap if (k in deep and f < deep_frames) else shallow
            pos[f, 2 * k + 1, 0] = 5.0 * k + 2 * r * (1 - ov)
    return _state(pos, fps=fps, radius=r)


def lattice(
    n_frozen: int,
    *,
    frames: int = 90,
    fps: float = 30.0,
    frozen_frames: int | None = None,
    seed: int = 0,
    extra_rest: int = 0,
) -> dict:
    """200 particles on a 20 x 10 lattice (pitch 0.09 m, radius 0.05: lattice neighbours lie within two radii). Moving particles
    oscillate by 0.01 m in y (period 2 s, random phase); `n_frozen` random ones keep exactly their initial position for the first
    `frozen_frames` frames (all frames by default). `extra_rest` extra particles rest 5 m away from the lattice (their neighbours rest too)."""
    rng = np.random.default_rng(seed)
    n = 200
    base = np.stack([(np.arange(n) % 20) * 0.09, (np.arange(n) // 20) * 0.09, np.zeros(n)], axis=1)
    phase = rng.uniform(0, 2 * np.pi, n)
    t = np.arange(frames) / fps
    pos = np.repeat(base[None, :, :], frames, axis=0)
    pos[:, :, 1] += 0.01 * np.sin(2 * np.pi * t[:, None] / 2.0 + phase[None, :])
    frozen = (
        np.arange(n_frozen) * 23
    ) % n  # stride 23 (coprime with 200): no two frozen particles are lattice neighbours up to 60
    ff = frames if frozen_frames is None else frozen_frames
    pos[:ff, frozen, :] = base[None, frozen, :]
    if extra_rest:
        rest = np.stack(
            [5.0 + (np.arange(extra_rest) % 10) * 0.09, (np.arange(extra_rest) // 10) * 0.09, np.zeros(extra_rest)],
            axis=1,
        )
        pos = np.concatenate([pos, np.repeat(rest[None, :, :], frames, axis=0)], axis=1)
    return _state(pos, fps=fps)


def permuted(sim: dict, seed: int) -> dict:
    perm = np.random.default_rng(seed).permutation(sim["pos"].shape[1])
    out = dict(sim)
    out["pos"] = sim["pos"][:, perm, :]
    out["radius"] = sim["radius"][perm]
    out["mass"] = sim["mass"][:, perm]
    return out


def _trig(sim: dict, name: str) -> bool:
    return bool(pl.detect(sim)[name]["triggered"])


def _only(sim: dict) -> set[str]:
    return {k for k, v in pl.detect(sim).items() if v["triggered"]}


# ------------------------------------------------------------------------------------------------ the six detectors
@pytest.mark.req("FR-015-34")
def test_the_corruption_names_follow_the_contract() -> None:
    assert tuple(pl.CORRUPTIONS) == CORR


@pytest.mark.req("FR-015-34")
@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        (0.30, True),
        (0.29, True),
        (0.31, True),
        (0.286, True),
        (0.314, True),
        (0.28, False),
        (0.32, False),
        (0.5, False),
        (1.0, False),
    ],
)
def test_gravity_detector_fits_the_free_fall_acceleration_within_5_percent_of_0_3_g(
    ratio: float, expected: bool
) -> None:
    d = pl.detect(free_fall(ratio))["gravity-x0.3"]
    assert d["statistic"] == "fitted_g_ratio"
    assert d["value"] == pytest.approx(ratio, rel=2e-3)  # the generating ratio, fitted from the positions
    assert bool(d["triggered"]) is expected
    assert d["sustained_s"] is None


@pytest.mark.req("FR-015-34")
def test_gravity_detector_tolerates_measurement_noise() -> None:
    d = pl.detect(free_fall(0.3, noise=1e-3, seed=4))["gravity-x0.3"]
    assert d["value"] == pytest.approx(0.3, rel=2e-2)
    assert d["triggered"]


@pytest.mark.req("FR-015-34")
@pytest.mark.parametrize(("angle", "expected"), [(3.0, True), (4.5, True), (5.5, False), (30.0, False), (36.0, False)])
def test_zero_friction_detector_flags_a_repose_angle_below_5_degrees(angle: float, expected: bool) -> None:
    d = pl.detect(free_fall(1.0, repose=angle))["zero-friction"]
    assert d["statistic"] == "repose_angle_deg"
    assert d["value"] == pytest.approx(angle)
    assert bool(d["triggered"]) is expected


def _with_injection(n_new: int, *, inflow: bool = False, n: int = 100, frames: int = 60) -> dict:
    mass = np.ones((frames, n + n_new))
    mass[:, n:] = 0.0
    mass[20:, n:] = 1.0  # n_new particles of 1 kg appear at frame 20 and stay
    base = free_fall(1.0, n=n + n_new, frames=frames, mass=mass, inflow=inflow)
    return base


@pytest.mark.req("FR-015-34")
@pytest.mark.parametrize(
    ("n_new", "expected_pct", "expected"),
    [(0, 0.0, False), (4, 4.0, False), (5, 5.0, True), (10, 10.0, True), (50, 50.0, True)],
)
def test_mass_detector_flags_a_total_mass_increase_of_5_percent_without_an_inflow_boundary(
    n_new: int, expected_pct: float, expected: bool
) -> None:
    d = pl.detect(_with_injection(n_new))["mass-injection"]
    assert d["statistic"] == "mass_increase_pct"
    assert d["value"] == pytest.approx(expected_pct, abs=1e-9)  # 100 kg initially: n_new kg added is n_new %
    assert bool(d["triggered"]) is expected


@pytest.mark.req("FR-015-34")
def test_mass_detector_ignores_a_mass_increase_through_a_declared_inflow_boundary() -> None:
    assert not _trig(_with_injection(10, inflow=True), "mass-injection")


@pytest.mark.req("FR-015-34")
def test_time_reversal_detector_needs_the_frame_order_to_be_exactly_reversed() -> None:
    sim = calibrated()
    t = sim["pos"].shape[0]
    rev = pl.reverse_time(sim)
    assert np.array_equal(rev["frame_order"], np.arange(t)[::-1])
    d = pl.detect(rev)["time-reversal"]
    assert (d["statistic"], d["value"], d["triggered"]) == ("reversed_frame_fraction", 1.0, True)
    assert not _trig(sim, "time-reversal")
    swapped = dict(sim, frame_order=np.array([1, 0, *range(2, t)]))  # one swap is not a reversal
    assert not _trig(swapped, "time-reversal")
    half = dict(sim, frame_order=np.concatenate([np.arange(t // 2)[::-1], np.arange(t // 2, t)]))
    assert not _trig(half, "time-reversal")


@pytest.mark.req("FR-015-34")
@pytest.mark.parametrize(
    ("n_deep", "expected"),
    [(0, False), (9, False), (10, True), (11, True), (20, True), (100, True)],
)
def test_interpenetration_detector_needs_at_least_10_percent_of_contacts_deeper_than_half_the_radius_sum(
    n_deep: int, expected: bool
) -> None:
    sim = contact_pairs(100, set(range(n_deep)))
    d = pl.detect(sim)["interpenetration"]
    assert d["statistic"] == "deep_overlap_contact_fraction"
    assert d["value"] == pytest.approx(n_deep / 100)
    assert bool(d["triggered"]) is expected
    if expected:
        assert d["sustained_s"] >= 1.0


@pytest.mark.req("FR-015-34")
@pytest.mark.parametrize(("overlap", "expected"), [(0.45, False), (0.55, True), (0.9, True)])
def test_interpenetration_overlap_threshold_is_half_the_radius_sum(overlap: float, expected: bool) -> None:
    assert _trig(contact_pairs(100, set(range(30)), deep_overlap=overlap), "interpenetration") is expected


@pytest.mark.req("FR-015-34")
@pytest.mark.parametrize(("deep_frames", "expected"), [(20, True), (15, True), (5, False), (0, False)])
def test_interpenetration_must_last_at_least_one_second(deep_frames: int, expected: bool) -> None:
    sim = contact_pairs(
        100, set(range(30)), deep_frames=deep_frames, frames=20, fps=10.0
    )  # 10 frames per second: 15 frames = 1.5 s
    assert _trig(sim, "interpenetration") is expected


@pytest.mark.req("FR-015-34")
@pytest.mark.parametrize(("n_frozen", "expected"), [(0, False), (8, False), (10, True), (12, True), (60, True)])
def test_frozen_detector_needs_at_least_5_percent_of_particles_still_for_1_s_while_neighbours_move(
    n_frozen: int, expected: bool
) -> None:
    d = pl.detect(lattice(n_frozen))["frozen-particles"]
    assert d["statistic"] == "frozen_particle_fraction"
    assert d["value"] == pytest.approx(n_frozen / 200)
    assert bool(d["triggered"]) is expected
    if expected:
        assert d["sustained_s"] >= 1.0


@pytest.mark.req("FR-015-34")
@pytest.mark.parametrize(("frozen_frames", "expected"), [(90, True), (45, True), (15, False)])
def test_frozen_particles_must_stay_still_for_one_second(frozen_frames: int, expected: bool) -> None:
    assert _trig(lattice(20, frozen_frames=frozen_frames), "frozen-particles") is expected  # 30 frames per second


@pytest.mark.req("FR-015-34")
def test_particles_at_rest_among_particles_at_rest_are_not_frozen_particles() -> None:
    sim = lattice(0, extra_rest=120)  # 120 of 320 particles rest, 5 m from the moving lattice: no moving neighbour
    d = pl.detect(sim)["frozen-particles"]
    assert d["value"] == pytest.approx(0.0)
    assert not d["triggered"]


@pytest.mark.req("FR-015-34")
@pytest.mark.parametrize("seed", range(5))
def test_a_calibrated_clip_triggers_none_of_the_six_detectors(seed: int) -> None:
    assert _only(calibrated(seed)) == set()
    assert _only(free_fall(1.0, seed=seed, repose=34.0)) == set()
    assert _only(contact_pairs(100, set())) == set()
    assert _only(lattice(0, seed=seed)) == set()


@pytest.mark.req("FR-015-34")
@pytest.mark.parametrize(
    ("builder", "name"),
    [
        (lambda: free_fall(0.3), "gravity-x0.3"),
        (lambda: free_fall(1.0, repose=2.0), "zero-friction"),
        (lambda: _with_injection(10), "mass-injection"),
        (lambda: pl.reverse_time(calibrated()), "time-reversal"),
        (lambda: contact_pairs(100, set(range(20))), "interpenetration"),
        (lambda: lattice(20), "frozen-particles"),
    ],
    ids=CORR,
)
def test_each_corrupted_state_triggers_its_own_detector_and_no_other(builder, name: str) -> None:
    assert _only(builder()) == {name}


# ------------------------------------------------------------------------------------------------ P-015-10
@pytest.mark.req("P-015-10")
@pytest.mark.parametrize("seed", range(3))
def test_mr1_time_reversal_is_an_involution(seed: int) -> None:
    sim = free_fall(0.7, seed=seed, n=12, frames=33)
    once = pl.reverse_time(sim)
    assert not np.array_equal(once["pos"], sim["pos"])
    twice = pl.reverse_time(once)
    assert np.array_equal(twice["pos"], sim["pos"])
    assert np.array_equal(twice["frame_order"], sim["frame_order"])
    assert np.array_equal(once["pos"], sim["pos"][::-1])


def _toy_simulate(initial: dict, *, gravity_scale: float = 1.0) -> dict:
    """A deterministic stand-in for the physics runner: ballistic motion from the initial state under g0 * gravity_scale."""
    t = np.arange(initial["frames"]) / initial["fps"]
    pos = np.repeat(initial["pos0"][None, :, :], initial["frames"], axis=0).copy()
    pos[:, :, 2] += initial["v0"][None, :] * t[:, None] - 0.5 * G0 * gravity_scale * t[:, None] ** 2
    return _state(pos, fps=initial["fps"])


def _initial() -> dict:
    rng = np.random.default_rng(3)
    return {
        "frames": 60,
        "fps": 30.0,
        "pos0": np.add(rng.uniform(0.0, 10.0, (25, 3)), [0, 0, 60]),
        "v0": rng.uniform(-2, 2, 25),
    }


@pytest.mark.req("P-015-10")
def test_mr2_the_identity_corruption_reproduces_the_calibrated_clip_bit_exactly() -> None:
    initial = _initial()
    calibrated_run = _toy_simulate(initial, gravity_scale=1.0)
    identity = pl.make_corrupted(_toy_simulate, initial, "gravity-x0.3", scale=1.0)
    assert np.array_equal(identity["pos"], calibrated_run["pos"])  # bit-exact
    corrupted = pl.make_corrupted(_toy_simulate, initial, "gravity-x0.3")
    assert not np.array_equal(corrupted["pos"], calibrated_run["pos"])
    assert pl.detect(corrupted)["gravity-x0.3"]["value"] == pytest.approx(0.3, rel=2e-3)


@pytest.mark.req("P-015-10")
def test_the_time_reversal_corruption_reverses_the_calibrated_run_and_unknown_names_are_refused() -> None:
    initial = _initial()
    rev = pl.make_corrupted(_toy_simulate, initial, "time-reversal")
    assert np.array_equal(rev["pos"], _toy_simulate(initial)["pos"][::-1])
    for bad in ("", "gravity", "gravity-x0.5", "Gravity-x0.3", "mass injection"):
        with pytest.raises(ValueError):  # noqa: PT011
            pl.make_corrupted(_toy_simulate, initial, bad)


BUILDERS = [
    lambda: free_fall(0.3),
    lambda: free_fall(1.0),
    lambda: free_fall(1.0, repose=2.0),
    lambda: _with_injection(10),
    lambda: pl.reverse_time(calibrated()),
    lambda: contact_pairs(100, set(range(20))),
    lambda: lattice(20),
    lambda: lattice(8),
]


@pytest.mark.req("P-015-10")
@settings(max_examples=30, deadline=None)
@given(st.sampled_from(range(len(BUILDERS))), st.integers(0, 10_000))
def test_mr3_every_detector_is_invariant_under_a_permutation_of_the_particle_ids(idx: int, seed: int) -> None:
    sim = BUILDERS[idx]()
    a, b = pl.detect(sim), pl.detect(permuted(sim, seed))
    for name in CORR:
        assert b[name]["triggered"] == a[name]["triggered"]
        assert b[name]["value"] == pytest.approx(a[name]["value"], rel=1e-9, abs=1e-12)
        assert b[name]["sustained_s"] == a[name]["sustained_s"] or b[name]["sustained_s"] == pytest.approx(
            a[name]["sustained_s"]
        )


# ------------------------------------------------------------------------------------------------ pair confirmation
def _conf_errors(conf: dict) -> list[str]:
    from jsonschema import Draft202012Validator

    base = contracts.validator("plausibility-pairs.schema.json").schema["$id"]
    v = Draft202012Validator({"$ref": base + "#/$defs/confirmation"}, registry=contracts._registry())
    return [e.message for e in v.iter_errors(conf)]


@pytest.mark.req("FR-015-34")
def test_confirm_pair_reports_the_statistic_of_the_corruption_and_the_clean_calibrated_run() -> None:
    conf = pl.confirm_pair(calibrated(), free_fall(0.3), "gravity-x0.3")
    assert conf["statistic"] == "fitted_g_ratio"
    assert conf["value"] == pytest.approx(0.3, rel=2e-3)
    assert conf["sustained_s"] is None
    assert (conf["own_detector_triggered"], conf["calibrated_detectors_clear"]) == (True, True)
    assert _conf_errors(conf) == []
    conf2 = pl.confirm_pair(lattice(0), lattice(20), "frozen-particles")
    assert conf2["statistic"] == "frozen_particle_fraction"
    assert conf2["value"] == pytest.approx(0.1)
    assert conf2["sustained_s"] >= 1.0
    assert _conf_errors(conf2) == []


@pytest.mark.req("FR-015-34")
def test_confirm_pair_flags_a_corruption_that_its_own_detector_misses_and_a_calibrated_clip_that_triggers() -> None:
    weak = pl.confirm_pair(calibrated(), free_fall(0.5), "gravity-x0.3")  # 0.5 g is not 0.3 g
    assert weak["own_detector_triggered"] is False
    bad_cal = pl.confirm_pair(
        free_fall(0.3), free_fall(0.3, seed=1), "gravity-x0.3"
    )  # the "calibrated" clip is itself corrupted
    assert bad_cal["calibrated_detectors_clear"] is False
    two = pl.confirm_pair(
        free_fall(1.0, repose=2.0), free_fall(0.3), "gravity-x0.3"
    )  # calibrated trips the zero-friction detector
    assert two["calibrated_detectors_clear"] is False


# ------------------------------------------------------------------------------------------------ pair documents
def _clip(i: int, kind: str, **kw) -> dict:
    return {
        "asset_id": f"clip-{i:03d}-{kind}",
        "path": f"data/reason/task_b/{i:03d}/{kind}.mp4",
        "sha256": kit.sha256_hex(f"{i}-{kind}".encode()),
        "duration_s": kw.get("duration_s", 6.0),
        "frame_count": kw.get("frame_count", 180),
        "fps": 30.0,
        "camera_id": kw.get("camera_id", "cam-dump-02"),
        "scene_id": kw.get("scene_id", "truck-dump-s07"),
    }


_CONF = {
    "gravity-x0.3": ("fitted_g_ratio", 0.301, None),
    "zero-friction": ("repose_angle_deg", 3.2, None),
    "mass-injection": ("mass_increase_pct", 8.5, None),
    "time-reversal": ("reversed_frame_fraction", 1.0, None),
    "interpenetration": ("deep_overlap_contact_fraction", 0.15, 1.8),
    "frozen-particles": ("frozen_particle_fraction", 0.08, 2.5),
}


def make_pair(i: int, corruption: str, **kw) -> dict:
    stat, value, sustained = _CONF[corruption]
    return {
        "pair_id": f"pair-{i:03d}",
        "scenario": ["muck-pile-formation", "truck-dump", "bench-collapse"][i % 3],
        "source_run_id": "20261009T020000Z-a1",
        "corruptions": kw.get("corruptions", [corruption]),
        "calibrated": _clip(i, "calibrated", **kw.get("cal", {})),
        "corrupted": _clip(i, "corrupted", **kw.get("cor", {})),
        "confirmation": {
            "statistic": stat,
            "value": value,
            "sustained_s": sustained,
            "own_detector_triggered": kw.get("own", True),
            "calibrated_detectors_clear": kw.get("clear", True),
        },
    }


def _hundred() -> list[dict]:
    plan = [CORR[i % 6] for i in range(100)]  # 100 = 6 x 16 + 4: four corruptions get 17 pairs
    return [make_pair(i + 1, c) for i, c in enumerate(plan)]


@pytest.mark.req("FR-015-33")
def test_a_valid_pair_set_has_100_pairs_with_16_or_17_per_corruption_and_exactly_one_corruption_each() -> None:
    cands = _hundred()
    out = pl.build_pair_set(cands, regenerate=lambda c, a: pytest.fail("nothing to regenerate"), seed=20261008)
    assert len(out.pairs) == 100
    counts = Counter(p["corruptions"][0] for p in out.pairs)
    assert set(counts) == set(CORR)
    assert all(v in (16, 17) for v in counts.values()), counts
    assert all(len(p["corruptions"]) == 1 for p in out.pairs)
    assert out.excluded == []
    doc = out.to_document()
    assert contracts.errors(doc, "plausibility-pairs.schema.json") == []
    assert [p["pair_id"] for p in doc["pairs"]] == [p["pair_id"] for p in cands]


@pytest.mark.req("FR-015-33")
def test_the_valid_pairs_of_the_spec_example_are_acceptable() -> None:
    doc = json.loads(
        (kit.SPEC015 / "contracts" / "examples" / "plausibility-pairs.valid.json").read_text(encoding="utf-8")
    )
    for p in doc["pairs"]:
        assert pl.check_pair(p) == []


@pytest.mark.req("FR-015-35")
@pytest.mark.parametrize(
    ("name", "pair"),
    [
        ("detector-not-triggered", make_pair(1, "gravity-x0.3", own=False)),
        ("calibrated-triggers-a-detector", make_pair(1, "gravity-x0.3", clear=False)),
        ("no-corruption", make_pair(1, "gravity-x0.3", corruptions=[])),
        ("two-corruptions", make_pair(1, "gravity-x0.3", corruptions=["gravity-x0.3", "zero-friction"])),
        ("unknown-corruption", make_pair(1, "gravity-x0.3", corruptions=["gravity-x0.5"])),
        ("scene-differs", make_pair(1, "gravity-x0.3", cor={"scene_id": "bench-collapse-s02"})),
        ("camera-differs", make_pair(1, "gravity-x0.3", cor={"camera_id": "cam-dump-03"})),
        ("duration-differs", make_pair(1, "gravity-x0.3", cor={"duration_s": 7.5})),
        ("frame-count-differs", make_pair(1, "gravity-x0.3", cor={"frame_count": 179})),
        ("duration-too-short", make_pair(1, "gravity-x0.3", cal={"duration_s": 4.0}, cor={"duration_s": 4.0})),
        ("duration-too-long", make_pair(1, "gravity-x0.3", cal={"duration_s": 9.0}, cor={"duration_s": 9.0})),
        (
            "statistic-out-of-range",
            {
                **make_pair(1, "gravity-x0.3"),
                "confirmation": {**make_pair(1, "gravity-x0.3")["confirmation"], "value": 0.5},
            },
        ),
        (
            "wrong-statistic-for-the-corruption",
            {**make_pair(1, "gravity-x0.3"), "confirmation": {**make_pair(1, "zero-friction")["confirmation"]}},
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_a_pair_that_fails_confirmation_declares_other_than_one_corruption_or_has_unequal_clips_is_not_acceptable(
    name: str, pair: dict
) -> None:
    reasons = pl.check_pair(pair)
    assert reasons, name
    assert all(isinstance(r, str) and r for r in reasons)


_HOSTILE = sorted((kit.SPEC015 / "contracts" / "examples").glob("plausibility-pairs.hostile-*.json"))


@pytest.mark.req("FR-015-35")
@pytest.mark.parametrize(
    "path", [p for p in _HOSTILE if "empty" not in p.name], ids=[p.stem for p in _HOSTILE if "empty" not in p.name]
)
def test_every_hostile_pair_of_the_spec_corpus_is_not_acceptable(path: Path) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert any(pl.check_pair(p) for p in doc["pairs"])


@pytest.mark.req("FR-015-35")
def test_excluded_pairs_are_replaced_by_regenerated_pairs_of_the_same_corruption_before_any_query() -> None:
    cands = _hundred()
    bad_idx = {5: cands[5]["corruptions"][0], 40: cands[40]["corruptions"][0], 77: cands[77]["corruptions"][0]}
    for i in bad_idx:
        cands[i] = make_pair(i + 1, bad_idx[i], own=False)
    calls: list[tuple[str, int]] = []

    def regenerate(corruption: str, attempt: int) -> dict:
        calls.append((corruption, attempt))
        # the first replacement of an interpenetration pair is bad again (calibrated detectors not clear): the slot is regenerated
        bad = corruption == "interpenetration" and attempt == 1
        return make_pair(200 + len(calls), corruption, clear=not bad)

    out = pl.build_pair_set(cands, regenerate=regenerate, seed=1)
    assert len(out.pairs) == 100
    assert bad_idx == {
        5: "frozen-particles",
        40: "interpenetration",
        77: "frozen-particles",
    }  # hand check of the plan above
    assert Counter(calls) == {("frozen-particles", 1): 2, ("interpenetration", 1): 1, ("interpenetration", 2): 1}
    assert {pid for pid, _ in out.excluded} >= {cands[i]["pair_id"] for i in bad_idx}
    assert all(reasons for _, reasons in out.excluded)
    assert all(pl.check_pair(p) == [] for p in out.pairs)
    counts = Counter(p["corruptions"][0] for p in out.pairs)
    assert all(v in (16, 17) for v in counts.values())
    assert counts == Counter(
        c["corruptions"][0] for c in _hundred()
    )  # same corruption per slot, so the same allocation
    assert contracts.errors(out.to_document(), "plausibility-pairs.schema.json") == []
    ids = [p["pair_id"] for p in out.pairs]
    assert len(set(ids)) == 100
    assert all(cands[i]["pair_id"] not in ids for i in bad_idx)


@pytest.mark.req("FR-015-35")
def test_a_pair_set_without_excluded_pairs_never_calls_the_regenerator() -> None:
    cands = copy.deepcopy(_hundred())
    pl.build_pair_set(cands, regenerate=lambda c, a: pytest.fail("called"), seed=0)

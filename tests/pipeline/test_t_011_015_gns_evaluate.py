"""T-011-015 - FR-011-06, FR-011-10, SC-011-01 (and the divergence and overflow reporting of FR-011-12 / FR-011-13):
held-out evaluation, rest check, acceptance statement.

Oracles (independent of the code under test; plan 011 test strategy FR-011-06 / FR-011-10 / SC-011-01: "fixture
    rollouts with known
theta and L and one not at rest", "report logic on fixture results that pass and fail by construction"):
- analytic clouds with known observables: a flank of exact slope theta (surface points every d / 8, d / 2 below the
    analytic free
  surface, H = 40 d; the extractor error is <= 0.1 deg for such a cloud, see
      tests/property/test_t_011_013_observables.py) plus 60
  particles on the floor at one abscissa x_tail (6 % of the cloud, so the 99th percentile of x is x_tail under
      every percentile
  definition). Collapse family: L = x_tail - L0; pile family: L = (x_right - x_left) / 2 with the pour point at 0;
      dump family:
  L = x_tail - x_crest. Reference packings theta = (30, 33, 36) deg with tails (1.00, 1.10, 1.20) give mean theta
      33 deg and mean
  L = 1.10 - 0.2 = 0.90 m (collapse, L0 = 0.2 m);
- hand deltas: a surrogate whose three packings have theta + 1.0 deg and tails + 0.03 m gives |dtheta| = 1.0 deg
    and |dL| / L =
  0.03 / 0.90 = 0.0333 (pass: <= 1.5 deg and <= 5 %); theta + 2.0 deg or tails + 0.06 m (0.0667) fail; the
      tolerance on the deltas is
  0.25 deg and 0.002 for the extractor resolution;
- the rest rule of FR-011-10: a packing is at rest iff the maximum particle speed over the last frame interval is below
  0.01 sqrt(g d) = 0.01 x sqrt(9.81 x 0.004) = 0.0019809 m/s, i.e. a displacement of 1.98e-5 m per 0.01 s frame; a
      particle moving
  2.5e-5 m in the last frame (0.0025 m/s) is not at rest, 1.5e-5 m (0.0015 m/s) is;
- position error growth by hand: a surrogate equal to the reference shifted by 1e-3 t m in x at step t has mean
    position error
  1e-3 t m at step t.

Expected public API (module `pitstudio_pipeline.surrogates.gns.evaluate`, package under `pipeline/src/`):

    evaluate_held_out(geometries, surrogate, *, expected=None, dataset_manifest=None, g=9.81) -> dict
        (`expected` and `dataset_manifest` are specified by T-011-096 and T-011-095; with their defaults the set is
            complete and not a fixture)
        geometries: list of {"geometry_id", "family", "geometry" (DC-011-01 geometry parameters used by the observables:
        column_width_m | pour_point_x_m | crest_x_m), "d", "dt", "bounds" [4], "references": [{"seed": int,
            "positions": float array
        [T, N, 2] (frames; the last one is the rest frame T_end), "particle_types": [N]}, ...]} with at least 3
            reference packings
        (more are spares used for FR-011-10 replacements, in seed order).
        surrogate(initial_state, n_steps) -> object with attributes positions [n_steps + 1, N, 2] (or fewer when
            diverged), status
        ("ok" | "diverged"), diverged_at_step, overflow_counts (list of int); initial_state is a dict with
            geometry_id, seed, positions
        (frame 0), velocities (zeros [N, 5, 2]), particle_type, bounds, d, dt.
        Returns a report dict:
          "geometries": list, per geometry {"geometry_id", "family", "used_seeds", "replacements",
              "reference_repose_deg",
            "reference_runout_m", "surrogate_repose_deg", "surrogate_runout_m", "delta_repose_deg" (|.|),
                "delta_runout_rel" (|.|),
            "pass" (bool), "reference_spread": {"repose_deg": {"range", "sd"}, "runout_m": {"range", "sd"}},
            "position_error_growth" (list of floats, one per step 0 ... T_end, mean over packings and particles of
                the Euclidean
            position error), "particle_count_per_step" (list of int), "overflow_count" (int, summed over packings
                and steps),
            "neighbour_overflow" (bool), "diverged" (bool), "diverged_at_step" (int | None), "reason" (str | None)},
          "replacements_total", "n_geometries", "all_pass" (bool), "sc_011_01" ("pass" | "fail"), "status" ("complete").
        A diverged surrogate packing fails its geometry (deltas None, reason "diverged at step s"); a geometry
            without 3 at-rest reference
        packings fails with a reason containing "at rest".
"""

from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.gns import evaluate  # noqa: E402

D = 0.004
DT = 0.01
L0 = 0.2
G = 9.81
REST_SPEED = 0.01 * math.sqrt(G * D)  # 0.0019809 m/s
FRAMES = 4


def flank(theta_deg: float, x0: float, sign: int, h: float = 40 * D, n: int = 700) -> np.ndarray:
    """n surface points on a flank of slope theta (the same count for every theta: packings of a geometry share N)."""
    th = math.radians(theta_deg)
    step = (h - D) / math.sin(th) / n  # spacing along the slope, <= 0.12 D for theta in [30, 36] deg
    xs = x0 + sign * (np.arange(n) + 0.37) * step * math.cos(th)
    ys = h - math.tan(th) * np.abs(xs - x0) - D / 2
    return np.column_stack([xs, ys])


def tail(x: float, n: int = 60) -> np.ndarray:
    return np.column_stack([np.full(n, x), np.full(n, D / 2)])


def cloud(family: str, theta: float, x_far: float, x_left: float = -1.0) -> np.ndarray:
    if family == "column-collapse":
        return np.vstack([flank(theta, 0.0, +1), tail(x_far)])
    if family == "pile-formation":
        return np.vstack([flank(theta, 0.0, +1), flank(theta, 0.0, -1), tail(x_far), tail(x_left)])
    plateau = np.column_stack([-(np.arange(1, 30) + 0.37) * D * 0.5, np.full(29, 40 * D - D / 2)])
    return np.vstack([flank(theta, 0.0, +1), plateau, tail(x_far)])


GEOMETRY_PARAMS = {
    "column-collapse": {"column_width_m": L0},
    "pile-formation": {"pour_point_x_m": 0.0},
    "dump-over-crest": {"crest_x_m": 0.0},
}
REF_THETA = (30.0, 33.0, 36.0)
REF_TAIL = (1.00, 1.10, 1.20)


def expected_reference(family: str) -> tuple[float, float]:
    """Hand values (mean theta, mean L) of the three reference packings."""
    mean_theta = float(np.mean(REF_THETA))
    if family == "column-collapse":
        return mean_theta, float(np.mean(REF_TAIL)) - L0
    if family == "pile-formation":
        return mean_theta, float(np.mean([(x + 1.0) / 2.0 for x in REF_TAIL]))  # left tail at -1.0, pour point 0
    return mean_theta, float(np.mean(REF_TAIL))  # dump: x99 - x_crest with the crest at 0


def reference(family: str, seed: int, theta: float, x_far: float, *, last_frame_shift: float = 0.0) -> dict:
    final = cloud(family, theta, x_far).astype(np.float32)
    first = final + np.float32(0.01)
    frames = [first] + [final.copy() for _ in range(FRAMES - 1)]
    if last_frame_shift:
        frames[-1] = frames[-1].copy()
        frames[-1][0, 1] += np.float32(last_frame_shift)
    return {"seed": seed, "positions": np.stack(frames), "particle_types": np.zeros(final.shape[0], dtype=np.int64)}


def geometry(gid: str, family: str, *, spare: bool = True) -> dict:
    refs = [reference(family, 1 + i, REF_THETA[i], REF_TAIL[i]) for i in range(3)]
    if spare:
        refs.append(reference(family, 4, 33.0, 1.10))
    return {
        "geometry_id": gid,
        "family": family,
        "geometry": dict(GEOMETRY_PARAMS[family]),
        "d": D,
        "dt": DT,
        "bounds": [-2.0, 0.0, 3.0, 1.0],
        "references": refs,
    }


class Result:
    def __init__(self, positions, status="ok", diverged_at_step=None, overflow_counts=None):
        self.positions = positions
        self.status = status
        self.diverged_at_step = diverged_at_step
        self.overflow_counts = overflow_counts if overflow_counts is not None else [0] * (len(positions) - 1)


def surrogate_for(plan, *, geom_ids=None):
    """plan: dict (geometry_id) -> function(initial_state, n_steps) -> Result; default = the reference itself."""

    def run(state, n_steps):
        fn = plan.get(state["geometry_id"])
        return fn(state, n_steps) if fn else Result(np.stack([cloud_for(state)] * (n_steps + 1)))

    return run


def cloud_for(state) -> np.ndarray:  # the reference rest frame of the packing (identity surrogate)
    return LOOKUP[(state["geometry_id"], state["seed"])]


LOOKUP: dict = {}


def build(families=(("column-collapse", 8), ("pile-formation", 6), ("dump-over-crest", 6))) -> list[dict]:
    geoms = []
    for family, n in families:
        for k in range(n):
            g = geometry(f"{family[:3]}-{k:02d}", family)
            for r in g["references"]:
                LOOKUP[(g["geometry_id"], r["seed"])] = r["positions"][-1]
            geoms.append(g)
    return geoms


def shifted(delta_theta: float, delta_tail: float):
    """A surrogate whose packings have theta + delta_theta and tails + delta_tail (the family of the geometry from
    the id)."""
    family = {"col": "column-collapse", "pil": "pile-formation", "dum": "dump-over-crest"}

    def run(state, n_steps):
        fam = family[state["geometry_id"][:3]]
        i = state["seed"] - 1 if state["seed"] <= 3 else 1
        final = cloud(fam, REF_THETA[i] + delta_theta, REF_TAIL[i] + delta_tail).astype(np.float32)
        return Result(np.stack([final] * (n_steps + 1)))

    return run


# ------------------------------------------------------------------ FR-011-06 per geometry report


@pytest.mark.req("FR-011-06")
def test_reference_means_over_the_three_packings_are_the_hand_values_for_every_family() -> None:
    geoms = build((("column-collapse", 1), ("pile-formation", 1), ("dump-over-crest", 1)))
    rep = evaluate.evaluate_held_out(geoms, surrogate_for({}))
    for gr in rep["geometries"]:
        theta, length = expected_reference(gr["family"])
        assert gr["reference_repose_deg"] == pytest.approx(theta, abs=0.25)
        assert gr["reference_runout_m"] == pytest.approx(length, abs=0.005)
        assert gr["used_seeds"] == [1, 2, 3]
        assert gr["replacements"] == 0


@pytest.mark.req("FR-011-06")
def test_a_surrogate_equal_to_the_reference_has_zero_deltas_and_passes() -> None:
    geoms = build((("column-collapse", 2), ("pile-formation", 1), ("dump-over-crest", 1)))
    rep = evaluate.evaluate_held_out(geoms, surrogate_for({}))
    for gr in rep["geometries"]:
        assert gr["delta_repose_deg"] == pytest.approx(0.0, abs=1e-9)
        assert gr["delta_runout_rel"] == pytest.approx(0.0, abs=1e-9)
        assert gr["pass"] is True
    assert rep["all_pass"] is True


@pytest.mark.req("FR-011-06")
def test_deltas_are_absolute_differences_of_the_packing_means() -> None:
    geoms = build((("column-collapse", 1),))
    rep = evaluate.evaluate_held_out(geoms, surrogate_for({"col-00": shifted(1.0, 0.03)}))
    gr = rep["geometries"][0]
    assert gr["delta_repose_deg"] == pytest.approx(1.0, abs=0.25)
    assert gr["delta_runout_rel"] == pytest.approx(0.03 / 0.90, abs=0.002)
    assert gr["surrogate_repose_deg"] == pytest.approx(34.0, abs=0.25)
    assert gr["surrogate_runout_m"] == pytest.approx(0.93, abs=0.005)
    below = evaluate.evaluate_held_out(
        build((("column-collapse", 1),)), surrogate_for({"col-00": shifted(-1.0, -0.03)})
    )["geometries"][0]
    assert below["delta_repose_deg"] == pytest.approx(1.0, abs=0.25)  # absolute value, not signed
    assert below["delta_runout_rel"] == pytest.approx(0.03 / 0.90, abs=0.002)


@pytest.mark.req("SC-011-01")
@pytest.mark.parametrize(
    ("d_theta", "d_tail", "passes"),
    [
        (1.0, 0.03, True),
        (2.0, 0.03, False),
        (1.0, 0.06, False),
        (2.0, 0.06, False),
        (0.0, 0.0, True),
        (-1.0, -0.03, True),
    ],
)
def test_a_geometry_passes_only_inside_1_5_degrees_and_5_percent(d_theta: float, d_tail: float, passes: bool) -> None:
    geoms = build((("column-collapse", 1),))
    gr = evaluate.evaluate_held_out(geoms, surrogate_for({"col-00": shifted(d_theta, d_tail)}))["geometries"][0]
    assert gr["pass"] is passes


@pytest.mark.req("SC-011-01")
def test_the_acceptance_statement_needs_every_one_of_the_20_geometries_to_pass() -> None:
    geoms = build()
    assert len(geoms) == 20
    ok = evaluate.evaluate_held_out(
        geoms, surrogate_for({gid: shifted(1.0, 0.03) for gid in (g["geometry_id"] for g in geoms)})
    )
    assert ok["n_geometries"] == 20
    assert ok["all_pass"] is True
    assert ok["sc_011_01"] == "pass"
    assert ok["status"] == "complete"
    plan = {g["geometry_id"]: shifted(1.0, 0.03) for g in geoms}
    plan["dum-03"] = shifted(2.0, 0.03)  # one geometry out of tolerance
    bad = evaluate.evaluate_held_out(geoms, surrogate_for(plan))
    assert bad["all_pass"] is False
    assert bad["sc_011_01"] == "fail"
    assert [g["pass"] for g in bad["geometries"]].count(False) == 1
    assert next(g for g in bad["geometries"] if not g["pass"])["geometry_id"] == "dum-03"


@pytest.mark.req("FR-011-06")
def test_the_reference_packing_spread_is_reported_next_to_the_deltas() -> None:
    gr = evaluate.evaluate_held_out(build((("column-collapse", 1),)), surrogate_for({}))["geometries"][0]
    spread = gr["reference_spread"]
    assert spread["repose_deg"]["range"] == pytest.approx(6.0, abs=0.3)  # packings at 30, 33, 36 deg
    assert spread["runout_m"]["range"] == pytest.approx(0.20, abs=0.005)  # tails 1.00 ... 1.20
    assert spread["repose_deg"]["sd"] > 0.0
    assert spread["runout_m"]["sd"] > 0.0


@pytest.mark.req("FR-011-06")
def test_position_error_growth_per_step_is_reported_by_hand() -> None:
    geoms = build((("column-collapse", 1),))

    def drifting(state, n_steps):
        ref = LOOKUP[(state["geometry_id"], state["seed"])]
        frames = [ref + np.array([1e-3 * t, 0.0], dtype=np.float32) for t in range(n_steps + 1)]
        return Result(np.stack(frames))

    gr = evaluate.evaluate_held_out(geoms, surrogate_for({"col-00": drifting}))["geometries"][0]
    # the reference frames are [shifted first frame, rest, rest, rest]; the error at step t is the distance to
    #   reference frame t
    expected = []
    for t in range(FRAMES):
        errs = []
        for r in geoms[0]["references"][:3]:
            ref_frame = r["positions"][t]
            sur = r["positions"][-1] + np.array([1e-3 * t, 0.0], dtype=np.float32)
            errs.append(np.linalg.norm(sur - ref_frame, axis=1).mean())
        expected.append(float(np.mean(errs)))
    assert gr["position_error_growth"] == pytest.approx(expected, abs=1e-6)
    assert len(gr["position_error_growth"]) == FRAMES


@pytest.mark.req("FR-011-06")
def test_the_particle_count_per_step_is_reported() -> None:
    geoms = build((("column-collapse", 1),))
    gr = evaluate.evaluate_held_out(geoms, surrogate_for({}))["geometries"][0]
    n = geoms[0]["references"][0]["positions"].shape[1]
    assert gr["particle_count_per_step"] == [n] * FRAMES


@pytest.mark.req("FR-011-06")
def test_the_surrogate_is_rolled_out_from_frame_zero_to_t_end_with_zero_velocity_history() -> None:
    geoms = build((("column-collapse", 1),))
    seen = []

    def spy(state, n_steps):
        frame0 = geoms[0]["references"][state["seed"] - 1]["positions"][0]
        seen.append(
            (
                state["geometry_id"],
                state["seed"],
                n_steps,
                state["velocities"].shape,
                float(np.abs(state["velocities"]).max()),
                bool(np.array_equal(state["positions"], frame0)),
            )
        )
        return Result(np.stack([LOOKUP[(state["geometry_id"], state["seed"])]] * (n_steps + 1)))

    evaluate.evaluate_held_out(geoms, spy)
    assert [(s[0], s[1], s[2]) for s in seen] == [
        ("col-00", 1, FRAMES - 1),
        ("col-00", 2, FRAMES - 1),
        ("col-00", 3, FRAMES - 1),
    ]
    n = geoms[0]["references"][0]["positions"].shape[1]
    assert all(s[3] == (n, 5, 2) and s[4] == 0.0 and s[5] for s in seen)


# ------------------------------------------------------------------ FR-011-10 rest rule


def with_unrested(extra_shift: float, bad_index: int = 1, spare_rested: bool = True) -> list[dict]:
    g = geometry("col-00", "column-collapse")
    g["references"][bad_index] = reference(
        "column-collapse",
        g["references"][bad_index]["seed"],
        REF_THETA[bad_index],
        REF_TAIL[bad_index],
        last_frame_shift=extra_shift,
    )
    for r in g["references"]:
        LOOKUP[(g["geometry_id"], r["seed"])] = r["positions"][-1]
    return [g]


@pytest.mark.req("FR-011-10")
def test_a_packing_not_at_rest_is_excluded_replaced_by_the_next_seed_and_counted() -> None:
    assert 2.5e-5 / DT >= REST_SPEED > 1.5e-5 / DT  # the hand thresholds of the docstring
    rep = evaluate.evaluate_held_out(with_unrested(2.5e-5), surrogate_for({}))
    gr = rep["geometries"][0]
    assert gr["used_seeds"] == [1, 3, 4]  # seed 2 moved 0.0025 m/s >= 0.0019809 m/s: replaced by the spare seed 4
    assert gr["replacements"] == 1
    assert rep["replacements_total"] == 1


@pytest.mark.req("FR-011-10")
def test_a_packing_just_below_the_rest_threshold_is_kept() -> None:
    rep = evaluate.evaluate_held_out(with_unrested(1.5e-5), surrogate_for({}))
    gr = rep["geometries"][0]
    assert gr["used_seeds"] == [1, 2, 3]
    assert gr["replacements"] == 0


@pytest.mark.req("FR-011-10")
def test_without_enough_at_rest_packings_the_geometry_fails_with_a_reason() -> None:
    g = geometry("col-00", "column-collapse", spare=False)
    g["references"][2] = reference("column-collapse", 3, REF_THETA[2], REF_TAIL[2], last_frame_shift=5e-5)
    for r in g["references"]:
        LOOKUP[(g["geometry_id"], r["seed"])] = r["positions"][-1]
    gr = evaluate.evaluate_held_out([g], surrogate_for({}))["geometries"][0]
    assert gr["pass"] is False
    assert "at rest" in gr["reason"]


# ------------------------------------------------------------------ FR-011-12 / FR-011-13 reporting


@pytest.mark.req("FR-011-12")
def test_a_diverged_surrogate_rollout_fails_its_geometry_and_reports_the_step() -> None:
    geoms = build((("column-collapse", 2),))

    def diverge(state, n_steps):
        ref = LOOKUP[(state["geometry_id"], state["seed"])]
        return Result(np.stack([ref] * 2), status="diverged", diverged_at_step=17)

    rep = evaluate.evaluate_held_out(geoms, surrogate_for({"col-01": diverge}))
    bad = next(g for g in rep["geometries"] if g["geometry_id"] == "col-01")
    assert bad["pass"] is False
    assert bad["diverged"] is True
    assert bad["diverged_at_step"] == 17
    assert bad["reason"] == "diverged at step 17"
    assert bad["delta_repose_deg"] is None
    assert bad["delta_runout_rel"] is None
    assert next(g for g in rep["geometries"] if g["geometry_id"] == "col-00")["pass"] is True
    assert rep["sc_011_01"] == "fail"


@pytest.mark.req("FR-011-13")
def test_neighbour_overflow_is_counted_and_flagged_without_changing_the_verdict() -> None:
    geoms = build((("column-collapse", 1),))

    def overflowing(state, n_steps):
        ref = LOOKUP[(state["geometry_id"], state["seed"])]
        counts = [0] * n_steps
        counts[1] = 4
        return Result(np.stack([ref] * (n_steps + 1)), overflow_counts=counts)

    gr = evaluate.evaluate_held_out(geoms, surrogate_for({"col-00": overflowing}))["geometries"][0]
    assert gr["overflow_count"] == 12  # 4 particles in one step, for each of the 3 packings
    assert gr["neighbour_overflow"] is True
    assert gr["pass"] is True


@pytest.mark.req("FR-011-13")
def test_no_overflow_means_no_flag() -> None:
    gr = evaluate.evaluate_held_out(build((("column-collapse", 1),)), surrogate_for({}))["geometries"][0]
    assert gr["overflow_count"] == 0
    assert gr["neighbour_overflow"] is False


# ------------------------------------------------------------------ hostile inputs


@pytest.mark.req("FR-011-06")
def test_hostile_geometry_lists_are_refused() -> None:
    geoms = build((("column-collapse", 1),))
    with pytest.raises(ValueError, match=r"."):
        evaluate.evaluate_held_out([], surrogate_for({}))
    short = copy.deepcopy(geoms)
    short[0]["references"] = short[0]["references"][:2]
    with pytest.raises(ValueError, match=r"."):
        evaluate.evaluate_held_out(short, surrogate_for({}))
    unknown = copy.deepcopy(geoms)
    unknown[0]["family"] = "landslide"
    with pytest.raises(ValueError, match="family"):
        evaluate.evaluate_held_out(unknown, surrogate_for({}))
    nan = copy.deepcopy(geoms)
    nan[0]["references"][0]["positions"] = nan[0]["references"][0]["positions"].copy()
    nan[0]["references"][0]["positions"][-1, 3, 0] = np.nan
    with pytest.raises(ValueError, match=r"."):
        evaluate.evaluate_held_out(nan, surrogate_for({}))


@pytest.mark.req("FR-011-06")
def test_a_surrogate_that_changes_the_particle_count_is_refused() -> None:
    geoms = build((("column-collapse", 1),))

    def wrong(state, n_steps):
        ref = LOOKUP[(state["geometry_id"], state["seed"])]
        return Result(np.stack([ref[:-1]] * (n_steps + 1)))

    with pytest.raises(ValueError, match="particle"):
        evaluate.evaluate_held_out(geoms, surrogate_for({"col-00": wrong}))

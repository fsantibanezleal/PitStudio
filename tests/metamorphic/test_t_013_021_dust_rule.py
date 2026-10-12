# ruff: noqa: E501, PT018
"""T-013-021: detection rule, leading-edge dust returns and the dust-rule relations.

Requirements: FR-013-12, FR-013-13, P-013-03, P-013-04, P-013-05, P-013-06, SC-013-01.

Oracle: the rule of FR-013-12 and FR-013-13 implemented in `sensor_kit.dust_reference` straight from the spec text (the
thresholds tau_on = 0.3216, tau_floor(retro) = 3.9120, tau_floor(diffuse) = 2.8134 of Phillips, Guenther and McAree 2017, the
linear keep law in u, the leading edge at the first sample above 1e-6 m^-1), the hash of FR-013-14 from the published
MurmurHash3 reference (`sensor_kit.beam_u_ref`), hand-computed edge positions, and the metamorphic relations P-013-03 to
P-013-05; P-013-06 compares the kept fractions of 10^5 beams with the reference hash (the midway fraction is
0.5 +/- 0.0063, four binomial standard deviations).

Expected API: `pitstudio.sensors.dust.apply_dust(...)` and its `DustResult` as in test_t_013_020 (row-aligned `tau`, `u`,
`kept`, `intensity`, `emit_dust`, `r_edge`, and the output `cloud`); `r_edge` is NaN where no dust return is emitted; a dust return
has the position of the input return scaled by `r_edge / range`, `range_m = r_edge`, intensity `dust_return_intensity` and
`material_class` "dust".
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
import sensor_kit as kit  # noqa: E402
from pitstudio.sensors import dust  # noqa: E402

TAU_ON, FLOOR = kit.TAU_ON, kit.TAU_FLOOR
R = 50.0


def _rows(n: int, material: str, r: float = R, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    d = rng.normal(size=(n, 3))
    return {
        "beam": np.arange(n, dtype=np.uint32),
        "range_m": np.full(n, r),
        "material": np.array([material] * n),
        "intensity": rng.uniform(0.2, 1.0, n),
        "xyz": d / np.linalg.norm(d, axis=1, keepdims=True) * r,
    }


def _apply(
    c: dict, beta, spacing: float = 0.25, *, frame: int = 3, seed: int = 7, max_returns: int = 1, di: float = 0.05
):
    return dust.apply_dust(
        c["beam"],
        c["range_m"],
        c["material"],
        c["intensity"],
        c["xyz"],
        beta,
        spacing,
        frame=frame,
        seed=seed,
        dust_return_intensity=di,
        max_returns=max_returns,
    )


def _layer(tau: float, r: float = R, spacing: float = 0.25) -> np.ndarray:
    return kit.uniform_beta(1, tau / r, r + 10.0, spacing)[0]


TAUS = [
    0.0,
    0.2,
    TAU_ON - 1e-6,
    TAU_ON + 1e-6,
    1.0,
    2.0,
    FLOOR["diffuse"] - 1e-6,
    FLOOR["diffuse"] + 1e-6,
    3.0,
    FLOOR["retro"] - 1e-6,
    3.95,
    FLOOR["retro"] + 1e-6,
    5.0,
]


@pytest.mark.req("FR-013-12")
@pytest.mark.parametrize("material", ["diffuse", "retro"])
@pytest.mark.parametrize("tau", TAUS)
def test_keep_or_drop_matches_the_rule_for_every_beam(tau: float, material: str) -> None:
    c = _rows(1500, material)
    beta = _layer(tau)
    res = _apply(c, beta)
    ref = kit.dust_reference(
        c["beam"], c["range_m"], c["material"], c["intensity"], np.tile(beta, (1500, 1)), 0.25, frame=3, seed=7
    )
    np.testing.assert_array_equal(res.kept, ref["kept"])
    np.testing.assert_array_equal(res.u, ref["u"])  # the hash value of FR-013-14, exactly
    np.testing.assert_allclose(res.tau, ref["tau"], rtol=1e-12, atol=1e-14)


@pytest.mark.req("FR-013-12")
def test_below_the_onset_everything_is_kept_and_above_the_floor_everything_is_dropped() -> None:
    for material, floor in (("diffuse", FLOOR["diffuse"]), ("retro", FLOOR["retro"])):
        c = _rows(3000, material)
        assert _apply(c, _layer(TAU_ON - 1e-6)).kept.all()  # (a) tau <= tau_on: kept whatever u
        assert not _apply(c, _layer(floor + 1e-6)).kept.any()  # (c) tau > tau_floor(m): dropped whatever u


@pytest.mark.req("FR-013-12")
def test_between_onset_and_floor_the_keep_law_is_linear_in_u() -> None:
    """tau = 1.5: keep iff u (2.8134 - 0.3216) < 2.8134 - 1.5, i.e. u < 1.3134 / 2.4918 = 0.52709 (diffuse), by hand."""
    c = _rows(4000, "diffuse")
    res = _apply(c, _layer(1.5))
    threshold = (FLOOR["diffuse"] - 1.5) / (FLOOR["diffuse"] - TAU_ON)
    assert threshold == pytest.approx(0.52709, abs=1e-5)
    np.testing.assert_array_equal(res.kept, res.u < threshold)
    retro = _apply(_rows(4000, "retro"), _layer(1.5))
    np.testing.assert_array_equal(retro.kept, retro.u < (FLOOR["retro"] - 1.5) / (FLOOR["retro"] - TAU_ON))


@pytest.mark.req("FR-013-13")
def test_a_dropped_return_leaves_one_dust_return_at_the_leading_edge_of_the_cloud() -> None:
    """Clean air to 11.75 m, 0.1 m^-1 from the sample at 12.0 m (spacing 0.25): r_edge = 12.0; tau(50 m) = 3.81 > floor."""
    spacing = 0.25
    s = np.arange(0, 70, spacing)
    beta = np.where(s >= 12.0, 0.1, 0.0)
    c = _rows(500, "diffuse")
    res = _apply(c, beta, spacing)
    assert not res.kept.any() and res.emit_dust.all()
    assert np.all(res.r_edge == 12.0)
    cl = res.cloud
    assert len(cl["range_m"]) == 500  # no kept return, one dust return per beam
    assert set(cl["material_class"].tolist()) == {"dust"} and np.all(cl["range_m"] == 12.0)
    assert np.all(cl["intensity"] == 0.05)  # the display value of the recipe
    np.testing.assert_allclose(np.stack([cl["x"], cl["y"], cl["z"]], axis=1), c["xyz"] * (12.0 / R), rtol=1e-12)
    np.testing.assert_array_equal(cl["beam"], c["beam"])


@pytest.mark.req("FR-013-13")
def test_the_edge_is_the_first_sample_strictly_above_one_micro_per_metre() -> None:
    spacing = 0.25
    s = np.arange(0, 70, spacing)
    beta = np.zeros_like(s)
    beta[s == 5.0] = 1.0e-6  # exactly the threshold: not above it
    beta[s == 5.25] = 1.5e-6  # the first sample above it
    beta[s >= 20.0] = 0.2
    res = _apply(_rows(300, "retro", r=30.0), beta, spacing)  # tau(30 m) is about 2.0: kept or dropped, both emit below
    assert res.emit_dust.sum() == (~res.kept).sum()
    assert np.all(res.r_edge[res.emit_dust] == 5.25)


@pytest.mark.req("FR-013-13")
def test_multi_return_sensors_also_get_a_dust_return_from_a_kept_return_in_dust() -> None:
    c = _rows(2000, "diffuse")
    beta = _layer(0.5)  # tau = 0.5 > tau_on: most returns survive (u < 0.93)
    single = _apply(c, beta, max_returns=1)
    multi = _apply(c, beta, max_returns=2)
    np.testing.assert_array_equal(single.kept, multi.kept)  # the rule for the target return is the same
    np.testing.assert_array_equal(
        single.emit_dust, ~single.kept
    )  # one echo: a dust return only in place of a lost return
    assert multi.emit_dust.all()  # two echoes: a dust return for every beam in dust (tau > tau_on), kept or not
    assert multi.cloud["range_m"].shape[0] == int(multi.kept.sum()) + 2000
    clear = _apply(c, _layer(0.2), max_returns=2)  # below the onset: nothing is added
    assert not clear.emit_dust.any() and clear.cloud["range_m"].shape[0] == 2000


@pytest.mark.req("P-013-03")
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1), scale=st.floats(1.0, 100.0), peak=st.floats(0.001, 0.5))
def test_more_dust_never_keeps_a_dropped_return_nor_raises_a_kept_intensity(
    seed: int, scale: float, peak: float
) -> None:
    rng = np.random.default_rng(seed)
    n, m = 600, 400
    beta = rng.uniform(0, peak, m)
    c = {
        "beam": np.arange(n, dtype=np.uint32),
        "range_m": rng.uniform(1.0, 95.0, n),
        "material": np.where(rng.uniform(size=n) < 0.5, "retro", "diffuse"),
        "intensity": rng.uniform(0.1, 1.0, n),
        "xyz": rng.normal(size=(n, 3)),
    }
    base, more = _apply(c, beta), _apply(c, beta * scale)
    assert not np.any(more.kept & ~base.kept)  # a return dropped at k = 1 is never kept at k >= 1
    both = more.kept & base.kept
    assert np.all(more.intensity[both] <= base.intensity[both] * (1 + 1e-12))  # a kept intensity is never raised
    assert np.all(more.tau >= base.tau - 1e-15)


@pytest.mark.req("P-013-03")
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1), r1=st.floats(1.0, 60.0), extra=st.floats(0.0, 30.0))
def test_a_farther_target_on_the_same_beam_never_has_a_higher_transmittance(seed: int, r1: float, extra: float) -> None:
    beta = np.random.default_rng(seed).uniform(0, 0.3, 400)
    t = dust.optical_depth(beta, 0.25, np.array([r1, r1 + extra]))
    assert np.exp(-t[1]) <= np.exp(-t[0]) * (1 + 1e-15) and t[1] >= t[0] - 1e-15


@pytest.mark.req("P-013-04")
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1))
def test_permuting_the_beams_permutes_the_output_identically(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n, m = 500, 300
    beta = rng.uniform(0, 0.2, (n, m))
    c = {
        "beam": rng.permutation(10_000)[:n].astype(np.uint32),
        "range_m": rng.uniform(1.0, 70.0, n),
        "material": np.where(rng.uniform(size=n) < 0.5, "retro", "diffuse"),
        "intensity": rng.uniform(0.1, 1.0, n),
        "xyz": rng.normal(size=(n, 3)),
    }
    perm = rng.permutation(n)
    p = {k: v[perm] for k, v in c.items()}
    a, b = _apply(c, beta, max_returns=2), _apply(p, beta[perm], max_returns=2)
    for field in ("tau", "u", "kept", "intensity", "emit_dust"):
        np.testing.assert_array_equal(getattr(b, field)[np.argsort(perm)], getattr(a, field), err_msg=field)
    np.testing.assert_array_equal(b.r_edge[np.argsort(perm)], a.r_edge)  # NaN positions equal as well


@pytest.mark.req("P-013-05")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    tau=st.floats(0.0, 5.0), beam=st.integers(0, 2**32 - 1), frame=st.integers(0, 10**5), seed=st.integers(0, 2**32 - 1)
)
def test_at_equal_tau_and_u_a_retro_return_is_kept_whenever_a_diffuse_one_is(
    tau: float, beam: int, frame: int, seed: int
) -> None:
    c = {
        "beam": np.array([beam, beam], dtype=np.uint32),
        "range_m": np.array([R, R]),
        "material": np.array(["retro", "diffuse"]),
        "intensity": np.array([0.5, 0.5]),
        "xyz": np.ones((2, 3)),
    }
    res = _apply(c, _layer(tau), frame=frame, seed=seed)
    assert res.u[0] == res.u[1] and res.tau[0] == res.tau[1]
    assert res.kept[0] or not res.kept[1]  # kept(diffuse) implies kept(retro)


def _kept_fraction_reference(material: str, tau: float, n: int, frame: int, seed: int) -> float:
    floor = FLOOR[material]
    u = np.array([kit.beam_u_ref(frame, b, seed) for b in range(n)])
    return float(np.mean((tau <= TAU_ON) | ((tau <= floor) & (u * (floor - TAU_ON) < floor - tau))))


@pytest.mark.req("P-013-06")
@pytest.mark.parametrize(
    ("material", "t1", "expected"),
    [
        ("diffuse", 1.0, 1.0),
        ("diffuse", 0.9, 1.0),
        ("diffuse", 0.74, 1.0),
        ("diffuse", 0.059, 0.0),
        ("diffuse", 0.01, 0.0),
        ("retro", 1.0, 1.0),
        ("retro", 0.8, 1.0),
        ("retro", 0.019, 0.0),
        ("retro", 0.005, 0.0),
    ],
)
def test_calibration_anchors_are_exact(material: str, t1: float, expected: float) -> None:
    """Uniform layer: T1 >= 0.725 keeps everything; T1 below 0.06 (diffuse) or 0.02 (retro) keeps nothing."""
    c = _rows(100_000, material, seed=1)
    res = _apply(c, _layer(-np.log(t1)), frame=0, seed=1)
    assert float(res.kept.mean()) == expected


@pytest.mark.req("P-013-06")
@pytest.mark.parametrize("material", ["diffuse", "retro"])
@pytest.mark.parametrize(("frame", "seed"), [(0, 1), (7, 20261007)])
def test_midway_between_onset_and_floor_half_of_the_returns_are_kept(material: str, frame: int, seed: int) -> None:
    tau = 0.5 * (TAU_ON + FLOOR[material])
    c = _rows(100_000, material, seed=2)
    res = _apply(c, _layer(tau), frame=frame, seed=seed)
    frac = float(res.kept.mean())
    assert frac == _kept_fraction_reference(
        material, tau, 100_000, frame, seed
    )  # the code agrees with the reference hash
    assert abs(frac - 0.5) <= 0.0063  # 4 binomial standard deviations of 10^5 beams

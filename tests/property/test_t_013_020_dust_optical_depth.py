# ruff: noqa: E501, PT018, RUF046
"""T-013-020: optical depth along a beam and the two-way intensity law of the dust post-model.

Requirements: FR-013-11, P-013-01, P-013-02.

Oracle: closed forms (uniform extinction: tau = beta R; linear extinction beta(s) = a s: tau = a R^2 / 2; piecewise-linear
profiles by exact trapezoids through `sensor_kit.tau_ref`, written from the definition), the two-way law I = I0 exp(-2 tau)
(Beer-Lambert, spec 013 section 3.2), and the metamorphic relations P-013-01 (zero dust is the identity) and P-013-02
(additivity of optical depth, e^(-2 tau) = (e^(-tau))^2, tau(0) = 0).

Expected API (package `pitstudio.sensors.dust`, root environment; NumPy and `minephys.environment` only):
- `dust.optical_depth(beta, spacing, ranges) -> float64 array (n,)`: the extinction profile `beta` (m^-1) is sampled at the
  ranges `s_i = i * spacing`; `beta` has shape (m,) (one profile for every return) or (n, m) (one per return); between samples
  the extinction is linear; `ranges` (n,) are m; the result is the integral of beta from 0 to each range (0 for range 0).
  The profile must reach the range (`(m - 1) * spacing >= range`).
- `dust.apply_dust(beam, range_m, material, intensity, xyz, beta, spacing, *, frame, seed, dust_return_intensity,
  max_returns=1) -> DustResult` (spec 013 FR-013-11 to FR-013-14, see test_t_013_021 for the rule): `beam` (n,) uint32 beam
  indices, `range_m` (n,) float64, `material` (n,) array of "retro"/"diffuse", `intensity` (n,) float64 in 0..1, `xyz` (n, 3)
  float64 sensor-frame positions of the returns. `DustResult` has row-aligned arrays `tau`, `u`, `kept`, `intensity`
  (= I0 exp(-2 tau) for every row), `emit_dust`, `r_edge` and `cloud`, a dict of arrays `beam`, `x`, `y`, `z`, `range_m`,
  `intensity`, `material_class` holding the kept returns (unchanged range and position, attenuated intensity) in input order
  followed by the dust returns (class "dust").
- `src/pitstudio/sensors/dust.py` imports `minephys.environment` (it uses its transmittance functions).
"""

from __future__ import annotations

import ast
import math
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


def _cloud(n: int, seed: int, material: str | None = None) -> dict:
    rng = np.random.default_rng(seed)
    r = rng.uniform(0.5, 250.0, n)
    d = rng.normal(size=(n, 3))
    xyz = d / np.linalg.norm(d, axis=1, keepdims=True) * r[:, None]
    mat = np.array([material] * n) if material else np.where(rng.uniform(size=n) < 0.3, "retro", "diffuse")
    return {
        "beam": np.arange(n, dtype=np.uint32),
        "range_m": r,
        "material": mat,
        "intensity": rng.uniform(0, 1, n),
        "xyz": xyz,
    }


def _apply(c: dict, beta: np.ndarray, spacing: float, *, frame: int = 0, seed: int = 1, max_returns: int = 1):
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
        dust_return_intensity=0.05,
        max_returns=max_returns,
    )


@pytest.mark.req("FR-013-11")
def test_the_module_is_built_on_minephys_environment() -> None:
    tree = ast.parse((ROOT / "src" / "pitstudio" / "sensors" / "dust.py").read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    assert any(m == "minephys.environment" or m.startswith("minephys.environment.") for m in imported), imported


@pytest.mark.req("FR-013-11")
@pytest.mark.parametrize(("beta", "r"), [(0.01, 37.3), (0.2, 12.0), (1.0, 3.21), (0.0, 80.0), (0.004, 249.9)])
def test_uniform_extinction_gives_tau_equal_beta_times_range(beta: float, r: float) -> None:
    for spacing in (0.5, 0.25, 0.1):
        profile = kit.uniform_beta(1, beta, 260.0, spacing)[0]
        tau = dust.optical_depth(profile, spacing, np.array([r]))
        assert tau[0] == pytest.approx(beta * r, rel=1e-12, abs=1e-15)


@pytest.mark.req("FR-013-11")
@pytest.mark.parametrize("r", [10.0, 30.7, 63.25, 99.99])
def test_linear_extinction_gives_a_r_squared_over_two_for_any_range_between_samples(r: float) -> None:
    a, spacing = 0.002, 0.5
    s = np.arange(300) * spacing
    assert dust.optical_depth(a * s, spacing, np.array([r]))[0] == pytest.approx(a * r * r / 2.0, rel=1e-12)


@pytest.mark.req("FR-013-11")
def test_two_layer_profile_is_the_exact_sum() -> None:
    """Zero extinction up to the sample at 19.75 m, 0.05 m^-1 from the sample at 20.0 m (spacing 0.25 m): the profile is a
    ramp over one sample interval (triangle 0.5 x 0.05 x 0.25 = 0.00625) and a plateau from 20 to 30 m (0.05 x 10 = 0.5);
    the integral to 30 m is the hand-computed 0.50625."""
    spacing = 0.25
    s = np.arange(0, 60, spacing)
    beta = np.where(s >= 20.0, 0.05, 0.0)
    expected = 0.05 * (30.0 - 20.0) + 0.5 * 0.05 * 0.25
    assert expected == pytest.approx(0.50625, abs=1e-15)
    assert dust.optical_depth(beta, spacing, np.array([30.0]))[0] == pytest.approx(expected, rel=1e-12)


@pytest.mark.req("FR-013-11")
def test_intensity_is_i0_times_exp_minus_two_tau_and_range_and_position_are_unchanged() -> None:
    c = _cloud(500, 3, "diffuse")
    beta = kit.uniform_beta(1, 0.004, 260.0, 0.25)[0]  # tau up to 1.0 at 250 m
    res = _apply(c, beta, 0.25)
    tau = 0.004 * c["range_m"]
    np.testing.assert_allclose(res.tau, tau, rtol=1e-12)
    np.testing.assert_allclose(res.intensity, c["intensity"] * np.exp(-2.0 * tau), rtol=1e-12)
    kept = res.kept
    cl = res.cloud
    n_kept = int(kept.sum())
    np.testing.assert_array_equal(cl["range_m"][:n_kept], c["range_m"][kept])  # range unchanged, bit for bit
    np.testing.assert_array_equal(np.stack([cl["x"], cl["y"], cl["z"]], axis=1)[:n_kept], c["xyz"][kept])
    np.testing.assert_allclose(cl["intensity"][:n_kept], (c["intensity"] * np.exp(-2.0 * tau))[kept], rtol=1e-12)
    assert np.array_equal(cl["beam"][:n_kept], c["beam"][kept])


@pytest.mark.req("P-013-01")
@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    n=st.sampled_from([1, 2, 17, 1000, 100_000]),
    seed=st.integers(0, 2**31 - 1),
    spacing=st.sampled_from([0.5, 0.25, 0.01 * 7]),
)
def test_zero_dust_is_the_identity_and_holds_no_dust_return(n: int, seed: int, spacing: float) -> None:
    """P-013-01: with beta = 0 the dusty cloud equals the clean cloud (positions and intensities), exactly."""
    c = _cloud(n, seed)
    beta = np.zeros(int(math.ceil(260.0 / spacing)) + 2)
    res = _apply(c, beta, spacing, max_returns=2)  # even a multi-return sensor adds nothing without dust
    assert res.kept.all() and not res.emit_dust.any()
    cl = res.cloud
    assert len(cl["range_m"]) == n
    np.testing.assert_array_equal(cl["range_m"], c["range_m"])
    np.testing.assert_array_equal(cl["intensity"], c["intensity"])
    np.testing.assert_array_equal(np.stack([cl["x"], cl["y"], cl["z"]], axis=1), c["xyz"])
    assert "dust" not in set(cl["material_class"].tolist())
    assert np.all(res.tau == 0.0)


@pytest.mark.req("P-013-02")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(0, 2**31 - 1),
    spacing=st.floats(0.01, 0.5),
    r1=st.floats(0.5, 90.0),
    r2=st.floats(0.5, 90.0),
    peak=st.floats(0.0, 1.0),
)
def test_optical_depth_is_additive_and_the_two_way_law_is_the_square(
    seed: int, spacing: float, r1: float, r2: float, peak: float
) -> None:
    rng = np.random.default_rng(seed)
    m = int(math.ceil((r1 + r2) / spacing)) + 2
    beta = rng.uniform(0.0, 1.0, m) * peak
    t1 = dust.optical_depth(beta, spacing, np.array([r1]))[0]
    t12 = dust.optical_depth(beta, spacing, np.array([r1 + r2]))[0]
    segment = kit.tau_ref(beta, spacing, r1 + r2) - kit.tau_ref(beta, spacing, r1)  # integral over [r1, r1 + r2]
    assert t12 == pytest.approx(t1 + segment, rel=1e-12, abs=1e-12)  # tau[0, R1+R2] = tau[0, R1] + tau[R1, R1+R2]
    assert t1 == pytest.approx(kit.tau_ref(beta, spacing, r1), rel=1e-12, abs=1e-14)
    assert math.exp(-2.0 * t12) == pytest.approx(math.exp(-t12) ** 2, rel=1e-12)  # two-way = (one-way)^2
    assert dust.optical_depth(beta, spacing, np.array([0.0]))[0] == 0.0  # tau(0) = 0, hence T1(0) = 1


@pytest.mark.req("P-013-02")
def test_one_profile_per_return_and_one_shared_profile_agree() -> None:
    rng = np.random.default_rng(5)
    profile = rng.uniform(0, 0.5, 400)
    r = rng.uniform(1, 90, 50)
    shared = dust.optical_depth(profile, 0.25, r)
    per_row = dust.optical_depth(np.tile(profile, (50, 1)), 0.25, r)
    np.testing.assert_array_equal(shared, per_row)
    np.testing.assert_allclose(shared, [kit.tau_ref(profile, 0.25, x) for x in r], rtol=1e-12)

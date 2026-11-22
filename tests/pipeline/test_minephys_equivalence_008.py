"""Equivalence of the synthesis physics adapters (pitstudio_pipeline.synthesize.physics) with the pre-dedupe implementations.

Not a locked test. The oracles below are the PitStudio formulas of `pipeline/src/pitstudio_pipeline/synthesize/physics.py`
at commit 2ccdd02 (the last revision that carried them), copied verbatim; the adapters now call `minephys` (pinned) and
convert units at the boundary. Tolerance: relative 1e-12 (the same formulas in float64, differing only in operation order).
Plume sigmas are not replaced (minephys ships the ISC3 Pasquill-Gifford and urban Briggs fits, not the Briggs open-country
class D curves), so that function is checked as unchanged.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from pitstudio_pipeline.synthesize import physics

RTOL = 1e-12


# ------------------------------------------------------------------------------ oracles (PitStudio at 2ccdd02)
def _old_x50_cm(b, s, h, q, a, rws):
    return a * (b * s * h / q) ** 0.8 * q ** (1 / 6) * (rws / 115.0) ** (-19.0 / 30.0)


def _old_n(b, s, d_mm, w, bcl, ccl, h):
    total = bcl + ccl
    return (
        (2.2 - 14.0 * b / d_mm)
        * math.sqrt((1.0 + s / b) / 2.0)
        * (1.0 - w / b)
        * (abs(bcl - ccl) / total + 0.1) ** 0.1
        * (total / h)
    )


def _old_rr(x, x50, n):
    return 1.0 - np.exp(-math.log(2.0) * (x / x50) ** n)


def _old_swebrec(x, x50, xmax, b):
    out = np.ones_like(x, dtype=float)
    inside = x < xmax
    ratio = np.log(xmax / x[inside]) / math.log(xmax / x50)
    out[inside] = 1.0 / (1.0 + ratio**b)
    return out


def _old_voight(t, alpha, a, tf, x0=0.0):
    k = (a * (alpha - 1.0)) ** (-1.0 / (alpha - 1.0))
    if math.isclose(alpha, 2.0):
        return x0 + k * np.log(tf / (tf - t))
    p = (alpha - 2.0) / (alpha - 1.0)
    return x0 + (k / p) * (tf**p - (tf - t) ** p)


def _old_sigma(x):
    return 0.08 * x / np.sqrt(1.0 + 1e-4 * x), 0.06 * x / np.sqrt(1.0 + 1.5e-3 * x)


def _old_plume(x_m, y_m, q, u, h):
    xx, yy = np.meshgrid(x_m, y_m, indexing="ij")
    sy, sz = _old_sigma(xx)
    return q / (math.pi * u * sy * sz) * np.exp(-(yy**2) / (2.0 * sy**2)) * np.exp(-(h**2) / (2.0 * sz**2))


def _old_bond(wi, p80, f80):
    return 10.0 * wi * (1.0 / math.sqrt(p80) - 1.0 / math.sqrt(f80))


# ------------------------------------------------------------------------------------------------------ tests
BLASTS = [
    physics.default_blast(),
    {**physics.default_blast(), "burden_m": 3.0, "spacing_m": 3.5, "diameter_mm": 165.0, "charge_kg": 90.0, "rock_factor": 5.0},
    {**physics.default_blast(), "burden_m": 6.0, "spacing_m": 8.0, "bench_m": 15.0, "charge_kg": 800.0, "rock_factor": 12.0, "rws": 85.0},
]


@pytest.mark.parametrize("p", BLASTS)
def test_kuz_ram_x50_and_uniformity_match_the_pre_dedupe_formulas(p: dict) -> None:
    x50 = physics.x50_cm(p["burden_m"], p["spacing_m"], p["bench_m"], p["charge_kg"], p["rock_factor"], p["rws"])
    assert x50 == pytest.approx(_old_x50_cm(p["burden_m"], p["spacing_m"], p["bench_m"], p["charge_kg"], p["rock_factor"], p["rws"]), rel=RTOL)
    args = (p["burden_m"], p["spacing_m"], p["diameter_mm"], p["drill_sd_m"], p["bottom_charge_m"], p["column_charge_m"], p["bench_m"])
    assert physics.uniformity_n(*args) == pytest.approx(_old_n(*args), rel=RTOL)
    assert isinstance(x50, float)


@pytest.mark.parametrize("p", BLASTS)
def test_size_distributions_match_the_pre_dedupe_formulas(p: dict) -> None:
    x50 = _old_x50_cm(p["burden_m"], p["spacing_m"], p["bench_m"], p["charge_kg"], p["rock_factor"], p["rws"])
    n = _old_n(p["burden_m"], p["spacing_m"], p["diameter_mm"], p["drill_sd_m"], p["bottom_charge_m"], p["column_charge_m"], p["bench_m"])
    x_max = 100.0 * min(p["spacing_m"], p["burden_m"])
    sizes = np.geomspace(0.1, x_max, 60)
    np.testing.assert_allclose(physics.rosin_rammler_cm(sizes, x50, n), _old_rr(sizes, x50, n), rtol=RTOL, atol=1e-15)
    np.testing.assert_allclose(physics.swebrec_cm(sizes, x50, x_max, p["swebrec_b"]), _old_swebrec(sizes, x50, x_max, p["swebrec_b"]), rtol=RTOL, atol=1e-15)
    above = np.array([x_max, 2 * x_max])
    np.testing.assert_array_equal(physics.swebrec_cm(above, x50, x_max, p["swebrec_b"]), np.ones(2))


@pytest.mark.parametrize("alpha", [1.6, 1.8, 2.0, 2.2, 2.4])
@pytest.mark.parametrize("seed", range(4))
def test_voight_displacement_matches_the_pre_dedupe_formula(alpha: float, seed: int) -> None:
    rng = np.random.default_rng(seed)
    a, tf = float(rng.uniform(0.5, 2.0)), float(rng.uniform(150.0, 400.0))
    t = np.linspace(0.0, 0.97 * tf, 200)
    np.testing.assert_allclose(physics.creep_displacement(t, alpha, a, tf), _old_voight(t, alpha, a, tf), rtol=RTOL, atol=1e-12)
    t2 = np.linspace(5.0, 0.9 * tf, 50)  # a series that does not start at 0: displacement still accumulates from t = 0
    np.testing.assert_allclose(physics.creep_displacement(t2, alpha, a, tf, x0=0.3), _old_voight(t2, alpha, a, tf, 0.3), rtol=RTOL, atol=1e-12)


def test_voight_hostile_inputs_keep_raising_value_error() -> None:
    t = np.linspace(0.0, 10.0, 5)
    for args in ((t, 1.0, 1.0, 20.0), (t, 2.0, 0.0, 20.0), (t, 2.0, 1.0, 0.0), (t, 2.0, 1.0, 10.0)):
        with pytest.raises(ValueError):
            physics.creep_displacement(*args)


def test_briggs_sigma_is_unchanged() -> None:
    x = np.arange(50.0, 2050.0, 50.0)
    for got, want in zip(physics.briggs_sigma_class_d(x), _old_sigma(x), strict=True):
        np.testing.assert_array_equal(got, want)


@pytest.mark.parametrize(("q", "u", "h"), [(1.0, 3.0, 10.0), (25.0, 1.5, 0.0), (0.2, 8.0, 40.0)])
def test_plume_ground_concentration_matches_the_pre_dedupe_formula(q: float, u: float, h: float) -> None:
    x = np.arange(50.0, 2050.0, 50.0)
    y = np.arange(-300.0, 301.0, 15.0)
    np.testing.assert_allclose(physics.plume_ground_g_m3(x, y, q, u, h), _old_plume(x, y, q, u, h), rtol=RTOL, atol=1e-300)


def test_bond_energy_matches_the_pre_dedupe_formula() -> None:
    for wi in (8.0, 14.0, 20.0):
        for p80 in (75.0, 150.0, 425.0):
            assert physics.bond_kwh_t(wi, p80, 12_500.0) == pytest.approx(_old_bond(wi, p80, 12_500.0), rel=RTOL)

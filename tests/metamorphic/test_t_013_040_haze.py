# ruff: noqa: E501, PT018, PT011
"""T-013-040: S3 haze post-model.

Requirements: FR-013-16, P-013-07.

Oracle: the analytic haze law I = J t + A (1 - t), t = exp(-tau_c) (Narasimhan and Nayar 2002, spec section 7 A3), written out
per channel in the test for constant extinction (tau_c = beta d), and for a per-pixel profile through `sensor_kit.tau_ref`; the
four metamorphic relations of P-013-07 (MR1 tau_c = 0 gives J, MR2 A = J gives J, MR3 homogeneity, MR4 betweenness and the limit A);
tolerance rtol 1e-6 (about 8 float32 ulp, spec section 7).

Expected API (package `pitstudio.sensors.camera`, root environment; NumPy only):
- `camera.haze(radiance, distance, airlight, *, beta, spacing=None, exit_distance=None) -> float32 array (h, w, 3)`.
  `radiance` (h, w, 3) float16/float32 linear radiance J (promoted to float32); `distance` (h, w) metres to the first hit
  (`DistanceToCameraSD`), a non-finite value (inf or NaN) is a pixel without a hit; `airlight` (3,) linear RGB A in [0, 10^6];
  `beta`: a float (uniform extinction in m^-1) or an array (h, w, m) of extinction profiles along each pixel's ray sampled at
  `spacing` (m, piecewise linear between samples); `exit_distance`: a float or (h, w) array, the distance at which the ray leaves
  the dust field's bounding box, used as the integration end for pixels without a hit (required if any pixel has none).
  tau_c is the integral of beta from 0 to the distance (or the exit distance); the output is I = J t + A (1 - t) per channel.
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
from pitstudio.sensors import camera  # noqa: E402

A = np.array([0.58, 0.46, 0.31])


def _image(h: int = 6, w: int = 8, seed: int = 0, peak: float = 4.0) -> np.ndarray:
    return np.random.default_rng(seed).uniform(0.0, peak, (h, w, 3)).astype(np.float32)


@pytest.mark.req("FR-013-16")
def test_uniform_haze_matches_the_analytic_law_per_channel() -> None:
    j = _image()
    d = np.random.default_rng(1).uniform(5.0, 150.0, (6, 8))
    beta = 0.015
    t = np.exp(-beta * d)[..., None]
    expected = j.astype(np.float64) * t + A[None, None, :] * (1.0 - t)
    got = camera.haze(j, d, A, beta=beta)
    assert got.dtype == np.float32 and got.shape == (6, 8, 3)
    np.testing.assert_allclose(got, expected, rtol=1e-6)


@pytest.mark.req("FR-013-16")
def test_float16_radiance_is_promoted_to_float32() -> None:
    j16 = _image(seed=2).astype(np.float16)
    d = np.full((6, 8), 40.0)
    got = camera.haze(j16, d, A, beta=0.01)
    t = np.exp(-0.01 * 40.0)
    np.testing.assert_allclose(got, j16.astype(np.float32) * t + A * (1 - t), rtol=1e-6)
    assert got.dtype == np.float32


@pytest.mark.req("FR-013-16")
def test_a_pixel_without_a_hit_integrates_to_the_exit_of_the_dust_box() -> None:
    j = _image(seed=3)
    d = np.random.default_rng(4).uniform(5.0, 60.0, (6, 8))
    d[0, 0], d[2, 3], d[5, 7] = np.inf, np.nan, np.inf  # sky pixels
    exit_d = np.full((6, 8), 120.0)
    exit_d[0, 0] = 80.0  # the ray of the first sky pixel leaves the box earlier
    got = camera.haze(j, d, A, beta=0.01, exit_distance=exit_d)
    eff = np.where(np.isfinite(d), d, exit_d)
    t = np.exp(-0.01 * eff)[..., None]
    np.testing.assert_allclose(got, j * t + A * (1 - t), rtol=1e-6)
    uniform_exit = camera.haze(j, d, A, beta=0.01, exit_distance=120.0)  # a scalar exit distance
    np.testing.assert_allclose(uniform_exit[2, 3], j[2, 3] * np.exp(-1.2) + A * (1 - np.exp(-1.2)), rtol=1e-6)


@pytest.mark.req("FR-013-16")
def test_a_pixel_without_a_hit_and_no_exit_distance_is_an_error() -> None:
    d = np.full((6, 8), 30.0)
    d[1, 1] = np.inf
    with pytest.raises(ValueError):
        camera.haze(_image(), d, A, beta=0.01)


@pytest.mark.req("FR-013-16")
def test_a_per_pixel_extinction_profile_is_integrated_along_the_ray() -> None:
    rng = np.random.default_rng(5)
    h, w, m, spacing = 3, 4, 300, 0.5
    beta = rng.uniform(0.0, 0.05, (h, w, m))
    d = rng.uniform(5.0, 140.0, (h, w))
    j = _image(h, w, seed=6)
    tau = np.array([[kit.tau_ref(beta[y, x], spacing, d[y, x]) for x in range(w)] for y in range(h)])
    t = np.exp(-tau)[..., None]
    got = camera.haze(j, d, A, beta=beta, spacing=spacing)
    np.testing.assert_allclose(got, j * t + A * (1 - t), rtol=1e-6)


@pytest.mark.req("P-013-07")
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1), a=st.floats(1e-3, 100.0))
def test_without_dust_the_image_is_unchanged_and_a_scene_of_airlight_colour_is_unchanged(seed: int, a: float) -> None:
    rng = np.random.default_rng(seed)
    j = rng.uniform(0, 1e4, (5, 7, 3)).astype(np.float32)
    d = rng.uniform(1, 300, (5, 7))
    airlight = rng.uniform(0, 1e4, 3)
    np.testing.assert_allclose(camera.haze(j, d, airlight, beta=0.0), j, rtol=1e-6)  # MR1: tau_c = 0 gives J
    flat = np.broadcast_to(airlight.astype(np.float32), (5, 7, 3)).copy()
    for beta in (0.0, 0.003, 0.2):
        np.testing.assert_allclose(camera.haze(flat, d, airlight, beta=beta), flat, rtol=1e-6)  # MR2: A = J gives J
    base = camera.haze(j, d, airlight, beta=0.02)
    scaled = camera.haze((j.astype(np.float64) * a).astype(np.float32), d, airlight * a, beta=0.02)
    np.testing.assert_allclose(scaled, a * base.astype(np.float64), rtol=1e-5)  # MR3: I(aJ, aA) = a I(J, A)


@pytest.mark.req("P-013-07")
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1), tau_c=st.floats(0.0, 20.0))
def test_the_result_lies_between_the_scene_and_the_airlight_and_tends_to_the_airlight(seed: int, tau_c: float) -> None:
    rng = np.random.default_rng(seed)
    j = rng.uniform(0, 1e4, (4, 6, 3)).astype(np.float32)
    airlight = rng.uniform(0, 1e4, 3)
    d = np.full((4, 6), 50.0)
    got = camera.haze(j, d, airlight, beta=tau_c / 50.0).astype(np.float64)
    lo = np.minimum(j, airlight[None, None, :]).astype(np.float64)
    hi = np.maximum(j, airlight[None, None, :]).astype(np.float64)
    slack = 1e-6 * np.maximum(hi, 1.0)
    assert np.all(got >= lo - slack) and np.all(got <= hi + slack)  # MR4: I between J and A per channel
    t = np.exp(-tau_c)
    np.testing.assert_allclose(got, j * t + airlight * (1 - t), rtol=1e-6, atol=1e-6)
    far = camera.haze(j, d, airlight, beta=20.0 / 50.0).astype(np.float64)  # tau_c = 20: t = 2e-9
    assert np.all(
        np.abs(far - airlight[None, None, :]) <= 1e-6 * (np.abs(j - airlight[None, None, :]) + np.abs(airlight) + 1.0)
    )

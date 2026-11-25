# ruff: noqa: E501, PT018
"""T-013-042: S2 exposure, noise and vignetting.

Requirements: FR-013-18, P-013-08.

Oracle: the signal model S = kappa L t_e / N^2 (electrons) evaluated by hand (L = 100, kappa = 2e6, t_e = 0.002 s, N = 5.6: S =
12,755.1 e-), the natural-vignetting law cos^4(theta) at known pixel angles (an offset of f tan 30 deg from the principal point gives
cos^4 30 deg = 0.5625), the DN arithmetic DN = clip(round(G (S + n)), 0, DN_max) by hand, and the metamorphic relations P-013-08
(MR1 doubling t_e doubles S, MR2 N / sqrt(2) doubles S, MR3 DN stays in [0, DN_max], MR4 the sample variance of S + n over 10^5 draws lies in
the two-sided 99.9 % chi-square interval of S + sigma_read^2, computed with the Wilson-Hilferty quantiles in `sensor_kit`).

Expected API (package `pitstudio.sensors.camera`, root environment; NumPy only):
- `camera.signal_electrons(L, *, exposure_time_s, f_number, kappa, cos4=None) -> float64`: S = kappa L t_e / N^2, times `cos4` (an array
  broadcastable to L) when given.
- `camera.vignette_cos4(width_px, height_px, fx_px, fy_px, cx_px, cy_px) -> float64 (h, w)`: cos^4 theta of the angle between each pixel
  ray (pixel centre at `(col + 0.5, row + 0.5)`) and the optical axis, `cos theta = 1 / sqrt(1 + ((u - cx)/fx)^2 + ((v - cy)/fy)^2)`.
- `camera.noisy_electrons(signal, *, read_noise_e, seed, image_index, first_pixel=0) -> float64`: S + n with zero-mean Gaussian n of
  variance S + read_noise_e^2, drawn from a counter-based generator keyed by (seed, image_index, pixel index) where the pixel index of
  the i-th element (C order) of `signal` is `first_pixel + i`: the same key gives the same draw whatever else is in the array.
- `camera.expose(L, *, exposure_time_s, f_number, kappa, gain, read_noise_e, dn_max, vignetting, intrinsics, seed, image_index, noise=True)
  -> uint16 array (h, w)`: DN = clip(round(gain (S + n)), 0, dn_max); `intrinsics = {fx_px, fy_px, cx_px, cy_px}` used when `vignetting` is
  true; `noise=False` skips the draw (n = 0). Rounding is to nearest.
"""

from __future__ import annotations

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
from pitstudio.sensors import camera  # noqa: E402

PARAMS = {"exposure_time_s": 0.002, "f_number": 5.6, "kappa": 2.0e6}
K = {"fx_px": 2200.0, "fy_px": 2200.0, "cx_px": 960.0, "cy_px": 540.0}


@pytest.mark.req("FR-013-18")
def test_signal_by_hand() -> None:
    s = camera.signal_electrons(100.0, **PARAMS)
    assert s == pytest.approx(2.0e6 * 100.0 * 0.002 / 5.6**2, rel=1e-12)
    assert s == pytest.approx(12755.102040816, rel=1e-10)
    np.testing.assert_allclose(
        camera.signal_electrons(np.array([0.0, 1.0, 10.0]), **PARAMS),
        [0.0, 127.55102040816, 1275.5102040816],
        rtol=1e-12,
        atol=0,
    )


@pytest.mark.req("FR-013-18")
def test_vignetting_follows_cos_to_the_fourth() -> None:
    f = 500.0
    cos4 = camera.vignette_cos4(1001, 1001, f, f, 500.5, 500.5)  # an odd image: the centre pixel is the principal point
    assert cos4.shape == (1001, 1001)
    assert cos4[500, 500] == pytest.approx(1.0, abs=1e-12)
    # f tan(30 deg) = 288.7 px to the right of the centre: theta = 30 deg, cos^4 = 0.5625 (289 px: a half-pixel tolerance)
    assert cos4[500, 500 + 289] == pytest.approx(0.5625, rel=5e-3)
    assert cos4[500, 500 + 289] == pytest.approx(cos4[500, 500 - 289], rel=1e-9)  # symmetric about the centre
    np.testing.assert_allclose(cos4, cos4[::-1, ::-1], rtol=1e-12)
    row = cos4[500, 500:]
    assert np.all(np.diff(row) < 0) and row.min() > 0  # decreasing away from the centre
    assert cos4[0, 0] == pytest.approx(
        1.0 / (1.0 + 1.0 + 1.0) ** 2, rel=1e-9
    )  # corner pixel centre: tan = 500 / 500 on both axes


@pytest.mark.req("FR-013-18")
def test_vignetting_off_leaves_a_uniform_scene_uniform_and_on_darkens_the_corners() -> None:
    img = np.full((54, 96), 50.0)
    kw = {
        **PARAMS,
        "gain": 0.25,
        "read_noise_e": 0.0,
        "dn_max": 4095,
        "intrinsics": {"fx_px": 220.0, "fy_px": 220.0, "cx_px": 48.0, "cy_px": 27.0},
        "seed": 1,
        "image_index": 0,
        "noise": False,
    }
    flat = camera.expose(img, vignetting=False, **kw)
    assert flat.dtype == np.uint16 and np.all(flat == flat[0, 0])
    dark = camera.expose(img, vignetting=True, **kw)
    assert dark[27, 48] >= dark[0, 0] and dark[0, 0] < flat[0, 0]
    assert dark.max() <= flat[0, 0]  # vignetting never brightens


@pytest.mark.req("FR-013-18")
def test_dn_by_hand_with_rounding_and_saturation_and_no_noise() -> None:
    kw = {
        **PARAMS,
        "gain": 0.25,
        "read_noise_e": 3.0,
        "dn_max": 4095,
        "vignetting": False,
        "intrinsics": K,
        "seed": 5,
        "image_index": 2,
        "noise": False,
    }
    dn = camera.expose(np.array([[100.0, 0.0, 10.0, 1.0e4]]), **kw)
    # S = 12755.10 -> 3188.78 -> 3189; S = 0 -> 0; S = 1275.51 -> 318.88 -> 319; S = 1.2755e6 -> 318,877 -> saturates at 4095
    assert dn.tolist() == [[3189, 0, 319, 4095]]
    one = camera.expose(np.array([[5.6**2 / (2.0e6 * 0.002)]]), **{**kw, "gain": 1.0})  # S = 1.0 e-, gain 1: DN = 1
    assert one.tolist() == [[1]]
    below_half = camera.expose(
        np.array([[0.4 * 5.6**2 / (2.0e6 * 0.002)]]), **{**kw, "gain": 1.0}
    )  # S = 0.4 e-: rounds to 0
    assert below_half.tolist() == [[0]]


@pytest.mark.req("P-013-08")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(L=st.floats(0.0, 1e3), t=st.floats(1e-5, 0.5), N=st.floats(1.4, 22.0))
def test_doubling_the_exposure_time_or_opening_the_aperture_a_stop_doubles_the_signal(
    L: float, t: float, N: float
) -> None:
    base = camera.signal_electrons(L, exposure_time_s=t, f_number=N, kappa=2.0e6)
    assert camera.signal_electrons(L, exposure_time_s=2 * t, f_number=N, kappa=2.0e6) == pytest.approx(
        2 * base, rel=1e-6, abs=0
    )  # MR1
    assert camera.signal_electrons(L, exposure_time_s=t, f_number=N / math.sqrt(2.0), kappa=2.0e6) == pytest.approx(
        2 * base, rel=1e-6, abs=0
    )  # MR2


@pytest.mark.req("P-013-08")
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(0, 2**31 - 1),
    gain=st.floats(0.01, 10.0),
    dn_max=st.integers(1, 65535),
    read=st.floats(0.0, 50.0),
    peak=st.floats(0.0, 1e3),
    noise=st.booleans(),
)
def test_dn_stays_between_zero_and_dn_max(
    seed: int, gain: float, dn_max: int, read: float, peak: float, noise: bool
) -> None:
    L = np.random.default_rng(seed).uniform(0, peak, (12, 16))
    dn = camera.expose(
        L,
        **PARAMS,
        gain=gain,
        read_noise_e=read,
        dn_max=dn_max,
        vignetting=True,
        intrinsics={"fx_px": 300.0, "fy_px": 300.0, "cx_px": 8.0, "cy_px": 6.0},
        seed=seed % 2**32,
        image_index=3,
        noise=noise,
    )  # MR3
    assert dn.dtype == np.uint16 and dn.min() >= 0 and dn.max() <= dn_max


@pytest.mark.req("P-013-08")
@pytest.mark.parametrize(("signal", "read"), [(1000.0, 3.0), (50.0, 5.0), (20000.0, 10.0)])
def test_noise_variance_is_in_the_chi_square_interval_of_signal_plus_read_noise(signal: float, read: float) -> None:
    """MR4: 10^5 draws of S + n have variance (S + sigma_read^2) within the two-sided 99.9 % chi-square interval."""
    n = 100_000
    draws = camera.noisy_electrons(np.full(n, signal), read_noise_e=read, seed=123, image_index=0)
    var = signal + read**2
    lo, hi = kit.chi2_interval(n - 1)
    stat = (n - 1) * float(np.var(draws, ddof=1)) / var
    assert lo <= stat <= hi
    assert abs(float(draws.mean()) - signal) <= 4.0 * math.sqrt(var / n)  # the mean is S (unbiased)


@pytest.mark.req("FR-013-18")
def test_the_generator_is_counter_based_and_keyed_by_seed_image_and_pixel() -> None:
    s = np.full(1000, 500.0)
    a = camera.noisy_electrons(s, read_noise_e=3.0, seed=7, image_index=4)
    np.testing.assert_array_equal(a, camera.noisy_electrons(s, read_noise_e=3.0, seed=7, image_index=4))  # reproducible
    assert not np.array_equal(a, camera.noisy_electrons(s, read_noise_e=3.0, seed=8, image_index=4))
    assert not np.array_equal(a, camera.noisy_electrons(s, read_noise_e=3.0, seed=7, image_index=5))
    # counter-based: the draw of a pixel does not depend on the rest of the array
    np.testing.assert_array_equal(
        a[100:300], camera.noisy_electrons(s[100:300], read_noise_e=3.0, seed=7, image_index=4, first_pixel=100)
    )
    np.testing.assert_array_equal(a[:1], camera.noisy_electrons(s[:1], read_noise_e=3.0, seed=7, image_index=4))
    # the noise level follows each element's own signal: a dark pixel is quieter than a bright one
    mixed = camera.noisy_electrons(
        np.concatenate([np.full(50_000, 10.0), np.full(50_000, 10_000.0)]), read_noise_e=1.0, seed=1, image_index=0
    )
    assert np.std(mixed[:50_000]) < 0.1 * np.std(mixed[50_000:])


@pytest.mark.req("FR-013-18")
def test_the_first_row_of_a_large_image_equals_a_one_row_image() -> None:
    kw = {
        **PARAMS,
        "gain": 0.25,
        "read_noise_e": 3.0,
        "dn_max": 4095,
        "vignetting": False,
        "intrinsics": K,
        "seed": 9,
        "image_index": 1,
    }
    big = camera.expose(np.full((40, 64), 20.0), **kw)
    row = camera.expose(np.full((1, 64), 20.0), **kw)
    np.testing.assert_array_equal(big[0], row[0])  # pixel indices 0..63 are the same in both

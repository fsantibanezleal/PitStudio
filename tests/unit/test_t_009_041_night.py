# ruff: noqa: E501
"""T-009-041 - FR-009-26, P-009-04 (and the night half of P-009-03): night exposure and noise.

Oracles (independent of the code under test):
- Table C of spec 009 typed out: exposure factor k_s = 2^-s (1/2, 1/4, 1/8, 1/16, 1/32), noise standard deviation sigma_n,s = 0.002, 0.004, 0.006,
  0.008, 0.010 (linear units); out = clip(k_s I + n, 0, 1) with n ~ N(0, sigma_n,s^2) per pixel and channel (FR-009-26);
- analytical: with sigma_n = 0 the result is clip(k I, 0, 1) = k I for linear I in [0, 1]; a constant linear image of 1.0 has k_s + n, so the noise
  is read back as out - k_s without clipping (k_s >= 31 sigma_n at s = 1..4 and 3.1 sigma at s = 5, where the clipped tail of 0.1 % moves the sample std
  by 0.03 %): its sample std must be within +-1 % of sigma_n at about 10^6 samples (standard error of a sample std: sigma / sqrt(2 n) = 0.07 %, spec
  9 plan tolerances) and its mean within 5 standard errors of 0; the Pearson correlation of channels and of horizontal neighbours is within 5
  standard errors (0.005) of 0 (independent draws);
- analytical: on an all-black linear image the output is clip(n, 0, 1) = max(n, 0), whose mean is sigma / sqrt(2 pi) (half-normal mean) and
  half of whose samples are exactly 0;
- P-009-04: exposure factors compose multiplicatively (2^-a * 2^-b = 2^-(a+b), rtol 1e-12) and, for sigma_n = 0, the mean Rec. 709 luminance
  (0.2126, 0.7152, 0.0722, the IEC 61966-2-1 primaries) of night_s(I) equals 2^-s times that of I, hence is non-increasing in s (the spec states the claim
  for sigma_n = 0 and before clipping; with noise a black image gains mean sigma / sqrt(2 pi) which grows with s, reported as an ambiguity);
- P-009-03 (night half): the sigma_n = 0 night is elementwise, so permutations and dihedral maps commute with it (exact).

Expected public API (module `pitstudio_pipeline.perception.corruptions`, package under `pipeline/src/`; see tests/unit/test_t_009_040_dust.py for the
transfer functions and `CorruptionResult`):

    EXPOSURE_K: dict[int, float]      {1: 0.5, 2: 0.25, 3: 0.125, 4: 0.0625, 5: 0.03125}
    SIGMA_N: dict[int, float]         {1: 0.002, 2: 0.004, 3: 0.006, 4: 0.008, 5: 0.010}
    apply_exposure(lin: ndarray, k: float) -> ndarray            k * lin, no clipping, float64
    night_linear(lin: ndarray, severity: int, *, seed: int, sigma_n: float | None = None) -> ndarray
        lin (H, W, 3) float64 linear RGB in [0, 1]; returns clip(EXPOSURE_K[severity] * lin + n, 0, 1) float64 with n drawn independently per pixel and
        channel from N(0, sigma^2) by a counter-based generator keyed by `seed` (numpy Philox), drawn in C order over (H, W, 3): the noise of
        element (r, c, ch) depends only on the seed and the flat index, not on the array size; sigma = SIGMA_N[severity] unless `sigma_n` is given
        (sigma_n = 0.0 is the noise-free night_0); severity 0 returns an equal copy; the same seed gives bit-identical output.
    night(image: ndarray, severity: int, *, seed: int, sigma_n: float | None = None) -> CorruptionResult
        uint8 sRGB (or float sRGB in [0, 1]) in, same dtype out (decode -> night_linear -> encode_u8 / srgb_encode); record =
        {"corruption": "night", "severity": severity, "seed": seed}; severity 0 returns the input unchanged.
"""

from __future__ import annotations

import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.perception import corruptions as cor  # noqa: E402

EXAMPLES = 200
K = {1: 0.5, 2: 0.25, 3: 0.125, 4: 0.0625, 5: 0.03125}
SIG = {1: 0.002, 2: 0.004, 3: 0.006, 4: 0.008, 5: 0.010}
W709 = np.array([0.2126, 0.7152, 0.0722])


def _dec(v: float) -> float:
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _enc(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055


@pytest.mark.req("FR-009-26")
def test_table_c_exposure_and_noise_constants() -> None:
    assert dict(cor.EXPOSURE_K) == K
    assert dict(cor.SIGMA_N) == SIG
    for s in range(1, 6):
        assert cor.EXPOSURE_K[s] == 2.0 ** (-s)


@pytest.mark.req("FR-009-26")
@pytest.mark.parametrize("severity", [1, 2, 3, 4, 5])
def test_without_noise_the_night_is_the_exposure_factor_times_the_image(severity: int) -> None:
    lin = np.random.default_rng(1).random((9, 11, 3))
    out = cor.night_linear(lin, severity, seed=0, sigma_n=0.0)
    np.testing.assert_allclose(out, K[severity] * lin, rtol=1e-12, atol=0.0)
    assert out.dtype == np.float64
    assert out.shape == lin.shape


@pytest.mark.req("FR-009-26")
def test_severity_zero_is_the_identity() -> None:
    lin = np.random.default_rng(2).random((4, 4, 3))
    np.testing.assert_array_equal(cor.night_linear(lin, 0, seed=5), lin)
    img = np.random.default_rng(3).integers(0, 256, size=(4, 4, 3), dtype=np.uint8)
    res = cor.night(img, 0, seed=5)
    np.testing.assert_array_equal(res.image, img)
    assert res.image.dtype == np.uint8
    assert res.record == {"corruption": "night", "severity": 0, "seed": 5}


@pytest.mark.req("FR-009-26")
@pytest.mark.parametrize("severity", [1, 2, 3, 4, 5])
def test_the_noise_has_the_table_c_standard_deviation_within_one_percent(severity: int) -> None:
    lin = np.ones((500, 667, 3))  # 1,000,500 samples
    out = cor.night_linear(lin, severity, seed=20261007)
    noise = (out - K[severity]).ravel()
    n = noise.size
    assert abs(float(noise.std()) / SIG[severity] - 1.0) <= 0.01
    assert abs(float(noise.mean())) <= 5.0 * SIG[severity] / math.sqrt(n)


@pytest.mark.req("FR-009-26")
def test_the_noise_is_independent_across_channels_and_neighbouring_pixels() -> None:
    out = cor.night_linear(np.ones((500, 667, 3)), 3, seed=7)
    n = out - K[3]
    bound = 5.0 / math.sqrt(500 * 667)
    for a, b in ((0, 1), (0, 2), (1, 2)):
        assert abs(float(np.corrcoef(n[..., a].ravel(), n[..., b].ravel())[0, 1])) <= bound
    assert abs(float(np.corrcoef(n[:, :-1, 0].ravel(), n[:, 1:, 0].ravel())[0, 1])) <= bound
    assert abs(float(np.corrcoef(n[:-1, :, 1].ravel(), n[1:, :, 1].ravel())[0, 1])) <= bound


@pytest.mark.req("FR-009-26")
def test_a_black_image_gets_the_half_normal_mean_and_is_clipped_at_zero() -> None:
    sigma = SIG[5]
    out = cor.night_linear(np.zeros((500, 667, 3)), 5, seed=11)
    assert out.min() >= 0.0
    assert out.max() <= 1.0
    assert abs(float((out == 0.0).mean()) - 0.5) <= 5.0 * 0.5 / math.sqrt(out.size)
    assert float(out.mean()) == pytest.approx(sigma / math.sqrt(2.0 * math.pi), abs=1e-4)  # 0.003989


@pytest.mark.req("FR-009-26")
def test_the_output_never_leaves_the_unit_interval_even_with_a_large_noise() -> None:
    lin = np.random.default_rng(4).random((50, 50, 3))
    out = cor.night_linear(lin, 1, seed=3, sigma_n=2.0)
    assert out.min() >= 0.0
    assert out.max() <= 1.0
    assert (out == 0.0).any()
    assert (out == 1.0).any()


@pytest.mark.req("FR-009-26")
def test_the_noise_is_seeded_and_counter_based() -> None:
    lin = np.random.default_rng(5).random((16, 16, 3))
    a = cor.night_linear(lin, 4, seed=1)
    b = cor.night_linear(lin, 4, seed=1)
    c = cor.night_linear(lin, 4, seed=2)
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, c)
    # counter-based: the noise of the first rows does not depend on how many rows follow
    big = cor.night_linear(np.ones((32, 16, 3)), 4, seed=9)
    small = cor.night_linear(np.ones((8, 16, 3)), 4, seed=9)
    np.testing.assert_array_equal(big[:8], small)


@pytest.mark.req("FR-009-26")
def test_an_8_bit_image_is_decoded_exposed_and_re_encoded_with_half_even_rounding() -> None:
    img = np.full((3, 3, 3), 255, dtype=np.uint8)  # linear 1.0
    res = cor.night(img, 2, seed=1, sigma_n=0.0)
    assert res.image.dtype == np.uint8
    want = int(np.rint(255.0 * _enc(K[2] * _dec(1.0))))
    assert (res.image == want).all()
    assert res.record == {"corruption": "night", "severity": 2, "seed": 1}
    grey = np.full((2, 2, 3), 128, dtype=np.uint8)
    out = cor.night(grey, 3, seed=1, sigma_n=0.0).image
    assert int(out[0, 0, 0]) == int(np.rint(255.0 * _enc(K[3] * _dec(128 / 255))))


@pytest.mark.req("FR-009-26")
def test_a_float_srgb_image_gives_a_float_result() -> None:
    img = np.full((2, 2, 3), 1.0)
    res = cor.night(img, 1, seed=0, sigma_n=0.0)
    assert res.image.dtype == np.float64
    assert res.image[0, 0, 0] == pytest.approx(_enc(0.5), rel=1e-12)


@pytest.mark.req("P-009-04")
@given(a=st.integers(0, 3), b=st.integers(0, 3), seed=st.integers(0, 2**32 - 1))
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_exposure_factors_compose_multiplicatively(a: int, b: int, seed: int) -> None:
    lin = np.random.default_rng(seed).random((5, 6, 3))
    k1, k2 = 2.0 ** (-a), 2.0 ** (-b)
    np.testing.assert_allclose(
        cor.apply_exposure(cor.apply_exposure(lin, k1), k2), cor.apply_exposure(lin, k1 * k2), rtol=1e-12, atol=0.0
    )
    np.testing.assert_allclose(cor.apply_exposure(lin, k1), k1 * lin, rtol=1e-12, atol=0.0)


@pytest.mark.req("P-009-04")
@given(seed=st.integers(0, 2**32 - 1), h=st.integers(1, 32), w=st.integers(1, 32))
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_the_noise_free_mean_luminance_is_two_to_the_minus_s_times_the_input_and_non_increasing(
    seed: int, h: int, w: int
) -> None:
    lin = np.random.default_rng(seed).random((h, w, 3))
    lum_in = float((lin @ W709).mean())
    means = [float((cor.night_linear(lin, s, seed=0, sigma_n=0.0) @ W709).mean()) for s in range(1, 6)]
    for s, m in zip(range(1, 6), means, strict=True):
        assert m == pytest.approx(2.0 ** (-s) * lum_in, rel=1e-12, abs=1e-15)
    assert all(later <= earlier + 1e-15 for earlier, later in itertools.pairwise(means))
    assert means[0] <= lum_in + 1e-15


def _dihedral(k: int, a: np.ndarray) -> np.ndarray:
    b = np.rot90(a, k % 4, axes=(0, 1))
    return b[:, ::-1] if k >= 4 else b


@pytest.mark.req("P-009-03")
@given(
    seed=st.integers(0, 2**32 - 1),
    h=st.integers(1, 32),
    w=st.integers(1, 32),
    severity=st.integers(1, 5),
    k=st.integers(0, 7),
    perm_seed=st.integers(0, 2**32 - 1),
)
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_the_noise_free_night_commutes_with_permutations_and_dihedral_maps(
    seed: int, h: int, w: int, severity: int, k: int, perm_seed: int
) -> None:
    lin = np.random.default_rng(seed).random((h, w, 3))
    night0 = lambda x: cor.night_linear(x, severity, seed=0, sigma_n=0.0)  # noqa: E731
    np.testing.assert_array_equal(night0(_dihedral(k, lin)), _dihedral(k, night0(lin)))
    perm = np.random.default_rng(perm_seed).permutation(h * w)
    flat = lin.reshape(h * w, 3)
    np.testing.assert_array_equal(
        night0(flat[perm].reshape(h, w, 3)).reshape(h * w, 3), night0(lin).reshape(h * w, 3)[perm]
    )

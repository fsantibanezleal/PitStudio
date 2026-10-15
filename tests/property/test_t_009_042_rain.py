# ruff: noqa: E501
"""T-009-042 - FR-009-27, P-009-05: rain streaks and contrast.

Oracles (independent of the code under test):
- Table C of spec 009 typed out: contrast c_s = 0.9 .. 0.5, streak coverage rho_s = 0.005, 0.01, 0.02, 0.03, 0.05, streak length l_s = 8, 12, 16, 20,
  24 px at 1,280 px width (scaled by W / 1280), rain light L_r = 0.85 (linear);
- analytical closed form of FR-009-27 given the mask m: out = (1 - m) [c I + (1 - c) Imean] + m L_r with Imean the per-channel image mean; for a CONSTANT
  image Imean = I, so unmasked pixels are unchanged and masked pixels equal L_r exactly (written out in the tests);
- geometry of the streaks (hand derivation from the spec text): each streak is a straight segment of Euclidean length l_s W / 1280, its angle from the vertical
  is theta + jitter with one theta ~ U(-15, 15) degrees per image and jitter ~ U(-2, 2) degrees per streak, so every angle lies in [theta - 2, theta + 2], the spread
  of one image's angles is at most 4 degrees and no angle exceeds 17 degrees in magnitude; start points are uniform over the image (Kolmogorov-Smirnov,
  `scipy.stats.kstest`, p >= 1e-3, fixed seed); the mean angle of an image estimates theta, uniform over [-15, 15] across seeds (KS, p >= 1e-3);
- the stopping rule "added until the covered fraction first reaches rho": rasterising all streaks reaches rho and rasterising all but the last stays below it;
- P-009-05, analytical bound: one streak adds at most its rasterised length plus one pixel, so rho_s <= f < rho_s + (l_s W / 1280 + 1) / (W H) for W in [640, 1920],
  H in [360, 1080], any seed; rho_s grows by at least 0.005 per severity while the overshoot is below 6e-5, hence f is non-decreasing in s for a fixed seed;
- 8-bit path: unmasked pixels of a constant code-128 image stay 128, masked pixels become round-half-to-even(255 * srgb_encode(0.85)) (hand evaluation of the IEC formula).

Expected public API (module `pitstudio_pipeline.perception.corruptions`, package under `pipeline/src/`; see tests/unit/test_t_009_040_dust.py for the transfer
functions and `CorruptionResult`):

    RAIN_C: dict[int, float]; RAIN_RHO: dict[int, float]; RAIN_LEN_PX: dict[int, float]      Table C (length at 1,280 px width); L_R: float == 0.85
    Streak                           frozen dataclass: x0, y0, x1, y1 (float pixel coordinates, x to the right, y downwards)
    rain_streaks(height: int, width: int, severity: int, *, seed: int) -> list[Streak]
        The streaks of one image, in drawing order: starts uniform over [0, width) x [0, height); length l_s * width / 1280; angle from the vertical
        (degrees, atan2(dx, dy), y downwards) = theta + jitter as above; streaks are added until the rasterised union first covers >= rho_s of the pixels. Deterministic in
        the seed.
    rasterise(streaks: Sequence[Streak], height: int, width: int) -> ndarray     bool (height, width): 1-px-wide lines clipped to the image
    rain_mask(height: int, width: int, severity: int, *, seed: int) -> ndarray   == rasterise(rain_streaks(...), height, width)
    rain_linear(lin: ndarray, severity: int, *, seed: int) -> ndarray
        lin (H, W, 3) float64 linear RGB: (1 - m) [c_s lin + (1 - c_s) lin.mean(axis=(0, 1))] + m L_r with m = rain_mask(H, W, severity, seed=seed); severity 0 returns a copy.
    rain(image: ndarray, severity: int, *, seed: int) -> CorruptionResult
        uint8 / float sRGB in, same dtype out (decode -> rain_linear -> encode); record = {"corruption": "rain", "severity": severity, "seed": seed}; severity 0 returns the
        input unchanged.
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
C = {1: 0.9, 2: 0.8, 3: 0.7, 4: 0.6, 5: 0.5}
RHO = {1: 0.005, 2: 0.01, 3: 0.02, 4: 0.03, 5: 0.05}
LEN = {1: 8.0, 2: 12.0, 3: 16.0, 4: 20.0, 5: 24.0}


def _angle(s: cor.Streak) -> float:
    return math.degrees(math.atan2(s.x1 - s.x0, s.y1 - s.y0))


def _length(s: cor.Streak) -> float:
    return math.hypot(s.x1 - s.x0, s.y1 - s.y0)


def _enc(x: float) -> float:
    return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055


@pytest.mark.req("FR-009-27")
def test_table_c_rain_constants() -> None:
    assert dict(cor.RAIN_C) == C
    assert dict(cor.RAIN_RHO) == RHO
    assert dict(cor.RAIN_LEN_PX) == LEN
    assert cor.L_R == 0.85


# ---------------------------------------------------------------- closed forms given the mask


@pytest.mark.req("FR-009-27")
@pytest.mark.parametrize("severity", [1, 2, 3, 4, 5])
def test_a_constant_image_keeps_its_unmasked_pixels_and_masked_pixels_equal_the_rain_light(severity: int) -> None:
    lin = np.empty((90, 160, 3))
    lin[..., 0], lin[..., 1], lin[..., 2] = 0.2, 0.4, 0.6
    out = cor.rain_linear(lin, severity, seed=3)
    m = cor.rain_mask(90, 160, severity, seed=3)
    assert m.any()
    assert not m.all()
    np.testing.assert_allclose(out[~m], lin[~m], rtol=0.0, atol=1e-12)
    np.testing.assert_allclose(out[m], 0.85, rtol=0.0, atol=1e-15)


@pytest.mark.req("FR-009-27")
@pytest.mark.parametrize("severity", [1, 3, 5])
def test_a_general_image_follows_the_contrast_and_streak_formula(severity: int) -> None:
    lin = np.random.default_rng(10).random((72, 128, 3))
    out = cor.rain_linear(lin, severity, seed=9)
    m = cor.rain_mask(72, 128, severity, seed=9)[..., None]
    mean = lin.mean(axis=(0, 1))
    expected = (1 - m) * (C[severity] * lin + (1 - C[severity]) * mean) + m * 0.85
    np.testing.assert_allclose(out, expected, rtol=0.0, atol=1e-12)
    assert out.dtype == np.float64


@pytest.mark.req("FR-009-27")
def test_severity_zero_returns_the_input_and_the_input_is_not_modified() -> None:
    lin = np.random.default_rng(1).random((20, 30, 3))
    before = lin.copy()
    np.testing.assert_array_equal(cor.rain_linear(lin, 0, seed=1), lin)
    cor.rain_linear(lin, 4, seed=1)
    np.testing.assert_array_equal(lin, before)
    img = np.random.default_rng(2).integers(0, 256, size=(20, 30, 3), dtype=np.uint8)
    res = cor.rain(img, 0, seed=1)
    np.testing.assert_array_equal(res.image, img)
    assert res.record == {"corruption": "rain", "severity": 0, "seed": 1}


@pytest.mark.req("FR-009-27")
def test_an_8_bit_constant_image_changes_only_on_the_streaks_to_the_encoded_rain_light() -> None:
    img = np.full((72, 128, 3), 128, dtype=np.uint8)
    res = cor.rain(img, 3, seed=4)
    m = cor.rain_mask(72, 128, 3, seed=4)
    assert res.image.dtype == np.uint8
    assert (res.image[~m] == 128).all()
    assert (res.image[m] == int(np.rint(255.0 * _enc(0.85)))).all()  # 237
    assert res.record == {"corruption": "rain", "severity": 3, "seed": 4}


@pytest.mark.req("FR-009-27")
def test_a_float_srgb_image_gives_a_float_result() -> None:
    res = cor.rain(np.full((40, 60, 3), 0.5), 2, seed=1)
    assert res.image.dtype == np.float64
    assert 0.0 <= float(res.image.min()) <= float(res.image.max()) <= 1.0


# ---------------------------------------------------------------- streak geometry


@pytest.mark.req("FR-009-27")
@pytest.mark.parametrize("severity", [1, 2, 3, 4, 5])
@pytest.mark.parametrize(("height", "width"), [(360, 640), (720, 1280), (1080, 1920)])
def test_every_streak_has_the_length_scaled_by_the_image_width_and_a_bounded_angle(
    severity: int, height: int, width: int
) -> None:
    streaks = cor.rain_streaks(height, width, severity, seed=5)
    assert streaks
    angles = [_angle(s) for s in streaks]
    for s in streaks:
        assert _length(s) == pytest.approx(LEN[severity] * width / 1280.0, rel=1e-9)
        assert s.y1 > s.y0 or math.isclose(s.y1, s.y0)  # streaks run downwards (angle from the vertical, |angle| <= 17)
        assert 0.0 <= s.x0 < width
        assert 0.0 <= s.y0 < height
    assert max(abs(a) for a in angles) <= 17.0 + 1e-9
    assert max(angles) - min(angles) <= 4.0 + 1e-9  # one image angle, per-streak jitter within +-2 degrees


@pytest.mark.req("FR-009-27")
def test_the_image_angle_is_uniform_over_minus_15_to_15_degrees_across_seeds() -> None:
    from scipy import stats

    centres = []
    for seed in range(300):
        angles = [_angle(s) for s in cor.rain_streaks(360, 640, 5, seed=seed)]
        centres.append((max(angles) + min(angles)) / 2.0)
    assert min(centres) < -10.0
    assert max(centres) > 10.0
    assert max(abs(c) for c in centres) <= 15.0 + 2.0
    assert stats.kstest((np.array(centres) + 15.0) / 30.0, "uniform").pvalue >= 1e-3


@pytest.mark.req("FR-009-27")
def test_the_streak_start_points_are_uniform_over_the_image() -> None:
    from scipy import stats

    xs, ys = [], []
    for seed in range(40):
        for s in cor.rain_streaks(360, 640, 5, seed=seed):
            xs.append(s.x0 / 640.0)
            ys.append(s.y0 / 360.0)
    assert len(xs) > 2000
    assert stats.kstest(xs, "uniform").pvalue >= 1e-3
    assert stats.kstest(ys, "uniform").pvalue >= 1e-3


@pytest.mark.req("FR-009-27")
@pytest.mark.parametrize("severity", [1, 3, 5])
def test_the_mask_is_the_one_pixel_wide_union_of_the_streaks(severity: int) -> None:
    h, w = 120, 200
    streaks = cor.rain_streaks(h, w, severity, seed=8)
    m = cor.rain_mask(h, w, severity, seed=8)
    assert m.dtype == bool
    assert m.shape == (h, w)
    np.testing.assert_array_equal(m, cor.rasterise(streaks, h, w))
    ys, xs = np.nonzero(m)
    for y, x in zip(
        ys[:400], xs[:400], strict=True
    ):  # every set pixel lies within one pixel of some streak (1-px-wide lines)
        best = min(_dist_to_segment(x, y, s) for s in streaks)
        assert best <= 1.0, (x, y, best)


def _dist_to_segment(px: float, py: float, s: cor.Streak) -> float:
    vx, vy = s.x1 - s.x0, s.y1 - s.y0
    t = max(0.0, min(1.0, ((px - s.x0) * vx + (py - s.y0) * vy) / (vx * vx + vy * vy)))
    return math.hypot(px - (s.x0 + t * vx), py - (s.y0 + t * vy))


@pytest.mark.req("FR-009-27")
@pytest.mark.parametrize("severity", [1, 2, 3, 4, 5])
def test_streaks_are_added_until_the_covered_fraction_first_reaches_rho(severity: int) -> None:
    h, w = 360, 640
    streaks = cor.rain_streaks(h, w, severity, seed=21)
    full = cor.rasterise(streaks, h, w)
    short = cor.rasterise(streaks[:-1], h, w)
    assert full.sum() >= RHO[severity] * h * w - 1e-9
    assert short.sum() < RHO[severity] * h * w


@pytest.mark.req("FR-009-27")
def test_the_streaks_and_the_mask_are_deterministic_in_the_seed() -> None:
    a = cor.rain_streaks(120, 200, 3, seed=1)
    assert a == cor.rain_streaks(120, 200, 3, seed=1)
    assert a != cor.rain_streaks(120, 200, 3, seed=2)
    np.testing.assert_array_equal(cor.rain_mask(120, 200, 3, seed=1), cor.rain_mask(120, 200, 3, seed=1))


# ---------------------------------------------------------------- P-009-05


@pytest.mark.req("P-009-05")
@given(
    width=st.integers(640, 1920),
    height=st.integers(360, 1080),
    seed=st.integers(0, 2**32 - 1),
    severity=st.integers(1, 5),
)
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_the_realised_coverage_is_within_one_streak_of_the_target(
    width: int, height: int, seed: int, severity: int
) -> None:
    n = int(cor.rain_mask(height, width, severity, seed=seed).sum())
    f = n / (width * height)
    assert f >= RHO[severity] - 1e-12
    assert f < RHO[severity] + (LEN[severity] * width / 1280.0 + 1.0) / (width * height)


@pytest.mark.req("P-009-05")
@given(width=st.integers(640, 1920), height=st.integers(360, 1080), seed=st.integers(0, 2**32 - 1))
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_the_coverage_is_non_decreasing_in_the_severity_for_a_fixed_seed(
    width: int, height: int, seed: int
) -> None:
    f = [cor.rain_mask(height, width, s, seed=seed).sum() / (width * height) for s in range(1, 6)]
    assert all(b >= a for a, b in itertools.pairwise(f))

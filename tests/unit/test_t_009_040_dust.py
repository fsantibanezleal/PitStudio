# ruff: noqa: E501
"""T-009-040 (unit half) - FR-009-25, FR-009-28, P-009-06: dust haze with depth and the sRGB transfer function.

Oracles (independent of the code under test):
- the Beer-Lambert / Koschmieder haze of spec 009 FR-009-25 evaluated with `math.exp` in this file: t = exp(-sigma_s * d / 1000) (sigma in
  1/km, d in m, Table C: 0.75, 1.5, 3.0, 6.0, 12.0), out = t * I + (1 - t) * A with the airlight A = (0.58, 0.46, 0.31) in linear RGB; hand
  values: sigma 3.0 at d = 500 m gives t = exp(-1.5) = 0.22313016014842982; d = 0 gives t = 1 (identity); d = 100 km at severity 5 gives
  t = exp(-1200) = 0 in float64 (the pixel is exactly A);
- the IEC 61966-2-1 transfer function written out in this file: decode v <= 0.04045 -> v / 12.92, else ((v + 0.055) / 1.055)^2.4; encode
  x <= 0.0031308 -> 12.92 x, else 1.055 x^(1/2.4) - 0.055 (sRGB standard; the 8-bit value of x is round-half-to-even of 255 * encode(x));
  the code 128 decodes to 0.21586050011389926 (hand evaluation of the decode formula);
- round-half-to-even: for every k in 0..254 the float (k + 0.5) / 255 times 255 is exactly k + 0.5 in float64 (checked while writing), so
  `quantize_u8((k + 0.5) / 255)` must give k for even k and k + 1 for odd k (Python's `round`/numpy `rint` rule, IEEE 754 roundTiesToEven);
- P-009-06: decode(encode(x)) = x (atol 1e-12) for x in [0, 1] and encode_u8(decode_u8(c)) = c for every code 0..255 (exact).

Expected public API (module `pitstudio_pipeline.perception.corruptions`, package under `pipeline/src/`):

    SIGMA_KM: dict[int, float]       {1: 0.75, 2: 1.5, 3: 3.0, 4: 6.0, 5: 12.0}      (Table C, dust extinction in 1/km)
    AIRLIGHT: tuple[float, float, float]        (0.58, 0.46, 0.31) linear RGB
    D_REF_M: float                   100.0 (FR-009-28)
    srgb_decode(v: ndarray) -> ndarray          IEC 61966-2-1 sRGB -> linear, float64, elementwise
    srgb_encode(x: ndarray) -> ndarray          linear -> sRGB, float64, elementwise (x clipped to [0, 1] first)
    decode_u8(codes: ndarray) -> ndarray        uint8 codes -> linear float64: srgb_decode(codes / 255)
    quantize_u8(v: ndarray) -> ndarray          uint8: numpy.rint(255 * v) clipped to 0..255 (round half to even), v = sRGB in [0, 1]
    encode_u8(x: ndarray) -> ndarray            quantize_u8(srgb_encode(x))
    transmittance(depth_m: ndarray, severity: int) -> ndarray      exp(-SIGMA_KM[severity] * depth_m / 1000), float64
    dust_linear(lin: ndarray, depth_m: ndarray, severity: int) -> ndarray
        lin (H, W, 3) float64 linear RGB, depth_m (H, W) float64 metres >= 0: t * lin + (1 - t) * AIRLIGHT (t broadcast over channels);
        severity 0 returns an equal copy of `lin`; severity 1..5 as Table C. (Argument checks: see test_t_009_043.)
    CorruptionResult                 frozen dataclass: image: ndarray, record: dict
    dust(image: ndarray, depth_m: ndarray | None, severity: int) -> CorruptionResult
        image (H, W, 3) is uint8 sRGB codes or float sRGB in [0, 1]; it is decoded to linear, dust_linear is applied, and the result is
        re-encoded: uint8 input gives uint8 output (encode_u8, round half to even), float input gives float64 output (srgb_encode, no
        rounding). depth_m None means the constant reference depth D_REF_M and record["depth_assumed"] is True (FR-009-28); otherwise False.
        record = {"corruption": "dust", "severity": severity, "depth_assumed": bool}. Severity 0 returns the input array unchanged (same
        values and dtype) with the same record fields.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.perception import corruptions as cor  # noqa: E402

SIGMA = {1: 0.75, 2: 1.5, 3: 3.0, 4: 6.0, 5: 12.0}  # Table C, typed from the spec
A = (0.58, 0.46, 0.31)


def _dec(v: float) -> float:
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _enc(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055


def _haze(i: float, d: float, s: int, c: int) -> float:
    t = math.exp(-SIGMA[s] * d / 1000.0)
    return t * i + (1.0 - t) * A[c]


# ---------------------------------------------------------------- constants


@pytest.mark.req("FR-009-25")
def test_table_c_dust_extinction_airlight_and_reference_depth() -> None:
    assert dict(cor.SIGMA_KM) == SIGMA
    assert tuple(cor.AIRLIGHT) == A
    assert cor.D_REF_M == 100.0


# ---------------------------------------------------------------- sRGB transfer function


@pytest.mark.req("P-009-06")
def test_srgb_decode_and_encode_match_the_iec_formulas_at_hand_points() -> None:
    v = np.array([0.0, 0.01, 0.04045, 0.04046, 0.25, 0.5, 1.0])
    np.testing.assert_allclose(cor.srgb_decode(v), [_dec(float(x)) for x in v], rtol=1e-12, atol=1e-15)
    x = np.array([0.0, 0.001, 0.0031308, 0.0031309, 0.2, 0.5, 1.0])
    np.testing.assert_allclose(cor.srgb_encode(x), [_enc(float(a)) for a in x], rtol=1e-12, atol=1e-15)
    assert cor.srgb_decode(np.array([0.0]))[0] == 0.0
    assert cor.srgb_decode(np.array([1.0]))[0] == pytest.approx(1.0, abs=1e-12)


@pytest.mark.req("P-009-06")
def test_the_code_128_decodes_to_the_hand_value() -> None:
    assert cor.decode_u8(np.array([128], dtype=np.uint8))[0] == pytest.approx(_dec(128 / 255), rel=1e-12)
    assert cor.decode_u8(np.array([128], dtype=np.uint8))[0] == pytest.approx(0.21586050011389926, rel=1e-9)


@pytest.mark.req("P-009-06")
def test_decode_of_encode_returns_the_value_for_a_float_grid() -> None:
    x = np.linspace(0.0, 1.0, 2001)
    np.testing.assert_allclose(cor.srgb_decode(cor.srgb_encode(x)), x, atol=1e-12)
    np.testing.assert_allclose(cor.srgb_encode(cor.srgb_decode(x)), x, atol=1e-12)


@pytest.mark.req("P-009-06")
def test_every_8_bit_code_survives_decode_then_encode_exactly() -> None:
    codes = np.arange(256, dtype=np.uint8)
    out = cor.encode_u8(cor.decode_u8(codes))
    assert out.dtype == np.uint8
    np.testing.assert_array_equal(out, codes)


@pytest.mark.req("FR-009-25")
def test_quantisation_rounds_half_to_even() -> None:
    k = np.arange(255)
    ties = (k + 0.5) / 255.0  # 255 * ties == k + 0.5 exactly in float64
    expected = np.where(k % 2 == 0, k, k + 1).astype(np.uint8)
    got = cor.quantize_u8(ties)
    assert got.dtype == np.uint8
    np.testing.assert_array_equal(got, expected)
    np.testing.assert_array_equal(
        cor.quantize_u8(np.array([-0.2, 0.0, 1.0, 1.7])), np.array([0, 0, 255, 255], dtype=np.uint8)
    )


# ---------------------------------------------------------------- FR-009-25: dust in linear RGB


@pytest.mark.req("FR-009-25")
def test_transmittance_is_exp_of_minus_sigma_times_depth_in_kilometres() -> None:
    d = np.array([0.0, 1.0, 100.0, 500.0, 2000.0])
    for s, sigma in SIGMA.items():
        np.testing.assert_allclose(cor.transmittance(d, s), np.exp(-sigma * d / 1000.0), rtol=1e-12, atol=0.0)
    assert cor.transmittance(np.array([500.0]), 3)[0] == pytest.approx(0.22313016014842982, rel=1e-12)
    assert cor.transmittance(np.array([0.0]), 5)[0] == 1.0


@pytest.mark.req("FR-009-25")
@pytest.mark.parametrize("severity", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("depth", [0.0, 1.0, 250.0, 500.0, 2000.0])
def test_constant_linear_image_and_depth_give_the_closed_form_haze(severity: int, depth: float) -> None:
    lin = np.empty((4, 5, 3))
    lin[..., 0], lin[..., 1], lin[..., 2] = 0.2, 0.4, 0.6
    out = cor.dust_linear(lin, np.full((4, 5), depth), severity)
    assert out.shape == (4, 5, 3)
    assert out.dtype == np.float64
    for c, i in enumerate((0.2, 0.4, 0.6)):
        np.testing.assert_allclose(out[..., c], _haze(i, depth, severity, c), rtol=1e-12, atol=1e-15)


@pytest.mark.req("FR-009-25")
def test_zero_depth_is_the_identity_and_infinite_depth_is_the_airlight() -> None:
    rng = np.random.default_rng(3)
    lin = rng.random((6, 7, 3))
    np.testing.assert_allclose(cor.dust_linear(lin, np.zeros((6, 7)), 4), lin, rtol=0.0, atol=1e-15)
    far = cor.dust_linear(lin, np.full((6, 7), 100_000.0), 5)  # t = exp(-1200) underflows to 0
    np.testing.assert_allclose(far, np.broadcast_to(np.array(A), (6, 7, 3)), rtol=0.0, atol=1e-15)


@pytest.mark.req("FR-009-25")
def test_depth_varies_per_pixel() -> None:
    lin = np.full((1, 3, 3), 0.1)
    depth = np.array([[0.0, 300.0, 900.0]])
    out = cor.dust_linear(lin, depth, 2)
    for j, d in enumerate((0.0, 300.0, 900.0)):
        for c in range(3):
            assert out[0, j, c] == pytest.approx(_haze(0.1, d, 2, c), rel=1e-12)


@pytest.mark.req("FR-009-25")
def test_severity_zero_returns_the_input_unchanged() -> None:
    rng = np.random.default_rng(5)
    lin = rng.random((3, 3, 3))
    np.testing.assert_array_equal(cor.dust_linear(lin, np.full((3, 3), 400.0), 0), lin)
    img = rng.integers(0, 256, size=(3, 3, 3), dtype=np.uint8)
    res = cor.dust(img, np.full((3, 3), 400.0), 0)
    assert res.image.dtype == np.uint8
    np.testing.assert_array_equal(res.image, img)
    assert res.record["corruption"] == "dust"
    assert res.record["severity"] == 0


@pytest.mark.req("FR-009-25")
def test_the_input_arrays_are_not_modified() -> None:
    rng = np.random.default_rng(6)
    lin, depth = rng.random((3, 4, 3)), rng.random((3, 4)) * 300.0
    lin0, depth0 = lin.copy(), depth.copy()
    cor.dust_linear(lin, depth, 3)
    np.testing.assert_array_equal(lin, lin0)
    np.testing.assert_array_equal(depth, depth0)


@pytest.mark.req("FR-009-25")
def test_a_uint8_image_is_decoded_hazed_in_linear_light_and_re_encoded_with_half_even_rounding() -> None:
    img = np.full((2, 3, 3), 128, dtype=np.uint8)
    res = cor.dust(img, np.full((2, 3), 1000.0), 2)
    assert res.image.dtype == np.uint8
    assert res.image.shape == (2, 3, 3)
    lin = _dec(128 / 255)
    for c in range(3):
        want = np.rint(255.0 * _enc(_haze(lin, 1000.0, 2, c)))  # numpy.rint: ties to even
        assert int(res.image[0, 0, c]) == int(want)
    assert res.record == {"corruption": "dust", "severity": 2, "depth_assumed": False}


@pytest.mark.req("FR-009-25")
def test_a_float_srgb_image_keeps_float_precision_without_rounding() -> None:
    img = np.full((2, 2, 3), 0.5)
    res = cor.dust(img, np.full((2, 2), 700.0), 4)
    assert res.image.dtype == np.float64
    for c in range(3):
        assert res.image[0, 0, c] == pytest.approx(_enc(_haze(_dec(0.5), 700.0, 4, c)), rel=1e-12)
    assert 0.0 <= float(res.image.min()) <= float(res.image.max()) <= 1.0


@pytest.mark.req("FR-009-25")
def test_the_haze_lifts_dark_pixels_towards_the_airlight_and_darkens_nothing_below_it() -> None:
    img = np.zeros((2, 2, 3), dtype=np.uint8)
    out = cor.dust(img, np.full((2, 2), 800.0), 3).image.astype(float)
    want = [255.0 * _enc(_haze(0.0, 800.0, 3, c)) for c in range(3)]
    np.testing.assert_allclose(out[0, 0], np.rint(want), atol=0.0)
    assert (out[0, 0] > 0).all()


# ---------------------------------------------------------------- FR-009-28: no depth map


@pytest.mark.req("FR-009-28")
def test_without_a_depth_map_the_reference_depth_of_100_m_is_used_and_flagged() -> None:
    rng = np.random.default_rng(11)
    img = rng.integers(0, 256, size=(5, 6, 3), dtype=np.uint8)
    for s in (1, 3, 5):
        a = cor.dust(img, None, s)
        b = cor.dust(img, np.full((5, 6), 100.0), s)
        np.testing.assert_array_equal(a.image, b.image)
        assert a.record == {"corruption": "dust", "severity": s, "depth_assumed": True}
        assert b.record["depth_assumed"] is False


@pytest.mark.req("FR-009-28")
def test_a_float_image_without_depth_uses_d_ref_too() -> None:
    img = np.full((3, 3, 3), 0.3)
    a = cor.dust(img, None, 4)
    b = cor.dust(img, np.full((3, 3), cor.D_REF_M), 4)
    np.testing.assert_allclose(a.image, b.image, rtol=0.0, atol=0.0)
    assert a.record["depth_assumed"] is True

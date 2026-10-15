# ruff: noqa: E501
"""T-009-043 - FR-009-29: hostile inputs of the corruptions raise ValueError naming the argument and return no image.

Oracles (independent of the code under test): hand-written hostile inputs, one per class listed in FR-009-29 (plan 009 test strategy row: NaN, inf, wrong
shape, negative depth, severity 6, unknown name), plus the neighbours of each boundary: float images exactly 0.0 and 1.0 are valid, -0.1 and 1.0001 are not;
severities 0 .. 5 are valid, -1 and 6 are not; a depth of exactly 0 is valid, -1e-9 is not. The expected exception text must contain the argument name
(`image`, `depth_m`, `severity`, `corruption`).

Expected public API (module `pitstudio_pipeline.perception.corruptions`, see tests/unit/test_t_009_040_dust.py, test_t_009_041_night.py and
tests/property/test_t_009_042_rain.py for dust / night / rain):

    CORRUPTIONS: tuple[str, ...]      ("dust", "night", "rain")
    apply_corruption(name: str, image: ndarray, severity: int, *, depth_m: ndarray | None = None, seed: int = 0) -> CorruptionResult
        Dispatches to dust (depth_m used), night or rain (depth_m ignored; seed used). dust(image, depth_m, severity), night(image, severity, *, seed) and
        rain(image, severity, *, seed) apply the same checks themselves. Checks, each raising ValueError whose message contains the argument name:
          corruption: not one of CORRUPTIONS (case-sensitive; None, "", other types);
          severity: not an int in {0, 1, 2, 3, 4, 5} (bool, float, str, None refused);
          image: not a numpy ndarray of shape (H, W, 3) with H, W >= 1 and dtype uint8 or float32 / float64; a float image must be finite and within [0, 1];
          depth_m (dust only, when given): not a float ndarray of shape (H, W) equal to the image's, containing a non-finite value or a value < 0.
        Nothing is returned and the inputs are not modified when a check fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.perception import corruptions as cor  # noqa: E402

H, W = 40, 64
GOOD_U8 = np.full((H, W, 3), 100, dtype=np.uint8)
GOOD_F = np.full((H, W, 3), 0.4)
GOOD_D = np.full((H, W), 250.0)


def _call(name: str, image, severity, depth=None):
    if name == "dust":
        return cor.dust(image, depth, severity)
    if name == "night":
        return cor.night(image, severity, seed=1)
    return cor.rain(image, severity, seed=1)


def _bad_images() -> list[tuple[str, object]]:
    nan = GOOD_F.copy()
    nan[3, 4, 1] = np.nan
    inf = GOOD_F.copy()
    inf[0, 0, 0] = np.inf
    ninf = GOOD_F.copy()
    ninf[1, 1, 1] = -np.inf
    high = GOOD_F.copy()
    high[2, 2, 2] = 1.0001
    low = GOOD_F.copy()
    low[2, 2, 2] = -0.1
    return [
        ("nan", nan),
        ("inf", inf),
        ("-inf", ninf),
        ("above-one", high),
        ("below-zero", low),
        ("2d", np.zeros((H, W), dtype=np.uint8)),
        ("4-channels", np.zeros((H, W, 4), dtype=np.uint8)),
        ("1-channel", np.zeros((H, W, 1), dtype=np.uint8)),
        ("4d", np.zeros((1, H, W, 3), dtype=np.uint8)),
        ("empty-rows", np.zeros((0, W, 3), dtype=np.uint8)),
        ("empty-cols", np.zeros((H, 0, 3), dtype=np.uint8)),
        ("int32", np.zeros((H, W, 3), dtype=np.int32)),
        ("int64", np.zeros((H, W, 3), dtype=np.int64)),
        ("uint16", np.zeros((H, W, 3), dtype=np.uint16)),
        ("bool", np.zeros((H, W, 3), dtype=bool)),
        ("complex", np.zeros((H, W, 3), dtype=complex)),
        ("list", GOOD_U8.tolist()),
        ("none", None),
        ("string", "image.png"),
    ]


BAD_IMAGES = _bad_images()


@pytest.mark.req("FR-009-29")
def test_the_three_corruption_names() -> None:
    assert tuple(cor.CORRUPTIONS) == ("dust", "night", "rain")


@pytest.mark.req("FR-009-29")
@pytest.mark.parametrize("name", ["dust", "night", "rain"])
@pytest.mark.parametrize(("label", "image"), BAD_IMAGES, ids=[b[0] for b in BAD_IMAGES])
def test_a_bad_image_raises_value_error_naming_the_image(name: str, label: str, image: object) -> None:
    with pytest.raises(ValueError, match="image"):
        _call(name, image, 2, GOOD_D if name == "dust" else None)


@pytest.mark.req("FR-009-29")
@pytest.mark.parametrize("severity", [6, 7, -1, 100, 1.5, 2.0, "2", None, True, False, [1], np.int64(9)])
@pytest.mark.parametrize("name", ["dust", "night", "rain"])
def test_a_severity_outside_zero_to_five_or_not_an_int_raises_value_error_naming_severity(
    name: str, severity: object
) -> None:
    with pytest.raises(ValueError, match="severity"):
        _call(name, GOOD_U8, severity, GOOD_D if name == "dust" else None)


@pytest.mark.req("FR-009-29")
@pytest.mark.parametrize("severity", [0, 1, 2, 3, 4, 5])
@pytest.mark.parametrize("name", ["dust", "night", "rain"])
def test_every_severity_from_zero_to_five_is_accepted(name: str, severity: int) -> None:
    res = _call(name, GOOD_U8, severity, GOOD_D if name == "dust" else None)
    assert res.image.shape == (H, W, 3)
    assert res.image.dtype == np.uint8


@pytest.mark.req("FR-009-29")
def test_the_valid_boundaries_are_accepted() -> None:
    edge = np.stack([np.zeros((4, 4)), np.ones((4, 4)), np.full((4, 4), 0.5)], axis=-1)  # floats exactly 0.0 and 1.0
    for name in ("night", "rain"):
        assert _call(name, edge, 2).image.shape == (4, 4, 3)
    assert cor.dust(edge, np.zeros((4, 4)), 2).image.shape == (4, 4, 3)  # a depth of exactly 0 is valid
    one = np.zeros((1, 1, 3), dtype=np.uint8)
    for name in ("dust", "night", "rain"):
        assert _call(name, one, 3, np.zeros((1, 1)) if name == "dust" else None).image.shape == (1, 1, 3)
    assert cor.dust(GOOD_F.astype(np.float32), GOOD_D, 1).image.shape == (H, W, 3)


@pytest.mark.req("FR-009-29")
@pytest.mark.parametrize(
    ("label", "depth"),
    [
        ("nan", np.where(np.arange(H * W).reshape(H, W) == 7, np.nan, 250.0)),
        ("inf", np.where(np.arange(H * W).reshape(H, W) == 7, np.inf, 250.0)),
        ("-inf", np.where(np.arange(H * W).reshape(H, W) == 7, -np.inf, 250.0)),
        ("negative", np.where(np.arange(H * W).reshape(H, W) == 7, -1e-9, 250.0)),
        ("all-negative", np.full((H, W), -5.0)),
        ("wider", np.full((H, W + 1), 250.0)),
        ("shorter", np.full((H - 1, W), 250.0)),
        ("transposed", np.full((W, H), 250.0)),
        ("3d", np.full((H, W, 1), 250.0)),
        ("1d", np.full((H * W,), 250.0)),
        ("scalar", np.array(250.0)),
        ("list", GOOD_D.tolist()),
        ("string", "depth.npy"),
    ],
)
def test_a_bad_depth_map_raises_value_error_naming_depth_m(label: str, depth: object) -> None:
    with pytest.raises(ValueError, match="depth_m"):
        cor.dust(GOOD_U8, depth, 3)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="depth_m"):
        cor.apply_corruption("dust", GOOD_U8, 3, depth_m=depth)  # type: ignore[arg-type]


@pytest.mark.req("FR-009-29")
@pytest.mark.parametrize("name", ["fog", "", "Dust", "DUST", "dust ", "snow", "rain\n", None, 7, ["dust"], "雨"])
def test_an_unknown_corruption_name_raises_value_error_naming_corruption(name: object) -> None:
    with pytest.raises(ValueError, match="corruption"):
        cor.apply_corruption(name, GOOD_U8, 2, depth_m=GOOD_D)  # type: ignore[arg-type]


@pytest.mark.req("FR-009-29")
@pytest.mark.parametrize("name", ["dust", "night", "rain"])
def test_the_dispatcher_equals_the_direct_call_and_keeps_severity_zero_unchanged(name: str) -> None:
    depth = GOOD_D if name == "dust" else None
    via = cor.apply_corruption(name, GOOD_U8, 3, depth_m=depth, seed=4)
    direct = _call_seeded(name, GOOD_U8, 3, depth, 4)
    np.testing.assert_array_equal(via.image, direct.image)
    assert via.record == direct.record
    zero = cor.apply_corruption(name, GOOD_U8, 0, depth_m=depth, seed=4)
    np.testing.assert_array_equal(zero.image, GOOD_U8)


def _call_seeded(name: str, image, severity, depth, seed):
    if name == "dust":
        return cor.dust(image, depth, severity)
    if name == "night":
        return cor.night(image, severity, seed=seed)
    return cor.rain(image, severity, seed=seed)


@pytest.mark.req("FR-009-29")
def test_a_failed_call_leaves_the_inputs_untouched() -> None:
    img, depth = GOOD_U8.copy(), GOOD_D.copy()
    depth[0, 0] = np.nan
    with pytest.raises(ValueError, match="depth_m"):
        cor.dust(img, depth, 3)
    np.testing.assert_array_equal(img, GOOD_U8)
    assert np.isnan(depth[0, 0])
    assert (depth[1:] == 250.0).all()

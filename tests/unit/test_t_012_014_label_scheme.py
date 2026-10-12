"""T-012-014 - FR-012-18, FR-012-19, P-012-07: three-class target encoding and instance decoding.

Oracles (independent of the code under test):
- hand calculation: label fixtures drawn below with their three-class encodings typed out pixel by pixel
  (0 = background, 1 = interior, 2 = boundary = a foreground pixel with at least one 8-neighbour of a different
  label value, background included);
- a reference encoder written in this file (`_ref_encode`, the FR-012-18 definition in numpy) for the property;
- hand calculation of marker-controlled flooding on a ridge fixture (FR-012-19), traced step by step in the test.
Fixtures keep every foreground pixel at least one pixel away from the image border, because FR-012-18 does not say
how out-of-image neighbours count (reported as an ambiguity).

Expected public API (module `pitstudio_pipeline.fragmentation.labels`, package under `pipeline/src/`):

    encode_three_class(label: np.ndarray) -> np.ndarray
        label: (H, W) integer instance mask (uint16 in the reader, 0 = background, j = instance j).
        Returns (H, W) uint8 with values in {0, 1, 2} per FR-012-18.
    decode_instances(probs: np.ndarray) -> tuple[np.ndarray, np.ndarray]
        probs: (3, H, W) float class probabilities in the order (background, interior, boundary).
        Predicted class = argmax over axis 0. Returns (instances, foreground):
        - instances (H, W) int32, 0 = not assigned, ids 1..n consecutive; seeds = 4-connected components of predicted
          interior pixels with area >= 4 px; every predicted boundary pixel reachable from a seed inside the
          predicted foreground is assigned by marker-controlled watershed (skimage.segmentation.watershed) on the
          boundary probability probs[2], restricted to the predicted foreground;
        - foreground (H, W) bool = predicted interior OR predicted boundary.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.fragmentation import labels  # noqa: E402

EXAMPLES = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "property_tests"
]["ci_examples_per_test"]


def _ref_encode(label: np.ndarray) -> np.ndarray:
    """FR-012-18 written out: compare each pixel with its 8 neighbours (out-of-image padded as background)."""
    h, w = label.shape
    p = np.pad(label, 1, constant_values=0)
    differs = np.zeros((h, w), dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                differs |= p[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w] != label
    return np.where(label == 0, 0, np.where(differs, 2, 1)).astype(np.uint8)


def _one_hot(classes: np.ndarray) -> np.ndarray:
    return np.stack([(classes == c).astype(np.float64) for c in range(3)])


# ---------------------------------------------------------------- FR-012-18 encoding (hand fixtures)

# Two touching 5 x 4 instances (rows 1-5; instance 1 cols 1-4, instance 2 cols 5-8) on a 7 x 10 tile.
TOUCHING = np.zeros((7, 10), dtype=np.uint16)
TOUCHING[1:6, 1:5] = 1
TOUCHING[1:6, 5:9] = 2
TOUCHING_ENC = np.array(
    [
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 2, 2, 2, 2, 2, 2, 2, 2, 0],
        [0, 2, 1, 1, 2, 2, 1, 1, 2, 0],
        [0, 2, 1, 1, 2, 2, 1, 1, 2, 0],
        [0, 2, 1, 1, 2, 2, 1, 1, 2, 0],
        [0, 2, 2, 2, 2, 2, 2, 2, 2, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    ],
    dtype=np.uint8,
)

# Instance 1 fills rows 1-7, cols 1-7 of a 9 x 9 tile except (4, 4), which is a one-pixel instance 2. The pixels
# (3, 3), (3, 5), (5, 3), (5, 5) touch instance 2 only diagonally: they are boundary under the 8-neighbour rule.
DIAGONAL = np.zeros((9, 9), dtype=np.uint16)
DIAGONAL[1:8, 1:8] = 1
DIAGONAL[4, 4] = 2
DIAGONAL_ENC = np.array(
    [
        [0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 2, 2, 2, 2, 2, 2, 2, 0],
        [0, 2, 1, 1, 1, 1, 1, 2, 0],
        [0, 2, 1, 2, 2, 2, 1, 2, 0],
        [0, 2, 1, 2, 2, 2, 1, 2, 0],
        [0, 2, 1, 2, 2, 2, 1, 2, 0],
        [0, 2, 1, 1, 1, 1, 1, 2, 0],
        [0, 2, 2, 2, 2, 2, 2, 2, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0],
    ],
    dtype=np.uint8,
)


@pytest.mark.req("FR-012-18")
def test_two_touching_instances_encode_to_the_hand_drawn_target() -> None:
    enc = labels.encode_three_class(TOUCHING)
    assert enc.dtype == np.uint8
    assert enc.shape == TOUCHING.shape
    np.testing.assert_array_equal(enc, TOUCHING_ENC)


@pytest.mark.req("FR-012-18")
def test_a_diagonal_only_contact_makes_a_boundary_pixel() -> None:
    np.testing.assert_array_equal(labels.encode_three_class(DIAGONAL), DIAGONAL_ENC)
    # 16 interior pixels: the 5 x 5 ring of rows/cols 2-6 minus the 3 x 3 block around (4, 4).
    assert int((labels.encode_three_class(DIAGONAL) == 1).sum()) == 25 - 9 == 16


@pytest.mark.req("FR-012-18")
def test_empty_tile_is_all_background() -> None:
    enc = labels.encode_three_class(np.zeros((16, 16), dtype=np.uint16))
    np.testing.assert_array_equal(enc, np.zeros((16, 16), dtype=np.uint8))


@pytest.mark.req("FR-012-18")
def test_small_isolated_instances() -> None:
    lab = np.zeros((7, 9), dtype=np.uint16)
    lab[3, 1] = 7  # one pixel: boundary
    lab[2:5, 4:7] = 9  # 3 x 3: ring of 8 boundary pixels around one interior pixel
    exp = np.zeros((7, 9), dtype=np.uint8)
    exp[3, 1] = 2
    exp[2:5, 4:7] = 2
    exp[3, 5] = 1
    np.testing.assert_array_equal(labels.encode_three_class(lab), exp)


@pytest.mark.req("FR-012-18")
def test_encoding_depends_only_on_label_equality_not_on_id_values() -> None:
    relabelled = np.where(TOUCHING == 1, 60000, np.where(TOUCHING == 2, 3, 0)).astype(np.uint16)
    np.testing.assert_array_equal(labels.encode_three_class(relabelled), TOUCHING_ENC)


# ---------------------------------------------------------------- FR-012-19 decoding (hand fixtures)


@pytest.mark.req("FR-012-19")
def test_exact_encoding_of_two_touching_rectangles_decodes_to_two_instances() -> None:
    instances, foreground = labels.decode_instances(_one_hot(TOUCHING_ENC))
    assert foreground.dtype == np.bool_
    np.testing.assert_array_equal(foreground, TOUCHING > 0)
    assert instances.shape == TOUCHING.shape
    assert set(np.unique(instances).tolist()) == {0, 1, 2}
    a, b = int(instances[3, 2]), int(instances[3, 7])
    assert a != b
    assert (instances[2:5, 2:4] == a).all()
    assert (instances[2:5, 6:8] == b).all()
    assert (instances[foreground] > 0).all(), "every boundary pixel joins an adjacent instance"
    assert (instances[~foreground] == 0).all()


@pytest.mark.req("FR-012-19")
def test_interiors_touching_only_diagonally_are_two_4_connected_instances() -> None:
    classes = np.zeros((8, 8), dtype=np.uint8)
    classes[1:7, 1:7] = 2
    classes[2:4, 2:4] = 1  # interior A, 4 px
    classes[4:6, 4:6] = 1  # interior B, 4 px, meets A only at the corner (3, 3)-(4, 4)
    instances, foreground = labels.decode_instances(_one_hot(classes))
    np.testing.assert_array_equal(foreground, classes > 0)
    assert int(instances.max()) == 2
    assert instances[2, 2] != instances[5, 5]
    assert (instances[foreground] > 0).all()


@pytest.mark.req("FR-012-19")
def test_interior_components_below_4_px_are_not_instances_but_stay_foreground() -> None:
    classes = np.zeros((7, 8), dtype=np.uint8)
    classes[1:6, 1:7] = 2
    classes[3, 2:5] = 1  # 1 x 3 interior = 3 px < 4
    instances, foreground = labels.decode_instances(_one_hot(classes))
    np.testing.assert_array_equal(foreground, classes > 0)
    assert int(instances.max()) == 0


@pytest.mark.req("FR-012-19")
@pytest.mark.parametrize(
    "cells",
    [
        [(2, 2), (2, 3), (3, 2), (3, 3)],  # 2 x 2 square
        [(2, 2), (3, 2), (4, 2), (4, 3)],  # L-tetromino, 4-connected
    ],
)
def test_interior_component_of_exactly_4_px_is_kept(cells: list[tuple[int, int]]) -> None:
    classes = np.zeros((7, 7), dtype=np.uint8)
    classes[1:6, 1:6] = 2
    for r, c in cells:
        classes[r, c] = 1
    instances, foreground = labels.decode_instances(_one_hot(classes))
    assert int(instances.max()) == 1
    assert (instances[foreground] == 1).all()


@pytest.mark.req("FR-012-19")
def test_boundary_pixels_follow_the_watershed_of_the_boundary_probability() -> None:
    """Ridge fixture, 6 x 12 tile, foreground rows 1-4 and cols 1-10.

    Interior A = rows 2-3, cols 2-3; interior B = rows 2-3, cols 8-9 (one-hot interior probability 0.9).
    Between them, rows 2-3, boundary pixels at cols 4, 5, 6, 7 with boundary probability 0.40, 0.45, 0.50, 0.90;
    the frame (rows 1 and 4, cols 1 and 10) has 0.95. Flooding by increasing boundary probability from the
    markers: col 4 (0.40) joins A, then col 5 (0.45) and col 6 (0.50) join A through it, before B's first
    neighbour col 7 (0.90) is reached; col 7 joins B. The frame (0.95) floods last. A nearest-marker rule would
    instead give col 6 to B, so the test separates the watershed from a distance assignment.
    """
    h, w = 6, 12
    probs = np.zeros((3, h, w))
    probs[0] = 1.0

    def put(r: int, c: int, p_boundary: float, interior: bool = False) -> None:
        if interior:
            probs[:, r, c] = (0.05, 0.90, 0.05)
        else:
            probs[:, r, c] = ((1 - p_boundary) / 2, (1 - p_boundary) / 2, p_boundary)

    for c in range(1, 11):
        put(1, c, 0.95)
        put(4, c, 0.95)
    for r in (2, 3):
        put(r, 1, 0.95)
        put(r, 10, 0.95)
        for c in (2, 3, 8, 9):
            put(r, c, 0.0, interior=True)
        for c, p in zip((4, 5, 6, 7), (0.40, 0.45, 0.50, 0.90), strict=True):
            put(r, c, p)
    instances, foreground = labels.decode_instances(probs)
    expected_fg = np.zeros((h, w), dtype=bool)
    expected_fg[1:5, 1:11] = True
    np.testing.assert_array_equal(foreground, expected_fg)
    a, b = int(instances[2, 2]), int(instances[2, 8])
    assert a != b
    assert {a, b} == {1, 2}
    for r in (2, 3):
        assert [int(instances[r, c]) for c in (4, 5, 6, 7)] == [a, a, a, b]


@pytest.mark.req("FR-012-19")
def test_predicted_foreground_is_the_argmax_interior_or_boundary() -> None:
    classes = TOUCHING_ENC.copy()
    probs = _one_hot(classes) * 0.6 + 0.4 / 3  # still argmax = class, probabilities sum to 1
    probs[:, 1, 1] = (0.5, 0.2, 0.3)  # a corner pixel predicted background
    instances, foreground = labels.decode_instances(probs)
    expected = TOUCHING > 0
    expected[1, 1] = False
    np.testing.assert_array_equal(foreground, expected)
    assert instances[1, 1] == 0


# ---------------------------------------------------------------- P-012-07 round trip on rectangles


@st.composite
def _rectangles(draw) -> np.ndarray:
    """1-40 non-overlapping axis-aligned rectangles of at least 4 x 4 px on 128 x 128, separated or touching.

    P-012-07 states "at least 3 x 3 px", but a 3 x 3 rectangle has a one-pixel interior, which FR-012-19 drops
    (area < 4); the compatible domain (>= 4 x 4, interior >= 2 x 2 = 4 px) is used and the conflict reported.
    Rectangles stay one pixel away from the border (FR-012-18 does not define out-of-image neighbours).
    """
    lab = np.zeros((128, 128), dtype=np.uint16)
    rects: list[tuple[int, int, int, int]] = []
    for _ in range(draw(st.integers(1, 40))):
        h, w = draw(st.integers(4, 24)), draw(st.integers(4, 24))
        if rects and draw(st.booleans()):  # attach to the right or bottom edge of an earlier rectangle
            t0, l0, h0, w0 = rects[draw(st.integers(0, len(rects) - 1))]
            if draw(st.booleans()):
                top, left = t0 + draw(st.integers(-(h - 1), h0 - 1)), l0 + w0
            else:
                top, left = t0 + h0, l0 + draw(st.integers(-(w - 1), w0 - 1))
        else:
            top, left = draw(st.integers(1, 123)), draw(st.integers(1, 123))
        if top < 1 or left < 1 or top + h > 127 or left + w > 127:
            continue
        if (lab[top : top + h, left : left + w] != 0).any():
            continue
        rects.append((top, left, h, w))
        lab[top : top + h, left : left + w] = len(rects)
    if not rects:
        lab[1:5, 1:5] = 1
    return lab


@pytest.mark.req("P-012-07")
@pytest.mark.req("FR-012-18")
@pytest.mark.req("FR-012-19")
@settings(max_examples=EXAMPLES, deadline=None)
@given(lab=_rectangles())
def test_decoding_the_exact_encoding_recovers_foreground_and_instance_count(lab: np.ndarray) -> None:
    enc = labels.encode_three_class(lab)
    np.testing.assert_array_equal(enc, _ref_encode(lab))
    instances, foreground = labels.decode_instances(_one_hot(enc))
    np.testing.assert_array_equal(foreground, lab > 0)
    n_true = len(np.unique(lab[lab > 0]))
    assert len(np.unique(instances[instances > 0])) == n_true
    assert int(instances.max()) == n_true

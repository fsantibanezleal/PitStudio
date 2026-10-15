"""T-009-017 - FR-009-13, P-009-14: crusher-family instances from 8-connected components of the semantic mask.

Oracles (independent of the code under test):
- FR-009-13, hand calculation (plan 009 test strategy): a 32 x 32 mask drawn below with known components; boxes are
  [x_min, y_min, x_max + 1, y_max + 1] in px, areas are pixel counts counted by hand;
- P-009-14, reference implementation `scipy.ndimage.label` with the 3 x 3 all-ones structure (8-connectivity) and
  `scipy.ndimage.find_objects` for the minimal box of each component; equivariance under a horizontal flip: a box
  x-interval [a, b) maps to [W - b, W - a) (hand-derived, spec 009 P-009-14).

Expected public API (module `pitstudio_pipeline.perception.crusher`, package under `pipeline/src/`):

    CrusherInstance                  frozen dataclass: category_id: int (1..5), box_xyxy: tuple[int, int, int, int]
                                     = (x_min, y_min, x_max + 1, y_max + 1), area_px: int (pixel count),
                                     instance_source: str == "connected-components".
    crusher_instances(mask: numpy.ndarray) -> list[CrusherInstance]
        `mask` is a 2-D (H, W) integer array (uint8 in the reader) of class values 0..5 (0 = background): one instance
        per 8-connected component of each non-zero class value (pixels of different classes never join, even when they
        touch). Order: ascending category_id, then raster order of each component's first pixel (row-major).
        An all-zero mask gives []. Pure and deterministic.
        ValueError (message contains "mask") for a non-ndarray, a non-integer dtype (float, bool, object), an array
        that is not 2-D, an empty array (H == 0 or W == 0), or a value outside 0..5 (negative or > 5).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.perception import crusher  # noqa: E402

EXAMPLES = 200


def _hand_mask() -> np.ndarray:
    m = np.zeros((32, 32), dtype=np.uint8)
    m[2:6, 3:9] = 5  # A: boulder, rows 2-5, cols 3-8 -> box (3, 2, 9, 6), 24 px
    m[2:6, 9:11] = 4  # B: person touching A on its right edge -> separate class -> box (9, 2, 11, 6), 8 px
    m[10, 10] = 5  # C: two pixels touching only at a corner -> ONE 8-connected component
    m[11, 11] = 5  #    box (10, 10, 12, 12), 2 px
    m[20:23, 20] = 1  # D: L shape of class 1: (20..22, 20) and (22, 21..23) -> 6 px, box (20, 20, 24, 23)
    m[22, 21:24] = 1
    m[31, 31] = 5  # E: single pixel in the bottom-right corner -> box (31, 31, 32, 32), 1 px
    m[15:17, 0] = 5  # F: two pixels on the left border -> box (0, 15, 1, 17), 2 px
    return m


EXPECTED_HAND = {
    (1, (20, 20, 24, 23), 6),
    (4, (9, 2, 11, 6), 8),
    (5, (3, 2, 9, 6), 24),
    (5, (10, 10, 12, 12), 2),
    (5, (31, 31, 32, 32), 1),
    (5, (0, 15, 1, 17), 2),
}


def _triples(instances: list) -> set[tuple[int, tuple[int, int, int, int], int]]:
    return {(i.category_id, tuple(i.box_xyxy), i.area_px) for i in instances}


@pytest.mark.req("FR-009-13")
def test_the_hand_drawn_mask_gives_exactly_the_hand_counted_instances() -> None:
    out = crusher.crusher_instances(_hand_mask())
    assert len(out) == 6
    assert _triples(out) == EXPECTED_HAND


@pytest.mark.req("FR-009-13")
def test_instances_are_marked_connected_components_and_ordered_by_class_then_raster_order() -> None:
    out = crusher.crusher_instances(_hand_mask())
    assert {i.instance_source for i in out} == {"connected-components"}
    assert [i.category_id for i in out] == [1, 4, 5, 5, 5, 5]
    fives = [i.box_xyxy for i in out if i.category_id == 5]
    # first pixel in raster order: A (row 2), C (row 10), F (row 15), E (row 31)
    assert fives == [(3, 2, 9, 6), (10, 10, 12, 12), (0, 15, 1, 17), (31, 31, 32, 32)]


@pytest.mark.req("FR-009-13")
def test_diagonal_neighbours_join_but_a_gap_of_one_pixel_separates() -> None:
    m = np.zeros((6, 6), dtype=np.uint8)
    m[1, 1] = 3
    m[2, 2] = 3  # diagonal: joined
    m[4, 4] = 3  # (3, 3) is empty: (2, 2) and (4, 4) are two pixels apart: separate
    out = crusher.crusher_instances(m)
    assert _triples(out) == {(3, (1, 1, 3, 3), 2), (3, (4, 4, 5, 5), 1)}


@pytest.mark.req("FR-009-13")
def test_a_ring_is_one_component_and_its_box_is_the_ring_box() -> None:
    m = np.zeros((9, 9), dtype=np.uint8)
    m[2:7, 2:7] = 2
    m[3:6, 3:6] = 0  # 5 x 5 ring of class 2
    out = crusher.crusher_instances(m)
    assert _triples(out) == {(2, (2, 2, 7, 7), 16)}  # 25 - 9 pixels


@pytest.mark.req("FR-009-13")
def test_an_all_background_mask_has_no_instances_and_other_integer_dtypes_work() -> None:
    assert crusher.crusher_instances(np.zeros((4, 7), dtype=np.uint8)) == []
    m = _hand_mask().astype(np.int64)
    assert _triples(crusher.crusher_instances(m)) == EXPECTED_HAND


@pytest.mark.req("FR-009-13")
def test_the_input_mask_is_not_modified() -> None:
    m = _hand_mask()
    before = m.copy()
    crusher.crusher_instances(m)
    np.testing.assert_array_equal(m, before)


@pytest.mark.req("FR-009-13")
@pytest.mark.parametrize(
    "mask",
    [
        np.zeros((4, 4), dtype=np.float32),
        np.zeros((4, 4), dtype=bool),
        np.full((4, 4), np.nan),
        np.zeros((4,), dtype=np.uint8),
        np.zeros((2, 4, 4), dtype=np.uint8),
        np.zeros((0, 4), dtype=np.uint8),
        np.zeros((4, 0), dtype=np.uint8),
        np.full((4, 4), 6, dtype=np.uint8),
        np.full((4, 4), 255, dtype=np.uint8),
        np.full((4, 4), -1, dtype=np.int16),
        [[0, 1], [1, 0]],
        None,
    ],
    ids=[
        "float",
        "bool",
        "nan",
        "1d",
        "3d",
        "no-rows",
        "no-cols",
        "class-6",
        "class-255",
        "negative",
        "list",
        "none",
    ],
)
def test_hostile_masks_are_rejected(mask: object) -> None:
    with pytest.raises(ValueError, match="mask"):
        crusher.crusher_instances(mask)  # type: ignore[arg-type]


def _random_mask(seed: int, h: int, w: int, density: float, n_classes: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    on = rng.random((h, w)) < density
    classes = rng.integers(1, n_classes + 1, size=(h, w))
    return np.where(on, classes, 0).astype(np.uint8)


def _reference(mask: np.ndarray) -> set[tuple[int, tuple[int, int, int, int], int]]:
    """scipy.ndimage.label (8-connectivity) per class; minimal box from find_objects; area from the label image."""
    from scipy import ndimage

    out = set()
    for c in range(1, 6):
        lab, n = ndimage.label(mask == c, structure=np.ones((3, 3), dtype=int))
        for k, sl in enumerate(ndimage.find_objects(lab), start=1):
            ys, xs = sl
            out.add((c, (xs.start, ys.start, xs.stop, ys.stop), int((lab == k).sum())))
        assert n == len(ndimage.find_objects(lab))
    return out


@pytest.mark.req("P-009-14")
@pytest.mark.req("FR-009-13")
@given(
    seed=st.integers(0, 2**32 - 1),
    h=st.integers(1, 64),
    w=st.integers(1, 64),
    density=st.floats(0.0, 1.0),
    n_classes=st.integers(1, 5),
)
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_boxes_are_the_minimal_enclosing_boxes_of_the_8_connected_components(
    seed: int, h: int, w: int, density: float, n_classes: int
) -> None:
    mask = _random_mask(seed, h, w, density, n_classes)
    got = crusher.crusher_instances(mask)
    assert _triples(got) == _reference(mask)
    assert len(got) == len(_triples(got))  # no duplicate instance
    for (
        inst
    ) in got:  # every pixel of the instance's class inside its box is accounted for by some instance of that class
        x0, y0, x1, y1 = inst.box_xyxy
        assert 0 <= x0 < x1 <= w
        assert 0 <= y0 < y1 <= h
        assert (mask[y0:y1, x0:x1] == inst.category_id).sum() >= inst.area_px


@pytest.mark.req("P-009-14")
@given(
    seed=st.integers(0, 2**32 - 1),
    h=st.integers(1, 64),
    w=st.integers(1, 64),
    density=st.floats(0.0, 1.0),
)
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_a_horizontal_flip_maps_every_box_interval_to_its_mirror(
    seed: int, h: int, w: int, density: float
) -> None:
    mask = _random_mask(seed, h, w, density, 5)
    base = crusher.crusher_instances(mask)
    flipped = crusher.crusher_instances(mask[:, ::-1].copy())
    expected = {
        (i.category_id, (w - i.box_xyxy[2], i.box_xyxy[1], w - i.box_xyxy[0], i.box_xyxy[3]), i.area_px) for i in base
    }
    assert _triples(flipped) == expected


@pytest.mark.req("P-009-14")
@given(seed=st.integers(0, 2**32 - 1), h=st.integers(1, 64), w=st.integers(1, 64), density=st.floats(0.0, 1.0))
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_the_instance_areas_add_up_to_the_foreground_pixels(seed: int, h: int, w: int, density: float) -> None:
    mask = _random_mask(seed, h, w, density, 5)
    assert sum(i.area_px for i in crusher.crusher_instances(mask)) == int((mask > 0).sum())

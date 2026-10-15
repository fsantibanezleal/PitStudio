# ruff: noqa: E501, PT018, PT011
"""T-013-041: S3 semantic-component boxes against a reference component labelling.

Requirements: FR-013-17.

Oracle: an independent breadth-first 8-connected labelling written in `sensor_kit` (the plan names `scipy.ndimage.label`, which is
not in the root environment: this reference does the same, one component per 8-connected set of equal class) and hand-built images
with known components (a diagonal contact merges, a gap separates, 15 px is below and 16 px is at the default minimum area).

Expected API (package `pitstudio.sensors.camera`, root environment; NumPy only):
- `camera.component_boxes(semantic, min_area_px=16) -> list[dict]`: `semantic` an integer (h, w) array of semantic ids (every id is a class,
  none is reserved as background). One box per 8-connected component of each id with area >= `min_area_px`: `{"class_id", "x_min", "y_min",
  "x_max", "y_max", "area"}` (inclusive pixel indices), sorted by (class_id, y_min, x_min).
- `camera.BOX_NOTE == "boxes from semantic components; touching instances merge"`.
- `min_area_px < 1` or a non-integer or non-2-D `semantic` raises `ValueError`.
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


def _reference(semantic: np.ndarray, min_area: int) -> list[tuple[int, int, int, int, int, int]]:
    out = []
    for cls in np.unique(semantic):
        for x0, y0, x1, y1, area in kit.label_components_8(semantic == cls):
            if area >= min_area:
                out.append((int(cls), y0, x0, x1, y1, area))
    return sorted(out)


def _got(semantic: np.ndarray, **kw) -> list[tuple[int, int, int, int, int, int]]:
    boxes = camera.component_boxes(semantic, **kw)
    assert boxes == sorted(boxes, key=lambda b: (b["class_id"], b["y_min"], b["x_min"]))
    return sorted((b["class_id"], b["y_min"], b["x_min"], b["x_max"], b["y_max"], b["area"]) for b in boxes)


@pytest.mark.req("FR-013-17")
def test_the_note_is_the_spec_text() -> None:
    assert camera.BOX_NOTE == "boxes from semantic components; touching instances merge"


@pytest.mark.req("FR-013-17")
def test_hand_built_components_and_their_boxes() -> None:
    img = np.ones((20, 30), dtype=np.uint32)  # background class 1 fills everything first
    img[2:6, 3:7] = 2  # a 4 x 4 block (16 px): at the minimum area
    img[10:13, 10:15] = 2  # a 3 x 5 block (15 px): below it
    img[15:18, 20:23] = 3  # 9 px: below
    img[0:4, 20:30] = 3  # 40 px, rows 0-3, columns 20-29
    boxes = camera.component_boxes(img)
    by_class = {}
    for b in boxes:
        by_class.setdefault(b["class_id"], []).append(b)
    assert [(b["x_min"], b["y_min"], b["x_max"], b["y_max"], b["area"]) for b in by_class[2]] == [(3, 2, 6, 5, 16)]
    assert [(b["x_min"], b["y_min"], b["x_max"], b["y_max"], b["area"]) for b in by_class[3]] == [(20, 0, 29, 3, 40)]
    assert len(by_class[1]) == 1 and by_class[1][0]["area"] == 20 * 30 - 16 - 15 - 9 - 40  # the connected remainder
    lowered = camera.component_boxes(img, min_area_px=1)
    assert sum(1 for b in lowered if b["class_id"] == 2) == 2 and sum(1 for b in lowered if b["class_id"] == 3) == 2


@pytest.mark.req("FR-013-17")
def test_diagonal_contact_merges_and_a_gap_separates() -> None:
    img = np.zeros((6, 6), dtype=np.uint32)
    img[1, 1] = img[2, 2] = img[3, 3] = 7  # touching only at corners: one 8-connected component
    img[5, 0] = img[5, 2] = 7  # one empty pixel apart: two more components
    boxes = [b for b in camera.component_boxes(img, min_area_px=1) if b["class_id"] == 7]
    assert sorted((b["x_min"], b["y_min"], b["x_max"], b["y_max"], b["area"]) for b in boxes) == [
        (0, 5, 0, 5, 1),
        (1, 1, 3, 3, 3),
        (2, 5, 2, 5, 1),
    ]


@pytest.mark.req("FR-013-17")
def test_touching_instances_of_one_class_merge_into_one_box() -> None:
    img = np.zeros((10, 20), dtype=np.uint32)
    img[2:8, 2:8] = 5  # two boulders of the same class that touch along a column
    img[2:8, 8:14] = 5
    (box,) = [b for b in camera.component_boxes(img) if b["class_id"] == 5]
    assert (box["x_min"], box["x_max"], box["area"]) == (2, 13, 72)


@pytest.mark.req("FR-013-17")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(0, 2**31 - 1),
    h=st.integers(1, 40),
    w=st.integers(1, 40),
    classes=st.integers(1, 4),
    min_area=st.sampled_from([1, 2, 4, 16, 30]),
)
def test_boxes_equal_the_reference_labelling_on_random_images(
    seed: int, h: int, w: int, classes: int, min_area: int
) -> None:
    rng = np.random.default_rng(seed)
    base = rng.integers(1, classes + 1, (h, w)).astype(np.uint32)
    if h > 8 and w > 8:  # add a few solid rectangles so that larger components exist
        for _ in range(4):
            y, x = int(rng.integers(0, h - 4)), int(rng.integers(0, w - 4))
            base[y : y + int(rng.integers(2, 5)), x : x + int(rng.integers(2, 5))] = int(rng.integers(1, classes + 1))
    assert _got(base, min_area_px=min_area) == _reference(base, min_area)


@pytest.mark.req("FR-013-17")
def test_default_minimum_area_is_16_pixels() -> None:
    rng = np.random.default_rng(9)
    img = rng.integers(1, 3, (30, 30)).astype(np.uint32)
    assert _got(img) == _reference(img, 16)


@pytest.mark.req("FR-013-17")
@pytest.mark.parametrize("bad", [np.zeros((4, 4, 3), np.uint32), np.zeros(8, np.uint32), np.zeros((4, 4), np.float32)])
def test_malformed_semantic_images_are_rejected(bad: np.ndarray) -> None:
    with pytest.raises(ValueError):
        camera.component_boxes(bad)
    with pytest.raises(ValueError):
        camera.component_boxes(np.zeros((4, 4), np.uint32), min_area_px=0)

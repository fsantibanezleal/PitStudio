# ruff: noqa: E501
"""T-009-093 - FR-009-47: COCO polygon consistency checks (`coco-polygon-invalid`).

Oracles (independent of the code under test):
- the shoelace formula evaluated by hand for each fixture: a 10 x 10 square has area 100 (either orientation); the right triangle (0,0), (10,0), (0,10) has area 50; two disjoint
  4 x 4... squares of 2 x 2 give 4 + 4 = 8; the unit square of the plan's test strategy has area 1;
- the rule of spec 009 FR-009-47: the stored `area` may differ from the polygon area by at most 1 px^2 (a difference of exactly 1 is allowed, 1.5 and 2 are not); a polygon needs an even number
  of coordinates and at least 3 vertices (6 numbers); every vertex must lie inside its image (0 <= x <= width, 0 <= y <= height; the image corner itself is inside);
- reported plan/spec mismatch: plan 009's row says "area 2 [against the unit square of area 1] ... rejected" but the spec text says "more than 1 px^2", which a difference of exactly 1 does not meet;
  these tests follow the spec text (difference 1.0 accepted, > 1 rejected) and use 100 vs 98.9 / 101.5 for the rejections.

Expected public API (module `pitstudio_pipeline.perception.loader`, see tests/unit/test_t_009_019_coco_loader.py): `CocoError` gains `.code`; for every problem confined to an annotation's
`segmentation` or its `area` (schema-level ones included: fewer than 6 numbers, an empty ring, a vertex beyond the 0.5 px margin of the schema, a non-numeric vertex) `load_coco` raises
CocoError with `.code == "coco-polygon-invalid"`, `.record_id == "annotation:<id>"` and a reason naming the problem ("area", "odd", "vertices" or "outside"). The checks run on the polygon rings of
`segmentation` (each ring separately for parity, vertex count and bounds); the polygon area is the sum of the absolute shoelace areas of the rings. Other CocoError cases keep their codes (not asserted here).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
from pitstudio_pipeline.perception import loader  # noqa: E402

SQ10 = [10.0, 10.0, 20.0, 10.0, 20.0, 20.0, 10.0, 20.0]  # 10 x 10 square, counter-clockwise on screen: area 100
SQ10_REV = [10.0, 10.0, 10.0, 20.0, 20.0, 20.0, 20.0, 10.0]
TRI = [0.0, 0.0, 10.0, 0.0, 0.0, 10.0]  # area 50


def _file(
    tmp_path: Path,
    seg: list,
    area: float,
    *,
    ann_id: int = 7,
    size: tuple[int, int] = (1280, 720),
    bbox=(10.0, 10.0, 10.0, 10.0),
) -> Path:
    doc = {
        "images": [{"id": 1, "file_name": "rgb/000001.png", "width": size[0], "height": size[1]}],
        "annotations": [
            {
                "id": ann_id,
                "image_id": 1,
                "category_id": 1,
                "bbox": list(bbox),
                "segmentation": seg,
                "area": area,
                "iscrowd": 0,
            }
        ],
        "categories": kit.coco_doc()["categories"],
    }
    p = tmp_path / "coco.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def _bad(path: Path, *words: str) -> loader.CocoError:
    with pytest.raises(loader.CocoError) as exc:
        loader.load_coco(path)
    assert exc.value.code == "coco-polygon-invalid"
    assert exc.value.record_id == "annotation:7"
    assert "annotation:7" in str(exc.value)
    for w in words:
        assert w in exc.value.reason, (w, exc.value.reason)
    return exc.value


@pytest.mark.req("FR-009-47")
@pytest.mark.parametrize(
    ("seg", "area"),
    [
        ([SQ10], 100.0),
        ([SQ10_REV], 100.0),  # orientation does not matter
        ([TRI], 50.0),
        ([[0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]], 1.0),  # the unit square of the plan
        ([SQ10], 101.0),  # difference exactly 1: allowed
        ([SQ10], 99.0),
        ([SQ10], 100.4),
        (
            [[10.0, 10.0, 12.0, 10.0, 12.0, 12.0, 10.0, 12.0], [30.0, 30.0, 32.0, 30.0, 32.0, 32.0, 30.0, 32.0]],
            8.0,
        ),  # two disjoint 2 x 2 rings: 4 + 4
    ],
)
def test_consistent_polygons_are_accepted(tmp_path: Path, seg: list, area: float) -> None:
    assert loader.load_coco(_file(tmp_path, seg, area))["annotations"][0]["area"] == area


@pytest.mark.req("FR-009-47")
@pytest.mark.parametrize("area", [101.5, 98.9, 102.0, 50.0, 200.0])
def test_an_area_that_differs_by_more_than_one_square_pixel_is_rejected_naming_the_annotation(
    tmp_path: Path, area: float
) -> None:
    _bad(_file(tmp_path, [SQ10], area), "area")


@pytest.mark.req("FR-009-47")
def test_the_unit_square_with_area_two_differs_by_one_and_is_accepted_but_area_three_is_not(tmp_path: Path) -> None:
    unit = [[10.0, 10.0, 11.0, 10.0, 11.0, 11.0, 10.0, 11.0]]
    assert (
        loader.load_coco(_file(tmp_path, unit, 2.0, bbox=(10.0, 10.0, 1.0, 1.0)))["annotations"][0]["area"] == 2.0
    )  # |2 - 1| = 1 <= 1 (spec text, see the module docstring)
    _bad(_file(tmp_path, unit, 3.0, bbox=(10.0, 10.0, 1.0, 1.0)), "area")


@pytest.mark.req("FR-009-47")
@pytest.mark.parametrize(
    "ring",
    [
        [10.0, 10.0, 20.0, 10.0, 20.0],
        [10.0, 10.0, 20.0, 10.0, 20.0, 20.0, 10.0],
        [10.0, 10.0, 20.0, 10.0, 20.0, 20.0, 10.0, 20.0, 5.0],
    ],
)
def test_a_ring_with_an_odd_number_of_coordinates_is_rejected(tmp_path: Path, ring: list) -> None:
    _bad(_file(tmp_path, [ring], 100.0), "odd")


@pytest.mark.req("FR-009-47")
@pytest.mark.parametrize("ring", [[], [1.0, 2.0], [1.0, 2.0, 3.0, 4.0]])
def test_a_ring_with_fewer_than_three_vertices_is_rejected(tmp_path: Path, ring: list) -> None:
    _bad(_file(tmp_path, [ring], 100.0), "vertices")


@pytest.mark.req("FR-009-47")
def test_an_annotation_with_no_ring_at_all_is_rejected(tmp_path: Path) -> None:
    _bad(_file(tmp_path, [], 100.0))


@pytest.mark.req("FR-009-47")
@pytest.mark.parametrize(
    "ring",
    [
        [-1.0, 10.0, 10.0, 10.0, 10.0, 20.0, -1.0, 20.0],  # a vertex at x = -1 (plan 009)
        [10.0, 10.0, 20.0, 10.0, 20.0, 721.0, 10.0, 20.0],  # y beyond the 720 px height
        [10.0, 10.0, 1280.01, 10.0, 1280.01, 20.0, 10.0, 20.0],  # x just beyond the width
        [10.0, -0.01, 20.0, -0.01, 20.0, 10.0, 10.0, 10.0],  # slightly above the top edge
    ],
)
def test_a_vertex_outside_its_image_is_rejected(tmp_path: Path, ring: list) -> None:
    _bad(_file(tmp_path, [ring], 100.0), "outside")


@pytest.mark.req("FR-009-47")
def test_vertices_on_the_image_border_are_inside(tmp_path: Path) -> None:
    ring = [0.0, 0.0, 1280.0, 0.0, 1280.0, 720.0, 0.0, 720.0]
    area = 1280.0 * 720.0
    assert (
        loader.load_coco(_file(tmp_path, [ring], area, bbox=(0.0, 0.0, 1280.0, 720.0)))["annotations"][0]["area"]
        == area
    )


@pytest.mark.req("FR-009-47")
def test_the_bounds_are_those_of_the_annotations_own_image(tmp_path: Path) -> None:
    ring = [10.0, 10.0, 200.0, 10.0, 200.0, 20.0, 10.0, 20.0]
    area = 190.0 * 10.0
    assert (
        loader.load_coco(_file(tmp_path, [ring], area, size=(1280, 720), bbox=(10.0, 10.0, 190.0, 10.0)))[
            "annotations"
        ][0]["id"]
        == 7
    )
    _bad(_file(tmp_path, [ring], area, size=(100, 100), bbox=(10.0, 10.0, 90.0, 10.0)), "outside")


@pytest.mark.req("FR-009-47")
@pytest.mark.parametrize("bad_vertex", ["10", None, True, [1.0]])
def test_a_non_numeric_vertex_is_a_polygon_error(tmp_path: Path, bad_vertex: object) -> None:
    ring = [10.0, 10.0, 20.0, 10.0, 20.0, 20.0, bad_vertex, 20.0]
    _bad(_file(tmp_path, [ring], 100.0))


@pytest.mark.req("FR-009-47")
def test_the_error_names_the_annotation_by_its_own_id(tmp_path: Path) -> None:
    with pytest.raises(loader.CocoError) as exc:
        loader.load_coco(_file(tmp_path, [SQ10], 500.0, ann_id=4242))
    assert exc.value.record_id == "annotation:4242"
    assert exc.value.code == "coco-polygon-invalid"

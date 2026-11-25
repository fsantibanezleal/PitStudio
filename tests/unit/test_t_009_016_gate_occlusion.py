# ruff: noqa: PT018
"""T-009-016 (fix): the table-to-render agreement of the SDG gate counts only objects no other object occludes.

Requirements: FR-009-55 (an object is visible only without occlusion by another object), FR-009-02.

Oracles: hand-built images. A pinhole camera at the origin looks along +x with fx = fy = 100 px on a 200 by 100 px
image, so a box of width w at distance d spans w * 100 / d pixels; the instance mask and the depth map are NumPy arrays
written here, and the expected flags follow from where the nearer object's pixels lie.

Expected API (`pitstudio_isaac.sdg.geometry_qa`, no Isaac Sim needed):
- `projected_hull(camera, placement, dims) -> list[(u, v)]`: the convex hull in pixels of the eight corners of the
  object's box (a `class`, `x_m`, `y_m`, `z_m`, `yaw_deg` placement with `length_m`, `width_m`, `height_m`);
- `occluded_by_object(row, ids, depth, id_to_path) -> dict[prim_id, bool]`: for each object of `row["objects"]`, True
  when some pixel inside its hull belongs to another object of the row and is nearer to the camera than the object's
  box (the depth of that pixel is less than the object's nearest distance along the optical axis);
- `evaluate_gate` skips an object whose measure has `occluded_by_object` true when it computes the agreement (the
  share and the count of objects it states are those of the objects no other object occludes); the thresholds are the
  same as before (`AGREEMENT_SHARE` 0.9, `MIN_MEDIAN_DEPTH_M` 10, `MIN_INSTANCE_PX` 16).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_isaac.sdg import geometry_qa  # noqa: E402

CAMERA = {
    "position_m": [0.0, 0.0, 0.0],
    "forward": [1.0, 0.0, 0.0],
    "up": [0.0, 0.0, 1.0],
    "width_px": 200,
    "height_px": 100,
    "fx_px": 100.0,
    "fy_px": 100.0,
    "cx_px": 100.0,
    "cy_px": 50.0,
}
BOX = {"length_m": 4.0, "width_m": 4.0, "height_m": 4.0}


def _object(prim: str, x: float, y: float) -> dict:
    return {"prim_id": prim, "class": "haul_truck", **BOX}


def _row(placements: list[dict], objects: list[dict]) -> dict:
    return {"camera": CAMERA, "objects": objects, "dr": {"placements": placements}}


def _placement(x: float, y: float, z: float = -2.0) -> dict:
    return {"class": "haul_truck", "x_m": x, "y_m": y, "z_m": z, "yaw_deg": 0.0}


@pytest.mark.req("FR-009-55")
def test_the_hull_of_a_box_follows_the_pinhole_formula() -> None:
    hull = geometry_qa.projected_hull(CAMERA, _placement(40.0, 0.0), {"class": "haul_truck", **BOX})
    us = [p[0] for p in hull]
    vs = [p[1] for p in hull]
    near, far = 38.0, 42.0
    assert min(us) == pytest.approx(100.0 - 2.0 * 100.0 / near, abs=0.01)
    assert max(us) == pytest.approx(100.0 + 2.0 * 100.0 / near, abs=0.01)
    assert min(vs) == pytest.approx(
        50.0 - 2.0 * 100.0 / near, abs=0.01
    )  # the top of the box, z = +2 m, at the near face
    assert max(vs) == pytest.approx(50.0 + 2.0 * 100.0 / near, abs=0.01)
    assert far > near


@pytest.mark.req("FR-009-55")
def test_a_nearer_object_inside_the_hull_occludes_and_a_farther_one_does_not() -> None:
    placements = [_placement(40.0, 0.0), _placement(20.0, 0.0)]  # the second stands in front of the first
    row = _row(placements, [_object("/World/Sdg/Obj_00", 40.0, 0.0), _object("/World/Sdg/Obj_01", 20.0, 0.0)])
    ids = np.zeros((100, 200), dtype=np.int32)
    depth = np.full((100, 200), 400.0, dtype=np.float32)
    ids[35:65, 80:120] = 1  # the far object's pixels
    depth[35:65, 80:120] = 40.0
    ids[30:70, 70:130] = 2  # the near object covers them
    depth[30:70, 70:130] = 20.0
    id_to_path = {1: "/World/Sdg/Obj_00", 2: "/World/Sdg/Obj_01"}
    flags = geometry_qa.occluded_by_object(row, ids, depth, id_to_path)
    assert flags == {"/World/Sdg/Obj_00": True, "/World/Sdg/Obj_01": False}


@pytest.mark.req("FR-009-55")
def test_an_object_with_only_terrain_or_farther_objects_in_its_hull_is_not_occluded() -> None:
    row = _row([_placement(40.0, 0.0)], [_object("/World/Sdg/Obj_00", 40.0, 0.0)])
    ids = np.zeros((100, 200), dtype=np.int32)
    depth = np.full((100, 200), 400.0, dtype=np.float32)
    assert geometry_qa.occluded_by_object(row, ids, depth, {}) == {"/World/Sdg/Obj_00": False}
    far = _row(
        [_placement(40.0, 0.0), _placement(90.0, 0.0)],
        [_object("/World/Sdg/Obj_00", 40.0, 0.0), _object("/World/Sdg/Obj_01", 90.0, 0.0)],
    )
    ids[45:55, 95:105] = 2
    depth[45:55, 95:105] = 90.0  # behind the first object: it does not occlude it
    flags = geometry_qa.occluded_by_object(far, ids, depth, {2: "/World/Sdg/Obj_01"})
    assert flags["/World/Sdg/Obj_00"] is False


def _frame(objects: list[dict]) -> dict:
    return {
        "rgb_std": 40.0,
        "clipped_fraction": 0.0,
        "annotations": 1,
        "haze_limited": False,
        "median_depth_m": 60.0,
        "objects": objects,
    }


@pytest.mark.req("FR-009-55")
def test_the_agreement_counts_only_objects_no_other_object_occludes() -> None:
    frames = [
        _frame(
            [
                {"table_visible": True, "visible_px": 500, "occluded_by_object": False},
                {"table_visible": True, "visible_px": 0, "occluded_by_object": True},  # behind a truck: not counted
                {"table_visible": True, "visible_px": 3, "occluded_by_object": False},  # a real disagreement
                {"table_visible": False, "visible_px": 0, "occluded_by_object": False},
            ]
        )
        for _ in range(5)
    ]
    gate = geometry_qa.evaluate_gate(frames)["thresholds"]["table_render_agreement"]
    assert gate["objects"] == 10 and gate["value"] == pytest.approx(0.5) and gate["passed"] is False
    assert geometry_qa.AGREEMENT_SHARE == 0.90 and geometry_qa.MIN_MEDIAN_DEPTH_M == 10.0
    assert geometry_qa.MIN_INSTANCE_PX == 16


@pytest.mark.req("FR-009-55")
def test_a_measure_without_the_occlusion_flag_is_counted_as_before() -> None:
    frames = [_frame([{"table_visible": True, "visible_px": 100}, {"table_visible": True, "visible_px": 2}])]
    gate = geometry_qa.evaluate_gate(frames)["thresholds"]["table_render_agreement"]
    assert gate["objects"] == 2 and gate["value"] == pytest.approx(0.5)

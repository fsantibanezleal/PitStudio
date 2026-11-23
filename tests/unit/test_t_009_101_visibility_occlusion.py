# ruff: noqa: E501, PT018
"""T-009-101: camera clearance of near objects and object visibility with size and occlusion by other objects.

Requirements: FR-009-55 (extends FR-009-54, whose carved-surface line of sight is unchanged).

Oracles: hand calculations on a pinhole camera (a box of width w at distance d spans w * fx / d pixels), the geometry of
an oriented box (shapely footprint polygon, a vertical extent above its base), and a brute-force march of every sight
line through the other objects' boxes at a step of 0.05 m (much finer than the box sizes). The scene is the analytic
carved surface of test_t_009_100 (a plane rising 0.02 m per metre with a 30 m wall across it at y = 100 to 110 m).

Expected API (`pitstudio_studio.sdg.table`, studio environment):
- `MIN_INSTANCE_PX` (16, the renderer's `scene_render.MIN_INSTANCE_PX`) and `VIEW_NEAR_M`;
- `object_too_near(camera, placement, dims) -> bool`: some point of the object's box lies closer than `VIEW_NEAR_M` to
  the camera centre and inside the view cone (the frustum of the camera's field of view);
- `camera_accepts(camera, placements) -> bool`: no placed object is too near;
- `projected_box_px(camera, placement, dims) -> float`: the area in pixels of the box of the object projected into the
  image (clipped to the image; 0 when it is behind the camera);
- `object_occluded(camera, placement, others) -> bool`: the sight line from the camera centre to the footprint centroid at
  mid-height or to the top centre meets the box of another placement of `others` (placements with a `class`);
- `objects_seen(scene, camera, placements) -> list[bool]`: per object, FR-009-54 visibility and the projected box of
  at least `MIN_INSTANCE_PX` pixels and no occlusion by another object;
- `structured_row` and `unstructured_row` record `visible` by `objects_seen`, never place an object that is too near and
  keep the redraw within `_PLACEMENT_TRIES` (an object that is still too near after the tries is not recorded).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "unit"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
from pitstudio_studio.sdg import carved_surface, table  # noqa: E402
from pitstudio_studio.sdg.objects import dimensions, footprint  # noqa: E402
from pitstudio_studio.sdg.scene_inputs import SceneInputs  # noqa: E402
from test_t_009_016_param_table import RECIPE  # noqa: E402
from test_t_009_100_line_of_sight import CELL, X_MIN, Y_MAX, _edge, make_elevation  # noqa: E402

NEAR = table.VIEW_NEAR_M
FX = 800.0


def _camera(position=(0.0, 0.0, 4.0), yaw_deg: float = 0.0, pitch_deg: float = 0.0, fx: float = FX) -> dict:
    yaw, tilt = math.radians(yaw_deg), math.radians(pitch_deg)
    return {
        "position_m": list(position),
        "forward": [math.cos(yaw) * math.cos(tilt), math.sin(yaw) * math.cos(tilt), -math.sin(tilt)],
        "up": [0.0, 0.0, 1.0],
        "width_px": 1280,
        "height_px": 720,
        "fx_px": fx,
        "fy_px": fx,
        "cx_px": 640.0,
        "cy_px": 360.0,
    }


def _at(cls: str, x: float, y: float, z: float = 0.0, yaw: float = 0.0) -> dict:
    return {"class": cls, "x_m": x, "y_m": y, "z_m": z, "yaw_deg": yaw}


@pytest.fixture(scope="module")
def surface() -> carved_surface.CarvedSurface:
    return carved_surface.CarvedSurface(make_elevation(), X_MIN, Y_MAX, CELL)


@pytest.fixture(scope="module")
def scene(surface, tmp_path_factory) -> SceneInputs:
    edges = (
        _edge("edge-a", [(-250.0, 0.0), (250.0, 0.0)], surface),
        _edge("edge-c", [(250.0, 0.0), (250.0, 290.0)], surface),
    )
    return SceneInputs(
        scene_dir=tmp_path_factory.mktemp("synthetic"),
        manifest_id="t-occ",
        case="A1",
        latitude_deg=40.5,
        longitude_deg=-112.1,
        z0_m=1800.0,
        ramp_width_m=30.0,
        edges=edges,
        terrain_tiles=Path("tiles.json"),
        carved=surface,
    )


@pytest.mark.req("FR-009-55")
def test_the_instance_threshold_is_the_renderers() -> None:
    from pitstudio_isaac.sdg import scene_render

    assert table.MIN_INSTANCE_PX == scene_render.MIN_INSTANCE_PX == 16


@pytest.mark.req("FR-009-55")
def test_an_object_closer_than_the_near_distance_inside_the_view_cone_is_too_near() -> None:
    cam = _camera()
    car = dimensions("light_vehicle")["length_m"]
    cases = [
        (_at("light_vehicle", 6.0, 0.0), True),  # 6 m ahead, on the axis
        (_at("light_vehicle", NEAR + car / 2.0 + 0.5, 0.0), False),  # the nearest face is 0.5 m beyond the limit
        (_at("light_vehicle", NEAR + car / 2.0 - 0.5, 0.0), True),  # the nearest face is 0.5 m inside it
        (_at("light_vehicle", -6.0, 0.0), False),  # behind the camera
        (_at("light_vehicle", 6.0, 40.0), False),  # beside the camera, far outside a 70 degree field of view
        (_at("haul_truck", 40.0, 0.0), False),
    ]
    for placement, expected in cases:
        assert table.object_too_near(cam, placement, dimensions(placement["class"])) is expected, placement


@pytest.mark.req("FR-009-55")
def test_a_camera_is_accepted_only_when_no_placed_object_is_too_near() -> None:
    cam = _camera()
    far = _at("haul_truck", 60.0, 0.0)
    near = _at("person", 5.0, 0.5)
    assert table.camera_accepts(cam, [far])
    assert not table.camera_accepts(cam, [far, near])
    assert table.camera_accepts(cam, [])


@pytest.mark.req("FR-009-55")
def test_the_projected_box_of_a_person_follows_the_pinhole_formula() -> None:
    cam = _camera(pitch_deg=0.0)
    dims = dimensions("person")
    length, width, height, eye = dims["length_m"], dims["width_m"], dims["height_m"], 4.0
    for distance in (50.0, 100.0, 200.0):
        near, far = distance - length / 2.0, distance + length / 2.0
        wide = width * FX / near  # the near face spans the widest
        tall = eye * FX / near - (eye - height) * FX / far  # the lowest point is the near base, the highest the far top
        area = table.projected_box_px(cam, _at("person", distance, 0.0, z=0.0), dims)
        assert area == pytest.approx(wide * tall, rel=0.03), distance
    assert table.projected_box_px(cam, _at("person", -50.0, 0.0), dims) == 0.0


@pytest.mark.req("FR-009-55")
def test_a_person_beyond_the_size_limit_is_not_seen_and_a_truck_at_the_same_distance_is(scene) -> None:
    y = 0.0
    cam = _camera((0.0, y, float(scene.carved.height(0.0, y)) + 4.0), yaw_deg=0.0, pitch_deg=1.0)
    placements = [_at("person", 240.0, 0.0, z=float(scene.carved.height(240.0, 0.0))), _at("haul_truck", 120.0, 0.0, z=float(scene.carved.height(120.0, 0.0)))]
    assert table.projected_box_px(cam, placements[0], dimensions("person")) < table.MIN_INSTANCE_PX
    assert table.objects_seen(scene, cam, placements) == [False, True]


@pytest.mark.req("FR-009-55")
def test_an_object_behind_another_object_is_not_seen_and_one_beside_it_is(scene) -> None:
    y = 0.0
    z = lambda x: float(scene.carved.height(x, y))  # noqa: E731
    cam = _camera((0.0, y, z(0.0) + 4.0), yaw_deg=0.0, pitch_deg=1.0)
    behind = [_at("haul_truck", 40.0, 0.0, z(40.0)), _at("haul_truck", 90.0, 0.0, z(90.0))]
    assert table.objects_seen(scene, cam, behind) == [True, False]
    beside = [_at("haul_truck", 40.0, -12.0, z(40.0)), _at("haul_truck", 90.0, 12.0, z(90.0))]
    assert table.objects_seen(scene, cam, beside) == [True, True]
    assert table.object_occluded(cam, behind[1], [behind[0]])
    assert not table.object_occluded(cam, behind[0], [behind[1]])  # the nearer one is never hidden by the farther one


def _march_blocked(camera: dict, target: dict, others: list[dict]) -> bool:
    """Brute force: does a sight line from the camera to the target's mid-height point or top centre pass through the box
    of any other placement (footprint polygon below its top)?"""
    from shapely.geometry import Point

    eye = np.asarray(camera["position_m"], dtype=float)
    height = dimensions(target["class"])["height_m"]
    for aim in (target["z_m"] + height / 2.0, target["z_m"] + height):
        end = np.array([target["x_m"], target["y_m"], aim])
        n = int(np.linalg.norm(end - eye) / 0.05)
        for k in range(n):
            p = eye + (end - eye) * k / n
            for other in others:
                if footprint(other["class"], other["x_m"], other["y_m"], other["yaw_deg"]).contains(Point(p[0], p[1])):
                    if other["z_m"] <= p[2] <= other["z_m"] + dimensions(other["class"])["height_m"]:
                        return True
    return False


@pytest.mark.req("FR-009-55")
def test_occlusion_agrees_with_a_brute_force_march_on_random_layouts(scene) -> None:
    rng = np.random.default_rng(101)
    cam = _camera((0.0, 0.0, float(scene.carved.height(0.0, 0.0)) + 4.0), pitch_deg=2.0)
    mismatches = 0
    for _ in range(60):
        placements = []
        for cls in ("haul_truck", "light_vehicle", "person", "shovel"):
            x, y = float(rng.uniform(15.0, 120.0)), float(rng.uniform(-14.0, 14.0))
            placements.append(_at(cls, x, y, float(scene.carved.height(x, y)), float(rng.uniform(0.0, 360.0))))
        for i, p in enumerate(placements):
            others = [q for j, q in enumerate(placements) if j != i]
            mismatches += table.object_occluded(cam, p, others) != _march_blocked(cam, p, others)
    assert mismatches <= 2  # the march resolves 0.05 m: a sight line grazing a box edge may differ by one step


@pytest.mark.req("FR-009-55")
def test_rows_never_place_a_near_object_and_mark_visible_by_size_and_occlusion(scene) -> None:
    flagged = {True: 0, False: 0}
    for seed in range(40):
        g = table.scenario_geometry(scene, RECIPE["seed"], seed)
        rows = [
            table.structured_row(scene, RECIPE, seed, g),
            table.unstructured_row(scene, RECIPE, seed, 0, g),
        ]
        for row in rows:
            placements = row["dr"]["placements"]
            assert len(row["objects"]) == len(placements)
            assert table.camera_accepts(g["camera"], placements), (seed, "an object is too near the camera")
            for i, (obj, p) in enumerate(zip(row["objects"], placements, strict=True)):
                others = [q for j, q in enumerate(placements) if j != i]
                if obj["visible"]:
                    assert table.projected_box_px(g["camera"], p, dimensions(p["class"])) >= table.MIN_INSTANCE_PX
                    assert not table.object_occluded(g["camera"], p, others), (seed, obj["prim_id"])
                    assert table.object_visible(scene, g["camera"], p, dimensions(p["class"]))
                flagged[obj["visible"]] += 1
            assert [o["visible"] for o in row["objects"]] == table.objects_seen(scene, g["camera"], placements)
    assert flagged[True] > 20


@pytest.mark.req("FR-009-55")
def test_an_object_that_is_still_too_near_after_the_tries_is_not_recorded(scene, monkeypatch) -> None:
    monkeypatch.setattr(table, "object_too_near", lambda _camera, _placement, _dims: True)
    g = table.scenario_geometry(scene, RECIPE["seed"], 9)
    row = table.structured_row(scene, RECIPE, 9, g)
    assert row["objects"] == [] and row["dr"]["placements"] == []
    row = table.unstructured_row(scene, RECIPE, 9, 0, g)
    assert row["objects"] == [] and row["dr"]["placements"] == []


@pytest.mark.req("FR-009-55")
def test_the_table_stays_deterministic_per_seed(scene) -> None:
    splits = {"train": [table.scenario_seed(RECIPE["seed"], i) for i in range(5)], "val": [], "test": []}
    a = list(table.build_rows(scene, RECIPE, splits, {"structured": 5, "unstructured": 3}))
    b = list(table.build_rows(scene, RECIPE, splits, {"structured": 5, "unstructured": 3}))
    assert a == b

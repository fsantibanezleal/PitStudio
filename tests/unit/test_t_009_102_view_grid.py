# ruff: noqa: E501, PT018
"""T-009-102: a camera is accepted only when the median depth of a 16 by 9 grid of rays on the carved surface is clear.

Requirements: FR-009-56 (extends FR-009-54, whose optical-axis test is unchanged).

Oracle: a brute-force march of every ray of the grid through the analytic carved surface of test_t_009_100 (a plane
rising 0.02 m per metre with a 30 m wall across it at y = 100 to 110 m) at a step of 0.25 m, and the pinhole model: the
ray through pixel (u, v) has the direction forward + (u - cx) / fx * right - (v - cy) / fy * up, and the depth the gate
measures is the distance to the image plane, the ray distance times the cosine of the angle to the optical axis.

Expected API (`pitstudio_studio.sdg.table`, studio environment):
- `VIEW_GRID == (16, 9)` (columns, rows of pixel centres at ((i + 0.5) / 16 * width, (j + 0.5) / 9 * height));
- `view_depths(scene, camera) -> np.ndarray` of 144 values (row-major, the top row first): the image-plane depth where
  the ray meets the carved surface, NaN where it meets nothing; NaN everywhere for a scene without a carved surface;
- `camera_view_clear(scene, camera) -> bool`: the median of the finite depths is at least `VIEW_NEAR_M` (True when no
  ray meets the surface);
- `scenario_geometry` accepts a camera only when `camera_clear` and `camera_view_clear` both hold.
"""

from __future__ import annotations

import dataclasses
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
from pitstudio_studio.sdg.scene_inputs import SceneInputs  # noqa: E402
from test_t_009_016_param_table import RECIPE  # noqa: E402
from test_t_009_100_line_of_sight import CELL, X_MIN, Y_MAX, _edge, make_elevation  # noqa: E402

NEAR = table.VIEW_NEAR_M
W, H = 1280, 720


def _camera(position, yaw_deg: float, pitch_deg: float, hfov_deg: float = 60.0) -> dict:
    yaw, tilt = math.radians(yaw_deg), math.radians(pitch_deg)
    fx = 0.5 * W / math.tan(math.radians(hfov_deg) / 2.0)
    return {
        "position_m": list(position),
        "forward": [math.cos(yaw) * math.cos(tilt), math.sin(yaw) * math.cos(tilt), -math.sin(tilt)],
        "up": [0.0, 0.0, 1.0],
        "width_px": W,
        "height_px": H,
        "fx_px": fx,
        "fy_px": fx,
        "cx_px": W / 2.0,
        "cy_px": H / 2.0,
    }


def oracle_depths(surface: carved_surface.CarvedSurface, camera: dict) -> np.ndarray:
    eye = np.asarray(camera["position_m"], dtype=float)
    fwd = np.asarray(camera["forward"], dtype=float)
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    out = np.full(144, np.nan)
    ts = np.arange(0.0, 4000.0, 0.25)
    for j in range(9):
        for i in range(16):
            u, v = (i + 0.5) / 16 * W, (j + 0.5) / 9 * H
            d = fwd + (u - camera["cx_px"]) / camera["fx_px"] * right - (v - camera["cy_px"]) / camera["fy_px"] * up
            d /= np.linalg.norm(d)
            pts = eye + ts[:, None] * d
            below = pts[:, 2] < np.asarray(surface.height(pts[:, 0], pts[:, 1]))
            if below.any():
                out[j * 16 + i] = ts[int(np.argmax(below))] * float(d @ fwd)
    return out


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
        manifest_id="t-grid",
        case="A1",
        latitude_deg=40.5,
        longitude_deg=-112.1,
        z0_m=1800.0,
        ramp_width_m=30.0,
        edges=edges,
        terrain_tiles=Path("tiles.json"),
        carved=surface,
    )


CAMERAS = {
    "low_pitched": _camera((0.0, 0.0, 2.0), 270.0, 5.0),  # away from the wall: axis meets the floor 23 m ahead, lower rows 6 to 13 m
    "high_flat": _camera((0.0, 0.0, 4.0), 90.0, 2.0),  # every ray meets the floor or the wall 12 m or farther
    "wall_frontal": _camera((0.0, 40.0, 4.0), 90.0, 0.0),  # the wall stands 60 m ahead
    "sky": _camera((0.0, 0.0, 4.0), 270.0, -20.0),  # looks up and away: no ray meets the surface
}


@pytest.mark.req("FR-009-56")
def test_the_grid_is_16_by_9_pixel_centres() -> None:
    assert table.VIEW_GRID == (16, 9)


@pytest.mark.req("FR-009-56")
@pytest.mark.parametrize("name", sorted(CAMERAS))
def test_the_depths_equal_a_brute_force_march_of_every_ray(scene, surface, name: str) -> None:
    got = table.view_depths(scene, CAMERAS[name])
    want = oracle_depths(surface, CAMERAS[name])
    assert got.shape == (144,)
    assert np.array_equal(np.isnan(got), np.isnan(want)), name
    finite = ~np.isnan(want)
    assert np.all(np.abs(got[finite] - want[finite]) < 1.0), name


@pytest.mark.req("FR-009-56")
def test_the_depth_is_the_distance_to_the_image_plane_not_the_ray_length(scene) -> None:
    depths = table.view_depths(scene, CAMERAS["wall_frontal"]).reshape(9, 16)
    # the camera at y = 40 faces a wall at y = 100 with a horizontal axis: the ray of the middle row through any column
    # meets the wall at y = 100, so the image-plane depth is 60 m in every column, the ray length is up to 68 m
    middle = depths[4]
    assert np.all(np.abs(middle - 60.0) < 1.5), middle


@pytest.mark.req("FR-009-56")
def test_a_camera_whose_axis_is_clear_but_whose_median_ray_is_near_is_refused(scene) -> None:
    low = CAMERAS["low_pitched"]
    assert table.camera_clear(scene, low)  # FR-009-54: the axis meets the floor 23 m ahead
    assert not table.camera_view_clear(scene, low)  # FR-009-56: the median finite depth is below 10 m
    median = float(np.nanmedian(table.view_depths(scene, low)))
    assert median < NEAR


@pytest.mark.req("FR-009-56")
def test_clear_cameras_are_accepted_and_a_sky_view_has_no_hit(scene) -> None:
    assert table.camera_view_clear(scene, CAMERAS["high_flat"])
    assert table.camera_view_clear(scene, CAMERAS["wall_frontal"])
    sky = table.view_depths(scene, CAMERAS["sky"])
    assert np.isnan(sky).all()
    assert table.camera_view_clear(scene, CAMERAS["sky"])  # no ray meets the surface: nothing is near


@pytest.mark.req("FR-009-56")
def test_a_scene_without_a_carved_surface_accepts_every_camera(scene) -> None:
    bare = dataclasses.replace(scene, carved=None)
    assert np.isnan(table.view_depths(bare, CAMERAS["low_pitched"])).all()
    assert table.camera_view_clear(bare, CAMERAS["low_pitched"])


@pytest.mark.req("FR-009-56")
def test_the_median_is_taken_over_the_finite_depths_only(scene, monkeypatch) -> None:
    depths = np.full(144, np.nan)
    depths[:5] = [3.0, 4.0, 50.0, 60.0, 70.0]  # median 50 over the five finite values, 70 or nan over all 144
    monkeypatch.setattr(table, "view_depths", lambda _s, _c: depths)
    assert table.camera_view_clear(scene, CAMERAS["high_flat"])
    depths[:5] = [3.0, 4.0, 5.0, 60.0, 70.0]  # median 5
    assert not table.camera_view_clear(scene, CAMERAS["high_flat"])


@pytest.mark.req("FR-009-56")
def test_every_accepted_camera_has_a_clear_median_and_the_check_is_part_of_the_site_draw(
    scene, surface, monkeypatch
) -> None:
    for seed in range(40):
        cam = table.scenario_geometry(scene, RECIPE["seed"], seed)["camera"]
        depths = oracle_depths(surface, cam)
        finite = depths[~np.isnan(depths)]
        assert finite.size == 0 or float(np.median(finite)) >= NEAR - 1.0, seed
    monkeypatch.setattr(table, "camera_view_clear", lambda _s, _c: False)
    with pytest.raises(ValueError, match="seed 7"):
        table.scenario_geometry(scene, RECIPE["seed"], 7)

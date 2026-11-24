# ruff: noqa: E501, PT018
"""T-009-100: camera and object heights from the carved surface, clear view ahead, objects in line of sight.

Requirements: FR-009-54 (and FR-004-50 for the surface it reads).

The carved surface of the tests is analytic, so every expected value is a hand calculation: a plane that rises 0.02 m
per metre towards +x with a 30 m high wall across it at y = 100 to 110 m (a step of one cell on each side). Oracles: the
bilinear height of the vertex convention (the grid value at x_min + c * cell, row 0 north), the distance along a ray that
falls at a known pitch onto a plane (h / sin(pitch)), and a brute-force march of every camera ray and sight line at a
step of 0.05 m, much finer than the half cell of the code under test (a sight line may penetrate the surface by less
than 0.25 m, which a half-cell march cannot resolve).

Expected API (package `pitstudio_studio.sdg`, studio environment):
- `carved_surface.CarvedSurface(elevation, x_min_m, y_max_m, cell_size_m)`: `height(x, y)` (bilinear, clamped at the
  border, nodata never blocks), `first_hit(origin, direction, max_range_m) -> float | None` (the distance along the unit
  `direction` of the first sample, marched at half the cell size, that is below the surface), `segment_clear(p0, p1)`.
- `carved_surface.load_carved_surface(folder)` reads `design/carved-grid.zarr` and checks its elevation digest.
- `SceneInputs.carved` (None for a scene without a carved surface), `SceneInputs.height_at` takes the carved height when
  there is one, `load_scene_inputs(scene_dir, *, require_carved=False)` finds the `st20_pit_design` folder next to
  `st45_validate`, ties it to the manifest through the SHA-256 of the pit design report and raises `SceneInputsError`
  when it is required and absent or does not match.
- `table.camera_clear(scene, camera) -> bool` and `table.object_visible(scene, camera, placement, dims) -> bool`;
  `table.scenario_geometry` accepts a camera only when `camera_clear`; every object entry of a structured and an
  unstructured row has a boolean `visible`.
"""

from __future__ import annotations

import hashlib
import itertools
import json
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
import scene_kit as kit  # noqa: E402
from pitstudio_studio.sdg import carved_surface, table  # noqa: E402
from pitstudio_studio.sdg.objects import dimensions  # noqa: E402
from pitstudio_studio.sdg.scene_inputs import (  # noqa: E402
    RoadEdge,
    SceneInputs,
    SceneInputsError,
    load_scene_inputs,
)
from shapely.geometry import LineString  # noqa: E402
from test_t_009_016_param_table import RECIPE, make_scene  # noqa: E402

CELL = 1.0
N = 600
X_MIN, Y_MAX = -300.0, 300.0
WALL_Y = (100.0, 110.0)
WALL_M = 30.0
NEAR = table.VIEW_NEAR_M


def plane_z(x: float, y: float) -> float:
    return 0.02 * x + (WALL_M if WALL_Y[0] <= y <= WALL_Y[1] else 0.0)


def make_elevation() -> np.ndarray:
    xs = X_MIN + np.arange(N) * CELL
    ys = Y_MAX - np.arange(N) * CELL
    return np.array([[plane_z(x, y) for x in xs] for y in ys], dtype=np.float32)


@pytest.fixture(scope="module")
def surface() -> carved_surface.CarvedSurface:
    return carved_surface.CarvedSurface(make_elevation(), X_MIN, Y_MAX, CELL)


def _edge(
    edge_id: str, pts: list[tuple[float, float]], s: carved_surface.CarvedSurface, width: float = 30.0
) -> RoadEdge:
    dense = []
    for (x0, y0), (x1, y1) in itertools.pairwise(pts):
        n = round(math.dist((x0, y0), (x1, y1)) / 5.0)
        dense += [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(n + 1)]
    xyz = np.array([[x, y, float(s.height(x, y))] for x, y in dense])
    line = LineString(xyz[:, :2])
    return RoadEdge(edge_id, xyz, line.buffer(width / 2.0, cap_style="flat", join_style="round"), float(line.length))


@pytest.fixture(scope="module")
def scene(surface: carved_surface.CarvedSurface, tmp_path_factory: pytest.TempPathFactory) -> SceneInputs:
    """A road along +x at y = 0 and one along +y at x = 250 that runs into the wall (x east, y north)."""
    edges = (
        _edge("edge-a", [(-250.0, 0.0), (250.0, 0.0)], surface),
        _edge("edge-c", [(250.0, 0.0), (250.0, 290.0)], surface),
    )
    return SceneInputs(
        scene_dir=tmp_path_factory.mktemp("synthetic"),
        manifest_id="t-los",
        case="A1",
        latitude_deg=40.5,
        longitude_deg=-112.1,
        z0_m=1800.0,
        ramp_width_m=30.0,
        edges=edges,
        terrain_tiles=Path("tiles.json"),
        carved=surface,
    )


def march(surface: carved_surface.CarvedSurface, p0, p1, step: float = 0.05) -> float:
    """Brute force: the deepest penetration (m, positive = inside the surface) of the segment p0 to p1."""
    p0, p1 = np.asarray(p0, dtype=np.float64), np.asarray(p1, dtype=np.float64)
    n = max(2, int(np.linalg.norm(p1 - p0) / step))
    worst = -1e9
    for k in range(n + 1):
        p = p0 + (p1 - p0) * k / n
        worst = max(worst, float(surface.height(p[0], p[1])) - p[2])
    return worst


# ---------------------------------------------------------------------------------------------------------------
# the surface
# ---------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-009-54")
def test_height_is_bilinear_in_the_vertex_convention_and_clamped_at_the_border(surface) -> None:
    assert surface.height(3.25, -50.0) == pytest.approx(0.02 * 3.25, abs=1e-5)
    assert surface.height(-300.0, 0.0) == pytest.approx(0.02 * -300.0, abs=1e-5)
    assert surface.height(1000.0, 0.0) == pytest.approx(
        0.02 * (X_MIN + (N - 1) * CELL), abs=1e-4
    )  # clamped, not extrapolated
    assert surface.height(0.0, 99.5) == pytest.approx(WALL_M / 2.0, abs=1e-4)  # half way up the one-cell step


@pytest.mark.req("FR-009-54")
def test_first_hit_of_a_ray_falling_onto_the_plane_is_height_over_sin_pitch(surface) -> None:
    pitch = math.radians(10.0)
    d = (math.cos(pitch), 0.0, -math.sin(pitch))  # towards +x, away from the wall
    hit = surface.first_hit((0.0, 0.0, 0.0 + surface.height(0.0, 0.0) + 3.0), d, 2000.0)
    assert hit is not None
    # the plane rises 0.02 per metre along +x, so the hit is a little before 3 / sin(10 deg) = 17.27 m
    expected = 3.0 / (math.sin(pitch) + 0.02 * math.cos(pitch))
    assert hit == pytest.approx(expected, abs=0.6)


@pytest.mark.req("FR-009-54")
def test_a_ray_that_never_meets_the_surface_returns_none(surface) -> None:
    assert surface.first_hit((0.0, 0.0, 80.0), (0.0, -1.0, 0.0), 2000.0) is None  # level at 80 m, above everything
    assert surface.first_hit((0.0, 0.0, 5.0), (0.0, 0.0, 1.0), 2000.0) is None  # straight up


@pytest.mark.req("FR-009-54")
def test_a_segment_is_clear_over_the_wall_and_blocked_through_it(surface) -> None:
    assert surface.segment_clear((0.0, 50.0, 40.0), (0.0, 150.0, 40.0))  # 40 m over a 30 m wall
    assert not surface.segment_clear((0.0, 50.0, 8.0), (0.0, 150.0, 8.0))  # through the wall
    assert surface.segment_clear((0.0, 120.0, 20.0), (0.0, 250.0, 20.0))  # beyond the wall, on its far side


@pytest.mark.req("FR-009-54")
def test_nodata_cells_do_not_block_a_ray() -> None:
    z = np.full((10, 10), np.nan, dtype=np.float32)
    s = carved_surface.CarvedSurface(z, 0.0, 10.0, 1.0)
    assert s.first_hit((2.0, 5.0, 1.0), (1.0, 0.0, 0.0), 8.0) is None


# ---------------------------------------------------------------------------------------------------------------
# camera
# ---------------------------------------------------------------------------------------------------------------
def _camera(position, yaw_deg: float, pitch_deg: float) -> dict:
    yaw, tilt = math.radians(yaw_deg), math.radians(pitch_deg)
    return {
        "position_m": list(position),
        "forward": [math.cos(yaw) * math.cos(tilt), math.sin(yaw) * math.cos(tilt), -math.sin(tilt)],
    }


@pytest.mark.req("FR-009-54")
def test_a_camera_is_clear_when_the_axis_meets_the_ground_beyond_the_near_distance_or_never(scene) -> None:
    near_wall = _camera((0.0, 95.0, 4.0), 90.0, 2.0)  # the wall is 5 m ahead, the floor 100 m ahead
    far_wall = _camera(
        (0.0, 40.0, 4.0), 90.0, 2.0
    )  # the wall is 60 m ahead, the floor 114 m ahead: the wall is hit at 60 m
    open_sky = _camera(
        (0.0, 0.0, 4.0), 270.0, -10.0
    )  # looking away from the wall, 10 degrees up: never meets the ground
    steep = _camera((0.0, 0.0, 4.0), 90.0, 20.0)  # the floor 11 m ahead along the axis (4 / sin 20 = 11.7 m)
    too_close = _camera((0.0, 0.0, 4.0), 90.0, 30.0)  # the floor 8 m ahead along the axis (4 / sin 30)
    assert not table.camera_clear(scene, near_wall)
    assert table.camera_clear(scene, far_wall)
    assert table.camera_clear(scene, open_sky)
    assert table.camera_clear(scene, steep)
    assert not table.camera_clear(scene, too_close)


@pytest.mark.req("FR-009-54")
def test_every_accepted_camera_is_above_the_carved_surface_with_clear_ground_ahead(scene, surface) -> None:
    lo, hi = table.CAMERA_HEIGHT_M
    seen_headings = set()
    for seed in range(60):
        g = table.scenario_geometry(scene, RECIPE["seed"], seed)
        cam = g["camera"]
        x, y, z = cam["position_m"]
        above = z - float(surface.height(x, y))
        assert lo - 1e-6 <= above <= hi + 1e-6, (seed, above)  # heights come from the carved surface
        # brute force: the axis does not meet the surface within the near distance
        end = np.asarray(cam["position_m"]) + NEAR * np.asarray(cam["forward"])
        assert march(surface, cam["position_m"], end) < 0.25, seed
        seen_headings.add(round(g["heading_deg"] / 90.0))
    assert len(seen_headings) >= 2  # both roads (headings along x and along y) were drawn


@pytest.mark.req("FR-009-54")
def test_a_camera_site_without_clear_ground_is_redrawn_and_a_seed_without_one_names_the_seed(
    scene, monkeypatch
) -> None:
    calls = {"n": 0}

    def flaky(_scene, _camera):
        calls["n"] += 1
        return calls["n"] > 5

    monkeypatch.setattr(table, "camera_clear", flaky)
    g = table.scenario_geometry(scene, RECIPE["seed"], 3)
    assert calls["n"] == 6 and g["camera"]["position_m"]
    monkeypatch.setattr(table, "camera_clear", lambda _s, _c: False)
    with pytest.raises(ValueError, match="seed 7"):
        table.scenario_geometry(scene, RECIPE["seed"], 7)


# ---------------------------------------------------------------------------------------------------------------
# objects
# ---------------------------------------------------------------------------------------------------------------
def _structured(scene, seed: int) -> dict:
    g = table.scenario_geometry(scene, RECIPE["seed"], seed)
    return table.structured_row(scene, RECIPE, seed, g) | {"camera": g["camera"], "geometry": g}


@pytest.mark.req("FR-009-54")
def test_object_heights_come_from_the_carved_surface_and_visibility_agrees_with_a_fine_march(scene, surface) -> None:
    seen = {True: 0, False: 0}
    offset = RECIPE["structured"]["placement"]["max_base_offset_m"]
    for seed in range(40):
        row = _structured(scene, seed)
        cam = np.asarray(row["camera"]["position_m"])
        assert len(row["objects"]) == len(row["dr"]["placements"])
        for obj, p in zip(row["objects"], row["dr"]["placements"], strict=True):
            assert isinstance(obj["visible"], bool)
            assert abs(p["z_m"] - float(surface.height(p["x_m"], p["y_m"]))) <= offset + 1e-6
            height = dimensions(p["class"])["height_m"]
            mid = (p["x_m"], p["y_m"], p["z_m"] + height / 2.0)
            top = (p["x_m"], p["y_m"], p["z_m"] + height)
            depth = max(march(surface, cam, mid), march(surface, cam, top))
            if obj["visible"]:
                assert depth < 0.25, (seed, obj["prim_id"], depth)
            elif depth < 0.0:
                assert table.projected_box_px(row["camera"], p, dimensions(p["class"])) < table.MIN_INSTANCE_PX or (
                    table.object_occluded(row["camera"], p, [q for q in row["dr"]["placements"] if q is not p])
                ), (seed, obj["prim_id"])
            seen[obj["visible"]] += 1
    assert seen[True] > 20


@pytest.mark.req("FR-009-54")
def test_an_object_behind_the_wall_is_recorded_not_visible_and_one_in_front_of_it_is_visible(scene, surface) -> None:
    from shapely.geometry import box

    x, y = 250.0, 60.0
    camera = _camera((x, y, float(surface.height(x, y)) + 4.0), 90.0, 2.0)
    for areas, expected in (([box(235.0, 130.0, 265.0, 200.0)], False), ([box(235.0, 70.0, 265.0, 95.0)], True)):
        geometry = {"camera": camera, "areas": areas}
        row = table.structured_row(scene, RECIPE, 11, geometry)
        assert row["objects"] and all(o["visible"] is expected for o in row["objects"]), (expected, row["objects"])


@pytest.mark.req("FR-009-54")
def test_an_object_that_is_not_visible_is_drawn_again_within_the_placement_tries(scene, monkeypatch) -> None:
    calls = []

    def never(_scene, _camera, _placement, _dims):
        calls.append(1)
        return False

    monkeypatch.setattr(table, "object_visible", never)
    g = table.scenario_geometry(scene, RECIPE["seed"], 5)
    row = table.structured_row(scene, RECIPE, 5, g)
    assert row["objects"] and all(o["visible"] is False for o in row["objects"])
    assert len(calls) >= len(row["objects"]) * table._PLACEMENT_TRIES  # every object was tried the full count
    n = {"i": 0}

    def third(_scene, _camera, _placement, _dims):
        n["i"] += 1
        return n["i"] % 3 == 0

    monkeypatch.setattr(table, "object_visible", third)
    row = table.structured_row(scene, RECIPE, 5, g)
    assert all(o["visible"] is True for o in row["objects"])


@pytest.mark.req("FR-009-54")
def test_the_unstructured_arm_marks_visibility_too(scene, surface) -> None:
    seen = set()
    for seed in range(20):
        g = table.scenario_geometry(scene, RECIPE["seed"], seed)
        row = table.unstructured_row(scene, RECIPE, seed, 0, g)
        for obj, p in zip(row["objects"], row["dr"]["placements"], strict=True):
            assert isinstance(obj["visible"], bool)
            assert abs(p["z_m"] - float(surface.height(p["x_m"], p["y_m"]))) <= 1e-6
            seen.add(obj["visible"])
    assert True in seen


@pytest.mark.req("FR-009-54")
def test_the_table_stays_deterministic_per_recipe_seed(scene) -> None:
    splits = {"train": [table.scenario_seed(RECIPE["seed"], i) for i in range(6)], "val": [], "test": []}
    a = list(table.build_rows(scene, RECIPE, splits, {"structured": 6, "unstructured": 4}))
    b = list(table.build_rows(scene, RECIPE, splits, {"structured": 6, "unstructured": 4}))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert all("visible" in o for r in a for o in r["objects"])


# ---------------------------------------------------------------------------------------------------------------
# loading the carved surface next to the validated scene
# ---------------------------------------------------------------------------------------------------------------
def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_carved(stage_dir: Path, elevation: np.ndarray, report_bytes: bytes, *, lie: bool = False) -> None:
    import zarr

    folder = stage_dir / "design" / "carved-grid.zarr"
    attrs = json.loads((kit.EXAMPLES / "terrain-grid.valid.json").read_text(encoding="utf-8"))
    rows, cols = elevation.shape
    digest = _sha(np.ascontiguousarray(elevation, dtype="<f4").tobytes())
    attrs.update(rows=rows, cols=cols, x_min_m=X_MIN, y_max_m=Y_MAX, cell_size_m=CELL)
    attrs["arrays"]["elevation"]["sha256"] = "0" * 64 if lie else digest
    group = zarr.open_group(str(folder), mode="w", zarr_format=3, attributes=attrs)
    arr = group.create_array(
        "elevation", shape=elevation.shape, chunks=(256, 256), dtype="float32", fill_value=float("nan")
    )
    arr[:] = elevation
    (stage_dir / "design" / "pit-design-report.json").write_bytes(report_bytes)
    digests = {
        p.relative_to(stage_dir).as_posix(): _sha(p.read_bytes()) for p in sorted(stage_dir.rglob("*")) if p.is_file()
    }
    (stage_dir / "digests.json").write_text(json.dumps(digests), encoding="utf-8")


def _tree(tmp: Path, *, carved: bool = True, lie: bool = False, other_report: bool = False) -> Path:
    base = tmp / "a1"
    scene_dir = make_scene(base / "st45_validate")
    if carved:
        report = (scene_dir / "design" / "pit-design-report.json").read_bytes()
        _write_carved(base / "st20_pit_design", make_elevation(), report + (b" " if other_report else b""), lie=lie)
    return scene_dir


@pytest.mark.req("FR-009-54")
def test_the_carved_surface_of_the_sibling_stage_is_loaded_and_drives_height_at(tmp_path) -> None:
    scene = load_scene_inputs(_tree(tmp_path), require_carved=True)
    assert scene.carved is not None
    assert scene.height_at(10.0, 20.0) == pytest.approx(0.2, abs=1e-5)
    legacy = load_scene_inputs(_tree(tmp_path / "x", carved=False))
    assert legacy.carved is None  # a scene built before FR-004-50 keeps the road-centre-line height


@pytest.mark.req("FR-009-54")
def test_a_required_carved_surface_that_is_absent_stale_or_altered_is_refused(tmp_path) -> None:
    with pytest.raises(SceneInputsError, match="carved"):
        load_scene_inputs(_tree(tmp_path / "a", carved=False), require_carved=True)
    with pytest.raises(SceneInputsError, match="another build"):
        load_scene_inputs(_tree(tmp_path / "b", other_report=True), require_carved=True)
    with pytest.raises(SceneInputsError, match="digest"):
        load_scene_inputs(_tree(tmp_path / "c", lie=True), require_carved=True)

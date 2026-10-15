# ruff: noqa: PT018
"""T-009-016 (fix): the `st55_sdg` shard driver renders the parameter table, resumable frame by frame (FR-009-02).

Requirements: FR-009-02, FR-009-44, NFR-009-03.

The queue entry raised `NotImplementedError("the shard driver needs the scene manifest format of spec 004")` after its
dry run had passed. The driver now exists; these tests cover every part of it that does not need Isaac Sim, through the
same code the real run uses (`driver.run`, `scene_render.write_frame`, `scene_render.annotate`, `masks`): resume after a
kill, guard block ends and stops, the probe of the first frames, the disk preflight, the instance outlines, the
annotations and the frame files. The Isaac calls themselves (`SdgRenderer`) are exercised by the first frames of the
real run, whose probe stops the job early when they are not usable.

Oracles: hand calculations written in the tests (pixel counts of rectangles, the shoelace area of an outline, the
pinhole projection of a point 10 m ahead), and the dataset contract `perception-dataset.schema.json`.
"""

from __future__ import annotations

import contextlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_isaac.sdg import driver, masks, run_job, scene_render  # noqa: E402
from pitstudio_isaac.sdg.cpu_renderer import CpuRenderer  # noqa: E402
from pitstudio_studio.sdg._schemas import schema_errors  # noqa: E402

CAMERA = {
    "position_m": [0.0, 0.0, 3.0],
    "forward": [1.0, 0.0, 0.0],
    "up": [0.0, 0.0, 1.0],
    "width_px": 1280,
    "height_px": 720,
    "fx_px": 1108.5,
    "fy_px": 1108.5,
    "cx_px": 640.0,
    "cy_px": 360.0,
}


def _row(rid: str = "pit-s-00000", *, x: float = 40.0, arm: str = "structured") -> dict:
    """A structured row with one truck 40 m ahead of the camera on level ground (z = 0)."""
    dr = {
        "sun_utc": "2025-06-21T18:00:00Z",
        "sun_elevation_deg": 60.0,
        "sun_azimuth_deg": 180.0,
        "dust_extinction_per_km": 0.5,
        "wet_segments": [{"segment_id": "edge-a", "wet": False}],
        "rock_texture_ids": ["rock-a"],
        "placements": [{"class": "haul_truck", "x_m": x, "y_m": 0.0, "z_m": 0.0, "yaw_deg": 0.0}],
    }
    obj = {
        "prim_id": "/World/Sdg/Obj_00",
        "class": "haul_truck",
        "asset_id": "haul-truck-220t",
        "length_m": 12.8,
        "width_m": 7.3,
        "height_m": 7.3,
    }
    return {
        "schema_version": "1.0",
        "index": 0,
        "record_id": rid,
        "family": "pit",
        "arm": arm,
        "split": "train",
        "scenario_seed": 11,
        "layout_id": "edge-a",
        "camera": CAMERA,
        "dr": dr,
        "objects": [obj],
        "distractors": [],
        "condition": "day",
    }


def _count(mask: np.ndarray) -> int:
    return int(mask.sum())


def _shoelace(poly: list[float]) -> float:
    xs, ys = poly[0::2], poly[1::2]
    return abs(sum(xs[i] * ys[(i + 1) % len(xs)] - xs[(i + 1) % len(xs)] * ys[i] for i in range(len(xs)))) / 2.0


# ---------------------------------------------------------------------------------------------------------------
# instance outlines and annotations
# ---------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-009-02")
def test_a_rectangle_has_a_four_corner_outline_of_its_own_area() -> None:
    mask = np.zeros((40, 50), dtype=bool)
    mask[10:25, 5:30] = True  # 15 rows x 25 columns
    (poly,) = masks.external_polygons(mask)
    assert len(poly) == 8
    assert _shoelace(poly) == 15 * 25
    assert set(zip(poly[0::2], poly[1::2], strict=True)) == {(5.0, 10.0), (30.0, 10.0), (30.0, 25.0), (5.0, 25.0)}


@pytest.mark.req("FR-009-02")
def test_an_l_shape_outline_has_six_corners_and_the_area_of_its_pixels() -> None:
    mask = np.zeros((30, 30), dtype=bool)
    mask[5:20, 5:10] = True  # vertical bar 15 x 5
    mask[15:20, 10:25] = True  # foot 5 x 15
    (poly,) = masks.external_polygons(mask)
    assert len(poly) == 12
    assert _shoelace(poly) == _count(mask)


@pytest.mark.req("FR-009-02")
def test_separate_components_give_one_polygon_each_largest_first() -> None:
    mask = np.zeros((30, 60), dtype=bool)
    mask[2:6, 2:6] = True  # 16 px
    mask[10:25, 20:50] = True  # 450 px
    polygons = masks.external_polygons(mask)
    assert [_shoelace(p) for p in polygons] == [450, 16]


@pytest.mark.req("FR-009-02")
def test_annotations_group_the_instances_of_an_object_and_leave_out_tiny_ones() -> None:
    ids = np.zeros((100, 200), dtype=np.uint32)
    ids[10:30, 20:60] = 2  # chassis of object 0 (40 x 20 = 800 px)
    ids[30:40, 20:60] = 3  # dump body of object 0 (40 x 10 = 400 px)
    ids[60:63, 100:105] = 4  # object 1, 15 px: counted, not annotated
    id_to_path = {
        0: "BACKGROUND",
        1: "UNLABELLED",
        2: "/World/Sdg/Obj_00/chassis",
        3: "/World/Sdg/Obj_00/dump_body",
        4: "/World/Sdg/Obj_01",
    }
    objects = [
        {"prim_id": "/World/Sdg/Obj_00", "class": "haul_truck"},
        {"prim_id": "/World/Sdg/Obj_01", "class": "person"},
    ]
    semantic, annotations, visible = scene_render.annotate(ids, id_to_path, objects)
    assert visible == {"/World/Sdg/Obj_00": 1200, "/World/Sdg/Obj_01": 15}
    assert int((semantic == 1).sum()) == 1200 and int((semantic == 4).sum()) == 15
    (ann,) = annotations
    assert ann["category_id"] == 1 and ann["image_id"] == 1 and ann["iscrowd"] == 0
    assert ann["bbox"] == [20.0, 10.0, 40.0, 30.0]  # x, y, w = 60 - 20, h = 40 - 10
    assert ann["area"] == 1200.0
    assert _shoelace(ann["segmentation"][0]) == 1200.0


# ---------------------------------------------------------------------------------------------------------------
# light and frustum
# ---------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-009-04")
def test_the_structured_sun_vector_is_the_analytical_conversion_of_elevation_and_azimuth() -> None:
    light = scene_render.light_for_row(_row())  # elevation 60, azimuth 180 (due south)
    assert light["direction"] == pytest.approx((0.0, -0.5, math.sqrt(3) / 2), abs=1e-12)
    assert light["fog_per_m"] == pytest.approx(0.5e-3)


@pytest.mark.req("FR-009-08")
def test_the_unstructured_light_scales_with_its_factor_and_has_no_fog() -> None:
    row = _row(arm="unstructured")
    row["dr"] = {**row["dr"], "light_intensity_factor": 4.0, "colour_temperature_k": 3000.0}
    light = scene_render.light_for_row(row)
    assert light["sun_intensity"] == 4.0 * scene_render.NOMINAL_SUN_INTENSITY
    assert light["temperature_k"] == 3000.0 and light["fog_per_m"] == 0.0


@pytest.mark.req("FR-009-44")
def test_a_point_ahead_is_in_the_frustum_and_one_behind_or_far_to_the_side_is_not() -> None:
    assert scene_render.in_frustum(CAMERA, [[10.0, 0.0, 3.0]])  # on the optical axis: projects to the principal point
    assert not scene_render.in_frustum(CAMERA, [[-10.0, 0.0, 3.0]])
    # 10 m ahead and 10 m left: u = 640 - 1108.5 < 0
    assert not scene_render.in_frustum(CAMERA, [[10.0, 10.0, 3.0]])
    flags = scene_render.frustum_flags(_row(x=40.0))
    assert flags == {"/World/Sdg/Obj_00": True}


# ---------------------------------------------------------------------------------------------------------------
# frame files through the CPU renderer (the same write_frame as the Isaac renderer)
# ---------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-009-02")
def test_a_frame_writes_the_files_and_a_record_that_validates(tmp_path: Path) -> None:
    record, measured = CpuRenderer().render_row(_row(), tmp_path / "f")
    assert [
        e
        for e in schema_errors(
            "perception-dataset", {**record, "frame_state": {"path": "x", "sha256": "0" * 64, "size_bytes": 1}}
        )
    ] == []
    assert record["coco_image_id"] == 1
    coco = json.loads((tmp_path / "f" / record["coco"]["path"]).read_text(encoding="utf-8"))
    assert schema_errors("coco-instances", coco) == []
    assert coco["images"][0]["id"] == 1 and len(coco["annotations"]) == 1
    depth = np.load(tmp_path / "f" / record["depth"]["path"])
    assert depth.dtype == np.float32 and depth.shape == (720, 1280)
    assert measured["annotations"] == 1 and measured["visible_px"]["/World/Sdg/Obj_00"] > 0
    assert measured["in_frustum"] == {"/World/Sdg/Obj_00": True}


# ---------------------------------------------------------------------------------------------------------------
# driver: resume, blocks, probe, preflight
# ---------------------------------------------------------------------------------------------------------------
class _Guard:
    def __init__(self, cooldown_after: int | None = None, stop_after: int | None = None) -> None:
        self.cooldown_after, self.stop_after, self.calls, self.cooled = cooldown_after, stop_after, 0, 0

    def check(self) -> str:
        self.calls += 1
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise RuntimeError("guard stop")
        return "cooldown" if self.cooldown_after is not None and self.calls % self.cooldown_after == 0 else "ok"

    def cool_down(self) -> None:
        self.cooled += 1


class _Counting:
    def __init__(self) -> None:
        self.rendered: list[str] = []
        self.closed = 0
        self._inner = CpuRenderer()

    def render_row(self, row, out_dir):
        self.rendered.append(row["record_id"])
        return self._inner.render_row(row, out_dir)

    def close(self) -> None:
        self.closed += 1


def _rows(n: int) -> list[dict]:
    return [_row(f"pit-s-{i:05d}", x=40.0 + i) for i in range(n)]


def _session(guard: _Guard | None):
    entered = []

    @contextlib.contextmanager
    def session():
        entered.append(1)
        yield guard

    return session, entered


@pytest.mark.req("NFR-009-03")
def test_a_killed_run_resumes_at_the_first_frame_without_a_sidecar(tmp_path: Path) -> None:
    rows = _rows(6)
    first = _Counting()
    session, _ = _session(None)
    result = driver.run(rows=rows, root=tmp_path, renderer_factory=lambda: first, session=session, limit=4)
    assert result == {"rendered": 4, "remaining": 2}
    assert not list(tmp_path.rglob("*.tmp"))
    second = _Counting()
    result = driver.run(rows=rows, root=tmp_path, renderer_factory=lambda: second, session=session)
    assert second.rendered == ["pit-s-00004", "pit-s-00005"]
    assert result == {"rendered": 2, "remaining": 0}


@pytest.mark.req("NFR-009-03")
def test_a_frame_whose_file_is_gone_is_rendered_again(tmp_path: Path) -> None:
    rows = _rows(2)
    session, _ = _session(None)
    driver.run(rows=rows, root=tmp_path, renderer_factory=_Counting, session=session)
    (tmp_path / "frames" / "pit-s-00001" / "depth" / "000000.npy").unlink()
    again = _Counting()
    driver.run(rows=rows, root=tmp_path, renderer_factory=lambda: again, session=session)
    assert again.rendered == ["pit-s-00001"]


@pytest.mark.req("NFR-009-03")
def test_a_guard_block_end_closes_the_renderer_releases_the_session_and_cools_down(tmp_path: Path) -> None:
    guard = _Guard(cooldown_after=3)
    session, entered = _session(guard)
    renderers: list[_Counting] = []

    def factory() -> _Counting:
        renderers.append(_Counting())
        return renderers[-1]

    result = driver.run(rows=_rows(7), root=tmp_path, renderer_factory=factory, session=session)
    assert result == {"rendered": 7, "remaining": 0}
    assert [len(r.rendered) for r in renderers] == [3, 3, 1]  # blocks of 3 frames, then the rest
    assert all(r.closed == 1 for r in renderers) and len(entered) == 3
    assert guard.cooled == 2  # between blocks, not after the last one


@pytest.mark.req("NFR-009-03")
def test_a_guard_stop_propagates_and_keeps_the_frames_already_written(tmp_path: Path) -> None:
    guard = _Guard(stop_after=3)
    session, _ = _session(guard)
    renderer = _Counting()
    with pytest.raises(RuntimeError, match="guard stop"):
        driver.run(rows=_rows(6), root=tmp_path, renderer_factory=lambda: renderer, session=session)
    assert renderer.closed == 1
    assert [driver.is_done(tmp_path, r) for r in _rows(6)] == [True, True, True, False, False, False]


@pytest.mark.req("FR-009-02")
def test_the_probe_stops_a_run_whose_first_frames_have_no_annotation(tmp_path: Path) -> None:
    rows = [_row(f"pit-s-{i:05d}", x=-40.0 - i) for i in range(5)]  # every truck is behind the camera
    session, _ = _session(None)
    with pytest.raises(driver.ProbeFailed, match="no annotation"):
        driver.run(rows=rows, root=tmp_path, renderer_factory=CpuRenderer, session=session)
    assert not any(driver.is_done(tmp_path, r) for r in rows)  # the probe frames are discarded, not kept as done
    assert not (tmp_path / "frames" / rows[0]["record_id"]).exists()


@pytest.mark.req("FR-009-02")
def test_the_first_frames_probe_both_arms_before_the_long_run(tmp_path: Path) -> None:
    rows = [_row(f"pit-s-{i:05d}", x=40.0 + i) for i in range(4)] + [
        _row(f"pit-u-{i:05d}", x=40.0 + i, arm="unstructured") for i in range(3)
    ]
    renderer = _Counting()
    session, _ = _session(None)
    driver.run(rows=rows, root=tmp_path, renderer_factory=lambda: renderer, session=session)
    assert renderer.rendered[:3] == ["pit-s-00000", "pit-s-00001", "pit-u-00000"]
    assert sorted(renderer.rendered) == sorted(r["record_id"] for r in rows)


@pytest.mark.req("FR-009-02")
def test_the_probe_rejects_empty_depth_and_a_flat_image() -> None:
    good = {"depth_finite_fraction": 1.0, "rgb_std": 30.0, "annotations": 1}
    driver.check_probe([good])
    with pytest.raises(driver.ProbeFailed, match="depth"):
        driver.check_probe([{**good, "depth_finite_fraction": 0.1}])
    with pytest.raises(driver.ProbeFailed, match="flat"):
        driver.check_probe([{**good, "rgb_std": 0.0}])


@pytest.mark.req("NFR-009-03")
def test_the_preflight_refuses_a_drive_that_cannot_hold_the_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Usage:
        free = driver.FREE_MARGIN_BYTES + 5 * driver.BYTES_PER_FRAME - 1

    monkeypatch.setattr(driver.shutil, "disk_usage", lambda _p: _Usage)
    with pytest.raises(OSError, match="GB free"):
        driver.preflight(tmp_path, 5)
    _Usage.free += 1
    driver.preflight(tmp_path, 5)


@pytest.mark.req("FR-009-02")
def test_the_table_reader_orders_structured_before_unstructured(tmp_path: Path) -> None:
    for name, rid in (("pit-unstructured.jsonl", "pit-u-00000"), ("pit-structured.jsonl", "pit-s-00000")):
        (tmp_path / name).write_text(json.dumps(_row(rid)) + "\n", encoding="utf-8")
    assert [r["record_id"] for r in driver.read_rows(tmp_path)] == ["pit-s-00000", "pit-u-00000"]
    with pytest.raises(FileNotFoundError):
        driver.read_rows(tmp_path / "empty")


# ---------------------------------------------------------------------------------------------------------------
# the Isaac lane runs on Python 3.12
# ---------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-009-02")
def test_every_source_of_the_isaac_lane_parses_as_python_3_12() -> None:
    """The dry run of the job found `except A, B:` (a 3.14 form the formatter writes) in `driver.py`: never again."""
    import ast

    sources = sorted((ROOT / "studio" / "isaac" / "src").rglob("*.py"))
    assert len(sources) >= 8
    for path in sources:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 12))


# ---------------------------------------------------------------------------------------------------------------
# the OpenUSD edits of the renderer, on a small scene of the layout of the real one
# ---------------------------------------------------------------------------------------------------------------
_ROOT_USDA = """#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    upAxis = "Z"
)

def Xform "World"
{
    def Xform "Terrain"
    {
        def Xform "Lod0"
        {
            def Mesh "Tile_0"
            {
            }
        }
    }

    def Xform "Design"
    {
        def Xform "Benches"
        {
            def Mesh "Bench_00"
            {
            }
        }

        def Xform "Berms"
        {
            def Mesh "Berm_00"
            {
            }
        }

        def Xform "HaulRoads"
        {
            def Mesh "Road_00"
            {
            }
        }

        def Xform "Ramp"
        {
            def Mesh "Ramp_00"
            {
            }
        }

        def Xform "Windrows"
        {
            def Mesh "Windrow_00"
            {
            }
        }
    }

    def Xform "Fleet"
    {
        def Xform "haul_truck_220t_00"
        {
        }
    }

    def Xform "People"
    {
        def Xform "Person_00"
        {
        }
    }

    def Scope "Lights"
    {
        def DistantLight "Sun"
        {
            float inputs:intensity = 3000
        }
    }
}
"""
_RAMP_USDA = """    def Xform "Ramp"
        {
            def Mesh "Ramp_00"
            {
            }
        }

"""
_TRUCK_USDA = """#usda 1.0
(
    defaultPrim = "haul_truck_220t"
)
def Xform "haul_truck_220t"
{
    def Mesh "chassis" (prepend apiSchemas = ["SemanticsLabelsAPI:class"])
    {
        token[] semantics:labels:class = ["haul_truck"]
    }
}
"""


def _usd_scene(tmp: Path) -> Path:
    (tmp / "assets").mkdir(parents=True)
    (tmp / "root.usda").write_text(_ROOT_USDA, encoding="utf-8")
    (tmp / "assets" / "haul-truck-220t.usda").write_text(_TRUCK_USDA, encoding="utf-8")
    return tmp


def _full_row() -> dict:
    """A structured row with one object of every placeable class, and an unstructured one with distractors."""
    row = _row()
    classes = ("haul_truck", "shovel", "light_vehicle", "person")
    dims = {
        "haul_truck": ("haul-truck-220t", 12.8, 7.3, 7.3),
        "shovel": (None, 15.0, 9.0, 11.0),
        "light_vehicle": (None, 5.3, 2.0, 1.9),
        "person": (None, 0.6, 0.6, 1.75),
    }
    row["objects"] = [
        {
            "prim_id": f"/World/Sdg/Obj_{i:02d}",
            "class": c,
            "asset_id": dims[c][0],
            "length_m": dims[c][1],
            "width_m": dims[c][2],
            "height_m": dims[c][3],
        }
        for i, c in enumerate(classes)
    ]
    row["dr"] = {
        **row["dr"],
        "placements": [
            {"class": c, "x_m": 30.0 + 20 * i, "y_m": 0.0, "z_m": 0.0, "yaw_deg": 10.0 * i}
            for i, c in enumerate(classes)
        ],
    }
    return row


@pytest.mark.req("FR-009-02")
def test_the_stage_edits_author_labelled_objects_bound_materials_and_the_camera(tmp_path: Path) -> None:
    pytest.importorskip("pxr")
    structured = _full_row()
    unstructured = {
        **_full_row(),
        "arm": "unstructured",
        "record_id": "pit-u-00000",
        "distractors": [
            {
                "prim_id": "/World/Sdg/Distractor_00",
                "shape": "cube",
                "centre_m": [20.0, 3.0, 1.0],
                "size_m": 2.0,
                "colour_rgb": [0.2, 0.3, 0.4],
            }
        ],
    }
    unstructured["dr"] = {
        **unstructured["dr"],
        "texture_ids": ["t1", "t2", "t3"],
        "light_intensity_factor": 2.0,
        "colour_temperature_k": 4000.0,
    }
    textures = {
        "rock-a": tmp_path / "a.jpg",
        "t1": tmp_path / "t1.jpg",
        "t2": tmp_path / "t2.jpg",
        "t3": tmp_path / "t3.jpg",
    }
    counts = scene_render.stage_selfcheck(_usd_scene(tmp_path / "scene"), textures, [structured, unstructured])
    assert counts == {"rows": 2, "objects": 8, "distractors": 1}


@pytest.mark.req("FR-009-02")
def test_a_scene_without_the_expected_prims_is_refused(tmp_path: Path) -> None:
    pytest.importorskip("pxr")
    scene = _usd_scene(tmp_path / "scene")
    (scene / "root.usda").write_text(_ROOT_USDA.replace(_RAMP_USDA, ""), encoding="utf-8")
    with pytest.raises(RuntimeError, match="/World/Design/Ramp"):
        scene_render.stage_selfcheck(scene, {"rock-a": tmp_path / "a.jpg"}, [_row()])


# ---------------------------------------------------------------------------------------------------------------
# queue entry paths
# ---------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-009-02")
def test_a_dry_run_needs_scratch_paths_and_never_the_real_dataset_root(tmp_path: Path) -> None:
    real = tmp_path / "processed" / "perception"
    with pytest.raises(ValueError, match="--table-dir and --out-root"):
        run_job.resolve_paths(tmp_path, dry_run=True, table_dir=None, out_root=None)
    with pytest.raises(ValueError, match="real dataset root"):
        run_job.resolve_paths(tmp_path, dry_run=True, table_dir=str(tmp_path / "t"), out_root=str(real))
    assert run_job.resolve_paths(
        tmp_path, dry_run=True, table_dir=str(tmp_path / "t"), out_root=str(tmp_path / "s")
    ) == (
        tmp_path / "t",
        tmp_path / "s",
    )
    assert run_job.resolve_paths(tmp_path, dry_run=False, table_dir=None, out_root=None) == (real / "param_table", real)

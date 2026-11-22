# ruff: noqa: E501, PT018
"""T-009-016 (fix): the SDG renderer shows the carved surface of `st20_pit_design`, never the source terrain (FR-009-54).

Requirements: FR-009-02, FR-009-54 (the surface the table takes every height from is the surface the renderer shows),
FR-004-50.

The scene here is built by hand: a root layer with the source terrain and the design meshes (what `st45_validate` holds),
a `st20_pit_design` folder next to it with the carved layer written by `design.carved.write_carved_layer`, the digests of
the stage and the manifest that ties the pit design report to the scene. Oracles: the prim states of the composed stage
(OpenUSD reference implementation), the material bindings it resolves, the SHA-256 of the files.

Expected API (`pitstudio_isaac.sdg.scene_render`):
- `carved_layer(scene_dir) -> Path | None`: the layer of the sibling `st20_pit_design` folder, None when it has none,
  `RuntimeError` when its SHA-256 differs from `digests.json` or the stage's pit design report differs from the one
  the scene manifest records.
- the stage self-check (and the renderer) composes the layer, deactivates `/World/Terrain` and `/World/Design`, binds the
  `rock` material to `/World/Carved` and the `gravel` material to every `road` face subset of the carved tiles;
  `SdgRenderer(...)` refuses a scene without a carved layer.
- `run_job.missing_inputs()` lists a scene without a carved layer.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
from pitstudio_isaac.sdg import scene_render  # noqa: E402
from pitstudio_studio.scene.design import carved  # noqa: E402

ROOT_USDA = """#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    upAxis = "Z"
)

def Xform "World"
{
    def Xform "Terrain"
    {
        def Mesh "Tile"
        {
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

    def Xform "Lights"
    {
        def DistantLight "Sun"
        {
        }
    }
}
"""
DEFAULT_ROW = {
    "record_id": "pit-s-00000",
    "arm": "structured",
    "dr": {
        "sun_elevation_deg": 40.0,
        "sun_azimuth_deg": 90.0,
        "dust_extinction_per_km": 0.0,
        "rock_texture_ids": ["rock-a"],
        "placements": [],
    },
    "objects": [],
    "distractors": [],
    "camera": {
        "position_m": [0.0, 0.0, 10.0],
        "forward": [1.0, 0.0, -0.1],
        "up": [0.0, 0.0, 1.0],
        "width_px": 1280,
        "height_px": 720,
        "fx_px": 900.0,
        "fy_px": 900.0,
        "cx_px": 640.0,
        "cy_px": 360.0,
    },
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_tree(tmp: Path, *, name: str = "a1", carved_layer: bool = True, tamper: str | None = None) -> Path:
    base = tmp / name
    scene = base / "st45_validate" / "scene"
    (scene / "assets").mkdir(parents=True)
    (scene / "root.usda").write_text(ROOT_USDA, encoding="utf-8")
    report = json.dumps({"ramp": {"min_width_m": 30.0}}).encode()
    (scene / "scene.manifest.json").write_text(
        json.dumps(
            {
                "validation": {"status": "complete"},
                "design": {"report": {"path": "design/pit-design-report.json", "sha256": _sha(report)}},
            }
        ),
        encoding="utf-8",
    )
    if carved_layer:
        stage = base / "st20_pit_design"
        (stage / "layers").mkdir(parents=True)
        (stage / "design").mkdir(parents=True)
        (stage / "design" / "pit-design-report.json").write_bytes(report + (b" " if tamper == "report" else b""))
        elevation = np.zeros((40, 40), dtype=np.float32)
        road = np.zeros((40, 40), dtype=bool)
        road[10:20, :] = True
        carved.write_carved_layer(
            stage / "layers" / "design-carved.usdc",
            elevation,
            lods=[{"lod": 0, "max_error_m": 0.25, "skirt_depth_m": 0.5}],
            x_min_m=0.0,
            y_max_m=40.0,
            cell_size_m=1.0,
            road_mask=road,
        )
        digest = _sha((stage / "layers" / "design-carved.usdc").read_bytes())
        digests = {"layers/design-carved.usdc": "0" * 64 if tamper == "layer" else digest}
        (stage / "digests.json").write_text(json.dumps(digests), encoding="utf-8")
    return scene


@pytest.mark.req("FR-009-54")
def test_the_carved_layer_of_the_sibling_stage_is_found_and_a_scene_without_one_gives_none(tmp_path) -> None:
    scene = make_tree(tmp_path / "with")
    layer = scene_render.carved_layer(scene)
    assert layer is not None and layer.name == "design-carved.usdc" and layer.is_file()
    assert scene_render.carved_layer(make_tree(tmp_path / "without", carved_layer=False)) is None


@pytest.mark.req("FR-009-54")
def test_a_carved_layer_that_differs_from_its_digest_or_belongs_to_another_build_is_refused(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="SHA-256"):
        scene_render.carved_layer(make_tree(tmp_path / "a", tamper="layer"))
    with pytest.raises(RuntimeError, match="another build"):
        scene_render.carved_layer(make_tree(tmp_path / "b", tamper="report"))


@pytest.mark.req("FR-009-54")
def test_the_stage_shows_the_carved_surface_and_hides_the_source_terrain_and_the_design_meshes(tmp_path) -> None:
    pxr = pytest.importorskip("pxr")
    scene = make_tree(tmp_path)
    textures = {"rock-a": tmp_path / "a.jpg"}
    counts = scene_render.stage_selfcheck(scene, textures, [DEFAULT_ROW])
    assert counts["rows"] == 1
    stage = pxr.Usd.Stage.Open(str(scene / "root.usda"))
    renderer = scene_render.SdgRenderer.__new__(scene_render.SdgRenderer)
    renderer.scene_dir, renderer.textures, renderer._carb = scene, textures, None
    renderer._prepare_stage(stage)
    for path in ("/World/Terrain", "/World/Design"):
        assert not stage.GetPrimAtPath(path).IsActive(), path
    assert stage.GetPrimAtPath("/World/Carved").IsValid()
    tiles = [p for p in pxr.Usd.PrimRange(stage.GetPrimAtPath("/World/Carved")) if p.IsA(pxr.UsdGeom.Mesh)]
    assert tiles
    # a prim of the inactive subtrees is not traversed by the renderer
    visible = {p.GetPath().pathString for p in stage.Traverse()}
    assert not any(p.startswith(("/World/Terrain", "/World/Design")) for p in visible)


@pytest.mark.req("FR-009-54")
def test_rock_is_bound_to_the_carved_surface_and_gravel_to_every_road_subset(tmp_path) -> None:
    pxr = pytest.importorskip("pxr")
    scene = make_tree(tmp_path)
    stage = pxr.Usd.Stage.Open(str(scene / "root.usda"))
    renderer = scene_render.SdgRenderer.__new__(scene_render.SdgRenderer)
    renderer.scene_dir, renderer.textures, renderer._carb = scene, {"rock-a": tmp_path / "a.jpg"}, None
    renderer._prepare_stage(stage)
    bind = pxr.UsdShade.MaterialBindingAPI
    root = stage.GetPrimAtPath("/World/Carved")
    assert bind(root).ComputeBoundMaterial()[0].GetPath().pathString == f"{scene_render.MATERIAL_SCOPE}/rock"
    subsets = [p for p in pxr.Usd.PrimRange(root) if p.IsA(pxr.UsdGeom.Subset)]
    assert subsets and all(p.GetName() == "road" for p in subsets)
    for prim in subsets:
        assert bind(prim).ComputeBoundMaterial()[0].GetPath().pathString == f"{scene_render.MATERIAL_SCOPE}/gravel"
    mesh = subsets[0].GetPrim().GetParent()
    assert bind(mesh).ComputeBoundMaterial()[0].GetPath().pathString == f"{scene_render.MATERIAL_SCOPE}/rock"


@pytest.mark.req("FR-009-54")
def test_the_real_renderer_refuses_a_scene_without_a_carved_layer(tmp_path) -> None:
    scene = make_tree(tmp_path, carved_layer=False)
    with pytest.raises(RuntimeError, match="no carved layer"):
        scene_render.SdgRenderer(scene, {})


@pytest.mark.req("FR-009-54")
def test_the_job_inputs_list_a_scene_without_a_carved_layer(tmp_path, monkeypatch) -> None:
    from pitstudio_isaac.sdg import run_job

    data = tmp_path / "data"
    make_tree(data / "processed" / "scene", name="a1-bingham", carved_layer=False)
    monkeypatch.setenv("PITSTUDIO_DATA", str(data))
    monkeypatch.delenv("PITSTUDIO_SDG_SCENE", raising=False)
    missing = run_job.missing_inputs()
    assert any("carved surface" in line and "FR-004-50" in line for line in missing), missing

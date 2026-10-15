# ruff: noqa: E501, PT018, RUF001
"""T-004-016: USD terrain layer metadata, labels, provenance and attribution.

Requirements: FR-004-08.

Oracle: the layer is read back with OpenUSD (`pxr`, reference implementation: `UsdGeom.GetStageUpAxis`,
`GetStageMetersPerUnit`, `UsdPhysics.GetStageKilogramsPerUnit`, the `UsdSemantics` schema API, variant sets) and compared
with the values handed in (hand-written expected attribute values, plan.md "FR-004-08"); the tile digest is recomputed
with hashlib from the mesh buffers stored in the layer.

Expected API (package `pitstudio_studio.scene.terrain`, studio environment):
- `terrain.usd.write_terrain_layer(path, tileset, *, source_id, project, epoch, attribution)` writes `terrain.usdc`
  (a binary crate layer). `tileset` is a `terrain.tiles.TileSet` (see test_t_004_015). The layer authors explicitly
  `upAxis = "Z"`, `metersPerUnit = 1.0`, `kilogramsPerUnit = 1.0`; has a default prim `World`; holds the prim
  `/World/Terrain` with a variant set `lod` whose variants are `lod0`, `lod1`, `lod2` (named after the LODs) and, in each
  variant, one `Mesh` prim per tile at the tile's index path (`index_entries[i]["prim"]`, e.g.
  `/World/Terrain/Lod0/Tile_0_1_0_0`), whose `points` / `faceVertexIndices` are the tile's float32 positions and uint32
  indices (all faces triangles). Every mesh prim has `SemanticsLabelsAPI:class` with the label `terrain`; the attributes
  `pitstudio:source_id` (string), `pitstudio:project` (string), `pitstudio:epoch` (int) and `pitstudio:attribution`
  (string) are authored on `/World/Terrain` (or on every mesh prim).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import terrain  # noqa: E402

LODS = [
    {"lod": 0, "max_error_m": 0.25, "skirt_depth_m": 0.5},
    {"lod": 1, "max_error_m": 1.0, "skirt_depth_m": 2.0},
    {"lod": 2, "max_error_m": 4.0, "skirt_depth_m": 8.0},
]
ATTRIBUTION = (
    "Elevation data: U.S. Geological Survey, 3D Elevation Program (3DEP), project UT Central QL2 2018, "
    "accessed 2026-10-02."
)


def _write(tmp_path: Path, attribution: str = ATTRIBUTION) -> tuple[Path, terrain.tiles.TileSet]:
    h = kit.fbm_grid(9, 8, amplitude=40.0)[:513, :513]
    ts = terrain.tiles.build_tiles(h, cell_size_m=1.0, x_min_m=-256.0, y_max_m=256.0, lods=LODS)
    path = tmp_path / "terrain.usdc"
    terrain.usd.write_terrain_layer(
        path, ts, source_id="usgs-3dep-bingham", project="UT Central QL2 2018", epoch=2018, attribution=attribution
    )
    return path, ts


def _meshes(stage, lod_name: str):
    from pxr import Usd, UsdGeom

    root = stage.GetPrimAtPath("/World/Terrain")
    root.GetVariantSet("lod").SetVariantSelection(lod_name)
    return [p for p in Usd.PrimRange(root) if p.IsA(UsdGeom.Mesh)]


@pytest.mark.req("FR-004-08")
def test_units_and_up_axis_are_authored_explicitly_in_the_layer(tmp_path: Path) -> None:
    from pxr import Sdf, Usd, UsdGeom, UsdPhysics

    path, _ = _write(tmp_path)
    assert path.read_bytes()[:8] == b"PXR-USDC"  # a binary crate layer
    layer = Sdf.Layer.FindOrOpen(str(path))
    for key, want in (("upAxis", "Z"), ("metersPerUnit", 1.0), ("kilogramsPerUnit", 1.0)):
        assert layer.pseudoRoot.HasInfo(key), f"{key} must be authored, not defaulted"
        assert layer.pseudoRoot.GetInfo(key) == want
    stage = Usd.Stage.Open(str(path))
    assert UsdGeom.GetStageUpAxis(stage) == "Z"
    assert UsdGeom.GetStageMetersPerUnit(stage) == 1.0
    assert UsdPhysics.GetStageKilogramsPerUnit(stage) == 1.0


@pytest.mark.req("FR-004-08")
def test_one_lod_variant_per_lod_holding_that_lods_tile_meshes(tmp_path: Path) -> None:
    from pxr import Usd

    path, ts = _write(tmp_path)
    stage = Usd.Stage.Open(str(path))
    root = stage.GetPrimAtPath("/World/Terrain")
    assert root.IsValid()
    variant_set = root.GetVariantSet("lod")
    assert variant_set.GetVariantNames() == ["lod0", "lod1", "lod2"]
    for lod in (0, 1, 2):
        meshes = _meshes(stage, f"lod{lod}")
        entries = [e for e in ts.index_entries if e["lod"] == lod]
        assert sorted(str(m.GetPath()) for m in meshes) == sorted(e["prim"] for e in entries)
        assert len(meshes) == 4


@pytest.mark.req("FR-004-08")
def test_mesh_buffers_in_the_layer_match_the_tile_digest(tmp_path: Path) -> None:
    from pxr import Usd, UsdGeom

    path, ts = _write(tmp_path)
    stage = Usd.Stage.Open(str(path))
    for lod in (0, 2):
        _meshes(stage, f"lod{lod}")
        for e in (e for e in ts.index_entries if e["lod"] == lod):
            mesh = UsdGeom.Mesh(stage.GetPrimAtPath(e["prim"]))
            pos = np.array(mesh.GetPointsAttr().Get(), dtype="<f4")
            idx = np.array(mesh.GetFaceVertexIndicesAttr().Get(), dtype="<u4")
            counts = np.array(mesh.GetFaceVertexCountsAttr().Get())
            assert (counts == 3).all() and len(idx) == 3 * e["triangles"] and len(pos) == e["vertices"]
            assert hashlib.sha256(pos.tobytes() + idx.tobytes()).hexdigest() == e["sha256"]


@pytest.mark.req("FR-004-08")
def test_every_mesh_prim_has_the_terrain_class_label_without_time_samples(tmp_path: Path) -> None:
    from pxr import Usd, UsdSemantics

    path, _ = _write(tmp_path)
    stage = Usd.Stage.Open(str(path))
    for lod in (0, 1, 2):
        for prim in _meshes(stage, f"lod{lod}"):
            assert "SemanticsLabelsAPI:class" in prim.GetAppliedSchemas()
            labels = UsdSemantics.LabelsAPI(prim, "class").GetLabelsAttr()
            assert list(labels.Get()) == ["terrain"]
            assert labels.GetNumTimeSamples() == 0


@pytest.mark.req("FR-004-08")
@pytest.mark.parametrize("attribution", [ATTRIBUTION, "Données altimétriques © Service géologique – Ünïcode ✓"])
def test_provenance_attributes_carry_the_dataset_card_text(tmp_path: Path, attribution: str) -> None:
    from pxr import Usd

    path, _ = _write(tmp_path, attribution)
    stage = Usd.Stage.Open(str(path))
    want = {
        "pitstudio:source_id": "usgs-3dep-bingham",
        "pitstudio:project": "UT Central QL2 2018",
        "pitstudio:epoch": 2018,
        "pitstudio:attribution": attribution,
    }

    def has_all(prim) -> bool:
        return all(prim.HasAttribute(k) and prim.GetAttribute(k).Get() == v for k, v in want.items())

    root = stage.GetPrimAtPath("/World/Terrain")
    meshes = _meshes(stage, "lod1")
    assert has_all(root) or all(has_all(m) for m in meshes)
    for prim in [root, *meshes]:
        if prim.HasAttribute("pitstudio:epoch"):
            assert type(prim.GetAttribute("pitstudio:epoch").Get()) is int

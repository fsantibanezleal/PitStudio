# ruff: noqa: PT018
"""T-004-050 (fix): every mesh that the real scene stages author carries normals.

Requirements: FR-004-34.

The first run of `st45_validate` on the real Bingham scene reported one `NormalsExistChecker` error per mesh of the
terrain tiles, the design layer and the fleet (5232 errors). The unit tests of the validators only saw hand-written
fixture meshes with normals, so the defect stayed hidden.

Oracle: the layers are read back with OpenUSD; the expected normal of a face is the unit vector of the cross product of
two of its edges, computed here with numpy; `usd-validation-nvidia` itself is run on a layer written by the stage code.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import assets, design, terrain  # noqa: E402

LODS = [{"lod": 0, "max_error_m": 0.25, "skirt_depth_m": 0.5}, {"lod": 1, "max_error_m": 1.0, "skirt_depth_m": 2.0}]


def _meshes(stage):
    from pxr import Usd, UsdGeom

    return [p for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.IsA(UsdGeom.Mesh)]


def _check_normals(stage) -> int:
    from pxr import UsdGeom

    meshes = _meshes(stage)
    assert meshes
    for prim in meshes:
        mesh = UsdGeom.Mesh(prim)
        normals = mesh.GetNormalsAttr().Get()
        assert normals is not None and len(normals) > 0, f"{prim.GetPath()} has no authored normals"
        n = np.asarray(normals, dtype=np.float64)
        assert np.allclose(np.linalg.norm(n, axis=1), 1.0, atol=1e-5), f"{prim.GetPath()}: normals are not unit vectors"
        interpolation = mesh.GetNormalsInterpolation()
        points = len(mesh.GetPointsAttr().Get())
        faces = len(mesh.GetFaceVertexCountsAttr().Get())
        assert len(n) == {"vertex": points, "uniform": faces}[interpolation], f"{prim.GetPath()}: {interpolation} count"
    return len(meshes)


@pytest.mark.req("FR-004-34")
def test_terrain_tiles_carry_unit_normals_that_point_up_on_flat_ground(tmp_path: Path) -> None:
    from pxr import Usd, UsdGeom

    h = np.zeros((129, 129))
    ts = terrain.tiles.build_tiles(h, cell_size_m=1.0, x_min_m=-64.0, y_max_m=64.0, lods=LODS)
    path = tmp_path / "terrain.usdc"
    terrain.usd.write_terrain_layer(path, ts, source_id="usgs-3dep-bingham", project="p", epoch=2018, attribution="a")
    stage = Usd.Stage.Open(str(path))
    stage.GetPrimAtPath("/World/Terrain").GetVariantSet("lod").SetVariantSelection("lod0")
    assert _check_normals(stage) >= 1
    tile = next(p for p in _meshes(stage) if str(p.GetPath()).startswith("/World/Terrain/Lod0/"))
    mesh = UsdGeom.Mesh(tile)
    n = np.asarray(mesh.GetNormalsAttr().Get(), dtype=np.float64)
    pts = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float64)
    interior = (pts[:, 2] == 0.0) & (np.abs(pts[:, 0]) < 30.0) & (np.abs(pts[:, 1]) < 30.0)  # away from the skirts
    assert interior.any()
    assert np.allclose(np.abs(n[interior, 2]), 1.0, atol=1e-5), "flat terrain must have vertical normals"


@pytest.mark.req("FR-004-34")
def test_design_meshes_carry_normals(tmp_path: Path) -> None:
    from pxr import Usd

    grid = kit.flat_grid(130.0, 1.0, 0.0)
    spec = kit.design_spec(h=12.0, alpha=70.0, b=10.0, g=8.0, w=20.0, windrow=2.5, floor_z=-36.0)
    res = design.build_design(grid, spec, outline_xy=kit.regular_polygon(180, 100.0))
    path = tmp_path / "design.usda"
    design.usd.write_design_layer(path, res, rel_path="layers/design.usda")
    assert _check_normals(Usd.Stage.Open(str(path))) > 10


@pytest.mark.req("FR-004-34")
def test_machine_boxes_carry_one_outward_normal_per_face(tmp_path: Path) -> None:
    from pxr import Usd, UsdGeom

    spec = kit.machine_spec(("haul_truck",))
    machine = assets.build_assets(spec, tmp_path).machines["haul-truck-220t"]
    stage = Usd.Stage.Open(str(machine))
    assert _check_normals(stage) == 2
    for prim in _meshes(stage):
        mesh = UsdGeom.Mesh(prim)
        assert mesh.GetNormalsInterpolation() == "uniform"
        n = np.asarray(mesh.GetNormalsAttr().Get(), dtype=np.float64)
        pts = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float64)
        centre = pts.mean(axis=0)
        idx = np.asarray(mesh.GetFaceVertexIndicesAttr().Get()).reshape(-1, 4)
        for face, normal in zip(idx, n, strict=True):
            assert np.dot(pts[face].mean(axis=0) - centre, normal) > 0, "a box face normal points inward"


@pytest.mark.req("FR-004-34")
def test_the_nvidia_validator_reports_no_normals_error_on_a_written_design_layer(tmp_path: Path) -> None:
    import usd_validation_nvidia as uvn
    from pxr import Usd

    grid = kit.flat_grid(130.0, 1.0, 0.0)
    spec = kit.design_spec(h=12.0, alpha=70.0, b=10.0, g=8.0, w=20.0, windrow=2.5, floor_z=-36.0)
    res = design.build_design(grid, spec, outline_xy=kit.regular_polygon(180, 100.0))
    path = tmp_path / "design.usda"
    design.usd.write_design_layer(path, res, rel_path="layers/design.usda")
    result = uvn.ValidationEngine().validate(Usd.Stage.Open(str(path)))
    rules = {getattr(i.rule, "__name__", str(i.rule)) for i in result.issues()}
    assert "NormalsExistChecker" not in rules, rules

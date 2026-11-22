# ruff: noqa: E501, PT018
"""T-004-095: terrain tiles carry grid normals and texture coordinates; the root layer binds the rock and road materials.

Requirements: FR-004-45, FR-004-46.

Oracle: an analytic terrain (`dem_kit.plane_z`, a piecewise-linear surface) whose unit normal is
`(-dz/dx, -dz/dy, 1) / norm` by hand; OpenUSD read back (`UsdShade.MaterialBindingAPI`, `UsdGeom.PrimvarsAPI`) as the
reference implementation; `materials.usda` byte equality for "never edited".

Expected API (package `pitstudio_studio.scene.compose`, studio environment): `compose.compose_scene(spec, upstream,
scene_dir)` as in T-004-040. With `terrain/grid.zarr/elevation` among the record files the composed `layers/terrain.usdc`
has, for every tile mesh of every `lod` variant, `normals` from the central-difference gradient of the grid at each vertex
and `primvars:st` (texcoord2f[], vertex interpolation) = (x / 50, y / 50); points are unchanged. With
`assets/materials.usda` among the assets `root.usda` references it under `/World/Materials`, binds `/World/Terrain` to
`bench_rock` and `/World/Design/HaulRoads` to `gravel_road`, sets `wrapS` and `wrapT` to `repeat` on every texture shader
and, for a texture file missing from `assets/textures`, disconnects the texture and authors a constant diffuse colour.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import dem_kit as dk  # noqa: E402
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import compose  # noqa: E402

TEXTURE_PERIOD_M = 50.0


def _spec() -> dict:
    spec = kit.scene_spec()
    spec["variants"] = {
        "pushback": ["pb0"],
        "scenario": ["baseline"],
        "time_of_day": ["noon"],
        "weather": ["clear"],
        "lod": ["lod0", "lod1", "lod2"],
    }
    return spec


def _compose(base: Path, **kw):
    up = dk.upstream(base / "up", **kw)
    return up, compose.compose_scene(_spec(), up, base / "scene"), base / "scene"


@pytest.fixture(scope="module")
def look(tmp_path_factory: pytest.TempPathFactory):
    base = tmp_path_factory.mktemp("look")
    return _compose(base)


def _meshes(stage, lod: str) -> list:
    from pxr import UsdGeom

    stage.GetPrimAtPath("/World").GetVariantSet("lod").SetVariantSelection(lod)
    return [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh) and "/Terrain/" in str(p.GetPath())]


def _open(folder: Path):
    from pxr import Usd

    return Usd.Stage.Open(str(folder / "root.usda"))


@pytest.mark.req("FR-004-45")
def test_vertex_normals_are_the_grid_gradient_at_every_vertex_skirt_included(look) -> None:
    from pxr import UsdGeom

    _, _, folder = look
    stage = _open(folder)
    for lod in ("lod0", "lod1", "lod2"):
        meshes = _meshes(stage, lod)
        assert len(meshes) == 2, lod
        for prim in meshes:
            mesh = UsdGeom.Mesh(prim)
            pts, nrm = np.array(mesh.GetPointsAttr().Get()), np.array(mesh.GetNormalsAttr().Get())
            assert nrm.shape == pts.shape and mesh.GetNormalsInterpolation() == "vertex"
            want = np.array([dk.analytic_normal(x, y) for x, y, _ in pts])
            assert np.abs(nrm - want).max() < 1e-4, (lod, prim.GetPath())


@pytest.mark.req("FR-004-45")
def test_adjacent_tiles_agree_on_their_shared_border(look) -> None:
    from pxr import UsdGeom

    _, _, folder = look
    stage = _open(folder)
    a, b = (UsdGeom.Mesh(p) for p in _meshes(stage, "lod0"))
    na = {(round(x, 6), round(y, 6), round(z, 6)): n for (x, y, z), n in zip(a.GetPointsAttr().Get(), a.GetNormalsAttr().Get(), strict=True)}
    shared = 0
    for (x, y, z), n in zip(b.GetPointsAttr().Get(), b.GetNormalsAttr().Get(), strict=True):
        key = (round(x, 6), round(y, 6), round(z, 6))
        if key in na:
            shared += 1
            assert np.abs(np.array(n) - np.array(na[key])).max() < 1e-6
            if abs(z - dk.plane_z(x, y)) < 1e-6:  # a surface vertex: both tiles carry the analytic normal
                assert np.abs(np.array(n) - dk.analytic_normal(x, y)).max() < 1e-4
    assert shared >= 10  # the five surface vertices of the border and their skirt copies


@pytest.mark.req("FR-004-45")
def test_points_are_unchanged_and_planar_texture_coordinates_are_authored(look) -> None:
    from pxr import Usd, UsdGeom

    up, _, folder = look
    before = Usd.Stage.Open(str(up["layers"]["terrain"]))
    after = _open(folder)
    for lod in ("lod0", "lod1", "lod2"):
        for p_before, p_after in zip(_meshes(before, lod), _meshes(after, lod), strict=True):
            assert list(UsdGeom.Mesh(p_before).GetPointsAttr().Get()) == list(UsdGeom.Mesh(p_after).GetPointsAttr().Get())
            pv = UsdGeom.PrimvarsAPI(p_after).GetPrimvar("st")
            assert pv and pv.GetInterpolation() == "vertex" and str(pv.GetTypeName()) == "texCoord2f[]"
            st, pts = np.array(pv.Get()), np.array(UsdGeom.Mesh(p_after).GetPointsAttr().Get())
            assert np.abs(st - pts[:, :2] / TEXTURE_PERIOD_M).max() < 1e-5


@pytest.mark.req("FR-004-46")
def test_terrain_is_bound_to_the_rock_and_the_haul_road_to_the_gravel(look) -> None:
    from pxr import Usd, UsdGeom, UsdShade

    _, _, folder = look
    stage = _open(folder)
    for lod in ("lod0", "lod1", "lod2"):
        for prim in _meshes(stage, lod):
            bound = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
            assert str(bound.GetPath()) == "/World/Materials/bench_rock", prim.GetPath()
    road = next(p for p in stage.Traverse() if str(p.GetPath()) == "/World/Design/HaulRoads/Road_00")
    assert road.IsA(UsdGeom.Mesh)
    assert str(UsdShade.MaterialBindingAPI(road).ComputeBoundMaterial()[0].GetPath()) == "/World/Materials/gravel_road"
    assert Usd.Stage.Open(str(folder / "assets" / "materials.usda")) is not None


@pytest.mark.req("FR-004-46")
def test_textures_repeat_and_resolve_and_a_missing_texture_gives_a_constant_colour(look) -> None:
    from pxr import UsdShade

    _, _, folder = look  # fixture: bench_rock.jpg exists, gravel_road.jpg does not
    stage = _open(folder)
    for name in ("bench_rock", "gravel_road"):
        tex = UsdShade.Shader(stage.GetPrimAtPath(f"/World/Materials/{name}/Texture"))
        assert tex.GetInput("wrapS").Get() == "repeat" and tex.GetInput("wrapT").Get() == "repeat", name
    rock = UsdShade.Shader(stage.GetPrimAtPath("/World/Materials/bench_rock/Texture")).GetInput("file").Get()
    assert Path(rock.resolvedPath).is_file()
    surface = UsdShade.Shader(stage.GetPrimAtPath("/World/Materials/bench_rock/Surface")).GetInput("diffuseColor")
    assert surface.HasConnectedSource()
    gravel = UsdShade.Shader(stage.GetPrimAtPath("/World/Materials/gravel_road/Surface")).GetInput("diffuseColor")
    assert not gravel.HasConnectedSource()
    colour = tuple(gravel.Get())
    assert len(colour) == 3 and all(0.0 < c < 1.0 for c in colour)


@pytest.mark.req("FR-004-46")
def test_the_material_layer_is_copied_unchanged_and_no_geometry_is_added(look) -> None:
    from pxr import Sdf

    up, _, folder = look
    source = next(Path(a) for a in up["assets"] if Path(a).name == "materials.usda")
    assert (folder / "assets" / "materials.usda").read_bytes() == source.read_bytes()
    root = Sdf.Layer.FindOrOpen(str(folder / "root.usda"))
    materials = root.GetPrimAtPath("/World/Materials")
    assert materials.referenceList.prependedItems[0].assetPath == "assets/materials.usda"


@pytest.mark.req("FR-004-45")
@pytest.mark.req("FR-004-46")
def test_a_scene_without_grid_or_materials_is_composed_as_before(tmp_path: Path) -> None:
    from pxr import Sdf, UsdGeom

    _, build, folder = _compose(tmp_path, grid=False, road=False, materials=False)
    stage = _open(folder)
    mesh = UsdGeom.Mesh(_meshes(stage, "lod0")[0])
    assert set(map(tuple, np.array(mesh.GetNormalsAttr().Get()))) == {(0.0, 1.0, 0.0)}  # untouched
    assert not UsdGeom.PrimvarsAPI(mesh.GetPrim()).GetPrimvar("st")
    assert Sdf.Layer.FindOrOpen(str(folder / "root.usda")).GetPrimAtPath("/World/Materials") is None
    assert build.manifest["validation"] == {"status": "pending"}


@pytest.mark.req("FR-004-45")
def test_composing_twice_gives_identical_terrain_and_root_layers(tmp_path: Path) -> None:
    _, _, one = _compose(tmp_path / "one")
    _, _, two = _compose(tmp_path / "two")
    for rel in ("layers/terrain.usdc", "layers/fleet.usda", "root.usda"):
        assert kit.sha256_file(one / rel) == kit.sha256_file(two / rel), rel

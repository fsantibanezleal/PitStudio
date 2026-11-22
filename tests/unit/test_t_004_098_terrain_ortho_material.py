# ruff: noqa: E501, PT018
"""T-004-098: the terrain material reads the orthophoto through `st_ortho` and the rock normal map through `st`.

Requirements: FR-004-49 (and the rock material of FR-004-26 with its normal map).

Oracle: the analytic terrain of `dem_kit` (400 x 400 cells of 1 m, x and y from -200 to 200): with the grid extent mapped
to [0, 1] the coordinate of a vertex is `u = (x + 200) / 400`, `v = (y + 200) / 400` (v up: the bottom row of the image is
v = 0) by hand; OpenUSD read back (`UsdShade`, `UsdGeom.PrimvarsAPI`) as the reference implementation; the scene manifest
schema as the contract.

Expected API (package `pitstudio_studio.scene`, studio environment):
- `compose.look.ortho_st(xy, grid)` returns the float32 `(n, 2)` coordinates of the points `xy` for the extent of `grid`.
- `compose.compose_scene(spec, upstream, scene_dir)`: with `terrain/albedo/ortho.jpg` among the record files every tile
  mesh of every `lod` variant has `primvars:st_ortho` (texcoord2f[], vertex interpolation); `/World/Materials/terrain_ortho`
  is a `UsdPreviewSurface` whose `diffuseColor` is the `UsdUVTexture` of that file through a primvar reader of `st_ortho`
  and whose `normal` is the `UsdUVTexture` of `assets/textures/bench_rock_normal.jpg` (raw colour space, scale 2 and bias -1)
  through a `UsdTransform2d` of scale `assets.ST_PERIOD_M / assets.ROCK_REPEAT_M` fed by a primvar reader of `st`, with `wrapS`
  and `wrapT` `repeat`; `/World/Terrain` is bound to it in place of `bench_rock`; without the orthophoto `bench_rock` stays.
- `assets.build_assets(spec, out, textures=)` with a texture named `<material id>-normal` also writes
  `assets/textures/<prim>_normal<suffix>`, records it (`id`, `source`, `spdx`, `sha256`) after its material and adds to that
  material a `NormalTexture` shader wired to the surface `normal` and a `Repeat` `UsdTransform2d` (scale
  `ST_PERIOD_M / ROCK_REPEAT_M`) between the primvar reader and both textures.
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
from pitstudio_studio.scene import assets, compose  # noqa: E402
from pitstudio_studio.scene.compose import grid as grid_mod  # noqa: E402
from pitstudio_studio.scene.compose import look  # noqa: E402

IMG = "usda-naip-bingham"


def _spec() -> dict:
    spec = kit.scene_spec()
    spec["variants"] = {"pushback": ["pb0"], "scenario": ["baseline"], "time_of_day": ["noon"], "weather": ["clear"], "lod": ["lod0", "lod1", "lod2"]}
    return spec


def _jpeg(path: Path) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.full((4, 4, 3), (120, 110, 90), dtype=np.uint8)).save(path, format="JPEG")
    return path


def _upstream(base: Path, *, ortho: bool = True, normal: bool = True) -> dict:
    up = dk.upstream(base / "up")
    if normal:
        kit.tiny_png(base / "up" / "assets_src" / "textures" / "bench_rock_normal.jpg", (128, 128, 255))
    if ortho:
        image = _jpeg(base / "up" / "records" / "terrain" / "albedo" / "ortho.jpg")
        up["files"]["terrain/albedo/ortho.jpg"] = image
        up["records"]["terrain"]["albedo"] = {
            "source": IMG,
            "year": 2018,
            "dem_year": 2018,
            "ground_resolution_m": 0.6,
            "images": [{"path": "terrain/albedo/ortho.jpg", "sha256": kit.sha256_file(image)}],
            "inputs": [{"path": f"{IMG}/m_4011231_se_12_060_20180909.tif", "sha256": "c9" * 32}],
        }
        up["records"]["sources"] = [
            *up["records"]["sources"],
            {
                "id": IMG,
                "role": "imagery",
                "spdx": "LicenseRef-USGov-PD",
                "licence_class": "public-domain",
                "redistribution": "redistributable",
                "attribution": "Imagery: U.S. Department of Agriculture, Farm Service Agency, National Agriculture Imagery Program (NAIP), 2018.",
                "project": "NAIP",
                "epoch": 2018,
                "status": "used",
            },
        ]
    return up


def _compose(base: Path, **kw):
    up = _upstream(base, **kw)
    build = compose.compose_scene(_spec(), up, base / "scene")
    return build, base / "scene"


def _open(folder: Path):
    from pxr import Usd

    return Usd.Stage.Open(str(folder / "root.usda"))


def _terrain_meshes(stage, lod: str) -> list:
    from pxr import UsdGeom

    stage.GetPrimAtPath("/World").GetVariantSet("lod").SetVariantSelection(lod)
    return [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh) and "/Terrain/" in str(p.GetPath())]


def _source_of(stage, shader_path: str, input_name: str):
    from pxr import UsdShade

    source = UsdShade.Shader(stage.GetPrimAtPath(shader_path)).GetInput(input_name).GetConnectedSource()
    assert source, f"{shader_path}.{input_name} is not connected"
    return source[0].GetPrim()


@pytest.fixture(scope="module")
def ortho(tmp_path_factory: pytest.TempPathFactory):
    base = tmp_path_factory.mktemp("ortho")
    build, folder = _compose(base)
    return build, folder, _open(folder)


@pytest.mark.req("FR-004-49")
def test_rock_repeat_is_a_world_scale_between_4_and_16_metres() -> None:
    assert 4.0 <= assets.ROCK_REPEAT_M <= 16.0 and assets.ST_PERIOD_M == 50.0


@pytest.mark.req("FR-004-49")
def test_st_ortho_maps_the_grid_extent_to_the_unit_square() -> None:
    grid = grid_mod.Grid(np.zeros((400, 400)), dk.X_MIN, dk.Y_MAX, dk.CELL)
    xy = np.array([[-200.0, -200.0], [200.0, 200.0], [-200.0, 200.0], [200.0, -200.0], [20.0, 10.0]])
    got = look.ortho_st(xy, grid)
    assert got.dtype == np.float32 and got.shape == (5, 2)
    expected = np.array([[0, 0], [1, 1], [0, 1], [1, 0], [0.55, 0.525]])  # (x + 200) / 400, (y + 200) / 400
    assert np.abs(got - expected).max() < 1e-6
    assert np.abs(got[1] * 400 - 400).max() <= 1.0  # the image pixel of the north-east corner is within one cell


@pytest.mark.req("FR-004-49")
def test_every_tile_mesh_of_every_lod_carries_st_ortho(ortho) -> None:
    from pxr import UsdGeom

    _, _, stage = ortho
    for lod in ("lod0", "lod1", "lod2"):
        meshes = _terrain_meshes(stage, lod)
        assert len(meshes) == 2
        for prim in meshes:
            primvar = UsdGeom.PrimvarsAPI(prim).GetPrimvar("st_ortho")
            assert primvar and str(primvar.GetTypeName()) == "texCoord2f[]" and primvar.GetInterpolation() == "vertex", prim.GetPath()
            points = np.array(UsdGeom.Mesh(prim).GetPointsAttr().Get(), dtype=np.float64)
            st = np.array(primvar.Get(), dtype=np.float64)
            assert st.shape == (len(points), 2)
            assert np.abs(st[:, 0] - (points[:, 0] + 200.0) / 400.0).max() < 1e-5
            assert np.abs(st[:, 1] - (points[:, 1] + 200.0) / 400.0).max() < 1e-5
            assert UsdGeom.PrimvarsAPI(prim).GetPrimvar("st")  # the rock coordinates stay (FR-004-45)


@pytest.mark.req("FR-004-49")
def test_terrain_ortho_reads_the_orthophoto_through_st_ortho_and_the_rock_normal_through_st(ortho) -> None:
    from pxr import UsdShade

    _, folder, stage = ortho
    base = "/World/Materials/terrain_ortho"
    surface = UsdShade.Shader(stage.GetPrimAtPath(f"{base}/Surface"))
    assert surface.GetShaderId() == "UsdPreviewSurface"
    diffuse = _source_of(stage, f"{base}/Surface", "diffuseColor")
    diffuse_tex = UsdShade.Shader(diffuse)
    assert diffuse_tex.GetShaderId() == "UsdUVTexture"
    assert diffuse_tex.GetInput("file").Get().path == "terrain/albedo/ortho.jpg"
    assert (folder / "terrain" / "albedo" / "ortho.jpg").is_file()
    reader = _source_of(stage, str(diffuse.GetPath()), "st")
    reader_attr = reader.GetAttribute("inputs:varname")
    assert reader.GetAttribute("info:id").Get() == "UsdPrimvarReader_float2"
    assert str(reader_attr.GetTypeName()) == "string" and reader_attr.Get() == "st_ortho"
    normal_tex = _source_of(stage, f"{base}/Surface", "normal")
    shader = UsdShade.Shader(normal_tex)
    assert shader.GetShaderId() == "UsdUVTexture"
    assert shader.GetInput("file").Get().path == "assets/textures/bench_rock_normal.jpg"
    assert (folder / "assets" / "textures" / "bench_rock_normal.jpg").is_file()
    assert shader.GetInput("wrapS").Get() == "repeat" and shader.GetInput("wrapT").Get() == "repeat"
    assert shader.GetInput("sourceColorSpace").Get() == "raw"
    assert tuple(shader.GetInput("scale").Get()) == (2.0, 2.0, 2.0, 1.0) and tuple(shader.GetInput("bias").Get()) == (-1.0, -1.0, -1.0, 0.0)
    transform = _source_of(stage, str(normal_tex.GetPath()), "st")
    assert transform.GetAttribute("info:id").Get() == "UsdTransform2d"
    scale = tuple(UsdShade.Shader(transform).GetInput("scale").Get())
    assert scale == pytest.approx((assets.ST_PERIOD_M / assets.ROCK_REPEAT_M,) * 2)
    st_reader = _source_of(stage, str(transform.GetPath()), "in")
    assert st_reader.GetAttribute("inputs:varname").Get() == "st"
    assert UsdShade.Material(stage.GetPrimAtPath(base)).GetSurfaceOutput().HasConnectedSource()


@pytest.mark.req("FR-004-49")
def test_terrain_is_bound_to_terrain_ortho_in_place_of_bench_rock(ortho) -> None:
    from pxr import UsdShade

    _, _, stage = ortho
    for lod in ("lod0", "lod1", "lod2"):
        for prim in _terrain_meshes(stage, lod):
            bound = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
            assert str(bound.GetPath()) == "/World/Materials/terrain_ortho", prim.GetPath()
    road = stage.GetPrimAtPath("/World/Design/HaulRoads/Road_00")
    assert str(UsdShade.MaterialBindingAPI(road).ComputeBoundMaterial()[0].GetPath()) == "/World/Materials/gravel_road"


@pytest.mark.req("FR-004-49")
def test_the_manifest_with_the_imagery_source_and_albedo_records_is_valid(ortho) -> None:
    build, _, _ = ortho
    assert kit.schema_errors("scene-manifest.schema.json", build.manifest) == []
    assert any(s["role"] == "imagery" for s in build.manifest["sources"])
    assert build.manifest["terrain"]["albedo"]["images"][0]["path"] == "terrain/albedo/ortho.jpg"


@pytest.mark.req("FR-004-49")
def test_without_the_orthophoto_bench_rock_stays_bound_and_no_st_ortho_is_authored(tmp_path: Path) -> None:
    from pxr import UsdGeom, UsdShade

    _, folder = _compose(tmp_path, ortho=False)
    stage = _open(folder)
    assert not stage.GetPrimAtPath("/World/Materials/terrain_ortho")
    for prim in _terrain_meshes(stage, "lod0"):
        assert str(UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0].GetPath()) == "/World/Materials/bench_rock"
        assert not UsdGeom.PrimvarsAPI(prim).GetPrimvar("st_ortho")


@pytest.mark.req("FR-004-49")
def test_the_orthophoto_without_a_rock_normal_map_still_binds_terrain_ortho_with_no_normal(tmp_path: Path) -> None:
    from pxr import UsdShade

    _, folder = _compose(tmp_path, normal=False)
    stage = _open(folder)
    surface = UsdShade.Shader(stage.GetPrimAtPath("/World/Materials/terrain_ortho/Surface"))
    assert surface.GetInput("diffuseColor").HasConnectedSource() and not surface.GetInput("normal").HasConnectedSource()


@pytest.mark.req("FR-004-49")
def test_composing_twice_gives_identical_layers(tmp_path: Path) -> None:
    _, one = _compose(tmp_path / "one")
    _, two = _compose(tmp_path / "two")
    for rel in ("layers/terrain.usdc", "root.usda", "terrain/albedo/ortho.jpg"):
        assert kit.sha256_file(one / rel) == kit.sha256_file(two / rel), rel


@pytest.mark.req("FR-004-49")
def test_a_per_tile_orthophoto_maps_each_tile_window_to_its_own_image(tmp_path: Path) -> None:
    """One image per LOD-0 tile (FR-004-48 for a larger extent): `st_ortho` maps the tile's window to [0, 1].

    The fixture's tile prims are named `Tile_<lod>_<level>_<x>_<y>` with level 0, x in {0, 1} and y 0. By the layout of the
    terrain stage (stride 256, 257 samples) tile x starts at grid column 256 x and tile y at row 256 (ny - 1 - y), with ny = 2
    for this 400 x 400 grid, and its image holds min(257, cols - c0) x min(257, rows - r0) pixels.
    """
    from pxr import UsdGeom, UsdShade

    up = _upstream(tmp_path)
    folder = tmp_path / "up" / "records" / "terrain" / "albedo"
    del up["files"]["terrain/albedo/ortho.jpg"]
    names = ["0-0-0-0.jpg", "0-0-1-0.jpg"]
    for name in names:
        up["files"][f"terrain/albedo/{name}"] = _jpeg(folder / name)
    up["records"]["terrain"]["albedo"]["images"] = [
        {"path": f"terrain/albedo/{n}", "sha256": kit.sha256_file(folder / n)} for n in names
    ]
    build = compose.compose_scene(_spec(), up, tmp_path / "scene")
    assert kit.schema_errors("scene-manifest.schema.json", build.manifest) == []
    stage = _open(tmp_path / "scene")
    for lod in ("lod0", "lod1", "lod2"):
        for prim in _terrain_meshes(stage, lod):
            tx = int(str(prim.GetPath()).rsplit("_", 2)[1])
            bound = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
            assert str(bound.GetPath()) == f"/World/Materials/terrain_ortho_{tx}_0", prim.GetPath()
            texture = UsdShade.Shader(_source_of(stage, f"{bound.GetPath()}/Surface", "diffuseColor"))
            assert texture.GetInput("file").Get().path == f"terrain/albedo/0-0-{tx}-0.jpg"
            points = np.array(UsdGeom.Mesh(prim).GetPointsAttr().Get(), dtype=np.float64)
            st = np.array(UsdGeom.PrimvarsAPI(prim).GetPrimvar("st_ortho").Get(), dtype=np.float64)
            c0, r0 = 256 * tx, 256  # ny = 2, ty = 0
            width, height = min(257, 400 - c0), min(257, 400 - r0)
            x_left, y_bottom = dk.X_MIN + c0, dk.Y_MAX - (r0 + height)
            assert np.abs(st[:, 0] - (points[:, 0] - x_left) / width).max() < 1e-5
            assert np.abs(st[:, 1] - (points[:, 1] - y_bottom) / height).max() < 1e-5
    assert not stage.GetPrimAtPath("/World/Materials/terrain_ortho")


# --------------------------------------------------------------------------------------------------------------
# st30_assets: the arid rock set carries a normal map and a world-scale repeat
# --------------------------------------------------------------------------------------------------------------
def _rock_spec(tmp: Path):
    spec = kit.machine_spec(("haul_truck",))
    spec["materials"] = [
        {"id": "gravel-road", "source": "polyhaven", "spdx": "CC0-1.0"},
        {"id": "bench-rock", "source": "polyhaven", "spdx": "CC0-1.0"},
    ]
    tex = {
        "gravel-road": kit.tiny_png(tmp / "gravel.png", (90, 90, 80)),
        "bench-rock": kit.tiny_png(tmp / "rock.png", (150, 130, 110)),
        "bench-rock-normal": kit.tiny_png(tmp / "rock_normal.png", (128, 128, 255)),
    }
    return spec, tex


@pytest.mark.req("FR-004-49")
def test_the_rock_material_gets_a_normal_texture_and_a_world_scale_repeat(tmp_path: Path) -> None:
    from pxr import Usd, UsdShade

    spec, tex = _rock_spec(tmp_path)
    out = tmp_path / "out"
    build = assets.build_assets(spec, out, textures=tex)
    assert [t["id"] for t in build.textures] == ["gravel-road", "bench-rock", "bench-rock-normal"]
    normal = build.textures[2]
    assert normal == {"id": "bench-rock-normal", "source": "polyhaven", "spdx": "CC0-1.0", "sha256": kit.sha256_file(tex["bench-rock-normal"])}
    assert kit.sha256_file(out / "assets" / "textures" / "bench_rock_normal.png") == normal["sha256"]
    stage = Usd.Stage.Open(str(build.materials_layer))
    base = "/Materials/bench_rock"
    surface = UsdShade.Shader(stage.GetPrimAtPath(f"{base}/Surface"))
    assert surface.GetInput("normal").GetConnectedSource()[0].GetPrim().GetPath() == stage.GetPrimAtPath(f"{base}/NormalTexture").GetPath()
    ntex = UsdShade.Shader(stage.GetPrimAtPath(f"{base}/NormalTexture"))
    assert ntex.GetShaderId() == "UsdUVTexture" and ntex.GetInput("file").Get().path == "textures/bench_rock_normal.png"
    assert ntex.GetInput("sourceColorSpace").Get() == "raw"
    assert tuple(ntex.GetInput("scale").Get()) == (2.0, 2.0, 2.0, 1.0) and tuple(ntex.GetInput("bias").Get()) == (-1.0, -1.0, -1.0, 0.0)
    repeat = UsdShade.Shader(stage.GetPrimAtPath(f"{base}/Repeat"))
    assert repeat.GetShaderId() == "UsdTransform2d"
    assert tuple(repeat.GetInput("scale").Get()) == pytest.approx((assets.ST_PERIOD_M / assets.ROCK_REPEAT_M,) * 2)
    assert repeat.GetInput("in").GetConnectedSource()[0].GetPrim().GetPath() == stage.GetPrimAtPath(f"{base}/UV").GetPath()
    for name in ("Texture", "NormalTexture"):
        src = UsdShade.Shader(stage.GetPrimAtPath(f"{base}/{name}")).GetInput("st").GetConnectedSource()[0].GetPrim()
        assert str(src.GetPath()) == f"{base}/Repeat", name
    gravel = UsdShade.Shader(stage.GetPrimAtPath("/Materials/gravel_road/Texture")).GetInput("st").GetConnectedSource()[0].GetPrim()
    assert str(gravel.GetPath()) == "/Materials/gravel_road/UV"  # the road keeps its own coordinates
    assert not stage.GetPrimAtPath("/Materials/gravel_road/NormalTexture")


@pytest.mark.req("FR-004-49")
def test_a_scene_without_a_rock_normal_input_has_the_materials_layer_as_before(tmp_path: Path) -> None:
    from pxr import Usd

    spec, tex = _rock_spec(tmp_path)
    del tex["bench-rock-normal"]
    build = assets.build_assets(spec, tmp_path / "out", textures=tex)
    assert [t["id"] for t in build.textures] == ["gravel-road", "bench-rock"]
    stage = Usd.Stage.Open(str(build.materials_layer))
    assert not stage.GetPrimAtPath("/Materials/bench_rock/NormalTexture") and not stage.GetPrimAtPath("/Materials/bench_rock/Repeat")

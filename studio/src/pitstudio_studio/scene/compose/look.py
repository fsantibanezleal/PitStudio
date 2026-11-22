"""The look of the composed scene: terrain normals and texture coordinates from the grid, rock and road materials.

`restyle_terrain` rewrites the tile meshes of the composed terrain layer in place. The terrain stage computes
each tile's vertex normals from the tile's own faces, so the border vertices (and the skirt faces under them) are
shaded differently from the neighbouring tile's and square seams show; here every vertex, skirt included, takes the
central difference gradient of the grid at its x, y, which is the same for both tiles. Points are never touched.
`author_looks` and `bind_materials` reference the material layer under `/World/Materials` in the root stage and bind it;
the material layer itself is copied unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_studio.scene.assets import ROCK_REPEAT_M, ST_PERIOD_M
from pitstudio_studio.scene.compose.grid import Grid
from pitstudio_studio.scene.terrain import imagery

TEXTURE_PERIOD_M = ST_PERIOD_M  # one texture repeat covers this many metres of terrain
FALLBACK_ALBEDO = (0.42, 0.38, 0.33)  # constant diffuse colour of a material whose texture file is missing
MATERIALS_PATH = "/World/Materials"
ORTHO_MATERIAL = "terrain_ortho"
ORTHO_ROUGHNESS = 0.85  # dry rock: matte
_TILE_PRIM = re.compile(r"^Tile_\d+_\d+_(\d+)_(\d+)$")  # Tile_<lod>_<level>_<x>_<y>
_TILE_IMAGE = re.compile(r"^0-\d+-(\d+)-(\d+)\.jpg$")  # <lod>-<level>-<x>-<y>.jpg


@dataclass(frozen=True)
class Ortho:
    """The orthophoto of a composed scene folder: one image for the whole grid, or one image per LOD-0 tile."""

    single: str | None = None
    tiles: dict[tuple[int, int], str] = field(default_factory=dict)  # (x, y) -> scene-relative image path


def find_ortho(scene: Path) -> Ortho | None:
    """The orthophoto images under `terrain/albedo/` of the scene folder, or None when there are none."""
    folder = Path(scene) / imagery.ALBEDO_DIR
    if not folder.is_dir():
        return None
    names = sorted(p.name for p in folder.glob("*.jpg"))
    if names == ["ortho.jpg"]:
        return Ortho(single=f"{imagery.ALBEDO_DIR}/ortho.jpg")
    found = {
        (int(m.group(1)), int(m.group(2))): f"{imagery.ALBEDO_DIR}/{n}" for n in names if (m := _TILE_IMAGE.match(n))
    }
    return Ortho(tiles=found) if found else None


def ortho_st(xy: np.ndarray, grid: Grid, window: tuple[float, float, float, float] | None = None) -> np.ndarray:
    """`st_ortho` of points `xy` (n, 2): the grid extent, or `window` (x_left, y_bottom, width_m, height_m), to [0, 1].

    v is up (the bottom row of the image is v = 0), the convention of `UsdUVTexture`.
    """
    rows, cols = grid.elevation.shape
    x_left, y_bottom, width, height = window or (
        grid.x_min,
        grid.y_max - rows * grid.cell,
        cols * grid.cell,
        rows * grid.cell,
    )
    xy = np.asarray(xy, dtype=np.float64)
    return np.stack([(xy[:, 0] - x_left) / width, (xy[:, 1] - y_bottom) / height], axis=-1).astype(np.float32)


def tile_extent(tx: int, ty: int, grid: Grid) -> tuple[float, float, float, float]:
    """The ground window `(x_left, y_bottom, width_m, height_m)` of the image of LOD-0 tile `(tx, ty)`."""
    rows, cols = grid.elevation.shape
    r0, c0, height, width = imagery.tile_window(tx, ty, rows, cols)
    return (
        grid.x_min + c0 * grid.cell,
        grid.y_max - (r0 + height) * grid.cell,
        width * grid.cell,
        height * grid.cell,
    )


def _ortho_material_name(tx: int, ty: int) -> str:
    return f"{ORTHO_MATERIAL}_{tx}_{ty}"


def restyle_terrain(layer_path: Path, grid: Grid, ortho: Ortho | None = None) -> int:
    """Author grid normals and planar `primvars:st` on every tile mesh of every `lod` variant; returns the count.

    With an `ortho` (FR-004-49) every mesh also gets `primvars:st_ortho`, the grid extent (or, with one image per
    tile, the window of that tile's image) mapped to [0, 1]; with one image per tile each mesh is bound to the material
    of its tile.
    """
    from pxr import Sdf, Vt

    layer = Sdf.Layer.FindOrOpen(str(layer_path))
    meshes: list[Any] = []

    def visit(path: Any) -> None:
        if path.IsPrimPath():
            spec = layer.GetPrimAtPath(path)
            if spec is not None and spec.typeName == "Mesh":
                meshes.append(path)

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    for path in meshes:
        spec = layer.GetPrimAtPath(path)
        points = np.array(layer.GetAttributeAtPath(path.AppendProperty("points")).default, dtype=np.float64)
        normals = grid.normals(points[:, 0], points[:, 1]).astype(np.float32)
        layer.GetAttributeAtPath(path.AppendProperty("normals")).default = Vt.Vec3fArray.FromNumpy(normals)
        st = layer.GetAttributeAtPath(path.AppendProperty("primvars:st"))
        if st is None:
            st = Sdf.AttributeSpec(spec, "primvars:st", Sdf.ValueTypeNames.TexCoord2fArray)
        st.default = Vt.Vec2fArray.FromNumpy((points[:, :2] / TEXTURE_PERIOD_M).astype(np.float32))
        st.SetInfo("interpolation", "vertex")
        if ortho is not None:
            _author_st_ortho(layer, spec, path, points, grid, ortho)
    layer.Save()
    return len(meshes)


def _author_st_ortho(layer: Any, spec: Any, path: Any, points: np.ndarray, grid: Grid, ortho: Ortho) -> None:
    from pxr import Sdf, Vt

    window = None
    tile = (0, 0)
    if ortho.single is None:
        match = _TILE_PRIM.match(path.name)
        if match is None or (int(match.group(1)), int(match.group(2))) not in ortho.tiles:
            raise ValueError(f"{path}: no orthophoto image for this tile")
        tile = (int(match.group(1)), int(match.group(2)))
        window = tile_extent(*tile, grid)
    primvar = layer.GetAttributeAtPath(path.AppendProperty("primvars:st_ortho"))
    if primvar is None:
        primvar = Sdf.AttributeSpec(spec, "primvars:st_ortho", Sdf.ValueTypeNames.TexCoord2fArray)
    primvar.default = Vt.Vec2fArray.FromNumpy(ortho_st(points[:, :2], grid, window))
    primvar.SetInfo("interpolation", "vertex")
    if window is not None:  # one image per tile: the mesh is bound to the material of its tile's image
        schemas = spec.GetInfo("apiSchemas") if spec.HasInfo("apiSchemas") else Sdf.TokenListOp()
        items = list(schemas.prependedItems)
        if "MaterialBindingAPI" not in items:
            schemas.prependedItems = [*items, "MaterialBindingAPI"]
            spec.SetInfo("apiSchemas", schemas)
        binding = layer.GetRelationshipAtPath(path.AppendProperty("material:binding"))
        if binding is None:
            binding = Sdf.RelationshipSpec(spec, "material:binding")
        binding.targetPathList.explicitItems = [Sdf.Path(f"{MATERIALS_PATH}/{_ortho_material_name(*tile)}")]


def author_looks(stage: Any, scene: Path) -> list[str]:
    """Reference the materials under `/World/Materials` and make their textures repeat.

    Returns the names of the texture files missing from the scene folder (those materials get a constant colour).
    Call before the root stage defines its other `/World` children: prims are authored in sorted name order.
    """
    from pxr import Sdf, UsdShade

    if not (Path(scene) / "assets" / "materials.usda").is_file():
        return []
    _bind(stage, "/World/Design/HaulRoads", "gravel_road")  # first: /World/Design sorts before /World/Materials
    holder = stage.DefinePrim(MATERIALS_PATH, "Scope")
    holder.GetReferences().AddReference("assets/materials.usda", "/Materials")
    missing: list[str] = []
    for material in sorted(holder.GetChildren(), key=lambda p: p.GetName()):
        shaders = {p.GetName(): UsdShade.Shader(p) for p in material.GetChildren()}
        kinds = {name: s.GetIdAttr().Get() for name, s in shaders.items()}
        for name in sorted(shaders):  # sorted name order: Surface, Texture, UV
            shader = shaders[name]
            if kinds[name] == "UsdUVTexture":
                asset = shader.GetInput("file").Get()
                file = asset.path if asset is not None else ""
                if file and not (Path(scene) / "assets" / file).is_file():
                    missing.append(Path(file).name)
            if name == "Surface":
                continue  # authored below once the texture of this material is known
        absent = any(Path(m).stem == material.GetName() for m in missing)
        for name in sorted(shaders):
            prim = stage.OverridePrim(shaders[name].GetPath()) if kinds[name] != "UsdPreviewSurface" or absent else None
            if prim is None:
                continue
            shader = UsdShade.Shader(prim)
            if kinds[name] == "UsdPreviewSurface":
                colour = shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f)
                colour.GetAttr().SetConnections([])
                colour.Set(FALLBACK_ALBEDO)
            elif kinds[name] == "UsdUVTexture":
                for wrap in ("wrapS", "wrapT"):
                    shader.CreateInput(wrap, Sdf.ValueTypeNames.Token).Set("repeat")

    return missing


def copy_asset(source: Path, target: Path) -> None:
    """Copy an asset layer; a primvar reader's `varname` authored as a token is written as a string.

    `UsdPrimvarReader_float2.inputs:varname` is a string in the shader schema; the assets stage authors a token and the
    validators (`UsdShadeShaderSdrCompliance`, `UsdValidationAttributeTypeMismatchChecker`) reject either that or a
    stronger override of its type, so the copy carries the schema type. Nothing else in the layer changes.
    """
    data = Path(source).read_bytes()
    Path(target).write_bytes(data.replace(b"token inputs:varname", b"string inputs:varname"))


def _bind(stage: Any, target: str, material: str) -> None:
    from pxr import Sdf, UsdShade

    prim = stage.OverridePrim(target)
    UsdShade.MaterialBindingAPI.Apply(prim)
    prim.CreateRelationship("material:binding").SetTargets([Sdf.Path(f"{MATERIALS_PATH}/{material}")])


def _normal_map(scene: Path) -> str | None:
    """The scene-relative path of the rock normal map `assets/textures/bench_rock_normal.<ext>`, if there is one."""
    found = sorted((Path(scene) / "assets" / "textures").glob("bench_rock_normal.*"))
    return f"assets/textures/{found[0].name}" if found else None


def _reader(stage: Any, path: str, varname: str) -> Any:
    from pxr import Sdf, UsdShade

    reader = UsdShade.Shader.Define(stage, path)
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.String).Set(varname)
    reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    return reader


def _ortho_material(stage: Any, name: str, image: str, normal: str | None) -> None:
    """`terrain_ortho`: diffuse colour from the orthophoto (`st_ortho`), normal from the rock normal map (`st`).

    The shaders are authored in sorted name order (the root layer lists every prim's children sorted).
    """
    from pxr import Sdf, UsdShade

    base = f"{MATERIALS_PATH}/{name}"
    material = UsdShade.Material.Define(stage, base)
    relief = None
    if normal is not None:
        relief = UsdShade.Shader.Define(stage, f"{base}/NormalTexture")
        relief.CreateIdAttr("UsdUVTexture")
        relief.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(normal))
        relief.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
        relief.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set((2.0, 2.0, 2.0, 1.0))
        relief.CreateInput("bias", Sdf.ValueTypeNames.Float4).Set((-1.0, -1.0, -1.0, 0.0))
        relief.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
        relief.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
        relief.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    ortho_reader = _reader(stage, f"{base}/OrthoST", "st_ortho")
    texture = UsdShade.Shader.Define(stage, f"{base}/OrthoTexture")
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(image))
    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(ortho_reader.GetOutput("result"))
    texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
    texture.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
    texture.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
    texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    if relief is not None:
        repeat = UsdShade.Shader.Define(stage, f"{base}/Repeat")
        repeat.CreateIdAttr("UsdTransform2d")
        factor = ST_PERIOD_M / ROCK_REPEAT_M
        repeat.CreateInput("scale", Sdf.ValueTypeNames.Float2).Set((factor, factor))
        repeat.CreateOutput("result", Sdf.ValueTypeNames.Float2)
        rock_reader = _reader(stage, f"{base}/ST", "st")
        repeat.CreateInput("in", Sdf.ValueTypeNames.Float2).ConnectToSource(rock_reader.GetOutput("result"))
        relief.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(repeat.GetOutput("result"))
    surface = UsdShade.Shader.Define(stage, f"{base}/Surface")
    surface.CreateIdAttr("UsdPreviewSurface")
    surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.GetOutput("rgb"))
    surface.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(ORTHO_ROUGHNESS)
    surface.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    normal_input = surface.CreateInput("normal", Sdf.ValueTypeNames.Normal3f)
    if relief is not None:
        normal_input.ConnectToSource(relief.GetOutput("rgb"))
    else:  # no rock normal map in the scene: the surface keeps its own (tangent-space up) normal
        normal_input.Set((0.0, 0.0, 1.0))
    surface.CreateOutput("surface", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput().ConnectToSource(surface.GetOutput("surface"))


def author_ortho(stage: Any, scene: Path, ortho: Ortho) -> None:
    """Author the material `terrain_ortho` (or one per tile) under `/World/Materials` (FR-004-49).

    Call after `author_looks` and before the root stage defines its other `/World` children.
    """
    stage.DefinePrim(MATERIALS_PATH, "Scope")
    normal = _normal_map(scene)
    if ortho.single is not None:
        _ortho_material(stage, ORTHO_MATERIAL, ortho.single, normal)
        return
    for (tx, ty), image in sorted(ortho.tiles.items(), key=lambda kv: _ortho_material_name(*kv[0])):
        _ortho_material(stage, _ortho_material_name(tx, ty), image, normal)


def bind_materials(stage: Any, ortho: Ortho | None = None, *, rock: bool = True) -> None:
    """Bind `/World/Terrain` to `terrain_ortho` when there is one image for the grid, else to the rock `bench_rock`.

    With one image per tile the tile meshes carry their own bindings (see `restyle_terrain`) and the terrain keeps the
    rock as its fallback. Call after `PhysicsScene` is defined: prims are authored in sorted order.
    """
    if ortho is not None and ortho.single is not None:
        _bind(stage, "/World/Terrain", ORTHO_MATERIAL)
    elif rock:
        _bind(stage, "/World/Terrain", "bench_rock")

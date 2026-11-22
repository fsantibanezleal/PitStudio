"""The look of the composed scene: terrain normals and texture coordinates from the grid, rock and road materials.

`restyle_terrain` rewrites the tile meshes of the composed terrain layer in place. The terrain stage computes
each tile's vertex normals from the tile's own faces, so the border vertices (and the skirt faces under them) are
shaded differently from the neighbouring tile's and square seams show; here every vertex, skirt included, takes the
central difference gradient of the grid at its x, y, which is the same for both tiles. Points are never touched.
`author_looks` and `bind_materials` reference the material layer under `/World/Materials` in the root stage and bind it;
the material layer itself is copied unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_studio.scene.compose.grid import Grid

TEXTURE_PERIOD_M = 50.0  # one texture repeat covers this many metres of terrain
FALLBACK_ALBEDO = (0.42, 0.38, 0.33)  # constant diffuse colour of a material whose texture file is missing
MATERIALS_PATH = "/World/Materials"
BINDINGS = (("/World/Terrain", "bench_rock"), ("/World/Design/HaulRoads", "gravel_road"))


def restyle_terrain(layer_path: Path, grid: Grid) -> int:
    """Author grid normals and planar `primvars:st` on every tile mesh of every `lod` variant; returns the count."""
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
    layer.Save()
    return len(meshes)


def author_looks(stage: Any, scene: Path) -> list[str]:
    """Reference the materials under `/World/Materials` and make their textures repeat.

    Returns the names of the texture files missing from the scene folder (those materials get a constant colour).
    Call before the root stage defines its other `/World` children: prims are authored in sorted name order.
    """
    from pxr import Sdf, UsdShade

    if not (Path(scene) / "assets" / "materials.usda").is_file():
        return []
    stage.OverridePrim("/World/Design")
    stage.OverridePrim("/World/Design/HaulRoads")
    holder = stage.DefinePrim(MATERIALS_PATH, "Scope")
    holder.GetReferences().AddReference("assets/materials.usda", "/Materials")
    missing: list[str] = []
    for material in holder.GetChildren():
        for shader_prim in material.GetChildren():
            shader = UsdShade.Shader(shader_prim)
            if shader.GetIdAttr().Get() != "UsdUVTexture":
                continue
            texture = UsdShade.Shader(stage.OverridePrim(shader_prim.GetPath()))
            for wrap in ("wrapS", "wrapT"):
                texture.CreateInput(wrap, Sdf.ValueTypeNames.Token).Set("repeat")
            asset = shader.GetInput("file").Get()
            name = asset.path if asset is not None else ""
            if name and not (Path(scene) / "assets" / name).is_file():
                missing.append(Path(name).name)
                surface = UsdShade.Shader(stage.OverridePrim(material.GetPath().AppendChild("Surface")))
                colour = surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f)
                colour.GetAttr().SetConnections([])
                colour.Set(FALLBACK_ALBEDO)
    return missing


def bind_materials(stage: Any) -> None:
    """Bind `/World/Terrain` and `/World/Design/HaulRoads` to their materials (after `PhysicsScene` is defined)."""
    from pxr import UsdShade

    for target, name in BINDINGS:
        material = UsdShade.Material(stage.GetPrimAtPath(f"{MATERIALS_PATH}/{name}"))
        if material:
            UsdShade.MaterialBindingAPI.Apply(stage.OverridePrim(target)).Bind(material)

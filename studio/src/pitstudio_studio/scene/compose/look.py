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
            elif kinds[name] == "UsdPrimvarReader_float2":  # the Sdr type of `varname` is string
                value = str(shaders[name].GetInput("varname").Get())
                spec = Sdf.CreatePrimInLayer(stage.GetEditTarget().GetLayer(), prim.GetPath())
                Sdf.AttributeSpec(spec, "inputs:varname", Sdf.ValueTypeNames.String).default = value
    return missing


def bind_materials(stage: Any) -> None:
    """Bind `/World/Terrain` and `/World/Design/HaulRoads` to their materials (after `PhysicsScene` is defined)."""
    from pxr import UsdShade

    for target, name in BINDINGS:
        material = UsdShade.Material(stage.GetPrimAtPath(f"{MATERIALS_PATH}/{name}"))
        if material:
            UsdShade.MaterialBindingAPI.Apply(stage.OverridePrim(target)).Bind(material)

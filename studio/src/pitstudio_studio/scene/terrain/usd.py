"""The terrain USD layer: one `lod` variant per LOD holding that LOD's tile meshes (FR-004-08)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from pitstudio_studio.scene.terrain.tiles import TileSet


def write_terrain_layer(
    path: Path | str, tileset: TileSet, *, source_id: str, project: str, epoch: int, attribution: str
) -> Path:
    """Write `terrain.usdc`: units and up axis authored explicitly, default prim `World`, `/World/Terrain` with the
    variant
    set `lod` (`lod0`, `lod1`, ...) whose variants hold one `Mesh` per tile at the tile's index path.

    Every mesh carries the `SemanticsLabelsAPI` class label `terrain`; the provenance attributes `pitstudio:source_id`,
    `pitstudio:project`, `pitstudio:epoch` and `pitstudio:attribution` sit on `/World/Terrain`.
    """
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdSemantics, Vt

    path = Path(path)
    if path.exists():
        path.unlink()
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    terrain = UsdGeom.Xform.Define(stage, "/World/Terrain")
    prim = terrain.GetPrim()
    prim.CreateAttribute("pitstudio:source_id", Sdf.ValueTypeNames.String).Set(source_id)
    prim.CreateAttribute("pitstudio:project", Sdf.ValueTypeNames.String).Set(project)
    prim.CreateAttribute("pitstudio:epoch", Sdf.ValueTypeNames.Int).Set(int(epoch))
    prim.CreateAttribute("pitstudio:attribution", Sdf.ValueTypeNames.String).Set(attribution)
    vset = prim.GetVariantSets().AddVariantSet("lod")
    lods = sorted({t.lod for t in tileset.tiles})
    for lod in lods:
        vset.AddVariant(f"lod{lod}")
    for lod in lods:
        vset.SetVariantSelection(f"lod{lod}")
        with vset.GetVariantEditContext():
            UsdGeom.Xform.Define(stage, f"/World/Terrain/Lod{lod}")
            for tile in (t for t in tileset.tiles if t.lod == lod):
                mesh = UsdGeom.Mesh.Define(stage, tile.prim)
                positions = np.asarray(tile.positions, dtype=np.float32)
                indices = np.asarray(tile.indices, dtype=np.int64).ravel()
                mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(positions))
                mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(indices) // 3, 3, dtype=np.int32)))
                mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(indices.astype(np.int32)))
                mesh.CreateSubdivisionSchemeAttr("none")
                lo, hi = positions.min(axis=0), positions.max(axis=0)
                mesh.CreateExtentAttr([Gf.Vec3f(*map(float, lo)), Gf.Vec3f(*map(float, hi))])
                UsdSemantics.LabelsAPI.Apply(mesh.GetPrim(), "class").CreateLabelsAttr(["terrain"])
    if lods:
        vset.SetVariantSelection(f"lod{lods[0]}")
    stage.GetRootLayer().Save()
    return path

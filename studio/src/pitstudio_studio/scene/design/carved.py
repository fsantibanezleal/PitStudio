"""The carved surface of `st20_pit_design` (FR-004-50): the pit at its design as a terrain grid and a tiled USD layer.

Inside the pit outline the surface is the top of the design meshes (the design height of every cell, plus the windrow
height on windrow cells); outside it is the source terrain grid. The SDG renderer shows this surface in place of the
source terrain and the design surface meshes, and the SDG parameter table takes every height from the same grid, so
the camera, the objects and the rendered ground cannot disagree.

`carve` refuses to fill a gap: a cell inside the outline that no design mesh covers raises `design-hole`.
`write_carved_grid` writes the terrain-grid contract (the source's CRS, extent and cell size); `write_carved_layer`
writes the layer on the source tiling with the normals and texture coordinates of FR-004-45 and a `road` GeomSubset on
the faces whose centroid lies on a road, which the renderer binds to the gravel material.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_studio.scene import common
from pitstudio_studio.scene.common import SceneStageError

CARVED_GRID = "design/carved-grid.zarr"
CARVED_LAYER = "layers/design-carved.usdc"
ROOT_PRIM = "/World/Carved"
SOURCE_PRIM_ROOT = "/World/Terrain/"
ROAD_SUBSET = "road"
PROVENANCE = "design-code"
# FR-004-52: a windrow is a ridge with a 1 m crest and side slopes at the angle of repose of the heaped rock. The scene
# specification carries no material card with a repose angle, so the value is 37 degrees (decision of the main session,
# 2026-11-23; UNVERIFIED against a published figure: the MSHA training slides tie the base width of an earth berm to the
# angle of repose without a number (arlweb.msha.gov/training/surfhaul/slide37.htm). Height rule, 30 CFR 56.9300(b):
# at least mid-axle height of the largest vehicle (arlweb.msha.gov/stats/top20viols/tips/9300.htm).
WINDROW_REPOSE_DEG = 37.0
WINDROW_CREST_HALF_WIDTH_M = 0.5


def windrow_raise(
    lines: Sequence[Any],
    shape: tuple[int, int],
    x_min_m: float,
    y_max_m: float,
    cell_m: float,
    height_m: float,
    repose_deg: float = WINDROW_REPOSE_DEG,
    crest_half_width_m: float = WINDROW_CREST_HALF_WIDTH_M,
) -> np.ndarray:
    """The raise (m) of every cell above the design surface: a trapezoid section about each windrow line.

    The raise is the windrow height within `crest_half_width_m` of a line and falls with the tangent of the angle of
    repose beyond it, to zero; where two windrows overlap the higher raise stands (never the sum). Cell centres are at
    `x_min + (col + 0.5) * cell` and `y_max - (row + 0.5) * cell`.
    """
    import math

    import shapely
    from scipy import ndimage as ndi
    from scipy.spatial import cKDTree

    out = np.zeros(shape, dtype=np.float64)
    slope = math.tan(math.radians(repose_deg))
    reach = crest_half_width_m + height_m / slope
    samples = []
    for line in lines:
        distances = np.arange(0.0, line.length + cell_m / 4.0, cell_m / 2.0)
        samples.append(shapely.get_coordinates(shapely.line_interpolate_point(line, distances)))
    if not samples:
        return out
    xy = np.vstack(samples)
    col = np.clip(np.floor((xy[:, 0] - x_min_m) / cell_m).astype(np.int64), 0, shape[1] - 1)
    row = np.clip(np.floor((y_max_m - xy[:, 1]) / cell_m).astype(np.int64), 0, shape[0] - 1)
    near = np.zeros(shape, dtype=bool)
    near[row, col] = True
    near = ndi.binary_dilation(near, structure=np.ones((3, 3), dtype=bool), iterations=math.ceil(reach / cell_m) + 1)
    rr, cc = np.nonzero(near)
    centres = np.column_stack([x_min_m + (cc + 0.5) * cell_m, y_max_m - (rr + 0.5) * cell_m])
    distance, _ = cKDTree(xy).query(centres, distance_upper_bound=reach)
    raised = np.where(
        np.isfinite(distance),
        np.clip(height_m - np.maximum(distance - crest_half_width_m, 0.0) * slope, 0.0, height_m),
        0.0,
    )
    out[rr, cc] = raised
    return out


def carve(
    z_design: np.ndarray,
    windrow_mask: np.ndarray,
    windrow_height_m: float,
    terrain: np.ndarray,
    inside: np.ndarray,
    raise_m: np.ndarray | None = None,
) -> np.ndarray:
    """The carved surface (float32): the design surface plus the windrows inside the outline, the terrain outside it.

    With `raise_m` (FR-004-52, the ridge of `windrow_raise`) the raise replaces the mask times the height.

    Terrain nodata outside the outline stays nodata. A cell inside the outline whose design height is not finite is a
    design hole: `SceneStageError` with error class `design-hole`, nothing is filled.
    """
    z_design = np.asarray(z_design, dtype=np.float64)
    inside = np.asarray(inside, dtype=bool)
    hole = inside & ~np.isfinite(z_design)
    if hole.any():
        r, c = (int(v) for v in np.argwhere(hole)[0])
        raise SceneStageError(
            "design-hole",
            f"{int(hole.sum())} cell(s) inside the pit outline are covered by no design mesh (first at row {r}, "
            f"column {c})",
            cells=int(hole.sum()),
        )
    if raise_m is not None:
        raised = np.asarray(raise_m, dtype=np.float64)
    else:
        raised = np.where(np.asarray(windrow_mask, dtype=bool), float(windrow_height_m), 0.0)
    return np.where(inside, z_design + raised, np.asarray(terrain, dtype=np.float64)).astype(np.float32)


def outline_step(carved: np.ndarray, inside: np.ndarray) -> dict[str, Any]:
    """The height step across the pit outline: carved height of a cell inside minus that of a 4-neighbour outside it."""
    z = np.asarray(carved, dtype=np.float64)
    inside = np.asarray(inside, dtype=bool)
    steps: list[np.ndarray] = []
    for axis in (0, 1):
        for sign in (1, -1):
            a = inside
            b = np.roll(inside, sign, axis=axis)
            za = z
            zb = np.roll(z, sign, axis=axis)
            edge = np.zeros_like(inside)  # a roll wraps around the border: those pairs are not neighbours
            index = [slice(None)] * 2
            index[axis] = slice(0, 1) if sign == 1 else slice(-1, None)
            edge[tuple(index)] = True
            pair = a & ~b & ~edge & np.isfinite(za) & np.isfinite(zb)
            steps.append((za - zb)[pair])
    d = np.concatenate(steps)
    if d.size == 0:
        return {"pairs": 0, "median_abs_m": 0.0, "max_abs_m": 0.0, "mean_signed_m": 0.0}
    return {
        "pairs": int(d.size),
        "median_abs_m": float(np.median(np.abs(d))),
        "max_abs_m": float(np.abs(d).max()),
        "mean_signed_m": float(d.mean()),
    }


def array_sha256(elevation: np.ndarray) -> str:
    """SHA-256 of a grid array as the terrain-grid contract defines it: float32 little-endian, row 0 north."""
    return common.sha256_bytes(np.ascontiguousarray(elevation, dtype="<f4").tobytes())


def write_carved_grid(
    path: Path | str,
    carved: np.ndarray,
    source_attrs: Mapping[str, Any],
    source_valid: np.ndarray,
    source_fill: np.ndarray,
    inside: np.ndarray,
) -> dict[str, Any]:
    """Write the carved grid as a terrain-grid Zarr group with the source's CRS, extent and cell size; returns its
    attrs.

    Cells that the design replaced are valid and never filled holes; the digests, counts and ranges are recomputed.
    """
    from pitstudio_studio.scene.terrain import build as terrain_build

    attrs = copy.deepcopy(dict(source_attrs))
    carved = np.asarray(carved, dtype=np.float32)
    valid = np.isfinite(carved) & (np.asarray(source_valid, dtype=bool) | np.asarray(inside, dtype=bool))
    fill = np.asarray(source_fill, dtype=bool) & ~np.asarray(inside, dtype=bool)
    old = dict(source_attrs.get("counts", {}))
    total = int(carved.size)
    if int(old.get("valid_cells", 0)) + int(old.get("nodata_cells", 0)) >= total:
        aoi_cells = total  # the AOI is the whole grid: every cell that is not valid is nodata
        nodata = total - int(valid.sum())
    else:  # an AOI polygon inside the grid: the design only turns nodata cells into valid ones
        newly_valid = int((valid & ~np.asarray(source_valid, dtype=bool)).sum())
        nodata = max(int(old.get("nodata_cells", 0)) - newly_valid, 0)
        aoi_cells = int(valid.sum()) + nodata
    attrs["arrays"] = {
        "elevation": terrain_build._array_record(carved, "float32", "m"),
        "valid_mask": terrain_build._array_record(valid, "bool", None),
        "fill_mask": terrain_build._array_record(fill, "bool", None),
    }
    attrs["counts"] = {
        **old,
        "valid_cells": int(valid.sum()),
        "filled_cells": int(fill.sum()),
        "nodata_cells": nodata,
    }
    attrs["nodata_frac"] = nodata / aoi_cells if aoi_cells else 1.0
    z = carved[valid].astype(np.float64)
    z0 = float(source_attrs["origin"]["z0_m"])
    attrs["elevation_range_m"] = {"min": float(z.min()), "max": float(z.max())}
    attrs["source_elevation_range_m"] = {"min": float(z.min()) + z0, "max": float(z.max()) + z0}
    rows, cols = carved.shape
    grid = terrain_build.TerrainGrid(
        elevation=carved,
        valid_mask=valid,
        fill_mask=fill,
        cell_size_m=float(attrs["cell_size_m"]),
        x_min_m=float(attrs["x_min_m"]),
        y_max_m=float(attrs["y_max_m"]),
        rows=rows,
        cols=cols,
        crs=attrs["crs"],
        counts=attrs["counts"],
        nodata_frac=attrs["nodata_frac"],
        attrs=attrs,
        fixture=bool(attrs.get("fixture", False)),
        source_id=str(attrs["source_ids"][0]),
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    terrain_build.write_grid_zarr(grid, Path(path))
    return attrs


def _road_faces(
    positions: np.ndarray, triangles: np.ndarray, road: np.ndarray, x_min: float, y_max: float, cell: float
):
    centroid = positions[triangles.reshape(-1, 3)][:, :, :2].mean(axis=1)
    col = np.clip(np.floor((centroid[:, 0] - x_min) / cell).astype(np.int64), 0, road.shape[1] - 1)
    row = np.clip(np.floor((y_max - centroid[:, 1]) / cell).astype(np.int64), 0, road.shape[0] - 1)
    return np.nonzero(road[row, col])[0].astype(np.int32)


def write_carved_layer(
    path: Path | str,
    carved: np.ndarray,
    *,
    lods: Sequence[Mapping[str, Any]],
    x_min_m: float,
    y_max_m: float,
    cell_size_m: float,
    road_mask: np.ndarray,
) -> dict[str, Any]:
    """Write `design-carved.usdc`: `/World/Carved` with the variant set `lod`, one mesh per tile of the source tiling.

    The tiles are those of `terrain.tiles.build_tiles` on the carved grid (same ids, 257 x 257 samples, same LODs),
    named
    `/World/Carved/Lod<n>/Tile_<lod>_<level>_<x>_<y>`. Normals and `primvars:st` are authored by the same function the
    compose stage applies to the terrain (FR-004-45). Returns the tile count per LOD.
    """
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdSemantics, UsdShade, Vt

    from pitstudio_studio.scene.compose import look
    from pitstudio_studio.scene.compose.grid import Grid
    from pitstudio_studio.scene.normals import author_normals
    from pitstudio_studio.scene.terrain import tiles as tiles_mod

    path = Path(path)
    if path.exists():
        path.unlink()
    carved64 = np.asarray(carved, dtype=np.float64)
    tileset = tiles_mod.build_tiles(
        carved64, cell_size_m=cell_size_m, x_min_m=x_min_m, y_max_m=y_max_m, lods=[dict(lod) for lod in lods]
    )
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    root = UsdGeom.Xform.Define(stage, ROOT_PRIM).GetPrim()
    root.CreateAttribute("pitstudio:provenance", Sdf.ValueTypeNames.String).Set(PROVENANCE)
    vset = root.GetVariantSets().AddVariantSet("lod")
    lod_ids = sorted({t.lod for t in tileset.tiles})
    for lod in lod_ids:
        vset.AddVariant(f"lod{lod}")
    roads = 0
    for lod in lod_ids:
        vset.SetVariantSelection(f"lod{lod}")
        with vset.GetVariantEditContext():
            UsdGeom.Xform.Define(stage, f"{ROOT_PRIM}/Lod{lod}")
            for tile in (t for t in tileset.tiles if t.lod == lod):
                mesh = UsdGeom.Mesh.Define(stage, tile.prim.replace(SOURCE_PRIM_ROOT, ROOT_PRIM + "/", 1))
                positions = np.asarray(tile.positions, dtype=np.float32)
                indices = np.asarray(tile.indices, dtype=np.int64).ravel()
                mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(positions))
                mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(indices) // 3, 3, dtype=np.int32)))
                mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(indices.astype(np.int32)))
                mesh.CreateSubdivisionSchemeAttr("none")
                author_normals(mesh, positions, np.full(len(indices) // 3, 3), indices)
                lo, hi = positions.min(axis=0), positions.max(axis=0)
                mesh.CreateExtentAttr([Gf.Vec3f(*map(float, lo)), Gf.Vec3f(*map(float, hi))])
                UsdSemantics.LabelsAPI.Apply(mesh.GetPrim(), "class").CreateLabelsAttr(["terrain"])
                faces = _road_faces(positions, indices, road_mask, x_min_m, y_max_m, cell_size_m)
                if faces.size:
                    binding = UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim())
                    binding.CreateMaterialBindSubset(ROAD_SUBSET, Vt.IntArray.FromNumpy(faces), UsdGeom.Tokens.face)
                    roads += int(faces.size)
    if lod_ids:
        vset.SetVariantSelection(f"lod{lod_ids[0]}")
    stage.GetRootLayer().Save()
    del stage
    look.restyle_terrain(path, Grid(carved64, float(x_min_m), float(y_max_m), float(cell_size_m)))
    return {"tiles": {lod: sum(1 for t in tileset.tiles if t.lod == lod) for lod in lod_ids}, "road_faces": roads}

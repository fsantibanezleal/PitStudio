"""Quadtree tiles of 257 x 257 samples per LOD with shared-edge watertightness, skirts and a tile index (FR-004-07)."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from pitstudio_studio.scene.terrain import rtin

TILE_SAMPLES = 257
STRIDE = TILE_SAMPLES - 1


@dataclass
class Tile:
    """One terrain tile of one LOD: site-frame float32 positions (grid vertices first, then skirt vertices) and
    triangles."""

    id: str
    lod: int
    level: int
    x: int
    y: int
    positions: np.ndarray
    indices: np.ndarray
    n_grid_vertices: int
    max_error_m: float
    skirt_depth_m: float
    prim: str


@dataclass
class TileSet:
    tiles: list[Tile]
    index_entries: list[dict[str, Any]]
    lods: list[dict[str, Any]]
    fixture: bool = False
    _meta: dict[str, Any] = field(default_factory=dict)

    def document(self, grid_elevation_sha256: str, layer_path: str) -> dict[str, Any]:
        """The complete DC-004-04 tile index document."""
        return {
            "schema_version": "1.0",
            "kind": "terrain-tiles",
            "frame": "site-enu",
            "tile_samples": TILE_SAMPLES,
            "grid_elevation_sha256": grid_elevation_sha256,
            "layer_path": layer_path,
            "lods": [dict(entry) for entry in self.lods],
            "tiles": self.index_entries,
            "fixture": self.fixture,
        }


def _fold_edge(edge: np.ndarray) -> np.ndarray:
    """1-D fold of the errors on a shared edge: a segment midpoint carries the largest error of its sub-segments."""
    folded = edge.copy()
    n = len(edge) - 1
    length = 2
    while length <= n:
        mids = np.arange(length // 2, n, length)
        if length >= 4:
            quarter = length // 4
            folded[mids] = np.maximum(folded[mids], np.maximum(folded[mids - quarter], folded[mids + quarter]))
        length *= 2
    return folded


def _window(elevation: np.ndarray, rb: int, cb: int) -> np.ndarray:
    window = np.full((TILE_SAMPLES, TILE_SAMPLES), np.nan)
    r0, c0 = rb * STRIDE, cb * STRIDE
    block = elevation[r0 : r0 + TILE_SAMPLES, c0 : c0 + TILE_SAMPLES]
    window[: block.shape[0], : block.shape[1]] = block
    return window


def _boundary_edges(triangles: np.ndarray) -> np.ndarray:
    """Directed edges (u, v) used by exactly one triangle, in the triangle's own orientation."""
    directed = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    undirected = np.sort(directed, axis=1)
    _, inverse, counts = np.unique(undirected, axis=0, return_inverse=True, return_counts=True)
    return directed[counts[inverse.ravel()] == 1]


def _build_tile(
    window: np.ndarray,
    errors: np.ndarray,
    mesh_err: float,
    skirt_depth: float,
    *,
    origin: tuple[float, float, int, int],
    cell: float,
    last_valid: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray, int] | None:
    x_min, y_max, r0, c0 = origin
    mesh = rtin.mesh_from_errors(window, errors, mesh_err)
    if len(mesh.triangles) == 0:
        return None
    rr, cc = mesh.rc[:, 0].astype(np.int64), mesh.rc[:, 1].astype(np.int64)
    x = x_min + (c0 + cc) * cell
    y = y_max - (r0 + rr) * cell
    grid_positions = np.stack([x, y, mesh.z.astype(np.float64)], axis=1).astype(np.float32)
    triangles = mesh.triangles.astype(np.int64)
    # skirts hang below the boundary edges that lie on a tile or grid boundary line
    last_r, last_c = last_valid
    lines = [(1, 0), (1, STRIDE), (0, 0), (0, STRIDE), (1, last_c), (0, last_r)]  # (axis: 1 = col, 0 = row, value)
    edges = _boundary_edges(triangles)
    keep = np.zeros(len(edges), dtype=bool)
    for axis, value in lines:
        coord = mesh.rc[:, axis]
        on = coord == value
        keep |= on[edges[:, 0]] & on[edges[:, 1]]
    edges = edges[keep]
    skirt_vertices = np.unique(edges.ravel()) if len(edges) else np.zeros(0, dtype=np.int64)
    skirt_index = {int(v): len(grid_positions) + i for i, v in enumerate(skirt_vertices)}
    skirt_positions = grid_positions[skirt_vertices].copy()
    skirt_positions[:, 2] = (grid_positions[skirt_vertices, 2].astype(np.float64) - skirt_depth).astype(np.float32)
    skirt_triangles = []
    for u, v in edges:
        su, sv = skirt_index[int(u)], skirt_index[int(v)]
        skirt_triangles.append((int(u), sv, int(v)))
        skirt_triangles.append((int(u), su, sv))
    positions = np.concatenate([grid_positions, skirt_positions]) if len(skirt_positions) else grid_positions
    all_triangles = (
        np.concatenate([triangles, np.array(skirt_triangles, dtype=np.int64)]) if skirt_triangles else triangles
    )
    return positions, all_triangles.astype(np.uint32), len(grid_positions)


def build_tiles(
    elevation: np.ndarray,
    *,
    cell_size_m: float,
    x_min_m: float,
    y_max_m: float,
    lods: list[dict[str, Any]],
    fixture: bool = False,
) -> TileSet:
    """Split the grid into 257 x 257 tiles (stride 256) and mesh each one per LOD with the RTIN of FR-004-06.

    Tile edges are shared: before triangulation the vertex errors on every shared edge are set to the largest of the two
    tiles (folded along the edge), so that both tiles split the same edge vertices and meet without cracks (P-004-02).
    Tile ids are `<lod>-<level>-<x>-<y>` with x east and y north (0 is the south-west tile); nodata-only tiles are
    skipped.
    """
    elevation = np.asarray(elevation, dtype=np.float64)
    rows, cols = elevation.shape
    nx = max(1, math.ceil((cols - 1) / STRIDE))
    ny = max(1, math.ceil((rows - 1) / STRIDE))
    level = max(0, math.ceil(math.log2(max(nx, ny)))) if max(nx, ny) > 1 else 0
    windows = {(rb, cb): _window(elevation, rb, cb) for rb in range(ny) for cb in range(nx)}
    fields = {key: rtin.error_field(window) for key, window in windows.items()}
    base = {key: f.fold().reshape(TILE_SAMPLES, TILE_SAMPLES) for key, f in fields.items()}
    floors = {key: np.zeros((TILE_SAMPLES, TILE_SAMPLES)) for key in windows}
    for rb, cb in windows:
        if (rb, cb + 1) in windows:  # east neighbour: shared column
            folded = _fold_edge(np.maximum(base[rb, cb][:, STRIDE], base[rb, cb + 1][:, 0]))
            floors[rb, cb][:, STRIDE] = folded
            floors[rb, cb + 1][:, 0] = folded
        if (rb + 1, cb) in windows:  # south neighbour: shared row
            folded = _fold_edge(np.maximum(base[rb, cb][STRIDE, :], base[rb + 1, cb][0, :]))
            floors[rb, cb][STRIDE, :] = folded
            floors[rb + 1, cb][0, :] = folded
    errors = {key: fields[key].fold(floors[key]) for key in windows}
    tiles: list[Tile] = []
    entries: list[dict[str, Any]] = []
    lod_rows: list[dict[str, Any]] = []
    for lod in lods:
        lod_id = int(lod["lod"])
        max_error = float(lod["max_error_m"])
        skirt = float(lod.get("skirt_depth_m", 2.0 * max_error))
        count = 0
        for (rb, cb), window in sorted(windows.items(), key=lambda kv: (ny - 1 - kv[0][0], kv[0][1])):
            built = _build_tile(
                window,
                errors[rb, cb],
                max_error,
                skirt,
                origin=(x_min_m, y_max_m, rb * STRIDE, cb * STRIDE),
                cell=cell_size_m,
                last_valid=(min(STRIDE, rows - 1 - rb * STRIDE), min(STRIDE, cols - 1 - cb * STRIDE)),
            )
            if built is None:
                continue
            positions, indices, n_grid = built
            tx, ty = cb, ny - 1 - rb
            prim = f"/World/Terrain/Lod{lod_id}/Tile_{lod_id}_{level}_{tx}_{ty}"
            tile = Tile(
                f"{lod_id}-{level}-{tx}-{ty}", lod_id, level, tx, ty, positions, indices, n_grid, max_error, skirt, prim
            )
            tiles.append(tile)
            pos = np.asarray(positions, dtype="<f4")
            idx = np.asarray(indices, dtype="<u4")
            entries.append(
                {
                    "id": tile.id,
                    "lod": lod_id,
                    "level": level,
                    "x": tx,
                    "y": ty,
                    "prim": prim,
                    "bbox": {
                        "x_min_m": float(pos[:, 0].min()),
                        "y_min_m": float(pos[:, 1].min()),
                        "z_min_m": float(pos[:, 2].min()),
                        "x_max_m": float(pos[:, 0].max()),
                        "y_max_m": float(pos[:, 1].max()),
                        "z_max_m": float(pos[:, 2].max()),
                    },
                    "max_error_m": max_error,
                    "vertices": len(pos),
                    "triangles": len(idx),
                    "sha256": hashlib.sha256(pos.tobytes() + idx.tobytes()).hexdigest(),
                }
            )
            count += 1
        lod_rows.append({"lod": lod_id, "max_error_m": max_error, "skirt_depth_m": skirt, "tile_count": count})
    return TileSet(tiles=tiles, index_entries=entries, lods=lod_rows, fixture=fixture)

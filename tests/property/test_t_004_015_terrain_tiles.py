# ruff: noqa: E501, PT018
"""T-004-015: quadtree tiles, shared-edge watertightness, skirts and the tile index.

Requirements: FR-004-07, P-004-02.

Oracle: the tile index fields are recomputed independently with hashlib and numpy from each tile's own buffers
(plan.md "FR-004-07"); watertightness is exact (bitwise) equality of the vertex positions on a shared edge (P-004-02);
skirts follow the hand rule "a copy of every boundary grid vertex lowered by the skirt depth"; the vertical error of the
tile surface is checked with the brute-force `scene_kit.mesh_errors`.

Expected API (package `pitstudio_studio.scene.terrain`, studio environment):
- `terrain.tiles.build_tiles(elevation, *, cell_size_m, x_min_m, y_max_m, lods) -> TileSet`; `elevation` float32/64
  [rows, cols] (row 0 = north, site frame, metres), `lods` a list of `{"lod": int, "max_error_m": float,
  "skirt_depth_m": float (optional, default 2 * max_error_m)}`. Per LOD the grid is split into tiles of 257 x 257 samples
  (stride 256 samples; adjacent tiles share the edge row or column), each meshed with the RTIN of FR-004-06 after
  forcing both neighbours to contain the edge vertices of either.
- `TileSet.tiles`: list of `Tile`; `Tile` has `id` ("<lod>-<quadtree level>-<x>-<y>", x east, y north, as in the
  DC-004-04 example), `lod`, `level`, `x`, `y`, `positions` (float32 [n, 3], site-frame x, y, z in metres),
  `indices` (uint32 [m, 3]), `n_grid_vertices` (the first `n_grid_vertices` positions are mesh vertices, the rest skirt
  vertices), `max_error_m`, `skirt_depth_m`.
- `TileSet.index_entries`: list of dicts with the DC-004-04 tile fields `id, lod, level, x, y, prim, bbox, max_error_m,
  vertices, triangles, sha256`; `TileSet.lods`: list of `{"lod", "max_error_m", "skirt_depth_m", "tile_count"}`.
- `build_tiles(..., fixture=False)` and `TileSet.document(grid_elevation_sha256, layer_path)`: the complete DC-004-04
  document (`schema_version`, `kind`, `frame`, `tile_samples` = 257, `grid_elevation_sha256`, `layer_path`, `lods`, `tiles`
  = `index_entries`, plus `fixture` when built with `fixture=True`; test_t_004_094), valid against the draft schema.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

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
GRID = dict(cell_size_m=1.0, x_min_m=-256.0, y_max_m=256.0)  # 513 x 513 samples: x, y in [-256, 256]


def _tiles(h: np.ndarray, lods: list[dict] = LODS, **grid: float) -> terrain.tiles.TileSet:
    return terrain.tiles.build_tiles(h, **(grid or GRID), lods=lods)


def _edge(tile: terrain.tiles.Tile, axis: int, value: float) -> set[tuple[float, float, float]]:
    pos = tile.positions[: tile.n_grid_vertices]
    sel = pos[pos[:, axis] == np.float32(value)]
    return {tuple(map(float, p)) for p in sel}


@pytest.mark.req("FR-004-07")
def test_513_grid_gives_four_tiles_per_lod_with_the_documented_ids_and_bboxes() -> None:
    ts = _tiles(kit.fbm_grid(9, 1, amplitude=30.0))  # 513 x 513 samples
    assert [(d["lod"], d["tile_count"]) for d in ts.lods] == [(0, 4), (1, 4), (2, 4)]
    assert len(ts.tiles) == 12
    ids = sorted(t.id for t in ts.tiles if t.lod == 0)
    assert ids == ["0-1-0-0", "0-1-0-1", "0-1-1-0", "0-1-1-1"]  # <lod>-<level>-<x>-<y>
    by_id = {t.id: t for t in ts.tiles}
    south_west = by_id["0-1-0-0"]
    xs, ys = south_west.positions[:, 0], south_west.positions[:, 1]
    assert (float(xs.min()), float(xs.max()), float(ys.min()), float(ys.max())) == (-256.0, 0.0, -256.0, 0.0)
    north_east = by_id["0-1-1-1"]
    assert (float(north_east.positions[:, 0].min()), float(north_east.positions[:, 1].min())) == (0.0, 0.0)


@pytest.mark.req("FR-004-07")
def test_single_257_grid_is_one_level_0_tile_per_lod() -> None:
    h = kit.fbm_grid(8, 3, amplitude=20.0)
    ts = _tiles(h, cell_size_m=0.5, x_min_m=10.0, y_max_m=20.0)
    assert sorted(t.id for t in ts.tiles) == ["0-0-0-0", "1-0-0-0", "2-0-0-0"]
    t = ts.tiles[0]
    assert float(t.positions[:, 0].min()) == 10.0 and float(t.positions[:, 0].max()) == 10.0 + 256 * 0.5
    assert float(t.positions[:, 1].max()) == 20.0 and float(t.positions[:, 1].min()) == 20.0 - 256 * 0.5


@pytest.mark.req("FR-004-07")
def test_index_entries_are_recomputed_independently() -> None:
    h = kit.fbm_grid(9, 2, amplitude=40.0)[:513, :513]
    ts = _tiles(h)
    tiles = {t.id: t for t in ts.tiles}
    assert len(ts.index_entries) == len(tiles) == 12
    for e in ts.index_entries:
        t = tiles[e["id"]]
        pos, idx = np.asarray(t.positions, "<f4"), np.asarray(t.indices, "<u4")
        assert e["sha256"] == hashlib.sha256(pos.tobytes() + idx.tobytes()).hexdigest()
        assert (e["vertices"], e["triangles"]) == (len(pos), len(idx))
        assert e["max_error_m"] == LODS[e["lod"]]["max_error_m"]
        assert (e["lod"], e["level"], e["x"], e["y"]) == (t.lod, 1, t.x, t.y)
        want = {
            "x_min_m": pos[:, 0].min(),
            "y_min_m": pos[:, 1].min(),
            "z_min_m": pos[:, 2].min(),
            "x_max_m": pos[:, 0].max(),
            "y_max_m": pos[:, 1].max(),
            "z_max_m": pos[:, 2].max(),
        }
        assert e["bbox"] == pytest.approx({k: float(v) for k, v in want.items()})  # bbox includes the skirts
        assert e["vertices"] <= 257**2 + 4 * 257 and e["triangles"] <= 2 * 256**2 + 8 * 256
        assert e["prim"].startswith("/World/Terrain/")


@pytest.mark.req("FR-004-07")
def test_the_tile_index_document_is_valid_against_the_dc_004_04_schema() -> None:
    ts = _tiles(kit.fbm_grid(9, 2, amplitude=40.0)[:513, :513])
    doc = ts.document("7b961cd56183d759c6597ecf1f2c989cdc97f8292d6f676a590bb138e4ca356a", "layers/terrain.usdc")
    assert kit.schema_errors("terrain-tiles.schema.json", doc) == []
    assert doc["tile_samples"] == 257 and doc["tiles"] == ts.index_entries and len(doc["tiles"]) == 12
    assert [(lod["lod"], lod["max_error_m"], lod["skirt_depth_m"], lod["tile_count"]) for lod in doc["lods"]] == [
        (0, 0.25, 0.5, 4),
        (1, 1.0, 2.0, 4),
        (2, 4.0, 8.0, 4),
    ]


@pytest.mark.req("FR-004-07")
def test_tiles_are_deterministic() -> None:
    h = kit.fbm_grid(9, 6, amplitude=25.0)[:513, :513]
    a, b = _tiles(h), _tiles(h)
    assert [e["sha256"] for e in a.index_entries] == [e["sha256"] for e in b.index_entries]


@pytest.mark.req("FR-004-07")
def test_skirt_vertices_hang_below_the_boundary_by_the_declared_depth() -> None:
    h = kit.fbm_grid(8, 5, amplitude=35.0)
    for lod in LODS:
        ts = _tiles(h, [lod], cell_size_m=1.0, x_min_m=0.0, y_max_m=256.0)
        (t,) = ts.tiles
        grid, skirt = t.positions[: t.n_grid_vertices], t.positions[t.n_grid_vertices :]
        on_boundary = (grid[:, 0] == 0.0) | (grid[:, 0] == 256.0) | (grid[:, 1] == 0.0) | (grid[:, 1] == 256.0)
        n_ring = int(on_boundary.sum())  # boundary mesh vertices, corners counted once
        assert n_ring <= len(skirt) <= n_ring + 4  # one skirt vertex per boundary vertex (corners may be doubled)
        top = {(float(p[0]), float(p[1])): float(p[2]) for p in grid[on_boundary]}
        for p in skirt:
            assert float(p[2]) == pytest.approx(top[(float(p[0]), float(p[1]))] - lod["skirt_depth_m"], abs=1e-4)
        assert t.skirt_depth_m == lod["skirt_depth_m"]
        referenced = set(np.unique(t.indices[(t.indices >= t.n_grid_vertices).any(axis=1)]).tolist())
        assert set(range(t.n_grid_vertices, len(t.positions))) <= referenced  # every skirt vertex is used
        assert len(t.indices) <= 2 * 256**2 + 8 * 256  # FR-004-07 / DC-004-04 triangle bound


@pytest.mark.req("FR-004-07")
def test_default_skirt_depth_is_twice_the_max_error() -> None:
    h = kit.fbm_grid(8, 5, amplitude=35.0)
    lods = [{"lod": i, "max_error_m": e} for i, e in enumerate((0.25, 1.0, 4.0))]
    ts = _tiles(h, lods, cell_size_m=1.0, x_min_m=0.0, y_max_m=256.0)
    assert [t.skirt_depth_m for t in ts.tiles] == [0.5, 2.0, 8.0]
    assert [d["skirt_depth_m"] for d in ts.lods] == [0.5, 2.0, 8.0]


@pytest.mark.req("FR-004-07")
def test_tile_surface_meets_the_lod_error_bound() -> None:
    h = kit.fbm_grid(8, 9, amplitude=45.0)
    ts = _tiles(h, [LODS[1]], cell_size_m=1.0, x_min_m=0.0, y_max_m=256.0)
    (t,) = ts.tiles
    grid = t.positions[: t.n_grid_vertices]
    rc = np.stack([np.rint(256.0 - grid[:, 1]), np.rint(grid[:, 0])], axis=1).astype(np.int32)  # (row, col)
    surface = t.indices[(t.indices < t.n_grid_vertices).all(axis=1)]
    worst, covered, _ = kit.mesh_errors(rc, grid[:, 2], surface, h)
    assert covered.all() and worst <= 1.0 + 2.5e-4


@pytest.mark.req("P-004-02")
@settings(max_examples=3, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(seed=st.integers(0, 2**31 - 1), amplitude=st.floats(5.0, 200.0), noise=st.floats(0.0, 3.0))
def test_adjacent_tiles_have_identical_vertices_on_every_shared_edge(seed: int, amplitude: float, noise: float) -> None:
    """P-004-02: 513^2 random grid, 4 tiles, every LOD; shared-edge vertex positions are bit-identical."""
    h = kit.fbm_grid(9, seed, amplitude=amplitude)[:513, :513]
    h = h + np.random.default_rng(seed).normal(0.0, noise, h.shape)
    ts = _tiles(h)
    for lod in (0, 1, 2):
        t = {(x.x, x.y): x for x in ts.tiles if x.lod == lod}
        assert _edge(t[0, 0], 0, 0.0) == _edge(t[1, 0], 0, 0.0) and len(_edge(t[0, 0], 0, 0.0)) >= 2  # x = 0 edge
        assert _edge(t[0, 1], 0, 0.0) == _edge(t[1, 1], 0, 0.0)
        assert _edge(t[0, 0], 1, 0.0) == _edge(t[0, 1], 1, 0.0)  # y = 0 edge
        assert _edge(t[1, 0], 1, 0.0) == _edge(t[1, 1], 1, 0.0)
    rough = {len(_edge(t, 0, 0.0)) for t in ts.tiles if t.x == 0 and t.lod == 0}
    assert max(rough) > 2  # the forced edge vertices of rough terrain are more than the two corners

# ruff: noqa: PT018
"""T-004-012: ground-point gridding with an order-independent mean; permutation invariance.

Requirements: FR-004-04, P-004-05.

Oracle: hand calculation on a 3 x 3-cell point fixture with known means and non-ground points that must be excluded
(plan.md "FR-004-04"); `math.fsum` per cell as an exactly rounded reference mean; P-004-05 is a metamorphic relation
(any permutation of the tile order and of the point order gives a bitwise-identical grid).

Expected API (package `pitstudio_studio.scene.terrain`, studio environment):
- `terrain.grid.grid_ground_points(x, y, z, classification, *, x_min, y_max, rows, cols, cell_size_m)`: site-frame
  coordinates in metres (float64), ASPRS classes (uint8). Keeps class 2 only. Cell (r, c) holds the points with
  `x_min + c * cell <= x < x_min + (c + 1) * cell` and `y_max - (r + 1) * cell < y <= y_max - r * cell` (row 0 = north).
  Returns a float64 array [rows, cols]: the per-cell mean elevation, computed with an order-independent summation
  (points sorted by cell and elevation, then a float64 sum), NaN where a cell has no ground point. Points outside the
  grid are ignored.
- `terrain.build_terrain_grid(spec, inputs)` accepts a `kind: "laz"` terrain source (see test_t_004_010).
"""

from __future__ import annotations

import math
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

# (x, y, z, class); cell (r, c) covers x in [c, c+1), y in [2-r, 3-r) on the 3 x 3 grid with x_min = 0, y_max = 3.
HAND = [
    (0.2, 2.2, 10.0, 2),
    (0.5, 2.5, 20.0, 2),
    (0.8, 2.8, 30.0, 2),  # cell (0,0): mean 20
    (0.4, 2.4, 999.0, 1),
    (0.6, 2.6, 500.0, 6),  # cell (0,0): unclassified / building, must be excluded
    (1.3, 1.3, 5.5, 2),
    (1.7, 1.7, 6.5, 2),
    (1.5, 1.5, 0.0, 7),  # cell (1,1): mean 6.0, noise excluded
    (2.5, 0.5, 100.0, 1),  # cell (2,2): non-ground only -> nodata
    (2.5, 2.5, 42.25, 2),  # cell (0,2): one ground point
    (0.1, 0.1, 0.1, 2),
    (0.5, 0.5, 0.2, 2),
    (0.9, 0.9, 0.3, 2),  # cell (2,0): mean 0.2
    (-5.0, 1.0, 77.0, 2),
    (3.5, 1.0, 88.0, 2),  # outside the grid: ignored
]
EXPECTED = np.full((3, 3), np.nan)
EXPECTED[0, 0], EXPECTED[1, 1], EXPECTED[0, 2], EXPECTED[2, 0] = 20.0, 6.0, 42.25, 0.2


def _arrays(points: list[tuple[float, float, float, int]]) -> tuple[np.ndarray, ...]:
    a = np.array(points, dtype=np.float64)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3].astype(np.uint8)


@pytest.mark.req("FR-004-04")
def test_per_cell_mean_of_class_2_points_matches_the_hand_calculation() -> None:
    x, y, z, c = _arrays(HAND)
    got = terrain.grid.grid_ground_points(x, y, z, c, x_min=0.0, y_max=3.0, rows=3, cols=3, cell_size_m=1.0)
    assert got.shape == (3, 3)
    np.testing.assert_allclose(got, EXPECTED, rtol=1e-12, atol=0.0, equal_nan=True)
    assert np.isnan(got[2, 2])  # only a non-ground point: nodata
    assert int(np.isnan(got).sum()) == 5


@pytest.mark.req("FR-004-04")
def test_only_ground_class_counts() -> None:
    n = 50
    x = np.full(n, 0.5)
    y = np.full(n, 0.5)
    z = np.linspace(1.0, 2.0, n)
    for cls in (0, 1, 3, 4, 5, 6, 7, 9, 17, 18):
        got = terrain.grid.grid_ground_points(
            x, y, z, np.full(n, cls, np.uint8), x_min=0.0, y_max=1.0, rows=1, cols=1, cell_size_m=1.0
        )
        assert np.isnan(got[0, 0]), cls
    got = terrain.grid.grid_ground_points(
        x, y, z, np.full(n, 2, np.uint8), x_min=0.0, y_max=1.0, rows=1, cols=1, cell_size_m=1.0
    )
    assert got[0, 0] == pytest.approx(1.5, rel=1e-12)


@pytest.mark.req("FR-004-04")
def test_declared_cell_size_is_used() -> None:
    """Two points 1.2 m apart share a 2 m cell and fall in different 1 m cells (hand calculation)."""
    x, y, z, c = np.array([0.4, 1.6]), np.array([0.5, 0.5]), np.array([10.0, 20.0]), np.array([2, 2], np.uint8)
    coarse = terrain.grid.grid_ground_points(x, y, z, c, x_min=0.0, y_max=2.0, rows=1, cols=1, cell_size_m=2.0)
    assert coarse[0, 0] == pytest.approx(15.0)
    fine = terrain.grid.grid_ground_points(x, y, z, c, x_min=0.0, y_max=2.0, rows=2, cols=2, cell_size_m=1.0)
    assert fine[1, 0] == pytest.approx(10.0) and fine[1, 1] == pytest.approx(20.0)
    assert np.isnan(fine[0, :]).all()


@pytest.mark.req("FR-004-04")
def test_laz_dense_tile_matches_fsum_reference(tmp_path: Path) -> None:
    """Every cell of a 4 x 4 grid holds 5 ground points at 1000 m +/- 1e-3: compare with the exactly rounded mean."""
    rng = np.random.default_rng(11)
    n_cells, per = 4, 5
    xs, ys, zs, cs = [], [], [], []
    for r in range(n_cells):
        for c in range(n_cells):
            xs += list(c + rng.uniform(0.05, 0.95, per))
            ys += list((n_cells - 1 - r) + rng.uniform(0.05, 0.95, per))
            zs += list(100.0 + rng.uniform(0.0, 1e-3, per) + 10 * r + c)
            cs += [2] * per
    x, y, z, c = map(np.array, (xs, ys, zs, cs))
    path = kit.write_laz(tmp_path / "dense.laz", kit.E0 + x, kit.N0 + y, kit.Z0 + z, c.astype(np.uint8))
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, 4.0, 4.0, 1.0)
    spec["terrain"]["sources"][0]["kind"] = "laz"
    grid = terrain.build_terrain_grid(spec, {"usgs-3dep-bingham": [path]})
    assert grid.elevation.shape == (4, 4)
    tile = terrain.io.read_laz(path)  # the stored (LAS-quantised) coordinates are the inputs of the reference mean
    for r in range(4):
        for col in range(4):
            sel = (np.floor(tile.x - kit.E0) == col) & (np.floor(kit.N0 + 4 - tile.y) == r)
            want = math.fsum(sorted(tile.z[sel] - kit.Z0)) / sel.sum()
            assert float(grid.elevation[r, col]) == pytest.approx(want, abs=2e-5)  # float32 storage


@pytest.mark.req("P-004-05")
@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_permutation_invariance_is_bitwise_on_2e4_points(seed: int) -> None:
    """P-004-05: any permutation of the point order (hence of any tile order) gives a bitwise-identical grid."""
    base = np.random.default_rng(1234)
    n = 20_000
    x = base.uniform(0.0, 20.0, n)
    y = base.uniform(0.0, 20.0, n)
    z = 1000.0 + base.normal(0.0, 1e-3, n) + 5.0 * np.sin(x)  # tiny differences on a large offset: sum order matters
    c = base.choice([1, 2, 2, 2, 6], n).astype(np.uint8)
    kw = {"x_min": 0.0, "y_max": 20.0, "rows": 20, "cols": 20, "cell_size_m": 1.0}
    ref = terrain.grid.grid_ground_points(x, y, z, c, **kw)
    perm = np.random.default_rng(seed).permutation(n)
    got = terrain.grid.grid_ground_points(x[perm], y[perm], z[perm], c[perm], **kw)
    np.testing.assert_array_equal(got, ref)  # NaN positions equal; every other value bit for bit
    assert got.tobytes() == ref.tobytes()


@pytest.mark.req("P-004-05")
def test_permutation_of_tile_order_through_the_stage_function(tmp_path: Path) -> None:
    rng = np.random.default_rng(5)
    paths = []
    for k in range(2):
        n = 4000
        x = rng.uniform(0.0, 8.0, n)
        y = rng.uniform(0.0, 8.0, n)
        z = 50.0 + rng.normal(0.0, 1e-3, n) + x
        paths.append(kit.write_laz(tmp_path / f"t{k}.laz", kit.E0 + x, kit.N0 + y, kit.Z0 + z, np.full(n, 2, np.uint8)))
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, 8.0, 8.0, 1.0)
    spec["terrain"]["sources"][0]["kind"] = "laz"
    a = terrain.build_terrain_grid(spec, {"usgs-3dep-bingham": paths})
    b = terrain.build_terrain_grid(spec, {"usgs-3dep-bingham": paths[::-1]})
    assert a.elevation.tobytes() == b.elevation.tobytes()
    assert a.valid_mask.tobytes() == b.valid_mask.tobytes()

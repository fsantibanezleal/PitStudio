# ruff: noqa: E501, PT018
"""T-004-013: harmonic (Laplace) hole fill, fill mask, large holes left as nodata.

Requirements: FR-004-05, P-004-06.

Oracle: a hand-solved 2-cell Laplace system (plan.md "FR-004-05"); the planar surface z = a x + b y + c, which is an
exact discrete harmonic function (P-004-06); the mean-value property and the maximum principle of discrete harmonic
functions, checked independently of the solver.

Expected API (package `pitstudio_studio.scene.terrain`, studio environment):
- `terrain.grid.fill_holes(elevation, *, max_fill_cells=16) -> FillResult`; `elevation` is a float64 array [rows, cols]
  with NaN as nodata. A hole is a 4-connected set of nodata cells. A hole of at most `max_fill_cells` cells is filled with
  the discrete harmonic interpolant of the surrounding valid cells (each unknown equals the mean of its four neighbours;
  Dirichlet values from the valid neighbours; solved in float64). Larger holes stay NaN.
  `FillResult` has `elevation` (float64 copy with the filled values), `fill_mask` (bool, True exactly on filled cells),
  `unfilled_holes` (int), `unfilled_cells` (int).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_studio.scene import terrain  # noqa: E402


@pytest.mark.req("FR-004-05")
def test_two_cell_hole_matches_the_hand_solved_laplace_system() -> None:
    """Unknowns u1 = (1,1), u2 = (1,2): 4 u1 = a + b + c + u2 and 4 u2 = d + e + f + u1.

    With a, b, c = 10, 20, 30 and d, e, f = 1, 2, 3: u1 = (4 * 60 + 6) / 15 = 16.4 and u2 = (4 * 6 + 60) / 15 = 5.6.
    """
    z = np.zeros((3, 4))
    z[0, 1], z[2, 1], z[1, 0] = 10.0, 20.0, 30.0  # neighbours of u1 (up, down, left)
    z[0, 2], z[2, 2], z[1, 3] = 1.0, 2.0, 3.0  # neighbours of u2 (up, down, right)
    z[0, 0] = z[0, 3] = z[2, 0] = z[2, 3] = 50.0  # corners: not neighbours of the hole
    z[1, 1] = z[1, 2] = np.nan
    res = terrain.grid.fill_holes(z)
    assert res.elevation[1, 1] == pytest.approx(16.4, abs=1e-9)
    assert res.elevation[1, 2] == pytest.approx(5.6, abs=1e-9)
    assert res.fill_mask.tolist() == [[False] * 4, [False, True, True, False], [False] * 4]
    assert (res.unfilled_holes, res.unfilled_cells) == (0, 0)
    np.testing.assert_array_equal(res.elevation[~res.fill_mask], z[~res.fill_mask])  # valid cells untouched


@pytest.mark.req("FR-004-05")
def test_single_cell_hole_is_the_mean_of_its_four_neighbours() -> None:
    z = np.arange(25, dtype=np.float64).reshape(5, 5) ** 1.5
    want = (z[1, 2] + z[3, 2] + z[2, 1] + z[2, 3]) / 4.0
    z[2, 2] = np.nan
    res = terrain.grid.fill_holes(z)
    assert res.elevation[2, 2] == pytest.approx(want, rel=1e-12)
    assert res.fill_mask[2, 2] and res.fill_mask.sum() == 1


@pytest.mark.req("FR-004-05")
def test_diagonal_cells_are_separate_holes() -> None:
    """4-connectivity: (1,1) and (2,2) touch only at a corner, so each is its own one-cell hole."""
    z = np.arange(36, dtype=np.float64).reshape(6, 6)
    z[1, 1] = z[2, 2] = np.nan
    res = terrain.grid.fill_holes(z, max_fill_cells=1)  # only a one-cell hole may be filled
    assert res.fill_mask[1, 1] and res.fill_mask[2, 2]
    assert res.unfilled_holes == 0


@pytest.mark.req("FR-004-05")
def test_hole_of_exactly_max_fill_cells_is_filled_and_one_more_is_not() -> None:
    plane = np.add.outer(np.arange(7.0) * 2.0, np.arange(40.0) * 0.5)
    for size, filled in ((16, True), (17, False)):
        z = plane.copy()
        z[3, 5 : 5 + size] = np.nan  # a 1 x size strip
        res = terrain.grid.fill_holes(z)  # default max_fill_cells = 16
        assert bool(res.fill_mask[3, 5 : 5 + size].all()) is filled
        if filled:
            assert (res.unfilled_holes, res.unfilled_cells) == (0, 0)
            np.testing.assert_allclose(res.elevation, plane, atol=1e-6)
        else:
            assert np.isnan(res.elevation[3, 5 : 5 + size]).all()  # left as nodata, never invented
            assert not res.fill_mask.any()
            assert (res.unfilled_holes, res.unfilled_cells) == (1, 17)


@pytest.mark.req("FR-004-05")
def test_max_fill_cells_parameter_is_honoured_and_unfilled_holes_are_counted() -> None:
    plane = np.add.outer(np.arange(12.0), np.arange(12.0) * 3.0)
    z = plane.copy()
    z[2:4, 2:4] = np.nan  # a 4-cell hole
    z[8:10, 5:8] = np.nan  # a 6-cell hole
    z[6, 9] = np.nan  # a 1-cell hole
    res = terrain.grid.fill_holes(z, max_fill_cells=4)
    assert res.fill_mask[2:4, 2:4].all() and res.fill_mask[6, 9]
    assert not res.fill_mask[8:10, 5:8].any()
    assert (res.unfilled_holes, res.unfilled_cells) == (1, 6)
    np.testing.assert_allclose(res.elevation[2:4, 2:4], plane[2:4, 2:4], atol=1e-6)


@pytest.mark.req("FR-004-05")
def test_grid_without_holes_is_returned_unchanged() -> None:
    z = np.random.default_rng(3).uniform(0, 100, (8, 8))
    res = terrain.grid.fill_holes(z)
    np.testing.assert_array_equal(res.elevation, z)
    assert not res.fill_mask.any() and (res.unfilled_holes, res.unfilled_cells) == (0, 0)


def _hole_cells(data: st.DataObject, rows: int, cols: int, size: int) -> set[tuple[int, int]]:
    """A random 4-connected hole of `size` cells whose cells all keep a one-cell margin to the grid edge."""
    r0 = data.draw(st.integers(2, rows - 3))
    c0 = data.draw(st.integers(2, cols - 3))
    cells = {(r0, c0)}
    while len(cells) < size:
        r, c = data.draw(st.sampled_from(sorted(cells)))
        dr, dc = data.draw(st.sampled_from([(1, 0), (-1, 0), (0, 1), (0, -1)]))
        if 1 <= r + dr <= rows - 2 and 1 <= c + dc <= cols - 2:
            cells.add((r + dr, c + dc))
    return cells


@pytest.mark.req("P-004-06")
@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(
    data=st.data(),
    a=st.floats(-1, 1),
    b=st.floats(-1, 1),
    c=st.floats(-500, 500),
    size=st.integers(1, 16),
)
def test_harmonic_fill_reproduces_a_plane(data: st.DataObject, a: float, b: float, c: float, size: int) -> None:
    """P-004-06: for z = a x + b y + c and any hole of at most 16 cells the fill returns the plane (atol 1e-6 m)."""
    rows = cols = 14
    yy, xx = np.mgrid[0:rows, 0:cols].astype(np.float64)
    plane = a * xx + b * yy + c
    z = plane.copy()
    hole = _hole_cells(data, rows, cols, size)
    for r, col in hole:
        z[r, col] = np.nan
    res = terrain.grid.fill_holes(z)
    mask = np.zeros_like(z, dtype=bool)
    for r, col in hole:
        mask[r, col] = True
    np.testing.assert_array_equal(res.fill_mask, mask)
    np.testing.assert_allclose(res.elevation, plane, rtol=0.0, atol=1e-6)


@pytest.mark.req("P-004-06")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(data=st.data(), seed=st.integers(0, 2**32 - 1), size=st.integers(1, 16))
def test_filled_values_are_harmonic_and_obey_the_maximum_principle(data: st.DataObject, seed: int, size: int) -> None:
    """On arbitrary valid data: each filled cell is the mean of its four neighbours and lies within their range."""
    rows = cols = 12
    z = np.random.default_rng(seed).uniform(-300.0, 300.0, (rows, cols))
    hole = _hole_cells(data, rows, cols, size)
    original = z.copy()
    for r, c in hole:
        z[r, c] = np.nan
    res = terrain.grid.fill_holes(z)
    out = res.elevation
    boundary = []
    for r, c in hole:
        nbrs = [(r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)]
        assert out[r, c] == pytest.approx(np.mean([out[p] for p in nbrs]), abs=1e-9)  # mean-value property
        boundary += [original[p] for p in nbrs if p not in hole]
    lo, hi = min(boundary), max(boundary)
    assert all(lo - 1e-9 <= out[r, c] <= hi + 1e-9 for r, c in hole)  # discrete maximum principle
    keep = np.ones_like(z, dtype=bool)
    for r, c in hole:
        keep[r, c] = False
    np.testing.assert_array_equal(out[keep], original[keep])

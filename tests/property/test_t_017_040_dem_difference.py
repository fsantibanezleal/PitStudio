"""T-017-040: DEM differencing, exactly rounded sums, hostile surfaces (property).

Requirements: FR-017-30, FR-017-48, P-017-10, P-017-11, P-017-12, P-017-13, P-017-14.

Spec: specs/017-planning-survey/spec.md
- FR-017-30: the DEM-differencing function returns, for two surfaces z0 (before) and z1 (after) on one grid with
  cell area
  A_c and an area-of-interest polygon, V_fill = A_c sum max(z1 - z0, 0), V_cut = A_c sum max(z0 - z1, 0) and
  V_net = V_fill - V_cut over the valid cells whose centre lies in the polygon, summed with exactly rounded summation
  (`math.fsum`, mirrored in the browser), and the count and fraction of excluded no-data cells;
- FR-017-48: if two surfaces differ in shape, origin or cell size without a declared resampling, have a cell size
  <= 0 or
  non-finite, or have no valid cell inside the polygon, the function raises `InvalidSurfaceError` with the reason;
- P-017-10 prism: adding a prism of height h > 0 over cells where z1 >= z0 raises V_fill by h x (cell count x A_c) and
  leaves V_cut unchanged (grids <= 512 x 512, h in [0.01, 100] m, rtol 1e-13);
- P-017-11 swap: swapping z0 and z1 swaps V_cut and V_fill and negates V_net (exact);
- P-017-12 partition: for a partition of the polygon's cells into disjoint polygons the volumes add up (rtol 1e-12);
- P-017-13 midpoint bound: for a C^2 difference field d = z1 - z0 >= 0 on a cell-aligned rectangle of area A
  (quadratic
  bowls, Gaussian mounds on a positive base) the gridded volume differs from the exact integral by at most
  A Delta^2 (max|d_xx| + max|d_yy|) / 24 (cells 4, 2, 1, 0.5 m; rectangles <= 2 km; the bound plus rtol 1e-12);
- P-017-14 offset and scaling: adding the same constant to both surfaces leaves V_cut and V_fill unchanged, and
  scaling the
  difference field by k scales them by k (|dV| <= 1e-15 (|c| + (k + 1) max|z|) N A_c; c in [-10^3, 10^3] m, k in
  [0, 10]).
plan.md test strategy rows FR-017-30 (hand calculation on 3 x 3 grids; P-017-10 ... 14) and FR-017-48 (mismatched
surfaces).

Oracles:
- the 3 x 3 hand example below (cell 2 m, A_c = 4 m^2): z0 = 10 everywhere, z1 = [[10, 11, 12], [9, 10, 10], [8,
  13, 10]];
  differences: fill cells 1, 2, 3 (sum 6) -> V_fill = 24; cut cells 1, 2 (sum 3) -> V_cut = 12; V_net = 12; with the
  right two columns as the polygon: fill 1 + 0 + 3 + 2 + 0 + 0 = 6 -> 24, cut 0;
- `math.fsum` for the exactly rounded sums, closed-form integrals for the midpoint bound: the quadratic bowl
  d = c0 + a x^2 + b y^2 over [0, L] x [0, L'] has the integral c0 L L' + a L^3 L' / 3 + b L L'^3 / 3 and the bound
  A Delta^2 (2a + 2b) / 24 (the midpoint error is exactly A Delta^2 (a + b) / 12 for a quadratic, so the bound is
  tight); the Gaussian mound h exp(-((x - xc)^2 + (y - yc)^2) / (2 sigma^2)) over a rectangle has the integral
  h (sigma sqrt(pi / 2))^2 [erf(.)-erf(.)] [erf(.)-erf(.)] (`math.erf`) and max|d_xx| = h / sigma^2 (at the centre);
- the properties themselves.

Expected public API (module `pitstudio.survey.difference`, root environment, numpy only):
    class InvalidSurfaceError(ValueError)           # `.reason`
    @dataclass(frozen=True) Surface                  # z: np.ndarray (ny, nx) float64 (NaN or `nodata` = no data),
                                                     # origin_xy: (x0, y0) lower-left corner (m), cell_size_m: float,
                                                     # nodata: float | None
    @dataclass(frozen=True) VolumeResult             # v_fill, v_cut, v_net (m^3), n_valid, n_nodata_excluded,
                                                     # nodata_fraction (excluded no-data cells / cells in the polygon)
    difference(before: Surface, after: Surface, *, polygon: np.ndarray | None = None) -> VolumeResult
        cell (i, j) (row i along y, column j along x) has its centre at (x0 + (j + 0.5) c, y0 + (i + 0.5) c) and
        area c^2;
        `polygon` (k, 2) is a simple polygon in the same coordinates (None: the whole grid); a cell counts when its
        centre lies strictly inside; a cell with no data in either surface is excluded and counted.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.survey.difference import InvalidSurfaceError, Surface, VolumeResult, difference

Z0 = np.full((3, 3), 10.0)
Z1 = np.array([[10.0, 11.0, 12.0], [9.0, 10.0, 10.0], [8.0, 13.0, 10.0]])


def _s(z, origin=(0.0, 0.0), cell=2.0, nodata=None) -> Surface:
    return Surface(z=np.asarray(z, dtype=np.float64), origin_xy=origin, cell_size_m=cell, nodata=nodata)


def _rect(x0, y0, x1, y1) -> np.ndarray:
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float64)


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-30
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-30")
def test_the_3_x_3_hand_example() -> None:
    r = difference(_s(Z0), _s(Z1))
    assert isinstance(r, VolumeResult)
    assert (r.v_fill, r.v_cut, r.v_net) == (24.0, 12.0, 12.0)
    assert (r.n_valid, r.n_nodata_excluded, r.nodata_fraction) == (9, 0, 0.0)


@pytest.mark.req("FR-017-30")
def test_a_polygon_selects_the_cells_whose_centres_lie_inside() -> None:
    # the right two columns: centres at x = 3 and 5; the polygon edge at x = 2 passes between centres 1 and 3
    r = difference(_s(Z0), _s(Z1), polygon=_rect(2.0, 0.0, 6.0, 6.0))
    assert (r.v_fill, r.v_cut, r.v_net, r.n_valid) == (24.0, 0.0, 24.0, 6)
    # a triangle: the centres (1, 1), (3, 1), (5, 1), (3, 3) ... only those strictly inside count
    tri = np.array([[0.0, 0.0], [6.0, 0.0], [3.0, 4.0]])
    inside = difference(_s(Z0), _s(Z1), polygon=tri)
    assert inside.n_valid == 4  # centres (1,1), (3,1), (5,1) and (3,3); (1,3) and (5,3) are outside the triangle


@pytest.mark.req("FR-017-30")
@pytest.mark.parametrize("marker", ["nan", "sentinel"])
def test_no_data_cells_are_excluded_counted_and_reported_as_a_fraction(marker: str) -> None:
    z1 = Z1.copy()
    nodata = None
    if marker == "nan":
        z1[0, 0] = np.nan
    else:
        z1[0, 0] = -9999.0
        nodata = -9999.0
    z0 = Z0.copy()
    z0[2, 2] = np.nan  # no data in the "before" surface excludes the cell as well
    r = difference(_s(z0, nodata=nodata), _s(z1, nodata=nodata))
    assert (r.n_valid, r.n_nodata_excluded) == (7, 2)
    assert r.nodata_fraction == pytest.approx(2 / 9)
    assert (r.v_fill, r.v_cut) == (24.0, 12.0)  # the two excluded cells had difference 0 in this example


@pytest.mark.req("FR-017-30")
def test_the_sums_are_exactly_rounded() -> None:
    rng = np.random.default_rng(1)
    z0 = rng.uniform(0, 1e3, (64, 64))
    z1 = z0 + rng.normal(0, 1e-3, (64, 64)) * 10.0 ** rng.integers(-8, 8, (64, 64))
    d = z1 - z0
    r = difference(_s(z0, cell=0.25), _s(z1, cell=0.25))
    area = 0.25**2
    assert r.v_fill == area * math.fsum(np.maximum(d, 0).ravel().tolist())
    assert r.v_cut == area * math.fsum(np.maximum(-d, 0).ravel().tolist())
    assert r.v_net == r.v_fill - r.v_cut


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-48
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-48")
def test_surfaces_that_differ_in_shape_origin_or_cell_size_are_refused() -> None:
    with pytest.raises(InvalidSurfaceError, match="shape"):
        difference(_s(Z0), _s(np.ones((3, 4))))
    with pytest.raises(InvalidSurfaceError, match="origin"):
        difference(_s(Z0), _s(Z1, origin=(1.0, 0.0)))
    with pytest.raises(InvalidSurfaceError, match="cell"):
        difference(_s(Z0), _s(Z1, cell=4.0))


@pytest.mark.req("FR-017-48")
@pytest.mark.parametrize("cell", [0.0, -2.0, float("nan"), float("inf")])
def test_a_non_positive_or_non_finite_cell_size_is_refused(cell: float) -> None:
    with pytest.raises(InvalidSurfaceError, match="cell"):
        difference(_s(Z0, cell=cell), _s(Z1, cell=cell))


@pytest.mark.req("FR-017-48")
def test_a_polygon_without_a_valid_cell_inside_is_refused() -> None:
    with pytest.raises(InvalidSurfaceError, match="valid"):
        difference(_s(Z0), _s(Z1), polygon=_rect(100.0, 100.0, 120.0, 120.0))  # entirely outside the grid
    all_nodata = np.full((3, 3), np.nan)
    with pytest.raises(InvalidSurfaceError, match="valid"):
        difference(_s(Z0), _s(all_nodata))
    z1 = Z1.copy()
    z1[:, 1:] = np.nan  # the polygon covers only no-data cells
    with pytest.raises(InvalidSurfaceError, match="valid"):
        difference(_s(Z0), _s(z1), polygon=_rect(2.0, 0.0, 6.0, 6.0))


@pytest.mark.req("FR-017-48")
@pytest.mark.parametrize("z", [np.zeros((0, 3)), np.zeros(5), np.zeros((2, 2, 2))])
def test_empty_or_wrongly_ranked_arrays_are_refused(z: np.ndarray) -> None:
    with pytest.raises(InvalidSurfaceError):
        difference(_s(z), _s(z))


# ----------------------------------------------------------------------------------------------------------------------
# properties
# ----------------------------------------------------------------------------------------------------------------------

grid_dims = st.tuples(st.integers(1, 48), st.integers(1, 48))


def _fields(ny: int, nx: int, seed: int):
    rng = np.random.default_rng(seed)
    z0 = rng.uniform(-50.0, 50.0, (ny, nx))
    z1 = z0 + rng.uniform(-3.0, 3.0, (ny, nx))
    return z0, z1


@pytest.mark.req("P-017-10")
@settings(max_examples=200, deadline=None)
@given(dims=grid_dims, seed=st.integers(0, 2**32 - 1), h=st.floats(0.01, 100.0), cell=st.sampled_from([0.25, 1.0, 4.0]))
def test_a_prism_over_cells_where_z1_is_not_below_z0_raises_the_fill_by_h_times_its_area(dims, seed, h, cell):
    z0, z1 = _fields(*dims, seed)
    over = z1 >= z0
    z1_prism = np.where(over, z1 + h, z1)
    base = difference(_s(z0, cell=cell), _s(z1, cell=cell))
    raised = difference(_s(z0, cell=cell), _s(z1_prism, cell=cell))
    assert raised.v_fill == pytest.approx(base.v_fill + h * over.sum() * cell**2, rel=1e-13, abs=1e-9)
    assert raised.v_cut == pytest.approx(base.v_cut, rel=1e-13, abs=1e-12)  # the cut cells are untouched


@pytest.mark.req("P-017-10")
def test_the_prism_relation_on_a_512_x_512_grid() -> None:
    z0, z1 = _fields(512, 512, 7)
    over = z1 >= z0
    base = difference(_s(z0, cell=0.5), _s(z1, cell=0.5))
    raised = difference(_s(z0, cell=0.5), _s(np.where(over, z1 + 12.5, z1), cell=0.5))
    assert raised.v_fill == pytest.approx(base.v_fill + 12.5 * over.sum() * 0.25, rel=1e-13)


@pytest.mark.req("P-017-11")
@settings(max_examples=200, deadline=None)
@given(dims=grid_dims, seed=st.integers(0, 2**32 - 1))
def test_swapping_the_surfaces_swaps_cut_and_fill_and_negates_the_net_exactly(dims, seed):
    z0, z1 = _fields(*dims, seed)
    ab = difference(_s(z0), _s(z1))
    ba = difference(_s(z1), _s(z0))
    assert ba.v_fill == ab.v_cut
    assert ba.v_cut == ab.v_fill
    assert ba.v_net == -ab.v_net


@pytest.mark.req("P-017-12")
@settings(max_examples=200, deadline=None)
@given(dims=st.tuples(st.integers(2, 40), st.integers(2, 40)), seed=st.integers(0, 2**32 - 1), split=st.integers(1, 39))
def test_volumes_over_disjoint_polygons_add_up(dims, seed, split):
    ny, nx = dims
    z0, z1 = _fields(ny, nx, seed)
    cut = 1 + split % (nx - 1)  # the split column boundary, a multiple of the cell size: no centre lies on it
    cell = 2.0
    whole = difference(_s(z0), _s(z1), polygon=_rect(0, 0, nx * cell, ny * cell))
    left = difference(_s(z0), _s(z1), polygon=_rect(0, 0, cut * cell, ny * cell))
    right = difference(_s(z0), _s(z1), polygon=_rect(cut * cell, 0, nx * cell, ny * cell))
    assert whole.v_fill == pytest.approx(left.v_fill + right.v_fill, rel=1e-12, abs=1e-9)
    assert whole.v_cut == pytest.approx(left.v_cut + right.v_cut, rel=1e-12, abs=1e-9)
    assert whole.n_valid == left.n_valid + right.n_valid


@pytest.mark.req("P-017-13")
@pytest.mark.parametrize("cell", [4.0, 2.0, 1.0, 0.5])
@pytest.mark.parametrize(("a", "b", "c0"), [(0.01, 0.02, 1.0), (0.0, 0.05, 0.5), (0.003, 0.003, 10.0)])
def test_the_gridded_volume_of_a_quadratic_bowl_is_within_the_midpoint_bound(
    cell: float, a: float, b: float, c0: float
):
    length, width = 64.0, 48.0
    nx, ny = int(length / cell), int(width / cell)
    xc = (np.arange(nx) + 0.5) * cell
    yc = (np.arange(ny) + 0.5) * cell
    d = c0 + a * xc[None, :] ** 2 + b * yc[:, None] ** 2
    result = difference(_s(np.zeros((ny, nx)), cell=cell), _s(d, cell=cell))
    exact = c0 * length * width + a * length**3 * width / 3 + b * length * width**3 / 3
    area = length * width
    bound = area * cell**2 * (2 * a + 2 * b) / 24
    assert abs(result.v_fill - exact) <= bound * (1 + 1e-12) + 1e-12 * exact
    assert result.v_cut == 0.0


@pytest.mark.req("P-017-13")
@pytest.mark.parametrize("cell", [4.0, 2.0, 1.0, 0.5])
def test_the_gridded_volume_of_a_gaussian_mound_on_a_positive_base_is_within_the_midpoint_bound(cell: float) -> None:
    length, width, h, sigma, base = 80.0, 60.0, 5.0, 9.0, 1.0
    xm, ym = 40.0, 30.0
    nx, ny = int(length / cell), int(width / cell)
    xc = (np.arange(nx) + 0.5) * cell
    yc = (np.arange(ny) + 0.5) * cell
    d = base + h * np.exp(-(((xc[None, :] - xm) ** 2) + ((yc[:, None] - ym) ** 2)) / (2 * sigma**2))
    result = difference(_s(np.zeros((ny, nx)), cell=cell), _s(d, cell=cell))

    def axis(total: float, centre: float) -> float:  # integral of exp(-(t - centre)^2 / (2 sigma^2)) over [0, total]
        return (
            sigma
            * math.sqrt(math.pi / 2)
            * (math.erf((total - centre) / (sigma * math.sqrt(2))) - math.erf(-centre / (sigma * math.sqrt(2))))
        )

    exact = base * length * width + h * axis(length, xm) * axis(width, ym)
    bound = length * width * cell**2 * (2 * h / sigma**2) / 24  # max|d_xx| = max|d_yy| = h / sigma^2
    assert abs(result.v_fill - exact) <= bound * (1 + 1e-12) + 1e-12 * exact


@pytest.mark.req("P-017-14")
@settings(max_examples=200, deadline=None)
@given(
    dims=grid_dims,
    seed=st.integers(0, 2**32 - 1),
    c=st.floats(-1e3, 1e3),
    k=st.floats(0.0, 10.0),
)
def test_a_common_offset_changes_nothing_and_scaling_the_difference_scales_the_volumes(dims, seed, c, k):
    z0, z1 = _fields(*dims, seed)
    n = z0.size
    cell = 2.0
    base = difference(_s(z0), _s(z1))
    shifted = difference(_s(z0 + c), _s(z1 + c))
    zmax = float(max(np.abs(z0).max(), np.abs(z1).max()))
    tol = 1e-15 * (abs(c) + (k + 1) * zmax) * n * cell**2 + 1e-12
    assert abs(shifted.v_fill - base.v_fill) <= tol
    assert abs(shifted.v_cut - base.v_cut) <= tol
    scaled = difference(_s(z0), _s(z0 + k * (z1 - z0)))
    assert abs(scaled.v_fill - k * base.v_fill) <= tol
    assert abs(scaled.v_cut - k * base.v_cut) <= tol

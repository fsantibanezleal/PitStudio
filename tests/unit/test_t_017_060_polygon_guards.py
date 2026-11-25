"""T-017-060: E2 polygon tool, hostile polygons, lane gate (unit; the browser behaviour is in
web/e2e/e2-polygon-volume.spec.ts).

Requirements: FR-017-46, FR-017-47, NFR-017-04.

Spec: specs/017-planning-survey/spec.md
- FR-017-46: when the visitor closes a polygon on the E2 map, the web app computes V_cut, V_fill and V_net over the
  4 m web
  grids of the two epochs in the `volume` worker and shows them with the no-data fraction and the uncertainty
  bounds (the
  Python reference below);
- FR-017-47: a polygon with fewer than 3 vertices, more than 10^4 vertices, a self-intersection, a non-finite
  coordinate,
  or lying entirely outside the grid is rejected with the reason (the volume function and the E2 tab) and shows no
  volume;
- NFR-017-04: live polygon volume on T2 takes at most 1 s for a 2,048 x 2,048 grid and a 10^4-vertex polygon
  (measured by the
  lane-measurement suite, spec 018; the Python reference must at least accept such a polygon).
plan.md test strategy rows FR-017-46 / FR-017-47: fixture polygon volumes from the Python reference; invalid
polygons written
in the test.

Oracles:
- the 3 x 3 hand example of T-017-040 (cell 2 m, z0 = 10, z1 = [[10, 11, 12], [9, 10, 10], [8, 13, 10]]): the right
  two
  columns as the polygon give V_fill = 24, V_cut = 0, V_net = 24 over N = 6 cells; the uncertainty bounds from the
  spec
  formulas with sigma_0 = sigma_1 = 0.1 m: 4 sqrt(6) sqrt(0.02) = 1.38564 and 4 x 6 x sqrt(0.02) = 3.39411 m^3;
- invalid polygons written by hand: two vertices, a bow-tie (0,0), (4,4), (4,0), (0,4), a polygon whose vertex
  touches another
  edge (a "T"), NaN and infinite coordinates, a square far outside the grid; 10,001 vertices (a circle) against
  10,000;
- the known-volume scene of T-017-044 at the 4 m web grid: the closed-form frustum 2 pi 379 = 2,381.327 m^3 is
  gridded to
  2,369.684 m^3 (-0.489 %, computed by numpy in the test) inside the polygon (40, 80)-(80, 120) and the trench cut is
  exactly 2,880 m^3 inside (130, 60)-(170, 140): these are the fixture polygon volumes that the web fixture mode
  must show.

Expected public API (module `pitstudio.survey.polygon`, root environment, numpy only):
    class PolygonError(ValueError)           # `.reason`
    MAX_VERTICES = 10_000
    validate_polygon(vertices, *, extent: tuple[float, float, float, float]) -> np.ndarray
        extent = (x_min, y_min, x_max, y_max) of the grid; returns the (n, 2) float64 array; PolygonError whose reason
        contains "at least 3" (fewer than 3 vertices), "10000" (more than MAX_VERTICES), "finite", "self-intersect"
        (edges that cross or touch each other other than at the shared vertex of consecutive edges), or "outside" (no
        part of the polygon inside the extent); malformed input (not an (n, 2) numeric array) is also a PolygonError.
    polygon_volumes(before: Surface, after: Surface, polygon, *, rmse0_m: float, rmse1_m: float) -> dict
        validates the polygon against the surfaces' extent, then `difference` and `volume_uncertainty`: {"v_cut_m3",
        "v_fill_m3", "v_net_m3", "nodata_fraction", "n_valid", "uncertainty_m3": {"uncorrelated", "correlated"}}; a
        polygon
        error raises PolygonError and no volume is computed; InvalidSurfaceError when no valid cell lies inside.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pytest
from pitstudio.survey.difference import Surface
from pitstudio.survey.polygon import MAX_VERTICES, PolygonError, polygon_volumes, validate_polygon

Z0 = np.full((3, 3), 10.0)
Z1 = np.array([[10.0, 11.0, 12.0], [9.0, 10.0, 10.0], [8.0, 13.0, 10.0]])
EXTENT = (0.0, 0.0, 6.0, 6.0)
RIGHT_TWO_COLUMNS = [[2.0, 0.0], [6.0, 0.0], [6.0, 6.0], [2.0, 6.0]]


def _s(z, cell=2.0) -> Surface:
    return Surface(z=np.asarray(z, dtype=np.float64), origin_xy=(0.0, 0.0), cell_size_m=cell, nodata=None)


def _circle(n: int, radius: float = 90.0, centre: float = 100.0) -> np.ndarray:
    t = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([centre + radius * np.cos(t), centre + radius * np.sin(t)])


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-46
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-46")
def test_the_volumes_the_no_data_fraction_and_the_uncertainty_over_a_polygon_by_hand() -> None:
    r = polygon_volumes(_s(Z0), _s(Z1), RIGHT_TWO_COLUMNS, rmse0_m=0.1, rmse1_m=0.1)
    assert (r["v_fill_m3"], r["v_cut_m3"], r["v_net_m3"]) == (24.0, 0.0, 24.0)
    assert r["nodata_fraction"] == 0.0
    assert r["n_valid"] == 6
    assert r["uncertainty_m3"]["uncorrelated"] == pytest.approx(4 * math.sqrt(6) * math.sqrt(0.02), rel=1e-12)
    assert r["uncertainty_m3"]["correlated"] == pytest.approx(4 * 6 * math.sqrt(0.02), rel=1e-12)


@pytest.mark.req("FR-017-46")
def test_the_no_data_fraction_over_the_polygon_is_reported() -> None:
    z1 = Z1.copy()
    z1[0, 1] = np.nan  # one no-data cell inside the right two columns (6 cells)
    r = polygon_volumes(_s(Z0), _s(z1), RIGHT_TWO_COLUMNS, rmse0_m=0.1, rmse1_m=0.1)
    assert r["nodata_fraction"] == pytest.approx(1 / 6)
    assert r["n_valid"] == 5


def _known_scene_4m():
    n, cell = 50, 4.0
    xs = (np.arange(n) + 0.5) * cell
    x, y = np.meshgrid(xs, xs)
    cone = 6.0 * np.clip((15.0 - np.hypot(x - 60.0, y - 100.0)) / 8.0, 0.0, 1.0)
    trench = np.where((y >= 70) & (y < 130), -4.0 * np.clip((8.0 - np.abs(x - 150.0)) / 4.0, 0.0, 1.0), 0.0)
    return _s(np.zeros((n, n)), cell), _s(cone + trench, cell)


@pytest.mark.req("FR-017-46")
def test_the_fixture_polygon_volumes_of_the_known_volume_scene_at_the_4_m_web_grid() -> None:
    before, after = _known_scene_4m()
    frustum = polygon_volumes(before, after, [[40, 80], [80, 80], [80, 120], [40, 120]], rmse0_m=0.1, rmse1_m=0.1)
    assert frustum["v_fill_m3"] == pytest.approx(2369.684453799179, rel=1e-9)
    assert frustum["v_fill_m3"] == pytest.approx(2 * math.pi * 379, rel=0.006)  # within the gridding floor (-0.489 %)
    assert frustum["v_cut_m3"] == 0.0
    assert frustum["n_valid"] == 100
    assert frustum["uncertainty_m3"]["uncorrelated"] == pytest.approx(16 * 10 * math.sqrt(0.02), rel=1e-12)
    trench = polygon_volumes(before, after, [[130, 60], [170, 60], [170, 140], [130, 140]], rmse0_m=0.1, rmse1_m=0.1)
    assert trench["v_cut_m3"] == pytest.approx(2880.0, rel=1e-12)
    assert trench["v_fill_m3"] == 0.0


@pytest.mark.req("FR-017-46")
def test_a_polygon_partly_outside_the_grid_is_accepted_and_counts_only_cells_inside() -> None:
    r = polygon_volumes(
        _s(Z0), _s(Z1), [[-10.0, -10.0], [4.0, -10.0], [4.0, 10.0], [-10.0, 10.0]], rmse0_m=0.1, rmse1_m=0.1
    )
    assert r["n_valid"] == 6  # the first two columns (centres 1 and 3 < 4)
    assert (r["v_fill_m3"], r["v_cut_m3"]) == (16.0, 12.0)  # cols 0, 1: fill 1 + 3 = 4 -> 16; cut 1 + 2 = 3 -> 12


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-47
# ----------------------------------------------------------------------------------------------------------------------

BOW_TIE = [[0.0, 0.0], [4.0, 4.0], [4.0, 0.0], [0.0, 4.0]]
T_TOUCH = [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [2.0, 0.0], [0.0, 4.0]]  # vertex (2, 0) lies on the edge (0,0)-(4,0)
OUTSIDE = [[100.0, 100.0], [110.0, 100.0], [110.0, 110.0], [100.0, 110.0]]


@pytest.mark.req("FR-017-47")
@pytest.mark.parametrize(
    ("polygon", "word"),
    [
        ([], "at least 3"),
        ([[0.0, 0.0]], "at least 3"),
        ([[0.0, 0.0], [4.0, 0.0]], "at least 3"),
        (BOW_TIE, "self-intersect"),
        (T_TOUCH, "self-intersect"),
        ([[0.0, 0.0], [4.0, 0.0], [4.0, float("nan")]], "finite"),
        ([[0.0, 0.0], [4.0, float("inf")], [4.0, 4.0]], "finite"),
        ([[0.0, 0.0], [float("-inf"), 0.0], [4.0, 4.0]], "finite"),
        (OUTSIDE, "outside"),
        ([[-50.0, -50.0], [-40.0, -50.0], [-40.0, -40.0]], "outside"),
    ],
    ids=["empty", "one", "two", "bow-tie", "t-touch", "nan", "inf", "neg-inf", "outside-high", "outside-low"],
)
def test_hostile_polygons_are_rejected_with_the_reason_and_no_volume(polygon, word: str) -> None:
    with pytest.raises(PolygonError) as info:
        validate_polygon(polygon, extent=EXTENT)
    assert word in info.value.reason
    with pytest.raises(PolygonError):
        polygon_volumes(_s(Z0), _s(Z1), polygon, rmse0_m=0.1, rmse1_m=0.1)


@pytest.mark.req("FR-017-47")
@pytest.mark.parametrize("bad", [None, "polygon", [[0.0, 0.0, 0.0]] * 3, [[0.0], [1.0], [2.0]], [["a", "b"]] * 3, 5])
def test_malformed_polygon_input_is_a_polygon_error(bad) -> None:
    with pytest.raises(PolygonError):
        validate_polygon(bad, extent=EXTENT)


@pytest.mark.req("FR-017-47")
def test_the_vertex_cap_is_10000() -> None:
    assert MAX_VERTICES == 10_000
    big = (0.0, 0.0, 200.0, 200.0)
    assert validate_polygon(_circle(MAX_VERTICES), extent=big).shape == (MAX_VERTICES, 2)
    with pytest.raises(PolygonError) as info:
        validate_polygon(_circle(MAX_VERTICES + 1), extent=big)
    assert "10000" in info.value.reason


@pytest.mark.req("FR-017-47")
def test_a_valid_triangle_is_accepted_and_returned_as_float64() -> None:
    out = validate_polygon([[0, 0], [4, 0], [0, 4]], extent=EXTENT)
    assert out.dtype == np.float64
    assert out.shape == (3, 2)


@pytest.mark.req("FR-017-47")
def test_no_valid_cell_inside_the_polygon_is_refused_by_the_volume_function() -> None:
    all_nodata = np.full((3, 3), np.nan)
    with pytest.raises(ValueError, match=r"."):  # InvalidSurfaceError is a ValueError (FR-017-48)
        polygon_volumes(_s(Z0), _s(all_nodata), RIGHT_TWO_COLUMNS, rmse0_m=0.1, rmse1_m=0.1)


# ----------------------------------------------------------------------------------------------------------------------
# NFR-017-04 (reference side)
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("NFR-017-04")
def test_a_10000_vertex_polygon_over_a_2048_x_2048_grid_is_accepted_and_integrated_by_the_reference() -> None:
    z0 = np.zeros((2048, 2048))
    z1 = np.full((2048, 2048), 0.5)
    polygon = _circle(MAX_VERTICES, radius=3000.0, centre=4096.0)  # inside the 8,192 m wide grid at 4 m cells
    started = time.perf_counter()
    r = polygon_volumes(_s(z0, 4.0), _s(z1, 4.0), polygon, rmse0_m=0.1, rmse1_m=0.1)
    elapsed = time.perf_counter() - started
    area_cells = r["n_valid"] * 16.0
    assert r["v_fill_m3"] == pytest.approx(0.5 * area_cells, rel=1e-12)
    assert area_cells == pytest.approx(
        math.pi * 3000.0**2, rel=2e-3
    )  # the disc of the polygon, to the cell rasterisation
    assert elapsed < 60.0  # the reference is not the browser: a generous bound, the 1 s limit is the web lane gate

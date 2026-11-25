# ruff: noqa: E501, PT018
"""T-007-061: hostile DEMs and routing requests are rejected with `InvalidDEM` or `InvalidRouteRequest`, naming the first offending cell or field and the number of offending cells.

Requirements: FR-007-36, FR-007-45.

Spec: specs/007-haulage-dispatch/spec.md FR-007-36 (if a DEM has a NaN or infinite cell outside its declared nodata mask, a cell size <= 0 or non-finite, or more than 4096 x 4096 cells (pipeline) or 1024 x 1024 cells (browser), or if g_max is non-finite,
<= 0 or > 1, or the start or goal is outside the grid or on a nodata cell, then the router rejects the request with `InvalidDEM` or `InvalidRouteRequest`; the error names the first offending cell or field and the number of offending cells), FR-007-37 (an unreachable
goal is a value, not an error) and FR-007-35 (inputs of the request: truck mass, rolling resistance, efficiency).

Oracle: hand-built hostile inputs, one violation each, with the first offending cell in row-major order and the count worked out by hand in the parametrisation; the boundary values that must be accepted (g_max = 1, a 4096 x 4096 DEM) written out.

Expected API (module `pitstudio.haulage.routing`; errors in `pitstudio.haulage.errors`, both subclasses of `HaulError`):
    errors.InvalidDEM(HaulError)            attributes: `cell` ((row, col) of the first offending cell in row-major order, or None when the violation is not about one cell), `count` (the number of offending cells; 1 for a scalar field), `field` ("z", "cell_m", "nodata" or "shape");
                                            the message contains "(row, col)" of the first offending cell when there is one, and the count.
    errors.InvalidRouteRequest(HaulError)   attributes: `field` ("start", "goal", "g_max", "mass_kg", "rr_pct", "eta", "g") and `value` (the offending value); the message contains the field name and repr of the value.
    Both are raised by `find_route(Dem(...), start, goal, ...)` (construction of the `Dem` may raise them too; the tests accept either place), before any search starts.
    Limits: more than 4096 x 4096 cells (rows x cols > 16,777,216) -> InvalidDEM (field "shape"), checked from the array's shape before its elements are read; the browser limit 1024 x 1024 belongs to the TypeScript port (T-007-064).
"""

from __future__ import annotations

import numpy as np
import pytest

from pitstudio.haulage.errors import HaulError, InvalidDEM, InvalidRouteRequest
from pitstudio.haulage.routing import Dem, NoFeasibleRoute, Route, find_route

G = 9.80665
OK = {"mass_kg": 400_000.0, "rr_pct": 3.0, "g_max": 0.1, "eta": 0.9, "g": G}


def go(z, *, cell_m=10.0, nodata=None, start=(0, 0), goal=(1, 1), **over):
    kw = {**OK, **over}
    return find_route(Dem(z, cell_m, nodata), start, goal, **kw)


def flat(rows=4, cols=5):
    return np.zeros((rows, cols))


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-36: the DEM
# ---------------------------------------------------------------------------------------------------------------------
def with_bad(cells, value):
    z = flat()
    for c in cells:
        z[c] = value
    return z


@pytest.mark.req("FR-007-36")
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf], ids=["nan", "inf", "-inf"])
@pytest.mark.parametrize(
    ("cells", "first", "count"),
    [
        ([(2, 3)], (2, 3), 1),
        ([(2, 3), (1, 4)], (1, 4), 2),  # row-major: (1, 4) comes before (2, 3)
        ([(3, 4), (0, 2), (2, 2), (0, 3)], (0, 2), 4),
        ([(r, c) for r in range(4) for c in range(5)], (0, 0), 20),
    ],
)
def test_a_non_finite_cell_outside_the_nodata_mask_names_the_first_cell_and_the_count(bad, cells, first, count):
    with pytest.raises(InvalidDEM) as ei:
        go(with_bad(cells, bad), start=(0, 0), goal=(3, 4))
    e = ei.value
    assert isinstance(e, HaulError)
    assert (e.cell, e.count, e.field) == (first, count, "z")
    assert f"({first[0]}, {first[1]})" in str(e) and str(count) in str(e)


@pytest.mark.req("FR-007-36")
def test_non_finite_cells_inside_the_nodata_mask_are_allowed_and_never_entered():
    z = flat(3, 5)
    z[1, 2] = np.nan
    z[0, 2] = np.inf
    nodata = np.zeros((3, 5), bool)
    nodata[1, 2] = nodata[0, 2] = True
    res = go(z, nodata=nodata, start=(0, 0), goal=(2, 4))
    assert isinstance(res, Route) and all(not nodata[c] for c in res.cells)
    assert np.isfinite(res.cost_j)


@pytest.mark.req("FR-007-36")
def test_a_non_finite_cell_that_the_mask_does_not_cover_is_counted_even_when_others_are_masked():
    z = flat(3, 5)
    z[0, 1] = np.nan  # masked
    z[2, 0] = np.nan  # not masked: the first and only offender
    nodata = np.zeros((3, 5), bool)
    nodata[0, 1] = True
    with pytest.raises(InvalidDEM) as ei:
        go(z, nodata=nodata, start=(0, 0), goal=(2, 4))
    assert (ei.value.cell, ei.value.count) == ((2, 0), 1)


@pytest.mark.req("FR-007-36")
@pytest.mark.parametrize(
    "cell_m", [0.0, -1.0, -0.0, float("nan"), float("inf"), float("-inf"), "10", None, True, [10.0]]
)
def test_a_cell_size_that_is_not_a_positive_finite_number_is_rejected(cell_m):
    with pytest.raises((InvalidDEM, TypeError)) as ei:
        go(flat(), cell_m=cell_m)
    if isinstance(ei.value, InvalidDEM):
        assert ei.value.field == "cell_m" and ei.value.count == 1


@pytest.mark.req("FR-007-36")
@pytest.mark.parametrize(
    "shape", [(4097, 4097), (1, 16_777_217), (16_777_217, 1), (8192, 2049)], ids=lambda s: "x".join(map(str, s))
)
def test_more_than_4096_by_4096_cells_is_rejected_from_the_shape_alone(shape):
    z = np.broadcast_to(np.float64(0.0), shape)  # no memory is allocated for this view
    with pytest.raises(InvalidDEM) as ei:
        go(z, start=(0, 0), goal=(0, 0))
    assert ei.value.field == "shape" and ei.value.count == shape[0] * shape[1]
    assert str(shape[0] * shape[1]) in str(ei.value)


@pytest.mark.req("FR-007-36")
def test_exactly_4096_by_4096_cells_is_accepted():
    z = np.broadcast_to(np.float64(5.0), (4096, 4096))
    res = go(z, start=(10, 10), goal=(10, 10))
    assert isinstance(res, Route) and res.cells == [(10, 10)] and res.cost_j == 0.0


@pytest.mark.req("FR-007-36")
@pytest.mark.parametrize(
    "z",
    [
        np.zeros(5),
        np.zeros((2, 2, 2)),
        np.zeros((0, 5)),
        np.zeros((5, 0)),
        np.zeros((0, 0)),
        np.array([["a", "b"], ["c", "d"]]),
        np.array([[None, 1.0], [2.0, 3.0]], dtype=object),
        5.0,
        None,
        [[0.0, 0.0], [0.0, 0.0]] * 0,
    ],
    ids=["1d", "3d", "0x5", "5x0", "0x0", "strings", "objects", "scalar", "none", "empty-list"],
)
def test_a_dem_that_is_not_a_non_empty_two_dimensional_numeric_array_is_rejected(z):
    with pytest.raises((InvalidDEM, TypeError)):
        go(z, start=(0, 0), goal=(0, 0))


@pytest.mark.req("FR-007-36")
@pytest.mark.parametrize(
    "nodata",
    [
        np.zeros((4, 4), bool),
        np.zeros((5, 4), bool),
        np.zeros(20, bool),
        np.zeros((4, 5), np.float64),
        np.zeros((4, 5), np.int64),
        "mask",
    ],
    ids=["wrong-cols", "wrong-rows", "1d", "float-dtype", "int-dtype", "string"],
)
def test_a_nodata_mask_of_another_shape_or_dtype_is_rejected(nodata):
    with pytest.raises((InvalidDEM, TypeError)) as ei:
        go(flat(), nodata=nodata, start=(0, 0), goal=(3, 4))
    if isinstance(ei.value, InvalidDEM):
        assert ei.value.field == "nodata"


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-36: g_max and the endpoints
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-36")
@pytest.mark.parametrize(
    "g_max",
    [float("nan"), float("inf"), float("-inf"), 0.0, -0.0, -0.1, 1.000001, 2.0, 1e300, "0.1", None, True, [0.1]],
)
def test_g_max_that_is_non_finite_zero_negative_or_above_one_is_rejected(g_max):
    with pytest.raises((InvalidRouteRequest, TypeError)) as ei:
        go(flat(), g_max=g_max)
    if isinstance(ei.value, InvalidRouteRequest):
        assert ei.value.field == "g_max" and "g_max" in str(ei.value) and repr(g_max) in str(ei.value)


@pytest.mark.req("FR-007-36")
@pytest.mark.parametrize("g_max", [1.0, 0.5, 1e-9, 5e-324])
def test_g_max_inside_zero_exclusive_one_inclusive_is_accepted(g_max):
    res = go(flat(), g_max=g_max)
    assert isinstance(res, Route)  # a flat DEM has no grade at all


@pytest.mark.req("FR-007-36")
@pytest.mark.parametrize("which", ["start", "goal"])
@pytest.mark.parametrize("cell", [(-1, 0), (0, -1), (4, 0), (0, 5), (4, 5), (100, 100), (-4, -5), (2**40, 0)])
def test_an_endpoint_outside_the_grid_is_rejected_naming_the_field_and_the_cell(which, cell):
    with pytest.raises(InvalidRouteRequest) as ei:
        go(flat(), **{which: cell, ("goal" if which == "start" else "start"): (1, 1)})
    e = ei.value
    assert e.field == which and tuple(e.value) == cell and which in str(e) and str(cell) in str(e)


@pytest.mark.req("FR-007-36")
@pytest.mark.parametrize("which", ["start", "goal"])
def test_an_endpoint_on_a_nodata_cell_is_rejected(which):
    nodata = np.zeros((4, 5), bool)
    nodata[2, 3] = True
    with pytest.raises(InvalidRouteRequest) as ei:
        go(flat(), nodata=nodata, **{which: (2, 3), ("goal" if which == "start" else "start"): (0, 0)})
    assert ei.value.field == which and which in str(ei.value)


@pytest.mark.req("FR-007-36")
@pytest.mark.parametrize("which", ["start", "goal"])
@pytest.mark.parametrize(
    "bad",
    [
        (0.0, 0.0),
        (0.5, 1),
        ("0", "0"),
        (True, False),
        (None, None),
        (0,),
        (0, 0, 0),
        "00",
        None,
        7,
        [0, 0.5],
        (float("nan"), 0),
        (np.int64(1), np.int64(2)),
    ],
    ids=repr,
)
def test_malformed_endpoints_are_rejected_except_integer_pairs(which, bad):
    other = (1, 1)
    kw = {which: bad, ("goal" if which == "start" else "start"): other}
    if (
        isinstance(bad, tuple)
        and len(bad) == 2
        and all(isinstance(v, (int, np.integer)) and not isinstance(v, bool) for v in bad)
    ):
        assert isinstance(go(flat(), **kw), (Route, NoFeasibleRoute))  # numpy integers are integers
        return
    with pytest.raises((InvalidRouteRequest, TypeError)) as ei:
        go(flat(), **kw)
    if isinstance(ei.value, InvalidRouteRequest):
        assert ei.value.field == which


@pytest.mark.req("FR-007-36")
def test_the_whole_grid_being_nodata_rejects_the_endpoints_and_does_not_search():
    nodata = np.ones((4, 5), bool)
    with pytest.raises(InvalidRouteRequest):
        go(flat(), nodata=nodata, start=(0, 0), goal=(3, 4))


@pytest.mark.req("FR-007-37")
def test_an_unreachable_goal_is_a_value_not_an_error_even_in_a_hostile_looking_grid():
    nodata = np.zeros((4, 5), bool)
    nodata[:, 2] = True  # a wall of no-data cells
    res = go(flat(), nodata=nodata, start=(0, 0), goal=(3, 4))
    assert isinstance(res, NoFeasibleRoute)


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-45 (router side): the truck parameters
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mass_kg", 0.0), ("mass_kg", -1.0), ("mass_kg", float("nan")), ("mass_kg", float("inf")), ("mass_kg", "400000"), ("mass_kg", None),
        ("rr_pct", -0.1), ("rr_pct", float("nan")), ("rr_pct", float("inf")), ("rr_pct", "3"),
        ("eta", 0.0), ("eta", -0.5), ("eta", 1.0000001), ("eta", float("nan")), ("eta", float("inf")), ("eta", None),
        ("g", 0.0), ("g", -9.8), ("g", float("nan")), ("g", float("inf")),
    ],
)  # fmt: skip
def test_non_physical_truck_parameters_are_rejected_naming_the_field(field, value):
    with pytest.raises((InvalidRouteRequest, TypeError)) as ei:
        go(flat(), **{field: value})
    if isinstance(ei.value, InvalidRouteRequest):
        assert ei.value.field == field and field in str(ei.value)


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize("value", [0.0, 3.0, 20.0])
def test_a_zero_rolling_resistance_is_allowed(value):
    assert isinstance(go(flat(), rr_pct=value), Route)


@pytest.mark.req("FR-007-36")
def test_a_rejected_request_leaves_the_inputs_untouched_and_never_returns_a_partial_route():
    z = with_bad([(1, 1)], np.nan)
    before = z.copy()
    with pytest.raises(InvalidDEM):
        go(z, start=(0, 0), goal=(3, 4))
    assert np.array_equal(z, before, equal_nan=True)

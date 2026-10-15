# ruff: noqa: E501, PT018
"""T-007-060: the least-energy grade-constrained A* router against networkx Dijkstra on dyadic DEMs, grade feasibility, admissibility, `NoFeasibleRoute`, the five metamorphic relations and the golden vectors.

Requirements: FR-007-35, FR-007-37, P-007-17, P-007-18.

Spec: specs/007-haulage-dispatch/spec.md FR-007-35 (the router `pitstudio.haulage.routing` returns the least-energy feasible 8-neighbour path between two DEM cells; an edge is feasible only if |dz| / L <= g_max; the edge cost is
c(e) = (m g / eta) max(0, RR/100 L + dz); the search uses the admissible heuristic h(n) = (m g / eta) max(0, RR/100 d_xy + z_goal - z_n); ties are broken by (f, g, cell index)), FR-007-37 (when no feasible path exists under the grade limit the router
returns `NoFeasibleRoute`, a value and not an exception, after expanding each feasible cell at most once), P-007-17 (on random DEMs of <= 64 x 64 cells with dyadic elevations k x 2^-10 m, |z| <= 2^12 m, g_max in [0.02, 0.3], the A* cost equals the networkx
Dijkstra cost on the same feasible graph at rtol 1e-12; every returned edge satisfies the grade limit exactly; h(n) never exceeds the true cost-to-go, computed by Dijkstra from the goal on the reverse graph), P-007-18 ((i) mirroring the DEM and the start and goal gives
the same cost; (ii) adding a dyadic constant to every elevation gives the same path and cost exactly; (iii) raising RR never lowers the cost; (iv) raising g_max never raises the cost; (v) on a flat DEM the cost equals (m g / eta)(RR/100)(octile distance); rtol 1e-12 except
(ii) exact) and plan.md (integer cell index for ties, nodata mask).

Oracle: `networkx` Dijkstra on the feasible graph built in tests/support/p007_routing.py (edges, costs and the reverse graph written there from the formulas above), the closed-form flat-DEM cost, mirrored and shifted copies of the same problem, and the golden vectors
tests/fixtures/haulage/routing/astar_goldens.json written by an independent heapq A* of the test author (cross-checked against networkx; random cases keep only optima that do not depend on the tie rule). Gravity is passed explicitly (9.80665 m/s^2).

Expected API (module `pitstudio.haulage.routing`; errors in `pitstudio.haulage.errors`):
    Dem(z: numpy.ndarray, cell_m: float, nodata: numpy.ndarray | None = None)     a dataclass: z float64 [rows, cols] metres, cell size in metres (square cells), nodata bool [rows, cols] (True = no data; such cells are never entered)
    find_route(dem, start, goal, *, mass_kg, rr_pct, g_max, eta=1.0, g=None) -> Route | NoFeasibleRoute
        start, goal: (row, col); mass_kg gross truck mass in kg; rr_pct rolling resistance in percent; g_max the grade limit as a fraction (dz / L); eta drive efficiency in (0, 1]; g gravity in m/s^2 (None = the knowledge-table value of `minephys`).
        Returns a `Route`: cells (list of (row, col) from start to goal, 8-neighbour steps), cost_j (float, joules at the source = K x sum of edge costs, K = mass_kg g / eta), expanded (int, the number of cells expanded) -
        or a `NoFeasibleRoute` value with `expanded` (the number of feasible cells expanded, each at most once); it never raises for a well-formed request with no path.
        Ties among equal priorities are broken by (f, g, cell index = row x cols + col), all ascending. start == goal returns the one-cell route of cost 0.
    heuristic(dem, cell, goal, *, mass_kg, rr_pct, eta=1.0, g=None) -> float      the formula of FR-007-35 with d_xy the Euclidean distance in metres between the cell centres
        evaluated as K x max(0, RR/100 x d_xy + (z_goal - z_n)) with the elevation difference formed first and K = mass_kg x g / eta; (the order matters: it makes f invariant under a dyadic shift of every elevation,
        which relation (ii) of P-007-18 demands exactly, because equal-cost paths do occur and the tie is decided by f).
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_routing as R

from pitstudio.haulage.routing import Dem, NoFeasibleRoute, Route, find_route, heuristic

SETTINGS = settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.filter_too_much],
)
MASS = 400_000.0


def route(z, start, goal, *, rr=3.0, g_max=0.12, eta=0.9, mass=MASS, cell=10.0, nodata=None):
    return find_route(Dem(z, cell, nodata), start, goal, mass_kg=mass, rr_pct=rr, g_max=g_max, eta=eta, g=R.G0)


def problem(seed: int, rows: int, cols: int, g_max: float, with_nodata: bool = False):
    rng = np.random.default_rng(seed)
    z = R.dyadic_dem(rng, rows, cols, relief=float(rng.integers(1, 4)))
    nodata = None
    if with_nodata:
        nodata = rng.random((rows, cols)) < 0.12
    free = [(r, c) for r in range(rows) for c in range(cols) if nodata is None or not nodata[r, c]]
    start, goal = (free[int(rng.integers(0, len(free)))] for _ in range(2))
    return z, nodata, start, goal


def assert_valid_path(z, nodata, cells, start, goal, g_max, cell=10.0):
    assert cells[0] == start and cells[-1] == goal
    for a, b in itertools.pairwise(cells):
        assert max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1, (a, b)  # 8-neighbour steps only
        ok, _length, _dz = R.feasible_edge(z, cell, a, b, g_max)
        assert ok, (a, b)  # the grade limit holds on every edge, exactly
    if nodata is not None:
        assert not any(nodata[c] for c in cells)
    assert len(set(cells)) == len(
        cells
    )  # a least-cost path with non-negative costs revisits nothing here (strictly positive costs on the random DEMs)


# ---------------------------------------------------------------------------------------------------------------------
# P-007-17: A* against networkx Dijkstra
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("P-007-17")
@SETTINGS
@given(
    seed=st.integers(0, 2**31 - 1),
    rows=st.integers(2, 12),
    cols=st.integers(2, 12),
    g_max=st.floats(0.02, 0.3),
    rr=st.floats(0.5, 10.0),
    eta=st.floats(0.5, 1.0),
    mass=st.floats(2e4, 7e5),
    nd=st.booleans(),
)
def test_the_astar_cost_equals_the_networkx_dijkstra_cost_and_every_edge_respects_the_grade_limit(
    seed, rows, cols, g_max, rr, eta, mass, nd
):
    z, nodata, start, goal = problem(seed, rows, cols, g_max, nd)
    k = R.k_of(mass, eta)
    res = route(z, start, goal, rr=rr, g_max=g_max, eta=eta, mass=mass, nodata=nodata)
    want = R.nx_distance(z, 10.0, nodata, g_max, k, rr, start, goal)
    if want is None:
        assert isinstance(res, NoFeasibleRoute)
        return
    assert isinstance(res, Route)
    assert res.cost_j == pytest.approx(want, rel=1e-12, abs=1e-9)
    assert_valid_path(z, nodata, res.cells, start, goal, g_max)
    assert R.path_cost(z, 10.0, res.cells, k, rr) == pytest.approx(
        res.cost_j, rel=1e-12, abs=1e-9
    )  # the reported cost is the cost of the reported path
    assert 1 <= res.expanded <= rows * cols


@pytest.mark.req("P-007-17")
@pytest.mark.parametrize("seed", [11, 12, 13])
def test_the_astar_cost_equals_the_networkx_cost_on_64_by_64_dems(seed):
    z, nodata, start, goal = problem(seed, 64, 64, 0.15)
    k = R.k_of(MASS, 0.9)
    want = R.nx_distance(z, 10.0, nodata, 0.15, k, 3.0, start, goal)
    res = route(z, start, goal, g_max=0.15)
    if want is None:
        assert isinstance(res, NoFeasibleRoute)
    else:
        assert res.cost_j == pytest.approx(want, rel=1e-12)
        assert_valid_path(z, nodata, res.cells, start, goal, 0.15)


@pytest.mark.req("P-007-17")
@SETTINGS
@given(
    seed=st.integers(0, 2**31 - 1),
    rows=st.integers(2, 10),
    cols=st.integers(2, 10),
    g_max=st.floats(0.05, 0.3),
    rr=st.floats(0.5, 10.0),
    eta=st.floats(0.5, 1.0),
)
def test_the_heuristic_never_exceeds_the_true_cost_to_go_and_vanishes_at_the_goal(seed, rows, cols, g_max, rr, eta):
    z, nodata, _start, goal = problem(seed, rows, cols, g_max, True)
    k = R.k_of(MASS, eta)
    dem = Dem(z, 10.0, nodata)
    to_go = R.nx_cost_to_go(z, 10.0, nodata, g_max, k, rr, goal)
    assert heuristic(dem, goal, goal, mass_kg=MASS, rr_pct=rr, eta=eta, g=R.G0) == 0.0
    for cell, true_cost in to_go.items():
        h = heuristic(dem, cell, goal, mass_kg=MASS, rr_pct=rr, eta=eta, g=R.G0)
        assert h >= 0.0
        assert h <= true_cost * (1 + 1e-12) + 1e-9, (cell, h, true_cost)  # admissible
        assert h == pytest.approx(
            R.heuristic(z, 10.0, cell, goal, k, rr), rel=1e-12, abs=1e-9
        )  # the formula of FR-007-35


@pytest.mark.req("FR-007-37")
@SETTINGS
@given(seed=st.integers(0, 2**31 - 1), rows=st.integers(3, 12), cols=st.integers(3, 12), g_max=st.floats(0.02, 0.1))
def test_no_feasible_route_is_a_value_after_expanding_each_feasible_cell_at_most_once(seed, rows, cols, g_max):
    z, nodata, start, goal = problem(seed, rows, cols, g_max, True)
    reach = R.reachable(z, 10.0, nodata, start, g_max)
    assume(goal not in reach and len(reach) >= 1)
    res = route(z, start, goal, g_max=g_max, nodata=nodata)  # must not raise
    assert isinstance(res, NoFeasibleRoute) and not isinstance(res, Exception)
    assert res.expanded == len(reach)  # every feasible (reachable) cell expanded exactly once, none twice


@pytest.mark.req("FR-007-37")
def test_a_steep_ridge_gives_no_feasible_route_and_a_higher_limit_opens_it():
    z = np.zeros((9, 9))
    z[:, 4] = 3.0  # a 3 m wall over 10 m cells: grade 0.3
    blocked = route(z, (4, 0), (4, 8), g_max=0.1)
    assert isinstance(blocked, NoFeasibleRoute) and blocked.expanded == 36  # the 4 x 9 cells west of the wall
    opened = route(z, (4, 0), (4, 8), g_max=0.35)
    assert isinstance(opened, Route)
    assert_valid_path(z, None, opened.cells, (4, 0), (4, 8), 0.35)


@pytest.mark.req("FR-007-35")
def test_the_grade_limit_is_inclusive_and_exact():
    z = np.zeros((1, 3))
    z[0, 1] = 1.0  # a 1 m step over 10 m: grade exactly 0.1 (dyadic elevation)
    z[0, 2] = 1.0
    assert isinstance(route(z, (0, 0), (0, 2), g_max=0.1), Route)  # |dz| / L = 0.1 <= 0.1
    assert isinstance(route(z, (0, 0), (0, 2), g_max=0.0999999999), NoFeasibleRoute)


@pytest.mark.req("FR-007-35")
def test_start_equal_to_goal_is_the_one_cell_route_of_cost_zero():
    res = route(np.zeros((3, 3)), (1, 1), (1, 1))
    assert isinstance(res, Route) and res.cells == [(1, 1)] and res.cost_j == 0.0


@pytest.mark.req("FR-007-35")
def test_the_search_is_deterministic_and_leaves_its_inputs_untouched():
    z, nodata, start, goal = problem(5, 16, 16, 0.2, True)
    z0, nd0 = z.copy(), nodata.copy()
    a = route(z, start, goal, g_max=0.2, nodata=nodata)
    b = route(z, start, goal, g_max=0.2, nodata=nodata)
    assert a == b
    assert np.array_equal(z, z0) and np.array_equal(nodata, nd0)


@pytest.mark.req("FR-007-35")
@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_float32_and_float64_dems_give_the_same_route_on_dyadic_elevations(dtype):
    z, _nd, start, goal = problem(21, 12, 12, 0.2)
    ref = route(z, start, goal, g_max=0.2)
    got = find_route(Dem(z.astype(dtype), 10.0), start, goal, mass_kg=MASS, rr_pct=3.0, g_max=0.2, eta=0.9, g=R.G0)
    assert (
        (got.cells, got.cost_j) == (ref.cells, ref.cost_j)
        if isinstance(ref, Route)
        else isinstance(got, NoFeasibleRoute)
    )


# ---------------------------------------------------------------------------------------------------------------------
# P-007-18: metamorphic relations
# ---------------------------------------------------------------------------------------------------------------------
sizes = st.tuples(st.integers(3, 12), st.integers(3, 12))


@pytest.mark.req("P-007-18")
@SETTINGS
@given(seed=st.integers(0, 2**31 - 1), size=sizes, g_max=st.floats(0.05, 0.3), rr=st.floats(0.5, 10.0))
def test_mirroring_the_dem_and_the_endpoints_gives_the_same_cost(seed, size, g_max, rr):
    rows, cols = size
    z, nodata, start, goal = problem(seed, rows, cols, g_max, True)
    base = route(z, start, goal, rr=rr, g_max=g_max, nodata=nodata)
    flips = {
        "columns": (lambda a: a[:, ::-1], lambda c: (c[0], cols - 1 - c[1])),
        "rows": (lambda a: a[::-1, :], lambda c: (rows - 1 - c[0], c[1])),
        "both": (lambda a: a[::-1, ::-1], lambda c: (rows - 1 - c[0], cols - 1 - c[1])),
    }
    for name, (fa, fc) in flips.items():
        got = route(
            np.ascontiguousarray(fa(z)),
            fc(start),
            fc(goal),
            rr=rr,
            g_max=g_max,
            nodata=None if nodata is None else np.ascontiguousarray(fa(nodata)),
        )
        if isinstance(base, NoFeasibleRoute):
            assert isinstance(got, NoFeasibleRoute), name
        else:
            assert isinstance(got, Route) and got.cost_j == pytest.approx(base.cost_j, rel=1e-12, abs=1e-9), name


@pytest.mark.req("P-007-18")
@SETTINGS
@given(seed=st.integers(0, 2**31 - 1), size=sizes, g_max=st.floats(0.05, 0.3), shift_units=st.integers(-(2**21), 2**21))
def test_adding_a_dyadic_constant_to_every_elevation_gives_the_same_path_and_cost_exactly(
    seed, size, g_max, shift_units
):
    z, nodata, start, goal = problem(seed, size[0], size[1], g_max, True)
    shift = shift_units / 1024.0
    assume(float(np.abs(z + shift).max()) <= 4096.0)
    a = route(z, start, goal, g_max=g_max, nodata=nodata)
    b = route(z + shift, start, goal, g_max=g_max, nodata=nodata)
    if isinstance(a, NoFeasibleRoute):
        assert isinstance(b, NoFeasibleRoute) and b.expanded == a.expanded
    else:
        assert b.cells == a.cells and b.cost_j == a.cost_j  # exact: dyadic differences are exact in float64


@pytest.mark.req("P-007-18")
@SETTINGS
@given(
    seed=st.integers(0, 2**31 - 1),
    size=sizes,
    g_max=st.floats(0.05, 0.3),
    rr=st.floats(0.5, 8.0),
    extra=st.floats(0.0, 5.0),
)
def test_raising_the_rolling_resistance_never_lowers_the_cost(seed, size, g_max, rr, extra):
    z, nodata, start, goal = problem(seed, size[0], size[1], g_max, True)
    a = route(z, start, goal, rr=rr, g_max=g_max, nodata=nodata)
    b = route(z, start, goal, rr=rr + extra, g_max=g_max, nodata=nodata)
    assert isinstance(a, Route) == isinstance(b, Route)  # feasibility does not depend on RR
    if isinstance(a, Route):
        assert b.cost_j >= a.cost_j * (1 - 1e-12)


@pytest.mark.req("P-007-18")
@SETTINGS
@given(
    seed=st.integers(0, 2**31 - 1),
    size=sizes,
    g_max=st.floats(0.03, 0.25),
    more=st.floats(0.0, 0.1),
    rr=st.floats(0.5, 8.0),
)
def test_raising_the_grade_limit_never_raises_the_cost(seed, size, g_max, more, rr):
    z, nodata, start, goal = problem(seed, size[0], size[1], g_max, True)
    a = route(z, start, goal, rr=rr, g_max=g_max, nodata=nodata)
    b = route(z, start, goal, rr=rr, g_max=g_max + more, nodata=nodata)
    if isinstance(a, Route):
        assert isinstance(b, Route) and b.cost_j <= a.cost_j * (
            1 + 1e-12
        )  # a feasible path stays feasible and optimal cost can only fall


@pytest.mark.req("P-007-18")
@SETTINGS
@given(
    rows=st.integers(1, 14), cols=st.integers(1, 14), rr=st.floats(0.5, 10.0), eta=st.floats(0.5, 1.0), mass=st.floats(2e4, 7e5),
    r0=st.integers(0, 13), c0=st.integers(0, 13), r1=st.integers(0, 13), c1=st.integers(0, 13), level_units=st.integers(-(2**21), 2**21),
)  # fmt: skip
def test_on_a_flat_dem_the_cost_is_the_rolling_resistance_times_the_octile_distance(
    rows, cols, rr, eta, mass, r0, c0, r1, c1, level_units
):
    start, goal = (r0 % rows, c0 % cols), (r1 % rows, c1 % cols)
    z = np.full((rows, cols), level_units / 1024.0)
    res = route(z, start, goal, rr=rr, g_max=0.1, eta=eta, mass=mass)
    want = R.k_of(mass, eta) * rr / 100.0 * 10.0 * R.octile(start[0] - goal[0], start[1] - goal[1])
    assert isinstance(res, Route)
    assert res.cost_j == pytest.approx(want, rel=1e-12, abs=1e-9)


# ---------------------------------------------------------------------------------------------------------------------
# golden vectors (identical cell sequences) and the tie rule
# ---------------------------------------------------------------------------------------------------------------------
GOLD = R.golden_cases()


@pytest.mark.req("FR-007-35")
@pytest.mark.parametrize("case", [c for c in GOLD if not c["tie_rule"]], ids=lambda c: c["id"])
def test_golden_routes_are_reproduced_cell_for_cell(case):
    z, nodata = R.case_arrays(case)
    res = find_route(
        Dem(z, case["cell_m"], nodata),
        tuple(case["start"]),
        tuple(case["goal"]),
        mass_kg=case["mass_kg"],
        rr_pct=case["rr_pct"],
        g_max=case["g_max"],
        eta=case["eta"],
        g=case["g"],
    )
    if case["cells"] is None:
        assert isinstance(res, NoFeasibleRoute) and res.expanded == case["expanded"]
        return
    assert isinstance(res, Route)
    assert [list(c) for c in res.cells] == case["cells"]
    assert res.cost_j == pytest.approx(case["cost_j"], rel=1e-12, abs=1e-9)


@pytest.mark.req("FR-007-35")
@pytest.mark.parametrize("case", [c for c in GOLD if c["tie_rule"]], ids=lambda c: c["id"])
def test_ties_are_broken_by_f_then_g_then_cell_index(case):
    z, nodata = R.case_arrays(case)
    res = find_route(
        Dem(z, case["cell_m"], nodata),
        tuple(case["start"]),
        tuple(case["goal"]),
        mass_kg=case["mass_kg"],
        rr_pct=case["rr_pct"],
        g_max=case["g_max"],
        eta=case["eta"],
        g=case["g"],
    )
    assert isinstance(res, Route)
    assert [list(c) for c in res.cells] == case[
        "cells"
    ]  # the path the spec's tie rule selects (heap on (f, g, index), re-parent only on a strictly lower g)
    assert res.cost_j == pytest.approx(case["cost_j"], rel=1e-12, abs=1e-9)


@pytest.mark.req("FR-007-35")
def test_the_three_by_three_flat_tie_goes_through_the_centre_by_hand():
    """Hand derivation: all costs 0, so f = g = 0 everywhere and the lowest cell index is expanded first. Expanding 0 queues 1, 3, 4; expanding 1 queues 2, 5; expanding 2 adds nothing; expanding 3 queues 6, 7;
    expanding 4 reaches 8 for the first time (parent 4); 5, 6, 7 are expanded next and never re-parent 8. The route is 0 -> 4 -> 8."""
    res = route(np.zeros((3, 3)), (0, 0), (2, 2), rr=0.0, g_max=0.1, eta=1.0)
    assert isinstance(res, Route) and res.cells == [(0, 0), (1, 1), (2, 2)] and res.cost_j == 0.0

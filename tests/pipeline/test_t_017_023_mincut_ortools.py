"""T-017-023: agreement with OR-Tools `SimpleMaxFlow` (studio environment).

Requirements: FR-017-15, SC-017-03.

Spec: specs/017-planning-survey/spec.md FR-017-15 (the E1 pit value equals the value from OR-Tools `SimpleMaxFlow`
exactly and its block set equals the OR-Tools source side exactly, on every golden instance and every generated
property instance) and SC-017-03 (equal to the OR-Tools and networkx objectives exactly on every golden instance).
plan.md: OR-Tools is a `studio/` dependency (a second copy of its large wheel in `pipeline/` was rejected), so this
file
runs in the studio CPU job (T-011-002 / T-017-002); the networkx and SciPy comparisons are in
tests/pipeline/test_t_017_022_mincut_oracles.py.

Oracle: OR-Tools `ortools.graph.python.max_flow.SimpleMaxFlow` (reference implementation, int64 capacities) on the s-t
network of FR-017-14: s -> i with capacity v_i for v_i > 0, i -> t with capacity -v_i for v_i < 0, i -> j with
capacity
sum|v| + 1 for every precedence "i requires j" (a cut through such an arc can never be minimal). The minimal source
side is `get_source_side_min_cut()` (the nodes reachable from the source in the final residual network) without the
source; the value is sum(positive) - the maximum flow.

Expected API: `pitstudio.planning.pit.ultimate_pit` (tests/property/test_t_017_021_closure.py) and
`pitstudio.planning.precedence.level_cone_precedence` (tests/unit/test_t_017_020_bev_precedence.py).
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.planning.pit import ultimate_pit
from pitstudio.planning.precedence import level_cone_precedence


def _ortools_pit(values: list[int], pairs) -> tuple[int, frozenset[int]]:
    from ortools.graph.python import max_flow

    n = len(values)
    s, t = n, n + 1
    inf = sum(abs(v) for v in values) + 1
    solver = max_flow.SimpleMaxFlow()
    for i, v in enumerate(values):
        if v > 0:
            solver.add_arc_with_capacity(s, i, v)
        elif v < 0:
            solver.add_arc_with_capacity(i, t, -v)
    for i, j in pairs:
        solver.add_arc_with_capacity(i, j, inf)
    assert solver.solve(s, t) == solver.OPTIMAL
    side = frozenset(int(i) for i in solver.get_source_side_min_cut() if i not in (s, t))
    positive = sum(v for v in values if v > 0)
    assert sum(values[i] for i in side) == positive - solver.optimal_flow()  # the identity, by hand
    return positive - solver.optimal_flow(), side


def _ours(values: list[int], pairs):
    arcs = np.array(sorted(pairs), dtype=np.int64).reshape(-1, 2)
    pit = ultimate_pit(np.array(values, dtype=np.int64), arcs)
    return pit.value, frozenset(int(i) for i in np.flatnonzero(pit.mask))


GOLDEN = {
    "ore-over-three-waste": ([5, -1, -1, -1], [(0, 1), (0, 2), (0, 3)]),
    "ore-too-weak": ([2, -1, -1, -1], [(0, 1), (0, 2), (0, 3)]),
    "tie": ([4, -4], [(0, 1)]),
    "chain": ([3, -1, 2, -1, -1], [(0, 1), (1, 2), (2, 3), (3, 4)]),
    "two-pits-share-a-waste-block": ([4, 4, -5], [(0, 2), (1, 2)]),
    "cycle": ([2, -1, -1], [(0, 1), (1, 2), (2, 0)]),
    "isolated-zero-and-negative": ([0, -7, 3], []),
    "big-cents": ([2**40 + 5, -(2**40), 7, -8], [(0, 1), (2, 3)]),
}


@pytest.mark.req("FR-017-15")
@pytest.mark.req("SC-017-03")
@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_golden_instances_equal_ortools_exactly_in_value_and_block_set(name: str) -> None:
    values, pairs = GOLDEN[name]
    assert _ours(values, pairs) == _ortools_pit(values, pairs)


@pytest.mark.req("FR-017-15")
@settings(max_examples=200, deadline=None)
@given(
    n=st.integers(1, 120),
    seed=st.integers(0, 2**32 - 1),
    density=st.floats(0.0, 4.0),
)
def test_random_block_models_equal_ortools_in_value_and_block_set(n, seed, density):
    rng = np.random.default_rng(seed)
    values = [int(v) for v in rng.integers(-1_000_000, 1_000_001, n)]
    pairs = {
        (int(i), int(rng.integers(i + 1, n))) for i in range(n - 1) for _ in range(int(density)) if rng.random() < 0.8
    }
    assert _ours(values, pairs) == _ortools_pit(values, pairs)


@pytest.mark.req("FR-017-15")
@pytest.mark.req("SC-017-03")
@pytest.mark.parametrize(
    ("dims", "slope", "m", "seed"), [((6, 6, 4), 45.0, 1, 0), ((8, 5, 5), 35.0, 2, 1), ((10, 10, 6), 45.0, 1, 2)]
)
def test_level_cone_grids_equal_ortools_in_value_and_block_set(dims, slope, m, seed) -> None:
    nx, ny, nz = dims
    arcs = level_cone_precedence(nx, ny, nz, dx=1.0, dy=1.0, dz=1.0, slope_deg=slope, m=m)
    values = [int(v) for v in np.random.default_rng(seed).integers(-50, 51, nx * ny * nz)]
    pairs = {(int(a), int(b)) for a, b in arcs}
    assert _ours(values, pairs) == _ortools_pit(values, pairs)

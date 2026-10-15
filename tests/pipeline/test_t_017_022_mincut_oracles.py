"""T-017-022: agreement with networkx and SciPy and with the stamped `oreblocks` optima (pipeline).

Requirements: FR-017-15, P-017-01, SC-017-03.

Spec: specs/017-planning-survey/spec.md
- FR-017-15: on every golden instance and every generated property instance, the E1 pit value equals the value from
  networkx `minimum_cut`, OR-Tools `SimpleMaxFlow` and SciPy `maximum_flow` exactly, and its block set equals the
  networkx and OR-Tools source sides exactly; on every `oreblocks` deposit the value equals the stamped optimum;
- P-017-01: the E1 pit value and block set equal those of networkx (minimal source side) on random block models (<=
  300
  blocks, random arcs to blocks above, values in [-10^6, 10^6] cents; exact);
- SC-017-03: min-cut exactness: equal to the OR-Tools and networkx objectives exactly on every golden instance, and
  equal
  to every stamped `oreblocks` optimum. (OR-Tools: tests/pipeline/test_t_017_023_mincut_ortools.py, studio
  environment.)
Also here, from T-017-021's description: the lambda = 1 reproduction of the `oreblocks` block values in cents.
plan.md test strategy row FR-017-15: networkx `minimum_cut`, SciPy `maximum_flow` (pipeline env) as reference
implementations, with infinite precedence capacities represented as sum|v| + 1 (a cut through such an arc can never be
minimal); `oreblocks` stamped optima.

Oracles (reference implementations called directly):
- networkx `minimum_cut` on the s-t network of FR-017-14 (s -> i with capacity v_i for v_i > 0, i -> t with -v_i for
  v_i < 0, i -> j with capacity sum|v| + 1 for every precedence "i requires j"); its reachable partition is the
  minimal
  source side, so the pit is `S - {s}` and the value is sum(positive) - cut value (hand identity);
- SciPy `scipy.sparse.csgraph.maximum_flow` (int32 capacities; every instance here has sum|v| + 1 < 2^31): the pit
  value
  is sum(positive) - flow;
- `oreblocks` 0.5.2: `make_twin(archetype, dims, seed)`: a seeded synthetic deposit, its block values, its own
  precedence (CSR over predecessors: block b requires `plist[pstart[b]:pstart[b+1]]`) and the stamped optimum
  `twin.upit.pit_value` from its own exact solver (float USD). The stamped value is compared with the cents-rounded
  pit
  value to within half a cent per pit block (the rounding of each value to cents); exact equality is checked on the
  cents instance against networkx.

Expected API: `pitstudio.planning.pit.ultimate_pit` (see tests/property/test_t_017_021_closure.py) and
`pitstudio.planning.bev.{block_values, to_cents}` (see tests/unit/test_t_017_020_bev_precedence.py).
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.planning.bev import block_values, to_cents
from pitstudio.planning.pit import ultimate_pit


def _network(values: list[int], pairs):
    import networkx as nx

    inf = sum(abs(v) for v in values) + 1
    g = nx.DiGraph()
    g.add_nodes_from(["s", "t", *range(len(values))])
    for i, v in enumerate(values):
        if v > 0:
            g.add_edge("s", i, capacity=v)
        elif v < 0:
            g.add_edge(i, "t", capacity=-v)
    for i, j in pairs:
        g.add_edge(i, j, capacity=inf)
    return g


def _networkx_pit(values: list[int], pairs) -> tuple[int, frozenset[int]]:
    """Maximum flow by networkx (Edmonds-Karp), then the set reachable from s in the residual network.

    `networkx.minimum_cut` itself returns the MAXIMAL source side (the nodes that cannot reach t), so zero-gain
    additions are included; FR-017-14 asks for the MINIMAL one, the nodes reachable from s in the final residual
    network, which is extracted here from the networkx residual graph.
    """
    import networkx as nx
    from networkx.algorithms.flow import edmonds_karp

    residual = edmonds_karp(_network(values, pairs), "s", "t")
    cut = residual.graph["flow_value"]
    seen, stack = {"s"}, ["s"]
    while stack:
        u = stack.pop()
        for v, data in residual[u].items():
            if v not in seen and data["capacity"] - data["flow"] > 0:
                seen.add(v)
                stack.append(v)
    pit = frozenset(i for i in seen if i != "s")
    positive = sum(v for v in values if v > 0)
    assert sum(values[i] for i in pit) == positive - cut  # the identity, by hand
    assert nx.is_directed(residual)
    return positive - cut, pit


def _scipy_value(values: list[int], pairs) -> int:
    from scipy.sparse import csr_array
    from scipy.sparse.csgraph import maximum_flow

    n = len(values)
    s, t = n, n + 1
    inf = sum(abs(v) for v in values) + 1
    assert inf < 2**31
    rows, cols, caps = [], [], []
    for i, v in enumerate(values):
        if v > 0:
            rows.append(s), cols.append(i), caps.append(v)
        elif v < 0:
            rows.append(i), cols.append(t), caps.append(-v)
    for i, j in pairs:
        rows.append(i), cols.append(j), caps.append(inf)
    graph = csr_array((np.array(caps, dtype=np.int32), (rows, cols)), shape=(n + 2, n + 2))
    flow = maximum_flow(graph, s, t).flow_value
    return sum(v for v in values if v > 0) - int(flow)


def _arcs(pairs) -> np.ndarray:
    return np.array(sorted(pairs), dtype=np.int64).reshape(-1, 2)


def _ours(values: list[int], pairs):
    pit = ultimate_pit(np.array(values, dtype=np.int64), _arcs(pairs))
    return pit.value, frozenset(int(i) for i in np.flatnonzero(pit.mask))


# ----------------------------------------------------------------------------------------------------------------------
# golden instances
# ----------------------------------------------------------------------------------------------------------------------

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
def test_golden_instances_equal_networkx_exactly_in_value_and_block_set(name: str) -> None:
    values, pairs = GOLDEN[name]
    assert _ours(values, pairs) == _networkx_pit(values, pairs)


@pytest.mark.req("FR-017-15")
@pytest.mark.req("SC-017-03")
@pytest.mark.parametrize("name", [n for n in sorted(GOLDEN) if n != "big-cents"])
def test_golden_instances_equal_scipy_maximum_flow_in_value(name: str) -> None:
    values, pairs = GOLDEN[name]
    assert _ours(values, pairs)[0] == _scipy_value(values, pairs)


# ----------------------------------------------------------------------------------------------------------------------
# generated instances
# ----------------------------------------------------------------------------------------------------------------------


@st.composite
def block_models(draw):
    n = draw(st.integers(1, 300))
    values = draw(st.lists(st.integers(-(10**6), 10**6), min_size=n, max_size=n))
    n_arcs = draw(st.integers(0, min(4 * n, 600)))
    pairs = set()
    for _ in range(n_arcs):  # an arc from a block to a block "above" it: a larger index
        i = draw(st.integers(0, max(0, n - 2)))
        j = draw(st.integers(i + 1, n - 1)) if i + 1 <= n - 1 else None
        if j is not None:
            pairs.add((i, j))
    return values, pairs


@pytest.mark.req("P-017-01")
@pytest.mark.req("FR-017-15")
@settings(max_examples=200, deadline=None)
@given(model=block_models())
def test_random_block_models_equal_networkx_minimal_source_side_and_scipy_value(model):
    values, pairs = model
    value, pit = _ours(values, pairs)
    nx_value, nx_pit = _networkx_pit(values, pairs)
    assert value == nx_value
    assert pit == nx_pit
    assert value == _scipy_value(values, pairs)


# ----------------------------------------------------------------------------------------------------------------------
# oreblocks: lambda = 1 reproduction and stamped optima
# ----------------------------------------------------------------------------------------------------------------------

TWINS = [
    ("porphyry", (10, 10, 6), 3),
    ("vein", (12, 8, 6), 5),
    ("layered", (10, 10, 5), 2),
    ("core_halo", (9, 9, 7), 1),
]


def _twin(archetype: str, dims: tuple[int, int, int], seed: int):
    from oreblocks import make_twin

    return make_twin(archetype, dims, seed)


def _twin_arcs(twin) -> list[tuple[int, int]]:
    prec = twin.precedence
    return [(b, int(p)) for b in range(len(prec.pstart) - 1) for p in prec.plist[prec.pstart[b] : prec.pstart[b + 1]]]


@pytest.mark.req("FR-017-12")
@pytest.mark.parametrize(("archetype", "dims", "seed"), TWINS)
def test_the_block_value_at_lambda_1_reproduces_the_oreblocks_values_in_cents(archetype, dims, seed) -> None:
    twin = _twin(archetype, dims, seed)
    econ, dep = twin.econ, twin.deposit
    ours = block_values(
        dep.tonnage,
        dep.grade,
        lam=1.0,
        recovery=econ.recovery,
        net_price=econ.price,
        processing_cost=econ.processing_cost,
        mining_cost=econ.mining_cost,
    )
    assert to_cents(ours).tolist() == to_cents(np.asarray(twin.values)).tolist()


@pytest.mark.req("FR-017-15")
@pytest.mark.req("SC-017-03")
@pytest.mark.parametrize(("archetype", "dims", "seed"), TWINS)
def test_the_pit_of_an_oreblocks_deposit_equals_networkx_exactly_and_the_stamped_optimum_to_the_cent_rounding(
    archetype, dims, seed
) -> None:
    twin = _twin(archetype, dims, seed)
    cents = [int(c) for c in to_cents(np.asarray(twin.values))]
    pairs = _twin_arcs(twin)
    value, pit = _ours(cents, pairs)
    assert (value, pit) == _networkx_pit(cents, pairs)  # exact on the integer instance
    stamped = twin.upit.pit_value
    assert abs(value / 100.0 - stamped) <= 0.005 * max(1, len(pit)) + 1e-6  # the stamped optimum, up to cent rounding
    assert len(pit) > 0  # the archetype is a real deposit: a non-empty pit

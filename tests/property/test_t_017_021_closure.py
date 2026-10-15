"""T-017-021: minimal maximum closure through `minephys.planning`; closure, monotonicity, scaling, relabelling
(property).

Requirements: FR-017-14, P-017-02, P-017-04, P-017-05.

Spec: specs/017-planning-survey/spec.md
- FR-017-14: the E1 ultimate pit is the minimal maximum-weight closure (the set of blocks reachable from the source in
  the final residual network of a maximum flow of the s-t network: s -> i with v_i > 0, i -> t with -v_i for v_i < 0,
  infinite precedence arcs), computed in exact int64 arithmetic by the `minephys.planning` min-cut, with its value
  sum v_i over the set;
- P-017-02: the returned pit is closed: every precedence of every pit block is in the pit;
- P-017-04: raising the value of a block never removes a block from the pit; raising the mining cost c_m never adds
  one;
- P-017-05: multiplying every value by a positive integer k leaves the pit unchanged and multiplies its value by k;
  relabelling the blocks relabels the pit.
plan.md test strategy row FR-017-14: the four-block example (+5 -> all four, value 2; +2 -> empty, value 0); the
lambda
example (full pit from lambda = 2/3); exhaustive enumeration as the independent oracle on tiny instances.
(The oracle comparison with networkx, SciPy and OR-Tools, the lambda = 1 reproduction of the `oreblocks` values and
the
stamped optima are in tests/pipeline/test_t_017_022_mincut_oracles.py: those libraries are pipeline-environment
packages, absent from the root environment this file runs in.)

Oracles:
- the worked examples of spec section 7 (planning theory page): one ore block of +5 above three waste blocks of -1
  (the ore block requires the three): the pit is all four blocks, value 5 - 3 = 2; with +2 the closure value is -1
  < 0:
  the empty pit, value 0; the revenue-factor example v_d(lambda) = 6 lambda - 1 over three waste blocks: full pit iff
  6 lambda - 1 > 3, i.e. lambda > 2/3 (at lambda = 2/3 the gain is exactly 0 and the MINIMAL closure is empty);
- exhaustive enumeration of every closed subset of an instance of up to 9 blocks (all 2^n subsets, written in the
  test): the maximum value, and the minimal maximum closure = the intersection of all maximum closures (the maximum
  closures form a lattice closed under intersection, so that intersection is the unique minimal one);
- the properties themselves, evaluated on the code under test with exact Python integers.

Expected public API (module `pitstudio.planning.pit`, root environment, wraps `minephys.planning`):
    @dataclass(frozen=True) Pit        # mask: np.ndarray[bool] (n,), value: int (sum of the values in the pit)
    ultimate_pit(values: np.ndarray, arcs: np.ndarray) -> Pit
        values: int64 (n,) (cents); arcs: int64 (m, 2) with (i, j) meaning block i requires block j (j is above i);
        returns the minimal maximum-weight closure. ValueError naming `values` (not int64, empty, wrong rank) or
        `arcs` (not (m, 2) integers, an index out of range, a self-arc).
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.planning.pit import Pit, ultimate_pit


def _arcs(pairs) -> np.ndarray:
    return np.array(sorted(pairs), dtype=np.int64).reshape(-1, 2)


def _enumerate(values: list[int], pairs) -> tuple[int, frozenset[int]]:
    """(maximum closure value, minimal maximum closure) by trying every subset of the blocks."""
    n = len(values)
    best, optimal = None, []
    for bits in itertools.product((0, 1), repeat=n):
        chosen = {i for i, b in enumerate(bits) if b}
        if any(i in chosen and j not in chosen for i, j in pairs):
            continue  # not closed
        total = sum(values[i] for i in chosen)
        if best is None or total > best:
            best, optimal = total, [chosen]
        elif total == best:
            optimal.append(chosen)
    return best, frozenset(set.intersection(*optimal))


def _mask_set(pit: Pit) -> frozenset[int]:
    return frozenset(int(i) for i in np.flatnonzero(pit.mask))


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-14: worked examples
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-14")
def test_one_ore_block_of_plus_5_over_three_waste_blocks_gives_the_whole_pit_with_value_2() -> None:
    pit = ultimate_pit(np.array([5, -1, -1, -1], dtype=np.int64), _arcs([(0, 1), (0, 2), (0, 3)]))
    assert pit.mask.tolist() == [True, True, True, True]
    assert pit.value == 2


@pytest.mark.req("FR-017-14")
def test_with_plus_2_the_pit_is_empty_with_value_0() -> None:
    pit = ultimate_pit(np.array([2, -1, -1, -1], dtype=np.int64), _arcs([(0, 1), (0, 2), (0, 3)]))
    assert pit.mask.tolist() == [False] * 4
    assert pit.value == 0


@pytest.mark.req("FR-017-14")
@pytest.mark.parametrize(("cents", "full"), [(320, True), (260, False), (301, True), (300, False), (299, False)])
def test_revenue_factor_example_the_full_pit_needs_6_lambda_minus_1_above_3(cents: int, full: bool) -> None:
    # the ore block is worth v_d = 6 lambda - 1 USD (`cents` / 100) over three waste blocks of -1 USD each: the
    # whole pit
    # pays iff v_d > 3, i.e. lambda > 2/3; at v_d = 3 (lambda = 2/3) the gain is exactly 0 and the minimal closure
    # is empty
    values = np.array([cents, -100, -100, -100], dtype=np.int64)
    pit = ultimate_pit(values, _arcs([(0, 1), (0, 2), (0, 3)]))
    assert bool(pit.mask.all()) is full
    assert bool(pit.mask.any()) is full
    assert pit.value == (cents - 300 if full else 0)


@pytest.mark.req("FR-017-14")
def test_minimal_closure_leaves_out_zero_gain_additions_and_keeps_required_zero_blocks() -> None:
    # block 0 (+4) requires block 1 (-4): the closure {0, 1} has value 0, the same as the empty set -> empty (minimal)
    tie = ultimate_pit(np.array([4, -4], dtype=np.int64), _arcs([(0, 1)]))
    assert (tie.mask.tolist(), tie.value) == ([False, False], 0)
    # block 0 (+4) requires block 1 (0): the zero-value block is required, so it is in the pit
    required = ultimate_pit(np.array([4, 0, 0], dtype=np.int64), _arcs([(0, 1)]))
    assert required.mask.tolist() == [True, True, False]  # block 2 is a free zero-value block: not required, left out
    assert required.value == 4


@pytest.mark.req("FR-017-14")
def test_values_far_beyond_float32_and_up_to_2_pow_50_are_summed_exactly() -> None:
    big = 2**50
    values = np.array([big + 1, -big, 3, -2], dtype=np.int64)
    pit = ultimate_pit(values, _arcs([(0, 1), (2, 3)]))
    best, minimal = _enumerate([int(v) for v in values], [(0, 1), (2, 3)])
    assert pit.value == best == 2  # (2^50 + 1) - 2^50 + (3 - 2)
    assert _mask_set(pit) == minimal
    assert isinstance(pit.value, int)


@pytest.mark.req("FR-017-14")
def test_invalid_values_and_arcs_are_refused_naming_the_argument() -> None:
    ok_v, ok_a = np.array([1, -1], dtype=np.int64), _arcs([(0, 1)])
    with pytest.raises(ValueError, match="values"):
        ultimate_pit(np.array([1.0, -1.0]), ok_a)
    with pytest.raises(ValueError, match="values"):
        ultimate_pit(np.array([], dtype=np.int64), _arcs([]))
    with pytest.raises(ValueError, match="arcs"):
        ultimate_pit(ok_v, _arcs([(0, 2)]))  # index out of range
    with pytest.raises(ValueError, match="arcs"):
        ultimate_pit(ok_v, _arcs([(1, 1)]))  # self-arc
    with pytest.raises(ValueError, match="arcs"):
        ultimate_pit(ok_v, np.array([[0.5, 1.0]]))


# ----------------------------------------------------------------------------------------------------------------------
# properties
# ----------------------------------------------------------------------------------------------------------------------


@st.composite
def instances(draw, max_blocks: int = 9):
    n = draw(st.integers(1, max_blocks))
    values = draw(st.lists(st.integers(-6, 6), min_size=n, max_size=n))
    pairs = draw(
        st.sets(st.tuples(st.integers(0, n - 1), st.integers(0, n - 1)).filter(lambda p: p[0] != p[1]), max_size=20)
        if n > 1
        else st.just(set())
    )
    return values, pairs


@pytest.mark.req("FR-017-14")
@settings(max_examples=200, deadline=None)
@given(instance=instances())
def test_value_and_block_set_equal_exhaustive_enumeration_on_tiny_instances(instance):
    values, pairs = instance
    pit = ultimate_pit(np.array(values, dtype=np.int64), _arcs(pairs))
    best, minimal = _enumerate(values, pairs)
    assert pit.value == best
    assert _mask_set(pit) == minimal


@pytest.mark.req("P-017-02")
@settings(max_examples=200, deadline=None)
@given(instance=instances(max_blocks=40))
def test_the_pit_is_closed_under_precedence_and_its_value_is_the_sum_of_its_blocks(instance):
    values, pairs = instance
    pit = ultimate_pit(np.array(values, dtype=np.int64), _arcs(pairs))
    chosen = _mask_set(pit)
    assert all(j in chosen for i, j in pairs if i in chosen)
    assert pit.value == sum(values[i] for i in chosen)
    assert pit.value >= 0  # the empty pit is always feasible


@pytest.mark.req("P-017-04")
@settings(max_examples=200, deadline=None)
@given(instance=instances(max_blocks=30), block=st.integers(0, 10**6), delta=st.integers(1, 20))
def test_raising_the_value_of_one_block_never_removes_a_block_from_the_pit(instance, block, delta):
    values, pairs = instance
    b = block % len(values)
    raised = list(values)
    raised[b] += delta
    before = _mask_set(ultimate_pit(np.array(values, dtype=np.int64), _arcs(pairs)))
    after = _mask_set(ultimate_pit(np.array(raised, dtype=np.int64), _arcs(pairs)))
    assert before <= after


@pytest.mark.req("P-017-04")
@settings(max_examples=200, deadline=None)
@given(
    instance=instances(max_blocks=30),
    cost=st.integers(1, 5),
    tonnage=st.lists(st.integers(1, 4), min_size=30, max_size=30),
)
def test_raising_the_mining_cost_never_adds_a_block_to_the_pit(instance, cost, tonnage):
    values, pairs = instance
    t = tonnage[: len(values)]
    raised = [v - cost * ti for v, ti in zip(values, t, strict=True)]  # every value falls by c_m T_i
    before = _mask_set(ultimate_pit(np.array(values, dtype=np.int64), _arcs(pairs)))
    after = _mask_set(ultimate_pit(np.array(raised, dtype=np.int64), _arcs(pairs)))
    assert after <= before


@pytest.mark.req("P-017-05")
@settings(max_examples=200, deadline=None)
@given(instance=instances(max_blocks=30), k=st.integers(1, 1000))
def test_scaling_every_value_by_k_leaves_the_pit_and_multiplies_its_value(instance, k):
    values, pairs = instance
    base = ultimate_pit(np.array(values, dtype=np.int64), _arcs(pairs))
    scaled = ultimate_pit(np.array([k * v for v in values], dtype=np.int64), _arcs(pairs))
    assert _mask_set(scaled) == _mask_set(base)
    assert scaled.value == k * base.value


@pytest.mark.req("P-017-05")
@settings(max_examples=200, deadline=None)
@given(instance=instances(max_blocks=30), seed=st.integers(0, 2**32 - 1))
def test_relabelling_the_blocks_relabels_the_pit(instance, seed):
    values, pairs = instance
    n = len(values)
    perm = np.random.default_rng(seed).permutation(n)  # old label i becomes perm[i]
    new_values = [0] * n
    for i, v in enumerate(values):
        new_values[int(perm[i])] = v
    new_pairs = {(int(perm[i]), int(perm[j])) for i, j in pairs}
    base = _mask_set(ultimate_pit(np.array(values, dtype=np.int64), _arcs(pairs)))
    moved = _mask_set(ultimate_pit(np.array(new_values, dtype=np.int64), _arcs(new_pairs)))
    assert moved == frozenset(int(perm[i]) for i in base)

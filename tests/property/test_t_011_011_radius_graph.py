"""T-011-011 - FR-011-02, FR-011-13, P-011-04 (+ the InvalidGraphError clause of FR-011-15 for the builder): radius
    graph.

Oracles (independent of the code under test; plan 011 test strategy FR-011-02 / FR-011-13):
- a brute-force O(N^2) reference written in this file: float64 squared distances from the float32 positions
  (FR-011-02), neighbour j of i iff j != i and d2 < R^2, lists ordered by (d2, j), the first K_max = 32 kept, the
  rest counted as overflow (FR-011-13);
- hand counts on an integer lattice (spacing 1, R = 2.5): the offsets (dx, dy) with 0 < dx^2 + dy^2 < 6.25 are
  4 at distance 1, 4 at sqrt 2, 4 at 2 and 8 at sqrt 5, i.e. 20 neighbours (r^2 = 8 > 6.25 is excluded). The
  expected list of the centre particle of a 5 x 5 lattice (index = 5 * row + col, coordinates (col, row)) is written
  out below by hand;
- the metamorphic relations of P-011-04: permutation, translation by a dyadic vector, and scaling by 2 (all exact
  when the coordinates are dyadic rationals, because binary64 squared distances are then exact).

Expected public API (module `pitstudio.granular.graph`, under `src/pitstudio/granular/`; module
`pitstudio.granular.errors` holds the error classes):

    build_radius_graph(positions: np.ndarray, radius: float, k_max: int = 32) -> RadiusGraph
        positions: float32 or float64 array [N, 2] (metres), N >= 1; squared distances in binary64.
        RadiusGraph (attribute access):
            neighbour_index: int64 [N, k_max]  neighbours by (distance, index); masked-off entries hold any value
                                                in [0, N) (the pad value is not specified by the spec);
            neighbour_mask:  bool  [N, k_max]  True for a listed neighbour;
            overflow_count:  int               number of particles with more than k_max neighbours within R.
        Raises `pitstudio.granular.errors.InvalidGraphError` for N = 0, a shape other than [N, 2], a non-finite
        coordinate, or a radius that is not a positive finite number.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio.granular.errors import InvalidGraphError  # noqa: E402
from pitstudio.granular.graph import build_radius_graph  # noqa: E402

EXAMPLES = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "property_tests"
]["ci_examples_per_test"]
K_MAX = 32


def reference_graph(pos32: np.ndarray, radius: float) -> tuple[list[list[int]], int]:
    """Brute-force neighbour lists (all of them, before the K_max cut) and the overflow count."""
    p = pos32.astype(np.float64)
    n = p.shape[0]
    d2 = ((p[:, None, :] - p[None, :, :]) ** 2).sum(-1)
    lists: list[list[int]] = []
    overflow = 0
    for i in range(n):
        cand = [j for j in range(n) if j != i and d2[i, j] < radius * radius]
        cand.sort(key=lambda j: (d2[i, j], j))
        if len(cand) > K_MAX:
            overflow += 1
        lists.append(cand)
    return lists, overflow


def listed(g, i: int) -> list[int]:
    return [int(j) for j, m in zip(g.neighbour_index[i], g.neighbour_mask[i], strict=True) if m]


def lattice(nx: int, ny: int, spacing: float = 1.0) -> np.ndarray:
    return np.array([[c * spacing, r * spacing] for r in range(ny) for c in range(nx)], dtype=np.float32)


def random_packing(seed: int, n: int, density: float, d: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    side = np.sqrt(n / density) * d
    return rng.uniform(0.0, side, size=(n, 2)).astype(np.float32)


# ------------------------------------------------------------------ FR-011-02 hand-counted fixtures


@pytest.mark.req("FR-011-02")
def test_lattice_centre_particle_has_the_hand_counted_twenty_neighbours_in_distance_then_index_order() -> None:
    g = build_radius_graph(lattice(5, 5), 2.5)
    expected = [7, 11, 13, 17, 6, 8, 16, 18, 2, 10, 14, 22, 1, 3, 5, 9, 15, 19, 21, 23]  # 1, sqrt2, 2, sqrt5 shells
    assert listed(g, 12) == expected
    assert g.neighbour_index.shape == (25, K_MAX)
    assert g.neighbour_mask.shape == (25, K_MAX)
    assert g.neighbour_mask[12].sum() == 20
    assert g.neighbour_mask[12][:20].all()
    assert not g.neighbour_mask[12][20:].any()
    assert g.overflow_count == 0


@pytest.mark.req("FR-011-02")
def test_lattice_corner_particle_has_seven_neighbours() -> None:
    # corner (0, 0): (1,0) (0,1) at 1; (1,1) at sqrt2; (2,0) (0,2) at 2; (2,1) (1,2) at sqrt5 -> indices below
    g = build_radius_graph(lattice(5, 5), 2.5)
    assert listed(g, 0) == [1, 5, 6, 2, 10, 7, 11]


@pytest.mark.req("FR-011-02")
def test_no_self_edge_and_pad_entries_stay_inside_the_particle_range() -> None:
    g = build_radius_graph(lattice(4, 3), 2.5)
    n = 12
    for i in range(n):
        assert i not in listed(g, i)
    assert g.neighbour_index.min() >= 0
    assert g.neighbour_index.max() < n


@pytest.mark.req("FR-011-02")
def test_pair_exactly_at_the_radius_is_not_connected_and_just_inside_is() -> None:
    at_r = np.array([[0.0, 0.0], [2.5, 0.0]], dtype=np.float32)
    inside = np.array([[0.0, 0.0], [2.4990234375, 0.0]], dtype=np.float32)  # 2.5 - 2**-10, exact in binary32
    assert listed(build_radius_graph(at_r, 2.5), 0) == []
    assert listed(build_radius_graph(inside, 2.5), 0) == [1]
    assert listed(build_radius_graph(inside, 2.5), 1) == [0]


@pytest.mark.req("FR-011-02")
def test_squared_distances_use_binary64_from_the_binary32_positions() -> None:
    # The connection decision must equal the binary64 decision on the binary32 coordinates, also when R is chosen
    # within 1e-9 of the exact binary64 separation (a binary32 distance computation would decide differently).
    a = np.float32(0.1)
    b = np.float32(0.1) + np.float32(2.4)
    pos = np.array([[a, 0.0], [b, 0.0]], dtype=np.float32)
    d_ref = float(np.float64(pos[1, 0]) - np.float64(pos[0, 0]))
    for radius in (d_ref - 1e-9, d_ref + 1e-9):
        connected = bool(listed(build_radius_graph(pos, radius), 0))
        assert connected == (d_ref * d_ref < radius * radius)


@pytest.mark.req("FR-011-13")
def test_overflow_keeps_the_32_nearest_and_counts_every_overflowing_particle() -> None:
    rng = np.random.default_rng(7)
    pos = rng.uniform(-0.5, 0.5, size=(41, 2)).astype(np.float32)  # all 41 within 1.5 of each other < R = 2.5
    ref, ref_overflow = reference_graph(pos, 2.5)
    g = build_radius_graph(pos, 2.5)
    assert ref_overflow == 41  # hand: every particle has 40 neighbours > 32
    assert g.overflow_count == 41
    for i in range(41):
        assert g.neighbour_mask[i].all()
        assert listed(g, i) == ref[i][:K_MAX]


@pytest.mark.req("FR-011-13")
def test_no_overflow_is_reported_at_exactly_32_neighbours() -> None:
    rng = np.random.default_rng(11)
    pos = rng.uniform(-0.5, 0.5, size=(33, 2)).astype(np.float32)  # 32 neighbours each: the limit itself
    g = build_radius_graph(pos, 2.5)
    assert g.overflow_count == 0
    assert g.neighbour_mask.all()


# ------------------------------------------------------------------ P-011-04 properties


@pytest.mark.req("P-011-04")
@settings(max_examples=EXAMPLES, deadline=None)
@given(seed=st.integers(0, 2**32 - 1), n=st.integers(1, 250), density=st.floats(0.3, 1.3))
def test_property_graph_equals_brute_force_with_symmetry_distance_bound_and_order(
    seed: int, n: int, density: float
) -> None:
    pos = random_packing(seed, n, density)
    ref, ref_overflow = reference_graph(pos, 2.5)
    g = build_radius_graph(pos, 2.5)
    assert g.overflow_count == ref_overflow
    p64 = pos.astype(np.float64)
    for i in range(n):
        got = listed(g, i)
        assert got == ref[i][:K_MAX]
        assert i not in got
        d2 = [((p64[i] - p64[j]) ** 2).sum() for j in got]
        assert all(v < 2.5 * 2.5 for v in d2)
        assert [(d, j) for d, j in zip(d2, got, strict=True)] == sorted(zip(d2, got, strict=True))
    if ref_overflow == 0:
        edges = {(i, j) for i in range(n) for j in listed(g, i)}
        assert all((j, i) in edges for i, j in edges)


@pytest.mark.req("P-011-04")
@settings(max_examples=EXAMPLES, deadline=None)
@given(seed=st.integers(0, 2**32 - 1), n=st.integers(2, 200), density=st.floats(0.3, 0.9))
def test_metamorphic_permutation_relabels_the_neighbour_sets(seed: int, n: int, density: float) -> None:
    pos = random_packing(seed, n, density)
    perm = np.random.default_rng(seed + 1).permutation(n)
    inv = np.empty(n, dtype=np.int64)
    inv[perm] = np.arange(n)
    g0 = build_radius_graph(pos, 2.5)
    g1 = build_radius_graph(pos[perm], 2.5)
    assert g0.overflow_count == g1.overflow_count
    if g0.overflow_count == 0:
        for new_i, old_i in enumerate(perm):
            assert {int(inv[j]) for j in listed(g0, int(old_i))} == set(listed(g1, new_i))


@pytest.mark.req("P-011-04")
@settings(max_examples=EXAMPLES, deadline=None)
@given(
    seed=st.integers(0, 2**32 - 1),
    n=st.integers(2, 120),
    shift=st.tuples(st.integers(-4096, 4096), st.integers(-4096, 4096)),
)
def test_metamorphic_translation_and_doubling_leave_the_graph_unchanged_on_dyadic_coordinates(
    seed: int, n: int, shift: tuple[int, int]
) -> None:
    rng = np.random.default_rng(seed)
    pos = (np.round(rng.uniform(0, 12, size=(n, 2)) * 256) / 256).astype(np.float32)  # multiples of 2**-8, ties likely
    base = build_radius_graph(pos, 2.5)
    moved = build_radius_graph(pos + np.array(shift, dtype=np.float32) / np.float32(16.0), 2.5)
    doubled = build_radius_graph(pos * np.float32(2.0), 5.0)
    for other in (moved, doubled):
        assert other.overflow_count == base.overflow_count
        assert np.array_equal(other.neighbour_mask, base.neighbour_mask)
        for i in range(n):
            assert listed(other, i) == listed(base, i)


# ------------------------------------------------------------------ hostile inputs (builder side of FR-011-15)


@pytest.mark.req("FR-011-15")
@pytest.mark.parametrize(
    "bad",
    [
        np.zeros((0, 2), dtype=np.float32),
        np.zeros((5, 3), dtype=np.float32),
        np.zeros((5,), dtype=np.float32),
        np.array([[0.0, np.nan], [1.0, 1.0]], dtype=np.float32),
        np.array([[np.inf, 0.0], [1.0, 1.0]], dtype=np.float32),
        np.array([[0.0, -np.inf], [1.0, 1.0]], dtype=np.float64),
    ],
    ids=["n0", "three-columns", "one-dimensional", "nan", "inf", "minus-inf"],
)
def test_hostile_positions_raise_invalid_graph_error_and_return_no_graph(bad: np.ndarray) -> None:
    with pytest.raises(InvalidGraphError):
        build_radius_graph(bad, 2.5)


@pytest.mark.req("FR-011-15")
@pytest.mark.parametrize("radius", [0.0, -1.0, float("nan"), float("inf")])
def test_hostile_radius_raises_invalid_graph_error(radius: float) -> None:
    with pytest.raises(InvalidGraphError):
        build_radius_graph(lattice(3, 3), radius)

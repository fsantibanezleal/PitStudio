"""T-017-020: block values, integer scaling, precedence generator (unit, property).

Requirements: FR-017-12, FR-017-13, P-017-06.

Spec: specs/017-planning-survey/spec.md
- FR-017-12: the block value is v_i(lambda) = max(T_i [lambda g_i r (p - s_r) - c_p] - T_i c_m, -T_i c_m) in USD, and
  every value entering a solver is scaled to integer cents (v x 100, rounded half to even) in int64;
- FR-017-13: for regular block grids without their own precedence file, the precedence generator adds an arc from block
  (i, j, k) to every block l = 1 ... m levels above whose horizontal centre offset is <= l dz / tan(alpha) (+ 1e-9 m),
  with overall slope angle alpha and m from the recipe (default 1, the 1:5 pattern at 45 degrees on cubic blocks);
- P-017-06: v_i(lambda) is non-decreasing in lambda and in g_i and equals the hand calculation of the planning theory
  page (grades in [0, 0.05], lambda in (0, 2]; exact order, hand values exact in cents).
plan.md test strategy rows FR-017-12 (planning page worked examples; break-even cut-off 0.147 % Cu) and FR-017-13
(hand-counted 1:5 pattern on cubic blocks at 45 degrees; the 3 x 3 pattern at a flatter angle).

Oracles (hand calculation and an independent brute-force definition):
- block value by hand: T = 1,000 t, g = 0.012, r = 0.85, p - s_r = 8,000 USD/t, c_p = 10 USD/t, c_m = 2.5 USD/t,
  lambda = 1: 1,000 (0.012 x 0.85 x 8,000 - 10) - 2,500 = 1,000 (81.6 - 10) - 2,500 = 69,100 USD; at lambda = 0.1
  the ore branch is 1,000 (8.16 - 10) - 2,500 = -4,340 < -2,500, so the block is waste: -2,500;
- break-even cut-off (spec section 7): c_p / (r (p - s_r)) = 10 / (0.85 x 8,000) = 0.00147 (0.147 % Cu);
- the min-cut worked example of section 7: one ore block of value +5 (T = 1, r = 1, p - s_r = 1, c_p = 0, c_m = 1,
  g = 6, lambda = 1) and waste blocks of value -1;
- half-to-even rounding on dyadic values (0.125 USD = 12.5 cents -> 12; 0.375 USD = 37.5 cents -> 38);
- the arc counts of a 5 x 5 grid between two levels by hand: 1:5 pattern = 25 + 80 = 105 arcs (each cell and its
  four edge neighbours inside the grid); the 3 x 3 pattern (radius sqrt(2)) = 13^2 = 169 arcs (the 3 x 3 window sums per
  axis 2 + 3 + 3 + 3 + 2 = 13); and a brute-force enumeration of the definition of FR-017-13 written in the test, used
  for random grids, block sizes, angles and m.

Expected public API (root environment, numpy only):
module `pitstudio.planning.bev`
    block_values(tonnage, grade, *, lam: float, recovery: float, net_price: float, processing_cost: float,
                 mining_cost: float) -> np.ndarray          # float64 USD per block (vectorised over tonnage and grade)
    breakeven_grade(*, recovery: float, net_price: float, processing_cost: float) -> float   # c_p / (r (p - s_r))
    to_cents(values: np.ndarray) -> np.ndarray              # int64 of round-half-even(v x 100); ValueError for a
                                                            # non-finite value or one whose cents exceed int64
module `pitstudio.planning.precedence`
    level_cone_precedence(nx: int, ny: int, nz: int, *, dx: float, dy: float, dz: float, slope_deg: float,
                          m: int = 1) -> np.ndarray
        int64 array (n_arcs, 2) of arcs (block, block_above) with block index (k * ny + j) * nx + i (x fastest, then y,
        then level; levels increase upward); no duplicates; ValueError naming `nx`, `ny`, `nz`, `dx`, `dy`, `dz`,
        `slope_deg` (outside (0, 90)) or `m` (< 1) for an invalid argument.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.planning.bev import block_values, breakeven_grade, to_cents
from pitstudio.planning.precedence import level_cone_precedence

ECON = {"recovery": 0.85, "net_price": 8000.0, "processing_cost": 10.0, "mining_cost": 2.5}


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-12
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-12")
def test_block_value_by_hand_at_lambda_1_and_at_a_low_revenue_factor() -> None:
    t, g = np.array([1000.0]), np.array([0.012])
    assert block_values(t, g, lam=1.0, **ECON)[0] == pytest.approx(69_100.0, rel=1e-12)
    assert block_values(t, g, lam=0.1, **ECON)[0] == pytest.approx(-2_500.0, rel=1e-12)  # waste: -T c_m


@pytest.mark.req("FR-017-12")
def test_the_value_is_the_better_of_ore_and_waste_per_block() -> None:
    t = np.full(3, 1000.0)
    g = np.array([0.0, 0.0014, 0.012])  # below, just below and above the break-even grade 0.00147
    v = block_values(t, g, lam=1.0, **ECON)
    assert v[0] == -2_500.0
    assert v[1] == -2_500.0  # 1000 (0.0014 x 0.85 x 8000 - 10) - 2500 = -2,980: waste is better
    assert v[2] > 0


@pytest.mark.req("FR-017-12")
def test_breakeven_cutoff_is_0_147_percent() -> None:
    cutoff = breakeven_grade(recovery=0.85, net_price=8000.0, processing_cost=10.0)
    assert cutoff == pytest.approx(10.0 / (0.85 * 8000.0), rel=1e-12)
    assert cutoff == pytest.approx(0.00147, abs=5e-6)


@pytest.mark.req("FR-017-12")
def test_the_section_7_worked_blocks_have_values_plus_5_and_minus_1() -> None:
    kw = {"lam": 1.0, "recovery": 1.0, "net_price": 1.0, "processing_cost": 0.0, "mining_cost": 1.0}
    v = block_values(np.ones(4), np.array([6.0, 0.0, 0.0, 0.0]), **kw)
    assert v.tolist() == [5.0, -1.0, -1.0, -1.0]
    # revenue-factor example v_d(lambda) = 6 lambda - 1
    for lam in (0.25, 2 / 3, 1.0):
        assert block_values(np.ones(1), np.array([6.0]), **{**kw, "lam": lam})[0] == pytest.approx(6 * lam - 1)


@pytest.mark.req("FR-017-12")
def test_values_are_scaled_to_int64_cents_rounding_half_to_even() -> None:
    cents = to_cents(np.array([0.125, 0.375, 0.625, -0.125, -0.375, 1.0, 69_100.0, 0.0]))
    assert cents.dtype == np.int64
    assert cents.tolist() == [12, 38, 62, -12, -38, 100, 6_910_000, 0]
    # 0.005 and 0.015 USD are not exact in binary; the exact dyadic half-cents above are the rounding oracle
    assert to_cents(np.array([2.5e-2]))[0] in (2, 3)


@pytest.mark.req("FR-017-12")
def test_cents_refuse_non_finite_values_and_int64_overflow() -> None:
    for bad in (np.nan, np.inf, -np.inf):
        with pytest.raises(ValueError, match=r"."):
            to_cents(np.array([1.0, bad]))
    with pytest.raises(ValueError, match=r"."):
        to_cents(np.array([1e17]))  # 1e19 cents > 2^63
    assert to_cents(np.array([9e16]))[0] == 9_000_000_000_000_000_000  # 9e18 cents < 2^63 is accepted


@pytest.mark.req("FR-017-12")
def test_dyadic_hand_values_are_exact_in_cents() -> None:
    # T = 256, g = 1/64, r = 1/2, p - s_r = 1024, c_p = 8, c_m = 2:
    # lambda 2 -> 256 (16 - 8) - 512 = 1536; lambda 1 -> -512
    kw = {"recovery": 0.5, "net_price": 1024.0, "processing_cost": 8.0, "mining_cost": 2.0}
    t, g = np.array([256.0]), np.array([1 / 64])
    assert to_cents(block_values(t, g, lam=2.0, **kw)).tolist() == [153_600]
    assert to_cents(block_values(t, g, lam=1.0, **kw)).tolist() == [-51_200]


@pytest.mark.req("P-017-06")
@settings(max_examples=200, deadline=None)
@given(
    g=st.floats(0.0, 0.05),
    dg=st.floats(0.0, 0.05),
    lam=st.floats(1e-3, 2.0),
    dlam=st.floats(0.0, 2.0),
)
def test_value_is_non_decreasing_in_lambda_and_in_grade_and_never_below_the_waste_value(g, dg, lam, dlam):
    t = np.array([1000.0])
    base = block_values(t, np.array([g]), lam=lam, **ECON)[0]
    assert block_values(t, np.array([g + dg]), lam=lam, **ECON)[0] >= base
    assert block_values(t, np.array([g]), lam=lam + dlam, **ECON)[0] >= base
    assert base >= -1000.0 * ECON["mining_cost"]  # never worse than waste


@pytest.mark.req("P-017-06")
@settings(max_examples=200, deadline=None)
@given(g=st.floats(0.0, 0.05), lam=st.floats(1e-3, 2.0), tonnage=st.floats(1.0, 1e5))
def test_value_equals_the_hand_formula(g, lam, tonnage):
    c_m, c_p, r, p = ECON["mining_cost"], ECON["processing_cost"], ECON["recovery"], ECON["net_price"]
    expected = max(tonnage * (lam * g * r * p - c_p) - tonnage * c_m, -tonnage * c_m)
    got = block_values(np.array([tonnage]), np.array([g]), lam=lam, **ECON)[0]
    assert got == pytest.approx(expected, rel=1e-12, abs=1e-9)


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-13
# ----------------------------------------------------------------------------------------------------------------------


def _brute(nx, ny, nz, dx, dy, dz, slope_deg, m) -> set[tuple[int, int]]:
    """The definition of FR-017-13, enumerated block pair by block pair."""
    tan = math.tan(math.radians(slope_deg))
    arcs = set()
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                src = (k * ny + j) * nx + i
                for level in range(1, m + 1):
                    if k + level >= nz:
                        break
                    reach = level * dz / tan + 1e-9
                    for jj in range(ny):
                        for ii in range(nx):
                            if math.hypot((ii - i) * dx, (jj - j) * dy) <= reach:
                                arcs.add((src, ((k + level) * ny + jj) * nx + ii))
    return arcs


def _arc_set(arcs: np.ndarray) -> set[tuple[int, int]]:
    return {(int(a), int(b)) for a, b in arcs}


@pytest.mark.req("FR-017-13")
def test_the_1_5_pattern_on_cubic_blocks_at_45_degrees_has_5_predecessors_for_an_interior_block() -> None:
    arcs = level_cone_precedence(5, 5, 2, dx=1.0, dy=1.0, dz=1.0, slope_deg=45.0)
    assert arcs.dtype == np.int64
    assert arcs.shape == (105, 2)  # 25 + 80, by hand
    centre = 2 * 5 + 2  # block (2, 2, 0)
    above = sorted(int(b) for a, b in arcs if a == centre)
    assert above == sorted(1 * 25 + y * 5 + x for x, y in [(2, 2), (1, 2), (3, 2), (2, 1), (2, 3)])  # the 5 blocks
    assert len(_arc_set(arcs)) == 105  # no duplicates
    assert all(b // 25 == 1 and a // 25 == 0 for a, b in arcs)  # arcs go from level 0 to level 1 only


@pytest.mark.req("FR-017-13")
def test_a_flatter_angle_gives_the_3_x_3_pattern() -> None:
    alpha = math.degrees(math.atan(1 / math.sqrt(2)))  # horizontal reach sqrt(2) per level: the diagonals are in
    arcs = level_cone_precedence(5, 5, 2, dx=1.0, dy=1.0, dz=1.0, slope_deg=alpha)
    assert arcs.shape == (169, 2)  # 13^2, by hand
    assert sum(1 for a, _ in arcs if a == 12) == 9  # the interior block sees the whole 3 x 3 window


@pytest.mark.req("FR-017-13")
def test_m_levels_above_use_a_reach_that_grows_with_the_level() -> None:
    arcs = _arc_set(level_cone_precedence(5, 5, 3, dx=1.0, dy=1.0, dz=1.0, slope_deg=45.0, m=2))
    two_up_from_centre = {b for a, b in arcs if a == 12 and b // 25 == 2}
    assert len(two_up_from_centre) == 13  # offsets with dx^2 + dy^2 <= 4: 1 + 4 + 4 + 4
    assert arcs == _brute(5, 5, 3, 1.0, 1.0, 1.0, 45.0, 2)


@pytest.mark.req("FR-017-13")
@settings(max_examples=200, deadline=None)
@given(
    nx=st.integers(1, 6),
    ny=st.integers(1, 6),
    nz=st.integers(1, 4),
    dx=st.floats(0.5, 4.0),
    dy=st.floats(0.5, 4.0),
    dz=st.floats(0.5, 4.0),
    slope=st.floats(15.0, 80.0),
    m=st.integers(1, 3),
)
def test_the_generator_equals_the_brute_force_definition(nx, ny, nz, dx, dy, dz, slope, m):
    got = level_cone_precedence(nx, ny, nz, dx=dx, dy=dy, dz=dz, slope_deg=slope, m=m)
    assert len(got) == len(_arc_set(got))
    assert _arc_set(got) == _brute(nx, ny, nz, dx, dy, dz, slope, m)


@pytest.mark.req("FR-017-13")
def test_a_single_level_grid_has_no_arcs() -> None:
    assert level_cone_precedence(4, 4, 1, dx=1.0, dy=1.0, dz=1.0, slope_deg=45.0).shape == (0, 2)


@pytest.mark.req("FR-017-13")
@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"nx": 0}, "nx"),
        ({"ny": -1}, "ny"),
        ({"nz": 0}, "nz"),
        ({"dx": 0.0}, "dx"),
        ({"dy": -2.0}, "dy"),
        ({"dz": float("nan")}, "dz"),
        ({"slope_deg": 0.0}, "slope_deg"),
        ({"slope_deg": 90.0}, "slope_deg"),
        ({"slope_deg": float("inf")}, "slope_deg"),
        ({"m": 0}, "m"),
    ],
)
def test_invalid_generator_arguments_are_refused_naming_the_argument(kwargs: dict, name: str) -> None:
    args = {"nx": 3, "ny": 3, "nz": 3, "dx": 1.0, "dy": 1.0, "dz": 1.0, "slope_deg": 45.0, **kwargs}
    with pytest.raises(ValueError, match=name):
        level_cone_precedence(args.pop("nx"), args.pop("ny"), args.pop("nz"), **args)

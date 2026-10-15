"""T-017-041: volume uncertainty bounds (unit).

Requirements: FR-017-33.

Spec: specs/017-planning-survey/spec.md FR-017-33: each real volume carries two uncertainty bounds from the per-epoch
RMSEz sigma_0, sigma_1: uncorrelated A_c sqrt(N) sqrt(sigma_0^2 + sigma_1^2) and fully correlated A_c N
sqrt(sigma_0^2 + sigma_1^2), N being the number of valid cells. plan.md test strategy row FR-017-33: the two bounds by
hand for N = 4 cells.

Oracles (hand calculation): A_c = 4 m^2 (2 m cells), N = 4, sigma_0 = 0.3 m, sigma_1 = 0.4 m: sqrt(0.09 + 0.16) = 0.5,
uncorrelated 4 x sqrt(4) x 0.5 = 4 m^3, fully correlated 4 x 4 x 0.5 = 8 m^3; a second case with N = 9, A_c = 1,
sigma_0 = sigma_1 = 0.1: sqrt(0.02) = 0.141421356..., uncorrelated 3 x 0.141421356 = 0.424264069, correlated 9 x
0.141421356 = 1.272792206; scaling relations (linear in the cell area and in the RMSEz scale; the correlated bound
is N
over sqrt(N) = sqrt(N) times the uncorrelated one).

Expected public API (module `pitstudio.survey.uncertainty`, root environment, pure Python):
    @dataclass(frozen=True) UncertaintyBounds      # uncorrelated_m3: float, correlated_m3: float
    volume_uncertainty(n_valid: int, cell_size_m: float, sigma0_m: float, sigma1_m: float) -> UncertaintyBounds
        A_c = cell_size_m ** 2; ValueError naming `n_valid` (not a positive integer), `cell_size_m` (<= 0 or
        non-finite),
        `sigma0_m` or `sigma1_m` (negative or non-finite; zero is allowed).
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.survey.uncertainty import UncertaintyBounds, volume_uncertainty


@pytest.mark.req("FR-017-33")
def test_the_two_bounds_for_four_cells_by_hand() -> None:
    b = volume_uncertainty(4, 2.0, 0.3, 0.4)
    assert isinstance(b, UncertaintyBounds)
    assert b.uncorrelated_m3 == pytest.approx(4.0, rel=1e-12)
    assert b.correlated_m3 == pytest.approx(8.0, rel=1e-12)


@pytest.mark.req("FR-017-33")
def test_nine_cells_of_one_square_metre_by_hand() -> None:
    b = volume_uncertainty(9, 1.0, 0.1, 0.1)
    assert b.uncorrelated_m3 == pytest.approx(3 * math.sqrt(0.02), rel=1e-12)
    assert b.correlated_m3 == pytest.approx(9 * math.sqrt(0.02), rel=1e-12)
    assert b.uncorrelated_m3 == pytest.approx(0.424264069, abs=1e-9)
    assert b.correlated_m3 == pytest.approx(1.272792206, abs=1e-9)


@pytest.mark.req("FR-017-33")
def test_zero_rmse_gives_zero_bounds_and_one_cell_gives_equal_bounds() -> None:
    assert volume_uncertainty(10, 2.0, 0.0, 0.0) == UncertaintyBounds(0.0, 0.0)
    one = volume_uncertainty(1, 3.0, 0.3, 0.4)
    assert one.uncorrelated_m3 == pytest.approx(one.correlated_m3, rel=1e-12)  # sqrt(1) = 1
    assert one.uncorrelated_m3 == pytest.approx(9.0 * 0.5, rel=1e-12)


@pytest.mark.req("FR-017-33")
@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"n_valid": 0}, "n_valid"),
        ({"n_valid": -3}, "n_valid"),
        ({"n_valid": 2.5}, "n_valid"),
        ({"n_valid": True}, "n_valid"),
        ({"cell_size_m": 0.0}, "cell_size_m"),
        ({"cell_size_m": -1.0}, "cell_size_m"),
        ({"cell_size_m": float("nan")}, "cell_size_m"),
        ({"cell_size_m": float("inf")}, "cell_size_m"),
        ({"sigma0_m": -0.1}, "sigma0_m"),
        ({"sigma0_m": float("nan")}, "sigma0_m"),
        ({"sigma1_m": -0.1}, "sigma1_m"),
        ({"sigma1_m": float("inf")}, "sigma1_m"),
    ],
)
def test_hostile_arguments_are_refused_naming_the_argument(kwargs: dict, name: str) -> None:
    args = {"n_valid": 4, "cell_size_m": 2.0, "sigma0_m": 0.3, "sigma1_m": 0.4, **kwargs}
    with pytest.raises(ValueError, match=name):
        volume_uncertainty(**args)


@pytest.mark.req("FR-017-33")
@settings(max_examples=200, deadline=None)
@given(
    n=st.integers(1, 10**6),
    cell=st.floats(0.1, 10.0),
    s0=st.floats(0.0, 2.0),
    s1=st.floats(0.0, 2.0),
    k=st.floats(0.1, 10.0),
)
def test_relations_correlated_over_uncorrelated_is_sqrt_n_and_both_are_linear_in_area_and_rmse(n, cell, s0, s1, k):
    b = volume_uncertainty(n, cell, s0, s1)
    expected = cell**2 * math.sqrt(s0**2 + s1**2)
    assert b.uncorrelated_m3 == pytest.approx(expected * math.sqrt(n), rel=1e-12, abs=1e-300)
    assert b.correlated_m3 == pytest.approx(expected * n, rel=1e-12, abs=1e-300)
    assert b.correlated_m3 >= b.uncorrelated_m3
    scaled = volume_uncertainty(n, cell, k * s0, k * s1)  # RMSEz scale k
    assert scaled.correlated_m3 == pytest.approx(k * b.correlated_m3, rel=1e-12, abs=1e-300)
    bigger_cell = volume_uncertainty(n, k * cell, s0, s1)  # area scales by k^2
    assert bigger_cell.uncorrelated_m3 == pytest.approx(k**2 * b.uncorrelated_m3, rel=1e-12, abs=1e-300)

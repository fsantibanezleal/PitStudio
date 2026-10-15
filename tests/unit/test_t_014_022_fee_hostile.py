# ruff: noqa: E501
"""T-014-022: FEE hostile inputs and inadmissible domains.

Requirements: FR-014-21.

Spec: specs/014-robot-learning/spec.md FR-014-21: "If the FEE reference receives a non-finite or negative rho, c, c_a, q,
d or w, angles outside alpha in (0, pi/2], phi in (0, pi/2), delta in [0, phi], or inputs for which D = cos(alpha + delta)
+ sin(alpha + delta) cot(beta + phi) <= 0 for every admissible beta, then it shall raise `ValueError` naming the input."

Oracle: the domain statement of the requirement itself (hostile corpus built by hand) and the algebra of D: with
D = sin(alpha + delta + beta + phi) / sin(beta + phi), D is positive on the whole admissible interval
(0, min(pi/2, pi - alpha - delta - phi)) exactly when alpha + delta + phi < pi, and the interval is empty (D <= 0 for
every admissible beta) when alpha + delta + phi >= pi. Hand-built examples: alpha = 90 deg with delta = phi = 60 deg
gives 210 deg >= 180 deg; alpha = 90 deg, delta = 20 deg, phi = 35 deg gives 145 deg < 180 deg (valid, the rake table).

Expected API of the implementation (module `pitstudio.robots.fee`, see T-014-020): `solve_fee`, `fee_force`, `fee_factors`.
Every invalid call raises `ValueError` (not a subclass-free `Exception`, not `ZeroDivisionError`, not a returned NaN) whose
message contains the name of the offending keyword argument (`rho`, `c`, `c_a`, `q`, `d`, `w`, `alpha`, `phi`, `delta`);
for the combined inadmissible domain the message names at least one of `alpha`, `delta` or `phi`.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.robots.fee import fee_force, solve_fee

DEG = math.pi / 180.0
GOOD = {
    "alpha": 60.0 * DEG,
    "delta": 20.0 * DEG,
    "phi": 35.0 * DEG,
    "rho": 1800.0,
    "c": 10_000.0,
    "c_a": 5_000.0,
    "q": 0.0,
    "d": 0.5,
    "w": 1.0,
}
ANGLE = st.one_of(st.floats(min_value=-10.0, max_value=10.0), st.just(math.nan), st.just(math.inf), st.just(-math.inf))
BAD_STRENGTH = [math.nan, math.inf, -math.inf, -1e-9, -1.0, -1e30]


@pytest.mark.req("FR-014-21")
def test_the_good_baseline_is_valid() -> None:
    sol = solve_fee(**GOOD)
    assert math.isfinite(sol.force)
    assert sol.force > 0.0


@pytest.mark.req("FR-014-21")
@pytest.mark.parametrize("name", ["rho", "c", "c_a", "q", "d", "w"])
@pytest.mark.parametrize("bad", BAD_STRENGTH, ids=["nan", "inf", "-inf", "-1e-9", "-1", "-1e30"])
def test_non_finite_or_negative_strength_or_geometry_raises_value_error_naming_the_input(name, bad) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        solve_fee(**{**GOOD, name: bad})


@pytest.mark.req("FR-014-21")
@pytest.mark.parametrize(
    ("name", "bad"),
    [
        ("alpha", 0.0),
        ("alpha", -0.1),
        ("alpha", math.pi / 2 + 1e-9),
        ("alpha", 2.0),
        ("alpha", 90.0),  # degrees passed where radians are expected
        ("alpha", math.nan),
        ("alpha", math.inf),
        ("phi", 0.0),
        ("phi", -0.1),
        ("phi", math.pi / 2),
        ("phi", 1.6),
        ("phi", 35.0),  # degrees passed where radians are expected
        ("phi", math.nan),
        ("phi", -math.inf),
        ("delta", -1e-9),
        ("delta", 35.0 * DEG + 1e-9),  # delta > phi
        ("delta", 1.0),
        ("delta", math.nan),
        ("delta", math.inf),
    ],
)
def test_angles_outside_their_domains_raise_value_error_naming_the_input(name, bad) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        solve_fee(**{**GOOD, name: bad})


@pytest.mark.req("FR-014-21")
@pytest.mark.parametrize(
    ("alpha", "delta", "phi"),
    [
        (90.0 * DEG, 60.0 * DEG, 60.0 * DEG),  # 210 deg >= 180 deg
        (90.0 * DEG, 80.0 * DEG, 80.0 * DEG),  # 250 deg
        (80.0 * DEG, 50.0 * DEG, 50.0 * DEG + 1e-6),  # 180 deg + 1e-6 rad: the interval (0, pi - sum) is empty
        (70.0 * DEG, 60.0 * DEG, 60.0 * DEG),  # 190 deg
    ],
)
def test_inputs_with_d_not_positive_for_every_admissible_beta_raise_value_error(alpha, delta, phi) -> None:
    assert alpha + delta + phi >= math.pi  # the hand-built corpus is inadmissible by construction
    with pytest.raises(ValueError, match=r"alpha|delta|phi"):
        solve_fee(**{**GOOD, "alpha": alpha, "delta": delta, "phi": phi})
    with pytest.raises(ValueError, match=r"alpha|delta|phi"):
        fee_force(0.1, **{**GOOD, "alpha": alpha, "delta": delta, "phi": phi})


@pytest.mark.req("FR-014-21")
def test_the_boundary_just_inside_the_admissible_domain_is_accepted() -> None:
    # alpha + delta + phi = 180 deg - 0.2 deg: the admissible interval is (0, 0.2 deg), D > 0 on all of it
    alpha, phi = 80.0 * DEG, 50.0 * DEG
    delta = math.pi - 0.2 * DEG - alpha - phi
    assert 0.0 <= delta <= phi
    sol = solve_fee(**{**GOOD, "alpha": alpha, "delta": delta, "phi": phi})
    assert 0.0 < sol.beta < 0.2 * DEG
    assert math.isfinite(sol.force)


@pytest.mark.req("FR-014-21")
@pytest.mark.parametrize("alpha_deg", [90.0, 5.0], ids=["alpha-at-upper-limit", "alpha-small"])
def test_alpha_at_its_upper_limit_and_delta_at_its_two_limits_are_accepted(alpha_deg) -> None:
    for delta in (0.0, 35.0 * DEG):  # delta in [0, phi] is closed at both ends
        sol = solve_fee(**{**GOOD, "alpha": alpha_deg * DEG, "delta": delta})
        assert math.isfinite(sol.force)
        assert math.isfinite(sol.beta)


@pytest.mark.req("FR-014-21")
@pytest.mark.parametrize("zero", ["d", "w"])
def test_zero_depth_or_zero_width_gives_zero_force_not_an_error(zero) -> None:
    sol = solve_fee(**{**GOOD, zero: 0.0})
    assert sol.force == 0.0
    assert sol.draft == 0.0
    assert sol.vertical == 0.0


@pytest.mark.req("FR-014-21")
@given(
    name=st.sampled_from(["rho", "c", "c_a", "q", "d", "w"]),
    bad=st.one_of(
        st.just(math.nan),
        st.just(math.inf),
        st.just(-math.inf),
        st.floats(max_value=-1e-12, allow_nan=False, allow_infinity=False),
    ),
)
@settings(max_examples=200, deadline=None)
def test_property_any_negative_or_non_finite_strength_is_rejected(name, bad) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        solve_fee(**{**GOOD, name: bad})


@pytest.mark.req("FR-014-21")
@given(alpha=ANGLE, phi=ANGLE, delta=ANGLE)
@settings(max_examples=300, deadline=None)
def test_property_angle_domain_decides_between_a_finite_solution_and_a_value_error(alpha, phi, delta) -> None:
    valid = (
        all(math.isfinite(x) for x in (alpha, phi, delta))
        and 0.0 < alpha <= math.pi / 2
        and 0.0 < phi < math.pi / 2
        and 0.0 <= delta <= phi
        and alpha + delta + phi < math.pi - 1e-9  # the open boundary is covered by the parametrised tests above
    )
    inadmissible = not all(math.isfinite(x) for x in (alpha, phi, delta)) or not (
        0.0 < alpha <= math.pi / 2 and 0.0 < phi < math.pi / 2 and 0.0 <= delta <= phi and alpha + delta + phi < math.pi
    )
    args = {**GOOD, "alpha": alpha, "phi": phi, "delta": delta}
    if valid:
        sol = solve_fee(**args)
        assert math.isfinite(sol.force)
    elif inadmissible:
        with pytest.raises(ValueError, match=r"alpha|delta|phi"):
            solve_fee(**args)

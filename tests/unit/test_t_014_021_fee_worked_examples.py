# ruff: noqa: E501
"""T-014-021: FEE equilibrium oracle and worked examples (cohesionless, cohesive, rake table); the cutting-force state.

Requirements: FR-014-17, P-014-04, P-014-06.

Spec: specs/014-robot-learning/spec.md FR-014-17 (the force acts only while the lip is below the surface and moves into
the soil; the rake from the lip pose is clamped to [5 deg, 90 deg]; draft opposes the horizontal motion; the bucket
carries the weight of its fill), P-014-04 (factor form equals the 2 x 2 wedge-equilibrium solve, rtol 1e-10),
P-014-06 and section 7 (hand-calculated worked examples and the rake table, rtol 1e-3, beta* atol 0.01 deg).

Oracle: (1) the 2 x 2 linear solve of the two wedge equilibrium equations of docs/theory/loading-and-terramechanics.md
section 3, written in tests/support/robots_oracles.py and independent of the factor form; (2) the numbers printed in
spec 014 P-014-06 and section 7 (hand calculation, alpha = 60 deg, delta = 20 deg, phi = 35 deg, d = 0.5 m, w = 1 m,
rho = 1,800 kg/m3, g = 9.81 m/s2); (3) the weight of the fill, m g with m = rho V_fill (hand calculation).

Expected API of the implementation (module `pitstudio.robots.fee`, see T-014-020 for the first four):
    fee_factors, fee_force, solve_fee, FeeSolution
    clamp_rake(alpha) -> float
        alpha clamped to [5 deg, 90 deg] (rad in, rad out)
    cutting_force(*, depth, tip_velocity_x, rake, delta, phi, rho, c, c_a, q, w, g=9.81) -> tuple[float, float]
        (Fx, Fz) on the bucket lip in the machine frame (x forward, z up), in N. depth is d (m, positive below the
        surface), tip_velocity_x is the horizontal tip velocity (m/s, positive into the soil), rake is the lip rake from
        the lip pose (rad, clamped by clamp_rake). The force is (0.0, 0.0) unless depth > 0 and tip_velocity_x > 0;
        otherwise Fx = -H (the draft opposes the motion) and Fz = -V (V > 0 pulls the tool into the ground).
    fill_weight(v_fill, rho, g=9.81) -> float
        weight of the fill (N, a positive number): rho * g * v_fill.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import robots_oracles as ref
from pitstudio.robots.fee import clamp_rake, cutting_force, fee_force, fill_weight, solve_fee

DEG = math.pi / 180.0
BASE = {"delta": 20.0 * DEG, "phi": 35.0 * DEG, "d": 0.5, "w": 1.0, "rho": 1800.0, "q": 0.0}

# Spec 014 section 7: rake table, cohesionless (alpha deg, beta* deg, N_gamma, F kN, H kN, V kN); alpha = 60 is P-014-06.
RAKE_TABLE = [
    (30.0, 35.589, 1.7143, 7.5679, 5.7973, 4.8646),
    (45.0, 32.826, 1.6100, 7.1071, 6.4413, 3.0036),
    (60.0, 28.105, 1.8196, 8.0327, 7.9107, 1.3949),
    (75.0, 22.423, 2.4495, 10.8133, 10.7721, -0.9424),
    (90.0, 16.174, 4.1619, 18.3728, 17.2648, -6.2839),
]


@pytest.mark.req("P-014-06")
@pytest.mark.parametrize(("alpha", "beta", "n_gamma", "f_kn", "h_kn", "v_kn"), RAKE_TABLE)
def test_rake_table_cohesionless(alpha, beta, n_gamma, f_kn, h_kn, v_kn) -> None:
    sol = solve_fee(alpha=alpha * DEG, c=0.0, c_a=0.0, **BASE)
    assert sol.beta / DEG == pytest.approx(beta, abs=0.01)
    assert sol.n_gamma == pytest.approx(n_gamma, rel=1e-3)
    assert sol.force / 1e3 == pytest.approx(f_kn, rel=1e-3)
    assert sol.draft / 1e3 == pytest.approx(h_kn, rel=1e-3)
    assert sol.vertical / 1e3 == pytest.approx(v_kn, rel=1e-3)


@pytest.mark.req("P-014-06")
def test_cohesionless_worked_example_matches_the_printed_values() -> None:
    sol = solve_fee(alpha=60.0 * DEG, c=0.0, c_a=0.0, **BASE)
    assert sol.beta / DEG == pytest.approx(28.105, abs=0.01)
    assert sol.n_gamma == pytest.approx(1.8196, rel=1e-3)
    assert sol.force == pytest.approx(8032.7, rel=1e-3)
    assert sol.draft == pytest.approx(7910.7, rel=1e-3)
    assert sol.vertical == pytest.approx(1394.9, rel=1e-3)
    # F = rho g d^2 N_gamma w, with the three cohesive terms absent: the weight term alone
    assert sol.force == pytest.approx(1800.0 * 9.81 * 0.25 * sol.n_gamma * 1.0, rel=1e-12)


@pytest.mark.req("P-014-06")
def test_cohesive_worked_example_c_10_kpa_ca_5_kpa() -> None:
    sol = solve_fee(alpha=60.0 * DEG, c=10_000.0, c_a=5_000.0, **BASE)
    assert sol.beta / DEG == pytest.approx(28.206, abs=0.01)
    assert sol.force == pytest.approx(25_141.0, rel=1e-3)


@pytest.mark.req("P-014-06")
def test_cohesion_dominates_a_shallow_cut_the_term_ratio_of_the_theory_example() -> None:
    # Theory doc worked example 2: cohesion scales with d, the weight term with d^2, so a shallow cut is cohesion-led.
    shallow = solve_fee(alpha=60.0 * DEG, c=10_000.0, c_a=5_000.0, **{**BASE, "d": 0.05})
    weight_only = solve_fee(alpha=60.0 * DEG, c=0.0, c_a=0.0, **{**BASE, "d": 0.05})
    assert shallow.force > 10.0 * weight_only.force


# --------------------------------------------------------------------------------------------------------- P-014-04
@st.composite
def admissible_cases(draw):
    phi = draw(st.floats(25.0, 40.0)) * DEG
    delta = min(draw(st.floats(10.0, 25.0)) * DEG, phi)
    alpha = draw(st.floats(5.0, 90.0)) * DEG
    c = draw(st.floats(0.0, 20_000.0))
    kw = {
        "alpha": alpha,
        "delta": delta,
        "phi": phi,
        "rho": draw(st.floats(1500.0, 2100.0)),
        "c": c,
        "c_a": draw(st.floats(0.0, 0.5)) * c,
        "q": draw(st.floats(0.0, 5_000.0)),
        "d": draw(st.floats(0.01, 2.0)),
        "w": draw(st.floats(0.1, 3.0)),
    }
    beta = draw(st.floats(0.02, 0.98)) * ref.beta_upper(alpha, delta, phi)
    return beta, kw


@pytest.mark.req("P-014-04")
@given(admissible_cases())
@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_p04_factor_form_equals_the_two_by_two_wedge_equilibrium_solve(case) -> None:
    beta, kw = case
    want = ref.fee_force_wedge_equilibrium(beta, **kw)
    assert fee_force(beta, **kw) == pytest.approx(want, rel=1e-10, abs=1e-9)


@pytest.mark.req("P-014-04")
def test_p04_minimum_force_equals_the_equilibrium_solve_at_the_minimiser() -> None:
    kw = {"alpha": 60.0 * DEG, "c": 10_000.0, "c_a": 5_000.0, **BASE}
    sol = solve_fee(**kw)
    assert sol.force == pytest.approx(ref.fee_force_wedge_equilibrium(sol.beta, **kw), rel=1e-10)


# ------------------------------------------------------------------------------------------ state, clamp, weight
@pytest.mark.req("FR-014-17")
def test_clamp_rake_to_5_and_90_degrees() -> None:
    assert clamp_rake(2.0 * DEG) == pytest.approx(5.0 * DEG, abs=1e-15)
    assert clamp_rake(0.0) == pytest.approx(5.0 * DEG, abs=1e-15)
    assert clamp_rake(-0.3) == pytest.approx(5.0 * DEG, abs=1e-15)
    assert clamp_rake(45.0 * DEG) == pytest.approx(45.0 * DEG, abs=1e-15)
    assert clamp_rake(90.0 * DEG) == pytest.approx(90.0 * DEG, abs=1e-15)
    assert clamp_rake(120.0 * DEG) == pytest.approx(90.0 * DEG, abs=1e-15)


@pytest.mark.req("FR-014-17")
def test_cutting_force_below_the_surface_moving_into_the_soil_is_the_worked_example() -> None:
    fx, fz = cutting_force(
        depth=0.5, tip_velocity_x=0.4, rake=60.0 * DEG, delta=20.0 * DEG, phi=35.0 * DEG, rho=1800.0, c=0.0, c_a=0.0,
        q=0.0, w=1.0,
    )  # fmt: skip
    assert fx == pytest.approx(-7910.7, rel=1e-3)  # draft H opposes the horizontal motion
    assert fz == pytest.approx(-1394.9, rel=1e-3)  # V > 0 pulls the tool into the ground


@pytest.mark.req("FR-014-17")
@pytest.mark.parametrize(
    ("depth", "vx"),
    [(0.0, 0.4), (-0.1, 0.4), (0.5, 0.0), (0.5, -0.4), (-0.5, -0.4), (1e-12, 0.0)],
    ids=["at-surface", "above-surface", "stationary", "retreating", "above-and-retreating", "touching-stationary"],
)
def test_cutting_force_is_zero_unless_below_the_surface_and_moving_into_the_soil(depth, vx) -> None:
    out = cutting_force(
        depth=depth, tip_velocity_x=vx, rake=60.0 * DEG, delta=20.0 * DEG, phi=35.0 * DEG, rho=1800.0, c=1e4, c_a=5e3,
        q=0.0, w=1.0,
    )  # fmt: skip
    assert out == (0.0, 0.0)


@pytest.mark.req("FR-014-17")
def test_cutting_force_uses_the_clamped_rake() -> None:
    soil = {
        "depth": 0.3, "tip_velocity_x": 0.2, "delta": 20.0 * DEG, "phi": 35.0 * DEG, "rho": 1800.0, "c": 5e3,
        "c_a": 1e3, "q": 0.0, "w": 1.2,
    }  # fmt: skip
    low = cutting_force(rake=1.0 * DEG, **soil)
    five = cutting_force(rake=5.0 * DEG, **soil)
    assert low == pytest.approx(five, rel=1e-12)
    high = cutting_force(rake=150.0 * DEG, **soil)
    ninety = cutting_force(rake=90.0 * DEG, **soil)
    assert high == pytest.approx(ninety, rel=1e-12)


@pytest.mark.req("FR-014-17")
def test_the_bucket_carries_the_weight_of_its_fill() -> None:
    # hand calculation: 1.5 m3 of 1,800 kg/m3 soil is 2,700 kg, which weighs 2,700 * 9.81 = 26,487 N
    assert fill_weight(1.5, 1800.0) == pytest.approx(26_487.0, rel=1e-12)
    assert fill_weight(0.0, 1800.0) == 0.0
    assert fill_weight(0.75, 1800.0, g=9.81) == pytest.approx(13_243.5, rel=1e-12)

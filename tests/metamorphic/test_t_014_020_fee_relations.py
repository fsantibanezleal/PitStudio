# ruff: noqa: E501
"""T-014-020: FEE wedge reference (factors, failure-angle minimiser, draft/vertical split) and its metamorphic relations.

Requirements: FR-014-17, P-014-01, P-014-02, P-014-03, P-014-05.

Spec: specs/014-robot-learning/spec.md FR-014-17 and P-014-01 .. P-014-05 (tolerances: rtol 1e-9 for F, atol 1e-8 rad for
beta*, "exact ordering" for P-014-05); plan.md "FEE wedge reference".

Oracle: (1) the factor expressions of docs/theory/loading-and-terramechanics.md section 3, transcribed in
tests/support/robots_oracles.py; (2) a dense-grid plus golden-section minimiser written in the test support (a different
algorithm from the implementation's bounded scalar minimiser); (3) the relations of the spec themselves (width
scaling, homogeneity in the soil strengths, depth scaling for a cohesionless soil, monotonicity in rho and q), which
need no reference value. Hypothesis draws >= 200 examples per relation from the FR-014-19 soil ranges and the
P-014-01 domain (alpha in [5 deg, 90 deg], d in [0.01, 2] m).

Numerical note for the implementer: F is flat at its minimum, so a minimiser that compares F values cannot resolve beta*
better than about 3e-8 rad at shallow rakes (measured with a golden-section search at alpha = 5 deg, delta = 10 deg,
phi = 25 deg), while P-014-01 and P-014-02 require atol 1e-8 rad. Solving dF/dbeta = 0 (a root find on the analytic
derivative of the factor form) meets it; the tests were checked against such a solver.

Expected API of the implementation (module `pitstudio.robots.fee`, NumPy float64, angles in rad, SI units, g = 9.81):
    fee_factors(alpha, beta, delta, phi) -> (n_gamma, n_c, n_a, n_q)
    fee_force(beta, *, alpha, delta, phi, rho, c, c_a, q, d, w, g=9.81) -> float
        F at a given failure angle beta (factor form)
    solve_fee(*, alpha, delta, phi, rho, c, c_a, q, d, w, g=9.81) -> FeeSolution
        FeeSolution is a frozen dataclass with float fields
        beta (the failure angle minimising F over (0, min(pi/2, pi - alpha - delta - phi))), n_gamma, n_c, n_a, n_q
        (the factors at beta), force (F), draft (H = F sin(alpha + delta)) and vertical (V = F cos(alpha + delta)).
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
from pitstudio.robots.fee import fee_factors, fee_force, solve_fee

DEG = math.pi / 180.0
SETTINGS = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@st.composite
def wedge_inputs(draw, *, with_q: bool = False, cohesionless: bool = False):
    """Soil of FR-014-19, tool of P-014-01: alpha in [5, 90] deg, d in [0.01, 2] m, w in [0.1, 3] m."""
    phi = draw(st.floats(25.0, 40.0)) * DEG
    delta = draw(st.floats(10.0, 25.0)) * DEG
    delta = min(delta, phi)
    rho = draw(st.floats(1500.0, 2100.0))
    c = 0.0 if cohesionless else draw(st.floats(0.0, 20_000.0))
    c_a = 0.0 if cohesionless else draw(st.floats(0.0, 0.5)) * c
    q = draw(st.floats(0.0, 5_000.0)) if with_q else 0.0
    return {
        "alpha": draw(st.floats(5.0, 90.0)) * DEG,
        "delta": delta,
        "phi": phi,
        "rho": rho,
        "c": c,
        "c_a": c_a,
        "q": q,
        "d": draw(st.floats(0.01, 2.0)),
        "w": draw(st.floats(0.1, 3.0)),
    }


# ------------------------------------------------------------------------------------------ factors and minimiser
@pytest.mark.req("FR-014-17")
@given(
    alpha=st.floats(5.0, 90.0),
    delta=st.floats(10.0, 25.0),
    phi=st.floats(25.0, 40.0),
    frac=st.floats(0.05, 0.95),
)
@SETTINGS
def test_factors_match_the_closed_form_at_any_admissible_beta(alpha, delta, phi, frac) -> None:
    a, p = alpha * DEG, phi * DEG
    dl = min(delta * DEG, p)
    beta = frac * ref.beta_upper(a, dl, p)
    got = fee_factors(a, beta, dl, p)
    want = ref.fee_factors_ref(a, beta, dl, p)
    assert got == pytest.approx(want, rel=1e-12, abs=0.0)


@pytest.mark.req("FR-014-17")
@given(wedge_inputs(with_q=True))
@SETTINGS
def test_force_at_a_given_beta_equals_the_factor_form(kw) -> None:
    beta = 0.5 * ref.beta_upper(kw["alpha"], kw["delta"], kw["phi"])
    assert fee_force(beta, **kw) == pytest.approx(ref.fee_force_factor_form(beta, **kw), rel=1e-12)


@pytest.mark.req("FR-014-17")
@given(wedge_inputs(with_q=True))
@SETTINGS
def test_beta_star_is_the_minimiser_of_f_over_the_admissible_interval(kw) -> None:
    sol = solve_fee(**kw)
    hi = ref.beta_upper(kw["alpha"], kw["delta"], kw["phi"])
    assert 0.0 < sol.beta < hi
    ref_beta, ref_force = ref.fee_minimum_grid(**kw)
    # F is flat at its minimum (dF/dbeta = 0), so the values agree far more closely than the angles do
    assert sol.force == pytest.approx(ref_force, rel=1e-9)
    assert sol.force == pytest.approx(ref.fee_force_factor_form(sol.beta, **kw), rel=1e-12)
    # no admissible beta gives a smaller force (up to the rounding of the factor form)
    for frac in (0.001, 0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 0.999):
        assert ref.fee_force_factor_form(frac * hi, **kw) >= sol.force * (1.0 - 1e-12)
    assert abs(sol.beta - ref_beta) < 1e-4  # a loose angle check; the sharp one is the force value above


@pytest.mark.req("FR-014-17")
@given(wedge_inputs(with_q=True))
@SETTINGS
def test_draft_and_vertical_split_the_force_at_alpha_plus_delta(kw) -> None:
    sol = solve_fee(**kw)
    ad = kw["alpha"] + kw["delta"]
    assert sol.draft == pytest.approx(sol.force * math.sin(ad), rel=1e-12)
    assert sol.vertical == pytest.approx(sol.force * math.cos(ad), rel=1e-12, abs=1e-9)
    # F itself may be negative for a shallow rake with adhesion (N_a < 0), so the split preserves |F|
    assert math.hypot(sol.draft, sol.vertical) == pytest.approx(abs(sol.force), rel=1e-12)
    ng, nc, na, nq = ref.fee_factors_ref(kw["alpha"], sol.beta, kw["delta"], kw["phi"])
    assert (sol.n_gamma, sol.n_c, sol.n_a, sol.n_q) == pytest.approx((ng, nc, na, nq), rel=1e-12)


# --------------------------------------------------------------------------------------- metamorphic relations
@pytest.mark.req("P-014-01")
@given(wedge_inputs(with_q=True), st.floats(0.1, 10.0))
@SETTINGS
def test_p01_width_scaling_scales_force_and_keeps_beta(kw, k) -> None:
    base = solve_fee(**kw)
    wide = solve_fee(**{**kw, "w": k * kw["w"]})
    assert wide.force == pytest.approx(k * base.force, rel=1e-9)
    assert wide.beta == pytest.approx(base.beta, abs=1e-8)


@pytest.mark.req("P-014-02")
@given(wedge_inputs(with_q=True), st.floats(0.1, 10.0))
@SETTINGS
def test_p02_scaling_all_soil_strengths_scales_force_and_keeps_beta(kw, k) -> None:
    base = solve_fee(**kw)
    scaled = solve_fee(**{**kw, "rho": k * kw["rho"], "c": k * kw["c"], "c_a": k * kw["c_a"], "q": k * kw["q"]})
    assert scaled.force == pytest.approx(k * base.force, rel=1e-9)
    assert scaled.beta == pytest.approx(base.beta, abs=1e-8)


@pytest.mark.req("P-014-03")
@given(wedge_inputs(cohesionless=True), st.floats(0.1, 10.0))
@SETTINGS
def test_p03_cohesionless_force_scales_with_depth_squared(kw, k) -> None:
    base = solve_fee(**kw)
    deep = solve_fee(**{**kw, "d": k * kw["d"]})
    assert deep.force == pytest.approx(k * k * base.force, rel=1e-9)


@pytest.mark.req("P-014-05")
@given(wedge_inputs(with_q=True), st.floats(1.001, 5.0), st.floats(1.001, 5.0))
@SETTINGS
def test_p05_force_is_non_decreasing_in_rho_and_in_q(kw, k_rho, k_q) -> None:
    base = solve_fee(**kw).force
    # the minimum of functions that are each non-decreasing in rho (N_gamma >= 0) is non-decreasing; the slack
    # of 1e-12 absorbs the rounding of the scalar minimiser (error O(dbeta^2) in F)
    more_rho = solve_fee(**{**kw, "rho": k_rho * kw["rho"]}).force
    assert more_rho >= base * (1.0 - 1e-12)
    q0 = max(kw["q"], 100.0)
    lo = solve_fee(**{**kw, "q": q0}).force
    hi = solve_fee(**{**kw, "q": k_q * q0}).force
    assert hi >= lo * (1.0 - 1e-12)


@pytest.mark.req("P-014-05")
def test_p05_the_factors_n_gamma_and_n_q_are_non_negative_over_the_admissible_interval() -> None:
    for alpha_deg in (5.0, 30.0, 60.0, 90.0):
        for phi_deg, delta_deg in ((25.0, 10.0), (35.0, 20.0), (40.0, 25.0)):
            a, p, dl = alpha_deg * DEG, phi_deg * DEG, delta_deg * DEG
            hi = ref.beta_upper(a, dl, p)
            for i in range(1, 100):
                ng, _nc, _na, nq = fee_factors(a, hi * i / 100.0, dl, p)
                assert ng >= 0.0
                assert nq >= 0.0

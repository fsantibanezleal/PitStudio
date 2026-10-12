"""T-005-010 - FR-005-01: Hertz-Mindlin contact law and effective properties of the Warp DEM.

Oracle: hand calculation of the closed-form contact law written out below (no call into the code under test is
used to build an expected value). Sources: LAMMPS `pair_style granular`, section "Description"
(https://docs.lammps.org/pair_granular.html) for the Hertz force (4/3) E* sqrt(R*) delta^(3/2), the Mindlin stiffness
8 G* a and the effective moduli; spec 005 FR-005-01 for the damping form, the Coulomb cap, the rolling-torque cap and
the worked example (R = 5 mm, E = 50 MPa, nu = 0.25, delta_n = 0.01 R: F_n = 0.6285 N, S_n = 1.8856e4 N/m,
S_t = 1.6162e4 N/m). Tolerance: rtol 1e-5 (plan 005, "Contact forces": float32 kernel, about ten operations).

Expected public API (module `pitstudio_studio.physics.dem.contact`):

    EffectiveProperties     frozen dataclass with float fields e_star [Pa], g_star [Pa], r_star [m], m_star [kg]
    effective_properties(*, youngs_1, poisson_1, radius_1, mass_1,
                            youngs_2, poisson_2, radius_2, mass_2) -> EffectiveProperties
        1/E* = (1 - nu1^2)/E1 + (1 - nu2^2)/E2;  1/G* = (2 - nu1)/G1 + (2 - nu2)/G2 with G = E / (2 (1 + nu));
        1/R* = 1/R1 + 1/R2;  1/m* = 1/m1 + 1/m2.  A wall passes radius_2 = math.inf and mass_2 = math.inf.
    damping_beta(restitution: float) -> float          beta = ln e / sqrt(ln^2 e + pi^2)  (0 for e = 1)
    evaluate_contacts(props, *, delta_n, v_n, delta_t, rolling_angle, restitution, friction_static,
                      friction_rolling, device) -> ContactForces
        Evaluates the contact law for N contacts in ONE Warp kernel launch on `device` ("cpu" in CI).
        delta_n (N,) normal overlap [m] (> 0 means in contact); v_n (N,) relative normal velocity [m/s], positive
        while the overlap grows (approach); delta_t (N, 3) accumulated tangential spring displacement [m];
        rolling_angle (N, 3) accumulated relative rolling rotation [rad].
    ContactForces                       numpy float arrays, one entry per contact:
        fn_elastic (N,)   = (4/3) E* sqrt(R*) delta_n^(3/2)                           [N]
        fn_damping (N,)   = -2 sqrt(5/6) beta sqrt(S_n m*) v_n                         [N]
        s_n (N,)          = 2 E* sqrt(R* delta_n)                                      [N/m]
        s_t (N,)          = 8 G* sqrt(R* delta_n)                                      [N/m]
        ft (N, 3)         = -S_t delta_t, capped so that |ft| <= mu_s F_n              [N]
        torque_rolling (N, 3)  elastic-plastic rolling resistance, |torque| <= mu_r R* F_n, opposing rolling_angle
        Contacts with delta_n <= 0 return zero force, stiffness and torque.
    The Coulomb and rolling caps are evaluated here with v_n = 0, where F_n = fn_elastic and every reading of
    "F_n" in FR-005-01 coincides.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)

from pitstudio_studio.physics.dem.contact import (  # noqa: E402
    EffectiveProperties,
    damping_beta,
    effective_properties,
    evaluate_contacts,
)

DEVICE = "cpu"  # Warp CPU device; the CI job hides CUDA
RTOL = 1.0e-5  # plan 005, tolerance "Contact forces"

# Worked example of FR-005-01 (spec 005, section 3.1).
R = 5.0e-3  # m
E = 50.0e6  # Pa
NU = 0.25
RHO = 2650.0  # kg/m^3 (only enters through the mass)
MASS = RHO * 4.0 / 3.0 * math.pi * R**3


def hand_e_star(e1: float, nu1: float, e2: float, nu2: float) -> float:
    return 1.0 / ((1.0 - nu1**2) / e1 + (1.0 - nu2**2) / e2)


def hand_g_star(e1: float, nu1: float, e2: float, nu2: float) -> float:
    g1 = e1 / (2.0 * (1.0 + nu1))
    g2 = e2 / (2.0 * (1.0 + nu2))
    return 1.0 / ((2.0 - nu1) / g1 + (2.0 - nu2) / g2)


def worked_props() -> EffectiveProperties:
    return effective_properties(
        youngs_1=E, poisson_1=NU, radius_1=R, mass_1=MASS, youngs_2=E, poisson_2=NU, radius_2=R, mass_2=MASS
    )


def run(props, delta_n, *, v_n=None, delta_t=None, rolling_angle=None, e=0.5, mu_s=0.5, mu_r=0.1):
    n = len(delta_n)
    return evaluate_contacts(
        props,
        delta_n=np.asarray(delta_n, dtype=np.float32),
        v_n=np.zeros(n, np.float32) if v_n is None else np.asarray(v_n, np.float32),
        delta_t=np.zeros((n, 3), np.float32) if delta_t is None else np.asarray(delta_t, np.float32),
        rolling_angle=np.zeros((n, 3), np.float32) if rolling_angle is None else np.asarray(rolling_angle, np.float32),
        restitution=e,
        friction_static=mu_s,
        friction_rolling=mu_r,
        device=DEVICE,
    )


# ---------------------------------------------------------------- hand calculation of the worked example
# E* = E / (2 (1 - nu^2)) = 50e6 / 1.875 = 2.6667e7 Pa;  G = E / 2.5 = 2.0e7 Pa;  G* = G / (2 (2 - nu)) = 5.7143e6 Pa
# R* = R / 2 = 2.5e-3 m;  delta_n = 0.01 R = 5e-5 m
# F_n = (4/3) (2.6667e7) sqrt(2.5e-3) (5e-5)^1.5 = 0.62854 N
# S_n = 2 (2.6667e7) sqrt(2.5e-3 * 5e-5) = 1.8856e4 N/m ;  S_t = 8 (5.7143e6) sqrt(1.25e-7) = 1.6162e4 N/m
E_STAR = hand_e_star(E, NU, E, NU)
G_STAR = hand_g_star(E, NU, E, NU)
R_STAR = R / 2.0
DELTA = 0.01 * R
FN_HAND = 4.0 / 3.0 * E_STAR * math.sqrt(R_STAR) * DELTA**1.5
SN_HAND = 2.0 * E_STAR * math.sqrt(R_STAR * DELTA)
ST_HAND = 8.0 * G_STAR * math.sqrt(R_STAR * DELTA)


@pytest.mark.req("FR-005-01")
def test_hand_calculation_matches_the_spec_worked_example() -> None:
    """Oracle self-check: the spec's rounded values equal the closed form (no code under test involved)."""
    assert abs(FN_HAND / 0.6285 - 1.0) <= 1e-4
    assert abs(SN_HAND / 1.8856e4 - 1.0) <= 1e-4
    assert abs(ST_HAND / 1.6162e4 - 1.0) <= 1e-4


@pytest.mark.req("FR-005-01")
def test_effective_properties_of_two_equal_spheres() -> None:
    p = worked_props()
    assert p.e_star == pytest.approx(E_STAR, rel=1e-12)
    assert p.g_star == pytest.approx(G_STAR, rel=1e-12)
    assert p.r_star == pytest.approx(R_STAR, rel=1e-12)
    assert p.m_star == pytest.approx(MASS / 2.0, rel=1e-12)


@pytest.mark.req("FR-005-01")
def test_effective_properties_of_unequal_spheres() -> None:
    # Hand values: sphere 1 (50 MPa, 0.25, 5 mm, m1); sphere 2 (200 MPa, 0.30, 10 mm, m2 = 3 m1)
    e2, nu2, r2, m2 = 200.0e6, 0.30, 10.0e-3, 3.0 * MASS
    p = effective_properties(
        youngs_1=E, poisson_1=NU, radius_1=R, mass_1=MASS, youngs_2=e2, poisson_2=nu2, radius_2=r2, mass_2=m2
    )
    # 1/E* = 0.9375/50e6 + 0.91/200e6 = 1.875e-8 + 4.55e-9 = 2.33e-8  ->  E* = 4.29185e7 Pa
    assert p.e_star == pytest.approx(1.0 / 2.33e-8, rel=1e-12)
    # G1 = 2e7, G2 = 200e6 / 2.6 = 7.69231e7;  1/G* = 1.75/2e7 + 1.70/7.69231e7 = 8.75e-8 + 2.21e-8 = 1.096e-7
    assert p.g_star == pytest.approx(1.0 / (1.75 / 2.0e7 + 1.70 / (200.0e6 / 2.6)), rel=1e-12)
    assert p.g_star == pytest.approx(1.0 / 1.096e-7, rel=1e-9)
    # 1/R* = 1/5e-3 + 1/10e-3 = 300  ->  R* = 3.3333e-3 m;  m* = m1 m2 / (m1 + m2) = 0.75 m1
    assert p.r_star == pytest.approx(1.0 / 300.0, rel=1e-12)
    assert p.m_star == pytest.approx(0.75 * MASS, rel=1e-12)


@pytest.mark.req("FR-005-01")
def test_effective_properties_against_a_wall() -> None:
    """A wall has R -> inf and m -> inf: R* = R1 and m* = m1; the moduli still combine both materials."""
    e2, nu2 = 1.0e9, 0.2
    p = effective_properties(
        youngs_1=E,
        poisson_1=NU,
        radius_1=R,
        mass_1=MASS,
        youngs_2=e2,
        poisson_2=nu2,
        radius_2=math.inf,
        mass_2=math.inf,
    )
    assert p.r_star == pytest.approx(R, rel=1e-12)
    assert p.m_star == pytest.approx(MASS, rel=1e-12)
    assert p.e_star == pytest.approx(hand_e_star(E, NU, e2, nu2), rel=1e-12)
    assert p.g_star == pytest.approx(hand_g_star(E, NU, e2, nu2), rel=1e-12)


@pytest.mark.req("FR-005-01")
@pytest.mark.parametrize(
    ("e", "beta_hand"),
    [
        # beta = ln e / sqrt(ln^2 e + pi^2), evaluated by hand to 6 digits
        (0.5, -0.6931472 / math.sqrt(0.6931472**2 + math.pi**2)),  # -0.215467
        (0.1, -2.3025851 / math.sqrt(2.3025851**2 + math.pi**2)),  # -0.591155
        (0.9, -0.1053605 / math.sqrt(0.1053605**2 + math.pi**2)),  # -0.033518
        (1.0, 0.0),
    ],
)
def test_damping_beta(e: float, beta_hand: float) -> None:
    assert damping_beta(e) == pytest.approx(beta_hand, rel=1e-6, abs=1e-12)


@pytest.mark.req("FR-005-01")
def test_worked_example_forces_and_stiffnesses_on_warp_cpu() -> None:
    out = run(worked_props(), [DELTA])
    assert float(out.fn_elastic[0]) == pytest.approx(FN_HAND, rel=RTOL)
    assert float(out.s_n[0]) == pytest.approx(SN_HAND, rel=RTOL)
    assert float(out.s_t[0]) == pytest.approx(ST_HAND, rel=RTOL)
    assert float(out.fn_damping[0]) == 0.0  # v_n = 0


@pytest.mark.req("FR-005-01")
def test_hertz_force_scales_as_overlap_to_the_three_halves() -> None:
    """Batch of overlaps in one launch; each entry against the closed form (and hence F ~ delta^1.5)."""
    deltas = np.array([1e-4, 1e-3, 1e-2, 5e-2]) * R
    out = run(worked_props(), deltas)
    k = 4.0 / 3.0 * E_STAR * math.sqrt(R_STAR)
    np.testing.assert_allclose(out.fn_elastic, k * deltas**1.5, rtol=RTOL)
    np.testing.assert_allclose(out.s_n, 2.0 * E_STAR * np.sqrt(R_STAR * deltas), rtol=RTOL)
    np.testing.assert_allclose(out.s_t, 8.0 * G_STAR * np.sqrt(R_STAR * deltas), rtol=RTOL)


@pytest.mark.req("FR-005-01")
def test_no_force_without_overlap() -> None:
    out = run(worked_props(), [0.0, -1e-4], v_n=[1.0, 1.0], delta_t=[[1e-5, 0, 0], [1e-5, 0, 0]])
    np.testing.assert_array_equal(out.fn_elastic, [0.0, 0.0])
    np.testing.assert_array_equal(out.fn_damping, [0.0, 0.0])
    np.testing.assert_array_equal(out.ft, np.zeros((2, 3)))
    np.testing.assert_array_equal(out.torque_rolling, np.zeros((2, 3)))


@pytest.mark.req("FR-005-01")
@pytest.mark.parametrize("v_n", [0.5, -0.5, 2.0])
def test_normal_damping_force(v_n: float) -> None:
    """F_d = -2 sqrt(5/6) beta sqrt(S_n m*) v_n: repulsive while approaching (v_n > 0), attractive while separating."""
    e = 0.5
    beta = math.log(e) / math.sqrt(math.log(e) ** 2 + math.pi**2)
    expected = -2.0 * math.sqrt(5.0 / 6.0) * beta * math.sqrt(SN_HAND * MASS / 2.0) * v_n
    out = run(worked_props(), [DELTA], v_n=[v_n], e=e)
    assert float(out.fn_damping[0]) == pytest.approx(expected, rel=RTOL)
    assert math.copysign(1.0, float(out.fn_damping[0])) == math.copysign(1.0, v_n)


@pytest.mark.req("FR-005-01")
def test_elastic_restitution_has_no_damping() -> None:
    out = run(worked_props(), [DELTA], v_n=[1.0], e=1.0)
    assert float(out.fn_damping[0]) == 0.0


@pytest.mark.req("FR-005-01")
def test_mindlin_spring_below_the_coulomb_cap() -> None:
    mu_s = 0.5
    # |S_t delta_t| = 1.6162e4 * 1e-6 = 0.0162 N < mu_s F_n = 0.314 N: elastic branch, F_t = -S_t delta_t
    dt_vec = np.array([[1.0e-6, -0.5e-6, 0.25e-6]])
    out = run(worked_props(), [DELTA], delta_t=dt_vec, mu_s=mu_s)
    np.testing.assert_allclose(out.ft[0], -ST_HAND * dt_vec[0], rtol=RTOL, atol=1e-12)


@pytest.mark.req("FR-005-01")
def test_coulomb_cap_on_the_tangential_force() -> None:
    mu_s = 0.5
    # |S_t delta_t| = 1.6162e4 * 1e-4 = 1.62 N > mu_s F_n = 0.3143 N: |F_t| = mu_s F_n along -delta_t
    dt_vec = np.array([[1.0e-4, 0.0, 0.0], [0.0, -3.0e-4, 4.0e-4]])
    out = run(worked_props(), [DELTA, DELTA], delta_t=dt_vec, mu_s=mu_s)
    cap = mu_s * FN_HAND
    for k in range(2):
        mag = float(np.linalg.norm(out.ft[k]))
        assert mag == pytest.approx(cap, rel=RTOL)
        direction = -dt_vec[k] / np.linalg.norm(dt_vec[k])
        np.testing.assert_allclose(out.ft[k] / mag, direction, atol=1e-6)


@pytest.mark.req("FR-005-01")
def test_frictionless_contact_has_no_tangential_force() -> None:
    out = run(worked_props(), [DELTA], delta_t=[[1e-5, 1e-5, 0.0]], mu_s=0.0)
    np.testing.assert_array_equal(out.ft, np.zeros((1, 3)))


@pytest.mark.req("FR-005-01")
def test_rolling_torque_saturates_at_its_cap() -> None:
    """A large accumulated rolling rotation drives the elastic-plastic model to its plastic limit mu_r R* F_n."""
    mu_r = 0.1
    angle = np.array([[0.0, 10.0, 0.0], [-6.0, 0.0, 8.0]])  # rad, far beyond the elastic range
    out = run(worked_props(), [DELTA, DELTA], rolling_angle=angle, mu_r=mu_r)
    cap = mu_r * R_STAR * FN_HAND  # 0.1 * 2.5e-3 * 0.6285 = 1.571e-4 N m
    for k in range(2):
        mag = float(np.linalg.norm(out.torque_rolling[k]))
        assert mag == pytest.approx(cap, rel=RTOL)
        np.testing.assert_allclose(out.torque_rolling[k] / mag, -angle[k] / np.linalg.norm(angle[k]), atol=1e-6)


@pytest.mark.req("FR-005-01")
def test_no_rolling_torque_without_rolling() -> None:
    out = run(worked_props(), [DELTA], rolling_angle=[[0.0, 0.0, 0.0]], mu_r=0.1)
    np.testing.assert_array_equal(out.torque_rolling, np.zeros((1, 3)))


@pytest.mark.req("FR-005-01")
@settings(max_examples=200, deadline=None)  # thresholds.yaml property_tests.ci_examples_per_test
@given(
    e1=st.floats(1.0e5, 1.0e11),
    e2=st.floats(1.0e5, 1.0e11),
    nu1=st.floats(-0.9, 0.49),
    nu2=st.floats(-0.9, 0.49),
    r1=st.floats(1.0e-4, 1.0),
    r2=st.floats(1.0e-4, 1.0),
    frac=st.floats(1.0e-5, 0.1),
    rot=st.lists(st.floats(-50.0, 50.0), min_size=3, max_size=3),
    tang=st.lists(st.floats(-1.0, 1.0), min_size=3, max_size=3),
    mu_s=st.floats(0.0, 2.0),
    mu_r=st.floats(0.0, 1.0),
)
def test_contact_law_matches_the_closed_form_for_any_materials(
    e1, e2, nu1, nu2, r1, r2, frac, rot, tang, mu_s, mu_r
) -> None:
    m1 = RHO * 4.0 / 3.0 * math.pi * r1**3
    m2 = RHO * 4.0 / 3.0 * math.pi * r2**3
    p = effective_properties(
        youngs_1=e1, poisson_1=nu1, radius_1=r1, mass_1=m1, youngs_2=e2, poisson_2=nu2, radius_2=r2, mass_2=m2
    )
    es, gs = hand_e_star(e1, nu1, e2, nu2), hand_g_star(e1, nu1, e2, nu2)
    rs = 1.0 / (1.0 / r1 + 1.0 / r2)
    assert p.e_star == pytest.approx(es, rel=1e-12)
    assert p.g_star == pytest.approx(gs, rel=1e-12)
    assert p.r_star == pytest.approx(rs, rel=1e-12)
    delta = frac * rs
    fn = 4.0 / 3.0 * es * math.sqrt(rs) * delta**1.5
    st_ = 8.0 * gs * math.sqrt(rs * delta)
    dvec = np.asarray(tang, dtype=np.float64) * delta
    out = run(p, [delta], delta_t=[dvec], rolling_angle=[rot], mu_s=mu_s, mu_r=mu_r)
    assert float(out.fn_elastic[0]) == pytest.approx(fn, rel=RTOL)
    assert float(out.s_t[0]) == pytest.approx(st_, rel=RTOL)
    # Coulomb cap holds for any history, and the elastic branch is exact below it
    ft_mag = float(np.linalg.norm(out.ft[0]))
    assert ft_mag <= mu_s * fn * (1.0 + RTOL) + 1e-30
    spring = st_ * float(np.linalg.norm(dvec))
    if spring < 0.99 * mu_s * fn:
        assert ft_mag == pytest.approx(spring, rel=1e-4, abs=1e-30)
    # Rolling torque never exceeds its cap
    assert float(np.linalg.norm(out.torque_rolling[0])) <= mu_r * rs * fn * (1.0 + RTOL) + 1e-30

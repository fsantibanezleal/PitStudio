"""T-005-011 - FR-005-02, FR-005-03: elastic impact overlap and duration; restitution and its velocity independence.

Oracles (independent of the code under test):
- FR-005-02: analytical Hertz impact. delta_max = (15 m* v0^2 / (16 E* sqrt(R*)))^(2/5) from energy conservation, and
  t_c = 2 (delta_max / v0) * I with I = int_0^1 (1 - x^(5/2))^(-1/2) dx (spec 005 section 7). I is evaluated twice:
  by `scipy.integrate.quad` (plan 005 test strategy) and in closed form I = (2/5) B(2/5, 1/2)
  = (2/5) Gamma(2/5) Gamma(1/2) / Gamma(9/10) (substitution u = x^(5/2)), giving 2 I = 2.943275.
- FR-005-03: reference implementation, SciPy `solve_ivp` (DOP853, rtol 1e-11) of the 1-D damped Hertz ODE
      m* delta'' = -(4/3) E* sqrt(R*) delta^(3/2) + 2 sqrt(5/6) beta sqrt(S_n m*) delta',  S_n = 2 E* sqrt(R* delta),
  integrated from first touch (delta = 0, delta' = v0) until delta returns to 0; e_ref = -delta'(end) / v0 (plan 005).
  The nominal e is the second oracle. NOTE (found while writing this test): this ODE reproduces the nominal e to
  < 1e-4 only when the normal force is NOT clipped at zero (the damping term may make the total normal force briefly
  tensile just before separation); with F_n clipped to >= 0 the realised e at nominal 0.1 is 0.253. FR-005-03 therefore
  requires the unclipped law, which is what the reference below integrates.
Tolerances: FR-005-02 1 % at dt = t_c / 200; FR-005-03 +- 0.01 of nominal and <= 0.5 % spread over 0.1-10 m/s.

Expected public API (module `pitstudio_studio.physics.dem.step`), shared by the DEM tests of spec 005:

    DemMaterial(*, density, youngs_modulus, poisson_ratio, restitution, friction_static, friction_rolling,
                youngs_modulus_real=None)                 SI units; particle mass = density * 4/3 pi r^3
    Plane(*, point, normal)                               rigid infinite wall (R -> inf, m -> inf) made of the
                                                          particle material; `normal` points into the domain
    DemSimulation(positions, radii, material, dt, *, velocities=None, angular_velocities=None,
                  gravity=(0.0, 0.0, -9.81), walls=(), contact_capacity=12, rayleigh_fraction=0.2,
                  domain=None, outflow=(), device="cpu")
        .step(n=1)                    advance n steps of size dt (symplectic Euler, translation and rotation)
        .positions, .velocities, .angular_velocities   numpy (N, 3) copies of the current state
        .masses (N,), .step_index (int, completed steps), .time (= step_index * dt)
    The contact law is FR-005-01 (T-005-010) between spheres and between spheres and walls.
"""

from __future__ import annotations

import functools
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.integrate import quad, solve_ivp

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)

from pitstudio_studio.physics.dem.step import DemMaterial, DemSimulation  # noqa: E402

DEVICE = "cpu"
R = 5.0e-3  # m, worked example of FR-005-01
E = 50.0e6  # Pa
NU = 0.25
RHO = 2650.0  # kg/m^3
MASS = RHO * 4.0 / 3.0 * math.pi * R**3  # 1.3875e-3 kg
M_STAR = MASS / 2.0
E_STAR = 1.0 / (2.0 * (1.0 - NU**2) / E)  # 2.6667e7 Pa
R_STAR = R / 2.0
SPEEDS = (0.1, 1.0, 10.0)  # m/s, ends and middle of FR-005-02/03's range

# Closed form and quadrature of the contact-duration integral (oracle self-consistency)
DURATION_CONST_GAMMA = 2.0 * 0.4 * math.gamma(0.4) * math.gamma(0.5) / math.gamma(0.9)
DURATION_CONST_QUAD = 2.0 * quad(lambda x: (1.0 - x**2.5) ** -0.5, 0.0, 1.0)[0]


def delta_max_hertz(v0: float) -> float:
    return (15.0 * M_STAR * v0**2 / (16.0 * E_STAR * math.sqrt(R_STAR))) ** 0.4


@functools.cache
def reference_impact(e: float, v0: float) -> tuple[float, float]:
    """SciPy reference of the damped Hertz ODE (unclipped normal force). Returns (restitution, contact time)."""
    beta = math.log(e) / math.sqrt(math.log(e) ** 2 + math.pi**2) if e < 1.0 else 0.0
    k = 4.0 / 3.0 * E_STAR * math.sqrt(R_STAR)

    def rhs(_t, y):
        d, v = y
        dp = max(d, 0.0)
        s_n = 2.0 * E_STAR * math.sqrt(R_STAR * dp)
        damping = -2.0 * math.sqrt(5.0 / 6.0) * beta * math.sqrt(s_n * M_STAR)  # >= 0
        return [v, (-k * dp**1.5 - damping * v) / M_STAR]

    def separated(_t, y):
        return y[0]

    separated.terminal = True
    separated.direction = -1
    dm = delta_max_hertz(v0)
    sol = solve_ivp(
        rhs,
        [0.0, 100.0 * dm / v0],
        [0.0, v0],
        method="DOP853",
        rtol=1e-11,
        atol=1e-14 * dm,
        events=separated,
        first_step=1e-6 * dm / v0,
    )
    return -float(sol.y_events[0][0][1]) / v0, float(sol.t_events[0][0])


def material(e: float) -> DemMaterial:
    return DemMaterial(
        density=RHO, youngs_modulus=E, poisson_ratio=NU, restitution=e, friction_static=0.0, friction_rolling=0.0
    )


def head_on(e: float, v0: float, dt: float):
    """Two equal spheres touching at t = 0 (separation exactly 2R), approaching at relative speed v0 along x.

    Steps until the overlap has been negative for 5 steps after the contact. Returns the overlap series
    delta_k = 2R - |x2 - x1| (k = 0 is the initial state), the relative velocity before and after the impact, and dt.
    """
    pos = np.array([[-R, 0.0, 0.0], [R, 0.0, 0.0]])
    vel = np.array([[0.5 * v0, 0.0, 0.0], [-0.5 * v0, 0.0, 0.0]])
    sim = DemSimulation(pos, np.full(2, R), material(e), dt, velocities=vel, gravity=(0.0, 0.0, 0.0), device=DEVICE)
    deltas = [0.0]
    touched, after = False, 0
    limit = int(20.0 * delta_max_hertz(v0) / v0 / dt) + 50
    for _ in range(limit):
        sim.step(1)
        p = sim.positions
        d = 2.0 * R - float(np.linalg.norm(p[1] - p[0]))
        deltas.append(d)
        touched = touched or d > 0.0
        if touched and d < 0.0:
            after += 1
            if after >= 5:
                break
    assert after >= 5, "the spheres never separated"
    v = sim.velocities
    return np.array(deltas), float(v[0, 0] - v[1, 0]), dt


def contact_end_time(deltas: np.ndarray, dt: float) -> float:
    """Contact duration from the overlap series: linear interpolation of the last zero crossing (start at t = 0)."""
    pos = np.nonzero(deltas > 0.0)[0]
    k = int(pos[-1])  # last positive sample
    d0, d1 = deltas[k], deltas[k + 1]
    return (k + d0 / (d0 - d1)) * dt


@pytest.mark.req("FR-005-02")
def test_contact_duration_constant_oracle() -> None:
    """Oracle self-check: closed form and quadrature agree with the spec's 2.9433."""
    assert abs(DURATION_CONST_GAMMA / DURATION_CONST_QUAD - 1.0) <= 1e-9
    assert abs(DURATION_CONST_GAMMA - 2.9433) <= 5e-5


@pytest.mark.req("FR-005-02")
@pytest.mark.parametrize("v0", SPEEDS)
def test_elastic_head_on_impact_overlap_and_duration(v0: float) -> None:
    dm = delta_max_hertz(v0)  # v0 = 1 m/s: 1.886e-4 m
    tc = DURATION_CONST_GAMMA * dm / v0  # v0 = 1 m/s: 5.55e-4 s
    deltas, _, dt = head_on(1.0, v0, tc / 200.0)
    assert float(deltas.max()) == pytest.approx(dm, rel=0.01)
    assert contact_end_time(deltas, dt) == pytest.approx(tc, rel=0.01)


@pytest.mark.req("FR-005-02")
def test_elastic_impact_conserves_the_relative_speed() -> None:
    """e -> 1 and mu_s = 0: the spheres separate with the approach speed (consistency of the elastic case)."""
    v0 = 1.0
    tc = DURATION_CONST_GAMMA * delta_max_hertz(v0) / v0
    _, v_rel_after, _ = head_on(1.0, v0, tc / 200.0)
    assert -v_rel_after == pytest.approx(v0, rel=0.01)


@pytest.mark.req("FR-005-03")
@pytest.mark.parametrize("e", [0.1, 0.3, 0.5, 0.7, 0.9, 0.95])
def test_reference_ode_reproduces_the_nominal_restitution(e: float) -> None:
    """Oracle self-check: the unclipped damped Hertz law has restitution e at every speed (SciPy reference)."""
    for v0 in SPEEDS:
        e_ref, _ = reference_impact(e, v0)
        assert e_ref == pytest.approx(e, abs=1e-3)


@pytest.mark.req("FR-005-03")
@pytest.mark.parametrize("e", [0.1, 0.3, 0.5, 0.7, 0.9, 0.95])
def test_realised_restitution_and_its_velocity_independence(e: float) -> None:
    realised = []
    for v0 in SPEEDS:
        e_ref, tc_ref = reference_impact(e, v0)
        _, v_rel_after, _ = head_on(e, v0, tc_ref / 200.0)
        e_dem = -v_rel_after / v0
        assert e_dem == pytest.approx(e, abs=0.01), f"nominal e={e}, v0={v0}"
        assert e_dem == pytest.approx(e_ref, abs=0.01), f"reference e={e_ref}, v0={v0}"
        realised.append(e_dem)
    spread = (max(realised) - min(realised)) / float(np.mean(realised))
    assert spread <= 0.005, f"restitution varies by {spread:.4%} over {SPEEDS} m/s: {realised}"

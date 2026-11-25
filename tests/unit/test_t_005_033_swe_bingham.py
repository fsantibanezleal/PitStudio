"""T-005-033 - FR-005-29: Bingham bed stress, exact arrest below h_stop, sheet-flow velocity above.

Oracles (the solver is never the reference):
- the implicit friction step: a uniform state with open boundaries is an exact solution of the flux update, so one step of
  length dt changes only the momentum, which must satisfy m + dt tau_b(m / h) / rho = m*; the root is found here with SciPy
  `brentq` on the Buckingham-Reiner relation written in its expanded form U = (tau_b h / 3 mu)(1 - 1.5 r + 0.5 r^3);
- the spec 005 worked example (rho 1800 kg/m3, S 0.0875, tau_y 100 Pa, mu_B 10 Pa s, h 0.2 m): tau_b = 309.0 Pa,
  U = 1.095 m/s, h_stop = 0.0647 m;
- the Newtonian limit U = rho g h^2 S / (3 mu_B).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.physics.swe import SweParams, SweSimulation  # noqa: E402

G, RHO = 9.81, 1800.0
ALL_OPEN = {"x-min": "open", "x-max": "open", "y-min": "open", "y-max": "open"}


def buckingham_reiner_u(tau_b, h, tau_y, mu):
    r = tau_y / tau_b
    return tau_b * h / (3.0 * mu) * (1.0 - 1.5 * r + 0.5 * r**3)


def reference_friction(m_star, h, dt, tau_y, mu):
    """Oracle of one implicit step: the root of m + dt tau_b(m/h) / rho = m*, 0 when m* <= dt tau_y / rho."""
    if m_star <= dt * tau_y / RHO:
        return 0.0
    f = lambda tau: h * buckingham_reiner_u(tau, h, tau_y, mu) + dt * tau / RHO - m_star  # noqa: E731
    tau = brentq(f, tau_y * (1 + 1e-12), RHO * m_star / dt, xtol=1e-13, rtol=1e-14)
    return m_star - dt * tau / RHO


def one_friction_step(h, m_star, dt, tau_y, mu):
    """Momentum after one step of a uniform sheet with open boundaries (the flux update changes nothing)."""
    s = SweSimulation(
        np.zeros((3, 3)), np.full((3, 3), h), dx=10.0, boundaries=ALL_OPEN, device="cpu",
        momentum=(np.full((3, 3), m_star), np.zeros((3, 3))),
        params=SweParams(rho=RHO, tau_y=tau_y, mu_b=mu, max_dt=dt, cfl=0.5),
    )  # fmt: skip
    s.advance(dt)
    assert s.steps == 1
    assert np.allclose(s.h, h, rtol=1e-14)
    return s.qx[1, 1]


@pytest.mark.parametrize(
    ("h", "m_star", "tau_y", "mu"),
    [
        (0.2, 0.30, 100.0, 10.0),
        (1.5, 6.00, 100.0, 10.0),
        (3.0, 40.0, 25.0, 0.5),
        (0.8, 2.00, 200.0, 1.0),
        (0.05, 0.40, 10.0, 0.05),
    ],
)
def test_implicit_bingham_friction_solves_the_buckingham_reiner_relation(h, m_star, tau_y, mu):
    dt = 0.02
    expected = reference_friction(m_star, h, dt, tau_y, mu)
    got = one_friction_step(h, m_star, dt, tau_y, mu)
    assert expected > 0.0
    assert got == pytest.approx(expected, rel=1e-9)
    assert got < m_star  # friction opposes the motion and never reverses it


def test_a_cell_below_the_yield_impulse_is_set_exactly_to_rest():
    h, tau_y, mu, dt = 0.5, 100.0, 10.0, 0.05
    below = 0.99 * dt * tau_y / RHO
    above = 1.01 * dt * tau_y / RHO
    assert one_friction_step(h, below, dt, tau_y, mu) == 0.0  # exactly zero, not small
    assert one_friction_step(h, above, dt, tau_y, mu) > 0.0


def test_friction_keeps_the_direction_of_the_momentum():
    s = SweSimulation(
        np.zeros((3, 3)), np.full((3, 3), 0.4), dx=10.0, boundaries=ALL_OPEN, device="cpu",
        momentum=(np.full((3, 3), 0.6), np.full((3, 3), -0.8)),
        params=SweParams(rho=RHO, tau_y=50.0, mu_b=5.0, max_dt=0.02, cfl=0.5),
    )  # fmt: skip
    s.advance(0.02)
    qx, qy = s.qx[1, 1], s.qy[1, 1]
    assert qx > 0 > qy
    assert qx / -qy == pytest.approx(0.6 / 0.8, rel=1e-12)


def test_spec_worked_example_matches_the_buckingham_reiner_values():
    """Spec 005 section 7: tau_b = 309.0 Pa, U = 1.095 m/s, h_stop = 0.0647 m (oracle of the oracle)."""
    h, s_bed, tau_y, mu = 0.2, 0.0875, 100.0, 10.0
    tau_b = RHO * G * h * s_bed
    assert tau_b == pytest.approx(309.0, abs=0.1)
    assert buckingham_reiner_u(tau_b, h, tau_y, mu) == pytest.approx(1.095, abs=2e-3)
    assert tau_y / (RHO * G * s_bed) == pytest.approx(0.0647, abs=1e-4)


def slope_channel(n, dx, s_bed):
    """Bed descending towards +x at slope S (rise per metre of horizontal distance), 3 cells wide.

    The hydrostatic reconstruction is first order on a slope: the net bed force per unit mass on a uniform layer is
    g S (1 - S dx / (2 h)), not g S, so these tests use a gentle slope and cells much finer than 2 h / S (here
    S dx / 2 h <= 1 %); on coarse cells the bed force is smaller by that factor (reported as a limit of the scheme)."""
    return (s_bed * dx * np.arange(n)[::-1])[None, :].repeat(3, axis=0)


SHEET = dict(n=400, dx=0.25, s_bed=0.02, tau_y=100.0, mu=10.0)  # h_stop = 0.2832 m


def test_a_layer_fed_above_one_and_a_half_h_stop_reaches_the_buckingham_reiner_velocity():
    """FR-005-29: fed at h = 1.6 h_stop the layer reaches the mean velocity of the relation with tau_b = rho g h S and
    keeps its depth, both within 2 %."""
    n, dx, s_bed, tau_y, mu = (SHEET[k] for k in ("n", "dx", "s_bed", "tau_y", "mu"))
    h_stop = tau_y / (RHO * G * s_bed)
    h_feed = 1.6 * h_stop
    u_ref = buckingham_reiner_u(RHO * G * h_feed * s_bed, h_feed, tau_y, mu)
    s = SweSimulation(
        slope_channel(n, dx, s_bed), np.full((3, n), h_feed), dx=dx, device="cpu",
        boundaries={"x-min": "inflow", "x-max": "open"}, inflow={"x-min": (h_feed, u_ref, 0.0)},
        params=SweParams(rho=RHO, tau_y=tau_y, mu_b=mu),
    )  # fmt: skip
    s.advance(300.0)  # starts at rest: the layer accelerates and relaxes (more than 10 relaxation times)
    h, qx = s.h[1], s.qx[1]
    mid = slice(100, 300)
    assert np.abs(h[mid] / h_feed - 1).max() <= 0.02
    assert np.abs(qx[mid] / h[mid] / u_ref - 1).max() <= 0.02


def test_a_layer_below_h_stop_stays_exactly_at_rest_away_from_its_edges():
    n, dx, s_bed, tau_y, mu = (SHEET[k] for k in ("n", "dx", "s_bed", "tau_y", "mu"))
    h_stop = tau_y / (RHO * G * s_bed)
    h0 = np.zeros((3, n))
    h0[:, 100:300] = 0.8 * h_stop
    s = SweSimulation(
        slope_channel(n, dx, s_bed), h0, dx=dx, device="cpu",
        params=SweParams(rho=RHO, tau_y=tau_y, mu_b=mu),
    )  # fmt: skip
    s.advance(3.0)  # an edge disturbance moves sqrt(g h) = 1.5 m/s: 4.5 m = 18 cells, short of the 21 cells kept
    inner = slice(100 + 21, 300 - 21)  # more than 20 cells from either edge
    assert np.all(s.qx[:, inner] == 0.0) and np.all(s.qy[:, inner] == 0.0)  # at rest exactly, not almost
    # the depth changes only by the numerical diffusion of the layer's edges, which decays away from them
    assert np.abs(s.h[:, inner] - 0.8 * h_stop).max() <= 1e-4 * 0.8 * h_stop


def test_newtonian_sheet_flow_limit_with_zero_yield_stress():
    n, dx, s_bed, mu, h_feed = 400, 0.25, 0.02, 10.0, 0.3
    u_ref = RHO * G * h_feed**2 * s_bed / (3.0 * mu)
    s = SweSimulation(
        slope_channel(n, dx, s_bed), np.full((3, n), h_feed), dx=dx, device="cpu",
        boundaries={"x-min": "inflow", "x-max": "open"}, inflow={"x-min": (h_feed, u_ref, 0.0)},
        params=SweParams(rho=RHO, tau_y=0.0, mu_b=mu),
    )  # fmt: skip
    s.advance(300.0)
    mid = slice(100, 300)
    assert np.abs(s.qx[1, mid] / s.h[1, mid] / u_ref - 1).max() <= 0.02
    assert np.abs(s.h[1, mid] / h_feed - 1).max() <= 0.02


def test_zero_yield_stress_and_zero_viscosity_leave_the_frictionless_solution_bit_for_bit():
    rng = np.random.default_rng(11)
    z = rng.uniform(0.0, 0.3, (10, 14))
    h0 = np.where(rng.uniform(size=z.shape) < 0.5, rng.uniform(0.0, 1.0, z.shape), 0.0)
    a = SweSimulation(z, h0, dx=1.0, device="cpu", params=SweParams(rho=1000.0))
    b = SweSimulation(z, h0, dx=1.0, device="cpu", params=SweParams(rho=2500.0, tau_y=0.0, mu_b=0.0))
    for s in (a, b):
        s.advance(6.0)
    assert np.array_equal(a.h, b.h) and np.array_equal(a.qx, b.qx) and np.array_equal(a.qy, b.qy)


def test_plastic_limit_with_zero_viscosity_decelerates_at_the_yield_stress():
    """mu_B = 0 and tau_y > 0: the stress is the constant tau_y, so m falls by exactly dt tau_y / rho per step."""
    h, tau_y, dt, m_star = 0.5, 80.0, 0.04, 1.0
    got = one_friction_step(h, m_star, dt, tau_y, 0.0)
    assert got == pytest.approx(m_star - dt * tau_y / RHO, rel=1e-12)
    assert math.isfinite(got)

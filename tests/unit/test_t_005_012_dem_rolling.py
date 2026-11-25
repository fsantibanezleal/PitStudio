"""T-005-012 - FR-005-04, FR-005-05: a sphere on an incline (rest vs rolling) and the sliding-to-rolling transition.

Oracles (analytical rigid-body mechanics, derived here by hand; plan 005 test strategy):
- FR-005-04, rolling with a resistance torque capped at mu_r R F_n (R* = R against a wall, F_n = m g cos(theta)):
      m a = m g sin(theta) - f ;  I alpha = f R - mu_r R m g cos(theta) ;  a = alpha R ;  I = (2/5) m R^2
  =>  (7/5) a = g (sin(theta) - mu_r cos(theta))  =>  a = (5/7) g (sin(theta) - mu_r cos(theta)).
  Static iff the torque the contact must resist, f R = m g sin(theta) R, stays below the cap: tan(theta) <= mu_r.
  No slip while rolling iff f = m g [(2/7) sin(theta) + (5/7) mu_r cos(theta)] <= mu_s m g cos(theta), which holds
  for every case below (largest: (2/7) 0.4 + (5/7) 0.1 = 0.186 < mu_s = 0.5).
- FR-005-05, sliding on a level plane with mu_r = 0: v(t) = v0 - mu_s g t, omega(t) R = (5/2) mu_s g t, so the slip
  v - omega R = v0 - (7/2) mu_s g t vanishes at t* = 2 v0 / (7 mu_s g), when v = v0 - (2/7) v0 = (5/7) v0.
Tolerances (spec FR-005-04/05, plan 005 "Rolling and sliding"): rest speed <= 1e-4 m/s after 1 s; mean acceleration
within 1 % over [0.5 s, 1.0 s] (after the transient); rolling speed within 1 %; transition time within 2 %.

The incline is modelled in its own frame: a level wall z = 0 with gravity rotated by theta about y,
g = 9.81 (sin(theta), 0, -cos(theta)), which is the same mechanical problem as a tilted plane under vertical gravity.
The sphere starts at rest at its static Hertz overlap delta_eq = (m g cos(theta) / ((4/3) E* sqrt(R)))^(2/3).

Expected public API (module `pitstudio_studio.physics.dem.step`, see T-005-011 for the full description):
    DemMaterial(*, density, youngs_modulus, poisson_ratio, restitution, friction_static, friction_rolling)
    Plane(*, point, normal)                          rigid wall of the particle material
    DemSimulation(positions, radii, material, dt, *, velocities=None, angular_velocities=None, gravity=...,
                  walls=(), device="cpu");  .step(n);  .positions, .velocities, .angular_velocities  (N, 3)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)

from pitstudio_studio.physics.dem.step import DemMaterial, DemSimulation, Plane  # noqa: E402

DEVICE = "cpu"
G = 9.81
R = 5.0e-3  # m
E = 50.0e6  # Pa
NU = 0.25
RHO = 2650.0
MASS = RHO * 4.0 / 3.0 * math.pi * R**3
E_STAR_WALL = 1.0 / (2.0 * (1.0 - NU**2) / E)  # sphere against a wall of the same material
DT = 2.0e-5  # s; Rayleigh limit 0.2 * 1.971e-4 s = 3.94e-5 s (FR-005-08 worked example)
MU_S = 0.5
MU_R = 0.1


def delta_eq(load: float) -> float:
    return (load / (4.0 / 3.0 * E_STAR_WALL * math.sqrt(R))) ** (2.0 / 3.0)


def material(mu_s: float, mu_r: float) -> DemMaterial:
    return DemMaterial(
        density=RHO, youngs_modulus=E, poisson_ratio=NU, restitution=0.5, friction_static=mu_s, friction_rolling=mu_r
    )


def sphere_on_wall(theta: float, *, mu_s: float, mu_r: float, v0: float = 0.0, dt: float = DT) -> DemSimulation:
    z0 = R - delta_eq(MASS * G * math.cos(theta))
    return DemSimulation(
        np.array([[0.0, 0.0, z0]]),
        np.array([R]),
        material(mu_s, mu_r),
        dt,
        velocities=np.array([[v0, 0.0, 0.0]]),
        angular_velocities=np.zeros((1, 3)),
        gravity=(G * math.sin(theta), 0.0, -G * math.cos(theta)),
        walls=(Plane(point=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)),),
        device=DEVICE,
    )


@pytest.mark.req("FR-005-04")
@pytest.mark.parametrize("ratio", [0.5, 0.95])
def test_sphere_stays_at_rest_below_the_rolling_friction(ratio: float) -> None:
    theta = math.atan(ratio * MU_R)
    sim = sphere_on_wall(theta, mu_s=MU_S, mu_r=MU_R)
    sim.step(round(1.0 / DT))  # 1 s
    speed = float(np.linalg.norm(sim.velocities[0]))
    assert speed <= 1.0e-4, f"tan(theta) = {ratio} mu_r: centre speed {speed:.3e} m/s after 1 s"


@pytest.mark.req("FR-005-04")
@pytest.mark.parametrize("ratio", [1.05, 2.0, 4.0])
def test_sphere_rolls_with_the_analytical_acceleration(ratio: float) -> None:
    theta = math.atan(ratio * MU_R)
    assert math.tan(theta) < MU_S
    a_hand = 5.0 / 7.0 * G * (math.sin(theta) - MU_R * math.cos(theta))  # ratio 1.05: 0.03482 m/s^2
    sim = sphere_on_wall(theta, mu_s=MU_S, mu_r=MU_R)
    every = round(0.01 / DT)
    sim.step(round(0.5 / DT))
    t, v = [], []
    for _ in range(51):  # samples at 0.50, 0.51, ..., 1.00 s
        t.append(sim.time)
        v.append(float(sim.velocities[0, 0]))
        sim.step(every)
    slope = float(np.polyfit(np.asarray(t), np.asarray(v), 1)[0])
    assert slope == pytest.approx(a_hand, rel=0.01)
    # rolling, not sliding: the contact point (at -R z) is at rest relative to the wall
    vx = float(sim.velocities[0, 0])
    wy = float(sim.angular_velocities[0, 1])
    assert abs(vx - wy * R) <= 0.01 * abs(vx)


@pytest.mark.req("FR-005-05")
@pytest.mark.parametrize(("v0", "mu_s"), [(1.0, 0.3), (0.5, 0.6)])
def test_sliding_sphere_reaches_pure_rolling(v0: float, mu_s: float) -> None:
    dt = 1.0e-5
    t_star = 2.0 * v0 / (7.0 * mu_s * G)  # (1.0, 0.3): 0.09709 s; (0.5, 0.6): 0.02427 s
    sim = sphere_on_wall(0.0, mu_s=mu_s, mu_r=0.0, v0=v0, dt=dt)
    t_roll = None
    for _ in range(round(2.0 * t_star / dt)):
        sim.step(1)
        slip = float(sim.velocities[0, 0]) - float(sim.angular_velocities[0, 1]) * R
        if t_roll is None and slip <= 1.0e-3 * v0:
            t_roll = sim.time
    assert t_roll is not None, "the sphere never stopped slipping"
    assert t_roll == pytest.approx(t_star, rel=0.02)
    # after the transition the sphere rolls at (5/7) v0 (mu_r = 0: no further deceleration)
    assert float(sim.velocities[0, 0]) == pytest.approx(5.0 / 7.0 * v0, rel=0.01)
    assert float(sim.angular_velocities[0, 1]) * R == pytest.approx(5.0 / 7.0 * v0, rel=0.01)

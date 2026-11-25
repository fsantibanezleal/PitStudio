"""T-005-015 - FR-005-15: exact particle and mass accounting with outflow.

Oracle: exact integer accounting and a hand count of the particles through each declared outlet (plan 005 test
strategy). Eighteen non-touching spheres (radii 4-6 mm, centres >= 0.15 m apart) in the box [-1, 1] x [-1, 1] x
[0, 20] m with outflow faces z-min and x-max:
- set A (10 spheres) starts at rest at heights z_i = 0.05 (i + 1) m and falls freely: it crosses z = 0 at
  t_i = sqrt(2 z_i / g) (0.101 s ... 0.319 s);
- set B (5 spheres) starts at z = 15 m, x_j = 0.0, 0.2, 0.4, 0.6, 0.8 m with v_x = 1 m/s: it crosses x = 1 m at
  t_j = 1 - x_j (1.0 ... 0.2 s) while falling (it drops 7.1 m by t = 1.2 s, staying inside);
- set C (3 spheres) starts at rest at z = 19 m and never leaves before t = 1.2 s.
Whether a sphere counts as gone when its centre or its whole body crosses the face is left to the implementation:
the hand count is only compared at output times more than 15 ms away from both instants (the integration error
of the crossing time is about g dt t / (2 v) < 1 ms at dt = 0.5 ms). The conservation identities are checked at
every output step, exactly (integers and float64 equality, "to the last bit"). The float32 masses sum exactly in
float64 here (18 values with close exponents need far fewer than 53 mantissa bits), so the identity is attainable.

Expected public API (module `pitstudio_studio.physics.dem.step`; constructor in T-005-011):
    DemSimulation(..., domain=((x0, y0, z0), (x1, y1, z1)), outflow=("z-min", "x-max"), ...)
        outflow faces use the DC-005-01 names x-min, x-max, y-min, y-max, z-min, z-max; a particle that leaves
        through a declared face is removed from the dynamics and recorded against that face
        .count_inside(), .count_exited()                      int
        .exited_by_boundary() -> dict[str, int]               one entry per declared face (0 included)
        .inside_mask() -> numpy bool (N,)                     True while the particle is in the domain
        .mass_inside(), .mass_exited()                        float (float64 sums of the per-particle masses)
        .masses                                               numpy (N,) per-particle masses
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)

from pitstudio_studio.physics.dem.step import DemMaterial, DemSimulation  # noqa: E402
from pitstudio_studio.physics.errors import PhysicsError  # noqa: E402

DEVICE = "cpu"
G = 9.81
RHO = 2650.0
DT = 5.0e-4  # s; Rayleigh limit at E = 0.1 MPa, R_min = 4 mm: 0.2 * 3.53e-3 s = 7.05e-4 s
EVERY = 20  # output every 10 ms
T_END = 1.2  # s
DOMAIN = ((-1.0, -1.0, 0.0), (1.0, 1.0, 20.0))
OUTFLOW = ("z-min", "x-max")
MARGIN = 0.015  # s


def material() -> DemMaterial:
    return DemMaterial(
        density=RHO, youngs_modulus=1.0e5, poisson_ratio=0.25, restitution=0.5, friction_static=0.5,
        friction_rolling=0.1,
    )  # fmt: skip


def scene():
    radii = 4.0e-3 + 2.0e-3 * (np.arange(18) % 5) / 4.0  # 4.0, 4.5, 5.0, 5.5, 6.0 mm repeating
    pos, vel = [], []
    events = []  # (particle, face, centre-crossing time, full-exit time)
    for i in range(10):  # set A
        z = 0.05 * (i + 1)
        pos.append([-0.9 + 0.15 * i, 0.0, z])
        vel.append([0.0, 0.0, 0.0])
        r = radii[len(pos) - 1]
        events.append((len(pos) - 1, "z-min", math.sqrt(2.0 * z / G), math.sqrt(2.0 * (z + r) / G)))
    for j, x in enumerate([0.0, 0.2, 0.4, 0.6, 0.8]):  # set B
        pos.append([x, 0.5, 15.0 - 0.3 * j])
        vel.append([1.0, 0.0, 0.0])
        r = radii[len(pos) - 1]
        events.append((len(pos) - 1, "x-max", 1.0 - x, 1.0 - x + r))
    for k in range(3):  # set C
        pos.append([-0.5 + 0.5 * k, -0.5, 19.0])
        vel.append([0.0, 0.0, 0.0])
    return np.asarray(pos), radii, np.asarray(vel), events


def make() -> tuple[DemSimulation, list]:
    pos, radii, vel, events = scene()
    sim = DemSimulation(
        pos, radii, material(), DT, velocities=vel, gravity=(0.0, 0.0, -G), domain=DOMAIN, outflow=OUTFLOW,
        device=DEVICE,
    )  # fmt: skip
    return sim, events


@pytest.mark.req("FR-005-15")
def test_initial_accounting() -> None:
    sim, _ = make()
    _, radii, _, _ = scene()
    assert sim.count_inside() == 18
    assert sim.count_exited() == 0
    assert sim.exited_by_boundary() == {"z-min": 0, "x-max": 0}
    assert sim.mass_exited() == 0.0
    hand = RHO * 4.0 / 3.0 * math.pi * float(np.sum(radii**3))
    assert sim.mass_inside() == pytest.approx(hand, rel=1e-6)  # float32 per-particle masses


@pytest.mark.req("FR-005-15")
def test_counts_and_masses_are_conserved_exactly_at_every_output_step() -> None:
    sim, events = make()
    n0 = sim.count_inside()
    m0 = sim.mass_inside()
    masses = np.asarray(sim.masses, dtype=np.float64)
    checked = 0
    for _ in range(round(T_END / DT / EVERY)):
        sim.step(EVERY)
        t = sim.time
        inside, exited = sim.count_inside(), sim.count_exited()
        assert inside + exited == n0, f"t = {t:.3f} s: {inside} inside + {exited} exited != {n0}"
        by_face = sim.exited_by_boundary()
        assert set(by_face) == set(OUTFLOW)
        assert sum(by_face.values()) == exited
        assert sim.mass_inside() + sim.mass_exited() == m0, f"t = {t:.3f} s: mass budget not exact"
        mask = np.asarray(sim.inside_mask(), dtype=bool)
        assert int(mask.sum()) == inside
        assert math.fsum(masses[~mask]) == pytest.approx(sim.mass_exited(), rel=1e-12, abs=0.0)
        # hand count away from every crossing instant
        if all(abs(t - tc) > MARGIN and abs(t - tf) > MARGIN for _, _, tc, tf in events):
            gone = {p for p, _, tc, _ in events if tc < t}
            assert set(np.nonzero(~mask)[0].tolist()) == gone, f"t = {t:.3f} s"
            for face in OUTFLOW:
                assert by_face[face] == sum(1 for p, f, tc, _ in events if f == face and tc < t), (face, t)
            checked += 1
    assert checked >= 60  # most of the 120 output steps are hand-checked
    # at the end every set-A and set-B sphere has left, set C has not
    assert sim.exited_by_boundary() == {"z-min": 10, "x-max": 5}
    assert sim.count_inside() == 3


@pytest.mark.req("FR-005-15")
@pytest.mark.parametrize(
    "kwargs",
    [
        {"domain": DOMAIN, "outflow": ("w-min",)},  # unknown face
        {"domain": None, "outflow": ("z-min",)},  # outflow without a domain
    ],
)
def test_malformed_outflow_declarations_are_rejected(kwargs) -> None:
    """Hostile input: an outflow that cannot be accounted for must not be ignored silently.

    (Derived from "declared outflow boundaries" in FR-005-15; an inverted domain box is not tested because spec 005
    section 8 records that no requirement rejects it.)
    """
    pos, radii, vel, _ = scene()
    with pytest.raises((PhysicsError, ValueError)):
        DemSimulation(pos, radii, material(), DT, velocities=vel, device=DEVICE, **kwargs)

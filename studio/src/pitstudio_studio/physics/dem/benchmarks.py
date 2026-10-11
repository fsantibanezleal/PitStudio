"""DEM benchmark scenarios (spec 005, FR-005-10 ... FR-005-12, FR-005-14).

Only the quasi-2-D slot discharge of FR-005-11 lives here so far: T-005-017's monotonicity and time-step relations
(P-005-04, P-005-06) call it. Its acceptance test against the fit Q = C rho_b sqrt(g) (W - k d)^(3/2) belongs to
T-005-018.
"""

from __future__ import annotations

import functools
import math

import numpy as np

from pitstudio_studio.physics.dem.step import DemMaterial, DemSimulation, Plane, rayleigh_time_step

G = 9.81

# Benchmark material (a glass-bead-like card; the stiffness is reduced for the time step, FR-005-09).
SLOT_DIAMETER = 0.01  # m, d
SLOT_MATERIAL = DemMaterial(
    density=2650.0,
    youngs_modulus=5.0e7,
    poisson_ratio=0.25,
    restitution=0.5,
    friction_static=0.5,
    friction_rolling=0.1,
    youngs_modulus_real=5.0e10,
)
SLOT_WIDTH, SLOT_HEIGHT, SLOT_THICKNESS = 30.0, 45.0, 4.0  # in particle diameters (FR-005-11)
SLOT_FILL = 15.0  # initial fill height in particle diameters
SLOT_DT = 0.2 * rayleigh_time_step(SLOT_MATERIAL, SLOT_DIAMETER / 2.0) * 0.75  # declared step, 0.75 of f_R = 0.2
SETTLE_TIME = 0.4  # s with the slot closed
WINDOW = (0.8, 0.5)  # steady window: the box holds 80 % down to 50 % of its initial mass (a heap stays beside the slot)
CHUNK = 200  # steps between mass samples


def _initial_packing(seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Jittered lattice of spheres filling the box to SLOT_FILL d, falling onto the closed floor."""
    d = SLOT_DIAMETER
    rng = np.random.default_rng(seed)
    nx, ny = 27, 3
    xs = (np.arange(nx) + 0.5) * (SLOT_WIDTH * d / nx)
    ys = (np.arange(ny) + 0.5) * (SLOT_THICKNESS * d / ny)
    layers = int(SLOT_FILL / 1.1)
    pts = []
    for k in range(layers):
        shift = rng.uniform(-0.15, 0.15, 2) * d
        for x in xs:
            for y in ys:
                jitter = rng.uniform(-0.08, 0.08, 3) * d
                pts.append(
                    (
                        x + shift[0] + jitter[0],
                        (y + shift[1] + jitter[1]) % (SLOT_THICKNESS * d),
                        (0.6 + 1.1 * k) * d + jitter[2],
                    )
                )
    pos = np.array(pts)
    pos[:, 0] = np.clip(pos[:, 0], 0.55 * d, (SLOT_WIDTH - 0.55) * d)
    return pos, np.full(len(pos), d / 2.0)


def _box(slot: float | None) -> dict:
    """Walls, domain and periodic range of the box; `slot` is the orifice width W in diameters (None = closed)."""
    d = SLOT_DIAMETER
    w, thickness = SLOT_WIDTH * d, SLOT_THICKNESS * d
    walls = [
        Plane(point=(0.0, 0.0, 0.0), normal=(1.0, 0.0, 0.0)),
        Plane(point=(w, 0.0, 0.0), normal=(-1.0, 0.0, 0.0)),
    ]
    if slot is None:
        walls.append(Plane(point=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)))
    else:
        lo, hi = 0.5 * (w - slot * d), 0.5 * (w + slot * d)
        walls.append(Plane(point=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0), tangent_range=(0, -math.inf, lo)))
        walls.append(Plane(point=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0), tangent_range=(0, hi, math.inf)))
    return {
        "walls": tuple(walls),
        "domain": ((0.0, 0.0, 0.0), (w, thickness, SLOT_HEIGHT * d)),
        "periodic_y": (0.0, thickness),
        "gravity": (0.0, 0.0, -G),
    }


@functools.cache
def slot_discharge(slot_width_over_d: float, *, dt_scale: float = 1.0, device: str = "cpu") -> float:
    """The FR-005-11 quasi-2-D slot benchmark: steady flow rate per unit thickness Q [kg m^-1 s^-1].

    A box 30 d wide and 45 d high, periodic over a thickness of 4 d, is filled to 15 d, settles on a closed floor,
    and the slot of width W = `slot_width_over_d` d opens in the floor. Particles leave through the floor (outflow
    face z-min). Q is the slope of the exited mass against time while the box holds 80 % to 50 % of its initial
    mass, divided by the thickness. `dt_scale` multiplies the benchmark's declared step.
    """
    if not (math.isfinite(slot_width_over_d) and 0.0 < slot_width_over_d < SLOT_WIDTH - 2.0):
        raise ValueError(f"slot_width_over_d: {slot_width_over_d!r} must lie in (0, {SLOT_WIDTH - 2.0})")
    if not (math.isfinite(dt_scale) and dt_scale > 0.0):
        raise ValueError(f"dt_scale: {dt_scale!r} must be positive")
    dt = SLOT_DT * dt_scale
    pos, radii = _initial_packing(seed=0)
    closed = DemSimulation(pos, radii, SLOT_MATERIAL, dt, device=device, **_box(None))
    closed.step(round(SETTLE_TIME / dt))
    sim = DemSimulation(
        closed.positions,
        radii,
        SLOT_MATERIAL,
        dt,
        velocities=closed.velocities,
        angular_velocities=closed.angular_velocities,
        outflow=("z-min",),
        device=device,
        **_box(slot_width_over_d),
    )
    total = sim.mass_inside()
    times, exited = [], []
    max_chunks = round(8.0 / (dt * CHUNK))  # 8 s is far above the discharge time of the widths in FR-005-11
    for _ in range(max_chunks):
        sim.step(CHUNK)
        times.append(sim.time)
        exited.append(sim.mass_exited())
        if sim.mass_inside() < WINDOW[1] * total:
            break
    remaining = total - np.asarray(exited)
    window = (remaining <= WINDOW[0] * total) & (remaining >= WINDOW[1] * total)
    if window.sum() < 3:
        raise RuntimeError("slot_discharge: the steady window holds fewer than three samples")
    slope = float(np.polyfit(np.asarray(times)[window], np.asarray(exited)[window], 1)[0])
    return slope / (SLOT_THICKNESS * SLOT_DIAMETER)

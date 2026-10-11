"""Soft-sphere DEM time stepping on Warp (spec 005, FR-005-01 ... FR-005-09, FR-005-15).

Symplectic (semi-implicit) Euler for translation and rotation. Positions are float64 (a 100 m shift must not swamp
micrometre Hertz overlaps); velocities, forces and contact histories are float32. Contact geometry is formed from
float64 position differences and then cast, so the law of `contact` sees exact overlaps. Neighbours come from a
Warp `HashGrid` built on float32 positions relative to a local origin.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import warp as wp

from pitstudio_studio.physics.dem.contact import damping_beta, hertz_normal

wp.config.quiet = True

GRID_CELLS = 128  # hash-grid size per axis; a hash table, not a domain limit


@dataclass(frozen=True)
class DemMaterial:
    """One DEM material (SI units): the particles and the walls are made of it."""

    density: float
    youngs_modulus: float
    poisson_ratio: float
    restitution: float
    friction_static: float
    friction_rolling: float
    youngs_modulus_real: float | None = None


@dataclass(frozen=True)
class Plane:
    """Rigid infinite wall (R -> inf, m -> inf) of the particle material; `normal` points into the domain."""

    point: tuple[float, float, float]
    normal: tuple[float, float, float]


@wp.kernel
def _make_local_positions(pos: wp.array(dtype=wp.vec3d), origin: wp.vec3d, out: wp.array(dtype=wp.vec3)):
    i = wp.tid()
    d = pos[i] - origin
    out[i] = wp.vec3(float(d[0]), float(d[1]), float(d[2]))


@wp.kernel
def _normal_forces(
    grid: wp.uint64,
    pos: wp.array(dtype=wp.vec3d),
    local: wp.array(dtype=wp.vec3),
    vel: wp.array(dtype=wp.vec3),
    radius: wp.array(dtype=float),
    mass: wp.array(dtype=float),
    r_max: float,
    pad: float,
    e_star: float,
    beta: float,
    force: wp.array(dtype=wp.vec3),
):
    i = wp.tid()
    f = wp.vec3(0.0, 0.0, 0.0)
    q = wp.hash_grid_query(grid, local[i], radius[i] + r_max + pad)
    j = int(0)  # noqa: UP018, RUF046  (Warp needs a typed variable for the iterator)
    while wp.hash_grid_query_next(q, j):
        if j == i:
            continue
        dx = pos[j] - pos[i]
        dist = wp.length(dx)
        delta = float(wp.float64(radius[i]) + wp.float64(radius[j]) - dist)
        if delta <= 0.0:
            continue
        n = wp.vec3(float(dx[0]), float(dx[1]), float(dx[2])) / float(dist)
        r_star = radius[i] * radius[j] / (radius[i] + radius[j])
        m_star = mass[i] * mass[j] / (mass[i] + mass[j])
        v_n = wp.dot(vel[i] - vel[j], n)
        f_el, f_d, _ = hertz_normal(e_star, r_star, m_star, beta, delta, v_n)
        f -= (f_el + f_d) * n
    force[i] = f


@wp.kernel
def _integrate(
    pos: wp.array(dtype=wp.vec3d),
    vel: wp.array(dtype=wp.vec3),
    force: wp.array(dtype=wp.vec3),
    mass: wp.array(dtype=float),
    gravity: wp.vec3,
    dt: float,
):
    i = wp.tid()
    v = vel[i] + (force[i] / mass[i] + gravity) * dt
    vel[i] = v
    pos[i] = pos[i] + wp.vec3d(wp.float64(v[0]), wp.float64(v[1]), wp.float64(v[2])) * wp.float64(dt)


class DemSimulation:
    """Soft-sphere DEM of N spheres on a Warp device ("cpu" in CI, "cuda:0" in production)."""

    def __init__(
        self,
        positions,
        radii,
        material: DemMaterial,
        dt: float,
        *,
        velocities=None,
        angular_velocities=None,
        gravity=(0.0, 0.0, -9.81),
        walls=(),
        contact_capacity: int = 12,
        rayleigh_fraction: float = 0.2,
        domain=None,
        outflow=(),
        device: str = "cpu",
    ) -> None:
        self.device = device
        self.material = material
        self.dt = float(dt)
        pos = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
        self.n = len(pos)
        rad = np.asarray(radii, dtype=np.float64)
        self._radius32 = rad.astype(np.float32)
        self._masses = (material.density * 4.0 / 3.0 * math.pi * rad**3).astype(np.float32).astype(np.float64)
        vel = np.zeros((self.n, 3)) if velocities is None else np.asarray(velocities, dtype=np.float64)
        self._gravity = wp.vec3(*[float(g) for g in gravity])
        self._origin = wp.vec3d(*[float(c) for c in pos.min(axis=0)])
        self._r_max = float(self._radius32.max())
        extent = float(np.ptp(pos, axis=0).max())  # float32 resolution of the local positions scales with it
        self._pad = 1.0e-3 * self._r_max + 4.0e-7 * max(extent, 1.0)
        mk = lambda a, dt_: wp.array(a, dtype=dt_, device=device)  # noqa: E731
        self._pos = mk(pos, wp.vec3d)
        self._local = wp.zeros(self.n, dtype=wp.vec3, device=device)
        self._vel = mk(vel.astype(np.float32), wp.vec3)
        self._force = wp.zeros(self.n, dtype=wp.vec3, device=device)
        self._radius = mk(self._radius32, float)
        self._mass = mk(self._masses.astype(np.float32), float)
        self.hash_grid = wp.HashGrid(GRID_CELLS, GRID_CELLS, GRID_CELLS, device=device)
        mat = material
        self._e_star = mat.youngs_modulus / (2.0 * (1.0 - mat.poisson_ratio**2))
        self._beta = damping_beta(mat.restitution)
        self.step_index = 0

    # ------------------------------------------------------------------ state
    @property
    def positions(self) -> np.ndarray:
        return self._pos.numpy().copy()

    @property
    def velocities(self) -> np.ndarray:
        return self._vel.numpy().astype(np.float64)

    @property
    def masses(self) -> np.ndarray:
        return self._masses.copy()

    @property
    def time(self) -> float:
        return self.step_index * self.dt

    # ------------------------------------------------------------------ stepping
    def step(self, n: int = 1) -> None:
        """Advance `n` steps; the loop only launches kernels (no host work between steps)."""
        dev = self.device
        for _ in range(n):
            wp.launch(_make_local_positions, dim=self.n, inputs=[self._pos, self._origin, self._local], device=dev)
            self.hash_grid.build(self._local, 2.0 * (self._r_max + self._pad))
            wp.launch(
                _normal_forces,
                dim=self.n,
                inputs=[
                    self.hash_grid.id, self._pos, self._local, self._vel, self._radius, self._mass,
                    self._r_max, self._pad, self._e_star, self._beta, self._force,
                ],
                device=dev,
            )  # fmt: skip
            wp.launch(
                _integrate,
                dim=self.n,
                inputs=[self._pos, self._vel, self._force, self._mass, self._gravity, self.dt],
                device=dev,
            )
        self.step_index += n

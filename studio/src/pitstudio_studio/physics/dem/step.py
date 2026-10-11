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

from pitstudio_studio.physics.dem.contact import contact_response, damping_beta, hertz_normal

wp.config.quiet = True

MAX_GRID_CELLS = 128  # hash-grid size per axis at most; a hash table, not a domain limit


def _grid_cells(n: int) -> int:
    """Hash-table cells per axis: about 4 cells per particle (a clear of a large table dominates small runs)."""
    return int(min(MAX_GRID_CELLS, max(4, 2 ** math.ceil(math.log2(max(4.0 * n, 1.0)) / 3.0))))


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
    torque: wp.array(dtype=wp.vec3),
):
    i = wp.tid()
    torque[i] = wp.vec3(0.0, 0.0, 0.0)
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
def _wall_forces(
    pos: wp.array(dtype=wp.vec3d),
    vel: wp.array(dtype=wp.vec3),
    ang: wp.array(dtype=wp.vec3),
    radius: wp.array(dtype=float),
    mass: wp.array(dtype=float),
    inertia: wp.array(dtype=float),
    wall_point: wp.array(dtype=wp.vec3d),
    wall_normal: wp.array(dtype=wp.vec3),
    n_walls: int,
    e_star: float,
    g_star: float,
    beta: float,
    mu_s: float,
    mu_r: float,
    dt: float,
    tang: wp.array(dtype=wp.vec3),
    roll: wp.array(dtype=wp.vec3),
    force: wp.array(dtype=wp.vec3),
    torque: wp.array(dtype=wp.vec3),
):
    i = wp.tid()
    for w in range(n_walls):
        h = i * n_walls + w
        p = pos[i] - wall_point[w]
        nw = wall_normal[w]
        dist = wp.dot(p, wp.vec3d(wp.float64(nw[0]), wp.float64(nw[1]), wp.float64(nw[2])))
        delta = float(wp.float64(radius[i]) - dist)
        if delta <= 0.0:
            tang[h] = wp.vec3(0.0, 0.0, 0.0)
            roll[h] = wp.vec3(0.0, 0.0, 0.0)
            continue
        n = -nw  # from the sphere towards the wall
        v_contact = vel[i] + wp.cross(ang[i] * radius[i], n)
        f, t, tang_new, roll_new = contact_response(
            e_star, g_star, radius[i], mass[i], inertia[i], beta, mu_s, mu_r, delta, n, v_contact, ang[i],
            radius[i], tang[h], roll[h], dt,
        )  # fmt: skip
        tang[h] = tang_new
        roll[h] = roll_new
        force[i] += f
        torque[i] += t


@wp.kernel
def _integrate(
    pos: wp.array(dtype=wp.vec3d),
    vel: wp.array(dtype=wp.vec3),
    ang: wp.array(dtype=wp.vec3),
    force: wp.array(dtype=wp.vec3),
    torque: wp.array(dtype=wp.vec3),
    mass: wp.array(dtype=float),
    inertia: wp.array(dtype=float),
    gravity: wp.vec3,
    dt: float,
):
    i = wp.tid()
    v = vel[i] + (force[i] / mass[i] + gravity) * dt
    vel[i] = v
    ang[i] = ang[i] + torque[i] / inertia[i] * dt
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
        self._torque = wp.zeros(self.n, dtype=wp.vec3, device=device)
        ang = np.zeros((self.n, 3)) if angular_velocities is None else np.asarray(angular_velocities, dtype=np.float64)
        self._ang = mk(ang.astype(np.float32), wp.vec3)
        self._inertia = mk((0.4 * self._masses * rad**2).astype(np.float32), float)
        self._n_walls = len(walls)
        wall_n = np.array([np.asarray(w.normal, float) / np.linalg.norm(w.normal) for w in walls]).reshape(-1, 3)
        self._wall_point = mk(np.array([w.point for w in walls], dtype=np.float64).reshape(-1, 3), wp.vec3d)
        self._wall_normal = mk(wall_n.astype(np.float32), wp.vec3)
        self._wall_tang = wp.zeros(self.n * self._n_walls, dtype=wp.vec3, device=device)
        self._wall_roll = wp.zeros(self.n * self._n_walls, dtype=wp.vec3, device=device)
        self._radius = mk(self._radius32, float)
        self._mass = mk(self._masses.astype(np.float32), float)
        self.hash_grid = wp.HashGrid(*(3 * [_grid_cells(self.n)]), device=device)
        mat = material
        self._e_star = mat.youngs_modulus / (2.0 * (1.0 - mat.poisson_ratio**2))
        self._g_star = (mat.youngs_modulus / (2.0 * (1.0 + mat.poisson_ratio))) / (4.0 * (2.0 - mat.poisson_ratio))
        self._beta = damping_beta(mat.restitution)
        self.step_index = 0
        self._cmds: list | None = None

    # ------------------------------------------------------------------ state
    @property
    def positions(self) -> np.ndarray:
        return self._pos.numpy().copy()

    @property
    def velocities(self) -> np.ndarray:
        return self._vel.numpy().astype(np.float64)

    @property
    def angular_velocities(self) -> np.ndarray:
        return self._ang.numpy().astype(np.float64)

    @property
    def masses(self) -> np.ndarray:
        return self._masses.copy()

    @property
    def time(self) -> float:
        return self.step_index * self.dt

    # ------------------------------------------------------------------ stepping
    def _record(self) -> list:
        """Pre-pack the launches of one step (the arguments never change between steps)."""
        dev = self.device
        mat = self.material
        cmds = [
            wp.launch(
                _make_local_positions, dim=self.n, inputs=[self._pos, self._origin, self._local], device=dev,
                record_cmd=True,
            ),
            wp.launch(
                _normal_forces,
                dim=self.n,
                inputs=[
                    self.hash_grid.id, self._pos, self._local, self._vel, self._radius, self._mass,
                    self._r_max, self._pad, self._e_star, self._beta, self._force, self._torque,
                ],
                device=dev,
                record_cmd=True,
            ),
        ]  # fmt: skip
        if self._n_walls:
            cmds.append(
                wp.launch(
                    _wall_forces,
                    dim=self.n,
                    inputs=[
                        self._pos, self._vel, self._ang, self._radius, self._mass, self._inertia,
                        self._wall_point, self._wall_normal, self._n_walls, self._e_star, self._g_star, self._beta,
                        mat.friction_static, mat.friction_rolling, self.dt,
                        self._wall_tang, self._wall_roll, self._force, self._torque,
                    ],
                    device=dev,
                    record_cmd=True,
                )
            )  # fmt: skip
        cmds.append(
            wp.launch(
                _integrate,
                dim=self.n,
                inputs=[
                    self._pos, self._vel, self._ang, self._force, self._torque, self._mass, self._inertia,
                    self._gravity, self.dt,
                ],
                device=dev,
                record_cmd=True,
            )
        )  # fmt: skip
        return cmds

    def step(self, n: int = 1) -> None:
        """Advance `n` steps; the loop only launches pre-packed kernels (no host work between steps)."""
        if self._cmds is None:
            self._cmds = self._record()
        cell = 2.0 * (self._r_max + self._pad)
        for _ in range(n):
            self._cmds[0].launch()
            self.hash_grid.build(self._local, cell)
            for cmd in self._cmds[1:]:
                cmd.launch()
        self.step_index += n

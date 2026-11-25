"""Soft-sphere DEM time stepping on Warp (spec 005, FR-005-01 ... FR-005-09, FR-005-15).

Symplectic (semi-implicit) Euler for translation and rotation. Positions are float64 (a 100 m shift must not swamp
micrometre Hertz overlaps); velocities, forces and contact histories are float32. Contact geometry is formed from
float64 position differences and then cast, so the law of `contact` sees exact overlaps. Neighbours come from a
Warp `HashGrid` built on float32 positions relative to a local origin.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
import warp as wp

from pitstudio_studio.physics.dem.contact import contact_response, damping_beta
from pitstudio_studio.physics.dem.grid import (
    CTL_COUNT,
    CTL_FAIL_STEP,
    CTL_HALT,
    CTL_PARTICLE,
    CTL_SIZE,
    CTL_STEP,
    NO_PARTICLE,
    check_overflow_kernel,
    commit_step_kernel,
    contact_kernel,
)
from pitstudio_studio.physics.errors import PhysicsError

wp.config.quiet = True

MAX_CONTACT_CAPACITY = 64  # DC-005-01 dem block bound
FACES = ("x-min", "x-max", "y-min", "y-max", "z-min", "z-max")  # DC-005-01 outflow face names
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

    @classmethod
    def from_card(cls, card: dict) -> DemMaterial:
        """Read a DC-005-01 material card (model "dem-sphere")."""
        if card.get("model") != "dem-sphere":
            raise PhysicsError("physics-params-invalid", f"material card {card.get('id')!r} is not a dem-sphere card")
        value = lambda key: float(card[key]["value"])  # noqa: E731
        real = card.get("youngs_modulus_real_pa")
        return cls(
            density=value("density_kg_m3"),
            youngs_modulus=value("youngs_modulus_pa"),
            poisson_ratio=value("poisson_ratio"),
            restitution=value("restitution"),
            friction_static=value("friction_static"),
            friction_rolling=value("friction_rolling"),
            youngs_modulus_real=None if real is None else float(real["value"]),
        )


def rayleigh_time_step(material: DemMaterial, r_min: float) -> float:
    """Delta t_R = pi R_min sqrt(rho / G) / (0.1631 nu + 0.8766) for the modulus in use (FR-005-08)."""
    shear = material.youngs_modulus / (2.0 * (1.0 + material.poisson_ratio))
    return math.pi * r_min * math.sqrt(material.density / shear) / (0.1631 * material.poisson_ratio + 0.8766)


def _es6_number(x: float) -> str:
    """ECMAScript Number-to-string, as RFC 8785 requires (shortest round-trip digits)."""
    if x == 0.0:
        return "0"
    sign = "-" if x < 0 else ""
    t = Decimal(repr(abs(x))).as_tuple()
    digits = "".join(map(str, t.digits))
    n = len(digits) + int(t.exponent)  # position of the decimal point relative to the first digit
    digits = digits.rstrip("0")
    k = len(digits)
    if k <= n <= 21:
        return sign + digits + "0" * (n - k)
    if 0 < n <= 21:
        return sign + digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * (-n) + digits
    exp = f"{'+' if n - 1 >= 0 else '-'}{abs(n - 1)}"
    return f"{sign}{digits[0]}{'.' + digits[1:] if k > 1 else ''}e{exp}"


def _canonical_json(value) -> str:
    """RFC 8785 (JCS) canonical JSON of a card: sorted keys, no spaces, ES6 numbers."""
    if isinstance(value, dict):
        items = ",".join(f"{json.dumps(k, ensure_ascii=False)}:{_canonical_json(v)}" for k, v in sorted(value.items()))
        return "{" + items + "}"
    if isinstance(value, list | tuple):
        return "[" + ",".join(_canonical_json(v) for v in value) + "]"
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return _es6_number(float(value))


def _is_reduced(card: dict) -> bool:
    real = card.get("youngs_modulus_real_pa")
    return real is not None and card["youngs_modulus_pa"]["value"] < real["value"]


def material_ref(card: dict) -> dict:
    """The benchmark report's material reference (DC-005-05 `material_ref`): both moduli when reduced (FR-005-09)."""
    ref = {
        "id": card["id"],
        "card_sha256": hashlib.sha256(_canonical_json(card).encode("utf-8")).hexdigest(),
        "youngs_modulus_pa": float(card["youngs_modulus_pa"]["value"]),
    }
    if _is_reduced(card):
        ref["youngs_modulus_real_pa"] = float(card["youngs_modulus_real_pa"]["value"])
    return ref


def rebenchmark_required(card: dict) -> frozenset[str]:
    """Benchmarks to run at the reduced modulus before the material's rollouts are used (FR-005-09)."""
    return frozenset({"dem-beverloo-silo", "dem-repose"}) if _is_reduced(card) else frozenset()


@dataclass(frozen=True)
class Plane:
    """Rigid wall (R -> inf, m -> inf) of the particle material; `normal` points into the domain.

    Infinite unless `tangent_range` limits it to the sphere centres whose coordinate on that axis lies in [lo, hi]
    (a floor with a slot is two such planes)."""

    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    tangent_range: tuple[int, float, float] | None = None  # (axis, lo, hi): acts only where lo <= centre[axis] <= hi


@wp.kernel
def _make_local_positions(pos: wp.array(dtype=wp.vec3d), origin: wp.vec3d, out: wp.array(dtype=wp.vec3)):
    i = wp.tid()
    d = pos[i] - origin
    out[i] = wp.vec3(float(d[0]), float(d[1]), float(d[2]))


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
    wall_axis: wp.array(dtype=int),
    wall_lo: wp.array(dtype=wp.float64),
    wall_hi: wp.array(dtype=wp.float64),
    n_walls: int,
    e_star: float,
    g_star: float,
    beta: float,
    mu_s: float,
    mu_r: float,
    dt: float,
    tang: wp.array(dtype=wp.vec3),
    roll: wp.array(dtype=wp.vec3),
    ctl: wp.array(dtype=int),
    inside: wp.array(dtype=int),
    force: wp.array(dtype=wp.vec3),
    torque: wp.array(dtype=wp.vec3),
):
    i = wp.tid()
    if ctl[0] != 0 or inside[i] == 0:
        return
    for w in range(n_walls):
        h = i * n_walls + w
        if wall_axis[w] >= 0:
            c = pos[i][wall_axis[w]]
            if c < wall_lo[w] or c > wall_hi[w]:
                tang[h] = wp.vec3(0.0, 0.0, 0.0)
                roll[h] = wp.vec3(0.0, 0.0, 0.0)
                continue
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
    ctl: wp.array(dtype=int),
    inside: wp.array(dtype=int),
    exit_face: wp.array(dtype=int),
    dom_min: wp.vec3d,
    dom_max: wp.vec3d,
    outflow: wp.array(dtype=int),
    period: float,
    period_lo: wp.float64,
):
    i = wp.tid()
    if ctl[0] != 0 or inside[i] == 0:
        return
    v = vel[i] + (force[i] / mass[i] + gravity) * dt
    vel[i] = v
    ang[i] = ang[i] + torque[i] / inertia[i] * dt
    p = pos[i] + wp.vec3d(wp.float64(v[0]), wp.float64(v[1]), wp.float64(v[2])) * wp.float64(dt)
    if period > 0.0:  # periodic along y: wrap the centre back into [lo, lo + period)
        p64 = wp.float64(period)
        p = wp.vec3d(p[0], p[1] - p64 * wp.floor((p[1] - period_lo) / p64), p[2])
    pos[i] = p
    # a particle whose centre crosses a declared outflow face leaves the dynamics and is recorded against it
    for face in range(6):
        if outflow[face] != 0 and inside[i] != 0:
            axis = face // 2
            if (face % 2 == 0 and p[axis] < dom_min[axis]) or (face % 2 == 1 and p[axis] > dom_max[axis]):
                inside[i] = 0
                exit_face[i] = face


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
        periodic_y: tuple[float, float] | None = None,
        device: str = "cpu",
    ) -> None:
        if isinstance(contact_capacity, bool) or not isinstance(contact_capacity, int | np.integer):
            raise PhysicsError(
                "physics-params-invalid", f"contact_capacity must be an integer, got {contact_capacity!r}"
            )
        if not 1 <= contact_capacity <= MAX_CONTACT_CAPACITY:
            raise PhysicsError(
                "physics-params-invalid", f"contact_capacity {contact_capacity} is outside 1..{MAX_CONTACT_CAPACITY}"
            )
        self.device = device
        self.material = material
        self.dt = float(dt)
        self.contact_capacity = int(contact_capacity)
        pos = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
        self.n = len(pos)
        rad = np.asarray(radii, dtype=np.float64)
        if rad.shape != (self.n,) or not (np.isfinite(rad).all() and (rad > 0.0).all()):
            raise PhysicsError("physics-params-invalid", "radii must be positive finite numbers, one per particle")
        self.rayleigh_dt = rayleigh_time_step(material, float(rad.min()))
        self._check_time_step(rayleigh_fraction)
        self._radius32 = rad.astype(np.float32)
        flags, bounds = self._parse_outflow(domain, outflow)
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
        ranges = [w.tangent_range if w.tangent_range is not None else (-1, 0.0, 0.0) for w in walls]
        self._wall_axis = mk(np.array([r[0] for r in ranges], dtype=np.int32), int)
        self._wall_lo = mk(np.array([r[1] for r in ranges], dtype=np.float64), wp.float64)
        self._wall_hi = mk(np.array([r[2] for r in ranges], dtype=np.float64), wp.float64)
        self._wall_tang = wp.zeros(self.n * self._n_walls, dtype=wp.vec3, device=device)
        self._wall_roll = wp.zeros(self.n * self._n_walls, dtype=wp.vec3, device=device)
        self._radius = mk(self._radius32, float)
        self._mass = mk(self._masses.astype(np.float32), float)
        self._period = 0.0 if periodic_y is None else float(periodic_y[1] - periodic_y[0])
        self._period_lo = wp.float64(0.0 if periodic_y is None else float(periodic_y[0]))
        if periodic_y is not None and not self._period > 4.0 * self._r_max:
            raise PhysicsError(
                "physics-params-invalid", "the periodic length must exceed four times the largest radius"
            )
        self.hash_grid = wp.HashGrid(*(3 * [_grid_cells(self.n)]), device=device)
        # contact lists: two buffers, read the previous step's, write this step's
        slots = self.n * self.contact_capacity
        self._lists = [
            (
                wp.full(slots, -1, dtype=int, device=device),
                wp.zeros(slots, dtype=wp.vec3, device=device),
                wp.zeros(slots, dtype=wp.vec3, device=device),
            )
            for _ in range(2)
        ]
        self._current = 0  # index of the list holding the latest contacts
        self.outflow = tuple(outflow)
        self._inside = wp.ones(self.n, dtype=int, device=device)
        self._exit_face = wp.full(self.n, -1, dtype=int, device=device)
        self._outflow_flags = mk(flags, int)
        self._dom_min = wp.vec3d(*bounds[0])
        self._dom_max = wp.vec3d(*bounds[1])
        self._counts = wp.zeros(self.n, dtype=int, device=device)
        self._ctl = wp.array([0, NO_PARTICLE] + [0] * (CTL_SIZE - 2), dtype=int, device=device)
        mat = material
        self._e_star = mat.youngs_modulus / (2.0 * (1.0 - mat.poisson_ratio**2))
        self._g_star = (mat.youngs_modulus / (2.0 * (1.0 + mat.poisson_ratio))) / (4.0 * (2.0 - mat.poisson_ratio))
        self._beta = damping_beta(mat.restitution)
        self.step_index = 0
        self._cmds: list[list] | None = None
        self._error: PhysicsError | None = None

    def _check_time_step(self, fraction: float) -> None:
        """FR-005-08: reject a step above f_R x Delta t_R (NaN, zero or negative steps and f_R outside (0, 1] too)."""
        if not 0.0 < fraction <= 1.0:
            raise PhysicsError("physics-params-invalid", f"rayleigh_fraction {fraction!r} is outside (0, 1]")
        if not self.dt > 0.0:
            raise PhysicsError("physics-params-invalid", f"time step {self.dt!r} s is not a positive number")
        limit = fraction * self.rayleigh_dt
        if self.dt > limit:
            raise PhysicsError(
                "dt-unstable",
                f"time step {self.dt:.6g} s exceeds the limit {limit:.6g} s "
                f"(f_R {fraction:.3g} x Rayleigh step {self.rayleigh_dt:.6g} s of the smallest particle)",
                dt=self.dt,
                dt_limit=limit,
            )

    @staticmethod
    def _parse_outflow(domain, outflow) -> tuple[np.ndarray, tuple]:
        """Validate the declared outflow faces and the domain box; returns (face flags, (min, max))."""
        unknown = [f for f in outflow if f not in FACES]
        if unknown:
            raise PhysicsError("physics-params-invalid", f"unknown outflow face(s) {unknown}; use {list(FACES)}")
        if outflow and domain is None:
            raise PhysicsError("physics-params-invalid", "an outflow boundary needs a declared domain box")
        flags = np.array([int(f in outflow) for f in FACES], dtype=np.int32)
        if domain is None:
            return flags, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        lo, hi = (tuple(float(c) for c in corner) for corner in domain)
        return flags, (lo, hi)

    def observables_metadata(self) -> dict:
        """Observables-file metadata (DC-005-03); both moduli are recorded when the modulus is reduced (FR-005-09)."""
        meta: dict = {}
        mat = self.material
        if mat.youngs_modulus_real is not None and mat.youngs_modulus < mat.youngs_modulus_real:
            meta["youngs_modulus"] = {"used_pa": mat.youngs_modulus, "real_pa": mat.youngs_modulus_real}
        return meta

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

    def contact_counts(self) -> np.ndarray:
        """Sphere-sphere contacts per particle at the latest step (the true count, also beyond the capacity)."""
        return self._counts.numpy().copy()

    def contact_list(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(neighbours (N, C), tangential history (N, C, 3), rolling history (N, C, 3)); -1 marks an empty slot."""
        nb, tang, roll = self._lists[self._current]
        c = self.contact_capacity
        return (
            nb.numpy().reshape(self.n, c).copy(),
            tang.numpy().astype(np.float64).reshape(self.n, c, 3),
            roll.numpy().astype(np.float64).reshape(self.n, c, 3),
        )

    # ------------------------------------------------------------------ stepping
    def _record(self) -> list[list]:
        """Pre-pack the launches of one step, once per list parity (the arguments never change between steps)."""
        dev = self.device
        mat = self.material
        n = self.n
        sets = []
        for parity in range(2):
            old, new = self._lists[parity], self._lists[1 - parity]
            cmds = [
                wp.launch(
                    _make_local_positions, dim=n, inputs=[self._pos, self._origin, self._local], device=dev,
                    record_cmd=True,
                ),
                wp.launch(
                    contact_kernel,
                    dim=n,
                    inputs=[
                        self.hash_grid.id, self._pos, self._local, self._vel, self._ang, self._radius,
                        self._mass, self._inertia, self._r_max, self._pad, self._e_star, self._g_star,
                        self._beta, mat.friction_static, mat.friction_rolling, self.dt, self.contact_capacity,
                        self._period,
                        *old, *new, self._counts, self._ctl, self._inside, self._force, self._torque,
                    ],
                    device=dev,
                    record_cmd=True,
                ),
                wp.launch(
                    check_overflow_kernel, dim=n, inputs=[self._counts, self.contact_capacity, self._ctl],
                    device=dev, record_cmd=True,
                ),
                wp.launch(commit_step_kernel, dim=1, inputs=[self._counts, n, self._ctl], device=dev, record_cmd=True),
            ]  # fmt: skip
            if self._n_walls:
                cmds.append(
                    wp.launch(
                        _wall_forces,
                        dim=n,
                        inputs=[
                            self._pos, self._vel, self._ang, self._radius, self._mass, self._inertia,
                            self._wall_point, self._wall_normal, self._wall_axis, self._wall_lo,
                            self._wall_hi, self._n_walls, self._e_star, self._g_star,
                            self._beta, mat.friction_static, mat.friction_rolling, self.dt,
                            self._wall_tang, self._wall_roll, self._ctl, self._inside, self._force, self._torque,
                        ],
                        device=dev,
                        record_cmd=True,
                    )
                )  # fmt: skip
            cmds.append(
                wp.launch(
                    _integrate,
                    dim=n,
                    inputs=[
                        self._pos, self._vel, self._ang, self._force, self._torque, self._mass, self._inertia,
                        self._gravity, self.dt, self._ctl, self._inside, self._exit_face,
                        self._dom_min, self._dom_max, self._outflow_flags, self._period, self._period_lo,
                    ],
                    device=dev,
                    record_cmd=True,
                )
            )  # fmt: skip
            sets.append(cmds)
        return sets

    def step(self, n: int = 1) -> None:
        """Advance `n` steps; the loop only launches pre-packed kernels (no host work between steps).

        A contact-list overflow halts the device-side run at the failing step; the error is raised here, after the
        launches, with `step_index` equal to the number of steps completed before the failing step.
        """
        if self._error is not None:
            raise self._error
        if self._cmds is None:
            self._cmds = self._record()
        cell = 2.0 * (self._r_max + self._pad)
        for _ in range(n):
            cmds = self._cmds[self._current]
            cmds[0].launch()
            self.hash_grid.build(self._local, cell)
            for cmd in cmds[1:]:
                cmd.launch()
            self._current = 1 - self._current
        ctl = self._ctl.numpy()
        self.step_index = int(ctl[CTL_STEP])
        if ctl[CTL_HALT]:
            particle, count, step = int(ctl[CTL_PARTICLE]), int(ctl[CTL_COUNT]), int(ctl[CTL_FAIL_STEP])
            self._error = PhysicsError(
                "contact-overflow",
                f"particle {particle} has {count} contacts, above the capacity {self.contact_capacity}, at step {step}",
                particle=particle,
                contacts=count,
                step=step,
            )
            raise self._error

    # ------------------------------------------------------------------ mass accounting (FR-005-15)
    def inside_mask(self) -> np.ndarray:
        """True while the particle is in the domain (it has not left through a declared outflow boundary)."""
        return self._inside.numpy().astype(bool)

    def count_inside(self) -> int:
        return int(self._inside.numpy().sum())

    def count_exited(self) -> int:
        return self.n - self.count_inside()

    def exited_by_boundary(self) -> dict[str, int]:
        """Particles recorded against each declared outflow face (faces with none included)."""
        faces = self._exit_face.numpy()
        return {name: int((faces == FACES.index(name)).sum()) for name in self.outflow}

    def mass_inside(self) -> float:
        """float64 sum of the per-particle masses inside the domain (exact: `math.fsum`)."""
        return math.fsum(self._masses[self.inside_mask()])

    def mass_exited(self) -> float:
        return math.fsum(self._masses[~self.inside_mask()])

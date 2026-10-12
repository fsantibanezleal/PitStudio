"""Differentiable DEM on the Warp tape and the gradient calibration arm (FR-011-17, FR-011-19, FR-011-21, P-011-11).

`rollout_gradient` settles a heap without recording, records the last W steps under `wp.Tape` and differentiates an objective of the
final state with respect to the sliding friction mu_s of the contact law. The recorded dynamics are a history-free form of the
Hertz-Mindlin law of spec 005 (`dem/contact.py` shares the Hertz normal force and damping):

- normal force: Hertz elastic force plus the damping of the restitution coefficient (`hertz_normal`);
- sliding friction: F_t = -mu_s F_n v_t / sqrt(|v_t|^2 + eps^2), the Coulomb cap with a smooth sign of the slip velocity v_t at the
  contact point (spin included), so that mu_s enters linearly and the tape sees a smooth dependence (no stored tangential spring:
  its history would have to be recorded step by step);
- rolling resistance: tau = -mu_r R* F_n w_t / sqrt(|w_t|^2 + eps_w^2) (the same smooth cap).

Contacts come from a candidate pair list built on the host from the positions at the start of the window (plus a skin that covers the
motion of the window; a window that outgrows it raises instead of silently missing a contact). Per-contact force buffers are written
by one kernel per step, summed per particle by a gather over a fixed CSR of the pairs (no atomics), and integrated by semi-implicit
Euler. Every step has its own state and buffer arrays, so the adjoint reads exactly the forward values. The friction is passed to the
kernels as one array element per contact and per particle; the gradient is the exact sum (`math.fsum`) of their adjoints, so it does not
depend on the order of any atomic. `wp.config.deterministic` is set to RUN_TO_RUN for this module (FR-011-19).
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import warp as wp

from pitstudio.calibration.errors import InvalidCalibrationError
from pitstudio_studio.physics.calibration.cmaes import ArmResult
from pitstudio_studio.physics.dem.contact import damping_beta, hertz_normal
from pitstudio_studio.physics.dem.step import rayleigh_time_step, DemMaterial

wp.config.quiet = True
wp.set_module_options({"deterministic": wp.DeterministicMode.RUN_TO_RUN})

G = 9.81
EPS_SLIP = 1.0e-3  # m/s, smoothing of the sign of the slip velocity
EPS_ROLL = 1.0e-2  # rad/s, the same for the rolling torque
MU_LIMITS = (0.05, 2.0)
RAYLEIGH_FRACTION = 0.2  # the time-step limit of FR-005-08
REBUILD_CHECK_EVERY = 50  # settling steps between candidate-list checks
BYTES_PER_PARTICLE_STEP = 84  # state 36 + total force/torque 24 + floor force/torque 24 (bytes of the recorded arrays)
BYTES_PER_PAIR_STEP = 36  # force on i, torque on i, torque on j (three float32 triples)


@dataclass
class TapeScene:
    """Particles of one heap in SI units (positions and velocities [N, 3], radii [N]) and the particle material."""

    positions: np.ndarray
    velocities: np.ndarray
    radii: np.ndarray
    density: float
    youngs_modulus: float
    poisson_ratio: float
    restitution: float
    rolling_friction: float = 0.0
    angular_velocities: np.ndarray | None = None


@dataclass
class TapeRollout:
    objective: float
    gradient: float
    final_positions: np.ndarray
    final_velocities: np.ndarray
    deterministic: bool = True
    pairs: int = 0
    extras: dict[str, Any] = field(default_factory=dict)


def tape_memory_bytes(particles: int, window_steps: int, pairs_per_particle: float = 3.0) -> int:
    """Bytes the recorded window allocates: per-step state and force arrays plus the per-contact force buffers."""
    return int(window_steps * (BYTES_PER_PARTICLE_STEP * particles + BYTES_PER_PAIR_STEP * pairs_per_particle * particles))


# ------------------------------------------------------------------ kernels


@wp.kernel
def _pair_forces(
    pi: wp.array(dtype=int),
    pj: wp.array(dtype=int),
    x: wp.array(dtype=wp.vec3),
    v: wp.array(dtype=wp.vec3),
    w: wp.array(dtype=wp.vec3),
    radius: wp.array(dtype=float),
    mass: wp.array(dtype=float),
    mu_s: wp.array(dtype=float),
    e_star: float,
    beta: float,
    mu_r: float,
    f_out: wp.array(dtype=wp.vec3),
    ti_out: wp.array(dtype=wp.vec3),
    tj_out: wp.array(dtype=wp.vec3),
):
    p = wp.tid()
    i = pi[p]
    j = pj[p]
    zero = wp.vec3(0.0, 0.0, 0.0)
    d = x[j] - x[i]
    dist = wp.length(d)
    ri = radius[i]
    rj = radius[j]
    delta = ri + rj - dist
    if delta <= 0.0 or dist <= 0.0:
        f_out[p] = zero
        ti_out[p] = zero
        tj_out[p] = zero
        return
    n = d / dist
    r_star = ri * rj / (ri + rj)
    m_star = mass[i] * mass[j] / (mass[i] + mass[j])
    v_rel = (v[i] + wp.cross(w[i], n * ri)) - (v[j] + wp.cross(w[j], -n * rj))
    v_n = wp.dot(v_rel, n)
    f_el, f_d, s_n = hertz_normal(e_star, r_star, m_star, beta, delta, v_n)
    fn = wp.max(f_el + f_d, 0.0)
    v_t = v_rel - n * v_n
    ft = -(mu_s[p] * fn) * v_t / wp.sqrt(wp.dot(v_t, v_t) + 1.0e-6)
    w_rel = w[i] - w[j]
    w_t = w_rel - n * wp.dot(w_rel, n)
    troll = -(mu_r * r_star * fn) * w_t / wp.sqrt(wp.dot(w_t, w_t) + 1.0e-4)
    f_out[p] = -(f_el + f_d) * n + ft
    ti_out[p] = wp.cross(n * ri, ft) + troll
    tj_out[p] = wp.cross(n * rj, ft) - troll


@wp.kernel
def _floor_forces(
    x: wp.array(dtype=wp.vec3),
    v: wp.array(dtype=wp.vec3),
    w: wp.array(dtype=wp.vec3),
    radius: wp.array(dtype=float),
    mass: wp.array(dtype=float),
    mu_s: wp.array(dtype=float),
    e_star: float,
    beta: float,
    mu_r: float,
    f_out: wp.array(dtype=wp.vec3),
    t_out: wp.array(dtype=wp.vec3),
):
    i = wp.tid()
    r = radius[i]
    delta = r - x[i][2]
    zero = wp.vec3(0.0, 0.0, 0.0)
    if delta <= 0.0:
        f_out[i] = zero
        t_out[i] = zero
        return
    n = wp.vec3(0.0, 0.0, -1.0)
    v_rel = v[i] + wp.cross(w[i], n * r)
    v_n = wp.dot(v_rel, n)
    f_el, f_d, s_n = hertz_normal(e_star, r, mass[i], beta, delta, v_n)
    fn = wp.max(f_el + f_d, 0.0)
    v_t = v_rel - n * v_n
    ft = -(mu_s[i] * fn) * v_t / wp.sqrt(wp.dot(v_t, v_t) + 1.0e-6)
    w_t = w[i] - n * wp.dot(w[i], n)
    troll = -(mu_r * r * fn) * w_t / wp.sqrt(wp.dot(w_t, w_t) + 1.0e-4)
    f_out[i] = -(f_el + f_d) * n + ft
    t_out[i] = wp.cross(n * r, ft) + troll


@wp.kernel
def _accumulate(
    csr_start: wp.array(dtype=int),
    csr_pair: wp.array(dtype=int),
    csr_side: wp.array(dtype=int),
    pair_f: wp.array(dtype=wp.vec3),
    pair_ti: wp.array(dtype=wp.vec3),
    pair_tj: wp.array(dtype=wp.vec3),
    floor_f: wp.array(dtype=wp.vec3),
    floor_t: wp.array(dtype=wp.vec3),
    f_total: wp.array(dtype=wp.vec3),
    t_total: wp.array(dtype=wp.vec3),
):
    i = wp.tid()
    f = floor_f[i]
    t = floor_t[i]
    for k in range(csr_start[i], csr_start[i + 1]):
        p = csr_pair[k]
        if csr_side[k] == 0:
            f = f + pair_f[p]
            t = t + pair_ti[p]
        else:
            f = f - pair_f[p]
            t = t + pair_tj[p]
    f_total[i] = f
    t_total[i] = t


@wp.kernel
def _integrate(
    x: wp.array(dtype=wp.vec3),
    v: wp.array(dtype=wp.vec3),
    w: wp.array(dtype=wp.vec3),
    f_total: wp.array(dtype=wp.vec3),
    t_total: wp.array(dtype=wp.vec3),
    mass: wp.array(dtype=float),
    inertia: wp.array(dtype=float),
    dt: float,
    x_new: wp.array(dtype=wp.vec3),
    v_new: wp.array(dtype=wp.vec3),
    w_new: wp.array(dtype=wp.vec3),
):
    i = wp.tid()
    vn = v[i] + (f_total[i] / mass[i] + wp.vec3(0.0, 0.0, -9.81)) * dt
    v_new[i] = vn
    w_new[i] = w[i] + t_total[i] / inertia[i] * dt
    x_new[i] = x[i] + vn * dt


@wp.kernel
def _objective(x: wp.array(dtype=wp.vec3), axis: int, inv_n: float, out: wp.array(dtype=float)):
    i = wp.tid()
    out[i] = x[i][axis] * inv_n


# ------------------------------------------------------------------ host helpers


def _validate(scene: TapeScene, mu: float, record_steps: int, settle_steps: int, dt: float, objective: str) -> None:
    if not isinstance(mu, int | float | np.floating) or not math.isfinite(mu) or not MU_LIMITS[0] <= mu <= MU_LIMITS[1]:
        raise InvalidCalibrationError(f"mu must be a finite number in {list(MU_LIMITS)}, got {mu!r}")
    if not isinstance(record_steps, int | np.integer) or record_steps < 1:
        raise InvalidCalibrationError(f"record_steps must be an integer >= 1, got {record_steps!r}")
    if not isinstance(settle_steps, int | np.integer) or settle_steps < 0:
        raise InvalidCalibrationError(f"settle_steps must be an integer >= 0, got {settle_steps!r}")
    if not isinstance(dt, int | float | np.floating) or not math.isfinite(dt) or dt <= 0:
        raise InvalidCalibrationError(f"dt must be a positive finite number, got {dt!r}")
    if objective not in ("mean_x", "mean_z"):
        raise InvalidCalibrationError(f"objective must be 'mean_x' or 'mean_z', got {objective!r}")
    pos = np.asarray(scene.positions, dtype=np.float64)
    vel = np.asarray(scene.velocities, dtype=np.float64)
    rad = np.asarray(scene.radii, dtype=np.float64)
    if pos.ndim != 2 or pos.shape[1] != 3 or pos.shape[0] == 0:
        raise InvalidCalibrationError(f"the scene needs positions of shape [N, 3] with N >= 1, got {list(pos.shape)}")
    if vel.shape != pos.shape or rad.shape != (pos.shape[0],):
        raise InvalidCalibrationError("velocities must match positions and radii must be one per particle")
    if not (np.isfinite(pos).all() and np.isfinite(vel).all() and np.isfinite(rad).all() and (rad > 0).all()):
        raise InvalidCalibrationError("the scene holds a non-finite value or a non-positive radius")
    for name in ("density", "youngs_modulus", "poisson_ratio", "restitution", "rolling_friction"):
        value = getattr(scene, name)
        if not isinstance(value, int | float | np.floating) or not math.isfinite(value) or value < 0:
            raise InvalidCalibrationError(f"scene.{name} must be a finite non-negative number, got {value!r}")
    if not 0.0 < scene.restitution <= 1.0 or scene.density <= 0 or scene.youngs_modulus <= 0 or scene.poisson_ratio >= 0.5:
        raise InvalidCalibrationError("scene material is outside the physical range")
    material = DemMaterial(scene.density, scene.youngs_modulus, scene.poisson_ratio, scene.restitution, 0.5, 0.0)
    limit = RAYLEIGH_FRACTION * rayleigh_time_step(material, float(rad.min()))
    if dt > limit:
        raise InvalidCalibrationError(f"dt {dt:g} s exceeds {RAYLEIGH_FRACTION} x the Rayleigh step ({limit:g} s)")


def candidate_pairs(positions: np.ndarray, radii: np.ndarray, skin: float) -> np.ndarray:
    """Pairs (i < j) whose centres are closer than r_i + r_j + skin, by an x-sorted sweep; int32 [P, 2]."""
    n = positions.shape[0]
    if n < 2:
        return np.zeros((0, 2), dtype=np.int32)
    order = np.argsort(positions[:, 0], kind="stable")
    xs = positions[order, 0]
    reach = 2.0 * float(radii.max()) + skin
    hi = np.searchsorted(xs, xs + reach, side="right")
    out = []
    for a in range(n):
        b = np.arange(a + 1, hi[a])
        if b.size == 0:
            continue
        i, j = order[a], order[b]
        d = np.linalg.norm(positions[j] - positions[i], axis=1)
        ok = d < radii[i] + radii[j] + skin
        if ok.any():
            lo_idx = np.minimum(i, j[ok])
            hi_idx = np.maximum(i, j[ok])
            out.append(np.column_stack([lo_idx, hi_idx]))
    if not out:
        return np.zeros((0, 2), dtype=np.int32)
    pairs = np.concatenate(out).astype(np.int32)
    return pairs[np.lexsort((pairs[:, 1], pairs[:, 0]))]


def _csr(pairs: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-particle lists of (pair index, side) in pair order: start offsets, pair ids, side flags (0 = first, 1 = second)."""
    owner = np.concatenate([pairs[:, 0], pairs[:, 1]]) if len(pairs) else np.zeros(0, dtype=np.int32)
    pair_id = np.concatenate([np.arange(len(pairs)), np.arange(len(pairs))]).astype(np.int32)
    side = np.concatenate([np.zeros(len(pairs)), np.ones(len(pairs))]).astype(np.int32)
    order = np.lexsort((pair_id, owner))
    counts = np.bincount(owner, minlength=n)
    start = np.concatenate([[0], np.cumsum(counts)]).astype(np.int32)
    return start, pair_id[order] if len(owner) else np.zeros(1, np.int32), side[order] if len(owner) else np.zeros(1, np.int32)


class _Dem:
    """Device arrays of one scene and the kernels of one step (shared by the settling and the recorded phases)."""

    def __init__(self, scene: TapeScene, mu: float, dt: float, device: str) -> None:
        self.device, self.dt, self.n = device, float(dt), len(scene.positions)
        rad = np.asarray(scene.radii, dtype=np.float64)
        mass = scene.density * 4.0 / 3.0 * math.pi * rad**3
        self.radius = wp.array(rad.astype(np.float32), dtype=float, device=device)
        self.mass = wp.array(mass.astype(np.float32), dtype=float, device=device)
        self.inertia = wp.array((0.4 * mass * rad**2).astype(np.float32), dtype=float, device=device)
        self.e_star = float(scene.youngs_modulus / (2.0 * (1.0 - scene.poisson_ratio**2)))
        self.beta = float(damping_beta(scene.restitution))
        self.mu_r = float(scene.rolling_friction)
        self.mu = float(mu)
        self.radii_np = rad

    def zeros_vec(self, n: int, grad: bool) -> wp.array:
        return wp.zeros(max(n, 1), dtype=wp.vec3, device=self.device, requires_grad=grad)

    def pair_arrays(self, pairs: np.ndarray, grad: bool) -> dict[str, Any]:
        p = len(pairs)
        csr_start, csr_pair, csr_side = _csr(pairs, self.n)
        d = self.device
        return {
            "p": p,
            "pi": wp.array(pairs[:, 0].astype(np.int32) if p else np.zeros(1, np.int32), dtype=int, device=d),
            "pj": wp.array(pairs[:, 1].astype(np.int32) if p else np.zeros(1, np.int32), dtype=int, device=d),
            "start": wp.array(csr_start, dtype=int, device=d),
            "pair": wp.array(csr_pair, dtype=int, device=d),
            "side": wp.array(csr_side, dtype=int, device=d),
            "mu_p": wp.array(np.full(max(p, 1), self.mu, dtype=np.float32), dtype=float, device=d, requires_grad=grad),
        }

    def step(self, topo: dict[str, Any], cur: tuple, nxt: tuple, buf: dict[str, Any], mu_floor: wp.array) -> None:
        """Launch the kernels of one step: (x, v, w) of `cur` to `nxt` through the force buffers `buf`."""
        x, v, w = cur
        d = self.device
        if topo["p"]:
            wp.launch(
                _pair_forces, dim=topo["p"],
                inputs=[topo["pi"], topo["pj"], x, v, w, self.radius, self.mass, topo["mu_p"], self.e_star, self.beta, self.mu_r],
                outputs=[buf["pair_f"], buf["pair_ti"], buf["pair_tj"]], device=d,
            )  # fmt: skip
        wp.launch(
            _floor_forces, dim=self.n,
            inputs=[x, v, w, self.radius, self.mass, mu_floor, self.e_star, self.beta, self.mu_r],
            outputs=[buf["floor_f"], buf["floor_t"]], device=d,
        )  # fmt: skip
        wp.launch(
            _accumulate, dim=self.n,
            inputs=[topo["start"], topo["pair"], topo["side"], buf["pair_f"], buf["pair_ti"], buf["pair_tj"], buf["floor_f"], buf["floor_t"]],
            outputs=[buf["f_total"], buf["t_total"]], device=d,
        )  # fmt: skip
        wp.launch(
            _integrate, dim=self.n,
            inputs=[x, v, w, buf["f_total"], buf["t_total"], self.mass, self.inertia, self.dt],
            outputs=list(nxt), device=d,
        )  # fmt: skip

    def buffers(self, p: int, grad: bool) -> dict[str, Any]:
        return {
            "pair_f": self.zeros_vec(p, grad),
            "pair_ti": self.zeros_vec(p, grad),
            "pair_tj": self.zeros_vec(p, grad),
            "floor_f": self.zeros_vec(self.n, grad),
            "floor_t": self.zeros_vec(self.n, grad),
            "f_total": self.zeros_vec(self.n, grad),
            "t_total": self.zeros_vec(self.n, grad),
        }


def rollout_gradient(
    scene: TapeScene,
    mu: float,
    *,
    settle_steps: int = 0,
    record_steps: int,
    dt: float,
    objective: str = "mean_x",
    device: str = "cpu",
) -> TapeRollout:
    """Settle without recording, record `record_steps` steps and return the objective and d objective / d mu_s."""
    _validate(scene, mu, record_steps, settle_steps, dt, objective)
    dem = _Dem(scene, float(mu), float(dt), device)
    n = dem.n
    pos = np.asarray(scene.positions, dtype=np.float64)
    vel = np.asarray(scene.velocities, dtype=np.float64)
    ang = np.zeros((n, 3)) if scene.angular_velocities is None else np.asarray(scene.angular_velocities, dtype=np.float64)
    r_max = float(dem.radii_np.max())

    def vec(a: np.ndarray, grad: bool = False) -> wp.array:
        return wp.array(np.ascontiguousarray(a, dtype=np.float32), dtype=wp.vec3, device=device, requires_grad=grad)

    # ---- settling: plain launches on two alternating state sets, candidate pairs refreshed when the heap has moved
    state_a = [vec(pos), vec(vel), vec(ang)]
    state_b = [vec(pos), vec(vel), vec(ang)]
    mu_floor_plain = wp.array(np.full(n, float(mu), dtype=np.float32), dtype=float, device=device)
    skin = 0.5 * r_max
    built_at = pos.copy()
    topo = dem.pair_arrays(candidate_pairs(pos, dem.radii_np, skin), grad=False)
    buf = dem.buffers(topo["p"], grad=False)
    cur, nxt = state_a, state_b
    for s in range(settle_steps):
        if s and s % REBUILD_CHECK_EVERY == 0:
            now = cur[0].numpy().astype(np.float64)
            if float(np.abs(now - built_at).max()) > 0.25 * skin:
                topo = dem.pair_arrays(candidate_pairs(now, dem.radii_np, skin), grad=False)
                buf = dem.buffers(topo["p"], grad=False)
                built_at = now
        dem.step(topo, tuple(cur), tuple(nxt), buf, mu_floor_plain)
        cur, nxt = nxt, cur
    now_x = cur[0].numpy().astype(np.float64)
    now_v = cur[1].numpy().astype(np.float64)
    now_w = cur[2].numpy().astype(np.float64)

    # ---- the recorded window
    speed = float(np.abs(now_v).max()) + float(np.abs(now_w).max()) * r_max
    window_skin = max(0.5 * r_max, 2.0 * speed * record_steps * dt + 0.5 * G * (record_steps * dt) ** 2)
    pairs = candidate_pairs(now_x, dem.radii_np, window_skin)
    topo = dem.pair_arrays(pairs, grad=True)
    mu_floor = wp.array(np.full(n, float(mu), dtype=np.float32), dtype=float, device=device, requires_grad=True)
    states = [(vec(now_x, True), vec(now_v, True), vec(now_w, True))]
    for _ in range(record_steps):
        states.append((vec(now_x * 0, True), vec(now_x * 0, True), vec(now_x * 0, True)))
    obj = wp.zeros(n, dtype=float, device=device, requires_grad=True)
    tape = wp.Tape()
    with tape:
        for t in range(record_steps):
            dem.step(topo, states[t], states[t + 1], dem.buffers(topo["p"], True), mu_floor)
        axis = 0 if objective == "mean_x" else 2
        wp.launch(_objective, dim=n, inputs=[states[-1][0], axis, 1.0 / n], outputs=[obj], device=device)
    value = math.fsum(float(v) for v in obj.numpy())
    tape.backward(grads={obj: wp.array(np.ones(n, dtype=np.float32), dtype=float, device=device)})
    grads = [float(g) for g in mu_floor.grad.numpy()]
    if topo["p"]:
        grads += [float(g) for g in topo["mu_p"].grad.numpy()[: topo["p"]]]
    gradient = math.fsum(grads)
    final_x = states[-1][0].numpy().astype(np.float64)
    final_v = states[-1][1].numpy().astype(np.float64)
    _check_pairs_still_cover(final_x, dem.radii_np, pairs)
    tape.zero()
    return TapeRollout(
        objective=value, gradient=gradient, final_positions=final_x, final_velocities=final_v, deterministic=True, pairs=topo["p"]
    )


def _check_pairs_still_cover(positions: np.ndarray, radii: np.ndarray, pairs: np.ndarray) -> None:
    """Raise when a pair outside the candidate list overlaps at the end of the window (a missed contact)."""
    have = {(int(a), int(b)) for a, b in pairs}
    for a, b in candidate_pairs(positions, radii, 0.0):
        if (int(a), int(b)) not in have:
            raise InvalidCalibrationError("the window moved the heap beyond the candidate contact list: raise the skin")


# ------------------------------------------------------------------ the gradient arm


def run_gradient_arm(
    simulator: Any,
    *,
    theta_star: float,
    packing_seeds: Sequence[int],
    mu0: float = 0.55,
    bounds: tuple[float, float] = (0.1, 1.0),
    budget: int = 60,
    adam_lr: float = 0.02,
    loss_tolerance_deg: float = 0.1,
) -> ArmResult:
    """Adam on L(mu) = mean over seeds of (theta - theta*)^2 with the tape gradient of `simulator.theta_and_grad`.

    One iteration evaluates every packing seed with its adjoint pass (3 forward-equivalents per heap, FR-011-21), updates mu with Adam
    (beta1 0.9, beta2 0.999, eps 1e-8; Kingma and Ba 2015) clipped to `bounds`, and stops when L <= tolerance^2 or when another
    iteration would exceed `budget`.
    """
    seeds = list(packing_seeds)
    if not seeds:
        raise InvalidCalibrationError("at least one optimisation seed is needed")
    started = time.perf_counter()
    cost = 3 * len(seeds)
    lo, hi = float(bounds[0]), float(bounds[1])
    beta1, beta2, eps = 0.9, 0.999, 1.0e-8
    mu, m, v, t = float(mu0), 0.0, 0.0, 0
    path: list[float] = []
    gradients: list[float] = []
    evaluations: list[tuple[float, float]] = []
    thetas: dict[float, list[float]] = {}
    simulations = 0
    stop_reason = "budget"
    tolerance = loss_tolerance_deg**2
    while simulations + cost <= budget:
        values, slopes = [], []
        for s in seeds:
            theta, slope = simulator.theta_and_grad(mu, s)
            values.append(float(theta))
            slopes.append(float(slope))
        simulations += cost
        loss = float(np.mean([(x - theta_star) ** 2 for x in values]))
        grad = float(np.mean([2.0 * (x - theta_star) * g for x, g in zip(values, slopes, strict=True)]))
        path.append(mu)
        gradients.append(grad)
        evaluations.append((mu, loss))
        thetas[mu] = values
        if loss <= tolerance:
            stop_reason = "loss-tolerance"
            break
        t += 1
        m = beta1 * m + (1.0 - beta1) * grad
        v = beta2 * v + (1.0 - beta2) * grad * grad
        step = adam_lr * (m / (1.0 - beta1**t)) / (math.sqrt(v / (1.0 - beta2**t)) + eps)
        mu = min(max(mu - step, lo), hi)
    if not evaluations:
        raise InvalidCalibrationError(f"budget {budget} cannot pay one iteration ({cost} forward-equivalents)")
    best_mu, best_loss = min(evaluations, key=lambda e: e[1])
    return ArmResult(
        mu_hat=best_mu,
        best_loss=best_loss,
        simulations=simulations,
        wall_time_s=float(time.perf_counter() - started),
        stop_reason=stop_reason,
        path=path,
        evaluations=evaluations,
        gradients=gradients,
        thetas=thetas,
    )

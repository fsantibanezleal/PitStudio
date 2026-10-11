"""Hertz-Mindlin contact law of the Warp DEM (FR-005-01).

Normal force F_n = (4/3) E* sqrt(R*) delta^(3/2) with the damping F_d = -2 sqrt(5/6) beta sqrt(S_n m*) v_n, the
Mindlin tangential spring F_t = -S_t delta_t capped by the Coulomb limit mu_s F_n, and an elastic-plastic rolling
torque capped at mu_r R* F_n. Sources: LAMMPS `pair_style granular` (Hertz force, Mindlin stiffness, effective moduli)
and spec 005 FR-005-01 (damping form, caps). The rolling stiffness k_r = S_n R*^2 and the critical rolling damping are
this implementation's choices (spec 005 section 7: the elastic-plastic rolling model is UNVERIFIED).

The kernels run in float32; positions stay float64 in the integrator (see `step`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import warp as wp

wp.config.quiet = True

TWO_SQRT_5_6 = 2.0 * math.sqrt(5.0 / 6.0)


@dataclass(frozen=True)
class EffectiveProperties:
    """Effective contact properties of a pair (FR-005-01)."""

    e_star: float  # Pa
    g_star: float  # Pa
    r_star: float  # m
    m_star: float  # kg


def effective_properties(
    *,
    youngs_1: float,
    poisson_1: float,
    radius_1: float,
    mass_1: float,
    youngs_2: float,
    poisson_2: float,
    radius_2: float,
    mass_2: float,
) -> EffectiveProperties:
    """Combine two bodies; a wall passes `radius_2 = mass_2 = math.inf`."""
    g1 = youngs_1 / (2.0 * (1.0 + poisson_1))
    g2 = youngs_2 / (2.0 * (1.0 + poisson_2))
    return EffectiveProperties(
        e_star=1.0 / ((1.0 - poisson_1**2) / youngs_1 + (1.0 - poisson_2**2) / youngs_2),
        g_star=1.0 / ((2.0 - poisson_1) / g1 + (2.0 - poisson_2) / g2),
        r_star=1.0 / (1.0 / radius_1 + 1.0 / radius_2),
        m_star=1.0 / (1.0 / mass_1 + 1.0 / mass_2),
    )


def damping_beta(restitution: float) -> float:
    """beta = ln e / sqrt(ln^2 e + pi^2); 0 for e = 1."""
    if restitution >= 1.0:
        return 0.0
    ln_e = math.log(restitution)
    return ln_e / math.sqrt(ln_e * ln_e + math.pi * math.pi)


@wp.func
def hertz_normal(e_star: float, r_star: float, m_star: float, beta: float, delta: float, v_n: float):
    """(elastic force, damping force, normal stiffness S_n) of one contact; zeros without overlap."""
    if delta <= 0.0:
        return 0.0, 0.0, 0.0
    root = wp.sqrt(r_star * delta)
    s_n = 2.0 * e_star * root
    f_el = (4.0 / 3.0) * e_star * root * delta
    f_d = -2.0 * wp.sqrt(5.0 / 6.0) * beta * wp.sqrt(s_n * m_star) * v_n
    return f_el, f_d, s_n


@wp.func
def clamp_vector(v: wp.vec3, limit: float):
    """`v` scaled down to length `limit` when it is longer (scaled by its largest component: no underflow)."""
    big = wp.max(wp.max(wp.abs(v[0]), wp.abs(v[1])), wp.abs(v[2]))
    if big == 0.0:
        return v
    if limit <= 0.0:
        return wp.vec3(0.0, 0.0, 0.0)
    mag = big * wp.length(v / big)
    if mag > limit:
        return v * (limit / mag)
    return v


@wp.kernel
def _evaluate_contacts_kernel(
    delta_n: wp.array(dtype=float),
    v_n: wp.array(dtype=float),
    delta_t: wp.array(dtype=wp.vec3),
    rolling_angle: wp.array(dtype=wp.vec3),
    e_star: float,
    g_star: float,
    r_star: float,
    m_star: float,
    beta: float,
    mu_s: float,
    mu_r: float,
    fn_elastic: wp.array(dtype=float),
    fn_damping: wp.array(dtype=float),
    s_n_out: wp.array(dtype=float),
    s_t_out: wp.array(dtype=float),
    ft: wp.array(dtype=wp.vec3),
    torque: wp.array(dtype=wp.vec3),
):
    i = wp.tid()
    d = delta_n[i]
    f_el, f_d, s_n = hertz_normal(e_star, r_star, m_star, beta, d, v_n[i])
    fn_elastic[i] = f_el
    fn_damping[i] = f_d
    s_n_out[i] = s_n
    if d <= 0.0:
        s_t_out[i] = 0.0
        ft[i] = wp.vec3(0.0, 0.0, 0.0)
        torque[i] = wp.vec3(0.0, 0.0, 0.0)
        return
    s_t = 8.0 * g_star * wp.sqrt(r_star * d)
    s_t_out[i] = s_t
    fn_total = wp.max(f_el + f_d, 0.0)
    ft[i] = clamp_vector(-s_t * delta_t[i], mu_s * fn_total)
    k_r = s_n * r_star * r_star
    torque[i] = clamp_vector(-k_r * rolling_angle[i], mu_r * r_star * fn_total)


@dataclass(frozen=True)
class ContactForces:
    """Per-contact outputs of `evaluate_contacts` (numpy float64 arrays; the kernel computes in float32)."""

    fn_elastic: np.ndarray
    fn_damping: np.ndarray
    s_n: np.ndarray
    s_t: np.ndarray
    ft: np.ndarray
    torque_rolling: np.ndarray


def evaluate_contacts(
    props: EffectiveProperties,
    *,
    delta_n: np.ndarray,
    v_n: np.ndarray,
    delta_t: np.ndarray,
    rolling_angle: np.ndarray,
    restitution: float,
    friction_static: float,
    friction_rolling: float,
    device: str = "cpu",
) -> ContactForces:
    """Evaluate the contact law for N contacts in one kernel launch on `device`."""
    n = len(delta_n)
    arr = lambda a, dt: wp.array(np.ascontiguousarray(a), dtype=dt, device=device)  # noqa: E731
    out_f = [wp.zeros(n, dtype=float, device=device) for _ in range(4)]
    out_v = [wp.zeros(n, dtype=wp.vec3, device=device) for _ in range(2)]
    wp.launch(
        _evaluate_contacts_kernel,
        dim=n,
        inputs=[
            arr(delta_n, float),
            arr(v_n, float),
            arr(delta_t, wp.vec3),
            arr(rolling_angle, wp.vec3),
            props.e_star,
            props.g_star,
            props.r_star,
            props.m_star,
            damping_beta(restitution),
            friction_static,
            friction_rolling,
            *out_f,
            *out_v,
        ],
        device=device,
    )
    return ContactForces(*(a.numpy().astype(np.float64) for a in (*out_f, *out_v)))

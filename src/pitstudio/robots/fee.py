# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""Fundamental earthmoving equation (FEE) wedge reference (FR-014-17, FR-014-21).

The 2-D wedge of ``docs/theory/loading-and-terramechanics.md`` section 3, in NumPy-free float64 arithmetic:

    F(beta) = (rho g d^2 N_gamma + c d N_c + c_a d N_a + q d N_q) w

with the four factors of the theory document. The failure angle beta* minimises F over
(0, min(pi/2, pi - alpha - delta - phi)). F is flat at its minimum, so beta* is found by solving dF/dbeta = 0 on the
analytic derivative (bisection to machine precision), not by comparing F values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

G = 9.81  # m/s^2
RAKE_MIN = math.radians(5.0)
RAKE_MAX = math.radians(90.0)
ALPHA_FLOOR = 1e-9  # rad; cot(alpha) overflows below ~1e-308, and every real rake is clamped to >= 5 deg

__all__ = [
    "FeeSolution",
    "G",
    "beta_upper",
    "clamp_rake",
    "cutting_force",
    "fee_factors",
    "fee_force",
    "fill_weight",
    "solve_fee",
    "validate_wedge_inputs",
]


def _cot(x: float) -> float:
    return 1.0 / math.tan(x)


def beta_upper(alpha: float, delta: float, phi: float) -> float:
    """Upper end of the admissible failure-angle interval."""
    return min(math.pi / 2.0, math.pi - alpha - delta - phi)


def fee_factors(alpha: float, beta: float, delta: float, phi: float) -> tuple[float, float, float, float]:
    """(N_gamma, N_c, N_a, N_q) at a failure angle beta (rad)."""
    d_term = math.cos(alpha + delta) + math.sin(alpha + delta) * _cot(beta + phi)
    n_gamma = (_cot(alpha) + _cot(beta)) / (2.0 * d_term)
    n_c = (1.0 + _cot(beta) * _cot(beta + phi)) / d_term
    n_a = (1.0 - _cot(alpha) * _cot(beta + phi)) / d_term
    n_q = (_cot(alpha) + _cot(beta)) / d_term
    return n_gamma, n_c, n_a, n_q


def _need_finite_nonneg(name: str, value: float) -> None:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be a finite number >= 0, got {value!r}")


def validate_wedge_inputs(
    *, alpha: float, delta: float, phi: float, rho: float, c: float, c_a: float, q: float, d: float, w: float
) -> None:
    """Raise ValueError naming the first invalid input (FR-014-21)."""
    for name, value in (("rho", rho), ("c", c), ("c_a", c_a), ("q", q), ("d", d), ("w", w)):
        _need_finite_nonneg(name, value)
    for name, value in (("alpha", alpha), ("phi", phi), ("delta", delta)):
        if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite angle in rad, got {value!r}")
    if not 0.0 < alpha <= math.pi / 2.0:
        raise ValueError(f"alpha must be in (0, pi/2] rad, got {alpha!r}")
    if not 0.0 < phi < math.pi / 2.0:
        raise ValueError(f"phi must be in (0, pi/2) rad, got {phi!r}")
    if not 0.0 <= delta <= phi:
        raise ValueError(f"delta must be in [0, phi] rad with phi = {phi!r}, got {delta!r}")
    if alpha + delta + phi >= math.pi:
        raise ValueError(
            f"alpha + delta + phi must be below pi (D <= 0 for every admissible beta), got {alpha + delta + phi!r}"
        )


def fee_force(
    beta: float,
    *,
    alpha: float,
    delta: float,
    phi: float,
    rho: float,
    c: float,
    c_a: float,
    q: float,
    d: float,
    w: float,
    g: float = G,
) -> float:
    """F at a given failure angle beta (factor form), in N."""
    validate_wedge_inputs(alpha=alpha, delta=delta, phi=phi, rho=rho, c=c, c_a=c_a, q=q, d=d, w=w)
    alpha = max(alpha, ALPHA_FLOOR)
    ng, nc, na, nq = fee_factors(alpha, beta, delta, phi)
    return (rho * g * d * d * ng + c * d * nc + c_a * d * na + q * d * nq) * w


@dataclass(frozen=True)
class FeeSolution:
    beta: float
    n_gamma: float
    n_c: float
    n_a: float
    n_q: float
    force: float
    draft: float
    vertical: float


def _dforce(u: float, alpha: float, delta: float, phi: float, a_w: float, b_c: float, c_ca: float) -> float:
    """Numerator of dF/dbeta (N' D - N D'), the denominator D^2 being positive."""
    s = alpha + delta
    cot_a = _cot(alpha)
    cot_u = _cot(u)
    cot_up = _cot(u + phi)
    csc2_u = 1.0 + cot_u * cot_u
    csc2_up = 1.0 + cot_up * cot_up
    d_term = math.cos(s) + math.sin(s) * cot_up
    n_val = a_w * (cot_a + cot_u) + b_c * (1.0 + cot_u * cot_up) + c_ca * (1.0 - cot_a * cot_up)
    n_der = -a_w * csc2_u + b_c * (-csc2_u * cot_up - cot_u * csc2_up) + c_ca * cot_a * csc2_up
    d_der = -math.sin(s) * csc2_up
    return n_der * d_term - n_val * d_der


def _minimiser(alpha: float, delta: float, phi: float, a_w: float, b_c: float, c_ca: float, hi: float) -> float:
    """beta* in (0, hi): the root of dF/dbeta nearest to the grid minimum, polished by bisection."""

    def f_val(u: float) -> float:
        d_term = math.cos(alpha + delta) + math.sin(alpha + delta) * _cot(u + phi)
        n_val = (
            a_w * (_cot(alpha) + _cot(u))
            + b_c * (1.0 + _cot(u) * _cot(u + phi))
            + c_ca * (1.0 - _cot(alpha) * _cot(u + phi))
        )
        return n_val / d_term

    n = 400
    grid = [hi * (1e-6 + (1.0 - 2e-6) * i / n) for i in range(n + 1)]
    vals = [f_val(u) for u in grid]
    i_min = min(range(n + 1), key=vals.__getitem__)
    lo_i, hi_i = max(i_min - 1, 0), min(i_min + 1, n)
    lo, up = grid[lo_i], grid[hi_i]
    g_lo = _dforce(lo, alpha, delta, phi, a_w, b_c, c_ca)
    g_up = _dforce(up, alpha, delta, phi, a_w, b_c, c_ca)
    if g_lo < 0.0 <= g_up or g_lo <= 0.0 < g_up:
        for _ in range(200):
            mid = 0.5 * (lo + up)
            if mid <= lo or mid >= up:
                break
            if _dforce(mid, alpha, delta, phi, a_w, b_c, c_ca) < 0.0:
                lo = mid
            else:
                up = mid
        return 0.5 * (lo + up)
    # minimum on the grid boundary or flat: golden-section refinement of F itself
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    x1, x2 = lo, up
    c1 = x2 - ratio * (x2 - x1)
    c2 = x1 + ratio * (x2 - x1)
    for _ in range(200):
        if f_val(c1) < f_val(c2):
            x2 = c2
        else:
            x1 = c1
        c1 = x2 - ratio * (x2 - x1)
        c2 = x1 + ratio * (x2 - x1)
    return 0.5 * (x1 + x2)


def solve_fee(
    *,
    alpha: float,
    delta: float,
    phi: float,
    rho: float,
    c: float,
    c_a: float,
    q: float,
    d: float,
    w: float,
    g: float = G,
) -> FeeSolution:
    """Failure angle minimising F, the four factors there, F, the draft H and the vertical V."""
    validate_wedge_inputs(alpha=alpha, delta=delta, phi=phi, rho=rho, c=c, c_a=c_a, q=q, d=d, w=w)
    alpha = max(alpha, ALPHA_FLOOR)
    hi = beta_upper(alpha, delta, phi)
    a_w = 0.5 * rho * g * d * d + q * d  # coefficient of (cot a + cot beta)
    b_c = c * d
    c_ca = c_a * d
    if d == 0.0 or w == 0.0 or (a_w == 0.0 and b_c == 0.0 and c_ca == 0.0):
        beta = 0.5 * hi
        ng, nc, na, nq = fee_factors(alpha, beta, delta, phi)
        return FeeSolution(beta, ng, nc, na, nq, 0.0, 0.0, 0.0)
    beta = _minimiser(alpha, delta, phi, a_w, b_c, c_ca, hi)
    ng, nc, na, nq = fee_factors(alpha, beta, delta, phi)
    force = (rho * g * d * d * ng + c * d * nc + c_a * d * na + q * d * nq) * w
    return FeeSolution(
        beta=beta,
        n_gamma=ng,
        n_c=nc,
        n_a=na,
        n_q=nq,
        force=force,
        draft=force * math.sin(alpha + delta),
        vertical=force * math.cos(alpha + delta),
    )


def clamp_rake(alpha: float) -> float:
    """Rake angle clamped to [5 deg, 90 deg] (rad in, rad out)."""
    return min(max(alpha, RAKE_MIN), RAKE_MAX)


def cutting_force(
    *,
    depth: float,
    tip_velocity_x: float,
    rake: float,
    delta: float,
    phi: float,
    rho: float,
    c: float,
    c_a: float,
    q: float,
    w: float,
    g: float = G,
) -> tuple[float, float]:
    """(Fx, Fz) on the bucket lip, machine frame (x forward, z up), in N.

    Zero unless the tip is below the surface (depth > 0) and moves into the soil (tip_velocity_x > 0); otherwise the draft
    opposes the motion (Fx = -H) and a positive V pulls the tool into the ground (Fz = -V).
    """
    if not (depth > 0.0 and tip_velocity_x > 0.0):
        return (0.0, 0.0)
    sol = solve_fee(alpha=clamp_rake(rake), delta=delta, phi=phi, rho=rho, c=c, c_a=c_a, q=q, d=depth, w=w, g=g)
    return (-sol.draft, -sol.vertical)


def fill_weight(v_fill: float, rho: float, g: float = G) -> float:
    """Weight of the fill (N): rho * g * v_fill."""
    return rho * g * v_fill

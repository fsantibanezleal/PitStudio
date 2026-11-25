# ruff: noqa: E501
"""Shared oracles of the spec 014 reference-core tests (root environment: numpy and the standard library only).

This module holds no test. It is imported by `tests/{unit,metamorphic,property}/test_t_014_*.py` and is locked with the
first of them. Nothing here calls the code under test; every function is a direct transcription of an equation printed in
`docs/theory/loading-and-terramechanics.md` section 3 (the 2-D wedge of the fundamental earthmoving equation, FEE), of the
Kolmogorov distribution, or a hand-written geometric helper.

Contents
- `fee_factors_ref`, `fee_force_factor_form`: the four wedge factors and F(beta) in factor form (theory doc, section 3).
- `fee_force_wedge_equilibrium`: F(beta) from the two wedge equilibrium equations solved as a 2 x 2 linear system
  (theory doc, "Horizontal and vertical equilibrium of the wedge"); it shares no code path with the factor form.
- `fee_minimum_grid`: the minimum of F over beta by a dense grid plus golden-section refinement.
- `kolmogorov_sf`, `ks_statistic`, `ks_pvalue`: the one-sample Kolmogorov-Smirnov test (asymptotic series with the
  Stephens small-sample correction), because SciPy is not part of the root environment.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np

G = 9.81  # m/s^2, the value of every worked example of spec 014 (P-014-06)


def cot(x: float) -> float:
    return 1.0 / math.tan(x)


def beta_upper(alpha: float, delta: float, phi: float) -> float:
    """Upper end of the admissible failure-angle interval (FR-014-17): min(pi/2, pi - alpha - delta - phi)."""
    return min(math.pi / 2.0, math.pi - alpha - delta - phi)


def fee_factors_ref(alpha: float, beta: float, delta: float, phi: float) -> tuple[float, float, float, float]:
    """(N_gamma, N_c, N_a, N_q) of the theory doc, section 3 (angles in rad)."""
    d_term = math.cos(alpha + delta) + math.sin(alpha + delta) * cot(beta + phi)
    n_gamma = (cot(alpha) + cot(beta)) / (2.0 * d_term)
    n_c = (1.0 + cot(beta) * cot(beta + phi)) / d_term
    n_a = (1.0 - cot(alpha) * cot(beta + phi)) / d_term
    n_q = (cot(alpha) + cot(beta)) / d_term
    return n_gamma, n_c, n_a, n_q


def fee_force_factor_form(
    beta: float, *, alpha: float, delta: float, phi: float, rho: float, c: float, c_a: float, q: float, d: float,
    w: float, g: float = G,
) -> float:  # fmt: skip
    """F = (rho g d^2 N_gamma + c d N_c + c_a d N_a + q d N_q) w at a given beta."""
    ng, nc, na, nq = fee_factors_ref(alpha, beta, delta, phi)
    return (rho * g * d * d * ng + c * d * nc + c_a * d * na + q * d * nq) * w


def fee_force_wedge_equilibrium(
    beta: float, *, alpha: float, delta: float, phi: float, rho: float, c: float, c_a: float, q: float, d: float,
    w: float, g: float = G,
) -> float:  # fmt: skip
    """Blade force P (times the width) from the wedge equilibrium equations, solved directly as a 2 x 2 system.

    Per unit width (theory doc, "Derivation of the 2-D wedge factors"), unknowns P (blade force) and R (soil reaction):
        P sin(a+d) - R sin(b+phi) = c d cot b - c_a d cot a
        P cos(a+d) + R cos(b+phi) = W + c d + c_a d + q d (cot a + cot b),   W = 1/2 rho g d^2 (cot a + cot b)
    """
    weight = 0.5 * rho * g * d * d * (cot(alpha) + cot(beta))
    a_mat = np.array(
        [[math.sin(alpha + delta), -math.sin(beta + phi)], [math.cos(alpha + delta), math.cos(beta + phi)]], dtype=float
    )
    rhs = np.array(
        [c * d * cot(beta) - c_a * d * cot(alpha), weight + c * d + c_a * d + q * d * (cot(alpha) + cot(beta))],
        dtype=float,
    )
    p_blade, _reaction = np.linalg.solve(a_mat, rhs)
    return float(p_blade) * w


def golden_section_min(f: Callable[[float], float], lo: float, hi: float, tol: float = 1e-13) -> float:
    """Argument of the minimum of a unimodal f on [lo, hi] (golden-section search)."""
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    c = hi - ratio * (hi - lo)
    d = lo + ratio * (hi - lo)
    while hi - lo > tol:
        if f(c) < f(d):
            hi = d
        else:
            lo = c
        c = hi - ratio * (hi - lo)
        d = lo + ratio * (hi - lo)
    return 0.5 * (lo + hi)


def fee_minimum_grid(
    *, alpha: float, delta: float, phi: float, rho: float, c: float, c_a: float, q: float, d: float, w: float,
    g: float = G, n: int = 4001,
) -> tuple[float, float]:  # fmt: skip
    """(beta*, F*) by a dense grid over the open interval (0, beta_upper) and a golden-section refinement."""
    hi = beta_upper(alpha, delta, phi)
    kw = {"alpha": alpha, "delta": delta, "phi": phi, "rho": rho, "c": c, "c_a": c_a, "q": q, "d": d, "w": w, "g": g}
    grid = np.linspace(hi * 1e-6, hi * (1.0 - 1e-6), n)
    vals = np.array([fee_force_factor_form(float(b), **kw) for b in grid])
    i = int(np.argmin(vals))
    lo_b = float(grid[max(i - 1, 0)])
    hi_b = float(grid[min(i + 1, n - 1)])
    beta = golden_section_min(lambda b: fee_force_factor_form(b, **kw), lo_b, hi_b)
    return beta, fee_force_factor_form(beta, **kw)


# ---------------------------------------------------------------------------------------------- Kolmogorov-Smirnov
def kolmogorov_sf(lam: float) -> float:
    """Survival function Q_KS(lam) = 2 sum_{k>=1} (-1)^(k-1) exp(-2 k^2 lam^2) of the Kolmogorov distribution."""
    if lam <= 0.0:
        return 1.0
    total = 0.0
    for k in range(1, 101):
        term = 2.0 * (-1.0) ** (k - 1) * math.exp(-2.0 * k * k * lam * lam)
        total += term
        if abs(term) < 1e-16:
            break
    return min(max(total, 0.0), 1.0)


def ks_statistic(sample: Sequence[float], cdf: Callable[[float], float]) -> float:
    """D_n = sup |F_n(x) - F(x)| of the empirical CDF against the target CDF."""
    xs = np.sort(np.asarray(sample, dtype=float))
    n = len(xs)
    f = np.array([cdf(float(x)) for x in xs])
    d_plus = np.max(np.arange(1, n + 1) / n - f)
    d_minus = np.max(f - np.arange(0, n) / n)
    return float(max(d_plus, d_minus))


def ks_pvalue(sample: Sequence[float], cdf: Callable[[float], float]) -> float:
    """Asymptotic p-value with the Stephens (1970) correction lam = (sqrt(n) + 0.12 + 0.11 / sqrt(n)) D_n."""
    n = len(sample)
    d_n = ks_statistic(sample, cdf)
    return kolmogorov_sf((math.sqrt(n) + 0.12 + 0.11 / math.sqrt(n)) * d_n)


def uniform_cdf(lo: float, hi: float) -> Callable[[float], float]:
    return lambda x: min(max((x - lo) / (hi - lo), 0.0), 1.0)

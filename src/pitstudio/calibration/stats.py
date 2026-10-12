"""Small statistics helpers of the calibration protocol (numpy and the standard library only).

`student_t_quantile` inverts the Student t distribution function, computed through the regularised incomplete beta function
(Lentz continued fraction, Numerical Recipes section 6.4), to full double precision; it replaces a table so that any number
of interval seeds works (FR-011-22 uses t at R - 1 degrees of freedom). `wilson_interval` is the Wilson score interval of a
binomial proportion (FR-011-24).
"""

from __future__ import annotations

import math

_TINY = 1e-300


def _betacf(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > _TINY else _TINY)
    h = d
    for m in range(1, 500):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > _TINY else _TINY
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > _TINY else _TINY
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-16:
            break
    return h


def regularised_beta(a: float, b: float, x: float) -> float:
    """I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_cdf(t: float, df: float) -> float:
    """P(T <= t) for a Student t variable with `df` degrees of freedom."""
    tail = 0.5 * regularised_beta(df / 2.0, 0.5, df / (df + t * t))
    return 1.0 - tail if t > 0 else tail


def student_t_quantile(p: float, df: float) -> float:
    """The t with P(T <= t) = p (bisection to 1e-13; p in (0, 1), df >= 1)."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"p must be inside (0, 1), got {p}")
    if df < 1:
        raise ValueError(f"df must be at least 1, got {df}")
    if p == 0.5:
        return 0.0
    if p < 0.5:
        return -student_t_quantile(1.0 - p, df)
    lo, hi = 0.0, 1.0
    while student_t_cdf(hi, df) < p:
        hi *= 2.0
        if hi > 1e12:
            break
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if student_t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-13 * max(1.0, hi):
            break
    return 0.5 * (lo + hi)


def wilson_interval(successes: int, n: int, *, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score interval of a binomial proportion (95 % with the default z)."""
    if n < 1 or not 0 <= successes <= n:
        raise ValueError(f"need 0 <= successes <= n and n >= 1, got {successes} of {n}")
    phat = successes / n
    denom = 1.0 + z * z / n
    centre = (phat + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(phat * (1.0 - phat) / n + z * z / (4.0 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)

"""Candidate-set Monte-Carlo probability of failure and its Wilson interval (FR-010-03, FR-010-08), numpy only.

Sampling: the generator is ``numpy.random.Generator(PCG64(SeedSequence(seed)))``; every distribution of the list
consumes
``n`` uniform draws ``rng.random(n)`` in list order, so equal seeds give equal samples and a longer run extends a
shorter
one (common random numbers). A uniform is ``lower + (upper - lower) u``; a normal truncated to [lo, hi] is
``mean + sd Phi^-1(Phi(a) + u (Phi(b) - Phi(a)))`` with a, b the standardised bounds (inverse CDF, never rejection;
when the
interval lies in the upper tail the survival function is used so no precision is lost); a lognormal is given by its
arithmetic mean and coefficient of variation cv: sigma^2 = ln(1 + cv^2), mu = ln(mean) - sigma^2 / 2.

PoF: the candidate set is the K lowest-F circles of the mean-parameter Bishop search. Each sample takes the minimum
factor
over the candidates and fails when it is < 1. A sample for which Bishop is invalid on every candidate (no factor at
all) is
counted as a failure: it cannot be shown to be stable.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np

from pitstudio.slope import lem
from pitstudio.slope import section as _section

MAX_SAMPLES = 1_000_000
Z95 = 1.96
CANDIDATE_SET = "lowest-F circles of the mean-parameter Bishop search"
_TINY = 2.0**-54


class InvalidSamplingError(ValueError):
    """The sample count, the candidate count, the seed or a distribution is out of range (FR-010-08)."""


# ----------------------------------------------------------------------------------------------------------------------
# normal distribution helpers


def _norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


_PPND_A = (
    3.3871328727963666080,
    1.3314166789178437745e2,
    1.9715909503065514427e3,
    1.3731693765509461125e4,
    4.5921953931549871457e4,
    6.7265770927008700853e4,
    3.3430575583588128105e4,
    2.5090809287301226727e3,
)
_PPND_B = (
    1.0,
    4.2313330701600911252e1,
    6.8718700749205790830e2,
    5.3941960214247511077e3,
    2.1213794301586595867e4,
    3.9307895800092710610e4,
    2.8729085735721942674e4,
    5.2264952788528545610e3,
)
_PPND_C = (
    1.42343711074968357734,
    4.63033784615654529590,
    5.76949722146069140550,
    3.64784832476320460504,
    1.27045825245236838258,
    2.41780725177450611770e-1,
    2.27238449892691845833e-2,
    7.74545014278341407640e-4,
)
_PPND_D = (
    1.0,
    2.05319162663775882187,
    1.67638483018380384940,
    6.89767334985100004550e-1,
    1.48103976427480074590e-1,
    1.51986665636164571966e-2,
    5.47593808499534494600e-4,
    1.05075007164441684324e-9,
)
_PPND_E = (
    6.65790464350110377720,
    5.46378491116411436990,
    1.78482653991729133580,
    2.96560571828504891230e-1,
    2.65321895265761230930e-2,
    1.24266094738807843860e-3,
    2.71155556874348757815e-5,
    2.01033439929228813265e-7,
)
_PPND_F = (
    1.0,
    5.99832206555887937690e-1,
    1.36929880922735805310e-1,
    1.48753612908506148525e-2,
    7.86869131145613259100e-4,
    1.84631831751005468180e-5,
    1.42151175831644588870e-7,
    2.04426310338993978564e-15,
)


def _poly(coefficients: tuple[float, ...], x: np.ndarray) -> np.ndarray:
    out = np.zeros_like(x)
    for c in reversed(coefficients):
        out = out * x + c
    return out


def norm_ppf(p: np.ndarray) -> np.ndarray:
    """Inverse standard normal CDF, Wichura's AS 241 (PPND16, relative accuracy about 1e-16), vectorised."""
    p = np.asarray(p, dtype=float)
    q = p - 0.5
    out = np.empty_like(p)
    centre = np.abs(q) <= 0.425
    r = 0.180625 - q[centre] ** 2
    out[centre] = q[centre] * _poly(_PPND_A, r) / _poly(_PPND_B, r)
    tail = ~centre
    pt = np.where(q[tail] < 0.0, p[tail], 1.0 - p[tail])
    r = np.sqrt(-np.log(pt))
    near = r <= 5.0
    z = np.empty_like(r)
    r1 = r[near] - 1.6
    z[near] = _poly(_PPND_C, r1) / _poly(_PPND_D, r1)
    r2 = r[~near] - 5.0
    z[~near] = _poly(_PPND_E, r2) / _poly(_PPND_F, r2)
    out[tail] = np.where(q[tail] < 0.0, -z, z)
    return out


# ----------------------------------------------------------------------------------------------------------------------
# guards


def _is_int(v: Any) -> bool:
    return isinstance(v, int | np.integer) and not isinstance(v, bool)


def _check_n(n: Any) -> int:
    if not _is_int(n) or not 1 <= int(n) <= MAX_SAMPLES:
        raise InvalidSamplingError(f"sample count must be an integer in [1, {MAX_SAMPLES}], got {n!r}")
    return int(n)


def _check_seed(seed: Any) -> int:
    if not _is_int(seed) or not 0 <= int(seed) < 2**64:
        raise InvalidSamplingError(f"seed must be an integer in [0, 2**64), got {seed!r}")
    return int(seed)


def _num(d: dict[str, Any], key: str, what: str) -> float:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise InvalidSamplingError(f"{what}: {key} must be a finite number, got {v!r}")
    return float(v)


def _check_distribution(d: Any) -> None:
    if not isinstance(d, dict):
        raise InvalidSamplingError("a distribution must be an object")
    kind = d.get("distribution")
    if kind == "normal":
        mean, sd = _num(d, "mean", "normal"), _num(d, "sd", "normal")
        if not sd > 0.0:
            raise InvalidSamplingError(f"normal: sd must be > 0, got {sd!r}")
        lo = _num(d, "truncate_lower", "normal") if "truncate_lower" in d else -math.inf
        hi = _num(d, "truncate_upper", "normal") if "truncate_upper" in d else math.inf
        if not lo < hi:
            raise InvalidSamplingError(f"normal: the truncation interval [{lo}, {hi}] is empty")
        a, b = (lo - mean) / sd, (hi - mean) / sd
        if not (_norm_cdf(b) - _norm_cdf(a) > 0.0 or _norm_cdf(-a) - _norm_cdf(-b) > 0.0):
            raise InvalidSamplingError("normal: the truncation interval has no probability mass")
    elif kind == "lognormal":
        mean, cv = _num(d, "mean", "lognormal"), _num(d, "cv", "lognormal")
        if not mean > 0.0 or not cv > 0.0:
            raise InvalidSamplingError(f"lognormal: mean and cv must be > 0, got {mean!r} and {cv!r}")
    elif kind == "uniform":
        lo, hi = _num(d, "lower", "uniform"), _num(d, "upper", "uniform")
        if not lo < hi:
            raise InvalidSamplingError(f"uniform: lower {lo} must be below upper {hi}")
    else:
        raise InvalidSamplingError(f"unknown distribution {kind!r}")
    if not isinstance(d.get("parameter"), str):
        raise InvalidSamplingError("a distribution names its parameter")


def sample_key(d: dict[str, Any]) -> str:
    """Key of a distribution in the samples dict: ``<material_id>.<parameter>`` or ``pore_pressure_ratio``."""
    material = d.get("material_id")
    return d["parameter"] if material is None else f"{material}.{d['parameter']}"


# ----------------------------------------------------------------------------------------------------------------------
# Wilson interval and sampling


def wilson_interval(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval of k successes in n trials (Wilson 1927), clamped to [0, 1]."""
    p = k / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    denom = 1 + z * z / n
    return max(0.0, (centre - half) / denom), min(1.0, (centre + half) / denom)


def _draw(d: dict[str, Any], u: np.ndarray) -> np.ndarray:
    kind = d["distribution"]
    if kind == "uniform":
        return float(d["lower"]) + (float(d["upper"]) - float(d["lower"])) * u
    u = np.clip(u, _TINY, 1.0 - _TINY)
    if kind == "lognormal":
        sigma2 = math.log1p(float(d["cv"]) ** 2)
        mu = math.log(float(d["mean"])) - sigma2 / 2.0
        return np.exp(mu + math.sqrt(sigma2) * norm_ppf(u))
    mean, sd = float(d["mean"]), float(d["sd"])
    lo = float(d["truncate_lower"]) if "truncate_lower" in d else -math.inf
    hi = float(d["truncate_upper"]) if "truncate_upper" in d else math.inf
    a, b = (lo - mean) / sd, (hi - mean) / sd
    if a >= 0.0:  # upper tail: work with the survival function Phi(-x)
        sa, sb = _norm_cdf(-a), _norm_cdf(-b)
        q = np.clip(sa - u * (sa - sb), sb if sb > 0.0 else 5e-324, sa)
        x = mean - sd * norm_ppf(q)
    else:
        pa, pb = _norm_cdf(a), _norm_cdf(b)
        x = mean + sd * norm_ppf(
            np.clip(pa + u * (pb - pa), pa if pa > 0.0 else 5e-324, pb if pb < 1.0 else 1.0 - _TINY)
        )
    return np.clip(x, lo, hi)


def draw_samples(distributions: list[dict[str, Any]], n: int, seed: int) -> dict[str, np.ndarray]:
    """One float64 array of ``n`` values per distribution, from the seeded PCG64 stream (see the module docstring)."""
    n = _check_n(n)
    seed = _check_seed(seed)
    for d in distributions:
        _check_distribution(d)
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))
    return {sample_key(d): _draw(d, rng.random(n)) for d in distributions}


# ----------------------------------------------------------------------------------------------------------------------
# the PoF


def _bishop_samples(
    prep: _section.Section, circle: lem.Circle, samples: dict[str, np.ndarray], n_slices: int, n_samples: int
) -> np.ndarray:
    """Bishop's factor of one circle for every sample (nan where the circle is invalid for that sample)."""
    arrays = lem._circle_arrays(prep, [circle])
    geo = lem._geometry(prep, arrays, n_slices)
    if not bool(geo.ok[0]):
        return np.full(n_samples, np.nan)
    table = lem._param_table(prep)
    for i, m in enumerate(prep.materials):
        for param, name in (
            ("cohesion_kpa", "c"),
            ("friction_angle_deg", "phi"),
            ("gsi", "gsi"),
            ("m_i", "m_i"),
            ("sigma_ci_mpa", "sigma_ci"),
            ("disturbance_d", "d"),
            ("unit_weight_kn_per_m3", "gamma"),
        ):
            key = f"{m.id}.{param}"
            if key in samples:
                if name not in table or table[name].shape[1] == 1:
                    table[name] = np.broadcast_to(table[name], (table[name].shape[0], n_samples)).copy()
                table[name][i] = samples[key]
    for name, arr in table.items():
        if arr.shape[1] == 1 and n_samples > 1:
            table[name] = np.broadcast_to(arr, (arr.shape[0], n_samples))
    ru = np.asarray(samples.get("pore_pressure_ratio", np.full(n_samples, prep.pore_pressure_ratio)), dtype=float)
    w = lem._weights(geo, table["gamma"])
    hb_layers = np.asarray([m.hoek_brown for m in prep.materials])
    ib = np.broadcast_to(geo.ib, (n_samples, n_slices))
    mix = lem._Mix.build(table, hb_layers, ib)
    f, _, status = lem._bishop_core(w, geo.sin, geo.cos, geo.tan, geo.b, ru, mix, 1e-9, 100)
    return np.where(status == lem._OK, f, np.nan)


def candidate_circles(prep: _section.Section, k: int) -> tuple[list[lem.Circle], list[lem.Circle]]:
    """The ``k`` lowest-F circles of the mean-parameter Bishop search, and the whole grid (document frame)."""
    grid = lem.circle_grid(prep)
    f, _, status = lem._bishop_batch(prep, lem._grid_arrays(prep), prep.slices, 1e-9, 100)
    valid = np.flatnonzero(status == lem._OK)
    if k > valid.size:
        raise InvalidSamplingError(f"candidates {k} exceed the {valid.size} valid circles of the search")
    chosen = valid[np.argsort(f[valid], kind="stable")[:k]]
    return [grid[int(i)] for i in chosen], grid


def _minimum_over(
    prep: _section.Section,
    circles: list[lem.Circle],
    samples: dict[str, np.ndarray],
    n: int,
    factor_of: Callable[[dict[str, np.ndarray], lem.Circle], np.ndarray] | None,
) -> np.ndarray:
    evaluate = factor_of if factor_of is not None else (lambda s, c: _bishop_samples(prep, c, s, prep.slices, n))
    minimum = np.full(n, np.inf)
    for circle in circles:
        values = np.asarray(evaluate(samples, circle), dtype=float)
        minimum = np.minimum(minimum, np.where(np.isnan(values), np.inf, values))
    return minimum


def minimum_factors(prep: _section.Section, samples: dict[str, np.ndarray], n: int, k: int) -> np.ndarray:
    """Per-sample minimum Bishop factor over the ``k`` candidate circles (inf where no candidate is valid)."""
    circles, _ = candidate_circles(prep, k)
    return _minimum_over(prep, circles, samples, n, None)


def probability_of_failure(
    section: Any,
    *,
    n: int | None = None,
    candidates: int | None = None,
    seed: int | None = None,
    factor_of: Callable[[dict[str, np.ndarray], lem.Circle], np.ndarray] | None = None,
) -> dict[str, Any]:
    """Candidate-set PoF of a section (FR-010-03); the result has the shape of
    ``slope-results.schema.json#/$defs/pof_result``.

    ``n``, ``candidates`` and ``seed`` default to ``analysis.pof`` of the section. ``factor_of(samples, circle)``
    returns the
    factor of every sample on one candidate circle (a test seam; the default is Bishop's factor with the sampled
    parameters). Raises ``InvalidSamplingError`` before drawing and before any factor is computed."""
    prep = _section.parse_section(section) if not isinstance(section, _section.Section) else section
    settings = prep.pof or {}
    n = _check_n(settings.get("samples") if n is None else n)
    seed = _check_seed(settings.get("seed") if seed is None else seed)
    k_raw: Any = settings.get("candidates") if candidates is None else candidates
    if not _is_int(k_raw) or int(k_raw) < 1:
        raise InvalidSamplingError(f"candidates must be an integer >= 1, got {k_raw!r}")
    k = int(k_raw)
    distributions = list(settings.get("distributions", []))
    for d in distributions:
        _check_distribution(d)
    chosen, _ = candidate_circles(prep, k)
    samples = draw_samples(distributions, n, seed)
    minimum = _minimum_over(prep, chosen, samples, n, factor_of)
    failures = int(np.sum((minimum < 1.0) | np.isinf(minimum)))
    lower, upper = wilson_interval(failures, n)
    return {
        "method": "bishop",
        "candidate_set": CANDIDATE_SET,
        "samples": n,
        "candidates": k,
        "failures": failures,
        "pof": failures / n,
        "wilson_95": {"lower": lower, "upper": upper, "z": Z95},
        "seed": seed,
    }

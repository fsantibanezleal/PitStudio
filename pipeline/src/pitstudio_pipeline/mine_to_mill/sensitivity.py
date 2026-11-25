"""Variance-based (Sobol) sensitivity indices of the D2 chain over the sweep box (spec 017, FR-017-02).

First-order indices use the Saltelli (2010) estimator and total indices the Jansen (1999) estimator, on the usual
A, B and AB_i sample matrices: A and B are the two halves of one scrambled Sobol sequence of dimension 2 d, AB_i is A with
column i taken from B. With V = Var(f):

    S_i  = mean( (f(B) - m) (f(AB_i) - f(A)) ) / V    (Saltelli et al., Comput. Phys. Commun. 181, 2010, eq. (b))
    S_Ti = mean( (f(A) - f(AB_i))^2 ) / (2 V)         (Jansen, Comput. Phys. Commun. 117, 1999)

V and the centre m are the sample variance and mean of f over A and B together. The cost is N (d + 2) evaluations for N = `n_base`. A percentile
bootstrap over the N base rows gives the optional intervals. The estimator is checked against closed forms (a linear
function and the Ishigami function) in tests/unit/test_t_017_011_sobol_indices.py.
"""
# ruff: noqa: E501

from __future__ import annotations

import math
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
from scipy.stats import qmc

LEVEL = 0.95


@dataclass(frozen=True)
class SobolResult:
    """Indices per input (rows) and output (columns)."""

    names: tuple[str, ...]
    first_order: np.ndarray
    total: np.ndarray
    first_order_ci: np.ndarray | None
    total_ci: np.ndarray | None
    variance: np.ndarray
    n_evaluations: int
    n_base: int
    seed: int


def _bounds(bounds: Mapping[str, tuple[float, float]]) -> tuple[tuple[str, ...], np.ndarray, np.ndarray]:
    if not isinstance(bounds, Mapping) or not bounds:
        raise ValueError("bounds must be a non-empty mapping of input name to (low, high)")
    lows, highs = [], []
    for name, pair in bounds.items():
        if not isinstance(pair, tuple | list) or len(pair) != 2:
            raise ValueError(f"bounds[{name!r}] must be a (low, high) pair")
        lo, hi = pair
        if not (math.isfinite(lo) and math.isfinite(hi)) or lo > hi:
            raise ValueError(f"bounds[{name!r}] must be finite with low <= high, got {pair!r}")
        lows.append(float(lo))
        highs.append(float(hi))
    return tuple(bounds), np.array(lows), np.array(highs)


def _evaluate(func: Callable[[np.ndarray], np.ndarray], x: np.ndarray) -> np.ndarray:
    y = np.asarray(func(x), dtype=np.float64)
    if y.ndim == 1:
        y = y[:, None]
    if y.ndim != 2 or y.shape[0] != x.shape[0]:
        raise ValueError(
            f"func must return an array of shape ({x.shape[0]},) or ({x.shape[0]}, k), got shape {y.shape}"
        )
    if not np.all(np.isfinite(y)):
        raise ValueError("func returned a value that is not finite")
    return y


def _indices(fa: np.ndarray, fb: np.ndarray, fab: np.ndarray, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """First-order and total indices (d, k) from f(A), f(B) (N, k) and f(AB_i) (d, N, k) over the base rows `rows`."""
    a, b, ab = fa[rows], fb[rows], fab[:, rows]
    variance = np.concatenate([a, b]).var(axis=0, ddof=1)
    if np.any(variance <= 0.0):
        raise ValueError("the output has zero variance over the box: the indices are undefined")
    centre = np.concatenate([a, b]).mean(axis=0)  # centred outputs make the estimator exact under f -> c f + d
    first = np.mean((b - centre)[None] * (ab - a[None]), axis=1) / variance
    total = np.mean((a[None] - ab) ** 2, axis=1) / (2.0 * variance)
    return first, total


def sobol_indices(
    func: Callable[[np.ndarray], np.ndarray],
    bounds: Mapping[str, tuple[float, float]],
    *,
    n_base: int,
    seed: int,
    n_bootstrap: int = 0,
) -> SobolResult:
    """Sobol first-order and total indices of `func` over the box `bounds` (see the module docstring)."""
    names, lo, hi = _bounds(bounds)
    if isinstance(n_base, bool) or not isinstance(n_base, int | np.integer) or n_base < 2:
        raise ValueError(f"n_base must be an integer of at least 2, got {n_base!r}")
    if isinstance(seed, bool) or not isinstance(seed, int | np.integer) or not 0 <= seed < 2**63:
        raise ValueError(f"seed must be an integer in [0, 2^63), got {seed!r}")
    if isinstance(n_bootstrap, bool) or not isinstance(n_bootstrap, int | np.integer) or n_bootstrap < 0:
        raise ValueError(f"n_bootstrap must be a non-negative integer, got {n_bootstrap!r}")
    d = len(names)
    engine = qmc.Sobol(d=2 * d, scramble=True, seed=np.random.default_rng(np.random.SeedSequence([int(seed), 17])))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # a count that is not a power of 2 loses balance, not coverage
        unit = engine.random(int(n_base))
    a, b = lo + unit[:, :d] * (hi - lo), lo + unit[:, d:] * (hi - lo)
    fa, fb = _evaluate(func, a), _evaluate(func, b)
    fab = np.empty((d, int(n_base), fa.shape[1]))
    for i in range(d):
        ab = a.copy()
        ab[:, i] = b[:, i]
        fab[i] = _evaluate(func, ab)
    every = np.arange(int(n_base))
    first, total = _indices(fa, fb, fab, every)
    variance = np.concatenate([fa, fb]).var(axis=0, ddof=1)
    first_ci = total_ci = None
    if n_bootstrap:
        rng = np.random.default_rng(np.random.SeedSequence([int(seed), 23]))
        draws = [_indices(fa, fb, fab, rng.integers(0, int(n_base), int(n_base))) for _ in range(int(n_bootstrap))]
        q = [100 * (1 - LEVEL) / 2, 100 * (1 + LEVEL) / 2]
        first_ci = np.moveaxis(np.percentile(np.stack([x[0] for x in draws]), q, axis=0), 0, -1)
        total_ci = np.moveaxis(np.percentile(np.stack([x[1] for x in draws]), q, axis=0), 0, -1)
    return SobolResult(
        names=names,
        first_order=first,
        total=total,
        first_order_ci=first_ci,
        total_ci=total_ci,
        variance=variance,
        n_evaluations=int(n_base) * (d + 2),
        n_base=int(n_base),
        seed=int(seed),
    )

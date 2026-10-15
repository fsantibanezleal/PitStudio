"""Inverse-velocity and Bayesian time-to-failure baselines (FR-010-19, FR-010-20), numpy only.

Both fit y = 1 / v against time on the same points: the last 25 % of the unmasked samples of the shared window (at least
10). Inverse velocity (Fukuzono 1985; Rose and Hungr 2007) takes the root of the ordinary least-squares line when its
slope
is negative. The Bayesian baseline forms the conjugate Gaussian posterior of (b0, b1) in standardised coordinates with
the
prior N(0, 10^2 I) and sigma^2 from the least-squares residuals, draws ``draws`` posterior samples (Cholesky of the
posterior covariance, so the draws depend continuously on the data) and reports the median and the 10 % and 90 %
quantiles
of the root over the draws with a negative slope. A forecast that never crosses zero is "no failure predicted" and is
scored
at the horizon cap t_c + 1,024 delta.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from pitstudio.slope.errors import InvalidWindowError
from pitstudio.slope.preprocess import Window

CAP_STEPS = 1024
LAST_FRACTION = 0.25
MIN_POINTS = 10
PRIOR_SD = 10.0
SIGMA2_FLOOR = 1e-12  # in standardised units: keeps the update regular for an exactly linear inverse velocity


@dataclass(frozen=True)
class Forecast:
    """A time-to-failure forecast; ``scored_at_cap`` is True exactly for "no failure predicted"."""

    outcome: str
    t_hat_f: float
    scored_at_cap: bool
    q10: float | None = None
    q90: float | None = None


def _points(t: Any, y: Any, last_fraction: float, min_points: int) -> tuple[np.ndarray, np.ndarray]:
    tt, yy = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    ok = np.isfinite(yy)
    tt, yy = tt[ok], yy[ok]
    if tt.size < min_points:
        raise InvalidWindowError(f"only {tt.size} unmasked samples, at least {min_points} are needed")
    m = min(tt.size, max(min_points, math.ceil(last_fraction * tt.size)))
    return tt[-m:], yy[-m:]


def _ols(tt: np.ndarray, yy: np.ndarray) -> tuple[float, float, float]:
    """(intercept at the mean time, slope, mean time) of the least-squares line, in the centred form."""
    t_bar, y_bar = float(tt.mean()), float(yy.mean())
    dt = tt - t_bar
    sxx = float(dt @ dt)
    slope = float(dt @ (yy - y_bar)) / sxx
    return y_bar, slope, t_bar


def inverse_velocity_ttf(
    t: Any, y: Any, *, last_fraction: float = LAST_FRACTION, min_points: int = MIN_POINTS
) -> float | None:
    """Root of the OLS line of y on t over the last ``last_fraction`` of the unmasked samples, or None (slope >= 0)."""
    tt, yy = _points(t, y, last_fraction, min_points)
    y_bar, slope, t_bar = _ols(tt, yy)
    return t_bar - y_bar / slope if slope < 0.0 else None


def _cap(window: Window) -> float:
    return float(window.t[-1] + CAP_STEPS * window.delta)


def inverse_velocity(window: Window) -> Forecast:
    """The inverse-velocity forecast of a pre-processed window."""
    root = inverse_velocity_ttf(window.t, window.y)
    if root is None:
        return Forecast("no failure predicted", _cap(window), True)
    return Forecast("predicted", float(root), False)


def bayes_posterior(
    t: Any, y: Any, sigma2: float, prior_variance: float = PRIOR_SD**2
) -> tuple[np.ndarray, np.ndarray]:
    """Posterior mean and covariance of (b0, b1) for y = b0 + b1 t + noise (variance ``sigma2``), prior N(0, v I)."""
    tt, yy = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    x = np.column_stack([np.ones(tt.size), tt])
    precision = np.eye(2) / prior_variance + x.T @ x / sigma2
    cov = np.linalg.inv(precision)
    mean = cov @ (x.T @ yy / sigma2)
    return mean, cov


def bayesian_ttf(window: Window, *, seed: int = 0, draws: int = 4000) -> Forecast:
    """The Bayesian TTF forecast: median and 10 % / 90 % quantiles of -b0 / b1 over the draws with b1 < 0."""
    tt, yy = _points(window.t, window.y, LAST_FRACTION, MIN_POINTS)
    cap = _cap(window)
    t_mu, t_sd = float(tt.mean()), float(tt.std())
    y_mu, y_sd = float(yy.mean()), float(yy.std())
    if not (t_sd > 0.0 and y_sd > 0.0):
        return Forecast("no failure predicted", cap, True)
    ts, ys = (tt - t_mu) / t_sd, (yy - y_mu) / y_sd
    x = np.column_stack([np.ones(ts.size), ts])
    beta, *_ = np.linalg.lstsq(x, ys, rcond=None)
    resid = ys - x @ beta
    sigma2 = max(float(resid @ resid) / max(ts.size - 2, 1), SIGMA2_FLOOR)
    mean, cov = bayes_posterior(ts, ys, sigma2, PRIOR_SD**2)
    chol = np.linalg.cholesky((cov + cov.T) / 2.0)
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))
    sample = mean[None, :] + rng.standard_normal((draws, 2)) @ chol.T
    b1 = y_sd * sample[:, 1] / t_sd  # slope in original units
    b0 = y_mu + y_sd * sample[:, 0] - b1 * t_mu
    falling = b1 < 0.0
    if int(falling.sum()) * 2 < draws:
        return Forecast("no failure predicted", cap, True)
    roots = -b0[falling] / b1[falling]
    q10, median, q90 = (float(v) for v in np.percentile(roots, [10.0, 50.0, 90.0]))
    return Forecast("predicted", median, False, q10, q90)

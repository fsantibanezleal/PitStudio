"""Independent textbook references for the C1 forecasting tests of spec 010 (numpy and the stdlib only).

An ORACLE module, never importing the code under test. Sources written out in the formulas:
- Voight (1988) material-failure law d2(Omega)/dt2 = A (dOmega/dt)^alpha, terminal stage integrated in closed form:
  v(t) = [(alpha - 1) A (t_f - t)]^(-1/(alpha - 1)); Omega(t) - Omega(t_on) = C [(t_f - t_on)^p - (t_f - t)^p] / p with
  C = [(alpha - 1) A]^(-1/(alpha - 1)), p = (alpha - 2) / (alpha - 1); for alpha = 2: (1/A) ln((t_f - t_on) / (t_f -
  t)).
  (docs/methods/m14-slope-forecasting.md; Fukuzono 1985, Rose and Hungr 2007 for inverse velocity.)
- Shared preprocessor of FR-010-18: linear resampling to L = 512 points, centred 9-point least-squares velocity
  v_k = sum_j j Omega_k+j / (60 delta) (sum of j^2 over -4..4 is 60), y = 1/v where v > 0.
- Inverse velocity: ordinary least squares of y on t over the last 25 % of the unmasked samples (at least 10).
- Conjugate Bayesian linear regression (Bishop, Pattern Recognition and Machine Learning, 3.3):
  Sigma_N = (Sigma_0^-1 + X'X / s2)^-1, mu_N = Sigma_N (Sigma_0^-1 mu_0 + X'y / s2).
- Robust noise estimate: sigma = 1.4826 MAD(second differences) / sqrt(6) (the variance of a second difference of white
  noise is 6 sigma^2).
- Percentile bootstrap (Efron 1979): numpy percentiles of the resampled statistic.
"""

from __future__ import annotations

import math

import numpy as np

L = 512
WINDOW = 9
CAP_FACTOR = 1024


# ----------------------------------------------------------------------------------------------------------------------
# Voight closed forms


def voight_a_from_onset(v_onset_mm_per_h: float, alpha: float, terminal_h: float) -> float:
    """A such that the terminal-stage velocity at its onset equals v_onset: [(alpha - 1) A T]^(-1/(alpha - 1)) = v."""
    return v_onset_mm_per_h ** (-(alpha - 1.0)) / ((alpha - 1.0) * terminal_h)


def voight_velocity(t, *, alpha: float, a: float, t_f: float):
    t = np.asarray(t, dtype=float)
    return ((alpha - 1.0) * a * (t_f - t)) ** (-1.0 / (alpha - 1.0))


def voight_displacement(t, *, alpha: float, a: float, t_f: float, t_on: float):
    """Displacement (mm) of the terminal stage, zero at t_on."""
    t = np.asarray(t, dtype=float)
    if abs(alpha - 2.0) < 1e-12:
        return np.log((t_f - t_on) / (t_f - t)) / a
    p = (alpha - 2.0) / (alpha - 1.0)
    c = ((alpha - 1.0) * a) ** (-1.0 / (alpha - 1.0))
    return c * ((t_f - t_on) ** p - (t_f - t) ** p) / p


def terminal_series(*, alpha=2.0, v_onset_per_day=1.0, terminal_h=240.0, steady_fraction=0.0, n=2000):
    """Noise-free LOS series (psi = 0): steady phase at the onset velocity, then the Voight terminal stage.

    Samples at t_i = t_0 + i (t_f - t_0) / n, i = 0 .. n - 1 (the failure time itself is not sampled). Returns a
    dict."""
    v_on = v_onset_per_day / 24.0
    a = voight_a_from_onset(v_on, alpha, terminal_h)
    steady_h = steady_fraction * terminal_h
    t_0, t_on, t_f = 0.0, steady_h, steady_h + terminal_h
    t = t_0 + np.arange(n) * (t_f - t_0) / n
    om = np.where(
        t < t_on,
        v_on * (t - t_0),
        v_on * steady_h + voight_displacement(np.minimum(t, t_f - 1e-9), alpha=alpha, a=a, t_f=t_f, t_on=t_on),
    )
    return {"t": t, "omega": om, "t_0": t_0, "t_on": t_on, "t_f": t_f, "a": a, "alpha": alpha, "v_on": v_on}


# ----------------------------------------------------------------------------------------------------------------------
# shared preprocessor (FR-010-18)


def preprocess(t, omega, t_c: float):
    """Resample [t_0, t_c] to 512 points, centred 9-point LS velocity, y = 1 / v where v > 0 (nan elsewhere)."""
    t, omega = np.asarray(t, dtype=float), np.asarray(omega, dtype=float)
    t0 = float(t[0])
    grid = np.linspace(t0, t_c, L)
    om = np.interp(grid, t, omega)
    delta = (t_c - t0) / (L - 1)
    j = np.arange(-4, 5)
    v = np.full(L, np.nan)
    for k in range(4, L - 4):
        v[k] = float((j * om[k - 4 : k + 5]).sum() / (60.0 * delta))
    y = np.where(v > 0, 1.0 / np.where(v > 0, v, 1.0), np.nan)
    return {"t": grid, "omega": om, "v": v, "y": y, "delta": delta}


# ----------------------------------------------------------------------------------------------------------------------
# baselines


def iv_ttf(t, y, *, last_fraction: float = 0.25, min_points: int = 10):
    """(beta0, beta1, t_hat or None): OLS over the last 25 % (>= min_points) of the unmasked samples."""
    t, y = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    ok = np.isfinite(y)
    tt, yy = t[ok], y[ok]
    m = max(min_points, math.ceil(last_fraction * len(tt)))
    tt, yy = tt[-m:], yy[-m:]
    x = np.column_stack([np.ones_like(tt), tt])
    beta, *_ = np.linalg.lstsq(x, yy, rcond=None)
    b0, b1 = float(beta[0]), float(beta[1])
    return b0, b1, (-b0 / b1 if b1 < 0 else None)


def bayes_posterior(x_t, y, sigma2: float, prior_variance: float = 100.0):
    """Posterior mean and covariance of (beta0, beta1) with prior N(0, prior_variance I), design rows [1, t]."""
    x = np.column_stack([np.ones(len(x_t)), np.asarray(x_t, dtype=float)])
    y = np.asarray(y, dtype=float)
    precision = np.eye(2) / prior_variance + x.T @ x / sigma2
    cov = np.linalg.inv(precision)
    mean = cov @ (x.T @ y / sigma2)
    return mean, cov


def standardise(t, y):
    t, y = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    return (t - t.mean()) / t.std(), (y - y.mean()) / y.std(), (t.mean(), t.std(), y.mean(), y.std())


# ----------------------------------------------------------------------------------------------------------------------
# TTF read-out (FR-010-22)


def read_out(path, times, cap_time):
    """('predicted' | 'no failure predicted', t_hat) from a median path y(times): first crossing of 0 linearly
    interpolated; else the LS line through the last 16 steps when it has a negative slope and its root is within the
    cap;
    else the cap. A path whose first step is already <= 0 reads the first step time."""
    p, s = np.asarray(path, dtype=float), np.asarray(times, dtype=float)
    nonpos = np.flatnonzero(p <= 0.0)
    if len(nonpos):
        k = int(nonpos[0])
        if k == 0:
            return "predicted", float(s[0])
        t = s[k - 1] + (0.0 - p[k - 1]) * (s[k] - s[k - 1]) / (p[k] - p[k - 1])
        return "predicted", float(t)
    tail_t, tail_p = s[-16:], p[-16:]
    slope, intercept = np.polyfit(tail_t, tail_p, 1)
    if slope < 0:
        root = -intercept / slope
        if root <= cap_time:
            return "predicted", float(root)
    return "no failure predicted", float(cap_time)


# ----------------------------------------------------------------------------------------------------------------------
# evaluation (FR-010-23 ...)


def rel_error(t_hat: float, t_f: float, t_c: float) -> float:
    return abs(t_hat - t_f) / (t_f - t_c)


def cutoff_time(t_0: float, t_f: float, c: float) -> float:
    return t_0 + c * (t_f - t_0)


def percentile_ci(stats, level: float = 0.95):
    a = (1.0 - level) / 2.0 * 100.0
    lo, hi = np.percentile(np.asarray(stats, dtype=float), [a, 100.0 - a])
    return float(lo), float(hi)


def bootstrap_stats(values, indices, fn=np.median):
    v = np.asarray(values, dtype=float)
    return np.array([fn(v[row]) for row in indices])


# ----------------------------------------------------------------------------------------------------------------------
# SNR (FR-010-12)


def snr_estimate(omega) -> tuple[float, float]:
    """(SNR, sigma_hat) = ((Omega_end - Omega_0) / sigma_hat, 1.4826 MAD(second differences) / sqrt(6))."""
    om = np.asarray(omega, dtype=float)
    d2 = om[2:] - 2.0 * om[1:-1] + om[:-2]
    mad = np.median(np.abs(d2 - np.median(d2)))
    sigma = 1.4826 * mad / math.sqrt(6.0)
    return float((om[-1] - om[0]) / sigma), float(sigma)


# ----------------------------------------------------------------------------------------------------------------------
# statistics helpers (numpy only, no scipy in the root environment)


def ks_statistic(sample, cdf) -> float:
    x = np.sort(np.asarray(sample, dtype=float))
    n = len(x)
    f = np.array([cdf(float(v)) for v in x])
    return float(max(np.max(np.arange(1, n + 1) / n - f), np.max(f - np.arange(0, n) / n)))


def ks_pvalue(d: float, n: int) -> float:
    """Asymptotic Kolmogorov distribution: 2 sum_{k>=1} (-1)^(k-1) exp(-2 k^2 n d^2)."""
    lam = math.sqrt(n) * d
    return float(
        min(1.0, max(0.0, 2.0 * sum((-1) ** (k - 1) * math.exp(-2.0 * k * k * lam * lam) for k in range(1, 100))))
    )


def pinball(y_true, q_pred, taus):
    """Mean pinball loss: mean over samples and quantiles of max(tau (y - q), (tau - 1) (y - q))."""
    y = np.asarray(y_true, dtype=float)[..., None]
    q = np.asarray(q_pred, dtype=float)
    tau = np.asarray(taus, dtype=float)
    diff = y - q
    return float(np.mean(np.maximum(tau * diff, (tau - 1.0) * diff)))

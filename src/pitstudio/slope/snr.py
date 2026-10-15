"""Signal-to-noise estimator of a displacement record (FR-010-12), numpy only.

``sigma_hat = 1.4826 MAD(second differences) / sqrt(6)``: the variance of the second difference of white noise is
6 sigma^2, the MAD (median absolute deviation about the median) is robust to the Voight curvature, and 1.4826 turns a
MAD
into a standard deviation for Gaussian data. ``SNR = (Omega_end - Omega_0) / sigma_hat``.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

MAD_TO_SIGMA = 1.4826


def _record(omega: Any) -> np.ndarray:
    arr = np.asarray(omega, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"a displacement record is one-dimensional, got {arr.ndim} dimensions")
    if arr.size < 4:
        raise ValueError(f"at least 4 samples are needed for a second-difference estimate, got {arr.size}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("the displacement record contains a non-finite value")
    return arr


def sigma_hat(omega: Any) -> float:
    """Robust standard deviation of the measurement noise from the second differences of the record."""
    om = _record(omega)
    d2 = om[2:] - 2.0 * om[1:-1] + om[:-2]
    mad = float(np.median(np.abs(d2 - np.median(d2))))
    return MAD_TO_SIGMA * mad / math.sqrt(6.0)


def estimate(omega: Any) -> tuple[float, float]:
    """(SNR, sigma_hat) of the record; a record without any noise (sigma_hat = 0) raises ``ValueError``."""
    om = _record(omega)
    sigma = sigma_hat(om)
    if sigma == 0.0:
        raise ValueError("the second differences are constant: the record has no measurable noise")
    return float((om[-1] - om[0]) / sigma), sigma


def snr_obs(t: Any, omega: Any, t_0: float, t_f: float) -> float:
    """SNR_obs of the C1 recipe: the estimator on the samples with ``t_0 <= t <= t_f`` (at least 4 of them)."""
    tt, om = np.asarray(t, dtype=float), np.asarray(omega, dtype=float)
    if tt.shape != om.shape:
        raise ValueError("time and displacement have different lengths")
    keep = (tt >= t_0) & (tt <= t_f)
    if int(keep.sum()) < 4:
        raise ValueError(f"only {int(keep.sum())} samples between t_0 and t_f: at least 4 are needed")
    return estimate(om[keep])[0]

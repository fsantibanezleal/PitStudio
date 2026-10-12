"""Tape-gradient gate against a central finite difference (FR-011-23, P-011-10).

FD = (mean of 4 runs at mu + h  -  mean of 4 runs at mu - h) / (2 h);
SE_FD = s_p sqrt(1/4 + 1/4) / (2 h), s_p the pooled standard deviation of the two groups (6 degrees of freedom). The
tape
gradient is trusted only if |FD| >= 2.447 SE_FD (t_{0.975,6}, FD is significant), its sign equals the sign of FD, and
|g_tape - FD| <= 3.707 SE_FD (t_{0.995,6}). The quantiles are the published values of the spec (section 7).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from pitstudio.calibration.errors import InvalidCalibrationError

RUNS_PER_SIDE = 4
DOF = 6
T_SIGNIFICANT = 2.447  # t_{0.975, 6}
T_AGREEMENT = 3.707  # t_{0.995, 6}


@dataclass(frozen=True)
class GateResult:
    trusted: bool
    fd_gradient: float
    se_fd: float
    failure: str  # "none" | "fd-not-significant" | "sign-mismatch" | "disagreement"
    runs_per_side: int = RUNS_PER_SIDE
    dof: int = DOF


def _runs(name: str, values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if arr.shape != (RUNS_PER_SIDE,):
        raise InvalidCalibrationError(f"{name} needs exactly {RUNS_PER_SIDE} runs, got {arr.size}")
    if not np.isfinite(arr).all():
        raise InvalidCalibrationError(f"{name} contains a non-finite loss")
    return arr


def check_gradient(
    tape_gradient: float, plus_runs: Sequence[float], minus_runs: Sequence[float], h: float
) -> GateResult:
    """Decide whether the tape gradient agrees with the finite difference of 4 + 4 repeated runs."""
    plus, minus = _runs("plus_runs", plus_runs), _runs("minus_runs", minus_runs)
    if not isinstance(h, int | float | np.floating) or not math.isfinite(h) or h <= 0:
        raise InvalidCalibrationError(f"h must be a positive finite number, got {h!r}")
    if not isinstance(tape_gradient, int | float | np.floating) or not math.isfinite(tape_gradient):
        raise InvalidCalibrationError(f"the tape gradient must be finite, got {tape_gradient!r}")
    fd = float((plus.mean() - minus.mean()) / (2.0 * h))
    pooled = math.sqrt((float(plus.var(ddof=1)) + float(minus.var(ddof=1))) / 2.0)
    se = pooled * math.sqrt(0.25 + 0.25) / (2.0 * h)
    if abs(fd) < T_SIGNIFICANT * se:
        failure = "fd-not-significant"
    elif tape_gradient * fd <= 0.0:
        failure = "sign-mismatch"
    elif abs(tape_gradient - fd) > T_AGREEMENT * se:
        failure = "disagreement"
    else:
        failure = "none"
    return GateResult(trusted=failure == "none", fd_gradient=fd, se_fd=se, failure=failure)

"""The time-to-failure read-out shared by every learned forecaster (FR-010-22), numpy only.

``read_out`` maps the median path y(s) of the inverse velocity at strictly increasing times to a failure time: the first
time the path reaches y <= 0, linearly interpolated between the last positive and the first non-positive step (a path
whose
first step is already <= 0 reads the first step time, the spec names no earlier step); when no step reaches 0, the
least-squares line through the last 16 steps is extrapolated if its slope is negative and its root does not exceed the
cap;
otherwise "no failure predicted", scored at the cap. The cap must be finite and not before the last step (a cap before
it
would put the scoring time inside the forecast). The same rule reads the 0.1 and 0.9 quantile paths for the 80 %
interval.
The same rule runs in the ``forecasters`` web worker.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

TAIL_STEPS = 16
QUANTILES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


@dataclass(frozen=True)
class ReadOut:
    """The failure time read from one path; ``scored_at_cap`` is True exactly for "no failure predicted"."""

    outcome: str
    t_hat_f: float
    scored_at_cap: bool


def read_out(path: Any, times: Any, cap_time: float) -> ReadOut:
    """Failure time of the median path ``path`` at ``times`` (see the module docstring); ``ValueError`` if hostile."""
    p, s = np.asarray(path, dtype=float), np.asarray(times, dtype=float)
    if p.ndim != 1 or s.ndim != 1 or p.shape != s.shape:
        raise ValueError("path and times must be one-dimensional arrays of the same length")
    if p.size < 2:
        raise ValueError("a path needs at least 2 steps")
    if not (np.all(np.isfinite(p)) and np.all(np.isfinite(s))):
        raise ValueError("the path and the times must be finite")
    if not np.all(np.diff(s) > 0.0):
        raise ValueError("the times must be strictly increasing")
    if not (math.isfinite(cap_time) and cap_time >= s[-1] and cap_time > 0.0):
        raise ValueError("the cap must be finite, positive and not before the last step")
    nonpositive = np.flatnonzero(p <= 0.0)
    if nonpositive.size:
        k = int(nonpositive[0])
        if k == 0:
            return ReadOut("predicted", float(s[0]), False)
        t = s[k - 1] + (0.0 - p[k - 1]) * (s[k] - s[k - 1]) / (p[k] - p[k - 1])
        return ReadOut("predicted", float(t), False)
    if p.size < TAIL_STEPS:
        raise ValueError(f"no step reaches zero and fewer than {TAIL_STEPS} steps are available to extrapolate")
    tail_t, tail_p = s[-TAIL_STEPS:], p[-TAIL_STEPS:]
    t_bar, p_bar = float(tail_t.mean()), float(tail_p.mean())
    dt = tail_t - t_bar
    slope = float(dt @ (tail_p - p_bar)) / float(dt @ dt)
    if slope < 0.0:
        root = t_bar - p_bar / slope
        if root <= cap_time:
            return ReadOut("predicted", float(root), False)
    return ReadOut("no failure predicted", float(cap_time), True)


def read_out_interval(
    quantile_paths: Any, times: Any, cap_time: float, quantiles: Any = QUANTILES
) -> tuple[ReadOut, ReadOut]:
    """The 80 % interval: ``read_out`` of the 0.1 path and of the 0.9 path (rows chosen by quantile value)."""
    paths = np.asarray(quantile_paths, dtype=float)
    q = np.asarray(quantiles, dtype=float)
    if paths.ndim != 2 or paths.shape[0] != q.size:
        raise ValueError("quantile_paths must be (quantiles, steps)")
    lo = int(np.argmin(np.abs(q - 0.1)))
    hi = int(np.argmin(np.abs(q - 0.9)))
    return read_out(paths[lo], times, cap_time), read_out(paths[hi], times, cap_time)

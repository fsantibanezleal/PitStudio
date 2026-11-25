"""Latency statistics: linear percentiles and seeded percentile bootstrap intervals (FR-016-26, FR-016-36)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

QUANTILES = {"p50": 50.0, "p90": 90.0, "p95": 95.0, "p99": 99.0}


class InvalidMeasurement(ValueError):
    """A non-finite or negative duration, or an empty sample; `.reason` contains "invalid measurement"."""

    def __init__(self, reason: str) -> None:
        self.reason = f"invalid measurement: {reason}"
        super().__init__(self.reason)


def _sorted_sample(samples_ms: Sequence[float]) -> np.ndarray:
    x = np.asarray(samples_ms, dtype=np.float64)
    if x.size == 0:
        raise InvalidMeasurement("empty sample")
    if not np.isfinite(x).all() or (x < 0).any():
        raise InvalidMeasurement("a duration is non-finite or negative")
    return np.sort(x)


def percentiles(samples_ms: Sequence[float]) -> dict[str, float]:
    """p50, p90, p95 and p99 by linear interpolation."""
    x = _sorted_sample(samples_ms)
    return {key: float(np.percentile(x, q, method="linear")) for key, q in QUANTILES.items()}


def latency_stats(samples_ms: Sequence[float], *, resamples: int = 2000, seed: int = 0, level: float = 0.95) -> dict:
    """Percentiles with `level` percentile-bootstrap intervals over `resamples` resamples of the sorted sample."""
    x = _sorted_sample(samples_ms)
    n = x.size
    rng = np.random.default_rng(seed)
    qs = list(QUANTILES.values())
    boot = np.empty((resamples, len(qs)))
    chunk = max(1, 4_000_000 // n)
    for start in range(0, resamples, chunk):
        stop = min(resamples, start + chunk)
        idx = rng.integers(0, n, size=(stop - start, n))
        boot[start:stop] = np.percentile(x[idx], qs, axis=1, method="linear").T
    lo_q, hi_q = 100 * (1 - level) / 2, 100 * (1 + level) / 2
    lows = np.percentile(boot, lo_q, axis=0, method="linear")
    highs = np.percentile(boot, hi_q, axis=0, method="linear")
    out: dict = {}
    for i, (key, q) in enumerate(QUANTILES.items()):
        value = float(np.percentile(x, q, method="linear"))
        # a percentile interval of the resamples can sit a rounding step off the point value of a flat sample
        out[key] = {"value_ms": value, "lo_ms": min(float(lows[i]), value), "hi_ms": max(float(highs[i]), value)}
    out["bootstrap"] = {"resamples": resamples, "seed": seed, "level": level}
    if not all(math.isfinite(v) for key in QUANTILES for v in out[key].values()):
        raise InvalidMeasurement("statistics are not finite")
    return out

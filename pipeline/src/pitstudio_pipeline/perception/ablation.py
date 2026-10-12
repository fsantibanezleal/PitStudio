"""The paired cluster-bootstrap DR ablation and its verdict (FR-009-31, P-009-11, SC-009-04).

D-FINE-S trained on arm S is compared with D-FINE-S trained on arm U on the same pit-family test images. The statistic
is a
set-level metric (mAP50), so images of one scenario are resampled together: each draw resamples the test scenario seeds
(clusters) with replacement and BOTH arms are scored on that same resample (identical resample indices). The verdict
follows
FR-000-05: "better" if the lower bound is above 0, "worse" if the upper bound is below 0, else "no significant
difference".
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


def verdict_of(lower: float, upper: float) -> str:
    """The decision rule of FR-000-05 on the interval of d = mAP50(S) - mAP50(U)."""
    if not (math.isfinite(lower) and math.isfinite(upper)) or lower > upper:
        raise ValueError(f"the interval [lower {lower}, upper {upper}] must be finite with lower <= upper")
    if lower > 0.0:
        return "better"
    if upper < 0.0:
        return "worse"
    return "no significant difference"


@dataclass(frozen=True)
class PairedResult:
    """Point difference, percentile interval, verdict and the `bootstrap` block of DC-009-05's `dr_ablation`."""

    difference: float
    lower: float
    upper: float
    verdict: str
    resamples: int
    level: float
    seed: int
    bootstrap_record: dict[str, Any]


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _value(stat: Callable[[Sequence[int]], float], clusters: Sequence[int], name: str) -> float:
    v = float(stat(clusters))
    if not math.isfinite(v):
        raise ValueError(f"{name} returned a non-finite statistic ({v!r}): stat must be finite")
    return v


def paired_cluster_bootstrap(
    clusters: Sequence[int],
    stat_a: Callable[[Sequence[int]], float],
    stat_b: Callable[[Sequence[int]], float],
    *,
    resamples: int = 10000,
    level: float = 0.95,
    seed: int,
) -> PairedResult:
    """Paired percentile bootstrap over clusters of `stat_a - stat_b`; both statistics see the same resamples."""
    if len(clusters) < 2 or not all(_is_int(c) for c in clusters) or len(set(clusters)) != len(clusters):
        raise ValueError(f"clusters must be at least 2 distinct ints, got {list(clusters)[:5]!r}")
    if not _is_int(resamples) or resamples < 1:
        raise ValueError(f"resamples must be an int >= 1, got {resamples!r}")
    if not isinstance(level, int | float) or isinstance(level, bool) or not (0.0 < level < 1.0):
        raise ValueError(f"level must be in (0, 1), got {level!r}")
    if not _is_int(seed):
        raise ValueError(f"seed must be an int, got {seed!r}")
    if not callable(stat_a):
        raise ValueError("stat_a must be callable")
    if not callable(stat_b):
        raise ValueError("stat_b must be callable")
    ordered = sorted(int(c) for c in clusters)
    difference = _value(stat_a, ordered, "stat_a") - _value(stat_b, ordered, "stat_b")
    rng = np.random.default_rng(seed)
    n = len(ordered)
    draws = np.empty(resamples, dtype=np.float64)
    for r in range(resamples):
        sample = [ordered[int(i)] for i in rng.integers(0, n, size=n)]
        draws[r] = _value(stat_a, sample, "stat_a") - _value(stat_b, sample, "stat_b")
    lo, hi = np.percentile(draws, [100.0 * (1.0 - level) / 2.0, 100.0 * (1.0 + level) / 2.0])
    lower, upper = float(lo), float(hi)
    return PairedResult(
        difference=difference,
        lower=lower,
        upper=upper,
        verdict=verdict_of(lower, upper),
        resamples=resamples,
        level=float(level),
        seed=seed,
        bootstrap_record={
            "resamples": resamples,
            "method": "paired-cluster-percentile",
            "cluster": "test-scenario-seed",
            "level": float(level),
            "identical_resample_indices": True,
            "seed": seed,
        },
    )

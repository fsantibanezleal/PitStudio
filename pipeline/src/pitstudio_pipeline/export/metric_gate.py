"""The deployed-graph task metric must reproduce the PyTorch post-processed metric within 0.1 pp (FR-016-05)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class MetricCheck:
    verdict: str
    delta_pp: float


def check_deployed_metric(pytorch_pct: float, deployed_pct: float, *, tol_pp: float = 0.1) -> MetricCheck:
    """`pass` iff |deployed - pytorch| <= tol_pp; non-finite or out-of-[0, 100] percentages raise ValueError."""
    for name, value in (("pytorch", pytorch_pct), ("deployed", deployed_pct)):
        if not math.isfinite(value) or not 0.0 <= value <= 100.0:
            raise ValueError(f"{name} metric {value!r} is not a percentage in [0, 100]")
    delta = deployed_pct - pytorch_pct
    return MetricCheck("pass" if abs(delta) <= tol_pp else "fail", delta)

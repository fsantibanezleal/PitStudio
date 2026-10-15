"""Latency and throughput protocol on an injected clock (FR-016-26, FR-016-27, FR-016-36).

`call` performs one inference. CUDA events and NVML sit behind the adapters that build `call`; this module owns the
warm-up, the iteration rule, the regimes and the rejection of invalid measurements.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from pitstudio.accel.stats import InvalidMeasurement, latency_stats

WARMUP_MIN_S = 5.0
WARMUP_MIN_CALLS = 10
ITERATIONS_MAX = 1000
TIMED_MAX_S = 30.0
ITERATIONS_MIN = 50
SPACED_GAP_S = 0.2
REGIMES = ("spaced", "sustained")
SCOPES = ("gpu-compute", "end-to-end")


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


@dataclass
class LatencyResult:
    status: str
    reason: str | None
    regime: str
    scope: str
    gap_ms: int
    warmup_s: float
    warmup_iterations: int
    iterations: int
    timed_s: float
    samples_ms: list[float] = field(default_factory=list)
    stats: dict[str, Any] | None = None


def _valid(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _one(call: Callable[[], Any], clock: Clock, scope: str) -> Any:
    """One duration in ms: the CUDA-event value `call` returns (gpu-compute) or the host-clock span (end-to-end)."""
    start = clock.monotonic()
    returned = call()
    host_ms = (clock.monotonic() - start) * 1000.0
    return returned if scope == "gpu-compute" else host_ms


def run_latency(
    call: Callable[[], Any], *, clock: Clock, regime: str, scope: str, seed: int = 0, resamples: int = 2000
) -> LatencyResult:
    """Warm up for at least 5 s and 10 calls, then time until 1,000 iterations or 30 s (floor 50 iterations)."""
    if regime not in REGIMES or scope not in SCOPES:
        raise ValueError(f"regime {regime!r} or scope {scope!r} is not one of {REGIMES} / {SCOPES}")
    gap_ms = 200 if regime == "spaced" else 0

    def rejected(reason: str, warm_s: float, warm_n: int, timed: float, samples: list[float]) -> LatencyResult:
        message = reason if reason.startswith("invalid measurement") else f"invalid measurement: {reason}"
        return LatencyResult("rejected", message, regime, scope, gap_ms, warm_s, warm_n, len(samples), timed, samples)

    warm_start = clock.monotonic()
    warm_n = 0
    while True:
        duration = _one(call, clock, scope)
        warm_n += 1
        warm_s = clock.monotonic() - warm_start
        if not _valid(duration):
            return rejected(f"warm-up duration {duration!r}", warm_s, warm_n, 0.0, [])
        if warm_s >= WARMUP_MIN_S and warm_n >= WARMUP_MIN_CALLS:
            break

    samples: list[float] = []
    timed_start = clock.monotonic()
    while True:
        duration = _one(call, clock, scope)
        timed_s = clock.monotonic() - timed_start
        if not _valid(duration):
            return rejected(f"duration {duration!r}", warm_s, warm_n, timed_s, samples)
        samples.append(float(duration))
        if len(samples) >= ITERATIONS_MAX or (timed_s >= TIMED_MAX_S and len(samples) >= ITERATIONS_MIN):
            break
        if regime == "spaced":
            clock.sleep(SPACED_GAP_S)
    try:
        stats = latency_stats(samples, resamples=resamples, seed=seed)
    except InvalidMeasurement as exc:
        return rejected(exc.reason, warm_s, warm_n, timed_s, samples)
    return LatencyResult("ok", None, regime, scope, gap_ms, warm_s, warm_n, len(samples), timed_s, samples, stats)


def sweep_plan(kind: str) -> tuple[str, tuple[int, ...]]:
    """The throughput sweep of a model kind: batch sizes for vision and policies, particle counts for the GNS."""
    plans = {
        "vision": ("batch", (1, 4, 16, 64)),
        "policy": ("batch", (1, 64, 4096)),
        "gns": ("particles", (1000, 2000, 10000)),
    }
    if kind not in plans:
        raise ValueError(f"unknown model kind {kind!r}; expected one of {', '.join(plans)}")
    return plans[kind]


@dataclass
class ThroughputResult:
    status: str
    reason: str | None
    entries: list[dict[str, Any]] = field(default_factory=list)


def run_throughput(
    call: Callable[[int], Any], *, clock: Clock, sizes: Sequence[int], iterations: int, sweep: str = "batch"
) -> ThroughputResult:
    """Samples per second as size x iterations / elapsed seconds, one entry per size."""
    entries: list[dict[str, Any]] = []
    for size in sizes:
        start = clock.monotonic()
        for _ in range(iterations):
            call(size)
        elapsed = clock.monotonic() - start
        if not math.isfinite(elapsed) or elapsed <= 0:
            return ThroughputResult("rejected", f"invalid measurement: elapsed {elapsed!r} s at size {size}", entries)
        entries.append(
            {
                "sweep": sweep,
                "size": size,
                "iterations": iterations,
                "elapsed_s": elapsed,
                "samples_per_s": size * iterations / elapsed,
            }
        )
    return ThroughputResult("ok", None, entries)

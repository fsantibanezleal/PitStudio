"""Throughput of the studio GPU stages (FR-006-18, FR-006-19, P-006-07).

Throughput is the work count divided by the wall time of the compute loop (input and output excluded): never
declared, never guessed. A zero, negative or non-finite work count or time omits the figure and names the reason.
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass

UNITS = {
    "dem": "particle-steps/s",
    "mpm": "particle-steps/s",
    "dust": "particle-steps/s",
    "shallow-water": "cell-steps/s",
    "vehicles": "vehicle-steps/s",
    "encode": "frames/s",
}


@dataclass(frozen=True)
class Measurement:
    throughput: dict | None
    reason: str | None


def _positive_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{what} must be a positive integer, got {value!r}")
    return value


def work_count(kind: str, *, items: int, steps: int = 1) -> int:
    """Items times steps (particles, cells or vehicles times steps); for `encode` the number of frames."""
    if kind not in UNITS:
        raise ValueError(f"unknown throughput kind {kind!r}")
    items, steps = _positive_int(items, "items"), _positive_int(steps, "steps")
    if kind == "encode" and steps != 1:
        raise ValueError("an encode counts frames: steps must be 1")
    return items * steps


class ComputeTimer:
    """Adds up the clock time spent inside `loop()` blocks (also when the body raises)."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self.seconds = 0.0

    @contextlib.contextmanager
    def loop(self) -> Iterator[None]:
        start = self._clock()
        try:
            yield
        finally:
            self.seconds += self._clock() - start


def _ok(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def measure(kind: str, work: float, seconds: float) -> Measurement:
    if kind not in UNITS:
        raise ValueError(f"unknown throughput kind {kind!r}")
    bad = [name for name, value in (("work count", work), ("time", seconds)) if not _ok(value)]
    if bad:
        return Measurement(None, f"throughput omitted: the {' and the '.join(bad)} is zero, negative or not finite")
    return Measurement({"value": work / seconds, "unit": UNITS[kind]}, None)


def result_fields(kind: str, work: float, seconds: float) -> dict:
    """The stage-result fragment: `{"throughput": ...}`, or `{"message": <reason>}` when the figure is omitted."""
    m = measure(kind, work, seconds)
    return {"throughput": m.throughput} if m.throughput is not None else {"message": str(m.reason)}

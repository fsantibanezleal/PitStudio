"""Joules per inference from the NVML total-energy counter, 10 Hz telemetry and the thermal flag (FR-016-28, FR-016-29).

The backend protocol is the runner's: `read(field) -> float`, raising for a field the device does not support.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

HW_THERMAL_SLOWDOWN = 0x40  # nvmlClocksEventReasonHwThermalSlowdown
MIN_WINDOW_S = 1.0
TELEMETRY_FIELDS = ("power_w", "sm_clock_mhz", "mem_clock_mhz", "temp_c", "clocks_event_mask")


class Backend(Protocol):
    def read(self, field: str) -> float: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


@dataclass(frozen=True)
class EnergyResult:
    joules: float | None
    reason: str | None
    window_s: float


def _counter_ok(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def joules_per_inference(
    e_start_mj: float, e_end_mj: float, iterations: int, batch: int, window_s: float
) -> EnergyResult:
    """(E_end - E_start) / 1000 / (iterations x batch); null with the reason for a bad counter or a short window."""
    if iterations <= 0 or batch <= 0:
        raise ValueError(f"iterations ({iterations}) and batch ({batch}) must be positive")
    if not (_counter_ok(e_start_mj) and _counter_ok(e_end_mj)):
        return EnergyResult(None, "energy counter value is non-finite or negative", window_s)
    if e_end_mj < e_start_mj:
        return EnergyResult(None, "energy counter decreased during the window", window_s)
    if not window_s >= MIN_WINDOW_S:
        return EnergyResult(None, f"energy window of {window_s:.3g} s is shorter than {MIN_WINDOW_S:g} s", window_s)
    return EnergyResult((e_end_mj - e_start_mj) / 1000.0 / (iterations * batch), None, window_s)


def measure_energy(backend: Backend, clock: Clock, run: Callable[[], Any], *, iterations: int, batch: int) -> EnergyResult:
    """Read the counter around `iterations` calls of `run`; the window is the clock span of the calls."""
    start_time = clock.monotonic()
    try:
        e_start = backend.read("energy_mj")
    except Exception as exc:
        for _ in range(iterations):
            run()
        return EnergyResult(None, f"energy counter unavailable ({type(exc).__name__})", clock.monotonic() - start_time)
    start_time = clock.monotonic()
    for _ in range(iterations):
        run()
    window = clock.monotonic() - start_time
    try:
        e_end = backend.read("energy_mj")
    except Exception as exc:
        return EnergyResult(None, f"energy counter unavailable ({type(exc).__name__})", window)
    return joules_per_inference(e_start, e_end, iterations, batch, window)


def sample_telemetry(backend: Backend, clock: Clock, *, duration_s: float, hz: float = 10.0) -> list[dict[str, Any]]:
    """Power, clocks, temperature and clocks-event reasons every 1/hz seconds; an unreadable field is None."""
    count = int(math.floor(duration_s * hz + 1e-9))
    start = clock.monotonic()
    samples: list[dict[str, Any]] = []
    for i in range(count):
        row: dict[str, Any] = {"t": clock.monotonic() - start}
        for name in TELEMETRY_FIELDS:
            try:
                row[name] = backend.read(name)
            except Exception:
                row[name] = None
        samples.append(row)
        if i + 1 < count:
            clock.sleep(1.0 / hz)
    return samples


def thermal_slowdown(samples: Sequence[Mapping[str, Any]]) -> bool:
    """True iff any sample carries the hardware thermal-slowdown clocks-event reason."""
    for sample in samples:
        mask = sample.get("clocks_event_mask")
        if mask is not None and int(mask) & HW_THERMAL_SLOWDOWN:
            return True
    return False

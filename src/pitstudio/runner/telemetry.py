"""GPU telemetry: the sampler writing `telemetry.jsonl` and the per-stage summary (FR-002-30..32)."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

BITS = {
    "idle": 0x1,
    "sw_power_cap": 0x4,
    "hw_slowdown": 0x8,
    "sw_thermal": 0x20,
    "hw_thermal": 0x40,
    "power_brake": 0x80,
}
CAPS = {
    "util_pct": 100,
    "power_w": 10000,
    "power_limit_w": 10000,
    "temp_c": 200,
    "sm_clock_mhz": 20000,
    "nvenc_util_pct": 100,
}
INTS = {"clocks_event_mask": 2**32 - 1, "energy_mj": 2**53 - 1, "pcie_replays": 2**32 - 1}  # fields stored as integers


def clean(raw: Any, cap: float, integer: bool = False) -> float | int | None:
    """A reading inside the schema's caps, else None: an unsupported, non-finite, negative or huge value is none."""
    if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw) or not 0 <= raw <= cap:
        return None
    return round(raw) if integer else raw


def read_sample(backend: Any, field: str) -> float | int | None:
    try:
        return clean(backend.read(field), CAPS.get(field) or INTS[field], field in INTS)
    except Exception:
        return None


def sample_loop(
    backend: Any,
    path: Path,
    hz: float,
    *,
    clock: Any = time,
    should_stop: Callable[[], bool],
    run_id: str,
    stage: dict,
    shard: int = 0,
    gpu: int = 0,
    on_sample: Callable[[dict], None] | None = None,
) -> int:
    """Append one JSON line per sample (flushed per line) until `should_stop()`; returns the number of samples."""
    n, t0, total = 0, None, backend.vram_total_bytes
    while not should_stop():
        t0 = clock.monotonic() if t0 is None else t0
        try:
            free = backend.read("free_bytes")
            used = clean(total - free, total, True) if free <= total else None
        except Exception:
            used = None
        row = {
            "t_s": clock.monotonic() - t0,
            "run_id": run_id,
            "stage": stage,
            "shard": shard,
            "gpu": gpu,
            "mem_used_bytes": used,
            "mem_total_bytes": total,
            **{f: read_sample(backend, f) for f in (*CAPS, *INTS)},
        }
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        n += 1
        if on_sample:
            on_sample(row)
        clock.sleep(1 / hz)
    return n


def pct(values: list[float], q: float) -> float:
    """Percentile by linear interpolation between order statistics (Hyndman-Fan type 7)."""
    s = sorted(values)
    h = (len(s) - 1) * q / 100
    lo = math.floor(h)
    return s[lo] + (h - lo) * (s[min(lo + 1, len(s) - 1)] - s[lo])


def summarize(samples: list[dict], *, sample_hz: float) -> dict:
    """The telemetry summary of spec 001 data-model 2.4: type-7 percentiles, only valid samples, no guessed zeros."""
    out: dict[str, Any] = {"sample_hz": sample_hz, "n_samples": len(samples)}
    why: dict[str, str] = {}

    def put(key: str, field: str, make: Callable[[list], Any], values: list | None = None) -> None:
        v = [s[field] for s in samples if s.get(field) is not None] if values is None else values
        out[key] = make(v) if v else None
        if not v:
            why[key] = f"no valid sample of {field} ({len(samples) - len(v)} invalid of {len(samples)})"

    def mean(v: list) -> float:
        return math.fsum(v) / len(v)

    put("gpu_busy_pct", "util_pct", lambda v: {"mean": mean(v), "p50": pct(v, 50), "p95": pct(v, 95)})
    put("mem_used_peak_bytes", "mem_used_bytes", max)
    put("power_w", "power_w", lambda v: {"mean": mean(v), "p95": pct(v, 95), "max": max(v)})
    both = [s for s in samples if s.get("power_w") is not None and s.get("power_limit_w") is not None]
    put(
        "power_at_limit_frac",
        "power_limit_w",
        lambda v: sum(v) / len(v),
        [s["power_w"] >= 0.95 * s["power_limit_w"] for s in both],
    )
    put("energy_j", "energy_mj", lambda v: (v[-1] - v[0]) / 1000)
    put("sm_clock_mhz", "sm_clock_mhz", lambda v: {"mean": mean(v), "p5": pct(v, 5)})
    put("temp_c_max", "temp_c", max)
    put(
        "clocks_event_frac",
        "clocks_event_mask",
        lambda v: {k: sum(1 for m in v if m & b) / len(v) for k, b in BITS.items()},
    )
    put("nvenc_util_pct", "nvenc_util_pct", lambda v: {"mean": mean(v), "max": max(v)})
    put("pcie_replays_delta", "pcie_replays", lambda v: v[-1] - v[0])
    return {**out, "unavailable": why}


def thermal_flag(summary: dict) -> bool:
    frac = summary.get("clocks_event_frac") or {}
    return frac.get("hw_thermal", 0) > 0.05 or frac.get("hw_slowdown", 0) > 0.05

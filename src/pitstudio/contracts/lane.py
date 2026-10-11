"""The measured lane gate (FR-001-13, data-model 2.6): the lane of an artefact is computed, never declared.

    live  <=>  web_drivable
               and max_asset_bytes <= 25,000,000
               and (interaction_ms <= 16 or run_ms_t2 <= 1,000)       (a null time never satisfies its bound)
               and (trace_bytes is null or trace_bytes <= 10,000,000)

The thresholds are the ``lane_gate.*`` keys of ``thresholds.yaml`` (MB = 10^6 B).
"""

from __future__ import annotations

import math
from typing import Any

from pitstudio.contracts.io import ContractError

LIVE_ASSET_BYTES_MAX = 25_000_000
INTERACTION_MS_MAX = 16
RUN_MS_MAX = 1_000
TRACE_BYTES_MAX = 10_000_000


def _count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{name} must be a non-negative integer", pointer=f"/{name}")
    return value


def _millis(value: Any, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ContractError(f"{name} must be null or a finite number >= 0", pointer=f"/{name}")
    return float(value)


def lane_failures(measurements: Any) -> list[str]:
    """The names of the gate conditions that fail (empty list = the lane is ``live``). Hostile input raises."""
    if not isinstance(measurements, dict):
        raise ContractError("lane measurements must be an object")
    for name in ("web_drivable", "max_asset_bytes", "interaction_ms", "run_ms_t2", "trace_bytes"):
        if name not in measurements:
            raise ContractError(f"{name} is missing", pointer=f"/{name}")
    web = measurements["web_drivable"]
    if not isinstance(web, bool):
        raise ContractError("web_drivable must be a boolean", pointer="/web_drivable")
    asset = _count(measurements["max_asset_bytes"], "max_asset_bytes")
    interaction = _millis(measurements["interaction_ms"], "interaction_ms")
    run = _millis(measurements["run_ms_t2"], "run_ms_t2")
    trace_raw = measurements["trace_bytes"]
    trace = None if trace_raw is None else _count(trace_raw, "trace_bytes")
    failing: list[str] = []
    if not web:
        failing.append("web_drivable")
    if asset > LIVE_ASSET_BYTES_MAX:
        failing.append("max_asset_bytes")
    if not ((interaction is not None and interaction <= INTERACTION_MS_MAX) or (run is not None and run <= RUN_MS_MAX)):
        failing.extend(["interaction_ms", "run_ms_t2"])
    if trace is not None and trace > TRACE_BYTES_MAX:
        failing.append("trace_bytes")
    return failing


def lane_of(measurements: Any) -> str:
    """``"live"`` when every condition of the gate holds, else ``"replay"``."""
    return "replay" if lane_failures(measurements) else "live"

"""GPU-hour records of the forecaster training stages (NFR-010-06).

The budget is an estimate, not a limit: the measured hours are recorded in the manifest of every training stage and an
overrun
is stated in a sentence (the cards quote it). A CPU training costs no GPU hours and is recorded as such. Standard
library only.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

BUDGET_GPU_HOURS = 2.0
TRAINED_ARMS = ("tcn", "patchtst", "chronos_bolt_fine_tuned")  # the zero-shot arm is not trained
DEVICES = ("cpu", "cuda")


def gpu_hours_record(arm: str, seconds: float, *, device: str) -> dict[str, Any]:
    """The record of one training run: hours (0 on the CPU, with a note), the device and the seconds."""
    if arm not in TRAINED_ARMS:
        raise ValueError(f"arm must be one of {list(TRAINED_ARMS)}, got {arm!r}")
    if device not in DEVICES:
        raise ValueError(f"device must be one of {list(DEVICES)}, got {device!r}")
    if isinstance(seconds, bool) or not isinstance(seconds, int | float) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"seconds must be a finite non-negative number, got {seconds!r}")
    record: dict[str, Any] = {
        "arm": arm,
        "gpu_hours": seconds / 3600.0 if device == "cuda" else 0.0,
        "device": device,
        "seconds": float(seconds),
    }
    if device == "cpu":
        record["note"] = "trained on the CPU"
    return record


def attach_gpu_hours(manifest: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    """A copy of a training-stage manifest with the record under ``gpu_hours`` (the input is not modified)."""
    out = dict(manifest)
    out["gpu_hours"] = dict(record)
    return out


def missing_gpu_hours(manifests: Sequence[Mapping[str, Any]]) -> list[str]:
    """The ``id`` of every ``s30_train`` manifest without a numeric, non-negative ``gpu_hours.gpu_hours``."""
    missing = []
    for m in manifests:
        if m.get("stage") != "s30_train":
            continue
        hours = (m.get("gpu_hours") or {}).get("gpu_hours")
        if isinstance(hours, bool) or not isinstance(hours, int | float) or not math.isfinite(hours) or hours < 0:
            missing.append(m["id"])
    return missing


def budget_report(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Total GPU hours against the estimate and the overrun statement (None within the budget)."""
    total = float(sum(r["gpu_hours"] for r in records))
    overrun = total > BUDGET_GPU_HOURS
    return {
        "total_gpu_hours": total,
        "budget_gpu_hours": BUDGET_GPU_HOURS,
        "overrun": overrun,
        "statement": f"training used {total:.2f} GPU-h against an estimate of {BUDGET_GPU_HOURS:g} GPU-h"
        if overrun
        else None,
    }

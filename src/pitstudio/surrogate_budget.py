"""GPU-hour records of the training and calibration stages (NFR-011-04).

The budgets are estimates, not limits: the measured hours are recorded in the run manifest and an overrun is stated in a
sentence (the cards quote it). Standard library only.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

BUDGET_GPU_HOURS: dict[str, float] = {"gns": 15.0, "fno-tailings": 2.0, "fno-dust": 2.0, "calibration": 2.0}


def _check_stage(stage: object) -> str:
    if not isinstance(stage, str) or stage not in BUDGET_GPU_HOURS:
        raise ValueError(f"unknown stage {stage!r}; expected one of {list(BUDGET_GPU_HOURS)}")
    return stage


def gpu_hours_record(stage: str, seconds: float) -> dict[str, Any]:
    """The record of one stage: hours, the estimate, whether it is within it and the overrun statement."""
    _check_stage(stage)
    if isinstance(seconds, bool) or not isinstance(seconds, int | float) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"seconds must be a finite non-negative number, got {seconds!r}")
    hours = seconds / 3600.0
    budget = BUDGET_GPU_HOURS[stage]
    within = hours <= budget
    overrun = 0.0 if within else hours - budget
    statement = (
        ""
        if within
        else f"{stage}: overrun of the GPU-hour estimate: measured {hours:.2f} GPU-h against an estimate of "
        f"{budget:g} GPU-h (over by {overrun:.2f} GPU-h)"
    )
    return {
        "stage": stage,
        "gpu_hours": hours,
        "budget_gpu_hours": budget,
        "budget_kind": "estimate",
        "within_budget": within,
        "overrun_gpu_hours": overrun,
        "statement": statement,
    }


def attach_gpu_hours(manifest: dict[str, Any], stage: str, seconds: float) -> dict[str, Any]:
    """Set `manifest["gpu_hours"][stage]` (replacing an earlier record) and return the same manifest object."""
    record = gpu_hours_record(stage, seconds)
    manifest.setdefault("gpu_hours", {})[stage] = record
    return manifest


def missing_gpu_hours(manifest: dict[str, Any], stages_run: Sequence[str]) -> list[str]:
    """The stages of `stages_run`, in order, that have no record in the manifest."""
    for stage in stages_run:
        _check_stage(stage)
    recorded = manifest.get("gpu_hours", {})
    return [stage for stage in stages_run if stage not in recorded]

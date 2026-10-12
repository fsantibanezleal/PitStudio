"""GNS speed report (FR-011-16): steps per second of the surrogate and of the solver, measurements only.

Steps per second is the reciprocal of the MEDIAN step time (NFR-011-02 uses the median of 100 steps). Hardware and tier are
named for every rate; a missing device or tier is reported "not run" with its reason and never guessed. The statement is a
list of measurements and carries no comparative wording.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

TIERS = ("T1", "T2")


def _times(label: str, values: Sequence[float]) -> float:
    if not values:
        raise ValueError(f"{label}: step_times_s must not be empty")
    for v in values:
        if not isinstance(v, int | float) or isinstance(v, bool) or not math.isfinite(v) or v <= 0:
            raise ValueError(f"{label}: every step time must be a positive finite number, got {v!r}")
    return float(median(values))


def _text(label: str, entry: Mapping[str, Any], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: {key} must be a non-empty string")
    return value


def build_speed_report(
    *,
    geometry_id: str,
    particles: int,
    python_cpu: Mapping[str, Any],
    python_gpu: Mapping[str, Any],
    browser: Mapping[str, Mapping[str, Any]],
    solver: Mapping[str, Any],
) -> dict[str, Any]:
    """Assemble the speed block; raises ValueError for any missing, empty, non-finite or non-positive input."""
    if not isinstance(geometry_id, str) or not geometry_id:
        raise ValueError("geometry_id must be a non-empty string")
    if not isinstance(particles, int) or isinstance(particles, bool) or particles < 1:
        raise ValueError(f"particles must be an integer >= 1, got {particles!r}")
    if set(browser) != set(TIERS):
        raise ValueError(f"browser must have exactly the tiers {list(TIERS)}, got {sorted(browser)}")

    cpu_median = _times("python_cpu", python_cpu.get("step_times_s", []))
    cpu = {
        "hardware": _text("python_cpu", python_cpu, "hardware"),
        "median_step_s": cpu_median,
        "steps_per_s": 1.0 / cpu_median,
    }
    gpu = _measured_or_not_run("python_gpu", python_gpu, extra=())
    tiers = {tier: _measured_or_not_run(f"browser {tier}", browser[tier], extra=("browser",), tier=tier) for tier in TIERS}
    wall = solver.get("wall_s_per_step")
    if not isinstance(wall, int | float) or isinstance(wall, bool) or not math.isfinite(wall) or wall <= 0:
        raise ValueError(f"solver: wall_s_per_step must be a positive finite number, got {wall!r}")
    solver_block = {
        "hardware": _text("solver", solver, "hardware"),
        "wall_s_per_step": float(wall),
        "steps_per_s": 1.0 / float(wall),
    }
    surrogate = {"python_cpu": cpu, "python_gpu": gpu, "browser": tiers}
    return {
        "geometry_id": geometry_id,
        "particles": particles,
        "surrogate": surrogate,
        "solver": solver_block,
        "statement": _statement(geometry_id, particles, surrogate, solver_block),
    }


def _measured_or_not_run(label: str, entry: Mapping[str, Any], *, extra: Sequence[str], tier: str | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {}
    if tier:
        base["tier"] = tier
    if "step_times_s" in entry:
        med = _times(label, entry["step_times_s"])
        base["hardware"] = _text(label, entry, "hardware")
        for key in extra:
            base[key] = _text(label, entry, key)
        base.update({"median_step_s": med, "steps_per_s": 1.0 / med})
        return base
    reason = entry.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"{label}: give step_times_s, or a reason when it was not run")
    for key in ("hardware", *extra):
        if isinstance(entry.get(key), str) and entry[key].strip():
            base[key] = entry[key]
    base.update({"status": "not run", "reason": reason})
    return base


def _statement(geometry_id: str, particles: int, surrogate: Mapping[str, Any], solver: Mapping[str, Any]) -> str:
    parts = [f"Measured steps per second for geometry {geometry_id} with {particles} particles (median step time):"]
    cpu = surrogate["python_cpu"]
    parts.append(f"surrogate in Python on {cpu['hardware']} (CPU): {cpu['steps_per_s']:.2f} steps/s;")
    gpu = surrogate["python_gpu"]
    if "steps_per_s" in gpu:
        parts.append(f"surrogate in Python on {gpu['hardware']} (GPU): {gpu['steps_per_s']:.2f} steps/s;")
    else:
        parts.append(f"surrogate in Python on GPU: not run ({gpu['reason']});")
    for tier, entry in surrogate["browser"].items():
        where = f"{entry.get('hardware', 'unnamed hardware')}, {entry.get('browser', 'unnamed browser')}"
        if "steps_per_s" in entry:
            parts.append(f"surrogate in the browser, tier {tier} ({where}): {entry['steps_per_s']:.2f} steps/s;")
        else:
            parts.append(f"surrogate in the browser, tier {tier} ({where}): not run ({entry['reason']});")
    parts.append(f"solver on {solver['hardware']}: {solver['steps_per_s']:.2f} steps/s ({solver['wall_s_per_step']:.3f} s per step).")
    return " ".join(parts)

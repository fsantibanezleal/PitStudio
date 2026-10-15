"""Pre-flight guards (VRAM, temperature, disk, quota, capabilities) and the in-run thermal guard (FR-002-19..22, 66)."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitstudio.runner.recipe import first_errors, strict_json

GIB = 2**30


def vram_ok(free_bytes: int, vram_gib_est: float, margin_gib: float) -> bool:
    return free_bytes >= math.ceil(vram_gib_est * GIB) + margin_gib * GIB


disk_ok = vram_ok  # the same rule, for the store volume (FR-002-20)


def quota_ok(stored_bytes: int, disk_gib_est: float, quota_gib: float) -> bool:
    return stored_bytes + math.ceil(disk_gib_est * GIB) <= quota_gib * GIB


def temp_ok(temp_c: float, max_start_temp_c: float) -> bool:
    return temp_c <= max_start_temp_c


def wait_for_cooldown(read_temp: Callable[[], float], max_c: float, wait_s: float, *, clock: Any = time) -> bool:
    """Poll every 10 s for up to `wait_s` until the GPU is at most `max_c`."""
    deadline = clock.monotonic() + wait_s
    while not temp_ok(read_temp(), max_c):
        if (left := deadline - clock.monotonic()) <= 0:
            return False
        clock.sleep(min(10, left))
    return True


def capability_refusal(path: Path, requires: list[str], driver: str) -> str | None:
    """`capability`, `capability-stale` or None for the probes a stage requires (FR-002-21)."""
    try:
        doc = strict_json(path.read_text(encoding="utf-8"))
    except OSError, ValueError, RecursionError:
        return "capability"
    if first_errors("capabilities", doc, n=1):
        return "capability"
    if doc["driver"] != driver:
        return "capability-stale"
    return None if all(doc["probes"].get(p, {}).get("status") == "pass" for p in requires) else "capability"


def thresholds(repo: Path) -> dict[str, float]:
    """The `runner.*` thermal keys of thresholds.yaml when the repository has them (defaults are FR-002-66's)."""
    import yaml

    f = repo / "specs" / "000-foundation" / "thresholds.yaml"
    run = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("runner", {}) if f.is_file() else {}
    names = ("pause_c", "resume_c", "stop_c", "block_minutes", "cooldown_minutes")
    keys = ("run_pause_temp_c", "run_resume_temp_c", "run_stop_temp_c", "gpu_block_minutes", "gpu_cooldown_minutes")
    return {a: run[b] for a, b in zip(names, keys, strict=True) if b in run}


@dataclass
class ThermalDecision:
    action: str  # run | pause | stop | cooldown
    reason: str | None = None  # thermal | hw-error | block
    checkpoint: bool = False
    exit_code: int | None = None
    resume_at_s: float | None = None


class ThermalGuard:
    """FR-002-66 as a state machine, one `observe` per telemetry sample."""

    def __init__(
        self,
        pause_c=83.0,
        resume_c=75.0,
        stop_c=87.0,
        block_minutes=45.0,
        cooldown_minutes=10.0,
        supports_checkpoint=False,
    ):
        self.pause_c, self.resume_c, self.stop_c = pause_c, resume_c, stop_c
        self.block_minutes, self.cooldown_minutes, self.supports_checkpoint = (
            block_minutes,
            cooldown_minutes,
            supports_checkpoint,
        )
        self.paused, self.stopped, self.block_start, self.cool_until = False, None, None, None

    def observe(self, t_s: float, temp_c: float, hw_error: bool = False) -> ThermalDecision:
        if self.stopped is None and (hw_error or temp_c >= self.stop_c):
            self.stopped = "hw-error" if hw_error else "thermal"
        if self.stopped:
            return ThermalDecision("stop", self.stopped, self.supports_checkpoint, 5)
        if self.cool_until is not None:
            if t_s < self.cool_until:
                return ThermalDecision("cooldown", "block", resume_at_s=self.cool_until)
            self.cool_until = self.block_start = None
        self.paused = temp_c > self.resume_c if self.paused else temp_c >= self.pause_c
        self.block_start = t_s if self.block_start is None else self.block_start
        if not self.paused and t_s - self.block_start >= self.block_minutes * 60:
            self.cool_until = t_s + self.cooldown_minutes * 60
            return ThermalDecision("cooldown", "block", resume_at_s=self.cool_until)
        return ThermalDecision("pause" if self.paused else "run")

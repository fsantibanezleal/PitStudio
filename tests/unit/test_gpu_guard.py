"""The in-run GPU guard pauses a hot job, stops it at the throttle point or on a new hardware error, and ends blocks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "bench"))
import gpu_guard  # noqa: E402
from gpu_guard import Guard, GuardStop  # noqa: E402


class FakeGPU:
    """A clock and a temperature script: each read returns the next temperature; sleeping advances the clock."""

    def __init__(self, temps: list[int], whea: list[int | None] | None = None) -> None:
        self.temps, self.t, self.slept = list(temps), 0.0, 0.0
        self.whea_values = list(whea) if whea else [0]
        self.since_args: list[str | None] = []

    def read(self) -> int:
        return self.temps.pop(0) if len(self.temps) > 1 else self.temps[0]

    def whea(self, since: str | None = None) -> int | None:
        """Events created after `since` (the guard's start); None = the log query failed."""
        self.since_args.append(since)
        return self.whea_values.pop(0) if len(self.whea_values) > 1 else self.whea_values[0]

    def clock(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s
        self.slept += s


def guard(g: FakeGPU, **kw) -> Guard:
    return Guard(
        read_temp=g.read,
        whea=g.whea,
        clock=g.clock,
        sleep=g.sleep,
        log=lambda m: None,
        temp_every_s=0,
        whea_every_s=0,
        **kw,
    )


def test_cool_gpu_runs_without_pausing() -> None:
    g = FakeGPU([60])
    gd = guard(g)
    assert gd.check() == "ok"
    assert g.slept == 0


def test_hot_gpu_pauses_until_the_resume_temperature() -> None:
    g = FakeGPU([84, 82, 79, 76, 75, 70])
    gd = guard(g)
    assert gd.check() == "ok"
    assert g.slept == 4 * 5  # 84 -> paused; reads 82, 79, 76, 75 (5 s apart); resumes at 75 = RESUME_C
    assert gd.paused_s == 20


def test_stop_temperature_raises_thermal() -> None:
    gd = guard(FakeGPU([gpu_guard.STOP_C]))
    with pytest.raises(GuardStop) as e:
        gd.check()
    assert e.value.reason == "thermal"


def test_reaching_stop_while_paused_raises_thermal() -> None:
    gd = guard(FakeGPU([85, 86, 87]))
    with pytest.raises(GuardStop) as e:
        gd.check()
    assert e.value.reason == "thermal"


def test_new_whea_event_raises_hw_error() -> None:
    g = FakeGPU([60], whea=[1])  # one event created since the guard started
    gd = guard(g)
    with pytest.raises(GuardStop) as e:
        gd.check()
    assert e.value.reason == "hw-error"
    assert g.since_args  # the event log was queried
    assert g.since_args[0] == gd.since  # counted by time from the guard's start, not by log size


def test_no_new_whea_event_keeps_running() -> None:
    gd = guard(FakeGPU([60], whea=[0]))
    assert gd.check() == "ok"


def test_failed_whea_query_is_not_read_as_zero_and_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gpu_guard.sys, "platform", "win32")
    logs: list[str] = []
    g = FakeGPU([60], whea=[None])
    gd = Guard(
        read_temp=g.read, whea=g.whea, clock=g.clock, sleep=g.sleep, log=logs.append, temp_every_s=0, whea_every_s=0
    )
    assert gd.check() == "ok"
    assert gd.check() == "ok"
    assert sum("hardware-error detection unavailable" in m for m in logs) == 1  # reported once, never silent


def test_block_end_is_signalled_and_paused_time_does_not_count() -> None:
    g = FakeGPU([60])
    gd = guard(g, block_s=100, cooldown_s=30)
    g.t = 99
    assert gd.check() == "ok"
    g.t = 100
    assert gd.check() == "cooldown"
    gd.cool_down()
    assert g.slept == 30
    assert gd.check() == "ok"


def test_never_resumes_above_the_resume_temperature() -> None:
    temps = [86, 84, 80, 78, 76, 76, 75]
    g = FakeGPU(temps)
    gd = guard(g)
    gd.check()
    assert g.temps == [75]  # every reading above 75 C was consumed while paused


def test_start_limit_matches_the_runner_spec() -> None:
    assert gpu_guard.START_MAX_C == 80  # FR-002-19 / runner.max_start_temp_c
    assert gpu_guard.RESUME_C < gpu_guard.PAUSE_C < gpu_guard.STOP_C

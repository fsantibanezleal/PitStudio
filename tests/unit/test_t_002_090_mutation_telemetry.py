# ruff: noqa: PT018
"""T-002-090 (mutation run, `telemetry.py`): the reading caps, the clocks-event bits and the sampler timing.

Requirement: NFR-002-05. Added after a real mutation run (specs/002-runner/mutation.json): the survivors were
the caps of data-model 2.4, the bit values of `clocks_event_mask` and the integer fields,
which the process-level tests of T-002-050 never put on their exact boundary.

Oracles: the caps of spec 001 data-model 2.4 and the NVML clocks-event reason bits, written out again below.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from pitstudio.runner import telemetry

CAPS = {
    "util_pct": 100,
    "power_w": 10000,
    "power_limit_w": 10000,
    "temp_c": 200,
    "sm_clock_mhz": 20000,
    "nvenc_util_pct": 100,
}
INTS = {"clocks_event_mask": 2**32 - 1, "energy_mj": 2**53 - 1, "pcie_replays": 2**32 - 1}


class Backend:
    def __init__(self, values: dict[str, Any], total: int = 100) -> None:
        self.values, self.vram_total_bytes = values, total

    def read(self, field: str) -> Any:
        v = self.values[field]
        if isinstance(v, Exception):
            raise v
        return v


@pytest.mark.req("NFR-002-05")
def test_the_clocks_event_bits_are_the_nvml_reason_values() -> None:
    assert telemetry.BITS == {
        "idle": 0x1,
        "sw_power_cap": 0x4,
        "hw_slowdown": 0x8,
        "sw_thermal": 0x20,
        "hw_thermal": 0x40,
        "power_brake": 0x80,
    }


@pytest.mark.req("NFR-002-05")
def test_the_caps_and_integer_bounds_are_those_of_the_schema() -> None:
    assert telemetry.CAPS == CAPS and telemetry.INTS == INTS


@pytest.mark.req("NFR-002-05")
@pytest.mark.parametrize(("field", "cap"), sorted({**CAPS, **INTS}.items()))
def test_a_reading_is_kept_up_to_its_cap_and_dropped_beyond_it(field: str, cap: int) -> None:
    def read(value: Any) -> Any:
        return telemetry.read_sample(Backend({field: value}), field)

    assert read(cap) == cap and read(0) == 0
    assert read(cap + 1) is None and read(-1) is None and read(cap + 0.5) is None
    assert read(float("nan")) is None and read(float("inf")) is None and read(-float("inf")) is None
    assert read("5") is None and read(None) is None and read(True) is None and read([1]) is None
    assert read(ValueError("backend failed")) is None


@pytest.mark.req("NFR-002-05")
def test_integer_fields_are_rounded_and_the_others_keep_their_fraction() -> None:
    assert telemetry.read_sample(Backend({"energy_mj": 12.6}), "energy_mj") == 13
    assert isinstance(telemetry.read_sample(Backend({"energy_mj": 12.0}), "energy_mj"), int)
    assert telemetry.read_sample(Backend({"util_pct": 12.6}), "util_pct") == 12.6
    assert telemetry.clean(5.4, 10, integer=True) == 5 and telemetry.clean(5.4, 10) == 5.4
    assert telemetry.clean(10, 10) == 10 and telemetry.clean(10.0001, 10) is None
    assert telemetry.clean(0, 10) == 0 and telemetry.clean(-0.0001, 10) is None


@pytest.mark.req("NFR-002-05")
def test_the_unknown_field_of_read_sample_is_none() -> None:
    assert telemetry.read_sample(Backend({"nope": 1}), "nope") is None


class Clock:
    def __init__(self) -> None:
        self.t, self.sleeps = 100.0, []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


@pytest.mark.req("NFR-002-05")
def test_sample_loop_writes_one_flushed_row_per_period_and_counts_them(tmp_path: Any) -> None:
    import json

    values = {f: 1 for f in (*CAPS, *INTS)} | {"free_bytes": 40}
    clock, path, seen = Clock(), tmp_path / "t.jsonl", []
    stops = iter([False, False, False, True])
    n = telemetry.sample_loop(
        Backend(values),
        path,
        4.0,
        clock=clock,
        should_stop=lambda: next(stops),
        run_id="20261012T000000Z-r",
        stage={"id": "s10"},
        shard=3,
        gpu=1,
        on_sample=seen.append,
    )
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert n == 3 == len(rows) == len(seen)
    assert clock.sleeps == [0.25, 0.25, 0.25]
    assert [r["t_s"] for r in rows] == [0.0, 0.25, 0.5]
    first = rows[0]
    assert first["run_id"] == "20261012T000000Z-r" and first["stage"] == {"id": "s10"}
    assert first["shard"] == 3 and first["gpu"] == 1
    assert first["mem_used_bytes"] == 60 and first["mem_total_bytes"] == 100
    assert first["util_pct"] == 1 and first["energy_mj"] == 1


@pytest.mark.req("NFR-002-05")
def test_sample_loop_reports_unreadable_memory_as_null(tmp_path: Any) -> None:
    import json

    values = {f: 1 for f in (*CAPS, *INTS)}
    for free in (101, RuntimeError("gone")):  # more free than total, and a failing read
        path = tmp_path / f"{type(free).__name__}.jsonl"
        stops = iter([False, True])
        telemetry.sample_loop(
            Backend({**values, "free_bytes": free}),
            path,
            2.0,
            clock=Clock(),
            should_stop=lambda s=stops: next(s),
            run_id="r",
            stage={"id": "s"},
        )
        assert json.loads(path.read_text(encoding="utf-8"))["mem_used_bytes"] is None
    assert math.isfinite(0.0)

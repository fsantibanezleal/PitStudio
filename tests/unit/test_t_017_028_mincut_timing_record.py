"""T-017-028: Python min-cut wall time recorded per baked instance (unit).

Requirements: NFR-017-06.

Spec: specs/017-planning-survey/spec.md NFR-017-06: Python min-cut wall time on the reference CPU is recorded per
baked
instance; <= 60 s for 10^5 blocks with the 1:5 precedence (an estimate; an overrun is reported). Measured by the run
manifests. plan.md test strategy row NFR-017-06 / NFR-017-07: manifest fields recorded (unit).

Oracles: a fake integer-nanosecond clock (the solve function advances it by an exact number of seconds, so every
elapsed
time is exact), the 60 s bound by hand (60.0 passes, 60.001 is an overrun), and the field list below.

Expected public API (module `pitstudio.planning.timing`, root environment):
    MINCUT_BUDGET_S = 60.0
    BUDGET_BLOCKS = 100_000
    record_mincut_time(instance_id: str, n_blocks: int, solve, *, clock, cpu: str) -> dict
        calls `solve()` once, timing it with `clock.monotonic()`; returns {"instance": instance_id, "n_blocks":
        n_blocks, "wall_s": elapsed seconds, "cpu": cpu, "budget_s": 60.0, "over_budget": bool, "note": str | None}
        where over_budget is true iff n_blocks <= 100,000 and wall_s > 60.0, and `note` then says "overrun" (None
        otherwise); the result of `solve()` is returned under the key "result". ValueError for a non-positive
        n_blocks, an empty instance id, or an elapsed time that is negative or not finite (a clock that went
        backwards).
    timing_manifest_entries(records: Sequence[dict]) -> dict
        {"mincut_wall_s": {instance: wall_s ...}, "overruns": [instance ids over budget, sorted]} for the run manifest
        (no instance is dropped; duplicate instance ids raise ValueError).
"""

from __future__ import annotations

import math

import pytest
from pitstudio.planning.timing import BUDGET_BLOCKS, MINCUT_BUDGET_S, record_mincut_time, timing_manifest_entries


class FakeClock:
    def __init__(self) -> None:
        self.ns = 0

    def monotonic(self) -> float:
        return self.ns / 1e9

    def advance(self, seconds: float) -> None:
        self.ns += round(seconds * 1e9)


def _record(instance: str, n_blocks: int, seconds: float, clock: FakeClock | None = None) -> dict:
    clock = clock or FakeClock()

    def solve() -> str:
        clock.advance(seconds)
        return "pit"

    return record_mincut_time(instance, n_blocks, solve, clock=clock, cpu="Reference CPU @ 3.0 GHz")


@pytest.mark.req("NFR-017-06")
def test_the_budget_constants_are_60_seconds_for_100000_blocks() -> None:
    assert MINCUT_BUDGET_S == 60.0
    assert BUDGET_BLOCKS == 100_000


@pytest.mark.req("NFR-017-06")
def test_the_record_holds_the_instance_size_wall_time_cpu_and_the_solve_result() -> None:
    rec = _record("oreblocks-porphyry-50x50x40", 100_000, 12.5)
    assert rec["instance"] == "oreblocks-porphyry-50x50x40"
    assert rec["n_blocks"] == 100_000
    assert rec["wall_s"] == 12.5
    assert rec["cpu"] == "Reference CPU @ 3.0 GHz"
    assert rec["budget_s"] == 60.0
    assert rec["over_budget"] is False
    assert rec["note"] is None
    assert rec["result"] == "pit"


@pytest.mark.req("NFR-017-06")
@pytest.mark.parametrize(("seconds", "over"), [(59.999, False), (60.0, False), (60.001, True), (600.0, True)])
def test_an_overrun_of_the_60_second_budget_at_the_case_size_is_reported(seconds: float, over: bool) -> None:
    rec = _record("big", 100_000, seconds)
    assert rec["over_budget"] is over
    assert (rec["note"] is not None) is over
    if over:
        assert "overrun" in rec["note"]


@pytest.mark.req("NFR-017-06")
def test_the_solve_is_called_exactly_once_and_its_time_is_the_clock_difference() -> None:
    clock = FakeClock()
    clock.advance(1_000.0)  # the clock does not start at zero
    calls = {"n": 0}

    def solve() -> None:
        calls["n"] += 1
        clock.advance(3.25)

    rec = record_mincut_time("x", 10, solve, clock=clock, cpu="c")
    assert calls["n"] == 1
    assert rec["wall_s"] == 3.25


@pytest.mark.req("NFR-017-06")
@pytest.mark.parametrize(
    ("instance", "n_blocks"),
    [("", 10), ("x", 0), ("x", -5)],
)
def test_invalid_instance_arguments_are_refused_before_solving(instance: str, n_blocks: int) -> None:
    called = {"n": 0}

    def solve() -> None:
        called["n"] += 1

    with pytest.raises(ValueError, match=r"."):
        record_mincut_time(instance, n_blocks, solve, clock=FakeClock(), cpu="c")
    assert called["n"] == 0


@pytest.mark.req("NFR-017-06")
def test_a_clock_that_goes_backwards_is_refused_not_recorded_as_a_negative_time() -> None:
    clock = FakeClock()

    def solve() -> None:
        clock.advance(-1.0)

    with pytest.raises(ValueError, match=r"."):
        record_mincut_time("x", 10, solve, clock=clock, cpu="c")


@pytest.mark.req("NFR-017-06")
def test_the_manifest_entry_lists_every_baked_instance_and_its_overruns() -> None:
    records = [_record("a", 1_000, 0.5), _record("b", 100_000, 75.0), _record("c", 100_000, 40.0)]
    entry = timing_manifest_entries(records)
    assert entry["mincut_wall_s"] == {"a": 0.5, "b": 75.0, "c": 40.0}
    assert entry["overruns"] == ["b"]
    assert all(math.isfinite(v) for v in entry["mincut_wall_s"].values())


@pytest.mark.req("NFR-017-06")
def test_duplicate_instance_ids_and_an_empty_list_are_handled() -> None:
    with pytest.raises(ValueError, match=r"."):
        timing_manifest_entries([_record("a", 10, 1.0), _record("a", 10, 2.0)])
    assert timing_manifest_entries([]) == {"mincut_wall_s": {}, "overruns": []}

"""T-016-043: joules per inference and telemetry flags (unit, fake GPU, hostile, property).

Requirements: FR-016-28, FR-016-29, P-016-06.

Spec: specs/016-export-acceleration/spec.md
- FR-016-28: joules per inference = (E_end - E_start) / 1,000 / (iterations x batch) from the NVML total-energy counter
  (mJ); sample power, SM and memory clocks, temperature and clocks-event reasons at 10 Hz; flag any window with a
  hardware thermal-slowdown sample;
- FR-016-29: if the energy counter is unavailable, decreases during the window, or the window is shorter than 1 s,
  joules per inference is null with the reason;
- P-016-06: joules per inference are unchanged when the iterations and the energy difference are both multiplied by
  k, are non-negative, and scale by 10^-3 under a mJ -> J relabelling of the counter (positive counters, k in
  [1, 10^3], rtol 1e-12).
plan.md test strategy rows FR-016-28 (counter 1,000,000 -> 1,500,000 mJ over 1,000 iterations of batch 1 -> 0.5 J;
thermal-slowdown flag on one sample), FR-016-29 (no counter, a decreasing counter, a 0.9 s window -> null with reason).

Oracles: hand calculation ((1,500,000 - 1,000,000) mJ = 500 J; 500 J / 1,000 inferences = 0.5 J); the NVML header
constant of the hardware thermal-slowdown clocks-event reason, `nvmlClocksEventReasonHwThermalSlowdown` =
0x0000000000000040 (NVML API reference, clocks event reasons; the software thermal bit is 0x20, the software power cap
bit 0x4, GPU idle 0x1); P-016-06's relations; a fake integer-nanosecond clock; the backend protocol of the runner's
GPU backends: `read(field) -> float`, raising for an unsupported field (spec 002 FR-002-32).

Expected public API (module `pitstudio.accel.energy`, root environment):
    HW_THERMAL_SLOWDOWN = 0x40
    joules_per_inference(e_start_mj: float, e_end_mj: float, iterations: int, batch: int, window_s: float)
        -> EnergyResult                      # joules: float | None, reason: str | None, window_s: float
        (E_end - E_start) / 1000 / (iterations * batch) when valid; None with a reason containing "counter" for a
        non-finite or decreasing counter and "window" for a window shorter than 1 s (a window of exactly 1.0 s is
        valid); raises ValueError for iterations <= 0 or batch <= 0.
    measure_energy(backend, clock, run, *, iterations: int, batch: int) -> EnergyResult
        reads backend.read("energy_mj") before and after calling `run()` `iterations` times (run advances the clock),
        window_s = clock.monotonic() difference; when the read raises or returns a non-finite value, joules None and
        reason contains "counter" and "unavailable".
    sample_telemetry(backend, clock, *, duration_s: float, hz: float = 10.0) -> list[dict]
        samples every 1/hz seconds on the clock (clock.sleep between samples): {"t": s since start, "power_w",
        "sm_clock_mhz", "mem_clock_mhz", "temp_c", "clocks_event_mask"}; a field the backend cannot read is None;
        length within floor(duration_s * hz) +/- 1.
    thermal_slowdown(samples: Sequence[Mapping]) -> bool
        True iff any sample's clocks_event_mask has the HW_THERMAL_SLOWDOWN bit; None masks are ignored.
"""

from __future__ import annotations

import itertools
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.accel.energy import (
    HW_THERMAL_SLOWDOWN,
    joules_per_inference,
    measure_energy,
    sample_telemetry,
    thermal_slowdown,
)


class FakeClock:
    def __init__(self) -> None:
        self.ns = 0

    def monotonic(self) -> float:
        return self.ns / 1e9

    def advance(self, seconds: float) -> None:
        self.ns += round(seconds * 1e9)

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)


class FakeBackend:
    """read(field) like the runner's backends; `values` maps a field to a constant or a list consumed in order."""

    def __init__(self, values: dict, unsupported: set[str] | None = None) -> None:
        self.values, self.unsupported = (
            {k: list(v) if isinstance(v, list) else v for k, v in values.items()},
            (unsupported or set()),
        )

    def read(self, field: str) -> float:
        if field in self.unsupported or field not in self.values:
            raise RuntimeError(f"{field} is not supported by this device")
        v = self.values[field]
        return v.pop(0) if isinstance(v, list) else v


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-28
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-28")
def test_half_a_joule_per_inference_by_hand() -> None:
    r = joules_per_inference(1_000_000, 1_500_000, iterations=1000, batch=1, window_s=2.5)
    assert r.joules == 0.5
    assert r.reason is None
    assert r.window_s == 2.5


@pytest.mark.req("FR-016-28")
def test_batch_and_iterations_divide_the_energy() -> None:
    # 2,000,000 mJ = 2,000 J over 100 iterations x 20 samples = 2,000 inferences -> 1 J each
    assert joules_per_inference(0, 2_000_000, iterations=100, batch=20, window_s=3.0).joules == 1.0
    # zero energy used is a valid, non-negative result
    assert joules_per_inference(5, 5, iterations=10, batch=1, window_s=2.0).joules == 0.0


@pytest.mark.req("FR-016-28")
def test_measure_energy_reads_the_counter_around_the_run_and_uses_the_clock_window() -> None:
    clock = FakeClock()
    backend = FakeBackend({"energy_mj": [1_000_000, 1_500_000]})

    def run() -> None:
        clock.advance(0.0025)  # 1,000 iterations x 2.5 ms = 2.5 s window

    r = measure_energy(backend, clock, run, iterations=1000, batch=1)
    assert r.joules == pytest.approx(0.5, rel=1e-12)
    assert r.window_s == pytest.approx(2.5, rel=1e-12)
    assert r.reason is None


@pytest.mark.req("FR-016-28")
def test_telemetry_is_sampled_at_10_hz_with_every_field() -> None:
    clock = FakeClock()
    backend = FakeBackend(
        {"power_w": 91.5, "sm_clock_mhz": 2100.0, "mem_clock_mhz": 8000.0, "temp_c": 66.0, "clocks_event_mask": 0.0}
    )
    samples = sample_telemetry(backend, clock, duration_s=3.2)
    assert 31 <= len(samples) <= 33  # floor(3.2 x 10) +/- 1
    assert all(
        set(s) >= {"t", "power_w", "sm_clock_mhz", "mem_clock_mhz", "temp_c", "clocks_event_mask"} for s in samples
    )
    assert samples[0]["power_w"] == 91.5
    gaps = [b["t"] - a["t"] for a, b in itertools.pairwise(samples)]
    assert all(g == pytest.approx(0.1, abs=1e-9) for g in gaps)
    assert not thermal_slowdown(samples)


@pytest.mark.req("FR-016-28")
def test_an_unsupported_telemetry_field_is_none_not_guessed() -> None:
    clock = FakeClock()
    backend = FakeBackend({"power_w": 90.0, "temp_c": 60.0, "clocks_event_mask": 0.0}, unsupported={"mem_clock_mhz"})
    samples = sample_telemetry(backend, clock, duration_s=1.0)
    assert all(s["mem_clock_mhz"] is None for s in samples)
    assert all(s["power_w"] == 90.0 for s in samples)


@pytest.mark.req("FR-016-28")
def test_the_nvml_hardware_thermal_slowdown_bit_is_0x40() -> None:
    assert HW_THERMAL_SLOWDOWN == 0x40


@pytest.mark.req("FR-016-28")
@pytest.mark.parametrize(
    ("masks", "flagged"),
    [
        ([0, 0, 0], False),
        ([0, 0x40, 0], True),
        ([0x1], False),
        ([0x4], False),
        ([0x40 | 0x4], True),
        ([0x2, 0x8], False),
    ],
)
def test_a_window_is_flagged_when_any_sample_has_the_hardware_thermal_slowdown_reason(masks, flagged) -> None:
    samples = [{"t": i * 0.1, "clocks_event_mask": m} for i, m in enumerate(masks)]
    assert thermal_slowdown(samples) is flagged


@pytest.mark.req("FR-016-28")
def test_none_masks_are_ignored_by_the_thermal_flag() -> None:
    assert thermal_slowdown([{"clocks_event_mask": None}, {"clocks_event_mask": 0x40}]) is True
    assert thermal_slowdown([{"clocks_event_mask": None}]) is False
    assert thermal_slowdown([]) is False


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-29
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-29")
def test_an_unavailable_counter_gives_null_joules_with_the_reason() -> None:
    clock = FakeClock()
    backend = FakeBackend({}, unsupported={"energy_mj"})

    def run() -> None:
        clock.advance(0.005)

    r = measure_energy(backend, clock, run, iterations=1000, batch=1)
    assert r.joules is None
    assert "counter" in r.reason
    assert "unavailable" in r.reason


@pytest.mark.req("FR-016-29")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -5.0])
def test_a_non_finite_or_negative_counter_value_gives_null_joules(bad: float) -> None:
    r = joules_per_inference(bad, 1_500_000, iterations=1000, batch=1, window_s=2.5)
    assert r.joules is None
    assert "counter" in r.reason
    r2 = joules_per_inference(1_000_000, bad, iterations=1000, batch=1, window_s=2.5)
    assert r2.joules is None


@pytest.mark.req("FR-016-29")
def test_a_counter_that_decreases_during_the_window_gives_null_joules_with_the_reason() -> None:
    r = joules_per_inference(1_500_000, 1_000_000, iterations=1000, batch=1, window_s=2.5)
    assert r.joules is None
    assert "counter" in r.reason
    assert "decreas" in r.reason


@pytest.mark.req("FR-016-29")
@pytest.mark.parametrize(
    ("window_s", "valid"), [(0.9, False), (0.999999, False), (1.0, True), (1.1, True), (0.0, False)]
)
def test_a_window_shorter_than_one_second_gives_null_joules_with_the_reason(window_s: float, valid: bool) -> None:
    r = joules_per_inference(1_000_000, 1_500_000, iterations=1000, batch=1, window_s=window_s)
    assert (r.joules is not None) is valid
    if not valid:
        assert r.joules is None
        assert "window" in r.reason


@pytest.mark.req("FR-016-29")
def test_measure_energy_with_a_short_window_gives_null_with_the_reason() -> None:
    clock = FakeClock()
    backend = FakeBackend({"energy_mj": [1_000_000, 1_500_000]})

    def run() -> None:
        clock.advance(0.0009)  # 1,000 x 0.9 ms = 0.9 s

    r = measure_energy(backend, clock, run, iterations=1000, batch=1)
    assert r.joules is None
    assert "window" in r.reason


@pytest.mark.req("FR-016-29")
@pytest.mark.parametrize(("iterations", "batch"), [(0, 1), (1, 0), (-5, 1), (10, -1)])
def test_non_positive_iterations_or_batch_are_refused(iterations: int, batch: int) -> None:
    with pytest.raises(ValueError, match=r"."):
        joules_per_inference(0, 10, iterations=iterations, batch=batch, window_s=2.0)


# ----------------------------------------------------------------------------------------------------------------------
# P-016-06
# ----------------------------------------------------------------------------------------------------------------------

counter = st.floats(min_value=0, max_value=1e12, allow_nan=False, allow_infinity=False)


@pytest.mark.req("P-016-06")
@settings(max_examples=200, deadline=None)
@given(
    e0=counter,
    delta=st.floats(0, 1e9),
    iterations=st.integers(1, 10**6),
    batch=st.integers(1, 4096),
    k=st.integers(1, 1000),
)
def test_joules_are_unchanged_when_iterations_and_energy_difference_are_scaled_together(
    e0, delta, iterations, batch, k
):
    a = joules_per_inference(e0, e0 + delta, iterations=iterations, batch=batch, window_s=2.0)
    # the exact difference actually seen by the function, scaled by k with the iterations
    d = (e0 + delta) - e0
    b = joules_per_inference(0.0, d * k, iterations=iterations * k, batch=batch, window_s=2.0)
    assert a.joules is not None
    assert a.joules >= 0.0
    assert b.joules == pytest.approx(a.joules, rel=1e-12, abs=0.0) or (a.joules == 0.0 and b.joules == 0.0)


@pytest.mark.req("P-016-06")
@settings(max_examples=200, deadline=None)
@given(
    e0=counter,
    delta=st.floats(1.0, 1e9),
    iterations=st.integers(1, 10**6),
    batch=st.integers(1, 4096),
)
def test_joules_scale_by_1e_minus_3_under_the_mj_to_j_relabelling(e0, delta, iterations, batch):
    r = joules_per_inference(e0, e0 + delta, iterations=iterations, batch=batch, window_s=2.0)
    raw_per_inference = ((e0 + delta) - e0) / (iterations * batch)  # the counter difference per inference, unit-free
    assert r.joules == pytest.approx(1e-3 * raw_per_inference, rel=1e-12)
    assert math.isfinite(r.joules)

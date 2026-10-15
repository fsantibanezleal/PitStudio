"""T-016-042: latency and throughput protocol, statistics, hostile measurements (unit, fake clock, hostile).

Requirements: FR-016-26, FR-016-27, FR-016-36.

Spec: specs/016-export-acceleration/spec.md
- FR-016-26: in latency mode, batch 1, a warm-up of >= 5 s and >= 10 iterations, then time until 1,000 iterations or
  30 s have elapsed, whichever comes first, but never fewer than 50 iterations, in two regimes (spaced: a 200 ms
  untimed gap between calls; sustained: back to back) and two scopes (GPU compute timed with CUDA events; end to end,
  host to device and back, timed with the host clock), reporting p50, p90, p95 and p99 (linear interpolation) with 95 %
  percentile bootstrap intervals (B = 2,000, seeded, resampling the sorted sample);
- FR-016-27: in throughput mode, sweep batch sizes {1, 4, 16, 64} for vision models, {1, 64, 4096} for policies and
  particle counts {1,000, 2,000, 10,000} for the GNS, reporting samples per second as batch x iterations / elapsed
  seconds;
- FR-016-36: a bench measurement with a non-finite or negative duration, or a record naming a backend or precision
  outside its enum, is discarded with the reason and the cell keeps the status "rejected (invalid measurement)".
plan.md test strategy rows FR-016-26 (fake clock: 20 ms -> 1,000 iterations; 100 ms -> 300 iterations; 1 s -> 50
iterations; `numpy.percentile(method="linear")`), FR-016-27 (batch 16 x 100 iterations in 2 s -> 800 samples/s),
FR-016-36 (NaN and negative durations, backend `tensorrt-rtx-2`, precision `int4`).

Oracles: a fake integer-nanosecond clock (so that every elapsed time is exact), the iteration counts above by hand,
`numpy.percentile(..., method="linear")` as the reference percentile, the hand percentiles of the sample 1..100
(position (n - 1) q gives 50.5, 90.1, 95.05 and 99.01; see the test), and an independent numpy bootstrap of the
median for a sample of 500 values (the implementation's 95 % interval must agree with the reference interval within
the Monte Carlo error: 20 % of the interval width).

Expected public API (root environment, pure Python and numpy; the CUDA events and NVML sit behind the adapters):
module `pitstudio.accel.stats`
    class InvalidMeasurement(ValueError)     # `.reason: str`, contains "invalid measurement"
    percentiles(samples_ms: Sequence[float]) -> dict[str, float]          # keys p50, p90, p95, p99 (linear)
    latency_stats(samples_ms: Sequence[float], *, resamples: int = 2000, seed: int = 0, level: float = 0.95) -> dict
        {"p50": {"value_ms", "lo_ms", "hi_ms"}, "p90": ..., "p95": ..., "p99": ...,
         "bootstrap": {"resamples": resamples, "seed": seed, "level": level}}; the interval is the percentile
        bootstrap of the statistic over `resamples` resamples (with replacement, size n) of the SORTED sample drawn
        with `numpy.random.default_rng(seed)`, taking the (1-level)/2 and (1+level)/2 percentiles; raises
        InvalidMeasurement for an empty sample, a non-finite or negative value.
module `pitstudio.accel.timing`
    run_latency(call, *, clock, regime: str, scope: str, seed: int = 0, resamples: int = 2000) -> LatencyResult
        `clock` offers monotonic() -> float (seconds) and sleep(seconds). `call()` performs one inference; for scope
        "gpu-compute" it returns the CUDA-event duration in ms, for "end-to-end" its return value is ignored and the
        duration is the host-clock difference around the call. regime "spaced" sleeps 0.2 s between calls (never
        inside a sample), "sustained" does not.
        LatencyResult: status "ok" | "rejected", reason (None when ok, "invalid measurement: ..." otherwise),
        regime, scope, gap_ms (200 or 0), warmup_s, warmup_iterations, iterations (timed), timed_s (host-clock span
        of the timed phase, gaps included), samples_ms (list, len == iterations), stats (latency_stats result, None
        when rejected). Warm-up: at least 5 s and at least 10 calls. Timed phase: stop when iterations >= 1000, or
        when timed_s >= 30 and iterations >= 50. A rejected result is returned (no exception) when any sample is
        non-finite or negative.
    sweep_plan(kind: str) -> tuple[str, tuple[int, ...]]
        "vision" -> ("batch", (1, 4, 16, 64)); "policy" -> ("batch", (1, 64, 4096)); "gns" -> ("particles",
        (1000, 2000, 10000)); other kinds raise ValueError.
    run_throughput(call, *, clock, sizes: Sequence[int], iterations: int, sweep: str = "batch") -> ThroughputResult
        `call(size)` runs one iteration of that size. ThroughputResult: status "ok" | "rejected", reason, entries: list
        of {"sweep", "size", "iterations", "elapsed_s", "samples_per_s"} with samples_per_s = size * iterations /
        elapsed_s (elapsed = host-clock span of the `iterations` calls); a non-positive or non-finite elapsed time
        gives status "rejected" with "invalid measurement" in the reason.
module `pitstudio.accel.records`
    class InvalidRecord(ValueError)          # `.reason: str`
    check_cell_key(backend: str, precision: str) -> None
        backend in {pytorch, ort-cpu, ort-cuda, ort-tensorrt, tensorrt, tensorrt-rtx}; precision in {fp32, fp16,
        int8, fp8}; anything else raises InvalidRecord (reason contains "invalid measurement").
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from pitstudio.accel.records import InvalidRecord, check_cell_key
from pitstudio.accel.stats import InvalidMeasurement, latency_stats, percentiles
from pitstudio.accel.timing import run_latency, run_throughput, sweep_plan


class FakeClock:
    """Integer nanoseconds: every advance and every elapsed time is exact."""

    def __init__(self) -> None:
        self.ns = 0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.ns / 1e9

    def advance(self, seconds: float) -> None:
        self.ns += round(seconds * 1e9)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)


def _sustained(duration_s: float, **kw):
    clock = FakeClock()
    calls = {"n": 0}

    def call():
        calls["n"] += 1
        clock.advance(duration_s)

    result = run_latency(call, clock=clock, regime="sustained", scope="end-to-end", **kw)
    return result, calls["n"], clock


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-26: iteration rule
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-26")
@pytest.mark.parametrize(
    ("duration_s", "iterations", "timed_s"),
    [(0.020, 1000, 20.0), (0.100, 300, 30.0), (1.0, 50, 50.0)],
)
def test_iteration_count_follows_1000_or_30_s_with_a_floor_of_50(duration_s, iterations, timed_s) -> None:
    result, calls, _ = _sustained(duration_s)
    assert result.status == "ok"
    assert result.iterations == iterations
    assert result.timed_s == pytest.approx(timed_s, abs=1e-9)
    assert len(result.samples_ms) == iterations
    assert all(s == pytest.approx(duration_s * 1000) for s in result.samples_ms)
    assert calls == result.warmup_iterations + iterations  # every call is either warm-up or timed


@pytest.mark.req("FR-016-26")
@pytest.mark.parametrize("duration_s", [0.020, 0.100, 1.0])
def test_warm_up_lasts_at_least_5_seconds_and_10_calls(duration_s: float) -> None:
    result, _, _ = _sustained(duration_s)
    assert result.warmup_s >= 5.0
    assert result.warmup_iterations >= 10


@pytest.mark.req("FR-016-26")
def test_warm_up_calls_are_not_timed_samples() -> None:
    clock = FakeClock()
    calls = {"n": 0}

    def call():
        calls["n"] += 1
        clock.advance(0.5 if calls["n"] <= 10 else 0.02)  # slow first 10 calls (the warm-up), then 20 ms

    result = run_latency(call, clock=clock, regime="sustained", scope="end-to-end")
    assert max(result.samples_ms) == pytest.approx(20.0)  # the slow warm-up calls never reach the sample


@pytest.mark.req("FR-016-26")
def test_spaced_regime_sleeps_200_ms_between_calls_and_the_gap_is_not_inside_a_sample() -> None:
    clock = FakeClock()

    def call():
        clock.advance(0.05)

    result = run_latency(call, clock=clock, regime="spaced", scope="end-to-end")
    assert result.gap_ms == 200
    assert result.status == "ok"
    assert all(s == pytest.approx(50.0) for s in result.samples_ms)  # the gap is untimed
    assert 0.2 in clock.sleeps
    assert set(clock.sleeps) == {0.2}
    # 0.25 s per iteration including the gap: 30 s is reached after 120 iterations, or 121 when the gap after the last
    # call is not counted before the stop test; both orderings satisfy FR-016-26
    assert result.iterations in (120, 121)
    assert result.timed_s >= 29.8


@pytest.mark.req("FR-016-26")
def test_sustained_regime_never_sleeps() -> None:
    _, _, clock = _sustained(0.02)
    assert clock.sleeps == []


@pytest.mark.req("FR-016-26")
def test_gpu_compute_scope_uses_the_cuda_event_durations_end_to_end_uses_the_host_clock() -> None:
    clock = FakeClock()

    def call():
        clock.advance(0.005)  # 5 ms on the host clock
        return 3.0  # the CUDA events measured 3 ms of GPU compute

    gpu = run_latency(call, clock=clock, regime="sustained", scope="gpu-compute")
    e2e = run_latency(call, clock=clock, regime="sustained", scope="end-to-end")
    assert gpu.scope == "gpu-compute"
    assert all(s == pytest.approx(3.0) for s in gpu.samples_ms)
    assert all(s == pytest.approx(5.0) for s in e2e.samples_ms)
    assert gpu.iterations == 1000  # 1,000 iterations x 5 ms on the host clock = 5 s < 30 s


@pytest.mark.req("FR-016-26")
def test_the_result_carries_four_percentiles_with_intervals_and_the_bootstrap_settings() -> None:
    result, _, _ = _sustained(0.02, seed=7)
    for key in ("p50", "p90", "p95", "p99"):
        entry = result.stats[key]
        assert entry["lo_ms"] <= entry["value_ms"] <= entry["hi_ms"]
        assert entry["value_ms"] == pytest.approx(20.0)
    assert result.stats["bootstrap"] == {"resamples": 2000, "seed": 7, "level": 0.95}


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-26: statistics
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-26")
def test_percentiles_of_1_to_100_by_the_linear_rule_by_hand() -> None:
    # linear interpolation: position (n - 1) q = 99 q on the sorted sample 1..100, value = 1 + position
    got = percentiles([float(i) for i in range(100, 0, -1)])  # unsorted input
    assert got["p50"] == pytest.approx(50.5, rel=1e-12)  # position 49.5
    assert got["p90"] == pytest.approx(90.1, rel=1e-12)  # position 89.1
    assert got["p95"] == pytest.approx(95.05, rel=1e-12)  # position 94.05
    assert got["p99"] == pytest.approx(99.01, rel=1e-12)  # position 98.01


@pytest.mark.req("FR-016-26")
def test_percentiles_agree_with_numpy_linear_on_random_samples() -> None:
    rng = np.random.default_rng(3)
    for n in (50, 77, 1000, 5000):
        x = rng.lognormal(1.0, 0.5, n)
        got = percentiles(x.tolist())
        for key, q in (("p50", 50), ("p90", 90), ("p95", 95), ("p99", 99)):
            assert got[key] == pytest.approx(float(np.percentile(x, q, method="linear")), rel=1e-12)


@pytest.mark.req("FR-016-26")
def test_bootstrap_is_seeded_deterministic_and_records_its_settings() -> None:
    x = np.random.default_rng(1).lognormal(1.0, 0.5, 300).tolist()
    a = latency_stats(x, seed=11)
    assert a == latency_stats(x, seed=11)
    assert a["bootstrap"] == {"resamples": 2000, "seed": 11, "level": 0.95}
    assert a != latency_stats(x, seed=12)  # a different seed changes the intervals (not the point values)
    assert a["p50"]["value_ms"] == latency_stats(x, seed=12)["p50"]["value_ms"]


@pytest.mark.req("FR-016-26")
def test_a_constant_sample_has_zero_width_intervals() -> None:
    s = latency_stats([4.25] * 60, seed=0)
    for key in ("p50", "p90", "p95", "p99"):
        assert (s[key]["lo_ms"], s[key]["value_ms"], s[key]["hi_ms"]) == (4.25, 4.25, 4.25)


@pytest.mark.req("FR-016-26")
def test_the_median_interval_agrees_with_an_independent_percentile_bootstrap() -> None:
    x = np.sort(np.random.default_rng(5).exponential(10.0, 500))
    ref_rng = np.random.default_rng(123)
    boots = np.median(x[ref_rng.integers(0, x.size, size=(20000, x.size))], axis=1)
    ref_lo, ref_hi = np.percentile(boots, [2.5, 97.5])
    got = latency_stats(x.tolist(), seed=9)["p50"]
    width = ref_hi - ref_lo
    assert got["lo_ms"] == pytest.approx(ref_lo, abs=0.2 * width)
    assert got["hi_ms"] == pytest.approx(ref_hi, abs=0.2 * width)
    assert got["lo_ms"] < got["value_ms"] < got["hi_ms"]


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-27: throughput
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-27")
def test_sweep_plans_by_model_kind() -> None:
    assert sweep_plan("vision") == ("batch", (1, 4, 16, 64))
    assert sweep_plan("policy") == ("batch", (1, 64, 4096))
    assert sweep_plan("gns") == ("particles", (1000, 2000, 10000))
    with pytest.raises(ValueError, match=r"."):
        sweep_plan("audio")


@pytest.mark.req("FR-016-27")
def test_batch_16_for_100_iterations_in_2_seconds_is_800_samples_per_second() -> None:
    clock = FakeClock()

    def call(size: int) -> None:
        clock.advance(0.02)  # 100 iterations x 20 ms = 2 s

    result = run_throughput(call, clock=clock, sizes=[16], iterations=100)
    assert result.status == "ok"
    (entry,) = result.entries
    assert entry == {"sweep": "batch", "size": 16, "iterations": 100, "elapsed_s": 2.0, "samples_per_s": 800.0}


@pytest.mark.req("FR-016-27")
def test_every_size_of_the_sweep_is_measured_in_order_with_its_own_elapsed_time() -> None:
    clock = FakeClock()

    def call(size: int) -> None:
        clock.advance(0.001 * size)  # a call takes 1 ms per sample

    result = run_throughput(call, clock=clock, sizes=[1000, 2000, 10000], iterations=10, sweep="particles")
    assert [e["size"] for e in result.entries] == [1000, 2000, 10000]
    assert all(e["sweep"] == "particles" for e in result.entries)
    # elapsed = 10 x 0.001 x size; throughput = size x 10 / elapsed = 1000 samples/s for every size
    for e in result.entries:
        assert e["samples_per_s"] == pytest.approx(1000.0, rel=1e-12)


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-36: hostile measurements
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-36")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), -0.5])
def test_a_non_finite_or_negative_cuda_event_duration_rejects_the_cell(bad: float) -> None:
    clock = FakeClock()
    calls = {"n": 0}

    def call():
        calls["n"] += 1
        clock.advance(0.005)
        return bad if calls["n"] % 100 == 0 else 3.0  # a bad measurement every 100 calls, in any phase

    result = run_latency(call, clock=clock, regime="sustained", scope="gpu-compute")
    assert result.status == "rejected"
    assert "invalid measurement" in result.reason
    assert result.stats is None


@pytest.mark.req("FR-016-36")
def test_a_negative_host_clock_duration_rejects_the_cell() -> None:
    clock = FakeClock()
    calls = {"n": 0}

    def call():
        calls["n"] += 1
        clock.advance(-0.002 if calls["n"] % 100 == 0 else 0.005)  # the clock steps back every 100 calls

    result = run_latency(call, clock=clock, regime="sustained", scope="end-to-end")
    assert result.status == "rejected"
    assert "invalid measurement" in result.reason


@pytest.mark.req("FR-016-36")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_latency_stats_refuses_bad_samples_with_the_reason(bad: float) -> None:
    with pytest.raises(InvalidMeasurement) as info:
        latency_stats([1.0, 2.0, bad, 3.0])
    assert "invalid measurement" in info.value.reason
    with pytest.raises(InvalidMeasurement):
        latency_stats([])


@pytest.mark.req("FR-016-36")
def test_a_throughput_run_with_no_elapsed_time_is_rejected_not_infinite() -> None:
    clock = FakeClock()
    result = run_throughput(lambda size: None, clock=clock, sizes=[1], iterations=10)  # the clock never moves
    assert result.status == "rejected"
    assert "invalid measurement" in result.reason
    assert not any(math.isinf(e.get("samples_per_s", 0.0)) for e in result.entries)


@pytest.mark.req("FR-016-36")
@pytest.mark.parametrize(
    ("backend", "precision"),
    [
        ("tensorrt-rtx-2", "fp16"),
        ("tensorrt", "int4"),
        ("TensorRT", "fp32"),
        ("tensorrt", "FP16"),
        ("", "fp32"),
        ("tensorrt", ""),
    ],
)
def test_a_backend_or_precision_outside_its_enum_is_discarded_with_the_reason(backend: str, precision: str) -> None:
    with pytest.raises(InvalidRecord) as info:
        check_cell_key(backend, precision)
    assert "invalid measurement" in info.value.reason


@pytest.mark.req("FR-016-36")
@pytest.mark.parametrize("backend", ["pytorch", "ort-cpu", "ort-cuda", "ort-tensorrt", "tensorrt", "tensorrt-rtx"])
@pytest.mark.parametrize("precision", ["fp32", "fp16", "int8", "fp8"])
def test_every_enumerated_backend_and_precision_is_accepted(backend: str, precision: str) -> None:
    assert check_cell_key(backend, precision) is None

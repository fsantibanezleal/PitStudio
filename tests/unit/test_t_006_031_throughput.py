# ruff: noqa: E501, PT018
"""T-006-031: throughput per unit kind, omission on bad counts or times, scaling relations.

Requirements: FR-006-18, FR-006-19, P-006-07.

Spec: specs/006-media-telemetry/spec.md FR-006-18 (every studio GPU stage reports a throughput {value, unit} equal to its work count
divided by the wall time of its compute loop (excluding input and output): particle-steps/s for DEM, MPM and dust, cell-steps/s for
shallow water, vehicle-steps/s for vehicles, frames/s for encodes (encoded frames of the final settings divided by their encode time)),
FR-006-19 (if the work count or the measured time is zero, negative or not finite, the stage omits the throughput, never reports a guessed
or zero value, and names the reason in its result message) and P-006-07 (multiplying the work count by k multiplies the throughput by k;
multiplying the measured time by k divides it by k; the throughput of a stage split into two parts of equal duration is the mean of their
throughputs; counts 1 to 10^15, times 10^-3 to 10^5 s; rtol 1e-12).

Oracle: hand calculation (20,000 particles x 5,000 steps = 10^8 particle-steps in 4 s is 2.5 x 10^7 particle-steps/s, and so on for each kind,
written out below); a fake clock; for the encode stage the fake FFmpeg moves the clock by frames / rate (3 / 200 s and 3 / 400 s), so the
six final-setting frames took 0.0225 s and the throughput is 6 / 0.0225 = 266.666... frames/s; the relations of P-006-07 stated in the spec.

Expected API of the implementation (module `pitstudio_studio.telemetry.throughput`):
    UNITS: dict[str, str]   {"dem": "particle-steps/s", "mpm": "particle-steps/s", "dust": "particle-steps/s", "shallow-water": "cell-steps/s",
                             "vehicles": "vehicle-steps/s", "encode": "frames/s"}
    work_count(kind: str, *, items: int, steps: int = 1) -> int     items x steps (particles, cells or vehicles times steps); for kind "encode"
                             the number of frames (`steps` must be 1); ValueError for an unknown kind, a non-positive or non-integer count
    ComputeTimer(clock)     `with timer.loop():` adds the clock time spent inside to `timer.seconds` (also when the body raises; the exception
                             propagates); time outside the loops (input, output) is never counted; loops may be repeated and add up
    measure(kind: str, work: float, seconds: float) -> Measurement
        Measurement(throughput: dict | None, reason: str | None); throughput == {"value": work / seconds, "unit": UNITS[kind]} (one float64
        division) or None with a reason when `work` or `seconds` is zero, negative or not finite; the reason names `work` and/or `time`;
        ValueError for an unknown kind
    result_fields(kind: str, work: float, seconds: float) -> dict
        the stage-result fragment: {"throughput": {...}} or, when omitted, {"message": <the reason>} (one line, 1 to 300 characters);
        never a key `throughput` with a guessed or zero value
    encode.run(...) reports `throughput` {"value": total final-setting frames / total final-setting encode seconds, "unit": "frames/s"}
        (both variants together); on a zero encode time it omits `throughput` and puts the reason in `message`.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit as kit
from pitstudio_studio.telemetry.throughput import UNITS, ComputeTimer, measure, result_fields, work_count

SETTINGS = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@pytest.mark.req("FR-006-18")
def test_units_per_kind():
    assert UNITS == {
        "dem": "particle-steps/s",
        "mpm": "particle-steps/s",
        "dust": "particle-steps/s",
        "shallow-water": "cell-steps/s",
        "vehicles": "vehicle-steps/s",
        "encode": "frames/s",
    }


@pytest.mark.req("FR-006-18")
@pytest.mark.parametrize(
    ("kind", "items", "steps", "seconds", "value", "unit"),
    [
        ("dem", 20_000, 5_000, 4.0, 2.5e7, "particle-steps/s"),  # 10^8 particle-steps / 4 s
        ("mpm", 1_000_000, 100, 2.0, 5.0e7, "particle-steps/s"),  # 10^8 / 2
        ("dust", 4_096, 250, 0.5, 2_048_000.0, "particle-steps/s"),  # 1,024,000 / 0.5
        ("shallow-water", 512 * 512, 400, 8.0, 13_107_200.0, "cell-steps/s"),  # 104,857,600 / 8
        ("vehicles", 40, 28_800, 1.0, 1_152_000.0, "vehicle-steps/s"),  # 40 vehicles x 8 h at 1 s steps
    ],
)
def test_throughput_is_work_over_compute_loop_time(kind, items, steps, seconds, value, unit):
    w = work_count(kind, items=items, steps=steps)
    assert w == items * steps
    m = measure(kind, w, seconds)
    assert m.reason is None and m.throughput == {"value": value, "unit": unit}
    assert result_fields(kind, w, seconds) == {"throughput": {"value": value, "unit": unit}}


@pytest.mark.req("FR-006-18")
def test_encode_throughput_counts_frames():
    assert work_count("encode", items=300) == 300
    assert measure("encode", 300, 1.5).throughput == {"value": 200.0, "unit": "frames/s"}


@pytest.mark.req("FR-006-18")
@pytest.mark.parametrize(
    ("kind", "kwargs"),
    [
        ("nope", {"items": 1}),
        ("dem", {"items": 0}),
        ("dem", {"items": -1}),
        ("dem", {"items": 1.5}),
        ("dem", {"items": 1, "steps": 0}),
        ("encode", {"items": 3, "steps": 2}),
    ],
)
def test_work_count_rejects_unknown_kinds_and_bad_counts(kind, kwargs):
    with pytest.raises(ValueError):  # noqa: PT011
        work_count(kind, **kwargs)


@pytest.mark.req("FR-006-18")
def test_the_compute_loop_excludes_input_and_output():
    clock = kit.FakeClock()
    timer = ComputeTimer(clock)
    clock.advance(5.0)  # reading the input
    with timer.loop():
        clock.advance(4.0)
    clock.advance(7.0)  # writing the output
    with timer.loop():  # a second loop adds up
        clock.advance(0.5)
    assert timer.seconds == pytest.approx(4.5, abs=1e-12)
    assert measure("dem", 90.0, timer.seconds).throughput["value"] == pytest.approx(20.0)


@pytest.mark.req("FR-006-18")
def test_the_timer_counts_a_raising_loop_and_lets_the_exception_through():
    clock = kit.FakeClock()
    timer = ComputeTimer(clock)

    def body():
        with timer.loop():
            clock.advance(2.0)
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        body()
    assert timer.seconds == pytest.approx(2.0)


# ---------------------------------------------------------------------------------------------------------------------
# FR-006-19: omission
# ---------------------------------------------------------------------------------------------------------------------
BAD = [0, 0.0, -1, -1e-300, float("nan"), float("inf"), float("-inf")]


@pytest.mark.req("FR-006-19")
@pytest.mark.parametrize("bad", BAD)
def test_a_bad_work_count_omits_the_throughput_and_names_the_work(bad):
    m = measure("dem", bad, 2.0)
    assert m.throughput is None and m.reason and "work" in m.reason.lower()
    fields = result_fields("dem", bad, 2.0)
    assert (
        "throughput" not in fields
        and fields["message"] == m.reason
        and 1 <= len(fields["message"]) <= 300
        and "\n" not in fields["message"]
    )


@pytest.mark.req("FR-006-19")
@pytest.mark.parametrize("bad", BAD)
def test_a_bad_time_omits_the_throughput_and_names_the_time(bad):
    m = measure("dem", 1000.0, bad)
    assert m.throughput is None and m.reason and "time" in m.reason.lower()
    fields = result_fields("dem", 1000.0, bad)
    assert "throughput" not in fields and fields["message"] == m.reason


@pytest.mark.req("FR-006-19")
def test_both_bad_names_both():
    m = measure("encode", 0, float("nan"))
    assert m.throughput is None and "work" in m.reason.lower() and "time" in m.reason.lower()


@pytest.mark.req("FR-006-19")
def test_never_a_zero_or_guessed_value_even_for_tiny_but_valid_numbers():
    m = measure(
        "dem", 1.0, 1e300
    )  # valid inputs: a tiny positive value is reported as it is, not rounded to zero or omitted
    assert m.throughput == {"value": 1e-300, "unit": "particle-steps/s"}


@pytest.mark.req("FR-006-19")
def test_unknown_kind_is_a_value_error():
    with pytest.raises(ValueError):  # noqa: PT011
        measure("warp-drive", 1.0, 1.0)


# ---------------------------------------------------------------------------------------------------------------------
# P-006-07
# ---------------------------------------------------------------------------------------------------------------------
COUNTS = st.integers(1, 10**15).map(float)
TIMES = st.floats(1e-3, 1e5, allow_nan=False, allow_infinity=False)
KINDS = st.sampled_from(sorted(UNITS))


def value(kind, w, t):
    return measure(kind, w, t).throughput["value"]


@pytest.mark.req("P-006-07")
@SETTINGS
@given(KINDS, COUNTS, TIMES, st.integers(1, 1000))
def test_multiplying_the_work_by_k_multiplies_the_throughput_by_k(kind, w, t, k):
    assert value(kind, w * k, t) == pytest.approx(k * value(kind, w, t), rel=1e-12)


@pytest.mark.req("P-006-07")
@SETTINGS
@given(KINDS, COUNTS, TIMES, st.floats(1e-3, 1e3, allow_nan=False))
def test_multiplying_the_time_by_k_divides_the_throughput_by_k(kind, w, t, k):
    assert value(kind, w, t * k) == pytest.approx(value(kind, w, t) / k, rel=1e-12)


@pytest.mark.req("P-006-07")
@SETTINGS
@given(KINDS, COUNTS, COUNTS, TIMES)
def test_a_stage_split_in_two_equal_durations_has_the_mean_throughput(kind, w1, w2, d):
    whole = value(kind, w1 + w2, 2 * d)
    assert whole == pytest.approx((value(kind, w1, d) + value(kind, w2, d)) / 2, rel=1e-12)


@pytest.mark.req("P-006-07")
@SETTINGS
@given(KINDS, COUNTS, TIMES)
def test_the_value_is_one_float64_division_and_the_unit_is_the_kinds(kind, w, t):
    m = measure(kind, w, t)
    assert m.throughput["value"] == w / t and m.throughput["unit"] == UNITS[kind]
    assert math.isfinite(m.throughput["value"]) and m.throughput["value"] > 0


# ---------------------------------------------------------------------------------------------------------------------
# the encode stage
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-18")
def test_the_encode_stage_reports_final_setting_frames_over_final_encode_time(tmp_path, monkeypatch):
    ctx = kit.prepare(tmp_path, monkeypatch)  # 3 frames: AV1 3/200 s and H.264 3/400 s per encode on the fake clock
    result = ctx.run()
    assert result["throughput"]["unit"] == "frames/s"
    assert result["throughput"]["value"] == pytest.approx(6 / (3 / 200 + 3 / 400), rel=1e-6)  # 266.67 frames/s


@pytest.mark.req("FR-006-19")
def test_a_zero_encode_time_omits_the_throughput_and_the_encode_fps(tmp_path, monkeypatch):
    inf = float("inf")
    ctx = kit.prepare(tmp_path, monkeypatch, fake_kw={"rates": {"av1": inf, "h264": inf}})  # the fake clock never moves
    result = ctx.run()
    assert "throughput" not in result
    assert result["message"] and "time" in result["message"].lower() and len(result["message"]) <= 300
    for o in result["outputs"]:
        enc = o.get("artefact", {}).get("encoder")
        if enc:
            assert enc["encode_fps"] is None

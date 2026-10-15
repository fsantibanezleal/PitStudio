# ruff: noqa: E501, PT018
"""T-006-032: profile mode: Warp activity timing, Chrome trace, kernel table, size cap, invalid flag, Nsight never launched.

Requirements: FR-006-20, FR-006-21.

Spec: specs/006-media-telemetry/spec.md FR-006-20 (when the runner profiles a stage (`PITSTUDIO_PROFILE=1`) a Warp-based studio stage enables
Warp activity timing and writes into its output folder a Chrome trace and a table of the 20 kernels with the largest total time (DC-006-03),
labelled "kernel timing, no admin rights", and never launches `nsys` or `ncu` itself), FR-006-21 (a `PITSTUDIO_PROFILE` value other than `0` or
`1` fails with error class `profile-invalid`; a trace that would exceed 100,000,000 bytes stops at that size and marks the table
`truncated: true`), DC-006-03 (`contracts/profile-summary.schema.json`: method `warp-activity-timing`, the fixed label, <= 20 kernels, trace file,
format `chrome-trace-json`, bytes, `truncated`, `kernels_total`) and spec section 8 (kernel names `^[A-Za-z_][A-Za-z0-9_.:-]{0,199}$`).

Oracle: a fake `warp` module (`timing_begin` / `timing_end` returning results with `name` and `elapsed` in milliseconds, as Warp documents for
`TimingResult`) fed with three named kernels of known durations; the kernel table computed by hand below; the Chrome Trace Event Format (complete
events `ph: "X"` with `ts` and `dur` in microseconds); the JSON Schema validator of the DC-006-03 contract; spies on `subprocess` and `os.system`.

Expected API of the implementation (module `pitstudio_studio.telemetry.profile`; error in `pitstudio_studio.media.errors`... see below):
    MAX_TRACE_BYTES = 100_000_000      MAX_TABLE_BYTES = 100_000      LABEL = "kernel timing, no admin rights"
    errors.ProfileInvalid(EncodeError)     (module `pitstudio_studio.media.errors`) error_class "profile-invalid"
    profile_enabled(env=None) -> bool      `env["PITSTUDIO_PROFILE"]`: unset or "0" is False, "1" is True; any other value (including the empty
                                           string, "2", "yes", " 1", "01") raises ProfileInvalid
    KernelProfile(output_dir: Path, *, stage: dict, warp, env=None, device="cuda", run_id=None, max_trace_bytes=MAX_TRACE_BYTES)
        constructor: decides `enabled` from `profile_enabled(env)` (ProfileInvalid before anything else happens);
        `with profile:` when enabled calls `warp.timing_begin(...)` once on entry and `warp.timing_end()` once on exit (also when the body raises; the
        exception propagates); when disabled it does nothing (no warp call, no file). On exit it writes `<output_dir>/profile/trace.json` (Chrome trace:
        {"traceEvents": [{"name", "cat": "kernel", "ph": "X", "ts", "dur", "pid", "tid"}, ...]}, one complete event per kernel launch, `dur` = elapsed
        milliseconds x 1000, `ts` non-decreasing) and `<output_dir>/profile/profile-summary.json` (DC-006-03). The table groups launches by (sanitised)
        kernel name: calls, total_ms = sum of elapsed, mean_ms = total_ms / calls, largest total first, at most 20 rows, `kernels_total` = distinct
        names; names are sanitised to the schema pattern (invalid characters become `_`, a bad first character gets a `_` prefix, at most 200
        characters). The trace is cut before the event that would take the file over `max_trace_bytes` (the file stays valid JSON and at most that
        size) and the summary then has `truncated: true`. `profile.summary` is the summary dict (None when disabled); `profile.trace_path`,
        `profile.summary_path` the written files. Nothing in this module launches a process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit as kit
from pitstudio_studio.media.errors import ProfileInvalid
from pitstudio_studio.telemetry.profile import (
    LABEL,
    MAX_TABLE_BYTES,
    MAX_TRACE_BYTES,
    KernelProfile,
    profile_enabled,
)

STAGE = {"id": "st50_physics"}
LAUNCHES = (
    [("dem_contact_forces", ms) for ms in (10.0, 12.0, 11.0, 7.0)]
    + [("dem_integrate", 2.5)] * 4
    + [("hash_grid_build", 1.0)] * 4
)  # hand table: contact_forces 4 calls 40.0 ms (mean 10.0); integrate 4 calls 10.0 ms (mean 2.5); hash_grid_build 4 calls 4.0 ms (mean 1.0)


class FakeWarp:
    TIMING_KERNEL, TIMING_ALL = 1, 255

    def __init__(self, launches):
        self.launches = list(launches)
        self.begun: list[tuple] = []
        self.ended = 0

    def timing_begin(self, *a, **kw):
        self.begun.append((a, kw))

    def timing_end(self, *a, **kw):
        self.ended += 1
        return [SimpleNamespace(name=n, elapsed=ms, device="cuda:0") for n, ms in self.launches]


def profiled(tmp_path, launches=LAUNCHES, *, env=None, device="cuda", **kw):
    warp = FakeWarp(launches)
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    p = KernelProfile(
        out, stage=STAGE, warp=warp, env={"PITSTUDIO_PROFILE": "1"} if env is None else env, device=device, **kw
    )
    with p:
        pass
    return p, warp, out


# ---------------------------------------------------------------------------------------------------------------------
# FR-006-21: the flag
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-21")
@pytest.mark.parametrize(
    ("env", "expected"), [({}, False), ({"PITSTUDIO_PROFILE": "0"}, False), ({"PITSTUDIO_PROFILE": "1"}, True)]
)
def test_profile_flag_zero_one_or_unset(env, expected):
    assert profile_enabled(env) is expected


@pytest.mark.req("FR-006-21")
@pytest.mark.parametrize(
    "value", ["2", "yes", "", " 1", "1 ", "01", "true", "True", "-1", "1.0", "\uff10", "1\n", "0x1", "on"]
)
def test_any_other_flag_value_is_profile_invalid(value):
    with pytest.raises(ProfileInvalid) as ei:
        profile_enabled({"PITSTUDIO_PROFILE": value})
    assert ei.value.error_class == "profile-invalid" and str(ei.value).startswith("profile-invalid: ")


@pytest.mark.req("FR-006-21")
def test_an_invalid_flag_fails_before_any_warp_call_and_the_stage_result_says_so(tmp_path):
    import pitstudio_stagekit

    warp = FakeWarp(LAUNCHES)
    out = tmp_path / "out"
    out.mkdir()
    job = {"output_dir": str(out)}
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")

    def stage(job):
        with KernelProfile(Path(job["output_dir"]), stage=STAGE, warp=warp, env={"PITSTUDIO_PROFILE": "2"}):
            return {"outputs": []}

    rc = pitstudio_stagekit.main(stage, ["--job", str(job_path)])
    doc = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert (
        rc == 1
        and doc["status"] == "failed"
        and doc["error_class"] == "unknown"
        and "profile-invalid: " in doc["message"]
    )
    assert warp.begun == [] and warp.ended == 0


# ---------------------------------------------------------------------------------------------------------------------
# FR-006-20
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-20")
@pytest.mark.parametrize("env", [{}, {"PITSTUDIO_PROFILE": "0"}])
def test_without_profile_mode_nothing_is_timed_or_written(tmp_path, env):
    p, warp, out = profiled(tmp_path, env=env)
    assert warp.begun == [] and warp.ended == 0 and p.summary is None
    assert list(out.iterdir()) == []


@pytest.mark.req("FR-006-20")
def test_activity_timing_is_enabled_once_and_collected_once(tmp_path):
    _, warp, _ = profiled(tmp_path)
    assert len(warp.begun) == 1 and warp.ended == 1
    a, kw = warp.begun[0]
    flt = kw.get("cuda_filter", a[0] if a else FakeWarp.TIMING_ALL)
    assert flt & FakeWarp.TIMING_KERNEL  # kernel activity is among the recorded activities


@pytest.mark.req("FR-006-20")
def test_the_kernel_table_matches_the_hand_calculation(tmp_path):
    p, _, out = profiled(tmp_path)
    s = p.summary
    assert (s["kind"], s["method"], s["label"], s["device"], s["truncated"]) == (
        "profile-summary",
        "warp-activity-timing",
        LABEL,
        "cuda",
        False,
    )
    assert LABEL == "kernel timing, no admin rights" and s["stage"] == STAGE and s["kernels_total"] == 3
    assert s["kernels"] == [
        {"name": "dem_contact_forces", "calls": 4, "total_ms": 40.0, "mean_ms": 10.0},
        {"name": "dem_integrate", "calls": 4, "total_ms": 10.0, "mean_ms": 2.5},
        {"name": "hash_grid_build", "calls": 4, "total_ms": 4.0, "mean_ms": 1.0},
    ]
    assert s["trace"]["file"] == "profile/trace.json" and s["trace"]["format"] == "chrome-trace-json"
    assert s["trace"]["bytes"] == (out / "profile" / "trace.json").stat().st_size
    assert json.loads((out / "profile" / "profile-summary.json").read_text(encoding="utf-8")) == s
    errors = list(kit.schema_validator("profile-summary").iter_errors(s))
    assert not errors, [e.message for e in errors]


@pytest.mark.req("FR-006-20")
def test_the_table_keeps_the_20_largest_total_times_and_counts_all_kernels(tmp_path):
    launches = [
        (f"kernel_{i:02d}", float(i + 1)) for i in range(25)
    ]  # kernel_i: one call of i + 1 ms; distinct totals 1..25
    launches += [("kernel_00", 0.5)]  # kernel_00: two calls, total 1.5 ms, mean 0.75
    p, _, _ = profiled(tmp_path, launches=launches)
    s = p.summary
    assert s["kernels_total"] == 25 and len(s["kernels"]) == 20
    assert [k["name"] for k in s["kernels"]] == [f"kernel_{i:02d}" for i in range(24, 4, -1)]  # totals 25 down to 6
    assert all(a["total_ms"] > b["total_ms"] for a, b in zip(s["kernels"], s["kernels"][1:], strict=False))
    assert not list(kit.schema_validator("profile-summary").iter_errors(s))
    # the dropped rows are exactly the 5 smallest: kernel_00 (1.5 ms), kernel_01 (2), kernel_02 (3), kernel_03 (4), kernel_04 (5)


@pytest.mark.req("FR-006-20")
def test_a_kernel_with_two_calls_is_averaged(tmp_path):
    p, _, _ = profiled(tmp_path, launches=[("a_kernel", 1.0), ("a_kernel", 2.0), ("b_kernel", 0.25)])
    assert p.summary["kernels"] == [
        {"name": "a_kernel", "calls": 2, "total_ms": 3.0, "mean_ms": 1.5},
        {"name": "b_kernel", "calls": 1, "total_ms": 0.25, "mean_ms": 0.25},
    ]


@pytest.mark.req("FR-006-20")
def test_the_chrome_trace_has_one_complete_event_per_launch(tmp_path):
    _, _, out = profiled(tmp_path)
    doc = json.loads((out / "profile" / "trace.json").read_text(encoding="utf-8"))
    ev = doc["traceEvents"]
    assert len(ev) == len(LAUNCHES)
    assert [e["name"] for e in ev] == [n for n, _ in LAUNCHES]
    assert [e["dur"] for e in ev] == pytest.approx([ms * 1000.0 for _, ms in LAUNCHES])  # microseconds
    assert all(e["ph"] == "X" and isinstance(e["ts"], (int, float)) for e in ev)
    ts = [e["ts"] for e in ev]
    assert ts == sorted(ts)


@pytest.mark.req("FR-006-20")
def test_cpu_runs_record_the_cpu_device(tmp_path):
    p, _, _ = profiled(tmp_path, device="cpu")
    assert p.summary["device"] == "cpu" and not list(kit.schema_validator("profile-summary").iter_errors(p.summary))


@pytest.mark.req("FR-006-20")
def test_no_kernels_gives_an_empty_but_valid_table(tmp_path):
    p, _, out = profiled(tmp_path, launches=[])
    assert p.summary["kernels"] == [] and p.summary["kernels_total"] == 0
    assert json.loads((out / "profile" / "trace.json").read_text(encoding="utf-8"))["traceEvents"] == []
    assert not list(kit.schema_validator("profile-summary").iter_errors(p.summary))


@pytest.mark.req("FR-006-20")
def test_nsys_and_ncu_are_never_launched(tmp_path, monkeypatch):
    launched = []

    def spy(*a, **k):
        launched.append((a, k))
        raise AssertionError("a process was launched")

    for name in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, spy)
    monkeypatch.setattr(os, "system", spy)
    p, _, _ = profiled(tmp_path)
    assert p.summary is not None and launched == []


@pytest.mark.req("FR-006-20")
def test_the_body_exception_propagates_and_the_timing_is_still_collected(tmp_path):
    warp = FakeWarp(LAUNCHES)
    out = tmp_path / "o"
    out.mkdir()
    with (
        pytest.raises(RuntimeError, match="stage failed"),
        KernelProfile(out, stage=STAGE, warp=warp, env={"PITSTUDIO_PROFILE": "1"}),
    ):
        raise RuntimeError("stage failed")
    assert warp.ended == 1


@pytest.mark.req("FR-006-20")
@pytest.mark.parametrize(
    "name",
    [
        "dem_contact<float>",
        "1st_kernel",
        "kernel with spaces",
        "ünïcode_kernel",
        "k" * 5000,
        "",
        "a/b\\c",
        "__init__",
        "kernel\x00",
        "x;rm -rf",
    ],
)
def test_hostile_kernel_names_are_sanitised_to_the_schema_pattern(tmp_path, name):
    p, _, _ = profiled(tmp_path, launches=[(name, 1.0), ("normal_kernel", 0.5)])
    errors = list(kit.schema_validator("profile-summary").iter_errors(p.summary))
    assert not errors, [e.message for e in errors]
    assert len(p.summary["kernels"]) == 2


# ---------------------------------------------------------------------------------------------------------------------
# FR-006-21: the size cap
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-21")
def test_the_limits_are_the_spec_numbers():
    assert MAX_TRACE_BYTES == 100_000_000 and MAX_TABLE_BYTES == 100_000


@pytest.mark.req("FR-006-21")
def test_a_trace_over_the_cap_is_cut_at_that_size_and_the_table_is_marked_truncated(tmp_path):
    launches = [("dem_contact_forces", 1.0 + i * 0.001) for i in range(400)]
    p, _, out = profiled(tmp_path, launches=launches, max_trace_bytes=3_000)
    trace = out / "profile" / "trace.json"
    assert trace.stat().st_size <= 3_000
    doc = json.loads(trace.read_text(encoding="utf-8"))  # still valid JSON
    assert 0 < len(doc["traceEvents"]) < 400
    assert p.summary["truncated"] is True and p.summary["trace"]["bytes"] == trace.stat().st_size <= 3_000
    assert not list(kit.schema_validator("profile-summary").iter_errors(p.summary))


@pytest.mark.req("FR-006-21")
def test_a_trace_under_the_cap_is_complete_and_not_truncated(tmp_path):
    p, _, out = profiled(tmp_path, max_trace_bytes=1_000_000)
    assert p.summary["truncated"] is False
    assert len(json.loads((out / "profile" / "trace.json").read_text(encoding="utf-8"))["traceEvents"]) == len(LAUNCHES)


@pytest.mark.req("FR-006-21")
@pytest.mark.parametrize("cap", [0, -1])
def test_a_non_positive_cap_is_a_value_error(tmp_path, cap):
    with pytest.raises(ValueError):  # noqa: PT011
        KernelProfile(tmp_path, stage=STAGE, warp=FakeWarp([]), env={"PITSTUDIO_PROFILE": "1"}, max_trace_bytes=cap)

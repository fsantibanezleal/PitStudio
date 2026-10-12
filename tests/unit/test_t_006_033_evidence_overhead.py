# ruff: noqa: E501, PT018
"""T-006-033: NVTX overhead without a profiler and the sizes of the profile outputs.

Requirements: NFR-006-02, NFR-006-03.

Spec: specs/006-media-telemetry/spec.md section 5 (NFR-006-02: NVTX overhead without a profiler attached <= 1 % of the stage's compute-loop
time, measured by a paired timing of a fixed Warp CPU workload with and without ranges; NFR-006-03: per stage a Chrome trace <= 100,000,000
bytes and a kernel table <= 100,000 bytes, a unit check on the written files); plan.md test strategy (median of 9 runs; byte counts of the
written files) and tolerances (NVTX calls are no-ops without a tool attached; 1 % covers the timer noise of a median of 9 runs).

Oracle: wall-clock timing of a fixed Warp CPU workload (a reference measurement, no code under test inside the workload), the real `nvtx`
package with no profiler attached, `os.stat` on the written files, the numeric limits of the spec.

Expected API: as in test_t_006_030_nvtx_ranges.py (`StepRanges.step`) and test_t_006_032_profile_outputs.py (`KernelProfile`, `MAX_TRACE_BYTES`,
`MAX_TABLE_BYTES`); additionally `KernelProfile(..., max_trace_bytes=n)` raises ValueError when n > MAX_TRACE_BYTES.
The overhead test is marked `slow` (about 3 s) and is part of the studio environment's slow job.
"""

import json
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit  # noqa: F401
from pitstudio_studio.telemetry.nvtx import StepRanges
from pitstudio_studio.telemetry.profile import MAX_TABLE_BYTES, MAX_TRACE_BYTES, KernelProfile

STEPS, N, RUNS = 100, 1 << 19, 9


@pytest.mark.slow
@pytest.mark.req("NFR-006-02")
def test_nvtx_ranges_cost_at_most_one_percent_of_a_fixed_warp_cpu_workload():
    import nvtx
    import warp as wp

    wp.config.quiet = True
    wp.init()

    @wp.kernel(module="unique")
    def saxpy(a: wp.array(dtype=wp.float32), b: wp.array(dtype=wp.float32), s: float):
        i = wp.tid()
        b[i] = b[i] + s * a[i]

    a = wp.ones(N, dtype=wp.float32, device="cpu")
    b = wp.zeros(N, dtype=wp.float32, device="cpu")
    ranges = StepRanges(
        env={"PITSTUDIO_NVTX_RANGE": "st50_physics"}, nvtx_module=nvtx
    )  # no profiler is attached to this process

    def plain():
        for _ in range(STEPS):
            wp.launch(saxpy, dim=N, inputs=[a, b, 0.5], device="cpu")

    def ranged():
        for _ in range(STEPS):
            with ranges.step("dem/step"):
                wp.launch(saxpy, dim=N, inputs=[a, b, 0.5], device="cpu")

    plain()  # warm up: kernel compilation and thread pools
    ranged()
    ratios = []
    for k in range(RUNS):  # paired runs, order alternating so that drift does not favour either arm
        order = (plain, ranged) if k % 2 == 0 else (ranged, plain)
        t = {}
        for fn in order:
            t0 = time.perf_counter()
            fn()
            t[fn.__name__] = time.perf_counter() - t0
        ratios.append(t["ranged"] / t["plain"])
    overhead = statistics.median(ratios) - 1.0
    assert overhead <= 0.01, f"median overhead {overhead:.4%} exceeds 1 % (ratios {ratios})"


# ---------------------------------------------------------------------------------------------------------------------
# NFR-006-03: output sizes
# ---------------------------------------------------------------------------------------------------------------------
class FakeWarp:
    TIMING_KERNEL, TIMING_ALL = 1, 255

    def __init__(self, launches):
        self.launches = launches

    def timing_begin(self, *a, **kw):
        return None

    def timing_end(self, *a, **kw):
        return [SimpleNamespace(name=n, elapsed=ms, device="cuda:0") for n, ms in self.launches]


def run_profile(tmp_path, launches, **kw):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    p = KernelProfile(out, stage={"id": "st50_physics"}, warp=FakeWarp(launches), env={"PITSTUDIO_PROFILE": "1"}, **kw)
    with p:
        pass
    return p, out


@pytest.mark.req("NFR-006-03")
def test_the_table_stays_under_100000_bytes_with_20_rows_of_maximum_length_names(tmp_path):
    launches = [
        (f"{'k' * 190}{i:09d}", float(i + 1)) for i in range(40)
    ]  # 40 distinct 199-character names: only 20 rows are written
    p, out = run_profile(tmp_path, launches)
    size = (out / "profile" / "profile-summary.json").stat().st_size
    assert len(p.summary["kernels"]) == 20 and 0 < size <= MAX_TABLE_BYTES == 100_000


@pytest.mark.req("NFR-006-03")
def test_a_large_trace_stays_under_the_cap_and_the_summary_reports_its_size(tmp_path):
    launches = [("dem_contact_forces", 0.25)] * 60_000
    p, out = run_profile(tmp_path, launches)
    trace = out / "profile" / "trace.json"
    assert 0 < trace.stat().st_size <= MAX_TRACE_BYTES == 100_000_000
    assert p.summary["trace"]["bytes"] == trace.stat().st_size and p.summary["truncated"] is False
    assert len(json.loads(trace.read_text(encoding="utf-8"))["traceEvents"]) == 60_000


@pytest.mark.req("NFR-006-03")
def test_a_cap_above_the_spec_limit_is_refused(tmp_path):
    with pytest.raises(ValueError):  # noqa: PT011
        KernelProfile(
            tmp_path,
            stage={"id": "st50_physics"},
            warp=FakeWarp([]),
            env={"PITSTUDIO_PROFILE": "1"},
            max_trace_bytes=MAX_TRACE_BYTES + 1,
        )


@pytest.mark.req("NFR-006-03")
def test_the_default_cap_is_the_spec_limit(tmp_path):
    p, _ = run_profile(tmp_path, [("a_kernel", 1.0)])
    assert p.summary["trace"]["bytes"] <= MAX_TRACE_BYTES

# ruff: noqa: E501
"""T-015-020: the footprint bench contract: public and labelled metrics, VRAM limits, GPU-time projection, and the `llamacpp` probe entry.

Requirements: FR-015-13, NFR-015-01, NFR-015-02, DC-015-07, DC-015-08.

Spec: specs/015-vlm/spec.md
- FR-015-13: when `st59_reason_bench` runs, it measures on 200 mixed queries (single 1280 x 720 images and 8-frame 640 x 360 sequences) the
  device-peak VRAM, prefill and decode tokens/s and wall time per query for the Q8_0 and BF16 paths, and publishes them with `performance: public` and
  the label "our hardware, not a comparative benchmark".
- NFR-015-01: device-peak VRAM (publishable: MIT runtime, open-model licence without a benchmark clause): Q8_0 <= 6 GB at a 16,384-token context; BF16 <= 12 GB;
  otherwise the context is reduced and the limit recorded ("GB" is 10^9 bytes, spec section 8).
- NFR-015-02: GPU time for tasks A-C (plan estimate 8-16 GPU-h): projected by the bench; if the projection exceeds 16 GPU-h, the run is split across >= 2 queue
  slots without reducing any pre-registered sample size.
- DC-015-07 (run and asset manifests, spec 001) and DC-015-08 (probe `llamacpp` in `studio/capabilities.json`, DC-000-02) as the producer side of the bench.
- spec section 7: model facts used for sizing: 2,438,696,960 BF16 parameters (about 4.9 GB); KV cache 2 x 28 x 8 x 128 x 2 B = 114,688 B per token (16,384 tokens
  about 1.9 GB); Q8_0 block of 32 weights = 34 bytes.

Oracle: the arithmetic of the spec facts written out (2 x 2,438,696,960 = 4,877,393,920 B; 114,688 x 16,384 = 1,879,048,192 B; 2,438,696,960 / 32 x 34 =
2,591,115,520 B); wall-time percentiles of a table built so that every percentile definition agrees (180 queries of 1 s and 20 of 5 s: mean 1.4, median 1.0, p95 5.0);
the metrics contract (`contracts/vlm-metrics.schema.json`, `$defs/bench` and `$defs/bench_path`, whose own rules reject a Q8_0 peak above 6 GB or a BF16 peak above 12 GB
at a 16,384-token context); the committed probe registry `studio/bench/run_bench.py` and the probe protocol of `studio/bench/_common.py` (the probe prints one JSON line).

Expected API of the implementation (package `pitstudio`, root environment), `pitstudio.reason.bench`:
- `LABEL == "our hardware, not a comparative benchmark"`, `PERFORMANCE == "public"`, `N_QUERIES == 200`.
- `bench_queries(seed=0) -> list[dict]`: 200 queries; each `{"kind": "image" | "sequence", "frames": 1 | 8, "width_px": 1280 | 640, "height_px": 720 | 360}` (image 1280 x 720 with 1
  frame; sequence 640 x 360 with 8 frames); both kinds occur; deterministic for a seed.
- `summarise_path(path, *, vram_peak_bytes, prefill_tokens_per_s, decode_tokens_per_s, wall_s, gpu, context_tokens=16384) -> dict`: one `bench_path` of the contract
  (`wall_s` is the list of per-query wall times; `wall_s_per_query` is `{"mean", "p50", "p95"}`; ValueError for an empty or non-finite or negative list, a negative or
  non-finite rate, an unknown path).
- `build_bench(paths) -> dict`: the contract's `bench` object with status "measured", `performance` "public", the label and `n_queries` 200.
  `not_run_bench(reason) -> dict`: status "not_run", empty `paths`, the reason.
- `vram_limit_bytes(path) -> int` (6,000,000,000 for "q8_0", 12,000,000,000 for "bf16"; ValueError otherwise); `within_vram_limit(path, peak_bytes, context_tokens=16384)
  -> bool` (limits apply at a 16,384-token context; at a smaller context a peak above the limit is also reported False but the verdict records that context);
  `kv_cache_bytes(tokens) -> int` (114,688 bytes per token); `weight_bytes(path, n_params) -> int` (2 bytes per parameter for "bf16"; 34 bytes per 32 for "q8_0").
- `project_gpu_hours(seconds_per_query, n_queries) -> float` and `split_workload(n_queries, hours, max_hours=16.0) -> list[int]`: one slot when the projection is at
  most `max_hours`, otherwise at least two slots, every slot projected at most `max_hours`, no slot empty, and the slot sizes sum to `n_queries` exactly.
`studio/bench/probe_llamacpp.py` and the `llamacpp` entry of `PROBES` in `studio/bench/run_bench.py` (project "pipeline").
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from pitstudio.reason import bench

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))  # the schema helper lives in tests/unit
import _p015_contracts as contracts

ROOT = Path(__file__).resolve().parents[2]

GPU = {"name": "NVIDIA RTX 5000 Ada Generation Laptop GPU", "driver": "581.42"}


def _errors(obj: dict, ref: str) -> list[str]:
    base = contracts.validator("vlm-metrics.schema.json").schema["$id"]
    v = Draft202012Validator({"$ref": base + ref}, registry=contracts._registry())
    return [e.message for e in v.iter_errors(obj)]


def _walls() -> list[float]:
    return [1.0] * 180 + [5.0] * 20


def _path(name: str = "q8_0", peak: int = 4_812_000_000, **kw) -> dict:
    return bench.summarise_path(
        name,
        vram_peak_bytes=peak,
        prefill_tokens_per_s=2150.0,
        decode_tokens_per_s=96.5,
        wall_s=kw.pop("wall_s", _walls()),
        gpu=GPU,
        **kw,
    )


@pytest.mark.req("FR-015-13")
def test_the_constants_follow_the_spec() -> None:
    assert bench.LABEL == "our hardware, not a comparative benchmark"
    assert bench.PERFORMANCE == "public"
    assert bench.N_QUERIES == 200


@pytest.mark.req("FR-015-13")
def test_the_bench_set_is_200_mixed_queries_of_single_1280x720_images_and_8_frame_640x360_sequences() -> None:
    qs = bench.bench_queries(7)
    assert len(qs) == 200
    kinds = {q["kind"] for q in qs}
    assert kinds == {"image", "sequence"}
    for q in qs:
        if q["kind"] == "image":
            assert (q["frames"], q["width_px"], q["height_px"]) == (1, 1280, 720)
        else:
            assert (q["frames"], q["width_px"], q["height_px"]) == (8, 640, 360)
    assert bench.bench_queries(7) == qs
    assert sum(q["kind"] == "image" for q in qs) >= 1
    assert sum(q["kind"] == "sequence" for q in qs) >= 1


@pytest.mark.req("FR-015-13")
def test_a_measured_path_has_the_peak_the_rates_and_the_wall_time_percentiles() -> None:
    p = _path()
    assert p["path"] == "q8_0"
    assert p["status"] == "measured"
    assert p["context_tokens"] == 16384
    assert (p["vram_peak_bytes"], p["prefill_tokens_per_s"], p["decode_tokens_per_s"]) == (4_812_000_000, 2150.0, 96.5)
    assert p["wall_s_per_query"] == {
        "mean": pytest.approx(1.4),
        "p50": pytest.approx(1.0),
        "p95": pytest.approx(5.0),
    }  # 180 x 1 s + 20 x 5 s
    assert p["gpu"] == GPU
    assert _errors(p, "#/$defs/bench_path") == []


@pytest.mark.req("FR-015-13")
def test_the_bench_object_is_public_labelled_and_valid() -> None:
    b = bench.build_bench([_path("q8_0"), _path("bf16", 9_930_000_000)])
    assert (b["status"], b["performance"], b["label"], b["n_queries"]) == (
        "measured",
        "public",
        "our hardware, not a comparative benchmark",
        200,
    )
    assert [p["path"] for p in b["paths"]] == ["q8_0", "bf16"]
    assert _errors(b, "#/$defs/bench") == []


@pytest.mark.req("FR-015-13")
def test_a_bench_that_did_not_run_says_why_and_has_no_paths() -> None:
    b = bench.not_run_bench("no CUDA device on this machine")
    assert (b["status"], b["performance"], b["n_queries"], b["paths"]) == ("not_run", "public", 200, [])
    assert b["reason"] == "no CUDA device on this machine"
    assert _errors(b, "#/$defs/bench") == []


@pytest.mark.req("FR-015-13")
@pytest.mark.parametrize(
    "kw",
    [
        {"wall_s": []},
        {"wall_s": [1.0, math.nan]},
        {"wall_s": [1.0, math.inf]},
        {"wall_s": [1.0, -0.1]},
        {"vram_peak_bytes": -1},
        {"prefill_tokens_per_s": math.nan},
        {"decode_tokens_per_s": -5.0},
        {"decode_tokens_per_s": math.inf},
        {"context_tokens": 0},
    ],
    ids=[
        "no-times",
        "nan-time",
        "inf-time",
        "negative-time",
        "negative-peak",
        "nan-rate",
        "negative-rate",
        "inf-rate",
        "zero-context",
    ],
)
def test_hostile_measurements_are_refused(kw: dict) -> None:
    args = {
        "vram_peak_bytes": 4_000_000_000,
        "prefill_tokens_per_s": 2000.0,
        "decode_tokens_per_s": 90.0,
        "wall_s": [1.0, 2.0],
        "gpu": GPU,
        **kw,
    }
    with pytest.raises(ValueError):  # noqa: PT011
        bench.summarise_path("q8_0", **args)


@pytest.mark.req("FR-015-13")
def test_an_unknown_path_is_refused() -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        _path("fp8")


@pytest.mark.req("FR-015-13")
@given(st.lists(st.floats(0.0, 3600.0, allow_nan=False), min_size=1, max_size=300))
def test_property_wall_time_summary_is_ordered_and_within_the_data(walls: list[float]) -> None:
    w = bench.summarise_path(
        "q8_0", vram_peak_bytes=1, prefill_tokens_per_s=1.0, decode_tokens_per_s=1.0, wall_s=walls, gpu=GPU
    )["wall_s_per_query"]
    assert min(walls) - 1e-9 <= w["p50"] <= w["p95"] <= max(walls) + 1e-9
    assert min(walls) - 1e-9 <= w["mean"] <= max(walls) + 1e-9
    assert w["mean"] == pytest.approx(sum(walls) / len(walls), rel=1e-9, abs=1e-9)


@pytest.mark.req("NFR-015-01")
def test_the_vram_limits_are_6_gb_for_q8_0_and_12_gb_for_bf16_in_decimal_gigabytes() -> None:
    assert bench.vram_limit_bytes("q8_0") == 6_000_000_000
    assert bench.vram_limit_bytes("bf16") == 12_000_000_000
    with pytest.raises(ValueError):  # noqa: PT011
        bench.vram_limit_bytes("fp8")


@pytest.mark.req("NFR-015-01")
@pytest.mark.parametrize(
    ("name", "peak", "ok"),
    [
        ("q8_0", 4_812_000_000, True),
        ("q8_0", 6_000_000_000, True),
        ("q8_0", 6_000_000_001, False),
        ("bf16", 9_930_000_000, True),
        ("bf16", 12_000_000_000, True),
        ("bf16", 12_000_000_001, False),
        ("q8_0", 0, True),
    ],
)
def test_a_peak_within_the_limit_at_16384_tokens_is_accepted_and_one_above_it_is_not(
    name: str, peak: int, ok: bool
) -> None:
    assert bench.within_vram_limit(name, peak, 16384) is ok
    assert bench.within_vram_limit(name, peak) is ok


@pytest.mark.req("NFR-015-01")
def test_the_contract_itself_rejects_a_q8_0_peak_above_6_gb_at_the_full_context() -> None:
    assert _errors(_path("q8_0", 4_812_000_000), "#/$defs/bench_path") == []
    over = {**_path("q8_0"), "vram_peak_bytes": 6_400_000_000}
    assert _errors(over, "#/$defs/bench_path") != []
    reduced = {**over, "context_tokens": 8192}  # a reduced context records the limit that was met instead
    assert _errors(reduced, "#/$defs/bench_path") == []


@pytest.mark.req("NFR-015-01")
def test_sizing_arithmetic_of_the_model_facts() -> None:
    assert bench.kv_cache_bytes(1) == 2 * 28 * 8 * 128 * 2 == 114_688
    assert bench.kv_cache_bytes(16_384) == 1_879_048_192
    assert bench.kv_cache_bytes(0) == 0
    assert bench.weight_bytes("bf16", 2_438_696_960) == 4_877_393_920
    assert bench.weight_bytes("q8_0", 2_438_696_960) == 2_438_696_960 // 32 * 34 == 2_591_115_520
    with pytest.raises(ValueError):  # noqa: PT011
        bench.kv_cache_bytes(-1)


@pytest.mark.req("NFR-015-02")
@pytest.mark.parametrize(("hours", "slots"), [(8.0, 1), (16.0, 1), (16.01, 2), (31.9, 2), (32.5, 3), (40.0, 3)])
def test_a_projection_above_16_gpu_hours_is_split_over_at_least_two_slots_without_dropping_a_query(
    hours: float, slots: int
) -> None:
    n = 6480 + 300 + 500 + 400 + 2000  # an illustrative workload
    parts = bench.split_workload(n, hours)
    assert sum(parts) == n  # no pre-registered sample size is reduced
    assert len(parts) >= slots if hours > 16.0 else len(parts) == 1
    assert all(p > 0 for p in parts)
    assert all(hours * p / n <= 16.0 + 1e-9 for p in parts)  # each slot is projected within the limit


@pytest.mark.req("NFR-015-02")
def test_the_projection_is_time_per_query_times_queries() -> None:
    assert bench.project_gpu_hours(1.8, 10_000) == pytest.approx(5.0, rel=1e-12)  # 18,000 s
    assert bench.project_gpu_hours(0.0, 10) == 0.0
    with pytest.raises(ValueError):  # noqa: PT011
        bench.project_gpu_hours(-1.0, 10)
    with pytest.raises(ValueError):  # noqa: PT011
        bench.project_gpu_hours(math.nan, 10)
    with pytest.raises(ValueError):  # noqa: PT011
        bench.split_workload(0, 5.0)


@pytest.mark.req("NFR-015-02")
@given(st.integers(1000, 20_000), st.floats(0.1, 200.0))
def test_property_a_split_never_changes_the_total_and_respects_the_slot_limit(n: int, hours: float) -> None:
    parts = bench.split_workload(n, hours)
    assert sum(parts) == n
    assert all(p >= 1 for p in parts)
    if hours <= 16.0:
        assert parts == [n]
    else:
        assert len(parts) >= 2
        assert all(
            hours * (p - 1) / n <= 16.0 + 1e-9 for p in parts
        )  # within one query of the limit (sizes are whole queries)


@pytest.mark.req("DC-015-08")
def test_the_llamacpp_probe_is_registered_in_the_capability_bench_under_the_pipeline_project() -> None:
    sys.path.insert(0, str(ROOT / "studio" / "bench"))
    try:
        import run_bench  # type: ignore[import-not-found]

        assert "llamacpp" in run_bench.PROBES
        project, _extra = run_bench.PROBES["llamacpp"]
        assert project == "pipeline"
        assert "llamacpp" not in run_bench.OPT_IN  # an ordinary probe: no disruptive load
    finally:
        sys.path.remove(str(ROOT / "studio" / "bench"))


@pytest.mark.req("DC-015-08")
def test_the_llamacpp_probe_skips_politely_without_the_external_binaries_and_is_public(tmp_path: Path) -> None:
    probe = ROOT / "studio" / "bench" / "probe_llamacpp.py"
    assert probe.is_file()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PITSTUDIO_LLAMACPP", "PITSTUDIO_MODELS"))}
    env["PITSTUDIO_MODELS"] = str(tmp_path)  # an empty data folder: no llama.cpp unpacked there
    r = subprocess.run([sys.executable, str(probe)], capture_output=True, text=True, env=env, timeout=120, check=False)
    last = [ln for ln in r.stdout.splitlines() if ln.strip()][-1]
    res = json.loads(last)
    assert res["probe"] == "llamacpp"
    assert res["status"] == "skip"  # an external tool is missing: a skip, never a crash or a false pass
    assert (
        res["publish"] == "public"
    )  # MIT runtime and an open-model licence without a benchmark clause (spec section 7)
    assert res["notes"]

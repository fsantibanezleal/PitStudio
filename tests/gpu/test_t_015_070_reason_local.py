# ruff: noqa: E501
"""T-015-070 (GPU, reference machine): the real GGUF conversion twice, the BF16 load and the footprint bench. Marked `gpu`: never run in CI and not run in the red phase.

Requirements: FR-015-05, FR-015-09, FR-015-13, P-015-12.

Spec: specs/015-vlm/spec.md
- FR-015-05 / P-015-12: converting the same inputs with the same tools twice yields identical SHA-256 values for the F16 model, the projector and the Q8_0 file.
- FR-015-09: the BF16 reference loads the official revision with transformers in BF16 on the reference GPU.
- FR-015-13 (+ NFR-015-01): `st59_reason_bench` measures device-peak VRAM, prefill and decode tokens/s and wall time per query on 200 mixed queries for the Q8_0 and BF16 paths and
  publishes them with `performance: public` and the label "our hardware, not a comparative benchmark"; Q8_0 <= 6 GB (decimal) and BF16 <= 12 GB at a 16,384-token context, otherwise the
  context is reduced and recorded.
- spec section 7: 2,438,696,960 BF16 parameters; Q8_0 block of 32 weights = 34 bytes (so a Q8_0 tensor takes 34 / 64 = 0.53125 of its F16 size).

Oracle: the published parameter count (Hugging Face API, spec section 7); the Q8_0 / F16 size ratio from the block arithmetic (quantised tensors take 34 bytes per 32 weights against 64 bytes in F16, so the
whole file lies between 0.50 and 0.58 once the unquantised norms and embeddings are included); the metrics contract schema for the bench object; the machine-wide limits of the spec. Nothing here is
compared with a number produced by the code under test except through those independent values.

Prerequisites (asserted with a message, never skipped): a CUDA device; `PITSTUDIO_MODELS` pointing at the data folder holding `hub/nvidia/Cosmos-Reason2-2B/<pinned revision>/` (the verified snapshot),
`llama.cpp/b11381/` (the unpacked CUDA 13.4 build), `llama.cpp/archives/` (both zips) and `llama.cpp/src-b11381/convert_hf_to_gguf.py`; `PITSTUDIO_TMP` for the outputs; the gated terms accepted.

Expected API of the implementation: as in tests/pipeline/test_t_015_010_runtime_pins.py (`runtime.load_pins`, `runtime.verify_runtime`), test_t_015_012_gguf_conversion.py (`convert.convert_model`),
test_t_015_015_bf16_reference.py (`bf16.attempt_bf16`, `bf16.reference_config`) and tests/contract/test_t_015_020_reason_bench.py; additionally
`pitstudio_pipeline.reason.stages.run_stage("st59_reason_bench", pins_path=..., archive_dir=..., runtime_dir=..., repo_root=..., launcher=<subprocess launcher>, out_dir=..., models_dir=..., hub_dir=...)`
returns 0 and writes `out_dir / "bench.json"`, the metrics `bench` object; `pitstudio_pipeline.reason.bf16.load_reference(snapshot, *, device="cuda")` returns the loaded transformers model.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pitstudio_pipeline.reason import bf16, convert, runtime, stages

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "unit"))  # the schema helper lives in tests/unit
import _p015_contracts as contracts  # noqa: E402

PARAMS = 2_438_696_960  # BF16 parameters of nvidia/Cosmos-Reason2-2B (spec 015 section 7)


def _need(var: str) -> Path:
    val = os.environ.get(var)
    assert val, f"{var} must point at the data folder of the reference machine (it is set by the scheduled GPU job)"
    p = Path(val)
    assert p.is_dir(), f"{var}={val} is not a folder"
    return p


def _assets() -> dict:
    import torch

    assert torch.cuda.is_available(), (
        "this test needs a CUDA device (it is marked gpu and runs only in the scheduled GPU job)"
    )
    models, tmp = _need("PITSTUDIO_MODELS"), _need("PITSTUDIO_TMP")
    pins_path = ROOT / "studio" / "reason" / "pins.json"
    pins = runtime.load_pins(pins_path)
    rev = pins["models"]["cosmos"]["revision"]
    snap = models / "hub" / "nvidia" / "Cosmos-Reason2-2B" / rev
    assert snap.is_dir(), (
        f"the verified Cosmos snapshot {snap} is missing (download it with the maintainer's token first)"
    )
    runtime_dir = models / "llama.cpp" / "b11381"
    archive_dir = models / "llama.cpp" / "archives"
    conv = models / "llama.cpp" / "src-b11381" / "convert_hf_to_gguf.py"
    assert conv.is_file(), f"{conv} is missing"
    return {
        "pins": pins,
        "pins_path": pins_path,
        "snap": snap,
        "runtime_dir": runtime_dir,
        "archive_dir": archive_dir,
        "conv": conv,
        "tmp": tmp,
        "models": models,
    }


def _run(argv: list[str]) -> int:
    return subprocess.run(argv, check=False).returncode


@pytest.mark.gpu
@pytest.mark.req("FR-015-05")
@pytest.mark.req("P-015-12")
def test_two_real_conversions_of_the_pinned_revision_give_identical_sha256_values_and_plausible_sizes() -> None:
    a = _assets()
    rt = runtime.verify_runtime(a["pins"], archive_dir=a["archive_dir"], runtime_dir=a["runtime_dir"], repo_root=ROOT)
    first = convert.convert_model(
        a["snap"],
        a["tmp"] / "reason-gguf-a",
        runtime=rt,
        pins=a["pins"],
        python=sys.executable,
        converter=a["conv"],
        runner=_run,
        repo_root=ROOT,
    )
    second = convert.convert_model(
        a["snap"],
        a["tmp"] / "reason-gguf-b",
        runtime=rt,
        pins=a["pins"],
        python=sys.executable,
        converter=a["conv"],
        runner=_run,
        repo_root=ROOT,
    )
    assert first.sha256 == second.sha256  # P-015-12: F16 model, projector and Q8_0 file, bit for bit
    f16, q8, mm = first.f16.stat().st_size, first.q8_0.stat().st_size, first.mmproj.stat().st_size
    assert 0.50 <= q8 / f16 <= 0.58  # 34 bytes per 32 weights against 64 bytes in F16
    assert mm > 500_000_000  # a vision projector of this model is hundreds of megabytes
    assert len(set(first.sha256.values())) == 3


@pytest.mark.gpu
@pytest.mark.req("FR-015-09")
def test_the_bf16_reference_loads_the_official_revision_on_the_reference_gpu_with_the_published_parameter_count() -> (
    None
):
    import torch

    a = _assets()
    cfg = bf16.reference_config(a["pins"])
    assert cfg["revision"] == a["pins"]["models"]["cosmos"]["revision"]
    state = bf16.attempt_bf16(lambda: bf16.load_reference(a["snap"], device="cuda"))
    assert state["status"] == "available", state.get("reason")
    model = state["model"]
    try:
        assert next(model.parameters()).dtype == torch.bfloat16
        assert next(model.parameters()).device.type == "cuda"
        assert sum(p.numel() for p in model.parameters()) == PARAMS
    finally:
        del model, state
        torch.cuda.empty_cache()


@pytest.mark.gpu
@pytest.mark.req("FR-015-13")
@pytest.mark.req("NFR-015-01")
def test_the_footprint_bench_is_published_with_the_label_and_meets_the_vram_limits() -> None:
    a = _assets()
    out = a["tmp"] / "reason-bench"
    code = stages.run_stage(
        "st59_reason_bench",
        pins_path=a["pins_path"],
        archive_dir=a["archive_dir"],
        runtime_dir=a["runtime_dir"],
        repo_root=ROOT,
        launcher=subprocess.Popen,
        out_dir=out,
        models_dir=a["models"],
        hub_dir=a["models"] / "hub",
    )
    assert code == 0
    bench = json.loads((out / "bench.json").read_text(encoding="utf-8"))
    base = contracts.validator("vlm-metrics.schema.json").schema["$id"]
    errs = [
        e.message
        for e in Draft202012Validator({"$ref": base + "#/$defs/bench"}, registry=contracts._registry()).iter_errors(
            bench
        )
    ]
    assert errs == []
    assert (bench["status"], bench["performance"], bench["label"], bench["n_queries"]) == (
        "measured",
        "public",
        "our hardware, not a comparative benchmark",
        200,
    )
    paths = {p["path"]: p for p in bench["paths"]}
    assert set(paths) == {"q8_0", "bf16"}
    limits = {"q8_0": 6_000_000_000, "bf16": 12_000_000_000}
    for name, p in paths.items():
        assert p["status"] == "measured"
        assert p["prefill_tokens_per_s"] > 0
        assert p["decode_tokens_per_s"] > 0
        assert p["wall_s_per_query"]["p95"] < 120.0  # no query reached the 120 s limit of FR-015-12
        assert p["wall_s_per_query"]["p50"] <= p["wall_s_per_query"]["p95"]
        if p["context_tokens"] == 16384:
            assert p["vram_peak_bytes"] <= limits[name], (
                f"{name} exceeds its limit at the full context: reduce the context and record it"
            )
        else:
            assert p["context_tokens"] < 16384  # a reduced context is recorded instead

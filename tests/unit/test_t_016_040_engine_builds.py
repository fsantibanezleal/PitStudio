"""T-016-040: engine builds on the fake GPU backend, build failures, "not run" cells (unit, fake GPU, hostile).

Requirements: FR-016-20, FR-016-21, FR-016-24 (and the s62_accel sides of FR-016-03 and FR-016-10).

Spec: specs/016-export-acceleration/spec.md
- FR-016-20: `s62_accel` builds, per model and applicable precision, a strongly typed TensorRT 11.3 engine with
  Polygraphy from the layer-1/2 ONNX variants (fp32 with the TF32 builder flag cleared, fp16 from the fp16 cast graph,
  int8 and fp8 from their QDQ graphs), one fixed optimisation profile covering the bench batch sizes, after pointing
  `CUDA_PATH` and the DLL search path at the CUDA 13 runtime wheel, and records engine SHA-256, TensorRT version,
  builder configuration and build time in the run manifest;
- FR-016-21: an engine build failure records the variant as `build-failed` with the builder's error text (scrubbed of
  paths) and continues with the next variant;
- FR-016-24: if TensorRT, the CUDA 13 runtime wheel or a CUDA GPU is unavailable, every TensorRT cell is "not run" while
  the PyTorch and ONNX Runtime cells still run; if the TensorRT 10.14 libraries are not in the `pipeline/` lock, every
  ONNX Runtime TensorRT-provider cell is "not run";
- FR-016-03 / FR-016-10: the consumer rejects a hostile ONNX file and refuses a hostile precision request before any
  build.
plan.md test strategy rows FR-016-20 (recorded builder configuration: TF32 cleared, profile batches, `CUDA_PATH` set to
the CUDA 13 wheel folder), FR-016-21 (a builder that raises -> `build-failed`, scrubbed text, next variant built),
FR-016-24 (capability fixtures: no TensorRT; no CUDA; no 10.14 libraries -> expected cell statuses). The real-engine
probe-graph check is tests/gpu/test_t_016_040_engine_probe_graph.py.

Oracles: hand calculation (the fake backend records exactly what it is called with; the fake clock makes the build time
12.5 s; SHA-256 by `hashlib` over the bytes the fake writes; the profile bounds are the smallest and largest bench batch
size of the variant); the capability fixtures below are hand-written truth tables.

Expected public API (root environment, pure Python; the real TensorRT adapter lives in `pipeline/accel/` and is not
needed here):
module `pitstudio.accel.engines`
    scrub_error(text: str) -> str          # replaces absolute file-system paths (Windows drive, UNC, POSIX) by "<path>"
    configure_cuda_env(env: Mapping[str, str], runtime_dir: Path) -> CudaEnv
        CudaEnv.env: dict (a copy of `env` with CUDA_PATH == str(runtime_dir) and PATH starting with a directory of
        `runtime_dir`); CudaEnv.dll_dirs: list[Path] (non-empty, every entry inside `runtime_dir`).
    build_engines(variants: Sequence[Mapping], backend, *, run_dir: Path, clock, onnx_guard: Callable[[Path], None])
        -> list[EngineRecord]
        variants: {"model": str, "precision": str, "onnx": Path, "config": export-config dict,
        "batch_sizes": tuple[int, ...]}.
        backend protocol: `version: str` and
        `build(onnx_path: Path, *, precision: str, profile: dict, flags: dict, out_path: Path) -> None`
        (writes the engine bytes to `out_path` or raises). For each variant, in order: `check_variant_request` (a
        refused variant raises `pitstudio.export.variant_rules.VariantRefused`, nothing built), `onnx_guard(onnx)` (its
        exception propagates, nothing built), then the build with `flags = {"strongly_typed": True, "tf32": False,
        "timing_cache": <path under run_dir>}` and `profile = {"min": min(batch_sizes), "opt": o, "max":
        max(batch_sizes)}` with min <= o <= max; the engine file is written under `run_dir / "engines"`.
        EngineRecord (dataclass): model, precision, status ("built" | "build-failed"), tensorrt_version, engine_path
        (Path | None), engine_sha256 (hex | None), builder_config (dict | None: strongly_typed, tf32, profile,
        precision, onnx_sha256), build_time_s (float: clock.monotonic() difference around the build), error (scrubbed
        text | None). A failing build never stops the loop and leaves no engine file.
module `pitstudio.accel.capabilities`
    cell_status(backend: str, capabilities: Mapping[str, bool]) -> CellStatus      # .status "run" | "not_run", .reason
        capabilities keys: tensorrt_11 (native TensorRT 11.3 importable), cuda13_runtime (the CUDA 13 runtime wheel),
        cuda_gpu, tensorrt_10_14_lock (the TensorRT 10.14 libraries are in the pipeline/ lock).
        backend "tensorrt" runs iff tensorrt_11 and cuda13_runtime and cuda_gpu; "ort-tensorrt" runs iff
        tensorrt_10_14_lock and cuda_gpu; "pytorch" and "ort-cpu" always run; "ort-cuda" runs iff cuda_gpu; a not-run
        cell has a non-empty reason naming the missing piece ("TensorRT", "CUDA 13", "GPU" or "10.14").
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from pitstudio.accel.capabilities import cell_status
from pitstudio.accel.engines import build_engines, configure_cuda_env, scrub_error
from pitstudio.export.variant_rules import VariantRefused

SHA_ONNX = hashlib.sha256(b"onnx-bytes").hexdigest()


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def monotonic(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeBackend:
    version = "11.3.0.99"

    def __init__(self, clock: FakeClock, *, fail_on: set[str] | None = None, message: str = "boom") -> None:
        self.clock, self.fail_on, self.message = clock, fail_on or set(), message
        self.calls: list[dict] = []

    def build(self, onnx_path: Path, *, precision: str, profile: dict, flags: dict, out_path: Path) -> None:
        self.calls.append({"onnx": onnx_path, "precision": precision, "profile": profile, "flags": flags})
        self.clock.advance(12.5)
        if onnx_path.name in self.fail_on:
            raise RuntimeError(self.message)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"ENGINE:" + onnx_path.name.encode() + b":" + precision.encode())


def _config(**over: object) -> dict:
    cfg = {"opset": 19, "gemm_heavy": True}
    cfg.update(over)
    return cfg


def _variant(tmp: Path, model: str, precision: str, *, batches=(1, 4, 16, 64), **cfg) -> dict:
    onnx_path = tmp / f"{model}-{precision}.onnx"
    onnx_path.write_bytes(b"onnx-bytes")
    return {
        "model": model,
        "precision": precision,
        "onnx": onnx_path,
        "config": _config(**cfg),
        "batch_sizes": batches,
    }


def _no_guard(_p: Path) -> None:
    return None


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-20
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-20")
def test_fp32_engine_is_built_strongly_typed_with_tf32_cleared_and_one_profile_over_the_bench_batches(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    backend = FakeBackend(clock)
    run_dir = tmp_path / "run"
    (rec,) = build_engines(
        [_variant(tmp_path, "d-fine-n", "fp32")], backend, run_dir=run_dir, clock=clock, onnx_guard=_no_guard
    )
    (call,) = backend.calls
    assert call["precision"] == "fp32"
    assert call["flags"]["strongly_typed"] is True
    assert call["flags"]["tf32"] is False
    profile = call["profile"]
    assert (profile["min"], profile["max"]) == (1, 64)
    assert profile["min"] <= profile["opt"] <= profile["max"]
    assert rec.status == "built"
    assert rec.builder_config["tf32"] is False
    assert rec.builder_config["strongly_typed"] is True
    assert rec.builder_config["profile"] == profile
    assert rec.builder_config["precision"] == "fp32"
    assert rec.builder_config["onnx_sha256"] == SHA_ONNX


@pytest.mark.req("FR-016-20")
def test_policy_batch_sizes_set_the_profile_bounds(tmp_path: Path) -> None:
    # the bench sweeps {1, 64, 4096} for policies: the single fixed profile must cover 1 .. 4096
    clock = FakeClock()
    backend = FakeBackend(clock)
    v = _variant(tmp_path, "il-policy", "fp32", batches=(1, 64, 4096))
    build_engines([v], backend, run_dir=tmp_path / "run", clock=clock, onnx_guard=_no_guard)
    assert (backend.calls[0]["profile"]["min"], backend.calls[0]["profile"]["max"]) == (1, 4096)


@pytest.mark.req("FR-016-20")
def test_each_variant_is_built_from_its_own_onnx_graph(tmp_path: Path) -> None:
    clock = FakeClock()
    backend = FakeBackend(clock)
    variants = [_variant(tmp_path, "m", p) for p in ("fp32", "fp16", "int8", "fp8")]
    records = build_engines(variants, backend, run_dir=tmp_path / "run", clock=clock, onnx_guard=_no_guard)
    assert [c["onnx"].name for c in backend.calls] == ["m-fp32.onnx", "m-fp16.onnx", "m-int8.onnx", "m-fp8.onnx"]
    assert [c["precision"] for c in backend.calls] == ["fp32", "fp16", "int8", "fp8"]
    assert [r.precision for r in records] == ["fp32", "fp16", "int8", "fp8"]
    assert all(c["flags"]["strongly_typed"] is True for c in backend.calls)


@pytest.mark.req("FR-016-20")
def test_the_record_carries_engine_digest_version_build_time_and_a_path_inside_the_run_folder(tmp_path: Path) -> None:
    clock = FakeClock()
    backend = FakeBackend(clock)
    run_dir = tmp_path / "run"
    (rec,) = build_engines(
        [_variant(tmp_path, "d-fine-n", "fp16")], backend, run_dir=run_dir, clock=clock, onnx_guard=_no_guard
    )
    data = Path(rec.engine_path).read_bytes()
    assert data == b"ENGINE:d-fine-n-fp16.onnx:fp16"
    assert rec.engine_sha256 == hashlib.sha256(data).hexdigest()
    assert rec.tensorrt_version == "11.3.0.99"
    assert rec.build_time_s == 12.5
    assert Path(rec.engine_path).resolve().is_relative_to((run_dir / "engines").resolve())
    assert Path(backend.calls[0]["flags"]["timing_cache"]).resolve().is_relative_to(run_dir.resolve())


@pytest.mark.req("FR-016-20")
def test_cuda_path_and_the_dll_search_path_point_at_the_cuda_13_runtime_wheel(tmp_path: Path) -> None:
    runtime = tmp_path / "site-packages" / "nvidia" / "cuda_runtime"
    (runtime / "bin").mkdir(parents=True)
    base = {"PATH": os.pathsep.join(["C:\\Windows", "C:\\Tools"]), "CUDA_PATH": "C:\\old\\cuda12"}
    result = configure_cuda_env(base, runtime)
    assert result.env["CUDA_PATH"] == str(runtime)
    first_path_entry = result.env["PATH"].split(os.pathsep)[0]
    assert Path(first_path_entry).resolve().is_relative_to(runtime.resolve())
    assert result.dll_dirs
    assert all(Path(d).resolve().is_relative_to(runtime.resolve()) for d in result.dll_dirs)
    assert base["CUDA_PATH"] == "C:\\old\\cuda12"  # the input mapping is not modified
    assert "C:\\Windows" in result.env["PATH"]


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-21
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-21")
def test_a_failing_build_is_recorded_with_scrubbed_text_and_the_next_variant_is_built(tmp_path: Path) -> None:
    clock = FakeClock()
    msg = "Network validation failed: unsupported node at C:\\Users\\bob\\work\\m-fp16.onnx (see /srv/bob/log.txt)"
    backend = FakeBackend(clock, fail_on={"m-fp16.onnx"}, message=msg)
    variants = [_variant(tmp_path, "m", p) for p in ("fp32", "fp16", "int8")]
    records = build_engines(variants, backend, run_dir=tmp_path / "run", clock=clock, onnx_guard=_no_guard)
    assert [r.status for r in records] == ["built", "build-failed", "built"]
    assert len(backend.calls) == 3  # the loop continued after the failure
    failed = records[1]
    assert failed.engine_path is None
    assert failed.engine_sha256 is None
    assert "Network validation failed" in failed.error
    assert "bob" not in failed.error
    assert "C:\\" not in failed.error
    assert "/srv" not in failed.error
    assert list((tmp_path / "run" / "engines").glob("*fp16*")) == []  # no engine file left behind


@pytest.mark.req("FR-016-21")
def test_every_variant_failing_gives_one_failed_record_each(tmp_path: Path) -> None:
    clock = FakeClock()
    backend = FakeBackend(clock, fail_on={"m-fp32.onnx", "m-fp16.onnx"}, message="out of memory")
    variants = [_variant(tmp_path, "m", p) for p in ("fp32", "fp16")]
    records = build_engines(variants, backend, run_dir=tmp_path / "run", clock=clock, onnx_guard=_no_guard)
    assert [r.status for r in records] == ["build-failed", "build-failed"]
    assert all(r.error == "out of memory" for r in records)


@pytest.mark.req("FR-016-21")
@pytest.mark.parametrize(
    ("raw", "forbidden"),
    [
        ("failed at C:\\Users\\Jane Doe\\proj\\model.onnx", ["Jane", "C:\\"]),
        ("failed at D:/data/secret/model.onnx line 3", ["secret", "D:/"]),
        ("failed at \\\\server\\share\\team\\model.onnx", ["server", "share"]),
        ("failed at /opt/jane/models/x.onnx", ["jane", "/opt"]),
        ("failed at /mnt/data/jane/x.onnx and /tmp/trt/cache.bin", ["jane", "/mnt", "/tmp"]),
    ],
)
def test_scrub_error_removes_absolute_paths_and_keeps_the_message(raw: str, forbidden: list[str]) -> None:
    out = scrub_error(raw)
    assert out.startswith("failed at")
    for token in forbidden:
        assert token not in out
    assert "<path>" in out


@pytest.mark.req("FR-016-21")
def test_scrub_error_leaves_text_without_paths_untouched() -> None:
    text = "Internal error: plugin 'GridSample' failed (code 7); ratio 3/4"
    assert scrub_error(text) == text


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-10 / FR-016-03 on the s62_accel side
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-10")
@pytest.mark.parametrize(
    ("precision", "cfg"),
    [("bf16", {}), ("fp8", {"opset": 18}), ("fp8", {"gemm_heavy": False}), ("int4", {})],
)
def test_a_hostile_precision_request_is_refused_before_anything_is_built(
    precision: str, cfg: dict, tmp_path: Path
) -> None:
    clock = FakeClock()
    backend = FakeBackend(clock)
    with pytest.raises(VariantRefused):
        build_engines(
            [_variant(tmp_path, "m", precision, **cfg)],
            backend,
            run_dir=tmp_path / "run",
            clock=clock,
            onnx_guard=_no_guard,
        )
    assert backend.calls == []


@pytest.mark.req("FR-016-03")
def test_a_hostile_onnx_file_is_rejected_by_the_guard_before_anything_is_built(tmp_path: Path) -> None:
    clock = FakeClock()
    backend = FakeBackend(clock)

    def guard(path: Path) -> None:
        raise ValueError(f"ir_version 11 in {path.name}")

    with pytest.raises(ValueError, match="ir_version 11"):
        build_engines(
            [_variant(tmp_path, "m", "fp32")], backend, run_dir=tmp_path / "run", clock=clock, onnx_guard=guard
        )
    assert backend.calls == []


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-24: "not run" cells from capability fixtures
# ----------------------------------------------------------------------------------------------------------------------

FULL = {"tensorrt_11": True, "cuda13_runtime": True, "cuda_gpu": True, "tensorrt_10_14_lock": True}
BACKENDS = ["pytorch", "ort-cpu", "ort-cuda", "ort-tensorrt", "tensorrt"]


@pytest.mark.req("FR-016-24")
def test_with_every_capability_every_backend_runs() -> None:
    assert {b: cell_status(b, FULL).status for b in BACKENDS} == dict.fromkeys(BACKENDS, "run")


@pytest.mark.req("FR-016-24")
@pytest.mark.parametrize("missing", ["tensorrt_11", "cuda13_runtime", "cuda_gpu"])
def test_without_tensorrt_the_cuda_13_wheel_or_a_gpu_every_tensorrt_cell_is_not_run_and_pytorch_and_ort_still_run(
    missing: str,
) -> None:
    caps = {**FULL, missing: False}
    status = cell_status("tensorrt", caps)
    assert status.status == "not_run"
    assert status.reason
    assert any(word in status.reason for word in ("TensorRT", "CUDA 13", "GPU"))
    assert cell_status("pytorch", caps).status == "run"
    assert cell_status("ort-cpu", caps).status == "run"


@pytest.mark.req("FR-016-24")
def test_without_the_tensorrt_10_14_libraries_the_ort_tensorrt_cells_are_not_run_but_native_tensorrt_runs() -> None:
    caps = {**FULL, "tensorrt_10_14_lock": False}
    status = cell_status("ort-tensorrt", caps)
    assert status.status == "not_run"
    assert "10.14" in status.reason
    assert cell_status("tensorrt", caps).status == "run"
    assert cell_status("ort-cuda", caps).status == "run"


@pytest.mark.req("FR-016-24")
def test_without_a_cuda_gpu_the_cpu_cells_still_run() -> None:
    caps = {"tensorrt_11": False, "cuda13_runtime": False, "cuda_gpu": False, "tensorrt_10_14_lock": False}
    assert cell_status("pytorch", caps).status == "run"
    assert cell_status("ort-cpu", caps).status == "run"
    for backend in ("tensorrt", "ort-tensorrt", "ort-cuda"):
        s = cell_status(backend, caps)
        assert s.status == "not_run"
        assert s.reason

"""s62_accel (engine builds) and s64_bench (benchmark matrix) in the accelerator environment (spec 016).

    python accel_run.py build [--dry-run]     fp32 / fp16 / int8 TensorRT 11.3 engines of every model of models.yaml
    python accel_run.py bench [--dry-run]     latency, throughput, energy, VRAM, thermal flag and output difference

Both subcommands take the machine GPU lock, refuse to start above 80 C and call `Guard.check()` between GPU steps. A
`--dry-run` runs every CPU part for real (ONNX guard, variants, ONNX Runtime CPU references, the timing protocol on the
CPU), asserts that a CUDA GPU is visible and that TensorRT imports, and stops before the first CUDA context or build.
Engines, variants and benchmark cells are written only under `<PITSTUDIO_MODELS>/accel/<run>/`, which is local
storage outside the repository: engines are never committed (FR-016-22) and TensorRT-for-RTX or licence-changed
results are written to
`local/` only (FR-016-23, FR-016-33). A model without an ONNX file, an engine that failed to build or a precision
without
calibration data is recorded as a "not available" cell with its reason, never as a number.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import sys
import threading
import time
from importlib import metadata
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "pipeline" / "src"), str(REPO / "studio" / "bench")]

import numpy as np  # noqa: E402
import yaml  # noqa: E402

START_MAX_C = 80


def folder(env: str, default: str) -> Path:
    return Path(os.environ.get(env, REPO / default))


def lock_path() -> Path:
    return folder("PITSTUDIO_GPU_LOCK", "models/local/gpu0.compute")


def load_registry() -> list[dict[str, Any]]:
    return yaml.safe_load((HERE / "models.yaml").read_text(encoding="utf-8"))["models"]


def resolve(root_env: str, rel: str) -> Path:
    return folder(root_env, "models/local") / rel


# ----------------------------------------------------------------------------------------------------------------------
# environment: CUDA 13 runtime wheel, TensorRT, NVML, lock and guard
# ----------------------------------------------------------------------------------------------------------------------


def use_cuda13_runtime_wheel() -> list[Path]:
    """CUDA_PATH and the DLL search path at the CUDA 13 runtime wheel (FR-016-20); cuDNN for the ORT CUDA EP."""
    import nvidia

    from pitstudio.accel.engines import configure_cuda_env

    runtime = None
    for base in nvidia.__path__:
        candidate = Path(base) / "cu13"
        if candidate.is_dir():
            runtime = candidate
    if runtime is None:
        raise RuntimeError("nvidia-cuda-runtime (CUDA 13) is not installed in this environment")
    cuda = configure_cuda_env(dict(os.environ), runtime)
    os.environ.update(cuda.env)
    extra = [Path(b) / "cudnn" / "bin" for b in nvidia.__path__ if (Path(b) / "cudnn" / "bin").is_dir()]
    for directory in [*cuda.dll_dirs, *extra]:
        os.add_dll_directory(str(directory))
        os.environ["PATH"] = f"{directory}{os.pathsep}{os.environ['PATH']}"
    for var in [v for v in os.environ if v == "CUDA_HOME" or v.startswith("CUDA_PATH_V")]:
        del os.environ[var]
    return cuda.dll_dirs


def import_trt():
    try:
        import tensorrt as trt
    except ModuleNotFoundError:  # the standalone cu13 wheels ship the module as `tensorrt_bindings`
        import tensorrt_bindings as trt

        sys.modules["tensorrt"] = trt
    return trt


def assert_cuda_visible() -> dict[str, Any]:
    """A CUDA GPU is visible through NVML and the runtime DLLs load; no CUDA context is created."""
    import pynvml

    pynvml.nvmlInit()
    count = pynvml.nvmlDeviceGetCount()
    if count < 1:
        raise SystemExit("no CUDA GPU is visible (NVML device count 0)")
    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    name = pynvml.nvmlDeviceGetName(handle)
    for dll in ("cudart64_13.dll",):
        ctypes.WinDLL(dll)
    return {
        "gpu_name": name if isinstance(name, str) else name.decode(),
        "driver": _decode(pynvml.nvmlSystemGetDriverVersion()),
    }


def _decode(value: Any) -> str:
    return value if isinstance(value, str) else value.decode()


def tensorrt_licence_check():
    from pitstudio.accel.licence import check_tensorrt_licence, read_installed_licence

    return check_tensorrt_licence(read_installed_licence(metadata.distribution("tensorrt-cu13-libs")))


def acquire_lock(wait_s: int = 6 * 3600):
    from filelock import FileLock, Timeout

    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if (path.parent / "gpu0.hold").exists():
        raise SystemExit("GPU hold file present")
    lock, started = FileLock(str(path)), time.time()
    while True:
        try:
            lock.acquire(timeout=30)
            return lock
        except Timeout:
            if time.time() - started > wait_s:
                raise SystemExit("GPU lock busy for too long") from None
            print("[lock] GPU busy; waiting", flush=True)


class RealClock:
    @staticmethod
    def monotonic() -> float:
        return time.perf_counter()

    @staticmethod
    def sleep(seconds: float) -> None:
        time.sleep(seconds)


class NvmlBackend:
    """The runner's backend protocol over NVML: read(field) -> float, raising for an unsupported field."""

    def __init__(self) -> None:
        import pynvml

        self.nvml = pynvml
        pynvml.nvmlInit()
        self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)

    def read(self, field: str) -> float:
        n, h = self.nvml, self.handle
        if field == "energy_mj":
            return float(n.nvmlDeviceGetTotalEnergyConsumption(h))
        if field == "power_w":
            return n.nvmlDeviceGetPowerUsage(h) / 1000.0
        if field == "sm_clock_mhz":
            return float(n.nvmlDeviceGetClockInfo(h, n.NVML_CLOCK_SM))
        if field == "mem_clock_mhz":
            return float(n.nvmlDeviceGetClockInfo(h, n.NVML_CLOCK_MEM))
        if field == "temp_c":
            return float(n.nvmlDeviceGetTemperature(h, n.NVML_TEMPERATURE_GPU))
        if field == "clocks_event_mask":
            return float(n.nvmlDeviceGetCurrentClocksEventReasons(h))
        if field == "vram_used_bytes":
            return float(n.nvmlDeviceGetMemoryInfo(h).used)
        raise KeyError(field)

    def fingerprint(self) -> dict[str, Any]:
        n, h = self.nvml, self.handle
        import psutil

        battery = psutil.sensors_battery()
        return {
            "gpu_name": _decode(n.nvmlDeviceGetName(h)),
            "driver": _decode(n.nvmlSystemGetDriverVersion()),
            "power_limit_enforced_w": n.nvmlDeviceGetEnforcedPowerLimit(h) / 1000.0,
            "power_source": "battery" if battery is not None and not battery.power_plugged else "ac",
            "os_power_mode": os.environ.get("PITSTUDIO_OS_POWER_MODE", "best-performance"),
        }


def start_guard():
    """Wait until the GPU is at most 80 C, then return the in-run Guard (FR-002-19)."""
    from gpu_guard import Guard, gpu_temp_reader

    read = gpu_temp_reader()
    deadline = time.time() + 20 * 60
    while read() > START_MAX_C:
        if time.time() > deadline:
            raise SystemExit(f"GPU did not cool to {START_MAX_C} C in 20 min; not starting")
        time.sleep(10)
    return Guard()


def guard_step(guard) -> None:
    if guard.check() == "cooldown":
        guard.cool_down()


# ----------------------------------------------------------------------------------------------------------------------
# stage A (CPU): ONNX guard, inputs, ONNX Runtime CPU references, precision variants
# ----------------------------------------------------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs(spec: dict[str, Any]) -> np.ndarray:
    path = resolve(spec["inputs"]["root"], spec["inputs"]["file"])
    if path.suffix == ".npz":
        data = np.load(path)[spec["inputs"]["golden_key"]]
        return np.ascontiguousarray(data[: spec["inputs"]["n_inputs"]], dtype=np.float32)
    return np.ascontiguousarray(np.load(path), dtype=np.float32)


def calibration_inputs(spec: dict[str, Any], eval_digests: set[str]) -> list[np.ndarray] | None:
    """500 seeded training inputs, disjoint from the golden and evaluation sets (FR-016-08); None when not wired."""
    cal = spec.get("calibration")
    if not cal:
        return None
    path = resolve(cal["root"], cal["file"])
    if not path.is_file():
        return None
    pool = np.load(path)[cal["key"]]
    digest = lambda a: hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()  # noqa: E731
    order = np.random.default_rng(20261015).permutation(len(pool))
    chosen: list[np.ndarray] = []
    for index in order:
        sample = np.ascontiguousarray(pool[index][None], dtype=np.float32)
        if digest(sample) not in eval_digests:
            chosen.append(sample)
        if len(chosen) == 500:
            return chosen
    return None


def stage_a(run: Path, models: list[dict[str, Any]]) -> dict[str, Any]:
    """Variants and CPU references for every available model; returns the manifest written to `variants.json`."""
    import onnxruntime as ort
    from pitstudio_pipeline.export.onnx_guard import OnnxFileRejected, check_onnx_file
    from pitstudio_pipeline.export.precision import make_variant

    manifest: dict[str, Any] = {"models": {}}
    for spec in models:
        entry: dict[str, Any] = {"kind": spec["kind"], "variants": {}, "state": "available"}
        manifest["models"][spec["id"]] = entry
        onnx_path = resolve(spec["root"], spec["onnx"])
        if not onnx_path.is_file():
            entry.update(state="not available", reason="no ONNX export at the registered path")
            continue
        try:
            info = check_onnx_file(onnx_path)
        except OnnxFileRejected as exc:
            entry.update(state="not available", reason=f"ONNX file rejected: {exc.reason}")
            continue
        try:
            inputs = load_inputs(spec)
        except (OSError, KeyError) as exc:
            entry.update(state="not available", reason=f"golden inputs missing ({type(exc).__name__})")
            continue
        session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        name = spec["input_name"]
        refs = [session.run(None, {name: inputs[i : i + 1]}) for i in range(len(inputs))]
        ref_dir = run / "reference" / spec["id"]
        ref_dir.mkdir(parents=True, exist_ok=True)
        np.save(ref_dir / "inputs.npy", inputs)
        for j in range(len(refs[0])):
            np.save(ref_dir / f"ref_output{j}.npy", np.concatenate([r[j] for r in refs]))
        entry.update(onnx=str(onnx_path), onnx_sha256=info.sha256, n_inputs=len(inputs), n_outputs=len(refs[0]))
        config = {"opset": 17, "gemm_heavy": False}
        vdir = run / "variants" / spec["id"]
        entry["variants"]["fp32"] = {"onnx": str(onnx_path), "onnx_sha256": info.sha256}
        try:
            path16 = make_variant(onnx_path, vdir / "fp16.onnx", "fp16", config=config)
            entry["variants"]["fp16"] = {"onnx": str(path16), "onnx_sha256": sha256_file(path16)}
        except Exception as exc:  # recorded; the other variants still run
            entry["variants"]["fp16"] = {
                "state": "not available",
                "reason": f"fp16 conversion failed: {type(exc).__name__}: {exc}"[:300],
            }
        digests = {
            hashlib.sha256(np.ascontiguousarray(inputs[i : i + 1]).tobytes()).hexdigest() for i in range(len(inputs))
        }
        calib = calibration_inputs(spec, digests)
        if calib is None:
            entry["variants"]["int8"] = {
                "state": "not available",
                "reason": "no calibration set of 500 training inputs is wired for this model",
            }
        else:
            try:
                path8 = make_variant(
                    onnx_path, vdir / "int8.onnx", "int8", config=config, calibration_inputs=calib, eval_digests=digests
                )
                entry["variants"]["int8"] = {"onnx": str(path8), "onnx_sha256": sha256_file(path8)}
            except Exception as exc:
                entry["variants"]["int8"] = {
                    "state": "not available",
                    "reason": f"int8 quantisation failed: {type(exc).__name__}: {exc}"[:300],
                }
    (run / "variants.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


# ----------------------------------------------------------------------------------------------------------------------
# build
# ----------------------------------------------------------------------------------------------------------------------


class PolygraphyBackend:
    """The real TensorRT backend of `pitstudio.accel.engines.build_engines` (strongly typed, TF32 cleared)."""

    def __init__(self, trt, guard) -> None:
        self.version, self.guard = trt.__version__, guard

    def build(self, onnx_path: Path, *, precision: str, profile: dict, flags: dict, out_path: Path) -> None:
        from polygraphy.backend.trt import CreateConfig, EngineFromNetwork, NetworkFromOnnxBytes, save_engine

        guard_step(self.guard)
        cache = Path(flags["timing_cache"])
        cache.parent.mkdir(parents=True, exist_ok=True)
        network = NetworkFromOnnxBytes(onnx_path.read_bytes(), strongly_typed=flags["strongly_typed"])
        config = CreateConfig(tf32=flags["tf32"], load_timing_cache=str(cache) if cache.exists() else None)
        engine = EngineFromNetwork(network, config=config, save_timing_cache=str(cache))()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        save_engine(engine, str(out_path))


def run_build(args: argparse.Namespace) -> int:
    from pitstudio_pipeline.export.onnx_guard import check_onnx_file

    from pitstudio.accel.engines import build_engines
    from pitstudio.export.variant_rules import (
        check_variant_request,  # noqa: F401  (refusals happen inside build_engines)
    )

    run = folder("PITSTUDIO_MODELS", "models/local") / "accel" / os.environ.get("PITSTUDIO_ACCEL_RUN", "run-001")
    run.mkdir(parents=True, exist_ok=True)
    models = load_registry()
    use_cuda13_runtime_wheel()
    trt = import_trt()
    fingerprint = assert_cuda_visible()
    manifest = stage_a(run, models)
    licence = tensorrt_licence_check()
    print(
        f"[build] stage A done; TensorRT {trt.__version__}; GPU {fingerprint['gpu_name']}; licence ok={licence.ok}",
        flush=True,
    )
    variants = []
    for model_id, entry in manifest["models"].items():
        for precision, variant in entry.get("variants", {}).items():
            if "onnx" in variant:
                batch = (1,)  # the exported graphs have a fixed batch of 1: one profile point
                variants.append(
                    {
                        "model": model_id,
                        "precision": precision,
                        "onnx": Path(variant["onnx"]),
                        "config": {"opset": 17, "gemm_heavy": False},
                        "batch_sizes": batch,
                    }
                )
    if args.dry_run:
        for v in variants:
            check_onnx_file(v["onnx"])
        assert hasattr(trt.NetworkDefinitionCreationFlag, "STRONGLY_TYPED")
        from gpu_guard import Guard

        assert Guard(read_temp=lambda: 60, whea=lambda s: 0).check() == "ok"
        print(
            f"[build] DRY RUN OK: {len(variants)} variants ready; stopped before the first TensorRT build", flush=True
        )
        return 0

    lock = acquire_lock()
    try:
        guard = start_guard()
        records = build_engines(
            variants, PolygraphyBackend(trt, guard), run_dir=run, clock=RealClock, onnx_guard=check_onnx_file
        )
    finally:
        lock.release()
    out = [
        {
            "model": r.model,
            "precision": r.precision,
            "status": r.status,
            "tensorrt_version": r.tensorrt_version,
            "engine_path": None if r.engine_path is None else str(r.engine_path),
            "engine_sha256": r.engine_sha256,
            "builder_config": r.builder_config,
            "build_time_s": round(r.build_time_s, 2),
            "error": r.error,
        }
        for r in records
    ]
    (run / "build-manifest.json").write_text(
        json.dumps(
            {"tensorrt": trt.__version__, "licence": {"ok": licence.ok, "sha256": licence.sha256}, "engines": out},
            indent=1,
        ),
        encoding="utf-8",
    )
    failed = [r for r in out if r["status"] != "built"]
    print(f"[build] {len(out) - len(failed)} engines built, {len(failed)} build-failed", flush=True)
    return 0


# ----------------------------------------------------------------------------------------------------------------------
# bench
# ----------------------------------------------------------------------------------------------------------------------


def fg_iou(a: np.ndarray, b: np.ndarray) -> float:
    pa, pb = a.argmax(1) > 0, b.argmax(1) > 0
    inter = (pa & pb).reshape(len(pa), -1).sum(1)
    union = (pa | pb).reshape(len(pa), -1).sum(1)
    return float(np.where(union > 0, inter / np.maximum(union, 1), 1.0).mean())


def measure_cell(call, *, backend: NvmlBackend | None, kind: str, dry: bool) -> dict[str, Any]:
    """Latency (four regime x scope entries), throughput, energy, VRAM peak and the thermal flag of one cell."""
    from pitstudio.accel.energy import measure_energy, sample_telemetry, thermal_slowdown
    from pitstudio.accel.timing import run_latency, run_throughput

    clock = RealClock()
    cell: dict[str, Any] = {"latency": [], "rejected": None}
    regimes = ("sustained",) if dry else ("spaced", "sustained")
    for regime in regimes:
        for scope in ("gpu-compute", "end-to-end"):
            fn = call if scope == "end-to-end" else getattr(call, "gpu", None)
            if fn is None:
                continue  # CUDA-event timing exists only where the runner exposes it (TensorRT)
            result = run_latency(fn, clock=clock, regime=regime, scope=scope)
            if result.status != "ok":
                cell["rejected"] = result.reason
                return cell
            cell["latency"].append(
                {
                    "regime": regime,
                    "scope": scope,
                    "gap_ms": result.gap_ms,
                    "warmup_s": round(result.warmup_s, 3),
                    "iterations": result.iterations,
                    "timed_s": round(result.timed_s, 3),
                    **{q: result.stats[q] for q in ("p50", "p90", "p95", "p99")},
                    "bootstrap": result.stats["bootstrap"],
                }
            )
    through = run_throughput(lambda size: call(), clock=clock, sizes=(1,), iterations=200 if not dry else 20)
    cell["throughput"] = through.entries if through.status == "ok" else None
    if backend is not None:
        energy = measure_energy(backend, clock, call, iterations=1000, batch=1)
        cell.update(
            joules_per_inference=energy.joules, energy_window_s=round(energy.window_s, 3), energy_reason=energy.reason
        )
        samples: list[dict[str, Any]] = []
        sampler = threading.Thread(target=lambda: samples.extend(sample_telemetry(backend, clock, duration_s=4.0)))
        sampler.start()
        peak = 0.0
        end = time.perf_counter() + 4.0
        while time.perf_counter() < end:
            call()
            peak = max(peak, backend.read("vram_used_bytes"))
        sampler.join()
        cell.update(vram_peak_bytes=int(peak), thermal_slowdown=thermal_slowdown(samples), telemetry_hz=10)
    return cell


def run_bench(args: argparse.Namespace) -> int:
    import onnxruntime as ort

    from pitstudio.accel.licence import apply_licence_policy
    from pitstudio.accel.records import check_cell_key, make_bench_record
    from pitstudio.export.comparator import compare

    root = folder("PITSTUDIO_MODELS", "models/local") / "accel" / os.environ.get("PITSTUDIO_ACCEL_RUN", "run-001")
    manifest = (
        json.loads((root / "variants.json").read_text(encoding="utf-8")) if (root / "variants.json").is_file() else None
    )
    built = {}
    if (root / "build-manifest.json").is_file():
        for e in json.loads((root / "build-manifest.json").read_text(encoding="utf-8"))["engines"]:
            built[(e["model"], e["precision"])] = e
    if manifest is None and args.dry_run:
        root.mkdir(parents=True, exist_ok=True)
        manifest = stage_a(root, load_registry())
    if manifest is None:
        raise SystemExit("no variants.json: run the engine build job (70) first")
    use_cuda13_runtime_wheel()
    trt = import_trt()
    fingerprint = assert_cuda_visible()
    licence = tensorrt_licence_check()
    models = {m["id"]: m for m in load_registry()}
    out = root / "bench"
    for sub in ("public", "local", "cells"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    plan = [
        (mid, p, b)
        for mid, e in manifest["models"].items()
        if e.get("state") == "available"
        for p in ("fp32", "fp16", "int8")
        for b in ("ort-cpu", "ort-cuda", "tensorrt")
    ]
    if args.dry_run:
        plan = [("slope-tcn", "fp32", "ort-cpu")]
    nvml = None if args.dry_run else NvmlBackend()
    lock = None if args.dry_run else acquire_lock()
    guard = None
    cells: list[dict[str, Any]] = []
    try:
        if not args.dry_run:
            guard = start_guard()
        for model_id, precision, backend in plan:
            entry = manifest["models"][model_id]
            spec = models[model_id]
            check_cell_key(backend, precision)
            variant = entry["variants"].get(precision, {})
            base = {
                "model": model_id,
                "backend": backend,
                "precision": precision,
                "tensorrt_version": trt.__version__ if backend == "tensorrt" else None,
            }
            if backend == "ort-cpu" and precision != "fp32":
                continue  # the CPU provider is the reference of the output comparison, measured for fp32 only
            if "onnx" not in variant:
                cells.append({**base, "status": "not_run", "reason": variant.get("reason", "variant not available")})
                continue
            if backend == "tensorrt" and (built.get((model_id, precision)) or {}).get("status") != "built":
                cells.append(
                    {
                        **base,
                        "status": "not_run",
                        "reason": (built.get((model_id, precision)) or {}).get("error") or "engine not built by job 70",
                    }
                )
                continue
            if guard is not None:
                guard_step(guard)
            inputs = np.load(root / "reference" / model_id / "inputs.npy")
            refs = [np.load(p) for p in sorted((root / "reference" / model_id).glob("ref_output*.npy"))]
            name = spec["input_name"]
            try:
                call, produce = make_call(backend, entry, variant, built.get((model_id, precision)), inputs, name, ort)
                outputs = produce()
                parity = compare(
                    [r[: len(outputs[0])] for r in refs], outputs, rtol=1e-3, atol=1e-5, max_abs=float("inf")
                )
                measured = measure_cell(call, backend=nvml, kind=spec["kind"], dry=args.dry_run)
            except Exception as exc:  # a failed cell is kept with its reason
                cells.append({**base, "status": "not_run", "reason": f"cell failed: {type(exc).__name__}: {exc}"[:300]})
                continue
            if measured["rejected"]:
                cells.append({**base, "status": "rejected", "reason": measured["rejected"]})
                continue
            cells.append(
                {
                    **base,
                    "status": "measured",
                    "measured": measured,
                    "output_difference": {
                        "max_abs_error": parity.max_abs_error,
                        "mismatch_fraction": parity.mismatch_fraction,
                        "fp32_tolerance_verdict": parity.verdict,
                        "mask_iou": fg_iou(refs[0][: len(outputs[0])], outputs[0]) if spec.get("mask_iou") else None,
                    },
                }
            )
            (out / "cells" / f"{model_id}-{backend}-{precision}.json").write_text(
                json.dumps(cells[-1], indent=1, default=float), encoding="utf-8"
            )
    finally:
        if lock is not None:
            lock.release()

    fp = {
        **(
            nvml.fingerprint()
            if nvml
            else {
                "gpu_name": fingerprint["gpu_name"],
                "driver": fingerprint["driver"],
                "power_limit_enforced_w": None,
                "power_source": "ac",
                "os_power_mode": "best-performance",
            }
        ),
        "ort_version": ort.__version__,
        "torch_version": "none",
    }
    run_meta = {
        "run_id": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-accel",
        "git_sha": os.environ.get("PITSTUDIO_GIT_SHA", "0" * 40),
        "date": time.strftime("%Y-%m-%d", time.gmtime()),
    }
    records = []
    for c in cells:
        entry = manifest["models"][c["model"]]
        built_e = built.get((c["model"], c["precision"])) or {}
        fingerprint_c = {
            **fp,
            "onnx_sha256": entry["variants"].get(c["precision"], {}).get("onnx_sha256") or entry["onnx_sha256"],
            "engine_sha256": built_e.get("engine_sha256") if c["backend"] == "tensorrt" else None,
            "tensorrt_licence_sha256": licence.sha256 if c["backend"] == "tensorrt" else None,
        }
        if c["status"] != "measured":
            cell = {k: c[k] for k in ("model", "backend", "precision", "tensorrt_version")} | {
                "status": c["status"],
                "reason": c["reason"],
                "latency": None,
                "throughput": None,
                "joules_per_inference": None,
                "energy_window_s": None,
                "vram_peak_bytes": None,
                "thermal_slowdown": None,
                "telemetry_hz": 10,
                "camera_streams": None,
                "parity": None,
            }
        else:
            # the numbers stay in the local cells folder: the bench record needs the PyTorch fp32 golden parity and, for
            # reduced precision, the evaluation-set task metric (layer-2 gate), neither of which this job measures
            cell = {k: c[k] for k in ("model", "backend", "precision", "tensorrt_version")} | {
                "status": "not_run",
                "reason": "golden-set parity and task-metric gate not evaluated here; numbers are in the cells folder",
                "latency": None,
                "throughput": None,
                "joules_per_inference": None,
                "energy_window_s": None,
                "vram_peak_bytes": None,
                "thermal_slowdown": None,
                "telemetry_hz": 10,
                "camera_streams": None,
                "parity": None,
            }
        records.append(make_bench_record(cell, run=run_meta, fingerprint=fingerprint_c))
    records = apply_licence_policy(records, licence)
    for r in records:
        target = "public" if r["performance"] == "public" else "local"
        (out / target / f"{r['model']}-{r['backend']}-{r['precision']}.json").write_text(
            json.dumps(r, indent=1), encoding="utf-8"
        )
    from pitstudio.accel.guards import find_local_only_records

    leaks = find_local_only_records(out / "public", local_dir=out / "local")
    if leaks:
        raise SystemExit(f"local-only records found in the public folder: {leaks}")
    print(
        f"[bench] {len(cells)} cells ({sum(1 for c in cells if c['status'] == 'measured')} measured); records in {out}",
        flush=True,
    )
    return 0


def make_call(backend, entry, variant, built_entry, inputs, name, ort):
    """Return (call, produce): `call()` runs one inference of batch 1 (and `call.gpu()` returns the GPU time when the
    runner has it); `produce()` returns the outputs for every input as arrays."""
    n = len(inputs)
    counter = {"i": 0}

    def next_input():
        counter["i"] += 1
        return inputs[counter["i"] % n : counter["i"] % n + 1]

    if backend in ("ort-cpu", "ort-cuda"):
        providers = ["CPUExecutionProvider"] if backend == "ort-cpu" else [("CUDAExecutionProvider", {"device_id": 0})]
        session = ort.InferenceSession(variant["onnx"], providers=providers)
        if backend == "ort-cuda" and session.get_providers()[0] != "CUDAExecutionProvider":
            raise RuntimeError("the CUDA execution provider did not load")

        def call():
            session.run(None, {name: next_input()})

        def produce():
            rows = [session.run(None, {name: inputs[i : i + 1]}) for i in range(n)]
            return [np.concatenate([r[j] for r in rows]).astype(np.float32) for j in range(len(rows[0]))]

        return call, produce

    from polygraphy.backend.common import BytesFromPath
    from polygraphy.backend.trt import EngineFromBytes, TrtRunner

    engine = EngineFromBytes(BytesFromPath(built_entry["engine_path"]))()
    runner = TrtRunner(engine)
    runner.activate()

    def call():
        runner.infer({name: next_input()})

    def gpu():
        runner.infer({name: next_input()})
        return runner.last_inference_time() * 1000.0

    call.gpu = gpu  # type: ignore[attr-defined]

    def produce():
        # the runner reuses its output buffers: copy every output before the next call
        rows = [{k: np.array(v) for k, v in runner.infer({name: inputs[i : i + 1]}).items()} for i in range(n)]
        keys = list(rows[0])
        return [np.concatenate([np.array(r[k]) for r in rows]).astype(np.float32) for k in keys]

    return call, produce


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("build", "bench"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return run_build(args) if args.command == "build" else run_bench(args)


if __name__ == "__main__":
    sys.exit(main())

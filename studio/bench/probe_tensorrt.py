"""Probe (pipeline/accel env): build a TensorRT 11 FP32 engine from ONNX, run it, check parity against ONNX Runtime CPU.

Regular TensorRT's licence has no benchmark clause, so its numbers are public. The probe pins the reviewed licence
text by hash; if NVIDIA changes it, the result drops to local-only until the new text is reviewed.
"""

from __future__ import annotations

import hashlib
import os
from importlib import metadata
from pathlib import Path
from typing import Any

from _common import run_probe, timer
from _onnx_model import tiny_conv

REVIEWED_LICENCE_SHA256 = "c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4"  # TensorRT SLA, 11.3 wheel
REPS = 50


def use_cuda13_runtime_wheel() -> None:
    """Make polygraphy load the CUDA 13 cudart from the nvidia-cuda-runtime wheel.

    polygraphy searches CUDA_PATH / CUDA_HOME / CUDA_PATH_V* first (a machine-wide CUDA 12 toolkit wins there), then
    nvidia/cuda_runtime (the CUDA 12 wheel layout), then PATH. The CUDA 13 wheel uses nvidia/cu13/bin/x86_64.
    """
    import nvidia

    for base in nvidia.__path__:
        d = Path(base) / "cu13" / "bin" / "x86_64"
        if d.is_dir():
            for var in [v for v in os.environ if v == "CUDA_HOME" or v.startswith("CUDA_PATH_V")]:
                del os.environ[var]
            os.environ["CUDA_PATH"] = str(d)
            os.environ["PATH"] = f"{d}{os.pathsep}{os.environ.get('PATH', '')}"
            os.add_dll_directory(str(d))
            return
    raise RuntimeError("nvidia-cuda-runtime (CUDA 13) is not installed in this environment")


def licence_sha256(dist_name: str) -> str:
    files = metadata.distribution(dist_name).files or []
    lic = next((f for f in files if f.name == "LICENSE.txt"), None)
    if lic is None:
        return "missing"
    return hashlib.sha256(Path(str(lic.locate())).read_bytes()).hexdigest()


def body(r: dict[str, Any]) -> None:
    lic_hash = licence_sha256("tensorrt-cu13-libs")
    r["versions"]["tensorrt_licence_sha256"] = lic_hash
    if lic_hash != REVIEWED_LICENCE_SHA256:
        r["publish"] = "local-only"
        r["notes"].append("TensorRT licence text changed since review — results kept local until re-reviewed")

    use_cuda13_runtime_wheel()
    import numpy as np
    import onnxruntime as ort
    import tensorrt as trt
    from polygraphy.backend.trt import CreateConfig, EngineFromNetwork, NetworkFromOnnxBytes, TrtRunner

    r["versions"].update(
        tensorrt=trt.__version__,
        polygraphy=metadata.version("polygraphy"),
        cuda_runtime=metadata.version("nvidia-cuda-runtime"),
    )
    model, arr = tiny_conv()
    with timer(r["metrics"], "engine_build_fp32_s"):
        engine = EngineFromNetwork(NetworkFromOnnxBytes(model), config=CreateConfig())()
    with TrtRunner(engine) as runner:
        y = runner.infer({"x": arr["x"]})["y"]
        times = []
        for _ in range(REPS):
            runner.infer({"x": arr["x"]})
            times.append(runner.last_inference_time())
    r["metrics"]["trt_infer_median_ms"] = round(1000 * float(np.median(times)), 3)
    ref = ort.InferenceSession(model, providers=["CPUExecutionProvider"]).run(None, {"x": arr["x"]})[0]
    err = float(np.abs(np.asarray(y) - ref).max())
    r["metrics"]["trt_vs_ort_cpu_max_abs_err"] = err
    if err > 1e-4:
        raise AssertionError(f"TensorRT and ONNX Runtime CPU disagree: max abs error {err:.2e}")


if __name__ == "__main__":
    run_probe("tensorrt", "public", body)

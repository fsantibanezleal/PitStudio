"""Probe (pipeline env, extra cu130): PyTorch CUDA GEMM throughput and torch (cuDNN) vs ONNX Runtime CUDA EP parity."""

from __future__ import annotations

import time
from typing import Any

from _common import run_probe, timer
from _onnx_model import tiny_conv

GEMM_N, GEMM_REPS, ORT_REPS = 4096, 20, 50


def body(r: dict[str, Any]) -> None:
    import numpy as np
    import onnxruntime as ort
    import torch

    ort.preload_dlls()  # the CUDA EP then uses the CUDA 13 / cuDNN 9 DLLs that torch ships (torch's lib dir first)
    r["versions"].update(
        torch=torch.__version__,
        torch_cuda=torch.version.cuda,
        cudnn=str(torch.backends.cudnn.version()),
        onnxruntime=ort.__version__,
    )
    if not torch.cuda.is_available():
        raise RuntimeError("torch sees no CUDA device")
    dev = torch.device("cuda:0")
    major, minor = torch.cuda.get_device_capability(0)
    r["metrics"].update(device=torch.cuda.get_device_name(0), arch=f"sm_{major}{minor}")

    for name, dtype in (("fp16", torch.float16), ("bf16", torch.bfloat16)):
        a = torch.randn(GEMM_N, GEMM_N, device=dev, dtype=dtype)
        b = torch.randn(GEMM_N, GEMM_N, device=dev, dtype=dtype)
        _ = a @ b
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        for _ in range(GEMM_REPS):
            _ = a @ b
        torch.cuda.synchronize()
        seconds = time.perf_counter() - t0
        r["metrics"][f"gemm_{name}_{GEMM_N}_tflops"] = round(2 * GEMM_N**3 * GEMM_REPS / seconds / 1e12, 1)
        del a, b

    model, arr = tiny_conv()
    sess = ort.InferenceSession(model, providers=[("CUDAExecutionProvider", {"use_tf32": 0}), "CPUExecutionProvider"])
    if sess.get_providers()[0] != "CUDAExecutionProvider":
        raise RuntimeError(f"ONNX Runtime fell back to {sess.get_providers()} — CUDA EP did not load")
    y_ort = sess.run(None, {"x": arr["x"]})[0]
    with timer(r["metrics"], f"ort_cuda_conv_x{ORT_REPS}_s"):
        for _ in range(ORT_REPS):
            sess.run(None, {"x": arr["x"]})

    torch.backends.cudnn.allow_tf32 = False  # compare full FP32 on both sides
    with torch.no_grad():
        f = torch.nn.functional
        y_t = (
            f.relu(
                f.conv2d(
                    torch.from_numpy(arr["x"]).to(dev),
                    torch.from_numpy(arr["w"]).to(dev),
                    torch.from_numpy(arr["b"]).to(dev),
                    padding=1,
                )
            )
            .mean((2, 3), keepdim=True)
            .cpu()
            .numpy()
        )
    err = float(np.abs(y_ort - y_t).max())
    r["metrics"]["ort_vs_torch_max_abs_err"] = err
    r["metrics"]["torch_max_vram_mb"] = round(torch.cuda.max_memory_allocated() / 2**20)
    if err > 1e-4:
        raise AssertionError(f"ONNX Runtime and torch disagree: max abs error {err:.2e}")


if __name__ == "__main__":
    run_probe("torch_ort", "public", body)

# ONNX Runtime and ONNX Runtime Web

> The inference runtime on both sides of PitStudio: the CPU parity reference and the CUDA baseline in the pipeline,
> and the WebGPU / WASM engine that runs the learned models live in the browser. · Part of: [Frameworks](README.md) ·
> Related: [PyTorch](pytorch.md) · [TensorRT](tensorrt.md) · [Export, parity and acceleration](../models/export-parity-acceleration.md) ·
> [Compute tiers](../web/compute-tiers.md)

## What and why

ONNX Runtime executes ONNX graphs through execution providers (EPs): CPU, CUDA, TensorRT and, in the browser, WebGPU
and WASM. PitStudio uses one ONNX file per model for every target, so the numbers on the web come from the same graph
that was checked against PyTorch.

| Role | Where | Why |
|---|---|---|
| **Parity reference** | ORT CPU EP in `pipeline/` | deterministic CPU numbers every other backend is compared to |
| **GPU baseline** | ORT CUDA EP (`onnxruntime-gpu`) | the honest "no special engine" GPU number next to TensorRT |
| **Live in the browser** | `onnxruntime-web` WebGPU → WASM | GNS, FNO, forecasters, meta-model, D-FINE-N, D-FINE-S int8, U-Net, policies, each ≤ 25 MB |

The ORT TensorRT EP is a third GPU path, kept apart: ORT 1.30 builds it against TensorRT 10.14.1.48, not 11.x [1][2]
([TensorRT](tensorrt.md)).

## Identity

| Item | Value |
|---|---|
| `onnxruntime` / `onnxruntime-gpu` | 1.30.0 (2026-09-10) in `pipeline/uv.lock`; `onnxruntime-gpu` 1.30.0 (CUDA EP only) in `pipeline/accel/uv.lock` [3] |
| `onnx` / `onnxslim` | 1.23.1 / 0.1.97 in the same locks |
| CUDA | GPU packages are built with CUDA 13.0 by default since 1.27 [4] |
| `onnxruntime-web` | 1.30.0, **planned**; not yet in `web/pnpm-lock.yaml` [5] |
| Licence | MIT · open |
| Ring | Adopt (CPU, Web) · Trial (GPU) |
| Environments | `pipeline/`, `pipeline/accel/`, `web/` |

On the reference machine, `ort.preload_dlls()` lets the CUDA EP use the CUDA 13 cuBLAS, cudart and cuDNN DLLs that
the torch cu130 wheel ships, so no CUDA toolkit is installed.

## How PitStudio uses it

- **`s60_export`** writes each model as ONNX at an explicit opset (17–19 for web models, because WebGPU kernels such as
  `GridSample` need it) and an **explicit IR version**: `onnx` now writes IR 14 by default and ONNX Runtime 1.30 reads at
  most IR 13, so an unpinned export fails to load. The capability probe pins IR 10 for its test graph.
- **Parity** is checked layer by layer: CPU EP vs PyTorch (fp32 rtol 1e-3, atol 1e-5), then every other backend vs the
  stored PyTorch fp32 outputs that the CPU EP matched
  ([DEC-0010](../architecture/decisions/DEC-0010-tensorrt-per-engine-parity.md)).
- **In the browser** the WebGPU EP is the recommended path; the WebGL EP and JSEP are being phased out [6]. Outputs can
  stay on the GPU (`preferredOutputLocation: 'gpu-buffer'`) [7]. Models load only on user action; the self-hosted ORT
  runtime is about 26.8–28.3 MB of `.wasm` plus glue (measured for the web budget).
- **Operator gaps on WebGPU** shape the exports: `conv3d` is unsupported; NonMaxSuppression, ScatterElements and RoiAlign
  are unconfirmed [8]. Detection needs no NMS in the browser: D-FINE is NMS-free and its export keeps the top-K
  selection inside the graph ([D-FINE](../models/d-fine.md)). The GNS ships a dense-adjacency variant that avoids
  scatter.

Artefacts it will produce: ONNX files with parity reports, the in-browser timing per tier (T1 WebGPU, T2 WASM), and the
"Acceleration" table rows for ORT CPU and ORT CUDA.

## Licence and redistribution

MIT. The browser runtime is self-hosted inside the Pages artefact; models we train are published when their inputs'
licences allow it ([Models](../models/README.md)).

## Assumptions and limits

- `onnxruntime` and `onnxruntime-gpu` are never co-installed in one environment (the `cpu` and `cu130` extras exclude
  each other).
- The ORT TensorRT EP documentation's requirement table stops at ORT 1.22 / TensorRT 10.9 and is stale [9]; the
  CI variables of the 1.30 release are the trustworthy source [1]. The TensorRT 10.14 libraries for that EP are
  planned for `pipeline/` and are **not yet** in its lock.
- An open ORT pull request reports that, on TensorRT 10, a version-check bug converts strongly typed networks to weak
  ones, cutting FP16 throughput to about 31 % [10]. Inside the ORT TensorRT EP, PitStudio feeds FP32 ONNX plus the
  FP16 flag, or QDQ models, never pre-cast FP16 graphs.
- Browser parity is tested by system class: exact for deterministic models, tolerance-based for chaotic ones.

## In PitStudio

- Probe: `probe_torch_ort.py` runs a Conv → ReLU → GlobalAveragePool graph (opset 17, IR 10) on the CUDA EP with TF32
  off and fails above a max absolute difference of 1e-4 against torch ([Capabilities probe](../studio/capabilities-probe.md)).
  **Not yet run** on the GPU.
- Status of model inference: **not yet run** — produced in the data-and-models phase. Reported then: per-model parity (fp32 rtol 1e-3 /
  atol 1e-5) and in-browser timings per tier.

## References

1. Microsoft. *ONNX Runtime v1.30.0 CI variables* (`cuda13_trt_version`).
   https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/tools/ci_build/github/azure-pipelines/templates/common-variables.yml
2. Microsoft. *Issue #32278: align CPython 3.14 CUDA 13 wheels with TensorRT 11*. https://github.com/microsoft/onnxruntime/issues/32278
3. Python Package Index. *onnxruntime-gpu* 1.30.0. https://pypi.org/pypi/onnxruntime-gpu/1.30.0/json
4. Microsoft. *CUDA execution provider*. https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html
5. npm. *onnxruntime-web* 1.30.0. https://registry.npmjs.org/onnxruntime-web/latest
6. Microsoft. *ONNX Runtime releases* (WebGL and JSEP phase-out). https://github.com/microsoft/onnxruntime/releases
7. Microsoft. *WebGPU execution provider tutorial*. https://onnxruntime.ai/docs/tutorials/web/ep-webgpu.html
8. Microsoft. *ORT-web WebGPU operator list*. https://github.com/microsoft/onnxruntime/blob/main/js/web/docs/webgpu-operators.md
9. Microsoft. *TensorRT execution provider*. https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html
10. Microsoft. *Pull request #29779: fix TensorRT build version check for 11*. https://github.com/microsoft/onnxruntime/pull/29779

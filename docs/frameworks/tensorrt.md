# TensorRT

> NVIDIA's inference compiler, used in an isolated environment to build fp32, fp16, int8 and fp8 engines of
> PitStudio's own ONNX models, each accepted only after a per-engine parity check. · Part of: [Frameworks](README.md) ·
> Related: [ONNX Runtime](onnx-runtime.md) · [TensorRT bench guide](../guides/tensorrt-bench.md) ·
> [Export, parity and acceleration](../models/export-parity-acceleration.md) ·
> [DEC-0010](../architecture/decisions/DEC-0010-tensorrt-per-engine-parity.md)

## What and why

TensorRT builds a device-specific engine from an ONNX graph and runs it with fused kernels and reduced precision.
PitStudio uses it to answer a mining question honestly: **how much inference does one laptop GPU deliver for pit
cameras and fragmentation images, at a stated accuracy?** Its strongest case is a high-resolution pit camera tiled into
detector crops, where throughput sets how many camera streams one GPU can serve ([B2](../cases/b2-synthetic-perception.md)).
Its weakest case is a tiny policy at batch 1, where it may give no gain — a valid published finding.

Version 11 changed the precision model: implicit quantisation and `IInt8Calibrator` were removed, networks are strongly
typed by default and the per-precision builder flags are gone [1]. FP16, INT8 and FP8 are therefore written into the
ONNX graph **before** the build: FP16 by ORT's float16 converter, INT8 and FP8 as Q/DQ nodes from ORT's quantiser [2][3].

Rejected alternatives: Torch-TensorRT (pins TensorRT 11.1, a third TensorRT version) [4]; `nvidia-modelopt[onnx]` (pins
`onnxruntime-gpu==1.22.0` on Windows, which has no Python 3.14 wheel) [5]; publishing TensorRT for RTX numbers
(licence, below).

## Identity

| Item | Value |
|---|---|
| Packages | `tensorrt-cu13-bindings` and `tensorrt-cu13-libs` 11.3.0.99, `polygraphy` 0.53.6, `nvidia-cuda-runtime` 13.4.92, pinned in `pipeline/accel/uv.lock` |
| Release | 11.3.0.99 uploaded 2026-09-09; built against CUDA 13.4 [6][7] |
| Wheels | cp314 Windows wheels only on `pypi.nvidia.com` (PyPI hosts sdists); "Windows Python 3.14 support is preliminary" [8][9] |
| Driver | "CUDA 13.x: NVIDIA driver r580 or later" [10] |
| Licence | TensorRT Software License Agreement · reference-only (engines never committed); **numbers of our own models are publishable** |
| Ring | Trial (scoped to `pipeline/accel/`) |
| Environment | `pipeline/accel/` (Python 3.14), isolated from `pipeline/` |

**Why an isolated environment:** the ORT TensorRT EP in `pipeline/` needs the TensorRT 10.14 libraries, and both
versions share one distribution name, so they cannot live in one venv [2][11].

**`nvidia-cuda-runtime` and the CUDA_PATH pitfall.** The TensorRT wheels ship nvinfer and the parser only, so the lock
adds the CUDA 13 runtime for Polygraphy's device buffers. Two things steer Polygraphy to the wrong `cudart`: it knows
only the CUDA 12 wheel layout, and a machine-wide CUDA 12 toolkit's `CUDA_PATH` comes first in its search. The probe
therefore points `CUDA_PATH` (and the DLL search path) at the CUDA 13 wheel's `bin` folder before importing TensorRT.

## How PitStudio uses it

- **`s62_accel`** (1–2 h): fp32 (TF32 cleared for parity), fp16, int8 and fp8 engines per model. FP8 needs Q/DQ at opset
  19 and is used only for GEMM-heavy models; Ada has no optimised FP8 group or depthwise convolutions, so CNNs use INT8
  [12]. FP4 is emulated on this hardware and not used [13].
- **`s64_bench`** (2–4 h): latency p50/p90/p99 (spaced and sustained regimes), throughput by batch, joules per inference
  from NVML energy, VRAM, accuracy delta and parity. Backends: PyTorch, ORT CPU, ORT CUDA, ORT TensorRT EP, native
  TensorRT 11.3.
- **Parity gate** on every engine and every TensorRT version: fp32 within rtol 1e-3 / atol 1e-5 of the reference;
  reduced precision within 1 percentage point of the task metric; detectors also re-run the dust, night and rain
  corruption curves, because INT8 robustness under degraded inputs is not guaranteed [14]. A failing variant is
  **reported as rejected**, never dropped.
- Web: an "Acceleration" tab on `/results`, labelled "measured on one laptop GPU, not a general benchmark". An
  independent study found TensorRT fastest on GPUs but "does not outperform plain PyTorch for the transformer-based
  model" [15]; our DETR results are read against that.

## Licence and redistribution

The installed 11.3.0.99 wheels carry the TensorRT SLA as `LICENSE.txt` (47,141 bytes, SHA-256
`c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4`), which has no benchmark, performance-data or
competitive-analysis clause [16]. Numbers of our own models are therefore publishable
([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)). The probe pins that hash: if the text
changes, results drop to local-only until it is re-read. **TensorRT for RTX** is different: its SLA §2.13 forbids
disclosing benchmark or performance data without NVIDIA's written permission [17]. Engines are device- and
version-specific and never committed or uploaded [18].

## Assumptions and limits

- **TensorRT #4813 (open):** a strongly typed FP32 engine of **D-FINE-S** on TensorRT 11.1 silently produced wrong
  results (scores off by up to 0.15, boxes by up to 597 px, real-data recall 0.49 → 0.34); comments report it also on an
  Ada laptop GPU (sm_89) and on TensorRT 10.14 and 10.16 [19]. D-FINE is our primary detector, so **no TensorRT version
  or EP is assumed safe**.
- **#4838 (open):** an FP16 grouped-convolution model fails to build on 11.2.1.2 on an Ada GPU [20].
- **#3650:** ScatterElements with reduction fails when indices outnumber outputs — the GNS case [21]; the dense MatMul
  variant is the fallback.
- 11.3 known issue: GridSample FP16 context creation may fail on Windows on an RTX 5080 [7].
- Laptop throttling makes numbers drift: spaced and sustained regimes, throttle reasons logged, clocks recorded (locking
  them needs admin and is not used) [22].

## In PitStudio

- Probe: `probe_tensorrt.py` builds an FP32 engine of the probe graph with Polygraphy and fails above a max absolute
  difference of 1e-4 against ORT CPU ([Capabilities probe](../studio/capabilities-probe.md)). Checked without a GPU: the
  licence hash and the CUDA 13 `cudart` resolution. **Not yet run** on the GPU.
- Status of model engines: **not yet run** — produced in the data-and-models phase. Reported then: per-engine parity on every TensorRT
  version and EP (fp32 rtol 1e-3 / atol 1e-5; reduced precision Δ ≤ 1 pp), with failing variants listed as rejected.

## References

1. NVIDIA. *TensorRT 11.0.0 release notes*. https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/release-notes-11/11.0.0.html
2. Microsoft. *ORT float16 converter* (v1.30.0). https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/onnxruntime/python/tools/transformers/float16.py
3. Microsoft. *ORT quantisation enums* (QDQ, QInt8, QFLOAT8E4M3FN). https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/onnxruntime/python/tools/quantization/quant_utils.py
4. Python Package Index. *torch-tensorrt* 2.14.0. https://pypi.org/pypi/torch-tensorrt/json
5. Python Package Index. *nvidia-modelopt* 0.47.0. https://pypi.org/pypi/nvidia-modelopt/0.47.0/json
6. Python Package Index. *tensorrt* 11.3.0.99. https://pypi.org/pypi/tensorrt/json
7. NVIDIA. *TensorRT 11.3.0 release notes*. https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/release-notes-11/11.3.0.html
8. NVIDIA. *pypi.nvidia.com tensorrt-cu13-bindings*. https://pypi.nvidia.com/tensorrt-cu13-bindings/
9. NVIDIA. *TensorRT 11.1.0 release notes*. https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/release-notes-11/11.1.0.html
10. NVIDIA. *TensorRT prerequisites*. https://docs.nvidia.com/deeplearning/tensorrt/latest/installing-tensorrt/prerequisites.html
11. NVIDIA. *pypi.nvidia.com tensorrt-cu13-libs*. https://pypi.nvidia.com/tensorrt-cu13-libs/
12. NVIDIA. *TensorRT 10.3.0 release notes* (FP8 on Ada). https://docs.nvidia.com/deeplearning/tensorrt/10.x.x/getting-started/release-notes-10/10.3.0.html
13. NVIDIA. *TensorRT support matrix*. https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/support-matrix.html
14. Karimov et al. (2025). *Quantization Robustness to Input Degradations for Object Detection*. DOI 10.48550/arXiv.2508.19600
15. Gomez Fernandez et al. (2026). *Benchmarking Edge Inference Strategies for Deep Learning Models in Industrial Machine
    Vision* (IEEE COINS 2026). DOI 10.48550/arXiv.2607.11356
16. NVIDIA. *TensorRT Software License Agreement*. https://docs.nvidia.com/deeplearning/tensorrt/latest/reference/sla.html
17. NVIDIA. *TensorRT for RTX Software License Agreement*. https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/reference/sla.html
18. NVIDIA. *TensorRT engine compatibility*. https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/engine-compatibility.html
19. NVIDIA. *TensorRT issue #4813*. https://github.com/NVIDIA/TensorRT/issues/4813
20. NVIDIA. *TensorRT issue #4838*. https://github.com/NVIDIA/TensorRT/issues/4838
21. NVIDIA. *TensorRT issue #3650*. https://github.com/NVIDIA/TensorRT/issues/3650
22. NVIDIA. *TensorRT performance benchmarking*. https://docs.nvidia.com/deeplearning/tensorrt/latest/performance/benchmarking.html

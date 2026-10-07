# DEC-0010: TensorRT 11.3 with a parity gate per engine

> Accelerated inference uses native TensorRT 11.3 in `pipeline/accel/` and the ONNX Runtime TensorRT execution provider
> (TensorRT 10.14) in `pipeline/`; every engine, on every TensorRT version and execution provider, must pass a parity
> check against the ONNX reference before any number is published, because a known wrong-output issue affects several
> TensorRT versions. · Part of: [decisions](README.md) · Related: [TensorRT](../../frameworks/tensorrt.md) ·
> [export, parity and acceleration](../../models/export-parity-acceleration.md) · [TensorRT bench](../../guides/tensorrt-bench.md)

**Status:** Accepted, 2026-10-04

## Context

The studio is meant to show how much faster PitStudio's own detectors, segmenters and surrogates run when compiled for
the GPU, as an edge-deployment story (onboard truck or crusher compute). The facts as of October 2026:

- **TensorRT 11.3** was released on 8 September 2026 and is built against CUDA 13.4 [1]. It supports compute capability
  7.5 and above (Ada is 8.9), Windows 11 and Python 3.10–3.14 [2]; the Windows cp314 bindings come from NVIDIA's package
  index [3]. Whether a CUDA 13.4 build runs on the R580 / CUDA 13.0 driver is a smoke-test question.
- **A known wrong-output issue.** TensorRT issue #4813 reports wrong FP32 results for D-FINE-S (one of PitStudio's
  detectors) on TensorRT 11.1; comments report the same class of problem on an sm_89 laptop GPU and on TensorRT
  10.16.1.11 and 10.14.1.48 [4]. No TensorRT version can be assumed safe for this model family.
- **Engines are device- and version-specific.** A TensorRT engine is tied to the device type and the TensorRT version it
  was built with [5], so engines are build products, never artefacts to commit.
- **Other routes.** ONNX Runtime's TensorRT execution provider page documents TensorRT 10.9 with CUDA 12 [6]; Torch-
  TensorRT 2.14.0 pins its own TensorRT 11.1, a third version [7]; ModelOpt's ONNX extra pins an old ONNX Runtime on
  Windows and its Windows guide requires Python < 3.14 [8] [9]; TensorRT for RTX forbids publishing performance data [10].
- **Licence.** The regular TensorRT licence has no benchmark clause, so numbers of PitStudio's own models are
  publishable ([DEC-0005](DEC-0005-performance-data-licence-rule.md)).

## Decision

1. **Two TensorRT paths, two environments.** Native TensorRT 11.3 with Polygraphy in `pipeline/accel/` (stages
   `s62_accel` → `s64_bench`), and ONNX Runtime with its TensorRT execution provider (TensorRT 10.14 libraries) in
   `pipeline/`. They cannot share an environment ([DEC-0001](DEC-0001-isolated-studio-environments.md)).
2. **Parity gate per engine.** Every engine (fp32, fp16, int8, fp8 where supported) on every TensorRT version and
   execution provider is compared with the ONNX reference on held-out inputs: fp32 within rtol 1e-3 / atol 1e-5;
   reduced precision within 1 percentage point of the task metric. A failing variant is reported as **rejected**, with
   its numbers, never silently dropped.
3. **What is published.** For each model: PyTorch, ORT CPU, ORT CUDA and TensorRT fp32 / fp16 / int8 / fp8 latency,
   throughput, energy per inference and accuracy change, each with its parity result, labelled "our hardware, not a
   comparative benchmark". Engines and timing caches are never committed or released.
4. **The licence is re-checked.** The capability probe pins the TensorRT `LICENSE.txt` by SHA-256; if the text changes,
   results drop to local-only.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Torch-TensorRT | Compile directly from PyTorch | Pins a third TensorRT version (11.1) [7] | One more version to validate, no new capability |
| ModelOpt for quantisation | NVIDIA's quantisation toolkit | Its Windows path does not resolve on Python 3.14 [8] [9] | Not installable in the pipeline environment |
| TensorRT for RTX as published evidence | Tuned for RTX consumer GPUs | Its licence forbids publishing performance data [10] | Licence; may be used locally only |
| Trust one TensorRT version without parity checks | Less work | Known wrong outputs on several versions [4] | Silent wrong results are unacceptable |

## Consequences

**Positive.** Every published acceleration number is backed by a parity result; wrong-output engines are caught and
shown as rejected; the edge-deployment story stays honest.

**Negative, accepted.** Building and checking engines for several precisions and paths costs GPU hours (an estimated
4–7 h, measured by the runner). The bootstrap found practical traps: the TensorRT wheels ship only the inference library
and parser, so `pipeline/accel/` adds the CUDA 13 runtime (13.4.92); Polygraphy 0.53.6 knows only the CUDA 12 wheel
layout, and a machine-wide CUDA 12.4 `CUDA_PATH` would load the wrong runtime, so the probe points `CUDA_PATH` at the
CUDA 13 wheel.

**Watch.** Issue #4813; TensorRT 11 on the R580 driver; the ONNX Runtime TensorRT provider's supported versions.

## References

1. TensorRT 11.3.0 release notes. https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/release-notes-11/11.3.0.html
2. TensorRT support matrix. https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/support-matrix.html
3. NVIDIA package index: `tensorrt-cu13-bindings`. https://pypi.nvidia.com/tensorrt-cu13-bindings/
4. TensorRT issue #4813 (wrong FP32 results for D-FINE-S). https://github.com/NVIDIA/TensorRT/issues/4813
5. TensorRT engine compatibility. https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/engine-compatibility.html
6. ONNX Runtime TensorRT execution provider. https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html
7. `torch-tensorrt` on PyPI. https://pypi.org/pypi/torch-tensorrt/json
8. `nvidia-modelopt` 0.47.0 on PyPI. https://pypi.org/pypi/nvidia-modelopt/0.47.0/json
9. ModelOpt installation for Windows. https://nvidia.github.io/Model-Optimizer/getting_started/windows/_installation_for_Windows.html
10. TensorRT for RTX software license agreement. https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/reference/sla.html

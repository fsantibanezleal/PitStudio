# TensorRT bench

> Build TensorRT engines (fp32 / fp16 / int8 / fp8) from PitStudio's exported ONNX models, gate every engine on parity
> with the stored PyTorch fp32 reference outputs, and benchmark latency, throughput and energy against PyTorch and ONNX Runtime —
> with numbers that may be published. · Part of: [Guides](README.md) · Related: [TensorRT](../frameworks/tensorrt.md) ·
> [export, parity and acceleration](../models/export-parity-acceleration.md) ·
> [DEC-0010 TensorRT per-engine parity](../architecture/decisions/DEC-0010-tensorrt-per-engine-parity.md) ·
> [ONNX Runtime](../frameworks/onnx-runtime.md)

## What and why

**Goal:** show what accelerated inference does for PitStudio's own models (detectors, U-Net, surrogates, policies) on
an RTX laptop GPU, as edge-deployment evidence, without ever trusting an engine that has not been checked. TensorRT can
silently produce wrong outputs: an open issue reports wrong FP32 results for D-FINE-S under TensorRT 11.1
strongly-typed builds, with comments reporting the same on Ada (sm_89) laptops and on TensorRT 10.16 and 10.14 [1].
PitStudio therefore assumes **no TensorRT version is safe**: every engine, on every TensorRT version and execution
provider, passes a parity gate or is reported as rejected.

**Status:** the capability probe for TensorRT exists (`studio/bench/probe_tensorrt.py`); the stages `s62_accel` and
`s64_bench` are written in the build phase; no model has been trained, so no engine exists. Results: **Not yet run** —
produced in the data-and-models phase.

## Prerequisites

- [Set up the studio](set-up-the-studio.md): `pipeline/` (PyTorch cu130, ONNX Runtime GPU 1.30 with the TensorRT 10.14
  libraries its TensorRT execution provider uses [2]) and `pipeline/accel/` (TensorRT 11.3.0.99 `tensorrt-cu13-*`
  wheels, Polygraphy, ONNX Runtime GPU and the CUDA 13 runtime wheel). The two TensorRT versions cannot share an
  environment.
- A GPU of compute capability ≥ 7.5; TensorRT 11.3 lists 8.9 (Ada), Windows 11, and Python 3.10–3.14 wheels [3].
  TensorRT 11.3 is built against CUDA 13.4 [4], which runs on an R580 (CUDA 13.0) driver only under CUDA minor-version
  compatibility [5]; the probe checks it on the machine.
- The pip wheels do not include `trtexec` [6]; engines are built with the Python API and Polygraphy.
- Exported ONNX models from `s60_export` (opset 17–19, IR version pinned; see Troubleshooting).

## Steps

1. **Run the capability probe.** It builds a TensorRT FP32 engine from a small ONNX graph, runs it, and checks parity
   against ONNX Runtime CPU; it also hashes TensorRT's `LICENSE.txt` against the reviewed text.

   ```bash run deferred=P6
   uv run --extra runner python studio/bench/run_bench.py tensorrt torch_ort
   ```

2. **Export the models** with parity against PyTorch (`s60_export`), then **build the engines** in `pipeline/accel/`:
   fp32, fp16, int8 (calibrated) and fp8 where the model allows it. Engines stay local: they are tied to the TensorRT
   version and the GPU, and they are never committed or published.

   ```bash run deferred=P6
   scripts/run_pipeline.sh --stage s60_export
   scripts/run_pipeline.sh --stage s62_accel
   ```

3. **Benchmark and gate.** `s64_bench` measures latency, throughput, energy per inference (from NVML power), the
   accuracy delta against fp32, and per-engine parity, for PyTorch, ORT CPU, ORT CUDA, ORT TensorRT EP and native
   TensorRT.

   ```bash run deferred=P6
   scripts/run_pipeline.sh --stage s64_bench
   ```

4. **Publish** the tables to the `/results` Acceleration tab and the TensorRT tool page.

   ```bash run deferred=P6
   uv run --extra runner studio publish <run_id>
   ```

## The parity gate (pre-registered)

| Engine precision | Check against | Tolerance |
|---|---|---|
| fp32 | the stored PyTorch fp32 outputs of the golden set (which ONNX Runtime CPU matches by parity layer 1) | `rtol` = $10^{-3}$, `atol` = $10^{-5}$ (and `max_abs` ≤ $10^{-4}$, `thresholds.yaml`) |
| fp16, int8, fp8 | the model's task metric at fp32 | Δ ≤ 1 percentage point; mask IoU ≥ 0.99 of fp32 for segmentation |

An engine that fails is listed as **rejected** with the failing metric; it is never silently dropped and never
benchmarked as if it were valid.

## Expected output

- Probe: `[bench] tensorrt: pass (<seconds> s)` and, in `studio/capabilities.json`, the TensorRT version, the licence
  hash result and the FP32 parity metric (public, because the regular TensorRT licence has no benchmark clause).
- Bench: one table per model with latency (median and p95, ms), throughput (items/s), energy (J/inference), accuracy
  delta (pp) and parity status per backend and precision, plus the GPU's power and throttle state during the
  measurement.

## Why these numbers may be published

| Software | Licence finding | Use |
|---|---|---|
| TensorRT 11.3 (regular) | Both 11.3.0.99 wheels ship the same `LICENSE.txt` (47,141 bytes, SHA-256 `c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4`): the TensorRT SLA, with no benchmark, performance-data or competitive-analysis clause | published; the probe pins the hash, and a changed text drops results to local-only until reviewed |
| TensorRT for RTX | SLA §2.13 requires NVIDIA's written permission to disclose benchmark or performance data [7] | internal only; never on the site |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Polygraphy loads `cudart64_12.dll` and fails | a machine-wide CUDA 12 toolkit's `CUDA_PATH` comes first in Polygraphy's search, and Polygraphy 0.53.6 knows only the CUDA 12 wheel layout | point `CUDA_PATH` at the `nvidia/cu13/bin/x86_64` folder of the `nvidia-cuda-runtime` wheel in `pipeline/accel/.venv` and drop `CUDA_HOME` / `CUDA_PATH_V*` (the probe's `use_cuda13_runtime_wheel()` does this) |
| ORT or TensorRT rejects the model's IR version | the `onnx` package now writes IR 14 by default, and ONNX Runtime 1.30 reads at most IR 13 | pin the IR version at export (the probe's model uses IR 10) |
| fp32 engine fails parity | known class of TensorRT wrong-output bugs [1] | report the variant as rejected; try the other TensorRT version / EP; never publish its latency as valid |
| Timings vary run to run | a laptop GPU spends time power- or thermally-capped | record throttle reasons with every measurement; NVIDIA's own guide locks clocks with an administrator command [8], which PitStudio does not assume |
| Engine fails to load after an upgrade | TensorRT engines are not portable across versions | rebuild; engines are cache entries keyed on the lock file |

## Assumptions and limits

- Benchmarks describe one laptop GPU under its power limit; they are "our hardware, not a comparative benchmark".
- Engines and quantised weights are local artefacts; only tables and parity results are published.

## In PitStudio

- Stages `s62_accel`, `s64_bench` extend the pipeline after `s60_export`; spec `016-export-acceleration`; the
  [export, parity and acceleration](../models/export-parity-acceleration.md) page.

## References

1. NVIDIA/TensorRT issue #4813 — wrong FP32 results for D-FINE-S under TensorRT 11.1 strongly-typed builds; also reported on sm_89 and TensorRT 10.16 / 10.14. https://github.com/NVIDIA/TensorRT/issues/4813
2. ONNX Runtime v1.30.0 CI variables — `cuda13_trt_version: '10.14.1.48'`. https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/tools/ci_build/github/azure-pipelines/templates/common-variables.yml
3. NVIDIA, "TensorRT support matrix" — SM ≥ 7.5, 8.9 listed, Windows 11, Python 3.10–3.14. https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/support-matrix.html
4. NVIDIA, "TensorRT 11.3.0 release notes" — built against CUDA 13.4. https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/release-notes-11/11.3.0.html
5. NVIDIA, "CUDA Toolkit release notes" — minor-version compatibility of CUDA 13.x on drivers ≥ 580. https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html
6. NVIDIA, "Installing TensorRT with pip" — pip wheels do not include `trtexec`. https://docs.nvidia.com/deeplearning/tensorrt/latest/installing-tensorrt/install-pip.html
7. NVIDIA, "TensorRT for RTX Software License Agreement", §2.13. https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/reference/sla.html
8. NVIDIA, "TensorRT performance benchmarking" — clock locking, throttling. https://docs.nvidia.com/deeplearning/tensorrt/latest/performance/benchmarking.html

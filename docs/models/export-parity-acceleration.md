# Export, parity and acceleration

> How every trained model becomes an ONNX file the browser and TensorRT can both read, which parity gates it must pass,
> and how TensorRT engines of our models are built, checked and published as a one-machine Acceleration table. · Part
> of: [Models](README.md) · Related: [Training recipes](training-recipes.md) · [TensorRT](../frameworks/tensorrt.md) ·
> [ONNX Runtime](../frameworks/onnx-runtime.md) · [TensorRT bench guide](../guides/tensorrt-bench.md)

## What and why

One ONNX file per model serves three runtimes: ONNX Runtime on the CPU (the parity reference), ONNX Runtime Web in the
browser (the live lane), and TensorRT on the GPU (the acceleration lane). Each runtime can change the numbers a model
produces: an operator falls back to another kernel, a precision is reduced, a compiler fuses layers. PitStudio
therefore treats every conversion as a claim to be checked, with fixed tolerances, and reports a failing variant as
rejected instead of dropping it quietly. This matters most for the primary detector: an open TensorRT issue reports
silently wrong FP32 outputs for **D-FINE-S** [1].

![Acceleration and encode flows](../assets/diagrams/acceleration-encode-flows.svg)

*Top: the same ONNX file runs on ONNX Runtime and TensorRT, and only engines that pass parity reach the published
table. Bottom: the video encode flow described in the encode guide.*

## ONNX export (`s60_export`)

| Setting | Value | Reason |
|---|---|---|
| Exporter | `torch.onnx.export` with `dynamo=True` (the default since PyTorch 2.9) [2] | the maintained exporter of PyTorch 2.14.1 (`pipeline/uv.lock`) |
| `verify` | `True` | it defaults to `False` in 2.14 [2] |
| Opset | **17–19**, chosen per model, reason recorded in the manifest | PyTorch 2.14.1 defaults to opset 20 (max 23) [3]; but `GridSample` exists at opsets 16, 20 and 22 [4], and the ONNX Runtime 1.30 WebGPU provider registers `GridSample` for opsets 16–19 only [5]. A deformable-attention detector exported at opset 20 would fall back to the CPU in the browser |
| IR version | **pinned to 10** | `onnx` 1.23.1 writes IR 14 by default, while ONNX Runtime 1.30 reads at most IR 13; the bootstrap probe model pins IR 10, and `s60_export` pins the IR version to what ONNX Runtime (Python and web) and the TensorRT parser read |
| Graph cleanup | `onnxslim` 0.1.97 | constant folding, dead-node removal |
| Unsupported operators | ONNX Script decompositions through `custom_translation_table` [2] | instead of hand-editing graphs |

Model-specific design choices that keep graphs portable:

- **Detectors (D-FINE, RF-DETR):** opset 19 so that `GridSample` keeps a WebGPU kernel; FP8 Q/DQ variants also need
  opset ≥ 19 [6].
- **GNS:** message aggregation in plain PyTorch lowers to `ScatterElements` with `reduction=add` (opset ≥ 16) [7];
  neighbour search stays outside the graph and `edge_index` is an input.
- **FNO:** the spectral layer is written as truncated real DFT matrix products, because exporting `torch.fft.rfft`
  hits an open shape-inference bug [8]; the graph then holds only `MatMul` / `Einsum`.

## Parity layers

| Layer | Compared | Tolerance (from `thresholds.yaml`) | On failure |
|---|---|---|---|
| 1. ONNX = PyTorch | ORT CPU EP fp32 vs PyTorch fp32 on a golden set of ≥ 200 vectors | rtol 1e-3, atol 1e-5, max abs ≤ 1e-4, 100 % argmax agreement | the export is fixed; nothing ships |
| 2. Reduced precision | fp16 / int8 / fp8 variant vs the fp32 model | task metric Δ ≤ 1 pp; masks IoU ≥ 0.99; detectors: corruption curves per precision | variant rejected, reason reported |
| 3. Browser = Python | ORT-web vs the Python reference, per system class | WASM fp32 max abs 1e-4; WebGPU fp32 1e-3; fp16 1e-2; top-1 agreement ≥ 0.995 | the model drops to the next tier or to PRECOMPUTE |
| 4. TensorRT engine | every engine, every TensorRT version and execution provider, vs PyTorch fp32 | fp32: rtol 1e-3 / atol 1e-5; reduced precision: Δ ≤ 1 pp | engine reported as **rejected** |

The tolerances are proposed defaults in `specs/000-foundation/thresholds.yaml`, calibrated at specification. TF32 is
cleared for every fp32 parity run, on PyTorch and on TensorRT, so that a TF32 rounding difference is never mistaken for
a bug or hides one.

## Acceleration lanes

Two TensorRT major versions are in play, and they cannot share one environment: ONNX Runtime 1.30's TensorRT execution
provider is built against TensorRT 10.14.1.48 [9], and its CUDA 13 Python 3.14 wheels request `nvinfer_10.dll` [10],
while native TensorRT 11.3 has the same distribution name. Hence two environments:

| Environment | Python | Locked today | Backends |
|---|---|---|---|
| `pipeline/` | 3.14 | `torch` 2.14.1 (+cu130), `onnxruntime-gpu` 1.30.0 | PyTorch eager / AMP, ORT CPU EP, ORT CUDA EP; ORT TensorRT EP once the TensorRT 10.14 libraries are added for `s64_bench` |
| `pipeline/accel/` | 3.14 | `tensorrt-cu13-bindings` and `tensorrt-cu13-libs` 11.3.0.99, `polygraphy` 0.53.6, `nvidia-cuda-runtime` 13.4.92, `onnxruntime-gpu` 1.30.0 | native TensorRT 11.3 engines fp32 / fp16 / int8 / fp8 |

Facts that shape the TensorRT 11 lane:

- **Strong typing only.** TensorRT 11.0 removed implicit quantization, the INT8 calibrator classes and the
  per-precision builder flags; networks are strongly typed [11]. FP16 must be written into the graph (casts), and
  INT8 / FP8 as explicit Q/DQ nodes. PitStudio uses ONNX Runtime's own tools on Python 3.14: its float16 converter,
  with `LayerNormalization`, `Softmax` and reductions kept in fp32 [12], and its static Q/DQ quantizer (`QInt8`,
  `QFLOAT8E4M3FN`) with per-channel weights and per-tensor activations [13][14]. TensorRT's Model Optimizer is not
  used: its ONNX extra pins an ONNX Runtime build that has no Python 3.14 wheel [15].
- **Precisions on this GPU (sm_89).** FP8 convolutions are supported on Ada since TensorRT 10.3, but there are no
  optimised FP8 kernels for group and depthwise convolutions, where INT8 is recommended [16]; FP4 runs only in
  emulation on this architecture [17]. FP4 and INT4 are therefore out of scope.
- **ORT TensorRT EP inputs.** An open ONNX Runtime pull request describes a version-check bug that converts strongly
  typed networks to weak ones on TensorRT 10 and cuts FP16 throughput to about 31 % [18]; the EP is fed fp32 graphs with
  its fp16 flag, or Q/DQ graphs, never pre-cast fp16 graphs.
- **Runtime libraries.** The TensorRT wheels ship `nvinfer` and the parser only. The bootstrap added the CUDA 13 runtime
  wheel to `pipeline/accel/` and found that Polygraphy 0.53.6 knows only the CUDA 12 wheel layout and finds a
  machine-wide CUDA 12 toolkit first through `CUDA_PATH`; the probe points `CUDA_PATH` at the CUDA 13 wheel's `bin`
  folder. ONNX Runtime's `preload_dlls()` covers CUDA, cuDNN and MSVC only, not TensorRT [19].
- **Engines are local.** An engine is tied to the GPU model and the TensorRT version [20]. Engines live under
  git-ignored run folders, are recorded in the manifest by SHA-256, TensorRT version and build flags, and are never
  committed or uploaded.

### Known issues that hit our models

| Issue | What is reported | PitStudio response |
|---|---|---|
| TensorRT #4813 (open) | strongly typed FP32 engine of **D-FINE-S** gives wrong outputs on TensorRT 11.1; comments report the same on an Ada laptop GPU (sm_89), on TensorRT 10.16.1.11 and on 10.14.1.48 with a related model [1] | no TensorRT path is assumed safe; layer 4 decides per engine, and a failing D-FINE engine is published as rejected |
| TensorRT #4838 (open) | FP16 grouped convolution fails to build on 11.2.1.2 on an Ada GPU; works on 10.16.1.11 [21] | affected layers stay fp32 in the cast graph, or the CNN uses INT8 |
| TensorRT #3650 (closed, fix not shown) | `ScatterElements` with reduction fails when indices outnumber outputs [22] — the GNS case (edges ≫ nodes) | tested at 1k / 2k / 10k particles; dense-incidence fallback; otherwise TensorRT is "not applicable" for the GNS |
| TensorRT 11.3 known issue | GridSample FP16 context creation may fail on Windows with an RTX 5080 [23] | covered by the same per-engine gate |

## Benchmark protocol (`s62_accel` → `s64_bench`)

`s62_accel` builds the engines (1–10 minutes per model and precision; about 1–2 h for the matrix). `s64_bench`
measures them (about 2–4 GPU-h, plus about 1 h of corruption re-evaluation). Total ≈ 4–7 GPU-h, one overnight slot
after `s60_export`, never concurrent with Isaac Sim. All durations are estimates.

- **Backends × precisions:** PyTorch eager (fp32, AMP), ORT CPU, ORT CUDA, ORT TensorRT EP, native TensorRT 11.3
  (fp32, fp16, int8, fp8 where applicable).
- **Latency mode:** batch 1; warm-up of at least 5 s; at least 1,000 timed iterations or 30 s with CUDA events;
  p50 / p90 / p99 with a bootstrap CI. Two regimes: *spaced* (a 200 ms gap between calls, as in RF-DETR's methodology,
  which uses it to reduce throttling variance [24]) and *sustained* (back to back, which exposes the laptop's power
  limit). Two scopes: GPU compute only and end to end (host-to-device and back).
- **Throughput mode:** batch sweeps {1, 4, 16, 64} for vision models, {1, 64, 4096} for policies, and particle counts
  {1k, 2k, 10k} for the GNS.
- **Energy:** NVML power sampled during the run gives joules per inference; clocks are recorded, not locked, because
  locking clocks needs elevated rights [25].
- **Accuracy:** layers 2 and 4 above, on the same golden set and task metrics; detectors re-run the dust / night / rain
  corruption curves per precision, because static INT8 detectors lost about 3–7 % mAP50-95 for a 1.5–3.3× speed-up in a
  published study, and degradation-aware calibration did not fix robustness consistently [26].
- **Outputs:** one JSON record per model × backend × precision with a fingerprint (GPU name, driver, TensorRT / ORT /
  torch versions, ONNX and engine SHA-256, power state), plus a baked table under 200 KB for the web.

### What to expect, honestly

Published detector latencies are for a T4 data-centre GPU with TensorRT FP16 at batch 1: D-FINE-N 2.12 ms and D-FINE-S
3.49 ms on TensorRT 10.4.0 [27]; RF-DETR-Seg-N 3.4 ms [28]. They are not numbers for our laptop. A 2026 industrial
study found TensorRT fastest on GPUs overall but **not** faster than plain PyTorch for its transformer model [29]. Small
models at batch 1 (dispatch policies, forecasters) are launch-bound, and "no material gain" is an expected and valid
result. The U-Net, a static-shape CNN, is the most likely INT8 winner. These are expectations, not results.

## The Acceleration tab

The web app's `/results` route has an **Acceleration** tab with:

- a model × backend × precision table: latency p50 / p99, throughput, joules per inference, VRAM, accuracy Δ and parity
  pass / fail, with rejected variants listed and their reason;
- a speed-versus-accuracy scatter;
- a "camera streams per GPU at a stated recall" panel for the synthetic-perception case B2;
- the caption "measured on one RTX 5000 Ada Laptop GPU (power-limited), Windows 11, date, commit SHA — not a general
  benchmark".

TensorRT never runs in the browser: engines are device-specific, so the live lane stays ONNX Runtime Web. **TensorRT for
RTX** may be evaluated internally, but its licence (§2.13) forbids disclosing benchmark or performance data without
NVIDIA's written permission [30], so its numbers never appear in the tab. Regular TensorRT numbers of our own models
are publishable: the TensorRT licence has no benchmark clause [31], and the reviewed licence text is pinned by SHA-256
in the TensorRT probe ([Capabilities](../data-contract/capabilities.md)).

## Assumptions and limits

- One machine, one driver, one power limit: every number is a measurement of this configuration only.
- Parity on a golden set bounds the error on that set; it does not prove equivalence on every input. The corruption
  curves and task metrics are the second line of defence.
- The ORT TensorRT EP lane depends on TensorRT 10.14 libraries that are not yet in the `pipeline/` lock; until they
  are, the bench covers PyTorch, ORT CPU, ORT CUDA and native TensorRT 11.3.

## In PitStudio

- **Stages:** `s60_export` (`pipeline/`), `s62_accel` and `s64_bench` (`pipeline/accel/`), which extend the frozen
  stage list after `s60_export` ([Pipeline stages](../pipelines/pipeline-stages.md)).
- **Artefacts:** ONNX files ≤ 25 MB for live models in `models/onnx/` or as release assets; engines git-ignored; the
  Acceleration table as web data.
- **Status:** not yet run. The TensorRT and ORT probes that smoke-test this lane are written; their CPU-side checks
  pass (probe graph vs CPU reference, licence hash, CUDA 13 runtime resolution), and their GPU runs wait for the end of
  the machine's GPU hold. Once the stages exist:

```bash run deferred=P6
uv run --extra runner studio run studio/recipes/cases/<case>.yaml --stage s62_accel
uv run --extra runner studio run studio/recipes/cases/<case>.yaml --stage s64_bench
```

## References

1. NVIDIA TensorRT issue #4813, wrong FP32 results for D-FINE-S (with later comments). https://github.com/NVIDIA/TensorRT/issues/4813
2. PyTorch 2.14, *torch.onnx export* (dynamo default, `verify`, `custom_translation_table`). https://docs.pytorch.org/docs/2.14/onnx_export.html
3. PyTorch v2.14.1, `torch/onnx/_constants.py` (default opset 20, max 23). https://raw.githubusercontent.com/pytorch/pytorch/v2.14.1/torch/onnx/_constants.py
4. ONNX operator `GridSample` (versions 16, 20, 22). https://onnx.ai/onnx/operators/onnx__GridSample.html
5. ONNX Runtime v1.30.0, WebGPU execution provider kernel registry. https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/onnxruntime/core/providers/webgpu/webgpu_execution_provider.cc
6. NVIDIA Model Optimizer, Windows examples README (opset 19+ for FP8). https://raw.githubusercontent.com/NVIDIA/Model-Optimizer/main/examples/windows/README.md
7. ONNX operator `ScatterElements` (reduction add/mul since 16). https://onnx.ai/onnx/operators/onnx__ScatterElements.html
8. PyTorch issue #155997, rfft → DFT export bug. https://github.com/pytorch/pytorch/issues/155997
9. ONNX Runtime v1.30.0 CI variables (`cuda13_trt_version: '10.14.1.48'`). https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/tools/ci_build/github/azure-pipelines/templates/common-variables.yml
10. ONNX Runtime issue #32278, CPython 3.14 CUDA 13 wheels and TensorRT 11. https://github.com/microsoft/onnxruntime/issues/32278
11. NVIDIA, *TensorRT 11.0.0 release notes*. https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/release-notes-11/11.0.0.html
12. ONNX Runtime v1.30.0, `float16.py` converter. https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/onnxruntime/python/tools/transformers/float16.py
13. ONNX Runtime v1.30.0, quantization utilities (`QuantFormat.QDQ`, `QInt8`, `QFLOAT8E4M3FN`). https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/onnxruntime/python/tools/quantization/quant_utils.py
14. NVIDIA, *TensorRT explicit quantization*. https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/quantized-types-explicit-quantization.html
15. `nvidia-modelopt` 0.47.0 on PyPI (dependency pins). https://pypi.org/pypi/nvidia-modelopt/0.47.0/json
16. NVIDIA, *TensorRT 10.3.0 release notes* (FP8 convolution on Ada). https://docs.nvidia.com/deeplearning/tensorrt/10.x.x/getting-started/release-notes-10/10.3.0.html
17. NVIDIA, *TensorRT support matrix* (FP4 emulation footnote). https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/support-matrix.html
18. ONNX Runtime pull request #29779, TensorRT 11 build version check. https://github.com/microsoft/onnxruntime/pull/29779
19. ONNX Runtime v1.30.0, `onnxruntime/__init__.py` (`preload_dlls`). https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/onnxruntime/__init__.py
20. NVIDIA, *TensorRT engine compatibility*. https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/engine-compatibility.html
21. NVIDIA TensorRT issue #4838, FP16 grouped-convolution build failure. https://github.com/NVIDIA/TensorRT/issues/4838
22. NVIDIA TensorRT issue #3650, `ScatterElements` with reduction. https://github.com/NVIDIA/TensorRT/issues/3650
23. NVIDIA, *TensorRT 11.3.0 release notes*. https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/release-notes-11/11.3.0.html
24. RF-DETR benchmark methodology. https://rfdetr.roboflow.com/latest/learn/benchmarks/
25. NVIDIA, *TensorRT performance benchmarking* (clock locking with `nvidia-smi -lgc`). https://docs.nvidia.com/deeplearning/tensorrt/latest/performance/benchmarking.html
26. Karimov et al., *Quantization Robustness to Input Degradations for Object Detection*, arXiv 2508.19600. https://arxiv.org/abs/2508.19600
27. D-FINE model zoo (T4, FP16, TensorRT 10.4.0, batch 1). https://github.com/Peterande/D-FINE
28. RF-DETR benchmark table (T4, TensorRT FP16, batch 1). https://github.com/roboflow/rf-detr
29. Gomez Fernandez et al., *Benchmarking Edge Inference Strategies for Deep Learning Models in Industrial Machine
    Vision*, IEEE COINS 2026, arXiv 2607.11356. https://arxiv.org/abs/2607.11356
30. NVIDIA, *TensorRT for RTX Software License Agreement* (§2.13). https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/reference/sla.html
31. NVIDIA, *TensorRT Software License Agreement*. https://docs.nvidia.com/deeplearning/tensorrt/latest/reference/sla.html

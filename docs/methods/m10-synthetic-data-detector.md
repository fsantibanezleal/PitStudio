# M10 — Synthetic-data detector with a domain-randomisation ablation

> Detectors for haul trucks, shovels, light vehicles, people and oversize boulders are trained only on rendered,
> exactly labelled pit images, with a structured-vs-unstructured randomisation ablation and corruption-robustness
> curves; real-domain transfer is reported as "not measured" unless a small real probe is labelled. · Part of:
> [Methods](README.md) · Related: [Sim-to-real theory](../theory/sim-to-real.md) · [D-FINE card](../models/d-fine.md) ·
> [RF-DETR-Seg card](../models/rf-detr-seg.md) · [Case B2](../cases/b2-synthetic-perception.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| SOTA | **yes** | precompute → live (ORT-web) | [B2](../cases/b2-synthetic-perception.md) | Replicator + ovrtx renders → D-FINE-N/S and RF-DETR-Seg-N (Apache-2.0), PyTorch in `pipeline/`; ONNX opset 19 | not yet implemented |

NVIDIA, Isaac Sim, Replicator and Omniverse are named nominatively. PitStudio is not affiliated with or endorsed by
NVIDIA and never redistributes NVIDIA binaries, assets, engines or caches; performance data of Isaac Sim, Replicator
and ovrtx stay local-only ([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)).

## What and why

Mining perception has a data problem: licence-clean, labelled images of haul trucks, people next to trucks and
boulders on a grizzly are essentially unavailable, and no published mining study measures sim-to-real transfer for
such detectors [9]. The physical-AI answer is synthetic data: render the scene, get pixel-exact labels for free, and
train. Domain randomisation was the first demonstration that a detector trained only on simulated RGB transfers to the
real world [5]; deliberately unrealistic randomisation followed by real fine-tuning beat real-only training [6]; and
**structured** domain randomisation, which places objects by context-aware distributions, beat plain randomisation
and synthetic baselines on KITTI [7].

M10 builds the mining version and measures what can honestly be measured:

- detection quality on **held-out synthetic** data;
- whether **structured** randomisation (physically tied to the pit) beats an **unstructured** arm, under the
  [decision rule](README.md#how-methods-are-compared);
- **corruption robustness** for dust, night and rain;
- real-domain transfer **only if** an optional real probe is labelled — otherwise the site says "not measured".

## The algorithm

### Synthetic data

- **Scenes:** PitStudio's procedural pit (from the Bingham terrain) with procedurally modelled equipment, berms,
  light vehicles and people. People come from MakeHuman exports under its CC0 option (licence §C conditions verified
  before use; fallback: procedural mannequins). No NVIDIA asset appears in any scene.
- **Renderers:** Isaac Sim with Replicator (COCO boxes, instance masks, depth; stage `st55_sdg`) and the kit-less ovrtx
  sensor lane for the fixed crusher camera (RGB and semantic segmentation; stage `st53_sensors`, see
  [M23](m23-rtx-sensor-simulation.md)).
- **Volume:** about 10k images per family for two families, plus an unstructured-randomisation ablation arm of about
  10k images — about 30k images, budgeted at roughly 4–17 GPU-hours of rendering (estimate; measured rates stay
  local-only).
- **Structured randomisation (main arm):** sun from latitude and time of day, dust optical depth from the plume field
  of [M16](m16-dust-dispersion.md), wet-road state from the watering schedule, rock textures by lithology, equipment
  placed on roads and benches where it can physically be.
- **Unstructured arm:** uniform random textures, lights and poses, as in classical domain randomisation [5][6].

Licences: our renders of our scenes are CC-BY-4.0. Cosmos captions ([M22](m22-cosmos-vlm-tasks.md)) are **not** used to
filter training data by default; doing so would require the "Built on NVIDIA Cosmos" notice on the detector card [10].

### Models

| Model | Parameters | COCO AP (published) | Role | Licence |
|---|---|---|---|---|
| D-FINE-N | 4 M | 42.8 | live detector | Apache-2.0 [1] |
| D-FINE-S | 10 M | 48.5 | main detector (int8 live, fp32 precompute) | Apache-2.0 [1] |
| RF-DETR-Seg-N | ~30 M class (seg size UNVERIFIED) | — | instance segmentation | Apache-2.0 (segmentation sizes) [3] |

D-FINE is a real-time DETR-family detector that refines boxes as probability distributions (fine-grained distribution
refinement) with self-distillation [2]. Input: an RGB image resized to 640 × 640. Output: a fixed set of query
predictions, each a class distribution and a box; the post-processor is inside the exported graph, so no
non-maximum suppression is needed in the browser [4]. Training uses DETR-style set prediction: predictions are matched
one-to-one to ground-truth objects, then classification, L1 and generalised-IoU box losses plus D-FINE's
distribution-refinement losses are applied [2]. Models start from the authors' COCO-pretrained Apache-2.0 weights and
are fine-tuned on synthetic data only. Ultralytics YOLO is excluded: its AGPL terms reach trained weights.

### Metrics

- **mAP50:** average precision at an intersection-over-union threshold of 0.5, where
  $\text{IoU}(A, B) = \lvert A \cap B\rvert / \lvert A \cup B\rvert$ for predicted and true boxes (or masks).
- **Corruption robustness:** the held-out set is re-evaluated under common corruptions at five severities [8]; fog,
  brightness, rain/snow and contrast map onto dust, night and wet conditions. The relative drop at severity $s$ is
  $100 \times (\text{mAP50}_{\text{clean}} - \text{mAP50}_s)/\text{mAP50}_{\text{clean}}$.
- **Camera streams per GPU** (studio only): a 3840 × 2160 pit-camera frame tiled at 640² with about 10 % overlap needs
  about 28 tiles (estimate); slicing-aided inference raised small-object AP by 5.1–6.8 points without retraining in
  published work [11]. Throughput per precision comes from the acceleration stages
  ([export, parity and acceleration](../models/export-parity-acceleration.md)).

### Budget and export

- **Training:** D-FINE N and S together 12–25 GPU-hours at 8–11 GB; RF-DETR-Seg-N 8–16 GPU-hours at 10–13 GB
  (estimates; measured by the `studio bench` probe before any long run).
- **Export:** opset **17–19**, because `GridSample` in opset 20 has no WebGPU kernel in ONNX Runtime 1.30 and the
  deformable attention of these detectors samples through it [12]; the IR version is pinned. Sizes: D-FINE-N fp16
  8 MB, D-FINE-S int8 10 MB, D-FINE-S fp32 40 MB, RF-DETR-Seg-N fp16 61 MB.
- **TensorRT:** a known open issue reports silently wrong outputs for D-FINE-S engines (TensorRT 11.1, also reported on
  10.14/10.16 and on Ada GPUs) [13]. No TensorRT path is assumed safe: every engine passes the per-engine parity gate
  or is reported as rejected ([DEC-0010](../architecture/decisions/DEC-0010-tensorrt-per-engine-parity.md)).

## Baseline and comparison

- **Unstructured vs structured randomisation:** the two arms train the same model with the same budget; mAP50 on the
  same held-out synthetic images; "structured DR better" only by the
  [decision rule](README.md#how-methods-are-compared) (pairing unit — images or training seeds — fixed in the spec).
- **Precision variants:** fp32 vs fp16 vs int8 on the same held-out set, including the corruption curves, because
  static INT8 engines can lose accuracy under noise, blur and low contrast [14].
- **Sim-to-real:** measured only with the optional real probe — at most 200 ground-level images with a per-file
  CC0, CC-BY or public-domain licence, labelled by two people (inter-annotator agreement reported). Without it, the
  equipment and people gap is **"not measured"**, and the B2 card says so. The measured sim-to-real result of the
  project is on fragmentation ([M11](m11-fragmentation-segmentation.md)), where a real labelled set exists.
- **Image realism:** no classifier two-sample test is claimed for equipment images without a real reference; they are
  labelled "calibrated synthetic — not validated against real data".

## Acceptance criterion (pre-registered)

- **D-FINE: synthetic held-out mAP50 ≥ 0.80 (S) and ≥ 0.70 (N).**
- **Relative drop ≤ 10 pp at corruption severity ≤ 2.**
- **"Structured DR better" only by the decision rule.**
- **RF-DETR-Seg-N: synthetic held-out mask AP50 ≥ 0.70; fp16 Δ ≤ 1 pp.**
- Export parity: fp32 rtol 1e-3 / atol 1e-5; reduced precision Δ ≤ 1 pp; failing variants reported as rejected.

**Results: Not yet run** — produced in the data-and-models phase. Reported: mAP50 per class and model, the DR ablation
with its paired CI, corruption curves per precision, the acceleration table, and — only if the probe is labelled —
real-probe metrics in aggregate.

## Lane and web delivery

**Precompute → live (ORT-web).** D-FINE-N fp16 (8 MB) and D-FINE-S int8 (10 MB) run live in ONNX Runtime Web on
replayed pit frames and on user-dropped images; gate ≤ 25 MB per model and ≤ 300 ms per image on the WebGPU tier
(estimate). D-FINE-S fp32 (40 MB) and RF-DETR-Seg-N (61 MB fp16) exceed the 25 MB live cap and are **precompute only**:
their outputs are baked. See [compute lanes](../pipelines/compute-lanes.md).

## Assumptions and limits

- Synthetic-only training: performance on real pit cameras is unknown unless the probe is labelled. Mining sim-to-real
  evidence in the literature is thin [9], so no transfer claim is made by analogy.
- Corruptions are image-space approximations of dust, night and rain; the physically based dust model is
  [M23](m23-rtx-sensor-simulation.md).
- Detection only: no tracking, no distance estimation, no safety function. Not a proximity-detection system.

## In PitStudio

- **Cases:** [B2](../cases/b2-synthetic-perception.md) (synthetic perception and crusher oversize); detector baseline
  for the hazard questions of [M22](m22-cosmos-vlm-tasks.md).
- **Code (planned):** rendering in `studio/isaac/` (`st55_sdg`) and `studio/rtx/` (`st53_sensors`); training,
  evaluation and export in `pipeline/` (`s30_train`, `s50_evaluate`, `s60_export`); engines and bench in
  `pipeline/accel/` (`s62_accel`, `s64_bench`); live inference in a `web/` ORT-web worker. Cards:
  [D-FINE](../models/d-fine.md), [RF-DETR-Seg](../models/rf-detr-seg.md). Data card:
  [synthetic data](../data-contract/dataset-cards/synthetic-data.md),
  [people assets](../data-contract/dataset-cards/makehuman-people.md).
- **Status:** not yet implemented — built test-first in the build phase.

## References

1. D-FINE repository — Apache-2.0; N/S/M/L/X sizes and COCO AP; T4 TensorRT FP16 latencies.
   https://github.com/Peterande/D-FINE
2. D-FINE paper (ICLR 2025) — fine-grained distribution refinement, GO-LSD. https://arxiv.org/abs/2410.13842
3. RF-DETR repository — Apache-2.0 for Nano–Large detection and all segmentation sizes; XL/2XL detection under PML 1.0.
   https://github.com/roboflow/rf-detr
4. D-FINE ONNX exporter — opset 16, post-processor inside the graph.
   https://raw.githubusercontent.com/Peterande/D-FINE/master/tools/deployment/export_onnx.py
5. Tobin, J. et al. (2017). *Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real
   World*. IROS. https://arxiv.org/abs/1703.06907
6. Tremblay, J. et al. (2018). Training deep networks with synthetic data: bridging the reality gap by domain
   randomization. CVPR-W. https://arxiv.org/abs/1804.06516
7. Prakash, A. et al. (2019). *Structured Domain Randomization*. ICRA. https://arxiv.org/abs/1810.10093
8. Hendrycks, D. & Dietterich, T. (2019). Benchmarking neural network robustness to common corruptions. ICLR.
   https://arxiv.org/abs/1903.12261
9. Crossref query — no matching mining sim-to-real perception study.
   https://api.crossref.org/works?query=synthetic+images+mining+haul+truck+detection+domain+randomization+open+pit&rows=15
10. NVIDIA Open Model License (2025-10-24) — §3.2 "Built on NVIDIA Cosmos".
    https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
11. Akyon, F. C. et al. (2022). *Slicing Aided Hyper Inference and Fine-tuning for Small Object Detection*. ICIP.
    https://arxiv.org/abs/2202.06934
12. ONNX `GridSample` (versions 16, 20, 22) and the ORT 1.30 WebGPU registry (GridSample 16–19 only).
    https://onnx.ai/onnx/operators/onnx__GridSample.html ·
    https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/onnxruntime/core/providers/webgpu/webgpu_execution_provider.cc
13. TensorRT issue #4813 — strongly typed FP32 engine silently wrong for D-FINE-S (comments: Ada laptop GPU, TensorRT
    10.14/10.16). https://github.com/NVIDIA/TensorRT/issues/4813
14. Karimov et al. *Quantization Robustness to Input Degradations for Object Detection*.
    https://arxiv.org/abs/2508.19600

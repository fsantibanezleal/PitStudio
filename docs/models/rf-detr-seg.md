# RF-DETR-Seg-N — synthetic-data instance segmentation

> A detection transformer with a mask head, trained on the same synthetic renders as the detector to produce per-object
> outlines; too large for the live web lane, so its masks are precomputed. · Part of: [Models](README.md) · Related:
> [M10 Synthetic-data detector](../methods/m10-synthetic-data-detector.md) ·
> [Case B2](../cases/b2-synthetic-perception.md) · [D-FINE](d-fine.md) ·
> [Export, parity and acceleration](export-parity-acceleration.md)

## What and why

A bounding box says where an object is; an instance mask says which pixels belong to it. For a boulder on a crusher
grizzly or a truck seen at an angle, box size is a poor proxy for object size, so case B2 adds an instance-segmentation
model next to the [D-FINE](d-fine.md) detector. **RF-DETR-Seg-N** is chosen because its code and every segmentation
size are Apache-2.0, it is a current real-time DETR (ICLR 2026), and its exporter already produces ONNX with boxes,
labels and masks [1][2][3].

## Model card

### Intended use

- Instance masks of equipment, people and boulders on synthetic held-out images of the studio's procedural pit and
  crusher scenes.
- Precomputed mask overlays and per-instance areas for the B2 replays; per-engine TensorRT parity and latency for the
  acceleration tables.

### Out of scope

- Live in-browser inference (the model exceeds the 25 MB live cap at every precision; see below).
- Real-image claims: the same "not measured unless the optional real probe is labelled" rule as the detector applies.
- Fragment size distributions; that is the [U-Net](unet-fragmentation.md)'s job, measured against real labels.

### Architecture

RF-DETR builds on a pre-trained DINOv2 vision-transformer backbone and a DETR decoder with multi-scale deformable
attention, and uses weight-sharing neural architecture search to pick accuracy–latency trade-offs without retraining
each candidate [2][4]. Training uses the DETR set-prediction loss with Hungarian matching and a GIoU + L1 box term
([D-FINE card](d-fine.md) gives the equations) [5][6]. For masks, DETR-family heads predict one mask per matched query
and train it with a Dice term and a focal (binary cross-entropy) term [5]; the soft Dice loss for a predicted mask
$p\in[0,1]^{H\times W}$ and ground truth $g\in\{0,1\}^{H\times W}$ is [7]:

$$
\mathcal L_{\text{Dice}}=1-\frac{2\sum_{u}p_u\,g_u+\varepsilon}{\sum_u p_u+\sum_u g_u+\varepsilon}
$$

$u$ runs over pixels and $\varepsilon$ is a small smoothing constant (–). RF-DETR's exact mask-loss weights are taken
from the upstream code at specification (UNVERIFIED — pinned at specification).

**Metric.** Mask AP50 is COCO-style average precision where a prediction counts as correct when its mask IoU with a
same-class ground-truth mask is ≥ 0.5, averaged over classes.

### Training data

The same arms as the detector: ~10k synthetic images per scene family × 2 families plus a ~10k unstructured-DR arm,
rendered by Replicator and ovrtx from our own procedural scenes, with exact instance masks from the renderer's
instance-segmentation annotator written as COCO JSON [8]. All synthetic, CC-BY-4.0 (ours); people from MakeHuman CC0
exports; CC0 textures. Splits are grouped by scenario seed and layout. Data card:
[synthetic data](../data-contract/dataset-cards/synthetic-data.md).

### Budget (estimate)

**8–16 GPU-h, 10–13 GB VRAM.** Upstream documents no minimum VRAM [3]; the estimate assumes about 4–8 h per arm at
batch 4–8 with gradient accumulation on the 16 GB laptop GPU, bf16 autocast, no FP8 training. Measured by the runner
probe `studio bench` before any long run; the GPU probes are written but not yet run on the reference machine.

### Export and web lane

- **Opset 19**: the deformable sampling uses `GridSample`, whose opset-19 form is `GridSample-16` [9], and opset 19
  keeps an FP8 Q/DQ variant possible for this attention-heavy model in the TensorRT lane [10]. The upstream exporter
  defaults to opset 17 with dynamic batch [1]; its output is the parity reference.
- `torch.onnx.export(dynamo=True, verify=True)` (torch 2.14.1), onnxslim 0.1.97, **IR version pinned to 10**.
- Parity: ONNX Runtime CPU fp32 vs PyTorch fp32 on ≥ 200 golden images (rtol 1e-3 / atol 1e-5 / max abs 1e-4);
  reduced precision accepted only if mask AP50 moves ≤ 1 pp and masks keep IoU ≥ 0.99 against fp32.

| Precision | Size at 4/2/1 bytes per parameter (estimate) | Lane |
|---|---|---|
| fp32 | ≈ 122 MB (30.5 M detection-Nano parameters [2]) | PRECOMPUTE |
| fp16 | ≈ 61 MB (≈ 67 MB at the 33.6 M Seg-N count of the upstream benchmark table [11]) | PRECOMPUTE |
| int8 | ≈ 31–34 MB | PRECOMPUTE |

Every precision exceeds the **25 MB live cap**, so RF-DETR-Seg-N is **precompute only** and is not shipped in the web
build; the web shows its baked masks.

**TensorRT relevance.** Upstream publishes **T4** latencies (TensorRT, FP16, batch 1): Seg-N 3.4 ms, Seg-S 4.4 ms [11],
measured with a 200 ms gap between passes to limit throttling variance [12] — a T4, not our machine. An independent
study found TensorRT fastest on GPUs overall but **not faster than plain PyTorch for a transformer model** [13], so no
speed-up is assumed. Every engine passes the per-engine parity gate on every TensorRT version and execution provider;
the D-FINE wrong-output issue #4813 shows DETR-style graphs can fail silently [14]
([DEC-0010](../architecture/decisions/DEC-0010-tensorrt-per-engine-parity.md)). Whether ONNX Runtime–produced FP8
Q/DQ graphs fuse into FP8 GEMMs on TensorRT 11.3 is UNVERIFIED and is tested in `s62_accel`.

### Pre-registered acceptance criteria

- Synthetic held-out **mask AP50 ≥ 0.70**.
- **fp16 Δ ≤ 1 pp** (mask AP50, fp16 vs fp32).
- Any comparison between arms or with another model is called "better" only by the decision rule (paired 95 % CI of the
  difference excludes 0) ([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).

### Evaluation protocol

- The detector's held-out synthetic test set, so masks and boxes are scored on identical images.
- Mask AP50 per class and overall; mask AP50:95 reported alongside.
- Corruption curves (dust, night, rain) reported descriptively with the same protocol as the detector [15]; no
  threshold is pre-registered for this model.
- Precision ladder: fp32 → fp16 → int8 → fp8 (TensorRT only), each with Δ mask AP50 and mask IoU vs fp32.

### Licence of weights

RF-DETR code is Apache-2.0, and its weights are Apache-2.0 for the Nano–Large detection sizes and **all segmentation
sizes**; the XL and 2XL **detection** weights (the `rfdetr[plus]` extra) are under PML 1.0 and are **never used** [1].
The DINOv2 backbone code and weights are Apache-2.0 [16]. With our CC-BY-4.0 synthetic data, the fine-tuned weights are
**Apache-2.0 + attribution**. Cosmos outputs never curate this training set (display-only).

## Assumptions and limits

- The segmentation parameter count is not stated in the upstream docs read (detection Nano 30.5 M; the benchmark
  table lists Seg-N at 33.6 M); sizes are arithmetic estimates.
- Synthetic-only training and testing; real-image performance is not measured.
- Throughput and VRAM are estimates; the 85 W laptop GPU throttles, so measured numbers carry their power state.
- Simulation-grade twin, not a live digital twin.

## In PitStudio

- **Case:** [B2](../cases/b2-synthetic-perception.md) (mask overlays and per-instance areas in the studio replay,
  acceleration tables). **Method:** [M10](../methods/m10-synthetic-data-detector.md).
- **Env and stages:** `pipeline/` `s30_train` → `s40_infer` (masks precomputed for the replays) → `s50_evaluate` →
  `s60_export` → `pipeline/accel/` `s62_accel` → `s64_bench`. The `rfdetr` package (Apache-2.0) is added to
  `pipeline/` and locked in the build phase.
- **Artefacts:** baked masks and metrics; `models/cards/` card; no ONNX in the web build. Recipes:
  [training recipes](training-recipes.md); framework pages [PyTorch](../frameworks/pytorch.md) and
  [TensorRT](../frameworks/tensorrt.md).

## Results

**Not yet trained** — produced in the data-and-models phase. Will be reported: mask AP50 and AP50:95 per class on the
synthetic held-out set (acceptance: mask AP50 ≥ 0.70); fp16, int8 and fp8 deltas (acceptance: fp16 Δ ≤ 1 pp); mask IoU
vs fp32; descriptive corruption curves; ONNX parity; TensorRT per-engine parity with rejected engines listed, latency,
throughput and J/inference.

## References

1. Roboflow. *RF-DETR* repository (Apache-2.0 / PML 1.0 split; sizes; exports). https://github.com/roboflow/rf-detr
   and export docs https://rfdetr.roboflow.com/latest/exports/
2. RF-DETR on PyPI (1.11.1; DINOv2 backbone). https://pypi.org/pypi/rfdetr/json
3. RF-DETR repository metadata (Apache-2.0). https://api.github.com/repos/roboflow/rf-detr
4. Robinson, I., Robicheaux, P., Popov, M., Ramanan, D., Peri, N. (2025). *RF-DETR: Neural Architecture Search for
   Real-Time Detection Transformers*. ICLR 2026. https://arxiv.org/abs/2511.09554
5. Carion, N. et al. (2020). *End-to-End Object Detection with Transformers*. https://arxiv.org/abs/2005.12872
6. Rezatofighi, H. et al. (2019). *Generalized Intersection over Union*. CVPR 2019. https://arxiv.org/abs/1902.09630
7. Milletari, F., Navab, N., Ahmadi, S.-A. (2016). *V-Net* (Dice-based objective). https://arxiv.org/abs/1606.04797
8. Isaac Sim data-collection guide (writers incl. `CocoWriter`, instance-segmentation annotator).
   https://github.com/isaac-sim/IsaacSim/blob/main/skills/data-collection-sim/SKILL.md
9. ONNX operator `GridSample` (versions 16, 20, 22). https://onnx.ai/onnx/operators/onnx__GridSample.html
10. NVIDIA Model Optimizer, Windows examples (FP8 needs opset ≥ 19).
    https://raw.githubusercontent.com/NVIDIA/Model-Optimizer/main/examples/windows/README.md
11. RF-DETR benchmark table (T4, TensorRT FP16, batch 1). https://github.com/roboflow/rf-detr
12. RF-DETR benchmark methodology (200 ms buffer). https://rfdetr.roboflow.com/latest/learn/benchmarks/
13. Gomez Fernandez et al. (2026). *Benchmarking Edge Inference Strategies for Deep Learning Models in Industrial
    Machine Vision*. IEEE COINS 2026. https://doi.org/10.48550/arXiv.2607.11356
14. NVIDIA TensorRT issue #4813. https://github.com/NVIDIA/TensorRT/issues/4813
15. Hendrycks, D., Dietterich, T. (2019). Common corruptions benchmark. ICLR 2019. https://arxiv.org/abs/1903.12261
16. Meta AI. *DINOv2* repository (Apache-2.0 code and weights). https://github.com/facebookresearch/dinov2

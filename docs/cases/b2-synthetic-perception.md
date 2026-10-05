# B2 — Synthetic-data perception and crusher oversize

> How far does a detector trained only on synthetic renders of a pit go — for haul trucks, light vehicles, people and
> crusher-jamming boulders — and how robust is it to dust, night and rain? · Part of: [Cases](README.md) ·
> Related: [M10 Synthetic-data detector](../methods/m10-synthetic-data-detector.md) ·
> [Sim-to-real](../theory/sim-to-real.md) · [D-FINE](../models/d-fine.md) ·
> [Synthetic data generation](../guides/synthetic-data-generation.md)

## What and why

**The question.** A perception engineer building collision avoidance, or a plant engineer who wants boulders caught
before they jam the primary crusher, has no licence-clean real training images. They ask: if we render the pit
ourselves, with exact labels and controlled randomisation, how well does a detector trained only on those renders do
on held-out renders; does structured (physically motivated) randomisation beat unstructured randomisation; how much
accuracy is lost under dust, night and rain; and how fast does it run per GPU?

**Why it matters.**

- Mobile equipment is the most common cause of fatalities among ICMM members (26 % in 2021–2024) [1]; perception is
  the input of every proximity system ([B1](b1-traffic-proximity.md)).
- Boulders that jam crushers caused seven-minute delays costing up to USD 650,000 per year at one operation, which
  used synthetic images to train a detector for them [2].
- Synthetic data is the only route here: no real, ground-level haul-truck or excavator image set with a traceable,
  redistributable licence could be verified, and the best-known open-pit perception set was unreachable with an
  unverified licence [3]. Domain randomisation has transferred to the real world in robotics [4], and structured
  randomisation outperformed plain randomisation on a driving benchmark [5]; in construction, adding synthetic images
  improved a worker detector by about 7.5 pp mAP [6]. None of this is mining evidence, so B2 claims only what it
  measures.

## Site and data

| Input | Kind | Source and licence | Card |
|---|---|---|---|
| ~10k images per family × 2 families (pit views; crusher pocket) + one ~10k unstructured-DR ablation arm | **synthetic** | Replicator + ovrtx renders of our procedural pit; COCO, masks, depth; CC-BY-4.0 | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |
| People | **synthetic** | MakeHuman exports under its CC0 option (fallback: procedural mannequins) | [makehuman-people](../data-contract/dataset-cards/makehuman-people.md) |
| Materials, HDRIs | real scans, CC0 | Poly Haven / ambientCG | [textures-cc0](../data-contract/dataset-cards/textures-cc0.md) |
| Optional real probe: ≤ 200 ground-level images, per-file CC0 / CC-BY / public domain | real | needs 6–10 maintainer labelling hours and a second labeller; **default: not done** | — |

**Structured randomisation** samples from physically motivated ranges: sun position from site latitude and time of
day, dust optical depth from the C3 dust field, wet-road state from the watering schedule, mud by road state, rock
textures from CC0 scans, bench geometry from the pit design. The ablation arm uses unstructured randomisation.

## Methods and baseline

| Rung | Method | Role in B2 |
|---|---|---|
| SOTA (learned) | [M10 Synthetic-data detector + DR ablation](../methods/m10-synthetic-data-detector.md) | D-FINE-N (live) and D-FINE-S detectors [7]; RF-DETR-Seg-N instance segmentation [8]; opset 19 |
| SOTA | [M23 RTX sensor simulation](../methods/m23-rtx-sensor-simulation.md), S3 crusher camera | Fixed crusher-pocket views with randomised rock sizes, lighting and dust |
| Frontier (learned, zero-shot) | [M22 Cosmos Reason 2, task C](../methods/m22-cosmos-vlm-tasks.md) | Captions of synthetic images scored for hallucination against scene truth |

**Baselines.** Structured DR vs the unstructured-DR arm ("structured DR better" only by the decision rule,
[DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)); D-FINE-N vs D-FINE-S; reduced
precision (fp16, int8) vs fp32; clean vs corrupted inputs (common-corruption protocol [9], mapped to dust, low sun and
rain).

## KPIs

| KPI | Unit | How it is computed |
|---|---|---|
| Synthetic held-out mAP50 | – | COCO-style mAP at IoU 0.5 on a held-out synthetic split, grouped by scene seed |
| Mask AP50 (RF-DETR-Seg-N) | – | Same, on instance masks |
| DR ablation gap | pp | mAP50(structured) − mAP50(unstructured) with paired CI over test images |
| Corruption drop | pp | mAP50(clean) − mAP50(corrupted) per corruption and severity |
| Quantisation delta | pp | Task metric at fp16/int8 minus fp32 |
| Camera streams per GPU | streams | Concurrent streams at a fixed frame rate with TensorRT engines of our models |
| Caption hallucination rate | % | Captioned objects or attributes absent from the scene truth ÷ all claims |

**Sim-to-real for equipment and people: "not measured".** It becomes measured only if the optional real probe is
labelled; then it is reported as aggregate metrics, with each image's licence recorded and no image published.

## Studio tools and artefacts

| Tool | Artefacts it produces for B2 |
|---|---|
| [Isaac Sim + Replicator](../frameworks/isaac-sim-replicator.md) (`st55_sdg`) | COCO boxes, instance and semantic masks, depth; structured and unstructured arms |
| [ovrtx](../frameworks/ovrtx.md) (`st53_sensors`, S3) | Crusher-camera RGB + semantic frames (boxes from connected components) |
| [Cosmos Reason 2](../frameworks/cosmos-reason-2.md) (`st59c_captions`) | ~2k captions with hallucination scores (text only) |
| [TensorRT](../frameworks/tensorrt.md) (`s62_accel`, `s64_bench`) | Local engines; published streams-per-GPU, latency and parity tables |
| [PyTorch](../frameworks/pytorch.md) / [ONNX Runtime](../frameworks/onnx-runtime.md) | Trained detectors; D-FINE-N fp16 (8 MB) and D-FINE-S int8 (10 MB) for the web |

## Web delivery

| Sub-tab | Element | Lane | Engine / asset |
|---|---|---|---|
| Scene | Pit and crusher-pocket views with label overlays | LIVE | three.js / R3F |
| Simulate | D-FINE-N / D-FINE-S int8 on sample synthetic frames, with a corruption slider | LIVE | ORT-web WebGPU → WASM; ≤ 300 ms/image target on T1 |
| Studio replay | SDG gallery (≤ 300 thumbnails); RF-DETR-Seg-N and D-FINE-S fp32 outputs | REPLAY (precompute) | 61 MB / 40 MB models exceed the 25 MB live cap, so only outputs ship |
| Studio replay | Cosmos captions | REPLAY (display-only) | "Built on NVIDIA Cosmos" |
| Charts | mAP per class; DR ablation; corruption curves; TensorRT acceleration table | REPLAY | baked tables |
| Context | Question, impact, honesty notes | STATIC | — |

## Assumptions and limits

- **Synthetic held-out is not real-world accuracy.** All B2 accuracy numbers are on synthetic test data unless the
  real probe is labelled. The page states this next to every metric.
- **Crusher-camera boxes** from connected components are exact for separated boulders and approximate when they
  touch; Replicator masks are used where exact instances matter.
- **People assets.** MakeHuman CC0 conditions are checked; if they do not fit, procedural mannequins replace them and
  the card says so.
- Performance data of Isaac Sim, Replicator and ovrtx stay local-only; regular TensorRT numbers of our models are
  published. PitStudio is not affiliated with or endorsed by NVIDIA.

## Reproduce this

```bash run deferred=P6
uv run studio plan studio/recipes/cases/b2.yaml --profile laptop-rtx5000ada
uv run studio run studio/recipes/cases/b2.yaml --profile laptop-rtx5000ada
uv run studio publish <run-id>
```

SDG is the heaviest GPU job in the suite (about 4–17 GPU-h for ~30k images, rate measured at the first run); see
[Synthetic data generation](../guides/synthetic-data-generation.md) and [TensorRT bench](../guides/tensorrt-bench.md).

## Results

**Not yet run** — produced in the data-and-models phase. What will be reported, with acceptance criteria:

- D-FINE synthetic held-out mAP50 **≥ 0.80 (S), ≥ 0.70 (N)**.
- Corruption robustness: relative drop **≤ 10 pp at severity ≤ 2**.
- RF-DETR-Seg-N synthetic held-out mask AP50 **≥ 0.70**; fp16 Δ **≤ 1 pp**.
- "Structured DR better" only by the decision rule.
- TensorRT per-engine parity (fp32 rtol 1e-3 / atol 1e-5; reduced precision Δ ≤ 1 pp); failing variants rejected.
- Cosmos caption hallucination rates (display-only, never a headline KPI).
- Sim-to-real for equipment and people: **"not measured"** unless the real probe is labelled.

## In PitStudio

- Recipe `studio/recipes/cases/b2.yaml`; route `/cases/B2`; model cards [D-FINE](../models/d-fine.md),
  [RF-DETR-Seg](../models/rf-detr-seg.md).
- Decisions: [DEC-0015](../architecture/decisions/DEC-0015-people-assets-makehuman.md),
  [DEC-0010](../architecture/decisions/DEC-0010-tensorrt-per-engine-parity.md).

## References

1. ICMM (2025). *2020–2024 Safety Performance: Insights*.
   https://www.icmm.com/en-gb/research/health-safety/2025/insights-2020-2024-safety-data
2. NVIDIA (2025-10-29). *Scaling Physical AI with Synthetic Data* (blog). https://blogs.nvidia.com/blog/scaling-physical-ai-omniverse/
3. Li et al. (2022). *AutoMine: An Unmanned Mine Dataset*. CVPR (page unreachable; licence UNVERIFIED — source
   unreachable). https://openaccess.thecvf.com/content/CVPR2022/html/Li_AutoMine_An_Unmanned_Mine_Dataset_CVPR_2022_paper.html
4. Tobin et al. (2017). *Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World*.
   IROS. https://arxiv.org/abs/1703.06907
5. Prakash et al. (2019). *Structured Domain Randomization*. ICRA. https://arxiv.org/abs/1810.10093
6. Neuhausen, Herbers, König (2020). Synthetic data for construction-worker detection. Appl. Sci. 10(14):4948. DOI
   10.3390/app10144948
7. Peterande. *D-FINE* (Apache-2.0). https://github.com/Peterande/D-FINE
8. Roboflow. *RF-DETR* (Apache-2.0 for Nano–Large detection and all segmentation sizes). https://github.com/roboflow/rf-detr
9. Hendrycks, Dietterich (2019). *Benchmarking Neural Network Robustness to Common Corruptions and Perturbations*.
   ICLR. https://arxiv.org/abs/1903.12261

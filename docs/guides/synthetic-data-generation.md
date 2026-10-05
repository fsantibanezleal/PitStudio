# Synthetic data generation

> Generate labelled synthetic images of open-pit equipment, people, boulders and muck piles with Isaac Sim + Replicator
> on PitStudio's own scenes, with structured and unstructured domain randomisation, seeded and sharded by the runner.
> · Part of: [Guides](README.md) · Related: [Isaac Sim + Replicator](../frameworks/isaac-sim-replicator.md) ·
> [M10 synthetic-data detector](../methods/m10-synthetic-data-detector.md) ·
> [synthetic-data card](../data-contract/dataset-cards/synthetic-data.md) · [sim-to-real](../theory/sim-to-real.md)

## What and why

**Goal:** produce the synthetic training sets for case B2 (equipment / people / boulder detection and crusher
oversize) and case D1 (fragmentation of muck piles with an exactly known size distribution). Licence-clean real images
of haul trucks and people in open pits are scarce, so PitStudio renders its own: every label is exact because it comes
from the scene, not from an annotator. The price is a domain gap, which is measured where real labelled data exist
(fragmentation) and stated as **"not measured"** where it does not (equipment and people, unless the optional real probe
is labelled).

**Status:** the SDG stage `st55_sdg` and its recipes are written in the build phase; nothing has been rendered. Results
sections elsewhere read "**Not yet run** — produced in the data-and-models phase".

## Prerequisites

- [Set up the studio](set-up-the-studio.md): `studio/isaac/` synced (Isaac Sim 6.1.0.0 with Replicator, Python 3.12
  uv-managed), NVIDIA terms and the Isaac Sim EULA accepted by the maintainer, Windows long paths enabled, the Isaac Sim
  Compatibility Checker passed on this driver.
- The open studio stages that build the scene: `st10_terrain` (USGS 3DEP Bingham Canyon terrain) → `st20_pit_design` →
  `st30_assets` → `st40_compose` → `st45_validate` ([studio stages](../pipelines/studio-stages.md)).
- People assets: MakeHuman 1.3.0 exports under its CC0 option, bundled system assets only
  ([MakeHuman people card](../data-contract/dataset-cards/makehuman-people.md)); textures from Poly Haven and ambientCG,
  both CC0 [1][2].
- Disk: tens of GB per image family in `PITSTUDIO_STORE`; the runner's disk guard refuses to start without room.

## What gets generated

| Set | Content | Labels | Size (design) |
|---|---|---|---|
| Structured DR, two image families | haul trucks, shovels, light vehicles, people and boulders on PitStudio's pit benches and roads; time of day, dust, rain and camera height drawn from mining-plausible ranges | COCO boxes, instance masks, depth | ~10k images per family |
| Unstructured-DR ablation arm | the same objects with random textures, lights and distractors (no scene structure) | same | ~10k images |
| Crusher camera (S3; rendered by ovrtx in `st53_sensors`, not Replicator) | oversize rocks at the crusher | boxes, masks | part of B2 |
| Muck piles (D1) | piles generated from a Swebrec size distribution with known parameters | instance masks + the exact size distribution | sized in the D1 spec |

**Structured versus unstructured randomisation.** Domain randomisation varies textures, lights and poses so widely that
the real world looks like one more variation [3]; structured domain randomisation samples them from the scene's own
context (objects on roads, cameras at plausible heights) and outperformed plain DR on a driving benchmark [4]. PitStudio
trains on both and calls one "better" only by the pre-registered decision rule
([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).

## Steps

1. **Build and validate the scene** on the open lane (bitwise-deterministic: the stage is built twice and the hashes
   must match).

   ```bash run deferred=P6
   uv run --extra runner studio run recipes/b2-perception.yaml --stage st45_validate
   ```

2. **Plan the SDG stage** to see the shard count, disk estimate and VRAM estimate against the 16 GB card.

   ```bash run deferred=P6
   uv run --extra runner studio plan recipes/b2-perception.yaml
   ```

3. **Run SDG.** The stage runs in `studio/isaac/` under `gpu0.compute`, sharded (each shard a cache entry, so an
   interrupted run resumes at the next shard), with Replicator's global seed set from the recipe seed
   (`rep.set_global_seed`) for reproducibility [5].

   ```bash run deferred=P6
   uv run --extra runner studio run recipes/b2-perception.yaml --stage st55_sdg
   uv run --extra runner studio run recipes/d1-muck-pile.yaml --stage st55_sdg
   ```

4. **Check the data before training.** `s50_evaluate` runs the data checks: duplicates, an injected-shift check, and for
   fragment images a C2ST with two classifier families plus a real-vs-real baseline on the real Mendeley set [6].

   ```bash run deferred=P6
   scripts/run_pipeline.sh --stage s50_evaluate
   ```

5. **Train and evaluate** the detectors (D-FINE-N/S, RF-DETR-Seg-N) and the U-Net — see
   [training recipes](../models/training-recipes.md).

## Expected output

- Per shard: images (PNG), COCO JSON, instance masks, depth, and a shard manifest with the seed and the scene hash.
- A run manifest naming `isaac-sim-replicator` as the producer, licence class reference-only for the tool and CC-BY-4.0
  for the generated data, and `performance: local-only` for any timing (Replicator throughput is covered by NVIDIA SLA
  §8.9 [7]; the images/s figure stays on the machine).
- On the web: an SDG gallery with ground-truth overlays on the Isaac Sim tool page, with REPLAY badges.

## How the results are judged (pre-registered)

| Claim | Criterion | Reported as |
|---|---|---|
| Detector on synthetic held-out data | mAP50 ≥ 0.80 (D-FINE-S), ≥ 0.70 (D-FINE-N); mask AP50 ≥ 0.70 (RF-DETR-Seg-N) | **Not yet run** |
| Corruption robustness (dust, night, rain; corruption benchmark protocol [8]) | relative drop ≤ 10 percentage points at severity ≤ 2 | **Not yet run** |
| Structured DR better than unstructured | only if the paired 95 % CI of the difference excludes 0 | **Not yet run** |
| Equipment / people sim-to-real | only with the optional real probe (≤ 200 licence-clean images, two labellers) | "not measured" unless labelled |
| Fragmentation sim-to-real (D1) | U-Net trained on synthetic vs on real, both tested on the real held-out originals (TSTR/TRTR [9]): TSTR ≥ 0.90 × TRTR on IoU, grouped k-fold | **Not yet run** |

The real fragmentation set has 960 labelled 512 × 512 images, which are 240 originals × 4 flips/rotations, and 231
source groups after conservatively merging 9 visually similar originals; splits are by source group and evaluation uses originals only
([Mendeley card](../data-contract/dataset-cards/mendeley-rock-fragments.md)).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Out of memory at 1080p with several cameras | 16 GB is Isaac Sim's floor | render ≤ 720p with 1–2 cameras per shard; the stage's declared OOM fallback halves the shard |
| First shard takes much longer than the rest | shader and extension caches warm up on first use | expected once; caches stay outside the repository and are never published |
| Identical images across shards | seeds not derived per shard | the runner derives `hash(master, stage, shard)`; do not hard-code seeds in the stage |
| Licence question about an asset | only CC0, CC-BY or own assets may appear in published renders | use the registry in `data/sources.yaml`; NVIDIA asset-library content is never published |

## Assumptions and limits

- Synthetic equipment and people data are **"calibrated synthetic — not validated against real data"** unless the real
  probe is labelled; no C2ST or TSTR claim is made for them.
- Renders show PitStudio's own scenes; no NVIDIA application UI and no NVIDIA sample assets appear in published images.
- Image counts and rates are design estimates (0.5–2 images/s in the GPU-time budget); the real rate is measured
  locally and not published.

## In PitStudio

- Cases [B2](../cases/b2-synthetic-perception.md) and [D1](../cases/d1-blast-muck-pile.md); methods
  [M10](../methods/m10-synthetic-data-detector.md), [M11](../methods/m11-fragmentation-segmentation.md),
  [M23](../methods/m23-rtx-sensor-simulation.md); spec `009-perception` and `012-fragmentation`.

## References

1. Poly Haven, "License" — CC0. https://polyhaven.com/license
2. ambientCG, "License" — CC0 1.0. https://docs.ambientcg.com/license/
3. Tobin, J. et al. (2017), "Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World", IROS. https://arxiv.org/abs/1703.06907
4. Prakash, A. et al. (2019), "Structured Domain Randomization", ICRA. https://arxiv.org/abs/1810.10093
5. NVIDIA, "Isaac Sim 6.0 Replicator snippets" — `rep.set_global_seed` for reproducibility. https://docs.isaacsim.omniverse.nvidia.com/6.0.0/replicator_tutorials/tutorial_replicator_isaac_snippets.html
6. Lopez-Paz, D. and Oquab, M. (2017), "Revisiting Classifier Two-Sample Tests", ICLR. https://arxiv.org/abs/1610.06545
7. NVIDIA, "NVIDIA Software License Agreement", §8.9. https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
8. Hendrycks, D. and Dietterich, T. (2019), "Benchmarking Neural Network Robustness to Common Corruptions and Perturbations", ICLR. https://arxiv.org/abs/1903.12261
9. Esteban, C., Hyland, S. L. and Rätsch, G. (2017), "Real-valued (Medical) Time Series Generation with Recurrent Conditional GANs" — TSTR/TRTS. https://arxiv.org/abs/1706.02633

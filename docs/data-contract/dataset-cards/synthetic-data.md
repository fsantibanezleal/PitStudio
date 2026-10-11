# Synthetic data

> Everything PitStudio generates itself — images, sensor returns, physics fields, event logs, size curves, creep
> series, deposits, rollouts and question sets — with how each set is validated against real data, or labelled
> honestly when no real reference exists. · Part of: [Dataset cards](README.md) · Related:
> [Sim-to-real](../../theory/sim-to-real.md) · [Synthetic data generation](../../guides/synthetic-data-generation.md) ·
> [Mendeley rock fragments](mendeley-rock-fragments.md) · [Quality and validation](../../architecture/quality-and-validation.md)

## What and why

Real public data cover terrain, slope deformation, one slope failure, fragment photographs and weather. They do not
cover the rest of an open pit: no licence-clean, real, ground-level image set of haul trucks or excavators could be
verified, and a search for public haul-cycle telemetry returned none [17]. PitStudio fills those gaps with synthetic
data from its own studio and pipeline.

Synthetic data is only useful if it is honest, so three rules apply: **exact labels by construction** (generators know
every fragment size, failure time and object position); **validation where real data of the same type exist**
(fragment images and terrain statistics; train-on-synthetic / test-on-real for fragmentation only); and the **honesty
rule** everywhere else (below). Isaac Sim, Replicator, ovrtx, Warp, Newton and Isaac Lab are named nominatively;
PitStudio is not affiliated with or endorsed by NVIDIA.

## Datasheet

### Composition

Every synthetic set is labelled synthetic, uses the same formats and loaders as real data, and carries a data card.

| Synthetic source | Content | Format | Generator (stage, environment) | Used by | Real reference of the same type |
|---|---|---|---|---|---|
| Replicator SDG | RGB with boxes, instance / semantic masks, depth; structured + unstructured domain randomisation | PNG + COCO JSON | Isaac Sim + Replicator, `st55_sdg` (`studio/isaac/`) | B2; M10; D-FINE, RF-DETR-Seg | none by default (optional real probe) |
| ovrtx sensors | RGB, depth, semantic; lidar point clouds with dust / rain; radar detections with Doppler | images + tables / fields | `st53_sensors` (`studio/rtx/`) | B1, B2, C3, E2; M23 | none |
| Warp / Newton runs | granular, shallow-water, dust-particle and vehicle runs | Zarr v3 fields, Parquet observables | `st50_physics` (`studio/`) | A3, C2, C3, D1; M7, M8, M9, M15 | physics benchmarks and literature targets (not a two-sample test) |
| DES cycles | haul-cycle event logs, queues, cycle times | Parquet | `minehaulsim` via `s05_synthesize` | A1, A2, B1, C3; M2, M4, M5 | none (no public haul telemetry) |
| Kuz-Ram PSDs | predicted fragment size distributions (Kuz-Ram / KCO, Swebrec) | Parquet | `minephys.blasting`, `s05_synthesize` | D1, D2; M12, M17 | none of the same type |
| Voight creep series | displacement series with a known failure time: regressive and progressive creep plus noise | Parquet | `minephys.geotech`, `s05_synthesize` | C1; M14 | de Wit (one event; descriptive only) |
| Plume fields | dust concentration fields | Zarr v3 | `minephys.environment` + Warp particles | C3; M16; FNO | none |
| `oreblocks` deposits | seeded block models with stamped exact optima | Parquet | `oreblocks`, `s05_synthesize` | E1; M18 | optional MineLib `marvin` (solver check) |
| Isaac Lab rollouts | policy trajectories and episode metrics | Parquet + replay traces | `st60_il_train`, `st61_il_mpm_eval` (`studio/isaaclab/`) | A2, A3; M21 | none (sim-to-sim gap reported) |
| Hazard-question sets | questions about rendered scenes, answers computed from USD prims | tables (format fixed at specification) | `st59a_vqa` | B1, B2; M22 | exact by construction |
| Plausibility pairs | simulation clip pairs, one controlled corruption per pair | video + label table | `st59b_plausibility` | M22 | exact by construction |
| Exact-PSD muck piles | rendered muck piles with every fragment's true size and mask | PNG + masks + Parquet PSD | Warp DEM (`st50_physics`) + Isaac Sim muck renders | D1; M11; U-Net | **Mendeley fragment images** |
| MakeHuman-based people | people placed in SDG and sensor scenes | part of the image sets above | [MakeHuman exports](makehuman-people.md) → `st30_assets` | B1, B2; M22 | none by default (optional real probe) |
| Procedural pit scenes | design surfaces (benches, ramps, pushbacks) and procedural equipment | USD → glTF / 3D Tiles | `st20_pit_design`, `st30_assets` | all 3D cases | real DEMs (terrain statistics) |

**Formats.** Tables and size curves are **Parquet**; run telemetry and event logs are JSON Lines
(`telemetry.jsonl`, `events.jsonl`). N-dimensional fields (heightfields,
concentration fields, particle states) are **Zarr v3**, a chunked format with partial reads [10]. Detection and
segmentation labels are **COCO JSON**, written by Replicator's COCO writer [12].

### Collection and provenance

- **Seeded and recorded.** Every set records its generator, version, git SHA, configuration hash and seeds, so a
  re-run reproduces it bit for bit where the generator is deterministic, and statistically otherwise.
- **Assets.** Only PitStudio's own procedural meshes, [CC0 materials](textures-cc0.md) and
  [MakeHuman CC0 exports](makehuman-people.md). **Never** Isaac Sim bundled assets: their licence forbids distributing
  any portion of them [11].
- **Priors with citations.** Fragmentation curves follow the Swebrec function and the prediction equations reviewed
  by Ouchterlony and Sanchidrián, with parameter priors from their tables [14][15]. Creep series follow Voight's
  material-failure law and the inverse-velocity guidelines [13][16]. Haul-cycle components follow fitted
  distributions from the literature [18]; their families and parameters are UNVERIFIED until transcribed with page
  numbers at specification.
- **Structured, not only random.** Classical domain randomisation (DR) varies rendering at random: Tobin et al.
  transferred a network trained only on simulated RGB images to real robotic control, with about 1.5 cm accuracy [1],
  and Tremblay et al. showed that deliberately unrealistic randomisation followed by real fine-tuning beat real-only
  training on KITTI cars [2]. **Structured DR** samples from context-aware distributions instead; Prakash et al.
  report it beating plain DR and other synthetic sets on KITTI [3]. PitStudio's structured design ties appearance to
  physics: sun position from site latitude and time of day, dust optical depth from the plume field, wet roads from
  the watering schedule, mud by road state, rock textures from CC0 scans, benches from the pit design. One
  **unstructured DR arm** is kept as an ablation, and "structured DR is better" is claimed only if the paired 95 %
  confidence interval of the difference excludes 0 ([DEC-0016](../../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).

### Licence and attribution

- **SPDX:** `CC-BY-4.0`. **Licence class:** `own`. **Redistribution:** yes.
- **Generated outputs.** No clause claiming rights over generated outputs was found in the simulator licences read
  [9][11]; the residual risk sits in the assets, which is why only own and CC0 assets are used.
- **Attribution text** on every published set or sample:
  "PitStudio synthetic data, set <id>, generator <name> <version>, git <sha>. Licensed under CC BY 4.0."
- **Not training data:** Cosmos Reason 2 answers and captions are `display-only` ("Built on NVIDIA Cosmos") and never
  enter a training set.

### Size, throughput and access

- **Images:** about 30,000 — two detector families × about 10,000 images plus a DR arm of about 10,000. At the
  planning rate of 0.5–2 images/s this is about 4–17 GPU-hours ($30{,}000 / 2 \approx 4.2$ h;
  $30{,}000 / 0.5 \approx 16.7$ h). The rate is an estimate replaced by the runner's measurement.
- **Disk:** about 2–5 MB per image with annotations (*estimate, to be measured*), so tens of gigabytes stay local.
- **Throughput figures stay local.** Measured Replicator and ovrtx throughput are performance data of NVIDIA software
  and are not published (NVIDIA SLA §8.9 [9];
  [DEC-0005](../../architecture/decisions/DEC-0005-performance-data-licence-rule.md)).
- **Physics runs:** about 1–2 scenarios per hour in `st50_physics` (estimate); DES, size curves, creep series and
  plumes run on CPU in seconds to minutes. Everything is generated into `PITSTUDIO_DATA` (default: a git-ignored
  folder); the web receives baked samples and shards of ≤ 10 MB each.
- **Fallback:** if an NVIDIA runtime fails on the reference machine, its sets end as "not run"; the open-lane
  generators (DES, Kuz-Ram, Voight, plumes, Warp / Newton) always run.

## Validation

![How each synthetic data type is validated or labelled](../../assets/diagrams/synthetic-data-validation.svg)

*Real references exist only for fragment images and terrain statistics; every other synthetic type carries the
honesty label instead of a validation claim.*

| Data type | Real reference | Test | Pre-registered criterion |
|---|---|---|---|
| Fragment images (exact-PSD muck piles) | Mendeley images, split by source group | classifier two-sample test on DINOv2 embeddings [4][6][7], two classifier families, real-vs-real baseline | AUC − real-vs-real AUC ≤ 0.10, bootstrap CI |
| Fragment images | Mendeley test folds | TSTR vs TRTR [5] — **only here** | TSTR ≥ 0.90 × TRTR (IoU) |
| Terrain statistics (procedural pit) | real DEMs (Bingham, Hambach) | classifier two-sample test, two families, real-vs-real baseline | AUC ≤ 0.60; 0.60–0.70 warn with attribution; > 0.70 fail |
| Slope series | de Wit, one event | **excluded** from the two-sample test and from TSTR | descriptive time-of-failure error only ([card](dewit-slope-failure.md)) |
| Physics runs | benchmarks (Beverloo, repose, column collapse, dam break, Stokes settling, mass conservation) | benchmark tests | per benchmark, on the physics pages |
| Every set | — | duplicate scans (exact hash, perceptual hash [19], embedding nearest neighbour [6]); train-vs-test AUC | no copies; train-vs-test AUC ≤ 0.60 |
| Every tested type | — | injected-shift check: a known shift must be detected | detection AUC ≥ 0.80 |

- **Why two classifier families and a real-vs-real baseline:** a two-sample test is a held-out classifier trying to
  tell synthetic from real [4]; one family can miss differences another finds, and the real-vs-real AUC shows how
  separable two real samples already are. **Why DINOv2 embeddings:** they are a better evaluation space for images
  than Inception features, and common metrics fail to detect memorisation [7] — hence the separate duplicate scans.
- **Detector robustness** (B2) is measured with a corruption suite in the style of Hendrycks and Dietterich [8]:
  relative drop ≤ 10 percentage points at severity ≤ 2.

**Honesty rule:** a data type with no real reference (equipment/people images without the optional real probe, dust
fields, haul telemetry) is labelled "calibrated synthetic — not validated against real data" and gets no C2ST/TSTR
claim.

**Not yet run** — produced in the data-and-models phase. Reported then: AUCs with bootstrap CIs, the TSTR / TRTR ratio
with fold spread, duplicate and injected-shift results, and the honesty label for every untested type.

**Optional real probe.** ≤ 200 ground-level images with a per-file CC0, CC BY or public-domain licence (for example
from Wikimedia Commons; the licence is recorded per file), labelled for equipment and people in 6–10 maintainer
labelling hours plus a second labeller. Only aggregate metrics are published; no probe image is committed. **Default:
not done**, so equipment and people sim-to-real is reported as **"not measured"**.

## Data card fields (every synthetic set)

| Field | Content |
|---|---|
| generator, version, git SHA | the code that made the set |
| config hash, seeds | exact reproduction inputs |
| priors with citations | every distribution or constant, with DOI or URL and page |
| assets with licences | every mesh, material, HDRI or character, with licence and SHA-256 |
| synthetic flag | `synthetic: true` on the set and every record |
| validation verdicts | test, AUC or ratio with CI, pass / warn / fail, or the honesty label |

## Assumptions and limits

- **Calibrated is not validated.** A generator tuned to literature values can still differ from a real pit in ways
  no test here can see.
- **DES cycle-time bias.** Simulated truck cycle times "tend to underestimate short hauls while overestimating long
  hauls" [20]; with no real telemetry to correct it, this known bias is stated wherever DES cycle times are shown.
- **One real image domain.** The fragment validation rests on one dataset of 240 effective tiles.
- **Planning numbers** (images per second, disk per image, scenarios per hour) are estimates until measured.

## In PitStudio

- **Source ids:** the studio synthetic sources in `data/sources.yaml` (SDG, sensors, physics, DES, PSDs, creep,
  plumes, deposits, rollouts, question sets), licence CC-BY-4.0.
- **Stages:** `s05_synthesize`, `st20_pit_design`, `st30_assets`, `st50_physics`, `st52_rtx_render`,
  `st53_sensors`, `st55_sdg`, `st60_il_train`, `st61_il_mpm_eval`, `st59a_vqa`, `st59b_plausibility`; validation in
  `s50_evaluate`; baking in `s60_export`.
- **Models:** [D-FINE](../../models/d-fine.md), [RF-DETR-Seg](../../models/rf-detr-seg.md),
  [U-Net](../../models/unet-fragmentation.md), [GNS](../../models/gns-granular.md), [FNO](../../models/fno-fields.md),
  [slope forecasters](../../models/slope-forecasters.md), [dispatch](../../models/dispatch-policies.md),
  [Isaac Lab policies](../../models/isaac-lab-policies.md).
- **Committed:** baked samples, shards (≤ 10 MB each) and validation metrics, with data cards. **Never committed:**
  full image sets, NVIDIA assets, caches or throughput numbers of NVIDIA software.
- **Status:** **Not yet run** — nothing has been generated or rendered. The CC0 textures it uses are **not yet
  downloaded by the pipeline** — fetched by `s00_download` in the data-and-models phase.

## References

1. Tobin, J. et al. "Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World",
   IROS 2017. https://arxiv.org/abs/1703.06907
2. Tremblay, J. et al. "Training Deep Networks with Synthetic Data: Bridging the Reality Gap by Domain
   Randomization", CVPR Workshops 2018. https://arxiv.org/abs/1804.06516
3. Prakash, A. et al. "Structured Domain Randomization: Bridging the Reality Gap by Context-Aware Synthetic Data",
   ICRA 2019. https://arxiv.org/abs/1810.10093
4. Lopez-Paz, D., Oquab, M. "Revisiting Classifier Two-Sample Tests", 2016. https://arxiv.org/abs/1610.06545
5. Esteban, C., Hyland, S. L., Rätsch, G. "Real-valued (Medical) Time Series Generation with Recurrent Conditional
   GANs" (defines TSTR), 2017. https://arxiv.org/abs/1706.02633
6. Oquab, M. et al. "DINOv2: Learning Robust Visual Features without Supervision", 2023. https://arxiv.org/abs/2304.07193
7. Stein, G. et al. "Exposing flaws of generative model evaluation metrics and their unfair treatment of diffusion
   models", NeurIPS 2023. https://arxiv.org/abs/2306.04675
8. Hendrycks, D., Dietterich, T. "Benchmarking Neural Network Robustness to Common Corruptions and Perturbations",
   ICLR 2019. https://arxiv.org/abs/1903.12261
9. NVIDIA. "NVIDIA Software License Agreement" (2026-05-07; §8.9 benchmarking disclosure), accessed 2026-10-02.
   https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
10. Zarr. "Zarr core specification v3", accessed 2026-10-02. https://zarr-specs.readthedocs.io/en/latest/v3/core/index.html
11. NVIDIA. "NVIDIA Isaac Sim Additional Software and Materials License", accessed 2026-10-02.
    https://docs.isaacsim.omniverse.nvidia.com/6.0.0/common/license-isaac-sim-additional.html
12. NVIDIA. Isaac Sim 6.0 "Scene-based SDG" tutorial (writers incl. the COCO writer), accessed 2026-10-02.
    https://docs.isaacsim.omniverse.nvidia.com/6.0.0/replicator_tutorials/tutorial_replicator_scene_based_sdg.html
13. Voight, B. "A method for prediction of volcanic eruptions", *Nature* 332:125–130, 1988. https://doi.org/10.1038/332125a0
14. Ouchterlony, F. The Swebrec function, *Mining Technology* 114(1):29–44, 2005. https://doi.org/10.1179/037178405X44539
15. Ouchterlony, F., Sanchidrián, J. A. Prediction-equation review, *J. Rock Mech. Geotech. Eng.* 11(5):1094–1109,
    2019. https://doi.org/10.1016/j.jrmge.2019.03.001
16. Carlà, T. et al. Inverse-velocity guidelines, *Landslides* 14(2):517–534, 2017. https://doi.org/10.1007/s10346-016-0731-5
17. Zenodo search for "haul truck" datasets (no public haul-cycle or telemetry dataset), accessed 2026-10-02.
    https://zenodo.org/api/records?q=%22haul%20truck%22&size=20&sort=mostviewed
18. Dindarloo, S. R., Osanloo, M., Frimpong, S. Cycle-component distributions for Monte Carlo truck–shovel
    simulation, *J. SAIMM* 115(3):209–219, 2015. https://doi.org/10.17159/2411-9717/2015/v115n3a6
19. ImageHash 4.3.2 (perceptual hashes), 2025. https://pypi.org/pypi/ImageHash/json
20. Chanda, E. K., Gardiner, S. Truck cycle-time prediction, simulation vs regression, *Eng. Constr. Archit. Manag.*
    17(5):446–460, 2010. https://doi.org/10.1108/09699981011074556

# Spec 009 — Perception: synthetic-data detectors with a domain-randomisation ablation
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent

Method M10 and case B2 ask how far detectors trained **only** on rendered, exactly labelled pit images go. This spec
fixes the synthetic data generation (SDG) for perception, the detectors (D-FINE-N live fp16, D-FINE-S int8 live and
fp32 precompute, RF-DETR-Seg-N precompute only), their training and evaluation on held-out synthetic data, the
structured-versus-unstructured domain-randomisation (DR) ablation, the corruption-robustness suite (dust, night, rain)
and the honesty rules for the missing real reference. It inherits the decision rule FR-000-05, the honesty rules
FR-000-07/08/09 and the thresholds of `specs/000-foundation/thresholds.yaml`.

Who benefits: perception and plant engineers (equipment, people and crusher-boulder detection without licence-clean real
images), data/AI practitioners (a measured DR ablation and corruption curves), and visitors of the B2 page (a live
detector in the browser).

Out of scope:
- generic ONNX export, parity layers 1, 2 and 4, TensorRT engines and the benchmark (spec 016);
- the in-browser worker, tiers and browser parity (spec 018);
- the ovrtx sensor lane itself (spec 013) — this spec consumes its crusher-camera frames as a file handoff;
- scene composition and asset conversion (spec 004);
- the runner, its locks and its fake GPU backend (spec 002);
- tracking, distance estimation or any safety function: this is not a proximity-detection system;
- any sim-to-real claim for equipment or people unless the optional real probe is labelled.

## 2. User stories

### US-009-1 (P1) Held-out synthetic accuracy with pre-registered acceptance
As a data/AI practitioner, I want D-FINE-N, D-FINE-S and RF-DETR-Seg-N scored on a held-out synthetic test set with
confidence intervals and pre-registered thresholds, so that I can judge what synthetic-only training achieves.
Independent test: run `s50_evaluate` on a fixture prediction set and check the report against hand-computed AP values.

### US-009-2 (P1) Structured versus unstructured randomisation
As a data/AI practitioner, I want the structured-DR arm compared with an unstructured-DR arm on identical test images,
with a paired confidence interval and the pre-registered decision rule, so that "structured DR is better" is claimed
only when the data support it. Independent test: feed two fixture prediction sets and check the interval and verdict.

### US-009-3 (P1) Robustness to dust, night and rain
As a perception engineer, I want the held-out set re-scored under a fixed corruption ladder for dust, night and rain at
five severities per precision, so that I can see how much accuracy is lost in bad conditions. Independent test: apply
the corruptions to constant images and compare with the closed-form values of §7 Table C.

### US-009-4 (P1) Honest sim-to-real statement
As a reviewer, I want every equipment and people result labelled "sim-to-real: not measured" unless the optional real
probe is labelled, so that nothing is presented as real-world accuracy. Independent test: build the B2 baked data
without a probe and assert the labels and the absence of any real-domain metric field.

### US-009-5 (P2) A live detector in the browser
As a visitor, I want D-FINE-N fp16 and D-FINE-S int8 to run live on sample synthetic frames, with the heavier variants
shown as precomputed outputs, so that I can try the detector without a GPU server. Independent test: check the web
build for the two live ONNX files, their sizes and their measured lanes.

### US-009-6 (P1) Reproducible, licence-clean synthetic data
As the maintainer, I want SDG driven by a schema-validated randomisation config, with seeded samplers, licence-checked
assets and an honest "not run" when Isaac Sim or ovrtx is unavailable, so that the data can be regenerated and
published safely. Independent test: run the samplers and the asset guard on CPU without Isaac Sim.

Story index (for traceability):

| Story | Title | Priority |
|---|---|---|
| US-009-1 | Held-out synthetic accuracy with pre-registered acceptance | P1 |
| US-009-2 | Structured versus unstructured randomisation | P1 |
| US-009-3 | Robustness to dust, night and rain | P1 |
| US-009-4 | Honest sim-to-real statement | P1 |
| US-009-5 | A live detector in the browser | P2 |
| US-009-6 | Reproducible, licence-clean synthetic data | P1 |

## 3. Functional requirements (EARS)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-009-01 | Ubiquitous | The perception dataset shall use exactly five classes with COCO category ids 1–5: `haul_truck`, `shovel`, `light_vehicle`, `person`, `boulder`, where `boulder` is a rock whose longest axis is ≥ the recipe's oversize limit `x_os` (default 1.0 m), decided from the scene's per-prim semantic tag and dimensions. | contract |
| FR-009-02 | Ubiquitous | The stage `st55_sdg` (pit family) shall write, for every image: an sRGB PNG at 1280 × 720 px, tight 2-D boxes and instance masks as COCO JSON, a semantic mask, a depth map (distance to the image plane, m, float32), the camera intrinsics (focal length in px, principal point), and a dataset-index record (DC-009-01) with family, arm, scenario seed, layout id and every sampled DR parameter value. | integration (gpu) + contract |
| FR-009-03 | Ubiquitous | The SDG recipe shall request, by default, three arms of 10,000 images each: structured pit family, structured crusher family (frames of the ovrtx S3 crusher camera, spec 013, handed off as files) and unstructured pit family; the unstructured arm shall reuse the scenario seeds and layouts of the structured pit family's training split. | contract |
| FR-009-04 | State | While sampling the structured arm, the DR sampler shall set the sun direction to the solar position (elevation, azimuth) at the site's WGS 84 centroid (terrain tile of spec 004) for a UTC instant drawn uniformly over one year, rejecting instants with a solar elevation < 5°; its solar-position routine shall reproduce the published SPA worked example (§7) within 0.01°, and the stage-frame direction vector shall match the analytical conversion within 1e-9 (float64). | unit |
| FR-009-05 | State | While sampling the structured arm, the DR sampler shall set the image's dust extinction coefficient σ (km⁻¹) to the value returned by `minephys.environment` for the plume concentration at the camera position of the scenario's dust field, and record σ in the dataset index. | unit |
| FR-009-06 | State | While sampling the structured arm, the DR sampler shall mark a road segment wet if and only if the time since its last watering pass in the scenario's watering schedule is ≤ the recipe's drying time (default 60 min, a design assumption), and record the flag per segment. | unit |
| FR-009-07 | State | While sampling the structured arm, the DR sampler shall place every vehicle and person so that its footprint centroid lies inside a road or bench polygon of the pit design and its base is within 0.05 m of the terrain height at that point, and shall draw rock textures only from the lithology's CC0 texture list. | property |
| FR-009-08 | State | While sampling the unstructured arm, the DR sampler shall draw textures uniformly from the whole texture pool, light intensity log-uniformly over [0.1, 10] × nominal, colour temperature uniformly over [2,000, 12,000] K, sun direction uniformly over the upper hemisphere, object positions uniformly over the visible ground region and 0–20 distractor primitives, independently of any physical field. | property |
| FR-009-09 | Unwanted | If the randomisation config (DC-009-03) has a non-finite number, a value outside its schema range, an unknown enum value, a negative or zero image count, an unknown texture id, or unknown keys, then the SDG stage shall reject it before any rendering with the JSON pointer of the first error and exit status ≠ 0. | unit (hostile) |
| FR-009-10 | Unwanted | If an asset referenced by an SDG scene has no licence record, or resolves to an `omniverse://` URL or to a path under a vendor asset root listed in the guard configuration, then `st55_sdg` shall abort before rendering with error code `asset-licence` and list every offending path. | unit (hostile) |
| FR-009-11 | Ubiquitous | The SDG scenes shall take every person instance either from a MakeHuman export record (DC-009-04: application 1.3.0, official zip SHA-256 equal to the pinned value, bundled system assets only, export settings, seed) or from the procedural mannequin generator, and the dataset card shall state which source was used and quote the people licence text. | contract |
| FR-009-12 | Unwanted | If a MakeHuman export record has a zip SHA-256 different from the pinned value, lists a community asset, or lacks export settings, then `st30_assets` handoff validation shall reject that character; and if no valid MakeHuman character remains, then SDG shall use procedural mannequins and set `people_source: mannequins` in the dataset card. | unit (hostile) |
| FR-009-13 | Ubiquitous | The dataset builder shall derive, for crusher-family frames (semantic masks without instance ids), one instance per 8-connected component of each class mask and its tight box `[x_min, y_min, x_max + 1, y_max + 1]` (px), and mark these labels `instance_source: connected-components`. | unit |
| FR-009-14 | Ubiquitous | The stage `s10_preprocess` shall validate every dataset-index record against DC-009-01 and every COCO file against DC-009-02, rejecting and never coercing invalid records. | contract |
| FR-009-15 | Unwanted | If a COCO file has a non-finite coordinate, a box with width or height ≤ 0, a box extending beyond its image by more than 0.5 px, an unknown category id, a duplicated annotation or image id, an annotation pointing to a missing image, or an image `file_name` that is absolute, contains `..` or a drive letter, then the loader shall reject the whole file with the record id and reason and load nothing from it. | unit (hostile) |
| FR-009-16 | Ubiquitous | The split builder shall assign scenario seeds, per family, to train / validation / test in the proportions 80 / 10 / 10 % (seeded, each count within ±1 seed of the target), with the unstructured arm in training only, and the test set shall hold ≥ 900 images per rendered family. | property |
| FR-009-17 | Unwanted | If a scenario seed or layout id occurs in two splits, or a 64-bit perceptual hash links a test image to a training or validation image at Hamming distance ≤ 4, then `s10_preprocess` shall stop with `split-leak` and list the pairs. | unit (hostile) |
| FR-009-18 | Ubiquitous | The stage `s30_train` shall fine-tune D-FINE-N and D-FINE-S from the upstream COCO-pretrained Apache-2.0 checkpoints and RF-DETR-Seg-N from the upstream Apache-2.0 segmentation-nano checkpoint (each pinned by SHA-256), on the synthetic training split only, with bf16 autocast and no FP8 training, using the upstream default loss coefficients (§7), and shall record checkpoint digests, seeds, epochs and the training-set digest in the manifest (DC-000-01). | integration (gpu) + contract |
| FR-009-19 | Unwanted | If the training-set manifest lists an input whose licence class is `display-only` or `reference-only`, or any real-probe image, then `s30_train` shall refuse to start with `training-input-licence` and name the inputs. | unit (hostile) |
| FR-009-20 | Event | When the runner reports a CUDA out-of-memory error for a perception training job, the stage shall restart from the last checkpoint with the recipe's declared `oom_fallback` (batch halved, gradient-accumulation steps doubled, effective batch unchanged), and when the batch would fall below 1 it shall stop with `oom-exhausted`. | unit (fake GPU) |
| FR-009-21 | Event | When `s30_train` restarts after an interruption, it shall resume from the last per-epoch checkpoint with the same epoch index, learning-rate schedule step and data order as an uninterrupted run. | unit (fake GPU) |
| FR-009-22 | Ubiquitous | The stage `s50_evaluate` shall compute box AP50 and AP50:95 per class and the overall mAP50 (unweighted mean over classes with ≥ 100 test instances) with the COCO protocol (101-point interpolated precision, `maxDets` 100, area "all") as implemented by `pycocotools`, and a 95 % cluster-bootstrap interval over test scenario seeds (B = 2,000, percentile, seeded). | unit + reference implementation |
| FR-009-23 | Ubiquitous | The stage `s50_evaluate` shall compute RF-DETR-Seg-N mask AP50 and AP50:95 with the same protocol using mask IoU, on pit-family test images only (exact Replicator instance masks), and shall report crusher-family mask metrics as descriptive and outside the acceptance. | unit + reference implementation |
| FR-009-24 | Unwanted | If a class present in a family has fewer than 100 test instances, then `s50_evaluate` shall set the acceptance verdict of every affected criterion to "not evaluable (insufficient support)" with the class and its count, instead of pass or fail. | unit (hostile) |
| FR-009-25 | Ubiquitous | The dust corruption at severity s shall map a linear-RGB pixel I with depth d (m) to t·I + (1 − t)·A, with t = exp(−σ_s·d), the airlight A = (0.58, 0.46, 0.31) linear RGB and σ_s from §7 Table C, operating in linear RGB (IEC 61966-2-1 transfer function) and re-encoding to 8-bit sRGB with round-half-to-even. | unit + metamorphic |
| FR-009-26 | Ubiquitous | The night corruption at severity s shall map a linear-RGB pixel I to clip(k_s·I + n, 0, 1), with the exposure factor k_s and the noise standard deviation σ_n,s from §7 Table C and n drawn independently per pixel and channel from N(0, σ_n,s²) with a counter-based seeded generator. | unit + metamorphic |
| FR-009-27 | Ubiquitous | The rain corruption at severity s shall map I to (1 − m)·[c_s·I + (1 − c_s)·Ī] + m·L_r, where Ī is the per-channel image mean, L_r = 0.85 (linear), and m is a binary streak mask of 1-px-wide straight streaks of length ℓ_s·W/1280 px at an image angle drawn from U(−15°, 15°) from the vertical (per-streak jitter U(−2°, 2°)), added until the covered fraction first reaches ρ_s, with c_s, ℓ_s and ρ_s from §7 Table C. | unit + property |
| FR-009-28 | Optional | Where an image has no depth map (real-probe images), the dust corruption shall use the constant reference depth d_ref = 100 m and set `depth_assumed: true` in its record. | unit |
| FR-009-29 | Unwanted | If a corruption receives a non-finite pixel or depth, an image that is not H × W × 3 (uint8, or float in [0, 1]), a depth map whose shape differs from the image, a negative depth, a severity outside {0, 1, 2, 3, 4, 5}, or an unknown corruption name, then it shall raise `ValueError` naming the argument and return no image; severity 0 shall return the input unchanged. | unit (hostile) |
| FR-009-30 | Ubiquitous | The stage `s50_evaluate` shall re-score the held-out test set for every model and precision variant (fp32, fp16, int8) under dust, night and rain at severities 1–5 and report the relative drop Δ_rel(c, s) = 100 × (m_clean − m_c,s) / m_clean in percent, with m = mAP50 (detectors) or mask AP50 (RF-DETR-Seg-N, descriptive). | unit |
| FR-009-31 | Ubiquitous | The DR ablation shall compare D-FINE-S trained on arm S (structured pit + structured crusher) with D-FINE-S trained on arm U (unstructured pit + the same structured crusher), with identical image count, epochs, schedule and seed, both scored on the same pit-family test images; the interval of d = mAP50(S) − mAP50(U) shall be the 95 % percentile interval of a paired cluster bootstrap over test scenario seeds (B = 10,000, seeded, identical resample indices for both arms), and the verdict shall follow FR-000-05 ("better" if the lower bound > 0, "worse" if the upper bound < 0, else "no significant difference"). | unit |
| FR-009-32 | State | While no labelled real probe exists, the evaluation report and every B2 baked data file shall carry `sim_to_real: "not measured"` and the label "calibrated synthetic — not validated against real data" for every class, and shall contain no real-domain metric field. | contract + unit |
| FR-009-33 | Optional | Where the optional real probe is labelled, `s50_evaluate` shall score D-FINE-N and D-FINE-S on it with labeller A as ground truth, report per-class AP50 with a 95 % image-bootstrap interval (B = 2,000), the mAP50 against labeller B as a sensitivity result, and inter-annotator agreement as the per-class box F1 at IoU ≥ 0.5 between the two labellers, and shall publish aggregate metrics only. | unit |
| FR-009-34 | Unwanted | If a probe image has no per-file licence record or a licence outside {CC0-1.0, CC-BY-2.0, CC-BY-2.5, CC-BY-3.0, CC-BY-4.0, public domain}, then the probe loader shall exclude it and list it; and if more than 200 images are supplied, or the second labeller's file is missing, then it shall refuse the probe with `probe-invalid`. | unit (hostile) |
| FR-009-35 | Ubiquitous | The D-FINE export shall produce graphs that declare default-domain opset 19, contain `GridSample` only at since-version 16, take `images` float32 [N, 3, 640, 640] with values in [0, 1] and `orig_target_sizes` int64 [N, 2], and output `labels` int64 [N, 300], `boxes` float32 [N, 300, 4] (xyxy, px) and `scores` float32 [N, 300], with the post-processor and top-300 selection inside the graph and no non-maximum suppression. | contract |
| FR-009-36 | Ubiquitous | The RF-DETR-Seg-N export shall produce graphs that declare default-domain opset 19, take a 312 × 312 input as configured upstream, and output boxes, labels and masks as the upstream exporter defines them; its lane shall be precompute at every precision. | contract |
| FR-009-37 | Ubiquitous | The web build shall contain exactly two perception ONNX files, D-FINE-N fp16 and D-FINE-S int8 (static QDQ); RF-DETR-Seg-N (every precision) and D-FINE-S fp32 shall ship only as baked outputs. | CI |
| FR-009-38 | Unwanted | If a live detector variant exceeds 25 × 10⁶ bytes, or its measured T1 median latency exceeds 300 ms per 640 × 640 image, or its T2 run time exceeds 1 s, then `s60_export` shall set its manifest lane to precompute and hand its precomputed outputs to the B2 page (FR-000-15). | contract |
| FR-009-39 | Unwanted | If a fp16 or int8 detector variant changes mAP50 by more than 1 percentage point against fp32 (spec 016, layer 2) or fails SC-009-03 on its own clean score, then `s60_export` shall report it as rejected with its numbers and reason and shall not ship it. | unit |
| FR-009-40 | Unwanted | If the capability report shows Isaac Sim / Replicator not passing, then `st55_sdg` and every perception stage downstream of it shall end "not run" with no substitute data and B2 shall show "not yet run" (FR-000-07); and if ovrtx is not passing, then the crusher family shall be "not run", the detectors shall be trained on the pit family only, and the model cards shall say "crusher family not run". | unit (fake GPU) |
| FR-009-41 | Ubiquitous | The SDG and sensor stages shall carry `performance: local-only`, and the perception dataset card and B2 baked data shall contain image counts, outputs and validation verdicts but no throughput, timing or telemetry figure of Isaac Sim, Replicator or ovrtx (FR-000-08). | contract |
| FR-009-42 | Unwanted | If a handed-off frame or dataset-index record has a file whose SHA-256 differs from the record, a path that is absolute or contains `..` or a drive letter, a semantic or instance mask whose size differs from its RGB image, or a class value outside {0, 1, 2, 3, 4, 5}, then the dataset builder shall reject that frame with the record id and reason and keep it out of every split. | unit (hostile) |
| FR-009-43 | Unwanted | If a prediction file given to `s50_evaluate` has a non-finite score or box, an image id absent from the test set, an unknown category id, or more than 300 detections for one image, or the two arms of the DR ablation do not cover the same test images, then `s50_evaluate` shall reject the input with the reason and report no metric from it. | unit (hostile) |
| FR-009-44 | Ubiquitous | The stage `st55_sdg` shall write, for every rendered frame, one frame-state file valid against `contracts/frame-state.schema.json` (DC-015-01, owned by spec 015-vlm; not redefined here) — world transforms in metres honouring the stage's `metersPerUnit` and `upAxis`, per-object prim id and class label, footprints, visible-pixel counts, depth and dust-field references and the sampled conditions — carrying the SHA-256 of its frame image, and shall list the frame-state path and SHA-256 in the frame's dataset-index record (DC-009-01). | contract + integration (gpu) |
| FR-009-45 | Unwanted | If a frame's stage lacks `metersPerUnit` or `upAxis`, a prim transform is non-finite, a labelled prim has a class label outside the frame-state schema's enumeration, or two objects share a prim id, then `st55_sdg` shall write no frame state for that frame, keep the frame out of the dataset index with the reason, and count it in the stage report. | unit (hostile) |

## 4. Correctness properties

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-009-01 | For any linear image I and depths d₁, d₂ ≥ 0 at severity σ, dust(dust(I, d₁), d₂) = dust(I, d₁ + d₂) (semigroup of the transmittance; metamorphic). | float64 images 1–64 px a side, values in [0, 1]; d in [0, 2,000] m; σ from Table C | atol 1e-12 |
| P-009-02 | For any image and depth, raising the dust severity never increases \|dust_s(I) − A\| at any pixel, and t ∈ (0, 1] (monotonicity; metamorphic). | as P-009-01, s₁ < s₂ in 1–5 | exact (float64 comparison) |
| P-009-03 | For any spatial permutation or dihedral transform π, dust(π I, π d) = π dust(I, d) and night₀(π I) = π night₀(I), where night₀ is the night corruption with σ_n set to 0 (equivariance; metamorphic). | float64 images, random permutations and the 8 dihedral maps | exact |
| P-009-04 | For σ_n = 0 and before clipping, applying exposure factors k₁ then k₂ equals applying k₁k₂, and the mean luminance of night_s(I) is non-increasing in s (composition and monotonicity; metamorphic). | float64 images in [0, 1], k in (0, 1] | rtol 1e-12 |
| P-009-05 | For any image of width W ≥ 640 and height H ≥ 360 and any seed, the realised rain streak coverage f satisfies ρ_s ≤ f < ρ_s + (ℓ_s·W/1280 + 1)/(W·H) (one streak adds at most its rasterised length plus one pixel), and f is non-decreasing in s for a fixed seed. | Hypothesis: W 640–1920, H 360–1080, seeds | exact |
| P-009-06 | For any x in [0, 1], the sRGB decode of the sRGB encode of x equals x, and the 8-bit encode of the 8-bit decode of every code 0–255 returns the same code. | float64 x; all 256 codes | atol 1e-12; exact for codes |
| P-009-07 | For any prediction set with distinct scores, AP50 does not depend on the order in which predictions are listed (permutation invariance; metamorphic). | Hypothesis: 1–20 images, 0–30 boxes per image, 5 classes | exact |
| P-009-08 | For any prediction set, scaling every image size and every box by k leaves AP50 and AP50:95 (area "all") unchanged (scale invariance of IoU; metamorphic). | k in [0.5, 4]; inputs with no IoU within 1e-6 of a threshold | atol 1e-12 |
| P-009-09 | Adding a prediction whose score is below every other score and which matches no ground truth never increases AP50; adding a perfect, highest-scoring prediction for an unmatched ground-truth box never decreases it (monotonicity; metamorphic). | as P-009-07 | exact |
| P-009-10 | For any m_clean > 0 and m_s, Δ_rel(k·m_clean, k·m_s) = Δ_rel(m_clean, m_s) for k > 0, and Δ_rel = 0 when m_s = m_clean (unit invariance). | float64 m in (0, 1] | rtol 1e-12 |
| P-009-11 | For any pair of per-image result sets, swapping arms S and U negates both interval bounds (same resample indices) and swaps "better" and "worse"; relisting the scenario seeds in any order leaves the interval unchanged; identical arms give the interval [0, 0] and "no significant difference" (antisymmetry, order invariance, identity; metamorphic). | Hypothesis: 10–200 seeds, 1–20 images per seed | atol 1e-12 |
| P-009-12 | For any sampled structured scenario, the solar elevation is ≥ 5° and every placed vehicle and person satisfies FR-009-07. | random pit-design fixtures, 1,000 draws per seed | exact |
| P-009-13 | For any seed assignment, the train / validation / test splits are disjoint, cover every seed, and the unstructured arm's seeds are a subset of the training seeds. | Hypothesis: 10–5,000 seeds | exact |
| P-009-14 | For any binary mask, the box of each 8-connected component encloses all its pixels and is minimal, and flipping the mask horizontally maps every box x-interval [a, b) to [W − b, W − a) (equivariance). | random masks up to 256 × 256 | exact |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-009-01 | Size of each live perception ONNX file (expected: D-FINE-N fp16 ≈ 8 MB, D-FINE-S int8 ≈ 10 MB) | ≤ 25 × 10⁶ bytes | CI budget check (spec 016) |
| NFR-009-02 | Live detector latency per 640 × 640 image | T1 median ≤ 300 ms over ≥ 50 images after 5 warm-up runs; T2 run ≤ 1 s | web timing record (spec 018) → manifest lane |
| NFR-009-03 | Long training jobs | every resume segment ≤ 8 h (one overnight slot); ≥ 1 checkpoint per epoch | run manifest |
| NFR-009-04 | Evaluation determinism | two `s50_evaluate` runs on the same predictions give byte-identical reports | pipeline test |
| NFR-009-05 | Volume per arm after validation | ≥ 9,500 valid images per requested 10,000 (otherwise the arm fails) | `s10_preprocess` report |
| NFR-009-06 | B2 SDG gallery | ≤ 300 thumbnails, counted in the replay budget class (spec 016) | budget report |
| SC-009-01 | D-FINE-S (fp32, arm S) on the pooled synthetic held-out test set | mAP50 ≥ 0.80 (point estimate; 95 % interval reported) | `s50_evaluate` report |
| SC-009-02 | D-FINE-N (fp32) on the pooled synthetic held-out test set | mAP50 ≥ 0.70 (point estimate; 95 % interval reported) | `s50_evaluate` report |
| SC-009-03 | Corruption robustness of D-FINE-S and D-FINE-N (fp32 and every live variant) | Δ_rel(c, s) ≤ 10 (percent of the clean score) for c ∈ {dust, night, rain}, s ∈ {1, 2} | `s50_evaluate` report |
| SC-009-04 | "Structured DR better" | stated only when the FR-009-31 interval excludes 0 in its favour; otherwise "no significant difference" (or "worse") | `s50_evaluate` report + B2 baked data |
| SC-009-05 | RF-DETR-Seg-N (fp32) on pit-family held-out images | mask AP50 ≥ 0.70 | `s50_evaluate` report |
| SC-009-06 | RF-DETR-Seg-N fp16 against fp32 | \|Δ mask AP50\| ≤ 1 percentage point | `s50_evaluate` / spec 016 layer 2 |
| SC-009-07 | Sim-to-real for equipment and people | "not measured" unless the probe is labelled; then aggregate metrics with inter-annotator agreement | B2 baked data |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-009-01 | Perception dataset index (one record per image: id, family, arm, split, scenario seed, layout id, relative paths, SHA-256, size, intrinsics, depth path, DR parameters, `synthetic: true`, licence) | `specs/009-perception/contracts/perception-dataset.schema.json` (draft; promoted to `contracts/perception-dataset.schema.json` by T-009-001) | `st55_sdg`, crusher handoff → `s10_preprocess`, `s30_train`, `s50_evaluate` |
| DC-009-02 | COCO instances subset (images, annotations with bbox / segmentation / area / iscrowd = 0, categories 1–5) | `specs/009-perception/contracts/coco-instances.schema.json` (draft; promoted to `contracts/coco-instances.schema.json` by T-009-002) | `st55_sdg`, dataset builder → loader |
| DC-009-03 | Randomisation config (arm, counts, structured parameter sources, unstructured ranges, texture pool, drying time, `x_os`) | `specs/009-perception/contracts/sdg-randomisation.schema.json` (draft; promoted to `contracts/sdg-randomisation.schema.json` by T-009-003) | recipe → DR sampler, `st55_sdg` |
| DC-009-04 | People asset record (source, application version, zip SHA-256, assets used, export settings, seed, export SHA-256) | `specs/009-perception/contracts/people-asset-record.schema.json` (draft; promoted to `contracts/people-asset-record.schema.json` by T-009-004) | maintainer export → `st30_assets` handoff, dataset card |
| DC-009-05 | Detection evaluation report (per model × precision × family × class: AP50, AP50:95, intervals, support; corruption curves; DR ablation; `sim_to_real`; honesty label; verdicts) | `specs/009-perception/contracts/detection-eval.schema.json` (draft; promoted to `contracts/detection-eval.schema.json` by T-009-005) | `s50_evaluate` → `s60_export`, B2 baked data, model cards |

Run and asset manifests (performance marker, lane, licence class) follow the foundation contract DC-000-01
(`contracts/manifest.schema.json`).
Per-frame scene states follow DC-015-01 (`contracts/frame-state.schema.json`, spec 015-vlm); this spec produces them
(FR-009-44) and defines no second contract for that artefact.

## 7. Edge cases and assumptions

**Table C — corruption ladder (pre-registered; severity 0 is the identity).** All operations are in linear RGB.

| Corruption | Parameter | s = 1 | s = 2 | s = 3 | s = 4 | s = 5 |
|---|---|---|---|---|---|---|
| dust | extinction σ_s (km⁻¹) | 0.75 | 1.5 | 3.0 | 6.0 | 12.0 |
| dust | equivalent meteorological optical range ln(20)/σ_s (km, informative) | 4.0 | 2.0 | 1.0 | 0.5 | 0.25 |
| night | exposure factor k_s | 2⁻¹ | 2⁻² | 2⁻³ | 2⁻⁴ | 2⁻⁵ |
| night | noise standard deviation σ_n,s (linear units) | 0.002 | 0.004 | 0.006 | 0.008 | 0.010 |
| rain | contrast factor c_s | 0.9 | 0.8 | 0.7 | 0.6 | 0.5 |
| rain | streak coverage ρ_s (fraction of pixels) | 0.005 | 0.01 | 0.02 | 0.03 | 0.05 |
| rain | streak length ℓ_s (px at 1,280 px width) | 8 | 12 | 16 | 20 | 24 |

The ladder follows the five-severity design of the common-corruptions benchmark (Hendrycks & Dietterich 2019,
https://arxiv.org/abs/1903.12261): dust plays the role of fog, night of brightness, rain of snow plus contrast. The
dust form is the Beer–Lambert / Koschmieder haze model with renderer depth, the physically based dust haze of the
sensor-physics page; the optical-range row uses the 5 % contrast threshold, ln(20) = 2.996. The values are design
choices fixed before any result, not sourced norms.

**Pinned upstream values (read on 2026-10-06 from the primary sources).**
- D-FINE ONNX exporter (`tools/deployment/export_onnx.py`): input names `images`, `orig_target_sizes`; output names
  `labels`, `boxes`, `scores`; post-processor inside the graph; upstream opset 16 (PitStudio re-exports at 19).
- D-FINE configuration (`configs/dfine/include/dfine_hgnetv2.yml`): `eval_spatial_size` [640, 640], `num_queries`
  300, `num_top_queries` 300; the N and S configs inherit them. The post-processor applies sigmoid scores and top-300
  over queries × classes and scales xyxy boxes by `orig_target_sizes` repeated as (s₀, s₁, s₀, s₁).
- RF-DETR 1.11.1 (`src/rfdetr/config.py`): `RFDETRSegNanoConfig` resolution 312, patch size 12, `num_queries` 100,
  `num_select` 100; `SegmentationTrainConfig` `mask_ce_loss_coef` 5.0, `mask_dice_loss_coef` 5.0, `cls_loss_coef`
  1.0. These are the default loss coefficients of FR-009-18.

**Edge cases and assumptions.**
- The input scale order of upstream D-FINE is ambiguous for non-square inputs (its ONNX inference script passes
  (height, width) while the post-processor multiplies x by the first value). PitStudio always letterboxes to 640 × 640
  and passes `orig_target_sizes` = [[640, 640]]; boxes are mapped back by the inverse letterbox outside the graph.
- The DR ablation pairs on test scenario seeds; with one training seed per arm (the plan's budget), the interval covers
  test-set sampling only, and the B2 card states "one training run per arm".
- "Structured DR better" is a statement about the synthetic test distribution, which arm S resembles; the card says so.
- Acceptance uses point estimates on the full held-out set, as in the plan; intervals are reported alongside.
- Crusher-family boxes from connected components are exact for separated boulders and merge touching ones; mask
  acceptance therefore uses the pit family only.
- 1 MB = 10⁶ bytes throughout.
- Images per second, disk per image and training GPU-hours are estimates, measured by the runner; SDG rates stay
  local-only.
- Solar-position oracle of FR-009-04: the worked example of the Solar Position Algorithm (Reda & Andreas 2004,
  *Solar Energy* 76(5):577–589, https://doi.org/10.1016/j.solener.2003.12.003): 2003-10-17 12:30:30 at UTC−7,
  39.742476° N, 105.1786° W, elevation 1,830.14 m, pressure 820 mbar, temperature 11 °C, ΔT = 67.0 s, refraction
  0.5667° → topocentric zenith 50.11162°, topocentric azimuth 194.340241°. The NREL report page was unreachable on
  2026-10-06; the values were read from the reference implementation's test vectors that transcribe the example
  (pvlib-python `tests/test_spa.py`, read 2026-10-06). The second oracle of FR-009-04 is analytical: the stage-frame
  vector conversion, and the solar elevation 90° − |φ − δ| at local solar noon for latitude φ and declination δ.

## 8. Clarifications log

- Families and classes (docs: "fixed in the perception spec") → resolved: two families (pit views from Replicator,
  crusher pocket from the ovrtx S3 camera) and five classes (FR-009-01, FR-009-03).
- Pairing unit of the DR ablation (docs: "images or training seeds — fixed in the spec") → resolved: test scenario
  seeds, paired cluster bootstrap (FR-009-31); B2's "paired CI over test images" is honoured with seeds as clusters of
  images, because images of one scenario are correlated.
- Ablation arms → resolved: arm U replaces only the structured pit family, keeping the crusher family and the budget
  equal (plan §7: two families + one unstructured arm).
- "Relative drop ≤ 10 pp" → resolved: Δ_rel as defined in the docs, in percent of the clean score (FR-009-30,
  SC-009-03).
- The ONNX Runtime framework page says "detection does NMS in a TypeScript worker", while the plan, M10 and the D-FINE
  card put the post-processor and top-K inside the graph (NMS-free) → resolved by the plan: no NMS for the live
  detectors (FR-009-35); reported to the coordinator.
- Reduced-precision Δ ≤ 1 pp → resolved as an absolute change in either direction (equivalence gate, spec 016).
- Mask acceptance on the crusher family (no instance ids) → resolved: pit family only (FR-009-23).
- Integration 2026-10-07: the frame-state contract is defined once, in spec 015-vlm (DC-015-01,
  `contracts/frame-state.schema.json`), and consumed there by the task-A builder and the task-C scorer. This spec adds
  its producer side: `st55_sdg` emits one valid frame state per frame (FR-009-44) and refuses frames whose stage data
  cannot give one (FR-009-45); task T-009-021.
- Integration 2026-10-07: draft schema written for DC-009-01 … DC-009-05 (`specs/009-perception/contracts/`, valid and
  hostile examples indexed in `examples/index.json`); the stricter reading was chosen each time: the dataset index is
  JSON Lines, one record per image validated by the root schema; the unstructured arm is pit family and training split
  only (record) and reuses the structured pit training seeds (`seed_source`, config); pit records are pinned to
  1280 × 720 px, Replicator instances, a frame state and depth to the image plane, crusher records carry
  connected-component labels, no instance mask and depth to the camera (images ≤ 1920 × 1080 px, NFR-013-05); depth is
  float32 `.npy` in metres; the COCO subset holds only `images`, `annotations` and `categories` (`info` and `licenses`
  are stripped), polygon segmentation only (the COCO form for iscrowd = 0), exactly the five id–name pairs, box
  coordinates ≥ −0.5 px and images ≤ 8,192 px a side; the unstructured ranges are bounded by the FR-009-08 envelope
  (defaults equal it), the structured sources, the 5° solar floor and the 0.05 m base offset are constants, and pool
  textures are CC0 only; the people record rejects community assets in the schema (`origin: system`), its export
  settings are format (fbx, dae, obj), scale unit and skeleton plus optional pose and flags, and mannequins are own
  data (CC-BY-4.0); the report carries `sim_to_real` per class, forced to "not measured" and with no probe block until
  the probe is labelled, probe classes are the four equipment and people classes, AP fields are absent at zero support,
  each SC row's model, precision, statistic and threshold are pinned, and an insufficient-support count is ≤ 99; seeds
  are 0 … 2⁶³ − 1 (recipe seed range, spec 001), and the array caps not stated here (≤ 50,000 images and ≤ 10⁶
  annotations per COCO file, ≤ 512 placements per image, image count 1 … 100,000 per arm, drying time (0, 1,440] min,
  `x_os` (0, 10] m) are design bounds.
- (no open items)

## 9. Changes (only for features that modify earlier behaviour)
### ADDED Requirements
(none — new feature)
### MODIFIED Requirements
(none)
### REMOVED Requirements
(none)

# Plan 009 — Perception: synthetic-data detectors with a domain-randomisation ablation
Spec: ./spec.md

## Summary
1. A pure-Python **DR sampler** in the open studio environment draws every per-image randomisation value (sun, dust,
   wet roads, placement, unstructured ranges) and writes a parameter table; the Isaac Sim stage `st55_sdg` only
   consumes it (FR-009-03 … FR-009-09, FR-009-41). An **asset guard** checks licences and people records before any
   render (FR-009-10 … FR-009-12).
2. A **dataset builder and loader** in `pipeline/` validate COCO and the dataset index, derive crusher-family instances
   and build seed-grouped splits with leak checks (FR-009-13 … FR-009-17).
3. **Training** fine-tunes the upstream checkpoints through the runner, with a declared out-of-memory fallback and
   resume (FR-009-18 … FR-009-21).
4. **Evaluation** wraps `pycocotools`, adds cluster-bootstrap intervals, the corruption ladder, the paired DR ablation
   and the honesty labels (FR-009-22 … FR-009-34).
5. **Export hooks** fix the detector graph signatures and lanes; the generic export, parity and TensorRT work is
   spec 016 (FR-009-35 … FR-009-39).

## Technical context
Runtime: Python 3.14 (`studio/` and `pipeline/` uv projects; `studio/isaac/` on Python 3.12 for Isaac Sim) · key
dependencies locked today: torch 2.14.1 (cu130), onnxruntime-gpu 1.30.0, onnx 1.23.1, onnxslim 0.1.97,
scikit-learn 1.9.1, shapely and pyarrow (studio); to be resolved, locked and proved on the target runtime before
feature code (task T-009-000): `pycocotools`, `rfdetr` 1.11.1, the D-FINE upstream code at a pinned commit
(Apache-2.0), `ImageHash` 4.3.2, `pvlib` (solar position) · target: local GPU (training, SDG), CPU (samplers,
evaluation, tests), GitHub Pages (two live ONNX files and baked outputs).

## Constitution check
| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | yes | synthetic data is labelled synthetic with exact labels; no sim-to-real claim without the probe (FR-009-32) |
| Spec before code | yes | every behaviour has an FR/P/NFR/SC id in spec 009 |
| Acceptance-test-first | yes | each task in tasks.md is a `[red]`/`[green]` pair; SC rows have acceptance tests that read the evaluation report |
| Independent oracles | yes | oracle per requirement in the table below: analytical (haze, exposure, sRGB, projection), published worked example (SPA solar position), reference implementations (`pycocotools`, `shapely`, `scipy.stats`, `ImageHash`, `minephys`), hand calculation |
| Determinism & explicit tolerances | yes | seeded samplers and counter-based noise; tolerances justified below |
| Neutral contracts | yes | DC-009-01 … DC-009-05 under `contracts/`, types generated; DC-000-01 for manifests |
| Static delivery | yes | live D-FINE-N fp16 / D-FINE-S int8 with baked fallback outputs; RF-DETR-Seg-N and D-FINE-S fp32 baked only (FR-009-37, FR-009-38) |
| Honesty | yes | "not measured" and "calibrated synthetic" labels; performance local-only for SDG and ovrtx (FR-009-32, FR-009-41) |
| Licence hygiene | yes | asset guard, MakeHuman §C record, no display-only inputs in training (FR-009-10, FR-009-11, FR-009-19) |
| Simplicity | yes | `pycocotools`, `rfdetr`, D-FINE upstream code and `pvlib` used directly; the corruption functions are the only new numerical code |

## Design
Data flow: [synthetic-data validation](../../docs/assets/diagrams/synthetic-data-validation.svg) and
[export parity](../../docs/assets/diagrams/model-export-parity.svg).

| Component (planned location) | Responsibility | Requirements |
|---|---|---|
| DR sampler (`studio/src/pitstudio_studio/sdg/`) | structured and unstructured draws; parameter table per image | FR-009-03 … FR-009-09, P-009-12 |
| Asset guard (`studio/src/pitstudio_studio/sdg/`) | licence records, vendor-path denylist, MakeHuman records, mannequin fallback | FR-009-10 … FR-009-12 |
| `st55_sdg` (`studio/isaac/src/pitstudio_isaac/sdg/`) | render RGB, boxes, masks, depth, intrinsics from the parameter table; write one frame state per frame (DC-015-01) | FR-009-02, FR-009-40, FR-009-41, FR-009-44, FR-009-45 |
| Dataset builder and loader (`pipeline/`, perception module) | COCO and index validation, crusher components, splits, leak checks | FR-009-01, FR-009-13 … FR-009-17, FR-009-42, P-009-13, P-009-14 |
| Training (`pipeline/` `s30_train`) | fine-tuning, licence guard, OOM fallback, resume | FR-009-18 … FR-009-21 |
| Evaluation (`pipeline/` `s50_evaluate`) | AP via `pycocotools`, intervals, support, corruptions, DR ablation, probe, labels | FR-009-22 … FR-009-34, FR-009-43, P-009-01 … P-009-11 |
| Export hooks (`pipeline/` `s60_export`, spec 016) | detector signatures, live set, lane, variant rejection | FR-009-35 … FR-009-39 |

The parameter table is the file handoff between the Python 3.14 sampler and the Python 3.12 Isaac Sim stage, so all
sampling logic is tested on CPU without Isaac Sim, and the GPU stage is a thin consumer.

## Test strategy
| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-009-01 | contract | hand calculation: tagged rocks of 1.2 m and 0.9 m with `x_os` = 1.0 m → `boulder` / not | pytest |
| FR-009-02 | integration (gpu) | analytical: a plane at 10 m gives depth 10 ± 0.01 m; a unit cube's box equals its pinhole projection ± 1 px | pytest (`gpu`) |
| FR-009-03 | contract | hand calculation: default counts 3 × 10,000; arm U seeds ⊆ pit training seeds | pytest |
| FR-009-04 | unit | published worked example: SPA (Reda & Andreas 2004, DOI 10.1016/j.solener.2003.12.003, appendix example; §7 of the spec); analytical: noon elevation 90° − \|φ − δ\| and vector conversion | pytest |
| FR-009-05 | unit | reference implementation: `minephys.environment` dust extinction on the fixture concentration | pytest |
| FR-009-06 | unit | hand calculation: watered 10:00, drying 60 min → wet at 10:59, dry at 11:01 | pytest |
| FR-009-07 | property | reference implementation: `shapely` point-in-polygon; analytical terrain height of a planar fixture | Hypothesis |
| FR-009-08 | property | analytical distributions: Kolmogorov–Smirnov against uniform / log-uniform (`scipy.stats`), p ≥ 1e-3 at n = 10,000, fixed seed | Hypothesis + scipy |
| FR-009-09 | unit (hostile) | hand calculation: one fixture per error class with its expected JSON pointer | pytest |
| FR-009-10 | unit (hostile) | hand calculation: `omniverse://` URL, vendor root path, missing record → `asset-licence` | pytest |
| FR-009-11 | contract | hand calculation: valid MakeHuman and mannequin records; card text present | pytest + jsonschema |
| FR-009-12 | unit (hostile) | hand calculation: wrong zip hash, community asset, missing settings → reject; none left → mannequins | pytest |
| FR-009-13 | unit | hand calculation: a 32 × 32 mask with three components and known boxes | pytest |
| FR-009-14 | contract | reference implementation: `jsonschema` (2020-12) on valid and invalid fixtures | pytest |
| FR-009-15 | unit (hostile) | hand calculation: one malformed COCO file per listed case | pytest |
| FR-009-16 | property | hand calculation: 80 / 10 / 10 % of n seeds within ±1; ≥ 900 test images per family | Hypothesis |
| FR-009-17 | unit (hostile) | reference implementation: `ImageHash` pHash of a re-encoded copy (Hamming ≤ 4) | pytest |
| FR-009-18 | integration (gpu) + contract | published values: upstream loss coefficients (RF-DETR 1.11.1 config); pinned checkpoint hashes; manifest fields by schema | pytest (`gpu`) |
| FR-009-19 | unit (hostile) | hand calculation: manifests with `display-only`, `reference-only` and probe inputs | pytest |
| FR-009-20 | unit (fake GPU) | hand calculation: batch/accumulation 16/1 → 8/2 → 4/4 → 2/8 → 1/16 → `oom-exhausted` | pytest + fake GPU backend (spec 002) |
| FR-009-21 | unit (fake GPU) | analytical: closed-form learning-rate schedule at step k; recorded data order; metamorphic: interrupted + resumed = uninterrupted | pytest + fake GPU backend |
| FR-009-22 | unit + reference | hand calculation: AP50 of tiny fixtures (e.g. one ground truth, one true and one false positive); reference implementation: direct `pycocotools` call on random fixtures | pytest |
| FR-009-23 | unit + reference | hand calculation: mask AP on 8 × 8 fixtures; `pycocotools` with RLE masks | pytest |
| FR-009-24 | unit (hostile) | hand calculation: 99 instances → "not evaluable (insufficient support)" | pytest |
| FR-009-25 | unit + metamorphic | analytical: constant image and depth → t·I + (1 − t)·A; IEC 61966-2-1 transfer function | pytest |
| FR-009-26 | unit + metamorphic | analytical: σ_n = 0 → k·I; noise sample std within ±1 % of σ_n at 10⁶ samples | pytest |
| FR-009-27 | unit + property | analytical: constant image with a known mask → closed form; coverage bound of P-009-05 | pytest + Hypothesis |
| FR-009-28 | unit | hand calculation: no depth → d = 100 m, `depth_assumed: true` | pytest |
| FR-009-29 | unit (hostile) | hand calculation: NaN, inf, wrong shape, negative depth, severity 6, unknown name → `ValueError` | pytest |
| FR-009-30 | unit | hand calculation: m_clean = 0.80, m_s = 0.75 → Δ_rel = 6.25 | pytest |
| FR-009-31 | unit | analytical: a constant per-seed difference d gives the interval [d, d]; hand calculation of the verdict mapping | pytest |
| FR-009-32 | contract + unit | hand calculation: B2 data built without a probe carries the labels and no real-domain field | pytest + jsonschema |
| FR-009-33 | unit | hand calculation: labellers with 3 and 3 boxes, 2 matches → F1 = 2/3; AP on a 4-image fixture | pytest |
| FR-009-34 | unit (hostile) | hand calculation: unlicensed file excluded; 201 images or missing labeller B → `probe-invalid` | pytest |
| FR-009-35 | contract | hand calculation: inspector on `onnx.helper` graphs (opset 19 with `GridSample`-16 passes; opset 20 with `GridSample`-20 fails; wrong I/O names fail); slow test on the real export | pytest + onnx |
| FR-009-36 | contract | hand calculation: same inspector with the RF-DETR signature; lane = precompute | pytest + onnx |
| FR-009-37 | CI | hand calculation: the allowed list of perception ONNX files in the web build | pytest |
| FR-009-38 | contract | hand calculation: timing records of 299 / 301 ms and sizes of 25,000,000 / 25,000,001 bytes | pytest |
| FR-009-39 | unit | hand calculation: Δ = 1.2 pp → rejected; Δ_rel = 11 at s = 2 → rejected | pytest |
| FR-009-40 | unit (fake GPU) | hand calculation: capability fixtures (Isaac Sim fail; ovrtx fail) → expected "not run" statuses and card notes | pytest + fake GPU backend |
| FR-009-41 | contract | hand calculation: a manifest with a timing field on a `local-only` stage is refused; card fields | pytest |
| FR-009-44 | contract + integration (gpu) | hand calculation: a fixture stage with `metersPerUnit` 0.01 and a cube translated by 500 units gives a 5 m transform; the written file validates against `contracts/frame-state.schema.json` (jsonschema reference validator) and its image SHA-256 equals `hashlib` on the PNG | pytest (+ `gpu` for the rendered case) |
| FR-009-45 | unit (hostile) | hand calculation: stages without `metersPerUnit` or `upAxis`, a NaN transform, an unknown class label, a duplicated prim id → no frame state, frame excluded, count reported | pytest |
| FR-009-42 | unit (hostile) | hand calculation: a frame with a wrong SHA-256, a `../` path, a 1279 × 720 mask, class value 6 → rejected | pytest |
| FR-009-43 | unit (hostile) | hand calculation: NaN score, unknown image id, category 7, 301 detections, arms on different images → rejected | pytest |
| P-009-01 … P-009-04 | metamorphic | invariants (semigroup, monotonicity, equivariance, composition) | Hypothesis |
| P-009-05, P-009-06 | property | analytical bounds; exact code round trip | Hypothesis |
| P-009-07 … P-009-09 | metamorphic | invariants checked through `pycocotools` | Hypothesis |
| P-009-10, P-009-11 | property | analytical (unit invariance, antisymmetry) | Hypothesis |
| P-009-12 … P-009-14 | property | invariants (daylight, placement, split disjointness, box minimality and flip equivariance) | Hypothesis |
| NFR-009-01, NFR-009-06 | CI | file sizes and counts against the stated caps | pytest |
| NFR-009-02 | contract | web timing records (spec 018) against 300 ms / 1 s | pytest |
| NFR-009-03 | contract | run manifest: segment ≤ 8 h, ≥ 1 checkpoint per epoch | pytest |
| NFR-009-04 | pipeline | metamorphic: two runs, byte-identical reports | pytest |
| NFR-009-05 | unit | hand calculation: 9,499 valid of 10,000 → arm fails | pytest |
| SC-009-01 … SC-009-07 | pipeline (acceptance) | pre-registered thresholds read from the evaluation report (DC-009-05) | pytest |

### Tolerances and their justification
- float64 closed forms (haze, exposure, sRGB, vector conversion): atol / rtol 1e-12 — fewer than 20 operations on
  values of order 1, so rounding stays near 1e-15.
- 8-bit outputs: exact after round-half-to-even; the float path is tested separately.
- Solar position against the SPA example: 0.01° — loose enough for a solar-position solver less exact than SPA, and
  far below any visible rendering effect (the sun's own angular diameter is about 0.5°).
- Depth and projection on the GPU render: ±0.01 m and ±1 px — renderer float32 depth and pixel-centre conventions.
- Noise statistics: ±1 % relative std at 10⁶ samples — the standard error of a sample std is σ/√(2n) ≈ 0.07 % of σ, so
  ±1 % is above 10 standard errors.
- Distribution checks: Kolmogorov–Smirnov p ≥ 1e-3 at a fixed seed — deterministic, and a correct sampler fails with
  probability 1e-3 at most for one seed choice, fixed once.

## Risks and complexity tracking
| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Own corruption ladder instead of an off-the-shelf corruption package | dust needs renderer depth (physically based haze), night and rain need fixed, closed-form definitions that tests can check | the reference corruption packages are stale and do not provide depth-based haze or night darkening |
| Cluster bootstrap over scenario seeds | images of one scenario are correlated; pairing on images alone would make the interval too narrow | a per-image paired t-interval is not valid for mAP, a set-level metric |
| DR sampler split from the Isaac Sim stage | sampling logic testable on CPU in CI, renderer replaceable | sampling inside Replicator scripts cannot be tested without a GPU and the vendor runtime |

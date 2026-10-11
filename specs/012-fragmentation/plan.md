# Plan 012 — Fragmentation: synthetic exact-PSD muck piles, U-Net versus watershed + Swebrec, measured sim-to-real
Spec: ./spec.md

## Summary
1. **Real reference:** a hardened archive reader, group keys with the nine committed links, and a seeded grouped
   5-fold builder that tests on originals only (FR-012-01 … FR-012-08).
2. **Synthetic exact-PSD piles:** a pure-numpy generator with a provable PSD bound, volume-exact rock meshes, Warp DEM
   piles (spec 005) and Replicator renders with fragment-id instance masks (FR-012-09 … FR-012-17).
3. **Learned and classical pipelines:** the three-class U-Net (pinned encoder, U-Net weight map) and the
   scikit-image watershed, both feeding one PSD function and one Swebrec fit (FR-012-18 … FR-012-28).
4. **Evaluation:** foreground IoU, TSTR / TRTR per fold, x50 errors and two paired comparisons under FR-000-05,
   plus the C2ST, injected-shift and duplicate checks (FR-012-29 … FR-012-37).
5. **Publishing:** metrics only from the real set, honest "not run" paths, the `minephys` design grid and the live
   int8 TSTR U-Net (FR-012-38 … FR-012-43).

## Technical context
Runtime: Python 3.14 (`pipeline/` and `studio/` uv projects; `studio/isaac/` on Python 3.12 for renders) · locked
today: torch 2.14.1 (cu130), onnxruntime-gpu 1.30.0, onnx 1.23.1, onnxslim 0.1.97, scikit-learn 1.9.1, pooch, numpy;
`minephys` (git dependency of the root package) · to be resolved, locked and proved before feature code (T-012-000):
`segmentation-models-pytorch` 0.5.0 and `timm`, `scikit-image`, `scipy`, `ImageHash` 4.3.2, a 7z reader (`py7zr`,
LGPL-2.1, used as an unmodified library), the DINOv2 ViT-B/14 weights (Apache-2.0, pinned by SHA-256) and, optionally,
SAM 2.1-tiny (Apache-2.0) · target: local GPU (training, renders), CPU (generator, PSD, evaluation, tests), GitHub
Pages (one live int8 ONNX file and baked metrics).

## Constitution check
| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | yes | the real labelled set is the test bed; synthetic data is exact by construction and validated against it (FR-012-30 … FR-012-36) |
| Spec before code | yes | every behaviour has an id in spec 012 |
| Acceptance-test-first | yes | `[red]`/`[green]` pairs in tasks.md; SC rows have acceptance tests on the evaluation report |
| Independent oracles | yes | analytical (Swebrec recovery, Gaussian AUC, pinhole and volume formulas, Q-1), published worked equation (U-Net weight map, Ronneberger et al. 2015, Eq. 2, p. 5), reference implementations (`minephys.blasting`, scikit-image, scikit-learn, `ImageHash`, the bootstrap data-check counts), hand calculation |
| Determinism & explicit tolerances | yes | seeded folds, generator and bootstraps; tolerances justified below |
| Neutral contracts | yes | DC-012-01 … DC-012-05 under `contracts/`, generated types; DC-000-01 lineage |
| Static delivery | yes | live int8 U-Net with precomputed fallback outputs; D1 design grid baked for T0 (FR-012-41, FR-012-43) |
| Honesty | yes | "not run" paths, "TRTR only" label, `no-fit` penalty, two separate comparison claims, fold spread reported |
| Licence hygiene | yes | Mendeley metrics only with verbatim attribution and a hash blocklist; the live model saw no Mendeley image; the encoder licence is read from its card (FR-012-38, FR-012-42) |
| Simplicity | yes | scikit-image, scikit-learn, `segmentation_models_pytorch` and `scipy.optimize` used directly; Swebrec and the design models come from `minephys`, never re-implemented |

## Design
Data flow: [D1 TSTR design with grouped folds](../../docs/assets/diagrams/case-d1-tstr-design.svg) and
[sim-to-real validation](../../docs/assets/diagrams/sim-to-real-validation.svg).

| Component (planned location) | Responsibility | Requirements |
|---|---|---|
| Archive reader and split builder (`pipeline/`, fragmentation module; links file in `data/splits/`) | safe extraction, masks, hashes, groups, folds, leak checks | FR-012-01 … FR-012-07, FR-012-44, P-012-08 |
| Pile generator (`studio/src/pitstudio_studio/physics/`, pure numpy + `minephys`) | exact-PSD fragment tables, rock meshes | FR-012-09 … FR-012-12, P-012-09 … P-012-12 |
| Pile and render stages (`st50_physics` spec 005; `studio/isaac/` `st55_sdg`) | settled piles, renders with fragment-id masks | FR-012-13, FR-012-39 |
| Synthetic dataset builder (`pipeline/`) | splits by pile seed, truth, consistency guards | FR-012-14 … FR-012-17, P-012-17 |
| Label scheme and U-Net (`pipeline/` `s30_train`, `s40_infer`) | encoding, decoding, loss, arms, inference guards | FR-012-18 … FR-012-23, P-012-07, P-012-16 |
| PSD, fit and watershed (`pipeline/`) | instance sizes, passing points, Swebrec fit, classical baseline | FR-012-23 … FR-012-28, P-012-01 … P-012-05, P-012-13 |
| Evaluation (`pipeline/` `s50_evaluate`) | IoU, ρ_f, x50 errors, paired comparisons, C2ST, duplicates | FR-012-29 … FR-012-37, FR-012-45, P-012-06, P-012-14, P-012-15, P-012-18 |
| Publishing (`s60_export`, CI guard, D1 recipe) | metrics only, attribution, not-run labels, design grid, int8 export | FR-012-38, FR-012-40 … FR-012-43, FR-012-46 |

The PSD function, the Swebrec fit and the watershed are shared by the TSTR, TRTR and classical arms, so the
comparisons differ only in the segmentation.

## Test strategy
| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-012-01 | unit + pipeline | hand calculation: a small 7z fixture with expected members; the real archive's size and SHA-256 from the dataset card | pytest |
| FR-012-02 | unit (hostile) | hand calculation: fixtures with `../x`, an absolute name, a drive letter, a missing member, a 511 px image, an RGB `label.png` | pytest |
| FR-012-03 | pipeline | reference implementation: the bootstrap data-check counts (960 images, 63,144 non-empty instances) from an independent script, recorded in the dataset card | pytest (`slow`, needs local data) |
| FR-012-04 | unit | hand calculation: the components of §7 and 231 groups | pytest |
| FR-012-05 | unit + property | hand-checked invariants of the partition (P-012-08); fold sizes as returned by scikit-learn's `GroupKFold` (reference implementation used directly) | pytest + Hypothesis |
| FR-012-06 | unit (hostile) | hand calculation: fold files with a shared group, a file 241 in a test list, a missing original | pytest |
| FR-012-07 | unit (hostile) | hand calculation: one byte changed in a label → `label-modified` | pytest |
| FR-012-08 | contract | hand calculation: lineage fixtures with and without a SAM output in a test label set | pytest + jsonschema |
| FR-012-09 | unit + property | analytical: truncated Swebrec passing function (closed form, with `minephys.blasting` as reference implementation of S) at the class boundaries | pytest + Hypothesis |
| FR-012-10 | property | analytical bound v_max / V_real (P-012-12) | Hypothesis |
| FR-012-11 | unit (hostile) | hand calculation: one invalid parameter per case | pytest |
| FR-012-12 | unit | analytical: sphere volume π x³ / 6; divergence-theorem volume of a unit cube and a regular tetrahedron (hand calculation) | pytest |
| FR-012-13 | integration (gpu) | analytical: one sphere of radius r at depth z covers π (f r / z)² px within 2 % and has depth z ± 0.01 m | pytest (`gpu`) |
| FR-012-14 | property | hand calculation: 80 / 10 / 10 % of pile seeds; ≥ 5,000 tiles; ≥ 50 held-out piles | Hypothesis |
| FR-012-15 | unit | hand calculation: Q-1 on a four-fragment table (sizes 0.1, 0.2, 0.3, 0.4 m) | pytest |
| FR-012-16 | unit (hostile) | hand calculation: an unknown instance id; a duplicated fragment id | pytest |
| FR-012-17 | unit (hostile) | hand calculation: a TSTR manifest containing one Mendeley hash | pytest |
| FR-012-18 | unit | hand calculation: 6 × 6 fixture with two touching instances | pytest |
| FR-012-19 | unit | hand calculation: two touching rectangles decode to two instances and the exact foreground | pytest |
| FR-012-20 | unit + integration (gpu) | published worked equation: weight map of Ronneberger et al. 2015, Eq. 2, p. 5, hand-calculated on a two-square fixture; layer shapes of the pinned encoder from its model card | pytest |
| FR-012-21 | unit | hand calculation: the layer table of the U-Net (encoder 64/64/128/256/512, decoder 256/128/64/32/16 channels) for the vendored variant | pytest |
| FR-012-22 | contract | hand calculation: identical config fields across arms, seed and step count | pytest |
| FR-012-23 | unit (hostile) | hand calculation: wrong dtype, shape, channels, NaN for the U-Net; a float image or an 8 × 8 image for the watershed → `ValueError` | pytest |
| FR-012-24 | unit | hand calculation: areas 4π, 16π, 36π px² → sizes 4, 8, 12 px and passing points 1/14, 5/14, 1; pinhole conversion | pytest |
| FR-012-25 | unit (hostile) | hand calculation: two instances, a zero area, a non-convergent fixture → `no-fit` and error 1.0 | pytest |
| FR-012-26 | unit | analytical: exact recovery (P-012-05); hand calculation of the M11 worked example (x50 0.25 m, x_max 1.5 m, b 2 → P(0.10 m) = 0.304) through `minephys.blasting` | pytest + Hypothesis |
| FR-012-27 | unit (hostile) | hand calculation: one invalid argument per case | pytest |
| FR-012-28 | unit | reference implementation: direct scikit-image calls on the fixture; hand calculation: two separated discs → two instances | pytest |
| FR-012-29 | unit | hand calculation: 4 × 4 masks (IoU 3/5), both empty → 1.0 | pytest |
| FR-012-30 | unit | hand calculation: IoU 0.72 / 0.80 → ρ_f = 0.90; mean, minimum, standard deviation of five values | pytest |
| FR-012-31 | unit | hand calculation: x̂50 = 11 px, x50 = 10 px → 0.10; MRE of three views | pytest |
| FR-012-32 | unit | analytical: identical per-cluster differences d give the interval [d, d]; antisymmetry; hand calculation of the verdict mapping | pytest + Hypothesis |
| FR-012-33 | unit + pipeline | analytical: Gaussian fixtures with AUC Φ(‖μ‖/√2) (P-012-15) | pytest + scikit-learn |
| FR-012-34 | unit + pipeline | analytical: a mean shift of ‖μ‖ = 2 must give AUC ≥ 0.80 (Φ(√2) = 0.921); on real data the threshold itself | pytest |
| FR-012-35 | pipeline | pre-registered threshold 0.60 on the report | pytest |
| FR-012-36 | unit + pipeline | reference implementation: `ImageHash` on a re-encoded copy (flagged); cosine of identical embeddings = 1 | pytest |
| FR-012-37 | unit (hostile) | hand calculation: 99 samples, one class, a NaN embedding → `c2st-invalid` | pytest |
| FR-012-38 | CI + contract | hand calculation: a fixture file whose hash is listed fails the guard; the attribution text equals the card's string | pytest |
| FR-012-39 | unit (fake GPU) | hand calculation: capability fixture with Isaac Sim failing → expected statuses and label | pytest + fake GPU backend (spec 002) |
| FR-012-40 | unit | hand calculation: SHA-256 mismatch → statuses and the D1 statement | pytest |
| FR-012-41 | unit + reference | reference implementation: `minephys.blasting` called directly on the grid (exact float64 equality) | pytest |
| FR-012-42 | contract | hand calculation: opset 17, `QuantizeLinear` / `DequantizeLinear` with per-channel `axis` on weights, calibration list disjoint from evaluation lists | pytest + onnx |
| FR-012-43 | unit | hand calculation: Δ IoU 1.2 pp → rejected; mask IoU 0.985 → rejected | pytest |
| FR-012-44 | unit (hostile) | hand calculation: a link 12–241, a link 5–5, a malformed file → `links-invalid` | pytest |
| FR-012-45 | unit (hostile) | hand calculation: 512² vs 511² masks, a uint8 foreground, x50 = 0 → `ValueError` | pytest |
| FR-012-46 | unit (hostile) | hand calculation: burden NaN, spacing 0, an input `minephys.blasting` rejects → no grid | pytest |
| P-012-01 … P-012-04, P-012-13, P-012-17 | metamorphic | invariants (dihedral symmetry, unit change, permutation, replication, pinhole scaling, quantile monotonicity) | Hypothesis |
| P-012-05 | property | analytical exact recovery | Hypothesis |
| P-012-06, P-012-07, P-012-08, P-012-16 | property / metamorphic | invariants | Hypothesis |
| P-012-09 … P-012-12 | metamorphic / property | invariants and the analytical bound | Hypothesis |
| P-012-14, P-012-15 | metamorphic / property | invariants; analytical AUC of Gaussian classes | Hypothesis + scikit-learn |
| P-012-18 | metamorphic | invariants of the paired cluster bootstrap (antisymmetry, order invariance, identity) | Hypothesis |
| NFR-012-01, NFR-012-02 | CI / contract | file size; web timing record (spec 018) | pytest |
| NFR-012-03 | contract | run manifest fields | pytest |
| NFR-012-04 | pipeline | metamorphic: two runs, byte-identical outputs | pytest |
| SC-012-01 … SC-012-05 | pipeline (acceptance) | pre-registered thresholds read from the evaluation report (DC-012-03) | pytest |

### Tolerances and their justification
- Swebrec fit recovery and scale equivariance: rtol 1e-6 — the solver stops at xtol = ftol = 1e-12, and the
  conditioning of the two-parameter fit near small b amplifies this by at most about 10⁶ on the tested domain.
- Generator scaling and pinhole formulas: rtol 1e-12 — a handful of float64 multiplications and exponentials.
- Mesh volume: rtol 1e-3 — the convex rock mesh is a polyhedron scaled to the target volume; 1e-3 bounds the
  float32 vertex storage of the render mesh.
- Rendered area of a sphere: 2 % — pixel quantisation of a disc of radius ≥ 20 px (perimeter / area ≈ 2/r) and
  anti-aliasing of the instance mask.
- Gaussian AUC: ±0.03 — with 4,000 samples per class the standard error of an AUC is below 0.007, so ±0.03 is above
  four standard errors while still catching a mis-oriented or leaking classifier.
- Null coverage ≥ 45 of 50: the probability that a correct 95 % interval covers 0.5 fewer than 45 times in 50 is about
  1 % (binomial), fixed once by the seeds.

## Risks and complexity tracking
| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Cluster bootstrap over source groups for the real comparison | the nine merged pairs and the shared TSTR model make tiles not independent | a per-tile paired t-interval would be too narrow |
| Penalty error 1.0 for `no-fit` images | a method must not gain by failing on hard images | dropping failed images would bias the comparison towards the method that fails more |
| Cumulative stratified fill instead of i.i.d. sampling | gives a provable PSD bound with a few thousand fragments | i.i.d. sampling by volume leaves the coarse tail noisy because few large fragments carry most of the volume |
| `smp` may be replaced by a vendored U-Net | `smp` has had no release for about 17 months and may fail on Python 3.14 / torch 2.14 | dropping the U-Net would remove the measured sim-to-real result |

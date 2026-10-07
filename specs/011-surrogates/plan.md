# Plan 011 — Surrogates and calibration: GNS, differentiable DEM calibration, FNO
Spec: ./spec.md

## Summary
Three learned or optimised layers on top of the studio's solvers (spec 005):
1. **GNS** (`pitstudio_pipeline.surrogates.gns`; pure numpy graph and observables in `src/pitstudio/granular/`):
   radius graph, encode–process–decode step, one-step training, held-out-geometry evaluation on observables, padded
   ONNX export → FR-011-01…16, P-011-01…07.
2. **DEM calibration** (`pitstudio_studio.physics.calibration` on Warp; numpy protocol core in
   `src/pitstudio/calibration/`): smooth observable, tape arm, CMA-ES arm, common budget, seed-ensemble interval,
   gradient gate, coverage study → FR-011-17…31, P-011-08…11.
3. **FNO** (`pitstudio_pipeline.surrogates.fno`): DFT-matmul spectral layer, tailings and dust direct maps, held-out
   terrain evaluation, MatMul-only export → FR-011-32…43, P-011-12…16.
Shared runner behaviour and labels → FR-011-44, FR-011-45.

## Technical context
Runtime: Python 3.14 in `pipeline/` (PyTorch cu130 / cpu, ONNX Runtime 1.30, onnx, onnxslim, zarr) and in `studio/`
(Warp 1.17 with its CPU and CUDA devices, Newton 1.6) · Node 24 web (spec 018 engines `gns` and `fno`) · targets: local
GPU for training and calibration, CPU for every CI test, GitHub Pages. Python tests live in `tests/<level>/`; tests
that need PyTorch or ONNX Runtime run in the `pipeline/` job, tests that need Warp or `cma` run in a `studio/` CPU job
(T-011-002), and all of them use `pytest.importorskip` in the root job. Tests marked `gpu` never run in CI.

Dependencies to resolve and lock before feature code (task T-011-002):

| Package | Environment | Purpose | If it does not resolve |
|---|---|---|---|
| `cma` (pycma, BSD-3-Clause) | `studio/` | CMA-ES arm | a minimal own CMA-ES for one and two dimensions following Hansen's tutorial, tested on the sphere function |
| `neuraloperator` 2.0.0 (MIT) | `pipeline/` (optional) | second spectral oracle (FR-011-43) | numpy FFT reference only, stated in the card |

## Constitution check
| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | yes | trained on the studio's own physics; real Bingham terrain for the FNO; literature repose targets as the real anchor; every dataset labelled "calibrated synthetic" (FR-011-45) |
| Spec before code | yes | all behaviour carries FR/P/NFR/SC/DC ids |
| Acceptance-test-first | yes | each task in `tasks.md` is a `[red]`/`[green]` pair with its own test file |
| Independent oracles | yes | brute-force pairwise distances (graph), analytic piles (observables), numpy FFT (spectral layer), a sliding-sphere closed form (tape), a fake analytic simulator with known coverage (interval, gate), ONNX Runtime CPU vs PyTorch (export), binomial arithmetic (coverage) |
| Determinism & explicit tolerances | yes | seeds for packings, trials, splits and bootstrap; deterministic Warp atomics; tolerances justified below |
| Neutral contracts | yes | DC-011-01…04 under `contracts/` with generated types (T-011-001) |
| Static delivery | yes | GNS and FNO live in ORT-web with baked rollouts and fields as T0; calibration is REPLAY |
| Honesty | yes | extrapolation labels (FR-011-11, FR-011-39), overflow and divergence flags (FR-011-12, FR-011-13), non-identified and unreliable trials counted against coverage (FR-011-22, FR-011-23), resolution transfer not claimed (FR-011-42) |
| Licence hygiene | yes | own code Apache-2.0; `geoelements/gns` cited, not copied; Warp and Newton Apache-2.0; terrain public domain |
| Simplicity | yes | pure-PyTorch GNS and FNO, no graph or operator framework; one observable function for reference and surrogate |

## Design

![GNS message passing](../../docs/assets/diagrams/gns-message-passing.svg)
![FNO built from DFT matrix products](../../docs/assets/diagrams/fno-architecture.svg)
![Breach to shallow water to FNO](../../docs/assets/diagrams/tailings-shallow-water.svg)

| Component | Module (planned) | Requirements |
|---|---|---|
| Radius graph (Python) | `src/pitstudio/granular/graph.py`; TS twin in the `gns` worker (spec 018) | FR-011-02, FR-011-13, P-011-04 |
| GNS model and step | `pitstudio_pipeline.surrogates.gns.model` | FR-011-01, FR-011-15, P-011-01, P-011-02, P-011-05 |
| Rollout loop and guards | `src/pitstudio/granular/rollout.py` (step passed in as a callable) | FR-011-12, P-011-03 |
| Observables | `src/pitstudio/granular/observables.py` | FR-011-05, P-011-06, P-011-07 |
| Dataset, training, evaluation | `pitstudio_pipeline.surrogates.gns.{data, train, evaluate}` | FR-011-03, FR-011-04, FR-011-06, FR-011-10, FR-011-14, FR-011-16 |
| GNS export | `pitstudio_pipeline.surrogates.gns.export` | FR-011-07, FR-011-08 |
| Calibration protocol core (interval, gate, coverage, budget accounting) | `src/pitstudio/calibration/` (numpy) | FR-011-21, FR-011-22, FR-011-23, FR-011-24, FR-011-25, P-011-09, P-011-10 |
| Heap observables (smooth, hard) | `src/pitstudio/calibration/observables.py` + a Warp kernel twin | FR-011-18, P-011-08 |
| Tape arm, CMA-ES arm, driver | `pitstudio_studio.physics.calibration.{tape, cmaes, driver}` | FR-011-17, FR-011-19, FR-011-20, FR-011-26…30, P-011-11 |
| Spectral layer and FNO | `pitstudio_pipeline.surrogates.fno.{spectral, model}` | FR-011-32, FR-011-33, P-011-12…16 |
| Field data, evaluation, export | `pitstudio_pipeline.surrogates.fno.{data, evaluate, export}` | FR-011-34…37, FR-011-41…43 |
| Web behaviour (A3, C2, C3 tabs) | `web/src/cases/a3/`, `web/src/cases/c2/`, `web/src/cases/c3/` on the spec 018 engines | FR-011-09, FR-011-11, FR-011-31, FR-011-38…40 |

Data flow: `st50_physics` (rollouts, fields, calibration runs; DC-011-01, DC-011-03, DC-011-04) → `s10_preprocess`
(validation, splits) → `s30_train` → `s40_infer` → `s50_evaluate` → `s60_export` (ONNX + DC-011-02 + manifests) → web.

### Interfaces and their hostile-input requirements
| Interface | Kind | Hostile requirement |
|---|---|---|
| Rollout files | file input | FR-011-14 |
| GNS step (PyTorch, ONNX, web) | function + UI | FR-011-15 |
| Rollout loop | function | FR-011-12, FR-011-13 |
| A3 geometry controls | UI control | FR-011-11 (extrapolation) + FR-018-41 (numeric controls) |
| Reference rollouts at evaluation | stage input | FR-011-10 |
| Calibration driver | function + recipe | FR-011-29, FR-011-30 |
| Field files | file input | FR-011-41 |
| FNO (PyTorch, ONNX, web) | function + UI | FR-011-40 |
| C2 / C3 controls | UI control | FR-011-39 + FR-018-41 |

### Numerical cores and their metamorphic relations
| Core | Relations (≥ 3) |
|---|---|
| Radius graph | P-011-04 (symmetry, no self-edge, distance bound, order, cross-language identity), P-011-01 (permutation through the model) |
| GNS step | P-011-01 (permutation), P-011-02 (translation), P-011-05 (aggregation equivalence), P-011-03 (conservation) |
| Granular observables | P-011-06 (analytic pile, mirror, translation, permutation), P-011-07 (translation, scaling, monotonicity) |
| Calibration protocol | P-011-08 (observable agreement), P-011-09 (coverage, linear scaling of the half-width in σ̂ and 1/\|ĝ\|), P-011-10 (gate acceptance and rejection), P-011-11 (determinism) |
| Spectral layer | P-011-12, P-011-13 (references), P-011-14 (shift), P-011-15 (linearity), P-011-16 (resolution change) |

### Tolerances and their justification
- **GNS equivariance 1e-5 × max \|a\|** (P-011-01, P-011-02, P-011-05): permuting particles changes only the order of
  ≤ 32 fp32 additions per aggregation (≤ 32 × 6e-8 ≈ 2e-6 relative), carried through 10 residual steps with layer
  normalisation; 1e-5 bounds the growth with a margin of 5.
- **Repose extractor 0.4°** (P-011-06): measured at specification on analytic piles laid particle by particle with bins
  of 2d: ≤ 0.35° for piles ≥ 30 d high over θ ∈ [20°, 45°].
- **Smooth vs hard 0.5°** (P-011-08): the soft-max envelope with β = 10/d exceeds the hard maximum by at most
  ln(n_b)/β ≈ 0.3 d for n_b ≤ 20 particles per bin, an almost uniform offset that the slope fit removes; 0.5° leaves
  room for the non-uniform part.
- **Coverage band [0.93, 0.97]** (P-011-09): over 2,000 fake trials the binomial standard deviation at 0.95 is 0.0049;
  the band is ± 4 standard deviations. A 20,000-trial simulation at specification gave 0.948–0.953 across
  σ ∈ {0.2°, 0.5°, 1°} with optimiser errors up to 0.1°.
- **Gate rates** (P-011-10): a 20,000-trial simulation at specification gave 99.0 % acceptance at \|g\| = 10 SE_FD and
  0 % for a flipped sign; 98 % over 1,000 trials leaves 3 binomial standard deviations.
- **Spectral references: float64 ≤ 1e-12 ‖a‖₂, float32 ≤ 1e-4 ‖a‖₂** (P-011-12…15): rounding of a length-64 matrix
  product grows like √n u per output, ≈ 8 × 1.1e-16 ≈ 1e-15 (float64) and 8 × 6e-8 ≈ 5e-7 (float32) relative to
  ‖a‖₂ per axis, twice for 2-D; the bounds keep margins of 100–1,000 for the inverse weighting.
- **Resolution change float64 ≤ 1e-10 ‖u‖₂** (P-011-16): the identity is exact in real arithmetic; the 128-point
  bases double the rounding path.
- **Export parity** (SC-011-04): `models.onnx_cpu_fp32`; browser parity FR-018-57.
- **fp16 acceptance** (FR-011-08, FR-011-37): ≤ 0.5° and ≤ 1 % keep the fp16 change at one third of the acceptance
  tolerance (1.5°, 5 %); ≤ 1 pp of relative L2 follows `models.quantized_task_metric_delta_max_pp`.

## Test strategy
| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-011-01 | pipeline | shapes from DC-011-02; parameter count by hand from the layer sizes (≈ 1.5 M); a zero-output decoder gives a = 0 and the hand-computed Euler step | pytest |
| FR-011-02, FR-011-13 | property + parity | brute-force O(N²) pairwise distances (numpy); hand-counted neighbours on a hexagonal lattice (R = 2.5 d); the TS builder on the same fixtures | Hypothesis, Vitest |
| FR-011-03, FR-011-04 | pipeline | split membership by geometry id and the 0.05 distance rule checked on a fixture manifest; validation-only selection checked from the training log | pytest |
| FR-011-05 | property | analytic piles of P-011-06; hand-computed percentiles | Hypothesis |
| FR-011-06, FR-011-10 | pipeline | fixture rollouts with known θ and L and one not at rest | pytest |
| FR-011-07 | pipeline | ONNX graph inspection: operator types of the live graph contain no ScatterElements; opset and IR version fields | pytest + onnx |
| FR-011-08 | pipeline | ONNX Runtime CPU fp32 against PyTorch fp32 (reference implementation) on 200 golden steps; a perturbed fp16 graph that must be refused | pytest |
| FR-011-09, FR-011-11 | E2E | baked fixture rollouts and the envelope of DC-011-02 | Playwright |
| FR-011-12 | unit | constructed states (a NaN, a particle beyond bounds + R) | pytest |
| FR-011-14 | pipeline (hostile) | one invalid file per class, built by the test | pytest |
| FR-011-15 | pipeline + web (hostile) | invalid inputs written in the test | pytest, Vitest |
| FR-011-16 | pipeline | contract of the speed block | pytest |
| FR-011-17, FR-011-19 | unit (Warp CPU device) + gpu | closed form of a sphere launched sliding on a plate: x(T) = v₀T − ½ μ g T² for T < 2v₀/(7 μ g), so ∂x/∂μ = −½ g T²; the tape gradient matches it within 2 % | pytest |
| FR-011-18 | property | analytic conical heaps (P-011-08) | Hypothesis |
| FR-011-20, FR-011-21 | unit | the fake linear simulator (exact optimum μ = (θ* − a)/b); the sphere function in one dimension | pytest |
| FR-011-22 | property | the interval formula by hand on fixed numbers; coverage on the fake simulator (P-011-09) | Hypothesis |
| FR-011-23 | property | the fake simulator with known gradient (P-011-10) | Hypothesis |
| FR-011-24, FR-011-25 | pipeline | Wilson interval by hand (45 of 50 → 0.786–0.957); paired bootstrap bounds from injected resamples (numpy) | pytest |
| FR-011-26 | contract | `calibration-result.schema.json` valid and invalid documents | pytest + jsonschema |
| FR-011-27 | unit | the fake simulator in two dimensions with one direction made flat (must be labelled "weakly identified") | pytest |
| FR-011-28 | unit + gpu | knowledge-table fixture rows with VERIFIED and UNVERIFIED status; provenance fields | pytest |
| FR-011-29, FR-011-30 | unit (hostile) | invalid requests written in the test; a memory estimate above 80 % of a fake device's free memory | pytest |
| FR-011-31 | E2E | baked calibration fixture | Playwright |
| FR-011-32 | property | numpy FFT (P-011-12, P-011-13); static check that the module imports no `torch.fft` and creates no complex tensor | Hypothesis + pytest |
| FR-011-33 | pipeline | channel order and units from DC-011-02 | pytest |
| FR-011-34, FR-011-41 | pipeline (hostile for 41) | split by patch on a fixture; invalid field files built by the test | pytest |
| FR-011-35, FR-011-42 | pipeline | hand-computed relative L2, area, arrival time and volume on 4 × 4 and 64 × 64 synthetic fields | pytest |
| FR-011-36 | pipeline | operator list of the exported graph against the whitelist | pytest + onnx |
| FR-011-37 | pipeline | ONNX Runtime CPU fp32 against PyTorch fp32 on 200 golden fields | pytest |
| FR-011-38, FR-011-39 | E2E | baked fixture fields | Playwright |
| FR-011-40 | pipeline + web (hostile) | invalid inputs written in the test | pytest, Vitest |
| FR-011-43 | pipeline | `neuraloperator` spectral convolution with copied weights (reference implementation), when installed | pytest |
| FR-011-44 | unit (fake GPU) + gpu | the runner's fake GPU backend (lock held, hold file, OOM raised twice); expected manifest records | pytest |
| FR-011-45 | contract | manifests against `contracts/manifest.schema.json`; label strings | pytest |
| P-011-01…P-011-16 | property / metamorphic | the relations themselves, plus the references named in the spec | Hypothesis |
| NFR-011-01, NFR-011-03 | pipeline | file sizes in the budget report | pytest |
| NFR-011-02 | E2E (forced T2; T1 in the `gpu` project) | lane-measurement suite (spec 018) | Playwright |
| NFR-011-04 | unit | GPU-hours present in the training and calibration manifests | pytest |
| SC-011-01 | pipeline | report logic on fixture results that pass and fail by construction | pytest |
| SC-011-02, SC-011-05, SC-011-06 | pipeline | coverage and verdict logic on fixture trial sets (44, 45 and 46 covering of 50) | pytest |
| SC-011-03 | pipeline | report logic on fixture fields | pytest |
| SC-011-04 | pipeline | as FR-011-08 and FR-011-37 | pytest |
| DC-011-01…DC-011-04 | contract | valid and invalid example documents per schema | pytest + jsonschema |

### Threshold keys requested (`thresholds.yaml`, ratchet-only; proposed keys, pending maintainer approval)
`models.gns_repose_abs_deg_max: 1.5`, `models.gns_runout_rel_max: 0.05`, `models.fno_rel_l2_mean_max: 0.05`,
`models.dem_calibration_coverage_min: 0.90`, `models.dem_calibration_trials: 50`,
`models.surrogate_fp16_rollout_delta: { repose_deg: 0.5, runout_rel: 0.01 }`.

## Risks and complexity tracking
| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Padded neighbour layout in the live graph | WebGPU `ScatterElements(reduction)` support is unverified; the incidence-matrix fallback would need ≈ 320 MB at 2,000 particles | ScatterElements live: may silently fall back or fail; dense incidence: exceeds browser memory |
| 3 packings per held-out geometry | single chaotic rollouts make a per-geometry comparison noisy | one packing: the acceptance would partly measure packing noise |
| Seed-ensemble delta interval | the docs left the interval open; it costs 24 forward runs per trial and is honest on a linear model by construction (P-011-09) | bootstrap over full re-calibrations: ≈ 8 × the cost per trial |
| Trial-scale heaps (≤ 5,000 particles) for the coverage study | 50 trials × 2 arms at full scale would exceed the calibration budget | fewer trials: raises the false-fail probability (§7 of the spec) |
| Two FNO instances | tailings and dust fields have different inputs and outputs | one multi-task model: couples two cases' acceptance |

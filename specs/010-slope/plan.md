# Plan 010 — Slope stability and time to failure (case C1)
Spec: ./spec.md

## Summary
C1 is built on the open lane only and is part of the first vertical slice (with A1). Five components:
1. **Static stability** (`pitstudio.slope.lem`, `pitstudio.slope.pof`): deterministic slip-circle search and
   candidate-set Monte-Carlo PoF over the `minephys.geotech` per-circle functions → FR-010-01…10, P-010-01…07.
2. **Event data** (`pitstudio.slope.events`, `pitstudio.slope.snr`, `pitstudio_pipeline.slope.dewit`): seeded Voight
   events, the SNR estimator and the de Wit ingestion → FR-010-11…17, P-010-08, P-010-11.
3. **Forecasting** (`pitstudio.slope.preprocess`, `.baselines`, `.readout`; `pitstudio_pipeline.slope.{train, infer,
   export}`): one preprocessor, inverse velocity, Bayesian TTF, TCN / PatchTST / Chronos-Bolt and one read-out →
   FR-010-18…22, FR-010-29…33, P-010-09, P-010-10, P-010-12, P-010-13.
4. **Evaluation** (`pitstudio.slope.evaluate`): relative errors, acceptance, paired bootstrap into the product's
   decision rule, descriptive real event → FR-010-23…28, P-010-14, SC-010-01…03.
5. **Radar series (S4b) and recipe** (`pitstudio.slope.radar`, `studio/recipes/cases/c1.yaml`, C1 web tabs) →
   FR-010-34…42, P-010-15…17.

## Technical context
Runtime: Python 3.14 in the root environment (numpy-only C1 cores, `minephys` dependency) and in `pipeline/`
(PyTorch cu130 / cpu, ONNX Runtime 1.30, scikit-learn, pooch) · Node 24 web (spec 018 engines `geotech` and
`forecasters`) · targets: local CPU/GPU, GitHub Pages. Python tests live in `tests/<level>/`; tests that import
PyTorch, ONNX Runtime or the pySlope oracle use `pytest.importorskip` in the root job and run for real in the
`pipeline/` job (T-010-002 wires that collection). No NVIDIA proprietary runtime is used by C1.

Dependencies to resolve and lock before feature code (dependency validation, task T-010-002):

| Package | Environment | Purpose | If it does not resolve |
|---|---|---|---|
| `chronos-forecasting` 2.3.2 (Apache-2.0) | `pipeline/` | Chronos-Bolt-tiny zero-shot and fine-tuning | Chronos-Bolt arms reported "not run"; TCN and PatchTST unaffected |
| `pyslope` 1.4.0 (MIT) | oracle-only group (never a runtime dependency) | Bishop oracle (SC-010-05) | an isolated uv project on a uv-managed Python 3.12 under `tests/oracles/pyslope/`; if that also fails, committed golden files produced once by pySlope 1.4.0 with the generating script, the pySlope version and the file SHA-256 |

## Constitution check
| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | yes | Real terrain sections (3DEP, DGM1) and the real de Wit series; synthetic events are labelled "calibrated synthetic" with noise matched to the real series (FR-010-11, FR-010-12) |
| Spec before code | yes | every behaviour has an FR/P/NFR/SC/DC id; tasks name them |
| Acceptance-test-first | yes | every requirement-bearing task in `tasks.md` is a `[red]`/`[green]` pair with its own test file |
| Independent oracles | yes | pySlope (Bishop), hand calculations (Bishop worked example, Hoek–Brown table, Wilson, inverse-velocity line), closed forms (Voight integral, conjugate posterior, quadratic-slope identity), numpy percentiles on injected resamples (bootstrap), ONNX Runtime CPU vs PyTorch (export); see the test strategy |
| Determinism & explicit tolerances | yes | seeds for events, PoF, bootstrap and Bayesian draws in the recipe; tolerances justified below |
| Neutral contracts | yes | DC-010-01…05 are JSON Schema 2020-12 under `contracts/`; types generated (T-010-001) |
| Static delivery | yes | live LEM / IV / Bayes in the `geotech` worker; forecasters in ORT-web; baked FoS/PoF grids and forecasts as T0 fallback (spec 018) |
| Honesty | yes | candidate-set PoF labelled (FR-010-04); UNVERIFIED acceptance levels (FR-010-05); n = 1 rule (FR-010-26…28); "not run" paths (FR-010-14, FR-010-17, FR-010-31, FR-010-38) |
| Licence hygiene | yes | `Data.zip` never committed; derived series carry the CC BY 4.0 attribution text; Chronos weights Apache-2.0 with notice |
| Simplicity | yes | one preprocessor, one read-out and one evaluation path for all methods; no new abstraction without two users |

## Design

![Inverse-velocity time-of-failure forecast](../../docs/assets/diagrams/inverse-velocity.svg)
![Method of slices](../../docs/assets/diagrams/slope-lem-slices.svg)
![GB-InSAR geometry](../../docs/assets/diagrams/radar-gb-insar.svg)

| Component | Module (planned) | Requirements |
|---|---|---|
| Section model and guards | `src/pitstudio/slope/section.py` | FR-010-07, DC-010-01 |
| Circle search, Bishop/Spencer composition, rejection rules | `src/pitstudio/slope/lem.py` | FR-010-01, FR-010-02, FR-010-09, P-010-01…06 |
| Candidate-set PoF, Wilson interval | `src/pitstudio/slope/pof.py` | FR-010-03, FR-010-08, P-010-07 |
| Section extraction from DEMs | `pitstudio_pipeline.slope.sections` (`s10_preprocess`) | FR-010-06 |
| Voight events, strata, splits | `src/pitstudio/slope/events.py` (called by `s05_synthesize`) | FR-010-11, FR-010-16, FR-010-17 |
| SNR estimator | `src/pitstudio/slope/snr.py` | FR-010-12, P-010-11 |
| de Wit ingestion | `pitstudio_pipeline.slope.dewit` (`s00_download` entry + `s10_preprocess`) | FR-010-13, FR-010-14, FR-010-15 |
| Shared preprocessor | `src/pitstudio/slope/preprocess.py` | FR-010-18, P-010-08 |
| Baselines (inverse velocity, Bayesian TTF) | `src/pitstudio/slope/baselines.py` over `minephys.geotech` | FR-010-19, FR-010-20, P-010-12 |
| Learned forecasters | `pitstudio_pipeline.slope.models` (TCN, PatchTST), `pitstudio_pipeline.slope.chronos` | FR-010-21, FR-010-29, FR-010-33 |
| Read-out | `src/pitstudio/slope/readout.py` (mirrored by the `forecasters` worker) | FR-010-22, P-010-13 |
| Evaluation and paired comparison | `src/pitstudio/slope/evaluate.py` → product decision rule (FR-000-05) | FR-010-23…28, P-010-14 |
| Export | `pitstudio_pipeline.slope.export` (`s60_export`) | FR-010-30, FR-010-31, DC-010-05 |
| Radar series (S4b) | `src/pitstudio/slope/radar.py` over the `minephys.geotech` LOS model | FR-010-34…37, FR-010-41, FR-010-42, P-010-15…17 |
| C1 web behaviour | `web/src/cases/c1/` (tabs) on the spec 018 engines | FR-010-04, FR-010-05, FR-010-10, FR-010-27, FR-010-32, FR-010-38 |
| Recipe | `studio/recipes/cases/c1.yaml` | FR-010-39, FR-010-40 |

Data flow: `s00_download` (de Wit) → `s10_preprocess` (sections, real series, SNR_obs) → `s05_synthesize` (events at
SNR_obs) → `s30_train` → `s40_infer` (all methods on identical windows) → `s50_evaluate` (DC-010-03) → `s60_export`
(ONNX, baked FoS/PoF and forecasts, manifests) → web.

### Interfaces and their hostile-input requirements
| Interface | Kind | Hostile requirement |
|---|---|---|
| Section input (`slope-section` JSON, `analyse_section`) | file + function | FR-010-07, FR-010-09 |
| PoF function | function | FR-010-08 |
| Section editor and C1 URL query | UI control | FR-010-10 |
| de Wit archive | file input | FR-010-14 |
| Synthesizer configuration | file + function | FR-010-16, FR-010-17 |
| Forecaster context (PyTorch, ONNX, web) | function + UI | FR-010-29 |
| Evaluation / decision request | function | FR-010-28 |
| Chronos export | stage | FR-010-31 |
| Radar-series builder | function | FR-010-36, FR-010-37, FR-010-42 |
| C1 recipe | CLI (`studio plan`) | FR-010-40 |

### Numerical cores and their metamorphic relations
| Core | Relations (≥ 3) |
|---|---|
| LEM composition | P-010-01 (c′), P-010-02 (φ′, r_u), P-010-04 (similarity, unit change), P-010-05 (translation, mirror), P-010-03 and P-010-06 (identities) |
| Candidate-set PoF | P-010-07 (common-random-number monotonicity, interval containment, narrowing) + the degenerate-distribution identity of T-010-015 |
| Event generator and SNR | P-010-11 (trend invariance, scale equivariance, recovery), P-010-08 (noise-free α = 2 exactness) |
| Preprocessor + baselines + read-out | P-010-09 (time translation, time scaling), P-010-10 (displacement scaling), P-010-12 (prior limit, permutation), P-010-13 (linear-path root, order) |
| Paired evaluation | P-010-14 (swap, shift, permutation) |
| Radar series | P-010-15 (bound, parallel/perpendicular, unwrap), P-010-16 (linearity, rigid motion, sign), P-010-17 (λ/2 periodicity, λ–displacement co-scaling, pixel-set invariance) |

### Tolerances and their justification
- **rtol 1e-9 for exact identities on the LEM** (P-010-03, P-010-04): float64 slice sums over ≤ 500 slices and ≤ 100
  fixed-point iterations accumulate ≤ 500 × 100 × 2.2e-16 ≈ 1e-11 relative error; 1e-9 leaves a margin of 100 for
  conditioning of tan φ′ near 60°.
- **Translation rtol 1e-10** (P-010-05): shifting by 10⁴ m loses up to 10⁴ × 2.2e-16 / H ≈ 4e-13 m relative to a 5 m
  slope in each coordinate difference; 1e-10 covers the propagation through the iteration.
- **Slice refinement 1e-3 F** (P-010-06): the midpoint-rule slice weights have O(n⁻²) error; from 200 to 400 slices the
  change is ≤ (1/200)² × curvature factor (≤ 40 for circles with ρ ≥ 1.02) ≈ 1e-3.
- **pySlope 1 % on a fixed circle, 2 % on the searched minimum** (SC-010-05): pySlope's Bishop convergence tolerance
  defaults to 0.005 (it is set to its tightest accepted value in the test) and its slice boundaries differ from ours;
  its trial-circle generation differs from our deterministic grid, so the searched minimum differs by the grid
  resolution (the published validation against Slide and Hyrcan shows differences of the same order).
- **Inverse-velocity noise-free bias 0.2 % of lead** (P-010-08): the centred 9-point slope of
  Ω = −(1/A) ln(t_f − t) has relative error (2/τ²) δ² Σs⁴ / (6 Σs²) = 3.93 (δ/τ)² with τ the remaining time; at the
  last velocity sample of c = 0.8, τ ≥ 128 δ, so the error is ≤ 2.4e-4, and the 25 % fit window keeps the t_f error
  below 1e-3 of lead; 2e-3 adds the linear-interpolation error of resampling.
- **Learned-model invariance \|Δe\| ≤ 1e-5** (P-010-09, P-010-10): inputs are rescaled by the context's mean \|y\| in
  fp32; a forward pass of ≤ 1 M parameters in fp32 changes outputs by ≤ 1e-6 relative under an exact input rescaling,
  and the read-out maps that to ≤ 1e-5 of lead.
- **SNR recovery 15 %** (P-010-11): the MAD estimate from n − 2 correlated second differences has a relative standard
  deviation of about 1.44 / √n (3.2 % at n = 2,000, measured by a 2,000-trial simulation at specification); 15 % is
  4.7 standard deviations, so 200 examples fail by chance with probability below 1e-3, and the property test runs
  derandomised (fixed seeds) so it is deterministic.
- **Bootstrap and paired intervals: exact** (P-010-14) because the resample index matrix depends only on the seed
  and the sorted event ids.
- **Radar phase 1e-9 rad (circular difference)** (P-010-17): phases reach (4π/λ) · 10 m ≈ 2.5 × 10⁴ rad at λ = 5 mm;
  float64 rounding gives ≤ 2.5 × 10⁴ × 2.2e-16 ≈ 6e-12 rad per operation, so 1e-9 leaves a margin above 100.
  Projection atol 1e-12 m (P-010-16): a 5,000 m translation loses ≤ 5,000 × 1.1e-16 ≈ 6e-13 m per coordinate.
- **Export parity** (SC-010-04): `models.onnx_cpu_fp32` in `thresholds.yaml`; browser parity is FR-018-57.

## Test strategy
| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-010-01 | unit | hand calculation: the three-slice Bishop iteration of the M13 page (F₀ = 1 → 1.866, 2.018, 2.034, 2.035; Σ W sin α = 560.1 kN/m); exhaustive count of the search grid for a hand-drawn section | pytest |
| FR-010-02 | unit | hand calculation: Hoek–Brown table of the slopes theory page (GSI 50, m_i 10, D ∈ {0, 0.7, 1}: m_b 1.677 / 0.641 / 0.281, s 0.00387 / 0.00071 / 0.00024, a 0.506; σ1 at σ3 = 1 MPa 10.49 / 6.67 / 4.72 MPa); Balmer's parametric τ(σn) and its derivative by hand at one σ3 | pytest |
| FR-010-03 | unit + property | Wilson by hand (230 of 10,000 → 2.02 %–2.61 %); zero-variance distributions give k = N · 1[F < 1] exactly; a fake per-sample F linear in c′ gives PoF = Φ((c_crit − μ)/σ) within 3 binomial standard errors | pytest, Hypothesis |
| FR-010-04, FR-010-05, FR-010-10 | E2E (hostile for 10) | baked fixture values and labels written in the test | Playwright |
| FR-010-06 | pipeline | analytic DEM (a planar bench and face of known angle) → known profile; Douglas–Peucker on a hand-drawn polyline | pytest (pipeline env) |
| FR-010-07, FR-010-08, FR-010-09 | unit (hostile) | one case per invalid class, expected error and field written in the test | pytest |
| FR-010-11 | unit | noise-free events match the closed-form Voight integral (P-010-08 path); Kolmogorov–Smirnov of the drawn priors against their declared distributions (p > 1e-3 at fixed seeds); split seeds disjoint | pytest, scipy.stats |
| FR-010-12 | property | pure Gaussian noise of known σ; analytic trends | Hypothesis |
| FR-010-13, FR-010-14 | pipeline (hostile) | the size and MD5 published by the Zenodo record; fixture archives (a series CSV, a map stack, a `..` entry, a duplicated timestamp, no unit, no failure time) built by the test | pytest |
| FR-010-15 | contract | manifest inputs of the training, validation, C2ST and TSTR stages scanned for the de Wit digest | pytest + jsonschema |
| FR-010-16, FR-010-17 | unit (hostile) | invalid configurations written in the test; nominal-SNR labels | pytest |
| FR-010-18 | unit | the centred least-squares slope of a quadratic equals its derivative at the centre exactly; linear displacement gives a constant velocity | pytest |
| FR-010-19 | unit | the M14 worked example: 1/v = 0.5 − 0.1 t → t̂_f = 5 d; decelerating data → cap | pytest |
| FR-010-20 | unit | closed-form conjugate posterior (Σ_N, μ_N) computed by hand on a 4-point example | pytest |
| FR-010-21 | pipeline | contract checks (split membership by seed, input and output shapes from DC-010-05); pinball loss by hand on two values | pytest (pipeline env) |
| FR-010-22 | property | linear median paths (P-010-13); hand-built paths with a crossing, an extrapolation and no failure | Hypothesis |
| FR-010-23, FR-010-24 | unit | hand-computed errors and lead times on a 5-event fixture; percentiles of injected bootstrap resamples computed with numpy | pytest |
| FR-010-25, FR-010-28 | unit (hostile for 28) | mean differences and percentile bounds from injected resamples (numpy); FR-000-05 verdict table | pytest |
| FR-010-26 | unit | contract: the real-event block has no interval, rank or verdict field; order fixed | pytest + jsonschema |
| FR-010-27 | E2E | exact EN and ES strings; DOM order; no emphasis class on any row | Playwright |
| FR-010-29 | unit + E2E (hostile) | invalid contexts written in the test | pytest, Vitest |
| FR-010-30 | pipeline | ONNX Runtime CPU fp32 against PyTorch fp32 (reference implementation) on 200 golden contexts | pytest (pipeline env) |
| FR-010-31 | pipeline | fault injection: an export that raises, and one with a perturbed weight that breaks parity | pytest |
| FR-010-32 | E2E | baked forecasts of a fixture event at the grid cut-offs | Playwright |
| FR-010-33 | unit (fake GPU) + gpu | the runner's fake GPU backend raising OOM twice; expected manifest records written in the test | pytest |
| FR-010-34, FR-010-36 | unit | hand geometry: radar at (0, 0, 0), pixel at (100, 0, 0), motion (1, 0, 0) → \|d\| = 1; motion (0, 1, 0) → 0; increments of 0.24 λ and 0.26 λ; hand calculation of the Bingham 2013 worked example (50.8 mm/day at 240 scans/day → 0.21 mm/scan, no flag for λ = 17.43 mm; a daily revisit → 50.8 mm ≥ λ/4 = 4.36 mm, flagged) | pytest |
| FR-010-35 | pipeline | contract of the S4b block; ψ = 0° reproduces the full-vector series when the noise is off | pytest |
| FR-010-37 | unit (hostile) | invalid configurations written in the test | pytest |
| FR-010-41 | unit | analytical phase of a linear motion (φ = 4π v t / λ before wrapping); motion toward the radar gives d > 0; reference implementation `numpy.unwrap` on the wrapped series; noise statistics (sample σ within the 99.9 % χ² interval) | pytest |
| FR-010-42 | unit (hostile) | invalid displacement fields, scan times, λ, noise and ρ values written in the test | pytest + Hypothesis |
| FR-010-38 | E2E | fixture with and without the EGMS layer | Playwright |
| FR-010-39 | pipeline + contract | manifests validated against `contracts/manifest.schema.json`; CPU run on samples | pytest |
| FR-010-40 | unit (hostile) | invalid recipes written in the test | pytest |
| P-010-01…P-010-07 | metamorphic / property | the relations themselves (no absolute oracle needed) | Hypothesis |
| P-010-08 | property | closed-form Voight α = 2 series and the bias bound above | Hypothesis |
| P-010-09, P-010-10 | metamorphic | invariance relations; learned models with fixed random weights | Hypothesis |
| P-010-11…P-010-17 | property / metamorphic | as stated in the spec | Hypothesis |
| NFR-010-01…03, NFR-010-05 | E2E (CI, forced T2) | lane-measurement suite of spec 018 (DC-018-06) | Playwright |
| NFR-010-04 | pipeline | file sizes in the budget report | pytest |
| NFR-010-06 | unit | manifest of each training stage carries GPU-hours | pytest |
| SC-010-01 | pipeline | report logic on fixture results that pass and fail by construction | pytest |
| SC-010-02 | unit | as FR-010-25 | pytest |
| SC-010-03 | unit + E2E | as FR-010-26 and FR-010-27 | pytest, Playwright |
| SC-010-04 | pipeline | as FR-010-30 | pytest |
| SC-010-05 | pipeline (oracle env) | pySlope 1.4.0 `add_single_circular_plane` on the same circle, and `get_min_FOS` on planar cases (20 m, 45°, γ 20 kN/m³, c′ 20 kPa, φ′ 30°, dry, and 4 more) | pytest |
| DC-010-01…DC-010-04 | contract | valid and invalid example documents per schema | pytest + jsonschema |
| DC-010-05 | contract | the exported IO description validates against `surrogate-io.schema.json` | pytest + jsonschema |

### Threshold keys (`thresholds.yaml`, ratchet-only)
`models.slope_ttf_rel_error_median_max: 0.10`, `models.slope_bootstrap_resamples: 10000`,
`models.slope_pyslope_fixed_circle_rtol: 0.01`, `models.slope_pyslope_search_rtol: 0.02`.

## Risks and complexity tracking
| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Candidate-set PoF (K = 64 live) | a full search per sample is 12,800 × 2,000 circle solves, far beyond the 1 s live gate | full-search PoF live: misses the gate; fixed single surface: underestimates PoF more and hides it |
| pySlope in an oracle-only environment | its runtime dependencies (django, psycopg2-binary, kaleido 0.2.1) do not belong in a product lock | dropping the oracle: the plan names pySlope; hand calculations alone do not cover the search |
| Two Chronos-Bolt arms (zero-shot and fine-tuned) | the method page names both uses | one arm: hides whether fine-tuning matters |
| Horizon-cap scoring of "no failure predicted" | keeps every event in the paired comparison | dropping such events: biases the comparison towards methods that abstain |

# Spec 010 — Slope stability and time to failure (case C1)
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent

Case C1 asks two questions about a pit wall. Before it moves: what are its factor of safety (FoS) and probability of
failure (PoF)? Once slope radar shows it accelerating: when will it fail, and how much warning is there? This spec fixes
the PitStudio side of methods M13 and M14 and of the analytical slope radar (sensor S4b of M23): the C1 slope sections
cut from real terrain, the deterministic slip-circle search and the Monte-Carlo PoF built on the `minephys.geotech`
reference functions (Bishop, Spencer, generalised Hoek–Brown, inverse velocity, Bayesian time to failure, Voight
creep, line-of-sight model), the seeded synthetic Voight event set with noise matched to the observed signal-to-noise
ratio of the one real failure series (de Wit, CC BY 4.0), the learned forecasters (TCN, PatchTST, Chronos-Bolt-tiny)
with one pre-registered time-to-failure (TTF) read-out, their evaluation under the decision rule FR-000-05 on seeded
events and the strictly descriptive evaluation of the single real event, the export of the forecasters, the
line-of-sight radar series of the C1 wall, and the C1-specific behaviour of the web workbench.

Geotechnical engineers, data/AI practitioners, students and reviewers benefit: every FoS, PoF and TTF number is
reproducible from a recipe, every "better than" claim is decided by a paired interval over seeded events, and the one
real event is never presented as evidence of skill. It inherits FR-000-05 (decision rule), FR-000-09 (synthetic
labels), FR-000-10 (sources and UNVERIFIED flags) and FR-000-14 (manifests).

**Out of scope:** the numerics of the `minephys.geotech` functions themselves (specified and tested in the `minephys`
repository's own specs); finite-element strength reduction; 3-D, kinematic or structurally controlled failures;
the generic web engine host, tiers and browser parity classes (spec 018-web-cases, engine `geotech` and
`forecasters`); the shared decision-rule display (spec 020-web-knowledge); the generic `s00_download` machinery and
data registry (spec 008-data-pipeline); the ONNX export gates and TensorRT bench in general (spec
016-export-acceleration); the RTX sensors S1–S4a and their lane (spec 013-sensors; the S4b slope-radar series is
specified here).
**Educational, not design or regulatory software; not a monitoring or alarm system.**

## 2. User stories

### US-010-1 (P1) Wall stability in the browser
As a geotechnical engineer, I want to edit a C1 section (geometry, strength, water) and see the Bishop and Spencer
factors of safety and a Monte-Carlo probability of failure with its interval, so that I can reason about a wall with
sourced methods. Independent test: open `/cases/C1/?tab=simulate`, raise c′ and check that FoS rises and that the
values equal the baked Python reference for the same section.

### US-010-2 (P1) Learned forecasters against inverse velocity on seeded events
As a data/AI practitioner, I want TCN, PatchTST and Chronos-Bolt-tiny compared with inverse velocity on many seeded
Voight events at the observed signal-to-noise ratio, with a paired interval per model and cut-off, so that "better than
inverse velocity" is claimed only when the data support it. Independent test: run `s50_evaluate` on a fixture set of
event errors and compare the interval and verdict with a hand-computed bootstrap.

### US-010-3 (P1) One real event, stated honestly
As a reviewer, I want the de Wit failure shown at the 50 % and 80 % record cut-offs with each method's TTF error and the
label "single real event — no significance test", with no interval and no ranking, so that one anecdote is not read as
evidence. Independent test: build the C1 baked data and assert the label, the fixed method order and the absence of any
interval or verdict field for the real event.

### US-010-4 (P2) The radar sees only its line of sight
As a student, I want to place the slope radar at different angles to the moving wall and see the line-of-sight
displacement map and how the forecast error grows as the angle grows, so that I understand why radar siting matters.
Independent test: generate LOS series for ψ = 0°, 45° and 70° from one event and check the projection and wrapping
rules by hand.

### US-010-5 (P1) Reproduce C1 on the open lane
As a developer, I want the C1 recipe to run end to end without any NVIDIA proprietary runtime and to write a manifest
for every artefact, so that C1 can be the first vertical slice and anyone can rebuild it. Independent test: plan the
recipe with the `linux-gpu` profile against the fake GPU backend, and run its CPU stages on the sample data.

Story index (for traceability):

| Story | Title | Priority |
|---|---|---|
| US-010-1 | Wall stability in the browser | P1 |
| US-010-2 | Learned forecasters against inverse velocity on seeded events | P1 |
| US-010-3 | One real event, stated honestly | P1 |
| US-010-4 | The radar sees only its line of sight | P2 |
| US-010-5 | Reproduce C1 on the open lane | P1 |

## 3. Functional requirements (EARS)

Units throughout: lengths m, stresses kPa (σci in MPa), angles in degrees at interfaces, time h, displacement mm.
Fixed parameters referred to as "§7" are in the parameter table of section 7.

### 3.1 Static stability (M13)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-010-01 | Ubiquitous | The C1 analysis shall compute, for a section valid against `slope-section.schema.json`, the minimum factor of safety over the deterministic slip-circle search of §7 (entry × exit × radius-ratio grid, ≤ 12,800 circles) by Bishop's simplified method, and Spencer's factor and interslice angle θ on the 64 lowest-Bishop circles (live) or on every circle (baked), using the `minephys.geotech` per-circle functions with n_s equal-width slices (50 live, 200 baked), and shall return F, the critical circle (centre, radius, entry and exit x), the iteration count and the number of rejected circles. | unit |
| FR-010-02 | Ubiquitous | For every material given by generalised Hoek–Brown inputs (GSI, m_i, σci, D), the C1 analysis shall convert it on every slice to the instantaneous Mohr–Coulomb pair (c′, φ′) at the slice-base effective normal stress (Balmer's parametric form, as implemented by `minephys.geotech`), re-evaluated at every fixed-point iteration, and shall stop when \|F_{k+1} − F_k\| ≤ 1e-9 or after 100 iterations. | unit |
| FR-010-03 | Ubiquitous | The PoF function shall draw N samples (default 2,000 live, 20,000 baked) of the declared independent input distributions (normal truncated by inverse CDF, never by rejection; lognormal; uniform), take for each sample the minimum F over the candidate set (the K lowest-F circles of the mean-parameter Bishop search; K = 64 live, 1,024 baked), and shall return k (samples with F < 1), PoF = k/N and its Wilson 95 % interval (z = 1.96). The generator is the product's seeded numpy `PCG64` through `SeedSequence`, mirrored in the browser by spec 018 (P-018-04). | unit |
| FR-010-04 | Event | When the web app shows a live PoF, it shall label it "PoF over the 64 most critical surfaces of the mean case", and shall show next to it, where one exists for the same section, the baked K = 1,024 PoF with its interval and the difference of the two. | E2E |
| FR-010-05 | Ubiquitous | The C1 workbench shall present FoS and PoF acceptance levels (bench, inter-ramp, overall) only as configurable inputs carrying the UNVERIFIED flag of their knowledge-table rows, never as defaults stated as facts, and shall show "Educational, not design software" next to every FoS and PoF. | E2E |
| FR-010-06 | Ubiquitous | The section extractor (`s10_preprocess`) shall cut at least 3 reference sections per site from the Bingham 3DEP 2018 DEM and the Hambach DGM1, each a ground profile sampled at 1 m along a line perpendicular to the wall and simplified by Douglas–Peucker with tolerance 0.25 m, and shall record the DEM SHA-256, the profile end coordinates and the provisional site label of the Bingham dataset card in the manifest. | pipeline |
| FR-010-07 | Unwanted | If a section has a non-finite coordinate or parameter, fewer than 2 ground vertices, non-increasing ground x, a slope height ≤ 0, a unit weight ≤ 0 or > 40 kN/m³, c′ < 0, φ′ outside [0°, 60°], r_u outside [0, 1), GSI outside [0, 100], m_i ≤ 0, σci ≤ 0, D outside [0, 1], an unknown method or material-model enum, n_s outside [10, 500], more than 10⁵ trial circles, or fails `slope-section.schema.json`, then the C1 analysis shall raise `InvalidSectionError` naming the field and its valid range and shall return no FoS. | unit (hostile) |
| FR-010-08 | Unwanted | If N ≤ 0 or N > 10⁶, a scale parameter is ≤ 0 or non-finite, a truncation interval is empty, K is outside [1, number of valid circles], or the seed is not an integer in [0, 2⁶⁴), then the PoF function shall raise `InvalidSamplingError` before drawing any sample. | unit (hostile) |
| FR-010-09 | Unwanted | If, for a trial circle, the Bishop or Spencer iteration does not converge within 100 iterations, m_α ≤ 0.2 on any slice, no θ in (−90°, 90°) equalises Spencer's force and moment factors, or the sliding mass is empty, then the C1 analysis shall exclude that circle from the minimum and count it in `rejected_circles`; if every circle is rejected it shall return the result "no valid slip surface" with no FoS. | unit (hostile) |
| FR-010-10 | Unwanted | If a section-editor control or the C1 URL query carries a value outside the ranges of FR-010-07 (the web engine further caps n_s ≤ 200 and N ≤ 10⁵, spec 018 engine `geotech`), then the C1 workbench shall keep the last valid section, show the control's valid range and unit, and send no request to the worker (FR-018-41). | E2E (hostile) |

### 3.2 Synthetic events and the real series

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-010-11 | Ubiquitous | The event synthesizer (`s05_synthesize`) shall generate seeded Voight events with the parameter priors of §7 (α, terminal duration, onset velocity, steady pre-onset phase, regressive episode in 20 % of events, line-of-sight factor cos ψ, white measurement noise with σ_d = cos ψ · ΔΩ / SNR_target, optional AR(1) atmospheric term), each recorded per `displacement-series.schema.json` with its exact t_f, seed, parameters, stratum and realised SNR, and shall split by event seed into 20,000 training, 1,000 validation and, per stratum (SNR_obs, 0.5 × SNR_obs, 2 × SNR_obs, SNR_obs + atmospheric), 500 test events. | pipeline |
| FR-010-12 | Ubiquitous | The SNR estimator shall return SNR = (Ω(t_end) − Ω(t_0)) / σ̂_d with σ̂_d = 1.4826 · MAD(Δ²Ω) / √6 over the record (Δ² the second difference of consecutive samples), and the C1 recipe shall define SNR_obs as this estimator on the de Wit series between t_0 and t_f, recorded in the manifest. | unit |
| FR-010-13 | Ubiquitous | The de Wit ingestion (`s00_download` → `s10_preprocess`) shall accept only the Zenodo record 15003054 archive `Data.zip` of 8,943,265 bytes with MD5 3adeb6c853d2e87249b7d3549a2a00ca (SHA-256 pinned at first download), shall extract the radar-derived surface-deformation series as delivered or, when delivered as maps, as the per-epoch median over the pixels in the top 5 % of final cumulative displacement, and shall record units, sampling interval, t_0, t_f with its documentary source, and the attribution text of the dataset card verbatim. | pipeline |
| FR-010-14 | Unwanted | If the archive fails its checksum, contains an entry with an absolute path, a drive letter or a `..` component, yields non-monotonic or duplicate timestamps, lacks a displacement unit, or states no failure time, then `s10_preprocess` shall reject it with the reason, and the C1 real-event panel shall show "Not run — <reason>" and no TTF number. | pipeline (hostile) |
| FR-010-15 | Ubiquitous | The training, validation and model-selection inputs of every C1 forecaster, and every classifier two-sample test or TSTR input of the product, shall exclude the de Wit-derived series: no such manifest lists its SHA-256 among its inputs. | contract |
| FR-010-16 | Unwanted | If a synthesizer configuration has α ≤ 1, a terminal duration ≤ 0, SNR_target ≤ 0 or non-finite, ψ outside [0°, 89°], fewer than 64 or more than 10⁶ samples per event, overlapping split seeds, or an unknown key, then `s05_synthesize` shall reject the configuration before generating any event. | unit (hostile) |
| FR-010-17 | Unwanted | If SNR_obs is unavailable (the real series was not ingested), then the synthesizer shall generate the strata at the nominal SNR grid {10, 30, 100} labelled "observed SNR not available — nominal SNR", and SC-010-01 shall be reported "not run (observed SNR unavailable)". | pipeline |

### 3.3 Forecasting and evaluation (M14)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-010-18 | Ubiquitous | Every method shall receive the same observed window [t_0, t_c] processed by one shared preprocessor: displacement resampled to L = 512 uniform samples (step δ = (t_c − t_0)/511) by linear interpolation; velocity v_k = least-squares slope over 9 consecutive samples assigned to the centre time; y_k = 1/v_k where v_k > 0, masked otherwise. | unit |
| FR-010-19 | Ubiquitous | The inverse-velocity baseline shall fit y = β₀ + β₁ t by ordinary least squares over the last 25 % of unmasked samples (at least 10) and return t̂_f = −β₀/β₁ when β₁ < 0, otherwise "no failure predicted", scored at the horizon cap t_c + 1,024 δ. | unit |
| FR-010-20 | Ubiquitous | The Bayesian TTF baseline shall, on the same points in standardised coordinates, form the conjugate posterior with prior N(0, 10² I) and σ² from the least-squares residuals, draw M = 4,000 seeded posterior samples, keep those with β₁ < 0, and return the median and the 10 % and 90 % quantiles of t_f = −β₀/β₁ in original units; when fewer than half the draws have β₁ < 0 it shall return "no failure predicted", scored at the horizon cap. | unit |
| FR-010-21 | Ubiquitous | TCN, PatchTST (patch 16, stride 8) and Chronos-Bolt-tiny (zero-shot and fine-tuned arms) shall map a context of 128 values of y (block means of 4 consecutive preprocessed values, masked values forward-filled, scaled by the context's mean \|y\|; a mask channel for TCN and PatchTST) to the quantiles 0.1, 0.2, …, 0.9 of the next 64 steps of 4δ, extend the forecast by feeding back the median up to 4 blocks (the cap of 1,024 δ), be trained with the pinball loss on the training split only, and have every hyper-parameter chosen on the validation split only. | pipeline |
| FR-010-22 | Ubiquitous | The TTF read-out shall be the same for every learned model: t̂_f is the first time the median path reaches y ≤ 0, linearly interpolated between the last positive and the first non-positive step; if no step reaches 0, a least-squares line through the last 16 median steps is extrapolated when its slope is negative and its root lies within the cap; otherwise "no failure predicted", scored at the cap; the 80 % TTF interval is read from the 0.1 and 0.9 paths by the same rule. | unit |
| FR-010-23 | Ubiquitous | `s50_evaluate` shall compute, for every test event, method and pre-registered cut-off c ∈ {0.5, 0.8}, the relative TTF error e = \|t̂_f − t_f\| / (t_f − t_c) (with t_c = t_0 + c (t_f − t_0)), and shall report per method and stratum the median, mean and 90th percentile of e, the error in h, and the lead time at alarm (first cut-off on the 1 % grid from 0.30 to 0.99 at which a failure is predicted with t̂_f − t_c ≤ T_alarm, default 24 h, configurable) with the fraction of events never alarmed. | pipeline |
| FR-010-24 | Ubiquitous | `s50_evaluate` shall state SC-010-01 per learned model and cut-off from the median e over the 500 test events of the SNR_obs stratum, with its percentile-bootstrap 95 % interval (B = 10,000, seed in the recipe). | pipeline |
| FR-010-25 | Ubiquitous | For each learned model and cut-off, `s50_evaluate` shall form the paired differences d_i = e_i(inverse velocity) − e_i(model) over the SNR_obs test events (pairing by event id), compute the 95 % interval of the mean d by paired percentile bootstrap (B = 10,000, resampling sorted event ids, seed in the recipe), and shall pass it to the product's decision rule (FR-000-05), so that a model is "better than inverse velocity" only if the lower bound is > 0; the report shall state that 8 such comparisons are made (4 learned arms × 2 cut-offs) and that no family-wise claim is made. | pipeline |
| FR-010-26 | Ubiquitous | For the real event, `s50_evaluate` shall report, at c ∈ {0.5, 0.8}, each method's t̂_f, the signed error t̂_f − t_f (h) and its ratio to t_f − t_c, with no interval, no ranking and no verdict, in the fixed order inverse velocity, Bayesian TTF, TCN, PatchTST, Chronos-Bolt (zero-shot), Chronos-Bolt (fine-tuned), together with SNR_obs. | pipeline |
| FR-010-27 | Ubiquitous | The C1 Charts tab shall show the real-event table of FR-010-26 in its fixed order, with no highlighting of any method, under the label "single real event — no significance test" (Spanish: "evento real único — sin prueba de significancia"), next to the synthetic results with their intervals and verdicts. | E2E |
| FR-010-28 | Unwanted | If a confidence interval, a ranking or a verdict is requested for fewer than 2 paired units, or for two methods whose event ids differ, then the evaluation shall return the verdict "single real event — no significance test" for one unit, and raise `InsufficientPairsError` for none or `UnpairedError` for mismatched ids, and shall never return an interval. | unit (hostile) |
| FR-010-29 | Unwanted | If a forecaster (PyTorch, ONNX Runtime or the web engine `forecasters`) receives a context whose length is not 128, whose shape or dtype differs from `surrogate-io.schema.json`, that contains a non-finite value after preprocessing, or that has no positive velocity at all, then it shall return "no forecast — <reason>" in the web app or raise `InvalidWindowError` in Python, and never a TTF. | unit + E2E (hostile) |
| FR-010-30 | Ubiquitous | `s60_export` shall export the forecasting graph of TCN, PatchTST and the fine-tuned Chronos-Bolt-tiny (one 64-step block, quantiles as output; the zero-shot arm is published as baked forecasts only) at opset 17 with IR version 10 by the dynamo exporter with verification, and shall check ONNX Runtime CPU fp32 against PyTorch fp32 on ≥ 200 golden contexts with `models.onnx_cpu_fp32` (rtol 1e-3, atol 1e-5, max abs 1e-4). | pipeline |
| FR-010-31 | Unwanted | If the Chronos-Bolt export fails or misses its parity, then `s60_export` shall mark Chronos-Bolt PRECOMPUTE, bake its forecasts for every published event and for the cut-off grid, keep TCN and PatchTST live, and the model card and the C1 page shall state the reason. | pipeline |
| FR-010-32 | Event | When the visitor moves the C1 cut-off slider (0.30–0.95 of the record, step 0.01), the workbench shall refit inverse velocity and the Bayesian band live, and shall update each learned forecast live or, for a PRECOMPUTE model, show the baked forecast of the nearest grid cut-off with that cut-off printed. | E2E |
| FR-010-33 | Optional | Where a CUDA GPU is available, forecaster training shall run only through the runner under `gpu0.compute`, honour `gpu0.hold`, use bf16 autocast for PatchTST and Chronos-Bolt, and on out-of-memory apply the declared fallback (batch halved, at most twice) recorded in the manifest; without a GPU it shall train on the CPU and record that. These behaviours shall be verified against the fake GPU backend. | unit (fake GPU) + gpu |

### 3.4 Slope radar series (S4b) and the C1 recipe

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-010-34 | Ubiquitous | The radar-series builder shall, for the C1 wall sector, scale an event's displacement by a Gaussian spatial weight (peak 1, σ_w = 30 m) along each facet's down-dip unit vector, project it with the `minephys.geotech` line-of-sight model onto the unit vector from the radar position to each pixel, add noise at SNR_obs, wrap the phase at wavelength λ and scan interval Δt_scan, unwrap it in time, and write per-pixel LOS series and a LOS-displacement map per `displacement-series.schema.json`. | unit |
| FR-010-35 | Ubiquitous | `s50_evaluate` shall report the S4b result: for radar positions with ψ = 0°, 45° and 70° at the peak pixel, the median relative TTF error of every method on the LOS series of the 500 SNR_obs test events at c ∈ {0.5, 0.8}, next to the same methods on the noise-free full-vector series; no threshold applies. | pipeline |
| FR-010-36 | Unwanted | If a pixel's LOS increment between consecutive scans reaches λ/4, then the builder shall mark that pixel's series "ambiguous (phase wrapping)" from that scan on, exclude it from TTF evaluation and count it in the manifest. | unit |
| FR-010-37 | Unwanted | If the radar position is within 1e-6 m of a pixel, λ or Δt_scan is ≤ 0 or non-finite, the pixel set is empty or larger than 10⁶, or a facet normal has zero length, then the builder shall raise `InvalidRadarConfigError` before projecting. | unit (hostile) |
| FR-010-41 | Ubiquitous | The radar-series builder shall report line-of-sight displacement with the sign "positive = toward the radar" (d = −u · ê, with ê the unit vector from the radar position to the pixel), compute the wrapped phase φ(t) = wrap₍₋π,π₎[(4π/λ) · (d(t) − d(t₀) + n(t))], where n is the noise of FR-010-34 (white at SNR_obs, plus the AR(1) term in the atmospheric stratum) drawn from a counter-based generator keyed by (run seed, pixel id, scan index), and the measured series d̂(t) = (λ/4π) · unwrap(φ)(t) with `numpy.unwrap` semantics along time, and shall keep d(t), d̂(t) and the wrap flags of FR-010-36 in each pixel's series record. | unit (analytical + reference implementation) |
| FR-010-42 | Unwanted | If the displacement field passed to the radar-series builder contains a NaN or infinite value, the scan times are not strictly increasing, λ is outside (1 mm, 1 m), a noise standard deviation is negative or non-finite, or the AR(1) coefficient has \|ρ\| ≥ 1, then the builder shall raise `InvalidRadarConfigError` naming the input and write no series. | unit (hostile) |
| FR-010-38 | Optional | Where EGMS-derived summaries over Hambach are present, the C1 Scene tab shall show them labelled "derived-only (EGMS)" with their attribution; otherwise the layer shall show "Not run — EGMS access not set up", and no C1 KPI shall depend on it. | E2E |
| FR-010-39 | Ubiquitous | The recipe `studio/recipes/cases/c1.yaml` shall run end to end on the open lane (no NVIDIA proprietary runtime), producing manifests (DC-000-01) for sections, FoS/PoF tables, event sets, forecasts, metrics and ONNX files, each naming its producer tool, measured lane, licence class and input SHA-256 digests. | pipeline + contract |
| FR-010-40 | Unwanted | If the C1 recipe names an unknown method, model or stratum, a cut-off outside (0, 1), duplicate cut-offs, or a test seed range overlapping the training range, then `studio plan` shall reject it with a schema error before any stage runs. | unit (hostile) |

## 4. Correctness properties

Properties on the Python reference path (PitStudio code composed with `minephys.geotech`); the browser twins carry
their own properties in spec 018. Examples per property test: `property_tests.ci_examples_per_test` (200 in CI).

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-010-01 | For any valid section, the minimum F (Bishop and Spencer) is non-decreasing in c′. | Hypothesis sections: H ∈ [5, 200] m, face 20°–80°, γ ∈ [16, 28] kN/m³, c′ ∈ [0, 200] kPa, φ′ ∈ [5°, 50°], r_u ∈ [0, 0.5] | F(c′+Δ) ≥ F(c′) − 1e-12 F |
| P-010-02 | For any valid section, the minimum F is non-decreasing in φ′ and non-increasing in r_u. | as P-010-01 | ± 1e-12 F |
| P-010-03 | On any fixed circle, Spencer's moment-equilibrium factor evaluated at θ = 0 equals Bishop's F. | as P-010-01, fixed circles | rtol 1e-9 |
| P-010-04 | Similarity: scaling every length by k and c′ by k (γ, φ′, r_u fixed) leaves F unchanged; converting the section to ft, psf and pcf leaves F unchanged. | k ∈ [0.1, 10] | rtol 1e-9 |
| P-010-05 | Translating the section by (Δx, Δz) leaves F unchanged; mirroring a left-facing section into a right-facing one leaves F unchanged and mirrors the critical circle. | \|Δ\| ≤ 10⁴ m | rtol 1e-10 |
| P-010-06 | Slice refinement on a fixed circle: \|F(400 slices) − F(200 slices)\| ≤ 1e-3 F. | as P-010-01 | stated |
| P-010-07 | With common random numbers (same seed, same N), raising every sample's c′ by Δ > 0 never increases k; the Wilson interval contains k/N, lies in [0, 1], and narrows when N grows at fixed k/N. | N ∈ [10, 10⁵], k ∈ [0, N] | exact |
| P-010-08 | For any noise-free, pure terminal-stage α = 2 event (no steady phase, no regressive episode), the shared preprocessor plus inverse velocity returns t_f within 0.2 % of the lead time at c ∈ {0.5, 0.8}. | A and t_f from the §7 priors, α = 2, n_obs ∈ [1,000, 10⁴] | e ≤ 0.002 |
| P-010-09 | Time translation: adding Δ to every timestamp shifts t̂_f by Δ for every method; scaling every timestamp about t_0 by k > 0 leaves e unchanged. | Δ ∈ [−10⁶, 10⁶] h; k ∈ [0.01, 100] | IV, Bayes: rtol 1e-9 of record span; learned: \|Δe\| ≤ 1e-5 |
| P-010-10 | Displacement scaling: multiplying every displacement by k > 0 leaves t̂_f unchanged for every method. | k ∈ [10⁻³, 10³] | IV, Bayes: rtol 1e-9; learned: \|Δe\| ≤ 1e-5 |
| P-010-11 | SNR estimator: σ̂_d is unchanged by adding a + b t to the series, is multiplied by k when the series is, and recovers σ of pure Gaussian noise. | n ∈ [2,000, 10⁵]; σ ∈ [10⁻³, 10³] | invariance rtol 1e-9; recovery within 15 % |
| P-010-12 | Bayesian TTF: the posterior mean and covariance equal the closed-form conjugate update; with prior variance 10⁸ the posterior mean equals the OLS coefficients; permuting the observations leaves the posterior unchanged. | 4–500 points, standardised | rtol 1e-6 (OLS limit); 1e-12 (closed form, permutation) |
| P-010-13 | Read-out: for a median path exactly linear, y = a − b s with a, b > 0, the read-out returns s = a/b whether the root lies inside the forecast or is extrapolated; raising the median path by any c > 0 never lowers t̂_f. | a, b log-uniform in [10⁻³, 10³] | rtol 1e-12; exact (order) |
| P-010-14 | Decision interval: swapping the two methods negates the interval; adding κ to every model error shifts it by −κ; permuting the event order leaves it unchanged. | 2–2,000 pairs, fixed bootstrap seed | exact |
| P-010-15 | LOS builder: \|d_LOS\| ≤ \|u\| for every pixel; motion along the LOS is fully seen and motion perpendicular to it gives 0; unwrapping the wrapped phase returns d_LOS when every scan increment is below λ/4. | random walls, radar positions, λ ∈ [1, 100] mm | rtol 1e-12; atol 1e-12 \|u\|; unwrap atol 1e-9 λ |
| P-010-16 | LOS projection: d is linear in u (d(a u₁ + b u₂) = a d(u₁) + b d(u₂)); a common rigid motion (rotation and translation) of radar and wall leaves d unchanged; a pixel moving straight toward the radar by s gives d = +s (sign convention of FR-010-41). | ‖u‖ ≤ 10 m; radar 50–5,000 m from the pixels; a, b ∈ [−10, 10] | atol 1e-12 m |
| P-010-17 | Phase: adding λ/2 to d(t) − d(t₀) at every scan leaves φ unchanged; scaling λ and the displacement field by the same k > 0 (SNR fixed, so the noise scales with it) leaves φ unchanged; a pixel's noise and phase series are unchanged when other pixels are added, removed or reordered. | λ ∈ [5, 50] mm; series of 2–10⁴ scans; k ∈ [0.1, 10]; pixel sets of 1–10³ | circular difference ≤ 1e-9 rad; exact (pixel-set invariance) |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-010-01 | One live section solve (Bishop search of ≤ 12,800 circles × 50 slices, Spencer on 64 circles) on T2 | ≤ 50 ms median of 20 runs (lane estimate) | lane-measurement suite (spec 018) |
| NFR-010-02 | One live PoF (N = 2,000, K = 64) on T2 | ≤ 1 s median of 5 runs | lane-measurement suite (spec 018) |
| NFR-010-03 | Inverse-velocity and Bayesian refit after a slider move on T2 | ≤ 16 ms p95 over 50 moves | lane-measurement suite (spec 018) |
| NFR-010-04 | Exported forecaster sizes | TCN and PatchTST < 4 × 10⁶ bytes each; Chronos-Bolt-tiny ≤ 25 × 10⁶ bytes (≈ 18 MB fp16 expected) | `s60_export` budget report (spec 016) |
| NFR-010-05 | Live TTF read-out (≤ 4 blocks) per learned model on T2 | ≤ 1 s, otherwise the model's lane is PRECOMPUTE (FR-000-15) | lane-measurement suite (spec 018) |
| NFR-010-06 | Forecaster training budget | ≤ 2 GPU-h in total (estimate); the measured value is recorded in the manifests and an overrun is stated in the card | run manifests |
| SC-010-01 | Synthetic (many seeded Voight events): TTF error ≤ 10 % of lead time at the observed SNR | median e ≤ 0.10 over the 500 SNR_obs test events at both c = 0.5 and c = 0.8, for each learned arm separately (TCN, PatchTST, Chronos-Bolt zero-shot, Chronos-Bolt fine-tuned; interval reported) | `s50_evaluate` report (FR-010-24) |
| SC-010-02 | "Better than inverse velocity" only by the decision rule (pairs = seeded events) | stated only when the FR-010-25 interval lies above 0; otherwise "no significant difference" (or "worse") | `s50_evaluate` report + C1 baked data |
| SC-010-03 | Real de Wit series = one event (n = 1) | TTF error at the 50 % and 80 % record cut-offs reported descriptively, no "better than" claim; the UI says "single real event — no significance test" | `s50_evaluate` report + E2E (FR-010-26, FR-010-27) |
| SC-010-04 | Export parity of every exported forecaster | fp32 rtol 1e-3, atol 1e-5, max abs 1e-4 (`models.onnx_cpu_fp32`) | `s60_export` parity report |
| SC-010-05 | Bishop agreement with the pySlope 1.4.0 oracle on the shared planar cases | fixed circle, 200 slices: \|ΔF\| ≤ 0.01 F; searched minimum: \|ΔF\| ≤ 0.02 F | oracle test (T-010-012) |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-010-01 | C1 slope section: ground polyline, materials (Mohr–Coulomb or Hoek–Brown), pore-pressure ratio, input distributions, search and slice settings, method enum, source DEM digest | `contracts/slope-section.schema.json` (new, T-010-001) | `s10_preprocess`, web section editor → C1 analysis, web engine `geotech` |
| DC-010-02 | Displacement series: event id, real / synthetic, stratum, seed, parameters, t (h), LOS displacement (mm), t_0, t_f and its source, SNR, sampling, attribution, pixel id and wrap flags for radar series | `contracts/displacement-series.schema.json` (new, T-010-001) | `s05_synthesize`, `s10_preprocess` (de Wit), radar-series builder → `s30_train`, `s40_infer`, `s50_evaluate`, web |
| DC-010-03 | TTF results: per event × method × cut-off: t̂_f, 80 % interval, e, error (h), lead time; per comparison: interval, method, B, seed, verdict; the real-event block with no interval field | `contracts/ttf-results.schema.json` (new, T-010-001) | `s50_evaluate` → `s60_export`, C1 Charts, model card |
| DC-010-04 | FoS / PoF tables: section id, method, F, critical circle, rejected circles, k, N, K, PoF, Wilson interval | `contracts/slope-results.schema.json` (new, T-010-001) | C1 analysis (baked) → web, docs results |
| DC-010-05 | Forecaster ONNX input/output description (names, shapes, dtypes, quantile order, scaling rule, opset) | `contracts/surrogate-io.schema.json` (new, defined in spec 011, DC-011-02) | `s60_export` → web engine `forecasters` |

Every artefact is also described by its manifest entry (DC-000-01, `contracts/manifest.schema.json`).

## 7. Edge cases and assumptions

### Parameter table (pre-registered)

| Item | Value |
|---|---|
| Slip-circle search | slope faces +x; entry x: 40 points uniform on [x_crest − 2H, x_crest + 0.5 (x_toe − x_crest)]; exit x: 40 points uniform on [x_crest + 0.5 (x_toe − x_crest), x_toe + H]; radius = ρ × half-chord, ρ ∈ 8 values geometrically spaced in [1.02, 4], centre above the chord; pairs with exit ≤ entry dropped |
| Slices | 50 (live), 200 (baked, pySlope comparisons); equal width over the horizontal extent of the sliding mass |
| Monte Carlo | live N = 2,000, K = 64; baked N = 20,000, K = 1,024; default distributions in the section editor: c′ ~ N(μ, 0.2 μ) truncated at 0; φ′ ~ N(μ, 3°) truncated to [5°, 60°]; GSI ~ N(μ, 5) truncated to [10, 100]; σci lognormal with CV 0.3; inputs independent unless the section states a correlation |
| Voight priors | α ~ U[1.7, 2.3]; terminal duration t_f − t_onset log-uniform in [24, 720] h; onset velocity log-uniform in [0.1, 10] mm/day, A set to match it; steady pre-onset phase U[0.1, 0.5] × terminal duration at the onset velocity (so the terminal stage always starts before 33 % of the record and every pre-registered cut-off observes it); regressive episode (velocity reduced by U[30 %, 70 %] over U[5 %, 15 %] of the record, pre-onset only) in 20 % of events; ψ ~ U[0°, 60°] |
| Sampling and noise | record from t_0 to t_f with n_obs samples (from the de Wit series; 2,000 if unavailable); white Gaussian noise σ_d = cos ψ · ΔΩ / SNR_target; atmospheric stratum adds AR(1) noise with lag-1 correlation 0.9 and marginal sd σ_d |
| Forecasting grid | L = 512 resampled points; velocity window 9 (centred); IV window last 25 % (≥ 10 points); learned context 128 (block means of 4); block 64 steps of 4δ; cap 1,024 δ (4 blocks); quantiles 0.1–0.9 |
| Evaluation | cut-offs c ∈ {0.5, 0.8}; alarm grid 0.30–0.99 step 0.01; T_alarm 24 h (configurable); bootstrap B = 10,000; Bayesian draws M = 4,000 |
| Radar (S4b) | ψ ∈ {0°, 45°, 70°} at the peak pixel; Δt_scan = 6 min; λ configurable, default 17.4 mm (illustrative Ku-band value, UNVERIFIED; no test depends on it) |

### Edge cases
- **Regressive or negative velocities** are masked, never inverted; a window with no positive velocity gives "no
  forecast" (FR-010-29), and a decelerating fit gives "no failure predicted" scored at the cap, so no event is ever
  dropped from a paired comparison.
- **Horizon-cap scoring** makes e large but finite for forecasts that never cross zero; the median (SC-010-01) is
  robust to it, and the mean and 90th percentile are reported so the effect stays visible.
- **Near-failure samples:** windows ending within 0.1 % of t_f are excluded by construction because c ≤ 0.99.
- **m_α ≤ 0.2:** Bishop's known numerical instability on steep exit slices is handled by rejecting the circle
  (FR-010-09), counted and reported.
- **Candidate-set PoF** underestimates PoF when a sample's critical circle lies outside the K circles; the live and
  baked values are shown side by side (FR-010-04).
- **Unknown de Wit inner format:** both a series and a map stack are handled (FR-010-13); a missing failure time stops
  the real-event evaluation honestly (FR-010-14).

### Assumptions and constants
- Pinned at specification (read 2026-10-07): de Wit `Data.zip` 8,943,265 bytes, MD5 3adeb6c853d2e87249b7d3549a2a00ca,
  CC BY 4.0, published 2025-03-11 (Zenodo API record 15003054); Chronos-Bolt-tiny configuration: context length 2,048,
  prediction length 64, nine quantiles 0.1–0.9, input patch 16, d_model 256, 4 encoder and 4 decoder layers (Hugging
  Face `amazon/chronos-bolt-tiny` `config.json`); pySlope 1.4.0 (MIT, 2025-10-18): Bishop only,
  `add_single_circular_plane(c_x, c_y, radius)`, `update_analysis_options(slices 10–500, tolerance default 0.005,
  max_iterations default 15)`, `get_min_FOS`, `get_min_FOS_circle`; its runtime dependencies include django,
  psycopg2-binary and kaleido 0.2.1 (PyPI JSON).
- UNVERIFIED, with oracles that do not depend on them: the Read & Stacey FoS / PoF acceptance values (inputs only);
  the open-pit guidance values of D (inputs only); the slope-specific citation of the Bayesian TTF construction
  (oracle: the closed-form conjugate update); the de Wit inner file formats, sampling and failure time (read at
  ingestion); the native sign convention of GB-InSAR instruments (the product fixes "positive = toward the radar",
  FR-010-41; tests use that definition, magnitudes and the λ/4 rule); the citation of the two-way phase relation
  4π/λ (the GB-InSAR review by Monserrat, Crosetto & Luzi 2014, DOI 10.1016/j.isprsjprs.2014.04.001, was found but its
  text was not readable; the oracle is analytical); the atmospheric-noise amplitude
  of the AR(1) stratum (a stated assumption, reported as a separate stratum); the method details of the 2026 hybrid
  deep-learning study (context only).
- The synthetic events follow Voight's law by construction, which favours methods built on it; the card states this.
- EGMS licence wording conflicts between pages; it is treated as derived-only and optional.

## 8. Clarifications log
- Ownership → resolved: `minephys.geotech` owns the per-circle Bishop / Spencer / Hoek–Brown, Voight, inverse-velocity,
  Bayesian and line-of-sight numerics; this spec owns their C1 composition (search, candidate-set PoF, shared
  preprocessing, read-out, evaluation, radar series) and the Python goldens' content; browser parity of the `geotech`
  and `forecasters` engines is FR-018-51, FR-018-52 and FR-018-57. Reported to the coordinator so that 013 does not
  re-specify the C1 radar series (superseded in part by the integration entry below: the S4b presentation is no
  longer deferred to spec 013).
- TTF read-out (docs: "fixed in the spec") → resolved: every learned model forecasts the inverse-velocity path as
  quantiles and the TTF is its zero crossing (FR-010-21, FR-010-22); no separate regression head.
- Aggregation of "TTF error ≤ 10 % of lead time" (not fixed by the plan) → resolved: median relative error over the
  SNR_obs test events, at each of the two pre-registered cut-offs, per model (SC-010-01); the decision rule uses the
  mean paired difference (DEC-0016) with a paired percentile bootstrap because the errors are skewed by the cap.
- "Observed SNR" (no definition in the docs) → resolved: displacement range over a robust second-difference noise
  estimate (FR-010-12), so that it can be measured on one real series.
- Live PoF cost → resolved: candidate-set PoF with K = 64 live, K = 1,024 baked, both shown (FR-010-03, FR-010-04).
- Hoek–Brown to Mohr–Coulomb conversion (docs: "fixed at specification") → resolved: instantaneous parameters at the
  slice-base normal stress in Balmer's parametric form, iterated with F (FR-010-02).
- Docs contradiction: the architecture page on lanes says ONNX models default to opset 20, while the plan fixes opset
  17–19 → resolved by the plan: forecasters at opset 17 (FR-010-30). Reported to the coordinator.
- Docs give C1 times in hours on the case page and in days on the method page → resolved: hours at every interface.
- User stories are written as headings, as in the template, and indexed in a table so that `tools/trace.py` registers
  their IDs (the same layout as spec 009).
- Integration 2026-10-07: this spec is the single owner of the S4b slope-radar series (plan §9 lists S1, S2, S3 and S4a
  for `st53_sensors`; S4b is the analytical GB-InSAR model of `minephys.geotech` used by case C1). Spec 013 retired
  its S4b generation requirements (FR-013-25…28, P-013-09, P-013-10, DC-013-06, US-013-5). The behaviours that only
  013 stated were added here: the sign convention, the explicit 4π/λ phase law, counter-based noise keying,
  `numpy.unwrap` semantics and keeping d and d̂ (FR-010-41); the extra hostile inputs (FR-010-42); linearity,
  rigid-motion, λ/2-periodicity, co-scaling and pixel-set invariance (P-010-16, P-010-17). The series uses
  `displacement-series.schema.json` (DC-010-02); no separate `los-series` schema exists. The out-of-scope line no
  longer defers the S4b presentation to spec 013.
- Integration 2026-10-07: every `thresholds.yaml` key this spec proposes is marked "proposed key, pending maintainer
  approval" and compiled with the other specs' proposals for the maintainer; lane-gate keys are consolidated as
  `lane_gate.*` and budget keys as `budgets.*`.
- (no open items)

## 9. Changes (only for features that modify earlier behaviour)
### ADDED Requirements
(none — new feature)
### MODIFIED Requirements
(none)
### REMOVED Requirements
(none)

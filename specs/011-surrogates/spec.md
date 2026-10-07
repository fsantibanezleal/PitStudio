# Spec 011 — Surrogates and calibration: GNS granular surrogate, differentiable DEM calibration, FNO fields
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent

GPU physics cannot run at mining scale in a browser, and a GPU simulation is only as credible as its parameters. This
spec fixes three pieces built on the studio's own solvers (spec 005-physics):
- **M8, GNS:** a 2-D graph network simulator trained on Warp DEM / Newton MPM rollouts, exported to ONNX (~3 MB) and
  run live in ONNX Runtime Web, judged on repose angle and run-out of held-out geometries (case A3);
- **M9, DEM calibration:** recovery of the sliding friction of the Warp DEM from a target angle of repose, once by
  differentiating through the simulation with Warp's tape and once with CMA-ES, judged on whether the reported 95 %
  interval covers a known synthetic truth;
- **M15, FNO:** a 2-D Fourier neural operator whose spectral layer is written as real matrix products (so it exports to
  ONNX and runs on WebGPU), trained on the Warp shallow-water (Bingham tailings) and dust fields (cases C2, C3), judged
  by relative L2 on held-out terrains.

It fixes their data, splits, observables, interval method, export and parity, the hostile inputs of every interface
and the metamorphic relations of every numerical core. Data/AI practitioners and modellers benefit: each surrogate
claim is a pre-registered test against its own solver, and each calibration reports an interval whose honesty is
measured. It inherits FR-000-05 (decision rule), FR-000-09 (synthetic labels) and FR-000-14 (manifests).

**Out of scope:** the solvers themselves (Warp DEM, Newton MPM, Warp shallow water and dust; spec 005-physics) and
their physics benchmarks; the browser engine host, tiers and parity classes (spec 018, engines `gns`, `fno`,
`granular`, `swe`); the generic export gates and the TensorRT bench (spec 016); 3-D surrogates; zero-shot
super-resolution claims; site-specific material characterisation. **Simulation-grade, educational.**

## 2. User stories

### US-011-1 (P1) Learned granular flow in the browser
As a visitor of case A3, I want to run a column collapse, a pile or a dump live in my browser with the GNS and see it
next to the GPU-simulated rollout of the same geometry with the repose and run-out errors, so that I can judge the
surrogate. Independent test: evaluate a fixture checkpoint on the held-out geometries and check the report; open the
A3 Simulate tab and check the live rollout, its tier badge and the baked reference.

### US-011-2 (P1) Honest calibration
As a DEM modeller, I want the sliding friction recovered from a repose angle by the gradient path and by CMA-ES, each
with a 95 % interval, and the empirical coverage of those intervals over synthetic-truth trials, so that I know whether
the uncertainty they report is honest. Independent test: run the full calibration pipeline against a fake analytic
simulator and check the coverage band.

### US-011-3 (P1) Interactive flood and dust what-ifs
As a visitor of cases C2 and C3, I want to move a breach or change the yield stress or the wind and see the FNO field
within 50 ms, with the solver's baked field and its error for comparison, so that I can explore scenarios. Independent
test: evaluate the exported FNO on the held-out terrains and check relative L2 per field; check the C2 live control.

### US-011-4 (P2) Exportable, verifiable surrogates
As a developer, I want every surrogate exported with a written input/output description and a parity report against
PyTorch, so that I can reuse it. Independent test: validate the IO description against its schema and re-run the
parity check on the golden set.

Story index (for traceability):

| Story | Title | Priority |
|---|---|---|
| US-011-1 | Learned granular flow in the browser | P1 |
| US-011-2 | Honest calibration | P1 |
| US-011-3 | Interactive flood and dust what-ifs | P1 |
| US-011-4 | Exportable, verifiable surrogates | P2 |

## 3. Functional requirements (EARS)

Fixed parameters referred to as "§7" are in the tables of section 7.

### 3.1 GNS granular surrogate (M8)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-011-01 | Ubiquitous | The GNS step shall take positions [N, 2] (m), the last C = 5 velocities [N, 5, 2] (m/s), particle type [N], the domain bounds [4] (m), a padded neighbour index [N, 32] and its mask [N, 32], shall build node features from the velocities, a type embedding and wall distances clipped at R, and edge features from (x_i − x_j)/R and its norm (no absolute position feature), shall apply an encoder, M = 10 residual message-passing steps of latent width 128 with layer normalisation, and a decoder, and shall return the acceleration [N, 2] (m/s²) applied by semi-implicit Euler at the dataset frame interval Δt_f. | unit |
| FR-011-02 | Ubiquitous | The graph builder (Python and the TypeScript worker) shall connect particles closer than R = 2.5 d (d the particle diameter of the dataset), exclude self-edges, list at most K_max = 32 neighbours per particle ordered by distance then index, pad with a mask, compute squared distances in binary64 from the binary32 positions, and count overflowing particles per step. | unit + parity |
| FR-011-03 | Ubiquitous | The GNS dataset shall consist of 2-D rollouts (DC-011-01) of the three geometry families of §7 (column collapse, pile formation, dump over a crest), 100 geometries with 3 packing seeds each, split by geometry id into 70 training, 10 validation and 20 test geometries, the test geometries lying inside the training envelope but at a normalised parameter distance ≥ 0.05 from every training geometry, and every reference pile at rest being at least 30 d high (a geometry that fails this is replaced and counted). | pipeline |
| FR-011-04 | Ubiquitous | Training (`s30_train`) shall minimise the mean squared error of normalised one-step accelerations with random-walk noise added to the input velocities (noise scale chosen on validation), and every hyper-parameter and the checkpoint shall be chosen on the validation geometries only. | pipeline |
| FR-011-05 | Ubiquitous | The observables shall be computed by one function for reference and surrogate rollouts at the reference's rest time T_end: the repose angle θ_r = arctan of the least-squares slope of the free surface (maximum particle top height per bin of width 2d) over the bins between 20 % and 80 % of the pile height, per flank as defined per family in §7; the run-out L as defined per family in §7 from the 99th percentile of particle x. | unit |
| FR-011-06 | Ubiquitous | `s50_evaluate` shall roll the GNS out from each held-out geometry's 3 initial packings to T_end, compare the means over the 3 packings of θ_r and L with the reference means, and report per geometry \|Δθ_r\| (°), \|ΔL\|/L, pass or fail against SC-011-01, the reference's own packing spread, the position error growth per step, the particle count per step and the overflow count. | pipeline |
| FR-011-07 | Ubiquitous | `s60_export` shall export the GNS step at opset 17 with IR version 10, with the padded-layout aggregation (Gather plus masked ReduceSum, no ScatterElements) as the live graph in fp32 and fp16, and a ScatterElements(reduction = add) variant only for the CPU and TensorRT bench (spec 016), with the input/output description of DC-011-02. | pipeline |
| FR-011-08 | Ubiquitous | The export shall check ONNX Runtime CPU fp32 against PyTorch fp32 on ≥ 200 golden steps with `models.onnx_cpu_fp32`, and shall accept the fp16 graph as the live model only if, on every held-out geometry, its rollout changes θ_r by ≤ 0.5° and L by ≤ 1 % relative to the fp32 rollout; otherwise the fp32 graph is the live model. | pipeline |
| FR-011-09 | Event | When the visitor starts a GNS scene in the A3 Simulate tab (default ≤ 2,000 particles), the web app shall build the neighbour graph in a worker, step the ONNX model on the active tier (WebGPU, else WASM), draw the rollout, and show the baked reference rollout of the same geometry with its θ_r and L errors where one is published. | E2E |
| FR-011-10 | Unwanted | If a reference rollout has not come to rest at T_end (maximum particle speed ≥ 0.01 √(g d)), then `s50_evaluate` shall exclude that packing, replace it by the next seed of the geometry and count the replacement in the report. | pipeline |
| FR-011-11 | Unwanted | If a visitor's geometry lies outside the training envelope of DC-011-02, then the web app shall still run the rollout, label it "extrapolation — no accuracy claim" and show no error against a reference. | E2E |
| FR-011-12 | Unwanted | If a rollout state becomes non-finite, or a particle moves beyond the domain bounds by more than R, then the rollout shall stop at that step and be marked "diverged at step s"; in `s50_evaluate` a diverged rollout fails its geometry. | unit + pipeline |
| FR-011-13 | Unwanted | If a particle has more than 32 neighbours within R in any step, then the step shall keep the 32 nearest, increment the overflow count, and the evaluation report and the web view shall flag the rollout "neighbour overflow". | unit |
| FR-011-14 | Unwanted | If a rollout file fails `granular-rollout.schema.json` — missing Δt_f, d or R, a non-finite value, non-increasing frame times, a particle count that changes between frames, an unknown geometry family, or a store path that is absolute or contains `..` — then `s10_preprocess` shall reject it with the reason and never coerce it. | pipeline (hostile) |
| FR-011-15 | Unwanted | If the GNS step (PyTorch, ONNX Runtime or the web engine `gns`) receives N = 0, shapes other than those of FR-011-01, a neighbour index outside [0, N), a mask whose shape differs from the index, an unknown particle type, or a non-finite value, then it shall raise `InvalidGraphError` (Python) or show "rollout stopped — <reason>" (web) and return no acceleration. | unit + E2E (hostile) |
| FR-011-16 | Ubiquitous | The GNS report shall state steps per second of the surrogate in Python (CPU and GPU) and in the browser per tier, and the solver's wall time per step for the same geometry, with hardware and tier named; speed statements are measurements, never "better" claims. | pipeline |

### 3.2 Differentiable DEM calibration (M9)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-011-17 | Ubiquitous | The calibration shall recover the sliding friction μ_s ∈ [0.1, 1.0] of the Warp DEM (spec 005) from a target repose angle θ* of a heap poured onto a flat plate, with rolling friction, restitution, effective modulus and density held at their cited knowledge-table values; synthetic-truth trials shall use trial-scale heaps of ≤ 5,000 particles and literature-target calibrations full-scale heaps of 2 × 10⁴ particles. | unit (fake simulator) + gpu |
| FR-011-18 | Ubiquitous | The calibration loss shall be L(μ) = (θ_s(μ) − θ*)², with θ_s the smooth repose observable of §7 (soft-max envelope per radial bin, β = 10/d, Gaussian bin weights, least-squares slope over the bins between 20 % and 80 % of the heap height, the bin range frozen at the start of the recorded window), averaged over S = 2 common packing seeds; the hard observable (maximum top height per bin) shall be reported with it. | unit |
| FR-011-19 | Ubiquitous | The gradient arm shall settle each heap without recording, record the last W = 1,000 steps with `wp.Tape` using Warp's deterministic atomic mode, per-contact force buffers and fixed iteration counts, back-propagate L, and update μ_s with Adam from the common start μ₀ = 0.55. | gpu + unit (Warp CPU device) |
| FR-011-20 | Ubiquitous | The CMA-ES arm shall minimise the same L from the same μ₀ with σ₀ = 0.1, the default population of the `cma` package for one dimension, and the bounds of FR-011-17. | unit (fake simulator) |
| FR-011-21 | Ubiquitous | Both arms shall stop when L ≤ (0.1°)² or when they reach the common budget of 60 forward-equivalent simulations (one adjoint pass counted as two), and shall return the best evaluated μ̂ with the number of simulations and the wall time. | unit (fake simulator) |
| FR-011-22 | Ubiquitous | Both arms shall form the same 95 % interval: run R = 8 forward simulations at μ̂ − h, μ̂ and μ̂ + h (h = 0.05 μ̂) with 8 interval seeds disjoint from the target and optimisation seeds; σ̂_θ is the standard deviation at μ̂ and ĝ the central-difference slope of the seed means; CI = μ̂ ± t₀.₉₇₅,₇ · σ̂_θ · √(1 + 1/S) / \|ĝ\|; if the 95 % interval of ĝ contains 0, the parameter is "not identified" and the trial counts as non-covering. | unit (fake simulator) |
| FR-011-23 | Ubiquitous | The gradient arm shall check its tape gradient at the first and at the final iterate against a central finite difference over 4 repeated runs at each of μ ± h (SE_FD from the pooled standard deviation, 6 degrees of freedom, §7): the gradient is trusted only if \|FD\| ≥ t₀.₉₇₅,₆ SE_FD (2.447 SE_FD), its sign equals the sign of FD, and \|g_tape − FD\| ≤ t₀.₉₉₅,₆ SE_FD (3.707 SE_FD); an untrusted gradient marks the trial "gradient unreliable", counted as non-covering for the gradient arm; the check simulations are reported separately from the budget. | unit (fake simulator) + gpu |
| FR-011-24 | Ubiquitous | The coverage study shall run 50 synthetic-truth trials per arm with μ†_j drawn uniformly in [0.3, 0.8] by a seeded generator, the same μ†_j and the same target θ*_j (from a packing seed disjoint from all others) for both arms, and shall report per arm the coverage (covering trials / 50) with its Wilson 95 % interval, the counts of "not identified" and "gradient unreliable", \|μ̂ − μ†\|, interval widths, simulations and wall time. | pipeline (fake simulator) + gpu |
| FR-011-25 | Ubiquitous | Any statement that one arm is more accurate, faster or narrower than the other shall come from the paired differences over the 50 trials (pairs = trials) through the decision rule (FR-000-05) with a paired percentile bootstrap (B = 10,000, seed in the recipe); otherwise "no significant difference". | unit |
| FR-011-26 | Ubiquitous | Every calibration result (DC-011-04) shall publish the loss terms and weights, W, the settling steps, S, R, h, the seeds, the gradient-check outcomes and the deterministic-accumulation setting. | contract |
| FR-011-27 | Optional | Where the secondary arm is enabled, the calibration shall recover (μ_s, μ_r) from θ* and a flat-bottom hopper discharge rate Q* with L = (θ_s − θ*)² / (1°)² + ((Q − Q*)/Q*)² / 0.05², report per-parameter coverage with the same interval method, and label a parameter "weakly identified" when its interval is wider than 50 % of its prior range; no success criterion applies to this arm. | unit (fake simulator) + gpu |
| FR-011-28 | Ubiquitous | The calibration shall be run at full scale against each cited literature repose target of the `minephys` knowledge tables (at least crushed gravel and dry sand), report μ̂ with its interval and the target's verification status, make no coverage claim, and publish the calibrated set with provenance for the DEM, GNS and MPM-evaluation consumers. | gpu + contract |
| FR-011-29 | Unwanted | If the gradient arm is requested for a solver that is not differentiable (Newton implicit MPM), then the calibration shall refuse it with "not differentiable — gradient-free only" and run the CMA-ES arm only. | unit |
| FR-011-30 | Unwanted | If θ* is outside [5°, 60°] or non-finite, μ₀ or the bounds are outside [0.05, 2] or inverted, the budget is outside [1, 10⁴], W is outside [100, 5,000], S or R is < 2, the seed sets overlap, or the estimated tape memory (24 B × particles × W plus contact buffers) exceeds 80 % of the free device memory, then the calibration shall raise `InvalidCalibrationError` with the reason before any simulation. | unit (hostile) |
| FR-011-31 | Ubiquitous | The A3 calibration view shall replay, with the REPLAY badge, the baked θ(μ) curve with its packing-seed band, both optimiser paths, the coverage chart with its interval and the fitted heap profile. | E2E |

### 3.3 FNO field surrogate (M15)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-011-32 | Ubiquitous | The FNO shall lift its input channels pointwise to width 32, apply 4 Fourier layers on a 64 × 64 grid, each the sum of a pointwise linear map and a spectral convolution over the kept modes k₁ ∈ {0…11} ∪ {52…63}, k₂ ∈ {0…11}, followed by GELU (none after the last), and project pointwise to its outputs; the spectral convolution shall use precomputed real cosine and sine bases as matrix products (forward unnormalised, inverse weighted 1 for k₂ = 0 and 2 otherwise and divided by 64²), with no call to `torch.fft` and no complex tensor. | unit |
| FR-011-33 | Ubiquitous | Two FNO instances shall be trained as direct maps (no autoregression): the tailings model from [bed elevation (patch mean removed, divided by patch relief), initial release depth, yield stress τ_y, plastic viscosity μ_B, density ρ (normalised constant channels)] to [h(t_k) for k = 1…8 at t_k = k T_end / 8, h_max]; the dust model from [bed elevation, source-strength field, wind speed, wind direction (cos, sin) as constant channels] to the time-averaged concentration field. | unit |
| FR-011-34 | Ubiquitous | The FNO data shall be Warp solver runs (spec 005) on 64 terrain patches of 64 × 64 cells (default cell 8 m, block-mean resampled from the 1 m Bingham 3DEP DEM) with 40 tailings and 20 dust scenarios per patch (breach cell, release volume, τ_y and μ_B, or source line and wind, drawn from the recipe ranges), split by patch into 48 training, 6 validation and 10 test patches. | pipeline |
| FR-011-35 | Ubiquitous | `s50_evaluate` shall report, per held-out scenario and per output field, the relative L2 error ‖û − u‖₂ / ‖u‖₂ on the 64 × 64 grid in physical units, its mean over the held-out scenarios per field and its 90th percentile, and the C2 / C3 KPI errors (inundated area at h_thr, arrival time at 5 checkpoint cells, maximum depth, receptor concentration) and the relative error of the total fluid volume of each h(t_k). | pipeline |
| FR-011-36 | Ubiquitous | `s60_export` shall export each FNO at opset 19 with IR version 10 and verify that the graph contains no DFT, Einsum or complex-typed tensor and only operators of the whitelist in §7, with the input/output description of DC-011-02. | pipeline |
| FR-011-37 | Ubiquitous | The export shall check ONNX Runtime CPU fp32 against PyTorch fp32 on ≥ 200 golden fields with `models.onnx_cpu_fp32`, and shall accept an fp16 graph as the live model only if the mean relative L2 of every field changes by ≤ 1 percentage point. | pipeline |
| FR-011-38 | Event | When the visitor moves a C2 or C3 control (breach position on the patch, release volume, τ_y, μ_B; or wind speed and direction), the web app shall evaluate the FNO on the active tier, draw the field, and show the baked solver field of the nearest published scenario with that scenario's relative L2. | E2E |
| FR-011-39 | Unwanted | If a control value lies outside the training ranges of DC-011-02, then the web app shall label the field "extrapolation — no accuracy claim". | E2E |
| FR-011-40 | Unwanted | If the FNO (PyTorch, ONNX Runtime or the web engine `fno`) receives an input whose shape is not [1, C_in, 64, 64], whose channel order differs from DC-011-02, or that contains a non-finite value, or an unknown patch id, then it shall raise `InvalidFieldInputError` (Python) or show "field not computed — <reason>" (web) and return no field. | unit + E2E (hostile) |
| FR-011-41 | Unwanted | If a field file fails `field-dataset.schema.json` — grid other than 64 × 64, missing units or cell size, a non-finite value, a depth below −1e-9 m, or a store path that is absolute or contains `..` — then `s10_preprocess` shall reject it with the reason. | pipeline (hostile) |
| FR-011-42 | Ubiquitous | `s50_evaluate` shall report the relative L2 of each model evaluated at 128 × 128 on refined held-out inputs against 128 × 128 solver runs, labelled "resolution transfer — not claimed". | pipeline |
| FR-011-43 | Optional | Where `neuraloperator` 2.0.0 resolves in the `pipeline/` lock, the spectral layer shall also be checked against its spectral convolution with the same weights; otherwise the card shall state that the numpy FFT reference is the only spectral oracle. | pipeline |

### 3.4 Shared

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-011-44 | Optional | Where a CUDA GPU is available, GNS training, FNO training and every calibration shall run only through the runner under `gpu0.compute`, honour `gpu0.hold`, and on out-of-memory apply the declared fallback (GNS and FNO: batch halved, at most twice; calibration: particle count halved once and the trial flagged) recorded in the manifest; these behaviours shall be verified against the fake GPU backend. | unit (fake GPU) + gpu |
| FR-011-45 | Ubiquitous | Every rollout, field and calibration dataset and every surrogate artefact shall carry a manifest (DC-000-01) naming the producing tool (Warp, Newton, PyTorch, ONNX Runtime), its measured lane and its inputs, and shall be labelled "calibrated synthetic — not validated against real data" (FR-000-09), the literature repose targets being the only real-world anchor. | contract |

## 4. Correctness properties

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-011-01 | GNS permutation equivariance: permuting the particles permutes the predicted accelerations. | random 2-D packings, N ≤ 2,000, no overflow, random weights | max abs ≤ 1e-5 × max \|a\| (fp32) |
| P-011-02 | GNS translation invariance: shifting every particle and the bounds by (Δx, 0) leaves the accelerations unchanged. | Δx ∈ [−10, 10] m, as P-011-01 | max abs ≤ 1e-5 × max \|a\| (fp32) |
| P-011-03 | Conservation: the particle count and every particle type are identical at every rollout step. | rollouts ≤ 1,000 steps | exact |
| P-011-04 | Graph builder: the neighbour relation is symmetric when no particle overflows, has no self-edge, every listed distance is < R, lists are sorted by (distance, index), and the Python and TypeScript builders return identical index and mask arrays. | random packings, N ≤ 5,000 | exact |
| P-011-05 | The padded-layout aggregation equals the scatter-add aggregation on the same graph. | as P-011-01 | rtol 1e-5 (fp32) |
| P-011-06 | Repose extractor: for particles laid on an analytic pile of slope θ, the extractor returns θ; mirroring x, translating, or permuting the particles leaves it unchanged. | θ ∈ [20°, 45°]; pile height ≥ 30 d; d ∈ [1, 10] mm | \|Δθ\| ≤ 0.4°; invariances exact |
| P-011-07 | Run-out: translating the final state and the reference toe together leaves L unchanged; scaling every length by k scales L by k; moving any particle outward never decreases L. | k ∈ [0.1, 10] | rtol 1e-9; exact (order) |
| P-011-08 | The smooth and hard repose observables agree on settled analytic heaps. | conical heaps of discs, θ ∈ [20°, 45°] | \|Δθ\| ≤ 0.5° |
| P-011-09 | Interval honesty on a fake simulator θ(μ) = a + b μ + ε, ε ~ N(0, σ²) per packing seed: the full pipeline (either arm + FR-011-22) covers μ† with frequency in [0.93, 0.97] over 2,000 trials; the half-width equals t₀.₉₇₅,₇ σ̂ √(1 + 1/S) / \|ĝ\| and scales linearly in σ̂ and as 1/\|ĝ\|. | a ∈ [20°, 30°], b ∈ [10, 40] °/unit, σ ∈ [0.2°, 1°] | coverage band (binomial 99.9 %); formula rtol 1e-9 |
| P-011-10 | Gradient gate on a fake simulator with known gradient g and Gaussian run-to-run noise: it accepts the true gradient in ≥ 98 % of 1,000 trials when \|g\| ≥ 10 SE_FD (expected 99 %), rejects a sign-flipped gradient in 100 % of them, and rejects every gradient when g = 0 and the tape returns 10 SE_FD. | g ∈ ±[10, 100] SE_FD; noise sd ∈ [0.1°, 2°] | stated (binomial margin ≥ 3 sd) |
| P-011-11 | Determinism: two tape gradients from identical inputs are bitwise identical. | small heaps on the Warp CPU device (CI) and on CUDA (gpu) | exact |
| P-011-12 | The DFT-matmul forward transform equals `numpy.fft.rfft2` at the kept modes. | random fields 64 × 64, float64 and float32 | float64 ≤ 1e-12 ‖a‖₂; float32 ≤ 1e-4 ‖a‖₂ |
| P-011-13 | The spectral convolution equals the FFT reference (rfft2 → per-mode complex weights on the kept modes → irfft2). | random fields and weights | as P-011-12 |
| P-011-14 | Circular-shift equivariance of the spectral convolution: shifting the input by (s₁, s₂) cells shifts the output by (s₁, s₂). | s ∈ [0, 63]² | as P-011-12 |
| P-011-15 | Linearity of the spectral convolution: S(αx + βy) = α S(x) + β S(y). | α, β ∈ [−10, 10] | as P-011-12 |
| P-011-16 | Resolution change: for an input band-limited to the kept modes, the spectral convolution with the same weights on the 128 × 128 trigonometric interpolation of the input equals the trigonometric interpolation of the 64 × 64 output. | band-limited random fields | float64 ≤ 1e-10 ‖u‖₂ |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-011-01 | GNS live ONNX size | ≤ 25 × 10⁶ bytes (≈ 3 MB fp16 expected) | `s60_export` budget report (spec 016) |
| NFR-011-02 | GNS step time | T1 ≤ 50 ms at 2,000 particles (median of 100 steps); on T2 the largest particle count meeting 50 ms is measured and used as the T2 cap | lane-measurement suite (spec 018) |
| NFR-011-03 | FNO live ONNX size and evaluation time | ≤ 25 × 10⁶ bytes each (≈ 5 MB fp16 expected); ≤ 50 ms on T1, ≤ 1 s on T2, otherwise lane PRECOMPUTE (FR-000-15) | `s60_export` budget report; lane-measurement suite |
| NFR-011-04 | Compute budgets | GNS ≤ 15 GPU-h, each FNO ≤ 2 GPU-h, each full-scale calibration ≤ 2 GPU-h (estimates); measured values recorded and overruns stated in the cards | run manifests |
| SC-011-01 | GNS on held-out geometries (SC-000-03) | repose ±1.5° and run-out ±5 %: \|Δθ_r\| ≤ 1.5° and \|ΔL\|/L ≤ 0.05 on every one of the 20 held-out geometries (means over 3 packings) | `s50_evaluate` report (FR-011-06) |
| SC-011-02 | DEM calibration | the 95 % CI of the recovered parameter covers the synthetic truth in ≥ 90 % of trials (≥ 45 of 50), for each arm | coverage study (FR-011-24) |
| SC-011-03 | FNO on held-out terrains | relative L2 ≤ 5 %: mean over the held-out scenarios of h_max (tailings model) and of the time-averaged concentration (dust model) | `s50_evaluate` report (FR-011-35) |
| SC-011-04 | Export parity of GNS and FNO | fp32 rtol 1e-3, atol 1e-5, max abs 1e-4 (`models.onnx_cpu_fp32`) | `s60_export` parity report |
| SC-011-05 | "Better / faster" claims (gradient vs CMA-ES; surrogate vs any baseline) | only by the decision rule; otherwise "no significant difference" | `s50_evaluate` report |
| SC-011-06 | Gradient reliability | every tape gradient used in a reported calibration passed FR-011-23; every failure is counted and published | calibration results (DC-011-04) |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-011-01 | Granular rollout metadata (Zarr or Parquet payload): family, geometry id and parameters, packing seed, solver and version, d, R, Δt_f, bounds, frame times, particle count, material parameters with provenance, rest time | `contracts/granular-rollout.schema.json` (new, T-011-001) | `st50_physics` (spec 005) → `s10_preprocess`, `s30_train`, `s50_evaluate` |
| DC-011-02 | Surrogate input/output description: model id, opset, IR version, input and output names, shapes, dtypes, channel order and units, normalisation statistics, training envelope (parameter ranges), precision, live / precompute | `contracts/surrogate-io.schema.json` (new, T-011-001; also used by specs 010 and 017) | `s60_export` → web engines `gns`, `fno`, `forecasters`, `meta-model` |
| DC-011-03 | Field dataset metadata: patch id, source DEM digest, cell size, grid, channels with units, scenario parameters, T_end, output times | `contracts/field-dataset.schema.json` (new, T-011-001) | `st50_physics` → `s10_preprocess`, `s30_train` |
| DC-011-04 | Calibration result: arm, trial id, μ†, θ*, μ̂, interval, identification flag, gradient-check log, loss terms and weights, W, settling steps, S, R, h, seeds, simulations, wall time, deterministic-accumulation flag | `contracts/calibration-result.schema.json` (new, T-011-001) | calibration driver (`st50_physics`) → `s50_evaluate`, web A3, specs 005 and 014 |

Every artefact is also described by its manifest entry (DC-000-01).

## 7. Edge cases and assumptions

### GNS geometry families and observables

| Family | Geometry parameters (recorded) | Repose θ_r | Run-out L |
|---|---|---|---|
| Column collapse against a wall at x = 0 | aspect ratio a = H₀/L₀ ∈ [0.5, 4], width L₀, d | the single flank | x₉₉ − L₀ |
| Pile formation from a pour point x_p | pour height, pour rate, d | mean of the two flanks | mean of (x₉₉ − x_p) and (x_p − x₁) |
| Dump over a crest at x_c | crest height, dump rate, d | the flank below the crest | x₉₉ − x_c |

x₉₉ and x₁ are the 99th and 1st percentiles of particle x at T_end. Test geometries: 8 collapses, 6 piles, 6 dumps.
The extractor's own resolution, measured at specification on analytic piles laid particle by particle, is ≤ 0.35° for
piles ≥ 30 d high and about 1° for 20 d piles; hence the 30 d floor of FR-011-03. Reference and surrogate go through
the same extractor, so its resolution enters both sides.

### Calibration observable
- Radial bins of width Δr = 2d from the heap axis; envelope h_b = (1/β) ln Σᵢ w_ib exp(β z_i^top), β = 10/d,
  w_ib = exp(−(r_i − r_b)² / (2 (Δr/2)²)); θ_s = arctan(−slope) of the least-squares line of h_b against r_b.
- The bin range (20 %–80 % of the heap height) is frozen at the start of the recorded window, so the observable is a
  smooth function of the particle positions inside the window.
- Gradient check: FD = (L̄₊ − L̄₋) / (2h) from 4 runs at each of μ ± h; SE_FD = s_p √(1/4 + 1/4) / (2h) with s_p the
  pooled standard deviation of the two groups (6 degrees of freedom); Student quantiles t₀.₉₇₅,₆ = 2.447 and
  t₀.₉₉₅,₆ = 3.707.

### FNO operator whitelist
MatMul, Add, Sub, Mul, Div, Erf (GELU), Reshape, Transpose, Concat, Slice, Gather, Unsqueeze, Squeeze, Constant,
Identity, Cast. Anything else fails FR-011-36.

### Edge cases
- **Chaotic flow:** particle-by-particle agreement is not claimed after a few steps; the comparison is on observables
  (FR-011-05, FR-011-06), and the packing spread of the reference is reported so that the tolerance can be read
  against it.
- **Rotation equivariance is not claimed** for the GNS (gravity and walls break it) or for the FNO (its learned weights
  are not symmetric); mirror symmetry of the trained models is reported, not asserted.
- **Overflow** (> 32 neighbours) is counted, never silent (FR-011-13); the default R = 2.5 d gives about 23 neighbours
  in a dense 2-D packing (π · 2.5² / 0.866 ≈ 22.7), leaving a margin to 32.
- **Non-identifiable trials** count against coverage (FR-011-22, FR-011-23), so an unbounded interval can never inflate
  coverage.
- **Empty fields:** an output field whose solver norm is below 1e-9 (for example h(t₁) far from the breach) is excluded
  from the relative L2 mean and counted.

### Assumptions and constants
- Binomial arithmetic (computed at specification): with 50 trials, a perfectly calibrated 95 % interval falls below 45
  covering trials with probability 0.038; with a true coverage of 90 % it does so with probability 0.38. The choice of
  50 trials balances this against the calibration budget.
- Wall-distance features, R and K_max follow the GNS reference design; `geoelements/gns` (MIT) is a cited reference,
  not a dependency (its scatter and cluster extensions lag the locked PyTorch line).
- UNVERIFIED, with oracles that do not depend on them: the Hertz contact transcription of the DEM (the coverage test
  uses the same forward model for truth and calibration); the literature repose values (inputs, no coverage claim);
  tailings rheology values (inputs; the FNO is judged against its own solver); whether ONNX Runtime Web's WebGPU
  `ScatterElements` honours `reduction` (avoided by the padded layout); `Einsum` WebGPU registration (avoided by the
  whitelist).

## 8. Clarifications log
- Aggregation layout (docs: "the spec fixes the layout") → resolved: padded neighbour layout N × 32 with mask for the
  live graph; the ScatterElements variant is bench-only (FR-011-07).
- Run-out percentile (docs: "fixed in the surrogates spec") → resolved: 99th percentile per family (§7).
- GNS acceptance aggregation → resolved: every held-out geometry, on means over 3 packings, because single chaotic
  rollouts make a per-run comparison noisy.
- DEM calibration targets: the method page lists repose and discharge, the model card repose only, and the plan says
  "friction from repose" → resolved by the plan: the acceptance arm recovers μ_s from repose (FR-011-17); repose plus
  discharge is an optional secondary arm with no success criterion (FR-011-27). Reported to the coordinator.
- Interval method (docs: "fixed in the surrogates spec") → resolved: the seed-ensemble delta interval of FR-011-22,
  identical for both arms; its honesty is tested on a fake simulator (P-011-09) before any GPU run.
- Number of trials → resolved: 50 per arm, with the false-fail probabilities recorded in §7.
- FNO input/output pairing (docs: direct map or next-step rollout, "fixed in the spec") → resolved: direct map to
  eight depth snapshots and h_max (FR-011-33); no autoregression.
- FNO bound "per terrain or mean" → resolved: mean over held-out scenarios, with the 90th percentile and per-terrain
  values reported (SC-011-03, FR-011-35).
- The tailings theory page says the exported graph contains "MatMul/Einsum operators", the FNO card avoids Einsum →
  resolved: MatMul only, Einsum excluded by the whitelist (FR-011-36). Reported to the coordinator.
- The architecture page on lanes says ONNX models default to opset 20, the plan says 17–19 → resolved by the plan: GNS
  opset 17, FNO opset 19. Reported to the coordinator.
- Browser particle cap: spec 018's engine `gns` caps at 5,000 particles; the default scene and the gate measurement use
  2,000 (NFR-011-02).
- User stories are headings as in the template and indexed in a table for `tools/trace.py`.
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

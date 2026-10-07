# Spec 017 — Planning and survey: mine-to-mill meta-model, ultimate pit and scheduling, splat survey and volumes
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent

Three cases close the value chain around the pit:
- **D2 (M17):** blast fragmentation carried through crushing and grinding to kWh/t, t/h and cost/t by the analytical
  `minephys` chain, and a small learned meta-model (gradient-boosted trees or an MLP → ONNX) that answers the same
  question instantly, accepted only if it reproduces the chain (R² ≥ 0.95 on held-out sweeps);
- **E1 (M18):** the ultimate pit as the exact minimum cut of the block precedence graph, nested shells by revenue
  factor, pushbacks and a MILP production schedule (HiGHS), on `oreblocks` synthetic deposits with stamped optima and,
  optionally, the MineLib `marvin` instance; live in the browser for up to 10⁵ blocks within 1 s;
- **E2 (M19):** a drone survey of a scene whose volume is known exactly, reconstructed with COLMAP and a Brush 3D
  Gaussian splat (packaged PLY → SPZ), its volume error against the truth, and the real excavated volume of Bingham
  Canyon between the 3DEP 2018 and 2023 DEMs by DEM differencing.

It fixes the sweeps, the family-selection rule and the evaluation of the meta-model; the block values, precedence,
canonical pit, shells, pushbacks, schedule formulation and oracle agreement of the planner; the volume definitions,
grid preparation, uncertainty, reconstruction route and honesty rules of the survey; and the hostile inputs of every
interface. Mine-to-mill teams, planners and surveyors benefit: every number is either exact against an independent
oracle or reported with its error against exact truth. It inherits FR-000-05, FR-000-09, FR-000-10 and FR-000-14.

**Out of scope:** the numerics of the `minephys` comminution and planning functions (the `minephys` repository's
specs); haul distance and lift per period (spec 007, M6 routing on the shells); the pit-design geometry from shells
(spec 004, `st20_pit_design`); the drone camera renders themselves (spec 013, scenario S2); browser engine host and
parity classes (spec 018, engines `comminution`, `meta-model`, `mincut`, `volume`); stochastic planning; plant design.
**Educational, not mine-planning, plant-design or survey-certification software.**

## 2. User stories

### US-017-1 (P1) Mine-to-mill trade-offs instantly
As a mine-to-mill engineer, I want to move blast and circuit sliders and see kWh/t, t/h and cost/t from the
analytical chain and from the meta-model side by side, with the meta-model's held-out R², so that I can explore
trade-offs fast and know how far to trust the fast answer. Independent test: evaluate a fixture meta-model on
held-out sweeps and compare R² with a hand computation; check the D2 Simulate tab shows both answers.

### US-017-2 (P1) The ultimate pit, exactly, in the browser
As a long-term planner, I want the ultimate pit and its nested shells for a block model, computed live as I move the
revenue factor and identical to independent max-flow oracles, so that I can trust the shells behind every haulage
case. Independent test: solve golden instances and compare value and block set with networkx and OR-Tools; move the
E1 revenue-factor slider and check the pit grows monotonically.

### US-017-3 (P2) A schedule with an NPV
As a planner, I want pushbacks and a feasible MILP schedule with its NPV, strip ratio and tonnage per period, so that
the life-of-mine sequence is explicit. Independent test: check a baked schedule against every precedence and capacity
constraint and recompute its NPV by hand.

### US-017-4 (P1) Survey volume error against exact truth
As a mine surveyor, I want the volume error of a photogrammetric survey of a known-volume scene for several survey
designs, and the real Bingham 2018 → 2023 excavated volume with its uncertainty, so that I know what a drone survey can
and cannot resolve. Independent test: difference two analytic surfaces with a known volume; run the volume report on a
fixture reconstruction.

### US-017-5 (P2) Draw a polygon, get a volume
As a visitor, I want to draw a polygon on the pit and read cut and fill between two epochs live, so that I can measure
excavation myself. Independent test: draw a fixture polygon in the E2 tab and compare with the Python reference.

Story index (for traceability):

| Story | Title | Priority |
|---|---|---|
| US-017-1 | Mine-to-mill trade-offs instantly | P1 |
| US-017-2 | The ultimate pit, exactly, in the browser | P1 |
| US-017-3 | A schedule with an NPV | P2 |
| US-017-4 | Survey volume error against exact truth | P1 |
| US-017-5 | Draw a polygon, get a volume | P2 |

## 3. Functional requirements (EARS)

Fixed parameters referred to as "§7" are in the tables of section 7.

### 3.1 Mine-to-mill meta-model (M17, case D2)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-017-01 | Ubiquitous | The D2 chain shall compose only `minephys` functions: Kuz-Ram / Swebrec run-of-mine size distribution (`minephys.blasting`) → crusher classification–breakage → F80 → Bond (or Morrell) specific energy to the target P80 → population-balance mill product (`minephys.comminution`) → throughput t/h = η P_mill / W → cost/t from the documented unit costs, and shall return kWh/t, t/h and cost/t for the input vector of §7. | unit |
| FR-017-02 | Ubiquitous | The sweep generator (`s05_synthesize`) shall draw 200 ore × circuit configurations by scrambled Sobol (seeded) over the box of §7, 64 blast designs per configuration by scrambled Sobol, evaluate the chain at every point, split by configuration into 140 training, 20 validation and 40 held-out sweeps, and link every box bound to its `minephys` knowledge-table row, propagating UNVERIFIED flags into the sweep manifest (DC-017-01). | pipeline |
| FR-017-03 | Ubiquitous | Two families shall be trained on the training sweeps with the mean squared error of standardised outputs: gradient-boosted trees (scikit-learn `HistGradientBoostingRegressor`, one per output) and an MLP (3 hidden layers of 64 units, SiLU, standardised and log-transformed positive inputs, multi-output), with hyper-parameters chosen on the validation sweeps only. | pipeline |
| FR-017-04 | Ubiquitous | The selection rule shall pick the family with the higher minimum over outputs of the validation R²; when the two differ by < 0.005 it shall pick the one with the smaller ONNX file; gradient-boosted trees are eligible only if their ONNX conversion is available in the lock, is ≤ 10⁶ bytes and passes FR-017-07 on ONNX Runtime CPU and WASM; the held-out sweeps shall be touched once, after selection. | pipeline |
| FR-017-05 | Ubiquitous | `s50_evaluate` shall report, per output (kWh/t, t/h, cost/t), the R² pooled over all held-out points, the distribution of per-sweep R² (median, minimum), the maximum absolute error, and the pass rates of the monotonicity checks of §7 for both the chain and the meta-model. | pipeline |
| FR-017-06 | Ubiquitous | For each held-out configuration, `s50_evaluate` shall take the meta-model's argmax of t/h subject to kWh/t ≤ the configuration's cap over a 1,024-point blast-design grid, re-evaluate the chain there, and report the t/h gap (%) and any cap violation. | pipeline |
| FR-017-07 | Ubiquitous | `s60_export` shall export the selected meta-model at opset 17 with IR version 10 (MLP: dynamo export with verification; trees: the locked `ai.onnx.ml` converter) with the input/output description of DC-011-02, and check ONNX Runtime CPU fp32 against the Python model on ≥ 200 golden inputs with `models.onnx_cpu_fp32`. | pipeline |
| FR-017-08 | Ubiquitous | The D2 Simulate tab shall show, for the same inputs, the chain result (engine `comminution`) and the meta-model result (engine `meta-model`) side by side with the held-out R² of each output, and the label "calibrated synthetic — not validated against real data" (FR-000-09). | E2E |
| FR-017-09 | Unwanted | If any meta-model input lies outside the sweep box, then the D2 tab shall label the meta-model answer "extrapolation — outside the training box" and still show the chain answer. | E2E |
| FR-017-10 | Unwanted | If a sweep configuration has an inverted or non-finite bound, an unknown input name, P80 ≥ the smallest feed F80 of the box, fewer than 8 or more than 4,096 points per configuration, fewer than 10 or more than 10⁴ configurations, or overlapping split seeds, then `s05_synthesize` shall reject it before evaluating the chain. | unit (hostile) |
| FR-017-11 | Unwanted | If the meta-model (Python, ONNX Runtime or the web engine `meta-model`) receives an input row whose width or order differs from DC-011-02 or that contains a non-finite value, then it shall raise `InvalidInputError` (Python) or show "no answer — <reason>" (web) and return no output. | unit + E2E (hostile) |

### 3.2 Ultimate pit, shells and schedule (M18, case E1)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-017-12 | Ubiquitous | The block value shall be v_i(λ) = max(T_i [λ g_i r (p − s_r) − c_p] − T_i c_m, −T_i c_m) in USD, and every value entering a solver shall be scaled to integer cents (v × 100, rounded half to even) in int64. | unit |
| FR-017-13 | Ubiquitous | For regular block grids without their own precedence file, the precedence generator shall add an arc from block (i, j, k) to every block ℓ = 1…m levels above whose horizontal centre offset is ≤ ℓ dz / tan α (+ 1e-9 m), with overall slope angle α and m from the recipe (default 1, the 1:5 pattern at 45° on cubic blocks); `oreblocks` and MineLib instances shall use their own arcs. | unit |
| FR-017-14 | Ubiquitous | The E1 ultimate pit shall be the minimal maximum-weight closure — the set of blocks reachable from the source in the final residual network of a maximum flow of the s–t network (s → i with v_i > 0, i → t with −v_i for v_i < 0, infinite precedence arcs) — computed in exact int64 arithmetic by the `minephys.planning` min-cut, with its value Σ v_i over the set. | unit |
| FR-017-15 | Ubiquitous | On every golden instance and every generated property instance, the E1 pit value shall equal the value from networkx `minimum_cut`, OR-Tools `SimpleMaxFlow` and SciPy `maximum_flow` exactly, and its block set shall equal the networkx and OR-Tools source sides exactly; on every `oreblocks` deposit the value shall equal the stamped optimum exactly. | pipeline + unit |
| FR-017-16 | Ubiquitous | The shell generator shall solve the pit at the revenue factors λ = 0.025, 0.050, …, 1.000 (40 values) and write a shell table (DC-017-03) with λ, block count, ore and waste tonnage, value and strip ratio. | unit |
| FR-017-17 | Ubiquitous | The pushback rule shall walk the distinct shells in increasing λ and close a pushback when its cumulative incremental ore tonnage reaches T_min (default one period of processing capacity), merging a final remainder below T_min / 2 into the previous pushback, and shall report each pushback's ore and waste tonnage and its incremental strip ratio. | unit |
| FR-017-18 | Ubiquitous | The scheduler (`pipeline/`, HiGHS) shall solve the time-indexed program of the planning theory page on bench-phase units (blocks grouped by pushback and bench; a unit requires the unit above it in the same pushback and the same bench in the previous pushback) with binary x_{u,t}, mining capacity M_t, processing capacity P_t and discount δ per period, with `mip_rel_gap` ≤ 1e-4 and a recorded time limit, and shall write the schedule, its NPV, its gap and its solver status (DC-017-03). | pipeline |
| FR-017-19 | Ubiquitous | Every produced schedule shall pass an independent checker that verifies each unit is mined at most once, each precedence holds in time, each period's mining and processing tonnage are within capacity, and the reported NPV equals Σ_t CF_t / (1 + δ)^t recomputed from the schedule. | unit |
| FR-017-20 | Ubiquitous | On tiny instances (≤ 8 units, ≤ 3 periods) the scheduler's objective shall equal the optimum found by exhaustive enumeration of every feasible assignment. | unit |
| FR-017-21 | Ubiquitous | `s50_evaluate` shall report for E1 the pit value, NPV of the schedule, the strip ratio of the pit and of every pushback (total and incremental), tonnage per period, and shall hand the per-period mined units to the routing of spec 007 for haul km and lift per period. | pipeline |
| FR-017-22 | Ubiquitous | The shells, pushbacks and schedule shall be written per `pit-shells.schema.json` for `st20_pit_design` (spec 004) and the web E1 tabs. | contract |
| FR-017-23 | Optional | Where the MineLib `marvin` instance is fetched (`s00_download`, SHA-256 pinned at first download), its UPIT value from `marvin.blocks`, `marvin.prec` and `marvin.upit` shall equal the published best-known value 1,415,655,436, and every derived artefact shall be a separate manifest entry licensed CC BY-SA 3.0 carrying the attribution text of the dataset card verbatim; the raw files shall never be committed or re-hosted. | pipeline + contract |
| FR-017-24 | Unwanted | If the MineLib host is unreachable, a file fails its pinned SHA-256, or a file fails to parse, then E1 shall show the MineLib check as "Not run — <reason>" and continue on the `oreblocks` deposits. | pipeline (hostile) |
| FR-017-25 | Event | When the visitor moves the E1 revenue-factor slider, the web app shall recompute the ultimate pit of the loaded block model (≤ 10⁵ blocks) in the `mincut` worker and redraw the shell, the pit value and the strip ratio. | E2E |
| FR-017-26 | Unwanted | If a block model has more than 10⁵ blocks, then the E1 tab shall not compute it live and shall show its baked shells with the REPLAY badge and the reason. | E2E |
| FR-017-27 | Unwanted | If a block model or MineLib file has a non-finite value, a duplicate block id, a precedence that names an unknown block, a negative tonnage, a grade outside [0, 1], an unknown destination, a sum of \|v\| in cents ≥ 2⁶² (≥ 2⁵³ for the web engine), or a file path that is absolute or contains `..`, then the loader shall reject it with the reason and produce no shell. | unit (hostile) |
| FR-017-28 | Unwanted | If a shell or schedule configuration has a revenue-factor grid that is empty, non-increasing or outside (0, 2], T_min ≤ 0, a period count outside [1, 50], a capacity ≤ 0, δ outside [0, 1), or more than 2 × 10⁵ binary variables, then the planner shall reject it before solving. | unit (hostile) |
| FR-017-29 | Optional | Where the kit-app-template licence prompt has been answered and the Kit lane runs, E1 shall publish pushback review captures of the shells in the pit stage (`st58_kit_capture`); otherwise the Composer artefact shall show "Not run". Kit performance data stay local-only. | E2E |

### 3.3 Survey and volumes (M19, case E2)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-017-30 | Ubiquitous | The DEM-differencing function shall return, for two surfaces z₀ (before) and z₁ (after) on one grid with cell area A_c and an area-of-interest polygon, V_fill = A_c Σ max(z₁ − z₀, 0), V_cut = A_c Σ max(z₀ − z₁, 0) and V_net = V_fill − V_cut over the valid cells whose centre lies in the polygon, summed with exactly rounded summation (`math.fsum`, mirrored in the browser), and the count and fraction of excluded no-data cells. | unit |
| FR-017-31 | Ubiquitous | The grid preparation shall read the horizontal CRS, the vertical datum and the vertical accuracy (RMSEz) of each DEM from its metadata, reproject the 2018 DEM onto the 2023 grid by bilinear interpolation when the grids differ, and record the transform, both SHA-256 digests and both 3DEP project names. | pipeline |
| FR-017-32 | Unwanted | If the two DEMs' vertical datums or geoid models differ and the recipe declares no vertical transform (with its source), then the real-volume result shall be "Not run — vertical datums differ"; a declared constant or grid offset shall be applied and recorded. | pipeline (hostile) |
| FR-017-33 | Ubiquitous | Each real volume shall carry two uncertainty bounds from the per-epoch RMSEz σ₀, σ₁: uncorrelated A_c √N √(σ₀² + σ₁²) and fully correlated A_c N √(σ₀² + σ₁²), N being the number of valid cells. | unit |
| FR-017-34 | Ubiquitous | The E2 real result shall be the 2018 → 2023 V_cut, V_fill and V_net (m³) over the Bingham pit area of interest (the Tang & Werner mining-footprint polygon intersected with the 3DEP query box, the overlap ratio reported; the site label stays provisional when no polygon intersects), with its uncertainty bounds, inputs and digests, labelled "measurement, not validation". | pipeline |
| FR-017-35 | Ubiquitous | The known-volume scene shall contain a conical-frustum stockpile and a trapezoidal pushback cut on a flat base, with exact volumes from their closed forms, a closed USD mesh whose divergence-theorem volume equals them, and the exact surface rasterised on the survey grid (cell 0.25 m) so that the gridding error of an exact surface is reported as the floor of the survey error. | unit |
| FR-017-36 | Ubiquitous | The survey shall comprise 12 rendered flights — ground sampling distance {2, 4, 8} cm/px × forward/side overlap {70, 80} % × sun elevation {30°, 60°} — each with nadir and ±30° oblique images and 3 sensor-noise seeds, recorded with exact intrinsics, poses and depth per `survey-flight.schema.json`. | contract |
| FR-017-37 | Ubiquitous | The reconstruction (`st58b_capture_splat`) shall run COLMAP 4.2.1 feature extraction, matching and mapping, align the model to the true camera centres by a least-squares similarity transform (Umeyama), run COLMAP dense stereo and fusion, and grid the fused points at 0.25 m by per-cell median elevation (empty cells left as no data) to give the photogrammetric surface. | gpu + unit |
| FR-017-38 | Ubiquitous | Brush v0.3.0 shall train a 3D Gaussian splat from the COLMAP output, and the Gaussian means with opacity ≥ 0.5 gridded at 0.25 m by per-cell median shall give the splat surface; the splat is a visual layer and its surface is reported, never used as ground truth. | gpu + unit |
| FR-017-39 | Ubiquitous | `s50_evaluate` shall report per flight and seed the volume error 100 (V̂ − V)/V (%) of fill and cut for the photogrammetric and the splat surfaces, the gridding floor, the reprojection RMSE (px), the alignment RMSE (m), the median absolute depth error against the rendered depth (m), the GSD and the image registration ratio; no pass threshold applies. | pipeline |
| FR-017-40 | Ubiquitous | Any statement that one surface or one survey design gives a smaller volume error than another shall come from paired differences of \|error\| over flights × seeds through the decision rule (FR-000-05) with a paired percentile bootstrap (B = 10,000); otherwise "no significant difference". | unit |
| FR-017-41 | Ubiquitous | The splat shall be packaged PLY → SPZ with `@playcanvas/splat-transform` 3.9.0; if the SPZ exceeds 25 × 10⁶ bytes the lowest-opacity Gaussians shall be pruned until it fits, the count recorded; the E2 view shall show it with the badge "captured (photogrammetry), not simulated". | pipeline + E2E |
| FR-017-42 | Ubiquitous | Before every run, the reconstruction stage shall verify the COLMAP and Brush binaries against their pinned SHA-256 and read their versions, and record both in the manifest. | unit (fake tools) |
| FR-017-43 | Unwanted | If Brush is missing, fails its checksum or its smoke run, then the splat surface and the splat view shall show "Not run — <reason>", and E2 shall continue with the photogrammetric surface and DEM differencing. | unit (fake tools) |
| FR-017-44 | Unwanted | If the RTX drone camera (ovrtx, scenario S2) is unavailable or its probe fails, then every synthetic-flight result shall show "Not run — RTX camera unavailable", and the real Bingham volume shall still be produced. | unit (fake tools) |
| FR-017-45 | Unwanted | If COLMAP registers fewer than 80 % of a flight's images or the alignment RMSE exceeds 5 × GSD, then that flight shall be reported "reconstruction failed — <reason>" with no volume, and counted. | unit (fake tools) |
| FR-017-46 | Event | When the visitor closes a polygon on the E2 map, the web app shall compute V_cut, V_fill and V_net over the 4 m web grids of the two epochs in the `volume` worker and show them with the no-data fraction and the uncertainty bounds. | E2E |
| FR-017-47 | Unwanted | If a polygon has fewer than 3 vertices, more than 10⁴ vertices, a self-intersection, a non-finite coordinate, or lies entirely outside the grid, then the volume function and the E2 tab shall reject it with the reason and show no volume. | unit + E2E (hostile) |
| FR-017-48 | Unwanted | If two surfaces differ in shape, origin or cell size without a declared resampling, have a cell size ≤ 0 or non-finite, or have no valid cell inside the polygon, then the DEM-differencing function shall raise `InvalidSurfaceError` with the reason. | unit (hostile) |
| FR-017-49 | Unwanted | If a PLY or SPZ file fails to parse, declares more than 10⁷ Gaussians, or has non-finite attributes, then the packaging stage shall reject it and the splat view shall show "Not run — <reason>". | unit (hostile) |
| FR-017-50 | Optional | Where a CUDA GPU is available, COLMAP dense stereo and Brush training shall run only through the runner under `gpu0.compute`, honour `gpu0.hold`, and stop with a recorded reason on a timeout (default 2 h per flight) or out-of-memory; these behaviours shall be verified with the fake GPU backend and fake tool binaries. | unit (fake GPU) + gpu |
| FR-017-51 | Ubiquitous | Every D2, E1 and E2 artefact shall carry a manifest (DC-000-01): sweeps and meta-model labelled "calibrated synthetic — not validated against real data", `oreblocks` deposits labelled synthetic, MineLib-derived layers in separate CC BY-SA 3.0 entries, the real Bingham volume with its public-domain attribution, and the splat with its producing tools. | contract |

## 4. Correctness properties

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-017-01 | The E1 pit value and block set equal those of networkx (minimal source side) on random block models. | Hypothesis: ≤ 300 blocks, random arcs to blocks above, values in [−10⁶, 10⁶] cents | exact |
| P-017-02 | The returned pit is closed: every precedence of every pit block is in the pit. | as P-017-01 and `oreblocks` deposits | exact |
| P-017-03 | Nesting: λ₁ < λ₂ implies pit(λ₁) ⊆ pit(λ₂). | 40-value grid, random deposits | exact |
| P-017-04 | Raising the value of a block never removes a block from the pit; raising the mining cost c_m never adds one. | as P-017-01 | exact |
| P-017-05 | Multiplying every value by a positive integer k leaves the pit unchanged and multiplies its value by k; relabelling the blocks relabels the pit. | k ∈ [1, 1,000] | exact |
| P-017-06 | v_i(λ) is non-decreasing in λ and in g_i and equals the hand calculation of the planning theory page. | grades in [0, 0.05], λ ∈ (0, 2] | exact (order); hand values exact in cents |
| P-017-07 | Every scheduler output on random feasible instances passes the checker of FR-017-19, and its NPV recomputed from cash flows equals the reported NPV. | ≤ 300 units, ≤ 20 periods, \|NPV\| ≥ 0.1 Σ\|CF_t\| | NPV rtol 1e-12 |
| P-017-08 | On tiny instances, raising a capacity never lowers the optimal NPV. | ≤ 8 units, ≤ 3 periods | exact (order, at gap 0) |
| P-017-09 | Pushbacks partition the final pit: they are disjoint, their union is the pit, and the union of the first k pushbacks is one of the shells. | random deposits | exact |
| P-017-10 | Adding a prism of height h > 0 over cells where z₁ ≥ z₀ raises V_fill by h × (cell count × A_c) and leaves V_cut unchanged. | grids ≤ 512 × 512, h ∈ [0.01, 100] m | rtol 1e-13 (one rounding of d + h per cell) |
| P-017-11 | Swapping z₀ and z₁ swaps V_cut and V_fill and negates V_net. | as P-017-10 | exact |
| P-017-12 | For a partition of the polygon's cells into disjoint polygons, the volumes add up. | random partitions | rtol 1e-12 |
| P-017-13 | For a C² difference field d = z₁ − z₀ ≥ 0 on a cell-aligned rectangle of area A (quadratic bowls, Gaussian mounds on a positive base), the gridded volume differs from the exact integral by at most the midpoint-rule bound A Δ² (max \|∂²d/∂x²\| + max \|∂²d/∂y²\|) / 24. | cells 4, 2, 1, 0.5 m; rectangles ≤ 2 km | the bound (plus rtol 1e-12) |
| P-017-14 | Adding the same constant to both surfaces leaves V_cut and V_fill unchanged; scaling the difference field by k scales them by k. | c ∈ [−10³, 10³] m; k ∈ [0, 10] | \|ΔV\| ≤ 1e-15 (\|c\| + (k + 1) max\|z\|) N A_c (one rounding per cell and operation) |
| P-017-15 | The divergence-theorem volume of a closed polyhedral mesh equals the closed form of a cube, a prism and a frustum mesh; it is unchanged by translation and scales as k³. | edge lengths in [0.1, 10³] m | rtol 1e-12 |
| P-017-16 | The Umeyama alignment recovers a known similarity transform from noise-free correspondences, and is unchanged by permuting the correspondences together. | scale ∈ [0.1, 10], random rotations and shifts, ≥ 3 non-collinear points | rtol 1e-9 |
| P-017-17 | Chain identities: t/h × kWh/t = η P_mill; kWh/t is non-increasing in the target P80 and non-decreasing in W_i; the Bond term is 0 when P80 = F80. | the §7 box | rtol 1e-12; exact (order) |
| P-017-18 | R² equals 1 for exact predictions, matches the hand calculation, and is unchanged when y and ŷ undergo the same affine map a y + b with a ≠ 0. | random vectors, n ∈ [2, 10⁴] | rtol 1e-12 |
| P-017-19 | The sweep design is a deterministic function of its seed, and its training, validation and held-out configurations are disjoint. | seeds 0–999 | exact |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-017-01 | Meta-model ONNX size | < 10⁶ bytes | `s60_export` budget report (spec 016) |
| NFR-017-02 | Meta-model batch evaluation in the browser on T2 | ≥ 200 scenarios per second (batch of 256) | lane-measurement suite (spec 018) |
| NFR-017-03 | Live ultimate pit on T2 | ≤ 1 s for 10⁵ blocks with the 1:5 precedence (median of 5 runs) | lane-measurement suite (spec 018) |
| NFR-017-04 | Live polygon volume on T2 | ≤ 1 s for a 2,048 × 2,048 grid and a 10⁴-vertex polygon | lane-measurement suite (spec 018) |
| NFR-017-05 | Splat asset | ≤ 25 × 10⁶ bytes, requested only on the splat route (never in the first view) | budget report + E2E |
| NFR-017-06 | Python min-cut wall time on the reference CPU | recorded per baked instance; ≤ 60 s for 10⁵ blocks with the 1:5 precedence (estimate; an overrun is reported) | run manifests |
| NFR-017-07 | Reconstruction time per flight | ≤ 2 h (estimate; recorded) | run manifests |
| SC-017-01 | Mine-to-mill meta-model | R² ≥ 0.95 vs the analytical chain on held-out sweeps, for kWh/t and for t/h (pooled over the 40 held-out sweeps) | `s50_evaluate` report (FR-017-05) |
| SC-017-02 | Meta-model export parity | fp32 rtol 1e-3, atol 1e-5, max abs 1e-4 (`models.onnx_cpu_fp32`) | `s60_export` parity report |
| SC-017-03 | Min-cut exactness | equal to the OR-Tools and networkx objectives exactly on every golden instance, and equal to every stamped `oreblocks` optimum | oracle tests (FR-017-15) |
| SC-017-04 | MILP schedules | every schedule satisfies every precedence and capacity constraint | checker (FR-017-19) |
| SC-017-05 | MineLib `marvin` (optional) | UPIT value = 1,415,655,436 | oracle test (FR-017-23) |
| SC-017-06 | Survey volume error | reported for every survey design and seed against exact truth, with no pass threshold (pre-registered); DEM differencing passes its worked examples and P-017-10…P-017-14 | `s50_evaluate` report; tests |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-017-01 | Comminution sweeps: configuration id, split, inputs with units, outputs (kWh/t, t/h, cost/t), knowledge-table row ids and verification status per bound, seed | `contracts/comminution-sweep.schema.json` (new, T-017-001) | `s05_synthesize` → `s30_train`, `s50_evaluate`, D2 replay |
| DC-017-02 | Block model: block id, grid indices, centre, tonnage, grade, destination values or BEV components, precedence arcs, source (`oreblocks` seed, MineLib instance, own grid), licence | `contracts/block-model.schema.json` (new, T-017-001) | `s05_synthesize` (`oreblocks`), `s10_preprocess` (MineLib) → min-cut, shells, scheduler, web `mincut` |
| DC-017-03 | Shells, pushbacks and schedules: λ grid, per-shell block sets (bit-packed) and tonnages, pushbacks, bench-phase units, schedule, NPV, gap, solver status, strip ratios | `contracts/pit-shells.schema.json` (new, T-017-001) | planner → `st20_pit_design` (spec 004), routing (spec 007), web E1 |
| DC-017-04 | Survey volumes: method (DEM differencing, photogrammetric, splat), surfaces' digests, grid, polygon, V_cut, V_fill, V_net, no-data fraction, uncertainty bounds, flight and seed, error metrics | `contracts/survey-volume.schema.json` (new, T-017-001) | `s50_evaluate` → web E2, docs results |
| DC-017-05 | Survey flight record: flight id, design (GSD, overlap, sun), seed, image index with SHA-256, intrinsics, poses, depth paths, exact scene volumes | `contracts/survey-flight.schema.json` (new, T-017-001) | `st53_sensors` S2 (spec 013) → `st58b_capture_splat`, `s50_evaluate` |

The meta-model input/output description uses `contracts/surrogate-io.schema.json` (DC-011-02). Every artefact is
also described by its manifest entry (DC-000-01).

## 7. Edge cases and assumptions

### D2 input vector and sweep box
| Group | Inputs (units) | Sampled |
|---|---|---|
| Blast design | burden B (m), spacing ratio S/B (–), powder factor q (kg/m³), hole diameter (mm), bench height (m) | per point (64 per configuration) over B, S/B, q; hole diameter and bench height per configuration |
| Ore | rock factor A (–), Bond work index W_i (kWh/t) or Morrell index M_i (kWh/t) | per configuration |
| Circuit | crusher closed-side setting (mm), target P80 (µm), installed mill power P_mill (kW), efficiency η (–), kWh/t cap (kWh/t) | per configuration |
| Costs | explosive (USD/kg), energy (USD/kWh), crushing and grinding consumables (USD/t) | per configuration |

Every bound is a `minephys` knowledge-table row; illustrative values are UNVERIFIED and flagged (FR-017-02).
Monotonicity checks reported for chain and meta-model: lower target P80 → higher kWh/t; higher W_i → higher kWh/t;
t/h × kWh/t = η P_mill.

### Worked examples used as oracles (hand calculations, re-checked at specification)
- Bond: W_i 14 kWh/t, F80 2,000 µm, P80 150 µm → W = 140 (1/√150 − 1/√2,000) = 8.30 kWh/t; at 10 MW, 1,205 t/h;
  with F80 1,500 µm, 7.82 kWh/t and 1,279 t/h (M17 page).
- Min-cut: one ore block (+5) under three waste blocks (−1 each) → pit = all four, value 2; with +2 → empty pit, value
  0 (planning theory page); revenue-factor example v_d(λ) = 6λ − 1 → full pit from λ = 2/3.
- Break-even cut-off: c_p 10 USD/t, r 0.85, p − s_r 8,000 USD/t → 0.147 % Cu.
- Ramp: H 15 m at 10 % grade → 150 m of ramp per bench.

### Edge cases
- **Ties in the closure:** zero-value blocks or zero-value sub-closures make several maximum closures optimal; the
  minimal one (FR-017-14) is unique, so set equality with the oracles is well defined.
- **Integer scaling:** rounding to cents can change the optimal set only when two closures differ by < 1 cent; the
  oracle comparisons use the same integer values, so exactness is unaffected.
- **Infeasible schedules:** a capacity too small to mine any unit gives a valid empty schedule with NPV 0; an
  infeasible MILP is reported with the solver status, never hidden.
- **No-data cells** are excluded from both surfaces' sums and counted; a polygon that covers only no-data cells is an
  error (FR-017-48).
- **Splats are not watertight:** the splat surface has holes at steep walls; the no-data fraction is reported with
  every splat volume.
- **Synthetic error is not field error:** the rendered flights lack lens distortion, motion blur and GNSS/IMU error
  unless added; the alignment uses exact camera centres, as a perfectly surveyed flight would.
- **Published `marvin` value:** if the own pit value and all three oracles agree on a value different from
  1,415,655,436, the report states that the published value is contradicted by three independent solvers.

### Assumptions and constants
- Pinned at specification (read 2026-10-07, MineLib instance page `minelib.org/v1/marvin.xhtml`): block size
  30 × 30 × 30 m; precedence of 8 levels at 45°; mine capacity < 60 Mt and processing capacity < 20 Mt (CPIT);
  best-known UPIT 1,415,655,436, CPIT 820,726,048 (LP gap 5.0 %), PCPSP 885,968,070 (LP gap 2.8 %); files
  `marvin.blocks`, `.prec`, `.upit`, `.cpit`, `.pcpsp`; the block count is not stated on the page and is read from the
  file. The licence (CC BY-SA 3.0) is stated on the MineLib home page, not on the instance page.
- `oreblocks` 0.5.2 deposits carry their own precedence and stamped exact optima; E1 checks that FR-017-12 at λ = 1
  reproduces the deposit's block values in cents (T-017-021) before shells are computed from them.
- UNVERIFIED, with oracles that do not depend on them: the Morrell constants (0.295, 10⁶, 4) and all comminution
  indices (the meta-model oracle is the chain itself, whatever its constants); Lane's formulas (not used by an oracle);
  the customary ramp grade; per-project 3DEP vertical accuracy (read from metadata); the SPZ size ratio ("about 10×"
  smaller; the size is measured); whether gradient-boosted trees convert to ONNX in the lock (eligibility rule of
  FR-017-04).

## 8. Clarifications log
- Python min-cut ownership: the M18 page mentions an own Python min-cut in the studio stage and a small min-cut in
  `minephys.planning`, while spec 018's engine table names `minephys.planning` as the Python reference → resolved: one
  Python implementation, the `minephys.planning` min-cut, used by E1, `st20_pit_design` and the browser parity
  fixtures (simplicity principle), with the E1 scale of NFR-017-03 and NFR-017-06. Reported to the coordinator so that
  the `minephys` planning spec covers ≥ 10⁵ blocks and the minimal-closure output.
- Canonical pit (not fixed in the docs) → resolved: the minimal maximum closure (FR-017-14), unique and returned by
  networkx and OR-Tools source sides.
- Precedence pattern (docs: "fixed in the spec") → resolved: level-cone generator with m levels, default 1:5
  (FR-017-13); oreblocks and MineLib keep their own arcs.
- Meta-model family choice (docs: "fixed in the planning-survey spec") → resolved: FR-017-04.
- "Held-out sweeps" → resolved: a sweep is one ore × circuit configuration; R² pooled over held-out sweeps is the
  acceptance (SC-017-01), the per-sweep distribution is reported (FR-017-05).
- MILP size → resolved: bench-phase units with ≤ 2 × 10⁵ binaries (FR-017-18, FR-017-28); block-level MILPs only on
  tiny instances.
- Reconstruction-to-surface route (docs: "fixed in the spec") → resolved: COLMAP dense stereo surface as the primary
  photogrammetric surface, the splat-mean surface as the second, both reported (FR-017-37, FR-017-38); no "better"
  claim without the decision rule (FR-017-40).
- Real-volume area of interest → resolved: the Tang & Werner polygon intersected with the query box (FR-017-34).
- Browser caps follow spec 018's engine table (`mincut` ≤ 10⁵ blocks; `volume` grid ≤ 2,048 × 2,048, polygon ≤ 10⁴
  vertices).
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

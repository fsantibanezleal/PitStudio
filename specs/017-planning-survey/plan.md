# Plan 017 — Planning and survey: mine-to-mill meta-model, ultimate pit and scheduling, splat survey and volumes
Spec: ./spec.md

## Summary
Three independent components, each with an exact or analytical reference:
1. **D2 mine-to-mill** (`src/pitstudio/cases/d2/chain.py` over `minephys`; `pitstudio_pipeline.mine_to_mill.{sweeps,
   train, evaluate, export}`): chain, Sobol sweeps split by configuration, GBM / MLP with a pre-registered selection
   rule, held-out R², optimisation gap → FR-017-01…11, P-017-17…19, SC-017-01, SC-017-02.
2. **E1 planning** (`src/pitstudio/planning/{bev, precedence, shells, pushbacks, checker}.py` with the
   `minephys.planning` min-cut; `pitstudio_pipeline.planning.{schedule, minelib}`): block values, precedence, minimal
   closure, oracles, shells, pushbacks, HiGHS schedule, checker → FR-017-12…29, P-017-01…09, SC-017-03…05.
3. **E2 survey** (`src/pitstudio/survey/{difference, uncertainty, polygon, meshvolume, align, grid}.py`;
   `pitstudio_studio.survey.{dem_prepare, colmap, brush, splat}`): DEM differencing, grid preparation, uncertainty,
   known-volume scene, reconstruction, splat packaging, honest fallbacks → FR-017-30…51, P-017-10…16, SC-017-06.

## Technical context
Runtime: Python 3.14 — root environment (numpy-only cores, `minephys`), `pipeline/` (scikit-learn 1.9.1, PyTorch,
ONNX Runtime 1.30, networkx 3.7, SciPy 1.18, `oreblocks` 0.5.2, pooch) and `studio/` (OR-Tools 9.15.6755, rasterio,
pyproj, shapely, trimesh, usd-core) · external portable tools COLMAP 4.2.1 and Brush v0.3.0 (SHA-256 pinned), npm tool
`@playcanvas/splat-transform` 3.9.0 (project-local, locked) · Node 24 web (spec 018 engines `comminution`,
`meta-model`, `mincut`, `volume`; Spark for the splat route) · targets: CPU for all of D2 and E1, GPU for COLMAP dense
stereo and Brush, GitHub Pages. Python tests live in `tests/<level>/`; tests needing `pipeline/` or `studio/`
packages use `pytest.importorskip` in the root job and run in the `pipeline/` job or the `studio/` CPU job
(T-011-002, T-017-002).

Dependencies to resolve and lock before feature code (task T-017-002):

| Package | Environment | Purpose | If it does not resolve |
|---|---|---|---|
| `highspy` 1.15.1 (MIT) | `pipeline/` | MILP schedules (FR-017-18) | `scipy.optimize.milp` (HiGHS inside SciPy 1.18, already locked), recorded as the solver |
| an `ai.onnx.ml` tree converter for `HistGradientBoostingRegressor` (`skl2onnx`, Apache-2.0) | `pipeline/` | GBM export (FR-017-04, FR-017-07) | trees are ineligible; the MLP is the meta-model (rule FR-017-04) |
| COLMAP 4.2.1 portable CUDA build, Brush v0.3.0 binary | external, per user | reconstruction (FR-017-37, FR-017-38) | "Not run" paths of FR-017-43 and FR-017-45; DEM differencing unaffected |

## Constitution check
| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | yes | real 3DEP DEMs and the real excavated volume; `oreblocks` synthetic deposits with exact optima; optional real-format MineLib benchmark; D2 labelled "calibrated synthetic" (FR-017-51) |
| Spec before code | yes | every behaviour has an id |
| Acceptance-test-first | yes | each task in `tasks.md` is a `[red]`/`[green]` pair with its own test file |
| Independent oracles | yes | networkx, OR-Tools and SciPy max flow; `oreblocks` stamped optima; MineLib published value; exhaustive enumeration for tiny schedules; hand calculations (Bond, min-cut, cut-off, NPV); closed-form volumes (frustum, trapezoidal prism, polyhedra); the midpoint-rule error bound; ONNX Runtime CPU vs the Python model |
| Determinism & explicit tolerances | yes | exact integer arithmetic for min-cut; exactly rounded sums for volumes; seeded Sobol, bootstrap and sensor noise |
| Neutral contracts | yes | DC-017-01…05 under `contracts/`, types generated (T-017-001); meta-model IO via DC-011-02 |
| Static delivery | yes | live chain, meta-model, min-cut and polygon volume; baked shells, schedules, volumes and the splat as T0 / REPLAY |
| Honesty | yes | extrapolation label (FR-017-09); "Not run" for MineLib, Brush, RTX camera, datum mismatch and failed reconstructions; "measurement, not validation" for the real volume; splat badge |
| Licence hygiene | yes | MineLib raw files never committed, derived layers CC BY-SA 3.0 in separate entries; 3DEP public domain with attribution; COLMAP and Brush external, never vendored |
| Simplicity | yes | one Python min-cut (`minephys.planning`) for E1, the pit design and the parity fixtures; one volume function for real, synthetic and web |

## Design

![Minimum cut selects the pit](../../docs/assets/diagrams/pit-optimisation-mincut.svg)
![Comminution circuit](../../docs/assets/diagrams/comminution-circuit.svg)

| Component | Module (planned) | Requirements |
|---|---|---|
| D2 chain composition | `src/pitstudio/cases/d2/chain.py` | FR-017-01, P-017-17 |
| Sweeps and splits | `pitstudio_pipeline.mine_to_mill.sweeps` (`s05_synthesize`) | FR-017-02, FR-017-10, P-017-19, DC-017-01 |
| Families, selection, evaluation, export | `pitstudio_pipeline.mine_to_mill.{train, select, evaluate, export}` | FR-017-03…07, FR-017-11, P-017-18 |
| D2 web behaviour | `web/src/cases/d2/` on engines `comminution` and `meta-model` | FR-017-08, FR-017-09, FR-017-11 |
| Block values and precedence | `src/pitstudio/planning/{bev, precedence}.py` | FR-017-12, FR-017-13, P-017-06 |
| Ultimate pit | `minephys.planning` min-cut, wrapped by `src/pitstudio/planning/pit.py` | FR-017-14, FR-017-15, P-017-01…05 |
| Shells and pushbacks | `src/pitstudio/planning/{shells, pushbacks}.py` | FR-017-16, FR-017-17, P-017-03, P-017-09 |
| Scheduler and checker | `pitstudio_pipeline.planning.schedule` (HiGHS), `src/pitstudio/planning/checker.py` | FR-017-18…20, FR-017-28, P-017-07, P-017-08 |
| Block-model loaders | `pitstudio_pipeline.planning.{oreblocks_io, minelib}` | FR-017-23, FR-017-24, FR-017-27, DC-017-02 |
| E1 web behaviour | `web/src/cases/e1/` on engine `mincut` | FR-017-25, FR-017-26 |
| DEM differencing, uncertainty, polygon | `src/pitstudio/survey/{difference, uncertainty, polygon}.py` | FR-017-30, FR-017-33, FR-017-47, FR-017-48, P-017-10…14 |
| Grid preparation | `pitstudio_studio.survey.dem_prepare` (rasterio) | FR-017-31, FR-017-32, FR-017-34 |
| Known-volume scene | `src/pitstudio/survey/meshvolume.py` + the scene recipe (spec 004 builds the USD) | FR-017-35, P-017-15 |
| Reconstruction | `pitstudio_studio.survey.{colmap, brush, splat}`, `src/pitstudio/survey/{align, grid}.py` | FR-017-36…45, FR-017-49, FR-017-50, P-017-16 |
| E2 web behaviour | `web/src/cases/e2/` on engine `volume` and the Spark route | FR-017-41, FR-017-46, FR-017-47 |

Data flow (E1): `s05_synthesize` (`oreblocks`) / `s00_download` → `s10_preprocess` (MineLib) → DC-017-02 → pit, shells,
pushbacks → schedule → DC-017-03 → `st20_pit_design`, routing (spec 007), web. Data flow (E2): `st10_terrain`
(DEMs) → `dem_prepare` → differencing → DC-017-04; `st53_sensors` S2 → DC-017-05 → `st58b_capture_splat` → surfaces →
`s50_evaluate` → DC-017-04 → web.

### Interfaces and their hostile-input requirements
| Interface | Kind | Hostile requirement |
|---|---|---|
| Sweep configuration | file + function | FR-017-10 |
| Meta-model input (Python, ONNX, web) | function + UI | FR-017-11, FR-017-09 |
| Block model and MineLib files | file input | FR-017-27, FR-017-24 |
| Shell and schedule configuration | file + function | FR-017-28 |
| E1 revenue-factor slider / block-model size | UI control | FR-017-26 + FR-018-41 |
| DEM pair (datum, grid) | file input | FR-017-32, FR-017-48 |
| Polygon (Python, web) | function + UI | FR-017-47 |
| External tools and their outputs | stage | FR-017-42…45, FR-017-49 |
| GPU stages | runner | FR-017-50 |

### Numerical cores and their metamorphic relations
| Core | Relations (≥ 3) |
|---|---|
| Min-cut / closure | P-017-03 (nesting), P-017-04 (value and cost monotonicity), P-017-05 (scaling, relabelling), P-017-02 (closure), P-017-01 (oracle) |
| Block value | P-017-06 (λ and grade monotonicity, hand values) + the λ = 1 reproduction check |
| Scheduler | P-017-07 (feasibility, NPV recomputation), P-017-08 (capacity monotonicity), FR-017-20 (enumeration) |
| Pushbacks | P-017-09 (partition, prefix = shell) + T_min rule by hand |
| DEM differencing | P-017-10 (prism), P-017-11 (swap), P-017-12 (partition), P-017-13 (midpoint bound), P-017-14 (offset, scaling) |
| Mesh volume and alignment | P-017-15 (closed forms, translation, k³), P-017-16 (known transform, permutation) |
| Chain and R² | P-017-17 (identities, monotonicity), P-017-18 (R² invariances) |

### Tolerances and their justification
- **Exact (min-cut, closure, shells, pushbacks):** integer capacities in int64; the minimal closure is unique; no
  floating point enters the decision. Values in the browser stay below 2⁵³ (FR-017-27), so binary64 integers are exact.
- **NPV rtol 1e-12** (P-017-07): the property instances have ≤ 300 units, so the scheduler's plain binary64 sum carries
  ≤ 300 × 1.1e-16 ≈ 3.3e-14 error relative to Σ\|CF\| against the exactly rounded recomputation (`math.fsum`); the
  generator keeps \|NPV\| ≥ 0.1 Σ\|CF\| (instances outside that bound are discarded), so cancellation amplifies the
  error at most tenfold, to 3.3e-13, and 1e-12 fails only on a modelling error.
- **Volumes:** exactly rounded sums (`math.fsum`) make P-017-11 exact and the others one rounding per cell (stated in
  each row); the browser mirrors the exactly rounded sum, so FR-018-51's tolerance applies.
- **Midpoint-rule bound** (P-017-13): the classical composite-midpoint error bound in two dimensions; analytic, no
  tuning.
- **Mesh volume rtol 1e-12** (P-017-15): a closed mesh of ≤ 10⁴ triangles sums signed tetrahedron volumes; the
  binary64 error is ≤ 10⁴ × 2.2e-16 ≈ 2e-12 relative before cancellation; meshes in the test have ≤ 10³ faces.
- **Umeyama rtol 1e-9** (P-017-16): an SVD of a 3 × 3 covariance in binary64 is backward stable to ≈ 1e-15; 1e-9
  covers ill-conditioned but non-degenerate point sets (condition number ≤ 10⁵ in the generator).
- **Chain identities rtol 1e-12** (P-017-17): closed forms of ≤ 20 operations.
- **Meta-model parity** (SC-017-02): `models.onnx_cpu_fp32`; browser parity FR-018-57.

## Test strategy
| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-017-01 | unit | Bond hand calculations of §7 through the chain with the PBM and crusher in pass-through configuration; t/h × kWh/t = η P_mill | pytest |
| FR-017-02, FR-017-10 | unit (hostile for 10) | seeded Sobol determinism (P-017-19); disjoint splits; invalid configurations written in the test | pytest, Hypothesis |
| FR-017-03, FR-017-04 | pipeline | selection decisions on fixture validation scores (including the tie and the ineligible-tree cases) | pytest |
| FR-017-05 | pipeline | R² by hand on 5 points; pooled vs per-sweep on a 2-sweep fixture | pytest |
| FR-017-06 | pipeline | a fixture meta-model equal to the chain gives a gap of 0; one with a known offset gives the hand-computed gap | pytest |
| FR-017-07 | pipeline | ONNX Runtime CPU fp32 against the Python model (reference implementation) on 200 golden inputs | pytest |
| FR-017-08, FR-017-09 | E2E | fixture values and labels written in the test | Playwright |
| FR-017-11 | unit + web (hostile) | invalid rows written in the test | pytest, Vitest |
| FR-017-12 | unit | hand calculations (planning page worked examples; break-even cut-off 0.147 % Cu) | pytest |
| FR-017-13 | unit | hand-counted 1:5 pattern on cubic blocks at 45°; the 3 × 3 pattern at a flatter angle | pytest |
| FR-017-14 | unit | the four-block example (+5 → all four, value 2; +2 → empty, value 0); the λ example (full pit from λ = 2/3) | pytest |
| FR-017-15 | pipeline + unit | networkx `minimum_cut`, SciPy `maximum_flow` (pipeline env) and OR-Tools `SimpleMaxFlow` (studio env) as reference implementations, with infinite precedence capacities represented as Σ\|v\| + 1 (a cut through such an arc can never be minimal); `oreblocks` stamped optima | pytest, Hypothesis |
| FR-017-16, FR-017-17 | unit | hand-built 2-D deposits with known shells; the T_min rule by hand | pytest |
| FR-017-18 | pipeline | the planning page's formulation written independently in the test as a dense matrix for a 4-unit instance; solver status values | pytest |
| FR-017-19 | unit | schedules violating each constraint once (each must be rejected) | pytest |
| FR-017-20 | unit | exhaustive enumeration of all assignments (≤ 4⁸ = 65,536) | pytest |
| FR-017-21, FR-017-22 | pipeline + contract | strip ratios and NPV by hand on a fixture; DC-017-03 validation | pytest + jsonschema |
| FR-017-23 | pipeline | the published best-known UPIT value of the MineLib `marvin` page (1,415,655,436) | pytest |
| FR-017-24, FR-017-27, FR-017-28 | pipeline / unit (hostile) | invalid files and configurations built by the test; a host stub that refuses connections | pytest |
| FR-017-25, FR-017-26 | E2E | fixture deposits below and above 10⁵ blocks | Playwright |
| FR-017-29 | E2E | fixture with and without Composer captures | Playwright |
| FR-017-30 | unit | hand calculation on 3 × 3 grids; P-017-10…14 | pytest, Hypothesis |
| FR-017-31, FR-017-32 | pipeline (studio env) | synthetic GeoTIFFs with known CRS, datum and RMSEz built by the test; a datum mismatch with and without a declared offset | pytest |
| FR-017-33 | unit | the two bounds by hand for N = 4 cells | pytest |
| FR-017-34 | pipeline | a fixture polygon pair with a known overlap ratio; contract of the result | pytest |
| FR-017-35 | unit | closed forms: frustum V = πh(R² + Rr + r²)/3, trapezoidal prism V = L h (b₁ + b₂)/2; divergence-theorem mesh volume (P-017-15) | pytest |
| FR-017-36 | contract | DC-017-05 valid and invalid flight records | pytest + jsonschema |
| FR-017-37, FR-017-38 | unit (fake tools) + gpu | fake COLMAP / Brush binaries emitting known outputs; Umeyama on known transforms (P-017-16); per-cell median gridding by hand on a 2 × 2 grid | pytest |
| FR-017-39 | pipeline | contract of the per-flight block; volume error by hand on a fixture | pytest |
| FR-017-40 | unit | paired bootstrap bounds from injected resamples (numpy) | pytest |
| FR-017-41, FR-017-49 | pipeline + E2E (hostile for 49) | a fixture PLY above the cap (pruning count by hand); malformed PLY / SPZ files | pytest, Playwright |
| FR-017-42…45 | unit (fake tools) | fake binaries with wrong SHA-256, failing smoke, 70 % registration, large alignment RMSE; RTX probe stub | pytest |
| FR-017-46, FR-017-47 | E2E + unit (hostile for 47) | fixture polygon volumes from the Python reference; invalid polygons written in the test | Playwright, pytest |
| FR-017-48 | unit (hostile) | mismatched surfaces written in the test | pytest |
| FR-017-50 | unit (fake GPU) + gpu | the runner's fake GPU backend and fake tool binaries (lock held, hold file, timeout, OOM) | pytest |
| FR-017-51 | contract | manifests against `contracts/manifest.schema.json`; label strings; separate CC BY-SA entries | pytest |
| P-017-01…P-017-19 | property / metamorphic | the relations and references named in the spec | Hypothesis |
| NFR-017-01, NFR-017-05 | pipeline + E2E | file sizes; request log of the first view | pytest, Playwright |
| NFR-017-02…04 | E2E (forced T2) | lane-measurement suite (spec 018) | Playwright |
| NFR-017-06, NFR-017-07 | unit | manifest fields recorded | pytest |
| SC-017-01, SC-017-02 | pipeline | report logic on fixture results that pass and fail by construction; as FR-017-07 | pytest |
| SC-017-03…05 | pipeline / unit | as FR-017-15, FR-017-19, FR-017-23 | pytest |
| SC-017-06 | pipeline | the report has one row per design and seed and no pass field | pytest |
| DC-017-01…05 | contract | valid and invalid example documents per schema | pytest + jsonschema |

### Threshold keys requested (`thresholds.yaml`, ratchet-only; proposed keys, pending maintainer approval)
`models.meta_model_r2_min: 0.95`, `models.meta_model_onnx_bytes_max: 1000000`,
`web.mincut_blocks_live_max: 100000`, `survey.splat_bytes_max: 25000000`.

## Risks and complexity tracking
| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Bench-phase units for the MILP | 10⁵ blocks × 20 periods is 2 × 10⁶ binaries | block-level MILP: intractable on the reference machine within a baked-run budget |
| Two reconstruction surfaces (photogrammetric, splat) | the docs leave the route open, and only the splat surface measures what 3DGS adds | splat only: holes at steep walls bias the volume; photogrammetry only: 3DGS would carry no measured role |
| Oracles split across `pipeline/` and `studio/` | networkx and SciPy are locked in `pipeline/`, OR-Tools in `studio/` | adding OR-Tools to `pipeline/`: a second copy of a large wheel for one test |
| Umeyama alignment to true camera centres | rendered flights have exact poses, as a surveyed flight would | ground control points: would add a second synthetic step without a measured benefit |

# Tasks 017 — Planning and survey: mine-to-mill meta-model, ultimate pit and scheduling, splat survey and volumes
Format: `- [ ] T-NNN-xxx [US-NNN-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/017-planning-survey/tests.lock <files>`).
Order: D2 and E1 run entirely on the CPU and come first; E2's DEM differencing and real volume precede the GPU
reconstruction work.

## Phase 1 — Setup
- [ ] T-017-001 (DC-017-01, DC-017-02, DC-017-03, DC-017-04, DC-017-05) schemas `comminution-sweep`, `block-model`, `pit-shells`, `survey-volume`, `survey-flight` + generated Pydantic and TypeScript types — test: tests/contract/test_t_017_001_planning_survey_schemas.py
- [ ] T-017-002 dependency validation: lock `highspy` in `pipeline/` (else record `scipy.optimize.milp`), try a tree-to-ONNX converter (else trees ineligible), pin the COLMAP and Brush binaries by SHA-256, lock `@playcanvas/splat-transform` 3.9.0; make the `pipeline/` job collect `tests/pipeline/test_t_017_*` and the `studio/` CPU job (T-011-002) the OR-Tools and rasterio tests — test: tests/pipeline/test_t_017_002_env_smoke.py

## Phase 2 — US-017-1 (P1) Mine-to-mill
- [ ] T-017-010 [US-017-1] (FR-017-01, P-017-17) D2 chain composition and identities — test: tests/unit/test_t_017_010_d2_chain.py
- [ ] T-017-011 [US-017-1] (FR-017-02, FR-017-10, P-017-19) Sobol sweeps, configuration split, knowledge-table links, hostile configurations — test: tests/unit/test_t_017_011_sweeps.py
- [ ] T-017-012 [US-017-1] (FR-017-03, FR-017-04) GBM and MLP training and the selection rule — test: tests/pipeline/test_t_017_012_meta_model_selection.py
- [ ] T-017-013 [US-017-1] (FR-017-05, FR-017-06, P-017-18, SC-017-01) held-out R², per-sweep distribution, monotonicity pass rates, optimisation gap, acceptance statement — test: tests/pipeline/test_t_017_013_meta_model_evaluate.py
- [ ] T-017-014 [US-017-1] (FR-017-07, SC-017-02, NFR-017-01) export, IO description, parity — test: tests/pipeline/test_t_017_014_meta_model_export.py
- [ ] T-017-015 [US-017-1] (FR-017-11) hostile meta-model inputs in Python and in the web engine — test: tests/pipeline/test_t_017_015_meta_model_guards.py, web/src/cases/d2/metaModelGuards.test.ts
- [ ] T-017-016 [US-017-1] (FR-017-08, FR-017-09, NFR-017-02) D2 Simulate: chain and meta-model side by side, R² badge, labels, batch rate — test: web/e2e/d2-simulate.spec.ts

## Phase 3 — US-017-2 (P1) Ultimate pit
- [ ] T-017-020 [US-017-2] (FR-017-12, FR-017-13, P-017-06) block values, integer scaling, precedence generator — test: tests/unit/test_t_017_020_bev_precedence.py
- [ ] T-017-021 [US-017-2] (FR-017-14, P-017-02, P-017-04, P-017-05) minimal maximum closure through `minephys.planning`; closure, monotonicity, scaling, relabelling; λ = 1 reproduction of `oreblocks` values — test: tests/property/test_t_017_021_closure.py
- [ ] T-017-022 [US-017-2] (FR-017-15, P-017-01, SC-017-03) agreement with networkx and SciPy and with the stamped `oreblocks` optima — test: tests/pipeline/test_t_017_022_mincut_oracles.py
- [ ] T-017-023 [US-017-2] (FR-017-15, SC-017-03) agreement with OR-Tools `SimpleMaxFlow` (studio environment) — test: tests/pipeline/test_t_017_023_mincut_ortools.py
- [ ] T-017-024 [US-017-2] (FR-017-16, FR-017-17, P-017-03, P-017-09) shells over the λ grid and the pushback rule — test: tests/property/test_t_017_024_shells_pushbacks.py
- [ ] T-017-025 [US-017-2] (FR-017-23, FR-017-24, SC-017-05) optional MineLib `marvin`: value check, share-alike handling, "Not run" paths — test: tests/pipeline/test_t_017_025_minelib_marvin.py
- [ ] T-017-026 [US-017-2] (FR-017-27) hostile block-model and MineLib files — test: tests/unit/test_t_017_026_block_model_guards.py
- [ ] T-017-027 [US-017-2] (FR-017-25, FR-017-26, NFR-017-03) E1 revenue-factor slider, live cap and baked fallback — test: web/e2e/e1-revenue-factor.spec.ts
- [ ] T-017-028 [US-017-2] (NFR-017-06) Python min-cut wall time recorded per baked instance — test: tests/unit/test_t_017_028_mincut_timing_record.py

## Phase 4 — US-017-3 (P2) Schedule
- [ ] T-017-030 [US-017-3] (FR-017-18, FR-017-28) bench-phase units, HiGHS formulation, solver status, hostile configurations — test: tests/pipeline/test_t_017_030_schedule.py
- [ ] T-017-031 [US-017-3] (FR-017-19, P-017-07, SC-017-04) independent schedule checker and NPV recomputation — test: tests/property/test_t_017_031_schedule_checker.py
- [ ] T-017-032 [US-017-3] (FR-017-20, P-017-08) tiny-instance exactness by enumeration; capacity monotonicity — test: tests/pipeline/test_t_017_032_schedule_enumeration.py
- [ ] T-017-033 [US-017-3] (FR-017-21, FR-017-22) E1 KPIs and the shell / schedule hand-off contract — test: tests/contract/test_t_017_033_e1_outputs.py
- [ ] T-017-034 [US-017-3] (FR-017-29) optional Composer review captures and their "Not run" state — test: web/e2e/e1-composer-captures.spec.ts

## Phase 5 — US-017-4 (P1) Survey volume
- [ ] T-017-040 [US-017-4] (FR-017-30, FR-017-48, P-017-10, P-017-11, P-017-12, P-017-13, P-017-14) DEM differencing, exactly rounded sums, hostile surfaces — test: tests/property/test_t_017_040_dem_difference.py
- [ ] T-017-041 [US-017-4] (FR-017-33) uncertainty bounds — test: tests/unit/test_t_017_041_volume_uncertainty.py
- [ ] T-017-042 [US-017-4] (FR-017-31, FR-017-32) grid preparation: CRS, datum, reprojection, datum mismatch — test: tests/pipeline/test_t_017_042_dem_prepare.py
- [ ] T-017-043 [US-017-4] (FR-017-34) real Bingham 2018 → 2023 volume over the area of interest — test: tests/pipeline/test_t_017_043_bingham_volume.py
- [ ] T-017-044 [US-017-4] (FR-017-35, P-017-15) known-volume scene: closed forms, mesh volume, gridding floor — test: tests/property/test_t_017_044_known_volume_scene.py
- [ ] T-017-045 [US-017-4] (FR-017-36) survey flight records — test: tests/contract/test_t_017_045_survey_flights.py
- [ ] T-017-046 [US-017-4] (FR-017-37, FR-017-38, P-017-16) reconstruction route with fake COLMAP and Brush binaries; Umeyama; per-cell gridding; GPU smoke — test: tests/unit/test_t_017_046_reconstruction.py, tests/gpu/test_t_017_046_reconstruction_smoke.py
- [ ] T-017-047 [US-017-4] (FR-017-39, FR-017-40, SC-017-06) per-flight metrics and paired comparisons — test: tests/pipeline/test_t_017_047_survey_report.py
- [ ] T-017-048 [US-017-4] (FR-017-42, FR-017-43, FR-017-44, FR-017-45) tool verification and the "Not run" / "failed" paths — test: tests/unit/test_t_017_048_tool_guards.py
- [ ] T-017-049 [US-017-4] (FR-017-41, FR-017-49, NFR-017-05) splat packaging, pruning to the cap, hostile PLY / SPZ, badge and route-only loading — test: tests/pipeline/test_t_017_049_splat_package.py, web/e2e/e2-splat-view.spec.ts
- [ ] T-017-050 [US-017-4] (FR-017-50, NFR-017-07) GPU stages under the runner against the fake GPU backend; time recorded — test: tests/unit/test_t_017_050_survey_fake_gpu.py

## Phase 6 — US-017-5 (P2) Polygon volume in the browser
- [ ] T-017-060 [US-017-5] (FR-017-46, FR-017-47, NFR-017-04) E2 polygon tool, hostile polygons, lane gate — test: tests/unit/test_t_017_060_polygon_guards.py, web/e2e/e2-polygon-volume.spec.ts

## Phase 7 — Labels and manifests
- [ ] T-017-070 (FR-017-51) manifests, synthetic labels, separate CC BY-SA entries, real-volume attribution — test: tests/contract/test_t_017_070_planning_survey_manifests.py

## Phase 8 — Polish and independent review
- [ ] T-017-090 mutation run on `src/pitstudio/planning/`, `src/pitstudio/survey/` and `src/pitstudio/cases/d2/`; record the scores
- [ ] T-017-091 independent review of the diff against this spec; append tasks for gaps

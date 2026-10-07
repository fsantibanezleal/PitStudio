# Tasks 010 — Slope stability and time to failure (case C1)
Format: `- [ ] T-NNN-xxx [US-NNN-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/010-slope/tests.lock <files>`).
Order: C1 is part of the first vertical slice (with A1); phases 1–4 and 6 come before any NVIDIA-runtime work.

## Phase 1 — Setup
- [ ] T-010-001 (DC-010-01, DC-010-02, DC-010-03, DC-010-04) schemas `slope-section`, `displacement-series`, `ttf-results`, `slope-results` + generated Pydantic and TypeScript types — test: tests/contract/test_t_010_001_slope_schemas.py
- [ ] T-010-002 dependency validation: resolve and lock `chronos-forecasting` in `pipeline/`; set up the pySlope 1.4.0 oracle (oracle-only group, else the isolated `tests/oracles/pyslope/` project on uv-managed Python 3.12, else committed pySlope goldens with script, version and SHA-256); make the `pipeline/` CI job collect `tests/pipeline/test_t_010_*` — test: tests/pipeline/test_t_010_002_oracle_env.py
- [ ] T-010-003 [US-010-5] (FR-010-40) C1 recipe parameters from the §7 table as recipe defaults; `studio plan` rejects invalid C1 recipes — test: tests/unit/test_t_010_003_c1_recipe.py

## Phase 2 — US-010-1 (P1) Wall stability
- [ ] T-010-010 [US-010-1] (FR-010-01, FR-010-09, P-010-03, P-010-06) circle search, Bishop and Spencer composition, rejection rules — test: tests/unit/test_t_010_010_lem_search.py
- [ ] T-010-011 [US-010-1] (FR-010-02) Hoek–Brown per-slice conversion iterated with F — test: tests/unit/test_t_010_011_hoek_brown_slices.py
- [ ] T-010-012 [US-010-1] (SC-010-05) Bishop against the pySlope 1.4.0 oracle on the shared planar cases — test: tests/pipeline/test_t_010_012_pyslope_oracle.py
- [ ] T-010-013 [US-010-1] (P-010-01, P-010-02, P-010-04, P-010-05) LEM metamorphic relations — test: tests/metamorphic/test_t_010_013_lem_relations.py
- [ ] T-010-014 [US-010-1] (FR-010-07) hostile sections — test: tests/unit/test_t_010_014_section_guards.py
- [ ] T-010-015 [US-010-1] (FR-010-03, FR-010-08, P-010-07) candidate-set PoF, Wilson interval, sampling guards — test: tests/property/test_t_010_015_pof.py
- [ ] T-010-016 [US-010-1] (FR-010-06) reference sections from the Bingham and Hambach DEMs — test: tests/pipeline/test_t_010_016_sections_from_dem.py
- [ ] T-010-017 [US-010-1] (FR-010-04, FR-010-05, FR-010-10) C1 Simulate tab: PoF labels, UNVERIFIED acceptance inputs, hostile controls and query — test: web/e2e/c1-simulate.spec.ts
- [ ] T-010-018 [US-010-1] (FR-010-01, FR-010-03) C1 golden scenarios for the `geotech` parity fixture of spec 018 (≥ 200 vectors per function, both ends of every range, no sample with \|F − 1\| < 1e-9, best and second-best circle gap ≥ 1e-9 F) — test: tests/parity/test_t_010_018_geotech_goldens.py

## Phase 3 — US-010-2 (P1) Forecasters against inverse velocity
- [ ] T-010-020 [US-010-2] (FR-010-11, FR-010-16) seeded Voight events, strata, splits, configuration guards — test: tests/unit/test_t_010_020_voight_events.py
- [ ] T-010-021 [US-010-2] (FR-010-12, P-010-11) SNR estimator — test: tests/property/test_t_010_021_snr.py
- [ ] T-010-022 [US-010-2] (FR-010-17) nominal-SNR fallback and "not run" statement — test: tests/unit/test_t_010_022_snr_fallback.py
- [ ] T-010-023 [US-010-2] (FR-010-18, P-010-08) shared preprocessor — test: tests/property/test_t_010_023_preprocess.py
- [ ] T-010-024 [US-010-2] (FR-010-19, FR-010-20, P-010-12) inverse-velocity and Bayesian baselines — test: tests/unit/test_t_010_024_iv_bayes.py
- [ ] T-010-025 [US-010-2] (P-010-09, P-010-10) time and displacement invariances of every method — test: tests/metamorphic/test_t_010_025_ttf_invariance.py
- [ ] T-010-026 [US-010-2] (FR-010-22, P-010-13) TTF read-out — test: tests/property/test_t_010_026_readout.py
- [ ] T-010-027 [US-010-2] (FR-010-21) TCN, PatchTST and Chronos-Bolt arms: inputs, outputs, splits, pinball loss — test: tests/pipeline/test_t_010_027_forecasters.py
- [ ] T-010-028 [US-010-2] (FR-010-29) hostile forecaster contexts in Python and in the C1 tab — test: tests/pipeline/test_t_010_028_window_guards.py, web/src/cases/c1/forecastGuards.test.ts
- [ ] T-010-029 [US-010-2] (FR-010-33) training under the runner: lock, hold, OOM fallback, CPU fallback — test: tests/unit/test_t_010_029_training_fake_gpu.py, tests/gpu/test_t_010_029_training_smoke.py
- [ ] T-010-030 [US-010-2] (FR-010-23, FR-010-24) relative errors, lead time at alarm, median with bootstrap interval — test: tests/unit/test_t_010_030_ttf_metrics.py
- [ ] T-010-031 [US-010-2] (FR-010-25, FR-010-28, P-010-14, SC-010-02) paired bootstrap into the decision rule; n < 2 and unpaired guards — test: tests/unit/test_t_010_031_paired_decision.py
- [ ] T-010-032 [US-010-2] (FR-010-30, FR-010-31, SC-010-04, NFR-010-04, DC-010-05) export, parity, IO description, Chronos fallback — test: tests/pipeline/test_t_010_032_forecaster_export.py
- [ ] T-010-033 [US-010-2] (SC-010-01) acceptance statement per arm and cut-off on fixture results — test: tests/pipeline/test_t_010_033_acceptance_report.py
- [ ] T-010-034 [US-010-2] (FR-010-32, NFR-010-03, NFR-010-05) cut-off slider and forecaster lanes — test: web/e2e/c1-cutoff-slider.spec.ts

## Phase 4 — US-010-3 (P1) One real event
- [ ] T-010-040 [US-010-3] (FR-010-13, FR-010-14) de Wit ingestion and hostile archives — test: tests/pipeline/test_t_010_040_dewit_ingest.py
- [ ] T-010-041 [US-010-3] (FR-010-15) the real series never enters training, selection, C2ST or TSTR — test: tests/contract/test_t_010_041_dewit_exclusion.py
- [ ] T-010-042 [US-010-3] (FR-010-26, SC-010-03) descriptive real-event report — test: tests/unit/test_t_010_042_real_event_report.py
- [ ] T-010-043 [US-010-3] (FR-010-27) Charts real-event panel in EN and ES, fixed order, no highlight — test: web/e2e/c1-real-event.spec.ts

## Phase 5 — US-010-4 (P2) Line of sight
- [ ] T-010-050 [US-010-4] (FR-010-34, FR-010-36, P-010-15) radar-series builder and wrapping flag — test: tests/unit/test_t_010_050_radar_series.py
- [ ] T-010-051 [US-010-4] (FR-010-37) hostile radar configurations — test: tests/unit/test_t_010_051_radar_guards.py
- [ ] T-010-052 [US-010-4] (FR-010-35) S4b report — test: tests/pipeline/test_t_010_052_s4b_report.py
- [ ] T-010-053 [US-010-4] (FR-010-38) optional EGMS layer and its "not run" state — test: web/e2e/c1-scene-egms.spec.ts
- [ ] T-010-054 [US-010-4] (FR-010-41, P-010-16, P-010-17) S4b sign convention, phase law, keyed noise and temporal unwrapping — test: tests/metamorphic/test_t_010_054_radar_phase.py
- [ ] T-010-055 [US-010-4] (FR-010-42) hostile displacement fields, scan times, wavelength, noise and AR(1) inputs of the radar-series builder — test: tests/unit/test_t_010_055_radar_phase_guards.py

## Phase 6 — US-010-5 (P1) Reproduce on the open lane
- [ ] T-010-060 [US-010-5] (FR-010-39) C1 recipe end to end on the sample data (CPU) with valid manifests — test: tests/pipeline/test_t_010_060_c1_recipe_e2e.py
- [ ] T-010-061 [US-010-5] (NFR-010-01, NFR-010-02) live LEM and PoF lane gates on forced T2 — test: web/e2e/c1-lane-gates.spec.ts
- [ ] T-010-062 [US-010-5] (NFR-010-06) GPU-hours recorded for every training stage — test: tests/unit/test_t_010_062_budget_record.py

## Phase 7 — Polish and independent review
- [ ] T-010-090 mutation run on `src/pitstudio/slope/`; record the score (numerical-core threshold)
- [ ] T-010-091 independent review of the diff against this spec; append tasks for gaps

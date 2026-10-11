# Tasks 011 — Surrogates and calibration: GNS, differentiable DEM calibration, FNO
Format: `- [ ] T-NNN-xxx [US-NNN-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/011-surrogates/tests.lock <files>`).
Order: the numpy cores (graph, observables, calibration protocol) and the fake-simulator tests come first and run on
the CPU; GPU work starts only after the GPU hold is lifted and through the runner.

## Phase 1 — Setup
- [ ] T-011-001 (DC-011-01, DC-011-02, DC-011-03, DC-011-04) schemas `granular-rollout`, `surrogate-io`, `field-dataset`, `calibration-result` + generated Pydantic and TypeScript types — test: tests/contract/test_t_011_001_surrogate_schemas.py
- [ ] T-011-002 dependency validation: lock `cma` in `studio/` (else the own minimal CMA-ES), try `neuraloperator` 2.0.0 in `pipeline/` (optional); add a `studio/` CPU CI job (Warp CPU device, `cma`, OR-Tools) and make the `pipeline/` job collect `tests/pipeline/test_t_011_*` and `tests/property/test_t_011_05*` — test: tests/pipeline/test_t_011_002_env_smoke.py

## Phase 2 — US-011-1 (P1) GNS
- [ ] T-011-010 [US-011-1] (FR-011-01, P-011-01, P-011-02) GNS step: inputs, features, encode–process–decode, Euler update, equivariances — test: tests/pipeline/test_t_011_010_gns_model.py
- [ ] T-011-011 [US-011-1] (FR-011-02, FR-011-13, P-011-04) radius graph in Python and TypeScript, overflow counting — test: tests/property/test_t_011_011_radius_graph.py, web/src/engines/gns/radiusGraph.test.ts
- [ ] T-011-012 [US-011-4] (FR-011-07, P-011-05) padded-layout export, bench-only ScatterElements variant — test: tests/pipeline/test_t_011_012_gns_export.py
- [ ] T-011-013 [US-011-1] (FR-011-05, P-011-06, P-011-07) repose and run-out observables — test: tests/property/test_t_011_013_observables.py
- [ ] T-011-014 [US-011-1] (FR-011-03, FR-011-04) dataset families, geometry split, validation-only selection — test: tests/pipeline/test_t_011_014_gns_training.py
- [ ] T-011-015 [US-011-1] (FR-011-06, FR-011-10, SC-011-01) held-out evaluation, rest check, acceptance statement — test: tests/pipeline/test_t_011_015_gns_evaluate.py
- [ ] T-011-016 [US-011-4] (FR-011-08, SC-011-04, NFR-011-01) CPU fp32 parity and the fp16 rollout rule — test: tests/pipeline/test_t_011_016_gns_parity.py
- [ ] T-011-017 [US-011-1] (FR-011-12, P-011-03) rollout loop: divergence stop, conservation — test: tests/unit/test_t_011_017_rollout_guards.py
- [ ] T-011-018 [US-011-1] (FR-011-14) hostile rollout files — test: tests/pipeline/test_t_011_018_rollout_ingest.py
- [ ] T-011-019 [US-011-1] (FR-011-15) hostile GNS inputs in Python and in the web engine — test: tests/pipeline/test_t_011_019_gns_input_guards.py, web/src/engines/gns/inputGuards.test.ts
- [ ] T-011-020 [US-011-1] (FR-011-09, FR-011-11, NFR-011-02) A3 live GNS: worker graph, tier, baked reference, extrapolation label, step time — test: web/e2e/a3-gns-live.spec.ts
- [ ] T-011-021 [US-011-1] (FR-011-16) speed report — test: tests/pipeline/test_t_011_021_gns_speed_report.py

## Phase 3 — US-011-2 (P1) Calibration
- [ ] T-011-030 [US-011-2] (FR-011-18, P-011-08) smooth and hard heap observables — test: tests/property/test_t_011_030_heap_observables.py
- [ ] T-011-031 [US-011-2] (FR-011-22, P-011-09) seed-ensemble interval and its coverage on the fake simulator — test: tests/property/test_t_011_031_interval_coverage.py
- [ ] T-011-032 [US-011-2] (FR-011-23, P-011-10) gradient gate on the fake simulator — test: tests/property/test_t_011_032_gradient_gate.py
- [ ] T-011-033 [US-011-2] (FR-011-20, FR-011-21) CMA-ES arm, common budget and stopping — test: tests/unit/test_t_011_033_cmaes_arm.py
- [ ] T-011-034 [US-011-2] (FR-011-17, FR-011-19, P-011-11) tape arm on the Warp CPU device against the sliding-sphere closed form; determinism; CUDA smoke — test: tests/unit/test_t_011_034_tape_arm.py, tests/gpu/test_t_011_034_tape_cuda.py
- [ ] T-011-035 [US-011-2] (FR-011-24, FR-011-25, SC-011-02, SC-011-05) coverage study driver and paired comparisons — test: tests/pipeline/test_t_011_035_coverage_study.py
- [ ] T-011-036 [US-011-2] (FR-011-26, SC-011-06) calibration result reporting and gradient-reliability accounting — test: tests/contract/test_t_011_036_calibration_result.py
- [ ] T-011-037 [US-011-2] (FR-011-27) optional (μ_s, μ_r) arm and "weakly identified" labelling — test: tests/unit/test_t_011_037_secondary_arm.py
- [ ] T-011-038 [US-011-2] (FR-011-28) literature-target calibrations: UNVERIFIED propagation, provenance, no coverage claim — test: tests/unit/test_t_011_038_literature_targets.py
- [ ] T-011-039 [US-011-2] (FR-011-29, FR-011-30) non-differentiable solver refusal and hostile calibration requests — test: tests/unit/test_t_011_039_calibration_guards.py
- [ ] T-011-040 [US-011-2] (FR-011-31) A3 calibration replay view — test: web/e2e/a3-calibration-replay.spec.ts

## Phase 4 — US-011-3 (P1) FNO
- [ ] T-011-050 [US-011-3] (FR-011-32, P-011-12, P-011-13, P-011-14, P-011-15, P-011-16) DFT-matmul spectral layer — test: tests/property/test_t_011_050_dft_spectral.py
- [ ] T-011-051 [US-011-3] (FR-011-33) tailings and dust models, channels, direct map — test: tests/pipeline/test_t_011_051_fno_model.py
- [ ] T-011-052 [US-011-3] (FR-011-34, FR-011-41) field data, patch split, hostile field files — test: tests/pipeline/test_t_011_052_field_ingest.py
- [ ] T-011-053 [US-011-3] (FR-011-35, FR-011-42, SC-011-03) relative L2 per field, KPIs, volume error, resolution transfer — test: tests/pipeline/test_t_011_053_fno_evaluate.py
- [ ] T-011-054 [US-011-4] (FR-011-36, FR-011-37, SC-011-04, NFR-011-03) export, operator whitelist, parity, fp16 rule — test: tests/pipeline/test_t_011_054_fno_export.py
- [ ] T-011-055 [US-011-3] (FR-011-40) hostile FNO inputs in Python and in the web engine — test: tests/pipeline/test_t_011_055_fno_input_guards.py, web/src/engines/fno/inputGuards.test.ts
- [ ] T-011-056 [US-011-3] (FR-011-38, FR-011-39) C2 and C3 live controls, baked comparison, extrapolation label — test: web/e2e/c2-c3-fno-live.spec.ts
- [ ] T-011-057 [US-011-4] (FR-011-43) optional `neuraloperator` spectral parity — test: tests/pipeline/test_t_011_057_neuraloperator_parity.py

## Phase 5 — Shared
- [ ] T-011-060 [US-011-4] (FR-011-44) runner behaviour of training and calibration against the fake GPU backend; CUDA smoke — test: tests/unit/test_t_011_060_gpu_fake.py, tests/gpu/test_t_011_060_gpu_smoke.py
- [ ] T-011-061 [US-011-4] (FR-011-45) manifests and "calibrated synthetic" labels — test: tests/contract/test_t_011_061_surrogate_manifests.py
- [ ] T-011-062 [US-011-4] (NFR-011-04) GPU-hours recorded for every training and calibration stage — test: tests/unit/test_t_011_062_budget_record.py

## Phase 6 — Polish and independent review
- [ ] T-011-090 mutation run on `src/pitstudio/granular/`, `src/pitstudio/calibration/` and the spectral layer; record the scores
- [ ] T-011-091 independent review of the diff against this spec; append tasks for gaps

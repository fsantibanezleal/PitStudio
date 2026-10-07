# Tasks 016 — Export and acceleration: ONNX with parity, TensorRT engines with per-engine parity, budgets
Format: `- [ ] T-016-xxx [US-016-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/016-export-acceleration/tests.lock <files>`).

## Phase 1 — Setup
- [ ] T-016-000 resolve, lock and prove the validators (Khronos glTF Validator, 3D Tiles Validator; project-local npm) and, optionally, the TensorRT 10.14 libraries for the ONNX Runtime TensorRT provider in `pipeline/`; no feature code — test: none (setup evidence in the PR)
- [ ] T-016-001 (DC-016-01) bench-record schema + generated types — test: tests/contract/test_t_016_001_bench_record_schema.py
- [ ] T-016-002 (DC-016-02) release-asset list schema + generated types — test: tests/contract/test_t_016_002_release_assets_schema.py
- [ ] T-016-003 (DC-016-03, DC-000-01) parity-report schema + generated types; export fields of the manifest — test: tests/contract/test_t_016_003_parity_report_schema.py
- [ ] T-016-004 (DC-016-04) export-config schema + generated types — test: tests/contract/test_t_016_004_export_config_schema.py
- [ ] T-016-005 (DC-016-05) acceleration web-table schema + generated types — test: tests/contract/test_t_016_005_accel_table_schema.py

## Phase 2 — US-016-1 (P1) One checked ONNX file per model
- [ ] T-016-010 [US-016-1] (FR-016-01, FR-016-02, P-016-11, NFR-016-03) dynamo export, cleanup, IR pin, checks, determinism — test: tests/unit/test_t_016_010_onnx_export.py, tests/pipeline/test_t_016_010_export_determinism.py
- [ ] T-016-011 [US-016-1] (FR-016-03) reject hostile ONNX files at every consumer — test: tests/unit/test_t_016_011_onnx_file_guards.py
- [ ] T-016-012 [US-016-1] (FR-016-04, FR-016-39, P-016-01, P-016-02, P-016-03, P-016-04) layer-1 comparator and its fail-closed guard — test: tests/unit/test_t_016_012_parity_comparator.py, tests/metamorphic/test_t_016_012_comparator_metamorphic.py
- [ ] T-016-013 [US-016-1] (FR-016-05, FR-016-06, FR-016-07) post-processed graphs, golden sets and their guards — test: tests/unit/test_t_016_013_golden_sets.py
- [ ] T-016-014 [US-016-1] (SC-016-02) layer-1 acceptance on the parity reports — test: tests/pipeline/test_t_016_014_layer1_acceptance.py

## Phase 3 — US-016-2 (P1) Reduced precision only when equivalent
- [ ] T-016-020 [US-016-2] (FR-016-08, FR-016-09, FR-016-10) fp16 / int8 / fp8 variants, layer-2 gate, hostile precision requests — test: tests/unit/test_t_016_020_reduced_precision.py
- [ ] T-016-021 [US-016-2] (SC-016-03) layer-2 acceptance on the parity reports — test: tests/pipeline/test_t_016_021_layer2_acceptance.py

## Phase 4 — US-016-4 (P1) Budgets, lanes and the asset list
- [ ] T-016-030 [US-016-4] (FR-016-11, FR-016-12, FR-016-13, P-016-09) manifest entries and measured lanes — test: tests/unit/test_t_016_030_lanes.py
- [ ] T-016-031 [US-016-4] (FR-016-14, FR-016-15, FR-016-16, P-016-10) asset hosts and the release-asset list — test: tests/unit/test_t_016_031_release_assets.py
- [ ] T-016-032 [US-016-4] (FR-016-17, FR-016-18, P-016-08, NFR-016-04, NFR-016-05) class budgets and size caps — test: tests/unit/test_t_016_032_budgets.py, tests/metamorphic/test_t_016_032_budget_metamorphic.py
- [ ] T-016-033 [US-016-4] (FR-016-19, FR-016-37) glTF, 3D Tiles and shards with validator runs; hostile scene inputs — test: tests/pipeline/test_t_016_033_web_bake_validators.py

## Phase 5 — US-016-3 (P1) An honest acceleration table
- [ ] T-016-040 [US-016-3] (FR-016-20, FR-016-21, FR-016-24) engine builds on the fake GPU backend, build failures, "not run" cells — test: tests/unit/test_t_016_040_engine_builds.py, tests/gpu/test_t_016_040_engine_probe_graph.py
- [ ] T-016-041 [US-016-3] (FR-016-25) ONNX Runtime TensorRT-provider input rule — test: tests/unit/test_t_016_041_ort_trt_inputs.py
- [ ] T-016-042 [US-016-3] (FR-016-26, FR-016-27, FR-016-36, P-016-05) latency and throughput protocol, statistics, hostile measurements — test: tests/unit/test_t_016_042_latency_stats.py, tests/metamorphic/test_t_016_042_latency_metamorphic.py
- [ ] T-016-043 [US-016-3] (FR-016-28, FR-016-29, P-016-06) joules per inference and telemetry flags — test: tests/unit/test_t_016_043_energy.py
- [ ] T-016-044 [US-016-3] (FR-016-30, FR-016-31, FR-016-32) layer-4 parity per engine, kept rejected cells, bench records — test: tests/unit/test_t_016_044_engine_parity.py
- [ ] T-016-045 [US-016-3] (SC-016-01, NFR-016-02) engine acceptance and matrix wall time on the bench records — test: tests/pipeline/test_t_016_045_engine_acceptance.py

## Phase 6 — US-016-5 (P1) Licence-safe acceleration evidence
- [ ] T-016-050 [US-016-5] (FR-016-22, FR-016-23, FR-016-33, FR-016-34, NFR-016-01, NFR-016-06) engine and cache guard, licence-hash gate, local-only backends, caption, table size, no GPU stages in CI — test: tests/unit/test_t_016_050_licence_guards.py, tests/contract/test_t_016_050_publish_guards.py

## Phase 7 — US-016-6 (P2) Camera streams per GPU
- [ ] T-016-060 [US-016-6] (FR-016-35, FR-016-38, P-016-07, P-016-12) tile count and streams per GPU; hostile stream inputs — test: tests/unit/test_t_016_060_camera_streams.py

## Phase 8 — Polish and hostile review
- [ ] T-016-090 mutation run on the comparator, statistics, energy, lane, budget and stream modules; record the score (≥ 0.80 numerical core)
- [ ] T-016-091 independent review of the diff against this spec; append tasks for gaps

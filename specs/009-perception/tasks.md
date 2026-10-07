# Tasks 009 — Perception: synthetic-data detectors with a domain-randomisation ablation
Format: `- [ ] T-009-xxx [US-009-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/009-perception/tests.lock <files>`).

## Phase 1 — Setup
- [ ] T-009-000 resolve, lock and prove the new dependencies (`pycocotools`, `rfdetr` 1.11.1, D-FINE upstream code at a pinned commit, `ImageHash` 4.3.2, `pvlib`) in `pipeline/` and `studio/` on Python 3.14 (`uv sync --locked`, import smoke); no feature code — test: none (setup evidence in the PR)
- [ ] T-009-001 (DC-009-01) perception dataset-index schema + generated types — test: tests/contract/test_t_009_001_perception_dataset_schema.py
- [ ] T-009-002 (DC-009-02) COCO instances subset schema + generated types — test: tests/contract/test_t_009_002_coco_instances_schema.py
- [ ] T-009-003 (DC-009-03) randomisation config schema + generated types — test: tests/contract/test_t_009_003_sdg_randomisation_schema.py
- [ ] T-009-004 (DC-009-04) people asset record schema + generated types — test: tests/contract/test_t_009_004_people_asset_record_schema.py
- [ ] T-009-005 (DC-009-05, DC-000-01) detection evaluation report schema + generated types; perception fields of the manifest — test: tests/contract/test_t_009_005_detection_eval_schema.py

## Phase 2 — US-009-6 (P1) Reproducible, licence-clean synthetic data
- [ ] T-009-010 [US-009-6] (FR-009-01, FR-009-03) class set and default arms — test: tests/contract/test_t_009_010_classes_arms.py
- [ ] T-009-011 [US-009-6] (FR-009-04, P-009-12) structured sun sampler and stage-frame vector — test: tests/unit/test_t_009_011_sun_sampler.py
- [ ] T-009-012 [US-009-6] (FR-009-05, FR-009-06) dust extinction from the plume field and wet-road flags — test: tests/unit/test_t_009_012_dust_wet_sampler.py
- [ ] T-009-013 [US-009-6] (FR-009-07, FR-009-08, P-009-12) structured placement and unstructured ranges — test: tests/property/test_t_009_013_placement_unstructured.py
- [ ] T-009-014 [US-009-6] (FR-009-09) reject hostile randomisation configs — test: tests/unit/test_t_009_014_sdg_config_guards.py
- [ ] T-009-015 [US-009-6] (FR-009-10, FR-009-11, FR-009-12) asset licence guard, MakeHuman records, mannequin fallback — test: tests/unit/test_t_009_015_asset_people_guard.py
- [ ] T-009-016 [US-009-6] (FR-009-02) `st55_sdg` outputs on a one-plane, one-cube scene — test: tests/gpu/test_t_009_016_sdg_outputs.py
- [ ] T-009-017 [US-009-6] (FR-009-13, P-009-14) crusher-family instances from connected components — test: tests/unit/test_t_009_017_crusher_components.py
- [ ] T-009-018 [US-009-6] (FR-009-40, FR-009-41) honest "not run" and `performance: local-only` for SDG and sensors — test: tests/unit/test_t_009_018_not_run_local_only.py
- [ ] T-009-019 [US-009-6] (FR-009-14, FR-009-15, FR-009-42) dataset-index and COCO validation; reject hostile COCO files and handoff frames — test: tests/unit/test_t_009_019_coco_loader.py
- [ ] T-009-020 [US-009-6] (FR-009-16, FR-009-17, P-009-13, NFR-009-05) seed-grouped splits, leak checks, arm volume — test: tests/property/test_t_009_020_splits.py
- [ ] T-009-021 [US-009-6] (FR-009-44, FR-009-45) per-frame frame-state files from `st55_sdg` valid against spec 015's `frame-state` schema; hostile stage data — test: tests/contract/test_t_009_021_frame_state_emission.py, tests/unit/test_t_009_021_frame_state_hostile.py

## Phase 3 — US-009-1 (P1) Held-out synthetic accuracy
- [ ] T-009-030 [US-009-1] (FR-009-18, FR-009-19) training configuration, pinned checkpoints, training-input licence guard — test: tests/unit/test_t_009_030_training_inputs.py, tests/gpu/test_t_009_030_training_smoke.py
- [ ] T-009-031 [US-009-1] (FR-009-20, FR-009-21, NFR-009-03) OOM fallback and resume on the fake GPU backend — test: tests/unit/test_t_009_031_oom_resume.py
- [ ] T-009-032 [US-009-1] (FR-009-22, FR-009-23, P-009-07, P-009-08, P-009-09) box and mask AP with cluster-bootstrap intervals — test: tests/unit/test_t_009_032_ap_eval.py, tests/metamorphic/test_t_009_032_ap_metamorphic.py
- [ ] T-009-033 [US-009-1] (FR-009-24, FR-009-43, NFR-009-04) insufficient-support verdict; reject hostile prediction files; deterministic reports — test: tests/unit/test_t_009_033_support_determinism.py
- [ ] T-009-034 [US-009-1] (SC-009-01, SC-009-02, SC-009-05, SC-009-06) acceptance on the evaluation report — test: tests/pipeline/test_t_009_034_acceptance.py

## Phase 4 — US-009-3 (P1) Robustness to dust, night and rain
- [ ] T-009-040 [US-009-3] (FR-009-25, FR-009-28, P-009-01, P-009-02, P-009-03, P-009-06) dust haze with depth, sRGB transfer — test: tests/unit/test_t_009_040_dust.py, tests/metamorphic/test_t_009_040_dust_metamorphic.py
- [ ] T-009-041 [US-009-3] (FR-009-26, P-009-04) night exposure and noise — test: tests/unit/test_t_009_041_night.py
- [ ] T-009-042 [US-009-3] (FR-009-27, P-009-05) rain streaks and contrast — test: tests/property/test_t_009_042_rain.py
- [ ] T-009-043 [US-009-3] (FR-009-29) reject hostile corruption inputs — test: tests/unit/test_t_009_043_corruption_guards.py
- [ ] T-009-044 [US-009-3] (FR-009-30, P-009-10, SC-009-03) corruption curves per precision and the robustness criterion — test: tests/unit/test_t_009_044_corruption_curves.py, tests/pipeline/test_t_009_044_corruption_acceptance.py

## Phase 5 — US-009-2 (P1) Structured versus unstructured randomisation
- [ ] T-009-050 [US-009-2] (FR-009-31, P-009-11, SC-009-04) paired cluster-bootstrap DR ablation and verdict — test: tests/unit/test_t_009_050_dr_ablation.py, tests/pipeline/test_t_009_050_dr_verdict.py

## Phase 6 — US-009-4 (P1) Honest sim-to-real statement
- [ ] T-009-060 [US-009-4] (FR-009-32, SC-009-07) "not measured" and "calibrated synthetic" labels in reports and B2 data — test: tests/contract/test_t_009_060_sim_to_real_labels.py
- [ ] T-009-061 [US-009-4] (FR-009-33, FR-009-34) optional real probe: aggregate metrics, agreement, hostile probe inputs — test: tests/unit/test_t_009_061_real_probe.py

## Phase 7 — US-009-5 (P2) A live detector in the browser
- [ ] T-009-070 [US-009-5] (FR-009-35, FR-009-36) detector and segmenter ONNX signatures — test: tests/contract/test_t_009_070_onnx_signature.py
- [ ] T-009-071 [US-009-5] (FR-009-37, FR-009-38, NFR-009-01, NFR-009-02, NFR-009-06) live set, sizes, measured lanes, gallery budget — test: tests/contract/test_t_009_071_live_lane.py
- [ ] T-009-072 [US-009-5] (FR-009-39) reject reduced-precision variants that fail Δ or robustness — test: tests/unit/test_t_009_072_variant_rejection.py

## Phase 8 — Polish and hostile review
- [ ] T-009-090 mutation run on the corruption, AP-wrapper and bootstrap modules; record the score (≥ 0.80 numerical core)
- [ ] T-009-091 independent review of the diff against this spec; append tasks for gaps

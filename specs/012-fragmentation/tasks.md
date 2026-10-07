# Tasks 012 — Fragmentation: synthetic exact-PSD muck piles, U-Net versus watershed + Swebrec, measured sim-to-real
Format: `- [ ] T-012-xxx [US-012-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/012-fragmentation/tests.lock <files>`).

## Phase 1 — Setup
- [ ] T-012-000 resolve, lock and prove the new dependencies (`segmentation-models-pytorch` 0.5.0, `timm`, `scikit-image`, `scipy`, `ImageHash` 4.3.2, `py7zr`, DINOv2 ViT-B/14 weights by SHA-256, optional SAM 2.1-tiny) in `pipeline/` and `studio/` on Python 3.14; commit `data/splits/mendeley-78ht3pjsr4-links.yaml`; no feature code — test: none (setup evidence in the PR)
- [ ] T-012-001 (DC-012-01) fragment-table schema + generated types — test: tests/contract/test_t_012_001_fragment_table_schema.py
- [ ] T-012-002 (DC-012-02) fragment-split schema (fold file and links) + generated types — test: tests/contract/test_t_012_002_fragment_split_schema.py
- [ ] T-012-003 (DC-012-03, DC-000-01) fragmentation evaluation report schema + generated types; lineage fields of the manifest — test: tests/contract/test_t_012_003_fragmentation_eval_schema.py
- [ ] T-012-004 (DC-012-04) muck-pile render index schema + generated types — test: tests/contract/test_t_012_004_muck_pile_render_schema.py
- [ ] T-012-005 (DC-012-05) D1 design-grid schema + generated types — test: tests/contract/test_t_012_005_d1_design_grid_schema.py

## Phase 2 — US-012-1 (P1) A measured synthetic-to-real ratio
- [ ] T-012-010 [US-012-1] (FR-012-01, FR-012-02) archive reader: allowed members only; reject hostile archives — test: tests/unit/test_t_012_010_mendeley_reader.py
- [ ] T-012-011 [US-012-1] (FR-012-03) masks, hashes and counts on the real archive — test: tests/pipeline/test_t_012_011_mendeley_counts.py
- [ ] T-012-012 [US-012-1] (FR-012-04, FR-012-05, FR-012-06, FR-012-44, P-012-08, NFR-012-04) group keys, links, grouped 5-fold, leak checks, hostile links file, deterministic fold file — test: tests/unit/test_t_012_012_groups_folds.py, tests/property/test_t_012_012_folds_property.py
- [ ] T-012-013 [US-012-1] (FR-012-07, FR-012-08) label integrity and label-assistant lineage — test: tests/unit/test_t_012_013_label_integrity.py
- [ ] T-012-014 [US-012-1] (FR-012-18, FR-012-19, P-012-07) three-class encoding and instance decoding — test: tests/unit/test_t_012_014_label_scheme.py
- [ ] T-012-015 [US-012-1] (FR-012-20, FR-012-21, P-012-16) U-Net architecture, pinned encoder, weight map and loss — test: tests/unit/test_t_012_015_unet_loss.py
- [ ] T-012-016 [US-012-1] (FR-012-22, FR-012-23, NFR-012-03) TSTR and TRTR arms with identical budgets; inference guards — test: tests/unit/test_t_012_016_training_arms.py
- [ ] T-012-017 [US-012-1] (FR-012-29, FR-012-30, FR-012-45, P-012-06) foreground IoU and per-fold ratios; hostile metric inputs — test: tests/unit/test_t_012_017_iou_ratio.py
- [ ] T-012-018 [US-012-1] (SC-012-02) TSTR / TRTR acceptance on the evaluation report — test: tests/pipeline/test_t_012_018_tstr_acceptance.py
- [ ] T-012-019 [US-012-1] (FR-012-40) real archive unavailable → "not run" and the synthetic-only statement — test: tests/unit/test_t_012_019_mendeley_unavailable.py

## Phase 3 — US-012-3 (P1) Synthetic muck piles with an exact PSD
- [ ] T-012-020 [US-012-3] (FR-012-09, FR-012-10, FR-012-11, P-012-09, P-012-10, P-012-11, P-012-12) exact-PSD generator, bound, hostile parameters — test: tests/unit/test_t_012_020_pile_generator.py, tests/property/test_t_012_020_pile_bound.py, tests/metamorphic/test_t_012_020_pile_metamorphic.py
- [ ] T-012-021 [US-012-3] (FR-012-12) volume-exact rock meshes — test: tests/unit/test_t_012_021_mesh_volume.py
- [ ] T-012-022 [US-012-3] (FR-012-13) pile renders with fragment-id masks, depth and intrinsics — test: tests/gpu/test_t_012_022_muck_render.py
- [ ] T-012-023 [US-012-3] (FR-012-14, FR-012-15, FR-012-16, FR-012-17, P-012-17) synthetic splits, exact truth, consistency and real-data guards — test: tests/unit/test_t_012_023_synthetic_truth.py
- [ ] T-012-024 [US-012-3] (FR-012-39) Isaac Sim not passing → synthetic arm "not run", "TRTR only" label — test: tests/unit/test_t_012_024_synthetic_not_run.py

## Phase 4 — US-012-2 (P1) Fragment sizes from images, learned versus classical
- [ ] T-012-030 [US-012-2] (FR-012-24, FR-012-25, FR-012-26, FR-012-27, P-012-01, P-012-02, P-012-03, P-012-04, P-012-05, P-012-13) image PSD, Swebrec fit, `no-fit`, hostile fit inputs — test: tests/unit/test_t_012_030_psd_fit.py, tests/metamorphic/test_t_012_030_psd_metamorphic.py
- [ ] T-012-031 [US-012-2] (FR-012-28, FR-012-23) watershed baseline, its per-fold tuning and its input guard — test: tests/unit/test_t_012_031_watershed.py
- [ ] T-012-032 [US-012-2] (FR-012-31, FR-012-32, P-012-18) x50 errors and the two paired comparisons — test: tests/unit/test_t_012_032_x50_comparison.py
- [ ] T-012-033 [US-012-2] (SC-012-01, SC-012-03) synthetic x50 and comparison acceptance on the evaluation report — test: tests/pipeline/test_t_012_033_x50_acceptance.py

## Phase 5 — US-012-4 (P1) Realism checks and licence-clean publishing
- [ ] T-012-040 [US-012-4] (FR-012-33, FR-012-34, FR-012-35, FR-012-37, P-012-14, P-012-15) DINOv2 C2ST, real-versus-real baseline, injected shift, train-versus-test, hostile inputs — test: tests/unit/test_t_012_040_c2st.py, tests/property/test_t_012_040_c2st_gaussian.py
- [ ] T-012-041 [US-012-4] (FR-012-36) duplicate scans — test: tests/unit/test_t_012_041_duplicates.py
- [ ] T-012-042 [US-012-4] (FR-012-38) metrics-only guard and verbatim attribution — test: tests/contract/test_t_012_042_metrics_only_guard.py
- [ ] T-012-043 [US-012-4] (SC-012-04) realism acceptance on the evaluation report — test: tests/pipeline/test_t_012_043_realism_acceptance.py

## Phase 6 — US-012-5 (P2) A live segmenter in the browser
- [ ] T-012-050 [US-012-5] (FR-012-42, FR-012-43, NFR-012-01, NFR-012-02, SC-012-05) TSTR-only export, int8 QDQ, int8 acceptance, size and lane — test: tests/contract/test_t_012_050_unet_export.py, tests/pipeline/test_t_012_050_int8_acceptance.py

## Phase 7 — US-012-6 (P2) Design outputs from cited models
- [ ] T-012-060 [US-012-6] (FR-012-41, FR-012-46) D1 design grid from `minephys.blasting`; hostile design inputs — test: tests/unit/test_t_012_060_d1_design_grid.py

## Phase 8 — Polish and hostile review
- [ ] T-012-090 mutation run on the generator, PSD / fit, IoU and C2ST modules; record the score (≥ 0.80 numerical core)
- [ ] T-012-091 independent review of the diff against this spec; append tasks for gaps

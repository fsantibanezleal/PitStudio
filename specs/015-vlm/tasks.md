# Tasks 015 — Vision-language reasoning (M22)
Format: `- [ ] T-015-xxx [US-015-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/015-vlm/tests.lock <files>`). Tests marked `gpu` run
only on the reference machine under the GPU lock, never in CI; nothing in CI needs a Hugging Face token.

## Phase 1 — Setup
- [ ] T-015-001 (DC-015-01, DC-015-02, DC-015-03, DC-015-04, DC-015-05, DC-015-06) contract schemas `frame-state`, `vlm-queries`, `reason-pins`, `vlm-record`, `vlm-metrics`, `plausibility-pairs` + generated Pydantic and TypeScript types + drift check — test: tests/contract/test_t_015_001_reason_schemas.py
- [ ] T-015-002 resolve and lock in `pipeline/` the transformers (Qwen3-VL), `gguf`, `huggingface-hub` additions and the test-only SciPy / statsmodels / scikit-learn references; prove `uv sync --frozen` and an import smoke on Python 3.14 before feature code; add the `llamacpp` probe to the bench registry (no requirement IDs; dependency gate)

## Phase 2 — US-015-3 (P1) provenance, runtime and hygiene
- [ ] T-015-010 [US-015-3] (FR-015-01, FR-015-02) pin verification of the llama.cpp archives and executables — test: tests/unit/test_t_015_010_runtime_pins.py
- [ ] T-015-011 [US-015-3] (FR-015-03, FR-015-04) model repository, revision and file-hash verification with a fake hub; hostile repositories — test: tests/unit/test_t_015_011_weights_provenance.py
- [ ] T-015-012 [US-015-3] (FR-015-05, P-015-12) own GGUF conversion pipeline with fake tools; determinism of the output hashes — test: tests/unit/test_t_015_012_gguf_conversion.py
- [ ] T-015-013 [US-015-3] (FR-015-06) no weights in git, release lists or the Pages artefact — test: tests/unit/test_t_015_013_no_weights_published.py
- [ ] T-015-014 [US-015-3] (FR-015-07, FR-015-08) gated-terms "not run" degradation and canary-token redaction — test: tests/unit/test_t_015_014_gated_terms_token.py
- [ ] T-015-015 [US-015-3] (FR-015-09, FR-015-10) BF16 reference loader states (fake) and the "agreement gate not evaluable" path — test: tests/unit/test_t_015_015_bf16_reference.py
- [ ] T-015-016 [US-015-3] (FR-015-11, FR-015-12, NFR-015-04) loopback server driver, network audit, retries and the 2 % error threshold — test: tests/unit/test_t_015_016_server_driver.py
- [ ] T-015-017 [US-015-3] (FR-015-24, FR-015-25, FR-015-44) committed prompts and hashes, decoding settings, hostile lane configurations — test: tests/unit/test_t_015_017_prompts_config.py

## Phase 3 — US-015-2 (P1) bench and gate
- [ ] T-015-020 [US-015-2] (FR-015-13, NFR-015-01, NFR-015-02, DC-015-07, DC-015-08) bench metrics contract (manifest and `llamacpp` probe entry) (public, labelled), VRAM limits and GPU-time projection — test: tests/contract/test_t_015_020_reason_bench.py
- [ ] T-015-021 [US-015-2] (FR-015-14, FR-015-15, P-015-05, SC-015-01) agreement gate (500 binary queries, point estimate, Wilson interval) and the rejection path — test: tests/unit/test_t_015_021_agreement_gate.py

## Phase 4 — US-015-1 (P1) task A
- [ ] T-015-030 [US-015-1] (FR-015-16) query builder: balance, one query per frame and type, condition shares — test: tests/unit/test_t_015_030_query_builder.py
- [ ] T-015-031 [US-015-1] (FR-015-17, FR-015-18, FR-015-19, P-015-08) ground truth for types 1–3 with ambiguity bands; invariances — test: tests/metamorphic/test_t_015_031_truth_types_1_3.py
- [ ] T-015-032 [US-015-1] (FR-015-20, FR-015-21, FR-015-22, P-015-08) ground truth for types 4–6 with ambiguity bands; invariances — test: tests/metamorphic/test_t_015_032_truth_types_4_6.py
- [ ] T-015-033 [US-015-1] (FR-015-23) hostile frame states — test: tests/unit/test_t_015_033_frame_state_hostile.py
- [ ] T-015-034 [US-015-1] (FR-015-26, FR-015-27, P-015-11) answer parser and fuzzing — test: tests/property/test_t_015_034_answer_parser.py
- [ ] T-015-035 [US-015-1] (FR-015-28, FR-015-29, FR-015-47, P-015-09) arm plan, detector + geometric rule, hostile query sets and detector inputs — test: tests/unit/test_t_015_035_arms_detector_rule.py
- [ ] T-015-036 [US-015-1] (FR-015-30, FR-015-32, P-015-01, P-015-03, P-015-04, SC-015-02) balanced accuracy, F1, bootstrap intervals, AUROC, Wilson; hostile inputs — test: tests/metamorphic/test_t_015_036_task_a_metrics.py
- [ ] T-015-037 [US-015-1] (FR-015-31, P-015-02, SC-015-03) exact McNemar verdicts per type and pooled — test: tests/metamorphic/test_t_015_037_mcnemar.py

## Phase 5 — US-015-4 (P2) task B
- [ ] T-015-040 [US-015-4] (FR-015-33, FR-015-34, FR-015-35, P-015-10) pair set, corruption detectors and pair rejection — test: tests/unit/test_t_015_040_plausibility_pairs.py
- [ ] T-015-041 [US-015-4] (FR-015-36, FR-015-37, P-015-06, SC-015-05) 2AFC protocol, per-pair scoring, interval over pairs, position bias — test: tests/metamorphic/test_t_015_041_task_b_scoring.py

## Phase 6 — US-015-5 (P2) task C
- [ ] T-015-050 [US-015-5] (FR-015-38, FR-015-46, P-015-07, SC-015-06) caption scoring (CHAIR_i, CHAIR_s, recall, condition accuracy), the template baseline, hostile captions and vocabulary — test: tests/metamorphic/test_t_015_050_caption_scoring.py
- [ ] T-015-051 [US-015-5] (FR-015-39) display-only guard over training and curation manifests — test: tests/contract/test_t_015_051_captions_display_only.py

## Phase 7 — Publication and web
- [ ] T-015-060 [US-015-1] (FR-015-40, FR-015-45, NFR-015-03) answer records, stratified sampling independent of correctness, optional real probe with Cohen's κ, text budget — test: tests/contract/test_t_015_060_records.py
- [ ] T-015-061 [US-015-3] (FR-015-42, SC-015-04) headline-KPI exclusion check — test: tests/contract/test_t_015_061_not_headline.py
- [ ] T-015-062 [US-015-1] (FR-015-43) hostile baked records in the web panel — test: web/src/features/reason/records-hostile.test.ts
- [ ] T-015-063 [US-015-1] (FR-015-41, FR-015-07, FR-015-42) notices, wrong answers shown, "not run" states, no Cosmos KPI tile — test: web/e2e/reason-panels.spec.ts

## Phase 8 — Local GPU integration (reference machine, after the GPU hold is lifted and the gated terms are accepted)
- [ ] T-015-070 [US-015-2] (FR-015-05, FR-015-09, FR-015-13, P-015-12) real conversion twice, BF16 load and the footprint bench — test: tests/gpu/test_t_015_070_reason_local.py
- [ ] T-015-071 [US-015-2] (FR-015-14) agreement gate on the real 500-query subset — test: tests/gpu/test_t_015_071_agreement_real.py

## Phase 9 — Polish and review
- [ ] T-015-090 mutation run on `src/pitstudio/reason/`; record the score (numerical core ≥ 0.80)
- [ ] T-015-091 independent review of the diff against this spec; append tasks for gaps

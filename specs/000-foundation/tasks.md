# Tasks 000 — Foundation: PitStudio
Format: `- [ ] T-000-xxx [US-000-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/000-foundation/tests.lock <files>`).
The foundation requirements are refined by the feature specs. The tasks here own the product-level acceptance tests
(site, evaluation reports, manifests and CI gates) that no single feature owns.

## Phase 1 — Setup
- [ ] T-000-000 confirm the shared fixtures (built site, evaluation-report fixtures, fake GPU backend) used by the acceptance tests below exist before they are written; no feature code — test: none (setup evidence in the PR)

## Phase 2 — Product-level acceptance (user stories)
- [ ] T-000-010 [US-000-1] (US-000-1) engineer story: on the built site, changing dispatch, road grade, power train, blast design and slope-monitoring settings updates t/h, kWh/t, CO₂/t, oversize and warning lead time, each with its source — test: web/e2e/t-000-010-engineer-story.spec.ts
- [ ] T-000-011 [US-000-2] (US-000-2) every learned-model result on the evaluation reports carries a classical baseline, a held-out split and a paired 95 % interval, and every synthetic dataset with a real reference carries a validation record — test: tests/pipeline/test_t_000_011_baseline_and_ci_acceptance.py
- [ ] T-000-012 [US-000-3] (US-000-3) student story: every theory page with an equation cites a primary source and embeds an interactive figure — test: web/e2e/t-000-012-student-story.spec.ts
- [ ] T-000-013 [US-000-4] (US-000-4) developer story: each published artefact lists its producer tool, manifest and telemetry, and its one-command reproduction command is parsed and resolves to a recipe — test: tests/contract/test_t_000_013_reproduce_story.py
- [ ] T-000-014 [US-000-5] (US-000-5) maintainer story with the fake GPU backend: two queued GPU jobs run one at a time, hit the guards, reuse the cache and resume after a simulated crash — test: tests/unit/test_t_000_014_queue_story.py
- [ ] T-000-015 [US-000-6] (US-000-6) reviewer story: every external number has a source, every card a lane and licence label, every missing run the "not yet run" text — test: tests/contract/test_t_000_015_honesty_story.py

## Phase 3 — Product-level requirements
- [ ] T-000-020 (FR-000-04) the access gate is shown before the workbench on first load and after a cleared session — test: web/e2e/t-000-020-access-gate.spec.ts
- [ ] T-000-021 (FR-000-12) footer shows version, commit SHA, build date, author, provenance, licences and the non-affiliation note — test: web/e2e/t-000-021-footer.spec.ts
- [ ] T-000-022 (FR-000-13) GPU work only through the runner; `gpu0.compute` / `gpu0.nvenc` lock and `gpu0.hold` refusal, fake GPU backend — test: tests/unit/test_t_000_022_gpu_lock_and_hold.py
- [ ] T-000-023 (FR-000-14) every published artefact has a manifest valid against `contracts/manifest.schema.json` with producer tool, measured lane, licence class, SHA-256 inputs and run — test: tests/contract/test_t_000_023_manifest_coverage.py
- [ ] T-000-024 (FR-000-16) the same recipes plan under the `linux-gpu` profile with the fake GPU and no recipe change — test: tests/unit/test_t_000_024_linux_gpu_profile.py

## Phase 4 — Correctness properties
- [ ] T-000-030 (P-000-01) same recipe, code, lock, params, seed and inputs give the same cache key and byte-identical deterministic outputs — test: tests/property/test_t_000_030_cache_key_determinism.py
- [ ] T-000-031 (P-000-02) manifest SHA-256 equals the SHA-256 of the served file for every artefact at build — test: tests/contract/test_t_000_031_served_sha.py
- [ ] T-000-032 (P-000-03) browser engine output equals the Python reference within the `web.*` class tolerance, per engine fixture — test: tests/parity/test_t_000_032_engine_parity_registry.py

## Phase 5 — Non-functional requirements and success criteria
- [ ] T-000-040 (NFR-000-05, NFR-000-06) git file-size and baked-asset caps; live model size cap — test: tests/contract/test_t_000_040_size_caps.py
- [ ] T-000-041 (NFR-000-08) runner size cap read from the line count — test: tests/contract/test_t_000_041_runner_loc.py
- [ ] T-000-042 (SC-000-01) TSTR ≥ 0.90 × TRTR (IoU) acceptance on the spec 012 evaluation report — test: tests/pipeline/test_t_000_042_sc_tstr_trtr.py
- [ ] T-000-043 (SC-000-02) learned dispatch versus SPTF / LP: "better" only by the decision rule over ≥ 30 paired seeds, on the spec 007 report — test: tests/pipeline/test_t_000_043_sc_dispatch.py
- [ ] T-000-044 (SC-000-03) GNS repose ±1.5° and run-out ±5 % on the spec 011 report — test: tests/pipeline/test_t_000_044_sc_gns.py
- [ ] T-000-045 (SC-000-04) detector mAP50 and corruption drop on the spec 009 report — test: tests/pipeline/test_t_000_045_sc_detector.py

## Phase 6 — Data contracts
- [ ] T-000-050 (DC-000-02) `studio/capabilities.json` valid against `contracts/capabilities.schema.json` and read by the runner guards and the web `/studio` page — test: tests/contract/test_t_000_050_capabilities_contract.py
- [ ] T-000-051 (DC-000-03) every `recipes/*.yaml` valid against `contracts/recipe.schema.json` — test: tests/contract/test_t_000_051_recipe_contract.py
- [ ] T-000-052 (DC-000-04) `studio/tools.yaml` valid against `contracts/tools.schema.json` and every tool shown on the tool map — test: tests/contract/test_t_000_052_tools_contract.py
- [ ] T-000-053 (DC-000-05) `data/sources.yaml` valid against `contracts/sources.schema.json` and consumed by `s00_download` and docs — test: tests/contract/test_t_000_053_sources_contract.py

## Phase — Blind red-proof for GPU and pipeline tests (G5 review, M5)
- [ ] T-000-060 (FR-000-17) `check_tdd.py --replay` runs each red test in the environment that owns it (root, `pipeline/`, `studio/`, `web/` with vitest) — test: tests/unit/test_t_000_060_replay_environments.py
- [ ] T-000-061 (FR-000-18) collection errors, import errors and a missing CUDA device are `environment-error`, never red — test: tests/unit/test_t_000_061_replay_environment_error.py
- [ ] T-000-062 (FR-000-19) local evidence record for `gpu` red and green commits, checked by `check_tdd.py` — test: tests/unit/test_t_000_062_gpu_evidence_record.py

## Phase 7 — Polish and hostile review
- [ ] T-000-090 mutation run on the product-level gate scripts (`tools/`); record the score (≥ 0.60 other)
- [ ] T-000-091 independent review of the diff against this spec; append tasks for gaps

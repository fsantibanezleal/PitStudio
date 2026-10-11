# Tasks 019 — Web studio: tool map, tool pages, published runs, GPU evidence and showcase honesty
Format: `- [ ] T-019-xxx [US-019-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/019-web-studio/tests.lock <files>`). Web test titles
start with the requirement ID followed by " · "; Python tests use `@pytest.mark.req("…")`.

## Phase 1 — Setup
- [ ] T-019-001 (DC-019-02, DC-019-03, FR-019-38) tool-map and studio-index schemas, generated types, `studio/toolmap.yaml` for the 20 ids; schema checks of the consumed files (tool registry, web and published run manifests, capabilities, published telemetry) — test: tests/contract/test_t_019_001_studio_schemas.py
- [ ] T-019-002 (FR-019-09, FR-019-10) version resolution from `uv.lock` files, `web/pnpm-lock.yaml` and external-binary records — test: tests/contract/test_t_019_002_resolve_versions.py
- [ ] T-019-003 (FR-019-02, FR-019-06, P-019-01, P-019-02, P-019-05) studio-index build: layout, artefact join, observed edges — test: web/src/studio/t_019_003_build_index.test.ts
- [ ] T-019-004 (FR-019-33, FR-019-43, FR-019-34, FR-019-35, FR-019-36, P-019-03, P-019-04, FR-000-07, FR-000-08) `tools/check_showcase.py`: done needs an artefact, not-yet-run with an artefact, outputs only, our scenes, local-only scrub, file guards — test: tests/contract/test_t_019_004_check_showcase.py

## Phase 2 — US-019-1 (P1) Tool map
- [ ] T-019-010 [US-019-1] (FR-019-01, FR-019-05) map nodes, encodings, keyboard access and names — test: web/src/studio/t_019_010_tool_map.test.tsx, web/e2e/t_019_010_tool_map.spec.ts
- [ ] T-019-011 [US-019-1] (FR-019-03, FR-019-04, FR-019-39) lazy React Flow, static SVG and table fallback, chunk failure — test: web/e2e/t_019_011_map_fallback.spec.ts
- [ ] T-019-012 [US-019-1] (FR-019-07) physical-AI loop tied to published runs — test: web/src/studio/t_019_012_loop.test.tsx

## Phase 3 — US-019-2 (P1) Tool pages
- [ ] T-019-020 [US-019-2] (FR-019-08, FR-019-20) 20 prerendered tool pages in block order; 404 for other ids — test: web/e2e/t_019_020_tool_pages.spec.ts
- [ ] T-019-021 [US-019-2] (FR-019-09, FR-019-11, FR-019-16, FR-019-17, FR-019-18, FR-019-19, FR-019-42) identity with probe status, role, where it ran, limits, reproduce, alternatives — test: web/src/studio/blocks/t_019_021_blocks.test.tsx
- [ ] T-019-022 [US-019-2] (FR-019-12, FR-019-13, FR-019-14, FR-000-06) artefact list, "Not yet run", "Evaluated, not adopted" — test: web/src/studio/blocks/t_019_022_artefacts.test.tsx, web/e2e/t_019_022_not_yet_run.spec.ts
- [ ] T-019-023 [US-019-2] (FR-019-15, FR-019-37) provenance chips with local-only replacement; Cosmos attribution — test: web/src/studio/blocks/t_019_023_provenance.test.tsx
- [ ] T-019-024 [US-019-2] (FR-019-40) hostile strings rendered as escaped, truncated text — test: web/src/studio/t_019_024_hostile_strings.test.tsx, web/e2e/t_019_024_hostile_strings.spec.ts

## Phase 4 — US-019-3 (P2) Published runs
- [ ] T-019-030 [US-019-3] (FR-019-21, FR-019-26, FR-019-41) runs ledger, filters, 404 for unpublished runs — test: web/src/studio/t_019_030_runs_ledger.test.tsx, web/e2e/t_019_030_runs.spec.ts
- [ ] T-019-031 [US-019-3] (FR-019-22, FR-019-23) run page and manifest viewer — test: web/src/studio/t_019_031_manifest_tree.test.tsx, web/e2e/t_019_031_run_page.spec.ts
- [ ] T-019-032 [US-019-3] (FR-019-24, FR-019-25) stage DAG and determinism block — test: web/src/studio/t_019_032_dag_determinism.test.tsx

## Phase 5 — US-019-4 (P2) GPU evidence
- [ ] T-019-033 [US-019-4] (FR-019-27, FR-019-28, FR-019-29, FR-019-31) timelines, paired busy % and power-at-limit, "How measured", unavailable fields — test: web/src/studio/telemetry/t_019_033_timelines.test.tsx, web/e2e/t_019_033_gpu_page.spec.ts
- [ ] T-019-034 [US-019-4] (FR-019-30, FR-019-32, FR-000-08) local-only stages and benchmark conditions — test: web/src/studio/telemetry/t_019_034_local_only.test.tsx
- [ ] T-019-035 [US-019-1] (FR-000-11) studio pages make no loopback request without the opt-in control — test: web/e2e/t_019_035_no_loopback.spec.ts
- [ ] T-019-036 [US-019-1] (FR-019-44, FR-019-45) the "connect to my local studio" control: port validation (hostile strings), exactly one `GET /health` per press with `credentials: "omit"` and a 3 s timeout, label rules for valid, invalid, refused and silent responses — test: web/src/studio/connect.test.ts, web/e2e/t_019_036_connect.spec.ts

## Phase 6 — Quality, gates and independent review
- [ ] T-019-040 [US-019-1] (NFR-019-01, NFR-019-02, NFR-019-03) initial JS, map readiness and studio data sizes — test: web/e2e/t_019_040_budgets.spec.ts
- [ ] T-019-041 [US-019-1] (NFR-019-04, NFR-019-05, NFR-000-02, FR-000-03) axe matrix and Lighthouse for the studio routes — test: web/e2e/t_019_041_a11y_studio.spec.ts
- [ ] T-019-088 [US-019-5] (SC-019-01, SC-019-02) release gate: 17 of 17 tools with an artefact or an evaluated-not-adopted page, 0 honesty violations — test: tests/contract/test_t_019_088_showcase_gate.py
- [ ] T-019-090 (NFR-019-06) coverage and mutation run on `web/src/studio/**` and `tools/check_showcase.py`; scores checked against `thresholds.yaml` — test: tests/contract/test_t_019_090_studio_quality_scores.py
- [ ] T-019-091 independent review of the diff against this spec; append tasks for gaps

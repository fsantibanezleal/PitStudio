# Tasks 020 — Web knowledge: theory, methods, results, knowledge base, interactive figures and site-wide quality
Format: `- [ ] T-020-xxx [US-020-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/020-web-knowledge/tests.lock <files>`). Web test titles
start with the requirement ID followed by " · "; Python tests use `@pytest.mark.req("…")`.

## Phase 1 — Setup
- [ ] T-020-001 (DC-020-01, FR-020-19) method registry: `contracts/methods.schema.json`, generated types, `studio/methods.yaml` for M1–M23 with criteria copied from the owning specs — test: tests/contract/test_t_020_001_methods_registry.py
- [ ] T-020-002 (DC-020-02, FR-020-23, FR-020-29) results bundle schema, generated types and `tools/check_results.py` (verdict consistency, restricted-software guard) — test: tests/contract/test_t_020_002_results_bundle.py
- [ ] T-020-003 (DC-020-04, FR-020-09, FR-020-10, FR-020-16) figure registry schema and `tools/check_figures.py` — test: tests/contract/test_t_020_003_figure_registry.py
- [ ] T-020-004 (DC-020-03, FR-020-39, FR-020-40, P-020-31) knowledge bundle schema and `tools/build_knowledge.py` with validation and drift check — test: tests/contract/test_t_020_004_knowledge_bundle.py

## Phase 2 — US-020-1 (P2) Theory and the chart component
- [ ] T-020-010 [US-020-1] (FR-020-07, FR-020-11, FR-020-12, FR-020-15, P-020-04, P-020-05, P-020-06, P-020-07, P-020-08, P-020-09) chart component: zoom, pan, read-out, keyboard, data table, theme, decimation, view transform — test: web/src/charts/t_020_010_chart.test.ts, web/e2e/t_020_010_chart.spec.ts
- [ ] T-020-011 [US-020-1] (FR-020-49, FR-020-50, P-020-10, P-020-11, P-020-12, P-020-13, P-020-14, P-020-15) teaching functions: Beverloo and Ritter — test: web/src/theory/fn/t_020_011_beverloo_ritter.test.ts
- [ ] T-020-012 [US-020-1] (FR-020-49, FR-020-50, P-020-16, P-020-17, P-020-18, P-020-19, P-020-20, P-020-21) teaching functions: lidar range and PPO clip — test: web/src/theory/fn/t_020_012_lidar_ppo.test.ts
- [ ] T-020-013 [US-020-1] (FR-020-49, FR-020-50, P-020-22, P-020-23, P-020-24, P-020-25, P-020-26, P-020-27, P-020-28, P-020-29, P-020-30) teaching functions: McNemar, Gaussian AUC, paired-t interval — test: web/src/theory/fn/t_020_013_statistics.test.ts
- [ ] T-020-014 [US-020-1] (FR-020-01, FR-020-02, FR-020-03, FR-020-04, FR-020-05, FR-020-47) theory index and 13 pages in EN and ES with KaTeX at build, drift and parity checks — test: tests/contract/test_t_020_014_theory_content.py, web/e2e/t_020_014_theory_pages.spec.ts
- [ ] T-020-015 [US-020-1] (FR-020-06, FR-020-08, FR-020-13) figures of spec §7.1 with marked features and reactive controls — test: web/src/theory/t_020_015_figures.test.tsx, web/e2e/t_020_015_figures.spec.ts
- [ ] T-020-016 [US-020-1] (FR-020-14, FR-020-48) hostile figure controls and URL parameters — test: web/e2e/t_020_016_hostile.spec.ts

## Phase 3 — US-020-4 (P2) Methods
- [ ] T-020-020 [US-020-4] (FR-020-17, FR-020-18) method index and 23 pages — test: web/src/routes/t_020_020_methods.test.tsx, web/e2e/t_020_020_methods.spec.ts

## Phase 4 — US-020-2 (P1) Results
- [ ] T-020-030 [US-020-2] (FR-020-22, FR-000-05, P-020-01, P-020-02, P-020-03) decision-rule display — test: web/src/results/t_020_030_verdict.test.ts
- [ ] T-020-031 [US-020-2] (FR-020-20, FR-020-21, FR-020-31) tabs, comparison rows and "Not yet run" — test: web/src/results/t_020_031_rows.test.tsx, web/e2e/t_020_031_results.spec.ts
- [ ] T-020-032 [US-020-2] (FR-020-24) acceptance criteria and computed status per model — test: web/src/results/t_020_032_criteria.test.ts
- [ ] T-020-033 [US-020-2] (FR-020-25, FR-020-26, FR-000-09) sim-to-real and parity tabs — test: web/src/results/t_020_033_gaps_parity.test.tsx
- [ ] T-020-034 [US-020-2] (FR-020-27) Cosmos tab and the no-headline rule — test: web/src/results/t_020_034_cosmos.test.tsx, web/e2e/t_020_034_cosmos_headline.spec.ts
- [ ] T-020-035 [US-020-2] (FR-020-28, FR-020-30, FR-000-08) Acceleration tab and the TensorRT licence pin — test: web/src/results/t_020_035_acceleration.test.tsx

## Phase 5 — US-020-3 (P2) Knowledge
- [ ] T-020-040 [US-020-3] (FR-020-32, FR-020-36, FR-020-37, FR-020-38) sections, provenance, datasets, frameworks, bibliography — test: web/src/knowledge/t_020_040_sections.test.tsx, web/e2e/t_020_040_knowledge.spec.ts
- [ ] T-020-041 [US-020-3] (FR-020-33, FR-020-34, FR-000-10) parameter browser and equation explorer — test: web/src/knowledge/t_020_041_parameters_equations.test.tsx
- [ ] T-020-042 [US-020-3] (FR-020-35, FR-020-41, P-020-32, NFR-020-08) glossary and search — test: web/src/knowledge/t_020_042_search.test.ts, web/e2e/t_020_042_search.spec.ts
- [ ] T-020-043 [US-020-3] (FR-020-42, SC-020-03) UNVERIFIED values kept out of headlines — test: web/src/knowledge/t_020_043_unverified_headline.test.ts

## Phase 6 — US-020-6 (P3) ⓘ modal
- [ ] T-020-050 [US-020-6] (FR-020-43, FR-020-44) seven tabs with themed diagrams, focus handling — test: web/e2e/t_020_050_architecture_modal.spec.ts
- [ ] T-020-051 [US-020-6] (FR-020-51) inline-SVG guard for ⓘ and theory diagrams — test: tests/contract/test_t_020_051_inline_svg.py

## Phase 7 — US-020-5 (P1) Languages, themes, accessibility and budgets
- [ ] T-020-060 [US-020-5] (FR-020-45, FR-000-03) locale key parity and no JSX text literals — test: web/src/locales/t_020_060_locales.test.ts
- [ ] T-020-061 [US-020-5] (FR-020-46) contrast of every text token on every surface, both themes — test: web/src/shell/t_020_061_contrast.test.ts
- [ ] T-020-062 [US-020-5] (NFR-020-01, NFR-020-03, NFR-020-04, NFR-000-01, NFR-000-04, NFR-000-07) per-route initial JS (postbuild constant aligned to 200,000 bytes), per-class budgets on the built artifact, KaTeX at build — test: tests/contract/test_t_020_062_budgets.py
- [ ] T-020-063 [US-020-5] (NFR-020-02, NFR-020-07, NFR-000-03) first view per route; figure render and zoom timing — test: web/e2e/t_020_063_first_view.spec.ts
- [ ] T-020-064 [US-020-5] (NFR-020-05, NFR-020-06, SC-020-01, NFR-000-02) axe over the route matrix; Lighthouse — test: web/e2e/t_020_064_a11y_matrix.spec.ts

## Phase 8 — Gates, polish and independent review
- [ ] T-020-088 [US-020-2] (SC-020-02) all 13 model rows of plan §7 present with criterion and status on the release build — test: web/e2e/t_020_088_criteria_rows.spec.ts
- [ ] T-020-090 (NFR-020-09) coverage and mutation run on `web/src/charts/**`, `web/src/theory/fn/**`, `web/src/results/verdict*`, `web/src/knowledge/search*`; scores checked against `thresholds.yaml` — test: tests/contract/test_t_020_090_web_quality_scores.py
- [ ] T-020-091 independent review of the diff against this spec; append tasks for gaps

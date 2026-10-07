# Tasks 018 — Web cases: Explore, case workbenches, in-browser engines, compute tiers and parity
Format: `- [ ] T-018-xxx [US-018-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/018-web-cases/tests.lock <files>`). Web test titles
start with the requirement ID followed by " · " (for example `it("FR-018-39 · rejects NaN …")`); Python tests use
`@pytest.mark.req("…")`. Tests tagged `@gpu` live under `web/e2e/gpu/` and run only in the Playwright `webgpu` project.

## Phase 1 — Setup
- [ ] T-018-001 (DC-018-01, FR-018-10) case registry: `contracts/cases.schema.json`, generated Python and TS types, `studio/cases.yaml` for the 12 cases, `tools/check_cases.py` cross-checks (methods, tools, sources, engines, categories, duplicates) — test: tests/contract/test_t_018_001_cases_registry.py
- [ ] T-018-002 (DC-018-02) engine input/output schemas for the 25 engines of spec §7.1 (units, validity ranges, caps, unit scales) and generated TS validators — test: tests/contract/test_t_018_002_engine_schemas.py
- [ ] T-018-003 (DC-018-03) replay shard header schema and generated types — test: tests/contract/test_t_018_003_replay_shard_schema.py
- [ ] T-018-004 (DC-018-04, DC-018-05, DC-018-06) parity fixture, parity report and lane measurement schemas — test: tests/contract/test_t_018_004_parity_lane_schemas.py
- [ ] T-018-005 (DC-018-04, FR-018-67) `tools/make_parity_fixtures.py` runs every reference of §7.1 and writes fixtures with SHA-256; fixtures validate, their digests are pinned, and empty or invalid fixture sets fail — test: tests/contract/test_t_018_005_parity_fixtures.py
- [ ] T-018-006 fake GPU backend `web/src/engines/tier/fake-gpu.ts` (test double, scripted adapters of spec §7.3) — test: web/src/engines/tier/t_018_006_fake_gpu.test.ts

## Phase 2 — US-018-4 (P1) Tiers, engine host and hostile inputs
- [ ] T-018-010 [US-018-4] (FR-018-29, FR-018-30) capability probe and `?tier=` override with the fake GPU — test: web/src/engines/tier/t_018_010_probe.test.ts
- [ ] T-018-011 [US-018-4] (FR-018-31, FR-018-06, FR-000-02) fallback chain T1 → T2 → T0 and tier badge — test: web/src/engines/tier/t_018_011_fallback.test.ts, web/e2e/t_018_011_tier_fallback.spec.ts
- [ ] T-018-012 [US-018-4] (FR-018-38, FR-018-39, FR-018-40, FR-018-46) typed protocol, generated validators, size caps, timeouts — test: web/src/engines/host/t_018_012_protocol.test.ts
- [ ] T-018-013 [US-018-4] (FR-018-43, FR-018-45, P-018-68, P-018-69, P-018-70) asset loader (SHA-256, path rules) and shard reader — test: web/src/assets/t_018_013_loader_shard.test.ts
- [ ] T-018-014 [US-018-4] (FR-018-33, FR-018-34, FR-018-35, FR-018-37, FR-000-11) lazy same-origin runtime loading, progress and Abort, no cross-origin or loopback request, no SharedArrayBuffer — test: web/e2e/t_018_014_runtime_loading.spec.ts
- [ ] T-018-015 [US-018-4] (FR-018-36) engines in module workers, no long task above 100 ms — test: web/e2e/t_018_015_long_tasks.spec.ts
- [ ] T-018-016 [US-018-4] (FR-018-44) offline or blocked runtime and model files fall back to T0 — test: web/e2e/t_018_016_offline_runtimes.spec.ts
- [ ] T-018-017 [US-018-4] (FR-018-32) GPU-compute engines replay on T2 — test: web/e2e/t_018_017_t2_replay.spec.ts

## Phase 3 — US-018-1 (P1) Explore
- [ ] T-018-020 [US-018-1] (FR-018-01, FR-018-07, NFR-018-01, NFR-018-02) pit from LOD-0 tiles with provenance, renderer choice, first-view and initial-JS budgets — test: web/e2e/t_018_020_explore_pit.spec.ts
- [ ] T-018-021 [US-018-1] (FR-018-02, FR-018-03) case rail (12 cases, 5 groups) and `?case=` — test: web/src/routes/t_018_021_case_rail.test.tsx, web/e2e/t_018_021_case_rail.spec.ts
- [ ] T-018-022 [US-018-1] (FR-018-04, FR-018-05) layers and KPIs with "Not yet run" — test: web/e2e/t_018_022_layers_kpis.spec.ts
- [ ] T-018-023 [US-018-1] (FR-018-08) poster and KPI table without WebGL 2 or WebGPU — test: web/e2e/t_018_023_no_3d_fallback.spec.ts

## Phase 4 — US-018-7 (P2) Catalogue
- [ ] T-018-025 [US-018-7] (FR-018-09) catalogue, coverage matrix and tool matrix from the registry — test: web/src/routes/t_018_025_catalogue.test.tsx, web/e2e/t_018_025_catalogue.spec.ts

## Phase 5 — US-018-2 (P1) Case pages
- [ ] T-018-030 [US-018-2] (FR-018-11, FR-018-12, FR-018-13) 12 prerendered pages, five WAI-ARIA sub-tabs, `?tab=`, 404 for unknown ids — test: web/e2e/t_018_030_case_pages.spec.ts
- [ ] T-018-031 [US-018-2] (FR-018-14, FR-018-15) Simulate and Studio replay tabs, badge by what is shown — test: web/src/routes/t_018_031_case_tabs.test.tsx, web/e2e/t_018_031_case_tabs.spec.ts
- [ ] T-018-032 [US-018-2] (FR-018-16, FR-000-05) Charts tab with intervals, verdicts and the single-event note — test: web/src/routes/t_018_032_charts_tab.test.tsx
- [ ] T-018-033 [US-018-2] (FR-018-17, FR-000-09, FR-000-10) Context tab: sources, licences, validity range, synthetic label — test: web/src/routes/t_018_033_context_tab.test.tsx
- [ ] T-018-034 [US-018-2] (FR-018-18, FR-000-01, FR-000-06) artefact card anatomy — test: web/src/cards/t_018_034_artefact_card.test.tsx
- [ ] T-018-035 [US-018-6] (FR-018-19, FR-018-20) "Reproduce this" block — test: web/src/routes/t_018_035_reproduce.test.tsx, web/e2e/t_018_035_reproduce.spec.ts
- [ ] T-018-036 [US-018-4] (FR-018-41, FR-018-42) hostile numeric controls and URL parameters — test: web/e2e/t_018_036_hostile_inputs.spec.ts
- [ ] T-018-037 [US-018-1] (NFR-018-04, NFR-000-02, FR-000-03) axe on 14 routes × 2 themes × 2 languages; Lighthouse on 3 routes — test: web/e2e/t_018_037_a11y_cases.spec.ts

## Phase 6 — US-018-5 (P2) Shared clock and media
- [ ] T-018-040 [US-018-5] (FR-018-21, FR-018-22, FR-018-68, P-018-01, P-018-02, P-018-03) `SimClock`, paused by default, keyboard controls, hostile calls — test: web/src/sim/t_018_040_clock.test.ts
- [ ] T-018-041 [US-018-5] (FR-018-23, FR-018-24, FR-018-28) scrub and play synchronisation, reduced motion — test: web/e2e/t_018_041_clock_sync.spec.ts
- [ ] T-018-042 [US-018-5] (FR-018-25, FR-018-26, FR-018-27) video source choice, `preload="none"`, failures — test: web/src/media/t_018_042_video_source.test.ts, web/e2e/t_018_042_video_cards.spec.ts

## Phase 7 — US-018-3 (P1) Engines and parity
- [ ] T-018-050 [US-018-3] (FR-018-47, FR-018-63) engine registry and the parity-report gate — test: web/src/engines/t_018_050_registry.test.ts, web/e2e/t_018_050_parity_gate.spec.ts
- [ ] T-018-051 [US-018-3] (FR-018-49, P-018-04, P-018-05, P-018-74, P-018-75) numpy-compatible PCG64 + SeedSequence port for the spec 010 Monte Carlo, with the `Math.*` lint rule, in Node and three browsers — test: web/src/engines/random/t_018_051_pcg64.test.ts, web/e2e/parity/t_018_051_pcg64_browsers.spec.ts
- [ ] T-018-052 [US-018-3] (FR-018-48) host adapters for the engines of specs 007, 013 and 014; their suites' verdicts merged into the parity report; a failing hosted engine runs in T0 — test: web/src/engines/host/t_018_052_hosted_engines.test.ts, web/e2e/parity/t_018_052_hosted_report.spec.ts
- [ ] T-018-059 [US-018-3] (FR-018-56, P-018-59, P-018-60, P-018-61) WGSL granular kernels and observables (`@gpu`) — test: web/e2e/gpu/t_018_059_granular.spec.ts
- [ ] T-018-060 [US-018-3] (FR-018-57) ORT-web parity of GNS, FNO, forecasters, meta-model and U-Net (WASM in CI, WebGPU `@gpu`) — test: web/e2e/parity/t_018_060_onnx_wasm.spec.ts, web/e2e/gpu/t_018_060_onnx_webgpu.spec.ts
- [ ] T-018-061 [US-018-3] (FR-018-54, FR-018-55, P-018-19, P-018-20, P-018-21) traffic: Rapier snapshot hash, TTC and near-misses — test: web/src/engines/traffic/t_018_061_ttc.test.ts, web/e2e/parity/t_018_061_rapier_hash.spec.ts
- [ ] T-018-063 [US-018-3] (FR-018-58, P-018-27) detector feed (u8 → float32 table, `orig_target_sizes`) and display threshold, no NMS — test: web/src/engines/ml/t_018_063_detector.test.ts, web/e2e/parity/t_018_063_detector.spec.ts
- [ ] T-018-064 [US-018-3] (FR-018-51, FR-018-52, P-018-28, P-018-29, P-018-30, P-018-31, P-018-32, P-018-33, P-018-34, P-018-35, P-018-36, P-018-76) geotech port: limit equilibrium, Monte Carlo, inverse velocity, slope radar — test: web/src/engines/analytical/geotech/t_018_064_geotech.test.ts
- [ ] T-018-065 [US-018-3] (FR-018-56, P-018-62, P-018-63, P-018-64) WGSL shallow water (`@gpu`) — test: web/e2e/gpu/t_018_065_shallow_water.spec.ts
- [ ] T-018-066 [US-018-3] (FR-018-51, P-018-37, P-018-38, P-018-39) AP-42 and Gaussian plume port — test: web/src/engines/analytical/environment/t_018_066_plume.test.ts
- [ ] T-018-067 [US-018-3] (FR-018-56, P-018-65, P-018-66, P-018-67) WGSL dust particles (`@gpu`) — test: web/e2e/gpu/t_018_067_dust_particles.spec.ts
- [ ] T-018-068 [US-018-3] (FR-018-51, P-018-40, P-018-41, P-018-42) blasting port — test: web/src/engines/analytical/blasting/t_018_068_blasting.test.ts
- [ ] T-018-069 [US-018-3] (FR-018-59, P-018-46, P-018-47, P-018-48) watershed — test: web/src/engines/watershed/t_018_069_watershed.test.ts
- [ ] T-018-070 [US-018-3] (FR-018-51, P-018-43, P-018-44, P-018-45) comminution port — test: web/src/engines/analytical/comminution/t_018_070_comminution.test.ts
- [ ] T-018-071 [US-018-3] (FR-018-53, P-018-49, P-018-50, P-018-51) min-cut ultimate pit — test: web/src/engines/mincut/t_018_071_mincut.test.ts
- [ ] T-018-072 [US-018-3] (FR-018-51, P-018-52, P-018-53, P-018-54) survey cut/fill volume — test: web/src/engines/volume/t_018_072_volume.test.ts
- [ ] T-018-073 [US-018-3] (FR-018-61, FR-018-62, NFR-018-06) "Run in Python" with Pyodide and the `minephys` wheel — test: web/e2e/t_018_073_pyodide.spec.ts

## Phase 8 — Lane gate (web half)
- [ ] T-018-080 [US-018-3] (FR-018-65, P-018-71, P-018-72, P-018-73) `deriveLane` — test: web/src/lane/t_018_080_derive_lane.test.ts
- [ ] T-018-081 [US-018-3] (FR-018-64, NFR-018-03) T2 measurement suite writing DC-018-06 — test: web/e2e/lane-gate/t_018_081_measure.spec.ts
- [ ] T-018-082 [US-018-3] (FR-018-66, FR-000-15) CI mislabel check `web/scripts/check-lanes.mjs` — test: web/src/lane/t_018_082_check_lanes.test.ts

## Phase 9 — Gates, polish and independent review
- [ ] T-018-088 [US-018-3] (SC-018-01, FR-018-67) parity-report completeness: every engine of §7.1 passes or is shown in T0; invalid report or measurement files fail the build — test: web/src/engines/t_018_088_parity_report.test.ts
- [ ] T-018-089 [US-018-2] (SC-018-02) vertical slice A1 + C1 end to end on the preview build — test: web/e2e/t_018_089_vertical_slice.spec.ts
- [ ] T-018-090 (NFR-018-05) coverage and mutation run on `web/src/engines/**`, `web/src/sim/**`, `web/src/assets/shard*`, `web/src/lane/**`; the scores are checked against `thresholds.yaml` and recorded — test: tests/contract/test_t_018_090_web_quality_scores.py
- [ ] T-018-091 independent review of the diff against this spec; append tasks for gaps

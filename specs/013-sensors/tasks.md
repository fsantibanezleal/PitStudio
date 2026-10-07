# Tasks 013 — RTX sensor simulation (M23)
Format: `- [ ] T-013-xxx [US-013-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/013-sensors/tests.lock <files>`). Tests marked `gpu`
run only on the reference machine, never in CI, and only under the GPU lock.

## Phase 1 — Setup
- [ ] T-013-001 (DC-013-01, DC-013-02, DC-013-03, DC-013-04, DC-013-05) contract schemas `sensor-recipe`, `lidar-envelope`, `sensor-shard`, `web-cloud-shard`, `dust-slider` (JSON Schema 2020-12) + generated Pydantic and TypeScript types + drift check — test: tests/contract/test_t_013_001_sensor_schemas.py
- [ ] T-013-002 resolve and lock the `studio/rtx/` additions (pyarrow, zarr, jsonschema, minephys) and the dev-only `mmh3` reference on their target interpreters; prove `uv sync --frozen` and an import smoke on 3.12 and 3.14 before feature code (no requirement IDs; dependency gate)

## Phase 2 — US-013-3 (P1) lane safety
- [ ] T-013-010 [US-013-3] (FR-013-01, FR-013-02) `SensorBackend` protocol, factory and fake backend; import-graph scan of the lane and of `src/pitstudio/sensors/` — test: tests/unit/test_t_013_010_sensor_backend.py
- [ ] T-013-011 [US-013-3] (FR-013-03) runtime-isolation check before renderer construction — test: tests/unit/test_t_013_011_runtime_isolation.py
- [ ] T-013-012 [US-013-3] (FR-013-04, NFR-013-05) sensor-recipe validation with exit code 2 and JSON pointer; hostile recipe corpus — test: tests/unit/test_t_013_012_recipe_validation.py
- [ ] T-013-013 [US-013-3] (FR-013-05, FR-013-06, DC-013-08) elevation-fan envelope guard and the `ovrtx` probe writer (no performance fields) — test: tests/unit/test_t_013_013_lidar_envelope.py
- [ ] T-013-014 [US-013-3] (FR-013-07, FR-013-08, FR-013-10) warm-up discard, point-count guard (stop at frame k) and per-frame counts in the index — test: tests/unit/test_t_013_014_point_count_guard.py
- [ ] T-013-015 [US-013-3] (FR-013-09) backend-output validation against a malformed-frame corpus — test: tests/unit/test_t_013_015_backend_output.py
- [ ] T-013-016 [US-013-3] (FR-013-31) shard writer: Parquet, Zarr v3 chunks, PNG, all ≤ 10 MB, index with SHA-256 — test: tests/pipeline/test_t_013_016_shard_writer.py
- [ ] T-013-017 [US-013-3] (FR-013-32, SC-013-02, DC-013-07) manifest marker `performance: local-only`, licence classes, no performance field in committed copies — test: tests/contract/test_t_013_017_manifest_local_only.py
- [ ] T-013-018 [US-013-3] (FR-013-33, NFR-013-04) clean-room repository scan (SPDX headers, NVIDIA notices, NVIDIA asset references) and adapter line budget — test: tests/unit/test_t_013_018_clean_room.py
- [ ] T-013-019 [US-013-3] (FR-013-34) statistical re-run check (counts ±1 %, Chamfer ≤ 3σ, PSNR ≥ 40 dB) — test: tests/unit/test_t_013_019_rerun_check.py

## Phase 3 — US-013-1 (P1) dust post-model, radar and metrics
- [ ] T-013-020 [US-013-1] (FR-013-11, P-013-01, P-013-02) optical depth with `minephys.environment` and two-way intensity — test: tests/property/test_t_013_020_dust_optical_depth.py
- [ ] T-013-021 [US-013-1] (FR-013-12, FR-013-13, P-013-03, P-013-04, P-013-05, P-013-06, SC-013-01) detection rule and leading-edge dust returns — test: tests/metamorphic/test_t_013_021_dust_rule.py
- [ ] T-013-022 [US-013-1] (FR-013-14, P-013-12) beam hash against the MurmurHash3 reference; uniformity — test: tests/property/test_t_013_022_beam_hash.py
- [ ] T-013-023 [US-013-1] (FR-013-15) dust post-model hostile inputs — test: tests/unit/test_t_013_023_dust_hostile.py
- [ ] T-013-024 [US-013-1] (FR-013-21, FR-013-22, FR-013-24) radar configuration guard, detection contract, sign normalisation, dust independence — test: tests/unit/test_t_013_024_radar_lane.py
- [ ] T-013-025 [US-013-1] (FR-013-36, FR-013-37, FR-013-42, P-013-13, SC-013-04) S1 metrics (P_d, points on target, dust returns, TTC margin), lidar-vs-radar comparison with the decision rule, hostile metric inputs — test: tests/metamorphic/test_t_013_025_s1_metrics.py
- [ ] T-013-026 [US-013-1] (FR-013-35, FR-013-42, P-013-11) web cloud-shard quantiser and its hostile inputs — test: tests/property/test_t_013_026_cloud_quantiser.py

## Phase 4 — US-013-2 (P1) live dust slider
- [ ] T-013-030 [US-013-2] (FR-013-38, P-013-15, SC-013-03) slider bake in `s60_export` and the TypeScript dust worker; Python goldens at 41 levels — test: web/src/engines/sensors/dust-slider-parity.test.ts
- [ ] T-013-031 [US-013-2] (FR-013-14) TypeScript MurmurHash3 known-answer vectors from the Python reference — test: web/src/engines/sensors/beam-hash.test.ts
- [ ] T-013-032 [US-013-2] (FR-013-39) hostile slider assets and out-of-range levels — test: web/src/engines/sensors/dust-slider-hostile.test.ts
- [ ] T-013-033 [US-013-2] (NFR-013-01, NFR-013-02, FR-013-38) slider timing on T2 and asset/worker sizes — test: web/e2e/sensors-dust-slider.spec.ts
- [ ] T-013-034 [US-013-2] (FR-013-40, FR-013-41, FR-013-24, NFR-013-03) sensor-comparison widget, local-only card, radar-immunity label, "not yet run" states, shard sizes — test: web/e2e/sensors-widget.spec.ts

## Phase 5 — US-013-4 (P2) cameras
- [ ] T-013-040 [US-013-4] (FR-013-16, P-013-07) S3 haze post-model — test: tests/metamorphic/test_t_013_040_haze.py
- [ ] T-013-041 [US-013-4] (FR-013-17) S3 semantic-component boxes against `scipy.ndimage.label` — test: tests/unit/test_t_013_041_component_boxes.py
- [ ] T-013-042 [US-013-4] (FR-013-18, P-013-08) S2 exposure, noise and vignetting — test: tests/metamorphic/test_t_013_042_exposure.py
- [ ] T-013-043 [US-013-4] (FR-013-19, P-013-14) pinhole intrinsics, poses and GSD worked example — test: tests/metamorphic/test_t_013_043_pinhole.py
- [ ] T-013-044 [US-013-4] (FR-013-20) camera post-model hostile inputs — test: tests/unit/test_t_013_044_camera_hostile.py

## Phase 6 — slope radar S4b (retired, integration 2026-10-07: moved to spec 010-slope, tasks T-010-050…055)
- ~~T-013-050~~ retired (LOS projection; now T-010-050, T-010-054)
- ~~T-013-051~~ retired (phase, noise, unwrapping, ambiguity flag; now T-010-050, T-010-054)
- ~~T-013-052~~ retired (S4b hostile inputs; now T-010-051, T-010-055)

## Phase 7 — US-013-6 (P3) rain arm
- [ ] T-013-060 [US-013-6] (FR-013-29, FR-013-30) `isaac` sensor backend behind the protocol (fake), guards reused, "not run" paths, rain refused on `ovrtx` — test: tests/unit/test_t_013_060_rain_arm.py

## Phase 8 — Local GPU integration (reference machine, after the GPU hold is lifted)
- [ ] T-013-070 [US-013-3] (FR-013-06, FR-013-07, FR-013-08, FR-013-19) `ovrtx` backend smoke: probe scene envelope, warm-up, non-empty S1 frames, S2 marker projection within 0.5 px — test: tests/gpu/test_t_013_070_ovrtx_smoke.py
- [ ] T-013-071 [US-013-1] (FR-013-23) S4a Doppler validation scene — test: tests/gpu/test_t_013_071_radar_doppler.py
- [ ] T-013-072 [US-013-6] (FR-013-29) rain arm local render at 0 and 50 mm/h — test: tests/gpu/test_t_013_072_rain_render.py
- [ ] T-013-073 [US-013-3] (FR-013-34) re-run check on one real shard — test: tests/gpu/test_t_013_073_rerun_real.py

## Phase 9 — Polish and review
- [ ] T-013-090 mutation run on `src/pitstudio/sensors/` and the lane guards; record the score (numerical core ≥ 0.80)
- [ ] T-013-091 independent review of the diff against this spec; append tasks for gaps

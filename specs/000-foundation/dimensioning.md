# Dimensioning of PitStudio

The size of the solution: repositories and deployables, stack, modules and their requirements, data, GPU-hours and agent-hours. Every number is derived from the specs, the lock files, `studio/capabilities.json`, the dataset cards or a measurement, and says which. A number that no source gives is marked UNVERIFIED and is not used in a total. FR-000-24 requires the per-spec counts to equal `specs/requirements.index.json` and the `tasks.md` files, and the whole document to be re-measured at each gate.

Companion documents: [module map](module-map.md) (modules, contracts, edges), [modules.yaml](modules.yaml), [foundation spec](spec.md).

## 1. Repositories, components and deployables

### 1.1 Repositories

| Repository | Role | Source of the fact |
|---|---|---|
| PitStudio (this repository) | the product: studio, pipeline, web app, specs, docs; Apache-2.0 | `pyproject.toml`, `STRUCTURE.md` |
| `minephys` | companion library of the physical models (geotechnics, blasting, environment, comminution, planning, haulage); its own `specs/` | root `uv.lock`: git source pinned at commit `143e709` |
| `minehaulsim` 0.12.1 | discrete-event haulage engine used through the spec 007 adapter | `pipeline/uv.lock` (PyPI) |
| `oreblocks` 0.5.2 | seeded block-model generator with stamped optima | `pipeline/uv.lock` (PyPI) |

### 1.2 Components (areas of the repository and environments)

| Component | Environment | Python | Lock entries | Modules | Modules needing the GPU |
|---|---|---|---|---|---|
| `src/pitstudio/`, `tools/`, `api/` (core, contracts glue, runner, console, CI checks) | root | 3.14.* | 60 | 22 | 0 |
| `pipeline/` (download, synthesize, preprocess, train, infer, evaluate, export) | pipeline | 3.14.* | 113 | 47 | 7 |
| `pipeline/accel/` (TensorRT 11 engines and bench; local only) | pipeline/accel | 3.14.* | 14 | 2 | 2 |
| `studio/` (scene, physics, encode, bench) | studio | 3.14.* | 60 | 17 | 11 |
| `studio/isaac/` (Isaac Sim, Replicator, Kit) | studio/isaac | 3.12.* | 174 | 4 | 3 |
| `studio/rtx/` (ovrtx sensors) | studio/rtx | 3.12.* | 9 | 3 | 3 |
| `studio/isaaclab/` (Isaac Lab IL) | studio/isaaclab | 3.12.* | 170 | 2 | 2 |
| `web/` (React app, 25 browser engines, build scripts) | web | Node 24, pnpm 11 | 222 packages (`pnpm-lock.yaml`) | 48 | 0 |
| external actors (maintainer, test authors, operator) | external | - | - | 3 | 0 |

Total: 148 modules, 134 contracts, 393 edges, 28 modules that need the GPU.

### 1.3 Deployables

| Deployable | What it is | Host and gate | Size limits (from `thresholds.yaml`) |
|---|---|---|---|
| Static site | the React app prerendered with 12 cases, the studio, theory, methods, results and knowledge routes | GitHub Pages through `pages.yml` (jobs `build`, `deploy`, `smoke`); static, no COOP/COEP | total 500 MB; first view 2 MB; own JS 10 MB; videos 150 MB; tiles and glb 95 MB; shards and clouds 60 MB; splats 25 MB; ONNX 80 MB (25 MB each live); runtimes 55 MB; studio showcase 25 MB; baked assets in git 100 MB |
| Browser "API" | static JSON manifests (`web/public/assets/manifest.json`, per-run manifests and telemetry, `studio/index.json`, `results/*.json`, `knowledge/bundle.json`) and 25 in-browser engines (TypeScript, WebAssembly with Rapier, WGSL, ONNX Runtime Web, Pyodide) behind one engine host | served by the same Pages artifact; validated against the contracts at build and at load | each manifest entry carries bytes and SHA-256; lane gate: asset 25 MB, interaction 16 ms or run 1 s on T2, trace 10 MB |
| Local console API | loopback FastAPI on 127.0.0.1 with 13 endpoints (health, recipes, queue, jobs, cancel, runs, artefacts, events, openapi, ui) | the operator's machine only; never part of the public site; run in CI as a service from the first build week | p95 latency of non-streaming endpoints <= 200 ms (NFR-003-01) |
| Studio environments | seven isolated uv environments (section 1.2) driven by the runner `studio` (10 command forms: plan, run, queue ls, queue cancel, worker, status, gc, publish, bench env, profile) | the reference workstation (one RTX 5000 Ada Laptop GPU, 16 GB); CI uses the fake GPU backend only | runner <= 1,500 lines of code (NFR-000-08) |
| CI | `ci.yml` (jobs `python`, `web`) and `pages.yml` | GitHub Actions, hosted Linux runners, no GPU | contract check <= 30 s for 2,000 artefacts (NFR-001-01) |

## 2. Stack and pinned versions

Versions are read from the lock files and from `studio/capabilities.json` (the P3 capability proof, generated 2026-10-11 on NVIDIA RTX 5000 Ada Generation Laptop GPU, driver 595.95). None is typed from memory.

### 2.1 Capability probes

| Probe | Status | Versions recorded by the probe |
|---|---|---|
| `warp_newton` | pass | python 3.14.4, warp 1.17.0, usd 0.26.8, newton 1.6.0 |
| `torch_ort` | pass | python 3.14.4, torch 2.14.1+cu130, torch_cuda 13.0, cudnn 92400, onnxruntime 1.30.0 |
| `tensorrt` | pass | python 3.14.4, tensorrt 11.3.0.99, polygraphy 0.53.6, cuda_runtime 13.4.92 |
| `nvenc` | pass | python 3.14.4, ffmpeg n8.1.3-14-g330caae0c1-20261003, pynvvideocodec 2.2.3 |
| `ovrtx` | pass | python 3.12.15, ovrtx 0.5.0.377615, ovstage 0.2.0.377349, ovphysx 0.6.3, warp 1.17.0, numpy 2.5.3, ovrtx_runtime 0.5.0 |
| `isaacsim` | pass | python 3.12.15, isaacsim 6.1.0.0, numpy 2.3.1, kit 110.3.0+feature.371399.00c488ae.gl, torch 2.11.0+cu130, warp 1.16.0 |
| `isaaclab` | pass | python 3.12.15, isaaclab 17.0.2, isaaclab_newton 5.4.1, isaaclab_tasks 18.0.1, isaaclab_rl 0.16.3, torch 2.11.0+cu128, torchvision 0.26.0+cu128, warp_lang 1.16.0, newton 1.5.2, mujoco 3.11.0, mujoco_warp 3.11.0, rsl_rl_lib 5.4.1, cuda 12.8 |

7 of 7 probes pass. The probe for `llamacpp` (spec 015) is not in the file yet: UNVERIFIED until it runs.

### 2.2 Python environments (locked)

| Environment | Python | Key packages (lock) |
|---|---|---|
| root | 3.14.* | numpy 2.5.3, pydantic 2.13.5, jsonschema 4.26.0, pyyaml 6.0.3, fastapi 0.142.2, uvicorn 0.54.0, filelock 4.0.10, psutil 7.2.2, nvidia-ml-py 13.615.71, pytest 9.1.1, hypothesis 6.168.3, ruff 0.16.10, mypy 2.4.0, datamodel-code-generator 0.83.0 |
| pipeline | 3.14.* | torch 2.14.1+cu130, torchvision 0.29.1+cu130, onnx 1.23.1, onnxruntime 1.30.0, numpy 2.5.3, scipy 1.18.1, scikit-learn 1.9.1, pyarrow 25.0.1, zarr 3.4.0, networkx 3.7, minehaulsim 0.12.1, oreblocks 0.5.2, pydantic 2.13.5 |
| pipeline/accel | 3.14.* | tensorrt-cu13-libs 11.3.0.99, onnx 1.23.1, numpy 2.5.3, nvidia-ml-py 13.615.71 |
| studio | 3.14.* | warp-lang 1.17.0, newton 1.6.0, usd-core 26.8, numpy 2.5.3, pyarrow 25.0.1, zarr 3.4.0, ortools 9.15.6755, rasterio 1.5.2, pyproj 3.8.0, shapely 2.1.2, laspy 2.7.0, trimesh 5.1.1, pynvvideocodec 2.2.3, pandas 3.0.6 |
| studio/isaac | 3.12.* | isaacsim 6.1.0.0, torch 2.11.0+cu130, onnxruntime 1.26.0, warp-lang 1.17.0, newton 1.5.0, numpy 2.3.1 |
| studio/rtx | 3.12.* | warp-lang 1.17.0, numpy 2.5.3, pyyaml 6.0.3 (ovrtx comes from the probe, section 2.1) |
| studio/isaaclab | 3.12.* | isaaclab 17.0.2, torch 2.11.0+cu128, torchvision 0.26.0+cu128, warp-lang 1.16.0, newton 1.5.2, onnx 1.23.1 |

### 2.3 Web

Node 24 (`web/.nvmrc`), `packageManager` pnpm@11.28.4. Resolved in `web/pnpm-lock.yaml`: react 19.3.0, react-router 8.4.0, vite 8.3.2, vitest 5.0.3, typescript 7.0.2, playwright 1.63.0, i18next 26.4.2, @biomejs/biome -. Planned and not yet locked (spec 018 plan; resolved by the first task that needs each, so UNVERIFIED today): three, @react-three/fiber, @react-three/drei, 3d-tiles-renderer, @sparkjsdev/spark, onnxruntime-web, @dimforge/rapier3d-simd-compat, pyodide, comlink, hyparquet, fast-check, Stryker.

## 3. Modules, requirements, tasks and tests

### 3.1 Per spec

Counts of active requirements are from `specs/requirements.index.json`; tasks and planned test files are from the `tasks.md` files (a task carries one test path; "with test" means the task names a test file). The index lists no test yet (`tests` is empty for every requirement), so **0 tests exist**; the figures below are planned.

| Spec | Modules | Components (plan) | US | FR | NFR | SC | P | DC | Tasks | With test | Without test | Test files planned |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 000-foundation | 3 | 0 | 6 | 24 | 8 | 4 | 3 | 6 | 34 | 31 | 3 | 31 |
| 001-contracts | 5 | 13 | 5 | 53 | 5 | 1 | 8 | 8 | 27 | 26 | 1 | 26 |
| 002-runner | 7 | 0 | 6 | 69 | 5 | 1 | 13 | 6 | 38 | 37 | 1 | 37 |
| 003-console | 3 | 9 | 5 | 31 | 3 | 1 | 4 | 4 | 21 | 19 | 2 | 19 |
| 004-scene-pipeline | 6 | 13 | 5 | 44 | 5 | 2 | 12 | 8 | 39 | 35 | 4 | 35 |
| 005-physics | 1 | 13 | 6 | 56 | 5 | 2 | 28 | 6 | 47 | 44 | 3 | 44 |
| 006-media-telemetry | 2 | 9 | 3 | 22 | 3 | 2 | 8 | 3 | 20 | 17 | 3 | 17 |
| 007-haulage-dispatch | 12 | 18 | 5 | 47 | 5 | 4 | 21 | 5 | 39 | 3 | 36 | 3 |
| 008-data-pipeline | 5 | 16 | 5 | 48 | 3 | 1 | 11 | 4 | 31 | 3 | 28 | 3 |
| 009-perception | 6 | 7 | 6 | 53 | 6 | 7 | 14 | 5 | 44 | 41 | 3 | 41 |
| 010-slope | 6 | 16 | 5 | 48 | 6 | 5 | 17 | 5 | 48 | 46 | 2 | 46 |
| 011-surrogates | 5 | 12 | 4 | 51 | 4 | 6 | 16 | 4 | 44 | 42 | 2 | 42 |
| 012-fragmentation | 8 | 8 | 6 | 48 | 4 | 5 | 18 | 5 | 35 | 32 | 3 | 32 |
| 013-sensors | 7 | 15 | 5 | 39 | 5 | 4 | 13 | 7 | 37 | 34 | 3 | 34 |
| 014-robot-learning | 6 | 16 | 5 | 49 | 5 | 10 | 15 | 7 | 45 | 43 | 2 | 43 |
| 015-vlm | 8 | 17 | 5 | 50 | 4 | 6 | 12 | 8 | 35 | 32 | 3 | 32 |
| 016-export-acceleration | 4 | 7 | 6 | 40 | 6 | 3 | 12 | 5 | 28 | 25 | 3 | 25 |
| 017-planning-survey | 11 | 15 | 5 | 53 | 7 | 6 | 19 | 5 | 40 | 38 | 2 | 38 |
| 018-web-cases | 29 | 20 | 7 | 69 | 6 | 2 | 54 | 6 | 57 | 56 | 1 | 56 |
| 019-web-studio | 5 | 8 | 5 | 49 | 6 | 2 | 5 | 2 | 28 | 27 | 1 | 27 |
| 020-web-knowledge | 6 | 12 | 6 | 54 | 9 | 3 | 32 | 4 | 35 | 34 | 1 | 34 |
| **Total** | 145 | 244 | 111 | 997 | 110 | 77 | 335 | 113 | 772 | 665 | 107 | 665 |

1743 active requirements and 42 retired ones (never reused); 772 tasks; the modules column counts code modules, not the 3 external actors.

### 3.2 Public interfaces counted in the specs

| Module group | Public interface | Count | Source |
|---|---|---|---|
| `runner-core`, `runner-publish`, `bench-probes`, `profile-stages` | `studio` command forms | 10 | spec 002 plan, section D1 |
| `console-api`, `console-jobs` | HTTP endpoints | 13 | spec 003 plan, endpoint table |
| 25 browser engines | one input schema and one output schema each (`contracts/engines/<id>.schema.json`) | 25 | spec 018 section 7.1 and `specs/018-web-cases/contracts/engines/` |
| TypeScript ports of `minephys` | port functions (geotech 6, environment 2, others) | at least 8 listed | spec 018 section 7.1 port table |
| every stage module | one stage entry (`job.json` in, `result.json` out) | 29 modules carry a runner stage | `modules.yaml` field `stage` |
| every module | contract inputs and outputs | see 3.3 | `modules.yaml` |

Function-level counts of the library code (for example the individual solvers and KPI functions) are not fixed by the specs; they are one of the numbers the first task of each spec records (UNVERIFIED until then).

### 3.3 Per module

`FR rows` and `Task lines` count the requirement rows and task lines that name the module's stage id or engine id; a dash means the module has no id of its own in the specs and its requirements are counted only at the spec level (3.1).

| Module | Spec | Env | GPU | Inputs | Outputs | FR rows | Task lines |
|---|---|---|---|---|---|---|---|
| `contracts-validate` | 001 | root | no | 9 | 0 | - | - |
| `contracts-gen-py` | 001 | root | no | 1 | 1 | - | - |
| `contracts-gen-ts` | 001 | web | no | 1 | 1 | - | - |
| `ci-guards` | 000 | root | no | 2 | 0 | - | - |
| `modules-check` | 000 | root | no | 1 | 0 | - | - |
| `ci-lane-check` | 001 | root | no | 1 | 0 | - | - |
| `ci-pages-deploy` | 001 | root | no | 2 | 0 | - | - |
| `runner-core` | 002 | root | no | 4 | 1 | - | - |
| `runner-guards` | 002 | root | no | 1 | 1 | - | - |
| `runner-telemetry` | 002 | root | no | 1 | 1 | - | - |
| `runner-store` | 002 | root | no | 7 | 2 | - | - |
| `runner-publish` | 002 | root | no | 6 | 5 | - | - |
| `stagekit` | 002 | root | no | 1 | 1 | - | - |
| `bench-probes` | 002 | studio | yes | 0 | 1 | - | - |
| `console-api` | 003 | root | no | 2 | 3 | - | - |
| `console-jobs` | 003 | root | no | 2 | 2 | - | - |
| `console-ui` | 003 | web | no | 4 | 0 | - | - |
| `st10_terrain` | 004 | studio | no | 1 | 2 | 15 | 0 |
| `st20_pit_design` | 004 | studio | no | 3 | 3 | 9 | 0 |
| `st30_assets` | 004 | studio | no | 3 | 1 | 6 | 0 |
| `st40_compose` | 004 | studio | no | 3 | 2 | 6 | 0 |
| `st45_validate` | 004 | studio | no | 4 | 2 | 7 | 0 |
| `st45b_kit_validate` | 004 | studio/isaac | no | 0 | 1 | 0 | 0 |
| `st50_physics` | 005 | studio | yes | 4 | 8 | 17 | 1 |
| `calibration-driver` | 011 | studio | yes | 0 | 1 | - | - |
| `st56_encode` | 006 | studio | yes | 1 | 2 | 17 | 0 |
| `profile-stages` | 006 | studio | yes | 0 | 1 | - | - |
| `s00_download` | 008 | pipeline | no | 1 | 2 | 18 | 2 |
| `s05_haul` | 007 | pipeline | no | 0 | 2 | - | - |
| `s05_creep` | 010 | pipeline | no | 0 | 2 | - | - |
| `s05_sensors` | 013 | pipeline | no | 2 | 1 | - | - |
| `s05_comminution` | 017 | pipeline | no | 0 | 2 | - | - |
| `s05_oreblocks` | 017 | pipeline | no | 0 | 2 | - | - |
| `s10_real_data` | 008 | pipeline | no | 2 | 5 | - | - |
| `s10_synthetic_data` | 008 | pipeline | no | 4 | 1 | - | - |
| `s20_feature_extraction` | 008 | pipeline | no | 1 | 0 | 6 | 0 |
| `data-card-check` | 008 | root | no | 2 | 0 | - | - |
| `haul-network-builder` | 007 | pipeline | no | 1 | 1 | - | - |
| `haul-des-adapter` | 007 | pipeline | no | 1 | 1 | - | - |
| `haul-kpi` | 007 | pipeline | no | 1 | 0 | - | - |
| `haul-routing` | 007 | pipeline | no | 2 | 1 | - | - |
| `haul-train` | 007 | pipeline | yes | 1 | 1 | - | - |
| `haul-eval` | 007 | pipeline | no | 1 | 2 | - | - |
| `st55_sdg` | 009 | studio/isaac | yes | 2 | 5 | 6 | 2 |
| `sdg-dr-sampler` | 009 | studio | no | 1 | 1 | - | - |
| `perception-dataset-builder` | 009 | pipeline | no | 1 | 1 | - | - |
| `perception-train` | 009 | pipeline | yes | 2 | 1 | - | - |
| `perception-infer` | 009 | pipeline | yes | 1 | 1 | - | - |
| `perception-eval` | 009 | pipeline | no | 2 | 2 | - | - |
| `slope-analysis` | 010 | pipeline | no | 1 | 1 | - | - |
| `slope-radar-builder` | 010 | pipeline | no | 0 | 1 | - | - |
| `slope-train` | 010 | pipeline | yes | 2 | 1 | - | - |
| `slope-infer` | 010 | pipeline | no | 2 | 1 | - | - |
| `slope-eval` | 010 | pipeline | no | 3 | 2 | - | - |
| `gns-train` | 011 | pipeline | yes | 3 | 1 | - | - |
| `fno-train` | 011 | pipeline | yes | 3 | 1 | - | - |
| `surrogates-infer` | 011 | pipeline | no | 1 | 1 | - | - |
| `surrogates-eval` | 011 | pipeline | no | 4 | 1 | - | - |
| `frag-pile-generator` | 012 | studio | yes | 1 | 1 | - | - |
| `frag-dataset-builder` | 012 | pipeline | no | 2 | 1 | - | - |
| `frag-split-builder` | 012 | pipeline | no | 0 | 1 | - | - |
| `unet-train` | 012 | pipeline | yes | 3 | 1 | - | - |
| `unet-infer` | 012 | pipeline | no | 1 | 1 | - | - |
| `frag-watershed` | 012 | pipeline | no | 0 | 1 | - | - |
| `frag-eval` | 012 | pipeline | no | 5 | 2 | - | - |
| `frag-d1-grid` | 012 | pipeline | no | 0 | 1 | - | - |
| `st52_rtx_render` | 013 | studio/rtx | yes | 0 | 3 | 0 | 0 |
| `st53_sensors` | 013 | studio/rtx | yes | 3 | 3 | 11 | 0 |
| `st57_rain_lidar` | 013 | studio/isaac | yes | 1 | 2 | 5 | 0 |
| `rtx-lidar-envelope-probe` | 013 | studio/rtx | yes | 0 | 1 | - | - |
| `sensors-metrics` | 013 | pipeline | no | 1 | 0 | - | - |
| `il-train` | 014 | studio/isaaclab | yes | 2 | 3 | - | - |
| `il-mpm-eval` | 014 | studio/isaaclab | yes | 2 | 2 | - | - |
| `il-twin-runner` | 014 | pipeline | no | 1 | 1 | - | - |
| `il-eval` | 014 | pipeline | no | 1 | 1 | - | - |
| `vlm-query-builder` | 015 | root | no | 1 | 1 | - | - |
| `vlm-pair-builder` | 015 | root | no | 0 | 1 | - | - |
| `st59a_vqa` | 015 | studio | yes | 2 | 2 | 0 | 0 |
| `st59b_plausibility` | 015 | studio | yes | 2 | 2 | 0 | 0 |
| `st59c_captions` | 015 | studio | yes | 1 | 2 | 0 | 0 |
| `st59_reason_bench` | 015 | studio | yes | 1 | 1 | 1 | 0 |
| `vlm-scoring` | 015 | root | no | 3 | 2 | - | - |
| `vlm-detector-rule` | 015 | root | no | 1 | 1 | - | - |
| `s60_export` | 016 | pipeline | no | 13 | 12 | 27 | 1 |
| `s62_accel` | 016 | pipeline/accel | yes | 2 | 1 | 6 | 0 |
| `s64_bench` | 016 | pipeline/accel | yes | 1 | 4 | 13 | 0 |
| `release-tooling` | 016 | root | no | 1 | 0 | - | - |
| `meta-train` | 017 | pipeline | no | 1 | 1 | - | - |
| `meta-eval` | 017 | pipeline | no | 2 | 1 | - | - |
| `plan-mincut` | 017 | pipeline | no | 1 | 1 | - | - |
| `plan-scheduler` | 017 | pipeline | no | 2 | 1 | - | - |
| `survey-dem-differencing` | 017 | pipeline | no | 1 | 1 | - | - |
| `survey-splat` | 017 | studio | yes | 1 | 2 | - | - |
| `survey-splat-package` | 017 | pipeline | no | 1 | 1 | - | - |
| `st58_kit_capture` | 017 | studio/isaac | yes | 0 | 1 | 1 | 0 |
| `survey-eval` | 017 | pipeline | no | 2 | 1 | - | - |
| `web-shell` | 018 | web | no | 0 | 0 | - | - |
| `web-sim-clock` | 018 | web | no | 0 | 0 | - | - |
| `web-tier-probe` | 018 | web | no | 0 | 0 | - | - |
| `web-assets-loader` | 018 | web | no | 5 | 2 | - | - |
| `web-engine-host` | 018 | web | no | 27 | 1 | - | - |
| `web-media` | 018 | web | no | 1 | 0 | - | - |
| `web-route-explore` | 018 | web | no | 2 | 0 | - | - |
| `web-route-cases` | 018 | web | no | 1 | 0 | - | - |
| `web-route-case` | 018 | web | no | 20 | 0 | - | - |
| `web-route-studio` | 019 | web | no | 4 | 0 | - | - |
| `web-route-studio-tool` | 019 | web | no | 3 | 0 | - | - |
| `web-route-studio-runs` | 019 | web | no | 4 | 0 | - | - |
| `web-route-studio-gpu` | 019 | web | no | 3 | 0 | - | - |
| `web-build-studio-index` | 019 | web | no | 1 | 1 | - | - |
| `web-route-theory` | 020 | web | no | 2 | 0 | - | - |
| `web-route-methods` | 020 | web | no | 1 | 0 | - | - |
| `web-route-results` | 020 | web | no | 6 | 0 | - | - |
| `web-route-knowledge` | 020 | web | no | 1 | 0 | - | - |
| `web-build-budgets` | 020 | web | no | 1 | 0 | - | - |
| `web-parity-suite` | 018 | web | no | 2 | 1 | - | - |
| `web-lane-gate` | 018 | web | no | 0 | 1 | - | - |
| `make-parity-fixtures` | 018 | pipeline | no | 3 | 1 | - | - |
| `engine-des` | 007 | web | no | 2 | 1 | 1 | 0 |
| `engine-policies` | 007 | web | no | 1 | 1 | 1 | 0 |
| `engine-haulage` | 007 | web | no | 0 | 1 | 2 | 0 |
| `engine-lp` | 007 | web | no | 0 | 1 | 1 | 0 |
| `engine-routing` | 007 | web | no | 0 | 1 | 1 | 0 |
| `engine-il1-twin` | 014 | web | no | 1 | 1 | 1 | 0 |
| `engine-il2-twin` | 014 | web | no | 1 | 1 | 1 | 0 |
| `engine-granular` | 018 | web | no | 0 | 1 | 0 | 0 |
| `engine-gns` | 018 | web | no | 1 | 1 | 1 | 0 |
| `engine-traffic` | 018 | web | no | 0 | 1 | 0 | 0 |
| `engine-dust-lidar` | 013 | web | no | 1 | 1 | 1 | 0 |
| `engine-detector` | 018 | web | no | 1 | 1 | 0 | 0 |
| `engine-geotech` | 018 | web | no | 0 | 1 | 1 | 1 |
| `engine-forecasters` | 018 | web | no | 1 | 1 | 1 | 0 |
| `engine-swe` | 018 | web | no | 0 | 1 | 0 | 0 |
| `engine-fno` | 018 | web | no | 1 | 1 | 1 | 0 |
| `engine-plume` | 018 | web | no | 0 | 1 | 0 | 0 |
| `engine-dust-particles` | 018 | web | no | 0 | 1 | 0 | 0 |
| `engine-blasting` | 018 | web | no | 0 | 1 | 0 | 0 |
| `engine-watershed` | 018 | web | no | 0 | 1 | 0 | 0 |
| `engine-unet` | 018 | web | no | 1 | 1 | 0 | 0 |
| `engine-comminution` | 018 | web | no | 0 | 1 | 2 | 0 |
| `engine-meta-model` | 018 | web | no | 1 | 1 | 2 | 0 |
| `engine-mincut` | 018 | web | no | 1 | 1 | 1 | 0 |
| `engine-volume` | 018 | web | no | 0 | 1 | 1 | 0 |
| `docs-knowledge-build` | 020 | root | no | 12 | 1 | - | - |
| `docs-check` | 000 | root | no | 0 | 0 | - | - |

## 4. Data

### 4.1 Third-party datasets

Download sizes are those reported by the publisher on the dataset cards; nothing is committed (NFR-008-03). `data/sources.yaml` holds no entry yet (`sources: []`), so the registry volumes are not machine-readable today: the cards are the source.

| Dataset | Source id | Licence (SPDX) | Size (download) | Licence class | Fallback if unavailable |
|---|---|---|---|---|---|
| USGS 3DEP Bingham Canyon | `usgs-3dep-bingham` | `LicenseRef-USGov-PD` | DEM 5.0–257.4 MB per epoch; 69 LAZ tiles of 10–37 MB | `public-domain` | none (core site) |
| McKinley Mine lidar 2023 | `ot-mckinley-2023` | `CC-BY-4.0` | ~5 × 10⁹ points; area-of-interest crop | `attribution` | Bingham-only scenes + CC0 textures |
| NRW Hambach lidar and DGM1 | `nrw-hambach-dgm1` | `DL-DE-ZERO-2.0` | per tile | `open-no-attribution` | none |
| EGMS over Hambach | `egms-hambach` | project reference to the CLMS policy | per burst or 100 km tile | `attribution` (derived-only) | C1 uses de Wit + synthetic only |
| de Wit open-pit slope failure | `dewit-slope-failure` | `CC-BY-4.0` | 8.9 MB (+ optional 7.5 GB HDF5) | `attribution` | none |
| Mendeley rock fragments | `mendeley-78ht3pjsr4` | `CC-BY-4.0` | 4.23 GB (SHA-256 published) | `attribution` | synthetic-only U-Net claim |
| Tang & Werner mining footprint | `tang-werner-footprint` | `CC-BY-4.0` | 296 MB | `attribution` | none |
| Xu et al. surface mining 1985–2022 | `xu-expansion-v3` | `CC-BY-4.0` | 32.8 MB | `attribution` | none |
| Maus et al. mining polygons v2 (optional) | `maus-v2` | `CC-BY-SA-4.0` | 23.5 MB | `share-alike` | Tang & Werner |
| ERA5 and GHCNh wind | `era5`, `ghcnh` | `CC-BY-4.0` / `LicenseRef-USGov-PD` | small (one site) | `attribution` / `public-domain` | GHCNh hourly station data (Salt Lake City) |
| MineLib marvin (optional) | `minelib-marvin` | `CC-BY-SA-3.0` | small | `share-alike` | `oreblocks` synthetic deposits (default) |
| EPA AP-42 §13.2.2 | `epa-ap42-13-2-2` | `LicenseRef-USGov-PD` | one PDF | `public-domain` | none |
| Poly Haven and ambientCG textures | `polyhaven`, `ambientcg` | `CC0-1.0` | per asset | `open-no-attribution` | none |
| MakeHuman people exports | `makehuman-exports` | `CC0-1.0` (licence §C) | per asset | `open-no-attribution` | procedural mannequins |
| Synthetic data | studio synthetic sources | `CC-BY-4.0` | ~30k images + tables and fields | `own` | NVIDIA-runtime sets end as "not run"; open-lane generators always run |

Largest items: the Mendeley archive (4,230,116,058 bytes, SHA-256 published, 4.44 GB uncompressed), the Bingham LAZ tiles (about 0.7 to 2.6 GB for 69 tiles, from the card's 10-37 MB per tile) and the optional de Wit HDF5 companion (7.5 GB or more). The fetch cost is bounded by the free-disk rule of FR-008-10 (1.2 x file size).

### 4.2 Synthetic data

The synthetic sets are produced by the studio and carry the licence CC-BY-4.0 (ours). Volumes are from the FR rows named; a rate that no spec fixes is UNVERIFIED and is measured by the runner.

| Set | Quantity | Source |
|---|---|---|
| Perception images | 3 arms x 10,000 = 30,000 requested; at least 9,500 valid per arm (28,500 minimum) | FR-009-03, NFR-009-05 |
| GNS rollouts | 100 geometries x 3 packing seeds = 300 (70 train, 10 validation, 20 test geometries) | FR-011-03 |
| FNO field data | 64 patches x (40 + 20) scenarios = 3,840 small solver runs | FR-011-34 |
| Calibration trials | 50 per arm x 2 arms = 100 | FR-011-24 |
| Mine-to-mill sweeps | 200 configurations x 64 blast designs = 12,800 chain evaluations | FR-017-02 |
| Dispatch comparison | at least 30 paired seeds per comparison | SC-000-02 |
| Muck piles, SDG rate, physics-run time, disk per image | not fixed by the specs read: UNVERIFIED | measured by the first task of specs 005, 009 and 012 |

The dataset card for the synthetic sets states about 30k images plus tables and fields, which agrees with the perception figure above.

## 5. Compute: GPU-hours

The reference machine is one 16 GB GPU, one job at a time under the machine lock, with the in-run thermal guard. The runner spec states the whole studio plan at about 55 to 150 GPU-hours in 8 to 19 overnight slots (spec 002, section 1).

### 5.1 Model families

| Family | Modules | Low (h) | High (h) | Basis |
|---|---|---|---|---|
| Dispatch policy (PPO and attention) | haul-train | - | 5.0 | NFR-007-05: `timeout_s` <= 18,000 (5 GPU-h), `vram_gib_est` <= 4 |
| Detectors D-FINE-N, D-FINE-S, RF-DETR-Seg-N | perception-train, perception-infer | - | - | spec 009 gives only NFR-009-03 (each resume segment <= 8 h) and says training GPU-hours are estimates measured by the runner: UNVERIFIED, no total |
| Slope forecasters (TCN, PatchTST, Chronos-Bolt) | slope-train | - | 2.0 | NFR-010-06: <= 2 GPU-h in total |
| GNS granular surrogate | gns-train | - | 15.0 | NFR-011-04: <= 15 GPU-h |
| FNO field surrogates (2 instances) | fno-train | - | 4.0 | NFR-011-04: each FNO <= 2 GPU-h; FR-011-33 trains two instances |
| DEM calibration (2 arms, one full-scale calibration each) | calibration-driver | - | 4.0 | NFR-011-04: each full-scale calibration <= 2 GPU-h; one per arm is an assumption (UNVERIFIED count) |
| U-Net (TSTR model and five TRTR folds) | unet-train | 2.9 | 2.9 | measured: about 29 min per fold at about 115 img/s with the guard; FR-012-22 gives the TSTR model the same number of steps, so 6 x 29 min |
| Robot learning IL-1, IL-2, IL-3 | il-train, il-mpm-eval | 5.0 | 15.0 | NFR-014-02: IL-1 1-4 h, IL-2 2-8 h, IL-3 2-3 h (upper estimates 4, 8, 3) |
| Cosmos Reason 2 tasks A-C | st59a_vqa, st59b_plausibility, st59c_captions, st59_reason_bench | 8.0 | 16.0 | NFR-015-02: plan estimate 8-16 GPU-h |
| TensorRT engines and benchmark matrix | s62_accel, s64_bench | 4.0 | 7.0 | NFR-016-02: estimate 4-7 GPU-h, <= 8 h wall time |
| **Sum of the stated figures** | | 49.9 | 70.9 | the low column uses the upper bound where only one is stated; the detector row is excluded (UNVERIFIED) |

The stated figures sum to 49.9 to 70.9 GPU-hours, inside the 55 to 150 of the runner spec once the detectors, the data jobs and the retries are added. The U-Net row is measured; every other row is an estimate that the run manifests will replace (NFR-010-06, NFR-011-04, NFR-014-02).

### 5.2 Data jobs and queue

| Job | Modules | Basis | Quantity |
|---|---|---|---|
| Physics scenario (any production scenario) | st50_physics | NFR-005-02: <= 60 min each, plan rate 1-2 scenarios per hour | - |
| GNS rollouts | st50_physics | FR-011-03: 100 geometries x 3 packing seeds | 300 rollouts |
| FNO field data | st50_physics | FR-011-34: 64 patches x (40 tailings + 20 dust) scenarios | 3,840 solver runs; time per run UNVERIFIED (measured by the first task) |
| DEM calibration coverage study | calibration-driver | FR-011-24: 50 synthetic-truth trials per arm | 100 trials |
| Perception SDG | st55_sdg, st52_rtx_render | FR-009-03: three arms of 10,000 images; NFR-009-05: at least 9,500 valid per arm | 30,000 images requested (>= 28,500 valid); rate UNVERIFIED |
| Muck piles | frag-pile-generator, st55_sdg | FR-012-09: pile generator over K = 20 size classes | pile count UNVERIFIED in the spec text read |
| Mine-to-mill sweeps | s05_comminution | FR-017-02: 200 configurations x 64 blast designs | 12,800 chain evaluations (CPU) |
| Encode (one clip pair) | st56_encode | NFR-006-01: <= 5 min per 30 s clip pair | - |
| Reconstruction (one flight) | survey-splat | NFR-017-07: <= 2 h per flight (estimate) | - |

Guard overhead: NFR-002-03 bounds the runner overhead at 1.0 s per stage execution. The measured U-Net pace (about 115 img/s, 29 min per fold) already includes the in-run guard. Queue order follows the dependency order of the module map: solvers and renders first (they feed the training sets), then training, evaluation and export, then the acceleration bench last (it needs the exported ONNX files). No GPU job is run in CI (NFR-016-06).

## 6. Effort per track

Pace: about 0.5 agent-hours per red task and 0.5 per green task (measured in the build so far), so a task with a test costs 1.0 agent-hour and a task without a test (setup, dependency proof, review) 0.5.

| Spec | Track | Tasks with test | Tasks without test | Agent-hours |
|---|---|---|---|---|
| 000-foundation | C | 31 | 3 | 32.5 |
| 001-contracts | C | 26 | 1 | 26.5 |
| 002-runner | C | 37 | 1 | 37.5 |
| 003-console | C | 19 | 2 | 20.0 |
| 004-scene-pipeline | A | 35 | 4 | 37.0 |
| 005-physics | A | 44 | 3 | 45.5 |
| 006-media-telemetry | A | 17 | 3 | 18.5 |
| 007-haulage-dispatch | B | 3 | 36 | 21.0 |
| 008-data-pipeline | A | 3 | 28 | 17.0 |
| 009-perception | B | 41 | 3 | 42.5 |
| 010-slope | B | 46 | 2 | 47.0 |
| 011-surrogates | B | 42 | 2 | 43.0 |
| 012-fragmentation | B | 32 | 3 | 33.5 |
| 013-sensors | A | 34 | 3 | 35.5 |
| 014-robot-learning | B | 43 | 2 | 44.0 |
| 015-vlm | B | 32 | 3 | 33.5 |
| 016-export-acceleration | B | 25 | 3 | 26.5 |
| 017-planning-survey | B | 38 | 2 | 39.0 |
| 018-web-cases | D | 56 | 1 | 56.5 |
| 019-web-studio | D | 27 | 1 | 27.5 |
| 020-web-knowledge | D | 34 | 1 | 34.5 |
| **Total** | | 665 | 107 | 718.5 |

Track attribution is by the spec's main work: A data and simulation (004, 005, 006, 008, 013), B models (007, 009, 010, 011, 012, 014, 015, 016, 017), C logic, APIs and connectors (000, 001, 002, 003), D web (018, 019, 020). Specs that also own web engines (007, 013, 014) or data generators are counted once, in their main track; docs (track E) are written with each unit and release and deploy (track F) are part of specs 001, 016 and 020, so neither has hours of its own.

| Track | Specs | Agent-hours | Share |
|---|---|---|---|
| A | 004, 005, 006, 008, 013 | 153.5 | 21 % |
| B | 007, 009, 010, 011, 012, 014, 015, 016, 017 | 330.0 | 46 % |
| C | 000, 001, 002, 003 | 116.5 | 16 % |
| D | 018, 019, 020 | 118.5 | 16 % |
| Total | | 718.5 | 100 % |

### 6.1 Critical path

The module map is a DAG of 148 modules whose longest chain has 20 modules. Weighting each module by its spec's agent-hours shared among the spec's modules, the heaviest chain is **135.7 agent-hours** long and runs through the specs 001 > 008 > 017 > 004 > 005 > 012 > 016 > 002 > 003:

`contracts-gen-py > s10_real_data > plan-mincut > st20_pit_design > st40_compose > st45_validate > st50_physics > frag-pile-generator > frag-dataset-builder > unet-train > unet-infer > frag-eval > s60_export > s62_accel > s64_bench > runner-store > console-api > console-ui`

With the build run as parallel tracks the elapsed effort is bounded below by this chain (135.7 agent-hours) and by the total divided by the agents running at once: with 4 agents 180 agent-hours each, with 8 agents 90. The chain is the solver-to-model path: scene stages, physics solvers and renders feed the model data, then training, evaluation, export and the web, which is why the solvers are the critical path and why every consumer is specified against a fixture (the availability states of the module map) rather than waiting for them.

GPU time on that chain: the physics solvers (1-2 scenarios per hour), GNS (<= 15 GPU-h) and the two FNOs (<= 4 GPU-h) are sequential on the one GPU; the detector and slope jobs queue behind them in the overnight slots.

## 7. Assumptions and UNVERIFIED

- Agent-hours use the measured 0.5 + 0.5 pace for every task; reviews, rework and the adversary gates are not added.
- The track split attributes each spec to one track; the critical path assumes work inside a spec is spread evenly over its modules.
- GPU rows other than the U-Net are the specs' estimates; the detector total, SDG rate, physics-run time and muck-pile count are UNVERIFIED.
- The number of full-scale DEM calibrations (one per arm) is an assumption; the spec states the per-calibration bound only.
- Planned web dependencies and the `llamacpp` probe are not locked or run yet.
- `data/sources.yaml` is empty: dataset volumes are the dataset cards' figures, not registry values.
- Function-level counts of the libraries are recorded by each spec's first task.

## 8. How this document is kept right

Per-spec counts must equal the index and the task files (T-000-095). The module and contract counts must equal `modules.yaml` (T-000-092). The document is regenerated and re-checked at every gate; a changed count is a change of this file in the same commit as the spec change that caused it.

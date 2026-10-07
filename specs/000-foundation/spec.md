# Spec 000 — Foundation: PitStudio
Status: Draft · Tier: L · Approved: —

The product-level specification, written from the approved solution plan (rev 2.4). Every feature spec
(`specs/NNN-*/`) is a child of this one and inherits its requirements, thresholds and honesty rules.

## 1. Intent

PitStudio is an open, reproducible **physical-AI simulation studio for open-pit mining**. It has four parts that share
one engine, one data contract and one manifest format:

1. A **local studio**: isolated environments, a job runner and a loopback console. It uses every Omniverse-class tool
   that runs on one RTX workstation, each in a mining role.
2. A **static web app** that explains, runs and showcases the work: 12 cases, live in-browser engines, replays of the
   studio's GPU work, a studio tool map, theory and results.
3. A **knowledge base**: `docs/` plus the companion library `minephys`.
4. A **scalable base**: the same recipes run on a Linux GPU host by switching profile.

**Who benefits:**
- mining engineers and managers (haulage, fragmentation, slope warning, tailings run-out);
- data/AI practitioners (how far synthetic-only training goes, measured where real labels exist);
- students (theory with interactive figures);
- developers (how to build an Omniverse-class pipeline on one workstation).

**Out of scope:**
- A live digital twin of a real operation (there is no telemetry feed).
- Design or regulatory software: slope, tailings and blasting outputs are educational, with stated validity ranges.
- Redistributing NVIDIA binaries, assets, engines or caches.
- Publishing performance data of software whose licence forbids it.

## 2. Users and user stories

| ID | Story | Priority |
|---|---|---|
| US-000-1 | As a mining engineer, I want to change dispatch, road grade, power train, blast design and slope-monitoring settings in a browser and see t/h, kWh/t, CO₂/t, oversize and warning lead time, so that I can reason about trade-offs with sourced models. | P1 |
| US-000-2 | As a data/AI practitioner, I want every learned model compared with a classical baseline on held-out data with confidence intervals, and every synthetic dataset validated against real data where real data exist, so that I can trust or reject the claims. | P1 |
| US-000-3 | As a student, I want each phenomenon explained with equations from primary sources and an interactive figure, so that I can learn the theory behind each case. | P2 |
| US-000-4 | As a developer, I want to reproduce any published artefact with one command and see which studio tool produced it, with its manifest and telemetry, so that I can build and operate a similar pipeline. | P1 |
| US-000-5 | As the maintainer, I want the studio to queue GPU jobs one at a time with guards, a cache and resume, so that long runs survive crashes and never compete for the GPU. | P1 |
| US-000-6 | As a reviewer or citer, I want every external number sourced, every lane and licence labelled and every "not yet run" stated, so that nothing is presented as more than it is. | P1 |

## 3. Product-level requirements (EARS)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-000-01 | Ubiquitous | The web app shall present every result with its data source, licence and lane (live / precomputed / replay). | E2E |
| FR-000-02 | Unwanted | If a compute tier cannot initialise, then the web app shall fall back to the next tier and show the active tier. | E2E (hostile) |
| FR-000-03 | Ubiquitous | The web app shall offer English (default) and Spanish, and light and dark themes, on every view. | E2E + axe |
| FR-000-04 | Event | When a visitor opens the site, the web app shall require the access gate before showing the workbench. | E2E |
| FR-000-05 | Ubiquitous | The product shall call a result "better than" another only when the paired 95 % confidence interval of the difference excludes 0, and otherwise shall state "no significant difference". | unit + E2E |
| FR-000-06 | Ubiquitous | The web app shall show, on every artefact card, a LIVE / REPLAY / STATIC badge and its provenance (producing tool, run id, commit). | E2E |
| FR-000-07 | Unwanted | If a studio tool has no published artefact, then the web app shall show it as "not yet run" (or "evaluated, not adopted" with the reason) and shall not mark it done. | unit + E2E |
| FR-000-08 | Ubiquitous | The product shall exclude performance data of software whose licence forbids publishing it (Isaac Sim, Kit, Replicator, ovrtx, TensorRT for RTX) from every committed or published artefact, and shall show "measured locally, not published (licence)" instead. | contract + CI guard |
| FR-000-09 | Ubiquitous | The product shall label every data type that has no real reference as "calibrated synthetic — not validated against real data" and shall make no C2ST or TSTR claim for it. | unit + E2E |
| FR-000-10 | Ubiquitous | The product shall attach a DOI or URL source to every external number in the UI, the docs and the knowledge tables, and shall flag every row whose value is not yet verified against its primary source as UNVERIFIED. | contract + docs check |
| FR-000-11 | Unwanted | If the public site is loaded, then the web app shall not contact a localhost service unless the visitor presses the opt-in "connect to my local studio" control. | E2E (hostile) |
| FR-000-12 | Ubiquitous | The web app shall show in the footer the version, commit SHA, build date, author, provenance, licences and a non-affiliation note for third-party trademarks. | E2E |
| FR-000-13 | Ubiquitous | The studio shall run GPU work only through the runner, which holds the machine-wide lock `gpu0.compute` (and `gpu0.nvenc` for encoding) and refuses to start while a `gpu0.hold` file exists in the lock directory. | unit (fake GPU) |
| FR-000-14 | Ubiquitous | Every published artefact shall be described by a manifest valid against `contracts/manifest.schema.json`, naming its producer tool, lane (measured, not declared), licence class, inputs with SHA-256 and the run that produced it. | contract |
| FR-000-15 | Unwanted | If a lane label in a manifest disagrees with the measured gate (asset ≤ 25 MB, interaction ≤ 16 ms or run ≤ 1 s on T2, trace ≤ 10 MB), then CI shall fail. | CI |
| FR-000-16 | Optional | Where a Linux GPU host is used, the studio shall run the same recipes by switching the profile, with no recipe change. | CI (plan with fake GPU, `linux-gpu` profile) |

## 4. Correctness properties

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-000-01 | For any run, re-running the same recipe with the same code, lock, params, seed and inputs yields the same cache key and, for deterministic stages, byte-identical outputs. | recipes × seeds (Hypothesis) | exact |
| P-000-02 | For any published artefact, the SHA-256 recorded in its manifest equals the SHA-256 of the served file. | every artefact at build | exact |
| P-000-03 | For any live engine with a Python reference, the browser output equals the reference within the system-class tolerance of `thresholds.yaml` (`web.*`). | per-engine parity fixtures | per class |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-000-01 | Initial JavaScript (gzip) | ≤ 200 KB | build report |
| NFR-000-02 | Accessibility | axe 0 serious/critical; Lighthouse a11y ≥ 0.95 | Playwright + LHCI |
| NFR-000-03 | First view (bytes transferred before interaction) | ≤ 2 MB | build report + Playwright |
| NFR-000-04 | Site total and per-class budgets | total = 500 MB; class caps as in `thresholds.yaml` `budgets` | CI budget check |
| NFR-000-05 | Files in git | each < 10 MB; baked assets in git ≤ 100 MB in total; larger files are release assets pinned by SHA-256 | CI size check |
| NFR-000-06 | Live model size | each ≤ 25 MB | CI budget check |
| NFR-000-07 | Video pair (AV1 1080p + H.264 720p) | ≤ 25 MB per pair | CI budget check |
| NFR-000-08 | Runner size | ≤ 1,500 lines of code (re-assess a framework beyond it) | CI line count |
| SC-000-01 | Fragmentation segmentation trained on synthetic exact-PSD muck piles vs on real images, both tested on the real held-out originals | TSTR ≥ 0.90 × TRTR (IoU), grouped k-fold | spec 012 evaluation |
| SC-000-02 | Learned dispatch vs SPTF / LP on t/h | "better" only by the decision rule over ≥ 30 paired seeds | spec 007 evaluation |
| SC-000-03 | GNS granular surrogate on held-out geometries | repose ±1.5°, run-out ±5 % | spec 011 evaluation |
| SC-000-04 | Synthetic-data detector | synthetic held-out mAP50 ≥ 0.80 (S), ≥ 0.70 (N); relative drop ≤ 10 pp at corruption severity ≤ 2 | spec 009 evaluation |

Feature-level acceptance criteria (FNO, forecasters, meta-model, Isaac Lab, Cosmos, TensorRT parity, DEM calibration)
live in their feature specs. They are copied from the plan's §7 and calibrated in `thresholds.yaml`.

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-000-01 | `web/public/assets/manifest.json` and per-run manifests | `contracts/manifest.schema.json` | runner / export stage → web app, CI |
| DC-000-02 | `studio/capabilities.json` | `contracts/capabilities.schema.json` | `studio/bench/run_bench.py` → runner guards, web `/studio` |
| DC-000-03 | runner recipes `recipes/*.yaml` | `contracts/recipe.schema.json` | maintainer → runner |
| DC-000-04 | studio tool registry `studio/tools.yaml` | `contracts/tools.schema.json` | maintainer → web tool map |
| DC-000-05 | data registry `data/sources.yaml` | `contracts/sources.schema.json` | maintainer → `s00_download`, docs |

## 7. Data sources (summary — full registry in `data/sources.yaml`)

| Source id | Real / synthetic | Licence (SPDX) | Redistribution |
|---|---|---|---|
| usgs-3dep-bingham | real | public domain (US Government work) | derived tiles, meshes, volumes |
| ot-mckinley-2023 | real | CC-BY-4.0 | derived meshes/textures |
| nrw-hambach-dgm1 | real | dl-de/zero-2.0 | derived |
| egms-hambach | real | Copernicus (derived-only) | derived summaries |
| dewit-slope-failure | real | CC-BY-4.0 | derived series |
| mendeley-78ht3pjsr4 | real | CC-BY-4.0 | metrics only |
| tang-werner-footprint | real | CC-BY-4.0 | masks |
| xu-expansion-v3 | real | CC-BY-4.0 | expansion curves |
| maus-v2 (optional) | real | CC-BY-SA-4.0 | separate share-alike layer |
| era5 / ghcnh | real | CC-BY-4.0 / US Government | wind statistics |
| minelib-marvin (optional) | real | CC-BY-SA-3.0 | derived-only, share-alike |
| epa-ap42-13-2-2 | real | public domain | cited table rows |
| polyhaven / ambientcg | real | CC0-1.0 | textures |
| makehuman-exports | synthetic | CC0-1.0 (licence §C) | our CC-BY renders only |
| studio synthetic (SDG, sensors, physics, DES, PSDs, creep, plumes, deposits, rollouts, question sets) | synthetic | CC-BY-4.0 (ours) | yes |

## 8. Risks and assumptions

- The reference machine is one RTX 5000 Ada Laptop GPU (16 GB). GPU work is gated by the capability probe.
  Proprietary NVIDIA runtimes may fail on it; every such tool degrades to "not run" or to "evaluated, not adopted"
  without blocking a core case.
- No headline KPI depends on an optional frontier piece (Cosmos, Isaac Lab MPM fine-tuning).
- Constants not verified against their primary page are flagged UNVERIFIED until pinned.

## 9. Feature specifications (children)

| Spec | Scope | Plan source |
|---|---|---|
| 001-contracts | manifest, recipe, tools, sources, capabilities schemas; generated types; drift check | §8, §11 |
| 002-runner | recipes, DAG, CAS cache, locks, hold, guards, telemetry, retries, resume, gc, profiles, fake GPU | §9 |
| 003-console | loopback FastAPI, jobs, SSE, `/health` CORS and loopback rules for the opt-in connect | §12 |
| 004-scene-pipeline | st10–st45: terrain, pit design, assets, compose, validate (open lane) | §9 |
| 005-physics | st50: Warp DEM, Newton MPM, shallow water, dust particles; physics benchmarks | §6 M7 M15 M16, §17 |
| 006-media-telemetry | st56 NVENC encode + VMAF; stage-side NVTX ranges, throughput and profile outputs (NVML sampling and publish: 002) | §9, §11 |
| 007-haulage-dispatch | M1–M6: DES twin with exact-trace parity, LP, PPO / attention env, energy routing | §6, §7 |
| 008-data-pipeline | s00–s20: registry, download, ingestion, synthesize, preprocess, features | §8, §9 |
| 009-perception | M10: SDG, detector training, DR ablation, corruption robustness | §6, §7 |
| 010-slope | M13–M14: LEM, Hoek–Brown, PoF, inverse velocity, forecasters, S4b slope-radar series | §6, §7 |
| 011-surrogates | M8 GNS, M9 DEM calibration, M15 FNO | §6, §7 |
| 012-fragmentation | M11–M12: synthetic muck piles, U-Net, watershed + Swebrec, TSTR/TRTR | §6, §7, §8 |
| 013-sensors | M23: ovrtx lane S1–S4a, dust model, point-count guard | §6, §9 |
| 014-robot-learning | M21: Isaac Lab IL-1/IL-2, TS twins, sim-to-sim gap | §6, §7 |
| 015-vlm | M22: Cosmos Reason 2 tasks A/B/C, Q8_0 vs BF16, controls | §6, §7 |
| 016-export-acceleration | s60/s62/s64: ONNX + parity, TensorRT engines + per-engine parity, budgets | §7, §9 |
| 017-planning-survey | M17–M19: mine-to-mill, min-cut + MILP, splat survey + volumes | §6 |
| 018-web-cases | Explore, cases, engines (TS/WGSL/ORT-web/Rapier/Pyodide), tiers, parity | §10, §11 |
| 019-web-studio | `/studio` tool map, tool pages, runs, GPU evidence, honesty rules, opt-in connect control | §11 |
| 020-web-knowledge | theory, methods, results, knowledge (generated from `minephys`) | §11, §13 |

The `minephys` models are specified in the `minephys` repository's own `specs/`.

## 10. Clarifications log
- (none)

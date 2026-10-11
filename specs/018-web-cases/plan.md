# Plan 018 — Web cases: Explore, case workbenches, in-browser engines, compute tiers and parity
Spec: ./spec.md

## Summary
Three route modules (`/`, `/cases`, `/cases/:id`) render from the case registry (DC-018-01) and the web manifest
(FR-018-01…20). One `SimClock` per page drives scene, charts, shards and video (FR-018-21…28, FR-018-68). A capability
probe picks T1/T2/T0 and a fallback chain moves failing engines down a tier (FR-018-29…32). One engine host runs every
engine — this spec's own and those of specs 007, 013 and 014 — in a module worker behind a schema-validated protocol,
loads heavy runtimes lazily and same-origin, and rejects hostile input with typed errors (FR-018-33…46). Each engine is
held to its system-class parity through committed fixtures; all verdicts meet in one parity report that the app reads at
run time (FR-018-47…63, FR-018-67); a CI suite measures the lane gate on T2 and fails on a mislabel (FR-018-64…66).

## Technical context
Runtime: Node 24 (`web/.nvmrc`), pnpm 11, React 19.3, React Router 8.4 framework mode (`ssr: false`, prerendered
routes), Vite 8.3, Vitest 5, Playwright 1.63 with axe. Planned web dependencies, resolved and locked in
`web/pnpm-lock.yaml` by the first task that needs them (never hand-pinned): three 0.186, @react-three/fiber 9.8,
@react-three/drei 10.7, 3d-tiles-renderer 0.5, @sparkjsdev/spark 2.3, onnxruntime-web 1.30,
@dimforge/rapier3d-simd-compat 0.21, pyodide 314.0, comlink 4.4, hyparquet, fast-check (property tests), Stryker
(mutation). Python 3.14 for fixture generation in `pipeline/` (locked: `onnxruntime` 1.30, `minephys` through the root
project, numpy); `networkx` is added to the pipeline lock and proven to install before T-018-005; Warp kernel references
run in `studio/` on the CPU device; WGSL observables come from the spec 005 goldens (DC-005-06). Target: GitHub Pages
(static, no COOP/COEP); CI on a hosted Linux runner with Chromium, Firefox and WebKit; the `webgpu` Playwright project on
a machine with a WebGPU adapter.

## Constitution check
| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | Pass | Live numbers come only from engines whose parity with the real reference engines is confirmed in the parity report; fallbacks are baked from real runs; missing results say "Not yet run" (FR-018-05, FR-018-15, FR-018-63) |
| Spec before code | Pass | Every behaviour has an ID in spec.md; hosted engines keep the IDs of specs 007, 013 and 014 |
| Acceptance-test-first | Pass | Every task in tasks.md is a `[red]`/`[green]` pair with its own locked test files |
| Independent oracles | Pass | Oracle per requirement below: reference implementations (`minephys`, numpy `PCG64`, networkx maximum flow, ONNX Runtime CPU, Rapier in Node, Warp CPU kernels, the spec 005 goldens, the spec 012 and 017 baselines), analytical solutions (Ritter dam break, Stokes settling, TTC closed form), hand calculations; never the code under test |
| Determinism & explicit tolerances | Pass | Seeds and fixtures pinned by SHA-256; tolerances per class with justification in spec §7.2 |
| Neutral contracts | Pass | DC-018-01…06 are JSON Schema 2020-12 under `contracts/`; TS validators and types are generated |
| Static delivery | Pass | Every engine has a T0 baked fallback (spec §7.1); browser outputs have parity tests (FR-018-48…59) |
| Honesty | Pass | The badge follows what is shown (FR-018-14); parity-unconfirmed engines run in T0 (FR-018-63); synthetic labels (FR-018-17) |
| Licence hygiene | Pass | Runtimes (MIT, Apache-2.0, MPL-2.0) are self-hosted unmodified; terrain is public domain; no NVIDIA binary or asset reaches the web |
| Simplicity | Pass | One clock, one engine host, one loader, one parity report; engines of other specs are hosted, not re-specified |

## Design
Data flow: [compute-tiers.svg](../../docs/assets/diagrams/compute-tiers.svg) (probe → tier → engine family → fallback)
and [web-routes.svg](../../docs/assets/diagrams/web-routes.svg) (routes and lanes).

| Component (planned path) | Responsibility | Requirements |
|---|---|---|
| `web/src/routes/explore.tsx`, `web/src/scene/` | Pit from LOD-0 tiles, rail, layers, KPIs, renderer choice, no-3D fallback | FR-018-01…08, NFR-018-01 |
| `web/src/routes/cases.tsx` | Catalogue and the two matrices | FR-018-09 |
| `web/src/routes/case.tsx` (prerender list generated from the registry) | Five sub-tabs, `?tab=`, 404 for unknown ids, cards, reproduce block | FR-018-11…20 |
| `studio/cases.yaml`, `contracts/cases.schema.json`, `tools/check_cases.py` | Case registry and its cross-checks | DC-018-01, FR-018-10 |
| `web/src/sim/clock.ts` | `SimClock` store (t, r, playing), fake time source for tests | FR-018-21…24, FR-018-68, P-018-01…03 |
| `web/src/media/` (`pickVideoSource.ts`, `VideoCard.tsx`, `videoSync.ts`) | Codec choice, `preload="none"`, poster, drift control | FR-018-25…28 |
| `web/src/engines/tier/` (`probe.ts`, `fake-gpu.ts`, `fallback.ts`, `TierBadge.tsx`) | T1/T2/T0 selection, `?tier=`, fallback chain | FR-018-06, FR-018-29…32 |
| `web/src/engines/host/` (`protocol.ts`, generated validators, `pool.ts`, `runtimeLoader.ts`, adapters for the engines of specs 007, 013, 014) | Worker protocol, typed errors, caps, timeouts, lazy same-origin runtimes, progress and Abort | FR-018-33…42, FR-018-44, FR-018-46, FR-018-48 |
| `web/src/assets/` (`loader.ts`, `shard.ts`) | Manifest lookup, SHA-256 via `crypto.subtle`, path rules, shard decoding | FR-018-43, FR-018-45, P-018-68…70 |
| `web/src/engines/random/` (`pcg64.ts`, `seedSequence.ts`) | numpy-compatible PCG64 for the Monte Carlo of spec 010 | FR-018-49, P-018-04, P-018-05, P-018-74, P-018-75 |
| `web/src/engines/analytical/{geotech,blasting,environment,comminution}/` | Ports of `minephys` (incl. slope-radar line of sight, inverse velocity, Monte-Carlo PoF) | FR-018-51, FR-018-52, P-018-28…45, P-018-76 |
| `web/src/engines/{mincut,volume,watershed}/` | Min-cut, survey volume, watershed | FR-018-51, FR-018-53, FR-018-59, P-018-46…54 |
| `web/src/engines/traffic/` (`world.ts`, `agents.ts`, `ttc.ts`) | Rapier world, rule-based agents, TTC and near-misses | FR-018-54, FR-018-55, P-018-19…21 |
| `web/src/engines/wgsl/{granular,swe,dust}/` | WGSL kernels and observables | FR-018-56, P-018-59…67 |
| `web/src/engines/ml/` (`ort.ts`, `detector.ts`) | ORT-web sessions per tier, detector feed and display threshold | FR-018-57, FR-018-58, P-018-27 |
| `web/src/engines/pyodide/` | "Run in Python" loader and comparison table | FR-018-61, FR-018-62, NFR-018-06 |
| `web/src/engines/registry.ts` | Engine table and parity-report gate | FR-018-47, FR-018-63 |
| `web/src/lane/derive.ts`, `web/e2e/lane-gate/`, `web/scripts/check-lanes.mjs` | Gate function, T2 measurements, CI mislabel check | FR-018-64…66, P-018-71…73 |
| `tools/make_parity_fixtures.py` (pipeline environment) | Runs this spec's references and writes DC-018-04 fixtures with SHA-256 | DC-018-04, FR-018-67 |
| `web/e2e/parity/` | In-browser parity runner; merges the verdicts of specs 007, 013, 014 and of this spec into DC-018-05; refuses empty or invalid fixture sets | DC-018-05, FR-018-48, FR-018-67, SC-018-01 |

## Test strategy
Levels: unit and property = Vitest (+ fast-check) under `web/src/**`; parity = Vitest (TS engines, Node) and
Playwright (in-browser, Chromium/Firefox/WebKit) over DC-018-04 fixtures; E2E = Playwright on the production build
served like Pages; contract = pytest under `tests/contract/`; gpu = Playwright project `webgpu`, tag `@gpu`.

| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-018-01, FR-018-07 | E2E | hand: expected source id, licence and badge from `data/sources.yaml`; renderer type exposed by the scene test hook | Playwright |
| FR-018-02, FR-018-09 | unit + E2E | hand: the catalogue of `docs/cases/README.md` and the matrices of `docs/cases/coverage-matrix.md` and `tool-matrix.md` | Vitest, Playwright |
| FR-018-03, FR-018-04, FR-018-05, FR-018-06 | E2E | hand: expected KPIs, layers and badge texts from a fixture manifest | Playwright |
| FR-018-08 | E2E (hostile) | hand: expected poster and text with WebGL 2 and WebGPU disabled by launch flags | Playwright |
| FR-018-10 | contract | hand: one mutated registry per failure class | pytest |
| FR-018-11, FR-018-12, FR-018-13 | E2E | hand: 12 ids → 200; WAI-ARIA tab keys; other query parameters kept; unknown and lower-case ids → 404 | Playwright |
| FR-018-14, FR-018-15, FR-018-17, FR-018-18 | unit + E2E | hand: fixture manifest with known artefacts, lanes and licence classes | Vitest, Playwright |
| FR-018-16 | unit + E2E | hand: intervals on both sides of 0 with the verdicts of FR-020-22 | Vitest, Playwright |
| FR-018-19, FR-018-20 | unit + E2E | hand: expected command strings from the recipe path; absent recipe → "Not yet run — recipe planned" | Vitest, Playwright |
| FR-018-21…24 | unit + E2E | analytical: clock time from a fake time source; frame periods from the fixture video fps | Vitest, Playwright |
| FR-018-25, FR-018-27 | unit + E2E | hand: request log shows no video bytes before play; absent or rejecting `MediaCapabilities`; corrupted file → message | Vitest, Playwright |
| FR-018-26 | unit | hand: truth table over (AV1 supported, power-efficient, H.264 supported) | Vitest |
| FR-018-28 | E2E | hand: `reducedMotion: 'reduce'` emulation → no transition frames | Playwright |
| FR-018-29, FR-018-30, FR-018-31 | unit + E2E | hand: fake GPU scripts (no `navigator.gpu`, null adapter, device rejection, device lost, hang > 2 s) → expected tier and badge | Vitest, Playwright |
| FR-018-32 | E2E | hand: forced T2 → REPLAY badge and note on A3, C2, C3 | Playwright |
| FR-018-33, FR-018-34, FR-018-35 | E2E | hand: request log by URL pattern and origin; `crossOriginIsolated` value | Playwright |
| FR-018-36 | E2E | analytical bound: long-task entries > 100 ms during an engine run = 0 | Playwright |
| FR-018-37 | E2E | hand: throttled route, Abort pressed → request cancelled within 500 ms | Playwright |
| FR-018-38, FR-018-39, FR-018-40 | unit (hostile) | hand: one request per error class, generated from DC-018-02 (NaN, ±Inf, out of range, wrong shape, empty, unknown enum, unknown id, wrong version, over cap) | Vitest + fast-check |
| FR-018-41, FR-018-42 | E2E (hostile) | hand: hostile values (empty, `abc`, `NaN`, `1e309`, `-5`, `<script>`, 20,000 characters, `../`) | Playwright |
| FR-018-43, FR-018-45 | unit + E2E (hostile) | hand: SHA-256 of a mutated byte; path list (`/x`, `https://x`, `../x`, `a\\b`, `%2e%2e/`); shards with bad header, length and code range | Vitest, Playwright |
| FR-018-44, FR-018-46 | E2E (hostile) | hand: aborted runtime routes; a stub engine that never returns | Playwright |
| FR-018-47 | unit | hand: the table of spec §7.1 | Vitest |
| FR-018-48 | unit + parity (report) | reference: the verdicts produced by the parity suites of specs 007, 013 and 014 on their goldens; hand: a hosted engine with a failing verdict is shown in T0 | Vitest, Playwright |
| FR-018-49 | lint + unit | hand: a planted forbidden `Math.*` call fails the rule; the source tree passes | Biome rule + Vitest |
| FR-018-51 | parity | reference implementation: `minephys` outputs (ports) and the numpy DEM differencing of spec 017 (survey volume) in DC-018-04 | Vitest, Playwright |
| FR-018-52 | parity | reference: `minephys` Monte Carlo on the same samples; analytical binomial standard error for the own-generator bound | Vitest |
| FR-018-53 | parity | reference implementations: `minephys.planning` min-cut and networkx maximum flow (minimal source side) | Vitest |
| FR-018-54 | parity | reference implementation: Rapier 0.21 run in Node with the same initial state (golden hash) | Playwright (3 browsers) |
| FR-018-55 | unit | published worked example: docs M20, truck 10 m/s east, light vehicle 5 m/s west, 100 m apart, R = 4 m → TTC = 6.4 s; hand cases for head-on, crossing, diverging, overlapping | Vitest |
| FR-018-56 | parity (gpu) | reference implementation: Warp kernels on the CPU device (per kernel); spec 005 golden observables (DC-005-06) | Playwright `webgpu` |
| FR-018-57 | parity | reference implementation: ONNX Runtime CPU 1.30 outputs in DC-018-04 | Playwright (WASM in CI; WebGPU in `webgpu`) |
| FR-018-58 | parity | reference implementation: ONNX Runtime CPU on the spec 009 export; the spec 009 preprocessing table | Playwright (WASM in CI; WebGPU in `webgpu`) |
| FR-018-59 | parity | reference implementation: the Python watershed baseline of spec 012 | Vitest |
| FR-018-61, FR-018-62 | E2E | reference implementation: `minephys` in Pyodide vs the FR-018-51 tolerance; hand: corrupted wheel digest | Playwright |
| FR-018-63 | unit + E2E | hand: parity report with one failing and one missing engine | Vitest, Playwright |
| FR-018-64 | E2E (CI) | hand: measurement file validates against DC-018-06 and lists every engine of §7.1 | Playwright |
| FR-018-65, P-018-71, P-018-72, P-018-73 | unit + property | hand: 16 boundary cases; reference implementation: spec 001's lane gate on its conformance corpus (DC-001-08); analytical: monotonicity and disjunction | Vitest + fast-check |
| FR-018-66 | contract | hand: manifest labelled `live` with failing measurements; a live engine without a measurement | Vitest (script) |
| FR-018-67 | contract (hostile) | hand: a fixture with one changed byte, an empty fixture set, malformed report and measurement files | pytest, Vitest |
| FR-018-68 | unit (hostile) | hand: seek(NaN), seek(−1), seek(D + 1), rate(−2), rate(Infinity) | Vitest |
| P-018-01, P-018-02, P-018-03 | property | analytical (relations on a fake time source) | Vitest + fast-check |
| P-018-04, P-018-05, P-018-74, P-018-75 | property | reference implementation: numpy `PCG64`, `SeedSequence`, `PCG64.advance` and `Generator.random` words in DC-018-04 | Vitest, Playwright (3 browsers) |
| P-018-19, P-018-20, P-018-21 | metamorphic | analytical (TTC closed form, docs M20) | Vitest + fast-check |
| P-018-27 | property | analytical (thresholding is a filter; set semantics) | Vitest + fast-check |
| P-018-28, P-018-29, P-018-30 | metamorphic | analytical (strength in the numerator; translation and similarity of limit equilibrium) | Vitest + fast-check |
| P-018-31, P-018-32, P-018-76 | metamorphic | analytical (inverse-velocity line under time translation, velocity scaling and time-unit change) | Vitest + fast-check |
| P-018-33 | unit | hand calculation of 20 Voight α = 2 series | Vitest |
| P-018-34, P-018-35, P-018-36 | metamorphic | analytical (projection on the line of sight) | Vitest + fast-check |
| P-018-37, P-018-38, P-018-39 | metamorphic | analytical (plume linear in Q, symmetric in y; AP-42 power law) | Vitest + fast-check |
| P-018-40, P-018-41, P-018-42 | metamorphic | analytical (Kuz-Ram monotonicity; Swebrec anchors; scaled distance R/√W) | Vitest + fast-check |
| P-018-43, P-018-44, P-018-45 | metamorphic | analytical (Bond's law; mass balance) | Vitest + fast-check |
| P-018-46, P-018-47, P-018-48 | metamorphic | analytical (watershed depends only on elevation order; flip; pixel size) | Vitest + fast-check |
| P-018-49, P-018-50, P-018-51 | metamorphic | analytical (closure scaling, relabelling, nested pits of the maximum-closure problem) | Vitest + fast-check |
| P-018-52, P-018-53, P-018-54 | metamorphic | hand calculation (prism volume Δz × area); analytical (additivity, antisymmetry, linearity) | Vitest + fast-check |
| P-018-59, P-018-60, P-018-61 | metamorphic (gpu) | analytical (Newton's third law, translation invariance, conservation) | Playwright `webgpu` |
| P-018-62, P-018-63, P-018-64 | metamorphic (gpu) | analytical: lake at rest, mirror symmetry, Ritter (1892) dry-bed front speed 2√(g h₀) | Playwright `webgpu` |
| P-018-65, P-018-66, P-018-67 | metamorphic (gpu) | analytical: Stokes terminal velocity; Galilean shift; conservation | Playwright `webgpu` |
| P-018-68, P-018-69, P-018-70 | property | analytical (affine 16-bit quantisation, `int16` or `uint16` as the header declares) | Vitest + fast-check |
| NFR-018-01, NFR-018-02 | E2E / build | hand: byte sums against 2,000,000 B and 200,000 B gzip | Playwright, postbuild |
| NFR-018-03 | E2E (CI) + gpu | hand: gate targets from plan §10 | lane-gate suite |
| NFR-018-04 | E2E | WCAG rules as encoded by axe-core; Lighthouse accessibility score | Playwright + axe, LHCI |
| NFR-018-05 | build | thresholds.yaml `coverage`, `mutation` | Vitest coverage, Stryker |
| NFR-018-06 | E2E | hand: 20 s warn, 60 s fail | Playwright |
| SC-018-01 | gate | parity report of the release commit | DC-018-05 |
| SC-018-02 | gate | E2E and parity tasks of A1 and C1 green on the preview | CI |

## Risks and complexity tracking
| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| A port of numpy's PCG64 + SeedSequence | Spec 010's Monte Carlo draws through numpy `PCG64`; sharing the raw stream makes the failing-sample count comparable | A different generator would make every browser sample differ from the reference |
| Generated validators per engine (DC-018-02) | One schema validates both the browser inputs and the fixture generator inputs | Hand-written guards would drift from the Python side |
| WGSL parity only in the `webgpu` project | Hosted CI has no WebGPU adapter | Software adapters are not guaranteed on the runner; results there are reported "not run", never "passed" |
| A parity report read at run time (FR-018-63) | An engine whose parity failed must not be shown LIVE on the deployed site | A CI failure alone would block unrelated deploys and still allow a stale LIVE label |
| Hosting engines specified elsewhere (FR-018-48) | Specs 007, 013 and 014 own those engines' behaviour and parity | Re-specifying them here produced conflicting tolerances, so the rows were withdrawn |
| Risk: R3F caps React below 19.4 | three/R3F are needed for the pit | Upgrades of React wait for R3F; noted in the lock review |
| Risk: Pyodide download (≈ 17 MB) is slow on weak links | Verifying with the real Python reference is the point of the button | Loaded only on click, with progress and Abort (FR-018-37) |

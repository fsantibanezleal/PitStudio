# Spec 018 — Web cases: Explore, case workbenches, in-browser engines, compute tiers and parity
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent
The static site must let a visitor see the real pit, pick any of the 12 cases and run it in the browser with numbers
that can be trusted. This spec covers the Explore route `/` (3D pit from the Bingham LOD-0 tileset, case rail, layers,
shared timeline paused by default, KPIs, tier badge, provenance), the catalogue `/cases`, the 12 case workbenches
`/cases/:id` (Scene · Simulate (live) · Studio replay · Charts · Context, plus "Reproduce this"), the in-browser engines
(TypeScript workers, Rapier WASM, WGSL compute, ONNX Runtime Web 1.30, the Pyodide button that loads `minephys`), the
compute tiers T1 WebGPU / T2 WebAssembly / T0 baked with fallback, lazy runtime loading, video delivery synced to one
`SimClock`, parity of every browser engine with its Python reference by system class, the web half of the measured
lane gate, and the hostile-input suite. Mining engineers, students and reviewers benefit: every live number is computed
by an engine whose parity is proven, and every fallback says what it shows. Out of scope: the Python reference engines
and their goldens' scientific content (specs 005, 007, 010, 012, 014, 017 and the `minephys` repository), the browser
engines that other specs define in full — the DES twin, learned dispatchers, haulage port, LP and router (007), the dust
slider (013) and the robot twins (014), which this spec only hosts — the tool map and
studio pages (019), theory/methods/results/knowledge and the shared chart component (020), the manifest schema (001),
the export stage and its budgets (016), the console (003) and the opt-in connect control (019).

## 2. User stories
### US-018-1 (P1) Explore the real pit
As a mining engineer, I want the start page to show the real Bingham Canyon pit with all 12 cases, their KPIs and the
compute tier, so that I can orient myself and choose a case. Independent test: open `/` on a fresh profile, check the
pit renders from the LOD-0 tileset within the first-view budget, 12 cases in 5 groups, a tier badge and a paused clock.

### US-018-2 (P1) Run a case live
As a mining engineer, I want to change a case's inputs (fleet size, dispatcher, slope section, blast design, …) and
see its KPIs update in my browser, so that I can reason about trade-offs. Independent test: on `/cases/A1/?tab=simulate`
change the fleet size and observe new t/h, queue time and match factor computed by the DES worker with the LIVE badge.

### US-018-3 (P1) Trust the browser's numbers
As a reviewer, I want every live engine to be checked against its Python reference with a tolerance fixed by its
system class, and to re-run an analytical model in real Python with one button, so that I can trust or reject what the
browser shows. Independent test: run the parity suite on the fixtures; press "Run in Python" on C1 and compare.

### US-018-4 (P1) Degrade honestly
As a visitor on any browser, I want the site to work without WebGPU, when a runtime fails or when I am offline after
load, and to tell me which tier is active, so that I am never shown a computation that did not happen. Independent
test: force `?tier=t2`, inject a fake GPU that loses its device, block the ORT-web files, and check badge and notices.

### US-018-5 (P2) Watch studio replays on one timeline
As a data/AI practitioner, I want the studio's videos, particle replays and charts to follow one shared timeline that
I control, so that I can compare them frame by frame. Independent test: scrub the clock on `/cases/C2/` and check the
video time, the 3D replay frame and the chart cursor agree within one frame.

### US-018-6 (P2) Reproduce a case
As a developer, I want each case page to show the exact runner commands, recipe and run that produced its artefacts,
so that I can rebuild them. Independent test: the "Reproduce this" block of `/cases/A1/` shows the recipe path and the
three commands with the published run id, and no machine path.

### US-018-7 (P2) Browse the catalogue and the matrices
As a student, I want a catalogue of the cases with the methods × cases and tools × cases matrices, so that I can see
how the ladder and the studio map onto real questions. Independent test: `/cases` shows 12 rows, a 23 × 12 and a
17 × 12 matrix generated from the case registry.

| Story | Priority | Title |
|---|---|---|
| US-018-1 | P1 | Explore the real pit |
| US-018-2 | P1 | Run a case live |
| US-018-3 | P1 | Trust the browser's numbers |
| US-018-4 | P1 | Degrade honestly |
| US-018-5 | P2 | Watch studio replays on one timeline |
| US-018-6 | P2 | Reproduce a case |
| US-018-7 | P2 | Browse the catalogue and the matrices |

## 3. Functional requirements (EARS)
Sizes use KB = 10³ bytes and MB = 10⁶ bytes, as specs 001 and 006 do (the stricter reading of the lane gate); the git
per-file limit stays 10 MiB as `tools/check_repo.py` implements. "Engine" means one entry of the engine table in §7.1;
"reference" means the Python implementation named there. Engines marked there as specified by specs 007, 013 or 014
are hosted by this spec (protocol, tiers, lazy loading, fallback, parity report, lane gate); their behaviour and parity
are defined in those specs and are not restated here.

### 3.1 Explore (`/`)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-018-01 | Ubiquitous | The Explore route shall render the Bingham Canyon pit from the LOD-0 terrain tileset (3D Tiles 1.1 with glTF tiles) listed in the web manifest, with a provenance chip naming the source `usgs-3dep-bingham`, its licence "public domain (US Government work)" and the STATIC badge. | E2E |
| FR-018-02 | Ubiquitous | The Explore route shall show a case rail with exactly 12 entries in 5 labelled groups, in this order: A (A1, A2, A3), B (B1, B2), C (C1, C2, C3), D (D1, D2), E (E1, E2), each with its title from the case registry in the active language and a link to `/cases/<id>/`. | unit + E2E |
| FR-018-03 | Event | When the visitor selects a case in the rail, or loads `/?case=<id>` with a known id, the Explore route shall highlight that case, show its headline KPIs and a link to its page within 200 ms, without starting the clock. | E2E |
| FR-018-04 | Event | When the visitor toggles a layer (terrain epoch 2018 / 2023, roads, pit shells, fleet, fields, sensors), the scene shall show or hide that layer within 100 ms, the toggle shall expose its state through `aria-pressed`, and a layer with no published artefact shall be disabled with the text "Not yet run". | E2E |
| FR-018-05 | Ubiquitous | The Explore route shall show each headline KPI of the selected case with value, unit, lane badge and provenance chip from the web manifest, and "Not yet run" in place of the value for every KPI without a published artefact. | unit + E2E |
| FR-018-06 | Ubiquitous | The Explore route and every `/cases/:id` page shall show the active compute tier as a text badge "T1 · WebGPU", "T2 · WebAssembly" or "T0 · baked" (Spanish labels in ES), visible without scrolling at a 1280 × 720 viewport and exposed with an accessible name. | E2E |
| FR-018-07 | Ubiquitous | The 3D views shall use three.js WebGPURenderer with its automatic WebGL 2 fallback, shall use the WebGL 2 backend when the URL carries `?renderer=webgl`, shall render splat scenes with WebGLRenderer + Spark in a canvas of their own, and shall never attach two renderers to one canvas. | E2E |
| FR-018-08 | Unwanted | If neither WebGPU nor WebGL 2 is available, then the Explore route and the Scene tabs shall show the scene's WebP poster, the text "3D view needs WebGL 2 or WebGPU" and the KPI table, and shall keep every other control usable. | E2E (hostile) |

### 3.2 Catalogue (`/cases`)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-018-09 | Ubiquitous | `/cases` shall render, from the case registry (DC-018-01), the catalogue (12 rows: id, title, category, KPIs with units, real data, synthetic data), the coverage matrix (23 methods M1–M23 × 12 cases) and the tool matrix (17 studio tools × 12 cases), each as an HTML table with `th` header cells carrying `scope`. | unit + E2E |
| FR-018-10 | Unwanted | If the case registry leaves a method M1–M23 or one of the 17 studio tools out of every case, references an unknown method, tool, data source or engine id, repeats a case id, or has a case outside categories A–E, then the build shall fail and name the offending id. | contract |

### 3.3 Case pages (`/cases/:id`)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-018-11 | Ubiquitous | For each of the 12 case ids, `/cases/<id>/` shall be a prerendered page answering HTTP 200 with the sub-tabs, in this order, Scene · Simulate (live) · Studio replay · Charts · Context, implemented as a WAI-ARIA tab list operable with the arrow keys, Home and End. | E2E |
| FR-018-12 | Event | When the visitor selects a sub-tab, the page shall show it and set the query parameter `tab=<scene\|simulate\|replay\|charts\|context>` (keeping the other parameters) without a navigation, so that loading that URL opens the same sub-tab. | E2E |
| FR-018-13 | Unwanted | If the case id is not one of the 12 canonical upper-case ids, then the site shall answer HTTP 404 with the app's not-found page and shall request no case asset. | E2E (hostile) |
| FR-018-14 | Ubiquitous | The Simulate (live) tab shall run each engine listed for the case in the registry on the active tier and update the case KPIs from the engine output after every accepted input change; an output computed in this browser shall carry the LIVE badge and an output taken from the T0 fallback shall carry the REPLAY badge. | E2E |
| FR-018-15 | Ubiquitous | The Studio replay tab shall list every web-manifest artefact whose `case` equals the page's id and whose lane is `replay`, as artefact cards (FR-018-18), and shall show "Not yet run" when there is none. | unit + E2E |
| FR-018-16 | Ubiquitous | The Charts tab shall show each KPI with its unit, its baseline, the paired 95 % confidence interval of the difference and the verdict produced by the decision-rule display (FR-020-22), shall show "single real event — no significance test" for the C1 real series, and every chart shall follow the interactive-chart rules FR-020-07 to FR-020-16. | unit + E2E |
| FR-018-17 | Ubiquitous | The Context tab shall show the case question, every data source with its registry id, SPDX licence and real or synthetic label, the validity range, and links to its theory, method and dataset-card pages, and shall label every data type without a real reference "calibrated synthetic — not validated against real data" (FR-000-09). | unit + E2E |
| FR-018-18 | Ubiquitous | Every artefact card on `/` and `/cases/:id` shall show the badge LIVE, REPLAY or STATIC, a producer chip linking to `/studio/tools/<producer.tool>/`, a run chip linking to `/studio/runs/<run_id>/`, the 7-hex commit, the licence class and, for REPLAY cards, "Precomputed on <GPU name> on <date>" (FR-000-06). | unit + E2E |
| FR-018-19 | Ubiquitous | Every case page shall end with a "Reproduce this" block showing the recipe path `studio/recipes/cases/<id in lower case>.yaml`, the commands `uv run studio plan <recipe> --profile laptop-rtx5000ada`, `uv run studio run <recipe> --profile laptop-rtx5000ada` and `uv run studio publish <run-id>` with the run id of the case's published artefacts, the requirement note derived from the recipe's stage resources (for example "needs an NVIDIA RTX GPU"), and a copy button; the block shall contain no absolute path, host name or user name. | unit + E2E |
| FR-018-20 | Unwanted | If the case's recipe file does not exist in the repository at build time, then the "Reproduce this" block shall state "Not yet run — recipe planned" and show no command. | unit |

### 3.4 Shared clock and media
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-018-21 | State | While the visitor has not pressed play, stepped or scrubbed, the page's single `SimClock` on `/` and on `/cases/:id` shall stay paused at t = 0 s, with no video playing and no replay advancing, for at least 10 s after load. | unit + E2E |
| FR-018-22 | Ubiquitous | The `SimClock` (state: time t in s, rate r, playing) shall drive the 3D scene, the charts' time cursor, the replay shards and every video of the page, and its play, pause, step (± 1/fps s, fps from the case registry, default 10) and scrub controls shall be operable by keyboard. | unit + E2E |
| FR-018-23 | Event | When the visitor scrubs or steps to time t, every subscribed view shall render its state at t within one animation frame and every video's `currentTime` shall be within one frame period (1/fps of that video) of t. | E2E |
| FR-018-24 | State | While the `SimClock` plays, each video shall stay within two frame periods of the clock, checked on each presented frame through `requestVideoFrameCallback` `mediaTime`, and shall be re-seeked to the clock when it drifts further. | E2E |
| FR-018-25 | Ubiquitous | Every video element shall be created with `preload="none"` and a WebP poster, and the page shall request no video bytes before the visitor presses play on it or on the clock. | E2E |
| FR-018-26 | Ubiquitous | The media card shall select the AV1 1080p file when `MediaCapabilities.decodingInfo` reports AV1 `supported` and `powerEfficient`, otherwise the H.264 720p file when H.264 is `supported`. | unit |
| FR-018-27 | Unwanted | If neither encoding is supported (an absent `MediaCapabilities` or a rejected or malformed `decodingInfo` answer counts as "not supported"), or the selected file fails to load or fails its SHA-256 check, then the card shall show the poster with "Video not available in this browser" (or "integrity check failed"), keep the REPLAY badge and leave the `SimClock` and the other views running. | unit + E2E (hostile) |
| FR-018-28 | State | While `prefers-reduced-motion: reduce` is set, the views shall not animate camera transitions or explainer steps, and the clock shall still advance only on user action. | E2E |

### 3.5 Compute tiers and runtimes
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-018-29 | Event | When a page loads, the capability probe shall select T1 if `navigator.gpu` exists, `requestAdapter()` returns an adapter and `requestDevice()` resolves within 2 s; otherwise T2 if `WebAssembly.instantiate` exists and a 1-function test module compiles; otherwise T0; the probe shall download no file and shall finish before any engine starts. | unit (fake GPU) + E2E |
| FR-018-30 | Optional | Where the URL carries `?tier=t2` or `?tier=t0`, the app shall use that tier when it is not higher than the probed tier, and shall ignore a request for a higher tier. | unit + E2E |
| FR-018-31 | Unwanted | If an engine fails to initialise on its tier, throws, exceeds its timeout, or its WebGPU device is lost, then the app shall move that engine to the next tier (T1 → T2 → T0) within 1 s, update the tier badge, show a non-modal notice naming the failed runtime, and keep the page interactive (FR-000-02). | unit (fake GPU) + E2E (hostile) |
| FR-018-32 | State | While the active tier is T2, the engines that need GPU compute (granular, shallow water, dust particles) shall show their baked replay with the REPLAY badge and the note "needs WebGPU to compute live" instead of computing. | E2E |
| FR-018-33 | Ubiquitous | The site shall request the ORT-web, Rapier and Pyodide runtime files (Pyodide with its numpy and PyYAML packages and the `minephys` wheel) only after a user action that needs them — opening a Simulate tab whose engines use them, or pressing "Run in Python" — and shall make zero requests for them before that action. | E2E |
| FR-018-34 | Ubiquitous | The site shall request every runtime, model and asset file from its own origin, and shall make zero requests to other origins (CDNs included) and zero requests to loopback addresses during a full session (FR-000-11). | E2E |
| FR-018-35 | Ubiquitous | Every engine shall run with `crossOriginIsolated === false` and without `SharedArrayBuffer`, using single-threaded WASM builds (ORT-web `env.wasm.numThreads = 1`). | E2E |
| FR-018-36 | Ubiquitous | The TypeScript engines shall run in module workers so that, during any engine run, the main thread records no long task above 100 ms attributable to the engine (`PerformanceObserver` type `longtask`). | E2E |
| FR-018-37 | Event | When a runtime or model is downloading, the page shall show progress as bytes received over the manifest size and an Abort control; Abort shall stop the download within 500 ms and return the view to its state before the action. | E2E |

### 3.6 Engine host interface and hostile inputs
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-018-38 | Ubiquitous | Every engine shall accept requests only through a typed message protocol — engine id, engine version and an input object in SI units validated against the engine's input schema (DC-018-02) — and shall answer with either a result validated against its output schema or a typed error with code `E_SCHEMA`, `E_RANGE`, `E_NONFINITE`, `E_SIZE`, `E_UNKNOWN_ENGINE`, `E_TIMEOUT` or `E_RUNTIME`. | unit |
| FR-018-39 | Unwanted | If a request contains NaN or ±Infinity, a value outside the engine's declared validity range, a wrong array shape or dtype, an empty required array, an unknown enum value, an unknown engine id or a version other than the loaded one, then the engine shall return the matching typed error within 50 ms without computing and without an uncaught error on any thread. | unit (hostile) |
| FR-018-40 | Unwanted | If a request exceeds the engine's size cap (§7.1), then the engine shall return `E_SIZE` naming the cap, and the UI control that produced it shall already have clamped the value to the cap with a visible note. | unit + E2E (hostile) |
| FR-018-41 | Unwanted | If a numeric control receives an empty, non-numeric, NaN, infinite or out-of-range value, then it shall keep its last valid value, show an inline message with the allowed range and unit, and send no engine request. | E2E (hostile) |
| FR-018-42 | Unwanted | If a URL parameter (`case`, `tab`, `t`, `tier`, `renderer`, `lang`) is unknown, malformed, non-finite, negative or longer than 2,000 characters, then the page shall ignore it (clamping `t` to [0, duration]), render normally, raise no uncaught error and request no resource derived from its value. | E2E (hostile) |
| FR-018-43 | Unwanted | If an artefact's served bytes do not match the SHA-256 of its manifest entry, or its manifest path is absolute, has a URL scheme, contains `..`, a backslash or a percent-encoded separator, or resolves outside `assets/`, then the loader shall not use it and the card shall show "integrity check failed" in place of the artefact. | unit + E2E (hostile) |
| FR-018-44 | Unwanted | If a runtime or model file cannot be fetched (offline, HTTP error, blocked) or fails to compile or instantiate, then the engine shall fall back to T0, show "<runtime> could not load — showing precomputed results", and leave no unhandled promise rejection. | E2E (hostile) |
| FR-018-45 | Unwanted | If a replay shard's header does not validate against DC-018-03, its byte length differs from frames × items × channels × 2 declared in the header, or a quantised code falls outside the header's declared code range, then the reader shall reject the whole shard with `E_SCHEMA` and the view shall show the poster frame. | unit (hostile) |
| FR-018-46 | Unwanted | If an engine run exceeds its timeout (§7.1; default 10 s), then the host shall terminate the worker, return `E_TIMEOUT`, and apply FR-018-31. | unit + E2E (hostile) |

### 3.7 Engines and parity by system class
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-018-47 | Ubiquitous | The engine registry `web/src/engines/registry.ts` shall list exactly the engines of §7.1, each with its id, cases, runtime, parity class, Python reference, size cap, timeout and T0 fallback. | unit |
| FR-018-48 | Ubiquitous | The engines specified by spec 007 (`des`, `policies`, `haulage`, `lp`, `routing`), spec 013 (`dust-lidar`) and spec 014 (`il1-twin`, `il2-twin`) shall run only through this spec's engine host and tiers (FR-018-29…46), and the parity verdicts of their own suites (FR-007-10, FR-007-15, FR-007-20, FR-007-32, FR-007-39, P-013-15, FR-014-42) shall be written into the parity report (DC-018-05) so that FR-018-63 applies to them, in Chromium, Firefox and WebKit. | unit + parity (report) |
| FR-018-49 | Ubiquitous | The PCG64 and SeedSequence port (`web/src/engines/random/pcg64.ts`, `seedSequence.ts`) used by the Monte-Carlo engines of this spec shall use only integer operations (BigInt or 32-bit limbs with `Math.imul`) and the exact conversion (word >> 11) × 2⁻⁵³, and a lint rule shall fail the build on any other `Math.*` call in those files. | lint + unit |
| ~~FR-018-50~~ | — | Withdrawn before approval: DES native-mode parity is unnecessary because spec 007 shares one counter-based variate source between Python and TypeScript (FR-007-05, FR-007-06). | — |
| FR-018-51 | Ubiquitous | Every analytical TypeScript engine of this spec (the `minephys` ports geotech, blasting, environment (AP-42 and Gaussian plume) and comminution, the slope-radar line of sight, and the survey volume engine) shall equal its reference of §7.1 on the parity fixture (≥ 200 input vectors per function, both ends of each validity range included) within $\lvert y_{ts} - y_{py}\rvert \le 10^{-12} s_y + \text{rtol}\,\lvert y_{py}\rvert$, with rtol = 10⁻⁹ for closed forms and rtol = max(10⁻⁹, 10 × the reference solver tolerance) for iterative functions, $s_y$ being the output's unit scale in DC-018-02. | parity |
| FR-018-52 | Ubiquitous | The Monte-Carlo probability of failure shall return exactly the reference's failing-sample count when fed the fixture's sample matrix, and with its own generator and N samples shall satisfy $\lvert p_{ts} - p_{py}\rvert \le 3\sqrt{p_{py}(1-p_{py})/N} + 1/N$. | parity |
| FR-018-53 | Ubiquitous | On every golden instance, the min-cut engine shall return the same pit block set as the reference (the source side of the minimal minimum cut) with objective within rtol 10⁻¹⁰. | parity |
| FR-018-54 | Ubiquitous | For every traffic golden (≤ 40 vehicles, ≥ 600 steps at 60 Hz), the browser Rapier run shall produce a SHA-256 snapshot hash after the last step equal to the golden produced in Node with the same Rapier version and initial state. | parity |
| FR-018-55 | Ubiquitous | The traffic engine shall compute, for every vehicle pair and step, the constant-velocity time to collision as the smallest positive root of $\lVert \mathbf p + \mathbf w \tau\rVert = R$ (∞ when not closing or the discriminant is negative, 0 when already overlapping), the minimum TTC per encounter, and near-misses per 1,000 h of exposure with threshold τ* = 3 s. | unit |
| FR-018-56 | Optional | Where a WebGPU adapter is available, on each fixed configuration of the WGSL granular, shallow-water and dust kernels, the per-kernel outputs (forces and one integration step), made non-dimensional by the configuration scale, shall equal Warp's CPU reference within max abs 10⁻³ (`web.webgpu_fp32_max_abs`); over full runs the observables shall agree with the golden observables of spec 005 (DC-005-06) within repose ±1.5°, run-out ±5 %, discharge ±5 % and mass drift < 0.5 %. | parity (gpu) |
| FR-018-57 | Ubiquitous | Every live ONNX model shall match ONNX Runtime CPU (Python) on its golden set (≥ 200 inputs) within max abs 1e-4 on the WASM fp32 path (`web.wasm_fp32_max_abs`), 1e-3 on WebGPU fp32 (`web.webgpu_fp32_max_abs`), 1e-2 on fp16 paths (`web.fp16_max_abs`), with top-1 agreement ≥ 0.995 for classifiers and detectors (`web.top1_agreement_min`); dispatch policies follow FR-007-32. | parity (WASM in CI; WebGPU gpu) |
| FR-018-58 | Ubiquitous | The detector engine shall feed the exported graph (post-processor and top-300 selection inside, no non-maximum suppression; FR-009-35) with the shipped 640 × 640 frame as `images` — a u8 → float32 lookup equal bit for bit to the spec 009 preprocessing — and its `orig_target_sizes`, and shall show the detections above the score threshold; on every golden image, `boxes` shall match ONNX Runtime CPU within max abs 0.5 px on the WASM path and 1 px on the WebGPU path, and `labels` shall be in top-1 agreement ≥ 0.995. | parity (WASM in CI; WebGPU gpu) |
| FR-018-59 | Ubiquitous | Given the fixture's elevation image and marker image, the TypeScript watershed shall return a label map identical to the Python watershed baseline of spec 012-fragmentation, and its x50 and x80 shall equal the reference within rtol 10⁻⁹. | parity |
| ~~FR-018-60~~ | — | Withdrawn before approval: the IL-1 and IL-2 twins and their parity are specified by spec 014 (FR-014-40…42) and hosted through FR-018-48. | — |
| FR-018-61 | Event | When the visitor presses "Run in Python" on an analytical engine, the page shall load Pyodide, numpy, PyYAML and the `minephys` wheel (each verified by SHA-256 against the manifest or `pyodide-lock.json`), evaluate the same inputs with `minephys`, and show both results side by side with absolute and relative differences and a parity verdict using the FR-018-51 tolerance. | E2E |
| FR-018-62 | Unwanted | If the `minephys` wheel or a Pyodide package fails its SHA-256 check, or Pyodide has not finished loading within 60 s, then the page shall show "Python reference could not load", keep the TypeScript result and leave no unhandled promise rejection. | E2E (hostile) |
| FR-018-63 | Unwanted | If the parity report of the deployed commit (DC-018-05) marks an engine as failing or does not list it, then that engine shall run in T0 and show "parity not confirmed — showing precomputed results" instead of the LIVE badge. | unit + E2E |

### 3.8 Lane gate (web half)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-018-64 | Ubiquitous | The lane-gate measurement suite shall measure, on forced T2 in headless Chromium, for every engine and live model: the 95th-percentile interaction time over 50 interactions (ms), the median full-run time over 5 runs (s), and the byte sizes of its largest engine-specific asset and of its trace, and shall write them with the runner configuration to the lane-measurement file (DC-018-06). | E2E (CI) |
| FR-018-65 | Ubiquitous | `deriveLane(m)` shall return `live` if and only if m is web-drivable, asset bytes ≤ 25,000,000, (p95 interaction ≤ 16 ms or T2 run ≤ 1,000 ms) and trace bytes ≤ 10,000,000, and `replay` otherwise, treating any missing, negative or non-finite measurement as failing its condition, and shall agree with the lane gate of spec 001 (FR-001-13) on every case of its conformance corpus (DC-001-08). | unit |
| FR-018-66 | Unwanted | If an artefact or engine labelled `live` in the web manifest has measurements for which `deriveLane` returns `replay`, or a live engine has no measurement in DC-018-06, then the web build shall fail and name it (FR-000-15). | contract (CI) |
| FR-018-67 | Unwanted | If a parity fixture fails its schema or its pinned SHA-256, an engine's fixture set is empty, or the parity report or the lane-measurement file fails its schema, then the parity suite or the build shall fail and name the file, and no engine shall be recorded as passing on an empty or invalid fixture set. | contract (hostile) |
| FR-018-68 | Unwanted | If the `SimClock` receives a non-finite or negative time or rate, then it shall ignore the call and keep its state; a seek beyond the duration D shall clamp to D. | unit (hostile) |

## 4. Correctness properties
Property tests use fast-check with the `property_tests` counts of `thresholds.yaml` (200 in CI, 2,000 at release); "exact" means `===` on
binary64 or on integers. Tolerances are justified in §7.2.

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-018-01 | For any sequence of play, pause, seek, step and rate operations driven by a fake time source, t stays in [0, D], and while playing at rate r ≥ 0 over a wall interval Δ, t advances by min(rΔ, D − t). | ops ≤ 200; r ∈ {0, 0.25, …, 8}; Δ dyadic in [0, 4] s | exact |
| P-018-02 | Clock rate scaling: doubling r for the same wall intervals doubles the advance until the clamp at D. | as P-018-01 | exact |
| P-018-03 | Clock idempotence: seek(t) twice equals seek(t) once; pause followed by play and pause with zero elapsed time leaves t unchanged. | t ∈ [0, D] | exact |
| P-018-04 | The TypeScript PCG64 port, seeded through SeedSequence as numpy's `default_rng` does, emits the same first 10⁴ 64-bit words and the same `random()` doubles as numpy's `PCG64` (the generator of the spec 010 Monte Carlo). | 3 entropy values × 3 spawn keys (incl. empty and multi-word keys) | exact |
| P-018-05 | Stream independence: interleaving draws from two generators with different spawn keys in any order leaves each generator's sequence unchanged. | 2 streams, random interleavings ≤ 10³ draws | exact |
| ~~P-018-06~~ | Withdrawn before approval: DES time scaling is P-007-08 (spec 007). | — | — |
| ~~P-018-07~~ | Withdrawn before approval: DES relabelling is P-007-06 (spec 007). | — | — |
| ~~P-018-08~~ | Withdrawn before approval: DES conservation and deterministic cycles are covered by P-007-09 (spec 007). | — | — |
| ~~P-018-09~~ | Withdrawn before approval: DES deterministic cycle is P-007-09 (spec 007). | — | — |
| ~~P-018-10~~ | Withdrawn before approval: the haulage port and its properties are specified by spec 007 (FR-007-15). | — | — |
| ~~P-018-11~~ | Withdrawn before approval: route energy relations are P-007-19 (spec 007). | — | — |
| ~~P-018-12~~ | Withdrawn before approval: fleet-sizing relations belong to spec 007 (FR-007-15) and the `minephys` haulage model. | — | — |
| ~~P-018-13~~ | Withdrawn before approval: LP relations are P-007-11 (spec 007). | — | — |
| ~~P-018-14~~ | Withdrawn before approval: LP relations are P-007-11 (spec 007). | — | — |
| ~~P-018-15~~ | Withdrawn before approval: LP relations are P-007-11 (spec 007). | — | — |
| ~~P-018-16~~ | Withdrawn before approval: routing relations are P-007-17 and P-007-18 (spec 007). | — | — |
| ~~P-018-17~~ | Withdrawn before approval: routing relations are P-007-17 and P-007-18 (spec 007). | — | — |
| ~~P-018-18~~ | Withdrawn before approval: routing relations are P-007-17 and P-007-18 (spec 007). | — | — |
| P-018-19 | TTC velocity scaling: TTC(p, k w) = TTC(p, w) / k. | k ∈ [0.1, 10]; closing pairs | rtol 1e-12 |
| P-018-20 | TTC rigid-motion invariance: translating and rotating both agents leaves TTC unchanged. | random SE(2) transforms | rtol 1e-12 |
| P-018-21 | TTC pair symmetry: TTC(a, b) = TTC(b, a). | random pairs | exact |
| ~~P-018-22~~ | Withdrawn before approval: the dust slider and its parity are specified by spec 013 (FR-013-38, P-013-15). | — | — |
| ~~P-018-23~~ | Withdrawn before approval: the dust slider and its parity are specified by spec 013 (FR-013-38, P-013-15). | — | — |
| ~~P-018-24~~ | Withdrawn before approval: the dust slider and its parity are specified by spec 013 (FR-013-38, P-013-15). | — | — |
| ~~P-018-25~~ | Withdrawn before approval: the live detectors have no browser-side NMS or box conversion (FR-009-35). | — | — |
| ~~P-018-26~~ | Withdrawn before approval: the live detectors have no browser-side NMS or box conversion (FR-009-35). | — | — |
| P-018-27 | Detector display monotonicity: raising the score threshold shows a subset of the detections shown before, and permuting the graph's output rows leaves the shown set unchanged. | thresholds in [0, 1]; random permutations of 300 rows | exact |
| P-018-28 | The factor of safety (Bishop, Spencer) is non-decreasing in effective cohesion c′. | sections in the validity range | exact (order) |
| P-018-29 | Translating the section geometry, slip surface and water table leaves the factor of safety unchanged. | shifts ≤ 10⁴ m | rtol 1e-9 |
| P-018-30 | Similarity: scaling all lengths and c′ by k (γ, φ′ and pore-pressure ratio fixed) leaves the factor of safety unchanged. | k ∈ [0.1, 10] | rtol 1e-9 |
| P-018-31 | Inverse-velocity time translation: shifting every observation time by Δ shifts the predicted failure time by Δ. | Δ ∈ [−10⁶, 10⁶] s | rtol 1e-12 of record span |
| P-018-32 | Inverse-velocity scaling: multiplying every velocity by k > 0 leaves the predicted failure time unchanged. | k ∈ [10⁻³, 10³] | rtol 1e-12 |
| P-018-33 | For an exact Voight α = 2 series (1/v linear in time), the predicted failure time equals the hand-calculated root of the line. | 20 hand-calculated series | rtol 1e-12 |
| P-018-34 | Slope-radar line of sight is linear: LOS(a d₁ + b d₂) = a LOS(d₁) + b LOS(d₂). | random displacement fields | rtol 1e-12 |
| P-018-35 | A displacement perpendicular to the line of sight projects to 0; a parallel one projects to ±‖d‖. | random geometries | atol 1e-12 m |
| P-018-36 | Rotating the scene and the radar together leaves every LOS value unchanged. | random rotations | rtol 1e-12 |
| P-018-37 | Gaussian plume concentration is linear in the source strength: C(kQ) = k C(Q). | k ∈ [0, 10⁴] | rtol 1e-12 |
| P-018-38 | Plume crosswind symmetry: C(x, y, z) = C(x, −y, z). | receptors in the grid | rtol 1e-12 |
| P-018-39 | AP-42 power law: doubling the silt content multiplies the emission factor by 2^a, doubling the mean weight by 2^b. | inputs in the AP-42 validity range | rtol 1e-12 |
| P-018-40 | Kuz-Ram x50 is non-increasing in powder factor at fixed rock and explosive inputs. | validity range | exact (order) |
| P-018-41 | Swebrec passing: P(x50) = 0.5, P(x_max) = 1, and P is non-decreasing in x. | valid (x50, x_max, b) | atol 1e-12 |
| P-018-42 | PPV square-root scaling: PPV(kR, k²W) = PPV(R, W). | k ∈ [0.1, 10] | rtol 1e-12 |
| P-018-43 | Bond specific energy is 0 when P80 = F80. | valid F80 | atol 1e-12 kWh/t |
| P-018-44 | Bond specific energy is non-increasing in P80 at fixed F80 and linear in the work index. | validity range | rtol 1e-12 (linearity); exact (order) |
| P-018-45 | Mine-to-mill chain mass balance: t/h leaving the mill equals t/h entering the crusher. | random designs | rtol 1e-12 |
| P-018-46 | Watershed invariance: a strictly increasing transform of the elevation image leaves the label map unchanged. | 64 × 64 to 512 × 512 images | exact |
| P-018-47 | Watershed flip equivariance: flipping the elevation and marker images flips the label map. | as P-018-46 | exact |
| P-018-48 | Changing the pixel size by k scales every fragment size, x50 and x80 by k. | k ∈ [0.1, 10] | rtol 1e-12 |
| P-018-49 | Min-cut: scaling every block value by k > 0 leaves the pit unchanged. | block models ≤ 10⁴ blocks | exact |
| P-018-50 | Min-cut: permuting block ids leaves the pit unchanged (as a set of positions). | as P-018-49 | exact |
| P-018-51 | Min-cut nesting: raising the revenue factor yields a pit that contains the previous pit. | revenue factors in [0.5, 2] | exact |
| P-018-52 | Survey volume additivity: for disjoint polygons, V(A ∪ B) = V(A) + V(B); a constant difference Δz over a polygon gives Δz × area (hand calculation). | grids ≤ 512 × 512 | rtol 1e-12 |
| P-018-53 | Survey volume antisymmetry: swapping the two epochs swaps cut and fill. | as P-018-52 | exact |
| P-018-54 | Survey volume linearity: scaling the difference field by k scales cut and fill by k. | k ∈ [0, 10] | rtol 1e-12 |
| ~~P-018-55~~ | Withdrawn before approval: the robot twins are specified by spec 014 (FR-014-40…42). | — | — |
| ~~P-018-56~~ | Withdrawn before approval: the robot twins are specified by spec 014 (FR-014-40…42). | — | — |
| ~~P-018-57~~ | Withdrawn before approval: the robot twins are specified by spec 014 (FR-014-40…42). | — | — |
| ~~P-018-58~~ | Withdrawn before approval: the IL-2 twin and its FEE force are specified by spec 014 (FR-014-41). | — | — |
| P-018-59 | Granular contact forces sum to zero over all particles without walls (Newton's third law). | ≤ 2×10⁴ particles | ‖Σf‖ ≤ 1e-5 Σ‖f‖ |
| P-018-60 | Translating every particle (no wall in range) leaves the contact forces unchanged. | random configurations | non-dim max abs 1e-3 |
| P-018-61 | Particle count is conserved exactly in a closed domain; MPM mass drift stays below 0.5 %. | full runs | exact (count); 0.5 % |
| P-018-62 | Shallow-water lake at rest: a flat free surface with zero velocity over any bed stays at rest. | 1,000 steps, random beds | ‖u‖ ≤ 1e-6 m/s; ‖Δη‖ ≤ 1e-5 m |
| P-018-63 | Shallow-water mirror symmetry: mirroring the initial state and the bed about x mirrors the solution. | 256 × 256 grids | non-dim max abs 1e-3 |
| P-018-64 | Shallow-water conservation and dam break: mass drift < 0.5 % in a closed domain, and the dry-bed front position is within ±5 % of the Ritter value 2√(g h₀) t. | h₀ ∈ [0.5, 20] m | 0.5 %; ± 5 % |
| P-018-65 | Dust particles in still air reach the Stokes terminal velocity (ρ_p − ρ_a) g d² / (18 μ) for particle Reynolds numbers < 0.1. | d ∈ [1, 30] µm | ± 1 % |
| P-018-66 | A uniform wind U shifts the particle-cloud centroid by U t and leaves its spread unchanged. | U ∈ [0, 20] m/s | rtol 1e-3 |
| P-018-67 | Dust particle count is conserved exactly in a closed box. | full runs | exact |
| P-018-68 | Shard round trip: decoding the 16-bit code (of the code type the header declares) of any value inside the header range returns it within half a quantum, (max − min) / 65,535 / 2. | random positions in bbox | ≤ half quantum |
| P-018-69 | Shard decoding preserves the order of quantised values. | all 65,536 codes | exact |
| P-018-70 | Shifting the header minimum by Δ shifts every decoded value by Δ. | dyadic Δ | exact |
| P-018-71 | `deriveLane` monotonicity: decreasing any size or time never turns `live` into `replay`. | random measurements incl. NaN | exact |
| P-018-72 | `deriveLane` boundaries are inclusive: exactly 25 MB, 16 ms, 1 s and 10 MB are `live` (hand table of 16 boundary cases). | hand table | exact |
| P-018-73 | `deriveLane` disjunction: with all other conditions met, either p95 interaction ≤ 16 ms or T2 run ≤ 1 s suffices. | random measurements | exact |
| P-018-74 | PCG64 advance consistency: `advance(n)` followed by one draw equals the (n + 1)-th draw of a fresh generator with the same seed for n ≤ 10⁶, and for n up to 2⁶⁴ − 1 equals numpy's `PCG64.advance(n)` followed by one draw. | n ∈ 0..10⁶; 20 random n < 2⁶⁴ | exact |
| P-018-75 | Uniform doubles: every `random()` value equals (word >> 11) × 2⁻⁵³ of the corresponding 64-bit word and lies in [0, 1). | 10⁶ draws, 3 seeds | exact |
| P-018-76 | Inverse-velocity time-unit invariance: expressing times in hours instead of seconds (velocities per hour) gives the same predicted failure instant. | random records | rtol 1e-12 |

## 5. Non-functional requirements and success criteria
| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-018-01 | First view of `/`: bytes transferred before the first interaction, including the LOD-0 tileset, the 3D chunk and fonts, until 2 s of network idle (NFR-000-03) | ≤ 2 MB (encoded bytes) | Playwright + CDP `encodedDataLength` |
| NFR-018-02 | Initial JavaScript of `/`, `/cases` and each `/cases/<id>/` (scripts referenced by the prerendered HTML; the 3D, engine and runtime chunks load by dynamic import) (NFR-000-01) | ≤ 200 KB gzip each (200,000 bytes; the postbuild constant is aligned by T-020-062) | `web/scripts/postbuild.mjs` |
| NFR-018-03 | Lane-gate targets per engine family (plan estimates): DES shift of ≈ 10⁴ events ≤ 1 s on T2; analytical evaluation ≤ 50 ms; min-cut on 10⁵ blocks ≤ 1 s; Rapier step for ≤ 40 vehicles ≤ 16 ms p95; WGSL granular 2×10⁴ particles ≥ 30 fps on T1; surrogate step ≤ 50 ms; detector ≤ 300 ms per image on T1; policies ≤ 2 MB each. A miss demotes the engine to REPLAY through FR-018-65 and is reported, not hidden | as stated | lane-measurement suite (DC-018-06); T1 figures in the `gpu` project |
| NFR-018-04 | Accessibility of `/`, `/cases` and the 12 case pages in light and dark, EN and ES (NFR-000-02); the 3D canvas has a visible text summary and the KPI table as its alternative | axe 0 serious/critical; Lighthouse accessibility ≥ 0.95 on `/`, `/cases`, `/cases/A1/` | Playwright + axe; LHCI |
| NFR-018-05 | Quality of the numerical cores in `web/src/engines/**`, `web/src/sim/**`, `web/src/assets/shard*` and `web/src/lane/**` | branch coverage ≥ 0.85; mutation score ≥ 0.80 (fail < 0.70) | Vitest coverage; Stryker |
| NFR-018-06 | Pyodide "Run in Python" first result on CI Chromium | ≤ 20 s (warn), hard limit 60 s (FR-018-62) | Playwright timing |
| SC-018-01 | At the web gate, every engine of §7.1 passes its parity class: TS, WASM and Rapier classes in CI in Chromium, Firefox and WebKit; WGSL and WebGPU classes in the `gpu` project; an engine without a pass is shown in T0 (FR-018-63) and listed as such | 100 % of engines either pass or are shown as T0 with the note | parity report (DC-018-05) |
| SC-018-02 | Vertical slice: `/cases/A1/` and `/cases/C1/` work end to end on the open lane (DES, limit equilibrium, inverse velocity, Bingham terrain) on a Pages preview before any NVIDIA-runtime work | both pages pass their E2E and parity tasks | CI on the preview build |

## 6. Data contracts
| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-018-01 | Case registry `studio/cases.yaml`: per case id, category, titles EN/ES, question, KPIs (name, unit, orientation), data source ids, synthetic data, methods, tools, engines, layers, clock fps, recipe path, validity range | `specs/018-web-cases/contracts/cases.schema.json` (draft; promoted to `contracts/cases.schema.json` by T-018-001) | maintainer → web build (`/`, `/cases`, `/cases/:id`), docs matrices, CI checks, spec 019 tool pages |
| DC-018-02 | Engine input and output schemas, one per engine id, with units, validity ranges, size caps and unit scales | `specs/018-web-cases/contracts/engines/<engine-id>.schema.json` (draft, one per engine id; promoted to `contracts/engines/<engine-id>.schema.json` by T-018-002) | maintainer → web engine host validators (generated), parity-fixture generator |
| DC-018-03 | Replay shard header (JSON) for 16-bit-quantised pose, particle and point shards ≤ 10 MB (code type `int16` or `uint16` declared in the header) and for 16-bit PNG / Float32 field tiles: schema version, kind, units, fps, frame range, item count, channels, bbox min/max, SHA-256 of the payload | `specs/018-web-cases/contracts/replay-shard.schema.json` (draft; `$defs/shard_header` and `$defs/replay_manifest`, the latter also DC-005-04; promoted to `contracts/replay-shard.schema.json` by T-018-003) | `s60_export`, `studio publish` → web shard reader |
| DC-018-04 | Parity fixtures `web/tests/fixtures/parity/<engine-id>/<fixture>.json[.gz]`: inputs, reference outputs, recorded variate streams, reference name and version, tolerance class | `specs/018-web-cases/contracts/parity-fixture.schema.json` (draft; promoted to `contracts/parity-fixture.schema.json` by T-018-004) | `tools/make_parity_fixtures.py` (pipeline environment, references) → Vitest and Playwright parity tests |
| DC-018-05 | Parity report `assets/parity-report.json` in the built Pages artifact, for the built commit: per engine id, version, class, tolerance, maximum observed error, browsers, verdict | `specs/018-web-cases/contracts/parity-report.schema.json` (draft; promoted to `contracts/parity-report.schema.json` by T-018-004) | parity suite in CI → web app (FR-018-63), `/results` parity tab (020) |
| DC-018-06 | Lane measurements `assets/lane-measurements.json` in the built Pages artifact: per engine or artefact id, web-drivable flag, asset bytes, p95 interaction ms, T2 run s, trace bytes, runner configuration, commit | `specs/018-web-cases/contracts/lane-measurements.schema.json` (draft; promoted to `contracts/lane-measurements.schema.json` by T-018-004) | lane-gate suite in CI → CI lane check (FR-018-66), export stage |

Consumed, defined elsewhere: the web manifest (DC-000-01, schema by spec 001), the tool registry (DC-000-04) and the
data registry (DC-000-05).

## 7. Edge cases and assumptions

### 7.1 Engine table
| Engine id | Cases | Runtime | Parity class | Python reference | Size cap | Timeout | T0 fallback |
|---|---|---|---|---|---|---|---|
| `des` | A1 | TS worker (spec 007) | exact event trace (FR-007-10) | `minehaulsim` through the spec 007 adapter | as FR-007-03 and FR-007-13 (live bundles ≤ 40 trucks; ≤ 2×10⁶ events) | 10 s | baked traces |
| `policies` | A1 | ORT-web inside the DES worker (spec 007) | FR-007-32 | ONNX Runtime CPU 1.30 | ≤ 2 MB per policy | 10 s | baked traces |
| `haulage` | A1, A2 | TS worker (spec 007) | FR-007-15 | `minephys.haulage` | as FR-007-16 | 2 s | baked grid |
| `lp` | A1 | TS worker (spec 007) | FR-007-20 | HiGHS (`highspy`) | as FR-007-21 | 2 s | baked solution |
| `routing` | A2, E1 | TS worker (spec 007) | FR-007-39 | the spec 007 Python router; networkx Dijkstra as oracle | as FR-007-36 (browser DEM ≤ 1024 × 1024 cells) | 5 s | baked routes |
| `il1-twin` | A2 | TS worker + ORT-web (spec 014) | FR-014-42 | Python twin of spec 014 | as spec 014 (≤ 2,000 steps) | 10 s | baked rollouts |
| `il2-twin` | A3 | TS worker + ORT-web (spec 014) | FR-014-42 | Python twin of spec 014 | as spec 014 (≤ 2,000 steps) | 10 s | baked rollouts |
| `granular` | A3 | WGSL compute (T1 only) | chaotic / particle | Warp DEM / MPM on the CPU device (kernels); spec 005 goldens DC-005-06 (observables) | ≤ 2×10⁴ particles | 30 s | replay shards, aggregates |
| `gns` | A3 | ORT-web | ML | ONNX Runtime CPU | ≤ 5,000 particles; model ≤ 25 MB | 10 s | precomputed rollouts |
| `traffic` | B1 | Rapier WASM + TS agents | rigid body (snapshot hash); TTC closed form | Rapier 0.21 in Node; TTC hand calculation | ≤ 40 vehicles | 10 s | baked video |
| `dust-lidar` | B1, C3 | TS worker (spec 013) | P-013-15 | the spec 013 Python post-model | as spec 013 (frames ≤ 150,000 returns) | 2 s | baked frames |
| `detector` | B2 | ORT-web (post-processor in the graph, no NMS) | ML | ONNX Runtime CPU on the spec 009 export | shipped sample frames only, 640 × 640 input | 5 s | precomputed detections |
| `geotech` | C1 | TS worker | analytical (+ statistical Monte Carlo) | `minephys.geotech` | ≤ 200 slices; ≤ 10⁵ Monte-Carlo samples | 5 s | baked grid |
| `forecasters` | C1 | ORT-web | ML | ONNX Runtime CPU | each ≤ 25 MB | 10 s | precomputed forecasts |
| `swe` | C2 | WGSL compute (T1 only) | chaotic / field | Warp shallow-water solver on the CPU device (kernels); spec 005 goldens DC-005-06 (observables) | ≤ 256 × 256 cells | 30 s | baked aggregates |
| `fno` | C2 | ORT-web | ML | ONNX Runtime CPU | ≤ 25 MB | 10 s | precomputed fields |
| `plume` | C3 | TS worker | analytical | `minephys.environment` (AP-42, Gaussian plume) | receptor grid ≤ 256 × 256 | 2 s | baked grid |
| `dust-particles` | C3 | WGSL compute (T1 only) | particle | Warp particles on the CPU device (kernels); spec 005 goldens DC-005-06 (observables) | ≤ 2×10⁴ particles | 30 s | replay shards |
| `blasting` | D1 | TS worker | analytical | `minephys.blasting` | — | 2 s | baked grid |
| `watershed` | D1 | TS worker | exact label map on fixture inputs | Python watershed baseline of spec 012 | ≤ 1024 × 1024 px | 5 s | precomputed PSDs |
| `unet` | D1 | ORT-web | ML | ONNX Runtime CPU | ≤ 25 MB | 10 s | precomputed masks |
| `comminution` | D2 | TS worker | analytical | `minephys.comminution` | — | 2 s | baked grid |
| `meta-model` | D2 | ORT-web | ML | ONNX Runtime CPU | ≤ 1 MB | 5 s | precomputed answers |
| `mincut` | E1 | TS worker | combinatorial | `minephys.planning` min-cut; networkx maximum flow as oracle | ≤ 10⁵ blocks | 10 s | baked nested shells |
| `volume` | E2 | TS worker | analytical | numpy DEM differencing of spec 017 | polygon ≤ 10⁴ vertices; grid ≤ 2048 × 2048 | 5 s | baked volumes |

The exact function list of each analytical port and its input domain are fixed in DC-018-02 (task T-018-002); the
slope-radar line-of-sight model, inverse velocity and the Bayesian time-to-failure band belong to `geotech`. The
engine-specific errors of specs 007, 013 and 014 (for example `InvalidScenario`, `UnsupportedFeature`) travel inside the
host's typed error (FR-018-38) as its `detail.name`.

### 7.2 Parity classes and tolerances
- **Engines of specs 007, 013 and 014** (DES, policies, haulage, LP, routing, dust slider, robot twins) keep the
  classes and tolerances of those specs; this spec only records their verdicts (FR-018-48).
- **PCG64 port — exact.** The generator is integer arithmetic; (word >> 11) × 2⁻⁵³ is exact in binary64.
- **Monte Carlo — exact count on fixture samples; binomial 3σ otherwise.** Normal and lognormal variates by inverse CDF
  use implementation-approximated functions, so samples drawn in the browser can differ in the last bits; the bound
  3√(p(1 − p)/N) + 1/N has a false-alarm rate below 0.3 % under the normal approximation, the 1/N term covering one
  sample flipping across F = 1.
- **Analytical — rtol 1e-9, atol 1e-12 × unit scale.** ECMAScript `Math.pow`, `exp` and `log` are
  implementation-approximated, so bitwise equality with CPython is not guaranteed. A closed form of ≤ 20 operations with
  ≤ 1 ulp error each accumulates ≤ 20 × 2.2e-16 ≈ 4.4e-15 relative error; rtol 1e-9 leaves a margin of 2×10⁵ for
  conditioning and stays five orders below the 4 significant figures the UI displays. Iterative solvers are bounded by
  their convergence tolerance, hence max(1e-9, 10 × tolerance).
- **Min-cut — exact set; objective rtol 1e-10.** The minimal minimum cut (the set reachable from the source in the
  residual network of any maximum flow) is unique, so set equality is well defined. Sums of n ≤ 10⁵ binary64 block
  values in different orders differ by at most n ε ≈ 2.2e-11 relative, inside 1e-10.
- **Detector boxes — 0.5 px (WASM), 1 px (WebGPU).** The graph's post-processor scales normalised boxes by the frame
  size, so a normalised error e becomes 640 e px: the WASM bound 1e-4 gives 0.064 px and the WebGPU bound 1e-3 gives
  0.64 px (FR-018-57); 0.5 px and 1 px leave margin and stay below what the overlay can draw at its display scale.
- **Rapier — exact snapshot hash.** Rapier's JS/WASM build is cross-platform deterministic for one version and identical
  initial state; initial states are written in the fixture as binary64, never computed with `Math.sin`/`cos` in the
  browser.
- **WGSL — non-dimensional max abs 1e-3 per kernel, observables ± 1.5° / 5 % / 0.5 %.** WGSL has fp32 arithmetic and
  only integer atomics (fixed-point accumulation), and granular flow is chaotic, so trajectories are never compared;
  the observable tolerances are those of DEC-0006 and of the physics benchmarks.
- **ML — `web.*` thresholds** from `specs/000-foundation/thresholds.yaml`.

### 7.3 Other assumptions
- CI runs on a hosted Linux runner without a GPU: T1 code paths are tested with the fake GPU backend
  (`web/src/engines/tier/fake-gpu.ts`, scripted adapters: none, null adapter, `requestDevice` rejection, device lost
  after N ms, buffer allocation failure); WGSL and WebGPU parity tests are tagged `@gpu`, run in the Playwright project
  `webgpu` on a machine with a WebGPU adapter, and are reported "not run" (never "passed") elsewhere.
- Lane timings are measured on the CI runner configuration recorded in DC-018-06; a slower visitor device can still feel
  slow, which the tier badge and T0 cover.
- Visitors upload no files: detectors, watershed and U-Net run on the shipped sample frames; the B2 corruption slider
  selects baked corrupted versions of those frames (severities 0–5), so no image-corruption code is ported.
- UNVERIFIED and therefore not relied on: whether three.js runs TSL `compute()` on its WebGL 2 backend (T2 never assumes
  GPU compute); whether Spark renders on WebGPURenderer (splats keep WebGLRenderer); whether GitHub Pages serves range
  requests (shards are separate files ≤ 10 MB); a WebGPU kernel for ScatterElements in ORT-web (the GNS uses its
  dense-adjacency export); the live detectors need no NonMaxSuppression kernel because their post-processor is in the
  graph (spec 009).
- Thresholds used here, as `thresholds.yaml` keys:
  `web.analytical_fp64_rtol: 1.0e-9`, `web.analytical_fp64_atol_scale: 1.0e-12`, `web.mc_pof_sigma: 3`,
  `web.detector_box_px_max: {wasm: 0.5, webgpu: 1.0}`, `web.granular_repose_deg: 1.5`, `web.granular_runout_rel: 0.05`, `web.granular_discharge_rel: 0.05`,
  `web.mass_drift_rel_max: 0.005`, `lane_gate.live_asset_mb_max: 25`, `lane_gate.interaction_ms_max: 16`,
  `lane_gate.run_s_max: 1`, `lane_gate.trace_mb_max: 10`, `budgets.first_view_mb_max: 2`.

## 8. Clarifications log
- Resolved — *asset in the lane gate.* `docs/architecture/lanes.md` counts "a WASM runtime" as an asset, but the ORT-web
  build is 26.78–28.31 MB, which would make every ONNX model non-live, against the plan's §10 ("GNS, FNO, … live
  (ORT-web) — each ≤ 25 MB"). The plan wins: $S_\text{asset}$ is the largest engine-specific file (model, policy,
  shard, scene, fixture); shared runtimes are budgeted in the runtime class (≤ 55 MB, NFR-020-03).
- Resolved — *"exact" for analytical ports.* `docs/architecture/lanes.md` groups LEM, Kuz-Ram and plume under "exact
  event trace"; `docs/methods/README.md` says "golden vectors to floating-point tolerance". Only the DES has an event
  trace; analytical ports use the FR-018-51 tolerance.
- Resolved — *engines specified in other specs.* The DES twin, its Philox4x64-10 variate source, the learned
  dispatchers in the twin, the haulage port, the LP and the router are specified by spec 007; the dust slider by spec
  013; the IL-1/IL-2 twins by spec 014. This spec hosts them and records their verdicts (FR-018-48) and withdrew its own
  overlapping rows (FR-018-50, FR-018-60, P-018-06…18, P-018-22…24, P-018-55…58) before approval. The PCG64 port
  (P-018-04) remains for the Monte Carlo of spec 010 (FR-010-03), which uses numpy `PCG64` through `SeedSequence`.
- Resolved — *NMS.* `docs/web/compute-tiers.md` and `docs/frameworks/onnx-runtime.md` say detection runs NMS in a
  TypeScript worker; spec 009, following the plan's M10 and the D-FINE model card, keeps the post-processor and top-K
  inside the graph (NMS-free, FR-009-35). This spec follows spec 009: the browser only feeds the graph and thresholds its output (FR-018-58).
- Resolved — *units.* Specs 001 and 006 read MB as 10⁶ bytes (the stricter reading of the lane gate and budgets); this
  spec does the same. The git per-file cap stays 10 MiB (`tools/check_repo.py`).
- Resolved — the near-miss threshold τ* is 3 s (docs M20 leaves it to the spec; the IL-1 criterion uses 3 s).
- Resolved — the case registry lives in `studio/cases.yaml` next to `studio/tools.yaml` (the docs name "the case
  registry" without a path).
- Resolved — case ids are canonical upper case (`/cases/A1/`); other spellings answer 404.
- Resolved — the B2 corruption slider shows baked corrupted frames; there are no visitor uploads.
- Resolved — the interaction bound is 16 ms as written in the plan (one 60 Hz frame is 16.7 ms).
- Resolved — size caps not given by the plan or by specs 007, 013 and 014 (shallow water 256 × 256, GNS 5,000
  particles, polygons 10⁴ vertices, watershed 1024 × 1024) are fixed in §7.1 from the gate estimates.
- Integration 2026-10-07: the opt-in connect control is spec 019's (FR-019-44); the out-of-scope line names it.
- Integration 2026-10-07: the threshold keys this spec proposes are marked "proposed keys, pending maintainer
  approval"; its `lane.*` and `web.first_view_mb_max` names are replaced by the consolidated `lane_gate.*` and
  `budgets.first_view_mb_max`.
- Integration 2026-10-07: draft schemas written for DC-018-01, DC-018-03, DC-018-04, DC-018-05 and DC-018-06
  (`specs/018-web-cases/contracts/`, valid and hostile examples indexed in `examples/index.json`). Resolved, stricter
  reading each time: (1) the case registry keys `categories` by letter and `cases` by the 12 canonical ids, so a
  missing, unknown or repeated id (a duplicate key, rejected by the loader) fails, and each case's `category` and
  `recipe` are fixed to its id; tools are a map tool id → `named` / `supporting` (the ● and ○ marks of the tool
  matrix); KPI units are a closed ASCII enum and orientation is `higher-is-better`, `lower-is-better`, `target`
  (with `target_value`) or `neutral`; synthetic data carry the spec 008 validation class. (2) `replay-shard.schema.json`
  is owned here and holds two documents, `$defs/shard_header` (this DC) and `$defs/replay_manifest` (FR-005-45,
  DC-005-04), chosen by `document`. Contradiction kept open, not fixed in FR text: this spec and DEC-0006 say int16
  codes, FR-005-45 says uint16; both headers and manifests declare `code_type` (`int16` or `uint16`) and the code range
  is bound to it. Every payload, field tiles included, is ≤ 10,000,000 bytes; the FR-018-45 length rule (× 2) applies
  to raw 16-bit payloads, Float32 tiles use × 4 and PNG tiles are checked by decoded size. (3) Parity classes are 15
  classes drawn from §7.2 plus `hosted` (engines of specs 007, 013, 014, with the owning requirement); each tolerance
  value is capped at the spec value, so a looser tolerance fails; analytical and ML fixtures need ≥ 200 vectors and a
  passing report entry needs ≥ 1 fixture file. Spec 016's export parity report is a different artefact, renamed
  `export-parity-report.schema.json` to avoid the name clash. (4) Lane measurements reuse the manifest's
  `lane_measurements` record, so the DC's "T2 run s" is stored as `run_ms_t2` in milliseconds; the runner record fixes
  headless Chromium, forced T2, 50 interactions and 5 runs.
- Integration 2026-10-07: draft engine schemas written for DC-018-02 (`specs/018-web-cases/contracts/engines/`, one per
  engine id: `des`, `policies`, `haulage`, `lp`, `routing`, `il1-twin`, `il2-twin`, `granular`, `gns`, `traffic`,
  `dust-lidar`, `detector`, `geotech`, `forecasters`, `swe`, `fno`, `plume`, `dust-particles`, `blasting`, `watershed`,
  `unet`, `comminution`, `meta-model`, `mincut`, `volume`; valid and hostile examples indexed in
  `examples/index-engines.json`). Resolved, stricter reading each time: (1) each file holds `$defs/input` (request) and
  `$defs/output` (result), discriminated by `kind`; both carry `engine` (const), `engine_version` (semver) and
  `function`, which selects the closed `args` or `result` record; inputs and outputs are SI with unit-suffixed names and
  the UI converts to display units; the FR-018-38 typed error has no DC row and is not part of these files. (2) Shipped
  files (scenario and twin bundles, frames, DEMs, models, policies) are referenced by web-manifest artefact id, SHA-256
  and byte size, never by path, and their caps are schema maxima (models 25 MB; dispatch policies < 2 MB as NFR-007-03
  states; IL policies < 1 MB; meta-model < 10⁶ bytes); per-pixel, per-cell and per-particle arrays travel as transferred
  typed-array buffers described by dtype, named dimensions and byte length. (3) The function list of each analytical
  port is fixed here: `geotech` `bishop`, `spencer`, `pof_monte_carlo`, `pof_from_samples`, `inverse_velocity`,
  `failure_band`, `slope_radar_los` (Mohr–Coulomb slices; line of sight positive away from the radar as in
  `minephys`); `blasting` `charge_per_hole`, `powder_factor`, `kuznetsov_x50`, `uniformity_index`, `swebrec_passing`,
  `kco_undulation`, `ppv_scaled_distance`, `flyrock_range_no_drag`; `plume` `ap42_emission_factor`, `pasquill_sigmas`,
  `plume_grid` (receptors in the plume frame, x downwind); `comminution` `bond_energy`, `passing_size`,
  `mine_to_mill_chain` (Bond only; the Morrell chain stays in Python); `volume` `cut_fill`. The unit scales $s_y$ are
  `$defs/unit_scales`: 1 in the field's SI unit, except emission factor 10⁻⁶ kg/m, concentration 10⁻⁹ kg/m³, PPV
  10⁻³ m/s and comminution sizes 10⁻⁶ m. (4) Validity ranges follow the `minephys` validity rows where they exist
  (AP-42 silt 1.8–25.2 % and weight 2–290 short tons, rock factor 0.8–22, powder factor ≤ 5 kg/m³, P80 ≥ 70 µm,
  route-energy |grade| ≤ 0.30 and rolling resistance ≤ 0.20), so a value `minephys` only warns about returns
  `E_RANGE`; where no spec gives a bound a physical one is chosen (for example inverse-velocity records ≤ 10⁵ points
  with v ≤ 10⁻² m/s, traffic runs ≤ 36,000 steps, LP ≤ 16 loaders and dumps). (5) Seeds are integers in
  [0, 2⁵³ − 1], exact in JavaScript and inside [0, 2⁶³) and [0, 2⁶⁴). (6) The hosted engines take the DES bundle
  (DC-007-01), the dust-slider frame (DC-013-05) and the twin bundle (DC-014-05) as assets that the owning engine
  validates, the DES returns its trace (DC-007-02) as a UTF-8 JSON buffer, and the learned dispatcher ids are `ppo`
  and `attention`. (7) Meta-model inputs outside the sweep box are flagged `extrapolation` (FR-017-09), not rejected;
  only the physical domain gives `E_RANGE`. Kept open, not fixed in FR text: P-018-43 (W = 0 at P80 = F80) against the
  `minephys` rejection of P80 ≥ F80; the line-of-sight sign of FR-010-41 against `minephys`; the dust Reynolds bound
  (P-018-65 < 0.1 with diameters, FR-005-39 < 1 with the radius as parameter; the schema bounds the radius to
  0.5–15 µm and the engine checks the bound); the granular discharge observable has no twin scenario in FR-005-22.
- Integration 2026-10-07 (2): the maintainer approved the threshold keys; the text now cites them as plain `thresholds.yaml` keys.
- Integration 2026-10-07 (2): shard code type resolved. This spec owns the replay-shard schema (DC-018-03); its header and the
  replay manifest declare `code_type` (`int16` or `uint16`), the reader takes the code type from the header, and
  DC-018-03, P-018-68 and FR-005-45 no longer fix one type (the open contradiction of the first pass is closed).

## 9. Changes (only for features that modify earlier behaviour)
### ADDED Requirements
- (none beyond this spec; the stub pages of `/` and `/cases` are replaced. No earlier requirement is modified; the rows
  struck through in §3 and §4 are this spec's own, withdrawn before approval)
### MODIFIED Requirements
- (none)
### REMOVED Requirements
- (none)

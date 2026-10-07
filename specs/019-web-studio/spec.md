# Spec 019 — Web studio: tool map, tool pages, published runs, GPU evidence and showcase honesty
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent
The site must show what the local studio actually did, tool by tool, without turning into a brochure for proprietary
software or presenting more than was run. This spec covers `/studio` (an interactive tool map: nodes are tools, colour
is lane, badge is ring, icon is licence class, edges are file handoffs, with the physical-AI loop tied to real run
manifests below it), the tool pages `/studio/tools/:toolId` (identity with the version read from the lock, mining role,
the artefacts each tool produced filtered by `producer.tool` with LIVE / REPLAY / STATIC badges, provenance, where it
ran, limits, reproduce, alternatives; "Not yet run" when nothing is published; "Evaluated, not adopted" pages), the
ledger `/studio/runs` and the run pages `/studio/runs/:runId` (manifest viewer, telemetry chart, stage DAG with cache
hits, determinism check), `/studio/gpu` (open-runtime timelines: busy %, VRAM against 16 GB, power against the enforced
limit, SM clock, throttle reasons; the local-only licence note for Isaac Sim, Kit, Replicator, ovrtx and TensorRT for
RTX) and the honesty rules checked in CI. Developers and reviewers benefit: every artefact leads to the tool, run,
manifest and GPU evidence behind it. Out of scope: producing runs, manifests and run cards (specs 002, 006), the
manifest and tool-registry schemas (001), the console endpoint, CORS and loopback rules behind the opt-in "connect to
my local studio" control (003; the control itself is FR-019-44, FR-019-45), the case pages (018) and the chart
component (020).

## 2. User stories
### US-019-1 (P1) See the studio as a map
As a developer, I want a map of the studio's tools with their lane, ring, licence class and the files they hand to each
other, so that I understand how the pipeline is built. Independent test: open `/studio`, check 17 tool nodes plus the
evaluated-not-adopted group, the encodings, keyboard access, and the static fallback with JavaScript disabled.

### US-019-2 (P1) Find what a tool produced
As a reviewer, I want each tool's page to show only the artefacts that tool produced, with provenance, or say "Not yet
run", so that nothing is attributed to a tool that did not make it. Independent test: with a fixture manifest, `/studio/tools/warp/`
lists exactly the Warp artefacts; with an empty one it reads "Not yet run".

### US-019-3 (P2) Inspect a published run
As a developer, I want to open a published run and see its manifest, stages, cache hits, telemetry and determinism
check, so that I can reproduce and judge it. Independent test: a fixture run card renders all five blocks and its
SHA-256 digests.

### US-019-4 (P2) Read GPU evidence honestly
As a practitioner, I want GPU timelines that state how they were measured and never show numbers that a licence forbids
publishing, so that I can compare runs fairly. Independent test: a run with a public PyTorch stage and a local-only
Isaac Sim stage shows charts for the first and only the licence note for the second.

### US-019-5 (P1) Keep the showcase honest in CI
As the maintainer, I want CI to fail when a tool is marked done without an artefact, when a proprietary tool contributes
anything but outputs, when a render is not of our scene, or when a local-only metric leaks, so that the site cannot drift
into overclaiming. Independent test: each planted violation fails its check.

| Story | Priority | Title |
|---|---|---|
| US-019-1 | P1 | See the studio as a map |
| US-019-2 | P1 | Find what a tool produced |
| US-019-3 | P2 | Inspect a published run |
| US-019-4 | P2 | Read GPU evidence honestly |
| US-019-5 | P1 | Keep the showcase honest in CI |

## 3. Functional requirements (EARS)
Sizes use KB = 10³ bytes and MB = 10⁶ bytes, as specs 001 and 006 do. A "run card" is the published run manifest that
`studio publish` writes (FR-002-48, `web/public/assets/runs/<run_id>/manifest.json`, schema DC-001-01) together with its
published telemetry (DC-002-03, ≤ 200 KB per run, FR-002-50); this spec reads them.

### 3.1 Tool map (`/studio`)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-019-01 | Ubiquitous | `/studio` shall render an interactive tool map with one node per tool-registry entry — the 17 studio tools, plus the evaluated-not-adopted entries in a separate labelled group — where the node colour encodes the lane (`live`, `replay`, `local-only`) together with a text label, a badge shows the ring (Adopt, Trial, Assess, Hold), a lucide icon distinct per licence class shows the licence class, and each edge is a file handoff of DC-019-02 labelled with the artefact kind it carries. | unit + E2E |
| FR-019-02 | Ubiquitous | Node positions shall be computed at build time from each entry's lane and its order in DC-019-02 (bands: scene → physics → sensors and synthetic data → training → acceleration → encoding → web), identical inputs shall give a byte-identical layout, and no layout library shall run in the browser. | unit |
| FR-019-03 | Ubiquitous | The React Flow (`@xyflow/react`) chunk shall be requested only on `/studio`, after hydration, and shall belong to no route's initial JavaScript. | E2E |
| FR-019-04 | Ubiquitous | The prerendered HTML of `/studio` shall contain a static SVG of the same graph and a data table (tool, environment, lane, ring, licence class, status, inbound and outbound handoffs), both usable with JavaScript disabled. | E2E |
| FR-019-05 | Event | When the visitor activates a node by click, Enter or Space, the app shall open `/studio/tools/<id>/`; nodes shall be reachable with Tab in band order, and each shall have the accessible name "<name> — lane <lane>, ring <ring>, licence <class>, status <status>". | E2E |
| FR-019-06 | Ubiquitous | An edge A → B shall be drawn solid with "observed in run <run id>" when a published artefact produced by B lists among its inputs an artefact produced by A, and dashed with "planned" otherwise. | unit |
| FR-019-07 | Ubiquitous | Below the map, `/studio` shall show the physical-AI loop (scene → sensors and synthetic data → labels → training → validation → acceleration → encoding → web), each step linking to the published runs whose stages realise it (§7.2) or showing "Not yet run". | unit + E2E |

### 3.2 Tool pages (`/studio/tools/:toolId`)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-019-08 | Ubiquitous | For every registry id of §7.1, `/studio/tools/<id>/` shall be a prerendered page answering HTTP 200 with eight blocks in this order: Identity · Role in mining · Artefacts it produced · Provenance · Where it ran · Limits and failures · Reproduce · Alternatives rejected. | E2E |
| FR-019-09 | Ubiquitous | The Identity block shall show the version resolved from the lock named in the registry (the environment's `uv.lock`, `web/pnpm-lock.yaml`, or the pinned external-binary record), its release date, the licence (SPDX id or name) and licence class, the ring, the environment, the capability-probe status from `studio/capabilities.json` (pass, fail or skip, with date, GPU and driver, and the public metrics or the text "measured locally, not published (licence)"), and, for NVIDIA tools, the non-affiliation notice. | contract + E2E |
| FR-019-10 | Unwanted | If a registry version differs from the version resolved from its lock or record, or the lock entry cannot be resolved, then the build shall fail naming the tool. | contract |
| FR-019-11 | Ubiquitous | The Role in mining block shall show the tool's mining role and the cases that use it, from the case registry (DC-018-01), each linking to `/cases/<id>/`. | unit |
| FR-019-12 | Ubiquitous | The Artefacts block shall list every web-manifest artefact whose `producer.tool` equals the page's id, grouped by case, each as an artefact card with its LIVE, REPLAY or STATIC badge (FR-018-18). | unit + E2E |
| FR-019-13 | Unwanted | If no artefact names the tool as producer and its status is not `evaluated-not-adopted`, then the page and its map node shall show "Not yet run", and the page shall show no image, video or metric of the tool (FR-000-07). | unit + E2E |
| FR-019-14 | State | While a tool's status is `evaluated-not-adopted`, its page shall show "Evaluated, not adopted" with the recorded reason and a link to its evidence page, and no artefact grid. | unit + E2E |
| FR-019-15 | Ubiquitous | Each artefact shall carry provenance chips — run id, recipe SHA-256 (first 12 hex), git SHA (7 hex), GPU model, driver, wall time, peak VRAM, energy (J) and the throttle shares (% of samples per clocks-event reason: software power cap, software thermal, hardware thermal, hardware slowdown, power brake) — and, for a stage with `performance: local-only`, the wall-time, VRAM, energy and throttle chips shall be replaced by "measured locally, not published (licence)". | unit + E2E |
| FR-019-16 | Ubiquitous | The Where it ran block shall read "Live in your browser" for live artefacts and otherwise "Precomputed on <GPU name> (<total memory> GB, power limit <W> W) on <date>". | unit |
| FR-019-17 | Ubiquitous | The Limits and failures block shall list the registry's recorded limits and every failed or rejected variant found in the tool's published manifests (for example TensorRT engines rejected by parity), with their numbers. | unit |
| FR-019-18 | Ubiquitous | The Reproduce block shall show the runner commands of the tool's published runs and their requirements (for `reference-only` tools: "needs an NVIDIA RTX GPU and acceptance of the NVIDIA terms"), with no absolute path, host name or user name. | unit |
| FR-019-19 | Ubiquitous | The Alternatives rejected block shall list the registry's rejected alternatives with their reasons. | unit |
| FR-019-20 | Unwanted | If the tool id is not a registry id (other spellings, encoded separators and `..` included), then the site shall answer HTTP 404 with the not-found page and request no tool asset. | E2E (hostile) |

### 3.3 Published runs (`/studio/runs`, `/studio/runs/:runId`)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-019-21 | Ubiquitous | `/studio/runs` shall list only runs published with `studio publish` (a run card in the Pages artifact), newest first, with run id, cases, producer tools, UTC date, determinism class and artefact count, filterable by case and tool through `?case=` and `?tool=`, and shall show "No published runs yet" when there is none. | unit + E2E |
| FR-019-22 | Ubiquitous | For every published run, `/studio/runs/<run id>/` shall be a prerendered page answering HTTP 200 with a manifest viewer, telemetry charts of its open-runtime stages, the stage DAG with cache hits, the determinism block and its artefacts. | E2E |
| FR-019-23 | Ubiquitous | The manifest viewer shall render the run card as a collapsible tree operable with the WAI-ARIA tree keys, show each SHA-256 in full with a copy control, render every string as text, and render a 200 KB run card within 500 ms on CI Chromium. | unit + E2E |
| FR-019-24 | Ubiquitous | The stage DAG shall show one node per stage with cache hit or miss as text and icon, exit status, retries and wall time (omitted for `performance: local-only` stages), and edges from each stage's inputs. | unit + E2E |
| FR-019-25 | Ubiquitous | The determinism block shall show the class (`bitwise`, `statistical`, `none`) and the re-run check: for `bitwise` both SHA-256 digests and "equal" or "different"; for `statistical` each observable with its tolerance and both values; for a missing check "pending". | unit |
| FR-019-26 | Unwanted | If a run id is not a published run (unknown, local, malformed or traversing), then the site shall answer HTTP 404 and request no run asset. | E2E (hostile) |

### 3.4 GPU evidence (`/studio/gpu`)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-019-27 | Ubiquitous | `/studio/gpu` shall show, for each published stage with `performance: public`, timelines of GPU busy % (labelled "time-busy fraction, not SM occupancy"), memory used against the GPU's total memory (`gpu.vram_total_bytes`; 16 GB on the reference machine), board power against the enforced limit (`gpu.power_limit_enforced_w`), SM clock, and the clocks-event (throttle) reasons as a stacked fraction band, each chart following FR-020-07 to FR-020-16. | unit + E2E |
| FR-019-28 | Ubiquitous | GPU busy % shall never appear without the stage's power-at-limit fraction beside it. | unit |
| FR-019-29 | Event | When the visitor opens "How measured" on a chart, the popover shall state that run's NVML sampling rate, the definitions of utilisation, power averaging and energy (difference of the total-energy counter), and link the NVML reference pages. | E2E |
| FR-019-30 | Ubiquitous | Stages that ran Isaac Sim, Kit, Replicator, ovrtx or TensorRT for RTX shall appear on `/studio/gpu` with links to their outputs, the note "Performance measured locally, not published (licence: NVIDIA SLA §8.9 / TensorRT for RTX SLA §2.13)" and no numeric telemetry, while stages that ran regular TensorRT on PitStudio's own models shall show full telemetry. | unit + E2E |
| FR-019-31 | Unwanted | If a telemetry field is null or missing in a run card, then the chart or chip shall show "not available on this GPU" and shall never draw 0 or an interpolated value for it. | unit |
| FR-019-32 | Ubiquitous | Every published timing on the studio pages shall state the GPU model, driver, enforced power limit and the share of time in each throttle state, and the text "our hardware, not a comparative benchmark". | unit + E2E |

### 3.5 Showcase honesty in CI
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-019-33 | Unwanted | If a registry entry has `status: done` and no web-manifest artefact names it as `producer.tool`, then CI shall fail naming the tool (FR-000-07). | contract |
| FR-019-43 | Unwanted | If a registry entry has `status: not-yet-run` while ≥ 1 web-manifest artefact names it as `producer.tool`, then CI shall fail naming the tool and the artefact (the registry must not under-report a tool that ran). | contract |
| FR-019-34 | Unwanted | If an artefact produced by a `reference-only` tool has a kind outside {image, video, point-cloud, label-set, table, metrics, text}, or the Pages artifact or the git tree contains a TensorRT engine (`*.engine`, `*.plan`, `*.trt`), a GGUF file, a CUDA, shader or extension cache, a file carrying the NVIDIA proprietary-licence header, or an `omniverse://` URL, then CI shall fail naming the file. | contract |
| FR-019-35 | Unwanted | If an image or video artefact produced by a `reference-only` tool lists no input artefact produced by PitStudio's scene-composition stage (`st40_compose`, licence class `own`), or has the kind `screenshot`, then CI shall fail naming the artefact. | contract |
| FR-019-36 | Unwanted | If a published run card or any committed file contains a numeric metric or telemetry value of a stage marked `performance: local-only`, then CI shall fail naming the file and field (FR-000-08). | contract |
| FR-019-37 | Ubiquitous | Every artefact produced by `cosmos-reason-2` shall show "Built on NVIDIA Cosmos" and the label "display-only". | unit + E2E |

### 3.6 Hostile inputs
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-019-38 | Unwanted | If the tool registry, `studio/toolmap.yaml`, the web manifest, `studio/capabilities.json` or a published run manifest or telemetry file (DC-001-01, DC-002-03) fails its schema (unknown lane, ring, status or licence class, missing field, duplicate id, edge to an unknown tool, run card above 200 KB, telemetry arrays of unequal length, non-finite numbers, absolute paths), then the build shall fail naming the file and the JSON pointer. | contract (hostile) |
| FR-019-39 | Unwanted | If the React Flow chunk fails to load (HTTP error, offline, script error), then `/studio` shall keep the static SVG and table, show "Interactive map unavailable", and raise no uncaught error. | E2E (hostile) |
| FR-019-40 | Unwanted | If a string in a manifest, run card or registry contains markup, script, control characters or more than 200 characters, then the studio pages shall render it as escaped text, truncated after 200 characters with an expander, and execute nothing. | unit + E2E (hostile) |
| FR-019-41 | Unwanted | If `?case=` or `?tool=` on `/studio/runs` holds an unknown, malformed or over-long (> 2,000 characters) value, then the ledger shall ignore it, show all runs with the note "unknown filter ignored", and request nothing derived from it. | E2E (hostile) |
| FR-019-42 | Unwanted | If `studio/capabilities.json` has no probe for a tool, or the probe's status is `fail` or `skip`, then the Identity block shall show "not probed", "probe failed" (with the scrubbed error text) or "probe skipped" respectively, and never "pass". | unit |

### 3.7 Opt-in connection to a local studio
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-019-44 | Event | When the visitor presses the "connect to my local studio" control on the `/studio` pages (a port field and a button) with a valid port, the page shall make exactly one `GET http://127.0.0.1:<port>/health` (the endpoint and CORS rules of spec 003: FR-003-06, FR-003-20) with `credentials: "omit"` and a 3 s timeout, show "connected — console <version>" only if the response is JSON whose `status` is `ok` and whose `console_version` matches `^[0-9]+\.[0-9]+\.[0-9]+$`, and otherwise (refusal, timeout, declined permission, invalid body) show "not connected", changing nothing else and making no further request until the next press. | E2E |
| FR-019-45 | Unwanted | If the port field of the "connect to my local studio" control holds anything other than a decimal integer in 1024–65535 (e.g. `abc`, `80`, `65536`, `8765/x`, `8765@host`, ` 8765`), then the control shall make no request and show an inline validation message. | unit (web, hostile) |

## 4. Correctness properties
| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-019-01 | Layout determinism: permuting the order of registry entries (and of edges) leaves every node position, keyed by tool id, unchanged. | registries of 1–40 tools, random orders | exact |
| P-019-02 | Artefact partition: every manifest artefact whose `producer.tool` is a registry id appears on exactly one tool page, and the union of the tool pages' lists equals that set. | random manifests ≤ 10³ artefacts | exact |
| P-019-03 | Honesty monotonicity: adding an artefact never makes the done-needs-artefact check fail; removing the only artefact of a `done` tool always makes it fail. | random registry × manifest pairs | exact |
| P-019-04 | Local-only leak detection: for any run card with planted values, the check of FR-019-36 reports exactly the numeric metric and telemetry fields of local-only stages (no miss, no false alarm), and its report is invariant to key order. | random run cards ≤ 200,000 bytes | exact |
| P-019-05 | Observed-edge derivation is invariant to the order and duplication of manifest artefacts. | random manifests | exact |

## 5. Non-functional requirements and success criteria
| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-019-01 | Initial JavaScript of `/studio`, the tool pages, `/studio/runs`, a run page and `/studio/gpu` (the React Flow chunk loads after hydration) (NFR-000-01) | ≤ 200 KB gzip each | `web/scripts/postbuild.mjs` |
| NFR-019-02 | Tool map interactive (nodes focusable and clickable) after load on CI Chromium | ≤ 1.5 s | Playwright performance marks |
| NFR-019-03 | Studio data: published telemetry per run ≤ 200,000 bytes (FR-002-50); the generated studio index ≤ 1,000,000 bytes; the studio showcase class within its 25 MB budget (NFR-020-03) | as stated | CI size check |
| NFR-019-04 | Accessibility of `/studio`, every tool page, `/studio/runs`, one run page and `/studio/gpu`: one instance of each template in light and dark × EN and ES, every instance in light/EN (NFR-000-02) | axe 0 serious/critical | Playwright + axe |
| NFR-019-05 | Lighthouse on `/studio`, `/studio/gpu` and one tool page | accessibility ≥ 0.95; performance warns below 0.80 | LHCI |
| NFR-019-06 | Quality of `web/src/studio/**` and `tools/check_showcase.py` | branch coverage ≥ 0.85; mutation ≥ 0.60 (`mutation.other_min`) | Vitest/pytest coverage; Stryker, mutmut |
| SC-019-01 | Definition of done: each of the 17 studio tools has ≥ 1 published artefact or an "Evaluated, not adopted" page with its reason | 17 of 17 at the release gate | honesty report in DC-019-03 |
| SC-019-02 | The deployed commit passes every showcase honesty check | 0 violations of FR-019-33 to FR-019-36 | CI on the release commit |

## 6. Data contracts
| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| ~~DC-019-01~~ | Withdrawn before approval: the run card is the published run manifest of spec 002 (FR-002-48, DC-001-01) with its published telemetry (DC-002-03). | — | — |
| DC-019-02 | Tool map source `studio/toolmap.yaml`: bands in order, tool order within each band, handoff edges (from tool, to tool, artefact kind) | `contracts/toolmap.schema.json` (new) | maintainer → build-time layout, `/studio` |
| DC-019-03 | Studio index `web/public/studio/index.json`, generated at build: per tool the resolved version and release date, probe status, layout position, artefact ids, observed edges, and the honesty-check report | `contracts/studio-index.schema.json` (new) | `web/scripts/build-studio-index.mjs` → `/studio` routes, CI |

Consumed, defined elsewhere: the web manifest and the published run manifests (DC-000-01, DC-001-01),
`studio/capabilities.json` (DC-000-02), the tool registry `studio/tools.yaml` (DC-000-04), the case registry
(DC-018-01) and the published telemetry (DC-002-03).

## 7. Edge cases and assumptions

### 7.1 Tool ids (prerendered pages)
| `toolId` | Tool | Environment | Licence class | Status at specification |
|---|---|---|---|---|
| `openusd` | OpenUSD (`usd-core`) | `studio/` | open | not-yet-run |
| `warp` | NVIDIA Warp | `studio/` | open | not-yet-run |
| `newton` | Newton | `studio/` | open | not-yet-run |
| `mujoco-warp` | MuJoCo-Warp | `studio/` | open | not-yet-run |
| `physx-ovphysx` | PhysX / ovphysx | `studio/isaac/`, `studio/rtx/` | reference-only | not-yet-run |
| `ovrtx` | ovrtx (RTX sensors) | `studio/rtx/` | reference-only | not-yet-run |
| `isaac-sim-replicator` | Isaac Sim + Replicator | `studio/isaac/` | reference-only | not-yet-run |
| `isaac-lab` | Isaac Lab | `studio/isaaclab/` | open | not-yet-run |
| `kit-usd-composer-explorer` | USD Composer / Explorer (Kit) | `studio/kit/` | reference-only | not-yet-run |
| `cosmos-reason-2` | Cosmos Reason 2 | `studio/reason/` | open weights (NVIDIA Open Model License) | not-yet-run |
| `pytorch` | PyTorch | `pipeline/` | open | not-yet-run |
| `onnx-runtime` | ONNX Runtime (+ Web) | `pipeline/`, `web/` | open | not-yet-run |
| `tensorrt` | TensorRT | `pipeline/accel/` | reference-only | not-yet-run |
| `nvenc-ffmpeg` | NVENC via FFmpeg | external binary | external (LGPL build) | not-yet-run |
| `nsight-nvml` | Nsight + NVML | runner + external | NVML bindings open; Nsight reference-only | not-yet-run |
| `threejs-r3f-3d-tiles` | three.js / R3F / 3D Tiles | `web/` | open | not-yet-run |
| `rapier-webgpu-pyodide` | Rapier / WebGPU / Pyodide | `web/` | open | not-yet-run |
| `cuopt` | NVIDIA cuOpt | — | open (Apache-2.0) | evaluated-not-adopted |
| `physicsnemo` | PhysicsNeMo | — | open | evaluated-not-adopted |
| `cosmos-predict-transfer` | Cosmos Predict / Transfer | — | open weights | evaluated-not-adopted |

Ids follow `docs/web/structure.md`; the registry (DC-000-04) fixes them in the build phase and this table changes only
with it.

### 7.2 Physical-AI loop steps
| Step | Realised by a published run containing stage | Typical tool |
|---|---|---|
| Scene | `st40_compose` | `openusd` |
| Sensors and synthetic data | `st53_sensors` or `st55_sdg` | `ovrtx`, `isaac-sim-replicator` |
| Labels | `st55_sdg` (label sets) | `isaac-sim-replicator` |
| Training | `s30_train` or `st60_il_train` | `pytorch`, `isaac-lab` |
| Validation | `s50_evaluate` | `pytorch` |
| Acceleration | `s62_accel` | `tensorrt` |
| Encoding | `st56_encode` | `nvenc-ffmpeg` |
| Web | `s60_export` | `onnx-runtime`, `threejs-r3f-3d-tiles` |

### 7.3 Other assumptions
- The memory reference line uses `gpu.vram_total_bytes` from the run card, never a constant; on the reference RTX 5000
  Ada Laptop GPU it reads 16 GB.
- The NVIDIA proprietary-licence header markers and the cache directory patterns used by FR-019-34 are fixed in task
  T-019-004 from the kit-app-template output and the documented cache locations; tests plant one file per marker.
- Studio pages make no loopback request unless the visitor presses the opt-in control (FR-019-44; FR-000-11, FR-003-25; tested by
  T-019-035).
- Telemetry charts follow the chart rules of spec 020 and decimate with its min/max-per-column method.
- No oracle here depends on an UNVERIFIED constant.

## 8. Clarifications log
- Resolved — *how many tool pages.* The plan says "17 pages"; the docs add "evaluated, not adopted" pages for cuOpt,
  PhysicsNeMo and Cosmos Predict/Transfer. The route serves 20 ids: the 17 studio tools (any of which may itself end as
  `evaluated-not-adopted`) and the three already evaluated.
- Resolved — *where map order and edges live.* `docs/web/structure.md` places "lane and order fields" in
  `studio/tools.yaml`, whose documented fields have no order or handoffs; the band order, tool order and handoff edges
  live in `studio/toolmap.yaml` (DC-019-02) so that the tool schema of spec 001 stays as documented.
- Resolved — *run card schema.* The run card is the published run manifest of spec 002 (FR-002-48, schema DC-001-01)
  with its published telemetry (DC-002-03); this spec withdrew its own run-card contract (DC-019-01) before approval.
- Resolved — *"renders show our scenes"* becomes checkable: every render by a reference-only tool must descend from an
  `st40_compose` scene (FR-019-35); the visual judgement remains a review item.
- Resolved — *throttle chip.* The telemetry summary (spec 002, FR-002-31) holds per-reason clocks-event shares and no
  union, so the chip lists the shares per reason instead of one throttle percentage.
- Resolved — *observed versus planned edges.* Declared handoffs are drawn even before any run, but marked "planned"
  until a published manifest shows them.
- Integration 2026-10-07: this spec owns "a tool marked done needs ≥ 1 artefact" (FR-019-33, CI and UI honesty, over
  spec 001's manifest field `producer.tool`); spec 001 struck its duplicate (FR-001-27), whose converse clause is now
  FR-019-43. The opt-in "connect to my local studio" control's UI moved here from spec 003 (FR-019-44, FR-019-45,
  formerly FR-003-26 and FR-003-27; task T-019-036); spec 003 keeps the endpoint, CORS and loopback rules. The 3 s
  timeout is the proposed key `console.optin_timeout_s` (pending maintainer approval).

## 9. Changes (only for features that modify earlier behaviour)
### ADDED Requirements
- (none beyond this spec; the stub page of `/studio` is replaced. No earlier requirement is modified; DC-019-01 is this
  spec's own row, withdrawn before approval)
### MODIFIED Requirements
- (none)
### REMOVED Requirements
- (none)

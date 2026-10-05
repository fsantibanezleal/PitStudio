# Web structure

> The shell that wraps every page, each route of the site and what it shows, the ⓘ architecture tabs, and what exists in
> `web/src/` today versus what the build phase adds. · Part of: [Web](README.md) · Related:
> [user flow](user-flow.md) · [showcase rules](showcase-rules.md) · [compute tiers](compute-tiers.md) ·
> [cases](../cases/README.md)

## What and why

PitStudio's web app has two jobs. It **explains and runs** the 12 open-pit cases (live engines in the browser, replays of
the studio's GPU work, theory and results), and it **showcases the studio**: one page per tool, showing only artefacts
that tool actually produced. Both jobs share one shell, one manifest format and one set of honesty rules, so a visitor
can always tell what was computed now, what was precomputed, by which tool, in which run.

The site is static (GitHub Pages, no server). That fixes three design constraints:

- every route must be prerendered HTML, so deep links work without a server rewrite;
- every computation is either in the browser ([compute tiers](compute-tiers.md)) or baked beforehand
  ([compute lanes](../pipelines/compute-lanes.md));
- the byte budget is finite: Pages caps a published site at 1 GB [1], and PitStudio caps itself at 500 MB
  ([budgets](budgets.md)).

![Route tree with lanes](../assets/diagrams/web-routes.svg)

*The shell wraps seven top-level routes; deep routes sit under `/cases` and `/studio`. Solid boxes exist today as stub
pages, dashed boxes are planned.*

## The shell

The shell is shared, app-agnostic code in `web/src/shell/`; the app supplies its configuration in
`web/src/app/config.ts` (product name, routes, links, footer, ⓘ tabs, access digest).

| Part | Code path | What it does | Status |
|---|---|---|---|
| Header | `web/src/shell/Header.tsx` | Brand mark (lucide `Mountain`) + "PitStudio", the seven nav links, GitHub link, ⓘ, language switch, theme toggle | exists |
| Footer | `web/src/shell/Footer.tsx` | Version (from `VERSION`), short commit SHA linked to the commit, build date (`SOURCE_DATE_EPOCH` when set), author, provenance list, licences, the non-affiliation note, and the gate note when the gate is on | exists |
| Access gate | `web/src/shell/AccessGate.tsx`, `web/src/shell/digest.ts` | Demo gate around every route; states on screen that it is not security ([access gate](access-gate.md)) | exists |
| ⓘ architecture modal | `web/src/shell/ArchitectureModal.tsx`, `web/src/app/architecture.tsx` | A dialog with one tab per aspect of the app and repository | exists, text only |
| Language | `web/src/shell/i18n.ts`, `web/src/locales/{en,es}/` | English default, Spanish everywhere. Priority: `?lang=` in the URL, then the stored choice (`fsl:lang` in `localStorage`), then English; the browser language is never used | exists |
| Theme | `web/src/shell/prefs.ts`, `web/src/shell/ThemeToggle.tsx`, `web/src/shell/tokens.css` | System → light → dark cycle, stored as `fsl:theme`; a boot script sets `data-theme` before first paint | exists |
| Page stub | `web/src/shell/PageStub.tsx` | A planned section with no content says "Not built yet" and shows no invented result | exists (used by every route today) |
| Not found / error | `web/src/shell/NotFound.tsx`, `ErrorBoundary` in `web/src/root.tsx` | 404 page and a generic error view inside the same frame | exists |

The footer's non-affiliation note reads, today: "Educational research project. Not affiliated with or endorsed by
NVIDIA or any mining company. This site collects no user data beyond GitHub Pages' own server logs."

Accessibility is part of the shell, not of each page: a skip link to `#main`, labelled navigation, keyboard-reachable
dialogs, and the target WCAG 2.2 AA with axe at 0 serious/critical findings and Lighthouse accessibility ≥ 0.95
(`specs/000-foundation/spec.md`, NFR-000-02).

## Routes

| Route | Content | Lanes shown | Status today |
|---|---|---|---|
| `/` **Explore** | 3D pit from real terrain (Bingham LOD-0 ≤ 2 MB), case rail (12 cases in 5 categories), layers, a shared timeline (paused by default), KPIs, tier badge, provenance | LIVE, REPLAY | stub (`src/routes/explore.tsx`) |
| `/cases` | Case catalogue, generated coverage matrix (methods × cases) and tool matrix (tools × cases) | STATIC | stub (`src/routes/cases.tsx`) |
| `/cases/:id` | One page per case (A1–E2) with sub-tabs **Scene · Simulate (live) · Studio replay · Charts · Context** and a "reproduce this" command | LIVE, REPLAY, STATIC | planned |
| `/studio` | **Interactive tool map**: nodes = tools (colour = lane, badge = ring, icon = licence class), edges = file handoffs (USD → physics → sensors/SDG → train → accelerate → encode → web). Below it, the physical-AI loop tied to real run manifests | STATIC, REPLAY | stub (`src/routes/studio.tsx`) |
| `/studio/tools/:toolId` | 17 tool pages (template below) | LIVE, REPLAY, STATIC | planned |
| `/studio/runs`, `/studio/runs/:runId` | Ledger of **published** runs: manifest viewer, telemetry chart (open-runtime stages), stage DAG with cache hits, determinism check | REPLAY | planned |
| `/studio/gpu` | **GPU evidence**: per-stage timelines (busy %, VRAM against 16 GB, power against the enforced limit, SM clock, throttle reasons) for open-runtime stages, plus a "how measured" popover | REPLAY, LOCAL-ONLY | planned |
| `/theory` | MDX + KaTeX per phenomenon with interactive figures | LIVE, STATIC | stub (`src/routes/theory.tsx`) |
| `/methods` | The method ladder M1–M23 (classical → SOTA → beyond-SOTA) | STATIC, LIVE | stub (`src/routes/methods.tsx`) |
| `/results` | Learned vs classical on held-out data with confidence intervals, sim-to-real and sim-to-sim gaps, parity, DR ablation, Isaac Lab vs baselines, Cosmos vs Qwen vs detector, and an **Acceleration** tab (PyTorch / ORT CPU / ORT CUDA / TensorRT fp32·fp16·int8·fp8 for our models, with per-engine parity) | REPLAY, LOCAL-ONLY | stub (`src/routes/results.tsx`) |
| `/knowledge` | Glossary EN/ES, equation explorer, parameter browser, datasets, frameworks, bibliography — generated from `minephys` at build time ([knowledge](../knowledge/README.md)) | STATIC, LIVE | stub (`src/routes/knowledge.tsx`) |
| `*` | Not-found page | — | exists (`src/routes/not-found.tsx`) |

Lane badges mean: **LIVE** computed now in this browser; **REPLAY** precomputed by a named tool in a named run;
**STATIC** a figure or table; **LOCAL-ONLY** performance figures that a licence forbids publishing, shown as a card that
says so ([showcase rules](showcase-rules.md)).

### `/cases/:id` sub-tabs

| Sub-tab | Content | Typical lane |
|---|---|---|
| Scene | The case's 3D scene (glTF / 3D Tiles), layers and camera presets | STATIC + REPLAY |
| Simulate (live) | The case's live engine on the active tier: e.g. the A1 DES with dispatch rules, the C1 limit-equilibrium and inverse-velocity models | LIVE (fallback REPLAY) |
| Studio replay | The studio's GPU outputs for the case: physics replays, RTX renders, sensor clouds, Isaac Lab rollouts | REPLAY |
| Charts | KPIs with confidence intervals and the pre-registered decision rule ("no significant difference" when the paired 95 % CI includes 0) | REPLAY + LIVE |
| Context | Why the case matters, data sources and licences, validity range, links to theory, methods and dataset cards | STATIC |

The first two case pages built are **A1** (truck–shovel dispatch) and **C1** (slope monitoring → time of failure), on
the open lane only, as the end-to-end vertical slice before any NVIDIA-runtime work.

### The `/studio` subtree

The tool map is a React Flow (`@xyflow/react` 12.12.0, MIT) graph loaded only on this route; the package is about
1.2 MB unpacked [2]. Node positions are precomputed at build time from lane and order fields of the tool registry
`studio/tools.yaml`, because the usual auto-layout library `elkjs` is EPL-2.0 OR GPL-3.0-or-later [3]. A plain SVG and a
data table render the same graph for no-JS visitors and screen readers.

**The 17 tool pages.** One page per studio tool, matching the [frameworks](../frameworks/README.md) pages one to one.
The `toolId` values below are the planned ids; the registry fixes them in the build phase.

| `toolId` (planned) | Tool | Environment | Licence class | Framework page |
|---|---|---|---|---|
| `openusd` | OpenUSD (`usd-core`) | `studio/` | open (TOST-1.0) | [openusd](../frameworks/openusd.md) |
| `warp` | NVIDIA Warp | `studio/` | open (Apache-2.0) | [warp](../frameworks/warp.md) |
| `newton` | Newton | `studio/` | open (Apache-2.0) | [newton](../frameworks/newton.md) |
| `mujoco-warp` | MuJoCo-Warp | `studio/` (via `newton[sim]`) | open (Apache-2.0) | [mujoco-warp](../frameworks/mujoco-warp.md) |
| `physx-ovphysx` | PhysX / ovphysx | `studio/isaac/`, `studio/rtx/` | reference-only | [physx-ovphysx](../frameworks/physx-ovphysx.md) |
| `ovrtx` | ovrtx (RTX sensors) | `studio/rtx/` | reference-only | [ovrtx](../frameworks/ovrtx.md) |
| `isaac-sim-replicator` | Isaac Sim + Replicator | `studio/isaac/` | reference-only | [isaac-sim-replicator](../frameworks/isaac-sim-replicator.md) |
| `isaac-lab` | Isaac Lab | `studio/isaaclab/` | open (BSD-3-Clause) | [isaac-lab](../frameworks/isaac-lab.md) |
| `kit-usd-composer-explorer` | USD Composer / Explorer (Kit) | `studio/kit/` (our extension) | reference-only | [kit-usd-composer-explorer](../frameworks/kit-usd-composer-explorer.md) |
| `cosmos-reason-2` | Cosmos Reason 2 | `studio/reason/` | open weights, NVIDIA Open Model License | [cosmos-reason-2](../frameworks/cosmos-reason-2.md) |
| `pytorch` | PyTorch | `pipeline/` | open | [pytorch](../frameworks/pytorch.md) |
| `onnx-runtime` | ONNX Runtime (+ Web) | `pipeline/`, `web/` | open (MIT) | [onnx-runtime](../frameworks/onnx-runtime.md) |
| `tensorrt` | TensorRT | `pipeline/accel/` | reference-only | [tensorrt](../frameworks/tensorrt.md) |
| `nvenc-ffmpeg` | NVENC via FFmpeg | external binary | external (LGPL build) | [nvenc-ffmpeg](../frameworks/nvenc-ffmpeg.md) |
| `nsight-nvml` | Nsight + NVML | runner + external | NVML bindings open; Nsight reference-only | [nsight-nvml](../frameworks/nsight-nvml.md) |
| `threejs-r3f-3d-tiles` | three.js / R3F / 3D Tiles | `web/` | open | [threejs-r3f-3d-tiles](../frameworks/threejs-r3f-3d-tiles.md) |
| `rapier-webgpu-pyodide` | Rapier / WebGPU / Pyodide | `web/` | open | [rapier-webgpu-pyodide](../frameworks/rapier-webgpu-pyodide.md) |

**Tool page template.** Every tool page has the same eight blocks, in this order:

1. **Identity** — version read from the lock file (never hand-typed), release date, licence and licence class, ring,
   environment, and the NVIDIA trademark notice where relevant.
2. **Role in mining** — what the tool does in PitStudio and which cases use it (from the tool matrix).
3. **Artefacts it produced** — filtered from the web manifest by `producer.tool`, each with its LIVE / REPLAY / STATIC
   badge. A tool with nothing published shows **"not yet run"**; a tool that was tried and dropped shows **"evaluated,
   not adopted"** with the reason.
4. **Provenance chips** — run id, recipe hash, git SHA, GPU model, driver, wall time, peak VRAM, energy, throttle %.
   Performance chips are omitted for tools whose licence forbids publishing performance data.
5. **Where it ran** — "live in your browser" or "precomputed on an RTX 5000 Ada Laptop GPU (16 GB, power-limited) on
   <date>".
6. **Limits and failures** — what did not work, with numbers where they exist.
7. **Reproduce** — the runner command and its requirements (for example "needs an RTX GPU and acceptance of the NVIDIA
   terms").
8. **Alternatives rejected** — with the reason.

**`/studio/runs`** lists only runs published with `studio publish`; local runs never appear. A run page shows the
manifest, a telemetry chart downsampled for the web, the stage DAG with cache hits, the artefacts and the determinism
class with its re-run check.

**`/studio/gpu`** shows NVML timelines for stages that run open runtimes (Warp, Newton, PyTorch, ORT, regular
TensorRT for our models). Stages that run Isaac Sim, Kit, Replicator, ovrtx or TensorRT for RTX appear with their
**outputs** and a "performance local-only (licence)" note instead of numbers; see [showcase rules](showcase-rules.md).

### The ⓘ modal

The ⓘ button opens the architecture view. Its tabs are configured in `web/src/app/config.ts` and today each renders one
paragraph of text from `web/src/locales/{en,es}/app.json`. The build phase adds a diagram per tab from
`docs/assets/diagrams/`, inlined so that it follows the app's theme switch.

| Tab id | Title | Content |
|---|---|---|
| `what` | What it is | The product in one paragraph: studio → scenes, physics, sensors, synthetic data, models → this site |
| `lanes` | Lanes | Live (in the browser, WebGPU → WebAssembly → precomputed), precompute (local GPU), replay (committed outputs) |
| `studio` | Studio | Isolated environments, one runner with GPU telemetry and a manifest per output; local-only, never called by the site |
| `webflow` | Web flow | Static Pages site, prerendered routes, lazy assets verified against the published manifest |
| `science` | Science flow | Download → synthesize → simulate → features → train → evaluate on held-out data → export, each number traced to a manifest |
| `contracts` | Contracts | JSON Schemas in `contracts/` for every artefact that crosses a boundary |
| `tools` | Tools | Open tools cited; proprietary SDKs installed by the user, never redistributed; restricted performance figures not published |

### Data the routes read

| File (planned unless marked) | Producer | Read by |
|---|---|---|
| `web/public/assets/manifest.json` | the export stage and `studio publish` | every artefact card; SHA-256 checked at build |
| `studio/capabilities.json` | `studio/bench/run_bench.py` (exists; not yet run on the reference machine) | `/studio`, tool pages |
| `studio/tools.yaml` | the maintainer, validated by `contracts/tools.schema.json` | the tool map and the 17 tool pages |
| per-run manifests and telemetry summaries | the runner, via `studio publish` | `/studio/runs`, `/studio/gpu` |

## Prerendering and deep links

`web/react-router.config.ts` sets `ssr: false` and prerenders every static path; `web/scripts/postbuild.mjs` then moves
the prerendered tree to the artifact root and turns the SPA fallback into `404.html`, which Pages serves for unknown
URLs. The router `basename` and the Vite `base` both come from `BASE_PATH` (`/PitStudio/` on Pages, `/` locally).

The e2e suite checks today that each of the seven top-level routes is a prerendered page with HTTP 200 and that an
unknown URL returns 404 with the app's not-found page (`web/e2e/shell.spec.ts`). Dynamic routes are not prerendered by
default; so that `/cases/A1/` or `/studio/tools/warp/` also return 200, the build phase enumerates the known ids (12
cases, 17 tools, published runs) for prerendering, and unknown ids fall back to `404.html`.

## What exists today versus planned

| Area | In `web/src/` today | Added in the build phase |
|---|---|---|
| Shell | complete: header, footer, gate, ⓘ (text), i18n, theme, not-found, error view | ⓘ diagrams, tier badge in the header, "connect to my local studio" opt-in |
| Routes | seven stubs + not-found | `/cases/:id`, `/studio/tools/:toolId`, `/studio/runs(/:runId)`, `/studio/gpu`, and real content in every stub |
| Engines | none | TS workers, WGSL kernels, ORT-web, Rapier, Pyodide ([compute tiers](compute-tiers.md)) |
| Assets | `public/favicon.svg` | tiles, glb, shards, ONNX, videos, splats, studio JSON ([budgets](budgets.md)) |
| Tests | Vitest unit tests for digest, gate and prefs; Playwright e2e for deep links, 404, gate, theme, language, ⓘ, axe | parity, hostile suite per engine, budgets, showcase rules, both themes and languages per route |

## Assumptions and limits

- The site is a **simulation-grade twin, not a live digital twin**: nothing on it is fed by a real operation.
- Slope, tailings and blasting outputs are **educational, not design or regulatory** results; every case page states
  its validity range.
- Third-party names (NVIDIA, Isaac, Omniverse, Cosmos, TensorRT) are used nominatively; PitStudio is not affiliated
  with or endorsed by NVIDIA, and the site shows renders of PitStudio's own scenes, never NVIDIA application UI.
- The console of the local studio is a separate web entry that is never part of the Pages artifact, and the public
  site never contacts `localhost` unless the visitor presses the opt-in button (Chrome's Local Network Access applies
  to any public-to-loopback request [4]).

## In PitStudio

- Specs: `018-web-cases` (Explore, cases, engines, tiers, parity), `019-web-studio` (tool map, tool pages, runs, GPU
  evidence, honesty rules), `020-web-knowledge` (theory, methods, results, knowledge) — children of
  `specs/000-foundation/spec.md`.
- Decisions: [DEC-0003 loopback console](../architecture/decisions/DEC-0003-loopback-console.md),
  [DEC-0005 performance-data licence rule](../architecture/decisions/DEC-0005-performance-data-licence-rule.md),
  [DEC-0006 3D and simulation on static web](../architecture/decisions/DEC-0006-3d-and-simulation-on-static-web.md).
- Status: shell done; routes are stubs; all routes and engines land in the build phase, the vertical slice (A1 + C1)
  first; all studio pages read "not yet run" until the data-and-models phase publishes artefacts.

## References

1. GitHub Docs, "GitHub Pages limits" (accessed 2026-10-02/03). https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
2. npm registry, `@xyflow/react` latest — 12.12.0, MIT, 1,216,196 bytes unpacked. https://registry.npmjs.org/@xyflow/react/latest
3. npm registry, `elkjs` latest — 0.12.0, EPL-2.0 OR GPL-3.0-or-later. https://registry.npmjs.org/elkjs/latest
4. Chrome for Developers, "Local Network Access" (2025–2026). https://developer.chrome.com/blog/local-network-access

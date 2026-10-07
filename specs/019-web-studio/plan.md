# Plan 019 — Web studio: tool map, tool pages, published runs, GPU evidence and showcase honesty
Spec: ./spec.md

## Summary
A build script joins the tool registry, the tool map source, the locks, the capability report, the case registry and
the web manifest into one studio index (DC-019-03) with precomputed layout, resolved versions, per-tool artefact lists,
observed edges and an honesty report (FR-019-01…07, FR-019-09…10, FR-019-33…36). Route modules render the map (React
Flow loaded lazily, static SVG and table prerendered), 20 tool pages, the runs ledger and run pages from the published
run manifests and telemetry of spec 002 (FR-002-48, DC-002-03), and the GPU evidence page with charts from spec 020 (FR-019-08…32). A Python check
(`tools/check_showcase.py`) enforces the honesty rules in CI, and schema validation rejects hostile inputs at build
(FR-019-37…42).

## Technical context
Runtime: Node 24, React 19.3, React Router 8.4 (prerender, dynamic ids enumerated from the index), Vite 8.3, Vitest 5,
Playwright 1.63 with axe, LHCI. Planned web dependency `@xyflow/react` 12.12 (MIT), resolved and locked in
`web/pnpm-lock.yaml` by T-019-010. Lock parsing for versions: `tomllib` for `uv.lock` files and a YAML reader for
`web/pnpm-lock.yaml` (root Python 3.14 environment, `jsonschema` and PyYAML already locked). Target: GitHub Pages; CI on
a hosted Linux runner; no GPU is needed by any test of this spec.

## Constitution check
| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | Pass | Pages show only artefacts of published runs; empty tools say "Not yet run" (FR-019-13) |
| Spec before code | Pass | Every behaviour has an ID |
| Acceptance-test-first | Pass | Every task in tasks.md is a `[red]`/`[green]` pair |
| Independent oracles | Pass | Hand-built registries, manifests and run cards with known expected pages; versions from the lock files themselves; layout determinism by byte equality |
| Determinism & explicit tolerances | Pass | Layout and index generation are byte-deterministic (FR-019-02, P-019-01) |
| Neutral contracts | Pass | DC-019-02 and DC-019-03 JSON Schema 2020-12 with generated types; run cards are spec 002's published manifests and telemetry |
| Static delivery | Pass | All studio pages are prerendered; the map has a no-JS fallback (FR-019-04) |
| Honesty | Pass | FR-019-13…15, FR-019-30, FR-019-33…37, FR-019-43, FR-019-44 |
| Licence hygiene | Pass | Outputs only for proprietary tools; file guards (FR-019-34); local-only performance (FR-019-30, FR-019-36) |
| Simplicity | Pass | React Flow used directly; no runtime layout engine (elkjs is EPL-2.0 OR GPL-3.0-or-later) |

## Design
Data flow: [tool-map.svg](../../docs/assets/diagrams/tool-map.svg) and
[manifest-contract.svg](../../docs/assets/diagrams/manifest-contract.svg) — the index build reads `studio/tools.yaml` + `studio/toolmap.yaml` + locks + `studio/capabilities.json` + `studio/cases.yaml` +
`web/public/assets/manifest.json` + run cards and writes `web/public/studio/index.json`.

| Component (planned path) | Responsibility | Requirements |
|---|---|---|
| `contracts/toolmap.schema.json`, `contracts/studio-index.schema.json` (run cards: published run manifests and telemetry of spec 002) | Contracts and generated types; validation of consumed files | DC-019-02, DC-019-03, FR-019-38 |
| `web/scripts/build-studio-index.mjs` (+ `tools/resolve_versions.py`) | Join, layout, versions, observed edges, honesty report | FR-019-01, FR-019-02, FR-019-06, FR-019-09, FR-019-10, P-019-01, P-019-02, P-019-05 |
| `tools/check_showcase.py` | CI honesty rules and file guards | FR-019-33…36, FR-019-43, P-019-03, P-019-04 |
| `web/src/studio/connect.ts`, `web/src/studio/ConnectControl.tsx` | The opt-in "connect to my local studio" control (port validation, one `GET /health`, labels) | FR-019-44, FR-019-45 |
| `web/src/routes/studio.tsx`, `web/src/studio/ToolMap.tsx` (lazy), `web/src/studio/StaticMap.tsx`, `web/src/studio/Loop.tsx` | Map, fallback, loop | FR-019-01, FR-019-03…07, FR-019-39 |
| `web/src/routes/studio-tool.tsx`, `web/src/studio/blocks/*.tsx` | The eight blocks | FR-019-08…20, FR-019-37, FR-019-40, FR-019-42 |
| `web/src/routes/studio-runs.tsx`, `web/src/routes/studio-run.tsx`, `web/src/studio/ManifestTree.tsx`, `web/src/studio/StageDag.tsx` | Ledger, run page, manifest viewer, DAG, determinism | FR-019-21…26, FR-019-41 |
| `web/src/routes/studio-gpu.tsx`, `web/src/studio/telemetry/*.tsx` | Timelines (charts of spec 020), "How measured", local-only cards, conditions | FR-019-27…32 |

## Test strategy
| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-019-01, FR-019-04, FR-019-05 | unit + E2E | hand: a fixture registry and toolmap with known lanes, rings, classes, edges; expected node names and table rows | Vitest, Playwright |
| FR-019-02, P-019-01 | unit + property | analytical: byte equality of layouts under permutation | Vitest + fast-check |
| FR-019-03 | E2E | hand: request log on every other route contains no React Flow chunk | Playwright |
| FR-019-06, P-019-05 | unit + property | hand: fixture manifests with and without an A → B input chain | Vitest + fast-check |
| FR-019-07 | unit + E2E | hand: fixture runs containing the stages of spec §7.2 | Vitest, Playwright |
| FR-019-08, FR-019-20 | E2E | hand: the 20 ids of spec §7.1 → 200 in block order; other spellings and traversals → 404 | Playwright |
| FR-019-09, FR-019-10 | contract + E2E | reference: the versions written in the committed lock files; hand: a registry with a mismatched version | pytest, Playwright |
| FR-019-11, FR-019-12, P-019-02 | unit + property | hand: fixture case registry and manifest; analytical partition relation | Vitest + fast-check |
| FR-019-13, FR-019-14 | unit + E2E | hand: empty manifest; a tool with `evaluated-not-adopted` and a reason | Vitest, Playwright |
| FR-019-15, FR-019-16 | unit + E2E | hand: one public and one local-only stage with known telemetry | Vitest, Playwright |
| FR-019-17, FR-019-18, FR-019-19 | unit | hand: registry entries and a manifest with a rejected TensorRT variant | Vitest |
| FR-019-21, FR-019-22, FR-019-26 | unit + E2E | hand: two published run cards and one unpublished run id | Vitest, Playwright |
| FR-019-23 | unit + E2E | hand: a 200 KB run card; tree keys of the WAI-ARIA pattern; render time bound | Vitest, Playwright |
| FR-019-24, FR-019-25 | unit | hand: run cards with hits, misses, retries, each determinism class and a pending check | Vitest |
| FR-019-27, FR-019-28, FR-019-29 | unit + E2E | hand: telemetry series with known values; reference lines at `vram_total_bytes` and `power_limit_enforced_w` | Vitest, Playwright |
| FR-019-30, FR-019-36, P-019-04 | unit + contract + property | hand: run card with an Isaac Sim stage; a committed file with a planted local-only metric; analytical: detection is exact on planted fields | Vitest, pytest + Hypothesis |
| FR-019-31 | unit | hand: null and missing telemetry fields | Vitest |
| FR-019-32 | unit + E2E | hand: a timing card with known conditions | Vitest, Playwright |
| FR-019-33, P-019-03 | contract + property | hand: a `done` tool with and without artefacts; analytical monotonicity | pytest + Hypothesis |
| FR-019-43 | contract | hand: a `not-yet-run` tool with and without an artefact naming it | pytest |
| FR-019-44 | E2E | the real console (fixture store) and a stub server that answers HTML, an oversized body, a wrong `status`, or never answers; expected label and request count | Playwright |
| FR-019-45 | unit (web, hostile) | table of hostile port strings → `validatePort` rejects, `fetch` spy never called | Vitest (`web/src/studio/connect.test.ts`) |
| FR-019-34, FR-019-35 | contract | hand: planted `*.engine`, `*.plan`, `*.gguf`, cache folder, header marker, `omniverse://` URL; a render without an `st40_compose` input; a `screenshot` kind | pytest |
| FR-019-37 | unit + E2E | hand: a Cosmos artefact card | Vitest, Playwright |
| FR-019-38 | contract (hostile) | hand: one malformed file per failure class | pytest |
| FR-019-39, FR-019-41 | E2E (hostile) | hand: aborted React Flow chunk; filters `?case=zz`, `?tool=<script>`, 20,000 characters | Playwright |
| FR-019-40 | unit + E2E (hostile) | hand: strings with markup, `<script>`, control characters and 20,000 characters | Vitest, Playwright |
| FR-019-42 | unit | hand: a capability report without the tool's probe, with `fail` and with `skip` | Vitest |
| NFR-019-01, NFR-019-03 | build | hand: byte sums against the budgets | postbuild, size check |
| NFR-019-02 | E2E | hand: 1.5 s bound | Playwright |
| NFR-019-04, NFR-019-05 | E2E | WCAG rules as encoded by axe-core; Lighthouse scores | Playwright + axe, LHCI |
| NFR-019-06 | build | `thresholds.yaml` `coverage`, `mutation.other_min` | coverage, Stryker, mutmut |
| SC-019-01, SC-019-02 | gate | honesty report of the release commit | CI |

## Risks and complexity tracking
| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| A separate `studio/toolmap.yaml` | Order and handoffs are not fields of the documented tool registry | Extending the tool schema would change spec 001's documented contract |
| Versions resolved from lock files at build | The plan forbids hand-typed versions | Reading versions at run time would need the locks in the Pages artifact |
| Risk: React Flow grows the `/studio` first view | The map is the route's main view | Lazy chunk after hydration; static SVG first (FR-019-03, FR-019-04) |
| Risk: header-marker guard false positives on docs quoting a licence | The guard must catch copied template code | Markers are matched on source and asset files, not on `docs/` prose; tests include a docs quote that must pass |

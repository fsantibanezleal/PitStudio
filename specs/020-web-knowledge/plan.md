# Plan 020 — Web knowledge: theory, methods, results, knowledge base, interactive figures and site-wide quality
Spec: ./spec.md

## Summary
Four route families render build-time content: theory MDX with KaTeX and figures (FR-020-01…06), the method ladder from
`studio/methods.yaml` (FR-020-17…19), results bundles with the decision-rule display (FR-020-20…31) and a knowledge
bundle generated from the pinned `minephys` (FR-020-32…42). One chart component in `web/src/charts/` implements the
interactive-figure rules for the whole site (FR-020-07…16) and is reused by specs 018 and 019. The ⓘ modal gains themed
diagrams (FR-020-43, FR-020-44). Site-wide checks cover locales, contrast, ES completeness, hostile URLs, budgets, axe
and Lighthouse (FR-020-45…48, NFR-020-01…09).

## Technical context
Runtime: Node 24, React 19.3, React Router 8.4 (prerender), Vite 8.3, Vitest 5, Playwright 1.63 with axe, LHCI. Planned
web dependencies, resolved and locked in `web/pnpm-lock.yaml` by the first task that needs them: `@mdx-js/rollup`,
`remark-math`, `rehype-katex` with `katex` (build time only), one canvas chart library of the plan's kit (uPlot or
ECharts, chosen by the first figure task against FR-020-07…15), fast-check, Stryker. Python 3.14 root environment for
`tools/build_knowledge.py` (pinned `minephys`, PyYAML, jsonschema; `bibtexparser` added and locked before T-020-004);
SciPy added to the pipeline lock as the reference for the teaching functions. Target: GitHub Pages; CI on a hosted Linux
runner.

## Constitution check
| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | Pass | Results show only published bundles; empty slots say "Not yet run" (FR-020-31) |
| Spec before code | Pass | Every behaviour has an ID |
| Acceptance-test-first | Pass | Every task in tasks.md is a `[red]`/`[green]` pair |
| Independent oracles | Pass | Analytical solutions (Ritter, Beverloo, inverse-square law, Φ), SciPy reference values, the WCAG luminance formula, hand-written expected tables from the docs; never the code under test |
| Determinism & explicit tolerances | Pass | Generation byte-identical (FR-020-40, P-020-31); tolerances justified in spec §7.2 |
| Neutral contracts | Pass | DC-020-01…04 JSON Schema 2020-12 with generated types |
| Static delivery | Pass | Everything is prerendered; equations rendered at build (NFR-020-04) |
| Honesty | Pass | Decision rule (FR-020-22, FR-020-23), UNVERIFIED badges (FR-020-33, FR-020-42), licence rules (FR-020-29, FR-020-30), synthetic labels (FR-020-25) |
| Licence hygiene | Pass | Bibliography cites, never copies; no paywalled text reproduced |
| Simplicity | Pass | One chart stack for the site; MDX and KaTeX used directly |

## Design
Data flow: routes in [web-routes.svg](../../docs/assets/diagrams/web-routes.svg); the knowledge bundle is generated from
the pinned `minephys` tables as described in `docs/knowledge/README.md` (tables → `tools/build_knowledge.py` → bundle
and generated docs pages → `/knowledge`, theory symbol tables, equation explorer).

| Component (planned path) | Responsibility | Requirements |
|---|---|---|
| `web/src/routes/theory.tsx`, `web/src/routes/theory-topic.tsx`, `web/src/content/theory/{en,es}/*.mdx` | Index and 13 pages, KaTeX at build, symbol tables, references | FR-020-01…06, FR-020-47 |
| `tools/check_theory.py` | Equation drift against `docs/theory/`, ES/EN id parity, raster-chart guard | FR-020-02, FR-020-03, FR-020-16, FR-020-47 |
| `web/src/charts/` (`Chart.tsx`, `decimate.ts`, `viewTransform.ts`, `colormaps.ts`, `DataTable.tsx`) | The interactive-chart rules for the whole site | FR-020-07…15, P-020-04…09 |
| `web/src/theory/figures.yaml`, `web/src/theory/Figure.tsx`, `tools/check_figures.py` | Figure registry, controls, markers, rubric checks | FR-020-06, FR-020-08…10, FR-020-13, FR-020-14, DC-020-04 |
| `web/src/theory/fn/` | Teaching functions | FR-020-49, FR-020-50, P-020-10…30 |
| `web/src/routes/methods.tsx`, `web/src/routes/method.tsx`, `studio/methods.yaml` | Method index and pages | FR-020-17…19, DC-020-01 |
| `web/src/routes/results.tsx`, `web/src/results/` (`verdict.ts`, `tabs/*.tsx`), `tools/check_results.py` | Tabs, rows, verdicts, criteria, licence rules | FR-020-20…31, P-020-01…03, DC-020-02 |
| `tools/build_knowledge.py`, `web/src/routes/knowledge.tsx`, `web/src/knowledge/` (`search.ts`, sections) | Bundle generation, drift check, sections, search | FR-020-32…42, P-020-31, P-020-32, DC-020-03 |
| `web/src/shell/ArchitectureModal.tsx`, `web/src/app/architecture.tsx`, `tools/check_inline_svg.py` | Tabs with inlined themed SVG; diagram guard | FR-020-43, FR-020-44, FR-020-51 |
| `web/src/locales/`, `web/biome.json` rule, `tools/check_locales.mjs` | Key parity, no JSX text literals | FR-020-45 |
| `web/src/shell/tokens.css`, `web/src/shell/contrast.test.ts` | Contrast of every text token on every surface | FR-020-46 |
| `web/scripts/budgets.mjs`, `web/scripts/postbuild.mjs` | Per-route initial JS, per-class budgets | NFR-020-01, NFR-020-03, NFR-020-04 |

## Test strategy
| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-020-01, FR-020-17 | E2E | hand: the 13 file stems of `docs/theory/` and the 23 of `docs/methods/`; unknown ids → 404 | Playwright |
| FR-020-02, FR-020-47 | contract | hand: display equations extracted from `docs/theory/*.md`; label sets per language | pytest |
| FR-020-03 | contract | hand: a planted malformed equation fails the build | pytest |
| FR-020-04 | E2E | hand: a `math` element per equation, anchors and symbol tables present | Playwright |
| FR-020-05 | contract + E2E | hand: reference lists of the docs pages; UNVERIFIED markers of the docs pages | pytest, Playwright |
| FR-020-06, FR-020-08 | unit + E2E | hand: the figure table of spec §7.1; marker value equals read-out text | Vitest, Playwright |
| FR-020-07, FR-020-11, FR-020-12 | E2E | hand: expected read-out for a synthetic series at known cursor positions; key bindings; computed colours change with theme | Playwright |
| FR-020-09, FR-020-10, FR-020-16 | contract | hand: one mutated figure registry per rule; a planted raster chart | pytest |
| FR-020-13 | E2E | analytical: digests of two settings differ for every control | Playwright |
| FR-020-14, FR-020-48 | E2E (hostile) | hand: hostile values (empty, `abc`, `NaN`, `1e309`, `-1`, markup, 20,000 characters) | Playwright |
| FR-020-15 | unit + E2E | analytical (decimation properties); hand: context count ≤ 8 | Vitest, Playwright |
| FR-020-18 | unit + E2E | hand: registry entry of M02 and its expected page blocks | Vitest, Playwright |
| FR-020-19 | contract | hand: one mutated registry per failure class | pytest |
| FR-020-20, FR-020-21 | unit + E2E | hand: a fixture results bundle with known rows | Vitest, Playwright |
| FR-020-22 | unit | hand: truth table of intervals (lo > 0, hi < 0, straddling, touching 0 at either end, n = 1, McNemar p and directions) | Vitest |
| FR-020-23 | contract | hand: bundles with a wrong stored verdict, non-finite bound, lo > hi, n = 1 paired, no orientation | pytest |
| FR-020-24, FR-020-31 | unit + E2E | hand: the criteria of plan §7 as recorded in DC-020-01; bundles that pass, fail and are missing | Vitest, Playwright |
| FR-020-25, FR-020-26, FR-020-27, FR-020-28 | unit + E2E | hand: fixture bundles and a fixture parity report with known values | Vitest, Playwright |
| FR-020-29 | contract | hand: bundles containing restricted-software performance rows | pytest |
| FR-020-30 | unit | hand: the reviewed TensorRT licence SHA-256 versus a changed one | Vitest |
| FR-020-32, FR-020-36, FR-020-37, FR-020-38 | contract + E2E | hand: small fixture tables, `sources.yaml`, `tools.yaml` and `.bib` with known rows | pytest, Playwright |
| FR-020-33, FR-020-34, FR-020-35 | unit + E2E | hand: fixture rows incl. UNVERIFIED ones; glossary pairs with accents | Vitest, Playwright |
| FR-020-39 | contract (hostile) | hand: one malformed input per failure class | pytest |
| FR-020-40 | contract | analytical (byte equality of two generations); hand: an edited generated page fails | pytest |
| FR-020-41 | unit + E2E (hostile) | hand: queries `<b>`, `.*`, `(`, `‮`, 20,000 characters | Vitest, Playwright |
| FR-020-42 | unit + E2E | hand: a KPI with a `knowledge:` input marked UNVERIFIED | Vitest, Playwright |
| FR-020-43, FR-020-44 | E2E | hand: seven tab names; computed SVG colours change with theme; focus order | Playwright |
| FR-020-51 | contract (hostile) | hand: planted missing file, malformed SVG, `fill="#123456"` outside the token block, `<script>`, `onload=`, `href="https://…"`; an unmodified docs diagram (tokens only) must pass | pytest |
| FR-020-45 | contract + lint | hand: a planted missing key and a planted JSX literal | Node script, Biome |
| FR-020-46 | unit | published formula: WCAG 2.2 relative luminance and contrast ratio, applied to the token values | Vitest |
| FR-020-49 | unit + parity | analytical forms and hand cases (Ritter h(0, t) = 4h₀/9; Beverloo at D = k d; McNemar b = 10, c = 0 → p = 2⁻⁹ = 0.001953125; Φ(0) = 0.5); reference implementation: SciPy (`scipy.special.ndtr`, `scipy.stats.t.ppf`, `scipy.stats.binomtest`) | Vitest |
| FR-020-50 | unit (hostile) | hand: one out-of-domain argument per function | Vitest |
| P-020-01, P-020-02, P-020-03 | property | analytical (relations of the decision rule) | Vitest + fast-check |
| P-020-04, P-020-05, P-020-06 | property | analytical (min/max decimation) | Vitest + fast-check |
| P-020-07, P-020-08, P-020-09 | property | analytical (affine and log view transforms) | Vitest + fast-check |
| P-020-10, P-020-11, P-020-12 | metamorphic | analytical (Beverloo law, $W = C\rho_b\sqrt g (D - kd)^{5/2}$) | Vitest + fast-check |
| P-020-13, P-020-14, P-020-15 | metamorphic | analytical (Ritter solution; its integral equals h₀ L) | Vitest + fast-check |
| P-020-16, P-020-17, P-020-18 | metamorphic | analytical (lidar range equation with two-way Beer–Lambert transmittance) | Vitest + fast-check |
| P-020-19, P-020-20, P-020-21 | metamorphic | analytical (PPO clipped objective) | Vitest + fast-check |
| P-020-22, P-020-23, P-020-24 | metamorphic | analytical (exact binomial McNemar test) | Vitest + fast-check |
| P-020-25, P-020-26, P-020-27 | metamorphic | analytical (AUC = Φ(Δμ / (σ√2)) for equal-variance normals) | Vitest + fast-check |
| P-020-28, P-020-29, P-020-30 | metamorphic | analytical (paired-t interval) | Vitest + fast-check |
| P-020-31 | property | analytical (byte equality) | pytest + Hypothesis |
| P-020-32 | property | analytical (normalisation and literal substring matching) | Vitest + fast-check |
| NFR-020-01, NFR-020-03, NFR-020-04 | build | hand: byte sums against the budgets | budget script, postbuild |
| NFR-020-02, NFR-020-07, NFR-020-08 | E2E | hand: thresholds | Playwright + CDP |
| NFR-020-05, NFR-020-06 | E2E | WCAG rules as encoded by axe-core; Lighthouse scores | Playwright + axe, LHCI |
| NFR-020-09 | build | `thresholds.yaml` `coverage`, `mutation` | Vitest coverage, Stryker |
| SC-020-01, SC-020-02, SC-020-03 | gate | CI reports of the release build | CI |

## Risks and complexity tracking
| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Theory text written twice (EN and ES MDX) | FR-000-03 requires Spanish on every view | Machine translation at run time would break prerendering and add an external call |
| Equation drift check against `docs/theory/` | Docs are the reviewed source of every equation | Generating MDX from the docs would force interactive-figure anchors into the docs wiki |
| Teaching functions outside `minephys` | Figures for PPO, McNemar, AUC and the paired interval are statistics, not mining models | Adding them to `minephys` would widen a domain library beyond its scope |
| Risk: KaTeX fonts add ≈ 0.3 MB on equation pages | Equations must render without client JavaScript | Loaded only on pages with equations (NFR-020-04), inside the first-view budget |
| Risk: Spanish content lags English | Two languages for long pages | FR-020-47 fails the build on any missing page or id |

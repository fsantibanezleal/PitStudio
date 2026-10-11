# Plan 000 — Foundation: PitStudio
Spec: ./spec.md

## Summary
The foundation spec states the product-level behaviour that every feature spec inherits. This plan adds no
components. It records how each product-level requirement is verified, by which independent oracle, and which feature
spec builds the behaviour:
1. **Honesty and presentation** (FR-000-01 … FR-000-12): badges, provenance, tiers, language, themes, access gate,
   footer, licence exclusions. Built by specs 018, 019 and 020; verified on the built site.
2. **Runner and contracts** (FR-000-13 … FR-000-16, DC-000-01 … DC-000-05, P-000-01, P-000-02): GPU lock and hold,
   manifests, lane gate, profiles. Built by specs 001, 002 and 003; verified with the fake GPU backend and the schemas.
3. **Budgets** (NFR-000-01 … NFR-000-08): CI checks on the build report, file sizes and line counts.
4. **Success criteria** (SC-000-01 … SC-000-04): acceptance tests on the evaluation reports of specs 007, 009, 011, 012.
5. **Tooling** (FR-000-17 … FR-000-19): red-proof replay per environment, `environment-error` classification and GPU
   evidence records, built in `tools/check_tdd.py`.

## Technical context
Runtime: Python 3.14 (root, `pipeline/`, `studio/` uv projects) and Node (web, vitest, Playwright) · no new
dependency · target: CI on GitHub Actions (no GPU), the local workstation for GPU evidence, GitHub Pages for delivery.

## Constitution check
| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | yes | the product is specified against real data where it exists; synthetic-only types are labelled (FR-000-09) |
| Spec before code | yes | every behaviour has an id in this spec or a child spec |
| Acceptance-test-first | yes | `[red]`/`[green]` pairs in tasks.md; SC rows have acceptance tests on the evaluation reports |
| Independent oracles | yes | see the test strategy table; no requirement is verified by the code it constrains |
| Determinism & explicit tolerances | yes | cache key and byte-identical outputs (P-000-01); class tolerances live in `thresholds.yaml` |
| Neutral contracts | yes | DC-000-01 … DC-000-05 under `contracts/`, generated types |
| Static delivery | yes | the public site loads no localhost service without the opt-in (FR-000-11) |
| Honesty | yes | FR-000-05, -07, -09, -10: significance rule, "not yet run", synthetic labels, sources |
| Licence hygiene | yes | FR-000-08 excludes performance data of software whose licence forbids it; CI guard |
| Local-only performance (SLA) | yes | FR-000-08 and the per-spec local-only rules |
| Runner owns the GPU | yes | FR-000-13 lock, hold and guards; fake GPU backend for CI |
| Simplicity | yes | runner capped at 1,500 lines (NFR-000-08), re-assessed beyond it |

## Test strategy
| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| US-000-1 | E2E | hand calculation: a scripted engineer session on the built site; the displayed t/h, kWh/t, CO₂/t, oversize and lead time equal the baked fixture values | Playwright |
| US-000-2 | pipeline (acceptance) | hand calculation: every model row of the evaluation reports has a baseline column and a CI, counted by an independent script | pytest |
| US-000-3 | E2E | hand calculation: each theory page lists an equation, a source and a figure element (counts from the page sources) | Playwright |
| US-000-4 | contract | hand calculation: the reproduction command of one artefact parsed against the recipe list | pytest |
| US-000-5 | unit (fake GPU) | hand calculation: scripted queue of two jobs, a crash and a resume; expected order and cache hits | pytest + fake GPU backend |
| US-000-6 | contract + E2E | hand calculation: counted sources, badges and "not yet run" texts on fixtures | pytest + Playwright |
| FR-000-01 | E2E | hand calculation: every result card in the built site has source, licence and lane text | Playwright |
| FR-000-02 | E2E (hostile) | hand calculation: WebGPU disabled, then WebAssembly disabled, gives the expected tier text | Playwright |
| FR-000-03 | E2E + axe | reference implementation: axe-core on both languages and both themes of every route | Playwright + axe |
| FR-000-04 | E2E | hand calculation: first load shows the gate and no workbench element in the DOM | Playwright |
| FR-000-05 | unit + E2E | analytical: identical differences give the interval [d, d]; an interval containing 0 gives "no significant difference" | pytest + vitest |
| FR-000-06 | E2E | hand calculation: every artefact card has one badge and a provenance line | Playwright |
| FR-000-07 | unit + E2E | hand calculation: a tool with no artefact is rendered "not yet run" | vitest + Playwright |
| FR-000-08 | contract + CI guard | hand calculation: a fixture artefact with a forbidden metric fails the guard; the hash list is a fixed fixture | pytest |
| FR-000-09 | unit + E2E | hand calculation: a data type with no real reference gets the label and no C2ST / TSTR field | pytest + Playwright |
| FR-000-10 | contract + docs check | reference implementation: `tools/check_docs.py` and the source-table schema | pytest |
| FR-000-11 | E2E (hostile) | hand calculation: the network log of the public site has no localhost request before the opt-in click | Playwright |
| FR-000-12 | E2E | hand calculation: footer text equals the build's version, commit SHA and date fixtures | Playwright |
| FR-000-13 | unit (fake GPU) | hand calculation: two jobs, a held lock and a `gpu0.hold` file give the expected refusals and order | pytest |
| FR-000-14 | contract | reference implementation: `jsonschema` against `contracts/manifest.schema.json` for every manifest | pytest + jsonschema |
| FR-000-15 | CI | hand calculation: a manifest lane that disagrees with a measured gate fixture fails | pytest |
| FR-000-16 | CI (fake GPU) | hand calculation: the plan JSON under `linux-gpu` equals the plan under the default profile except the profile fields | pytest |
| P-000-01 | property | metamorphic: re-run invariance of the cache key; byte equality of deterministic outputs | Hypothesis |
| P-000-02 | contract | analytical: SHA-256 of the served file (`hashlib`) equals the manifest value | pytest |
| P-000-03 | parity | reference implementation: the Python reference of each engine against the browser output within `web.*` | pytest + vitest |
| NFR-000-01 | CI | reference implementation: the build report of the bundler (gzip size) | build report |
| NFR-000-02 | CI | reference implementation: axe-core and Lighthouse CI | Playwright + LHCI |
| NFR-000-03 | CI | reference implementation: bytes transferred recorded by Playwright | Playwright |
| NFR-000-04 | CI | hand calculation: summed file sizes of the build against `thresholds.yaml` `budgets` | pytest |
| NFR-000-05 | CI | hand calculation: 10,485,759-byte and 10,485,760-byte fixtures around `contracts.git_file_bytes_max` | pytest |
| NFR-000-06 | CI | hand calculation: a 25 MB fixture and a 25 MB + 1 byte fixture | pytest |
| NFR-000-07 | CI | hand calculation: pairs of fixture sizes around 25 MB | pytest |
| NFR-000-08 | CI | reference implementation: a line count over the runner package | pytest |
| SC-000-01 | pipeline (acceptance) | pre-registered threshold `data.tstr_over_trtr_min` read from the spec 012 report | pytest |
| SC-000-02 | pipeline (acceptance) | pre-registered decision rule and ≥ 30 paired seeds read from the spec 007 report | pytest |
| SC-000-03 | pipeline (acceptance) | thresholds `models.gns_repose_abs_deg_max` and `models.gns_runout_rel_max` read from the spec 011 report | pytest |
| SC-000-04 | pipeline (acceptance) | thresholds of spec 009 (mAP50 0.80 / 0.70, drop ≤ 10 pp) read from its report | pytest |
| DC-000-01 | contract | reference implementation: `jsonschema` 2020-12 on valid and hostile examples | pytest |
| DC-000-02 | contract | reference implementation: `jsonschema` on `studio/capabilities.json` fixtures | pytest |
| DC-000-03 | contract | reference implementation: `jsonschema` on every recipe | pytest |
| DC-000-04 | contract | reference implementation: `jsonschema` on `studio/tools.yaml` | pytest |
| DC-000-05 | contract | reference implementation: `jsonschema` on `data/sources.yaml` | pytest |
| FR-000-17 | unit (fixture repositories) | hand calculation: a fixture repository with one red test per environment; the report names the environment of each | pytest |
| FR-000-18 | unit (fixture repositories) | hand calculation: fixtures with a syntax error at collection, an import of a missing module and a `gpu` test on a machine with device count 0 give `environment-error`; an assertion failure gives red | pytest |
| FR-000-19 | unit (fixture repositories) | hand calculation: evidence records with a missing file, a wrong parent SHA, a changed test hash, the wrong outcome and a drive-letter path each fail; a correct record passes | pytest |

## Risks and complexity tracking
| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Foundation acceptance tests tasked at the foundation, not copied into every feature | one owner for product-level criteria | citing foundation IDs in many feature tasks would hide which test proves the product-level claim |

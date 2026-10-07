# Plan 001 — Contracts
Spec: ./spec.md

## Summary

Five JSON Schema 2020-12 files under `contracts/` (manifest, recipe, tools, sources, and the tightened capability
schema) carry every rule that one document can state (FR-001-01…04, -10…12, -14, -16, -17, -21…25, -28, -31, -35,
-36). A small package `pitstudio.contracts` loads and writes documents safely (FR-001-05…08), computes the two derived
labels that must never be declared by hand — the measured lane and the licence class (FR-001-13, -18, -19) — and
canonicalises JSON (RFC 8785) for spec 002's digests. `tools/check_contracts.py` runs the cross-file rules (FR-001-13,
-15, -17…20, -26, -27, -29, -33, -50, -51). Two generators turn every schema into Pydantic models and type-only
TypeScript modules, and CI fails on drift (FR-001-40…46).

## Technical context

Runtime: Python 3.14 (root `.venv`); generated models also import on Python 3.12 · Node 24 · jsonschema 4.26.0,
referencing 0.37.0, pydantic 2.13.5, PyYAML 6.0.3 (root lock); datamodel-code-generator 0.83.0, Hypothesis 6.168.3,
pytest 9.1.1 (root `dev` group); json-schema-to-typescript 16.0.0 (web `devDependencies`, added with `pnpm add -D` in
T-001-002); TypeScript 7.0.2 and Vitest 5.0.3 (web lock) · target: CPU only, CI (ubuntu) and Windows; GitHub Pages
(static) consumes the web index.

## Constitution check

| Principle | Pass? | Note / justification |
|---|---|---|
| 1. Real, not demo | yes | the corpus's valid examples are built from the real field values in the docs (sources table, stage list, tool list); no invented datasets |
| 2. Spec before code | yes | every module below maps to FR/P ids; `studio/tools.yaml` content is fixed by data-model §4.3 |
| 3. Acceptance-test-first | yes | each task in tasks.md is a `[red]`/`[green]` pair; corpus fixtures and their `index.json` are part of `[red]` |
| 4. Independent oracles | yes | fixtures are hand-built with the expected verdict and pointer by construction; reference validator = Python `jsonschema` (third-party 2020-12 implementation) for schema-level rules; RFC 8785 published examples for canonical bytes; `tsc` for TS conformance; pydantic-core's regex compiler for FR-001-03 |
| 5. Determinism & explicit tolerances | yes | all decisions are exact (booleans, integers, strings); NFR-001-04 checks byte-identical generation on two OSes; P-001-02 tolerance argued below |
| 6. Neutral contracts | yes | this spec is the principle's implementation: DC-001-01…08 |
| 7. Static delivery | yes | TS output is type-only (NFR-001-02); the web index is validated at build (FR-001-20), the browser does no schema work |
| 8. Honesty | yes | lane measured not declared (FR-001-13); local-only scrub (FR-001-14); evaluated-not-adopted reason and page (FR-001-53; done ⇒ artefact is spec 019's FR-019-33); every number sourced in research.md |
| 9. Licence hygiene | yes | licence lattice and reference-only block (FR-001-18, -19); SPDX allowlist (data-model §5.2); credential values impossible in `sources.yaml` (FR-001-32) |
| 10. Simplicity | yes | one package with two-plus users per abstraction: loaders (runner, console, checker), lattice (checker, `studio publish`), JCS (runner cache key, P-001-07); no plugin system; the checker is one script |

## Design

![Manifest producers, field groups and consumers](../../docs/assets/diagrams/manifest-contract.svg)

| Component | Path | Requirements |
|---|---|---|
| Schemas | `contracts/{manifest,recipe,tools,sources,capabilities}.schema.json` | FR-001-01…04, -10…12, -14, -16, -17, -21…25, -28, -31, -35, -36 |
| Loaders and writer | `src/pitstudio/contracts/io.py` (`load_json`, `load_yaml`, `dump_json`, `ContractError`) | FR-001-05…07, P-001-05, P-001-07 |
| Validator | `src/pitstudio/contracts/validate.py` (schema registry via `referencing`, lazy errors, post-schema rules of data-model §1.3–1.4 and §3.2) | FR-001-08, -23, P-001-08 |
| Canonical JSON | `src/pitstudio/contracts/jcs.py` (RFC 8785) | P-001-07; used by spec 002 |
| Lane gate | `src/pitstudio/contracts/lane.py` (`lane_of(measurements) -> "live" \| "replay"`) | FR-001-13, P-001-01…03 |
| Licence lattice | `src/pitstudio/contracts/licence.py` (`licence_class_of`, `check_share_alike`) | FR-001-18, -19, P-001-04 |
| Privacy scan | `src/pitstudio/contracts/privacy.py` | FR-001-15 |
| Generated Python | `src/pitstudio/contracts/_generated/` + `tools/gen_types.py` | FR-001-40, -42, -43, -46, NFR-001-04 |
| Generated TypeScript | `web/src/contracts/generated/` + `web/scripts/gen-types.mjs` (`pnpm gen:types`) | FR-001-41, -42, -44, NFR-001-02 |
| Contract checker | `tools/check_contracts.py` | FR-001-13, -15…20, -26, -27, -29, -33, -50, -51, NFR-001-01 |
| Tool registry | `studio/tools.yaml` (20 studio tools + components) | FR-001-25 |
| Capability writer change | `studio/bench/run_bench.py` (`allow_nan=False`, non-finite → fail) | FR-001-07, -37 |
| CI wiring | `.github/workflows/ci.yml` (python job: `gen_types.py --check`, `check_contracts.py`; web job: `pnpm gen:types --check`); `.github/workflows/pages.yml` (served-digest check before upload) | FR-001-20, -42, -50 |

Data flow: maintainer YAML and producer JSON → `load_*` (syntax and hostile classes) → `validate` (schema + post-schema
rules) → typed access through the generated models where convenient → `check_contracts.py` (cross-file rules) in CI and
`pages.yml`.

### Proposed `thresholds.yaml` additions (proposed keys, pending maintainer approval)

The lane gate of FR-001-13 reads the consolidated `lane_gate` keys (`live_asset_mb_max: 25`, `interaction_ms_max: 16`,
`run_s_max: 1`, `trace_mb_max: 10`; MB = 10⁶ B, so bytes and milliseconds convert exactly); the earlier
`contracts.lane_*` names are withdrawn in their favour.

```yaml
contracts:
  git_file_bytes_max: 10485760        # = tools/check_repo.py (10 MiB)
  error_message_chars_max: 300
  check_runtime_s_max: 30             # NFR-001-01
```

## Test strategy

| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-001-01 | contract | JSON Schema 2020-12 meta-schema via `Draft202012Validator.check_schema` (reference implementation) | pytest |
| FR-001-02 | contract | hand-written schema walker rule (data-model §1.2); seeded open-object schema must be flagged | pytest |
| FR-001-03 | contract | Python `re.compile` and pydantic-core `StringConstraints(pattern=…)` build (reference implementations); a seeded lookahead pattern must fail | pytest |
| FR-001-04 | contract (hostile) | hand-built fixtures (bad digests, timestamps, URLs) with expected pointer; validated with `FormatChecker` while `rfc3339_validator`/`rfc3987` imports are blocked (`sys.modules[...] = None`) | pytest |
| FR-001-05, FR-001-06 | unit (hostile) | hand-built byte strings (NaN, duplicate keys, BOM, invalid UTF-8, depth 33, alias, tag, multi-document, `yes`, dates) with expected error kind and line | pytest |
| FR-001-07 | unit | hand calculation: expected bytes written out literally for small objects | pytest |
| FR-001-08 | unit | fixture with three known violations → expected sorted pointer list | pytest |
| FR-001-10…12, FR-001-14, FR-001-16, FR-001-17 | contract (hostile) | corpus fixtures with expected verdict, pointer and keyword (by construction from data-model §2) | pytest + `jsonschema` |
| FR-001-13 | contract + CI | hand calculation of the gate for each fixture's measurements (data-model §2.6) | pytest |
| FR-001-15 | contract (hostile) | fixtures embedding drive-letter, UNC, `/home/…` paths and the test process's host and user names (`socket.gethostname()`, `getpass.getuser()` as reference values) | pytest |
| FR-001-18, FR-001-19 | unit + contract | hand calculation over the rank table (data-model §5.4) | pytest |
| FR-001-20 | contract + CI | `hashlib.sha256` of the fixture files (reference implementation) vs a deliberately wrong index entry | pytest |
| FR-001-21…24 | contract (hostile) | corpus fixtures (data-model §3.4, §3.5) with expected pointer | pytest + `jsonschema` |
| FR-001-25…29, FR-001-53 | contract (hostile) | fixture registries and manifests; the 20 ids and statuses of data-model §4.3 as the expected list; lock fixtures with known packages | pytest |
| FR-001-31…33, FR-001-52 | contract (hostile) | fixture registries (data-model §5); secret patterns copied from `tools/check_repo.py` as reference strings; hand-built entries with one bad access mode, fallback id, file kind, checksum or extract pattern each | pytest |
| FR-001-35, FR-001-36 | contract (hostile) | the existing five sample results of `test_capabilities_contract.py` must stay valid; hand-built bounds violations | pytest |
| FR-001-37 | unit (hostile) | probe results with `float("nan")` metrics → expected `fail` entry; output parsed by a strict JSON parser (`json.loads(..., parse_constant=raise)`) | pytest |
| FR-001-40, FR-001-42, FR-001-46 | contract / CI | regeneration into a temporary folder under `PITSTUDIO_TMP` compared byte-for-byte with the committed files; a seeded one-character edit must be reported | pytest |
| FR-001-41, FR-001-44 | unit (web) | `tsc` (reference compiler) on `web/src/contracts/generated.test.ts` with `@ts-expect-error` lines; Vitest asserts the generated text has no runtime statement | Vitest + tsc |
| FR-001-43 | contract | `uv run --python 3.12 --with pydantic==<locked> python -c "import …"` subprocess; `mypy src` | pytest |
| FR-001-45 | contract | the boundary list of data-model §7.3 inspected by test: each boundary function calls `validate` (call spy) | pytest |
| FR-001-50, FR-001-51 | unit (hostile) | fixture repository trees under `tests/contract/fixtures/repo/{clean,broken-*}` with the expected findings list | pytest |
| P-001-01…03 | property + metamorphic | invariant (monotonicity, unit change, boundary) of the analytical gate | Hypothesis |
| P-001-04 | property + metamorphic | lattice laws over the rank table | Hypothesis |
| P-001-05 | property | invariant (round trip) | Hypothesis |
| P-001-06 | property | Python `jsonschema` as the reference acceptor | pytest over the corpus |
| P-001-07 | property + metamorphic | RFC 8785 §3.2.4 example and Appendix B samples (published worked example) for canonical bytes; YAML ↔ JSON equivalence | Hypothesis |
| P-001-08 | property | invariant (determinism across runs and key orders); Windows run in the runner-windows CI job of spec 002 | Hypothesis |
| NFR-001-01 | CI | wall-clock timing of the checker on the scale fixture (2,000 artefacts, 64 recipes) | pytest + `time.perf_counter` |
| NFR-001-02 | build | scan of `web/build/client/**/*.js` for the generated type names (none may appear) | Vitest (node) |
| NFR-001-03 | contract | `index.json` coverage over data-model §8.2 | pytest |
| NFR-001-04 | CI | two generations byte-identical; the Windows CI job repeats the drift check | pytest |
| NFR-001-05 | mutation | mutation score | mutmut (T-001-090) |

**Tolerances.** Every assertion here is exact. P-001-02 compares `x_ms ≤ 16` with `x_ms / 1000 ≤ 0.016` (and the
other thresholds likewise) for `x_ms` drawn with at most three decimals: the smallest distance between such a value and
a threshold is 0.001 ms, a relative gap of ≥ 6 × 10⁻⁵ at 16 ms, far above the float64 rounding of one division
(≈ 1.1 × 10⁻¹⁶ relative), so both comparisons must agree exactly.

## Risks and complexity tracking

| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Custom YAML loader instead of `yaml.safe_load` | `safe_load` keeps duplicate keys silently, turns `yes`/`on` into booleans and dates into `datetime`, accepts `.nan`, expands aliases (research.md R6) | plain `safe_load` makes hostile recipes look valid |
| RFC 8785 canonicaliser in the core package (~60 lines) | digests must be reproducible by a TypeScript twin and stable across Python versions | `json.dumps(sort_keys=True)` differs in number format and key order (research.md R4) |
| Post-schema rules in `validate` (calendar dates, params depth, shard count, device names, case-fold duplicates) | not expressible in the portable regex subset or in JSON Schema | lookaround patterns break pydantic-core (FR-001-03) |
| Conditionals (`if`/`then`) in the manifest schema | publication rules depend on `published`, `kind`, `asset_host`, `lane` | splitting into many document kinds multiplies schemas and generated types |

Other risks: a future datamodel-code-generator or json-schema-to-typescript release changes its output — the drift
check fails on the upgrade PR, which then regenerates in the same commit; the Pages workflow gains a Python step for
FR-001-20 (uv is already used by the CI python job).

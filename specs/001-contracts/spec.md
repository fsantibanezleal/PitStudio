# Spec 001 — Contracts
Status: Clarified
Tier: L · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none) — tightens the existing `contracts/capabilities.schema.json` and the writer in
`studio/bench/run_bench.py` (no earlier requirement IDs; see §9)

## 1. Intent

PitStudio moves data across many boundaries: between ten isolated environments (Python 3.12 and 3.14), from the studio
to the pipeline, from both to the static web app, and from the maintainer's YAML files to the runner and the CI
checks. Every such boundary is a JSON Schema 2020-12 contract under `contracts/`, and Python and TypeScript types are
generated from it, never written by hand (constitution, principle 6). This spec defines the five product contracts
named by the foundation (DC-000-01…05): the **manifest** (studio runs and web assets), the **recipe** (runner input,
plus the job request the console accepts), the **tool registry** (studio tool map), the **source registry** (data
licences and digests) and the existing **capability report**. It also defines the shared loaders and writers, the type
generators with their CI drift check, and `tools/check_contracts.py`, which enforces the cross-file honesty rules that
a single schema cannot express: the measured lane gate (FR-000-15), the licence-class lattice, the `performance:
local-only` scrub (FR-000-08), the served-file digest (P-000-02) and privacy (the tool-status honesty check, "done
needs an artefact", is spec 019-web-studio's, FR-019-33, over this spec's manifest fields).

Who benefits: the web app and CI (one machine-checked provenance format), the maintainer (hostile files rejected before
any work starts), reviewers (every label can be recomputed from the committed data).

Out of scope: the runner's own protocol files (profile, job spec, events: spec 002-runner), the console's response
schemas (spec 003-console), the pandera ingestion schemas (spec 008-data-pipeline), the web rendering of manifests
(spec 019-web-studio), the site budget totals (spec 018-web-cases) and the media encode itself (spec
006-media-telemetry). Those specs reuse the loaders, generators and checker defined here.

## 2. User stories

### US-001-1 (P1) Machine-checked provenance for every published artefact
As a reader of the web app or a reviewer, I want every published artefact to be described by a manifest that names its
producing tool, run, commit, inputs with SHA-256, measured lane, licence class and `performance` marker, so that every
badge and number on the site can be traced and re-checked. Independent test: validate the example run and web-index
manifests of the conformance corpus and the committed `web/public/assets/manifest.json`; every hostile manifest in the
corpus is rejected with the expected rule.

### US-001-2 (P1) Inputs are rejected before work starts
As the maintainer, I want recipes, the tool registry and the source registry validated on load, with hostile documents
(malformed YAML, path tricks, non-finite numbers, unknown enums, oversized files) rejected with a precise message, so
that no GPU hour is spent on a broken or unsafe input. Independent test: run the loaders and validators over the
hostile corpus; each file is rejected with its expected JSON pointer and rule, and no partial object is returned.

### US-001-3 (P1) Generated types that cannot drift
As a developer, I want Pydantic models and TypeScript types generated from the schemas, with CI failing when the
committed types differ from a fresh generation, so that Python and TypeScript always agree with the contract.
Independent test: edit one character of a generated file or of a schema; the drift check fails and names the file.

### US-001-4 (P1) Honesty rules enforced across files
As a reviewer, I want one command that recomputes lanes, licence classes, local-only scrubs, served-file digests,
registry references and tool status from the committed files and fails on any disagreement, so that the site cannot
claim more than its data shows. Independent test: the checker passes on a consistent fixture repository and fails, with
the named rule, on each seeded inconsistency.

### US-001-5 (P2) The existing capability report stays honest
As the maintainer, I want the committed capability report's schema bounded and covered by hostile tests and generated
types, so that a probe cannot publish a non-finite or unbounded value. Independent test: the hostile capability
fixtures are rejected; the existing five contract tests still pass.

Story index (for traceability):

| ID | Priority | Story |
|---|---|---|
| US-001-1 | P1 | Machine-checked provenance for every published artefact |
| US-001-2 | P1 | Inputs are rejected before work starts |
| US-001-3 | P1 | Generated types that cannot drift |
| US-001-4 | P1 | Honesty rules enforced across files |
| US-001-5 | P2 | The existing capability report stays honest |

## 3. Functional requirements (EARS)

Normative field tables, patterns, enums, caps and the hostile-class matrix are in [data-model.md](data-model.md); a
requirement that names "data-model §n" makes that section part of the requirement.

### 3.1 All contracts, loaders and writers

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-001-01 | Ubiquitous | The repository shall hold `contracts/manifest.schema.json`, `recipe.schema.json`, `tools.schema.json`, `sources.schema.json` and `capabilities.schema.json`, each declaring `"$schema": "https://json-schema.org/draft/2020-12/schema"` and `"$id": "https://fsantibanezleal.github.io/PitStudio/contracts/<file name>"`, and each shall pass `Draft202012Validator.check_schema` with 0 errors. | contract |
| FR-001-02 | Ubiquitous | Every object-typed subschema of every contract shall be closed: it declares `additionalProperties: false`, or it is a map that declares both `propertyNames` with a `pattern` and a typed `additionalProperties`, or it sits under `allOf`/`oneOf`/`anyOf` with `unevaluatedProperties: false` on the composing schema (data-model §1.2). | contract (schema walker) |
| FR-001-03 | Ubiquitous | Every `pattern` in every contract shall compile under Python `re` and under pydantic-core's default Rust regex engine, and shall contain no lookaround, backreference, possessive quantifier or atomic group. | contract |
| FR-001-04 | Ubiquitous | Every safety-relevant string (SHA-256 digest, git SHA, UTC timestamp, URL, release tag, id, relative path; list in data-model §1.3) shall be constrained by `pattern` and `maxLength` in the schema itself; `format` may appear only as an additional annotation. | contract (hostile, with the optional format-checker packages absent) |
| FR-001-05 | Unwanted | If a JSON contract document contains a non-finite number (`NaN`, `Infinity`, `-Infinity`), a duplicate object key, invalid UTF-8, a byte-order mark, nesting deeper than 32 levels, or more bytes than its cap (data-model §1.4), then `pitstudio.contracts.load_json` shall raise `ContractError` naming the file and the line or JSON pointer, before schema validation, and shall return no partial object. | unit (hostile) |
| FR-001-06 | Unwanted | If a YAML contract document contains an anchor or alias, an explicit tag, a duplicate key, more than one document, a non-string mapping key, a non-finite float (`.nan`, `.inf`, `-.inf`) or more bytes than its cap, then `pitstudio.contracts.load_yaml` shall raise `ContractError` naming the file and line; and it shall load the YAML 1.1 implicit booleans other than `true`/`false` (`yes`, `no`, `on`, `off`, `y`, `n`, any case) and unquoted dates and timestamps as strings. | unit (hostile) |
| FR-001-07 | Ubiquitous | Every contract writer (`pitstudio.contracts.dump_json` and `studio/bench/run_bench.py`) shall write UTF-8 without a byte-order mark, LF line endings, 2-space indentation, a trailing newline and `allow_nan=False`, so that equal input objects give byte-identical files. | unit |
| FR-001-08 | Ubiquitous | The validator `pitstudio.contracts.validate(document, schema_name)` shall report every violation (lazy), each with its JSON pointer, the failing schema keyword and a message of ≤ 300 characters containing no absolute path, sorted by pointer. | unit |

### 3.2 Manifest (`contracts/manifest.schema.json`)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-001-10 | Ubiquitous | The manifest schema shall define two document kinds discriminated by `kind`: `run` (one studio or pipeline run) and `web-index` (the published artefact index `web/public/assets/manifest.json`), each with `schema_version` matching `^1\.[0-9]+$` and the field groups of data-model §2 (identity, inputs, environment, stages, telemetry summary, determinism, artefacts, encoder record, licence). | contract |
| FR-001-11 | Ubiquitous | Every artefact record shall carry `id`, `path`, `bytes`, `sha256`, `kind`, `producer.tool`, `producer.stage`, `run_id`, `git_sha`, `lane`, `licence_class`, `spdx`, `asset_host` and `budget_class`, and shall carry a non-empty `attribution` unless its licence class is `public-domain`, `open-no-attribution` or `own` (refines FR-000-14). | contract |
| FR-001-12 | Unwanted | If an artefact has `asset_host: release` without a `release_tag` matching `^assets-v[0-9]+\.[0-9]{2}\.[0-9]{3}$`, or `asset_host: git` with a `release_tag` or with `bytes` ≥ 10,485,760, then the manifest shall fail validation. | contract (hostile) |
| FR-001-13 | Unwanted | If an artefact with `lane` `live` or `replay` lacks `lane_measurements`, or an artefact with `lane: static` has `lane_measurements` or a kind outside the static kinds (data-model §2.6), or `lane` differs from the gate computed from its measurements (live iff web-drivable ∧ largest asset ≤ 25,000,000 B ∧ (interaction ≤ 16 ms ∨ run ≤ 1,000 ms on T2) ∧ trace ≤ 10,000,000 B), then `tools/check_contracts.py` shall fail naming the artefact and the failing condition (refines FR-000-15). | contract (hostile) + CI |
| FR-001-14 | Unwanted | If a run manifest with `published: true` has a stage with `performance: local-only` whose `telemetry` is anything other than the string `measured locally, not published (licence)`, or which carries `wall_s`, `throughput` or any `attempts[].duration_s`, then the manifest shall fail validation (refines FR-000-08). | contract (hostile) |
| FR-001-15 | Unwanted | If any string value of a committed manifest matches an absolute-path pattern (data-model §1.5) or contains the host name, the user name or the home directory of the machine running the check, then `tools/check_contracts.py` shall fail naming the file and JSON pointer; and the manifest schema shall define no field for a host name, user name or absolute path. | contract (hostile) |
| FR-001-16 | Unwanted | If a run manifest with `published: true` has `git_dirty: true`, `launcher: test` or `gpu.backend: fake` (schema), or lists an artefact produced by a stage whose `status` is not `succeeded` (`tools/check_contracts.py`), then the manifest shall be rejected naming the pointer. | contract (hostile) |
| FR-001-17 | Ubiquitous | Every artefact of kind `video` shall carry an `encoder` record (data-model §2.7) and no other kind shall carry one; and `tools/check_contracts.py` shall fail when `abs(duration_s − frames / fps) > 1 / fps`. | contract |
| FR-001-18 | Ubiquitous | `pitstudio.contracts.licence_class_of(inputs)` shall return the maximum of `own` and the input classes under the total order public-domain < open-no-attribution < own < attribution < share-alike < display-only < reference-only, and `tools/check_contracts.py` shall fail when a published artefact's `licence_class` differs from that value computed from its inputs' classes. | unit + contract |
| FR-001-19 | Unwanted | If a published artefact has an input of class `reference-only`, inputs with two different share-alike SPDX ids, or a share-alike class with an `spdx` different from its share-alike input's, then `tools/check_contracts.py` shall fail naming the artefact. | contract (hostile) |
| FR-001-20 | Unwanted | If the SHA-256 or the byte size of a served file differs from its web-index entry (git-hosted: the file under `web/public/`; release-hosted: the downloaded release asset before it is copied into the Pages artifact), then the check shall fail and the Pages build shall stop before upload (refines P-000-02). | contract + CI |

### 3.3 Recipe (`contracts/recipe.schema.json`)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-001-21 | Ubiquitous | The recipe schema shall define a recipe document (`id`, `case`, `seed`, optional `description`, 1–64 `stages`) with the stage fields of data-model §3.2 and a `$defs/job_request` document (data-model §3.5), and shall define no field for a machine profile or an absolute path; data shall be referenced only by logical id and SHA-256 or by upstream stage. | contract |
| FR-001-22 | Ubiquitous | The recipe schema shall bind every frozen stage id to its environment as in data-model §3.3, so that a recipe naming a stage with any other `env` fails validation. | contract |
| FR-001-23 | Unwanted | If a recipe contains any hostile value of data-model §3.4 (unknown stage id, env, case, determinism class or resource kind; an `entry` that is not a dotted lowercase module path; a malformed input id or digest; an unsafe output path; a seed outside 0…2⁶³−1 or of type bool or float; params breaking the key, depth, size or finiteness limits; `timeout_s` outside 1…604,800; `gpu: none` with a VRAM estimate > 0; `gpu: exclusive` without one; `statistical` without observable tolerances; `none` without a reason; more than 10,000 shards; more than 4 OOM fallback steps), then the recipe shall fail validation with the pointer of the offending value. | contract (hostile) |
| FR-001-24 | Unwanted | If a job request contains an unknown field (including any stage field such as `entry`, `env` or `params`, i.e. an inline recipe), a recipe id, stage key or profile id that does not match its pattern, more than 64 stages or a duplicate stage, then it shall fail validation against `recipe.schema.json#/$defs/job_request`. | contract (hostile) |

### 3.4 Tool registry (`contracts/tools.schema.json`, `studio/tools.yaml`)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-001-25 | Ubiquitous | The tool registry schema shall define the entry fields of data-model §4, and `studio/tools.yaml` shall hold exactly 20 entries of `category: studio-tool` — the 17 tools of data-model §4.3 with status `not-yet-run` or `done`, and 3 with status `evaluated-not-adopted` (cuOpt, PhysicsNeMo, Cosmos Predict/Transfer) — plus any number of `category: component` entries (own code and libraries that may appear as `producer.tool`). | contract |
| FR-001-26 | Unwanted | If a registry entry gives `version` as a literal string, or as a lock reference whose lock file does not exist or does not contain the named package, then validation (literal) or `tools/check_contracts.py` (unresolvable reference) shall fail naming the entry. | contract (hostile) |
| ~~FR-001-27~~ | — | Retired: tool status against published artefacts and the evaluated-not-adopted fields. | superseded by FR-019-33, FR-019-43 and FR-001-53 (integration 2026-10-07) |
| FR-001-53 | Unwanted | If a registry entry has `status: evaluated-not-adopted` without a `reason` of ≥ 20 characters, or its `docs_page` does not exist in the repository, then validation (reason) or `tools/check_contracts.py` (missing page) shall fail naming the entry. | contract (hostile) |
| FR-001-28 | Unwanted | If a registry entry lists a performance-restricted licence (data-model §5.3) in `spdx` and declares `performance: public`, then the registry shall fail validation. | contract (hostile) |
| FR-001-29 | Unwanted | If a manifest names a `producer.tool` that is not a registry id, or a stage environment that is not among that tool's `envs`, then `tools/check_contracts.py` shall fail naming the manifest and pointer. | contract (hostile) |

### 3.5 Source registry (`contracts/sources.schema.json`, `data/sources.yaml`)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-001-31 | Ubiquitous | The source registry schema shall define the entry fields of data-model §5 (identity, access mode, files with digests, file kind, publisher checksum, uncompressed size and extract patterns, SPDX id, licence class, redistribution class, attribution, account with the name of its environment variable, fallback sources, card) — the single definition of every registry field that `s00_download` (spec 008) reads — and the committed `data/sources.yaml` shall validate, including the empty list. | contract |
| FR-001-32 | Unwanted | If a source entry has a non-`https` URL, a URL with user information or with a query parameter named like a credential (`key`, `token`, `apikey`, `api_key`, `access_token`, `signature`), a malformed digest, an SPDX id outside the allowlist, a licence class not allowed for its SPDX id and kind (data-model §5.2), a missing attribution for class `attribution` or `share-alike`, `account.needed: true` without `fallback`, a value matching the secret patterns of `tools/check_repo.py`, a duplicate id, or `bytes` or `uncompressed_bytes` outside 1…68,719,476,736 (64 GiB), then validation or `tools/check_contracts.py` shall fail naming the entry. | contract (hostile) |
| FR-001-33 | Unwanted | If a manifest input id is neither a source id, nor the id of an artefact of the same run, nor (for `kind: knowledge`) a row id of the `minephys` knowledge tables pinned by the lock, or a run manifest with `published: true` uses a source whose file entry has no pinned `sha256`, then `tools/check_contracts.py` shall fail naming the manifest and pointer. | contract (hostile) |
| FR-001-52 | Unwanted | If a source entry has an unknown `access` value, `access: account` without `account.needed: true` (or the reverse), a fallback source id that is not another registry id, names the entry itself or repeats, a file without `kind` or with an unknown kind, a malformed `publisher_checksum`, `extract` or `uncompressed_bytes` on a file whose kind is not `archive`, an `extract` pattern that is not a `relglob` (absolute, drive letter, backslash, `.` or `..` segment), or files whose SPDX ids mix a share-alike id with any other id, then validation or `tools/check_contracts.py` shall fail naming the entry and the JSON pointer. | contract (hostile) |

### 3.6 Capability report (`contracts/capabilities.schema.json`)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-001-35 | Ubiquitous | The capability schema shall keep its current shape (closed objects; `status` ∈ {pass, fail, skip}; `metrics` either an object of numbers or strings or the constant `measured locally, not published (licence)`; `error` ≤ 300 characters) and gain the bounds of data-model §6, so that every committed or generated report produced by `run_bench.public_view` validates. | contract |
| FR-001-36 | Unwanted | If a capability report has a probe name outside `^[a-z][a-z0-9_]{0,31}$`, more than 64 probes, an unknown status, a non-finite number, a version string over 64 characters, more than 20 notes or a note over 300 characters, a GPU name over 128 characters, a driver not matching `^[0-9]+(\.[0-9]+)+$` or an unknown field, then it shall fail validation (via `load_json` for non-finite numbers). | contract (hostile) |
| FR-001-37 | Unwanted | If a probe result handed to `run_bench.public_view` or to the local report writer contains a non-finite metric or telemetry value, then `run_bench.py` shall record that probe as `status: fail` with the error `non-finite metric <name>` (name ≤ 64 characters) and shall still write two valid JSON files. | unit (hostile) |

### 3.7 Generated types and drift

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-001-40 | Ubiquitous | `tools/gen_types.py` shall generate one Pydantic v2 module per `contracts/*.schema.json` into `src/pitstudio/contracts/_generated/` with datamodel-code-generator 0.83.0 and the pinned options of data-model §7.1 (schema version 2020-12, `pydantic_v2.BaseModel`, target Python 3.12, `extra="forbid"`, no timestamp, repository-relative header, LF, ruff-formatted). | contract |
| FR-001-41 | Ubiquitous | `web/scripts/gen-types.mjs` (`pnpm gen:types`) shall generate one type-only TypeScript module per contract into `web/src/contracts/generated/` with json-schema-to-typescript 16.0.0 and the pinned options of data-model §7.2. | contract (web) |
| FR-001-42 | Unwanted | If a committed generated file differs from a fresh generation, a generated file has no schema, or a schema has no generated file, then `uv run python tools/gen_types.py --check` (Python CI job) or `pnpm gen:types --check` (web CI job) shall exit 1 listing every differing file. | CI |
| FR-001-43 | Ubiquitous | The generated Python modules shall import on Python 3.12 and 3.14 with the locked pydantic version, parse every valid example of the conformance corpus, and pass `mypy src` and `ruff format --check`. | contract |
| FR-001-44 | Ubiquitous | The generated TypeScript modules shall contain only type declarations and comments (no runtime statement), every valid corpus example shall type-check against its type, and an example with an unknown property or an out-of-enum value shall fail type-checking. | unit (web, `tsc`) |
| FR-001-45 | State | While a contract rule cannot be expressed in the generated types (conditionals, TypeScript patterns, cross-file rules), every trust boundary of data-model §7.3 shall validate with `pitstudio.contracts.validate` and the contract checks, never with the generated types alone. | contract (boundary list) |
| FR-001-46 | Unwanted | If a schema is invalid, uses an unsupported construct (`prefixItems`, `$dynamicRef`, a remote `$ref`), or the generator receives an unknown option, then the generator shall exit non-zero naming the schema and shall leave every committed generated file unchanged. | unit (hostile) |

### 3.8 The contract checker

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-001-50 | Ubiquitous | `tools/check_contracts.py` shall validate every committed contract document of data-model §8.1 against its schema, run the cross-file rules FR-001-13, -15 to -20, -26, -29, -33 and -53, and exit 0 when clean, 1 on findings and 2 on a usage error; CI shall run it in the Python job. | unit + CI |
| FR-001-51 | Unwanted | If a contract file is unreadable or malformed, is a symbolic link resolving outside the repository, or is an unknown file in a contract folder, then `tools/check_contracts.py` shall report it as a finding (file, rule id, message ≤ 300 characters), continue with the other files, and exit 1 without a Python traceback. | unit (hostile) |

## 4. Correctness properties

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-001-01 | Lane-gate monotonicity: for measurements m ≤ m′ componentwise (asset bytes, interaction ms, run ms, trace bytes; same web-drivable flag), gate(m′) = live ⇒ gate(m) = live. | Hypothesis: integers 0…10¹⁰ B, 0…10⁶ ms, nullable times | exact |
| P-001-02 | Lane-gate unit invariance: the gate evaluated in bytes and milliseconds equals the gate evaluated in MB (= 10⁶ B) and seconds with the thresholds converted (25 MB, 0.016 s, 1 s, 10 MB). | Hypothesis: integer bytes; ms with ≤ 3 decimals | exact |
| P-001-03 | Lane-gate threshold boundary and disjunction symmetry: measurements exactly at 25,000,000 B, 16 ms, 1,000 ms and 10,000,000 B give live; one unit beyond any single threshold (other conditions met) gives replay; swapping which of interaction and run time satisfies its bound leaves the result unchanged. | enumerated boundary cases × Hypothesis for the others | exact |
| P-001-04 | Licence-class lattice: `licence_class_of` is invariant under permutation of inputs, idempotent (a duplicated input changes nothing), monotone (adding an input never lowers the class) and associative (class(A ∪ B) = max(class(A), class(B))). | Hypothesis: lists of 0–20 classes | exact |
| P-001-05 | Serialisation round trip: for every valid document d, `load_json(dump_json(d)) == d`, and `dump_json(load_json(dump_json(d)))` is byte-identical to `dump_json(d)`. | Hypothesis strategies per document kind (data-model §8.3) | exact |
| P-001-06 | Generated-model agreement: for every corpus fixture not tagged `conditional` or `cross-file`, the generated Pydantic model accepts it if and only if the JSON Schema validator accepts it. | conformance corpus | exact |
| P-001-07 | Syntax invariance: a YAML document and its JSON equivalent (comments added, keys reordered, flow vs block style, quoted vs plain scalars of the same type) give the same validation outcome and the same RFC 8785 canonical bytes. | Hypothesis: valid recipes / registries rendered both ways | exact |
| P-001-08 | Validation determinism: the sorted error list for a document is identical across two runs, across Windows and Linux, and across key orders of the input. | corpus × key permutations | exact |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-001-01 | Contract-check run time on the CI runner for a repository with up to 2,000 published artefacts and 64 recipes | ≤ 30 s | CI timing of `tools/check_contracts.py` on the scale fixture |
| NFR-001-02 | Bytes the generated TypeScript types add to the built JavaScript | 0 B (type-only modules) | build-output scan for generated identifiers |
| NFR-001-03 | Hostile-corpus coverage | ≥ 1 invalid fixture per applicable (schema × hostile class) cell of data-model §8.2; ≥ 1 valid example per document kind | corpus coverage test |
| NFR-001-04 | Generation determinism | two consecutive runs byte-identical; Windows and Linux outputs byte-identical | drift check on both OSes |
| NFR-001-05 | Mutation score of `src/pitstudio/contracts/` (lane gate, licence lattice, loaders) | ≥ 0.80 (`mutation.numerical_core_min`) | mutation run (T-001-090) |
| SC-001-01 | After the build phase, every push to `main` passes the contract check and both drift checks | 0 findings, 0 drift | CI history |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-001-01 | run manifests `runs/<run_id>/manifest.json`, published run manifests, `web/public/assets/manifest.json` (refines DC-000-01) | `contracts/manifest.schema.json` | runner, `s60_export`, `st56_encode`, `studio publish` → web app, CI, `pages.yml` |
| DC-001-02 | recipes `studio/recipes/cases/*.yaml`, `studio/recipes/_bench/*.yaml`; console job requests (refines DC-000-03) | `contracts/recipe.schema.json` (`$defs/job_request`) | maintainer, console → runner |
| DC-001-03 | studio tool registry `studio/tools.yaml` (refines DC-000-04) | `contracts/tools.schema.json` | maintainer → web tool map, contract check |
| DC-001-04 | data registry `data/sources.yaml` (refines DC-000-05) | `contracts/sources.schema.json` | maintainer → `s00_download`, docs, contract check |
| DC-001-05 | capability report `studio/capabilities.json` (refines DC-000-02) | `contracts/capabilities.schema.json` | `studio/bench/run_bench.py` → runner guards, web `/studio` |
| DC-001-06 | generated Pydantic models `src/pitstudio/contracts/_generated/*.py` | every `contracts/*.schema.json` | `tools/gen_types.py` → runner, console, pipeline, checks |
| DC-001-07 | generated TypeScript types `web/src/contracts/generated/*.ts` | every `contracts/*.schema.json` | `web/scripts/gen-types.mjs` → web app, console UI |
| DC-001-08 | conformance corpus `tests/contract/fixtures/<schema>/{valid,invalid}/` with `index.json` | the schema it exercises | test authors → contract, property and web type tests |

## 7. Edge cases and assumptions

- **No GPU, no network.** Every requirement here is verified on a CPU CI runner; nothing downloads data. The
  served-file check (FR-001-20) for release assets runs inside `pages.yml`, where the assets are fetched by tag.
- **Format keywords.** Python `jsonschema` checks a `format` only when the matching optional package is installed:
  `date-time` needs `rfc3339-validator`, `uri` needs `rfc3987` or `rfc3986-validator`, and "if a dependency is not
  installed … validation will succeed without throwing an error" (python-jsonschema documentation, "Validating
  formats"). None of them is in the root lock today, so FR-001-04 puts every safety-relevant rule in `pattern`.
- **Non-finite numbers.** Python's `json` accepts and writes `NaN`/`Infinity` by default, and `jsonschema` treats a
  Python `nan` as a number; browsers' `JSON.parse` rejects them. FR-001-05 and FR-001-07 close that gap on both sides.
- **Units.** All sizes in contracts are integer bytes and all durations milliseconds or seconds as named in the field.
  The lane gate's "MB" is decimal (10⁶ B), the stricter reading; the git per-file limit is 10 MiB = 10,485,760 B, as
  `tools/check_repo.py` already implements (GitHub's own limits are stated in MiB).
- **Lane values.** Artefact lanes are `live`, `replay` and `static`. "Precompute" is a lane of computation that produces
  replay artefacts (docs `architecture/lanes.md`), so FR-000-01's "precomputed" maps to the REPLAY badge (FR-000-06).
- **Empty registries.** `data/sources.yaml` is `sources: []` today and `studio/tools.yaml` does not exist; both must
  validate as soon as they are written (FR-001-25 counts are checked from the first commit of `tools.yaml`).
- **No UNVERIFIED constants.** No threshold or oracle here depends on a value tagged UNVERIFIED in the docs. Source
  entries whose digest is not yet known are allowed with `sha256: null` until first download; FR-001-33 keeps them out
  of published runs.
- **Pinned values read at specification.** RFC 8785 §3.2.4 canonical example and Appendix B number samples (oracle of
  P-001-07 and spec 002's cache key); the SPDX id `DL-DE-ZERO-2.0` ("Data licence Germany – zero – version 2.0",
  spdx.org); json-schema-to-typescript 16.0.0 (MIT) treats every draft through its draft-4 model, ignores `prefixItems`
  and `if`/`then`/`else`, and supports `$defs` and `const` (its README); datamodel-code-generator 0.83.0 offers
  `--schema-version 2020-12`, `--disable-timestamp`, `--extra-fields forbid` and `--target-python-version 3.12`
  (its `--help` in the root lock). Details and URLs: [research.md](research.md).
- **Licence text is not legal advice.** The SPDX allowlist and the class mapping record what publishers state; adding an
  SPDX id is a schema change reviewed like code.

## 8. Clarifications log

- Resolved — **set of contracts.** Plan §8 lists ingestion (pandera), manifest, recipe, tools and "bench results"; the
  foundation adds the source registry. The capability report *is* the bench-results contract. This spec covers the five
  JSON Schema contracts; pandera schemas stay in spec 008-data-pipeline.
- Resolved — **licence classes vs redistribution classes.** `docs/architecture/README.md` lists "redistributable,
  derived-only, share-alike, reference-only, no-redistribution" as licence classes, while
  `docs/data-contract/sources-and-licences.md` defines seven licence classes plus a separate three-value redistribution
  class. The plan names "licence classes" without enumerating them. This spec adopts the seven + three model of
  sources-and-licences.md; the architecture overview line needs a docs correction (reported to the coordinator).
- Resolved — **field names.** The committed `data/sources.yaml` comment and `docs/data-contract/ingestion.md` use
  `license` / `license_url`, the tool registry page uses `licence`, and the manifest page uses `spdx`. The docs state
  that the schema "makes them normative" and "may refine them". All contracts use `spdx` (SPDX id or LicenseRef),
  `licence_class` and, for sources, `licence_url`; the example comment in `data/sources.yaml` is updated in T-001-022
  and the docs pages need the same rename (reported).
- Resolved — **resource units.** The docs' illustrative recipe uses `vram_gb_est` / `disk_gb_est`. Units are made
  explicit as `vram_gib_est` / `disk_gib_est` (GiB = 2³⁰ B), because "wrong units" is a hostile class and NVML and
  `psutil` report bytes.
- Resolved — **performance marker source.** A stage's `performance` value comes from its tool's registry entry, never
  from the recipe, so a recipe cannot mark a restricted tool public (FR-001-28, docs DEC-0005 rule 5).
- Resolved — **performance-restricted licences.** DEC-0005 names NVIDIA SLA §8.9 (Kit, Isaac Sim, Replicator,
  ovrtx/ovstage, ovphysx) and TensorRT for RTX §2.13. Their SPDX references, including the package labels
  `LicenseRef-NvidiaProprietary` and `LicenseRef-NVIDIA-Omniverse`, form the restricted set; regular TensorRT is not in
  it (data-model §5.3).
- Resolved — **non-showcase producers.** Artefacts made by our own code or by libraries outside the 17 studio tools
  (for example `minephys`, `minehaulsim`) need a valid `producer.tool`; the registry therefore has `category:
  component` entries that the web tool map does not draw (FR-001-25).
- Resolved — **TypeScript generator.** json-schema-to-typescript 16.0.0 is chosen over Zod; reasons in
  [research.md](research.md) R2.
- Resolved — **generated Python target.** Generated models target Python 3.12 so that they import in the 3.12 NVIDIA
  environments as well as in the 3.14 root (FR-001-43).
- Resolved — **property-test generator.** `hypothesis-jsonschema` 0.23.1 (last upload 2024-02-28, classifiers up to
  3.11, drafts 4/6/7) is not adopted; strategies are written per document kind in the tests (data-model §8.3).
- Integration 2026-10-07: manifest inputs gain `kind: knowledge` (id = a `minephys` knowledge-table row id, a slug) so
  spec 020's UNVERIFIED-in-headline rule (FR-020-42) can name knowledge rows; FR-001-33 accepts them.
- Integration 2026-10-07: this spec is the single owner of `contracts/sources.schema.json`. The registry fields that
  spec 008-data-pipeline needs were moved here from its retired DC-008-01: `access`, file `kind`,
  `publisher_checksum`, `uncompressed_bytes` and `extract` (data-model §5.1, §5.1.1, new `relglob` pattern in §1.3);
  the account variable is `account.env_var` (the name `account_env` is dropped); `fallback` holds an ordered list of
  source ids (`fallback.sources`, replacing the single `fallback.source`), because a source may have a fallback chain
  (plan §8: ERA5 falls back to GHCNh, then to ISD). The 64 GiB size bound of spec 008 replaces 2⁵³−1 in FR-001-32;
  the other registry hostile classes of spec 008 (fallback ids, mixed share-alike files) and those of the new fields
  are FR-001-52 (task T-001-024). Spec 008 now only consumes the schema (FR-008-01, FR-008-02).
- Integration 2026-10-07: the manifest stage record (data-model §2.3, rule 7 of §2.9) gains the status `not_run`, the
  `reason` field and the error class `lock-not-held`, matching spec 002's stage result (FR-002-60…63); no
  requirement text of this spec changes (FR-001-10 cites data-model §2).
- Integration 2026-10-07: "a tool marked done needs ≥ 1 artefact" has one owner, spec 019-web-studio (FR-019-33, the
  CI and UI honesty check, using this spec's manifest field `producer.tool`); its converse (`not-yet-run` while an
  artefact names the tool) moved there too (FR-019-43). FR-001-27 is struck; its remaining registry-only clause
  (evaluated-not-adopted reason and docs page) is FR-001-53 (task T-001-031).
- Integration 2026-10-07: every `thresholds.yaml` key this spec proposes is marked "proposed key, pending maintainer
  approval" and compiled with the other specs' proposals for the maintainer; lane-gate keys are consolidated as
  `lane_gate.*` and budget keys as `budgets.*`.

## 9. Changes (only for features that modify earlier behaviour)

### ADDED Requirements
- FR-001-01 … FR-001-53 (as listed in §3; FR-001-27 retired), P-001-01 … P-001-08, NFR-001-01 … NFR-001-05, SC-001-01,
  DC-001-01 … DC-001-08.

### MODIFIED Requirements
- `contracts/capabilities.schema.json` (no earlier requirement ID): gains the bounds of data-model §6 (probe-name
  length, probe count, version, note, GPU-name lengths). Every report `run_bench.public_view` can produce today stays
  valid (FR-001-35).
- `studio/bench/run_bench.py` (no earlier requirement ID): writes `studio/capabilities.json` and the local report with
  `allow_nan=False` and without a byte-order mark (FR-001-07); a probe returning a non-finite metric is reported as
  `fail` with the error "non-finite metric <name>" instead of writing invalid JSON (FR-001-37).

### REMOVED Requirements
- (none)

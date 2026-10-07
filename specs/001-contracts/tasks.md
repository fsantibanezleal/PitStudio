# Tasks 001 — Contracts
Format: `- [ ] T-NNN-xxx [US-NNN-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/001-contracts/tests.lock <files>`).

## Phase 1 — Setup

- [ ] T-001-001 [US-001-1] (DC-001-01, DC-001-02, DC-001-03, DC-001-04, DC-001-05, FR-001-01, FR-001-02, FR-001-03, FR-001-04) schema + generated types, step 1: write `contracts/{manifest,recipe,tools,sources}.schema.json` from data-model §1–5 and tighten `capabilities.schema.json` (§6); tests meta-validate each schema, walk every object subschema for closure, compile every pattern with `re` and pydantic-core (a seeded lookahead pattern must be rejected), and validate hostile digests, timestamps and URLs with the optional format-checker modules blocked — test: tests/contract/test_t_001_001_schemas.py
- [ ] T-001-002 [US-001-3] (DC-001-06, DC-001-07, FR-001-40, FR-001-41, FR-001-42, FR-001-43, FR-001-44, FR-001-46, NFR-001-02, NFR-001-04) schema + generated types, step 2: validate the generator dependencies before feature code (add json-schema-to-typescript 16.0.0 with `pnpm add -D`; prove the datamodel-code-generator 0.83.0 options of data-model §7.1 give byte-identical output twice and on Windows and Linux), then write `tools/gen_types.py`, `web/scripts/gen-types.mjs` (`pnpm gen:types [--check]`), commit the generated modules, and add both `--check` steps to `.github/workflows/ci.yml`; tests cover drift detection (seeded one-character edit, orphan file, missing file), unsupported constructs (`prefixItems`, `$dynamicRef`, remote `$ref`) leaving committed files unchanged, import on Python 3.12 and 3.14, type-only TS output, and `@ts-expect-error` fixtures — test: tests/contract/test_t_001_002_generated_types.py, web/src/contracts/generated.test.ts
- [ ] T-001-003 [US-001-2] (FR-001-05, FR-001-06, FR-001-07, FR-001-08) `pitstudio.contracts.io` and `validate`: strict JSON and YAML loaders, deterministic writer, lazy sorted validation errors without absolute paths — test: tests/unit/test_t_001_003_loaders.py
- [ ] T-001-004 (DC-001-08, NFR-001-03) conformance corpus `tests/contract/fixtures/` with `index.json` covering every applicable cell of data-model §8.2 and one valid example per document kind; shared Hypothesis strategies `tests/contract/strategies.py` — test: tests/contract/test_t_001_004_corpus_coverage.py

## Phase 2 — US-001-1 (P1) Machine-checked provenance

- [ ] T-001-010 [US-001-1] (FR-001-10, FR-001-11, FR-001-12, FR-001-14, FR-001-16, FR-001-17) manifest kinds, artefact fields, asset-host rules, the local-only scrub, publication preconditions and the encoder record, each with valid and hostile fixtures — test: tests/contract/test_t_001_010_manifest_schema.py
- [ ] T-001-011 [US-001-1] (FR-001-13, P-001-01, P-001-02, P-001-03) `pitstudio.contracts.lane.lane_of` and the checker's lane rule: boundary table, monotonicity, unit-change invariance, disjunction symmetry, hostile measurements (negative, non-finite, missing) — test: tests/property/test_t_001_011_lane_gate.py
- [ ] T-001-012 [US-001-1] (FR-001-18, FR-001-19, P-001-04) `pitstudio.contracts.licence.licence_class_of` and the share-alike / reference-only rules: rank table, permutation invariance, idempotence, monotonicity, associativity, unknown class rejected — test: tests/property/test_t_001_012_licence_class.py
- [ ] T-001-013 [US-001-1] (FR-001-15) privacy scan of every string in committed manifests (drive letters, UNC, POSIX roots, `file:/`, host, user and home of the checking process); scrubbed `<repo>/` and `~/` forms allowed — test: tests/contract/test_t_001_013_privacy.py
- [ ] T-001-014 [US-001-1] (FR-001-20) served-file digest and size check for git-hosted and release-hosted artefacts; the `pages.yml` step that runs it before upload — test: tests/contract/test_t_001_014_served_sha.py

## Phase 3 — US-001-2 (P1) Inputs rejected before work starts

- [ ] T-001-020 [US-001-2] (FR-001-21, FR-001-22, FR-001-23, FR-001-24) recipe document, stage-to-environment binding, the hostile values of data-model §3.4 and the job request of §3.5 (inline recipes rejected) — test: tests/contract/test_t_001_020_recipe_schema.py
- [ ] T-001-021 [US-001-2] (FR-001-25, FR-001-26, FR-001-28) tool-registry schema and the committed `studio/tools.yaml` (20 studio tools of data-model §4.3 plus components), literal versions rejected, lock references resolved against lock fixtures, performance-restricted licences forced to `local-only` — test: tests/contract/test_t_001_021_tools_registry.py
- [ ] T-001-022 [US-001-2] (FR-001-31, FR-001-32) source-registry schema, the committed `data/sources.yaml` (empty list and the updated example comment with `spdx` / `licence_url` / `licence_class`), the (SPDX, kind) → class table, credential-like values and URLs rejected — test: tests/contract/test_t_001_022_sources_registry.py
- [ ] T-001-024 [US-001-2] (FR-001-52) source-registry fields read by `s00_download` (spec 008): access modes, ordered fallback sources, file kinds, publisher checksums, archive `extract` patterns (`relglob`) and caps, mixed share-alike files; one hostile fixture per class — test: tests/contract/test_t_001_024_sources_download_fields.py

## Phase 4 — US-001-5 (P2) The capability report stays honest

- [ ] T-001-023 [US-001-5] (FR-001-35, FR-001-36, FR-001-37) capability bounds; every `run_bench.public_view` output of the existing samples still valid; non-finite probe metrics become `fail` and both files parse with a strict JSON parser; `allow_nan=False` writer — test: tests/contract/test_t_001_023_capabilities.py

## Phase 5 — US-001-4 (P1) Honesty rules across files

- [ ] T-001-030 [US-001-4] (FR-001-50, FR-001-51, NFR-001-01, SC-001-01) `tools/check_contracts.py`: document discovery (data-model §8.1), exit codes 0/1/2, findings without tracebacks for unreadable, malformed, out-of-repo symlinked and unknown files, the scale fixture timed ≤ 30 s, CI step in the python job — test: tests/unit/test_t_001_030_check_contracts.py
- [ ] T-001-031 [US-001-4] (FR-001-53, FR-001-29, FR-001-33) cross-file rules: evaluated-not-adopted reason and docs page, producer tool and environment vs registry, manifest inputs vs sources and same-run artefacts, unpinned sources in published runs — test: tests/contract/test_t_001_031_cross_file.py

## Phase 6 — US-001-3 (P1) Types that cannot drift: properties

- [ ] T-001-040 [US-001-3] (P-001-05, P-001-07, P-001-08) serialisation round trip, YAML ↔ JSON syntax invariance with RFC 8785 canonical bytes (§3.2.4 example and Appendix B samples as fixed vectors), validation determinism across runs and key orders — test: tests/property/test_t_001_040_roundtrip.py
- [ ] T-001-041 [US-001-3] (P-001-06, FR-001-45) generated-model agreement with the JSON Schema validator over the corpus; every trust boundary of data-model §7.3 calls `validate` (call spy) — test: tests/contract/test_t_001_041_agreement.py

## Phase 7 — Polish and hostile review

- [ ] T-001-090 (NFR-001-05) mutation run on `src/pitstudio/contracts/` (lane gate, licence lattice, loaders, JCS); record the score and fail below 0.80 — test: tests/contract/test_t_001_090_mutation_score.py
- [ ] T-001-091 independent review of the diff against this spec (every FR/P has a locked test that names it; corpus covers data-model §8.2); append tasks for gaps

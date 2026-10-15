# Research 001 — Contracts
Spec: ./spec.md

Decisions taken while specifying the contracts, each with the alternatives considered and the evidence read on
2026-10-06/07. Local checks were run in the root environment (`uv.lock`: jsonschema 4.26.0, pydantic 2.13.5, PyYAML
6.0.3, datamodel-code-generator 0.83.0); they observe library behaviour and are not tests of PitStudio code.

## R1. Validator: JSON Schema 2020-12 with Python `jsonschema` 4.26.0

- Already locked in the root project and used by `tests/contract/test_capabilities_contract.py`
  (`Draft202012Validator`, `FormatChecker`).
- **Formats are not a safety net.** The python-jsonschema documentation states that format checking is not enforced by
  default and that "if a dependency is not installed when using a checker that requires it, validation will succeed
  without throwing an error"; `date-time` needs `rfc3339-validator`, `uri` and `uri-reference` need `rfc3987` or
  `rfc3986-validator` [1]. None is in the root lock. Decision: every safety-relevant string is constrained by `pattern`
  (FR-001-04); `format` stays an annotation.
- **Non-finite numbers pass.** Locally, `Draft202012Validator({"type": "number"}).is_valid(float("nan"))` is `True`,
  and `json.loads("[NaN, Infinity]")` returns `[nan, inf]`; the standard `json.dumps` writes `NaN` unless
  `allow_nan=False`. Browsers' `JSON.parse` rejects these tokens (ECMA-404 has no NaN). Decision: the loader rejects
  them before validation and every writer uses `allow_nan=False` (FR-001-05, FR-001-07, FR-001-37).
- **Duplicate keys pass.** `json.loads('{"a":1,"a":2}')` returns `{"a": 2}` silently. Decision: the loader uses
  `object_pairs_hook` to reject duplicates (FR-001-05).
- **Booleans are not integers** in `jsonschema` (`{"type": "integer"}` rejects `True`), so a `seed: true` is rejected by
  the schema itself; the hostile corpus pins this (data-model §3.4).

## R2. TypeScript types: json-schema-to-typescript 16.0.0 (chosen) vs Zod

| Option | Facts read | Assessment |
|---|---|---|
| **json-schema-to-typescript 16.0.0** | MIT; Node ≥ 16; unpacked 294,380 B; dependencies lodash, js-yaml, prettier, `@apidevtools/json-schema-ref-parser` [2]. README: every draft goes through its draft-4 model ("a `$schema` declaration does not change the output"); `$defs` handled like `definitions`; `const` → literal types; `prefixItems` ignored (`unknown[]`); `if`/`then`/`else` ignored; options `strictIndexSignatures`, `unreachableDefinitions`, `declareExternallyReferenced`, `format` [3] | **Chosen.** Output is type declarations only, so it adds 0 bytes to the bundle and cannot threaten the 200 KB initial-JS budget (NFR-000-01, NFR-001-02). The JSON Schema stays the single runtime source of truth, validated in Python at the trust boundaries |
| Zod 4.6.5 (+ `z.fromJSONSchema`) | MIT; unpacked 6,140,311 B [4]. Docs: "The `z.fromJSONSchema()` function is experimental and is not considered part of Zod's stable API"; no statement of which drafts it supports [5] | Rejected: runtime code in the bundle; an experimental converter would make a second, runtime interpretation of the contract whose fidelity to 2020-12 is unstated |
| json-schema-to-zod 2.8.1 | ISC; converts JSON Schema to Zod source [6] | Rejected: same runtime cost; adds a translation layer whose 2020-12 coverage is not documented |

Consequences recorded in the spec: schemas avoid `prefixItems` (FR-001-46 makes the generator fail on it), use
conditionals only for cross-field rules (looser TS types are acceptable, FR-001-45), and the TS conformance test uses
`@ts-expect-error` fixtures (FR-001-44). Version pinned by the web lock when T-001-002 adds it with `pnpm add -D`.

## R3. Python types: datamodel-code-generator 0.83.0

- Already in the root `dev` group. Its `--help` (0.83.0, local) lists `--schema-version` with `2020-12`,
  `--output-model-type pydantic_v2.BaseModel`, `--target-python-version` up to 3.14, `--extra-fields
  {allow,ignore,forbid}`, `--disable-timestamp`, `--custom-file-header`, `--use-annotated` ("requires
  --target-python-version 3.11+"), `--field-constraints`, `--enum-field-as-literal`, and `--formatters
  {builtin,black,isort,ruff-check,ruff-format}` with the note that ruff formatters need the `ruff` extra. Decision:
  options of data-model §7.1; `--disable-timestamp` and a relative input path keep the output deterministic and
  path-free (NFR-001-04).
- **Target 3.12.** The 3.12 environments (`studio/isaac`, `studio/isaaclab`) cannot install the root project
  (`requires-python ==3.14.*`), and `studio/rtx` has neither pydantic nor jsonschema in its lock. Generated models
  target 3.12 so that any environment with pydantic can import them; the stage-side protocol of spec 002 stays
  standard-library only.
- **Regex dialect.** Locally, pydantic 2.13.5 refuses to build a validator for `^(?!\.)[a-z]+$`: "regex parse error …
  look-around, including look-ahead and look-behind, is not supported" (pydantic-core uses the Rust `regex` crate by
  default). A schema pattern with lookaround would therefore break the generated models at import. Decision:
  FR-001-03 (portable subset; checked by compiling every pattern with Python `re` and pydantic-core).

## R4. Canonical JSON: RFC 8785 (JCS)

RFC 8785 fixes property order (UTF-16 code units, §3.2.3), ECMAScript number serialisation (§3.2.2.3) and requires an
error on NaN/Infinity [7]. Its §3.2.4 example and Appendix B samples are published worked examples, used as the
oracle for canonical bytes (P-001-07; spec 002 cache keys). Alternatives: `json.dumps(sort_keys=True,
separators=(",", ":"))` (Python float `repr` differs from ECMAScript for exponents, e.g. `1e+23` vs `1e23`; key order
by code point differs from UTF-16 order outside the BMP) — rejected for digests that a TypeScript twin may have to
reproduce.

## R5. Property-test generation: hand-written strategies

`hypothesis-jsonschema` 0.23.1 was last uploaded on 2024-02-28, declares classifiers up to Python 3.11, and states that
drafts 04, 05 and 07 are "fully tested and working" [8]; 2020-12 is not claimed. Decision: per-kind Hypothesis
strategies in `tests/contract/strategies.py` (data-model §8.3).

## R6. YAML loading

Locally, PyYAML 6.0.3 `safe_load`:

- keeps the last of two duplicate keys (`a: 1\na: 2` → `{'a': 2}`);
- resolves YAML 1.1 implicit booleans (`yes`, `on`, `No` → `True`, `True`, `False`) [9];
- turns `2026-10-04` into `datetime.date` [10];
- accepts `.nan` and `.inf`;
- expands aliases (`b: *x` duplicates the anchored list), which is the mechanism of exponential "alias bomb" documents.

Decision: a `SafeLoader` subclass that refuses anchors, aliases, tags, duplicate and non-string keys and multiple
documents, removes the implicit boolean (except `true`/`false`) and timestamp resolvers, and rejects non-finite floats
(FR-001-06).

## R7. Licence identifiers and classes

- `DL-DE-ZERO-2.0` is an SPDX id ("Data licence Germany – zero – version 2.0") [11]. The other ids in data-model §5.2
  are SPDX list ids or `LicenseRef-` references recorded in the docs (`data-contract/sources-and-licences.md`).
- The lattice of data-model §5.4 encodes the docs rule "a derived artefact takes the most restrictive class of its
  inputs" (`data-contract/sources-and-licences.md`), with `own` as the floor because a derivative of public-domain or
  CC0 data is published under our own licence.
- The restricted set of data-model §5.3 follows docs DEC-0005 (SLA §8.9 for Kit, Isaac Sim, Replicator,
  ovrtx/ovstage, ovphysx; TensorRT for RTX §2.13; regular TensorRT not restricted).

## R8. Units and caps

- Lane gate in decimal bytes (25,000,000; 10,000,000): the stricter reading of "25 MB" and "10 MB" in the plan's §10.
- Git per-file limit 10,485,760 B: what `tools/check_repo.py` already enforces (`10 * 1024 * 1024`).
- Document caps (data-model §1.4) are about 10× the largest expected document: a 64-stage recipe with full fields is
  < 40 KB; a 2,000-artefact web index at ≈ 1.5 KB per record is ≈ 3 MB.

## Sources

1. python-jsonschema, "Schema Validation — Validating Formats". https://python-jsonschema.readthedocs.io/en/stable/validate/
2. npm registry, `json-schema-to-typescript` latest (16.0.0). https://registry.npmjs.org/json-schema-to-typescript/latest
3. json-schema-to-typescript README. https://raw.githubusercontent.com/bcherny/json-schema-to-typescript/master/README.md
4. npm registry, `zod` latest (4.6.5). https://registry.npmjs.org/zod/latest
5. Zod, "JSON Schema". https://zod.dev/json-schema
6. npm registry, `json-schema-to-zod` latest (2.8.1). https://registry.npmjs.org/json-schema-to-zod/latest
7. RFC 8785, *JSON Canonicalization Scheme (JCS)*, §3.2.2.3, §3.2.3, §3.2.4, Appendix B. https://www.rfc-editor.org/rfc/rfc8785.txt
8. PyPI, `hypothesis-jsonschema` (0.23.1). https://pypi.org/pypi/hypothesis-jsonschema/json
9. YAML 1.1 type repository, Boolean. https://yaml.org/type/bool.html
10. YAML 1.1 type repository, Timestamp. https://yaml.org/type/timestamp.html
11. SPDX License List, `DL-DE-ZERO-2.0`. https://spdx.org/licenses/DL-DE-ZERO-2.0.html

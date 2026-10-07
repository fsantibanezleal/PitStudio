# Quickstart 001 — Contracts
Spec: ./spec.md

How to use the contracts once spec 001 is built. The commands below are specified here and exist after the build
phase; today only `contracts/capabilities.schema.json` and its tests exist.

## Validate one document

```python
from pitstudio.contracts import ContractError, load_yaml, validate

try:
    recipe = load_yaml("studio/recipes/cases/a1.yaml", kind="recipe")   # syntax + hostile classes (FR-001-06)
except ContractError as e:
    print(e)                     # file, line, rule — never a partial object
else:
    errors = validate(recipe, "recipe")                                    # every violation, sorted (FR-001-08)
    for err in errors:
        print(err.pointer, err.keyword, err.message)
```

`load_json(path, kind=…)` does the same for JSON documents and rejects `NaN`, duplicate keys, a byte-order mark and
over-deep or oversized files (FR-001-05). Write documents only with `dump_json` (FR-001-07).

## Check the whole repository

```bash
uv run python tools/check_contracts.py          # 0 clean, 1 findings, 2 usage error (FR-001-50)
```

It validates every committed contract document (data-model §8.1) and recomputes what must never be declared by hand:
the lane of each artefact from its measurements, the licence class from its inputs, the local-only scrub, the tool
statuses against the published artefacts, the registry and source references and the privacy rules.

## Regenerate the types after a schema change

```bash
uv run python tools/gen_types.py                # Pydantic models → src/pitstudio/contracts/_generated/
cd web && pnpm gen:types                        # TypeScript types → web/src/contracts/generated/
uv run python tools/gen_types.py --check        # what CI runs (FR-001-42)
cd web && pnpm gen:types --check
```

Commit the schema and both generated folders in the same commit; CI fails on any drift.

## Add a field or a schema

1. Edit or add `contracts/<name>.schema.json` following data-model §1 (closed objects, portable patterns, `pattern`
   rather than `format`, caps).
2. Add at least one valid and one invalid fixture per applicable hostile class to `tests/contract/fixtures/` and list
   them in `index.json` (NFR-001-03).
3. Regenerate both type sets and run the checks above.
4. A new SPDX id, artefact kind, stage id or environment is a schema change: it needs the spec update first.

## Read a manifest

```python
from pitstudio.contracts import load_json, validate
from pitstudio.contracts.lane import lane_of
from pitstudio.contracts.licence import licence_class_of

index = load_json("web/public/assets/manifest.json", kind="manifest")
assert not validate(index, "manifest")
for a in index["artefacts"]:
    if "lane_measurements" in a:
        assert a["lane"] == lane_of(a["lane_measurements"])   # the measured lane (FR-001-13)
```

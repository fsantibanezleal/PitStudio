# contracts/

JSON Schema 2020-12 for every artifact that crosses a boundary (studio → pipeline → web, runner ↔ console).

| Schema | Status |
|---|---|
| `capabilities.schema.json` | active — validated by `tests/contract/test_capabilities_contract.py` |
| `manifest.schema.json`, `recipe.schema.json`, `tools.schema.json`, `sources.schema.json` | planned (specification phase, spec 001-contracts) |

Python (Pydantic) and TypeScript types will be **generated** from these files, never hand-written, and a CI job will
regenerate them and fail on drift. That generation step arrives with spec 001-contracts in the build phase.

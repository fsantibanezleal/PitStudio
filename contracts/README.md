# contracts/

JSON Schema 2020-12 for every artifact that crosses a boundary (studio → pipeline → web, runner ↔ console).

| Schema | Documents |
|---|---|
| `manifest.schema.json` | run manifests and the published web index (`kind: run` / `web-index`) |
| `recipe.schema.json` | recipes and the console job request (`#/$defs/job_request`) |
| `tools.schema.json` | the studio tool registry `studio/tools.yaml` |
| `sources.schema.json` | the data registry `data/sources.yaml` |
| `capabilities.schema.json` | the capability report `studio/capabilities.json` |

Python (Pydantic) and TypeScript types are **generated** from these files (`tools/gen_types.py`,
`pnpm gen:types`), never hand-written; CI regenerates them and fails on drift. `tools/check_contracts.py` runs the rules
a schema cannot state. This folder holds only these schemas and this README.

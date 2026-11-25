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
a schema cannot state.

The schemas of the area specs 004 to 020 sit beside them (one file per schema, the `$id` of each spec draft kept):
scene, physics, media, haulage, data, perception, slope, surrogates, fragmentation, sensors, robot learning, VLM, export,
planning and survey, case registry, studio and knowledge contracts. The 25 browser-engine input/output schemas are under
`engines/<id>.schema.json`. The spec drafts under `specs/NNN-*/contracts/` and their example corpora are the oracle of
the contract tests; a schema here is a promoted draft, restructured only where the generators need it (a reference with
sibling keywords becomes an `allOf`), never loosened.

Registry documents validated by these schemas: `studio/cases.yaml` (`tools/check_cases.py`), `studio/toolmap.yaml`,
`studio/methods.yaml`, `web/src/theory/figures.yaml` (`tools/check_figures.py`), published results bundles
(`tools/check_results.py`) and the knowledge bundle (`tools/build_knowledge.py`).

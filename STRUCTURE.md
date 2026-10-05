# Repository structure

Every area exists in every repository of this family; an area this product does not need is **dormant** and its
README says so. Update the table when an area becomes active.

| Area | Purpose | Status |
|---|---|---|
| `src/pitstudio/` | Slim core: contracts glue, manifest, lane gate, I/O (root uv project, `.venv`) | active |
| `studio/` | Local simulation studio: isolated uv environments per tool family (`studio/` 3.14, `studio/isaac/`, `studio/rtx/`, `studio/isaaclab/` 3.12), the capability bench (`studio/bench/`) and, from the build phase, recipes and stage code. Its GPU work never runs in CI (only pure helpers are unit-tested there) | active |
| `pipeline/` | Heavy lane (own uv project): download → synthesize → preprocess → feature_extraction → train → infer → evaluate → export | active |
| `data/` | Source registry (`sources.yaml`), dataset cards, tiny samples; raw/interim/processed are git-ignored | active |
| `models/` | Model cards + accepted run manifests; small final ONNX artifacts | active |
| `web/` | Web companion (React + Vite), deployed to GitHub Pages | active |
| `contracts/` | JSON Schemas for every cross-boundary artifact; Python/TypeScript types are generated from them (generation + drift check from the build phase) | active |
| `specs/` | Specifications: constitution, foundation, features, traceability | active |
| `tests/` | Unit, property, metamorphic, contract, parity, pipeline and GPU tests | active |
| `docs/` | The wiki | active |
| `scripts/` | Bootstrap and run scripts (PowerShell + POSIX shell) and figure generation | active |
| `tools/` | Repository checks used by CI and editor hooks | active |
| `manuscripts/` | A Quarto field guide (12 cases + studio walkthrough) and a technical report, the report only if the results support it | planned (after the data-and-models phase) |
| `api/` | Loopback studio console (FastAPI on 127.0.0.1): recipes, queue, runs, artefacts, telemetry. Never part of the public site | planned (dependencies locked in the root `api` extra; code in milestone M3) |
| `infra/` | Environment definitions (e.g. a CUDA container for Linux) | dormant |
| `deploy/` | Deployment notes beyond GitHub Pages | dormant |
| `requirements/` | Generated pip fallback files for users without uv | planned (generated and CI-validated from the build phase) |

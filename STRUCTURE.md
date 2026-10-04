# Repository structure

Every area exists in every repository of this family; an area this product does not need is **dormant** and its
README says so. Update the table when an area becomes active.

| Area | Purpose | Status |
|---|---|---|
| `src/pitstudio/` | Slim core: contracts glue, manifest, lane gate, I/O (root uv project, `.venv`) | active |
| `pipeline/` | Heavy lane (own uv project): download → synthesize → preprocess → feature_extraction → train → infer → evaluate → export | active |
| `data/` | Source registry (`sources.yaml`), dataset cards, tiny samples; raw/interim/processed are git-ignored | active |
| `models/` | Model cards + accepted run manifests; small final ONNX artifacts | active |
| `web/` | Web companion (React + Vite), deployed to GitHub Pages | active |
| `contracts/` | JSON Schemas for every cross-boundary artifact (types are generated) | active |
| `specs/` | Specifications: constitution, foundation, features, traceability | active |
| `tests/` | Unit, property, metamorphic, contract, parity, pipeline and GPU tests | active |
| `docs/` | The wiki | active |
| `scripts/` | Bootstrap and run scripts (PowerShell + POSIX shell) and figure generation | active |
| `tools/` | Repository checks used by CI and editor hooks | active |
| `manuscripts/` | Guides, manuals or papers about this work | dormant |
| `api/` | Optional local API over the same engine | dormant |
| `infra/` | Environment definitions (e.g. a CUDA container for Linux) | dormant |
| `deploy/` | Deployment notes beyond GitHub Pages | dormant |
| `requirements/` | Generated pip fallback files (validated in CI) | active |

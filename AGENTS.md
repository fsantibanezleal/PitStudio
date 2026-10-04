# AGENTS.md — how to work in PitStudio

Guide for AI coding agents (and humans) working in this repository. Keep it short; depth lives in `docs/` and `specs/`.

## What this repo is
PitStudio — Physical-AI simulation studio for open-pit mining: OpenUSD scenes, GPU physics, RTX sensors, synthetic data, trained models and an interactive web explorer. A real research product: real data (fetched, never re-hosted), validated synthetic
data, local pipelines and training (CPU or NVIDIA GPU), ONNX models, and a static web companion on GitHub Pages
(`https://fsantibanezleal.github.io/PitStudio/`). Read `README.md`, `STRUCTURE.md`, `docs/README.md`, `specs/constitution.md`.

## Commands
| Task | Command |
|---|---|
| Set up (Windows / Linux) | `scripts/bootstrap.ps1` / `scripts/bootstrap.sh` (checks tools, creates both venvs, picks cpu/cu126/cu130) |
| Core tests (CPU) | `uv run pytest -m "not gpu"` |
| Pipeline | `scripts/run_pipeline.ps1 --all` / `scripts/run_pipeline.sh --all` |
| Web dev / build | `cd web && pnpm dev` · `pnpm build` (base path `/PitStudio/`) |
| Web tests | `cd web && pnpm test && pnpm test:e2e` |
| Traceability | `python tools/trace.py --check` |
| Test-first integrity | `python tools/check_tdd.py` |
| Repo hygiene | `python tools/check_repo.py` |

## Non-negotiable rules
1. **Spec before code.** Every behaviour has a requirement ID in `specs/NNN-*/spec.md` (EARS). Change the spec first.
2. **Acceptance-test-first.** For each task `T-NNN-xxx`: write failing tests that reference its IDs
   (`@pytest.mark.req("FR-…")` / TS title `"FR-… · …"`), lock them (`python tools/lock_tests.py specs/NNN-*/tests.lock <files>`),
   commit `test(T-…): … [red]`; then implement without touching locked tests, commit `feat(T-…): … [green]`.
3. **Independent oracles.** Expected values come from analytical results, reference implementations, published values
   or hand calculation — never from running the code under test.
4. **Never weaken a test.** If a locked test is wrong, write it in `specs/test-change-requests.md` and stop the task.
5. **Contracts are generated.** Edit `contracts/*.schema.json`, then regenerate Python/TS types; never hand-edit generated files.
6. **Data honesty.** Third-party data is fetched by `pipeline` stages from `data/sources.yaml` (licence + sha256),
   never committed. Synthetic data is labelled and validated. Every number shown in the web app comes from a committed artifact.
7. **Static delivery.** The web app must work on GitHub Pages with no backend; every live feature has a baked fallback.
8. **Small, verified steps.** Run the relevant tests before every commit; Conventional Commits with task + requirement IDs.
9. **No secrets, no machine paths, no files > 10 MB, no Git LFS** (`tools/check_repo.py`).
10. **Ask before installing software on the maintainer's machine.** Project-local installs (`uv sync`, `pnpm install`) are fine.

## Layout (see STRUCTURE.md for active vs dormant areas)
`src/pitstudio/` core · `pipeline/` heavy lane (own uv project) · `data/` · `models/` · `web/` · `contracts/` ·
`specs/` · `tests/` · `docs/` · `manuscripts/` · `scripts/` · `tools/` · `api/` (optional local API) · `infra/` · `deploy/`.

# Contributing to PitStudio

Thanks for your interest. This is a research repository maintained by one person; issues and pull requests are welcome.

## Set up
- Windows: `scripts/bootstrap.ps1` · Linux/macOS: `scripts/bootstrap.sh`. They check that `uv`, Node and pnpm are
  present (they never install system software for you), create the core venv and the pipeline venv, and choose the
  PyTorch build (`cpu`, `cu126` or `cu130`) from your NVIDIA driver.
- Web: `cd web && pnpm install`.

## How changes are made
1. **Spec first.** Behaviour is specified in `specs/NNN-*/spec.md` with requirement IDs (EARS). Open an issue or a spec
   change before code.
2. **Tests first.** Failing tests referencing the requirement IDs are committed and locked (`[red]`), then the
   implementation makes them pass (`[green]`). Expected values come from an independent oracle.
3. **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) with the task id, e.g.
   `test(T-003-004): FR-003-01 failing acceptance test [red]`.
4. **Branches:** work on `task/<slug>` → PR into `develop` → release PR into `main` (deployed to GitHub Pages).
5. **Before a PR:** `uv run pytest -m "not gpu"`, `python tools/trace.py --check`, `python tools/check_tdd.py`,
   `python tools/check_repo.py`, and in `web/`: `pnpm check && pnpm build && pnpm test:e2e`.

## Adding a dataset
Add it to `data/sources.yaml` (URL, sha256, SPDX licence traced to the original publisher, attribution,
redistribution class), write a card in `data/cards/`, and extend the download stage. Never commit third-party data.

## Licence of contributions
Inbound = outbound: contributions are accepted under the repository's licences (code Apache-2.0; docs/data CC-BY-4.0).

## Conduct
See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

# Quickstart

> Clone PitStudio, install the core environment, run the CPU test suite, and build and serve the web app the way GitHub
> Pages serves it — no GPU needed. · Part of: [Guides](README.md) · Related:
> [set up the studio](set-up-the-studio.md) · [configuration](../reference/configuration.md) ·
> [CLI reference](../reference/cli.md)

## What and why

**Goal:** a working checkout in about fifteen minutes on any machine (Windows, Linux or macOS): the Python core with its
tests green, and the web companion built and served locally. This is the entry point for everything else. It needs no
GPU, no NVIDIA software and no accounts.

## Prerequisites

| Item | Version | How |
|---|---|---|
| git | any recent | system package or installer |
| uv | per-user install | see the uv documentation [1]; no administrator rights needed |
| Python | 3.14 for the core (`.python-version`, `requires-python = "==3.14.*"`) | `uv python install 3.14` — a uv-managed interpreter, never the Microsoft Store shim |
| Node.js | 24 (`web/.nvmrc`; `engines: node >=24`) | Node 24 is the active LTS until it enters maintenance on 2026-10-20; Node 26 becomes LTS on 2026-10-28 [2] and is also accepted |
| pnpm | 11.28.4, pinned in `web/package.json` (`packageManager`) | via Corepack, which ships with Node: `corepack enable`, or prefix commands with `corepack` |
| Disk | a few GB | the core and pipeline environments; the web `node_modules` |

## Steps

1. **Clone.**

   ```bash run
   git clone https://github.com/fsantibanezleal/PitStudio.git
   cd PitStudio
   ```

2. **Create the core environment.** The root project is Python 3.14 with `jsonschema`, `numpy`, `pydantic`, `pyyaml` and
   the companion library `minephys`, which is installed from its git repository and pinned to a commit in `uv.lock`.

   ```bash run
   uv sync --all-groups
   ```

3. **Run the CPU test suite** (GPU tests are marked `gpu` and skipped).

   ```bash run
   uv run pytest -m "not gpu"
   ```

4. **Run the repository checks** that CI runs: secrets, machine paths and file sizes; requirement traceability.

   ```bash run
   uv run python tools/check_repo.py
   uv run python tools/trace.py --check
   ```

5. **Install and build the web app.** The default build uses base path `/`.

   ```bash run
   cd web
   pnpm install
   pnpm build
   pnpm dev
   ```

   `pnpm dev` serves the app at `http://localhost:5173/`. `pnpm run check` runs Biome, route type generation,
   TypeScript and the Vitest unit tests.

6. **Build it the way Pages serves it**, under `/PitStudio/`. From **PowerShell**:

   ```powershell run
   cd web
   $env:BASE_PATH = "/PitStudio/"
   pnpm build
   pnpm serve
   ```

   From **Git Bash**, stop the shell from rewriting the path (see Troubleshooting):

   ```bash run
   cd web
   MSYS2_ENV_CONV_EXCL=BASE_PATH BASE_PATH=/PitStudio/ pnpm build
   MSYS2_ENV_CONV_EXCL=BASE_PATH BASE_PATH=/PitStudio/ pnpm serve
   ```

   `pnpm serve` mimics Pages at `http://localhost:4173/PitStudio/`: real files, `dir/` → `dir/index.html`, unknown paths
   → `404.html` with status 404.

7. **Optional: the pipeline CPU smoke** that CI runs (CPU PyTorch, sample data only).

   ```bash run
   cd pipeline
   uv sync --extra cpu --all-groups --locked
   uv run pytest -m "not gpu and not slow"
   ```

8. **Optional: the bootstrap scripts** do steps 2, 5 and 7 in one go. They never install system software: they check
   that `uv`, `node`, `pnpm` and `git` exist, create the core and pipeline environments, and pick the PyTorch build from
   the NVIDIA driver (driver ≥ 580 → `cu130`, ≥ 525 → `cu126`, otherwise `cpu`), then verify it with
   `scripts/verify_gpu.py`.

   ```powershell run deferred=P6
   ./scripts/bootstrap.ps1
   ```

   ```bash run deferred=P6
   ./scripts/bootstrap.sh
   ```

## Expected output

- `uv sync` ends without errors and creates `.venv/`.
- `pytest` ends with a summary line of the form `<n> passed` (the scaffold and contract tests; no failures, GPU tests
  deselected).
- `tools/check_repo.py` and `tools/trace.py --check` exit 0 and print nothing alarming.
- `pnpm build` ends with the postbuild line
  `postbuild: Pages layout ready; start page loads <n> scripts, <x> KB gzip (budget 200.0 KB)`.
- In the browser: the PitStudio header with seven sections (Explore, Cases, Studio, Theory, Methods, Results,
  Knowledge), each a stub page marked "Not built yet", the ⓘ view, EN/ES and the theme toggle. No gate appears unless
  you built with `ACCESS_PASSPHRASE` ([access gate](../web/access-gate.md)).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| The built site requests its assets under a `C:/Program Files/Git/...` prefix and every page is blank | Git Bash converts values that look like Unix paths (here `BASE_PATH=/PitStudio/`) into Windows paths when it starts a native program such as Node [3] | Build from PowerShell, or prefix the build and serve commands with `MSYS2_ENV_CONV_EXCL=BASE_PATH`, which exempts only that variable. Do not use `MSYS_NO_PATHCONV=1`: it also stops the conversion that the Corepack `pnpm` shim needs, and pnpm then fails with `Cannot find module 'C:\c\Program Files\…\pnpm.js'` |
| `pnpm: command not found` | Corepack shims are not enabled | `corepack enable`; if Node is installed system-wide and that needs elevation, run `corepack pnpm install` and `corepack pnpm build` instead |
| `uv sync` selects a Python other than 3.14 | No 3.14 interpreter known to uv | `uv python install 3.14` |
| An interpreter path contains `WindowsApps` | The Microsoft Store shim was picked | Install a uv-managed interpreter and keep `python-preference` on managed interpreters |
| `uv sync` fails fetching `minephys` | No network access to GitHub | `minephys` is a git dependency until its first PyPI release; allow access to `github.com` |
| `postbuild: initial JS budget exceeded` | The start page loads more than 200 KB of gzip JavaScript | Find the import that pulled a heavy library into the start page; heavy views must be lazy |
| `pnpm test:e2e` cannot find a browser | Playwright browsers are not installed | `pnpm exec playwright install chromium` |

## Assumptions and limits

- The quickstart exercises the scaffold only: the core library, contracts, checks and the web shell. No case, engine,
  model or simulation exists yet; they arrive in the build phase.
- It does not touch the GPU, even on a machine that has one (the bootstrap script only reads the driver version).

## In PitStudio

- CI runs the same steps on Ubuntu: `.github/workflows/ci.yml` (`python` job: `uv sync`, Ruff, mypy, pytest, trace,
  TDD replay, repository and docs checks, pipeline smoke; `web` job: install, check, build, e2e).
- Next: [set up the studio](set-up-the-studio.md) for GPU work, or [first recipe](first-recipe.md) once the runner
  exists.

## References

1. Astral, "uv documentation" (installation, `uv python install`, `uv sync`, `uv run`). https://docs.astral.sh/uv/reference/cli/
2. Node.js release schedule — v24 maintenance from 2026-10-20; v26 LTS on 2026-10-28. https://raw.githubusercontent.com/nodejs/Release/main/schedule.json
3. MSYS2, "Filesystem Paths" — automatic conversion of path-like arguments for native programs and how to exclude them. https://www.msys2.org/docs/filesystem-paths/

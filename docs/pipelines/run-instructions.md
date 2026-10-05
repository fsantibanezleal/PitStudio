# Run instructions

> The commands that run in this repository today, and the plan's commands that will exist once the build phase adds
> the runner, the stages and the recipes, each block tagged accordingly. · Part of: [Pipelines](README.md) · Related:
> [Quickstart](../guides/quickstart.md) · [Set up the studio](../guides/set-up-the-studio.md) ·
> [CLI reference](../reference/cli.md) · [Compute lanes](compute-lanes.md)

## What and why

PitStudio documents its commands before all of them exist. To keep the docs honest, every shell block carries one of
three tags:

| Tag | Meaning |
|---|---|
| `bash` | illustrative only |
| `bash run` | runs today in this repository |
| `bash run deferred=P6` | a command from the plan that exists after the build phase implements it |

A docs check (`tools/check_docs.py`) rejects any shell block without one of these tags.

## Prerequisites

- **uv**, **Node 24** with **pnpm** (through `corepack enable`) and **git**. The bootstrap scripts check for them and
  tell you what is missing; they never install system software.
- For GPU lanes: an NVIDIA driver (≥ 580 for the CUDA 13 lane, ≥ 525 for CUDA 12.6; [Compute lanes](compute-lanes.md)).
- For the NVIDIA studio environments: an RTX GPU, and your own acceptance of the NVIDIA software terms (the Isaac Sim
  pip packages read `OMNI_KIT_ACCEPT_EULA=YES` [1]).
- Optional accounts and acts (Hugging Face terms and a read token for Cosmos Reason 2, an OpenTopography key, a
  Copernicus CDS account, EGMS Explorer, elevated Nsight captures) are listed with their fallbacks in
  [Licences and maintainer acts](../studio/owner-acts-and-licences.md). Keys are read from environment variables and
  never stored in the repository.

## Environment variables

| Variable | Default | Used for |
|---|---|---|
| `PITSTUDIO_STORE` | a short path outside the repo, e.g. `C:\ps` on Windows | runner store: content-addressed cache, runs, queue, locks |
| `PITSTUDIO_DATA` | git-ignored `data/` subfolders of the repo | raw, external, synthetic, interim and processed data |
| `PITSTUDIO_MODELS` | git-ignored model folders of the repo | checkpoints, engines, model caches |
| `PITSTUDIO_TMP` | git-ignored `.tmp/` of the repo | scratch files, local bench reports |
| `GPU_LOCK_DIR` | a `gpu-locks` folder in the system temp directory | machine-wide GPU locks (`gpu0.compute`, `gpu0.nvenc`) and the `gpu0.hold` stop file, shared by every project on the machine |
| `PITSTUDIO_FFMPEG` | `ffmpeg` on `PATH` | path to the FFmpeg 8.1 executable used by the NVENC probe and encoding |

## Runs today

### Bootstrap

Creates the core and pipeline environments, picks the PyTorch build from the driver, verifies it, and installs the web
dependencies.

```bash run deferred=P6
scripts/bootstrap.sh            # Linux / macOS
pwsh -File scripts/bootstrap.ps1   # Windows
```

### Core environment and tests

```bash run
uv sync --all-groups --locked
uv run ruff check . && uv run ruff format --check .
uv run pytest -m "not gpu"
```

### Docs check

Links, forbidden internal references, shell-block tags and diagram rules:

```bash run
uv run python tools/check_docs.py
```

### Pipeline, CPU lane (the CI smoke)

```bash run
cd pipeline
uv sync --extra cpu --all-groups --locked
uv run pytest -m "not gpu and not slow"
```

### Web app

```bash run
cd web
pnpm install --frozen-lockfile
pnpm run check
pnpm run build
```

### Studio environments

The locks exist for every studio environment. Syncing the NVIDIA ones downloads tens of GB and implies accepting
NVIDIA's terms.

```bash run deferred=P6
uv sync --project studio --locked
uv sync --project pipeline/accel --locked
uv sync --project studio/isaac --locked
uv sync --project studio/rtx --locked
uv sync --project studio/isaaclab --locked
```

### Capability bench

Runs every probe whose environment is installed, under the machine-wide GPU lock, and updates
`studio/capabilities.json` ([Capabilities](../data-contract/capabilities.md)). It refuses to start (exit code 4)
while a `gpu0.hold` file exists, and exits with code 3 if another job holds the GPU.

```bash run deferred=P6
uv run --extra runner python studio/bench/run_bench.py              # all installed probes
uv run --extra runner python studio/bench/run_bench.py warp_newton  # one probe
```

## After the build phase

### The runner

The runner (`src/pitstudio/runner/`, root environment, extra `runner`) executes recipes as cached, locked, resumable
jobs ([Runner](../studio/runner.md)).

```bash run deferred=P6
uv run --extra runner studio plan studio/recipes/<case>.yaml        # dry run: DAG, cache hits, disk and VRAM estimates
uv run --extra runner studio run studio/recipes/<case>.yaml         # run a recipe
uv run --extra runner studio run studio/recipes/<case>.yaml --stage s30_train --force
uv run --extra runner studio queue ls
uv run --extra runner studio worker                                 # the single queue worker
uv run --extra runner studio status
uv run --extra runner studio gc --keep-pinned --keep-last 3
```

### Stages, benchmarks and publication

```bash run deferred=P6
uv run --extra runner studio bench env                              # capability probe
uv run --extra runner studio run studio/recipes/<case>.yaml --stage s62_accel
uv run --extra runner studio run studio/recipes/<case>.yaml --stage s64_bench
uv run --extra runner studio profile                                # torch.profiler / Warp timing; prints the Nsight command
uv run --extra runner studio publish <run_id>                       # bake a run into web artefacts + a run card
```

### The whole pipeline

```bash run deferred=P6
scripts/run_pipeline.sh --all       # Linux / macOS
pwsh -File scripts/run_pipeline.ps1 --all   # Windows
```

### Reproducing a case

Each case page ends with a "reproduce this" block; the general form is a recipe run followed by a publish, and the
manifests of the published run let you compare your SHA-256 digests and metrics with ours
([Reproduce a case](../guides/reproduce-a-case.md)).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `verify_gpu.py` prints `FAIL: expected cu130 …` | a CPU wheel or a driver below the lane's floor | re-run the bootstrap; check the driver version |
| a probe fails with "interpreter is the Microsoft Store shim" | a Python 3.12 environment picked the Windows Store alias | the 3.12 environments set `python-preference = "only-managed"`; install the interpreter with `uv python install 3.12` |
| Polygraphy loads `cudart64_12.dll` | a machine-wide CUDA 12 toolkit comes first through `CUDA_PATH` | the TensorRT probe points `CUDA_PATH` at the CUDA 13 runtime wheel; do the same in your shell |
| NVENC fails with "Driver does not support the required nvenc API version" | an FFmpeg 9.x build on an R580 driver | use FFmpeg 8.1 [2] |
| `GPU hold in …: … -- not starting` | a `gpu0.hold` file exists in `GPU_LOCK_DIR` | intended: GPU work is stopped machine-wide until the file is removed |
| `GPU lock … is held by another job` | another job holds `gpu0.compute` | wait; one heavy GPU job runs at a time |

## Assumptions and limits

- Commands are shown in POSIX shell syntax; on Windows they run unchanged in PowerShell except where a `.ps1` script is
  named.
- `bash run` blocks are listed by `uv run python tools/check_docs.py --list-run` for review; their success on a given
  machine still depends on that machine's driver, disk and network.
- Deferred commands follow the plan's runner design; their exact flags are fixed when the runner is implemented and the
  [CLI reference](../reference/cli.md) is updated with them.

## In PitStudio

- **Scripts today:** `scripts/bootstrap.ps1`, `scripts/bootstrap.sh`, `scripts/verify_gpu.py`,
  `studio/bench/run_bench.py`, `tools/check_docs.py`.
- **CI:** `.github/workflows/ci.yml` runs the core checks and the CPU pipeline smoke; `.github/workflows/pages.yml`
  builds and deploys the web app. No GPU work ever runs in CI.

## References

1. NVIDIA, *Isaac Sim Python installation* (6.0.0; `OMNI_KIT_ACCEPT_EULA`). https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/install_python.html
2. FFmpeg nv-codec-headers README (SDK 13.1 needs driver ≥ 610). https://raw.githubusercontent.com/FFmpeg/nv-codec-headers/master/README

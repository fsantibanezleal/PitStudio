# Configuration

> Every knob PitStudio reads: environment variables (data, model, temp and store folders, FFmpeg, the GPU lock
> directory, web build variables, tool caches), machine profiles, recipes, `params.yaml`, per-environment project
> files, thresholds and browser storage keys. · Part of: [Reference](README.md) · Related: [CLI](cli.md) ·
> [set up the studio](../guides/set-up-the-studio.md) · [environments](../studio/environments.md) ·
> [access gate](../web/access-gate.md)

## What and why

PitStudio keeps three things apart: **code** (in the repository), **machine facts** (in environment variables and a
machine profile), and **experiment choices** (in recipes and parameter files that are part of the cache key). Public
code never hard-codes a local path: every folder comes from a variable that defaults to a git-ignored folder in the
repository, so the same commit runs on any machine and nothing machine-specific leaks into a manifest.

## Environment variables

### Folders and tools

| Variable | Default when unset | Read by | Status |
|---|---|---|---|
| `PITSTUDIO_DATA` | the git-ignored `data/raw/`, `data/external/`, `data/interim/`, `data/processed/`, `data/synthetic/` folders of the repository | pipeline stages `s00`–`s20`, studio scene stages | planned |
| `PITSTUDIO_MODELS` | the git-ignored `models/checkpoints/` folder | training, export, acceleration | planned |
| `PITSTUDIO_TMP` | the git-ignored `.tmp/` folder at the repository root | `studio/bench/` (local reports under `bench/`), scratch work | **exists** (bench) |
| `PITSTUDIO_STORE` | `C:\ps` on Windows — a short path outside the repository, because Isaac Sim and synthetic-data paths get long; on other machines the profile names the store root | the runner: content-addressed cache, `runs/<run_id>/`, human-readable `views/`, queue database | planned |
| `PITSTUDIO_FFMPEG` | `ffmpeg` found on `PATH` | NVENC probe, `st56_encode` | **exists** (probe) |
| `GPU_LOCK_DIR` | `<system temp>/gpu-locks` | bench and runner: `gpu0.compute`, `gpu0.nvenc`, `gpu0.hold` | **exists** (bench) |

`GPU_LOCK_DIR` is **machine-wide on purpose**: every project on the machine that uses the GPU must point at the same
folder, so that two jobs never share the GPU. It holds:

| File | Meaning |
|---|---|
| `gpu0.compute` | exclusive lock for heavy GPU work (one job at a time) |
| `gpu0.nvenc` | lock for the video encoder; encoding can overlap CPU stages |
| `gpu0.hold` | a text file whose presence stops all GPU work on the machine; its content is the reason. Created and removed by the maintainer |

Locks use the operating system's file locking, so a crashed job cannot leave a permanent lock [1].

### Web build

| Variable | Default | Effect | Status |
|---|---|---|---|
| `BASE_PATH` | `/` | Vite `base` and the router `basename`; on Pages `/PitStudio/` (CI takes it from `actions/configure-pages`). Also read by `pnpm serve` and the e2e tests | **exists** |
| `ACCESS_PASSPHRASE` | unset → the gate is off | only its SHA-256 digest reaches the bundle ([access gate](../web/access-gate.md)); repository secret for deploys, `ci-demo-gate` in CI | **exists** |
| `SOURCE_DATE_EPOCH` | unset → today | build date in the footer, for reproducible builds | **exists** |
| `GITHUB_SHA` | unset → `git rev-parse --short=7 HEAD` | commit SHA in the footer | **exists** |
| `LIVE_URL` | — | target of `pnpm test:live` | **exists** |

On Windows, set `BASE_PATH` from PowerShell, or prefix `MSYS2_ENV_CONV_EXCL=BASE_PATH` in Git Bash, which otherwise rewrites
`/PitStudio/` as a Windows path ([quickstart](../guides/quickstart.md)).

### Tool caches (relocate them to a disk with room)

| Variable | Tool | Why set it |
|---|---|---|
| `HF_HOME` | Hugging Face hub (Cosmos Reason 2 weights, base models) | gigabytes of weights; keep them next to `PITSTUDIO_MODELS`, never in the repository |
| `TORCH_HOME` | PyTorch / torchvision downloaded weights | same |
| `UV_CACHE_DIR` | uv's package cache | Isaac Sim and PyTorch wheels are tens of GB |

### Other variables you may meet

| Variable | Context |
|---|---|
| `OMNI_KIT_ACCEPT_EULA` | Isaac Sim / Kit read it as acceptance of the NVIDIA EULA; it is set only by the person who accepts the terms, never by PitStudio's scripts [2] |
| `CUDA_PATH` | Polygraphy searches it first; a machine-wide CUDA 12 toolkit there breaks TensorRT 11 on CUDA 13. The TensorRT probe points it at the CUDA 13 runtime wheel ([TensorRT bench](../guides/tensorrt-bench.md)) |
| `PM_PACKAGES_ROOT` | kit-app-template's packman cache, outside the repository ([Composer review](../guides/composer-review.md)) |
| `MSYS2_ENV_CONV_EXCL` | Git Bash: environment variables exempt from POSIX-to-Windows path conversion (`BASE_PATH` for web builds). Prefer it to `MSYS_NO_PATHCONV=1`, which also breaks the Corepack `pnpm` shim |

## Machine profiles (planned)

Recipes never name machine paths or hardware. A profile supplies them:

| Field | Meaning |
|---|---|
| VRAM | GPU memory the guards budget against |
| power class | e.g. a power-limited laptop GPU vs a desktop or server GPU |
| GPU count | number of devices; locks are per device (`gpu0.*`, `gpu1.*`) |
| store root | where `PITSTUDIO_STORE` lives on that machine |
| CPU slots | parallel CPU stages allowed |
| enabled environments | which of `studio/`, `studio/isaac/`, `studio/rtx/`, `studio/isaaclab/`, `studio/reason/`, `pipeline/`, `pipeline/accel/` exist |

Two profiles are planned: `laptop-rtx5000ada` (the reference machine) and `linux-gpu` (a future Linux GPU host). CI
plans every recipe with `linux-gpu` against a fake GPU backend, so a profile switch is tested on every push
(FR-000-16). Planned location: `recipes/_profiles/<name>.yaml`.

## Recipes and `params.yaml` (planned)

| File | Holds | Validated by | Part of the cache key? |
|---|---|---|---|
| `recipes/<case>.yaml` | one case's stage DAG: stage ids, environments, inputs, parameters, resources, determinism class, retry policy, master seed | `contracts/recipe.schema.json` | yes (parameters and seed) |
| `params.yaml` (pipeline) | pipeline stage parameters: splits, seeds, model hyperparameters, export opset and IR version | the pipeline's parameter schema | yes, per stage |
| `studio/tools.yaml` | the studio tool registry: id, environment, licence class, ring, lane, status, what it produces | `contracts/tools.schema.json` | no (drives the web tool map) |
| `data/sources.yaml` | every real data source: URL, SHA-256, SPDX licence traced to the publisher, attribution, redistribution class | `contracts/sources.schema.json` | yes, via input digests |

The **cache key** of a stage is the SHA-256 of a canonical JSON of the stage id, its code digest, its environment's
lock-file digest, its parameters, its derived seed and its input digests ([first recipe](../guides/first-recipe.md)).

## Project files per environment (exist)

| File | Role |
|---|---|
| `pyproject.toml` + `uv.lock` (root, `studio/`, `studio/isaac/`, `studio/rtx/`, `studio/isaaclab/`, `pipeline/`, `pipeline/accel/`) | direct dependencies only; versions are written by the resolver, never by hand |
| `.python-version` | `3.14` for root, `studio/`, `pipeline/`, `pipeline/accel/`; `3.12` for `studio/isaac/`, `studio/rtx/`, `studio/isaaclab/` |
| `[tool.uv] python-preference = "only-managed"` | in the 3.12 environments: only uv-managed interpreters, never the Microsoft Store shim |
| `pipeline/pyproject.toml` extras `cpu`, `cu126`, `cu130` | mutually exclusive PyTorch builds (driver ≥ 525 → `cu126`, ≥ 580 → `cu130`) |
| `web/.nvmrc` (`24`), `web/package.json` (`packageManager: pnpm@11.28.4`, `engines.node >=24`), `web/pnpm-lock.yaml` | Node and pnpm versions |
| `specs/000-foundation/thresholds.yaml` | every numeric gate (below); values only ratchet up, and lowering one needs a spec change |
| `REUSE.toml`, `LICENSES/` | licence of every path |

### Thresholds (`specs/000-foundation/thresholds.yaml`)

| Key | Value | Meaning |
|---|---|---|
| `coverage.branch_core_min` | 0.85 | branch coverage of the core |
| `mutation.numerical_core_min` | 0.80 | mutation score of numerical code |
| `property_tests.ci_examples_per_test` | 200 | Hypothesis examples per property in CI |
| `data.tstr_over_trtr_min` | 0.90 | synthetic-trained over real-trained score where real labels exist |
| `data.c2st_auc_real_vs_synthetic_max` | 0.60 | classifier two-sample test, tabular / 1-D |
| `models.onnx_cpu_fp32` | rtol 1e-3, atol 1e-5, max_abs 1e-4 | export parity |
| `models.quantized_task_metric_delta_max_pp` | 1.0 | reduced-precision tolerance |
| `models.corruption_relative_drop_max_pp_at_severity_2` | 10 | robustness |
| `web.wasm_fp32_max_abs` / `web.webgpu_fp32_max_abs` / `web.fp16_max_abs` | 1e-4 / 1e-3 / 1e-2 | browser parity per system class |
| `web.top1_agreement_min` | 0.995 | classifier parity in the browser |
| `web.initial_js_gzip_kb_max` | 200 | initial JavaScript |
| `web.model_file_mb_target` / `web.model_file_mb_hard_cap` | 25 / 95 | model file sizes |
| `web.site_total_mb_max` | 500 | site total |

## Browser storage and URL parameters (exist)

| Key | Storage | Meaning |
|---|---|---|
| `?lang=en` / `?lang=es` | URL | language for this visit; beats the stored choice |
| `fsl:lang` | `localStorage` | stored language (shared by the maintainer's apps on the same origin) |
| `fsl:theme` | `localStorage` | `system`, `light` or `dark` |
| `PitStudio:access` | `sessionStorage` | the gate's digest once the passphrase matched; cleared when the tab closes |

## Assumptions and limits

- Defaults that point inside the repository are git-ignored; nothing under them is ever committed.
- Planned variables and files may gain fields in their specs; this page follows them.

## In PitStudio

- Code that reads variables today: `studio/bench/run_bench.py`, `studio/bench/_common.py`, `studio/bench/probe_nvenc.py`,
  `web/build-info.ts`, `web/vite.config.ts`, `web/react-router.config.ts`, `web/scripts/postbuild.mjs`.

## References

1. Microsoft, `LockFileEx` — locks are released by the operating system when the process terminates. https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex
2. NVIDIA, "Isaac Sim Python install" — EULA acceptance at first import or via `OMNI_KIT_ACCEPT_EULA`. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_python.html

# CLI reference

> Every command PitStudio offers: what exists today (the capability bench, bootstrap and verification scripts,
> repository tools, web scripts) and what the build phase adds (the `studio` runner CLI and the pipeline runner), with
> arguments, outputs and exit codes. · Part of: [Reference](README.md) · Related: [runner](../studio/runner.md) ·
> [pipeline stages](../pipelines/pipeline-stages.md) · [studio stages](../pipelines/studio-stages.md) ·
> [configuration](configuration.md)

## What and why

PitStudio has one rule for GPU work: it goes through the runner, which holds the machine-wide GPU lock, applies the
guards and writes a manifest. The commands below are the entry points to that runner and to the repository's checks.
Status is marked per command; nothing marked *planned* exists in the repository yet.

## Existing commands

### `studio/bench/run_bench.py` — capability probe

Runs capability probes one at a time, each in its own environment, under the machine-wide GPU lock, with NVML telemetry,
and writes the results. Needs the root project's `runner` extra.

```bash run
uv run --extra runner python studio/bench/run_bench.py --help
```

| Argument | Default | Meaning |
|---|---|---|
| `probes …` | all | subset of `warp_newton`, `torch_ort`, `tensorrt`, `nvenc`, `ovrtx`, `isaacsim`, `isaaclab` |
| `--timeout SECONDS` | `1800` | per-probe timeout; a timeout marks the probe `fail` |
| `--no-write` | off | do not update `studio/capabilities.json`; the local report is still written |

| Probe | Environment it runs in | Script today |
|---|---|---|
| `warp_newton` | `studio/` | `probe_warp_newton.py` |
| `torch_ort` | `pipeline/` with `--extra cu130` | `probe_torch_ort.py` |
| `tensorrt` | `pipeline/accel/` | `probe_tensorrt.py` |
| `nvenc` | `studio/` (FFmpeg from `PITSTUDIO_FFMPEG` or `PATH`) | `probe_nvenc.py` |
| `ovrtx` | `studio/rtx/` | not yet (reports `skip`) |
| `isaacsim` | `studio/isaac/` | not yet (reports `skip`) |
| `isaaclab` | `studio/isaaclab/` | not yet (reports `skip`) |

Pre-flight per probe: the environment's `.venv` must exist, at least 4,096 MB of VRAM must be free, and the GPU must be
at or below 80 °C; otherwise the probe is skipped with the reason.

| Output | Content | Committed? |
|---|---|---|
| `studio/capabilities.json` | date, GPU model, driver, and per probe: status, versions, publishable metrics and telemetry; licence-restricted metrics replaced by "measured locally, not published (licence)"; local paths scrubbed | yes (validated by `contracts/capabilities.schema.json`) |
| `$PITSTUDIO_TMP/bench/bench-<UTC time>.json` | everything, incl. restricted metrics and full telemetry | no |

| Exit code | Meaning |
|---|---|
| 0 | no probe failed (passes and skips) |
| 1 | at least one probe failed |
| 2 | usage error (for example an unknown probe name) |
| 3 | another job holds `gpu0.compute` in `GPU_LOCK_DIR` |
| 4 | a `gpu0.hold` file in `GPU_LOCK_DIR` stops all GPU work |

### Bootstrap and verification

| Command | What it does | Status |
|---|---|---|
| `scripts/bootstrap.ps1` (PowerShell 7+) / `scripts/bootstrap.sh` | checks for `uv`, `node`, `pnpm`, `git` (never installs system software), runs `uv sync --all-groups`, creates the pipeline environment with the PyTorch build chosen from the driver (≥ 580 → `cu130`, ≥ 525 → `cu126`, else `cpu`), runs `verify_gpu.py`, installs the web dependencies | exists |
| `scripts/verify_gpu.py --expect cpu\|cu126\|cu130` (inside `pipeline/`) | prints the torch version, CUDA build and availability; exits 1 if a CUDA build was expected but torch cannot use CUDA or the CUDA version differs | exists |

It imports torch and calls `torch.cuda.is_available()`. On a CUDA build of torch that initialises the GPU driver, so
it counts as GPU work and is checked when the GPU is available:

```bash run deferred=P6
cd pipeline && uv run python ../scripts/verify_gpu.py --expect cpu
```

### Repository tools

| Command | What it does | Exit |
|---|---|---|
| `uv run python tools/release.py [--apply] [--version X.YY.ZZZ]` | computes the next `X.YY.ZZZ` from Conventional Commits; `--apply` updates `VERSION`, `pyproject.toml`, `web/package.json`, `CITATION.cff`, `CHANGELOG.md`, writes `release-notes.md`, commits and tags ([release and cite](../guides/release-and-cite.md)) | 1 nothing to release; 2 invalid version |
| `uv run python tools/trace.py [--check]` | regenerates `specs/traceability.md` and `specs/requirements.index.json`; `--check` fails on orphans or unknown/retired requirement IDs | 1 on findings |
| `uv run python tools/check_tdd.py [--rev-range A..B] [--replay]` | test-first integrity over git history: every `[green]` has an earlier `[red]`, locked tests unchanged, no added skips without approval; `--replay` checks that `[red]` tests failed at their commit | 1 on violations |
| `uv run python tools/check_repo.py` | scans tracked files for secrets, machine paths, files > 10 MB and template residue | 1 on any finding |
| `uv run python tools/lock_tests.py <specs/NNN-…/tests.lock> <test files…>` | appends SHA-256 locks for test files after their `[red]` commit (append-only) | 2 on usage error |

```bash run
uv run python tools/check_repo.py
uv run python tools/trace.py --check
```

### Web scripts (`web/package.json`)

| Script | What it does |
|---|---|
| `pnpm dev` | development server at `http://localhost:5173/` |
| `pnpm build` | production build + `scripts/postbuild.mjs` (Pages layout, `404.html`, initial-JS budget ≤ 200 KB gzip) |
| `pnpm serve` | serves `build/client` like Pages at `BASE_PATH` (default port 4173) |
| `pnpm run check` | Biome + route type generation + TypeScript + Vitest |
| `pnpm test` | Vitest unit tests |
| `pnpm typecheck` / `pnpm lint` / `pnpm format` | type check / Biome CI / Biome write |
| `pnpm test:e2e` | Playwright against the production build (deep links, 404, gate, theme, language, ⓘ, axe) |
| `pnpm test:live` | Playwright against the deployed site (`LIVE_URL`) |

```bash run
cd web && pnpm install && pnpm run check
```

## Planned: the `studio` runner CLI

The runner lives in `src/pitstudio/runner/` (root project, Python 3.14, extra `runner`) and is invoked as `studio`.
Flags below follow the runner design; the exact syntax is fixed by spec `002-runner`.

| Command | Purpose |
|---|---|
| `studio bench env` | run the capability probe and update the committed `studio/capabilities.json` (wraps `run_bench.py`) |
| `studio plan <recipe> [--profile <name>]` | dry run: the DAG, cache hits and misses, disk and VRAM estimates against a machine profile |
| `studio run <recipe> [--stage <id>] [--force] [--profile <name>]` | run a recipe or selected stages; cached stages are skipped unless `--force` |
| `studio publish <run_id>` | bake a run into web artefacts plus a run card, with manifest entries and SHA-256 |
| `studio profile <recipe> --stage <id>` | `torch.profiler` / Warp timing for one stage; prints the Nsight Systems command for an elevated shell |
| `studio gc [--keep-pinned] [--keep-last N]` | mark-and-sweep of the store from pinned manifests |

```bash run deferred=P6
uv run --extra runner studio bench env
uv run --extra runner studio plan studio/recipes/cases/a1.yaml --profile linux-gpu
uv run --extra runner studio run studio/recipes/cases/a1.yaml --stage s30_train
uv run --extra runner studio publish <run_id>
uv run --extra runner studio profile studio/recipes/cases/a3.yaml --stage st50_physics
uv run --extra runner studio gc --keep-pinned --keep-last 3
```

Behaviour common to every GPU command: refuse while `gpu0.hold` exists; take `gpu0.compute` (exclusive) or
`gpu0.nvenc`; pre-flight guards for free VRAM, disk, temperature and capabilities; stages run as
`uv run --project <env> --frozen …` in a Windows job object or a Linux process group; 1–4 Hz NVML telemetry; one
manifest per run. In CI the same `studio plan` runs for every recipe with the `linux-gpu` profile against a fake GPU
backend.

## Planned: the pipeline runner

The pipeline (`pipeline/`, Python 3.14) runs its stages in order or one at a time.

| Command | Purpose |
|---|---|
| `scripts/run_pipeline.ps1 --all` / `scripts/run_pipeline.sh --all` | every stage in order |
| `scripts/run_pipeline.ps1 --stage <id>` / `scripts/run_pipeline.sh --stage <id>` | one stage |

Stages: `s00_download` → `s05_synthesize` → `s10_preprocess` → `s20_feature_extraction` → `s30_train` → `s40_infer` →
`s50_evaluate` → `s60_export`, then in `pipeline/accel/` `s62_accel` → `s64_bench`
([pipeline stages](../pipelines/pipeline-stages.md)).

```bash run deferred=P6
scripts/run_pipeline.sh --all
scripts/run_pipeline.sh --stage s60_export
```

## Planned: studio stage ids (for `--stage`)

| Lane | Stage ids |
|---|---|
| `studio/` (3.14) | `st10_terrain`, `st20_pit_design`, `st30_assets`, `st40_compose`, `st45_validate`, `st50_physics`, `st56_encode` |
| `studio/isaac/` (3.12) | `st52_rtx_render`, `st54_vehicles`, `st55_sdg`, `st57_rain_lidar` |
| `studio/rtx/` (3.12) | `st53_sensors` |
| `studio/isaaclab/` (3.12) | `st60_il_train`, `st61_il_mpm_eval` |
| `studio/kit/` | `st58_kit_capture`, `st45b_kit_validate` |
| `studio/reason/` | `st59_reason_bench`, `st59a_vqa`, `st59b_plausibility`, `st59c_captions` |
| optional | `st58b_capture_splat` (COLMAP → Brush → SPZ) |

## Planned: the local console

The console is a FastAPI app bound to `127.0.0.1` only, with `/health`, recipes, the queue, runs, artefacts and an SSE
telemetry stream; `POST /jobs` is validated against the recipe schema, so hostile input gets a 4xx. Its web entry is
excluded from the Pages artifact. It uses the root project's `api` extra (FastAPI, Uvicorn); the launch command and
port variable are fixed by spec `003-console` ([console](../studio/console.md)).

## Assumptions and limits

- Planned commands may change name or flags in their specs; this page is updated with them.
- Every GPU command assumes a correctly set `GPU_LOCK_DIR`; two projects with different lock directories on one
  machine would not see each other's locks.

## In PitStudio

- Code: `studio/bench/`, `scripts/`, `tools/`, `web/package.json` (exist); `src/pitstudio/runner/`,
  `scripts/run_pipeline.*`, the console (build phase).
- Specs: `002-runner`, `003-console`, `008-data-pipeline`, `016-export-acceleration`.

## References

None external; this page documents PitStudio's own interfaces.

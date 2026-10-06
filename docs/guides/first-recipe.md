# First recipe

> Write a runner recipe, plan it as a dry run, run it under the GPU lock and guards, read its manifest and telemetry,
> see the content-addressed cache at work on a re-run, and switch machine profiles. · Part of: [Guides](README.md) ·
> Related: [runner](../studio/runner.md) · [studio stages](../pipelines/studio-stages.md) ·
> [recipe and tool registry](../data-contract/recipes-and-tool-registry.md) · [CLI reference](../reference/cli.md)

## What and why

**Goal:** understand the one way GPU and studio work runs in PitStudio. A **recipe** is a YAML file that describes, for
one case, a DAG of stages with their parameters and a master seed. The **runner** (`src/pitstudio/runner/`, about
1,500 lines by design) plans the DAG, skips stages whose outputs are already in the cache, runs the rest one GPU job at
a time in their own environments, and writes a manifest for every run
([DEC-0002](../architecture/decisions/DEC-0002-in-repo-runner.md)). Nothing heavy runs outside it: the runner holds the
machine-wide lock `gpu0.compute` (and `gpu0.nvenc` for encoding) and refuses to start while a `gpu0.hold` file exists
(a product-level requirement of the foundation spec, written in the specification phase).

**Status:** the runner, its CLI and the recipe schema are written in the build phase. Every command below is
`deferred=P6`; the recipe is illustrative.

## Prerequisites

- [Quickstart](quickstart.md) done; for GPU stages, [set up the studio](set-up-the-studio.md) done and the capability
  probe run.
- `PITSTUDIO_STORE` set to a short path on a disk with room (default on Windows: `C:\ps`); `GPU_LOCK_DIR` set
  machine-wide ([configuration](../reference/configuration.md)).

## Steps

1. **Write the recipe.** Recipes live in `studio/recipes/cases/` and are validated against `contracts/recipe.schema.json`; a recipe
   that does not validate is refused before anything runs. The first recipes are the vertical slice: cases A1 and C1 on
   the open lane only.

   ```yaml
   # studio/recipes/cases/c1.yaml — illustrative; field names follow the runner design, the schema is fixed in the build phase
   recipe: c1-slope
   case: C1
   seed: 1234                      # master seed; each stage gets hash(master, stage id, shard)
   stages:
     - id: s00_download            # fetch the real slope-failure series (data/sources.yaml, SHA-256 pinned)
       env: pipeline
       resources: { gpu: none, disk_gb_est: 1 }
       determinism: bitwise
     - id: s05_synthesize          # synthetic creep series with known failure time
       env: pipeline
       inputs: [s00_download]
       resources: { gpu: none }
       determinism: bitwise
       shardable: true
     - id: s30_train               # forecasters (TCN / PatchTST) on the synthetic series
       env: pipeline
       inputs: [s05_synthesize]
       resources: { gpu: exclusive, vram_gb_est: 4, disk_gb_est: 2 }
       determinism: statistical
       retry: { on: [cuda_oom], fallback: { batch_size: half } }
     - id: s50_evaluate
       env: pipeline
       inputs: [s30_train, s00_download]
       resources: { gpu: exclusive, vram_gb_est: 2 }
       determinism: statistical
   ```

   Each stage declares where it runs (`env`: `studio`, `isaac`, `pipeline`, `reason` or `external`), what it consumes
   (`inputs`, by digest), what it needs (`resources`: `gpu: exclusive | nvenc | none`, VRAM and disk estimates), how
   reproducible it is (`determinism: bitwise | statistical | none`), and how it may be retried.

2. **Plan it** (dry run). The plan shows the DAG, which stages are cache hits, and the disk and VRAM estimates against
   the active machine profile.

   ```bash run deferred=P6
   uv run --extra runner studio plan studio/recipes/cases/c1.yaml
   ```

3. **Run it.** Each stage runs as `uv run --project <env> --frozen …` inside a Windows job object (a process group on
   Linux), so a crash or a cancel takes the whole process tree down with it.

   ```bash run deferred=P6
   uv run --extra runner studio run studio/recipes/cases/c1.yaml
   uv run --extra runner studio run studio/recipes/cases/c1.yaml --stage s30_train
   ```

4. **Read the run.** Every run writes, under the store:

   ```text
   $PITSTUDIO_STORE/runs/<run_id>/
     manifest.json        # contracts/manifest.schema.json: inputs + SHA-256, tool versions from the locks, seeds,
                          # determinism class, telemetry summary, retries, exit status, licence class, lane
     events.jsonl         # stage events, streamed to the console over SSE
     telemetry.parquet    # 1–4 Hz NVML samples: VRAM, utilisation, power, temperature, SM clock, throttle reasons
     logs/
   ```

   The manifest carries no hostname, user name or absolute path: GPU model, driver and power limit only.

5. **Re-run and watch the cache.** The cache key of a stage is the SHA-256 of a canonical JSON over the stage id, the
   digest of the stage's code, the digest of its environment's lock file, its parameters, its derived seed and the
   digests of its inputs. Run the recipe again unchanged and every stage is a cache hit; change one parameter and only
   that stage and its descendants run.

   ```bash run deferred=P6
   uv run --extra runner studio run studio/recipes/cases/c1.yaml
   uv run --extra runner studio run studio/recipes/cases/c1.yaml --stage s30_train --force
   ```

6. **Plan on another machine profile.** Recipes never name machine paths; a profile supplies VRAM, power class, GPU
   count, store root, CPU slots and enabled environments. CI plans every recipe with the `linux-gpu` profile against a
   fake GPU backend on every push, which is how "the same recipes run on a Linux GPU host" is tested now (foundation spec, specification phase).

   ```bash run deferred=P6
   uv run --extra runner studio plan studio/recipes/cases/c1.yaml --profile linux-gpu
   ```

7. **Publish or clean up.** `studio publish` bakes a run into web artefacts plus a run card; `studio gc` removes store
   entries not reachable from pinned manifests.

   ```bash run deferred=P6
   uv run --extra runner studio publish <run_id>
   uv run --extra runner studio gc --keep-pinned --keep-last 3
   ```

## Expected output

- `studio plan`: one line per stage with `hit` or `miss`, its environment, its GPU slot and its estimates, then the
  totals; no stage runs.
- `studio run`: per-stage start and end events, guard decisions, and the run id; on success the manifest validates
  against its schema.
- A second unchanged `studio run`: every stage reported as a cache hit; wall time near zero.

## How the runner protects the machine

| Guard | When | Effect |
|---|---|---|
| `gpu0.hold` file in `GPU_LOCK_DIR` | before any GPU stage | refuse to start; the file's text is the reason |
| `gpu0.compute` lock (exclusive), `gpu0.nvenc` lock | per GPU / encode stage | one heavy GPU job at a time; encoding can overlap CPU stages |
| Free VRAM ≥ estimate + margin (device-level NVML; Windows WDDM has no per-process VRAM [1]) | pre-flight | skip or wait |
| GPU temperature, free disk, required capabilities | pre-flight | fail fast with the reason |
| CUDA out-of-memory | during the stage | retry once with the stage's declared fallback (smaller batch or shard) |
| Interrupted run | after a crash or cancel | re-run the recipe: completed stages and shards are cache hits; long stages checkpoint and resume |
| Idle sleep | while the queue is not empty | the runner asks Windows to stay awake; closing the lid is still the user's choice [2] |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "recipe does not validate" | a field is missing or misspelled | fix the YAML against `contracts/recipe.schema.json` |
| "capability missing: …" | the probe recorded the tool as failed or skipped on this machine | re-run the capability probe after fixing the environment |
| Every stage is a miss after a dependency update | the environment's lock digest is part of the cache key | expected: new lock, new results |
| A `statistical` stage differs from a previous run | MPM, RTX rendering, synthetic data and training are not bit-reproducible | compare observables within `thresholds.yaml`, not bytes |
| The run stops overnight | the laptop slept or the lid was closed | keep it on AC with the lid open; resume by re-running the recipe |

## Assumptions and limits

- The runner is deliberately small; if it outgrows its ~1,500-line budget, a make-style DAG tool is re-assessed rather
  than growing a framework.
- Determinism is declared per stage and tested: `bitwise` stages are re-run and compared by SHA-256, `statistical`
  stages by observables within tolerances.

## In PitStudio

- Spec `002-runner` (recipes, DAG, CAS cache, locks, hold, guards, telemetry, retries, resume, gc, profiles, fake GPU);
  recipe contract of the foundation spec (`specs/000-foundation/spec.md`, written in the specification phase).
- Pages: [runner](../studio/runner.md), [console](../studio/console.md), [manifest](../data-contract/manifest.md).

## References

1. NVIDIA, "nvidia-smi documentation" — per-process memory not available under WDDM on Windows. https://docs.nvidia.com/deploy/nvidia-smi/index.html
2. Microsoft, `SetThreadExecutionState` — keep-awake semantics; cannot prevent user-initiated sleep. https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate

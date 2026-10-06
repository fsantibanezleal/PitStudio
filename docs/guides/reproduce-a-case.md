# Reproduce a case

> Take an artefact published on a case page, find the commit, recipe and run that produced it, re-run it on your
> machine with the same locks and seeds, and compare the result with the published manifest — bit for bit where the
> stage is deterministic, by observables where it is not. · Part of: [Guides](README.md) · Related:
> [cases](../cases/README.md) · [first recipe](first-recipe.md) · [run instructions](../pipelines/run-instructions.md) ·
> [manifest](../data-contract/manifest.md)

## What and why

**Goal:** independent confirmation. Every artefact on the site names the tool, run and commit behind it, and every
case page offers a "reproduce this" command. Re-running that command with the same code, lock files, parameters, seeds
and inputs gives the same cache key, and for deterministic stages byte-identical outputs (foundation property
a correctness property of the foundation spec, written in the specification phase). For stages that are not bit-reproducible (MPM, RTX rendering, synthetic data, training) the check compares
observables within the tolerances of `specs/000-foundation/thresholds.yaml`.

**Status:** nothing has been published yet, so there is nothing to reproduce today; the commands are
`deferred=P6`. The first reproducible cases will be A1 and C1 on the open lane.

## Prerequisites

- [Quickstart](quickstart.md) for any case; [set up the studio](set-up-the-studio.md) for cases that need GPU or RTX
  tools (table below).
- Network access to the public data sources in `data/sources.yaml`; optional accounts only where noted.

**What each case needs.**

| Case | Open lane (CPU or any CUDA GPU) | Needs an RTX GPU and NVIDIA terms | Optional accounts |
|---|---|---|---|
| [A1](../cases/a1-truck-shovel-dispatch.md) dispatch and fleet sizing | DES, LP, match factor; PPO / attention training (GPU recommended) | — (TensorRT only for the latency table) | — |
| [A2](../cases/a2-haul-road-electrification.md) haul-road energy | energy routing | Isaac Lab IL-1 (optional) | — |
| [A3](../cases/a3-loading-payload-variance.md) loading and payload | Warp / Newton / MuJoCo-Warp (CUDA) | Isaac Lab IL-2 (optional) | — |
| [B1](../cases/b1-traffic-proximity.md) traffic and proximity | agent traffic, TTC, Rapier | ovrtx lidar/radar, Isaac Sim vehicles, Cosmos (optional) | — |
| [B2](../cases/b2-synthetic-perception.md) synthetic perception | detector training (CUDA) | Isaac Sim + Replicator, ovrtx | Hugging Face token for Cosmos captions (optional) |
| [C1](../cases/c1-slope-time-of-failure.md) slope → time of failure | LEM, Hoek–Brown, inverse velocity, forecasters | — | EGMS access (optional; fallback: real de Wit series + synthetic) |
| [C2](../cases/c2-tailings-breach.md) tailings breach | Warp shallow water (CUDA), FNO | Composer hero clip (optional) | — |
| [C3](../cases/c3-dust.md) dust and water trucks | AP-42, Gaussian plume, Warp particles (CUDA) | ovrtx dust-in-lidar | Copernicus CDS for ERA5 (optional; fallback: NOAA station data) |
| [D1](../cases/d1-blast-muck-pile.md) blast and muck pile | Kuz-Ram/KCO, Swebrec, Warp DEM (CUDA), U-Net | Isaac Sim muck renders | — |
| [D2](../cases/d2-mine-to-mill.md) mine-to-mill | `minephys` chain, meta-model | — | — |
| [E1](../cases/e1-pit-shell-pushbacks.md) pit shell and pushbacks | min-cut, nested shells, MILP | Composer review (optional) | — |
| [E2](../cases/e2-survey-reconciliation.md) survey reconciliation | DEM differencing of 3DEP 2018 → 2023 | ovrtx drone camera; COLMAP and Brush (CUDA) | — |

## Steps

1. **Collect the provenance** from the artefact card: run id, recipe hash, git SHA, and the artefact's SHA-256 from the
   manifest. The "reproduce this" block on the case page shows the exact command.

2. **Check out that commit** and sync the environments from their lock files (never re-resolve).

   ```bash
   git checkout <git sha>
   uv sync --locked
   ```

3. **Fetch the inputs.** `s00_download` downloads every real source listed in `data/sources.yaml` and checks its
   SHA-256; raw data are never committed.

   ```bash run deferred=P6
   scripts/run_pipeline.sh --stage s00_download
   ```

4. **Plan, then run the recipe** of the case with the recipe's master seed.

   ```bash run deferred=P6
   uv run --extra runner studio plan studio/recipes/cases/a1.yaml
   uv run --extra runner studio run studio/recipes/cases/a1.yaml
   ```

5. **Compare with the published manifest.** For `bitwise` stages, compare SHA-256 values; for `statistical` stages,
   compare the observables the manifest lists (for example repose angle, run-out, held-out metric) within the
   thresholds file.

   ```bash run deferred=P6
   sha256sum "$PITSTUDIO_STORE"/views/a1-dispatch/<stage>/<artefact>
   ```

6. **See it in the web app** (optional): publish the run locally and build the site.

   ```bash run deferred=P6
   uv run --extra runner studio publish <run_id>
   ```

## Expected output

- The plan reports the same cache keys as the published run when code, locks, parameters, seeds and inputs match.
- `bitwise` stages: identical SHA-256. `statistical` stages: observables within tolerance, reported side by side.
- A difference is a finding, not a failure of the reader: report it as a GitHub issue with both manifests.

## Why results can differ

| Source of difference | Applies to | What to expect |
|---|---|---|
| Different GPU model or driver | Warp atomics, PyTorch kernels | Warp has a deterministic mode for supported atomics since 1.15.0, giving run-to-run bit-exactness **on the same GPU** [1]; across GPUs, compare observables |
| Different PyTorch build or platform | training | completely reproducible results are not guaranteed across PyTorch releases or platforms [2] |
| RTX rendering and Replicator | images | reproducible scene randomisation with a global seed [3]; pixels are compared statistically |
| Different data download | everything downstream | `s00_download` refuses files whose SHA-256 differs from the registry |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Every stage is a cache miss | a lock file or the code digest differs from the published run | check out the exact commit; `uv sync --locked` |
| `s00_download` fails a checksum | the publisher changed the file | report it; the registry entry needs review before anything is re-run |
| A case needs an account you do not have | optional sources (OpenTopography, CDS, EGMS) | the recipe's documented fallback runs instead and the manifest says so |
| RTX stages refuse to start | the capability probe recorded the tool as unavailable on this machine | reproduce the open-lane parts; the RTX outputs remain the published replay |

## Assumptions and limits

- Reproducing a run reproduces a **simulation-grade** result; it says nothing about a real mine, and slope, tailings and
  blasting outputs remain educational, with the validity ranges stated on each case page.
- Licence-restricted performance numbers (Isaac Sim, Kit, Replicator, ovrtx) were never published, so there is nothing
  to compare them with; only their outputs are compared.

## In PitStudio

- The reproducibility property and the manifest requirement of the foundation spec (written in the specification phase); specs `002-runner` and
  `008-data-pipeline`.

## References

1. NVIDIA, Warp CHANGELOG — deterministic execution mode for supported atomics in 1.15.0 (2026-07-07). https://raw.githubusercontent.com/NVIDIA/warp/main/CHANGELOG.md
2. PyTorch, "Reproducibility" notes (source) — no guarantee across releases, commits or platforms; deterministic algorithms. https://raw.githubusercontent.com/pytorch/pytorch/main/docs/source/notes/randomness.md
3. NVIDIA, "Isaac Sim 6.0 Replicator snippets" — `rep.set_global_seed`. https://docs.isaacsim.omniverse.nvidia.com/6.0.0/replicator_tutorials/tutorial_replicator_isaac_snippets.html

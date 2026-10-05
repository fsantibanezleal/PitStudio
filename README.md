# PitStudio

Physical-AI simulation studio for open-pit mining: OpenUSD scenes, GPU physics, RTX sensors, synthetic data, trained
models and an interactive web explorer.

[![CI](https://github.com/fsantibanezleal/PitStudio/actions/workflows/ci.yml/badge.svg)](https://github.com/fsantibanezleal/PitStudio/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/fsantibanezleal/PitStudio)](https://github.com/fsantibanezleal/PitStudio/releases)
[![License](https://img.shields.io/github/license/fsantibanezleal/PitStudio)](LICENSE)
[![Live site](https://img.shields.io/badge/live-GitHub%20Pages-7500C0)](https://fsantibanezleal.github.io/PitStudio/)

> **Status: early.**
> - Done: the wiki is written, the repository and web shell are live, and the GPU capability bench is in place.
> - Not done: no simulation, training or rendering has run yet. Every result page says "not yet run" until it has.
> - The models and engines are built test-first from the specifications in [`specs/`](specs/).

## What it is / is not

PitStudio is an open, reproducible **physical-AI suite for open-pit mining**. Four parts share one engine, one data
contract and one manifest format:

1. **A local studio.** One RTX workstation runs the Omniverse-class tools, each in a mining role:
   - OpenUSD scenes built from real lidar;
   - Warp / Newton GPU physics for bulk material, digging, tailings and dust;
   - Isaac Sim + Replicator for synthetic data;
   - ovrtx RTX lidar, radar and camera;
   - Isaac Lab for haul-truck and excavator policies;
   - Cosmos Reason 2 for vision-language safety questions;
   - PyTorch, TensorRT, NVENC and NVML.

   A job runner and a loopback console drive all of them.
2. **A static web app** that explains, runs and showcases the work: 12 scenario workbenches, live in-browser engines,
   replays of the studio's GPU runs, a studio tool map, theory and results.
3. **A knowledge base:** the [wiki](docs/README.md) plus the companion library
   [`minephys`](https://github.com/fsantibanezleal/minephys), which holds sourced equations and parameter tables.
4. **A scalable base:** the same recipes run on a Linux GPU host by switching the profile.

It is **not**:
- a live digital twin of a real mine (there is no telemetry feed);
- design or regulatory software: slope, tailings and blasting outputs are educational, with stated validity ranges;
- an NVIDIA product.

## Live

**https://fsantibanezleal.github.io/PitStudio/** is a static site. Heavy computation is precomputed locally; light
computation runs in your browser, on WebGPU, then WebAssembly, then a precomputed fallback. The access gate is a demo
gate, not a security boundary: all published content is public.

## How it works

Every artefact belongs to one of four lanes:

| Lane | Meaning |
|---|---|
| **live** | Runs in the browser. |
| **precompute** | Local pipelines and training. |
| **replay** | The web app animates committed artefacts. |
| **local-only** | Performance data whose licence forbids publishing. |

A lane is assigned by measurement (size, latency), never by hand. See [`docs/architecture/`](docs/architecture/README.md)
and [`docs/studio/`](docs/studio/README.md).

## Quickstart

These commands run today:

```bash
uv sync --all-groups && uv run pytest -m "not gpu"         # core + tests
cd web && pnpm install && pnpm dev                         # the web shell
scripts/run_web.sh                                         # build + serve as GitHub Pages does (PowerShell: scripts/run_web.ps1)
```

The pipeline stages (`scripts/run_pipeline.sh --all`) and the studio recipes are built in the next phases. See
[`docs/guides/quickstart.md`](docs/guides/quickstart.md).

## Cases and methods

The scenarios fall into five categories:
- haulage and energy;
- safety and autonomy;
- geotechnics and environment;
- drill-blast-to-mill;
- planning and survey.

There are 12 [cases](docs/cases/README.md) across these categories, built on the real USGS 3DEP Bingham Canyon terrain.
They use 23 [methods](docs/methods/README.md), 11 of them learned, on a ladder from classical to SOTA to beyond-SOTA.
Every learned method is compared with a classical baseline under a pre-registered decision rule: "better" only when
the paired 95 % confidence interval excludes zero.

## Data & licences

Sources, licences and checksums are in [`docs/data-contract/`](docs/data-contract/README.md), with one
[dataset card](docs/data-contract/dataset-cards/README.md) per source. Third-party data is downloaded by the pipeline
and never redistributed here.

## Documentation

The wiki starts at [`docs/README.md`](docs/README.md); specifications are in [`specs/`](specs/).

## Cite

See [`CITATION.cff`](CITATION.cff).

## Versioning · Changelog · Licence

Releases are numbered `X.YY.ZZZ` ([CHANGELOG](CHANGELOG.md)). Code is Apache-2.0 ([LICENSE](LICENSE)); docs, figures
and original data are CC-BY-4.0 (see [`REUSE.toml`](REUSE.toml)). Author: Felipe A. Santibanez-Leal.

NVIDIA, Omniverse, Isaac Sim, Cosmos and RTX are trademarks of NVIDIA Corporation. This project is independent and not
affiliated with or endorsed by NVIDIA (see [NOTICE](NOTICE)).

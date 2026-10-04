# PitStudio

Physical-AI simulation studio for open-pit mining: OpenUSD scenes, GPU physics, RTX sensors, synthetic data, trained models and an interactive web explorer

[![CI](https://github.com/fsantibanezleal/PitStudio/actions/workflows/ci.yml/badge.svg)](https://github.com/fsantibanezleal/PitStudio/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/fsantibanezleal/PitStudio)](https://github.com/fsantibanezleal/PitStudio/releases)
[![License](https://img.shields.io/github/license/fsantibanezleal/PitStudio)](LICENSE)
[![Live site](https://img.shields.io/badge/live-GitHub%20Pages-7500C0)](https://fsantibanezleal.github.io/PitStudio/)

## What it is / is not
<!-- Honest scope: the question this project answers, for whom, and what it deliberately does not do. -->

## Live
**https://fsantibanezleal.github.io/PitStudio/** — static site; heavy computation is precomputed locally, light
computation runs in your browser (WebGPU → WebAssembly → precomputed fallback). The access gate is a demo gate, not a
security boundary; all published content is public.

## Screenshots
<!-- Real views, light and dark. -->

## How it works
Three lanes — **live** (in the browser), **precompute** (local pipelines and training), **replay** (the web app
animates committed artifacts). See the in-app ⓘ Architecture view and [`docs/architecture/`](docs/architecture/).

## Quickstart
```bash
# Windows: scripts/bootstrap.ps1   ·   Linux/macOS: scripts/bootstrap.sh
uv run pytest -m "not gpu"            # core tests
scripts/run_pipeline.sh --all         # fetch data, synthesize, train, evaluate, bake (CPU or GPU)
cd web && pnpm install && pnpm dev
```

## Data & licences
Sources, licences and checksums: [`data/sources.yaml`](data/sources.yaml) · dataset cards: [`data/cards/`](data/cards/) ·
contracts: [`docs/data-contract/`](docs/data-contract/). Third-party data is downloaded by the pipeline, never redistributed here.

## Methods
<!-- The method ladder classical → SOTA → beyond-SOTA, each with a DOI/URL. -->

## Documentation
The wiki starts at [`docs/README.md`](docs/README.md). Specifications: [`specs/`](specs/).

## Cite
See [`CITATION.cff`](CITATION.cff).

## Versioning · Changelog · Licence
`X.YY.ZZZ` releases ([CHANGELOG](CHANGELOG.md)). Code: Apache-2.0 ([LICENSE](LICENSE)); docs, figures and original
data: CC-BY-4.0; see [`REUSE.toml`](REUSE.toml). Author: Felipe A. Santibanez-Leal.

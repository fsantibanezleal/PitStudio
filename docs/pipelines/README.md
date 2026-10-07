# Pipelines

> The stages that turn sources into data, data into models, and models and simulations into web artefacts, in which
> environment each runs, and how to run them. · Part of: [Docs home](../README.md) · Related:
> [Studio](../studio/README.md) · [Data contract](../data-contract/README.md) · [Models](../models/README.md)

PitStudio has two families of stages that share one runner, one cache and one manifest format:

- **Pipeline stages** (`s00`…`s60`, then `s62`, `s64`): download, synthesize, preprocess, extract features, train,
  infer, evaluate, export, then accelerate and benchmark. They run in `pipeline/` (Python 3.14, CPU, cu126 or cu130) and
  `pipeline/accel/` (TensorRT 11.3).
- **Studio stages** (`st10`…`st61`): terrain, pit design, assets, composition, validation, GPU physics, RTX rendering,
  synthetic data, sensors, captures, encoding, robot learning and vision-language tasks. They run in the studio
  environments, from the open `studio/` lane on Python 3.14 to the NVIDIA lanes on Python 3.12.

Stages hand data to each other only as files with SHA-256 digests, validated by schemas on both sides, so a 3.12
environment and a 3.14 environment never import each other.

![Pipeline stages with environments, runtimes and outputs](../assets/diagrams/pipeline-stages.svg)

*The pipeline lane from download to benchmark; runtimes are plan estimates, measured by the runner.*

## Map of this section

| Page | What it answers |
|---|---|
| [Pipeline stages](pipeline-stages.md) | `s00_download` … `s60_export`, `s62_accel`, `s64_bench`: inputs, outputs, runtimes, determinism |
| [Studio stages](studio-stages.md) | `st10_terrain` … `st61_il_mpm_eval`, grouped by environment, with tools, outputs and licence notes |
| [Compute lanes](compute-lanes.md) | the CPU, CUDA 12.6 and CUDA 13.0 builds, the `cpu` / `cu126` / `cu130` extras, the studio GPU lanes and the pip fallbacks |
| [Run instructions](run-instructions.md) | commands that run today, and the plan's commands that exist after the build phase |

## Status

- The environments are locked (`uv.lock` in the root, `pipeline/`, `pipeline/accel/`, `studio/`, `studio/isaac/`,
  `studio/rtx/`, `studio/isaaclab/`). CI installs the root and the `pipeline/` CPU lane and runs their tests.
- The capability bench and four GPU probes exist; they have not run on the reference machine yet (GPU hold).
- No stage has run: the runner, the stages and the recipes are built in the build phase.

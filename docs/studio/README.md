# Studio

> The local GPU half of PitStudio: isolated tool environments, one small runner that schedules every GPU job, a
> loopback console, a capability probe, and a path to a Linux GPU host. · Part of: [Docs home](../README.md) ·
> Related: [Frameworks](../frameworks/README.md) · [Studio stages](../pipelines/studio-stages.md) ·
> [Set up the studio](../guides/set-up-the-studio.md) · [DEC-0001](../architecture/decisions/DEC-0001-isolated-studio-environments.md)

## What and why

PitStudio has two halves. The **web app** on GitHub Pages explains the science and runs light engines in the browser.
The **studio** is where the heavy work happens: building OpenUSD scenes from real lidar, GPU physics, RTX sensor and
synthetic-data renders, robot learning, model training and acceleration, video encoding and GPU telemetry. It runs on
one Windows workstation with a 16 GB laptop GPU (the reference machine), and the same recipes are meant to run on a
Linux GPU host later.

The studio is local-only by design. NVIDIA runtimes cannot run on CI runners and must not be redistributed, and the
web never calls the studio: it only shows the artefacts the studio baked, each with its provenance.

![Studio environments: one uv project and one lock each](../assets/diagrams/studio-environment-map.svg)

*The studio's environments with their Python version and key locked packages; stages cross environments only through
files.*

## Map

| Page | What you find |
|---|---|
| [Environments](environments.md) | Every environment, its Python version, what it holds, why it is isolated, and the file-only handoff |
| [Runner](runner.md) | Recipes, the stage DAG, the content-addressed cache, GPU locks and guards, telemetry, retries and resume |
| [Console](console.md) | The loopback FastAPI console: jobs, runs, live telemetry; never part of the public site |
| [Capabilities probe](capabilities-probe.md) | What exists today in `studio/bench/`: the probes, their checks, public vs local-only results, exit codes |
| [Scaling to Linux](scaling-to-linux.md) | Machine profiles, the CI plan check against a fake GPU, the open container, the Isaac Sim container rule |
| [Maintainer acts and licences](owner-acts-and-licences.md) | The one-time acts (licence prompts, gated model terms, admin captures) and what degrades without them |

## Orientation

- **What exists today.** All six Python environments are locked (`studio/`, `studio/isaac/`, `studio/rtx/`,
  `studio/isaaclab/`, `pipeline/`, `pipeline/accel/`, plus the root project). The capability bench and its contract
  tests exist. The runner, the console, the Kit extension and the Cosmos lane are **planned** and will be built
  test-first in the build phase.
- **Status of results.** Nothing has been trained, rendered or baked yet. The GPU capability probes are written but not
  yet run on the reference machine, which is under a GPU hold.
- **Licence rules** that shape the studio: NVIDIA tools are named nominatively and never redistributed; PitStudio is not
  affiliated with or endorsed by NVIDIA; performance data of Isaac Sim, Kit, Replicator, ovrtx and TensorRT for RTX
  stay local-only ([DEC-0004](../architecture/decisions/DEC-0004-proprietary-sdks-reference-only.md),
  [DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)).
- **Where things live on disk.** The runner's store is `PITSTUDIO_STORE` (default `C:\ps` on Windows: a short path
  outside the repo). Data, models and scratch come from `PITSTUDIO_DATA`, `PITSTUDIO_MODELS` and `PITSTUDIO_TMP`,
  which default to git-ignored folders in the repo ([Configuration](../reference/configuration.md)).

## Reading paths

- **Reproduce a case:** [Environments](environments.md) → [Runner](runner.md) →
  [Reproduce a case](../guides/reproduce-a-case.md).
- **Check a machine:** [Capabilities probe](capabilities-probe.md) → [Maintainer acts and licences](owner-acts-and-licences.md).
- **Understand one tool:** [Frameworks](../frameworks/README.md).

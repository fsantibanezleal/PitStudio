# PitStudio documentation

> The knowledge base of PitStudio, an open and reproducible physical-AI simulation studio for open-pit mining: what it
> is, who it is for, how to read it, and a map of every page. · Related:
> [context](context/README.md) · [architecture](architecture/README.md) · [cases](cases/README.md) ·
> [guides](guides/README.md)

## What PitStudio is

PitStudio asks a practical question: **how far can an open, Omniverse-class physical-AI toolchain go on open-pit mining
problems when it runs on one workstation GPU, uses real public data where it exists and says so where it does not?**
It applies OpenUSD scenes, GPU physics, RTX sensor simulation, synthetic data, robot learning, vision-language
reasoning, accelerated inference and hardware video encoding to twelve mining cases. Every result is reproducible from
the repository, and every number on the website is either recomputed live in the browser or replayed from a run whose
manifest is committed.

The scope is deliberately bounded:

- **A simulation-grade twin, not a live digital twin.** There is no telemetry feed from a real operation. Scenes are
  built from real public terrain (USGS 3DEP lidar of Bingham Canyon as the default site), and operations are simulated.
- **Educational, not design or regulatory software.** Slope, tailings and blasting outputs come with their validity
  ranges and must not be used to design or approve a real structure.
- **Not an NVIDIA product.** NVIDIA, Omniverse, Isaac Sim, Cosmos and RTX are trademarks of NVIDIA Corporation.
  PitStudio is independent and not affiliated with or endorsed by NVIDIA. NVIDIA tools are named nominatively, run
  only on the maintainer's machine, and are never redistributed ([DEC-0004](architecture/decisions/DEC-0004-proprietary-sdks-reference-only.md)).

**Status (2026-10-04).** The documentation is written before the code. The repository holds the scaffold, the locked
environments, the first contract (the capability report schema), the capability bench, the web shell and the CI checks. Nothing has been trained or rendered yet; every
results section says **Not yet run** and lists the criterion that was fixed in advance. The GPU capability probes
are written but have not yet run on the reference machine.

## The four parts of the product

![The four parts of PitStudio around one shared core](assets/diagrams/pitstudio-overview.svg)

*The four parts share one engine (`minephys` plus the slim `pitstudio` package), one data contract (JSON Schema under
`contracts/`) and one manifest format.*

| Part | What it is | Where it lives | Start reading at |
|---|---|---|---|
| 1. Local studio | Every Omniverse-class tool that runs on the reference workstation (RTX 5000 Ada Laptop, 16 GB), each in a mining role, driven by one job runner and a loopback console | `studio/`, `pipeline/`, `api/`, `src/pitstudio/runner/` | [studio/](studio/README.md) |
| 2. Static web app | A GitHub Pages site that explains, runs and showcases everything: a 3D pit, 12 case workbenches, live in-browser engines, replays of the studio's GPU work, a tool map with the artefacts each tool produced | `web/` | [web/](web/README.md) |
| 3. Knowledge base | This wiki plus the companion library `minephys`: cited equations, parameter tables, a bibliography, a glossary and catalogues | `docs/`, `minephys` | [knowledge/](knowledge/README.md) |
| 4. Scalable base | The same recipes and lock files run on a Linux GPU host; only a machine profile is laptop-specific | `studio/recipes/_profiles/` | [studio/scaling-to-linux](studio/scaling-to-linux.md) |

## Who it is for, and where to start

Each path is a reading order. Pages build on the ones before them.

**Mining engineers and managers** want to know what dispatch, road grade, electrification and fragmentation do to
t/h, kWh/t and CO₂/t; how early radar warns of a wall failure; how far a tailings breach travels.

1. [The mining value chain](context/mining-value-chain.md) and [open-pit operations](context/open-pit-operations.md)
2. [Scenario impact](context/scenario-impact.md): why these twelve cases
3. [The case catalogue](cases/README.md), then [A1 dispatch](cases/a1-truck-shovel-dispatch.md),
   [A2 road energy](cases/a2-haul-road-electrification.md), [C1 slope time of failure](cases/c1-slope-time-of-failure.md),
   [C2 tailings breach](cases/c2-tailings-breach.md), [D2 mine-to-mill](cases/d2-mine-to-mill.md)
4. [Quality and validation](architecture/quality-and-validation.md): when a result may be called "better"

**Data and AI practitioners** want to know how far synthetic-only training goes, whether a learned surrogate can
replace a GPU granular simulation in the browser, and what a vision-language model gets right about pit safety.

1. [Physical AI and simulation twins](context/physical-ai-and-simulation-twins.md) and [sim-to-real](theory/sim-to-real.md)
2. [B2 synthetic-data perception](cases/b2-synthetic-perception.md) and [D1 blast and muck pile](cases/d1-blast-muck-pile.md)
   (the case where sim-to-real is measured on real labelled images)
3. [Models](models/README.md), [training recipes](models/training-recipes.md),
   [export, parity and acceleration](models/export-parity-acceleration.md)
4. [M08 GNS surrogate](methods/m08-gns-surrogate.md), [M10 synthetic-data detector](methods/m10-synthetic-data-detector.md),
   [M22 Cosmos VLM tasks](methods/m22-cosmos-vlm-tasks.md)
5. [The data contract](data-contract/README.md) and the [dataset cards](data-contract/dataset-cards/README.md)

**Students** want the theory and equations with interactive figures.

1. [The mining value chain](context/mining-value-chain.md)
2. [Theory](theory/README.md): start with [haulage](theory/haulage.md), [drill and blast](theory/drill-and-blast.md)
   and [slopes and monitoring](theory/slopes-and-monitoring.md)
3. [Methods](methods/README.md), from classical to beyond state of the art
4. [Glossary](reference/glossary.md) and the [knowledge catalogue](knowledge/README.md)

**Developers** want to build and operate a complete Omniverse-class pipeline on one workstation.

1. [Architecture](architecture/README.md), [containers](architecture/c4-containers.md) and [lanes](architecture/lanes.md)
2. [The studio](studio/README.md): [environments](studio/environments.md), [runner](studio/runner.md),
   [console](studio/console.md), [capabilities probe](studio/capabilities-probe.md)
3. [Quickstart](guides/quickstart.md), [set up the studio](guides/set-up-the-studio.md), [first recipe](guides/first-recipe.md)
4. [The manifest contract](data-contract/manifest.md) and [recipes and tool registry](data-contract/recipes-and-tool-registry.md)
5. [Decisions](architecture/decisions/README.md): why each part is built the way it is

## Map of every section

| Section | What it holds |
|---|---|
| [context/](context/README.md) | The mining domain, the physical-AI idea, why these cases, what exists already |
| [theory/](theory/README.md) | The science per phenomenon: governing equations from primary sources, assumptions, validity ranges |
| [methods/](methods/README.md) | One page per method M01–M23 of the ladder (classical → state of the art → beyond) |
| [cases/](cases/README.md) | Twelve cases in five categories, with the coverage and tool matrices |
| [frameworks/](frameworks/README.md) | One page per tool or library, including the ones evaluated and not adopted |
| [studio/](studio/README.md) | The local studio: environments, runner, console, capability probe, scaling, owner acts |
| [knowledge/](knowledge/README.md) | Catalogue generated from `minephys`: parameters, equations, bibliography, glossary |
| [data-contract/](data-contract/README.md) | Sources and licences, ingestion, manifest, recipe and tool schemas, capabilities, dataset cards |
| [models/](models/README.md) | Model cards, training recipes, export, parity and acceleration |
| [pipelines/](pipelines/README.md) | Pipeline and studio stages, compute lanes, run instructions |
| [web/](web/README.md) | Web structure, user flow, showcase rules, compute tiers, access gate, budgets |
| [architecture/](architecture/README.md) | arc42-lite, C4 views, lanes, deployment, quality and validation, decisions |
| [guides/](guides/README.md) | Task-oriented how-tos, from the quickstart to release and citation |
| [reference/](reference/README.md) | CLI, configuration, glossary, FAQ |

Every page, by section:

- **context:** [mining value chain](context/mining-value-chain.md) · [open-pit operations](context/open-pit-operations.md) ·
  [physical AI and simulation twins](context/physical-ai-and-simulation-twins.md) · [scenario impact](context/scenario-impact.md) ·
  [prior art and positioning](context/prior-art-and-positioning.md)
- **theory:** [haulage](theory/haulage.md) · [loading and terramechanics](theory/loading-and-terramechanics.md) ·
  [drill and blast](theory/drill-and-blast.md) · [slopes and monitoring](theory/slopes-and-monitoring.md) ·
  [bulk flow, DEM and MPM](theory/bulk-flow-dem-mpm.md) · [comminution](theory/comminution.md) · [dust](theory/dust.md) ·
  [tailings](theory/tailings.md) · [planning](theory/planning.md) · [RTX sensor physics](theory/rtx-sensor-physics.md) ·
  [robot learning](theory/robot-learning.md) · [vision-language reasoning](theory/vision-language-reasoning.md) ·
  [sim-to-real](theory/sim-to-real.md)
- **methods:** [M01 match factor and queueing](methods/m01-match-factor-queueing.md) ·
  [M02 haulage DES](methods/m02-haulage-des.md) · [M03 LP dispatch](methods/m03-lp-dispatch.md) ·
  [M04 PPO dispatch](methods/m04-ppo-dispatch.md) · [M05 attention fleet policy](methods/m05-attention-fleet-policy.md) ·
  [M06 haul-road energy and routing](methods/m06-haul-road-energy-routing.md) ·
  [M07 GPU granular physics](methods/m07-gpu-granular-physics.md) · [M08 GNS surrogate](methods/m08-gns-surrogate.md) ·
  [M09 differentiable DEM calibration](methods/m09-differentiable-dem-calibration.md) ·
  [M10 synthetic-data detector](methods/m10-synthetic-data-detector.md) ·
  [M11 fragmentation segmentation](methods/m11-fragmentation-segmentation.md) ·
  [M12 blast fragmentation models](methods/m12-blast-fragmentation-models.md) ·
  [M13 slope stability LEM](methods/m13-slope-stability-lem.md) · [M14 slope forecasting](methods/m14-slope-forecasting.md) ·
  [M15 shallow water and FNO](methods/m15-shallow-water-fno.md) · [M16 dust dispersion](methods/m16-dust-dispersion.md) ·
  [M17 comminution and mine-to-mill](methods/m17-comminution-mine-to-mill.md) ·
  [M18 pit optimisation and scheduling](methods/m18-pit-optimisation-scheduling.md) ·
  [M19 Gaussian-splat survey](methods/m19-gaussian-splat-survey.md) · [M20 traffic and TTC](methods/m20-traffic-ttc.md) ·
  [M21 Isaac Lab policies](methods/m21-isaac-lab-policies.md) · [M22 Cosmos VLM tasks](methods/m22-cosmos-vlm-tasks.md) ·
  [M23 RTX sensor simulation](methods/m23-rtx-sensor-simulation.md)
- **cases:** [coverage matrix](cases/coverage-matrix.md) · [tool matrix](cases/tool-matrix.md) ·
  [A1 truck–shovel dispatch](cases/a1-truck-shovel-dispatch.md) · [A2 haul-road electrification](cases/a2-haul-road-electrification.md) ·
  [A3 loading and payload variance](cases/a3-loading-payload-variance.md) · [B1 traffic and proximity](cases/b1-traffic-proximity.md) ·
  [B2 synthetic perception](cases/b2-synthetic-perception.md) · [C1 slope time of failure](cases/c1-slope-time-of-failure.md) ·
  [C2 tailings breach](cases/c2-tailings-breach.md) · [C3 dust](cases/c3-dust.md) ·
  [D1 blast and muck pile](cases/d1-blast-muck-pile.md) · [D2 mine-to-mill](cases/d2-mine-to-mill.md) ·
  [E1 pit shell and pushbacks](cases/e1-pit-shell-pushbacks.md) · [E2 survey reconciliation](cases/e2-survey-reconciliation.md)
- **frameworks:** [OpenUSD](frameworks/openusd.md) · [Warp](frameworks/warp.md) · [Newton](frameworks/newton.md) ·
  [MuJoCo-Warp](frameworks/mujoco-warp.md) · [PhysX / ovphysx](frameworks/physx-ovphysx.md) · [ovrtx](frameworks/ovrtx.md) ·
  [Isaac Sim + Replicator](frameworks/isaac-sim-replicator.md) · [Isaac Lab](frameworks/isaac-lab.md) ·
  [Kit, USD Composer and Explorer](frameworks/kit-usd-composer-explorer.md) · [Cosmos Reason 2](frameworks/cosmos-reason-2.md) ·
  [PyTorch](frameworks/pytorch.md) · [ONNX Runtime](frameworks/onnx-runtime.md) · [TensorRT](frameworks/tensorrt.md) ·
  [NVENC and FFmpeg](frameworks/nvenc-ffmpeg.md) · [Nsight and NVML](frameworks/nsight-nvml.md) ·
  [three.js, R3F and 3D Tiles](frameworks/threejs-r3f-3d-tiles.md) · [Rapier, WebGPU and Pyodide](frameworks/rapier-webgpu-pyodide.md) ·
  [COLMAP, Brush and splats](frameworks/colmap-brush-splats.md) · [minehaulsim](frameworks/minehaulsim.md) ·
  [oreblocks](frameworks/oreblocks.md) · [minephys](frameworks/minephys.md) · not adopted:
  [cuOpt](frameworks/not-adopted-cuopt.md), [PhysicsNeMo](frameworks/not-adopted-physicsnemo.md),
  [Cosmos Predict and Transfer](frameworks/not-adopted-cosmos-predict-transfer.md)
- **studio:** [environments](studio/environments.md) · [runner](studio/runner.md) · [console](studio/console.md) ·
  [capabilities probe](studio/capabilities-probe.md) · [scaling to Linux](studio/scaling-to-linux.md) ·
  [owner acts and licences](studio/owner-acts-and-licences.md)
- **knowledge:** [catalogue](knowledge/README.md)
- **data-contract:** [sources and licences](data-contract/sources-and-licences.md) · [ingestion](data-contract/ingestion.md) ·
  [manifest](data-contract/manifest.md) · [recipes and tool registry](data-contract/recipes-and-tool-registry.md) ·
  [capabilities](data-contract/capabilities.md) · dataset cards: [index](data-contract/dataset-cards/README.md),
  [Bingham 3DEP](data-contract/dataset-cards/bingham-3dep.md), [McKinley lidar](data-contract/dataset-cards/mckinley-lidar.md),
  [Hambach NRW](data-contract/dataset-cards/hambach-nrw.md), [EGMS Hambach](data-contract/dataset-cards/egms-hambach.md),
  [de Wit slope failure](data-contract/dataset-cards/dewit-slope-failure.md),
  [Mendeley rock fragments](data-contract/dataset-cards/mendeley-rock-fragments.md),
  [Tang & Werner footprint](data-contract/dataset-cards/tang-werner-footprint.md),
  [Xu mining expansion](data-contract/dataset-cards/xu-mining-expansion.md), [Maus polygons](data-contract/dataset-cards/maus-polygons.md),
  [ERA5 / GHCNh](data-contract/dataset-cards/era5-ghcnh.md), [MineLib marvin](data-contract/dataset-cards/minelib-marvin.md),
  [AP-42](data-contract/dataset-cards/ap42.md), [CC0 textures](data-contract/dataset-cards/textures-cc0.md),
  [MakeHuman people](data-contract/dataset-cards/makehuman-people.md), [synthetic data](data-contract/dataset-cards/synthetic-data.md)
- **models:** [D-FINE](models/d-fine.md) · [RF-DETR-Seg](models/rf-detr-seg.md) · [U-Net fragmentation](models/unet-fragmentation.md) ·
  [GNS granular](models/gns-granular.md) · [FNO fields](models/fno-fields.md) · [dispatch policies](models/dispatch-policies.md) ·
  [Isaac Lab policies](models/isaac-lab-policies.md) · [slope forecasters](models/slope-forecasters.md) ·
  [mine-to-mill meta-model](models/mine-to-mill-meta-model.md) · [DEM calibration](models/dem-calibration.md) ·
  [Cosmos Reason 2](models/cosmos-reason-2.md) · [training recipes](models/training-recipes.md) ·
  [export, parity and acceleration](models/export-parity-acceleration.md)
- **pipelines:** [pipeline stages](pipelines/pipeline-stages.md) · [studio stages](pipelines/studio-stages.md) ·
  [compute lanes](pipelines/compute-lanes.md) · [run instructions](pipelines/run-instructions.md)
- **web:** [structure](web/structure.md) · [user flow](web/user-flow.md) · [showcase rules](web/showcase-rules.md) ·
  [compute tiers](web/compute-tiers.md) · [access gate](web/access-gate.md) · [budgets](web/budgets.md)
- **architecture:** [C4 context](architecture/c4-context.md) · [C4 containers](architecture/c4-containers.md) ·
  [lanes](architecture/lanes.md) · [deployment](architecture/deployment.md) ·
  [quality and validation](architecture/quality-and-validation.md) · [decisions](architecture/decisions/README.md)
- **guides:** [quickstart](guides/quickstart.md) · [set up the studio](guides/set-up-the-studio.md) ·
  [first recipe](guides/first-recipe.md) · [synthetic data generation](guides/synthetic-data-generation.md) ·
  [Isaac Lab task](guides/isaac-lab-task.md) · [Composer review](guides/composer-review.md) ·
  [Cosmos tasks](guides/cosmos-tasks.md) · [TensorRT bench](guides/tensorrt-bench.md) · [encode videos](guides/encode-videos.md) ·
  [profile the GPU](guides/profile-the-gpu.md) · [reproduce a case](guides/reproduce-a-case.md) ·
  [release and cite](guides/release-and-cite.md)
- **reference:** [CLI](reference/cli.md) · [configuration](reference/configuration.md) · [glossary](reference/glossary.md) ·
  [FAQ](reference/faq.md)

## How to read these pages

**Page shape.** Content pages share one structure: a one-line summary with links to the section and related pages,
then *What and why*, the core content (equations, design or steps), *Assumptions and limits*, *In PitStudio* (where the
page is used: cases, methods, code paths, status) and numbered *References*.

**Equations** are GitHub Markdown math (`$…$` inline, `$$…$$` display). Every symbol is defined with its unit, and every
equation cites its primary source. Units are SI unless a source works in US customary units (AP-42, US blasting
rules); those pages state the conversion.

**Sources and status labels.**

- Every external number carries a reference to a DOI or URL.
- **UNVERIFIED (pinned at specification)** marks a value whose primary text could not be read when the page was
  written. It is checked against the primary source before it becomes a constant in code; the web app flags such rows.
- **Not yet run** marks a result that the data-and-models phase will produce. The page lists what will be reported and
  the acceptance criterion that was fixed before any run.
- **Illustrative** marks numbers chosen to explain arithmetic. They are not data about any real mine or machine.

**Lane badges.** The web app and these pages label every artefact **LIVE** (computed in your browser), **REPLAY**
(precomputed by a named tool in a named run) or **STATIC** (a figure). Performance data of licence-restricted
NVIDIA software is **local-only**: measured on the maintainer's machine and never published. See
[lanes](architecture/lanes.md).

**Shell blocks.** A block marked `bash` is illustrative. A block marked `bash run` runs today in this repository. A
block marked `bash run deferred=P6` is a command from the plan that will exist once the build phase implements it; it
does not run yet.

**Paths and environment variables.** Code paths are relative to the repository root. Machine-specific folders are never
written into the repository: the studio store is `PITSTUDIO_STORE` (default a short path such as `C:\ps` on Windows),
and datasets, models and temporary files go to `PITSTUDIO_DATA`, `PITSTUDIO_MODELS` and `PITSTUDIO_TMP` (default:
git-ignored folders inside the repository). See [configuration](reference/configuration.md).

**Licences.** Code is Apache-2.0. Documentation, figures, our USD scenes and our synthetic data are CC-BY-4.0.
Share-alike-derived layers (MineLib, Maus polygons) stay CC BY-SA in separate entries. Third-party data is downloaded
by the pipeline and never redistributed. See [sources and licences](data-contract/sources-and-licences.md).

# Recipes and tool registry

> Two small contracts drive the studio: recipes tell the runner what to compute, and the tool registry tells the web app
> which tool produced what. · Part of: [Data contract](README.md) · Related: [Runner](../studio/runner.md) ·
> [Manifest](manifest.md) · [Studio stages](../pipelines/studio-stages.md) · [Tool matrix](../cases/tool-matrix.md)

## What and why

The studio spans ten isolated environments, from Python 3.14 physics to Python 3.12 NVIDIA runtimes and a llama.cpp
binary. A recipe is the machine-independent description of a computation across them: a small directed acyclic graph
(DAG) of stages, each bound to one environment, with declared inputs, outputs, resources and determinism. The runner
turns a recipe into cached, locked, resumable jobs. The **tool registry** is the other side: one entry per studio tool
(17 in total), with its environment, its version read from the lock, its licence class and the kinds of artefact it
produces. The web app's `/studio` tool map and the 17 tool pages are generated from it, and the artefacts shown on each
tool page are filtered from the manifests by `producer.tool`.

## Recipes: `contracts/recipe.schema.json`

Recipes are YAML files in `studio/recipes/cases/` (one per case; benchmark suites in `studio/recipes/_bench/`),
validated against `contracts/recipe.schema.json` (written in the specification phase). Configuration composition is
done with explicit overlay files and the same JSON Schema / Pydantic machinery as the manifests.

### Recipe fields

| Field | Meaning |
|---|---|
| `id`, `case` | recipe id and the case it serves (e.g. `D1`) |
| `seed` | master seed; per-stage seeds are derived from a hash of (master seed, stage id, shard) |
| `stages[]` | the DAG nodes (below); edges follow from `inputs` referring to other stages' `outputs` |
| `profile` | not stored in the recipe: chosen at run time (`laptop-rtx5000ada`, `linux-gpu`) |

### Stage fields

| Field | Values | Meaning |
|---|---|---|
| `id` | e.g. `s30_train`, `st50_physics` | stage id from the frozen stage lists ([Pipeline stages](../pipelines/pipeline-stages.md), [Studio stages](../pipelines/studio-stages.md)) |
| `env` | `studio`, `isaac`, `rtx`, `isaaclab`, `kit`, `reason`, `pipeline`, `accel`, `external` | target environment; every Python stage runs as `uv run --project <env> --frozen …` |
| `entry` | module or executable | what is launched |
| `inputs` | logical ids + SHA-256 | data by id and digest, **never by path** |
| `params` | object (Pydantic-validated) | stage parameters; they enter the cache key |
| `resources` | `gpu: exclusive \| nvenc \| none`, `vram_gb_est`, `disk_gb_est`, `cpu` | which lock the stage takes and what the guards check before start |
| `determinism` | `bitwise \| statistical \| none` | declared class, tested by a re-run check ([Manifest](manifest.md)) |
| `retry` | policy, incl. `oom_fallback` | retries only for classified transient failures (e.g. CUDA out-of-memory → smaller batch or shard) |
| `timeout` | seconds | hard limit |
| `outputs` | declared files and their schemas | outputs are promoted only after they validate |
| `shardable` | shard size | e.g. 1,000 synthetic frames per shard; each shard is its own cache entry |

### Cache key and store

The cache key is the SHA-256 of a canonical JSON over: the stage id, the stage's code digest, the environment's
`uv.lock` digest, the params, the derived seed and the input digests. A hit materialises the outputs from the
content-addressed store without running anything. The store lives under `PITSTUDIO_STORE` (a short path such as `C:\ps`
on Windows, outside the repository): `cas/`, `runs/<run_id>/`, `views/`, `queue.db`, `locks/`. Each stage writes into a
temporary folder of its run and is promoted by rename only after its outputs validate.

### Profiles

`studio/recipes/_profiles/<profile>.yaml` describes a machine: VRAM, power class, GPU count, store root, CPU slots and
enabled environments. Recipes never change between machines; only the profile does. CI checks this on every push: it
plans every recipe with the `linux-gpu` profile against a fake GPU backend and fails on any operating-system or path
leak.

### An illustrative recipe

```yaml
# studio/recipes/cases/<case>.yaml  (illustrative; real recipes are written in the build phase)
id: d1-blast-muck-pile
case: D1
seed: 20261004
stages:
  - id: st50_physics
    env: studio
    entry: pitstudio_studio.physics.dem
    inputs: [{ id: d1-blast-design, sha256: "<sha256>" }]
    params: { particles: 20000, steps: 2000 }
    resources: { gpu: exclusive, vram_gb_est: 4, disk_gb_est: 5 }
    determinism: bitwise
    retry: { oom_fallback: { particles: 10000 } }
    outputs: [{ path: fields.zarr, schema: zarr-field }]
  - id: s30_train
    env: pipeline
    entry: pitstudio_pipeline.train.unet
    inputs: [{ stage: st50_physics }, { id: mendeley-78ht3pjsr4, sha256: "7f4336a4…f402d" }]
    resources: { gpu: exclusive, vram_gb_est: 7 }
    determinism: statistical
```

The console accepts the same documents: `POST /jobs` is validated against this schema, so hostile input returns a 4xx
error ([Console](../studio/console.md)).

## Tool registry: `contracts/tools.schema.json` and `studio/tools.yaml`

### Entry fields

| Field | Meaning |
|---|---|
| `id` | stable tool id, used as `producer.tool` in manifests |
| `name`, `env` | display name and studio environment |
| `version` | read from the environment's lock file (or from the pinned binary for external tools), never typed by hand |
| `licence`, `osi` | SPDX id or licence name, and whether it is OSI-approved |
| `licence_class` | `own`/open class or `reference-only` ([Sources and licences](sources-and-licences.md)) |
| `ring` | Adopt, Trial, Assess or Hold |
| `lane` | live, replay or local-only |
| `role`, `cases` | the mining role and the cases that use the tool |
| `produces` | artefact kinds (e.g. `video`, `point-cloud`, `onnx`, `table`) |
| `status` | `not-yet-run`, `done` or `evaluated-not-adopted` (with a reason) |
| `alternatives_rejected` | short list with reasons |
| `notice` | trademark or licence notice (e.g. non-affiliation, "Built on NVIDIA Cosmos") |

### The 17 tools

| Tool (`id`) | Environment | Version source | Mining role | Cases |
|---|---|---|---|---|
| OpenUSD | `studio/` | `usd-core` 26.8 | pit scenes from real lidar; layers and variants | all |
| Warp | `studio/` | `warp-lang` 1.17.0 | own DEM, shallow water, dust particles, differentiable calibration | A3, C2, C3, D1 |
| Newton | `studio/` | `newton` 1.6.0 | implicit MPM granular flow, vehicles, Isaac Lab backend | A2, A3 |
| MuJoCo-Warp | `studio/` | `mujoco-warp` 3.12.0 | articulated shovel and loader kinematics | A1, A3 |
| PhysX / ovphysx | `studio/isaac/`, `studio/rtx/` | Isaac Sim lock; `ovphysx` 0.6.3 | vehicle visual twin; cross-engine rigid-body check | B1 |
| ovrtx | `studio/rtx/` | `ovrtx` 0.5.0.377615 | RTX lidar, radar and camera sensors | B1, B2, C3, E2 |
| Isaac Sim + Replicator | `studio/isaac/` | `isaacsim` 6.1.0.0 | RTX renders and synthetic data | B2, D1, videos |
| Isaac Lab | `studio/isaaclab/` | tag v3.0.0-EA | haul-truck and excavator policies | A2, A3 |
| USD Composer / Explorer (Kit) | `studio/kit/` | our extension; application generated outside the repo | scene review, path-traced media | C2, E1 |
| Cosmos Reason 2 | `studio/reason/` | llama.cpp b11381 + model revision | vision-language safety reasoning | B1, B2 |
| PyTorch | `pipeline/` | `torch` 2.14.1 | training of every learned model | A1, A3, B2, C1, C2, D1, D2 |
| ONNX Runtime (+Web) | `pipeline/`, `web/` | `onnxruntime` 1.30.0; ORT-web pinned in the web lock | parity reference, GPU baseline, in-browser inference | all learned |
| TensorRT | `pipeline/accel/` | `tensorrt-cu13-libs` 11.3.0.99 | accelerated inference of our models | A1, B2, D1 |
| NVENC / FFmpeg | `studio/` + external | FFmpeg 8.1 (pinned zip), `pynvvideocodec` 2.2.3 | AV1 + H.264 video encode | all videos |
| Nsight / NVML | runner + external | `nvidia-ml-py` 13.615.71 | GPU evidence and profiling | all GPU stages |
| three.js / R3F / 3D Tiles | `web/` | web lock | 3D pit and replays in the browser | all |
| Rapier / WebGPU / Pyodide | `web/` | web lock | live rigid bodies, WGSL kernels, `minephys` in the browser | B1, A3, all analytical |

Versions above are those in the committed locks today; the web packages enter `web/pnpm-lock.yaml` in the web phase.
Three further tools are documented as **evaluated, not adopted** (NVIDIA cuOpt, PhysicsNeMo, Cosmos Predict/Transfer),
each with its reason ([cuOpt](../frameworks/not-adopted-cuopt.md), [PhysicsNeMo](../frameworks/not-adopted-physicsnemo.md),
[Cosmos Predict/Transfer](../frameworks/not-adopted-cosmos-predict-transfer.md)).

### An illustrative registry entry

```yaml
# studio/tools.yaml  (illustrative)
- id: ovrtx
  name: ovrtx (RTX sensors)
  env: studio/rtx
  version: { from_lock: studio/rtx/uv.lock, package: ovrtx }
  licence: LicenseRef-NvidiaProprietary
  osi: false
  licence_class: reference-only
  ring: Assess
  lane: replay
  role: truck lidar in dust and rain, drone survey camera, crusher camera, proximity radar
  cases: [B1, B2, C3, E2]
  produces: [point-cloud, image, video]
  status: not-yet-run
  notice: "Not affiliated with or endorsed by NVIDIA; performance data local-only (licence)."
```

## From registry to web tool map

- **Map.** `/studio` renders an interactive tool map (React Flow, lazy-loaded) whose node positions are precomputed
  from `tools.yaml`. Node colour = lane, badge = ring, icon = licence class. Edges are file handoffs:
  USD → physics → sensors and synthetic data → training → acceleration → encoding → web. A static SVG and a data table
  are the fallback for no-JS readers and screen readers.
- **Tool pages.** `/studio/tools/:toolId` shows the identity card (version from the lock, licence, ring, environment),
  the mining role, the **artefacts the tool produced** (filtered by `producer.tool`, each with a LIVE / REPLAY /
  STATIC badge), provenance chips, limits and failures, the reproduce command and the rejected alternatives.
- **Honesty rules in CI.** A registry entry with `status: done` must have at least one published artefact whose
  manifest names it as producer; a tool with nothing published shows "not yet run", never a stock image; proprietary
  tools contribute outputs only, never binaries, engines, caches or NVIDIA assets; renders show our scenes, not NVIDIA
  application UI ([Showcase rules](../web/showcase-rules.md)).

## Assumptions and limits

- The runner is deliberately small (about 1,500 lines of code); if recipes need features beyond a DAG with cache,
  locks, guards, retries and shards, the plan re-assesses an existing task runner rather than growing this one.
- Recipes refer to data by id and digest, so a recipe cannot silently pick up a different file; the cost is that every
  new input needs a registry entry first.
- A tool's ring and lane are claims about the project, not about the tool in general.

## In PitStudio

- **Files:** `contracts/recipe.schema.json`, `contracts/tools.schema.json`, `studio/recipes/cases/`, `studio/recipes/_bench/` and
  `studio/recipes/_profiles/` (all created in the build phase), `studio/tools.yaml`.
- **Consumers:** the runner (`src/pitstudio/runner/`), the console (`POST /jobs`), the web `/studio` routes, CI.
- **Status:** schemas and registry are written in the specification and build phases. Commands, once the runner exists:

```bash run deferred=P6
uv run --extra runner studio plan studio/recipes/cases/<case>.yaml --profile linux-gpu
uv run --extra runner studio run studio/recipes/cases/<case>.yaml --stage st50_physics
```

## References

1. React Flow (`@xyflow/react`) package metadata. https://registry.npmjs.org/@xyflow/react/latest
2. uv CLI reference (`uv run --project`, `--frozen`). https://docs.astral.sh/uv/reference/cli/
3. Microsoft, *Job Objects* (child-process cleanup used by the runner). https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
4. filelock documentation (OS-level file locks for `gpu0.compute` and `gpu0.nvenc`). https://py-filelock.readthedocs.io/en/latest/

# C4 level 2: containers

> The deployable and runnable units of PitStudio (console, runner, studio and pipeline environments, store, core
> library, web app, repository and releases), what each one holds, how they talk, and which of them may ever run in CI.
> · Part of: [architecture](README.md) · Related: [C4 context](c4-context.md) · [studio environments](../studio/environments.md) ·
> [runner](../studio/runner.md) · [deployment](deployment.md)

## What and why

At level 2 the C4 model opens the system box and shows its containers: separately running applications and data
stores. PitStudio has more containers than a typical research repository because the tools it drives cannot share a
Python interpreter, a CUDA runtime or a licence. The container boundaries are therefore not a matter of taste; each one
is forced by a version pin, a process-isolation rule or a licence ([DEC-0001](decisions/DEC-0001-isolated-studio-environments.md)).

## The diagram

![C4 containers of PitStudio](../assets/diagrams/c4-containers.svg)

*On the workstation, the console sends jobs to the runner, the runner launches stages in isolated environments that
import the core library and write to the store, and `studio publish` hands baked files to the public repository and
release assets, from which `pages.yml` builds the web app.*

## Containers

| Container | Path | Technology (versions from the locks) | Responsibility | Runs in CI? |
|---|---|---|---|---|
| Studio console | `api/`, `web/console/` | FastAPI 0.142.2, uvicorn 0.54.0 (root extra `api`); a separate web entry reusing the shell | Recipes, queue, runs, artefacts and an SSE event and telemetry stream, bound to 127.0.0.1 with `/health` | Contract tests only (Schemathesis), no GPU |
| Runner | `src/pitstudio/runner/` | Python 3.14; filelock 4.0.10, psutil 7.2.2, nvidia-ml-py 13.615.71 (root extra `runner`) | `studio plan / run / queue / worker / status / gc / publish / bench / profile`; DAG, cache, locks, guards, telemetry, resume | Unit tests against a fake GPU backend; `studio plan` for every recipe with the `linux-gpu` profile |
| Open studio environment | `studio/` | Python 3.14; usd-core 26.8, warp-lang 1.17.0, newton 1.6.0 (mujoco-warp 3.12.0), usd-validation-nvidia 1.22.0, simready-validate 2026.8.0, PyNvVideoCodec 2.2.3, nvidia-ml-py | Scene build and validation, GPU physics (DEM, MPM, shallow water, dust, vehicles), media encoding, telemetry | The CPU-capable subset (scene authoring, USD validation, Warp CPU kernels) |
| Isaac environment | `studio/isaac/` | Python 3.12 (uv-managed); isaacsim 6.1.0.0, torch 2.11.0 (cu130) | RTX renders, Replicator synthetic data, PhysX vehicle visual twin, lidar rain | Never |
| RTX sensor environment | `studio/rtx/` | Python 3.12; ovrtx 0.5.0.377615, ovstage 0.2.0.377349, ovphysx 0.6.3 | Kit-less RTX camera, lidar and radar | Never |
| Robot-learning environment | `studio/isaaclab/` | Python 3.12; Isaac Lab at the `v3.0.0-EA` tag, kit-less on Newton | Haul-truck and excavator policies | Never |
| Kit extension | `studio/kit/` | Kit's own Python; only PitStudio's Apache-2.0 extension, `.kit` file and scripts | Headless path-traced captures and scene validation in USD Composer/Explorer generated outside the repository | Never |
| VLM evaluation | `studio/reason/` | llama.cpp b11381 (external binary, CUDA build) | Cosmos Reason 2 tasks scored against scene ground truth | Never |
| Pipeline environment | `pipeline/` | Python 3.14; torch 2.14.1 (cpu / cu126 / cu130 extras), onnxruntime(-gpu) 1.30.0, onnx 1.23.1, minehaulsim 0.12.1, oreblocks 0.5.2 | `s00_download` → `s05_synthesize` → `s10_preprocess` → `s20_feature_extraction` → `s30_train` → `s40_infer` → `s50_evaluate` → `s60_export` | CPU smoke on samples (`--extra cpu`) |
| Acceleration environment | `pipeline/accel/` | Python 3.14; TensorRT 11.3.0.99 (cu13 bindings and libs), Polygraphy 0.53.6, CUDA runtime 13.4.92 | `s62_accel` (engines) → `s64_bench` (latency, throughput, energy, parity) | Never; engines are never committed |
| Studio store | `PITSTUDIO_STORE` (default a short path such as `C:\ps`) | Files + SQLite (`queue.db`, WAL) | Content-addressed outputs, run folders, the queue, lock files, human-readable views | No |
| Core library and contracts | `minephys`, `src/pitstudio/`, `contracts/` | numpy 2.5.3, pydantic 2.13.5, jsonschema 4.26.0; JSON Schema 2020-12 | Sourced models, manifest handling, lane gate, generated types | Yes: tests, type checks, schema drift |
| Web app | `web/` | React 19.3.0, React Router 8.4.0 (framework mode, prerendered), Vite 8.3.2, Node 24 | The public site: routes, live engines, replays, the studio showcase | Yes: build, budgets, Playwright E2E |
| Repository and releases | GitHub `main`, `assets-vX.YY.ZZZ` | git; GitHub Releases | Code, docs, baked files < 10 MB (≤ 100 MB in total); larger assets as release assets pinned by SHA-256 | Size checks |

The `studio/kit` and `studio/reason` folders, the console and the runner are planned for the build phase; the other
environments are already locked in the repository. External tools run only as subprocesses and are never vendored:
the FFmpeg 8.1 LGPL build (NVENC), Nsight Systems and Compute, COLMAP, Brush and llama.cpp.

## How the containers talk

| From → to | Mechanism | Contract |
|---|---|---|
| Console → runner | `POST /jobs` on 127.0.0.1, validated against the recipe schema (hostile input → 4xx) | `contracts/recipe.schema.json` |
| Runner → console | Server-sent events from `events.jsonl` and 1–4 Hz telemetry [1] | event schema |
| Runner → environments | `uv run --project <env> --frozen …` in a Windows job object (a process group on Linux) [2] [3] | a job-spec file per stage |
| Environment → environment | Never directly; only versioned files plus `manifest.json` | `contracts/manifest.schema.json` |
| Environments → store | Outputs written to `runs/<run_id>/tmp/`, promoted by rename after schema validation, then content-addressed | manifest with SHA-256 per output |
| Store → repository and releases | `studio publish <run_id>`: web artefacts + run card; files < 10 MB to git, larger ones to the release upload list | web manifest, licence class, lane |
| Repository → web app | `pages.yml` build | the web manifest is read at build time |
| Visitor → web app | HTTPS, static files, same origin | — |

Two rules hold throughout. **Environments never import each other and never share a virtual environment**, so the
Python 3.12 NVIDIA runtimes and the Python 3.14 open stack meet only through schema-validated files. **ovrtx is never
imported in the same process as Kit or Isaac Sim**, because each carries an RTX runtime.

## Data stores

```text
PITSTUDIO_STORE/                 (outside the repository; default a short path such as C:\ps)
  cas/sha256/ab/…                content-addressed outputs
  runs/<run_id>/                 manifest.json, events.jsonl, telemetry.parquet, logs/, nsys/
  views/<recipe>/<stage>/        human-readable hardlinks into cas/
  queue.db                       the worker's queue (SQLite, WAL)
  locks/                         gpu0.compute, gpu0.nvenc
PITSTUDIO_DATA/                  raw, interim and processed datasets (never committed)
PITSTUDIO_MODELS/                checkpoints and exported models
PITSTUDIO_TMP/                   scratch, local bench reports
studio/capabilities.json         committed capability report (no host identifiers)
```

The machine-wide lock directory `GPU_LOCK_DIR` is shared by every project on the machine, because they all share one
GPU; a `gpu0.hold` file in it stops all GPU work, and the bench refuses to start while it exists. Windows unlocks a
`LockFileEx` lock when its process dies, so a crashed job cannot leave a permanent stale lock [4] [5]. Per-process VRAM
is not observable under the Windows WDDM driver model, so memory guards use device-level free memory [6].

## Assumptions and limits

- Several uv projects (seven today: the root, `studio/`, `studio/isaac/`, `studio/rtx/`, `studio/isaaclab/`,
  `pipeline/`, `pipeline/accel/`) must stay resolved; each has its own lock file and is re-locked deliberately.
- Isaac Lab is pinned to an early-access tag; its own dependency pins may differ from Isaac Sim's and are taken from its
  lock file, not assumed.
- The store layout is a design target for the build phase; only the bench and its local report folder exist today.

## In PitStudio

- Environment details and the commands to create each one: [studio environments](../studio/environments.md) and
  [set up the studio](../guides/set-up-the-studio.md).
- Runner internals: [runner](../studio/runner.md); console: [console](../studio/console.md); stages:
  [pipeline stages](../pipelines/pipeline-stages.md) and [studio stages](../pipelines/studio-stages.md).
- Status: environments `studio/`, `studio/isaac/`, `studio/rtx/`, `studio/isaaclab/`, `pipeline/` and
  `pipeline/accel/` are locked; runner, console, `studio/kit/` and `studio/reason/` are planned for the build phase.

## References

1. FastAPI. Server-sent events. https://fastapi.tiangolo.com/tutorial/server-sent-events/
2. Astral. uv command-line reference (`uv run --project`, `--frozen`). https://docs.astral.sh/uv/reference/cli/
3. Microsoft Learn. Job objects. https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
4. filelock documentation. https://py-filelock.readthedocs.io/en/latest/
5. Microsoft Learn. LockFileEx. https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex
6. NVIDIA. nvidia-smi documentation. https://docs.nvidia.com/deploy/nvidia-smi/index.html

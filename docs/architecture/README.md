# Architecture

> PitStudio's architecture in arc42-lite form: goals, constraints, context, solution strategy, building blocks,
> runtime and deployment views, cross-cutting concepts, quality requirements and risks, with the C4 views and the
> decision records one click away. · Part of: [documentation home](../README.md) · Related:
> [C4 context](c4-context.md) · [C4 containers](c4-containers.md) · [lanes](lanes.md) · [decisions](decisions/README.md)

## Pages in this section

| Page | What it covers |
|---|---|
| [C4 context](c4-context.md) | The system, its two kinds of user and the external systems it talks to |
| [C4 containers](c4-containers.md) | What runs where: console, runner, studio and pipeline environments, store, core library, web app |
| [Lanes](lanes.md) | Live, precompute, replay and local-only, and the measured gate that assigns them |
| [Deployment](deployment.md) | GitHub Pages, release assets copied at build, the local studio, and what never runs in CI |
| [Quality and validation](quality-and-validation.md) | Test-first development, metamorphic relations, the pre-registered decision rule, quality gates |
| [Decisions](decisions/README.md) | DEC-0001 to DEC-0017: every major choice with its alternatives |

The structure below follows arc42 (sections 1–11, glossary in [reference](../reference/glossary.md)).

![The four parts of PitStudio around one shared core](../assets/diagrams/pitstudio-overview.svg)

*Four parts, one shared core: the local studio, the static web app, the knowledge base and the scalable base all depend
on `minephys`, the slim `pitstudio` package and the JSON Schema contracts.*

## 1. Goals

**Requirement in one sentence.** A full local studio that applies every Omniverse-class tool that runs on one
workstation to open-pit mining, robustly and reproducibly, plus a static web app that explains, runs and showcases all
of it, plus a knowledge base, on a base that scales to a Linux GPU host.

| Priority | Quality goal | What it means here |
|---|---|---|
| 1 | Honesty | Every external number is sourced; every artefact carries its lane; synthetic and precomputed content is labelled; "better" requires a paired confidence interval; a tool with no artefact shows "not yet run" |
| 2 | Reproducibility | Locked environments, seeds, content-addressed cache keys, manifests with tool versions read from the lock files; the public repository reproduces on CPU from committed artefacts |
| 3 | Licence cleanliness | Only our code, our USD and our outputs are published; NVIDIA software is reference-only; performance data follows each licence |
| 4 | Static delivery within budgets | A GitHub Pages site with a first view ≤ 2 MB and a total ≤ 500 MB that still works without WebGPU |
| 5 | Robust studio | One heavy GPU job at a time, pre-flight guards, telemetry, resumable shards, no orphan processes |
| 6 | Scalability | The same recipes and lock files on a Linux GPU host; only a machine profile changes |

## 2. Constraints

**Technical.**

- **One reference workstation:** an RTX 5000 Ada Generation Laptop GPU with 16 GB of VRAM and a power-limited laptop
  envelope, driver 582.78 (R580, CUDA 13.0), Windows 11. Isaac Sim lists 16 GB as its minimum VRAM class and does not
  list laptop GPUs [1].
- **Python split:** Isaac Sim 6.1, Kit 110.3, Isaac Lab 3.0 and the Kit-less ovrtx libraries require Python 3.12 (or
  ≤ 3.13), while the open GPU stack (usd-core 26.8, Warp 1.17, Newton 1.6) runs on the apps' Python 3.14 [2] [3].
- **Process isolation:** ovrtx and Kit each carry an RTX runtime and must not share a process; TensorRT 11.3 and the
  TensorRT 10.14 libraries used by ONNX Runtime's TensorRT EP cannot share an environment ([DEC-0001](decisions/DEC-0001-isolated-studio-environments.md)).
- **No RTX in WSL2:** the Isaac Sim container is Linux-only, OpenGL–CUDA interop is unsupported in WSL2, and Vulkan/RTX
  initialisation failures are reported there [4] [5] [6]. The studio is Windows-native.
- **Static hosting:** GitHub Pages serves static files only, with a 1 GB site limit, a 10-minute deploy limit, a soft
  100 GB per month bandwidth and 10 builds per hour [7].
- **Hosted CI has no RTX GPU,** and NVIDIA's terms limit Omniverse to NVIDIA platforms; studio stages never run in CI.

**Licence.** NVIDIA's Software License Agreement forbids making its components subject to an open-source licence and
forbids publishing benchmark or performance data of the covered software without permission (§8.9) [8]. The OpenUSD
licence (TOST-1.0) is Apache-derived but not OSI-approved [9]. Share-alike datasets must stay share-alike.

**Organisational.** The repository is public, unbranded and real: no corporate names, no internal references, no machine
paths. Documentation comes before specification, specification before code, failing tests before implementation.
Installs that need administrator rights (a newer driver, Nsight Systems captures) are the maintainer's acts, each with a
declared purpose and a fallback ([owner acts and licences](../studio/owner-acts-and-licences.md)).

## 3. Context and scope

PitStudio talks to two kinds of person (visitors and the maintainer) and five external systems (GitHub, open data
providers, package and model indexes, and the locally installed NVIDIA runtimes). See [C4 context](c4-context.md).

Out of scope: a live digital twin with telemetry from a real operation; engineering design or regulatory approval of
slopes, tailings or blasts; a backend for the public site; Kubernetes, Ray, workflow servers and multi-node training.

## 4. Solution strategy

| Concern | Approach | Decision |
|---|---|---|
| Many tools with incompatible pins | One uv project per tool family, entered only through `uv run --project <env> --frozen`; file-only handoff | [DEC-0001](decisions/DEC-0001-isolated-studio-environments.md) |
| Long GPU jobs on one shared GPU | A small in-repo runner: DAG of stages, content-addressed cache, per-device GPU locks, NVML guards and telemetry, resumable shards | [DEC-0002](decisions/DEC-0002-in-repo-runner.md) |
| Operating the studio | A loopback-only FastAPI console plus a CLI that always works without it | [DEC-0003](decisions/DEC-0003-loopback-console.md) |
| Proprietary SDKs in a public repo | Reference, never redistribute; licence classes on every artefact; trademark notice | [DEC-0004](decisions/DEC-0004-proprietary-sdks-reference-only.md) |
| Performance numbers of proprietary software | Published only where the licence allows; otherwise `performance: local-only` | [DEC-0005](decisions/DEC-0005-performance-data-licence-rule.md) |
| 3D and simulation on a static site | USD in the studio; glTF, 3D Tiles, quantized shards, AV1 + H.264 video and splats on the web; WebGPU per route with WebGL fallback; parity by system class | [DEC-0006](decisions/DEC-0006-3d-and-simulation-on-static-web.md) |
| Assets larger than git allows | GitHub Release assets pinned by SHA-256 and copied into the Pages artifact at build | [DEC-0007](decisions/DEC-0007-large-assets-as-release-assets.md) |
| Driver and runtime versions | Chosen by on-machine checks (Isaac Sim Compatibility Checker, smoke tests), not assumed | [DEC-0008](decisions/DEC-0008-isaac-sim-version-by-compatibility-checker.md) |
| A vision-language model on Windows | Cosmos Reason 2 as our own Q8_0 GGUF through llama.cpp, BF16 as reference | [DEC-0009](decisions/DEC-0009-vlm-llamacpp-gguf.md) |
| Accelerated inference | TensorRT 11.3 with a parity gate per engine | [DEC-0010](decisions/DEC-0010-tensorrt-per-engine-parity.md) |
| Video | NVENC through an FFmpeg 8.1 LGPL build, AV1 + H.264, VMAF-targeted | [DEC-0011](decisions/DEC-0011-nvenc-ffmpeg-8-1.md) |
| Granular physics | Own Warp DEM + Newton implicit MPM | [DEC-0012](decisions/DEC-0012-granular-physics-warp-newton.md) |
| Haulage simulation | `minehaulsim` as the reference engine + a TypeScript twin with exact-trace parity | [DEC-0013](decisions/DEC-0013-haulage-engine-minehaulsim.md) |
| Survey reconstruction | Brush for Gaussian splats | [DEC-0014](decisions/DEC-0014-splats-brush.md) |
| People in synthetic scenes | MakeHuman CC0 exports | [DEC-0015](decisions/DEC-0015-people-assets-makehuman.md) |
| Claims of improvement | A pre-registered decision rule on paired confidence intervals | [DEC-0016](decisions/DEC-0016-pre-registered-decision-rule.md) |
| Domain knowledge as code | The companion package `minephys` holds the sourced models and parameter tables | [DEC-0017](decisions/DEC-0017-companion-package-minephys.md) |

## 5. Building block view

| Area | Path | Responsibility | Runtime | Status (2026-10-04) |
|---|---|---|---|---|
| Core package | `src/pitstudio/` | Contracts glue, manifest, lane gate, I/O; hosts the runner | Python 3.14 (root uv project) | scaffold |
| Runner | `src/pitstudio/runner/` (extra `runner`) | Recipes, DAG, CAS cache, GPU locks, guards, telemetry, queue, resume, `gc`, `publish`, `bench`, `profile` | Python 3.14 | planned (build phase); `filelock`, `psutil`, `nvidia-ml-py` already locked |
| Console | `api/`, `web/console/` | Loopback FastAPI + SSE and a console web entry | Python 3.14, React | planned (build phase); `fastapi` and `uvicorn` locked as the `api` extra |
| Contracts | `contracts/*.schema.json` | JSON Schema 2020-12 for manifests, recipes, tool registry, capabilities, bench results; types generated for Python and TypeScript | — | `capabilities.schema.json` exists; the rest arrive with the specifications |
| Open studio | `studio/` | Scene building (usd-core), GPU physics (Warp, Newton, MuJoCo-Warp), validation, media encoding, telemetry | Python 3.14 | environment locked |
| NVIDIA studio envs | `studio/isaac/`, `studio/rtx/`, `studio/isaaclab/`, `studio/kit/`, `studio/reason/` | RTX renders and synthetic data; Kit-less RTX sensors; robot learning; scene review; vision-language evaluation | Python 3.12 (uv-managed), Kit, llama.cpp | `isaac`, `rtx`, `isaaclab` locked; `kit`, `reason` planned |
| Capability bench | `studio/bench/` | Runs probes under the machine-wide GPU lock and writes `studio/capabilities.json` | Python 3.14 + each env | written; not yet run on the reference machine |
| Pipeline | `pipeline/`, `pipeline/accel/` | Download → synthesize → preprocess → features → train → infer → evaluate → export; TensorRT builds and benchmarks | Python 3.14, torch cu130; TensorRT 11.3 | environments locked |
| Companion library | `minephys` (separate repository) | Sourced mining models and cited parameter tables, numpy-only, Pyodide-safe | Python ≥ 3.12 | git dependency until its first release |
| Web app | `web/` | Static React Router 8 site with live engines, replays and the studio showcase | Node 24, pnpm | shell, routes and access gate built; content routes are stubs |
| Specifications and checks | `specs/`, `tools/`, `.github/workflows/` | Constitution, thresholds, traceability; CI checks | — | active |

## 6. Runtime view

**Scenario 1: the maintainer runs a case recipe** (planned; the runner arrives in the build phase).

1. `studio plan <recipe>` resolves the recipe's DAG against the machine profile, computes every stage's cache key
   (stage code digest + lock digest + parameters + derived seed + input digests) and prints cache hits, misses and the
   disk and VRAM estimates.
2. `studio run <recipe>` queues the stages. The single worker takes the `gpu0.compute` lock for any stage that declares
   exclusive GPU use, runs the pre-flight guards (free VRAM, disk, temperature, required capabilities from
   `studio/capabilities.json`) and launches the stage with `uv run --project <env> --frozen` inside a Windows job object.
3. During the stage, a 1–4 Hz NVML sampler records power, clocks, throttle reasons and VRAM with NVTX ranges. Outputs go
   to a temporary folder and are promoted only after they validate against their schema.
4. The stage writes `manifest.json` (recipe hash, seeds, tool versions from the lock, GPU and driver, telemetry summary,
   determinism class, licence class, SHA-256 per output; no host names, user names or absolute paths) into the store
   under `PITSTUDIO_STORE`.
5. `studio publish <run_id>` bakes the run into web artefacts and a run card. Files under 10 MB go to git; larger ones
   join the release upload list.

**Scenario 2: a visitor opens a case.** The prerendered page loads (≤ 200 KB of initial JavaScript, first view ≤ 2 MB).
The live tab runs the analytical model or the discrete-event simulation in a web worker; the replay tab streams a baked
video or shard only after the visitor asks for it; the tier badge shows T1 (WebGPU), T2 (WASM) or T0 (baked). The site
never contacts a local studio unless the visitor clicks "connect to my local studio".

**Scenario 3: a push or pull request.** CI runs lint, type checks, the CPU test subset, traceability, TDD replay, the
repository and documentation checks and the pipeline CPU smoke, then builds the web app with its initial-JS budget and
runs the Playwright end-to-end tests. A push to `main` also runs `pages.yml`, which builds, tests and deploys the site.
See [quality and validation](quality-and-validation.md) and [deployment](deployment.md).

## 7. Deployment view

Three nodes: the maintainer's workstation (studio, pipeline, store, console; local-only), GitHub (repository, Actions,
release assets, Pages) and the visitor's browser (static site, compute tiers). See [deployment](deployment.md) and
[C4 containers](c4-containers.md).

## 8. Cross-cutting concepts

- **Contracts first.** Every cross-boundary file has a JSON Schema 2020-12 under `contracts/`; Python and TypeScript types
  are generated, never hand-written, and CI checks for drift ([data contract](../data-contract/README.md)).
- **Manifests and provenance.** Studio runs and web assets share one manifest format: producer tool and version (from
  the lock), recipe hash, seeds, determinism class, licence class, lane, telemetry summary, encoder record, asset host
  (git or release) and SHA-256 ([manifest](../data-contract/manifest.md)).
- **Determinism classes.** Each stage declares `bitwise` (scene authoring, deterministic Warp kernels), `statistical`
  (MPM, RTX rendering, synthetic data, training) or `none` (documented exceptions), and is re-run to check it.
- **Licence and redistribution classes.** Every source and artefact has one licence class (`licence_class`:
  `public-domain`, `open-no-attribution`, `attribution`, `share-alike`, `own`, `display-only`, `reference-only`); a
  derived artefact takes the most restrictive class of its inputs. Each source in `data/sources.yaml` also has a coarser
  redistribution class (`redistributable`, `derived-only`, `no-redistribution`) that decides what may leave the machine
  ([sources and licences](../data-contract/sources-and-licences.md),
  [DEC-0004](decisions/DEC-0004-proprietary-sdks-reference-only.md)).
- **Lanes and honesty labels.** LIVE, REPLAY or STATIC on every artefact card; `performance: local-only` for
  licence-restricted performance data ([lanes](lanes.md)).
- **Parity by system class.** Exact event traces for discrete-event and analytical engines, snapshot hashes for
  deterministic rigid-body physics, per-kernel and observable parity for chaotic particle systems, numerical tolerances
  for ONNX models ([DEC-0006](decisions/DEC-0006-3d-and-simulation-on-static-web.md)).
- **Data folders.** Datasets, models and temporary files live outside git under `PITSTUDIO_DATA`, `PITSTUDIO_MODELS` and
  `PITSTUDIO_TMP`; the studio store under `PITSTUDIO_STORE` ([configuration](../reference/configuration.md)).
- **Security.** The console binds to 127.0.0.1 only and validates every job against the recipe schema (hostile input →
  4xx). CI needs no credentials of the studio. The site's access gate is a demo gate and says it is not a security
  boundary ([access gate](../web/access-gate.md)).
- **Internationalisation and accessibility.** English and Spanish everywhere in the web app; WCAG 2.2 AA; light and
  dark themes; reduced motion respected; no autoplay.
- **Telemetry as evidence.** GPU telemetry of open-runtime stages is published as charts; Nsight captures are summarised
  locally ([Nsight and NVML](../frameworks/nsight-nvml.md)).

## 9. Architecture decisions

Seventeen decision records, each with context, decision, at least two alternatives and consequences:
[decisions](decisions/README.md).

## 10. Quality requirements

| Quality | Scenario | Measure |
|---|---|---|
| Honesty | A model result is shown as "better" | Only if the paired 95 % confidence interval of the difference excludes 0; otherwise "no significant difference" |
| Honesty | A studio tool page is opened before the tool has run | It shows "not yet run"; CI fails if a tool marked done has no artefact |
| Reproducibility | A recipe is re-run with the same inputs | Cache hit; `bitwise` stages reproduce the SHA-256, `statistical` stages reproduce observables within thresholds |
| Licence | A licence-restricted stage publishes a timing | CI fails on any performance field for a stage marked `performance: local-only` |
| Performance (web) | First visit on a laptop | ≤ 200 KB gzip initial JavaScript; first view ≤ 2 MB; heavy assets load only on user action |
| Robustness | A training stage runs out of GPU memory | Classified retry with the stage's declared fallback; other failures fail fast with the log tail in the manifest |
| Scalability | A recipe is planned for a Linux GPU host | CI plans every recipe with the `linux-gpu` profile against a fake GPU backend with no OS or path leaks |
| Accessibility | Any route in either theme and language | axe clean; Lighthouse accessibility ≥ 0.95 |

Details, thresholds and the quality gates are on [quality and validation](quality-and-validation.md).

## 11. Risks and technical debt

| # | Failure story | Mitigation |
|---|---|---|
| 1 | Isaac Sim at the 16 GB minimum runs out of memory or crawls on a power-limited laptop | Capability probe first; ≤ 720p and 1–2 cameras; ovrtx as a second RTX path; the open lane carries the science |
| 2 | Synthetic-only perception fails on real images | Sim-to-real measured only for fragmentation (real labelled set); equipment/people reported as "not measured" unless the real probe is labelled; randomisation ablation and corruption curves; bounded claims |
| 3 | A licence trap appears late (an NVIDIA asset, a template header, a published SDK benchmark, a missing Cosmos attribution) | Licence classes and repository guards for headers, engines, GGUF files, `omniverse://` URLs and local-only performance; reviewed again before data publication and before release |
| 4 | Unverified constants are presented as real calculations | Verification status per table row; pinned to primary pages during specification; UNVERIFIED flagged in the UI |
| 5 | The web app is too heavy | First view ≤ 2 MB; lazy assets; compute tiers; CI budgets; Lighthouse |
| 6 | Scope explosion across 17 tools stalls the product | Milestone order; optional tools (Isaac Lab MPM fine-tuning, Cosmos, Composer) can end as an honest "not adopted" page; core cases never depend on them |
| 7 | Parity breaks between Python and TypeScript/WGSL | Parity by system class; counter-based PRNG; no transcendental `Math.*` calls in variate generation |
| 8 | Pre-release APIs (ovrtx, Isaac Lab EA, R3F v10) break | Lock files; thin adapters; watched versions; Isaac Lab moves to its GA tag when it ships |
| 9 | The 3.12 ↔ 3.14 split corrupts handoffs | Schema-validated file handoff on both sides |
| 10 | Owner acts are not given (Cosmos terms, Kit prompt, Nsight admin) | Each tool degrades to "not run" or to NVML-only evidence; nothing else blocks |
| 11 | TensorRT silently returns wrong outputs (a known D-FINE issue reported on several TensorRT versions and on the GPU's architecture) | Parity gate per engine on every TensorRT version and execution provider; no TensorRT path is assumed safe; failing variants are reported as rejected |
| 12 | Disk fills during synthetic data or physics (tens of GB) | Runner disk guard, per-class quotas, `gc` from pinned manifests |
| 13 | The runner grows into a framework | About 1,500 lines of code as a budget; re-assess doit beyond it |
| 14 | ovrtx lidar silently returns zero points for wide elevation fans on Windows | Per-frame point-count guard; elevation fan limited to a tested range; fail fast |
| 15 | Isaac Lab kit-less on Windows fails, or pins drift between the EA tag and its branch | Bootstrap smoke test; one pinned commit; the optional lane may end as "evaluated, not adopted" |
| 16 | Repository history grows past 1 GB through re-baked assets | Heavy assets as release assets copied at build; ≤ 100 MB baked in git; re-bake only at releases; CI repository-size check |
| 17 | MakeHuman CC0 conditions do not fit the use | Licence conditions re-read at bootstrap; fallback procedural mannequins, stated in the B2 card |
| 18 | Brush (last release more than 12 months ago) fails on this GPU | Bootstrap smoke; fallback gsplat with a maintainer-installed CUDA toolkit, or E2 with DEM differencing only |
| 19 | A 3.12 environment picks up the Microsoft Store Python shim | uv-managed interpreters only (`python-preference = "only-managed"`); the bootstrap probe asserts the interpreter |
| 20 | The real fragment labels are unusable | Checked at bootstrap: usable (960 labelled images = 240 originals × 4 augmentations, split by source group); fallback would be a synthetic-only claim |

**Current debt.** The capability probes are written but have not run on the reference machine, so every studio
capability is unconfirmed on it. The NOTICE file does not yet carry the trademark statement that
[DEC-0004](decisions/DEC-0004-proprietary-sdks-reference-only.md) requires.

## References

1. Isaac Sim 6.1 requirements. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html
2. `isaacsim` on PyPI (6.1.0.0, Python ==3.12). https://pypi.org/pypi/isaacsim/json
3. ovrtx repository (Python 3.10–3.13). https://github.com/NVIDIA-Omniverse/ovrtx
4. Isaac Sim container installation (Linux-only; Windows and WSL unsupported).
   https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_container.html
5. NVIDIA. CUDA on WSL user guide (OpenGL–CUDA interop unsupported). https://docs.nvidia.com/cuda/wsl-user-guide/index.html
6. Community report: Isaac Sim fails in WSL2 + Docker due to Vulkan/RTX initialisation (2026-03-30).
   https://github.com/robotmcp/ros-mcp-server/issues/289
7. GitHub Docs. GitHub Pages limits. https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
8. NVIDIA Software License Agreement (2026-05-07).
   https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
9. OpenUSD licence (TOST-1.0). https://raw.githubusercontent.com/PixarAnimationStudios/OpenUSD/release/LICENSE.txt

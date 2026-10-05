# Frameworks

> One page per engine and tool that PitStudio runs: what it is, the exact version this repo pins, its licence class,
> its role in open-pit mining, and its limits. · Part of: [Docs home](../README.md) · Related:
> [Studio](../studio/README.md) · [Environments](../studio/environments.md) · [Tool matrix](../cases/tool-matrix.md) ·
> [DEC-0004](../architecture/decisions/DEC-0004-proprietary-sdks-reference-only.md)

## What and why

PitStudio is a physical-AI simulation studio for open-pit mining. It uses 17 studio tools, from the Omniverse-class
runtimes to the browser engines, plus three mining packages and a few external tools. Every tool here has at least one job tied to a case. A
tool that was evaluated and then rejected has its own "not adopted" page, so the reason stays on record.

Two rules hold on every page:

- **Versions come from the lock files**, never from memory: the `uv.lock` of the environment that holds the tool, or
  `web/pnpm-lock.yaml`. External tools (FFmpeg, llama.cpp, COLMAP, Brush, Nsight) are pinned by version and SHA-256 of
  the release archive. Web libraries that the web phase has not yet added show their planned version and say
  "not yet in the web lock".
- **Licence class** is one of two values:
  - **open**: an OSI licence, or an Apache-derived one with a recorded exception (OpenUSD).
  - **reference-only**: NVIDIA proprietary software or model weights. The repo references them by name and version,
    never redistributes binaries, assets, engines or caches, and publishes only our own outputs
    ([DEC-0004](../architecture/decisions/DEC-0004-proprietary-sdks-reference-only.md)).

  The performance data of Isaac Sim, Kit, Replicator, ovrtx and TensorRT for RTX stay local, because their licences
  forbid publishing them. Regular TensorRT numbers of our own models are published
  ([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)).

NVIDIA product names are used nominatively. PitStudio is not affiliated with or endorsed by NVIDIA.

![Studio tool map: 17 tools along the file-handoff chain](../assets/diagrams/tool-map.svg)

*The 17 studio tools along the handoff chain USD → physics → sensors and synthetic data → training → acceleration →
encoding → web. Border colour = lane; dashed border = reference-only.*

## Tool catalogue

Rings follow the technology-radar convention: **Adopt** (default choice), **Trial** (used, still being proven on this
machine), **Assess** (optional lane, may end as "evaluated, not adopted"), **Hold** (not used).

| Tool | Version pinned (lock) | Licence · class | Ring | Environment | Mining role | Page |
|---|---|---|---|---|---|---|
| OpenUSD (`usd-core`) | 26.8 | TOST-1.0 (Apache-derived) · open | Adopt | `studio/` (3.14) | Pit scenes from real lidar: terrain, design, fleet, sensor and weather layers | [OpenUSD](openusd.md) |
| NVIDIA Warp (`warp-lang`) | 1.17.0 | Apache-2.0 · open | Adopt | `studio/` | Own DEM, shallow-water and dust kernels; differentiable calibration | [Warp](warp.md) |
| Newton | 1.6.0 | Apache-2.0 · open | Trial | `studio/` | Implicit MPM for stockpiles and bucket fill; rigid trucks | [Newton](newton.md) |
| MuJoCo-Warp | 3.12.0 (pinned by Newton) | Apache-2.0 · open | Trial | `studio/` | Articulated shovel and loader kinematics; batched vehicle rollouts | [MuJoCo-Warp](mujoco-warp.md) |
| PhysX / ovphysx | ovphysx 0.6.3; PhysX inside Isaac Sim 6.1.0.0 | source BSD-3 / Apache-2.0; wheels NVIDIA licence · reference-only | Trial (scoped) | `studio/rtx/`, `studio/isaac/` (3.12) | PhysX vehicle visual twin; Kit-less rigid-body cross-check | [PhysX / ovphysx](physx-ovphysx.md) |
| ovrtx (+ ovstage) | 0.5.0.377615 (+ 0.2.0.377349) | NVIDIA SLA · reference-only | Trial (scoped) | `studio/rtx/` (3.12) | RTX truck lidar, proximity radar, drone and crusher cameras | [ovrtx](ovrtx.md) |
| Isaac Sim + Replicator | 6.1.0.0 | NVIDIA proprietary (source Apache-2.0) · reference-only | Trial | `studio/isaac/` (3.12) | Synthetic data of equipment, people and boulders; RTX clips; rain lidar | [Isaac Sim + Replicator](isaac-sim-replicator.md) |
| Isaac Lab | tag v3.0.0-EA (commit `ae37b02`) | BSD-3-Clause · open | Assess | `studio/isaaclab/` (3.12) | Haul-truck ramp driving and excavator digging policies | [Isaac Lab](isaac-lab.md) |
| USD Composer / Explorer (Kit) | Kit 110.3 via kit-app-template 110.3.0 (generated outside the repo) | NVIDIA SLA + product terms · reference-only | Trial (scoped) | `studio/kit/` (Kit's Python 3.12) | Scene review, design measurement, path-traced hero media | [Composer / Explorer](kit-usd-composer-explorer.md) |
| Cosmos Reason 2 (2B) | model revision `9ce19a1` on llama.cpp b11381 (external) | NVIDIA Open Model License · reference-only (outputs display-only) | Assess | `studio/reason/` | Pit-safety questions scored against exact scene truth | [Cosmos Reason 2](cosmos-reason-2.md) |
| PyTorch | 2.14.1 (`pipeline/`); 2.11.0 (`studio/isaac/`) | BSD-3-style · open | Adopt | `pipeline/` (3.14) | Training of every learned model | [PyTorch](pytorch.md) |
| ONNX Runtime (+ Web) | 1.30.0 (onnx 1.23.1); web 1.30.0 planned | MIT · open | Adopt (CPU, Web) · Trial (GPU) | `pipeline/`, `pipeline/accel/`, `web/` | Parity reference, GPU baseline, live in-browser models | [ONNX Runtime](onnx-runtime.md) |
| TensorRT | 11.3.0.99 | NVIDIA TensorRT SLA · reference-only (numbers publishable) | Trial (scoped) | `pipeline/accel/` (3.14) | Camera streams per GPU, INT8 fragmentation, surrogate sweeps | [TensorRT](tensorrt.md) |
| NVENC / FFmpeg | FFmpeg n8.1.3 LGPL (external); PyNvVideoCodec 2.2.3 | LGPL-2.1+ build / MIT · open | Trial | external + `studio/` | AV1 + H.264 clips of every render and replay | [NVENC / FFmpeg](nvenc-ffmpeg.md) |
| Nsight / NVML | nvidia-ml-py 13.615.71, nvtx 0.2.16; Nsight redist planned | BSD / Apache-2.0 · open; Nsight · reference-only | Adopt (NVML) · Trial (Nsight) | root, `studio/`, `pipeline/accel/` | GPU evidence for every stage | [Nsight / NVML](nsight-nvml.md) |
| three.js / R3F / 3D Tiles | planned three 0.186.1, R3F 9.8.1, 3d-tiles-renderer 0.5.3 | MIT / MIT / Apache-2.0 · open | Adopt / Adopt / Trial | `web/` | 3D pit and replay of studio artefacts | [three.js / R3F / 3D Tiles](threejs-r3f-3d-tiles.md) |
| Rapier / WebGPU / Pyodide | planned Rapier 0.21.0, Pyodide 314.0.7 | Apache-2.0 / W3C standard / MPL-2.0 · open | Adopt / Trial / Adopt | `web/` | Live rigid bodies, WGSL granular and field kernels, `minephys` in the browser | [Rapier / WebGPU / Pyodide](rapier-webgpu-pyodide.md) |
| COLMAP / Brush / splats | COLMAP 4.2.1, Brush v0.3.0 (external); splat-transform 3.9.0, Spark 2.3.1 planned | BSD / Apache-2.0 / MIT / MIT · open | Trial / Trial / Trial / Adopt | external + `web/` | Drone-survey reconstruction for volume reconciliation | [COLMAP / Brush / splats](colmap-brush-splats.md) |

### Mining packages

| Package | Version pinned (lock) | Licence · class | Ring | Environment | Mining role | Page |
|---|---|---|---|---|---|---|
| `minehaulsim` | 0.12.1 | Apache-2.0 · open | Adopt | `pipeline/` | Haulage discrete-event reference engine (DES) | [minehaulsim](minehaulsim.md) |
| `oreblocks` | 0.5.2 | MIT · open | Adopt | `pipeline/` | Synthetic deposits with exact pit-shell optima | [oreblocks](oreblocks.md) |
| `minephys` | 0.0.0, git `143e709` | Apache-2.0 · open | Adopt | root, `studio/`, `pipeline/`, Pyodide, Kit | Cited mining-engineering models and knowledge tables | [minephys](minephys.md) |

### Evaluated, not adopted

| Tool | Version checked | Licence | Ring | Why not | Page |
|---|---|---|---|---|---|
| NVIDIA cuOpt | 26.8.0 | Apache-2.0 | Assess | Linux-only wheels; HiGHS solves our LP and MILP sizes on the CPU | [cuOpt](not-adopted-cuopt.md) |
| PhysicsNeMo | 2.2.2 | Apache-2.0 | Assess | Our GNS and FNO are small plain-PyTorch models; it pulls hydra-core | [PhysicsNeMo](not-adopted-physicsnemo.md) |
| Cosmos Predict / Transfer 2.5 | 2B checkpoints | NVIDIA Open Model License | Hold (local) | 32.5 / 65.4 GB of VRAM; an optional cloud run is the maintainer's call | [Cosmos Predict / Transfer](not-adopted-cosmos-predict-transfer.md) |

## How to read a tool page

Each page follows the same order:

1. **What and why**: what the tool is and why PitStudio chose it over the alternatives.
2. **Identity**: version from the lock, release date, licence and class, ring, environment.
3. **How PitStudio uses it**: stages, cases, the artefacts it will produce.
4. **Licence and redistribution**.
5. **Assumptions and limits**, including known bugs with their issue numbers.
6. **In PitStudio**: status today. Nothing has been trained, rendered or baked yet; the GPU capability probes are
   written but not yet run on the reference machine.

The web app renders the same facts on `/studio/tools/:toolId`, from the tool registry
([Recipes and tool registry](../data-contract/recipes-and-tool-registry.md)). A tool with no published artefact shows
**"not yet run"** there, never a stock image ([Showcase rules](../web/showcase-rules.md)).

## In PitStudio

- The environments that hold these tools, and why they are isolated: [Environments](../studio/environments.md).
- Which case uses which tool: [Tool matrix](../cases/tool-matrix.md).
- What each tool's maintainer act or licence acceptance is: [Maintainer acts and licences](../studio/owner-acts-and-licences.md).
- The probes that check each tool on the reference machine: [Capabilities probe](../studio/capabilities-probe.md).

## References

1. NVIDIA. *NVIDIA Software License Agreement* (2026-05-07), §8.9 and §12.2.
   https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
2. NVIDIA. *TensorRT Software License Agreement*. https://docs.nvidia.com/deeplearning/tensorrt/latest/reference/sla.html
3. NVIDIA. *TensorRT for RTX Software License Agreement* (2025-04-21), §2.13.
   https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/reference/sla.html

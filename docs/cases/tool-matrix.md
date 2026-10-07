# Tool matrix — studio tools × cases

> Which studio tool produces artefacts for which case, so that every tool in the studio is exercised by at least one
> mining question and every published artefact can be traced to the tool that made it. · Part of: [Cases](README.md) ·
> Related: [Coverage matrix](coverage-matrix.md) · [Frameworks](../frameworks/README.md) ·
> [Showcase rules](../web/showcase-rules.md) · [Studio](../studio/README.md)

## What and why

The studio is a suite of tools, each in a mining role, driven by one runner. The `/studio` tool map has one page per
tool, and each tool page shows **only artefacts that tool produced** (filtered by the manifest field
`producer.tool`). A tool with nothing published shows **"not yet run"**; a tool that was dropped gets an
"evaluated, not adopted" page instead. The tool matrix is the bridge between the two views: for each tool, the cases
it serves and the artefacts it is expected to produce there.

Like the [coverage matrix](coverage-matrix.md), the web version (`/cases`, "Tools" tab) is **generated from the case
registry**. The registry marks the tools each case names; the supporting marks follow from the case's methods and
lanes.

## Matrix

● = named in the case's studio-tool list. ○ = supporting role that follows from the case's methods or web lanes
(e.g. the exporter, the telemetry, the browser engine). For the browser-engine row: R = Rapier, W = WGSL compute,
P = `minephys` in Pyodide.

| Tool (framework page) | Env | A1 | A2 | A3 | B1 | B2 | C1 | C2 | C3 | D1 | D2 | E1 | E2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [OpenUSD](../frameworks/openusd.md) | `studio/` | | | | ○ | ○ | | ○ | ○ | ○ | | ○ | ○ |
| [Warp](../frameworks/warp.md) | `studio/` | | | ● | | | | ● | ● | ● | | | |
| [Newton](../frameworks/newton.md) | `studio/`, `studio/isaaclab/` | | ● | ● | | | | | | | | | |
| [MuJoCo-Warp](../frameworks/mujoco-warp.md) | `studio/`, `studio/isaaclab/` | | | ● | | | | | | | | | |
| [PhysX / ovphysx](../frameworks/physx-ovphysx.md) | `studio/isaac/`, `studio/rtx/` | | | | ○ | | | | | | | | |
| [ovrtx](../frameworks/ovrtx.md) | `studio/rtx/` | | | | ● | ● | | | ● | | | | ● |
| [Isaac Sim + Replicator](../frameworks/isaac-sim-replicator.md) | `studio/isaac/` | | | | ● | ● | | | | ● | | | |
| [Isaac Lab](../frameworks/isaac-lab.md) | `studio/isaaclab/` | | ● | ● | | | | | | | | | |
| [USD Composer / Explorer (Kit)](../frameworks/kit-usd-composer-explorer.md) | `studio/kit/` | | | | | | | ● | | | | ● | |
| [Cosmos Reason 2](../frameworks/cosmos-reason-2.md) | `studio/reason/` | | | | ● | ● | | | | | | | |
| [PyTorch](../frameworks/pytorch.md) | `pipeline/` | ● | ○ | ○ | | ○ | ● | ○ | | ○ | ● | | |
| [ONNX Runtime (+Web)](../frameworks/onnx-runtime.md) | `pipeline/`, web | ○ | ○ | ○ | | ○ | ○ | ○ | | ○ | ○ | | |
| [TensorRT](../frameworks/tensorrt.md) | `pipeline/accel/` | ● | | | | ● | | | | ● | | | |
| [NVENC / FFmpeg](../frameworks/nvenc-ffmpeg.md) | `studio/` (external FFmpeg 8.1) | | ○ | ○ | ○ | | | ○ | | ○ | | | ○ |
| [Nsight / NVML](../frameworks/nsight-nvml.md) | runner (all envs) | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| [three.js / R3F / 3D Tiles](../frameworks/threejs-r3f-3d-tiles.md) | web | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| [Rapier / WebGPU / Pyodide](../frameworks/rapier-webgpu-pyodide.md) | web | ○ P | ○ P | ○ W | ○ R P | | ○ P | ○ W | ○ W P | ○ P | ○ P | ○ P | |
| [COLMAP + Brush splats](../frameworks/colmap-brush-splats.md) | external tools | | | | | | | | | | | | ● |
| [minehaulsim](../frameworks/minehaulsim.md) | root | ○ | ○ | | ○ | | | | ○ | | | | |
| [oreblocks](../frameworks/oreblocks.md) | `pipeline/` | | | | | | | | | | | ○ | |
| [minephys](../frameworks/minephys.md) | root, web (Pyodide), Kit | ○ | ○ | ○ | ○ | | ○ | | ○ | ○ | ○ | ○ | |

Coverage check: every one of the 17 studio and web tools of the tool map has at least one mark, and so do the
external survey tools and the three companion libraries.

## What each tool produces, per case

| Tool | Cases | Artefacts (manifest `producer.tool`) | Lane on the web |
|---|---|---|---|
| OpenUSD | B1, B2, C2, C3, D1, E1, E2 | Composed pit stages from `st10_terrain` → `st40_compose`, validated by `st45_validate` (build-twice hash); the same scene spec emits the glTF / 3D Tiles of every Scene tab | static (tiles) |
| Warp | A3, C2, C3, D1 | DEM muck-pile and bucket runs, autodiff calibration (A3), shallow-water fields (C2), Lagrangian dust particles (C3): Zarr fields + Parquet observables | replay; live WGSL twins |
| Newton | A2, A3 | Implicit-MPM granular runs; the kit-less physics backend of Isaac Lab IL-1 and IL-2; FEE → MPM zero-shot check | replay |
| MuJoCo-Warp | A3 | Excavator articulation dynamics for IL-2 | replay (via Isaac Lab rollouts) |
| PhysX / ovphysx | B1 | Rigid-body vehicles of the B1 visual twin (`st54_vehicles` in Isaac Sim); ovphysx vehicles are CPU-only, so they are not the vehicle path | replay (clips) |
| ovrtx | B1, B2, C3, E2 | S1 truck lidar with dust/rain (B1, C3), S4a 77 GHz radar (B1), S3 crusher camera (B2), S2 drone survey camera (E2): images, point-cloud shards ≤ 10 MB | replay; performance local-only |
| Isaac Sim + Replicator | B1, B2, D1 | Vehicle clips and rain lidar (B1), COCO / mask / depth SDG sets with structured + unstructured DR (B2), muck-pile renders with instance masks (D1) | replay; performance local-only |
| Isaac Lab | A2, A3 | IL-1 haul-truck and IL-2 excavator policies (ONNX MLP < 1 MB), seeded evaluation episodes, rollout clips, sim-to-sim gap tables | live (TS twins) + replay |
| USD Composer / Explorer | C2, E1 | Path-traced hero clip of the breach (C2); pushback review and measure captures (E1), via our own extension and `st58_kit_capture` | replay; performance local-only |
| Cosmos Reason 2 | B1, B2 | Hazard-question answers scored against exact USD ground truth (B1); synthetic-image captions scored for hallucination (B2) | precomputed text, display-only, "Built on NVIDIA Cosmos" |
| PyTorch | A1, C1, D2 named; A2, A3, B2, C2, D1 supporting | Trained models: dispatch policies, forecasters, meta-model, GNS, detectors, U-Net, FNO; training curves | replay (curves); models go live via ONNX |
| ONNX Runtime (+Web) | A1, A2, A3, B2, C1, C2, D1, D2 | Exported ONNX (opset 17–19, pinned IR) with Python ↔ web parity reports | live (ORT-web WebGPU → WASM) |
| TensorRT | A1, B2, D1 | Local fp32/fp16/int8/fp8 engines (never published); latency, throughput, J/inference and per-engine parity tables of our models | replay (tables, published) |
| NVENC / FFmpeg | A2, A3, B1, C2, D1, E2 | AV1 1080p + H.264 720p clip pairs (VMAF-targeted, ≤ 25 MB per pair); the published set is six pairs within the 150 MB video budget | replay |
| Nsight / NVML | all | NVML 1–4 Hz telemetry with NVTX ranges per stage; optional maintainer-run Nsight captures | replay (charts) for open-runtime stages; local-only for NVIDIA proprietary runtimes |
| three.js / R3F / 3D Tiles | all | The Scene tab: Bingham LOD-0 (≤ 2 MB first view) and case layers | live render |
| Rapier / WebGPU / Pyodide | 10 cases | Rapier traffic (B1); WGSL DEM/MPM, shallow-water and dust kernels (A3, C2, C3); `minephys` analytical models on demand | live |
| COLMAP + Brush | E2 | Sparse model (COLMAP 4.2.1), 3D Gaussian splat (Brush v0.3.0) → SPZ via `splat-transform`, ≤ 25 MB | precompute → view (Spark) + live volume |
| minehaulsim | A1, A2, B1, C3 | Reference DES traces for the TS twin's exact-trace parity | live (TS twin) |
| oreblocks | E1 | Synthetic block models with stamped exact optima | live (min-cut) |
| minephys | 9 cases | Cited equations and parameter tables behind every analytical calculator | live |

## Assumptions and limits

- **Performance data.** Isaac Sim, Kit, Replicator, ovrtx and TensorRT for RTX contribute outputs only; their
  throughput, latency and GPU timelines stay local-only under their licences (NVIDIA SLA §8.9, TensorRT for RTX SLA
  §2.13). Regular TensorRT numbers of our own models are published; the probe pins the licence text by SHA-256
  ([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)).
- **Optional tools.** Cosmos Reason 2 needs the maintainer to accept the gated model terms; USD Composer/Explorer
  needs the kit-app-template licence prompt answered; Nsight captures need an elevated run. If any of these is
  refused, the tool's page says "not run" and its cases fall back as described on each case page
  ([Maintainer acts and licences](../studio/owner-acts-and-licences.md)). No headline KPI depends on them.
- **Status.** Nothing is published yet. The GPU capability probes are written but not yet run on the reference
  machine; every tool page currently shows "not yet run".
- PitStudio is not affiliated with or endorsed by NVIDIA and never redistributes NVIDIA binaries, assets, engines or
  caches.

## In PitStudio

- Source of truth: the case registry (`tools.schema.json` registry → `/studio` tool map; case registry → this matrix).
- A tool marked done must have at least one artefact; proprietary tools contribute outputs only; renders show our
  scenes, never NVIDIA application UI ([Showcase rules](../web/showcase-rules.md)).

## References

No external figures are used on this page. Tool versions and licences are on each [framework page](../frameworks/README.md).

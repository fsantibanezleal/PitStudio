# Decisions

> The decision records of PitStudio (DEC-0001 to DEC-0017): each states its context, the decision, at least two
> alternatives that were considered and rejected, and the consequences. · Part of: [architecture](../README.md) ·
> Related: [solution strategy](../README.md#4-solution-strategy) · [C4 containers](../c4-containers.md) ·
> [lanes](../lanes.md)

## How to read and change these records

- **Format.** Every record has a status line, *Context*, *Decision*, *Alternatives considered*, *Consequences* and
  *References*. External facts cite a URL or DOI; versions come from the lock files.
- **Accepted records are not rewritten.** A changed decision gets a new record that supersedes or amends the old one,
  and the old record's status line points to it. Corrections of typos and broken links are the only edits allowed.
- **Scope.** These records cover PitStudio only. They are written from the approved plan and introduce no behaviour
  that the plan does not have.

## Index

| Record | Decision | Status |
|---|---|---|
| [DEC-0001](DEC-0001-isolated-studio-environments.md) | One isolated uv environment per tool family; file-only handoff | Accepted, 2026-10-04 |
| [DEC-0002](DEC-0002-in-repo-runner.md) | A small in-repo runner with a CAS cache, per-device GPU locks, NVML guards and resume | Accepted, 2026-10-04 |
| [DEC-0003](DEC-0003-loopback-console.md) | A loopback-only FastAPI console with its own web entry, excluded from Pages | Accepted, 2026-10-04 |
| [DEC-0004](DEC-0004-proprietary-sdks-reference-only.md) | Proprietary SDKs are referenced, never redistributed; licence classes; trademark notice | Accepted, 2026-10-04 |
| [DEC-0005](DEC-0005-performance-data-licence-rule.md) | Performance data is published only where the governing licence allows it | Accepted, 2026-10-04 |
| [DEC-0006](DEC-0006-3d-and-simulation-on-static-web.md) | USD in the studio; glTF, 3D Tiles, shards, video and splats on a static site; parity by system class | Accepted, 2026-10-04 |
| [DEC-0007](DEC-0007-large-assets-as-release-assets.md) | Large web assets are GitHub Release assets copied into the Pages artifact at build | Accepted, 2026-10-04 |
| [DEC-0008](DEC-0008-isaac-sim-version-by-compatibility-checker.md) | The Isaac Sim version is chosen by the on-machine Compatibility Checker and a headless smoke | Accepted, 2026-10-04 |
| [DEC-0009](DEC-0009-vlm-llamacpp-gguf.md) | Cosmos Reason 2 runs as our own Q8_0 GGUF through llama.cpp, with a BF16 reference | Accepted, 2026-10-04 |
| [DEC-0010](DEC-0010-tensorrt-per-engine-parity.md) | TensorRT 11.3 with a parity gate per engine; no TensorRT version is assumed safe | Accepted, 2026-10-04 |
| [DEC-0011](DEC-0011-nvenc-ffmpeg-8-1.md) | Video through NVENC with an FFmpeg 8.1 LGPL build, AV1 + H.264, VMAF-targeted | Accepted, 2026-10-04 |
| [DEC-0012](DEC-0012-granular-physics-warp-newton.md) | Granular physics with an own Warp DEM and Newton implicit MPM | Accepted, 2026-10-04 |
| [DEC-0013](DEC-0013-haulage-engine-minehaulsim.md) | `minehaulsim` is the haulage reference engine, with a TypeScript twin at exact-trace parity | Accepted, 2026-10-04 |
| [DEC-0014](DEC-0014-splats-brush.md) | Brush v0.3.0 trains the survey Gaussian splats | Accepted, 2026-10-04 |
| [DEC-0015](DEC-0015-people-assets-makehuman.md) | People in synthetic scenes come from MakeHuman CC0 exports | Accepted, 2026-10-04 |
| [DEC-0016](DEC-0016-pre-registered-decision-rule.md) | "Better" only when the paired 95 % confidence interval excludes zero | Accepted, 2026-10-04 |
| [DEC-0017](DEC-0017-companion-package-minephys.md) | Sourced models and parameter tables live in the companion package `minephys` | Accepted, 2026-10-04 |

## Decisions recorded elsewhere

Some choices of the plan are narrower and are documented on the page they affect rather than in a record of their own:
scene review with USD Composer/Explorer generated outside the repository ([Kit, USD Composer and Explorer](../../frameworks/kit-usd-composer-explorer.md),
covered by [DEC-0004](DEC-0004-proprietary-sdks-reference-only.md)); RTX sensors through ovrtx plus PitStudio's own
dust model ([ovrtx](../../frameworks/ovrtx.md)); Isaac Lab for haul-truck and excavator learning and own PyTorch
environments for dispatch ([Isaac Lab](../../frameworks/isaac-lab.md)); NVML telemetry with Nsight captures by the
maintainer ([Nsight and NVML](../../frameworks/nsight-nvml.md)); and the tools evaluated but not adopted
([cuOpt](../../frameworks/not-adopted-cuopt.md), [PhysicsNeMo](../../frameworks/not-adopted-physicsnemo.md),
[Cosmos Predict and Transfer](../../frameworks/not-adopted-cosmos-predict-transfer.md)).

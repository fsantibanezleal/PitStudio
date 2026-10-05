# DEC-0014: Brush trains the survey Gaussian splats

> Case E2 reconstructs a rendered drone survey with COLMAP and trains the 3D Gaussian splat with Brush v0.3.0, an
> Apache-2.0 trainer with a prebuilt Windows binary and a published checksum, so no CUDA toolkit or compiler has to be
> installed with administrator rights. · Part of: [decisions](README.md) · Related:
> [COLMAP, Brush and splats](../../frameworks/colmap-brush-splats.md) · [M19 Gaussian-splat survey](../../methods/m19-gaussian-splat-survey.md) ·
> [E2 survey reconciliation](../../cases/e2-survey-reconciliation.md)

**Status:** Accepted, 2026-10-04

## Context

E2 renders a drone flight over a scene of exactly known volume, reconstructs it, and measures the volume error; the
reconstruction is also shown in the browser as a splat. 3D Gaussian splatting (Kerbl et al. 2023) is the state-of-the-art
representation for this [1]. The training tool must run on Windows without elevation, under a licence compatible with
a public Apache-2.0 repository.

- The original Inria implementation is non-commercial ("cannot use … for commercial purposes without prior and explicit
  consent") [2].
- gsplat (Apache-2.0) reports up to 4× less GPU memory and about 15 % less time than the original implementation [3], but
  it compiles CUDA kernels just in time, which needs the CUDA toolkit and Visual Studio Build Tools, both
  administrator installs on this machine.
- Brush (Apache-2.0) is a Rust trainer built on WebGPU. Its v0.3.0 release, published 2025-09-14, ships a Windows x86-64
  zip with a `.sha256` file; the repository was still active in October 2026 [4] [5]. Its last release is more than
  12 months old.

## Decision

- **Pipeline (stage `st58b_capture_splat`):** rendered drone images from `studio/rtx` → COLMAP 4.2.1 (portable,
  external) for camera poses → Brush v0.3.0 (portable binary, SHA-256 verified) for the splat → `@playcanvas/splat-transform`
  (MIT, project-local npm, locked) to convert PLY to SPZ for the web, ≤ 25 MB per scene.
- **Volume** is computed from the reconstruction and compared with the exact volume of the rendered scene. DEM
  differencing of the real USGS 3DEP 2018 and 2023 surveys gives the real excavated volume as a separate result.
- **Fallbacks, in order:** gsplat with a maintainer-installed CUDA toolkit and Build Tools (an elevated owner act, only
  if Brush fails its smoke test); otherwise E2 reports DEM differencing only.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| gsplat | Memory-efficient, Apache-2.0, actively developed [3] | Just-in-time CUDA build needs the CUDA toolkit and Visual Studio Build Tools (elevated installs) | Kept as the fallback |
| Inria 3DGS reference code | The original method | Non-commercial licence [2] | Incompatible with the repository's licence |
| No splat; DEM differencing only | No new tool | Loses the reconstruction view and the neural-reconstruction step of the physical-AI workflow | Remains the final fallback |

## Consequences

**Positive.** A per-user, no-elevation path to splats; the binary is pinned by checksum; the web viewer reads the same
SPZ through Spark.

**Negative, accepted.** A release more than a year old is a maintenance risk; Brush's WebGPU training speed on the
reference GPU is unmeasured until the smoke test.

**Watch.** New Brush releases; gsplat's Windows wheels.

**Status.** Brush v0.3.0 is downloaded, verified and extracted; its smoke test waits for the reference machine. COLMAP
and splat-transform arrive with their milestone.

## References

1. Kerbl, B. et al. (2023). 3D Gaussian Splatting for real-time radiance field rendering. *ACM Transactions on Graphics*
   42. https://doi.org/10.1145/3592433
2. Inria Gaussian splatting licence. https://github.com/graphdeco-inria/gaussian-splatting/blob/main/LICENSE.md
3. gsplat repository. https://github.com/nerfstudio-project/gsplat
4. Brush repository (Apache-2.0). https://github.com/ArthurBrussee/brush
5. Brush v0.3.0 release (published 2025-09-14; Windows zip with `.sha256`). https://github.com/ArthurBrussee/brush/releases/tag/v0.3.0

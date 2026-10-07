# COLMAP, Brush and Gaussian splats

> The survey-reconstruction chain for case E2: COLMAP recovers camera poses from drone images, Brush trains a 3D
> Gaussian splat, splat-transform compresses it to SPZ, and Spark shows it in the browser. · Part of:
> [Frameworks](README.md) · Related: [M19 Gaussian-splat survey](../methods/m19-gaussian-splat-survey.md) ·
> [E2 survey reconciliation](../cases/e2-survey-reconciliation.md) · [ovrtx](ovrtx.md) ·
> [DEC-0014](../architecture/decisions/DEC-0014-splats-brush.md)

## What and why

Case E2 asks how well a drone survey reconciles excavated volume. PitStudio renders a synthetic drone flight with ovrtx
over a scene whose volume is known exactly (scenario S2), reconstructs it, and compares the reconstructed volume with
the truth; the real anchor is DEM differencing of the Bingham 3DEP surfaces from 2018 to 2023.

| Step | Tool | What it does |
|---|---|---|
| Structure from motion | **COLMAP** 4.2.1 | camera poses and a sparse point cloud from the image set [1][2] |
| Splat training | **Brush** v0.3.0 | trains 3D Gaussian splats from COLMAP data; WebGPU-based (Burn), so no CUDA toolkit build; loads and writes `.ply` [3] |
| Compression | **`@playcanvas/splat-transform`** 3.9.0 | PLY → SPZ (versions 2–4) on Node [4] |
| Web viewer | **Spark** 2.3.1 | three.js-based splat renderer for PLY, SPZ and other formats; WebGL 2 [5][6] |

SPZ is "typically around 10x smaller" than the corresponding PLY [7]. A splat is a **visual layer only**: it carries no
physics and no labelled ground truth, and it is shown with a "captured (photogrammetry), not simulated" badge.

Rejected alternatives ([DEC-0014](../architecture/decisions/DEC-0014-splats-brush.md)):

| Alternative | Why not |
|---|---|
| gsplat as the trainer | its CUDA kernels need a CUDA toolkit and Visual Studio Build Tools, an elevated install; kept as the fallback [8] |
| the original Inria 3DGS code | non-commercial licence |
| OpenDroneMap | AGPL-3.0; external process at most, not adopted [9] |
| GaussianSplats3D for the web | no longer in active development; points to Spark [10] |

## Identity

| Tool | Version | Release | Licence · class | Ring | How it is pinned |
|---|---|---|---|---|---|
| COLMAP | 4.2.1 | 2026-09-29 [1] | new BSD (third-party deps separate) [2] · open | Trial | portable CUDA build, per user; installed when the E2 stages are built |
| Brush | v0.3.0 | 2025-09-14; repository active [11] | Apache-2.0 · open | Trial | prebuilt Windows binary, SHA-256 verified and extracted |
| splat-transform | 3.9.0 | 2026-10-02 [4] | MIT · open | Trial | project-local npm, locked; needs Node ≥ 22 |
| Spark | 2.3.1 | 2026-10-01 [5] | MIT · open | Adopt | web lock, planned (peer `three` ≥ 0.180) |

Brush's latest release is more than 12 months old, a staleness flag, while the repository itself is active [11].

## How PitStudio uses it

- Optional stage `st58b_capture_splat` (about 0.5–2 h): ovrtx drone images (S2) → COLMAP → Brush → splat-transform.
- Metrics: volume error (%) against the exact scene volume; reprojection RMSE; ground-truth depth vs reconstructed depth.
- Web: one splat scene, ≤ 25 MB, on its own WebGL route (Spark is WebGL-centric; it never shares a canvas with the
  WebGPU renderer) ([Budgets](../web/budgets.md)).

## Licence and redistribution

All four are open and run as external tools or locked dependencies; none is vendored. The images and the splat come
from our own procedural scene, so the published splat is CC-BY-4.0.

## Assumptions and limits

- Brush on this GPU is unproven until its smoke runs. Fallbacks: gsplat after the maintainer installs a CUDA toolkit and
  Visual Studio Build Tools, or E2 with DEM differencing only.
- A splat is not a surface. How the reconstruction becomes a volume for differencing is fixed in the
  [M19 method page](../methods/m19-gaussian-splat-survey.md), not here.
- Spark's compatibility with `WebGPURenderer` is **UNVERIFIED**; the splat route uses WebGL [6].

## In PitStudio

- Probe: Brush smoke after the GPU hold; the binary is already verified and extracted
  ([Capabilities probe](../studio/capabilities-probe.md)).
- Status: **not yet run** — produced in the data-and-models phase. Reported then: volume error (%), reprojection RMSE and
  depth error against the exact scene.

## References

1. COLMAP. *Releases* (4.2.1). https://github.com/colmap/colmap/releases
2. COLMAP. *License*. https://colmap.github.io/license.html
3. A. Brussee. *Brush releases*. https://github.com/ArthurBrussee/brush/releases
4. npm. *@playcanvas/splat-transform*. https://www.npmjs.com/package/@playcanvas/splat-transform
5. sparkjsdev. *Spark releases*. https://github.com/sparkjsdev/spark/releases
6. sparkjsdev. *Spark README*. https://raw.githubusercontent.com/sparkjsdev/spark/main/README.md
7. Niantic. *SPZ*. https://github.com/nianticlabs/spz
8. nerfstudio. *gsplat*. https://github.com/nerfstudio-project/gsplat
9. OpenDroneMap. *ODM*. https://github.com/OpenDroneMap/ODM
10. M. Kellogg. *GaussianSplats3D*. https://github.com/mkkellogg/GaussianSplats3D
11. GitHub API. *ArthurBrussee/brush* (licence, last push). https://api.github.com/repos/ArthurBrussee/brush

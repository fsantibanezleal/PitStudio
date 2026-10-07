# M19 — Survey reconstruction: COLMAP → 3D Gaussian splatting → volume, vs DEM differencing

> Drone images of a pit or stockpile are turned into camera poses with COLMAP and into a 3D Gaussian-splat scene with
> Brush; the reconstructed surface gives an excavated or stockpiled volume that is compared with exact synthetic truth
> and with lidar DEM differencing. · Part of: [Methods](README.md) · Related:
> [RTX sensor physics](../theory/rtx-sensor-physics.md) · [COLMAP, Brush and splats](../frameworks/colmap-brush-splats.md) ·
> [DEC-0014](../architecture/decisions/DEC-0014-splats-brush.md) · [Case E2](../cases/e2-survey-reconciliation.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| SOTA | **yes** (per-scene learned reconstruction) | precompute → view + live volume | [E2](../cases/e2-survey-reconciliation.md) | COLMAP 4.2.1 (new BSD, external), Brush v0.3.0 (Apache-2.0, external), `@playcanvas/splat-transform` 3.9.0 (MIT), Spark 2.3.1 (MIT) | not yet implemented |

## What and why

Survey reconciliation compares what the plan said would be mined with what was actually moved. The classical tool is
**DEM differencing**: subtract two surveyed surfaces and integrate. Drone photogrammetry made the surveys cheap; UAV
stockpile volumes have been compared with terrestrial laser scanning in published work [10]. 3D Gaussian splatting
(3DGS) adds a photorealistic, real-time viewable reconstruction from the same images [1], which is why it is now the
state of the art for reality capture.

M19 asks two honest questions for case E2:

1. **Accuracy:** on a scene whose volume is known *exactly* — a procedural stockpile and pushback rendered by the RTX
   drone camera of [M23](m23-rtx-sensor-simulation.md) — how large is the volume error of the photogrammetric
   reconstruction?
2. **Real scale:** on real public-domain lidar DEMs of the Bingham pit from 2018 and 2023, what volume was actually
   excavated?

The splat itself is a **visual** layer: it is not used for physics and is not labelled ground truth, and the web shows
it with a "captured (photogrammetry), not simulated" badge.

## The algorithm

### Camera poses: COLMAP

COLMAP (new BSD; Windows binaries with CUDA) performs feature extraction, matching and mapping (incremental, or the
global mapper added in 4.2) to recover camera intrinsics, poses and a sparse point cloud [5][6]. It runs as an
external portable tool, never vendored.

### 3D Gaussian splatting

The scene is a set of anisotropic 3D Gaussians, each with a mean $\mu$, a covariance
$\Sigma = R\,S\,S^{\top}R^{\top}$ (rotation $R$ from a quaternion, scale $S$ diagonal), an opacity $o$ and a
view-dependent colour in spherical harmonics [1]. For rendering, each Gaussian is projected to the image with the
viewing transform $W$ and the Jacobian $J$ of the projection, $\Sigma' = J W \Sigma W^{\top} J^{\top}$, and pixels are
composited front to back [1]:

$$
C = \sum_{i \in \mathcal N} c_i\,\alpha_i \prod_{j<i}(1 - \alpha_j), \qquad
\alpha_i = o_i \exp\!\left(-\tfrac12 (\mathbf p - \mu'_i)^{\top}\Sigma_i'^{-1}(\mathbf p - \mu'_i)\right)
$$

with $\mathbf p$ the pixel position, $\mu'_i$ the projected mean and $c_i$ the colour of Gaussian $i$. The parameters
are optimised by gradient descent on a weighted sum of an L1 and a structural-similarity (D-SSIM) photometric loss
against the training images, with adaptive densification (clone, split, prune) [1]. Initialisation uses COLMAP's
sparse points.

- **Trainer:** Brush v0.3.0 (Apache-2.0), a prebuilt Windows binary pinned by SHA-256, WebGPU-based
  ([DEC-0014](../architecture/decisions/DEC-0014-splats-brush.md)). Its last release is more than 12 months old while
  the repository is active, so a smoke test gates it. Fallback: gsplat (Apache-2.0) [2], whose CUDA build needs an
  elevated toolkit install by the maintainer, or E2 with DEM differencing only.
- **Excluded:** the original Inria 3DGS code is non-commercial [3].
- **Packaging:** `@playcanvas/splat-transform` converts PLY to SPZ. A degree-3 spherical-harmonics PLY stores 62
  floats (248 B) per Gaussian, so 1 M Gaussians are about 248 MB; SPZ is "typically around 10x smaller" [7], so about
  25 MB (arithmetic).

### Volume

On a regular grid of cell area $A_c$ (m²), the volume between a reference surface $z_0$ and a surface $z_1$ is

$$
V^{+} = A_c \sum_c \max(z_1 - z_0,\, 0), \qquad V^{-} = A_c \sum_c \max(z_0 - z_1,\, 0)
$$

(fill and cut, m³). The reconstructed surface $z_1$ is gridded from the photogrammetric reconstruction (multi-view
depth or depth rendered from the splats; the route is fixed in the spec). The **volume error** is
$100\,(\hat V - V)/V$ (%).

```text
survey_volume(images):
    poses, sparse = colmap(images)                    # external tool
    splats        = brush.train(images, poses, sparse)
    surface       = grid(depth_from(splats or mvs), cell=1 m)
    return fill_cut(surface, reference_dem)
```

## Baseline and comparison

- **Exact synthetic truth:** the procedural stockpile and pushback in the USD scene have exact volumes; the drone
  flight (nadir and oblique, two sun angles) is rendered by the RTX sensor lane. Reported: volume error, reprojection
  RMSE (px), ground sampling distance, and depth error against the renderer's ground-truth depth.
- **Classical baseline:** lidar **DEM differencing** — on the synthetic scene against the exact DEM, and on the real
  Bingham 3DEP DEMs (2018 → 2023, public domain) for the real excavated volume [8][9].
- No paired-seed claim: each reconstruction is one deterministic pipeline run; repeated flights with different seeds
  give the spread that is reported.

## Acceptance criterion (pre-registered)

No numeric volume-error threshold is pre-registered for M19; the error is a reported result. Its pre-registered checks
are:

- DEM differencing passes worked examples and metamorphic relations (adding a known prism adds exactly its volume;
  swapping surfaces swaps cut and fill; refining the grid converges);
- the reconstruction pipeline completes on the smoke scene, and every artefact carries its manifest (tool versions,
  inputs and SHA-256);
- the volume error on the synthetic scene is **reported**, whatever it is.

**Results: Not yet run** — produced in the data-and-models phase. Reported: volume error vs exact truth, the
DEM-differencing comparison, the real Bingham 2018 → 2023 excavated volume, and the splat scene.

## Lane and web delivery

**Precompute → view + live volume.** Reconstruction runs in the studio (optional stage `st58b_capture_splat`, about
0.5–2 h, estimate). The web shows the SPZ splat in Spark (three.js, WebGL2) [4] within a 25 MB budget for one scene,
and computes cut/fill volumes **live** on the gridded DEMs as the visitor draws a polygon. Fallback: poster frames and
baked volumes.

## Assumptions and limits

- Photogrammetry fails on texture-less or moving surfaces (water, dust); the synthetic flight controls for this, real
  flights would not.
- Splats are not watertight surfaces; volume needs a gridded surface, which adds interpolation error at steep walls.
- The real 2018 → 2023 comparison has no ground-truth tonnage; it is a measurement, not a validation.
- Simulation-grade twin: the synthetic flight is rendered, not flown.

## In PitStudio

- **Cases:** [E2](../cases/e2-survey-reconciliation.md) (volume error %, real excavated volume).
- **Code (planned):** drone camera renders in `studio/rtx/` (`st53_sensors`, scenario S2 of
  [M23](m23-rtx-sensor-simulation.md)); reconstruction in the optional studio stage `st58b_capture_splat` (COLMAP and
  Brush as external tools, splat-transform as a project-local npm tool); DEM differencing in the terrain code of
  `studio/` and in a `web/` worker. Data card: [Bingham 3DEP](../data-contract/dataset-cards/bingham-3dep.md).
- **Status:** not yet implemented — built test-first in the build phase.

## References

1. Kerbl, B. et al. (2023). 3D Gaussian Splatting. ACM Transactions on Graphics 42.
   https://doi.org/10.1145/3592433
2. gsplat (Apache-2.0) — memory and speed claims, Windows notes. https://github.com/nerfstudio-project/gsplat
3. Inria 3DGS licence — non-commercial. https://github.com/graphdeco-inria/gaussian-splatting/blob/main/LICENSE.md
4. Spark — 3DGS renderer for three.js (MIT; PLY, SPZ, SPLAT, KSPLAT, SOG). https://github.com/sparkjsdev/spark
5. COLMAP repository (new BSD; Windows; CUDA). https://github.com/colmap/colmap
6. COLMAP releases (4.2.1; 4.2 global mapper). https://github.com/colmap/colmap/releases
7. SPZ (Niantic, MIT) — "typically around 10x smaller" than PLY. https://github.com/nianticlabs/spz
8. USGS 3DEP lidar on AWS (public domain). https://registry.opendata.aws/usgs-lidar/
9. USGS 3DEP products — "free of charge and without use restrictions".
   https://www.usgs.gov/3d-elevation-program/about-3dep-products-services
10. Tucci et al. (2019). Monitoring and computation of the volumes of stockpiles … UAV photogrammetric surveying.
    Remote Sensing (CC BY). https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/rs11121471

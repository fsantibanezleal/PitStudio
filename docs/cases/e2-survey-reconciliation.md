# E2 — Survey → volumetric reconciliation

> How accurately does a drone survey reconstruct a moved volume when the true volume is known exactly, and how much
> material was really excavated at Bingham Canyon between two public lidar epochs? · Part of: [Cases](README.md) ·
> Related: [M19 Gaussian-splat survey](../methods/m19-gaussian-splat-survey.md) ·
> [COLMAP + Brush splats](../frameworks/colmap-brush-splats.md) · [RTX sensor physics](../theory/rtx-sensor-physics.md) ·
> [Bingham 3DEP card](../data-contract/dataset-cards/bingham-3dep.md)

## What and why

**The question.** A mine surveyor reconciles what the plan said would be mined against what was mined, and checks
stockpile inventories. They ask: how accurate is a volume computed from a drone survey, how does the error depend on
ground sampling distance, image overlap and lighting, and what is the real excavated volume between two surveys? The
twin can answer the first question with **ground truth by construction**: render a drone flight over a scene whose
volume is known exactly, reconstruct it, and measure the error.

**Why it matters.**

- UAV photogrammetry is an established method for stockpile volumes, compared against terrestrial-laser-scanner
  ground truth [1].
- Reconstruction is the first step of the reconstruct → simulate → train physical-AI workflow [2].
- Public multi-epoch lidar over a large open pit makes real excavation measurable without any operator data: USGS
  3DEP publishes 1 m bare-earth DEMs over Bingham Canyon for 2013 (partial), 2018 and 2023 [3][4].

## Site and data

| Input | Kind | Source and licence | Card |
|---|---|---|---|
| 1 m DEMs 2018 and 2023 (and 2013, partial) | **real** | USGS 3DEP, public domain; SHA-256 pinned on first download [3][4] | [bingham-3dep](../data-contract/dataset-cards/bingham-3dep.md) |
| Area of interest for the pit | real polygons | open mining-footprint polygons, CC BY 4.0, used to confirm the hand-typed bounding box [5] | [tang-werner-footprint](../data-contract/dataset-cards/tang-werner-footprint.md) |
| Drone flight over a known-volume scene (images, exact depth and camera poses) | **synthetic** | ovrtx RTX renders of our own USD scene with CC0 materials; CC-BY-4.0 | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md), [textures-cc0](../data-contract/dataset-cards/textures-cc0.md) |

## Methods and baseline

| Rung | Method | Role in E2 |
|---|---|---|
| SOTA (learned reconstruction) | [M19 COLMAP → 3D Gaussian splatting → volume](../methods/m19-gaussian-splat-survey.md) | COLMAP 4.2.1 structure-from-motion [6] → Brush v0.3.0 3DGS training [7][8] → `splat-transform` PLY → SPZ → Spark viewer [9] |
| SOTA | [M23 RTX sensor simulation, S2 drone camera](../methods/m23-rtx-sensor-simulation.md) | Pinhole survey camera; exposure, noise and vignetting applied by us on linear HDR output |
| Classical | DEM differencing (inside M19) | Cut and fill between two gridded surfaces; also the real-volume method |

**Volume by differencing.** On a common grid with cell area $a$ (m²), the cut volume is
$V_{\text{cut}} = a \sum_c \max(z_{\text{before},c} - z_{\text{after},c},\,0)$ (m³) and the fill volume is the same with the
sign reversed, where $z_c$ (m) is the surface elevation of cell $c$; surfaces are the reference DEMs (real) or the
reconstructed surface (synthetic). Topographic
differencing of 3DEP products follows established open workflows [10].

**Baseline.** On the synthetic scene, the reconstructed volume is compared with the exact scene volume across survey
designs (GSD, overlap, lighting). DEM differencing is the classical reference method and the one applied to the real
epochs.

## KPIs

| KPI | Unit | How it is computed |
|---|---|---|
| Volume error | % | $(V_{\text{recon}} - V_{\text{true}}) / V_{\text{true}} \times 100$ on the known-volume scene |
| Error vs survey design | % per GSD (cm/px) and overlap (%) | Volume error across rendered flights with varied GSD, overlap and lighting |
| Real excavated volume | m³ (cut and fill) | DEM difference 2018 → 2023 over the pit area of interest |

## Studio tools and artefacts

| Tool | Artefacts it produces for E2 |
|---|---|
| [ovrtx](../frameworks/ovrtx.md) (`st53_sensors`, S2) | Drone image sequences with exact poses and depth |
| [COLMAP + Brush](../frameworks/colmap-brush-splats.md) (`st58b_capture_splat`) | Sparse model; 3D Gaussian splat (PLY → SPZ, ≤ 25 MB for one scene) |
| [OpenUSD](../frameworks/openusd.md) | The known-volume scene and its exact volume |
| [NVENC / FFmpeg](../frameworks/nvenc-ffmpeg.md) | Drone flight clip pair (AV1 + H.264) |

## Web delivery

| Sub-tab | Element | Lane | Engine / asset |
|---|---|---|---|
| Scene | Splat of the synthetic scene; Bingham 2018 → 2023 difference map on the pit | LIVE (view) | Spark in three.js; 3D Tiles |
| Simulate | Draw a polygon → cut/fill volume on the gridded DEMs | LIVE | TS worker |
| Studio replay | Drone flight frames and clip; COLMAP sparse model | REPLAY | AV1 + H.264; baked points |
| Charts | Volume error vs GSD and overlap; real cut and fill per epoch pair | REPLAY | baked tables |
| Context | Question, method, honesty notes | STATIC | — |

## Assumptions and limits

- **Synthetic error is not field error.** Rendered images lack real lens distortion, motion blur and GNSS/IMU errors
  unless added; the ovrtx camera is pinhole and the image effects are ours. The synthetic error budget bounds what
  the pipeline can do, not what a real flight will achieve.
- **Real volumes depend on the DEMs.** The 2013 epoch is partial; DEM accuracy, ground classification and
  co-registration limit the real-volume figure, which is stated with its inputs.
- **The site is a public terrain source only.** The real excavated volume is computed from public-domain DEMs and
  implies nothing about the operator's own reconciliation.
- **Brush fallback.** If Brush fails on the reference GPU, the gsplat fallback needs a maintainer-installed CUDA
  toolkit; otherwise E2 reports DEM differencing only ([DEC-0014](../architecture/decisions/DEC-0014-splats-brush.md)).
- ovrtx performance data stay local-only.

## Reproduce this

```bash run deferred=P6
uv run studio plan studio/recipes/cases/e2.yaml --profile laptop-rtx5000ada
uv run studio run studio/recipes/cases/e2.yaml --profile laptop-rtx5000ada
uv run studio publish <run-id>
```

COLMAP and Brush are external portable tools verified by SHA-256; the splat step is optional and takes about
0.5–2 h.

## Results

**Not yet run** — produced in the data-and-models phase. What will be reported:

- Volume error (%) on the known-volume scene for each survey design (GSD, overlap, lighting).
- Real excavated volume 2018 → 2023 (cut and fill, m³) over the pit area of interest, with the DEM inputs and their
  checksums.

## In PitStudio

- Recipe `studio/recipes/cases/e2.yaml`; route `/cases/E2`.

## References

1. Tucci et al. (2019). *Monitoring and Computation of the Volumes of Stockpiles … UAV Photogrammetric Surveying*.
   Remote Sensing 11(12):1471, CC BY. DOI 10.3390/rs11121471
2. NVIDIA (2025-10-29). *Scaling Physical AI with Synthetic Data* (blog). https://blogs.nvidia.com/blog/scaling-physical-ai-omniverse/
3. USGS. *About 3DEP Products & Services*. https://www.usgs.gov/3d-elevation-program/about-3dep-products-services
4. USGS. The National Map Access API, 1 m DEM products over Bingham Canyon.
   https://tnmaccess.nationalmap.gov/api/v1/products?bbox=-112.17,40.50,-112.12,40.54&datasets=Digital%20Elevation%20Model%20(DEM)%201%20meter&max=10
5. Tang, Werner (2023). *Global mining footprint*. Zenodo, CC BY 4.0. https://zenodo.org/records/7894216
6. COLMAP (new BSD). https://github.com/colmap/colmap
7. Kerbl et al. (2023). *3D Gaussian Splatting for Real-Time Radiance Field Rendering*. ACM TOG 42. DOI 10.1145/3592433
8. Brush (Apache-2.0). https://github.com/ArthurBrussee/brush
9. Spark (MIT), 3D Gaussian splat renderer for three.js. https://github.com/sparkjsdev/spark
10. OpenTopography. *OT_3DEP_Workflows* (DEM generation and topographic differencing notebooks).
    https://github.com/OpenTopography/OT_3DEP_Workflows

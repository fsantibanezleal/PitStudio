# USGS 3DEP — Bingham Canyon terrain

> Public-domain 1 m elevation models (2013, 2018, 2023) and 69 lidar tiles over the Bingham Canyon area, the default
> real site of PitStudio. · Part of: [Dataset cards](README.md) · Related:
> [E2 Survey reconciliation](../../cases/e2-survey-reconciliation.md) ·
> [A1 Truck–shovel dispatch](../../cases/a1-truck-shovel-dispatch.md) ·
> [C2 Tailings breach](../../cases/c2-tailings-breach.md) · [Studio stages](../../pipelines/studio-stages.md)

## What and why

PitStudio needs one real hard-rock open pit whose terrain can be fetched by anyone, without an account, and
published as derived meshes. The US Geological Survey's 3D Elevation Program (3DEP) offers exactly that for the
Bingham Canyon copper pit in Utah: its products are "available, free of charge and without use restrictions" [1].

Two properties make it the **default real site**:

- **Several epochs.** Bare-earth DEMs from 2013, 2018 and 2023 let the pipeline measure a *real* excavated volume
  (case E2) instead of a simulated one.
- **Real geometry for haulage and flow.** Benches, ramps and haul roads of a working pit feed the road network of A1,
  the pit profile of A2, the real ramp of the IL-1 haul-truck policy and the terrain of the tailings / flooding run
  (C2).

The two other terrain sources play narrower roles: [McKinley](mckinley-lidar.md) gives close-up roads and textures,
and [Hambach](hambach-nrw.md) pairs terrain with ground deformation.

## Datasheet

### Composition

Products returned by The National Map (TNM) Access API for the query box (see the limit on the box below) [3][4]:

| Product | 3DEP project | Format | Size per file (MB) | Files | Note |
|---|---|---|---|---|---|
| 1 m DEM | UT Wasatch L3 2013 | GeoTIFF | 5.0 | 1 | partial coverage of the box |
| 1 m DEM | UT Central QL2 2018 | GeoTIFF | 165.6 | 1 | |
| 1 m DEM | UT 2023 Salt Lake Co | GeoTIFF | 257.4 | 1 | published 2026-01-13 |
| Lidar point cloud (LPC) | UT Central QL2 2018 | LAZ | 10–37 | 30 | |
| Lidar point cloud | 2023 project | LAZ | 10–37 | 12 | |
| Lidar point cloud | Wasatch Fault project | LAZ | 10–37 | 12 | |
| Lidar point cloud | 2006 project | LAZ | 10–37 | 15 | |

- **Total:** 3 DEM epochs and 69 LAZ tiles [3][4].
- **DEM format:** 3DEP distributes 1 m project DEMs as cloud-optimised GeoTIFF; most lidar since 2014 is quality
  level 2 (QL2) [1].
- **Coordinate system and vertical datum:** read from each file's metadata at download and recorded in the manifest
  (not asserted here).
- **Classes:** the point classes present in each LAZ tile are read from the tile; `st10_terrain` keeps ground points
  for the terrain grid.

### Collection and provenance

- **Publisher:** USGS, 3D Elevation Program, served through The National Map. Airborne lidar is collected per 3DEP
  project (project names above) and processed into point clouds and bare-earth DEMs [1].
- **How it was found:** a TNM Access API product query on 2026-10-02 for the box
  `-112.17,40.50,-112.12,40.54` (west, south, east, north in degrees), once for LPC and once for 1 m DEMs [3][4].
- **Download hosts:** direct `rockyweb.usgs.gov` URLs for LAZ tiles and `prd-tnm.s3.amazonaws.com` URLs for DEMs
  [3][4]. The same point clouds also exist as Entwine Point Tiles in the public `s3://usgs-lidar-public` bucket (no
  account), with raw LAZ 1.4 in a requester-pays bucket [2].
- **Landing page:** [1]. There is no DOI; the citation names the program and the project.

### Licence and attribution

- **SPDX:** `LicenseRef-USGov-PD` (US Government work). The AWS registry labels it "US Government Public Domain" [2].
- **Licence class:** `public-domain`. **Redistribution class:** `redistributable`.
- **Attribution text** (a courtesy, not a condition), reproduced on every derived artefact:
  "Elevation data: U.S. Geological Survey, 3D Elevation Program (3DEP), project <project name>, accessed <date>."
- **Conflicts:** none found.

### Size, checksums and access

- **Size:** DEMs 5.0 MB, 165.6 MB and 257.4 MB; LAZ tiles 10–37 MB each, so about 0.7–2.6 GB for all 69 tiles
  (bounds from the per-tile range) [3][4].
- **Checksum:** the TNM API output has no checksum field [3][4]; whether USGS publishes checksums elsewhere is
  UNVERIFIED. The SHA-256 is pinned at first download.
- **Account:** none.
- **Programmatic path:** TNM Access API product query → HTTPS download by `s00_download` (pooch). The public
  Entwine bucket is a documented alternative [2], not the default path.
- **Fallback:** none. Bingham is the core site; if it cannot be fetched, the cases that depend on it are reported as
  "not run".

## Assumptions and limits

- **The query box is hand-typed.** It must be confirmed against the [Tang & Werner](tang-werner-footprint.md) or
  [Maus](maus-polygons.md) mine polygons before anything is labelled "Bingham Canyon". Until then the site name on
  derived artefacts is provisional.
- **The 2013 DEM is partial.** The real excavated volume of E2 uses the 2018 → 2023 pair; 2013 is used only where it
  covers the pit.
- **Benches in coarse scenes are regenerated.** The web's first view (≤ 2 MB) cannot carry 1 m terrain, so coarse
  scenes regenerate benches with design code (`st20_pit_design`) and label them "regenerated by design code, not
  observed".
- **Surfaces, not processes.** DEMs are snapshots on survey dates. They give geometry and volumes, not deformation or
  operations. PitStudio is a simulation-grade twin, not a live digital twin.
- **Vertical accuracy** differs per project and is read from each project's metadata; volume uncertainty is
  propagated from it, not assumed.
- **Mixed epochs in the lidar set** (2006, 2018, 2023, Wasatch Fault) differ in density and classification; tiles
  are grouped by project, never mixed into one surface.

## In PitStudio

- **Source id:** `usgs-3dep-bingham` in `data/sources.yaml`.
- **Stages:** `s00_download` → `st10_terrain` (crop, ground grid, site-local frame, terrain meshes and levels of
  detail) → `st20_pit_design` (benches, ramps, pushback variants) → `st40_compose`. The 2018 → 2023 DEM difference for
  E2 is computed in the pipeline lane and baked by `s60_export`.
- **Cases:** A1 (road network), A2 (pit profile), C2 (terrain for GPU shallow water), E2 (real excavated volume) and
  the default 3D pit of the Explore view.
- **Methods:** [M6](../../methods/m06-haul-road-energy-routing.md) grade-constrained routing on the DEM,
  [M15](../../methods/m15-shallow-water-fno.md) shallow water,
  [M19](../../methods/m19-gaussian-splat-survey.md) volume against DEM differencing,
  [M21](../../methods/m21-isaac-lab-policies.md) IL-1 on a real ramp.
- **Models:** [FNO fields](../../models/fno-fields.md) (terrain inputs), [Isaac Lab policies](../../models/isaac-lab-policies.md).
- **Committed:** derived terrain tiles, meshes and volumes, each with the attribution text. **Never committed:** raw
  LAZ tiles and DEM GeoTIFFs.
- **Status:** **Not yet downloaded by the pipeline** — fetched by `s00_download` in the data-and-models phase.

## References

1. U.S. Geological Survey. "About 3DEP products and services", accessed 2026-10-02.
   https://www.usgs.gov/3d-elevation-program/about-3dep-products-services
2. AWS Registry of Open Data. "USGS 3DEP LiDAR Point Clouds", accessed 2026-10-02.
   https://registry.opendata.aws/usgs-lidar/
3. U.S. Geological Survey. The National Map Access API, LPC products for the box `-112.17,40.50,-112.12,40.54`,
   accessed 2026-10-02.
   https://tnmaccess.nationalmap.gov/api/v1/products?bbox=-112.17,40.50,-112.12,40.54&datasets=Lidar%20Point%20Cloud%20(LPC)&max=10
4. U.S. Geological Survey. The National Map Access API, 1 m DEM products for the same box, accessed 2026-10-02.
   https://tnmaccess.nationalmap.gov/api/v1/products?bbox=-112.17,40.50,-112.12,40.54&datasets=Digital%20Elevation%20Model%20(DEM)%201%20meter&max=10

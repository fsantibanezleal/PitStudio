# McKinley Mine lidar 2023 (OpenTopography)

> A dense CC BY 4.0 lidar survey, DEM and orthophoto of a working surface coal mine in New Mexico, used for close-up
> haul roads and ground textures. · Part of: [Dataset cards](README.md) · Related:
> [USGS 3DEP Bingham Canyon](bingham-3dep.md) · [CC0 textures](textures-cc0.md) ·
> [Maintainer acts and licences](../../studio/owner-acts-and-licences.md) · [OpenUSD](../../frameworks/openusd.md)

## What and why

The default site ([Bingham Canyon](bingham-3dep.md)) gives real pit geometry at 1 m, which is too coarse for
close-up views of haul roads, windrows and ground texture. The McKinley Mine survey is the densest openly licensed
lidar of a mine found: about 46 points per m², a 0.3 m DEM and a 0.10 m orthophoto [1]. Its publisher states it is
meant for "volumetric measurements, change detection … monitoring mining progression and reclamation" [1].

PitStudio uses it for **close-up roads and textures** only. No case KPI depends on it, which is why it can stay
optional.

## Datasheet

### Composition

| Item | Value | Source |
|---|---|---|
| Survey | "Lidar Survey of the McKinley Mine, NM 2023" | [1] |
| Area | 107.8 km² | [1] |
| Points | 4,975,347,484 (46.15 points/m²) | [1] |
| Acquisition date | 2023-10-17 | [2] |
| Products | LAZ point cloud, 0.3 m DEM, 0.10 m orthophoto | [1] |
| Horizontal CRS | NAD83(2011) / UTM zone 12N, EPSG:6341 | [2] |
| Vertical CRS | NAVD88 height, EPSG:5703 | [2] |
| Site type | surface coal mine (strip mining) | [1] |

`st10_terrain` crops an area of interest, keeps ground points, grids them and reprojects from EPSG:6341 + 5703 to the
scene's site-local metric frame; the site origin and its EPSG code are written to the manifest.

### Collection and provenance

- **Collected** for the US Office of Surface Mining Reclamation and Enforcement (OSMRE) by a survey contractor
  (Surdex), and **distributed** by OpenTopography [1][2].
- **Collection id:** OpenTopography `OT.112024.6341.2`; DOI 10.5069/G9BZ6486 [1].
- **Version read:** the record published 2024-11-18, read on 2026-10-02 [1].
- **Landing page:** https://portal.opentopography.org/datasetMetadata?otCollectionID=OT.112024.6341.2 [1].

### Licence and attribution

- **SPDX:** `CC-BY-4.0`. **Licence class:** `attribution`. **Redistribution class:** `redistributable` (CC BY 4.0),
  but PitStudio fetches the data and commits derived meshes and textures only.
- **OpenTopography terms:** data are free of copyright restrictions subject to the dataset licence, with attribution
  to the source and to OpenTopography; **API keys must not be shared, made public or embedded** in an app that lets
  third parties bypass one key per user [3].
- **Attribution text**, reproduced verbatim on every derived artefact and render:
  "Lidar Survey of the McKinley Mine, NM 2023. U.S. Office of Surface Mining Reclamation and Enforcement (OSMRE);
  distributed by OpenTopography. https://doi.org/10.5069/G9BZ6486. Licensed under CC BY 4.0."
- **Conflicts:** none found.

### Size, checksums and access

- **Size:** about 5 × 10⁹ points for the whole survey [1]. A 4 km² pit area of interest is about 185 M points,
  roughly 1.5–2.5 GB of LAZ (an *estimate* from the point density, to be measured) [2]. The pipeline therefore crops
  early and never ships points.
- **Checksum:** none published (UNVERIFIED); the SHA-256 is pinned at first download.
- **Account:** **yes** — bulk download needs an OpenTopography login [1], and scripted access needs a free API key.
  The key is an optional maintainer act. It is read from an environment variable at run time and never committed,
  logged or used in CI [3].
- **Programmatic path:** OpenTopography portal / API with the maintainer's key. The scripted bulk URL pattern is
  UNVERIFIED and is pinned at specification.
- **Default and fallback:** optional accounts are off by default, so the default build uses **Bingham-only scenes +
  CC0 textures**. The McKinley close-ups appear only when the maintainer provides a key.

## Assumptions and limits

- **Coal strip mine, not hard-rock benches.** McKinley's geometry does not stand in for a copper pit; it is used for
  road surfaces, windrows and textures, never for bench design or slope cases.
- **Orthophoto texture** carries the attribution text wherever it is visible, including renders.
- **Area of interest** (crop bounds) is fixed at specification; the 185 M-point estimate scales with it.
- **Key handling** is the main risk: a leaked key breaks the OpenTopography terms [3]. CI uses no key and no
  McKinley data.

## In PitStudio

- **Source id:** `ot-mckinley-2023` in `data/sources.yaml`.
- **Stages:** `s00_download` (optional, key-gated) → `st10_terrain` (crop, ground grid, reprojection, meshes) →
  `st30_assets` / `st40_compose` (road close-ups, orthophoto-based ground materials) → `s60_export` (derived meshes
  and textures).
- **Cases:** none depends on it for a KPI; it improves close-up studio scenes and renders of haul roads.
- **Committed:** derived meshes and textures with the attribution text. **Never committed:** raw LAZ, DEM and
  orthophoto files, the API key.
- **Status:** **Not yet downloaded by the pipeline** — fetched by `s00_download` in the data-and-models phase, only
  if the maintainer provides an OpenTopography key.

## References

1. U.S. Office of Surface Mining Reclamation and Enforcement; OpenTopography. "Lidar Survey of the McKinley Mine, NM
   2023", 2024. https://doi.org/10.5069/G9BZ6486 — record:
   https://portal.opentopography.org/datasetMetadata?otCollectionID=OT.112024.6341.2 (accessed 2026-10-02)
2. OpenTopography. Dataset metadata for OT.112024.6341.2 (area, points, acquisition date, CRS EPSG:6341 + 5703),
   accessed 2026-10-02. https://portal.opentopography.org/datasetMetadata?otCollectionID=OT.112024.6341.2
3. OpenTopography. Usage terms (licence statement; API key not public or embeddable), accessed 2026-10-02.
   https://opentopography.org/usageterms

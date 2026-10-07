# NRW lidar and DGM1 — Hambach

> Airborne lidar and 1 m terrain models of North Rhine-Westphalia under a zero-condition licence, covering the
> Hambach lignite pit for the slope-monitoring case. · Part of: [Dataset cards](README.md) · Related:
> [EGMS over Hambach](egms-hambach.md) · [C1 Slope time of failure](../../cases/c1-slope-time-of-failure.md) ·
> [Slopes and monitoring](../../theory/slopes-and-monitoring.md) · [Sources and licences](../sources-and-licences.md)

## What and why

Case C1 needs a real pit where terrain and ground deformation can both be fetched openly. In Germany, the state of
North Rhine-Westphalia (NRW) publishes its airborne laser scanning and terrain models as open data, and the region
holds the Hambach, Garzweiler and Inden lignite pits [1]. Together with [EGMS](egms-hambach.md) InSAR deformation,
Hambach becomes a fully open European site with real slopes and real measured motion.

The licence is the cleanest found for a European pit: *Datenlizenz Deutschland – Zero – 2.0* allows copying,
modification, commercial use and redistribution **with no attribution condition** [1][4].

## Datasheet

### Composition

- **3D-Messdaten Laserscanning:** airborne laser scanning at ≥ 8 points/m², full-waveform since 2017, with
  ground / non-ground classification, delivered as LAS/LAZ per tile [1].
- **Height-model products** in the open download tree `opengeodata.nrw.de/produkte/geobasis/hm/` [2]:

  | Folder | Content (from the product name) | Used by PitStudio |
  |---|---|---|
  | `3dm_l_las` | 3D laser-scan point clouds, per tile | yes (ground points where finer detail is needed) |
  | `dgm1_tiff` | DGM1, 1 m digital terrain model (bare earth), per tile | yes (terrain) |
  | `dom1_tiff` | DOM1, 1 m digital surface model, per tile | no |
  | `bdom50_las` | surface-model product, per tile | no |
  | `ndom50_tiff` | surface-model product, per tile | no |

- **Index files:** each folder has machine-readable `index.json` / `index.xml` listings [3].
- **Coordinate system:** read from the tile metadata at download and recorded in the manifest (not asserted here).
- **Tile list:** the tiles over Hambach are fixed at specification from the index files and a mine polygon.

### Collection and provenance

- **Publisher:** Geobasis NRW (Bezirksregierung Köln), the state survey of North Rhine-Westphalia [1].
- **Collection:** state-wide airborne laser scanning, updated on a rolling basis; full-waveform recording since 2017
  [1].
- **Version read:** rolling product, read on 2026-10-02 [1][2]. The tile dates are recorded per file at download.
- **Landing page:** https://www.bezreg-koeln.nrw.de/geobasis-nrw/produkte-und-dienste/hoehenmodelle/3d-messdaten [1].
  There is no DOI.

### Licence and attribution

- **SPDX:** `DL-DE-ZERO-2.0`. **Licence class:** `open-no-attribution`. **Redistribution class:**
  `redistributable`.
- **Publisher statement:** "kostenfrei und zur Nutzung ohne Einschränkungen oder Bedingungen" ("free of charge and
  for use without restrictions or conditions") [1].
- **Attribution text:** none required [4]. PitStudio still adds a courtesy line to derived artefacts:
  "Terrain: Geobasis NRW, 3D-Messdaten / DGM1, dl-de/zero-2.0, accessed <date>."
- **Conflicts:** none found.

### Size, checksums and access

- **Size:** per tile; the tile sizes were not read (UNVERIFIED) and are recorded at download.
- **Checksum:** none seen; the SHA-256 is pinned at first download.
- **Account:** none.
- **Programmatic path:** read `index.json` of the product folder → select the tiles that intersect the Hambach area
  of interest → HTTPS download by `s00_download` (pooch) [3].
- **Fallback:** none needed — open, no account.

## Assumptions and limits

- **The area of interest** around the Hambach pit is set from a mine polygon ([Tang & Werner](tang-werner-footprint.md)
  or [Maus](maus-polygons.md)) at specification, not hand-typed.
- **A lignite pit, not a hard-rock pit.** Its slope materials differ from Bingham's benches, so C1 uses Hambach for
  real geometry and real deformation, never as a source of rock-mass parameters.
- **Snapshot terrain.** The DGM1 is a surface at the scan date; it does not move. Deformation comes from EGMS.
- **Tile dates differ** across the area; the manifest records each tile's date so that mixed epochs are visible.

## In PitStudio

- **Source id:** `nrw-hambach-dgm1` in `data/sources.yaml`.
- **Stages:** `s00_download` → `st10_terrain` (tile mosaic, ground grid, site-local frame, meshes) →
  `st40_compose`; derived slope profiles feed the C1 analysis in the pipeline lane.
- **Cases:** [C1](../../cases/c1-slope-time-of-failure.md) (real slope geometry next to EGMS deformation).
- **Methods:** [M13](../../methods/m13-slope-stability-lem.md) limit-equilibrium sections on real profiles,
  [M23](../../methods/m23-rtx-sensor-simulation.md) analytical slope-radar geometry.
- **Committed:** derived terrain (meshes, profiles). **Never committed:** raw tiles.
- **Status:** **Not yet downloaded by the pipeline** — fetched by `s00_download` in the data-and-models phase.

## References

1. Bezirksregierung Köln, Geobasis NRW. "3D-Messdaten" (density, LAS/LAZ, dl-de/zero-2.0), accessed 2026-10-02.
   https://www.bezreg-koeln.nrw.de/geobasis-nrw/produkte-und-dienste/hoehenmodelle/3d-messdaten
2. Geobasis NRW. Open geodata, height models (product folders), accessed 2026-10-02.
   https://www.opengeodata.nrw.de/produkte/geobasis/hm/
3. Geobasis NRW. `3dm_l_las` folder with `index.json` / `index.xml`, accessed 2026-10-02.
   https://www.opengeodata.nrw.de/produkte/geobasis/hm/3dm_l_las/
4. GovData. "Datenlizenz Deutschland – Zero – Version 2.0", accessed 2026-10-02.
   https://www.govdata.de/dl-de/zero-2-0

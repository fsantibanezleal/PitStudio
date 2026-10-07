# Xu et al. — global surface mining and reclamation, 1985–2022

> Annual 30 m time series of disturbance and reclamation for 74,726 surface-mining polygons under CC BY 4.0, giving
> real expansion curves for the default sites. · Part of: [Dataset cards](README.md) · Related:
> [Tang & Werner mining footprint](tang-werner-footprint.md) ·
> [E1 Pit shell and pushbacks](../../cases/e1-pit-shell-pushbacks.md) · [Planning](../../theory/planning.md) ·
> [Sources and licences](../sources-and-licences.md)

## What and why

A pit grows year by year. Planning (category E) simulates that growth with nested shells and pushbacks, but a
simulation alone does not show what real growth looked like. Xu et al. publish, for each surface-mining polygon,
annual disturbance and reclamation from 1985 to 2022 at 30 m, with vegetation and status attributes, under CC BY 4.0
[1][2]. For the default sites this gives a **real expansion curve**: disturbed area through time.

The curves are **real context**, shown next to the simulated pushbacks. No case KPI is computed from them.

## Datasheet

### Composition

| Item | Value | Source |
|---|---|---|
| Polygons | 74,726 | [1] |
| Period | 1985–2022, annual | [1] |
| Resolution | 30 m (Landsat-based) | [1] |
| Per-polygon attributes | annual disturbance and reclamation, NDVI, bare-surface share, status (active / stable / closed) | [1] |
| Package | one ZIP of polygons and tables, 32.8 MB | [2] |
| Version | v3, 2025-09-09 | [2] |

The exact table layout and coordinate system are read from the archive after download and recorded in the manifest.

### Collection and provenance

- **Authors:** Xu et al. [1].
- **Article:** "Global surface mining and land reclamation of time series from 1985–2022", *Earth System Science
  Data* 18:6293, 2026 [1].
- **Collection:** derived by the authors from the 30 m Landsat record; the method is described in the article [1].
- **Version read:** Zenodo v3, 2025-09-09, read on 2026-10-02 [2].
- **Landing page and DOI:** https://zenodo.org/records/17085099, DOI 10.5281/zenodo.17085099 [2].

### Licence and attribution

- **SPDX:** `CC-BY-4.0`. **Licence class:** `attribution`. **Redistribution class:** `redistributable`; PitStudio
  commits derived curves only.
- **Attribution text**, reproduced verbatim on every derived curve:
  "Xu et al. (2025). Global surface mining and land reclamation of time series from 1985–2022, v3. Zenodo.
  https://doi.org/10.5281/zenodo.17085099. Licensed under CC BY 4.0."
- **Conflicts:** none found.

### Size, checksums and access

- **Size:** 32.8 MB (one ZIP) [2].
- **Checksum:** MD5 published by Zenodo [2]; `s00_download` checks it and pins a SHA-256 at first download.
- **Account:** none.
- **Programmatic path:** Zenodo record API → HTTPS download by pooch [2].
- **Fallback:** none needed (open, small).

## Assumptions and limits

- **30 m pixels** blur bench-scale change; the curves describe the footprint of mining land, not volumes. Real volumes
  come from the [3DEP DEM difference](bingham-3dep.md) (E2).
- **Polygon match.** A polygon of this set must be matched to the confirmed site outline
  ([Tang & Werner](tang-werner-footprint.md)); a mismatch is reported, not forced.
- **Classification noise** from clouds, seasons and sensor changes shows up as year-to-year jitter; curves are shown
  as published, with no smoothing that changes their values.
- **Ends in 2022.** The 2023 DEM epoch at Bingham is outside the series.

## In PitStudio

- **Source id:** `xu-expansion-v3` in `data/sources.yaml`.
- **Stages:** `s00_download` → `s10_preprocess` (select the polygons of the default sites, extract annual series) →
  `s60_export` (expansion curves).
- **Cases:** real context for the planning category ([E1](../../cases/e1-pit-shell-pushbacks.md),
  [E2](../../cases/e2-survey-reconciliation.md)); no KPI depends on it.
- **Committed:** expansion curves (Parquet) with the attribution text. **Never committed:** the ZIP or its full tables.
- **Status:** **Not yet downloaded by the pipeline** — fetched by `s00_download` in the data-and-models phase.

## References

1. Xu et al. "Global surface mining and land reclamation of time series from 1985–2022", *Earth System Science Data*
   18:6293, 2026. https://essd.copernicus.org/articles/18/6293/2026/ (accessed 2026-10-02)
2. Xu et al. (2025). Dataset v3 (Zenodo record: licence, size, MD5). https://doi.org/10.5281/zenodo.17085099 —
   record API: https://zenodo.org/api/records/17085099 (accessed 2026-10-02)

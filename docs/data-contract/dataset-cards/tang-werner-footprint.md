# Tang & Werner — global mining footprint

> 74,548 feature-typed polygons of mining land worldwide under CC BY 4.0, used to confirm and bound the real sites
> and as PitStudio's committed mining-footprint masks. · Part of: [Dataset cards](README.md) · Related:
> [Maus et al. mining polygons](maus-polygons.md) · [USGS 3DEP Bingham Canyon](bingham-3dep.md) ·
> [NRW Hambach terrain](hambach-nrw.md) · [Sources and licences](../sources-and-licences.md)

## What and why

Two of PitStudio's real sites are located by hand-typed coordinates: the Bingham Canyon query box and the Hambach
area of interest. Before anything is labelled with a mine's name, the location must be checked against an
independent, openly licensed mine outline. Tang & Werner (2023) published a global mining footprint with polygons
typed by feature (for example pit, waste dump, tailings storage facility) under CC BY 4.0, with an MD5 per file [1].

It is preferred over [Maus et al.](maus-polygons.md) as the default because it is CC BY, not share-alike, so its
derived masks can sit in the same layer as other CC BY artefacts.

## Datasheet

### Composition

| Item | Value | Source |
|---|---|---|
| Polygons | 74,548 | [1] |
| Mapped area | about 66,000 km² | [1] |
| Format | Esri shapefile set (`.shp` main file 296 MB) | [1] |
| Attributes | feature type per polygon (pit, dump, tailings facility, …) | [1] |
| Version | v1, 2023-04-26 | [1] |

The full attribute list and the coordinate system are read from the shapefile set after download and recorded in
the manifest.

### Collection and provenance

- **Authors:** Tang, Werner [1].
- **Collection:** polygons digitised by the authors and typed by mining feature [1]; the imagery and mapping method
  are described in the authors' article, which was not re-read for this card.
- **Version read:** Zenodo v1, 2023-04-26, read on 2026-10-02 [1].
- **Landing page and DOI:** https://zenodo.org/records/7894216, DOI 10.5281/zenodo.7894216 [1].

### Licence and attribution

- **SPDX:** `CC-BY-4.0`. **Licence class:** `attribution`. **Redistribution class:** `redistributable`; PitStudio
  commits derived masks only.
- **Attribution text**, reproduced verbatim on every derived mask:
  "Tang, Werner (2023). Global mining footprint. Zenodo. https://doi.org/10.5281/zenodo.7894216. Licensed under
  CC BY 4.0."
- **Conflicts:** none found.

### Size, checksums and access

- **Size:** 296 MB for the `.shp` file, plus the companion files of the set [1].
- **Checksum:** MD5 published per file [1]; `s00_download` checks it and pins a SHA-256 at first download.
- **Account:** none.
- **Programmatic path:** Zenodo record API → HTTPS download by pooch [1].
- **Fallback:** none needed (open, no account). It is itself the fallback of the optional Maus layer.

## Assumptions and limits

- **Mapping date.** The polygons describe mining land at the imagery dates used by the authors, not today's pit
  edge; a polygon can lag a growing pit.
- **Footprint, not depth.** Polygons bound the disturbed area; they carry no elevation and say nothing about bench
  geometry.
- **Global product, local use.** Accuracy at one site is not guaranteed by global accuracy figures; each site check is
  visual and recorded (polygon id, overlap with the area of interest).
- **Site confirmation rule.** If the Bingham query box does not overlap a pit-type polygon for Bingham Canyon, the box
  is corrected before any artefact is labelled "Bingham Canyon".

## In PitStudio

- **Source id:** `tang-werner-footprint` in `data/sources.yaml`.
- **Stages:** `s00_download` → `s10_preprocess` (select the polygons over the default sites, check the areas of
  interest, rasterise masks on the terrain grid) → `st10_terrain` (area-of-interest crop) → `s60_export` (masks).
- **Uses:** confirmation of the [Bingham](bingham-3dep.md) and [Hambach](hambach-nrw.md) areas of interest; the
  mining-footprint mask layer over the real terrain; the fallback for the share-alike [Maus](maus-polygons.md) layer.
- **Cases:** supports every case that uses the real sites (A1, A2, C1, C2, E2) through the site check; no KPI is
  computed from the polygons themselves.
- **Committed:** derived masks with the attribution text. **Never committed:** the shapefile set.
- **Status:** **Not yet downloaded by the pipeline** — fetched by `s00_download` in the data-and-models phase.

## References

1. Tang, Werner (2023). "Global mining footprint" (Zenodo record: files, MD5, licence), v1, 2023-04-26.
   https://doi.org/10.5281/zenodo.7894216 — record API: https://zenodo.org/api/records/7894216 (accessed 2026-10-02)

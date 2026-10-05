# Maus et al. — global mining polygons v2 (optional)

> 44,929 mining-area polygons under CC BY-SA 4.0, an optional share-alike layer kept apart from every CC BY artefact.
> · Part of: [Dataset cards](README.md) · Related: [Tang & Werner mining footprint](tang-werner-footprint.md) ·
> [Sources and licences](../sources-and-licences.md) · [Manifest](../manifest.md) ·
> [MineLib marvin](minelib-marvin.md)

## What and why

A second, independent mine-outline set strengthens the site checks of the real sites (Bingham, Hambach): if two
independent polygon sets agree, a hand-typed area of interest is unlikely to be wrong. Maus et al. (2022) published
version 2 of their global mining polygons with grids at several resolutions and a stated accuracy [1].

The catch is the licence: **CC BY-SA 4.0**, share-alike. Every layer derived from it must also be CC BY-SA 4.0. That
is acceptable for an optional, clearly labelled layer, but not for the core masks, which is why
[Tang & Werner](tang-werner-footprint.md) (CC BY) is the default and the fallback.

## Datasheet

### Composition

| Item | Value | Source |
|---|---|---|
| Polygons | 44,929 | [1] |
| Mapped area | 101,583 km² | [1] |
| Formats | GeoPackage of polygons + GeoTIFF grids at 30″, 5′ and 30′ | [1] |
| Main file | `global_mining_polygons_v2.gpkg`, 23.5 MB | [2] |
| Stated accuracy | 88.3 % overall accuracy at control points | [1] |
| Version | v2, 2022-03-14 | [1] |

PitStudio uses only the GeoPackage; the grids are not downloaded.

### Collection and provenance

- **Authors:** Maus et al. [1]; the data descriptor article is DOI 10.1038/s41597-022-01547-4 [1].
- **Collection:** polygons delineated by the authors, with accuracy assessed at control points [1]; the method is
  described in the data descriptor.
- **Version read:** PANGAEA v2, 2022-03-14, read on 2026-10-02 [1].
- **Landing page and DOI:** https://doi.pangaea.de/10.1594/PANGAEA.942325, DOI 10.1594/PANGAEA.942325 [1].

### Licence and attribution

- **SPDX:** `CC-BY-SA-4.0`. **Licence class:** `share-alike`. **Redistribution class:** `redistributable`, with
  share-alike: **every derived layer is CC BY-SA 4.0 too**.
- **Separate manifest entries.** A Maus-derived layer is always its own manifest entry with its own `licence_class`
  and attribution; it is never merged with, baked into, or rasterised together with a CC BY layer.
- **Attribution text**, reproduced verbatim on every derived layer:
  "Maus et al. (2022). Global-scale mining polygons (Version 2). PANGAEA. https://doi.org/10.1594/PANGAEA.942325.
  Licensed under CC BY-SA 4.0. This derived layer is licensed under CC BY-SA 4.0."
- **Conflicts:** none found.

### Size, checksums and access

- **Size:** 23.5 MB (GeoPackage) [2].
- **Checksum:** none published on the page [2]; the SHA-256 is pinned at first download.
- **Account:** none.
- **Programmatic path:** HTTPS download from `download.pangaea.de/dataset/942325/files/` by pooch [2].
- **Fallback:** [Tang & Werner](tang-werner-footprint.md). Without Maus, site checks use one polygon set and no
  share-alike layer is shown.

## Assumptions and limits

- **88.3 % overall accuracy** is a global figure [1]; at a single site the outline can still be off and is checked
  visually.
- **Mapping epoch.** Polygons describe mining land at the authors' imagery dates; a growing pit can extend beyond them.
- **Share-alike contagion** is the main risk: one accidental merge would relicense a CC BY layer. Every manifest
  entry lists the source ids it derives from, so an entry that mixes a share-alike source with a CC BY source is
  visible and is treated as a defect.
- **Optional.** No case or KPI depends on this layer.

## In PitStudio

- **Source id:** `maus-v2` (optional) in `data/sources.yaml`.
- **Stages:** `s00_download` (optional) → `s10_preprocess` (select polygons over the default sites, cross-check with
  Tang & Werner) → `s60_export` (a separate share-alike outline layer).
- **Cases:** none directly; it strengthens the site checks behind A1, A2, C1, C2 and E2.
- **Committed:** a separate share-alike outline layer, labelled CC BY-SA 4.0. **Never committed:** the GeoPackage
  or grids.
- **Status:** **Not yet downloaded by the pipeline** — fetched by `s00_download` in the data-and-models phase.

## References

1. Maus, V. et al. (2022). "Global-scale mining polygons (Version 2)". PANGAEA. https://doi.org/10.1594/PANGAEA.942325
   (accessed 2026-10-02). Data descriptor: https://doi.org/10.1038/s41597-022-01547-4
2. PANGAEA. File listing for dataset 942325 (file names, sizes, download base URL), accessed 2026-10-02.
   https://doi.pangaea.de/10.1594/PANGAEA.942325?format=textfile

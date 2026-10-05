# EGMS — ground motion over Hambach

> Sentinel-1 InSAR ground-motion products of the European Ground Motion Service over the Hambach pit, used as real
> slope deformation for case C1 under a derived-only rule. · Part of: [Dataset cards](README.md) · Related:
> [NRW Hambach terrain](hambach-nrw.md) · [C1 Slope time of failure](../../cases/c1-slope-time-of-failure.md) ·
> [de Wit slope failure](dewit-slope-failure.md) ·
> [Maintainer acts and licences](../../studio/owner-acts-and-licences.md)

## What and why

Slope monitoring (C1) is about displacement through time. Open-pit slope radars are private, but the European
Ground Motion Service (EGMS) publishes Sentinel-1 persistent- and distributed-scatterer InSAR for Europe [2]. Over
Hambach, it gives real line-of-sight and decomposed motion of a working pit's walls, next to the open
[NRW terrain](hambach-nrw.md). A 2026 EGMS review reports the service capturing deformation around Hambach (search
result only, not fetched — UNVERIFIED) [4].

EGMS is **optional**: its download is a manual maintainer act, and C1 has a complete fallback.

## Datasheet

### Composition

Three product levels [2]:

| Level | Content | Format |
|---|---|---|
| L2a basic | line-of-sight (LOS) displacement per measurement point | CSV in ZIP archives per Sentinel-1 burst |
| L2b calibrated | LOS displacement referenced to GNSS | CSV in ZIP archives per burst |
| L3 ortho | vertical and east–west motion on a 100 m grid | GeoTIFF + CSV in 100 km tiles |

- **Releases:** multi-year windows from 2015–2020 up to 2019–2023 at the time of reading; 6-day sampling since
  October 2016 [2].
- **Availability:** only the latest two product releases can be downloaded [1]. The release used is recorded at
  download.
- **Units and reference frame:** read from the product description of the release used and recorded in the manifest.

### Collection and provenance

- **Publisher:** Copernicus Land Monitoring Service (CLMS), operated for the European Union with the European
  Environment Agency [1].
- **Collection:** Sentinel-1 radar acquisitions processed by persistent- and distributed-scatterer interferometry
  into time series, then calibrated (L2b) and decomposed (L3) [2].
- **Version read:** product description v3, read on 2026-10-02 [2].
- **Landing page:** https://land.copernicus.eu/en/products/european-ground-motion-service [1].

### Licence and attribution

- **Two statements conflict.** The CLMS data policy is "full, open and free": it allows reproduction, adaptation and
  commercial use and requires a source statement [3]. The EGMS product description carries an "EUPL (>= 1.2)"
  licence line [2].
- **Consequence:** the source is **`derived-only`** until the conflict is resolved. Raw products are never committed
  or re-hosted; only derived summaries are published.
- **SPDX:** no exact id; the registry uses the project id `LicenseRef-Copernicus-CLMS`, pointing to the CLMS data
  policy, and records the EUPL line as the conflicting label. **Licence class:** `attribution` (source statement), derived-only.
- **Attribution text:** the CLMS source statement, reproduced on every derived artefact. Its exact wording is pinned
  from the data policy at specification (UNVERIFIED here); the artefact also names the EGMS release and level.

### Size, checksums and access

- **Size:** per burst (L2a/L2b) or per 100 km tile (L3) [2]; the Hambach selection is small.
- **Checksum:** none published (UNVERIFIED); the SHA-256 is pinned when the files are first stored.
- **Account:** **yes** — EGMS Explorer is the only access path [1]. A scripted API is UNVERIFIED.
- **Programmatic path:** none assumed. The maintainer downloads the Hambach tiles from EGMS Explorer by hand; the
  pipeline then registers them by SHA-256 like any other source.
- **Default and fallback:** the optional maintainer act is off by default, so **C1 uses de Wit + synthetic only**.

## Assumptions and limits

- **No failure in the record (expected).** EGMS shows slow, ongoing motion, not a failure with a known time. It is
  therefore real deformation *context* for C1, never a time-of-failure ground truth; that role belongs to the
  [de Wit event](dewit-slope-failure.md) and the synthetic Voight series.
- **Not a classifier two-sample test reference.** The validation of synthetic data compares against real data only
  for fragment images and terrain statistics; EGMS is not used for that.
- **Spatial and temporal resolution:** a 100 m grid (L3) and 6-day sampling cannot resolve single benches or fast
  pre-failure acceleration [2].
- **LOS geometry:** L2 values are along the satellite line of sight; comparisons with slope-normal motion need the
  geometry stated in the derived summary.
- **Release churn:** older releases disappear from Explorer [1], so a re-run may need the release pinned in the
  manifest to be re-downloaded or replaced.

## In PitStudio

- **Source id:** `egms-hambach` in `data/sources.yaml`.
- **Stages:** manual download (maintainer act) → registration in `s00_download` by SHA-256 → `s10_preprocess`
  (clip to the Hambach area of interest, select pit-wall points, aggregate) → `s60_export` (derived summaries).
- **Cases:** [C1](../../cases/c1-slope-time-of-failure.md).
- **Methods:** [M14](../../methods/m14-slope-forecasting.md) (real deformation context),
  [M23](../../methods/m23-rtx-sensor-simulation.md) (analytical slope-radar model compared with real LOS motion).
- **Committed:** derived summaries only (for example aggregated velocity statistics over the pit walls), with the
  source statement. **Never committed:** raw EGMS CSV, ZIP or GeoTIFF files.
- **Status:** **Not yet downloaded by the pipeline** — fetched by `s00_download` in the data-and-models phase, only
  if the maintainer downloads the tiles from EGMS Explorer.

## References

1. Copernicus Land Monitoring Service. "European Ground Motion Service" product page (Explorer-only access, latest
   two releases), accessed 2026-10-02. https://land.copernicus.eu/en/products/european-ground-motion-service
2. Copernicus Land Monitoring Service. "European Ground Motion Service — Product Description" v3 (levels,
   resolution, epochs, formats, EUPL line), accessed 2026-10-02.
   https://library.land.copernicus.eu/products/European_Ground_Motion_Service_Product_Description_v3.html
3. Copernicus Land Monitoring Service. "Data policy" (full, open and free; source statement), accessed 2026-10-02.
   https://land.copernicus.eu/en/data-policy
4. "EGMS: a decade of Sentinel-1 observations", *Remote Sensing of Environment*, 2026 (search result only, not
   fetched — UNVERIFIED). https://www.sciencedirect.com/science/article/pii/S0034425726001598

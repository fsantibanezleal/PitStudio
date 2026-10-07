# ERA5 and GHCNh — wind for the dust case

> Hourly wind for the dust case: ERA5 reanalysis (CC BY, needs a Copernicus account) or, by default, NOAA GHCNh hourly
> observations at Salt Lake City International Airport (US Government data, no account). · Part of:
> [Dataset cards](README.md) · Related: [C3 Dust](../../cases/c3-dust.md) ·
> [M16 Dust dispersion](../../methods/m16-dust-dispersion.md) · [EPA AP-42 §13.2.2](ap42.md) ·
> [Maintainer acts and licences](../../studio/owner-acts-and-licences.md)

## What and why

The dust case (C3) spreads haul-road and blast emissions with a Gaussian plume and Lagrangian particles. Both need
the **wind**: how often it blows from each direction and how strongly. PitStudio needs wind statistics near the
default site (Bingham Canyon), from a source that anyone can fetch.

- **ERA5** is the cleaner gridded source: hourly from 1940 at 0.25°, under a CC-BY licence, scripted with `cdsapi`
  [1]. It needs a Copernicus Climate Data Store (CDS) account, which is an optional maintainer act.
- **NOAA GHCNh** (Global Historical Climatology Network – hourly) is the **no-account fallback**: hourly station
  observations, US Government data. PitStudio uses its station at Salt Lake City International Airport [2].
- **Open-Meteo was rejected as the primary source:** its data are CC BY 4.0, but the free API is for non-commercial
  use only, with call limits [4].

Optional accounts are off by default, so **the default build uses GHCNh**.

## Datasheet

### Composition

| Item | ERA5 single levels | GHCNh station |
|---|---|---|
| Content | gridded reanalysis, hourly | station observations, hourly |
| Period | 1940 → present [1] | station record (years selected at specification) |
| Resolution / location | 0.25° grid [1] | station `USW00024127` "UT SALT LAKE CITY INTL AP": lat 40.7706°, lon −111.9650°, elevation 1288.4 m, WMO 72572 [2] |
| Variables used | near-surface wind (fields fixed at specification) | wind speed and direction (fields fixed at specification) |
| Format | GRIB (NetCDF option) [1] | per-station files (format pinned at specification) |

The station sits about 32 km from the centre of the Bingham query box (great-circle distance computed from the
station coordinates [2] and the provisional box of the [Bingham card](bingham-3dep.md)).

### Collection and provenance

- **ERA5:** produced by ECMWF for the Copernicus Climate Change Service (C3S) and served by the CDS; dataset
  "ERA5 hourly data on single levels from 1940 to present", DOI 10.24381/cds.adbb2d47 [1]. Read on 2026-10-02.
- **GHCNh:** NOAA National Centers for Environmental Information (NCEI). GHCNh is the successor of the Integrated
  Surface Database (ISD): ISD "has been superseded, with no update beyond 08/24/2025", and users are directed to GHCNh
  [3]. ISD (ISD, ISD-Lite, ISD CSV) remains available on NOAA's Open Data Dissemination (NODD) buckets as a static
  alternative [3]. The station line was checked in the GHCNh station list on 2026-10-04 [2].

### Licence and attribution

- **ERA5 — SPDX:** `CC-BY-4.0` (the CDS page states a "CC-BY licence" [1]; the exact version is confirmed at
  specification). **Licence class:** `attribution`. **Redistribution class:** `redistributable` with attribution.
- **GHCNh — SPDX:** `LicenseRef-USGov-PD`. **Licence class:** `public-domain` (US Government data). The NOAA terms
  are verified at specification (UNVERIFIED here). **Redistribution class:** `redistributable`.
- **Attribution text** on every derived wind statistic:
  - ERA5: "Contains ERA5 data: Copernicus Climate Change Service (C3S), ERA5 hourly data on single levels from 1940
    to present. https://doi.org/10.24381/cds.adbb2d47. CC BY. Accessed <date>." (any additional wording required by
    the CDS licence is pinned at specification)
  - GHCNh: "NOAA National Centers for Environmental Information, Global Historical Climatology Network – hourly
    (GHCNh), station USW00024127, accessed <date>."
- **Conflicts:** none found.

### Size, checksums and access

- **Size:** small — one grid cell or one station, a few years of hourly values.
- **Checksum:** ERA5 is an API extract with no publisher checksum; GHCNh files publish none that was seen. In both
  cases the SHA-256 of the retrieved file is pinned at first download, and for ERA5 the exact request (variables,
  area, period) is stored with it.
- **Account:** ERA5 **yes** (CDS account + licence acceptance, optional maintainer act); GHCNh **no**.
- **Programmatic path:** ERA5 with `cdsapi` and the maintainer's key from an environment variable [1]; GHCNh by HTTPS
  from NCEI (exact URL pattern pinned at specification). The ISD copy on NODD is the static alternative [3].
- **Fallback chain:** ERA5 (if the account exists) → GHCNh (default) → ISD on NODD.

## Assumptions and limits

- **ERA5 at 0.25° is coarse for in-pit flow.** At this latitude a cell is roughly 21 km × 28 km (from 0.25° of
  longitude and latitude); it cannot see the pit's own circulation, cold-air pooling or wind channelling along
  benches.
- **The airport is not the pit.** The station stands in the valley at 1288.4 m [2], about 32 km north-east of the
  query box; the pit's elevation and exposure differ (not asserted here). Its statistics represent regional flow, and
  the C3 case page states this.
- **Screening, not regulatory modelling.** Wind statistics drive a screening plume; regulatory dispersion modelling
  (AERMOD) is out of scope ([AP-42 card](ap42.md)).
- **Data gaps and calm hours** are counted and reported, not filled silently.

## In PitStudio

- **Source ids:** `era5`, `ghcnh` in `data/sources.yaml`.
- **Stages:** `s00_download` → `s10_preprocess` (QC, gap and calm counts, wind-speed and direction distributions) →
  `s60_export` (wind statistics).
- **Cases:** [C3](../../cases/c3-dust.md).
- **Methods:** [M16](../../methods/m16-dust-dispersion.md) (plume and Lagrangian dust),
  [M23](../../methods/m23-rtx-sensor-simulation.md) (dust in the lidar model through the C3 dust field).
- **Committed:** wind statistics only (distributions and summary tables) with the attribution text. **Never
  committed:** raw GRIB/NetCDF or station files, the CDS key.
- **Status:** **Not yet downloaded by the pipeline** — fetched by `s00_download` in the data-and-models phase.

## References

1. Copernicus Climate Change Service (C3S), ECMWF. "ERA5 hourly data on single levels from 1940 to present", Climate
   Data Store. https://doi.org/10.24381/cds.adbb2d47 — https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels
   (accessed 2026-10-02)
2. NOAA NCEI. GHCNh station list (line `USW00024127 40.7706 -111.9650 1288.4 UT SALT LAKE CITY INTL AP 72572`),
   accessed 2026-10-04.
   https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh-station-list.txt
3. NOAA NESDIS. "Service location change: Integrated Surface Data – global hourly" (ISD superseded by GHCNh; ISD on
   NODD), 2026. https://www.nesdis.noaa.gov/news/service-location-change-integrated-surface-data-global-hourly
   (accessed 2026-10-04)
4. Open-Meteo. Terms (CC BY 4.0 data; free API non-commercial with limits), accessed 2026-10-02.
   https://open-meteo.com/en/terms

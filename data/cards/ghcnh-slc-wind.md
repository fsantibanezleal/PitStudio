---
id: ghcnh-slc-wind
kind: real
title: "NOAA GHCNh hourly observations of station USW00024127, Salt Lake City International Airport, Utah, calendar years 2015 to 2024 (wind speed and direction used by case C3)"
spdx: CC0-1.0
licence_class: public-domain
redistribution: redistributable
attribution: "Menne, M.J., Noone, S., Casey, N.W., Dunn, R.H., McNeill, S., Kantor, D., Thorne, P.W., Orcutt, K., Cunningham, S., Risavi, N. (2023): Global Historical Climatology Network-Hourly (GHCNh), station USW00024127, NOAA National Centers for Environmental Information. https://doi.org/10.25921/jp3d-3v19"
files_sha256:
  - 1bf226bfc3330cf88d85c97f4c4edac3bd99d57aadd4640cffdaf1e1ca41f4a3
  - d14d682a038e7715c2c5c33a7985771940397d3bd440e5238b3e0e45dceb318e
  - 68e43b7629b1c18d1a349cdef0d8e628b7edda6c60b98fb7e4b55cb0b30cb78e
  - b259bc020d537cfa8f76cd7e1ae8cf8a80f182d3ce2870cc55da1fbd08ac8519
  - 4cafb829629cda126a1f632054ff0a4b1e6fe5c8404fdfb9602fa24ac21b5f3a
  - 1b89bbd96e4fe02b77e31284ef968abb084b54a74f0e7b3cd1ed2b0fb7afdb8d
  - da1437b1d268d8e4890efca0d0de685daca68566acd45868168609d1e7a743ec
  - 0e4b76a89e85351bf5eee7ef8b7ffa082dffe08f2f4d4014b4521d99d955a12e
  - 571c3b8f7a9279c191720733fe1ede427eef7f90f5b703953108e18974747c66
  - 21c876e5ef94ecbc3639507b76bb1951f920ce78a2b931a1452f4bcee299e283
landing_url: "https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly"
citation: "Menne et al. 2023, Global Historical Climatology Network-Hourly (GHCNh), subset: station USW00024127, 2015 to 2024, NOAA NCEI, https://doi.org/10.25921/jp3d-3v19. Accessed 2026-11-24."
---

# ghcnh-slc-wind

## What and why

The hourly wind of the nearest long-record station to the Bingham Canyon pit (about 32 km, [era5-ghcnh](../../docs/data-contract/dataset-cards/era5-ghcnh.md)), the no-account fallback of the ERA5 wind (spec 008 section 7). Case C3 (haul-road dust) reads its wind speed and direction for the wind rose, the prevailing wind of the plume map and the long-term concentration at the receptors (`pitstudio_pipeline.dust`).

## Composition

Ten pipe-separated files, one per calendar year 2015 to 2024 (UTC), of the NCEI per-year folder (`.../hourly/access/by-year/<year>/psv/GHCNh_USW00024127_<year>.psv`), 329 columns each, 128,086 rows in all (several report types per hour: FM-15 routine, FM-12, FM-16 special), reduced by the reader to 87,629 UTC hours with a speed. Station USW00024127 "SALT LAKE CITY INTL AP", latitude 40.7706, longitude -111.965, elevation 1288.4 m. The 2025 file was not fetched (the year is incomplete); the period is stated in the run summary as 2015-01-01 to 2024-12-31 UTC.

## Collection and provenance

NOAA NCEI GHCNh, successor of the Integrated Surface Database. Files fetched anonymously over HTTPS on 2026-11-24 with a Python script into `raw/ghcnh-slc-wind/` of the data root; the digests in the front matter were computed on the downloaded bytes. The NCEI server dates of the files are 2026-07-10 and 2026-07-11 (Last-Modified headers).

## Licence and attribution

The NCEI metadata record of GHCNh (read 2026-11-24, `iso?id=gov.noaa.ncdc:C01688`) states that the data "were produced by NOAA and are not subject to copyright protection in the United States" and that NOAA "waives any potential copyright and related rights in these data worldwide" through the Creative Commons Zero 1.0 Universal Public Domain Dedication (CC0-1.0). NOAA and NCEI give no warranty of accuracy. Cite as in the front matter; the NCEI record asks that users credit NOAA NCEI as the creator.

## Size checksums and access

122,614,918 bytes in ten files of 11.9 to 12.7 MB; SHA-256 in the front matter and in `data/sources.yaml`. Anonymous HTTPS, never committed or re-hosted.

## Assumptions and limits

- Quality codes seen in the wind columns of 2015, 2019 and 2024: speed 1, 5, A, P, 4 or blank; direction 1, 5, 9, 4 or blank. The text of the GHCNh documentation (PDF) could not be read here, so the meaning of the codes is UNVERIFIED: 1 and 5 are read as "passed" by the ISD convention and every other code drops the speed or the direction, counted in the run summary.
- Direction 999 stands on every calm and variable hour, with `wind_direction_Measurement_Code` C (calm, speed 0.0) or V (variable) and quality code 9 or blank; N marks a normal observation. The letters follow the ISD wind-observation-type convention (UNVERIFIED for GHCNh). Such hours have no direction. The `ghcnh_hourly` pandera schema of `pitstudio_pipeline.ingest.schemas` bounds `wind_direction` to 0 to 360, so it would reject these files whole: this is reported to the owner as a question (the schema bound and the real values disagree) and the C3 reader validates the wind columns itself.
- The anemometer height of the station is not stated by the files (10 m by the usual WMO siting, UNVERIFIED); no height correction is applied.
- The reader keeps the earliest valid record of each UTC hour.

## In PitStudio

`pitstudio_pipeline.dust.winds.read_ghcnh_wind` reads the files; `pitstudio_pipeline.dust.c3_run` turns them into the wind rose, the prevailing wind of the plume map and the receptor statistics of case C3.

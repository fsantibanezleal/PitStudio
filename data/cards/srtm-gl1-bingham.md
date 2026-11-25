---
id: srtm-gl1-bingham
kind: real
title: "SRTM GL1 one-arc-second elevation tile N40W113 (NASA, February 2000, EGM96 heights) over the Bingham Canyon area, Utah"
spdx: LicenseRef-USGov-PD
licence_class: public-domain
redistribution: redistributable
attribution: "NASA Shuttle Radar Topography Mission (SRTM) Global 1 arc second, NASA JPL and NGA; distributed by NASA EOSDIS Land Processes DAAC (public domain)."
files_sha256:
  - f855eeb49139b416a2bad301d8fee9ee35c0118232b0707d43fad0f5ff069390
landing_url: "https://www.earthdata.nasa.gov/data/catalog/lpcloud-srtmgl1-003"
citation: "NASA Shuttle Radar Topography Mission Global 1 arc second (SRTMGL1 version 3), acquired 2000-02-11 to 2000-02-21, NASA EOSDIS Land Processes DAAC, catalog entry LPCLOUD SRTMGL1.003. Tile N40W113 fetched from the OpenTopography public bucket on 2026-11-24."
---

# srtm-gl1-bingham

## What and why

The only global elevation model that predates the 3DEP lidar over the Bingham Canyon pit (acquired 2000-02-11 to 2000-02-21, NASA Earthdata catalog temporal extent). It is the older epoch of the coarse E2 pair, "coarse 30 m, 2000 to 2018" (spec 017, FR-017-34): the 3DEP 2023 and 2013 tiles do not cover the pit, and the 2006 point clouds are a later unit.

## Composition

One GeoTIFF tile N40W113, 3601 x 3601 cells of 1 arc-second (about 31 m north-south and 24 m east-west here), EPSG:4326, int16 metres, no data -32768, 1184 to 3347 m, no void cell in the tile. The tile holds the original SRTM GL1 heights (the folder `SRTM_GL1_srtm` of the bucket, orthometric EGM96; the ellipsoidal product lives in another folder).

## Collection and provenance

Radar interferometry (C-band) flown on the Space Shuttle Endeavour, STS-99. The key route of the OpenTopography global DEM API was not used: no OpenTopography key exists in the coordination credentials, and the public bucket `opentopography.s3.sdsc.edu` serves the same tiles anonymously (HEAD and GET answered 200, 11,459,943 bytes). The tile was fetched on 2026-11-24 to `raw/srtm-gl1-bingham/` of the data root.

## Licence and attribution

NASA catalog statement read on 2026-11-24: "This dataset is openly shared, without restriction, in accordance with the EOSDIS Data Use and Citation Guidance." Treated as public domain; SPDX `LicenseRef-USGov-PD`. Credit: NASA JPL and NGA, distributed by NASA EOSDIS Land Processes DAAC.

## Size checksums and access

11,459,943 bytes; SHA-256 in the front matter. Anonymous HTTPS, never committed or re-hosted.

## Assumptions and limits

- Heights are EGM96 (USGS EROS page, read 2026-11-24). The run converts to NAVD88 with the PROJ grids `us_nga_egm96_15` and `us_noaa_g2018u0` (a shift of -0.62 to -0.30 m over the 2018 tile); the converted DEM then differs from the lidar by an unknown geoid-model offset of a few centimetres (the geoid of the 2018 product is UNVERIFIED).
- The absolute vertical accuracy of SRTM is not stated by the pages read. A secondary source reports better than 9 m at 90 % for the original data (the papers of Farr et al. 2007 and Rodriguez et al. 2006 were not readable here: UNVERIFIED). The E2 bounds use the larger of 9 m / 1.645 and the standard deviation measured on stable ground (7.05 m); in steep terrain the measured value is the figure that applies.
- C-band radar reflects from canopy and rock surfaces at February 2000 conditions (snow or vegetation shift heights); the 2018 lidar is bare earth. The stable-ground mean difference, -5.5 m (SRTM higher), is the combined signature of these effects and is reported, not removed.
- Cell size 1 arc-second, no 1 m detail; steep pit walls are smoothed.

## In PitStudio

`pitstudio_studio.survey.coarse_pair` samples the tile bilinearly at the cell centres of a 30 m UTM grid, adds the datum grid, differences it against the 2018 lidar DEM block-averaged to 30 m over the pit outline, and reports cut, fill and net with bounds and the stable-ground check, labelled "measurement, not validation" and "coarse 30 m, 2000 to 2018".

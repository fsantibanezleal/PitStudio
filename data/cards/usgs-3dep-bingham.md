---
id: usgs-3dep-bingham
kind: real
title: "USGS 3DEP one-metre lidar DEMs of the Bingham Canyon area, Utah: UT Central QL2 2018 and UT 2023 Salt Lake Co (tile x40y449)"
spdx: LicenseRef-USGov-PD
licence_class: public-domain
redistribution: redistributable
attribution: "U.S. Geological Survey, 3D Elevation Program (public domain)"
files_sha256:
  - 484a57cc33c95696d163bddf5dc6de353e71cc3d1946b568cf895939c6c90391
  - e1b755b0f23f6a8f0f361fa941c819bf7bf804e8678dd372c48ccbfbea1cec19
landing_url: "https://apps.nationalmap.gov/downloader/"
citation: "U.S. Geological Survey, 3D Elevation Program, one-metre DEM tile x40y449, projects UT Central QL2 2018 and UT 2023 Salt Lake Co, The National Map. Accessed through the TNM Access API, 2026-10-12 and 2026-10-13."
---

# usgs-3dep-bingham

## What and why

Two lidar-derived bare-earth elevation models of the Bingham Canyon area: the terrain of the A1 scene (2018) and the two epochs of the E2 survey-volume case (spec 017, FR-017-30 to FR-017-34).

## Composition

| File | Project | Epoch | Grid |
|---|---|---|---|
| `ut-central-ql2-2018-dem.tif` | UT Central QL2 2018 | 2018 | 10,012 x 10,012 cells of 1 m, NAD83 / UTM 12N (EPSG:26912), float32, no data -999999; valid in the western part of the tile |
| `ut-2023-salt-lake-co-dem.tif` | UT 2023 Salt Lake Co (`UT_2023SaltLakeCo_C24`) | 2023 | 10,000 x 10,000 cells of 1 m, EPSG:26912, no data -999999; valid only east of about x 404,600 m |

The two files carry no vertical-datum, geoid or accuracy tags. Their product text names NAVD88 metres (quoted in the interim manifest of the data root). The two tiles overlap only in a strip about 162 m wide; the Bingham pit lies in the 2018 part only.

## Collection and provenance

Selected by the TNM Access API query for datasets "Digital Elevation Model (DEM) 1 meter" over the bounding box lon -112.17 to -112.12, lat 40.50 to 40.54, which returns three products (2023, 2018 and a 2013 tile whose valid cells do not reach the pit). Downloaded 2026-10-12 and 2026-10-13 to `raw/usgs-3dep-bingham/` of the data root; digests as in the registry. Flight dates inside each project year are not stated by the product text read (UNVERIFIED).

## Licence and attribution

Public domain, a work of the U.S. Government. SPDX `LicenseRef-USGov-PD`. Credit line: U.S. Geological Survey, 3D Elevation Program (public domain).

## Size checksums and access

165,604,778 and 257,390,595 bytes; SHA-256 values in the front matter. Anonymous access to the staged-products bucket; never committed or re-hosted.

## Assumptions and limits

- Vertical accuracy (RMSEz) is not in the files: the E2 recipe uses the specification bound of 0.10 m and labels it as such (UNVERIFIED against the project reports).
- The geoid model of either product is not stated by the text read (UNVERIFIED); a mismatch between GEOID12B and GEOID18 would add an unknown offset of a few centimetres.
- Bare earth under vegetation and steep faces carry larger errors than the specification bound; horizontal misregistration on slopes appears as vertical difference.

## In PitStudio

`st10_terrain` reads the 2018 file for the A1 scene terrain; the E2 run (`pitstudio_studio.survey.real_run`) differences the two epochs over the cells that hold data in both and reports the volumes with their bounds, labelled "measurement, not validation".

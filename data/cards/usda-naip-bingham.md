# usda-naip-bingham

The orthophoto that colours the terrain of the Bingham Canyon scene (spec 004, FR-004-48 and FR-004-49).

| Item | Value |
|---|---|
| Producer | U.S. Department of Agriculture, Farm Service Agency, Aerial Field Photography Office (National Agriculture Imagery Program, NAIP) |
| Product | Utah 2018 NAIP, 60 cm ground sample distance, four bands (red, green, blue, near-infrared), 8 bit, one GeoTIFF per quarter quad |
| File used | `m_4011231_se_12_060_20180909.tif`, acquired 2018-09-09, NAD83 / UTM zone 12N (EPSG:26912), 374 MB, SHA-256 `c9dbdf58dea5573a04b565b0c47b0bb9d4cea3b466e5e47235d38f678c6ef7fc` |
| Access | Microsoft Planetary Computer STAC collection `naip` (anonymous, signed blob URL), item `ut_m_4011231_se_12_060_20180909_20181209`, fetched 2026-11-22 |
| Licence | Public domain. Statement: USDA Farm Service Agency, "Policies and Links", Digital Rights and Copyright: most information presented on the FSA site is public domain and may be freely distributed or copied, with a byline requested ("U. S. Department of Agriculture, Farm Service Agency"). Page saved in the data root with its SHA-256 `c04cf016951f217eb7f334e8c31adf034050ea958ee08f3c6961dc0bbef29331`. SPDX: `LicenseRef-USGov-PD`. |
| Where it lives | the data root, `raw/naip/` (never committed; 374 MB) |

## Collection and choice of year

NAIP covers the area in 2011, 2014, 2016, 2018 and 2021 (STAC search of the collection over the bounding box of the scene, 2026-11-22). The elevation model of the scene is USGS 3DEP project "UT Central QL2 2018" (`usgs-3dep-bingham`, epoch 2018), so the stage `st10_terrain` takes the acquisition year nearest 2018 (a tie goes to the earlier year): 2018, a gap of zero years. The exact lidar flight dates of the 3DEP project could not be read (the ScienceBase item answered 403 and the project metadata file is not published beside the tiles): the project year 2018 is the year used, UNVERIFIED to the month. The photograph and the DEM can differ where the pit advanced between their dates.

## Known biases and limits

- Shadows are baked into the colour (September, mid-morning to noon sun in the image, not the sun of the rendered scene); the terrain shows them under every light.
- The image is an orthophoto of the surface at its date: benches blasted or backfilled between the lidar flight and the photograph can be shifted in colour against the DEM. The registration check compares the rendered plan view with the photograph, in grid cells.
- Vehicles and stockpiles present on the photograph date are painted on the ground.
- 8-bit colour from a four-band sensor; the near-infrared band is never read.

## Use and leakage

Used as the diffuse colour of the terrain in rendered scene images and the published flyover. It is not a training label and no perception model is trained on the terrain colour alone; the synthetic datasets that render this scene state the orthophoto in their scene manifest (`terrain.albedo`).

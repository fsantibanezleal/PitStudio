# Sources and licences

> Every real data source PitStudio plans to use, its licence traced to the original publisher, what may be committed,
> and the licence classes that also cover our own outputs and the NVIDIA tools. · Part of:
> [Data contract](README.md) · Related: [Ingestion](ingestion.md) · [Manifest](manifest.md) ·
> [Dataset cards](dataset-cards/README.md) · [Licences and maintainer acts](../studio/owner-acts-and-licences.md)

## What and why

A public repository can only publish what its inputs allow. PitStudio therefore records, for every source, the licence
as stated by the **original publisher** (not by a mirror or an aggregator), an SPDX identifier, a redistribution class
and a fallback for when the source is unavailable or needs an account the maintainer has not created. The table below
is the human-readable view of `data/sources.yaml`; each row links to a full datasheet.

Three facts shape the whole contract:

- **No licence-clean, real, ground-level image set of haul trucks or excavators was found** during source research.
  The candidates were non-commercial, gated, YouTube-sourced, Google Earth-derived or unreachable (see
  [Excluded sources](#excluded-sources)). Equipment and people perception is therefore trained on synthetic data, and
  its sim-to-real gap is reported as "not measured" unless an optional real probe is labelled.
- **Fragmentation is the one perception task with a real labelled set** (Mendeley rock fragments, CC BY 4.0), so it
  is the only place where PitStudio measures a sim-to-real gap (TSTR vs TRTR).
- **No public haul-cycle telemetry or comminution test data was found**; those gaps are filled with calibrated synthetic
  data under the honesty rule of the [synthetic-data card](dataset-cards/synthetic-data.md).

![Sources grouped by licence class and what is committed](../assets/diagrams/data-sources-licences.svg)

*Sources by licence class, the fetch-and-check path, and the split between committed artefacts and material that never
leaves the machine.*

## Licence classes

Every source, and every artefact PitStudio produces, belongs to exactly one licence class. The class is written into
each manifest entry as `licence_class` ([Manifest](manifest.md)); a derived artefact takes the most restrictive class of
its inputs.

| Class (`licence_class`) | SPDX ids in use | Condition | Derivatives we may publish | Members |
|---|---|---|---|---|
| `public-domain` | `LicenseRef-USGov-PD` | none; citation by courtesy | yes | USGS 3DEP, EPA AP-42, NOAA GHCNh (terms checked at specification) |
| `open-no-attribution` | `DL-DE-ZERO-2.0`, `CC0-1.0` | none | yes | NRW Hambach elevation data, Poly Haven, ambientCG, MakeHuman exports under licence §C |
| `attribution` | `CC-BY-4.0`, `LicenseRef-Copernicus-CLMS` | attribution text must travel with every derivative | yes, with the attribution text | McKinley lidar, de Wit series, Mendeley fragments, Tang & Werner, Xu et al., ERA5, EGMS (derived-only) |
| `share-alike` | `CC-BY-SA-4.0`, `CC-BY-SA-3.0` | attribution + derivatives under the same licence | yes, **as separate CC BY-SA entries** | Maus v2 polygons, MineLib `marvin` (both optional) |
| `own` | `Apache-2.0`, `CC-BY-4.0` | our terms | yes | code (Apache-2.0); docs, figures, our USD, our synthetic data (CC-BY-4.0); trained weights (below) |
| `display-only` | NVIDIA Open Model License outputs | shown with "Built on NVIDIA Cosmos"; not used to train | text only | Cosmos Reason 2 answers and captions |
| `reference-only` | NVIDIA SLA, TensorRT SLA, NVIDIA Open Model License | use on the local machine; no redistribution | **never** | Isaac Sim, Kit, Replicator, ovrtx runtimes, assets and caches; TensorRT engines; Cosmos weights |

**Trained weights.** Our weights are Apache-2.0 with attribution when every training input permits it; otherwise they
take the most restrictive terms of their inputs, stated in the model card ([Models](../models/README.md)).

The **redistribution class** in `data/sources.yaml` is a second, coarser field with three values: `redistributable`,
`derived-only` (only derived artefacts may leave the machine) and `no-redistribution`. It decides what `s60_export` may
copy; the licence class decides which notice travels with it.

## Every source of the plan

### Identity and licence

| Source | Id in `data/sources.yaml` | Original publisher and landing page | SPDX | Licence class | Redistribution |
|---|---|---|---|---|---|
| [USGS 3DEP, Bingham Canyon](dataset-cards/bingham-3dep.md) | `usgs-3dep-bingham` | USGS, The National Map Access API [1][2] | `LicenseRef-USGov-PD` | `public-domain` | redistributable |
| [McKinley Mine lidar 2023](dataset-cards/mckinley-lidar.md) | `ot-mckinley-2023` | OSMRE via OpenTopography, OT.112024.6341.2, DOI 10.5069/G9BZ6486 [3] | `CC-BY-4.0` | `attribution` | redistributable (fetched) |
| [NRW Hambach DGM1 / LAZ](dataset-cards/hambach-nrw.md) | `nrw-hambach-dgm1` | Geobasis NRW, `opengeodata.nrw.de/produkte/geobasis/hm/` [4][5] | `DL-DE-ZERO-2.0` | `open-no-attribution` | redistributable |
| [EGMS over Hambach](dataset-cards/egms-hambach.md) | `egms-hambach` | Copernicus Land Monitoring Service, EGMS Explorer [6][7][8] | `LicenseRef-Copernicus-CLMS` | `attribution` | **derived-only** (label conflict) |
| [de Wit open-pit slope failure](dataset-cards/dewit-slope-failure.md) | `dewit-slope-failure` | Colorado School of Mines via Zenodo, DOI 10.5281/zenodo.15003054 [9] | `CC-BY-4.0` | `attribution` | redistributable |
| [Rock-fragment segmentation](dataset-cards/mendeley-rock-fragments.md) | `mendeley-78ht3pjsr4` | Si et al. via Mendeley Data, DOI 10.17632/78ht3pjsr4.1 [10][11] | `CC-BY-4.0` | `attribution` | redistributable; we commit metrics only |
| [Tang & Werner mining footprint](dataset-cards/tang-werner-footprint.md) | `tang-werner-footprint` | Zenodo, DOI 10.5281/zenodo.7894216 [12] | `CC-BY-4.0` | `attribution` | redistributable |
| [Xu et al. 1985–2022, v3](dataset-cards/xu-mining-expansion.md) | `xu-expansion-v3` | Zenodo, DOI 10.5281/zenodo.17085099 [13][14] | `CC-BY-4.0` | `attribution` | redistributable |
| [Maus v2 polygons](dataset-cards/maus-polygons.md) (optional) | `maus-v2` | PANGAEA, DOI 10.1594/PANGAEA.942325 [15] | `CC-BY-SA-4.0` | `share-alike` | redistributable, share-alike |
| [ERA5 single levels](dataset-cards/era5-ghcnh.md) | `era5` | ECMWF / Copernicus Climate Change Service, DOI 10.24381/cds.adbb2d47 [16] | `CC-BY-4.0` (version as pinned at specification) | `attribution` | redistributable |
| [NOAA GHCNh, Salt Lake City](dataset-cards/era5-ghcnh.md) | `ghcnh` | NOAA NCEI, station `USW00024127` [17] | `LicenseRef-USGov-PD` (terms checked at specification) | `public-domain` | redistributable |
| [MineLib `marvin`](dataset-cards/minelib-marvin.md) (optional) | `minelib-marvin` | Espinoza et al., minelib.org [18][19] | `CC-BY-SA-3.0` | `share-alike` | **derived-only**, share-alike |
| [EPA AP-42 §13.2.2](dataset-cards/ap42.md) | `epa-ap42-13-2-2` | US EPA [20][21] | `LicenseRef-USGov-PD` | `public-domain` | cited parameters only |
| [Poly Haven / ambientCG](dataset-cards/textures-cc0.md) | `polyhaven`, `ambientcg` | Poly Haven [22]; ambientCG [23] | `CC0-1.0` | `open-no-attribution` | redistributable |
| [MakeHuman exports](dataset-cards/makehuman-people.md) | `makehuman-exports` | MakeHuman community, licence §C [24] | `CC0-1.0` (exports under §C) | `open-no-attribution` | raw exports stay local; our renders are published |
| Optional real probe | per file | per file (e.g. Wikimedia Commons) | per file: CC0 / CC BY / public domain | per file | aggregate metrics only |

### Size, access, what is committed, fallback

| Source | Size | Account needed? | Committed (derived only) | Fallback if unavailable |
|---|---|---|---|---|
| USGS 3DEP Bingham: 1 m DEMs 2013 / 2018 / 2023 + 69 LAZ tiles | DEM 5.0–257.4 MB per tile; LAZ 10–37 MB per tile [1] | no | derived tiles, meshes, volumes | none: this is the core site |
| McKinley Mine lidar 2023 | 4,975,347,484 points over 107.8 km² → AOI crop [3] | **OpenTopography API key** (optional maintainer act) | derived meshes and textures | Bingham-only scenes + CC0 textures |
| NRW Hambach DGM1 / LAZ | per tile (tile sizes UNVERIFIED — pinned at specification) | no | derived surfaces | none |
| EGMS over Hambach | per burst or 100 km tile [7] | **EGMS Explorer access** (optional, manual) | derived summaries | case C1 uses the de Wit series + synthetic creep only |
| de Wit slope failure | 8.9 MB `Data.zip` (+ optional 7.5 GB HDF5 companion) [9] | no | derived series | none |
| Mendeley rock fragments | 4,230,116,058 bytes, publisher SHA-256 [11] | no | **metrics only** | U-Net claim becomes synthetic-only, stated in the D1 card |
| Tang & Werner footprint | 296 MB shapefile [12] | no | masks | none |
| Xu et al. v3 | 32.8 MB zip [13] | no | expansion curves | none |
| Maus v2 polygons (optional) | 23.5 MB GeoPackage [15] | no | separate share-alike layer | Tang & Werner |
| ERA5 single levels | small per-site extract [16] | **Copernicus CDS account** (optional) | wind statistics | NOAA GHCNh hourly data for Salt Lake City |
| NOAA GHCNh | one station, hourly | no | wind statistics | ERA5 when the account exists |
| MineLib `marvin` (optional) | small text files [19] | no | derived shells and schedules, CC BY-SA | `oreblocks` synthetic deposits (the default) [25] |
| EPA AP-42 §13.2.2 | one PDF section [20] | no | cited table rows | none |
| Poly Haven / ambientCG | per asset | no | textures (e.g. WebP) | none |
| MakeHuman exports | per asset (local application ~325 MB) | no | our CC-BY renders only | procedural mannequins, stated in the B2 card |
| Optional real probe | ≤ 200 ground-level images | **6–10 maintainer labelling hours + a second labeller** | aggregate metrics only | equipment and people sim-to-real reported as "not measured" |

No account is ever needed by CI: every account-bound source runs in the local pipeline only, and its key is read from
an environment variable, never from the repository.

## Attribution texts

The attribution travels with every derivative: in the manifest entry, in the dataset card and in the web footer's
provenance list. The form is author or organisation, title, year, publisher or repository, DOI or URL, licence:

- **McKinley:** U.S. Office of Surface Mining Reclamation and Enforcement, *Lidar Survey of the McKinley Mine, NM
  2023*, distributed by OpenTopography, DOI 10.5069/G9BZ6486, CC BY 4.0 [3].
- **de Wit:** de Wit (2025), *Data used for the study of time-lapse velocity variations during an open-pit mine slope
  failure using seismic noise interferometry*, Zenodo, DOI 10.5281/zenodo.15003054, CC BY 4.0 [9].
- **Mendeley:** Si, Zhu, Di, Wang (2019), *Rock fragment image segmentation combining CNN and watershed algorithm*,
  Mendeley Data v1, DOI 10.17632/78ht3pjsr4.1, CC BY 4.0 [10].
- **Tang & Werner:** Tang and Werner (2023), global mining footprint, Zenodo, DOI 10.5281/zenodo.7894216, CC BY
  4.0 [12].
- **Xu et al.:** Xu et al., *Global surface mining and land reclamation of time series from 1985–2022*, v3, Zenodo,
  DOI 10.5281/zenodo.17085099, CC BY 4.0 [13][14].
- **ERA5:** Copernicus Climate Change Service, *ERA5 hourly data on single levels from 1940 to present*,
  DOI 10.24381/cds.adbb2d47 [16].
- **EGMS:** the source statement required by the Copernicus Land Monitoring Service data policy [8].
- **Share-alike layers:** Maus et al. (2022), DOI 10.1594/PANGAEA.942325, CC BY-SA 4.0 [15]; Espinoza, Goycoolea,
  Moreno and Newman, *MineLib*, DOI 10.1007/s10479-012-1258-3, CC BY-SA 3.0 [18][26].

Public-domain and CC0 sources need no attribution; PitStudio still cites them, because every external number needs a
source.

## Share-alike handling

CC BY-SA 3.0 and 4.0 require derivatives to carry the same licence. PitStudio keeps that contagion contained:

1. Share-alike sources are **optional**. The defaults are CC BY or synthetic: Tang & Werner instead of Maus, `oreblocks`
   instead of MineLib.
2. Anything derived from a share-alike source gets its **own manifest entry** with `licence_class: share-alike` and the
   original SPDX id. It is never merged into a CC BY layer, a combined tile set or a shared model input.
3. Raw MineLib instances are never re-hosted. A third-party record claims they are for "academic download only"
   without citing a source; the publisher's own page states CC BY-SA 3.0 [18], and that statement governs.

## NVIDIA material: reference-only

PitStudio names NVIDIA products nominatively. It is not affiliated with or endorsed by NVIDIA, and it never
redistributes NVIDIA binaries, assets, engines or caches.

- **Software and assets.** The Isaac Sim additional licence grants installation and use on systems with NVIDIA GPUs,
  forbids distributing "any portion of the Software" and contains no clause on outputs [27]. PitStudio therefore uses
  Isaac Sim, Kit, Replicator and ovrtx only in local environments, renders only its own procedural meshes with CC0
  materials and MakeHuman CC0 people, and never commits Isaac Sim or SimReady asset files.
- **Engines and weights.** TensorRT engines are device- and version-specific build products of NVIDIA software; Cosmos
  Reason 2 weights (BF16 and our own GGUF conversion) fall under the NVIDIA Open Model License. Both stay local, under
  git-ignored paths ([Export, parity and acceleration](../models/export-parity-acceleration.md)).
- **Performance data.** The NVIDIA Software License Agreement §8.9 forbids disclosing "the results of benchmarking,
  competitive analysis, regression or performance data" without written permission [28]; this covers Kit, Isaac Sim,
  Replicator and ovrtx. The TensorRT for RTX licence §2.13 contains the same kind of ban [29]. Their timings,
  throughput and GPU telemetry are therefore marked `performance: local-only` and never reach a committed file.
- **Regular TensorRT is different.** The TensorRT licence contains no benchmark, performance-data or
  competitive-analysis clause [30]. The bootstrap read the `LICENSE.txt` shipped in both TensorRT 11.3.0.99 wheels
  (47,141 bytes, SHA-256 `c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4`); the TensorRT probe pins
  that hash, and if the text ever changes the results drop to local-only until it is reviewed again. TensorRT numbers
  of **our own models** are therefore publishable.
- **Cosmos outputs.** NVIDIA claims no ownership of outputs, but distributing or "making available" a product that uses
  a Cosmos model requires the notice "Built on NVIDIA Cosmos", and using Cosmos outputs to train a model extends that
  duty to the model [31]. PitStudio's default is display-only: Cosmos answers and captions are shown with the notice
  and are never used to curate or train other models.

## Our own outputs

| Output | Licence | Where |
|---|---|---|
| Code | Apache-2.0 | whole repository |
| Docs, figures, diagrams | CC-BY-4.0 | `docs/`, web |
| Our USD scenes and synthetic data | CC-BY-4.0 | release assets, web |
| Trained weights | Apache-2.0 + attribution when all inputs permit; otherwise the most restrictive input terms | `models/onnx/`, release assets |
| Cosmos answers and captions | display-only, "Built on NVIDIA Cosmos" | web text |

## Excluded sources

These candidates were evaluated during source research and excluded; they are recorded so that nobody re-adds them by
accident.

| Candidate | Reason |
|---|---|
| AutoMine | unreachable from the build machine; licence unverified |
| MOCS construction images; Roboflow "mining-truck" | source unreachable; licence unverified |
| ACID; AIDCON; SH17 | non-commercial terms and/or gated, YouTube-sourced images [32][33] |
| MineCan | imagery sourced from Google Earth, whose terms a CC BY label cannot override [34] |
| Zenodo mirrors of Sketchfab / Objaverse models | licence not traced to the original model page |
| U-CARFnet images | the data-availability statement covers code only [35] |
| Isaac Sim / SimReady assets in published renders | proprietary, reference-only [27] |
| Open-Meteo free API as a primary source | non-commercial free tier [36] |

## Assumptions and limits

- **Licences can change.** Every manifest records the licence as read; the Cosmos, Isaac Sim and TensorRT texts are
  re-read whenever a tool version changes, and the TensorRT text is pinned by hash.
- **Some licence texts could not be parsed** during source research (Copernicus legal notices, the AP-42 PDF). Their
  exact clauses stay UNVERIFIED until they are read in full at specification; the derived-only class is used where
  doubt remains (EGMS).
- **The ERA5 licence version** is stated as "CC-BY" on the CDS page [16]; the exact version is pinned at download.
- **"Public domain" for US Government data** is the class used here; EPA's own disclaimer page adds a note on
  non-commercial, scientific and educational distribution of its documents [21]. PitStudio reproduces no EPA document,
  only cited equation constants.
- This page is not legal advice. It records what the publishers state and the conservative reading PitStudio applies.

## In PitStudio

- **Registry:** `data/sources.yaml` (schema `contracts/sources.schema.json`, written at specification), one entry per
  id above. Today the file holds an empty list and an example entry.
- **Download:** `s00_download` reads the registry, fetches with pooch and verifies SHA-256 ([Ingestion](ingestion.md)).
- **Guards:** CI checks that every committed artefact has a manifest entry with a licence class, that no file under a
  `reference-only` class is tracked, and that no metric marked `performance: local-only` appears in a committed file.
- **Status:** no source has been downloaded by the pipeline yet. The Mendeley archive was downloaded once during the
  bootstrap for a label-format check (see its card).

## References

1. U.S. Geological Survey, The National Map Access API, LPC and 1 m DEM queries for the Bingham Canyon area, accessed
   2026-10-02. https://tnmaccess.nationalmap.gov/api/v1/products?bbox=-112.17,40.50,-112.12,40.54&datasets=Lidar%20Point%20Cloud%20(LPC)&max=10
2. U.S. Geological Survey, *About 3DEP products and services*. https://www.usgs.gov/3d-elevation-program/about-3dep-products-services
3. OpenTopography, *Lidar Survey of the McKinley Mine, NM 2023*, OT.112024.6341.2, DOI 10.5069/G9BZ6486.
   https://portal.opentopography.org/datasetMetadata?otCollectionID=OT.112024.6341.2
4. Bezirksregierung Köln, Geobasis NRW, *3D-Messdaten*. https://www.bezreg-koeln.nrw.de/geobasis-nrw/produkte-und-dienste/hoehenmodelle/3d-messdaten
5. GovData, *Datenlizenz Deutschland – Zero – Version 2.0*. https://www.govdata.de/dl-de/zero-2-0
6. Copernicus Land Monitoring Service, *European Ground Motion Service*. https://land.copernicus.eu/en/products/european-ground-motion-service
7. Copernicus Land Monitoring Service, *EGMS Product Description v3*. https://library.land.copernicus.eu/products/European_Ground_Motion_Service_Product_Description_v3.html
8. Copernicus Land Monitoring Service, *Data policy*. https://land.copernicus.eu/en/data-policy
9. de Wit (2025), *Data used for the study of time-lapse velocity variations during an open-pit mine slope failure
   using seismic noise interferometry*, Zenodo, DOI 10.5281/zenodo.15003054. https://zenodo.org/api/records/15003054
10. Si, Zhu, Di, Wang (2019), *Rock fragment image segmentation combining CNN and watershed algorithm*, Mendeley Data
    v1, DOI 10.17632/78ht3pjsr4.1. https://data.mendeley.com/datasets/78ht3pjsr4/1
11. Mendeley Data public API, file listing of dataset 78ht3pjsr4 v1 (size, SHA-256). https://data.mendeley.com/public-api/datasets/78ht3pjsr4/files?folder_id=root&version=1
12. Tang and Werner (2023), global mining footprint, Zenodo, DOI 10.5281/zenodo.7894216. https://zenodo.org/api/records/7894216
13. Xu et al., global surface mining and land reclamation 1985–2022, v3, Zenodo, DOI 10.5281/zenodo.17085099.
    https://zenodo.org/api/records/17085099
14. Xu et al. (2026), *Earth System Science Data* 18, 6293. https://essd.copernicus.org/articles/18/6293/2026/
15. Maus et al. (2022), global-scale mining polygons v2, PANGAEA, DOI 10.1594/PANGAEA.942325; article DOI
    10.1038/s41597-022-01547-4. https://doi.pangaea.de/10.1594/PANGAEA.942325
16. Copernicus Climate Change Service, *ERA5 hourly data on single levels from 1940 to present*, DOI 10.24381/cds.adbb2d47.
    https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels
17. NOAA NCEI, *GHCNh station list* (station USW00024127, Salt Lake City Intl AP). https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh-station-list.txt
18. MineLib home page (licence statement). https://minelib.org/
19. MineLib instance pages, e.g. https://minelib.org/v1/kd.xhtml
20. U.S. EPA, *AP-42, Fifth Edition, Volume I, Chapter 13: Miscellaneous Sources* (§13.2.2 Unpaved Roads, final section
    November 2006). https://www.epa.gov/air-emissions-factors-and-quantification/ap-42-fifth-edition-volume-i-chapter-13-miscellaneous-0
21. U.S. EPA, *EPA disclaimers*. https://www.epa.gov/web-policies-and-procedures/epa-disclaimers
22. Poly Haven, *License*. https://polyhaven.com/license
23. ambientCG, *License*. https://docs.ambientcg.com/license/
24. MakeHuman community, *License* (sections A and C). http://www.makehumancommunity.org/content/license.html
25. `oreblocks` on PyPI. https://pypi.org/project/oreblocks/
26. Espinoza, Goycoolea, Moreno, Newman, MineLib: a library of open pit mining problems, *Annals of Operations
    Research* 206, DOI 10.1007/s10479-012-1258-3.
27. NVIDIA, *Isaac Sim Additional Software and Materials License*. https://docs.isaacsim.omniverse.nvidia.com/6.0.0/common/license-isaac-sim-additional.html
28. NVIDIA, *Software License Agreement* (§8.9). https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
29. NVIDIA, *TensorRT for RTX Software License Agreement* (§2.13). https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/reference/sla.html
30. NVIDIA, *TensorRT Software License Agreement*. https://docs.nvidia.com/deeplearning/tensorrt/latest/reference/sla.html
31. NVIDIA, *Open Model License* (§2.1, §3.1, §3.2). https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
32. ACID dataset terms. https://www.acidb.net/dataset
33. AIDCON dataset. https://www.ai2lab.org/aidcon/
34. MineCan benchmark record (imagery source). https://zenodo.org/api/records/18663545
35. U-CARFnet, *PLOS ONE* (2023), data-availability statement. https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0291115
36. Open-Meteo, *Terms*. https://open-meteo.com/en/terms

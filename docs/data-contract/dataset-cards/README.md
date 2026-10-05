# Dataset cards

> One datasheet per data source: what it holds, who published it, under which licence, how the pipeline fetches and
> checks it, and what PitStudio may publish from it. · Part of: [Data contract](../README.md) · Related:
> [Sources and licences](../sources-and-licences.md) · [Ingestion](../ingestion.md) · [Manifest](../manifest.md) ·
> [Pipeline stages](../../pipelines/pipeline-stages.md)

## What and why

PitStudio combines real public data (terrain, ground deformation, fragment images, weather, mining footprints,
emission factors) with synthetic data produced by its own studio. Each source has its own licence, access steps and
limits. A card states them **before** the pipeline downloads anything, so three questions always have a written
answer: which case needs this source, what may be committed or published from it, and what happens if it is not
available.

The cards follow the *datasheets for datasets* idea of Gebru et al. [1], adapted to a pipeline that never re-hosts
third-party data:

| Card section | Datasheet question it answers [1] |
|---|---|
| What and why | Motivation: which question or case the data serves, and why this source |
| Composition | What the files contain: products, epochs, counts, formats, coordinate systems, classes |
| Collection and provenance | Who collected and published it, how, which version was read and when |
| Licence and attribution | Distribution terms: SPDX id, licence class, redistribution class, attribution text |
| Size, checksums and access | Maintenance and access: size, checksum, account, programmatic path, fallback |
| Assumptions and limits | Known gaps, biases and UNVERIFIED items |
| In PitStudio | Uses: source id, stages, cases, methods, models, committed and never-committed artefacts, status |

## The cards

Licence classes and redistribution classes are defined in [Sources and licences](../sources-and-licences.md). Sizes
are the download sizes reported by the publisher; "per tile" or "per asset" means the size depends on the area or the
selection fixed at specification.

| Card | Source id | Licence class | SPDX | Size (download) | Account? | Committed artefact | Fallback if unavailable |
|---|---|---|---|---|---|---|---|
| [USGS 3DEP Bingham Canyon](bingham-3dep.md) | `usgs-3dep-bingham` | `public-domain` | `LicenseRef-USGov-PD` | DEM 5.0–257.4 MB per epoch; 69 LAZ tiles of 10–37 MB | no | derived tiles, meshes, volumes | none (core site) |
| [McKinley Mine lidar 2023](mckinley-lidar.md) | `ot-mckinley-2023` | `attribution` | `CC-BY-4.0` | ~5 × 10⁹ points; area-of-interest crop | OpenTopography key (optional) | derived meshes and textures | Bingham-only scenes + CC0 textures |
| [NRW Hambach lidar and DGM1](hambach-nrw.md) | `nrw-hambach-dgm1` | `open-no-attribution` | `DL-DE-ZERO-2.0` | per tile | no | derived terrain | none |
| [EGMS over Hambach](egms-hambach.md) | `egms-hambach` | `attribution` (derived-only) | project reference to the CLMS policy | per burst or 100 km tile | EGMS Explorer (optional, manual) | derived summaries | C1 uses de Wit + synthetic only |
| [de Wit open-pit slope failure](dewit-slope-failure.md) | `dewit-slope-failure` | `attribution` | `CC-BY-4.0` | 8.9 MB (+ optional 7.5 GB HDF5) | no | derived series | none |
| [Mendeley rock fragments](mendeley-rock-fragments.md) | `mendeley-78ht3pjsr4` | `attribution` | `CC-BY-4.0` | 4.23 GB (SHA-256 published) | no | metrics only | synthetic-only U-Net claim |
| [Tang & Werner mining footprint](tang-werner-footprint.md) | `tang-werner-footprint` | `attribution` | `CC-BY-4.0` | 296 MB | no | masks | none |
| [Xu et al. surface mining 1985–2022](xu-mining-expansion.md) | `xu-expansion-v3` | `attribution` | `CC-BY-4.0` | 32.8 MB | no | expansion curves | none |
| [Maus et al. mining polygons v2](maus-polygons.md) (optional) | `maus-v2` | `share-alike` | `CC-BY-SA-4.0` | 23.5 MB | no | separate share-alike layer | Tang & Werner |
| [ERA5 and GHCNh wind](era5-ghcnh.md) | `era5`, `ghcnh` | `attribution` / `public-domain` | `CC-BY-4.0` / `LicenseRef-USGov-PD` | small (one site) | CDS account for ERA5 (optional) | wind statistics | GHCNh hourly station data (Salt Lake City) |
| [MineLib marvin](minelib-marvin.md) (optional) | `minelib-marvin` | `share-alike` | `CC-BY-SA-3.0` | small | no | derived-only, CC BY-SA | `oreblocks` synthetic deposits (default) |
| [EPA AP-42 §13.2.2](ap42.md) | `epa-ap42-13-2-2` | `public-domain` | `LicenseRef-USGov-PD` | one PDF | no | cited table rows | none |
| [Poly Haven and ambientCG textures](textures-cc0.md) | `polyhaven`, `ambientcg` | `open-no-attribution` | `CC0-1.0` | per asset | no | textures | none |
| [MakeHuman people exports](makehuman-people.md) | `makehuman-exports` | `open-no-attribution` | `CC0-1.0` (licence §C) | per asset | no | our CC-BY renders only | procedural mannequins |
| [Synthetic data](synthetic-data.md) | studio synthetic sources | `own` | `CC-BY-4.0` | ~30k images + tables and fields | no | baked samples, shards and metrics | NVIDIA-runtime sets end as "not run"; open-lane generators always run |

![Sources grouped by licence class and what is committed](../../assets/diagrams/data-sources-licences.svg)

*Every source sits in exactly one licence class; the class decides what may be committed, published or only used
locally.*

## Rules every card applies

- **Licence traced to the original publisher**, never to a mirror's label. Where the publisher shows two conflicting
  statements, the card records both and the source becomes `derived-only`.
- **Raw third-party data is never committed.** `s00_download` fetches it with pooch into `PITSTUDIO_DATA` (default:
  a git-ignored folder in the repo) and checks a SHA-256. Where the publisher gives an MD5 or no checksum at all, the
  SHA-256 is pinned at first download; a later mismatch fails the stage.
- **Share-alike layers** (Maus, MineLib) are always separate manifest entries and are never merged with CC BY
  layers.
- **Every committed artefact** carries its `licence_class`, the source ids it derives from and the attribution text
  in the [manifest](../manifest.md).
- **Optional accounts are off by default.** OpenTopography, Copernicus CDS and EGMS need a maintainer act (see
  [Maintainer acts and licences](../../studio/owner-acts-and-licences.md)); without it the stated fallback is used.
- **UNVERIFIED** marks a fact that could not be read on its primary page. It is pinned at specification or left out
  of every calculation.

## Status

No source has been downloaded by the pipeline yet; `s00_download` runs in the data-and-models phase. The one
exception is the Mendeley fragment archive: it was downloaded and checked during bootstrap, a **data check** whose
counts and split rules are on its [card](mendeley-rock-fragments.md). Nothing was trained on it.

## References

1. Gebru, T., Morgenstern, J., Vecchione, B., Wortman Vaughan, J., Wallach, H., Daumé III, H., Crawford, K.
   "Datasheets for Datasets", 2018 (v8, 2021). https://arxiv.org/abs/1803.09010

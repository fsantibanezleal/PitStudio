# Ingestion

> How a source enters PitStudio: a registry entry in `data/sources.yaml`, a download pinned by SHA-256, and schemas that
> reject bad data instead of repairing it. · Part of: [Data contract](README.md) · Related:
> [Sources and licences](sources-and-licences.md) · [Manifest](manifest.md) ·
> [Pipeline stages](../pipelines/pipeline-stages.md) · [Dataset cards](dataset-cards/README.md)

## What and why

Every number PitStudio shows depends on data it did not create. Ingestion is the boundary where that data is pinned
(same bytes every time), described (licence, units, ranges) and checked. The rule for the boundary is short:
**reject, never coerce.** A value of the wrong type, a value outside its physical range or a file whose hash does not
match stops the stage with a report. Nothing is cast, clipped, imputed or "fixed" on the way in, because a silent
repair would make every later result depend on a choice nobody reviewed.

## The source registry: `data/sources.yaml`

The registry lists every real or synthetic source the pipeline uses. Its fields are those of the example entry already
committed in the file; `contracts/sources.schema.json` (written at specification) makes them normative.

| Field | Type | Meaning | Example |
|---|---|---|---|
| `id` | string, kebab-case | stable source id used by recipes and manifests | `mendeley-78ht3pjsr4` |
| `kind` | `real` \| `synthetic` | origin of the data | `real` |
| `title` | string | publisher's title | "Rock fragment image segmentation …" |
| `landing_url` | URL | the original publisher's page, preferably a DOI | `https://doi.org/10.17632/78ht3pjsr4.1` |
| `files[]` | list | one entry per downloaded file | — |
| `files[].url` | URL | direct download URL | publisher file URL |
| `files[].sha256` | 64 hex chars | pinned digest, checked on every download | `7f4336a4…f402d` |
| `files[].bytes` | integer | expected size in bytes | `4230116058` |
| `license` | SPDX id | licence as stated by the original publisher | `CC-BY-4.0` |
| `license_url` | URL | where that licence statement was read | dataset landing page |
| `attribution` | string | text that travels with every derivative | author, title, year, DOI, licence |
| `redistribution` | `redistributable` \| `derived-only` \| `no-redistribution` | what may leave the machine | `redistributable` |
| `citation` | string | full citation for docs and the web bibliography | — |
| `card` | path | the dataset card | `data/cards/<id>.md` |

Rules the schema enforces:

- every `id` is unique, and every manifest input refers to an existing `id`;
- every `files[]` entry carries a `sha256` before the source is used in a published run;
- share-alike sources (`CC-BY-SA-3.0`, `CC-BY-SA-4.0`) are separate entries, never merged with CC BY entries
  ([Sources and licences](sources-and-licences.md));
- account-bound sources store **no credential**; keys come from environment variables on the maintainer's machine.

## Download: `s00_download` with pooch and SHA-256

`s00_download` (pipeline environment, pooch 1.9.0 in `pipeline/uv.lock`) walks the registry and fetches each file.

1. **Pinned hash.** pooch checks every file against a known hash. The algorithm can be named as a prefix
   (`"sha256:…"`, `"md5:…"`), and SHA-256 is the default when no prefix is given [1]. PitStudio always stores SHA-256.
2. **Mismatch stops the stage.** When a downloaded or cached file does not match its registry hash, pooch raises an
   exception "to warn of possible file corruption" [1]. The stage fails; it never continues with unverified bytes.
3. **No published checksum.** USGS 3DEP, OpenTopography, PANGAEA and MineLib publish no checksum for the files used
   here [2]. The first download computes the SHA-256, the maintainer reviews it, and the digest is committed to the
   registry. Where Zenodo publishes MD5 (de Wit, Tang & Werner, Xu et al.), the first download is checked against it
   before its SHA-256 is pinned.
4. **Large files.** Hashes of multi-GB archives use `hashlib.file_digest`, which "may bypass Python's I/O" and read
   the file descriptor directly [3]. Example: the Mendeley archive is 4,230,116,058 bytes; its publisher SHA-256
   `7f4336a4fe1f83e3c828eed4c73e036d7694f94076b6f040e6211315693f402d` was matched on the local copy during the
   bootstrap.
5. **Where files go.** Raw files land under `PITSTUDIO_DATA` (default: the git-ignored `data/raw/` and
   `data/external/` folders of the repo). Synthetic, interim and processed data use the git-ignored `data/synthetic/`,
   `data/interim/` and `data/processed/` folders. Scratch files go to `PITSTUDIO_TMP`. Nothing under these folders is
   ever committed.

## Schemas: pandera, "reject, never coerce"

Every tabular input is validated by a pandera schema (pandera 0.33.1, `pipeline/uv.lock`) in `s10_preprocess`, before
any computation uses it. pandera validates pandas and Polars data frames with the same schema API [4]; the pipeline
works in Polars.

| Schema setting | PitStudio value | Effect |
|---|---|---|
| column dtype | declared for every column | a value of another type fails |
| `coerce` | `False` | types are never converted on the way in |
| `strict` | `True` | an unexpected column fails |
| `nullable` | `False` unless declared | a missing value fails |
| range checks | physical bounds, per column, in the column's unit | a value outside the bounds fails |
| `lazy` | `True` | every rule runs before the error is raised, and violations are grouped into one `SchemaErrors` report [4] |
| metadata | unit (SI), source id, citation of the bound | units and bounds are documented in the schema itself |

An illustrative schema (the real ones are written in the build phase):

```python
import pandera.polars as pa
import polars as pl

wind_hourly = pa.DataFrameSchema(
    {
        "time_utc": pa.Column(pl.Datetime("us", "UTC"), unique=True),
        "wind_dir_deg": pa.Column(pl.Float64, pa.Check.in_range(0.0, 360.0)),  # unit: degrees from north
        "wind_speed_m_s": pa.Column(pl.Float64, pa.Check.ge(0.0)),  # unit: m/s
    },
    coerce=False,  # reject, never coerce
    strict=True,  # no unexpected columns
)
# wind_hourly.validate(frame, lazy=True)  -> raises SchemaErrors listing every failing row and rule
```

Non-tabular inputs get file-level validators with the same "reject" semantics:

| Input type | Checked properties (examples) |
|---|---|
| Rasters (DEM GeoTIFF) | CRS, resolution in metres, dtype, nodata value, extent inside the declared area of interest |
| Point clouds (LAZ) | CRS, point count > 0, classification codes present, bounds inside the area of interest |
| Images and masks (Mendeley) | 512 × 512 RGB images; indexed masks with 0 = background and *k* = instance *k*; one mask per image |
| Vector layers (polygons) | geometry validity, CRS, required attribute columns |
| Synthetic outputs | the same schema as the real data of the same type, plus the generator manifest |

## Outlier policy

The ingestion contract distinguishes three cases:

1. **Physically impossible or malformed values** (negative wind speed, a direction above 360°, a mask index with no
   label, a DEM cell outside the declared nodata convention): the file is **rejected**. The report names the file, the
   row or pixel, the column, the value and the rule. The source entry or the parser is then fixed explicitly and the
   fix is reviewed; the data is never patched in place.
2. **Values that are physically possible but unusual** (a gust, a steep wall, a very large rock): they are data. The
   ingestion contract never removes them.
3. **Deliberate exclusions** that a method needs (for example, an epoch outside the area of interest): they are
   declared rules in the stage's recipe parameters, so they enter the cache key, and the manifest records each rule
   and how many records it removed.

Unit conversions (feet to metres, mm to m) happen in explicit, tested code after validation, never inside a schema.

## Splits are fixed at ingestion

Leakage is a data problem, so split groups are defined when the data enters, not when a model is trained. The
Mendeley set is the clearest case: its 960 images are 240 originals plus 3 flips or rotations of each, and 9 visually
similar pairs of originals are merged conservatively (there is no pixel-level overlap), which leaves 231 source
groups. Splitting by file would put flipped copies of test tiles into
training; PitStudio splits by source group and evaluates on originals only
([dataset card](dataset-cards/mendeley-rock-fragments.md)). Synthetic data uses the scenario seed, pit layout or shift
as its group key ([synthetic data](dataset-cards/synthetic-data.md)).

## Assumptions and limits

- Range bounds are physical limits with a cited source, not statistical fences; choosing them is part of the
  specification of each schema, and an UNVERIFIED bound is flagged as such.
- pooch protects integrity, not provenance: a publisher that silently replaces a file changes its hash, which stops
  the stage; it is then the maintainer's decision to re-pin after reading the new version.
- Account-bound downloads (OpenTopography, Copernicus CDS, EGMS Explorer) cannot run in CI. CI runs the pipeline on
  CPU with the tiny licence-cleared samples in `data/samples/` only.

## In PitStudio

- **Stages:** `s00_download` (registry → raw files), `s10_preprocess` (schemas, area-of-interest crops, grids, split
  groups). See [Pipeline stages](../pipelines/pipeline-stages.md).
- **Tests:** contract tests check `data/sources.yaml` against its schema; schema tests feed each pandera schema
  hostile inputs (wrong dtype, out-of-range, extra column, nulls) and expect a rejection, never a repaired frame.
- **Status:** the registry holds no entries yet; schemas are written in the build phase. The pipeline environment
  installs today, and its CPU tests run in CI:

```bash run
uv sync --project pipeline --extra cpu --all-groups --locked
```

Once the build phase adds the runner and the stages, a single source is fetched through the runner:

```bash run deferred=P6
uv run --extra runner studio plan studio/recipes/cases/<case>.yaml
uv run --extra runner studio run studio/recipes/cases/<case>.yaml --stage s00_download
```

## References

1. Pooch documentation, *Hashes: calculating and bypassing*. https://www.fatiando.org/pooch/latest/hashes.html
2. Source survey of landing pages and repository APIs (checksum availability per source): USGS TNM Access API
   https://tnmaccess.nationalmap.gov/api/v1/products ; OpenTopography https://portal.opentopography.org/datasetMetadata?otCollectionID=OT.112024.6341.2 ;
   PANGAEA https://doi.pangaea.de/10.1594/PANGAEA.942325 ; Zenodo record APIs, e.g. https://zenodo.org/api/records/15003054
3. Python 3.14 documentation, `hashlib.file_digest`. https://docs.python.org/3.14/library/hashlib.html
4. pandera documentation (lazy validation, `SchemaErrors`, supported data-frame libraries including Polars).
   https://pandera.readthedocs.io/en/stable/

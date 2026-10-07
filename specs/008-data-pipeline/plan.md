# Plan 008 — Data pipeline, stages s00–s20
Spec: ./spec.md

## Summary

1. **`s00_download`** validates the registry (FR-008-01, FR-008-02). It fetches files with pooch, using a resumable
   httpx downloader, into git-ignored data roots. It verifies each file by streaming SHA-256 and quarantines mismatches
   (FR-008-05, FR-008-06). It applies pin, licence, oversize, path, retry, account, fallback and offline rules
   (FR-008-07 … FR-008-17).
2. **The archive extractor** unpacks only allowed members, under a size cap (FR-008-18, FR-008-19).
3. **`s10_preprocess`**:
   - validates with pandera (Polars) and file-level validators, rejecting and never coercing, and writes one report
     (FR-008-20 … FR-008-24);
   - converts units explicitly after validation (FR-008-25) and checks the site name (FR-008-26);
   - fixes splits at ingestion: the Mendeley 231 groups and 5 × 48 grouped folds (FR-008-27 … FR-008-31).
4. **`s05_synthesize`** runs the CPU generators and collects studio outputs by digest. Every set is labelled and goes
   through the real-data validators. Each set gets one validation class, and the honesty rule is enforced at the
   data-card writer (FR-008-32 … FR-008-38).
5. **`s20_feature_extraction`** computes causal window features and pinned DINOv2 ViT-S/14 embeddings, with transforms
   fitted on training groups only (FR-008-39 … FR-008-42). Data cards and samples are checked in CI
   (FR-008-43 … FR-008-45).

## Technical context

- **Runtime:** Python 3.14, `pipeline/` environment. Already locked: pooch 1.9.0, pandera 0.33.1, polars, pyarrow,
  zarr, httpx, duckdb, scikit-learn, torch (cpu/cu126/cu130 extras), `minephys`, `minehaulsim`, `oreblocks`. The root
  environment (jsonschema) runs the contract and card checks.
- **Dependencies to choose, add and lock before feature code** (T-008-002; per the dependency-validation rule: research
  the best tool, resolve with `uv add`, prove it on Windows/Python 3.14 wheels, record the licence):

  | Need | Candidates |
  |---|---|
  | 7z extraction | `py7zr` (LGPL-2.1-or-later, used unmodified) |
  | GeoTIFF tags and CRS | `tifffile` + `pyproj`, or `rasterio` |
  | LAZ headers | `laspy` with `lazrs` |
  | Vector layers | `pyogrio` + `shapely` |
  | DINOv2 loader | `transformers` at a pinned revision, or `torch.hub` |

- **Targets:** local CPU (all stages); GPU only for embeddings, under `gpu0.compute`. CI runs on CPU with
  `data/samples/` only and no network (FR-008-16).
- **Locations:** `pitstudio_pipeline.{download, archive, ingest, splits, synthesize, features, cards}`; schemas in
  `contracts/`; split files in `data/splits/`; pin proposals in `data/pins/`; cards in `data/cards/`.

## Constitution check

| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | yes | Real sources come through the real pipeline with pinned bytes. Synthetic data is labelled, uses the real formats and loaders (FR-008-34), and is validated against real data only where real data of the same type exists (FR-008-36). |
| Spec before code | yes | Every module below maps to requirement ids. The open points of the docs are resolved in spec §8: link identities, fold design, registry fields, 7z, embedding variant. |
| Acceptance-test-first | yes | Every task is a `[red]`/`[green]` pair with its own test files, locked after `[red]`. |
| Independent oracles | yes | FIPS 180-2 SHA-256 example + `hashlib` (P-008-01); hand-calculated groups and folds (P-008-06, P-008-07); exact transform identities (FR-008-29); the dataset card's counts (SC-008-01); the NCEI GHCNh documentation for the wind schema; definition constants for unit conversions (FR-008-25). |
| Determinism & explicit tolerances | yes | `bitwise` for s00, s10, s05 (CPU) and s20 (CPU); `statistical` for GPU embeddings (cosine ≥ 0.999). Tolerances below. |
| Neutral contracts | yes | DC-008-02 … DC-008-05 are JSON Schema 2020-12 with generated types (T-008-001); the registry schema is spec 001's (DC-001-04). |
| Static delivery | n/a | No web runtime here; only metrics and small derived artefacts leave the machine (FR-008-45). |
| Honesty | yes | Validation classes and the exact label (FR-008-36); the refusal to attach C2ST/TSTR verdicts (FR-008-37); "not-run" instead of substitutes (FR-008-14, FR-008-35); a provisional site name until confirmed (FR-008-26). |
| Licence hygiene | yes | SPDX allow-list and classes (spec 001, enforced by FR-008-02); share-alike outputs kept separate (FR-008-04); raw data never committed (FR-008-15, NFR-008-03); Mendeley publishes metrics only (FR-008-45); credentials never written (FR-008-13). |
| Simplicity | yes | pooch is used directly; the only additions are a resumable downloader (pooch has no resume) and an extractor guard (pooch cannot unpack 7z, and its zip/tar processors do not cap sizes). |

## Design

Diagrams: `docs/assets/diagrams/pipeline-stages.svg`, `docs/assets/diagrams/data-sources-licences.svg`,
`docs/assets/diagrams/synthetic-data-validation.svg`, `docs/assets/diagrams/case-d1-tstr-design.svg`.

| Component | Responsibility | Requirements |
|---|---|---|
| Registry loader (`download.registry`) | Validation against spec 001's `sources.schema.json` and source-registry checks; whole-registry rejection | FR-008-01, FR-008-02 |
| Share-alike guard (`download.licence`) | Share-alike merge refusal, using spec 001's `licence_class_of` | FR-008-04 |
| Fetcher (`download.fetch`) | pooch registry + a custom httpx downloader (Range resume, size cap, HTTPS-only redirects, backoff); streaming digest; `.part` → promote or quarantine; fetch records | FR-008-05, FR-008-06, FR-008-10 … FR-008-12, FR-008-17, P-008-01, P-008-02 |
| Pin gate (`download.pins`) | `--pin` proposals in `data/pins/`, publisher checksum, `UnpinnedSource` | FR-008-07, FR-008-08 |
| Access and fallback (`download.access`) | `account.env_var`, manual `external/` sources, the fallback chain, marking consumers `not-run`, offline mode, data-root guard | FR-008-13 … FR-008-16, NFR-008-02 |
| Extractor (`archive`) | Member listing; path, link and size checks; streaming size cap; atomic extraction into a temporary folder, then rename | FR-008-18, FR-008-19, P-008-05, NFR-008-01 |
| Tabular schemas (`ingest.schemas`) | One pandera (Polars) schema per tabular source (`ghcnh`, `era5`, `dewit-slope-failure`, `egms-hambach`, `xu-expansion-v3`); bounds carry unit + citation metadata | FR-008-20, FR-008-21, P-008-03 |
| Outlier and exclusion rules (`ingest.rules`) | Declared recipe rules only (area-of-interest crops, epochs); counts into the manifest | FR-008-22, P-008-04 |
| File validators (`ingest.files`) | Raster, point-cloud, vector, image/mask validators; reports | FR-008-23, FR-008-24 |
| Units (`ingest.units`) | Definition-exact conversions after validation; typed errors | FR-008-25, FR-008-46, P-008-11 |
| Site check (`ingest.site`) | Bingham area of interest ∩ footprint pit polygons; provisional label | FR-008-26 |
| Splits (`splits`) | Group keys per dataset; Mendeley union-find over the 9 links; the augmentation-structure check; seeded greedy grouped folds; split file with membership SHA-256; consumer-side integrity check | FR-008-27 … FR-008-31, FR-008-47, P-008-06 … P-008-08, SC-008-01, DC-008-04 |
| Synthesis (`synthesize`) | Generator registry (DES via the spec 007 adapter, `minephys` generators, `oreblocks`); studio-output collector with digest checks; `synthetic: true`; validators shared with real data | FR-008-32 … FR-008-35, FR-008-38, P-008-09 |
| Cards (`cards`) | Front-matter writer and checker; validation classes; honesty guard | FR-008-33, FR-008-36, FR-008-37, FR-008-43, FR-008-44, DC-008-05 |
| Features (`features`) | Causal windows; DINOv2 ViT-S/14 with one shared preprocessing function; transforms fitted on training groups; input checks | FR-008-39 … FR-008-42, FR-008-48, P-008-10 |
| Samples hygiene (CI check) | `data/samples/` licence classes, no Mendeley pixels, sizes; `git ls-files` scan of the data roots | FR-008-45, NFR-008-03 |

## Test strategy

Network is never used in tests: transfers go through `httpx.MockTransport`, which serves fixed bytes, Range responses,
redirects, oversize bodies and failures.

| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-008-01, FR-008-02 | contract | hand-built registries, one violation each (classes from spec 001's hostile corpus); nothing downloaded | pytest + jsonschema |
| FR-008-04 | pipeline | the class table of spec 001 data-model §5.2; hand-built share-alike + attribution input pairs | pytest |
| FR-008-05, FR-008-06, FR-008-17, P-008-01 | pipeline | `hashlib.sha256` (reference); FIPS 180-2 "abc" vector; fixture bytes with known digests | pytest, Hypothesis |
| FR-008-07, FR-008-08 | pipeline | fixture MD5/SHA-256 pairs computed with `hashlib` in the test | pytest |
| FR-008-10, FR-008-11, FR-008-15 | pipeline | hostile transports and names; a temporary repository tree | pytest |
| FR-008-12, P-008-02, NFR-008-02 | pipeline | the uninterrupted transfer's bytes; a transport that fails on any request | pytest, Hypothesis |
| FR-008-13, FR-008-14, FR-008-16 | pipeline | a sentinel key string searched for in every output; the fallback table of spec §7 | pytest |
| FR-008-18, FR-008-19, P-008-05 | pipeline | hand-built hostile archives (zip, tar, 7z) | pytest, Hypothesis |
| NFR-008-01 | pipeline (slow, local only) | the 1 GB bound, measured with psutil | pytest `-m slow` |
| FR-008-20, FR-008-21, P-008-03 | pipeline | generated valid frames compared with themselves; injected violations | pytest, Hypothesis |
| FR-008-22, P-008-04 | pipeline | rows at the bounds; declared crops with hand-counted removals | pytest, Hypothesis |
| FR-008-23, FR-008-24 | pipeline | synthetic GeoTIFF / LAZ / GeoPackage / PNG fixtures with known properties | pytest |
| FR-008-25, P-008-11 | pipeline | definition constants (0.3048 m/ft, 3.785411784 L/gal) | pytest, Hypothesis |
| FR-008-46 | pipeline | non-finite values and unknown pairs | pytest |
| FR-008-47 | pipeline | split files with one tampering each (digest, duplicate test record, train/test overlap, schema) | pytest |
| FR-008-48 | pipeline | hand-built hostile series (unordered, NaN, too short) and images (undecodable, 1 or 4 channels, 8 px side) | pytest |
| FR-008-26 | pipeline | hand-drawn polygons inside and outside the box | pytest |
| FR-008-27, FR-008-28, P-008-06, P-008-08 | pipeline | hand calculation (231 groups, the listed components) | pytest, Hypothesis |
| FR-008-29, SC-008-01 | pipeline | exact flip/rotation identities on generated masks (CI); the card's counts on the real archive (local) | pytest |
| FR-008-30, P-008-07 | pipeline | hand calculation (48 per fold; group counts 45, 46, 46, 47, 47) | pytest, Hypothesis |
| FR-008-31 | pipeline | the group-key table of FR-008-31 | pytest |
| FR-008-32, FR-008-35, FR-008-38, P-008-09 | pipeline | double-run SHA-256 equality; missing or tampered studio fixtures | pytest |
| FR-008-33, FR-008-34 | pipeline | the real-data validators applied to synthetic fixtures | pytest |
| FR-008-36, FR-008-37 | pipeline | the class table of FR-008-36; the exact label string | pytest |
| FR-008-39, FR-008-42, P-008-10 | pipeline | hand-computed windows on short series; invariants | pytest, Hypothesis |
| FR-008-40, FR-008-41 | pipeline (CPU) + gpu | CPU embedding of a fixed image, twice (bitwise); CPU vs GPU cosine; a tampered weights digest | pytest (`gpu` marker for the GPU half) |
| FR-008-43, FR-008-44 | contract | registry ↔ card field equality | pytest + jsonschema |
| FR-008-45, NFR-008-03 | contract | `git ls-files` listing; sample cards | pytest |
| DC-008-02 … DC-008-05 | contract | JSON Schema 2020-12 meta-schema; round-trip of the generated types; one hostile document per schema | pytest + jsonschema |

### Metamorphic relations per numerical core (≥ 3 each)

| Core | Relations |
|---|---|
| Streaming digest + resume | chunking invariance, resume-offset invariance, 200-restart equivalence (P-008-01, P-008-02) |
| Splits | input-order invariance, link-order invariance, redundant-link invariance (P-008-08) |
| Window features | causality, translation equivariance, linear scaling (P-008-10) |
| Unit conversions | round trip, composition, linearity (P-008-11) |

### Tolerances and their justification

| Quantity | Tolerance | Justification |
|---|---|---|
| Digests, split files, CPU generator outputs, CPU embeddings, fetch and ingestion decisions | exact | Deterministic integer or byte operations, or fixed CPU kernels with fixed seeds; anything weaker would hide drift. |
| Unit conversions | 1 ulp | One float64 multiplication or division per step, correctly rounded. |
| Scaled window features | rtol 1e-12 | ≤ 10⁴ sequential float64 operations per window. |
| CPU vs GPU embeddings | cosine ≥ 0.999 | fp32 with TF32 disabled; kernel ordering differs between devices. A cosine of 0.999 is far below the distances a two-sample test separates (`statistical` class). |
| s00 peak memory | ≤ 1 GB | Streaming hashing and extraction use buffers of ≤ 64 MB; 1 GB leaves room for the interpreter, polars and py7zr's dictionary. |

## Risks and complexity tracking

| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Custom resumable downloader inside pooch | A 4.23 GB archive over an unstable link | pooch's default downloader restarts from 0 after a failure |
| Own extractor guard | 7z support plus path and size safety | pooch's processors do not unpack 7z and do not cap sizes |
| Registry fields defined in the spec 001 schema | The fallback, account and extract rules need fields | A second registry file or schema would split one source of truth |
| Fixed link list for Mendeley | Reproducible, reviewable groups | Recomputing similarity at ingestion would make the groups depend on an image-similarity threshold and its library version |
| One embedding variant (ViT-S/14) | Smallest pinned backbone, enough for two-sample tests | Larger variants cost VRAM and time with no evaluation benefit shown |
| Real-archive tests run locally only (`slow`) | CI never holds the 4.23 GB archive or any Mendeley pixel | Synthetic fixtures cover the same code paths in CI |

# Spec 008 — Data pipeline, stages s00–s20
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent

Every number PitStudio shows depends on data it did not create, or on synthetic data it must label honestly. This spec
covers the first four stages of the frozen pipeline lane (`pipeline/`, Python 3.14), where that data enters:

| Stage | What it does |
|---|---|
| `s00_download` | Fetches every source in `data/sources.yaml` with pooch, pinned by SHA-256, with the licence traced to the original publisher. Raw data is never committed. Each optional or account-bound source has a declared fallback. |
| `s05_synthesize` | Produces the synthetic sources, labelled, in the same formats and through the same loaders as real data, and collects the studio's GPU outputs by digest. |
| `s10_preprocess` | Validates every input ("reject, never coerce"), applies the outlier policy, crops to declared areas of interest and fixes the split groups at ingestion. |
| `s20_feature_extraction` | Computes causal window features and frozen image embeddings. |

The spec also fixes:
- the honesty rule for synthetic data (FR-000-09);
- the data cards;
- the Mendeley fragment split: 240 originals; 9 conservative similarity links giving 231 groups; grouped 5-fold; test
  folds on originals only.

That split feeds SC-000-01.

Who benefits: the maintainer, who gets one reproducible fetch-and-check path; data/AI practitioners, who get
leakage-free splits and honest labels; reviewers, who get a licence record for every byte.

Out of scope:
- training, inference, evaluation and export (`s30`–`s64`; specs 009–017);
- terrain meshes and USD (`st10_terrain`, spec 004);
- the schemas of `manifest`, `recipe`, `tools` and `sources` (spec 001; this spec consumes the source-registry schema);
- the runner's cache, locks and retries (spec 002), which these stages use.

## 2. User stories

| ID | Priority | Story (short) |
|---|---|---|
| US-008-1 | P1 | One command fetches every source, verified, licence-traced, never committed, with fallbacks |
| US-008-2 | P1 | Ingestion rejects bad data with a full report and keeps real outliers |
| US-008-3 | P1 | Splits fixed at ingestion by source group, so no evaluation leaks |
| US-008-4 | P1 | Every synthetic set labelled, same format and loader as real data, with a data card and a verdict or the honesty label |
| US-008-5 | P2 | Preprocessing and features reproducible bit for bit on CPU, with manifests |

### US-008-1 (P1) Verified, licence-traced fetch
As the maintainer, I want one command to fetch every registered source, verify it against a pinned SHA-256, refuse
unlicensed or unpinned data, and fall back honestly when an optional source or account is missing, so that every run
starts from the same bytes. Independent test: with a mocked transport, a tampered file stops the stage and leaves
nothing promoted.

### US-008-2 (P1) Reject, never coerce
As a data/AI practitioner, I want every input validated against a declared schema that rejects (and never repairs)
bad values with a report naming the file, row, column, value and rule, while physically possible extremes stay in the
data, so that no result depends on a silent fix. Independent test: a frame with one injected violation raises a report
naming that cell, and a valid frame comes back unchanged.

### US-008-3 (P1) Leakage-free splits fixed at ingestion
As a practitioner, I want the Mendeley fragment images split by source group into 5 folds of exactly 48 originals,
with tests on originals only and no flipped copy of a test tile in training, so that TSTR and TRTR are honest.
Independent test: the split file reproduces the hand-calculated 231 groups and 5 × 48 originals.

### US-008-4 (P1) Honest synthetic data
As a reviewer, I want every synthetic set flagged, in the real format, loaded by the real loader, and carrying either
a validation verdict against real data of the same type or the label "calibrated synthetic — not validated against
real data", so that nothing is presented as more than it is. Independent test: attaching a C2ST verdict to a DES-cycle
set is refused.

### US-008-5 (P2) Reproducible preprocessing and features
As a developer, I want s05 (CPU generators), s10 and s20 (CPU) to give byte-identical outputs for the same inputs and
seeds, recorded in manifests, so that a published artefact can be rebuilt. Independent test: two runs give equal
SHA-256 for every output.

## 3. Functional requirements (EARS)

All modules live in the `pipeline/` environment (package `pitstudio_pipeline`): `download`, `archive`, `ingest`,
`splits`, `synthesize`, `features`, `cards`.

**Registry and licences**

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-008-01 | Ubiquitous | `s00_download` shall read its sources only from `data/sources.yaml` and shall validate the whole registry against `contracts/sources.schema.json` (DC-001-04, owned by spec 001-contracts, whose data-model §5 defines every registry field this spec reads) before it opens any connection. | contract |
| FR-008-02 | Unwanted | If the registry fails validation against `contracts/sources.schema.json` or the source-registry checks of spec 001 (its hostile entry classes: duplicate ids, SPDX ids outside the allowlist, missing licence fields, non-HTTPS URLs, malformed digests, out-of-range sizes, mixed share-alike files, unknown fallback ids, credential-like values), then `s00_download` shall reject the whole registry with `RegistryError` listing every violation (entry id, JSON pointer, rule), and shall download nothing. | contract (hostile) |
| ~~FR-008-03~~ | — | Retired: SPDX → licence-class mapping and derived class. | superseded by FR-001-18 and spec 001 data-model §5.2 (integration 2026-10-07) |
| FR-008-04 | Unwanted | If a stage would combine inputs of the `share-alike` class (classes as computed by spec 001's `licence_class_of`, FR-001-18) with inputs of any other class into one output file, then it shall refuse with `ShareAlikeMerge` naming the sources. Share-alike derivatives always stay separate outputs. | unit (hostile) |

**Download (`s00_download`)**

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-008-05 | Event | When `s00_download` runs an entry whose files carry a pinned `sha256`, it shall fetch each file over HTTPS through pooch, using a resumable httpx downloader, into `PITSTUDIO_DATA/raw/<id>/<basename>`. Account-bound and manual sources go to `PITSTUDIO_DATA/external/<id>/` instead. It shall compute the SHA-256 of the complete file by streaming (`hashlib.file_digest`), and shall promote the file from its `.part` name only when the digest and the byte count match. It shall re-verify a cached file before reusing it. | integration |
| FR-008-06 | Unwanted | If a downloaded or cached file's SHA-256 or byte count differs from the registry, then `s00_download` shall stop that source with `ChecksumMismatch` (expected and actual digest, expected and actual bytes), move the file to `PITSTUDIO_DATA/quarantine/<id>/`, promote nothing, and end the stage with a non-zero exit status. It shall never continue with unverified bytes. | integration (hostile) |
| FR-008-07 | Event | When an entry has no `sha256` yet and `s00_download` runs with `--pin`, it shall first verify the publisher checksum when one is declared (`files[].publisher_checksum`, for example Zenodo MD5), then write the computed SHA-256 to `data/pins/<id>.proposed.yaml` for the maintainer to review. It shall never edit `data/sources.yaml` itself, and shall mark the run `unpublishable` in its manifest. | integration |
| FR-008-08 | Unwanted | If an entry has no `sha256` and `--pin` is not given, or a run marked publishable would use a file without a pinned `sha256`, then `s00_download` shall refuse with `UnpinnedSource`. | unit (hostile) |
| ~~FR-008-09~~ | — | Retired: missing licence fields and non-commercial or no-derivatives terms are rejected by the registry schema before any download. | superseded by FR-001-31, FR-001-32 and FR-008-02 (integration 2026-10-07) |
| FR-008-10 | Unwanted | If the server announces (`Content-Length`) or delivers more bytes than the file's `bytes`, then `s00_download` shall abort the transfer before writing past the declared size, delete the partial file and report `Oversize`. If the free disk space at the target is below 1.2 × (`files[].bytes` + `files[].uncompressed_bytes`), it shall refuse to start that file with `InsufficientDisk`. | integration (hostile) |
| FR-008-11 | Unwanted | If a file's local name would be unsafe, then `s00_download` shall reject the file with `UnsafePath` before writing anything. The local name is the percent-decoded last segment of the URL path. It is unsafe if it contains a path separator, `..`, a drive letter, a NUL or control character, or a Windows reserved device name, or if it is longer than 200 characters. If a redirect leads to a non-HTTPS URL, `s00_download` shall reject the file with `InsecureRedirect` before writing anything. | unit (hostile) |
| FR-008-12 | Unwanted | If a transfer fails with a connection error, a timeout, HTTP 429 or HTTP 5xx, then `s00_download` shall retry up to 5 times with backoffs of 1, 2, 4, 8 and 16 s. It shall resume from the received byte offset when the server answers 206 and restart when it answers 200. After the last retry it shall fail with `DownloadFailed`. Any other HTTP 4xx shall fail at once. | integration (hostile) |
| FR-008-13 | State | While the environment variable named by an account-bound entry's `account.env_var` is unset or empty, `s00_download` shall skip the entry, apply its declared fallback and record `fallback-used` with the ids of `fallback.sources` in the fetch record. The key value shall never appear in any log line, fetch record, manifest, report or exception message. | integration |
| FR-008-14 | Unwanted | If an entry that declares no fallback source (no `fallback`, or `fallback.sources: []`) is unavailable or fails verification, then `s00_download` shall mark it `unavailable`, mark every recipe stage that consumes it `not_run` with the reason (spec 002, FR-002-60), and shall not substitute any other data. | integration |
| FR-008-15 | Unwanted | If `PITSTUDIO_DATA` resolves inside the repository working tree but outside its git-ignored data folders (`data/raw/`, `data/external/`, `data/interim/`, `data/processed/`, `data/synthetic/`), then every stage of this spec shall refuse to start with `UnsafeDataRoot`. | unit (hostile) |
| FR-008-16 | State | While `PITSTUDIO_OFFLINE=1` or the samples mode used by CI is active, `s00_download` shall read only `data/samples/` and already verified cached files, and shall open no network connection. | unit |
| FR-008-17 | Ubiquitous | `s00_download` shall write one fetch record per file, valid against `contracts/fetch-record.schema.json`. The record holds: source id, URL, final URL after redirects, bytes, SHA-256, publisher checksum status, SPDX id, licence class, redistribution class, retrieval time (UTC), status (`verified`, `fallback-used`, `unavailable`, `skipped-no-account`, `pin-proposed`), fallback ids and attempt count. | contract |

**Archives**

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-008-18 | Event | When an entry declares a file of kind `archive` with `extract` patterns (`files[].extract`), the archive extractor shall extract only the members that match those patterns into `PITSTUDIO_DATA/interim/<id>/`. Before extracting, it shall list all members and check their declared sizes. While extracting, it shall count the bytes written and stop at the cap. The cap is the file's `uncompressed_bytes`, or 20 × the compressed size when that is undeclared. Archives can be 7z, zip or tar. | integration |
| FR-008-19 | Unwanted | If any member has an absolute path, a drive letter or a `..` component, resolves outside the extraction root, is a symlink, hardlink or device, or makes the declared or written total exceed the cap, then the extractor shall reject the whole archive with `UnsafeArchive` naming the member, and leave no extracted file behind. | integration (hostile) |

**Ingestion (`s10_preprocess`)**

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-008-20 | Ubiquitous | Before any computation uses a tabular input, `s10_preprocess` shall validate it with a pandera (Polars) schema whose settings are: every column's dtype declared; `coerce=False`; `strict=True`; `nullable=False` unless the column declares otherwise; physical range checks whose metadata name the unit (SI) and the cited source of each bound; `lazy=True`. | unit |
| FR-008-21 | Unwanted | If a frame violates its schema (wrong dtype, out-of-range value, null, extra or missing column, duplicate key), then `s10_preprocess` shall reject the file. It shall write one ingestion report, valid against `contracts/ingestion-report.schema.json`, listing every failing (file, row, column, value, rule), and no output for that source. It shall never cast, clip, impute or drop rows to make the frame pass. | unit (hostile) |
| FR-008-22 | Ubiquitous | `s10_preprocess` shall keep every value inside its physical bounds, extremes included, and shall apply no statistical fence. It shall remove records only through exclusion rules declared in the recipe parameters (including area-of-interest crops), which enter the cache key, and shall record each rule and the number of records it removed in the manifest. | unit |
| FR-008-23 | Ubiquitous | `s10_preprocess` shall validate non-tabular inputs with file-level validators: rasters (CRS present, cell size in metres > 0 and finite, declared dtype, declared nodata value, extent inside the area of interest); point clouds (CRS present, point count > 0, classification codes present, bounds inside the area of interest); vector layers (valid geometries, CRS present, required attributes present); images and masks (Mendeley: 512 × 512 RGB JPEG images; indexed `P`-mode masks with 0 = background and *k* = instance *k*, at most 255 instances, exactly one mask per image). | unit |
| FR-008-24 | Unwanted | If a non-tabular input fails its validator, then `s10_preprocess` shall reject the file with a report naming the file, the property, the found value and the expected value. | unit (hostile) |
| FR-008-25 | Ubiquitous | Unit conversions shall happen only after validation, in explicit tested functions: ft → m × 0.3048 (exact by definition); mm → m ÷ 1,000; km/h → m/s ÷ 3.6; US gallon → L × 3.785411784. They shall never happen inside a schema. | unit |
| FR-008-46 | Unwanted | If a unit conversion receives a non-finite value or an unknown unit pair, then it shall raise `UnitError` naming the value and the pair, and shall never return NaN or Infinity. | unit (hostile) |
| FR-008-26 | Unwanted | If the Bingham area of interest does not intersect a pit polygon of the mining-footprint layer (`tang-werner-footprint`), then `s10_preprocess` shall label every derived artefact "site name provisional", and shall not write "Bingham Canyon" as a confirmed site name. | unit |

**Splits fixed at ingestion**

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-008-27 | Ubiquitous | `s10_preprocess` shall assign every record of every dataset to exactly one group through the dataset's declared group key, and shall make every split at group level. It shall commit the split in a file valid against `contracts/split.schema.json` (DC-008-04) under `data/splits/<id>.json`, with the SHA-256 of its membership lists. Later stages shall read splits only from that file. | contract + unit |
| FR-008-28 | Ubiquitous | For `mendeley-78ht3pjsr4`, the group of file *k* (1 … 960) shall be the connected component of g(k) = ((k − 1) mod 240) + 1 under the 9 conservative links (29, 39), (34, 41), (36, 37), (41, 49), (59, 60), (189, 199), (192, 196), (196, 198), (196, 201). The group id is the smallest original in the component. This gives 231 groups. | unit |
| FR-008-29 | Event | When `s10_preprocess` ingests the Mendeley set, it shall check, for every k in 1 … 240, that the foreground masks (label > 0) of files k + 240, k + 480 and k + 720 equal the horizontal flip, the vertical flip and the 180° rotation of file k's foreground mask, exactly. It shall also check that the `cv2_mask` and `label.png` foregrounds are equal for all 960 files. If any check fails, it shall reject the dataset with `AugmentationStructureBroken`, because the group key depends on it. | integration |
| FR-008-30 | Ubiquitous | The Mendeley split shall have 5 grouped folds of exactly 48 originals each. Assignment: order the groups by a seeded permutation (seed recorded in the split file), sort them stably by size (descending), then give each group to the fold with the fewest originals so far (lowest fold index on ties). For each fold, the test list shall hold only the originals (001–240) of its groups. The training pool shall hold all four versions of the originals of the other folds' groups. Any validation subset carved from a training pool shall also be by group. | unit |
| FR-008-47 | Unwanted | If a split file fails its schema, its membership SHA-256 differs from its lists, a record appears in two test lists, or a group appears in both the test list and the training pool of one fold, then every consumer of the split (`s20`, `s30`, `s50`) shall refuse to start with `SplitIntegrityError`, naming the first offending record. | unit (hostile) |
| FR-008-31 | Ubiquitous | Synthetic sets shall use the declared group key of their type: DES cycles → scenario seed; Voight creep series → event seed; muck-pile renders → muck-pile id (one DEM run); procedural terrain → pit layout id; SDG and sensor sets → scene seed. Real terrain tiles shall use (project, spatial block), with the block size declared in the recipe. The single real slope-failure series (`dewit-slope-failure`) shall be one group, used only descriptively, and never split. | unit |

**Synthetic data (`s05_synthesize`)**

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-008-32 | Ubiquitous | `s05_synthesize` shall generate the CPU synthetic sources and shall collect the studio's outputs as files with their SHA-256 digests. The CPU sources are: DES cycles (spec 007 adapter), Kuz-Ram/KCO + Swebrec PSDs (`minephys.blasting`), Voight creep series (`minephys.geotech`), Gaussian plume fields (`minephys.environment`), `oreblocks` deposits and comminution sweeps (`minephys.comminution`). The studio outputs are SDG images, sensor clouds, physics fields, Isaac Lab rollouts, hazard-question sets and plausibility pairs. | integration |
| FR-008-33 | Ubiquitous | Every synthetic set and every one of its records shall carry `synthetic: true`. Every set shall have a data card with: generator, version, git SHA, configuration SHA-256, seeds, priors with citation and page, assets with licence and SHA-256, and a validation entry per FR-008-36. | contract |
| FR-008-34 | Ubiquitous | A synthetic set of a type that has a real counterpart shall pass the same schema or validator, and load through the same loader, as the real data of that type: Voight series as the de Wit displacement series; muck-pile masks as the Mendeley mask validator (indexed, 0 = background, *k* = instance); procedural terrain as the DEM raster validator. | unit |
| FR-008-35 | Unwanted | If a studio output that a synthetic set needs is missing, or its digest differs from its studio manifest, then `s05_synthesize` shall mark that set `not-run` with the reason, and shall not substitute a placeholder or any other data. | unit (hostile) |
| FR-008-36 | Ubiquitous | The data-card writer shall give every synthetic set exactly one validation class. `validated-against-real` applies to fragment images and terrain statistics; their verdict stays `pending` until `s50_evaluate` sets it. `descriptive-only (single real event)` applies to Voight creep series. `unvalidated` applies to every other type: equipment and people images without the optional real probe, sensor clouds, dust and plume fields, DES and haul cycles, PSDs, comminution sweeps, Isaac Lab rollouts, physics fields, question sets and plausibility pairs. `unvalidated` carries the exact label "calibrated synthetic — not validated against real data" and `c2st_tstr: not-applicable`. Physics benchmark verdicts may be recorded in a separate field. | unit + contract |
| FR-008-37 | Unwanted | If any stage or tool tries to attach a C2ST or TSTR verdict to a set whose class is `unvalidated` or `descriptive-only`, then the data-card writer shall refuse with `HonestyRuleViolation` and leave the card unchanged. | unit (hostile) |
| FR-008-38 | Ubiquitous | For CPU generators, re-running `s05_synthesize` with the same seeds and configuration shall give byte-identical outputs (equal SHA-256), and the manifest shall record `determinism.class: bitwise`. | integration |

**Features (`s20_feature_extraction`)**

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-008-39 | Ubiquitous | `s20_feature_extraction` shall compute window features of displacement series (the windows, steps and features declared in the recipe parameters) causally: a feature stamped at time t shall use only samples with time ≤ t. | unit + property |
| FR-008-48 | Unwanted | If a displacement series has non-increasing timestamps, a non-finite sample, fewer samples than the longest declared window, or a window length ≤ 0, then `s20_feature_extraction` shall reject the series with a report naming the series and the first offending index, and shall compute no feature for it. If an image given to the embedder is not decodable, or has a channel count other than 3 or a side < 14 px, it shall reject that image the same way. | unit (hostile) |
| FR-008-40 | Optional | Where a CUDA device passes the runner's guards, `s20_feature_extraction` shall compute frozen DINOv2 ViT-S/14 image embeddings under the `gpu0.compute` lock, with the model id, revision and weights SHA-256 pinned. One preprocessing function, with its parameters recorded in the manifest, shall serve real and synthetic images alike. On CPU the same code path shall run and give bitwise-identical embeddings across runs. CPU and GPU embeddings of the same image shall have cosine similarity ≥ 0.999. | integration (gpu) + unit |
| FR-008-41 | Unwanted | If the embedding weights' SHA-256, revision or licence (Apache-2.0) differs from the pin, then `s20_feature_extraction` shall refuse to embed with `ModelPinMismatch`. | unit (hostile) |
| FR-008-42 | Ubiquitous | `s20_feature_extraction` shall compute every feature per record. It shall fit any feature normaliser or other transform only on the training groups of the split it serves, and store it with that split's id. It shall never fit anything on test-fold records. | unit |

**Data cards and committed data**

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-008-43 | Ubiquitous | Every registry entry shall have `data/cards/<id>.md`. Its front matter shall be valid against `contracts/data-card.schema.json`, and its id, SPDX id, licence class, redistribution class and SHA-256 list shall equal the registry entry's. Its body shall contain the sections What and why, Composition, Collection and provenance, Licence and attribution, Size checksums and access, Assumptions and limits, and In PitStudio. | contract |
| FR-008-44 | Unwanted | If a data card disagrees with the registry, or a required section is missing, then the CI card check shall fail, naming the card, the field and both values. | contract (hostile) |
| FR-008-45 | Ubiquitous | `data/samples/` shall hold only public-domain or CC0 crops, or synthetic fixtures, each with a sample card naming its source and licence. It shall hold no Mendeley image, mask or crop: that set publishes metrics only. | contract |

## 4. Correctness properties

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-008-01 | The streaming SHA-256 of any byte string, for any chunk sizes, equals `hashlib.sha256` of the whole string, and SHA-256("abc") = `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad` (FIPS 180-2 example). | byte strings 0 … 10 MB, chunks 1 B … 1 MB (Hypothesis) | exact |
| P-008-02 | For any interruption offset, a download resumed through HTTP Range gives the same bytes and SHA-256 as an uninterrupted one. A server that ignores Range (200) restarts the file and also gives the same result. | mocked transport (httpx `MockTransport`), offsets 0 … size | exact |
| P-008-03 | Reject, never coerce: for any valid frame, validation returns a frame equal to its input (values, dtypes, column order, row order). For any frame with one injected violation, validation raises, and the report contains that (row, column, rule). No validation ever returns a modified frame. | generated frames for every tabular schema (Hypothesis) | exact |
| P-008-04 | Outlier preservation: rows whose values lie inside the bounds, including exactly at a bound, are never removed (rows out = rows in). | edge-of-bound generators | exact |
| P-008-05 | Archive safety: for generated archives mixing safe and hostile member names (absolute, `..`, drive letters, symlinks, oversize), every write stays under the extraction root and covers only allowed members. Any hostile member leads to nothing written. | zip, tar and 7z archives (Hypothesis) | exact |
| P-008-06 | Mendeley groups (hand calculation): 231 groups. The multi-member groups are {29, 39}, {34, 41, 49}, {36, 37}, {59, 60}, {189, 199} and {192, 196, 198, 201}, and the other 225 originals are singletons. group(k) = group(k + 240·j) for j = 1, 2, 3. | k = 1 … 960 | exact |
| P-008-07 | Mendeley folds: they are pairwise disjoint; the union of the test lists is the 240 originals, each exactly once; every fold has 48 test originals; the group counts of folds 0 … 4 are 45, 46, 46, 47 and 47 (hand calculation: 48 − the originals in the fold's multi-member groups + the number of those groups, for any seed); no group (in any of its four versions) is in both the training pool and the test list of the same fold; the same seed reproduces the split file byte for byte. | seeds 0 … 2³² − 1 (Hypothesis) | exact |
| P-008-08 | Metamorphic, splits: (i) permuting the input file order leaves groups and folds unchanged; (ii) permuting the order of the links leaves the groups unchanged; (iii) adding a link between two files already in one group leaves the groups unchanged. | random permutations | exact |
| P-008-09 | Generator determinism: the same seed and configuration give equal SHA-256. For stochastic generators, a different seed gives a different SHA-256. | each CPU generator × 5 seeds | exact |
| P-008-10 | Metamorphic, window features: (i) changing samples after time t leaves every feature stamped ≤ t unchanged (causality); (ii) on uniform sampling, shifting the series by m samples shifts the features by m (translation equivariance); (iii) multiplying the displacement by c > 0 multiplies the linear features (displacement, velocity) by c and leaves the ratio features unchanged. | synthetic series, length 10 … 10⁴ | (i), (ii) exact; (iii) rtol 1e-12 |
| P-008-11 | Metamorphic, unit conversions: (i) round trip ft → m → ft within 1 ulp; (ii) composition ft → m → mm equals ft → mm within 1 ulp; (iii) conversion is linear: f(a·x) = a·f(x) within 1 ulp for powers of two a. | finite float64 in [−10⁹, 10⁹] | as stated |
| ~~P-008-12~~ | Retired: licence-class commutativity, idempotence and monotonicity. | — | superseded by P-001-04 (integration 2026-10-07) |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-008-01 | Peak memory of `s00_download` while hashing and extracting the 4,230,116,058-byte Mendeley archive | ≤ 1 GB resident | psutil sampling during the integration run on the reference machine |
| NFR-008-02 | Idempotent re-run: with every file cached and verified, a second `s00_download` run | opens no network connection and changes no file (SHA-256 of `PITSTUDIO_DATA/raw/` unchanged) | integration test with a transport that fails on any request |
| NFR-008-03 | Third-party raw data in git | zero tracked files under `data/raw/`, `data/external/`, `data/interim/`, `data/processed/` or `data/synthetic/`; every sample file < 1 MB (NFR-000-05 caps any file at 10 MB) | CI check on `git ls-files` |
| SC-008-01 | The Mendeley set is usable as intended, before any TSTR/TRTR claim (feeds SC-000-01) | 960 images; 960 masks; 240 originals verified by FR-008-29; 63,144 instances with pixels (mean 65.8 per image); 231 groups; 5 folds × 48 originals | `s10_preprocess` report against the dataset card's counts |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| ~~DC-008-01~~ | Retired: the registry fields read by `s00_download`. | superseded by DC-001-04 (`contracts/sources.schema.json`, spec 001 data-model §5; integration 2026-10-07) | — |
| DC-008-02 | Fetch record per file | `contracts/fetch-record.schema.json` (new) | `s00_download` → manifest, `s10_preprocess` |
| DC-008-03 | Ingestion report (accepted or rejected; every violation as file, row or pixel, column or property, value, rule, unit) | `contracts/ingestion-report.schema.json` (new) | `s10_preprocess` → maintainer, manifest |
| DC-008-04 | Split file (dataset id and version, group-key rule, links, groups, folds with test and train-pool lists, seed, method, membership SHA-256) | `contracts/split.schema.json` (new) | `s10_preprocess` → `s20`, `s30`, `s50` (specs 010, 012) |
| DC-008-05 | Data-card front matter for real and synthetic sets (identity, licence, digests, synthetic fields, validation class and verdict or label) | `contracts/data-card.schema.json` (new) | `s00` / `s05` / maintainer → CI card check, web knowledge pages |

Every stage output is also listed in a manifest valid against `contracts/manifest.schema.json` (DC-000-01), with
inputs by SHA-256 and the licence class computed by spec 001 (FR-001-18).

## 7. Edge cases and assumptions

**Edge cases**
- **Pooch has no resume.** pooch verifies and caches files but cannot resume a partial transfer. The 4.23 GB archive
  therefore uses a custom httpx downloader handed to pooch (FR-008-05, FR-008-12).
- **Publisher checksums.** Zenodo publishes MD5. It is checked before the SHA-256 pin is proposed and never replaces
  it (FR-008-07).
- **Manual sources.** EGMS is downloaded by hand by the maintainer. `s00_download` only verifies the files it finds
  under `PITSTUDIO_DATA/external/egms-hambach/`, and applies the fallback when they are absent.
- **Fallbacks from the plan's §8:**

  | Source | Fallback |
  |---|---|
  | `ot-mckinley-2023` | Bingham-only scenes + CC0 textures |
  | `egms-hambach` | case C1 uses de Wit + synthetic only |
  | `era5` | `ghcnh` (default), then ISD on NODD |
  | `maus-v2` | `tang-werner-footprint` |
  | `minelib-marvin` | `oreblocks` (the default anyway) |
  | `mendeley-78ht3pjsr4` | synthetic-only U-Net claim, stated in the D1 card |
  | `makehuman-exports` | procedural mannequins (studio side) |
  | optional real probe | "not measured" |
  | every other source | no fallback source (`fallback.sources: []` or no `fallback`): dependent stages are `not_run` (FR-008-14) |

- **Unnamed instances.** 48 named instances have no pixels in their masks. These are fully overlapped polygons and are
  not a violation; instance indices may have gaps.
- **The de Wit series** is one real event. It gets no split, no C2ST and no TSTR (FR-008-31, FR-008-36).

**Assumptions (pinned at specification)**
- **Mendeley archive.** `Research Data.7z`, 4,230,116,058 bytes, publisher SHA-256
  `7f4336a4fe1f83e3c828eed4c73e036d7694f94076b6f040e6211315693f402d`. Layout and counts as in the dataset card
  (bootstrap data check, 2026-10-04).
- **The 9 conservative links** come from the bootstrap phase-correlation search (raw NCC > 0.9; high-pass NCC
  0.19–0.32, inside the null distribution). The dataset card states their number, but not their identities, which are
  fixed here (FR-008-28).
- **NOAA GHCNh format.** GHCNh documentation v1.1.0 (2026-03-10), read on 2026-10-06:
  - per-station files are pipe-separated (`.psv`, §III(A), pp. 5–6) with 329 columns (§X, p. 18), and Parquet files
    also exist;
  - `DATE` is ISO 8601 in UTC;
  - `wind_direction` is in whole degrees from true north, with 360 = north and `000` = calm (Table 1, p. 7), so the
    schema range is [0, 360];
  - `wind_speed` is in metres per second (Table 1, p. 7), with a range of ≥ 0;
  - every variable has `_Measurement_Code`, `_Quality_Code`, `_Report_Type`, `_Source_Code` and
    `_Source_Station_ID` columns (§III(A), p. 6).
- **Embedding model.** DINOv2 ViT-S/14 (`facebook/dinov2-small`), Apache-2.0. The revision and weights SHA-256 are
  pinned at first download (FR-008-40). The variant is the smallest DINOv2 backbone, which is enough for two-sample
  tests on 512 × 512 tiles.

**UNVERIFIED (kept out of every oracle)**
- NRW tile sizes, the McKinley bulk URL pattern, an EGMS scripted API, the ERA5 licence version, the GHCNh terms of
  use, and the AP-42 PDF digest are read and recorded when their registry entries are pinned (FR-008-07). No
  requirement here depends on their values.

## 8. Clarifications log

1. **Mendeley link identities (resolved).** The card states 9 pairs and 231 groups, but not which pairs. They are
   pinned from the bootstrap check (FR-008-28) and verified by hand calculation (P-008-06): 240 − 15 + 6 = 231.
2. **Fold design (resolved).** The card says "for example 5 folds". This spec fixes 5 grouped folds of exactly 48
   originals. This is achievable because 225 singleton groups can fill any imbalance, and 240 / 5 = 48 (FR-008-30).
   With the greedy rule, the multi-member groups of sizes 4, 3, 2, 2, 2, 2 always go to folds 0, 1, 2, 3, 4, 2, which
   gives the group counts 45, 46, 46, 47 and 47 (P-008-07).
3. **Registry fields (resolved, with coordination; superseded by item 10).** `s00_download` needs fields the ingestion page's table does not
   list: optional, access, account variable, fallback, publisher checksum, uncompressed size, extract patterns and file
   kind. They are added to `contracts/sources.schema.json` additively, coordinated with spec 001 (DC-008-01,
   T-008-001).
4. **Resumable downloads (resolved).** "Fetched with pooch" stays true for verification and caching; the transfer
   itself uses a resumable httpx downloader passed to pooch (FR-008-05).
5. **7z extraction (resolved).** The Mendeley archive is 7z, which pooch cannot unpack. A 7z library is chosen and
   locked in the dependency-validation task (T-008-002). The candidate is `py7zr` (LGPL-2.1-or-later), used as an
   unmodified installed dependency and never vendored.
6. **Terrain processing split (resolved).** Terrain meshes and USD belong to `st10_terrain` (spec 004).
   `s10_preprocess` does the file-level validation and the declared crops of the inputs the pipeline lane consumes
   (FR-008-23).
7. **Honesty classes (resolved).** Validated against real data: fragment images and terrain statistics. Descriptive
   only: the slope series. Every other synthetic type: the exact honesty label (FR-008-36). This follows the plan's §8
   and the synthetic-data card.
8. **Site name (resolved).** The Bingham query box is hand-typed, so it is checked against the footprint layer before
   "Bingham Canyon" is written as a confirmed site (FR-008-26). This follows the 3DEP card.
9. **Embedding variant (resolved).** The docs name DINOv2 without a size. ViT-S/14 is fixed here (§7).
10. Integration 2026-10-07: the source-registry schema has one owner, spec 001-contracts. Every field this spec
    reads (access mode, account variable `account.env_var`, ordered `fallback.sources`, `files[].kind`,
    `files[].publisher_checksum`, `files[].uncompressed_bytes`, `files[].extract`, the 64 GiB size bound) now lives
    in spec 001 (data-model §5, FR-001-31, FR-001-32, FR-001-52). Retired here: DC-008-01 (field list), FR-008-03
    and P-008-12 (licence-class mapping and lattice, = FR-001-18, P-001-04) and FR-008-09 (missing licence fields,
    rejected by the schema). FR-008-02 is now the consumer-side rule (reject the whole registry on any spec 001
    violation); FR-008-07, -10, -13, -14 and -18 use spec 001's field names. Item 3 is superseded. T-008-001 no
    longer writes `sources.schema.json`. FR-008-14 uses spec 002's stage status `not_run` (FR-002-60).

## 9. Changes (only for features that modify earlier behaviour)
Not applicable: a new feature. The registry fields this spec reads are defined by spec 001 (DC-001-04).
### ADDED Requirements
### MODIFIED Requirements
### REMOVED Requirements

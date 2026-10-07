# Tasks 008 — Data pipeline, stages s00–s20
Format: `- [ ] T-NNN-xxx [US-NNN-x] (REQ IDs) description — test: <path::name>`

Rules:
- Every task with requirement IDs is a `[red]`/`[green]` commit pair.
- Each task's tests live in their own file(s) and are locked after `[red]`
  (`python tools/lock_tests.py specs/008-data-pipeline/tests.lock <files>`).
- Python tests carry `@pytest.mark.req("<ID>")`.
- `tests/pipeline/` runs in the `pipeline/` environment; `tests/gpu/` carries the `gpu` marker and never runs in CI;
  tests marked `slow` that need the real archive run only on the maintainer's machine.
- No test opens a network connection.

## Phase 1 — Setup
- [ ] T-008-001 (DC-008-02, DC-008-03, DC-008-04, DC-008-05) Write the new schemas `fetch-record`,
  `ingestion-report`, `split` and `data-card` (JSON Schema 2020-12; `contracts/sources.schema.json` is written by
  spec 001, T-001-022 and T-001-024); generate their Pydantic and TypeScript types; contract tests check the
  meta-schema, round trips and one hostile document per schema — test: tests/contract/test_t_008_001_data_schemas.py
- [ ] T-008-002 Dependency validation, before any feature code: choose and `uv add` (pipeline) a 7z extractor (`py7zr`
  candidate), GeoTIFF tag/CRS reading (`tifffile` + `pyproj` vs `rasterio`), LAZ headers (`laspy` + `lazrs`), vector
  layers (`pyogrio` + `shapely`) and the DINOv2 loader (`transformers` vs `torch.hub`). The lock must resolve on
  Windows/Python 3.14 wheels; record each licence; smoke-import each package — test: tests/pipeline/test_t_008_002_deps_smoke.py

## Phase 2 — US-008-1 (P1): verified, licence-traced fetch
- [ ] T-008-010 [US-008-1] (FR-008-01, FR-008-02) Registry loader: schema validation before any connection; one
  hostile registry per violation class of spec 001 (duplicate id, SPDX outside the allow-list, missing licence
  fields, non-HTTPS, bad digest, size bounds, mixed share-alike, unknown fallback, credential-like fields) rejects the
  whole registry and downloads nothing — test: tests/contract/test_t_008_010_registry.py
- [ ] T-008-011 [US-008-1] (FR-008-04) Share-alike merge refusal with spec 001's `licence_class_of` — test: tests/pipeline/test_t_008_011_licence_classes.py
- [ ] T-008-012 [US-008-1] (FR-008-05, FR-008-06, FR-008-17, P-008-01) Fetch through pooch + streaming SHA-256,
  `.part` promotion, cached re-verification, quarantine on mismatch, fetch records — test: tests/pipeline/test_t_008_012_download_verify.py
- [ ] T-008-013 [US-008-1] (FR-008-07, FR-008-08) `--pin` proposals with publisher-checksum checks (the registry is
  never edited), `UnpinnedSource` — test: tests/pipeline/test_t_008_013_pin_licence.py
- [ ] T-008-014 [US-008-1] (FR-008-10, FR-008-11, FR-008-15) Oversize bodies and headers, insufficient disk, unsafe
  local names, insecure redirects, unsafe data root — test: tests/pipeline/test_t_008_014_download_hostile.py
- [ ] T-008-015 [US-008-1] (FR-008-12, P-008-02, NFR-008-02) Classified retries with backoff, Range resume and 200
  restart, idempotent cached re-run with no request — test: tests/pipeline/test_t_008_015_retry_resume.py
- [ ] T-008-016 [US-008-1] (FR-008-13, FR-008-14, FR-008-16) Account-bound skip + fallback (sentinel key never
  written), no fallback source → `unavailable` and `not-run` consumers, offline and samples mode — test: tests/pipeline/test_t_008_016_fallback_offline.py
- [ ] T-008-017 [US-008-1] (FR-008-18, FR-008-19, P-008-05) Archive extraction by patterns under the size cap; hostile
  members (absolute, drive, `..`, symlink, hardlink, device, bomb) reject the archive with nothing written — test: tests/pipeline/test_t_008_017_archive_safety.py
- [ ] T-008-018 [US-008-1] (NFR-008-01) Peak memory ≤ 1 GB while verifying and extracting the real Mendeley archive
  (`slow`, local only) — test: tests/pipeline/test_t_008_018_mendeley_memory.py

## Phase 3 — US-008-2 (P1): reject, never coerce
- [ ] T-008-020 [US-008-2] (FR-008-20, FR-008-21, P-008-03) pandera (Polars) schemas for `ghcnh` (format of the NCEI
  documentation v1.1.0), `era5`, `dewit-slope-failure`, `egms-hambach` and `xu-expansion-v3`, with the documented
  settings; one ingestion report per rejected file; valid frames returned unchanged — test: tests/pipeline/test_t_008_020_tabular_schemas.py
- [ ] T-008-021 [US-008-2] (FR-008-22, P-008-04) Values at the bounds kept; only declared exclusion rules and crops
  remove records, with counts in the manifest and the rules in the cache key — test: tests/pipeline/test_t_008_021_outlier_policy.py
- [ ] T-008-022 [US-008-2] (FR-008-23, FR-008-24) Raster, point-cloud, vector and image/mask validators and their
  rejection reports — test: tests/pipeline/test_t_008_022_file_validators.py
- [ ] T-008-023 [US-008-2] (FR-008-25, FR-008-46, P-008-11) Definition-exact unit conversions after validation, their
  three relations, `UnitError` on non-finite values or unknown pairs — test: tests/pipeline/test_t_008_023_units.py
- [ ] T-008-024 [US-008-2] (FR-008-26) Bingham area-of-interest check against the footprint pit polygons; "site name
  provisional" label — test: tests/pipeline/test_t_008_024_site_name.py

## Phase 4 — US-008-3 (P1): leakage-free splits
- [ ] T-008-030 [US-008-3] (FR-008-27, FR-008-28, P-008-06, P-008-08) Group keys and the split file; Mendeley union-find
  over the 9 links (231 groups, the listed components); order invariances — test: tests/pipeline/test_t_008_030_mendeley_groups.py
- [ ] T-008-031 [US-008-3] (FR-008-29, SC-008-01) Augmentation-structure check (exact flips and rotation of the
  foreground; `cv2_mask` = `label.png`), `AugmentationStructureBroken`; the card's counts on the real archive (`slow`,
  local) and on generated fixtures (CI) — test: tests/pipeline/test_t_008_031_mendeley_integrity.py
- [ ] T-008-032 [US-008-3] (FR-008-30, FR-008-47, P-008-07) Seeded greedy grouped 5-fold: 48 originals per fold,
  group counts 45, 46, 46, 47, 47, originals-only tests, four-version training pools, byte-identical reproduction;
  tampered split files refused by consumers — test: tests/pipeline/test_t_008_032_mendeley_folds.py
- [ ] T-008-033 [US-008-3] (FR-008-31) Group keys of the synthetic types, terrain spatial blocks, de Wit as a single
  unsplit group — test: tests/pipeline/test_t_008_033_group_keys.py

## Phase 5 — US-008-4 (P1): honest synthetic data
- [ ] T-008-040 [US-008-4] (FR-008-32, FR-008-35, FR-008-38, P-008-09) CPU generators and the studio-output collector;
  missing or tampered studio outputs → `not-run`; byte-identical re-runs — test: tests/pipeline/test_t_008_040_synthesize.py
- [ ] T-008-041 [US-008-4] (FR-008-33, FR-008-34) `synthetic: true` on sets and records; synthetic data cards; synthetic
  sets pass the real-data validators and loaders — test: tests/pipeline/test_t_008_041_synthetic_format.py
- [ ] T-008-042 [US-008-4] (FR-008-36, FR-008-37) Validation classes per type, the exact honesty label,
  `HonestyRuleViolation` on any C2ST/TSTR verdict for an unvalidated or descriptive-only set — test: tests/pipeline/test_t_008_042_honesty_rule.py

## Phase 6 — US-008-5 (P2): reproducible features
- [ ] T-008-050 [US-008-5] (FR-008-39, FR-008-42, FR-008-48, P-008-10) Causal window features, transforms fitted on
  training groups only, the three relations, hostile series and images rejected — test: tests/pipeline/test_t_008_050_window_features.py
- [ ] T-008-051 [US-008-5] (FR-008-40, FR-008-41) DINOv2 ViT-S/14 pin (id, revision, SHA-256, licence), shared
  preprocessing, bitwise CPU re-run, `ModelPinMismatch`; CPU vs GPU cosine ≥ 0.999 under the lock — test: tests/pipeline/test_t_008_051_embeddings.py, tests/gpu/test_t_008_051_embeddings_gpu.py

## Phase 7 — Data cards and committed data
- [ ] T-008-060 [US-008-4] (FR-008-43, FR-008-44) Card front matter against the schema, registry ↔ card field
  equality, required sections; a CI failure names the card, field and both values — test: tests/contract/test_t_008_060_data_cards.py
- [ ] T-008-061 [US-008-1] (FR-008-45, NFR-008-03) Samples: public-domain/CC0 crops or synthetic fixtures with sample
  cards, no Mendeley pixels, each < 1 MB; no tracked file under the data roots — test: tests/contract/test_t_008_061_samples_hygiene.py

## Phase 8 — Polish and independent review
- [ ] T-008-090 Mutation run on `pitstudio_pipeline.{download, archive, ingest, splits, synthesize, features, cards}`;
  record the scores against `thresholds.yaml` `mutation`
- [ ] T-008-091 Independent review of the diff against this spec; append tasks for gaps

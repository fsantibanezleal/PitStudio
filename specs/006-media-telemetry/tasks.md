# Tasks 006 — Media and telemetry: `st56_encode` and the studio stages' GPU evidence
Format: `- [ ] T-006-xxx [US-006-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/006-media-telemetry/tests.lock <files>`).
Tests under `tests/gpu/` carry the `gpu` marker (reference machine only, skipped while `gpu0.hold` exists); the others
run in the studio CPU job with fakes or with the pinned CPU build of FFmpeg.

## Phase 1 — Setup
- [ ] T-006-001 (DC-006-01, DC-006-02, DC-006-03) contract schemas `frame-manifest`, `encode-report`, `profile-summary` + generated types; valid and invalid examples — test: tests/contract/test_t_006_001_media_schemas.py
- [ ] T-006-002 fakes (`FakeFFmpeg`, `FakeNVTX`, fake clock, held-lock environment fixtures, fake Warp stage), frame-sequence fixtures (clean and corrupt, ≤ 2 MB in total) and the CI step that installs the pinned Linux FFmpeg 8.1 LGPL build verified by its published checksum (no requirement IDs; setup)

## Phase 2 — US-006-1 (P1) A small, playable, high-quality clip pair with its record
- [ ] T-006-010 [US-006-1] (FR-006-02, FR-006-03, FR-006-04, P-006-01, P-006-02, P-006-03, P-006-04) VMAF bisection, re-measure, pair and poster budgets, `vmaf-unreachable` / `over-budget`, recorded relaxation — test: tests/property/test_t_006_010_vmaf_search.py
- [ ] T-006-011 [US-006-1] (P-006-05) VMAF aggregation relations: order, translation, splitting — test: tests/metamorphic/test_t_006_011_vmaf_aggregation.py
- [ ] T-006-012 [US-006-1] (FR-006-05) output verification: full decode, frame count, duration, `moov` before `mdat` (CPU encoders of the pinned build) — test: tests/unit/test_t_006_012_output_verification.py
- [ ] T-006-013 [US-006-1] (FR-006-06, FR-006-14) encoder records against spec 001's manifest schema, encode report, path scrubbing, local-only producers — test: tests/contract/test_t_006_013_encoder_record.py
- [ ] T-006-014 [US-006-1] (FR-006-07, FR-006-22) `resources.gpu: nvenc` in every encode recipe stage; held-lock check (spec 002) and `lock-not-held` — test: tests/unit/test_t_006_014_nvenc_lock.py
- [ ] T-006-015 [US-006-1] (P-006-06) frame-list digest: invariant to renaming, sensitive to a pixel and to frame order — test: tests/property/test_t_006_015_frame_digest.py
- [ ] T-006-016 [US-006-1] (FR-006-01, FR-006-16) NVENC AV1 1080p + H.264 720p + WebP poster end to end; encode determinism — test: tests/gpu/test_t_006_016_nvenc_encode.py

## Phase 3 — US-006-2 (P1) Honest "not run" when the encoder cannot run
- [ ] T-006-020 [US-006-2] (FR-006-09, FR-006-10, FR-006-11) FFmpeg discovery, version parse, executable digest, encoder/filter/option listing, driver gate and `not_run` results with their reasons — test: tests/unit/test_t_006_020_ffmpeg_gates.py
- [ ] T-006-021 [US-006-2] (FR-006-12, FR-006-13) hostile frames and names; argument lists without a shell — test: tests/unit/test_t_006_021_frames_hostile.py
- [ ] T-006-022 [US-006-2] (FR-006-15) PyNvVideoCodec previews can never be published — test: tests/unit/test_t_006_022_preview_encoder.py

## Phase 4 — US-006-3 (P2) Evidence from inside every studio GPU stage
- [ ] T-006-030 [US-006-3] (FR-006-17, P-006-08) nested NVTX step ranges under the helper's range, balanced on exceptions, no-op without `nvtx` — test: tests/property/test_t_006_030_nvtx_ranges.py
- [ ] T-006-031 [US-006-3] (FR-006-18, FR-006-19, P-006-07) throughput per unit kind, omission on bad counts or times, scaling relations — test: tests/unit/test_t_006_031_throughput.py
- [ ] T-006-032 [US-006-3] (FR-006-20, FR-006-21) profile mode: Warp activity timing, Chrome trace, kernel table, size cap, invalid flag, Nsight never launched — test: tests/unit/test_t_006_032_profile_outputs.py
- [ ] T-006-033 [US-006-3] (NFR-006-02, NFR-006-03) NVTX overhead and profile-output sizes — test: tests/unit/test_t_006_033_evidence_overhead.py

## Phase 5 — Acceptance
- [ ] T-006-040 (NFR-006-01, SC-006-01, SC-006-02) acceptance on the published runs (data-and-models phase): encode time, VMAF and budgets per clip, throughput and encoder records present — test: tests/pipeline/test_t_006_040_media_acceptance.py

## Phase 6 — Polish and review
- [ ] T-006-090 mutation run on `pitstudio_studio.media.search`, `pitstudio_studio.media.frames` and `pitstudio_studio.telemetry.throughput`; record the score against `mutation.numerical_core_min`
- [ ] T-006-091 independent review of the diff against this spec; append tasks for gaps

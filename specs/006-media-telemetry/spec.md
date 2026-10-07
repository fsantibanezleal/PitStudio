# Spec 006 — Media and telemetry: `st56_encode` (NVENC AV1 + H.264, VMAF-targeted) and the studio stages' GPU evidence
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent
The studio's GPU work reaches readers as videos and as GPU evidence. This spec covers (1) `st56_encode`, which encodes
lossless frame sequences on the GPU's NVENC engines through an external, pinned FFmpeg 8.1 LGPL build into an AV1 1080p
+ H.264 720p MP4 pair with a WebP poster, choosing the bitrate by measured VMAF, keeping each pair ≤ 25 MB, running
under the `gpu0.nvenc` lock and recording the encoder in the manifest — with honest "not run" outcomes when FFmpeg is
missing, unpinned or too new for the driver (FFmpeg 9.x needs driver ≥ 610), and rejection of corrupt frames and
oversized outputs; and (2) the stage side of GPU evidence for every studio stage: NVTX step ranges inside the range the
stage helper opens, a measured throughput in every GPU stage's result, encoder throughput for encodes, and kernel
timing tables when the runner profiles a stage. It serves visitors (small, playable clips), reviewers (an encoder
record and VMAF for every file) and practitioners (GPU claims backed by measurements).
The runner's NVML sampling at 1–4 Hz, the telemetry summary and its downsample for the web, `studio profile` and
`studio publish` (which bakes a run into web artefacts; the run card is the published run manifest
`web/public/assets/runs/<run_id>/manifest.json` with its published telemetry `web/public/assets/runs/<run_id>/telemetry.json`,
FR-002-48, DC-002-03) are specified in spec 002-runner; the manifest's telemetry-summary and encoder-record schemas in spec 001-contracts. This spec
reuses them and adds nothing that contradicts them. Out of scope also: rendering the frames (RTX, Kit, Isaac and
open-lane replay stages), the web pages showing the evidence (specs 018, 019) and Nsight captures (maintainer acts).

## 2. User stories
### US-006-1 (P1) A small, playable, high-quality clip pair with its record
As a visitor, I want each studio clip as an AV1 1080p file with an H.264 720p fallback and a poster, small enough for
the site and good enough to read; as a reviewer, I want the exact encoder, settings and VMAF of each file, so that I can
reproduce it. Independent test: encode a 10 s fixture sequence; both files decode cleanly, meet the VMAF target, fit
25 MB together, and the encoder records validate against the manifest schema.

### US-006-2 (P1) Honest "not run" when the encoder cannot run
As the maintainer, I want the encode stage to end without output and with the precise reason when FFmpeg is missing,
unpinned, too new for the driver or lacks NVENC or libvmaf, and to reject corrupt frames before encoding, so that no
clip comes from a wrong build or bad input. Independent test: run the stage against fake FFmpeg builds (absent, 9.0 on
driver 582.78, no `av1_nvenc`) and corrupt frame fixtures.

### US-006-3 (P2) Evidence from inside every studio GPU stage
As a data/AI practitioner, I want every studio GPU stage to mark its steps with NVTX ranges, report a measured
throughput, and write kernel timing tables when profiled, so that the runner's telemetry can be read per step and
compared across runs. Independent test: run a fake Warp stage with a fake NVTX module and a fake clock; check the
recorded ranges, the reported throughput and, in profile mode, the kernel table.

Story index (for traceability):

| ID | Priority | Title |
|---|---|---|
| US-006-1 | P1 | A small, playable, high-quality clip pair with its record |
| US-006-2 | P1 | Honest "not run" when the encoder cannot run |
| US-006-3 | P2 | Evidence from inside every studio GPU stage |

## 3. Functional requirements (EARS)
MB means 10⁶ bytes and KB 10³ bytes, as in the budgets. Stages run under spec 002's stage helper (job specification in,
stage result out). The error classes named below travel as the prefix of the stage-result message (`<class>: <detail>`)
with `error_class: unknown`, except `lock-not-held`, which is the stage result's own error class (FR-002-63). A "not
run" outcome is a stage result with `status: not_run`, no output and the stated `reason` (FR-002-60); in normal
operation the runner's capability guard (spec 002) already refuses the stage when the `nvenc` probe is not `pass`, and
the tool shows "not yet run" because it published nothing (FR-000-07).

### 3.1 `st56_encode`
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-006-01 | Ubiquitous | `st56_encode` shall take a lossless PNG frame sequence (8- or 16-bit RGB, ≥ 1920 × 1080) with its frame manifest (DC-006-01) and produce, per clip, `<clip>.av1.mp4` (`av1_nvenc`, 1920 × 1080, yuv420p 8-bit), `<clip>.h264.mp4` (`h264_nvenc`, High profile, 1280 × 720, yuv420p 8-bit), both MP4 with `+faststart` and the source frame rate, and `<clip>.webp` (a 1280 × 720 poster of the frame `poster_frame`, default 0). | integration (gpu) |
| FR-006-02 | Ubiquitous | `st56_encode` shall choose, per variant, the largest constant-quality value (smallest file) whose measured VMAF — libvmaf model `vmaf_v0.6.1`, computed on every frame at the variant's resolution against the lossless source scaled with Lanczos to that resolution — has a mean ≥ 93 and a 5th percentile (Hyndman–Fan type 7) ≥ 85, by bisection over the integer range declared per encoder (default AV1 [20, 50], H.264 [15, 40]) with at most 8 encodes per variant, and shall re-measure the chosen setting rather than infer it. | unit (fake encoder) + integration (gpu) |
| FR-006-03 | Ubiquitous | `st56_encode` shall keep bytes(AV1) + bytes(H.264) ≤ 25,000,000 per clip (NFR-000-07) and the poster ≤ 150,000 bytes, choosing the WebP quality in [50, 90] to fit. | unit + integration (gpu) |
| FR-006-04 | Unwanted | If no setting in the range reaches the VMAF target, or the pair at the target exceeds 25,000,000 bytes, then `st56_encode` shall fail with error class `vmaf-unreachable` or `over-budget`, reporting the best measured (setting, VMAF mean, VMAF p5, bytes) and promoting no output — unless the recipe declares, for that clip, a relaxation (a lower target with mean ≥ 80, a shorter duration or a crop) with a written reason, which the encode report then carries as `relaxation`. | unit (hostile, fake encoder) |
| FR-006-05 | Ubiquitous | `st56_encode` shall verify each output by decoding it fully with the same FFmpeg (`-v error -f null`, empty error output), by a decoded frame count equal to the source frame count, by a duration of frames/fps within one frame period, and by an MP4 top-level box order in which `moov` precedes `mdat`; a failing file is deleted and the stage fails with error class `decode-failed`. | unit + integration |
| FR-006-06 | Ubiquitous | `st56_encode` shall attach to each video output in its stage result the encoder record of the manifest contract (spec 001: codec, profile, pix_fmt, width, height, fps, frames, duration_s, bitrate_kbps, vmaf {mean, p5, model}, source_frames_sha256, encoder {ffmpeg_version, build_sha256, nvenc_api, args}, encode_fps), with arguments recorded verbatim except that paths are reduced to file names, and shall write an encode report (DC-006-02) with, per variant, every tried setting with its VMAF mean, VMAF p5 and bytes, the chosen setting, the pair total, the poster bytes and the relaxation or null. | unit + contract |
| FR-006-07 | Ubiquitous | Every recipe stage of `st56_encode` shall declare `resources.gpu: nvenc` (never `exclusive`), so that the runner holds `gpu0.nvenc` for it and encodes can overlap CPU stages but not another encode. | contract |
| ~~FR-006-08~~ | — | Retired: the stage's own zero-timeout probe of the `gpu0.nvenc` lock file. | superseded by FR-002-62, FR-002-63 and FR-006-22 (integration 2026-10-07) |
| FR-006-22 | Unwanted | If `st56_encode`, when it starts, finds that the runner's held-lock list (`PITSTUDIO_HELD_LOCKS`, FR-002-62) does not contain `gpu0.nvenc` or is malformed — for example when it is launched directly, outside the runner — then it shall refuse through the stage helper's guard `require_lock("nvenc", 0)` (FR-002-63) with `error_class: lock-not-held`, before launching FFmpeg. | unit (hostile) |
| FR-006-09 | Event | When `st56_encode` starts, it shall resolve FFmpeg from `PITSTUDIO_FFMPEG` (the profile's binary map) or else from `PATH`, parse its version from the first line of `-version`, check that the executable's SHA-256 equals the recipe's pinned `binaries` digest and the tool-registry pin (DC-000-04), and check that `av1_nvenc`, `h264_nvenc`, the `libvmaf` filter, the `libwebp` encoder and every declared encoder option are listed by `-encoders`, `-filters` and `-h encoder=<name>`, all within 10 s. | unit (fake FFmpeg) |
| FR-006-10 | Unwanted | If FFmpeg is not found, then `st56_encode` shall end within 2 s as `not_run` (FR-002-60) with the reason `FFmpeg not found: set PITSTUDIO_FFMPEG or put ffmpeg on PATH`, with no output. | unit (hostile, fake FFmpeg) |
| FR-006-11 | Unwanted | If the FFmpeg major version is ≥ 9 (NVENC SDK 13.1 headers, driver ≥ 610 required) and the NVML driver version is < 610, then `st56_encode` shall end as `not_run` (FR-002-60) with the reason `FFmpeg <version> needs NVIDIA driver >= 610 (found <driver>); use the pinned FFmpeg 8.1 build`; and if the version string cannot be parsed, the executable is not the pinned one, or an encoder, filter or declared option is missing, it shall end as `not_run` with the specific reason. | unit (hostile, fake FFmpeg) |
| FR-006-12 | Unwanted | If a frame cannot be decoded or is truncated, the frames differ in size or bit depth, a frame index is missing from the sequence, the SHA-256 of the frame list differs from the frame manifest, there are fewer than 2 frames, the resolution is below 1920 × 1080, or the frame rate is not one of 24, 25, 30, 50 or 60 fps, then `st56_encode` shall fail with error class `frames-invalid` naming the first bad frame, before any encode. | unit (hostile) |
| FR-006-13 | Unwanted | If a clip name contains anything outside `[a-z0-9-]` or is longer than 64 characters, or a frame path resolves outside the stage's input folder, then `st56_encode` shall fail with error class `name-invalid`; FFmpeg shall always be called with an argument list, never through a shell. | unit (hostile) |
| FR-006-14 | Optional | Where the frames come from a stage whose performance is `local-only` (Kit, Isaac Sim, Replicator, ovrtx), the encoder record, the encode report and the stage result shall contain encoder data only — never the producer's render or capture time, frame rate or telemetry. | unit |
| FR-006-15 | Unwanted | If a recipe stage selects the in-process PyNvVideoCodec encoder (local previews) and declares any output `publish: true`, then `st56_encode` shall fail at start with error class `not-publishable`; PyNvVideoCodec outputs are local previews only. | unit (hostile) |
| FR-006-16 | State | While the same frames are encoded twice with the same FFmpeg build, driver, GPU and arguments, `st56_encode` shall report determinism `bitwise` only if both outputs have the same SHA-256; otherwise it shall report `statistical` with a VMAF-mean difference ≤ 0.5 between the two encodes. | integration (gpu) |

### 3.2 GPU evidence from inside the studio stages
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-006-17 | Event | When a studio GPU stage (`st50_physics`, `st56_encode`) runs, it shall open, inside the NVTX range that the stage helper opens (`PITSTUDIO_NVTX_RANGE`, spec 002), one nested range `<range>/<step>` per declared step (for example `st50_physics/dem/step`, `st56_encode/av1/vmaf`), balanced also when the body raises, and shall create Warp timers with `use_nvtx=True`; where the `nvtx` module is not importable or no profiler is attached, the ranges shall do nothing. | unit (fake NVTX) |
| FR-006-18 | Ubiquitous | Every studio GPU stage shall report in its stage result a throughput {value, unit} equal to its work count divided by the wall time of its compute loop (excluding input and output): particle-steps/s for DEM, MPM and dust, cell-steps/s for shallow water, vehicle-steps/s for vehicles, frames/s for encodes (encoded frames of the final settings divided by their encode time). | unit (fake clock) |
| FR-006-19 | Unwanted | If the work count or the measured time is zero, negative or not finite, then the stage shall omit the throughput (never report a guessed or zero value) and name the reason in its result message. | unit (hostile) |
| FR-006-20 | Event | When the runner profiles a stage (`PITSTUDIO_PROFILE=1`, spec 002), a Warp-based studio stage shall enable Warp activity timing and write into its output folder a Chrome trace and a table of the 20 kernels with the largest total time (DC-006-03), labelled "kernel timing, no admin rights", and shall never launch `nsys` or `ncu` itself. | unit (fake stage) |
| FR-006-21 | Unwanted | If `PITSTUDIO_PROFILE` has a value other than `0` or `1`, then the stage shall fail with error class `profile-invalid`; and if a trace would exceed 100,000,000 bytes, the stage shall stop tracing at that size and mark the table `truncated: true`. | unit (hostile) |

## 4. Correctness properties
| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-006-01 | VMAF search optimality: for any VMAF curve non-increasing in the quality value, the chosen value equals the largest value meeting both targets found by enumerating the whole range. | Hypothesis: fake encoders with random monotone VMAF and size curves | exact |
| P-006-02 | VMAF search, target monotonicity: raising either VMAF target never yields a larger quality value (smaller file). | Hypothesis: pairs of targets | exact ordering |
| P-006-03 | VMAF search, size invariance: multiplying the fake size curve by any factor changes the outcome only through the byte budget, never the VMAF-based choice. | Hypothesis: factors 0.1–10 | exact |
| P-006-04 | VMAF search, safety: for any curve, monotone or not, the chosen value's re-measured VMAF meets both targets, or the search reports `vmaf-unreachable`. | Hypothesis: arbitrary fake curves | exact |
| P-006-05 | VMAF aggregation: the mean and the 5th percentile of per-frame scores are invariant to frame order; adding a constant c to every score adds c to both; the mean over two equal-length halves equals the mean of their means. | Hypothesis: 2–10,000 scores in [0, 100] | exact for order; atol 1 × 10⁻⁹ |
| P-006-06 | Frame-list digest: renaming frame files without changing content or order leaves `source_frames_sha256` unchanged; changing one pixel of one frame or swapping two frames changes it. | fixture sequences | exact |
| P-006-07 | Throughput: multiplying the work count by k multiplies the throughput by k; multiplying the measured time by k divides it by k; the throughput of a stage split into two parts of equal duration is the mean of their throughputs. | Hypothesis: counts 1–10¹⁵, times 10⁻³–10⁵ s | rtol 1 × 10⁻¹² |
| P-006-08 | NVTX balance: for any sequence of steps, some of which raise, every pushed range is popped exactly once, in last-in-first-out order. | Hypothesis: random step trees of depth ≤ 4 with random exceptions | exact |

## 5. Non-functional requirements and success criteria
| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-006-01 | Encode time of one clip pair (30 s, 1080p30) including the VMAF search | ≤ 5 min on the reference machine (plan estimate 1–5 min) | run manifest `wall_s` |
| NFR-006-02 | NVTX overhead without a profiler attached | ≤ 1 % of the stage's compute-loop time | paired timing of a fixed Warp CPU workload with and without ranges |
| NFR-006-03 | Profile outputs per stage | trace ≤ 100,000,000 bytes; kernel table ≤ 100,000 bytes | unit check on the written files |
| SC-006-01 | Every published clip pair meets the VMAF targets (or carries a recorded relaxation) and the 25 MB pair budget | 100 % of clips, in the data-and-models phase | encoder records and encode reports of the published runs |
| SC-006-02 | Every published run of a studio GPU stage carries a throughput, and every published encode carries encoder records for both variants and an `nvenc_util_pct` summary (or its "unavailable" reason) | 100 %, in the data-and-models phase | published run manifests |

## 6. Data contracts
| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-006-01 | Frame manifest (producer tool and stage, performance class, fps, frame count, width, height, bit depth, colour space, frame-name pattern, SHA-256 of the ordered list of per-frame SHA-256) | `contracts/frame-manifest.schema.json` (to be written: T-006-001) | render and replay stages → `st56_encode` |
| DC-006-02 | Encode report (per clip: search trace per variant, chosen settings, pair total, poster bytes, relaxation) | `contracts/encode-report.schema.json` (T-006-001) | `st56_encode` → run outputs, reviewers |
| DC-006-03 | Kernel timing table (method, label, top kernels with calls, total and mean time, truncated flag, trace file name) | `contracts/profile-summary.schema.json` (T-006-001) | profiled studio stages → local run folder |

The encoder record and the telemetry summary are parts of the manifest contract (DC-000-01, spec 001); the pinned FFmpeg
build is in the tool registry (DC-000-04); recipes (DC-000-03) declare `resources.gpu: nvenc` and the `ffmpeg` binary.

## 7. Edge cases and assumptions
- **Pinned (sources read by the docs):** NVENC SDK 13.0 headers need driver ≥ 570 and SDK 13.1 headers need driver ≥ 610
  (nv-codec-headers READMEs); BtbN builds use SDK 13.0 for FFmpeg ≤ 8.1 and SDK 13.1 for 9.0 and later
  (`50-ffnvcodec.sh`); FFmpeg refuses to encode when the build's NVENC API is newer than the driver's, with no fallback
  (`libavcodec/nvenc.c`). The record's `nvenc_api` comes from the pinned build entry (13.0 for BtbN n8.1), not from a
  probe.
- **VMAF targets** mean ≥ 93 and 5th percentile ≥ 85 are the docs' proposal, fixed here; `thresholds.yaml` keys (proposed
  keys, pending maintainer approval): `media.vmaf_mean_min: 93`, `media.vmaf_p5_min: 85`, `media.vmaf_relaxed_mean_min: 80`,
  `media.poster_bytes_max: 150000`. VMAF is a consistent target for synthetic renders, not a guarantee of fidelity.
- Measuring each variant at its own resolution (source scaled with Lanczos) is a design choice; measuring the 720p file
  upscaled to 1080p would rate it lower for the same bits.
- The two NVENC engines and unrestricted sessions allow both variants of a clip to encode concurrently under the one
  `gpu0.nvenc` lock; whether that is faster is measured, not assumed.
- Which `av1_nvenc` options the 8.1 build exposes (for example `-tune uhq`) is settled by FR-006-09 at run time.
- Particle- and dust-heavy content may need more bits than the budget allows; FR-006-04 then fails honestly.
- The held-lock check of FR-006-22 detects a direct launch outside the runner, which has no held-lock list.
- MP4 `+faststart` puts the `moov` box first so playback can start before the download ends.

## 8. Clarifications log
- Resolved (overlap with specs 001 and 002, written in parallel): the assignment of this spec lists "NVML 1–4 Hz
  telemetry, the telemetry summary schema and `studio publish` with a run card". Spec 002 already specifies the NVML
  sampler, the telemetry summary computation, the web downsample, `studio profile` and `studio publish` (whose
  published run manifest is the run card), and spec 001 the telemetry-summary and encoder-record schemas. To avoid two
  sets of requirements for one behaviour, this spec keeps only what those do not cover: the encode stage, the
  stage-side NVTX step ranges, throughput reporting and profile outputs. The coordinator is told.
- Resolved: the publication rules of the plan for videos (pinned encoder, VMAF met, pair ≤ 25 MB) are enforced at the
  producer: `st56_encode` promotes no output that fails them (FR-006-04, FR-006-05, FR-006-15), because recipe outputs
  declare `publish` statically and publication (spec 002) does not inspect encodes.
- Resolved: the poster is 1280 × 720 (the docs give no size; 150 KB at 1080p is not reliably reachable for detailed
  renders); the 150 KB cap is kept.
- Resolved: the docs' troubleshooting advice ("relax the VMAF target for that clip and record it") becomes the explicit,
  recorded relaxation of FR-006-04 with a floor of mean VMAF 80.
- Resolved: NVENC determinism is checked, not assumed (FR-006-16); the docs' `bitwise` class applies only when the
  check passes.
- Resolved: encoder throughput (`encode_fps`) is publishable even for frames from licence-restricted renderers, because
  FFmpeg/NVENC performance is not covered by those licences; the renderers' own timings are not (FR-006-14).
- Resolved (superseded by the integration entry below): "not run" was first written as a failed stage result with a
  `not-run:` message, because spec 002's stage results had no such status; the capability guard normally prevents the
  start.
- Integration 2026-10-07: spec 002 now has the stage status `not_run` with a mandatory reason (FR-002-60, FR-002-61)
  and exports the locks it holds (`PITSTUDIO_HELD_LOCKS`, FR-002-62) with a stage-helper guard (FR-002-63).
  FR-006-10 and FR-006-11 now end as `not_run` with their reasons; the stage-side lock-file probe FR-006-08 is struck
  and replaced by FR-006-22. The run card path is spec 002's: `web/public/assets/runs/<run_id>/manifest.json` with
  `telemetry.json` (FR-002-48, DC-002-03).
- Integration 2026-10-07: every `thresholds.yaml` key this spec proposes is marked "proposed key, pending maintainer
  approval" and compiled with the other specs' proposals for the maintainer; lane-gate keys are consolidated as
  `lane_gate.*` and budget keys as `budgets.*`.

## 9. Changes (only for features that modify earlier behaviour)
### ADDED Requirements
(none — new feature)
### MODIFIED Requirements
(none)
### REMOVED Requirements
(none)

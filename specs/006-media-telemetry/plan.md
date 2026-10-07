# Plan 006 — Media and telemetry: `st56_encode` and the studio stages' GPU evidence
Spec: ./spec.md

## Summary
Two components in the `studio/` environment. `pitstudio_studio.media` implements `st56_encode`: FFmpeg discovery and
gates, the held-lock check, frame checks, the VMAF bisection, the two encodes and the poster, output verification, the
encoder records and the encode report (FR-006-01…16). `pitstudio_studio.telemetry` holds the stage-side evidence
helpers used by every studio GPU stage: nested NVTX step ranges, throughput measurement and the profile-mode kernel
table (FR-006-17…21). The runner's NVML sampler, telemetry summary, downsample, profile command and publication are
spec 002's; this plan only produces what those consume (stage-result throughput, encoder records, profile files).
Every external dependency — FFmpeg, NVTX, the GPU lock, the clock — has a fake so that all logic is tested in CI.

## Technical context
Runtime: Python 3.14 in `studio/` (`uv run --project studio --frozen …`); locked `nvtx` 0.2.16, `warp-lang` 1.17.0,
`nvidia-ml-py` 13.615.71 (driver version for the gate), the stage helper of spec 002 (held-lock check, `not_run`). External: FFmpeg n8.1 LGPL (BtbN build with `av1_nvenc`, `h264_nvenc`, `libvmaf`, `libwebp`), called as a
subprocess with an argument list. CI: the studio CPU job (T-004-002) installs the pinned Linux FFmpeg 8.1 LGPL build,
verified by its published checksum (T-006-002), so decode, VMAF, poster and box-order tests run with that build's CPU
encoders; NVENC tests are `gpu`-marked and run only on the reference machine.

## Constitution check
| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | yes | clips encoded by the pinned build and measured by libvmaf; throughput measured, never declared |
| Spec before code | yes | every behaviour has an FR/P id |
| Acceptance-test-first | yes | every task in `tasks.md` is a `[red]`/`[green]` pair |
| Independent oracles | yes | brute-force enumeration for the search, `ffprobe` read-back, the ISO base-media box order, the published driver gates, SHA-256 by `hashlib`, hand-computed throughput |
| Determinism & explicit tolerances | yes | encode determinism checked (FR-006-16); tolerances justified below |
| Neutral contracts | yes | DC-006-01…03 (T-006-001); encoder record and telemetry summary reuse spec 001's manifest schema |
| Static delivery | yes | only files; publication is spec 002's |
| Honesty | yes | `not_run` results with their reasons (FR-006-10, FR-006-11; FR-002-60); relaxations recorded (FR-006-04); throughput omitted rather than guessed (FR-006-19) |
| Licence hygiene | yes | FFmpeg never vendored; licence-restricted producers' timings never recorded (FR-006-14); Nsight never launched (FR-006-20) |
| Simplicity | yes | FFmpeg CLI instead of bindings; three small helpers for the evidence |

## Design
Diagrams: ![Acceleration and encode flows](../../docs/assets/diagrams/acceleration-encode-flows.svg) ·
![Manifest contract](../../docs/assets/diagrams/manifest-contract.svg)

```text
st56_encode: held-lock check → FFmpeg discovery + gates → frame checks (decode every frame, digest)
             → per variant: bisection over CQ { encode → libvmaf vs Lanczos-scaled source } → re-measure
             → pair budget → poster → decode + frame count + box order → encoder records + encode report
             → stage result (outputs, encoder records, throughput in frames/s)
evidence:    stage helper's NVTX range → nested step ranges; compute-loop timer → throughput; profile mode →
             Warp activity timing → Chrome trace + kernel table
```

| Component (module) | Requirements |
|---|---|
| `media.ffmpeg` (discovery, version parse, executable SHA, encoder/filter/option listing, driver gate) | FR-006-09…11 |
| `media.lock` (held-lock check through the stage helper's `require_lock("nvenc", 0)`) | FR-006-07, FR-006-22 |
| `media.frames` (frame manifest, decode check, digest, names and paths) | FR-006-12, FR-006-13; P-006-06 |
| `media.search` (CQ bisection, VMAF aggregation, re-measure, budget, relaxation) | FR-006-02…04; P-006-01…05 |
| `media.encode` (argument lists, variants, poster, verification, box order, determinism check, encoder modes) | FR-006-01, FR-006-05, FR-006-15, FR-006-16 |
| `media.record` (encoder records, encode report, local-only producer rule) | FR-006-06, FR-006-14 |
| `telemetry.nvtx` (nested step ranges, Warp timers) | FR-006-17; P-006-08 |
| `telemetry.throughput` (compute-loop timer, units, omission) | FR-006-18, FR-006-19; P-006-07 |
| `telemetry.profile` (activity timing, trace, kernel table, cap) | FR-006-20, FR-006-21 |

Key decisions:
- **Search variable:** NVENC constant quality `-cq` with `-rc vbr -b:v 0`; fixed options (preset, tune, a 2 s GOP,
  B-frames, look-ahead) are recipe data checked against `-h encoder=<name>` (FR-006-09).
- **VMAF filter graph:** `[0:v]scale=<w>:<h>:flags=lanczos,format=yuv420p[ref];[1:v]format=yuv420p[dist];
  [dist][ref]libvmaf=model=version=vmaf_v0.6.1:log_fmt=json`, per-frame scores read from the JSON log.
- **Box order:** a short reader of top-level ISO base-media boxes (size, type) asserting `ftyp`, then `moov` before
  `mdat`.
- **Held-lock check:** `pitstudio_stagekit.require_lock("nvenc", 0)` reads the runner's `PITSTUDIO_HELD_LOCKS`
  (FR-002-62, FR-002-63); `gpu0.nvenc` listed → continue, otherwise refuse with `lock-not-held` (FR-006-22).
- **Fakes:** `FakeFFmpeg` (version line, encoder/filter/option lists, programmable VMAF(cq) and size(cq) curves, decode
  errors), `FakeNVTX` (records push/pop), a fake clock, hand-set `PITSTUDIO_HELD_LOCKS` values, a fake Warp stage with named
  fake kernels of known durations.

## Test strategy
| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-006-01 | integration (gpu) | expected codec, profile, size, pixel format and frame rate read back by `ffprobe` (reference implementation) | pytest |
| FR-006-02 | unit (fake encoder) + integration (gpu) | brute-force enumeration of the range on the fake curves; libvmaf as the reference metric on the real build | pytest, Hypothesis |
| FR-006-03 | unit + integration (gpu) | byte counts by `os.stat`; budget constants from the spec | pytest |
| FR-006-04 | unit (hostile, fake encoder) | fake curves that never reach 93/85, and that reach it only above 25 MB; expected payloads written by hand; a declared relaxation recorded verbatim | pytest |
| FR-006-05 | unit + integration | fixture MP4s with `mdat` before `moov`, a truncated file and a dropped frame must fail; frame counts by `ffprobe -count_frames` | pytest |
| FR-006-06 | unit + contract | spec 001's manifest schema for the encoder record; schema DC-006-02; hand-written expected record and report for a fake encode; path scrubbing on an argument list with absolute paths | pytest, jsonschema |
| FR-006-07 | contract | every `st56_encode` stage in `studio/recipes/` checked for `resources.gpu: nvenc` | pytest |
| FR-006-22 | unit (hostile) | hand-written `PITSTUDIO_HELD_LOCKS` values (`gpu0.nvenc` → runs; unset, empty, `gpu0.compute`, malformed → `lock-not-held`); a spy asserting FFmpeg is never launched without the lock listed | pytest |
| FR-006-09 | unit (fake FFmpeg) | hand-written `-version`, `-encoders`, `-filters`, `-h encoder` outputs; executable SHA-256 by `hashlib`; 10 s bound by wall clock | pytest |
| FR-006-10 | unit (hostile, fake FFmpeg) | no executable on `PATH` and an empty `PITSTUDIO_FFMPEG`: the exact message of the spec, ≤ 2 s | pytest |
| FR-006-11 | unit (hostile, fake FFmpeg) | the published driver gates: fake 9.0.2 with driver 582.78 → `not_run`; fake 9.0.2 with driver 615 → not this reason; an unparseable version; a different executable digest; missing `av1_nvenc`, `libvmaf`, `libwebp` or a declared option | pytest |
| FR-006-12 | unit (hostile) | corrupt fixtures: truncated PNG, a 1919 × 1080 frame, a 16-bit frame in an 8-bit sequence, a missing index, a tampered digest, a single frame, 29.97 fps | pytest |
| FR-006-13 | unit (hostile) | names with `/`, `\`, `..`, upper case, 65 characters; a frame path escaping the input folder; a spy on `subprocess.run` asserting `shell=False` and a list argument | pytest |
| FR-006-14 | unit | a frame manifest whose producer is `local-only`; the field sets of the record, report and result compared with the allowed lists | pytest |
| FR-006-15 | unit (hostile) | a recipe stage with the PyNvVideoCodec mode and one `publish: true` output | pytest |
| FR-006-16 | integration (gpu) | SHA-256 equality of two encodes by `hashlib`; VMAF difference from the two libvmaf logs | pytest |
| FR-006-17 | unit (fake NVTX) | the recorded push/pop sequence equals the expected nesting under the helper's range, also after an exception; no calls when `nvtx` is absent | pytest |
| FR-006-18 | unit (fake clock) | hand calculation: work count ÷ compute-loop time for each unit kind | pytest |
| FR-006-19 | unit (hostile) | zero, negative, NaN and infinite counts and times: throughput absent, reason present | pytest |
| FR-006-20 | unit (fake stage) | a fake stage with three named kernels of known durations: expected table rows; schema DC-006-03; `subprocess` spy asserting `nsys`/`ncu` are never launched | pytest, jsonschema |
| FR-006-21 | unit (hostile) | `PITSTUDIO_PROFILE` values `2`, `yes`, empty; a fake trace writer exceeding 10⁸ bytes | pytest |
| P-006-01 | property | brute-force enumeration over the range | Hypothesis |
| P-006-02 | metamorphic | monotonicity in the target | Hypothesis |
| P-006-03 | metamorphic | invariance under size scaling | Hypothesis |
| P-006-04 | property | safety: the final re-measure is checked against the targets | Hypothesis |
| P-006-05 | metamorphic | order invariance, translation equivariance and splitting of mean and type-7 percentile (NumPy `percentile` as reference) | Hypothesis |
| P-006-06 | property | SHA-256 of per-frame digests on a hand-built 3-frame fixture | pytest |
| P-006-07 | metamorphic | scaling of a ratio | Hypothesis |
| P-006-08 | property | last-in-first-out balance on random step trees | Hypothesis |
| NFR-006-01 | pipeline (data phase) | threshold in the spec | run manifest |
| NFR-006-02 | unit | paired timing (median of 9 runs) of a fixed Warp CPU workload with and without ranges | pytest |
| NFR-006-03 | unit | byte counts of the written files | pytest |
| SC-006-01, SC-006-02 | pipeline (data phase) | the targets of FR-006-02/03; the fields of FR-006-06/18 in the published run manifests | pytest on published runs |
| DC-006-01…03 | contract | JSON Schema 2020-12 meta-validation; valid and invalid examples; generated types round-trip | jsonschema |

### Tolerances and their justification
| Quantity | Tolerance | Why |
|---|---|---|
| Duration check (FR-006-05) | one frame period | MP4 timestamps are quantised to the stream time base; one frame is the natural unit |
| Re-encode VMAF difference (FR-006-16) | ≤ 0.5 | VMAF is reported to about 0.01; a difference above 0.5 would be visible in the published quality figures |
| VMAF targets (FR-006-02) | mean ≥ 93, p5 ≥ 85; relaxation floor 80 | the docs' proposal; 93 is near "visually lossless" on VMAF's 0–100 scale; p5 guards against bad scenes inside a good average |
| VMAF aggregation (P-006-05) | atol 1 × 10⁻⁹ | float64 sums of ≤ 10⁴ scores ≤ 100 differ by < 10⁻¹⁰ between orders |
| Throughput (P-006-07) | rtol 1 × 10⁻¹² | one float64 division |
| NVTX overhead (NFR-006-02) | ≤ 1 % | NVTX calls are no-ops without a tool attached; 1 % covers timer noise of a median of 9 runs |

## Risks and complexity tracking
| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| A pinned Linux FFmpeg in the CI job | decode, VMAF, poster and box-order logic must run against the real build family | fakes alone cannot catch errors in real filter graphs |
| A held-lock check in the stage (spec 002's list) | detects a direct launch outside the runner | trusting the runner alone gives no defence when a stage is started by hand |
| Risk: FFmpeg 9.x replaces 8.1 by mistake | the digest check and the driver gate stop it (FR-006-09, FR-006-11) | — |
| Risk: VMAF unreachable within 25 MB for dust-heavy clips | honest failure or a recorded relaxation (FR-006-04) | — |

# Encode videos

> Encode studio clips (physics replays, RTX renders, Kit captures, Isaac Lab rollouts) with the GPU's NVENC encoder
> through an external FFmpeg 8.1 LGPL build into an AV1 1080p + H.264 720p pair with a WebP poster, at a VMAF quality
> target, inside the 25 MB per-pair budget. · Part of: [Guides](README.md) · Related:
> [NVENC and FFmpeg](../frameworks/nvenc-ffmpeg.md) ·
> [DEC-0011 NVENC via FFmpeg 8.1](../architecture/decisions/DEC-0011-nvenc-ffmpeg-8-1.md) ·
> [budgets](../web/budgets.md) · [studio stages](../pipelines/studio-stages.md)

## What and why

**Goal:** every video on the site is small enough for the budget, plays in every major browser, and carries a record
of how it was made. AV1 gives the best quality per byte but its support depends on hardware in Safari (about 95 % global
support) [1]; H.264 plays everywhere. PitStudio therefore ships each clip as a pair — AV1 at 1080p and H.264 at 720p —
plus a WebP poster, and the browser's `MediaCapabilities` picks one. Encoding runs on the GPU's NVENC engine, which the
RTX 5000 Ada Laptop GPU supports for H.264, HEVC and AV1 4:2:0 [2].

**Status:** the NVENC capability probe exists (`studio/bench/probe_nvenc.py`); the encode stage `st56_encode` with its
VMAF search is written in the build phase. No clip has been encoded for publication.

## Prerequisites

- [Set up the studio](set-up-the-studio.md): the open studio environment `studio/` and the FFmpeg **n8.1** LGPL shared
  build from BtbN, unpacked outside the repository, with `PITSTUDIO_FFMPEG` pointing at `ffmpeg.exe` (or `ffmpeg` on
  `PATH`). FFmpeg is an external program run as a subprocess and never vendored.
- **Driver gating.** FFmpeg's NVENC code is compiled against a specific NVENC SDK header version and refuses to open the
  encoder on an older driver [3]. The SDK 13.0 headers need driver ≥ 570 [4]; the SDK 13.1 headers need ≥ 610 [5].
  BtbN builds pick the SDK 13.0 headers for FFmpeg ≤ 8.1 [6], so **FFmpeg 8.1 works on an R580 driver and FFmpeg 9.x
  does not**.
- The LGPL builds do not include x264 or x265 [7]; there is no CPU H.264 fallback inside this build.

## Steps

1. **Run the NVENC probe.** It encodes a synthetic 10 s 1080p30 test pattern with `av1_nvenc` (preset p5, CQ 30) and
   `h264_nvenc` (preset p5, CQ 23), then decodes each output fully to check it is clean, and records the FFmpeg version.

   ```bash run deferred=P6
   uv run --extra runner python studio/bench/run_bench.py nvenc
   ```

2. **Encode a clip pair** through the runner, under the `gpu0.nvenc` lock (encoding can overlap CPU stages but never
   another encode). The stage searches encoder quality settings until each output meets its VMAF target, then checks
   the pair against 25 MB.

   ```bash run deferred=P6
   uv run --extra runner studio run recipes/c2-tailings.yaml --stage st56_encode
   ```

   For orientation, a single NVENC AV1 encode with FFmpeg looks like this (illustrative; the stage chooses the
   quality value per clip):

   ```bash
   "$PITSTUDIO_FFMPEG" -i frames/%05d.png -c:v av1_nvenc -preset p5 -cq 30 -movflags +faststart clip.av1.mp4
   ```

   `+faststart` moves the MP4 index to the front so playback can start before the download ends [8].

3. **Publish.** The clips become Release assets if they exceed the in-git size cap, are pinned by SHA-256 in the
   manifest, and are copied into the Pages artifact at build ([budgets](../web/budgets.md)).

   ```bash run deferred=P6
   uv run --extra runner studio publish <run_id>
   ```

## Expected output

- Probe: `[bench] nvenc: pass (<seconds> s)`; in `studio/capabilities.json` the FFmpeg version and, because FFmpeg is
  open software, the measured encode rate and bitrate per encoder (`av1_nvenc_fps`, `av1_nvenc_kbps`, …). The fps
  figure includes the CPU-side generation of the test pattern.
- Stage: per clip, `<name>.av1.mp4` (1080p), `<name>.h264.mp4` (720p), `<name>.webp` (poster), and an **encoder
  record** in the manifest: FFmpeg version string, encoder, settings, VMAF score per output, sizes and SHA-256.
- Budget check: each pair ≤ 25 MB; all videos ≤ 150 MB (six pairs).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `this FFmpeg build has no ['av1_nvenc']` | a build without NVENC, or a GPL/CPU-only build | use the BtbN LGPL shared build that includes NVENC |
| NVENC opens fail with a "minimum required driver" message | an FFmpeg 9.x build (SDK 13.1 headers) on a driver below 610 | use FFmpeg n8.1 |
| `FFmpeg not found: set PITSTUDIO_FFMPEG or put ffmpeg on PATH` | the probe found no binary | set `PITSTUDIO_FFMPEG` to the full path of `ffmpeg.exe` |
| `output does not decode cleanly` | encoder or container problem | keep the probe's failure; do not publish clips from that build |
| A pair exceeds 25 MB | the clip is long or very detailed | shorten the clip, lower its resolution, or relax the VMAF target for that clip and record it |
| `skip` because the GPU is busy | another job holds VRAM or the lock | wait; encodes take `gpu0.nvenc`, heavy jobs take `gpu0.compute` |

## Assumptions and limits

- VMAF measures perceived quality of natural video; for synthetic renders it is a consistent target, not a guarantee
  of visual fidelity. VMAF is licensed BSD-2-Clause-Patent [9].
- Encoding performance of FFmpeg/NVENC is publishable; capture performance of Kit or Isaac Sim, which produced the
  frames, is not ([showcase rules](../web/showcase-rules.md)).

## In PitStudio

- Stage `st56_encode` (studio lane, Python 3.14); spec `006-media-telemetry`; every video on the site carries its
  encoder record.

## References

1. caniuse, "AV1 video format" — about 95 % support; Safari depends on hardware decoding. https://caniuse.com/av1
2. NVIDIA, "Video Encode and Decode GPU Support Matrix" — RTX 5000 Ada Laptop: H.264, HEVC, AV1 4:2:0 encode; unrestricted sessions. https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new
3. FFmpeg, `libavcodec/nvenc.c` — strict API check and minimum-driver message, no fallback. https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavcodec/nvenc.c
4. FFmpeg, `nv-codec-headers` README (n13.0.19.1) — SDK 13.0.19, driver ≥ 570. https://raw.githubusercontent.com/FFmpeg/nv-codec-headers/n13.0.19.1/README
5. FFmpeg, `nv-codec-headers` README (master) — SDK 13.1.15, driver ≥ 610. https://raw.githubusercontent.com/FFmpeg/nv-codec-headers/master/README
6. BtbN, FFmpeg-Builds `50-ffnvcodec.sh` — header branch chosen by FFmpeg version (≤ 8.1 → SDK 13.0). https://raw.githubusercontent.com/BtbN/FFmpeg-Builds/master/scripts.d/50-ffnvcodec.sh
7. BtbN, "FFmpeg-Builds" README — variants; LGPL builds exclude x264/x265. https://github.com/BtbN/FFmpeg-Builds
8. FFmpeg, "Formats" documentation — `movflags +faststart`. https://ffmpeg.org/ffmpeg-formats.html
9. Netflix, VMAF licence — BSD-2-Clause-Patent. https://raw.githubusercontent.com/Netflix/vmaf/master/LICENSE

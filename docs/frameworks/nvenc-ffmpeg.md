# NVENC and FFmpeg

> The GPU's hardware video encoder, driven through a pinned LGPL build of FFmpeg 8.1, turns every RTX render and
> simulation replay into an AV1 + H.264 pair sized by a quality target. · Part of: [Frameworks](README.md) · Related:
> [Encode videos guide](../guides/encode-videos.md) · [Budgets](../web/budgets.md) ·
> [Nsight / NVML](nsight-nvml.md) · [DEC-0011](../architecture/decisions/DEC-0011-nvenc-ffmpeg-8-1.md)

## What and why

**NVENC** is the dedicated video-encoder hardware on NVIDIA GPUs; it is "completely independent of CUDA cores or
graphics engine" [1]. On the reference GPU, NVIDIA's support matrix lists unrestricted concurrent encode sessions and
AV1 4:2:0 encoding [2]. **FFmpeg** drives it through the `av1_nvenc` and `h264_nvenc` encoders and adds VMAF quality
measurement through libvmaf.

Why this path ([DEC-0011](../architecture/decisions/DEC-0011-nvenc-ffmpeg-8-1.md)):

- **The NVENC API version gates the driver.** FFmpeg refuses to encode when its NVENC headers are newer than the driver
  supports ("Driver does not support the required nvenc API version"), with no fallback [3]. SDK 13.1 headers need
  driver 610 or newer; SDK 13.0 headers need 570 or newer [4][5]. BtbN's build script uses the 13.0 headers for FFmpeg
  8.1 and the 13.1 headers for 9.0 and master [6]. On an R580 driver — the reference machine runs 582.78 — **only an 8.1 build encodes**.
- **LGPL, run as an external tool.** The `lgpl` variant excludes GPL-only libraries such as libx264 and libx265 [7];
  H.264 comes from the hardware encoder instead. FFmpeg is never linked or vendored, so its licence stays outside the
  repo [8].
- **Capture frames, encode outside Kit.** Kit's Movie Capture documents no codec or bitrate settings and its 3.0 line
  notes "Video Codec 13.0 and 590+ driver support" [9][10]; RTX stages write lossless PNG/EXR frames instead, and the
  publishable encode is reproducible and codec-controlled.

Rejected: FFmpeg 9.x or master builds on this driver; gyan.dev builds (GPLv3-only) [11]; HEVC for the web (about 17 %
full browser support) [12].

## Identity

| Item | Value |
|---|---|
| FFmpeg | n8.1.3 LGPL shared build from BtbN (autobuild 2026-10-03), per-user portable zip verified against the published `checksums.sha256` [13] |
| FFmpeg upstream | 8.1.3 "Hoare" (2026-09-21) [14] |
| In-process alternative | `pynvvideocodec` 2.2.3 (MIT; cp314 Windows wheels; driver ≥ 531.61), pinned in `studio/uv.lock` [15][16] |
| Licence · class | FFmpeg LGPL-2.1+ build (external tool) · open; PyNvVideoCodec MIT · open |
| Ring | Trial |
| Environment | external tool called from `studio/` (Python 3.14); path from `PITSTUDIO_FFMPEG` or `PATH` |

## How PitStudio uses it

Stage `st56_encode` (about 1–5 minutes per clip pair, including the quality search) holds the `gpu0.nvenc` lock, so
encoding can overlap CPU stages but not another encode:

1. Input: lossless PNG/EXR frame sequences from Isaac Sim, Kit, ovrtx or the open-lane viewers, with a frame manifest.
2. Variants per clip, all MP4 with `+faststart` (index at the front, needed for progressive playback) [17]:
   **AV1 1080p** primary, **H.264 720p** fallback, and a WebP poster.
3. **VMAF-targeted bitrate:** bisect the bitrate until VMAF against the lossless frames meets the target (proposed: mean
   ≥ 93, 5th percentile ≥ 85, fixed in the thresholds file at specification). Then enforce the byte budget: **a pair
   ≤ 25 MB**. If the budget forbids the target, the clip is shortened or cropped, never silently degraded.
4. The manifest records codec, profile, resolution, frames, bitrate, bytes, SHA-256, VMAF, FFmpeg version, build
   SHA-256, NVENC API and arguments.

The web plays the AV1 source first and H.264 second; `MediaCapabilities.decodingInfo()` lets the app prefer AV1 only
where decoding is power-efficient [18]. AV1 has 80.39 % full plus 14.63 % partial browser support, and Safari decodes it
only on devices with a hardware decoder; H.264 has 97.26 % [19][20].

## Licence and redistribution

FFmpeg is LGPL-2.1-or-later as long as it is built without `--enable-gpl` and `--enable-nonfree` [8]. PitStudio runs it
as a subprocess from a per-user path, records its version and archive hash, and never commits or ships it. Encoded
videos of our scenes are CC-BY-4.0. Encoder throughput of our open-lane stages is publishable.

## Assumptions and limits

- A future FFmpeg upgrade to 9.x would silently break NVENC on an R580 driver [3]; the pin and the probe's smoke encode
  fail fast instead.
- Which `av1_nvenc` options (for example `-tune uhq`, `-tf_level`) the 8.1 build exposes with SDK 13.0 headers is
  settled by the smoke, not assumed [21].
- Particle- and dust-heavy RTX content is high-entropy and may need more bits than the budget allows; VMAF decides.
- PyNvVideoCodec bundles its own FFmpeg binaries, which NVIDIA does not update [22]; it is used only for local encodes.

## In PitStudio

- Probe: `probe_nvenc.py` encodes a 10 s 1080p30 test pattern with `av1_nvenc` (preset p5, CQ 30) and `h264_nvenc`
  (preset p5, CQ 23), then decodes both fully and fails on any decode error ([Capabilities probe](../studio/capabilities-probe.md)).
  Checked without a GPU: FFmpeg installed and both encoders listed. **Not yet run** on the GPU.
- Status of case videos: **not yet run** — produced in the data-and-models phase. Reported then: VMAF and bytes per clip pair against
  the ≤ 25 MB pair budget.

## References

1. NVIDIA. *NVENC Video Encoder API programming guide 13.0*. https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/nvenc-video-encoder-api-prog-guide/index.html
2. NVIDIA. *Video encode and decode GPU support matrix*. https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new
3. FFmpeg. *libavcodec/nvenc.c*. https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavcodec/nvenc.c
4. FFmpeg. *nv-codec-headers README (master, SDK 13.1)*. https://raw.githubusercontent.com/FFmpeg/nv-codec-headers/master/README
5. FFmpeg. *nv-codec-headers README (sdk/13.0)*. https://raw.githubusercontent.com/FFmpeg/nv-codec-headers/sdk/13.0/README
6. BtbN. *FFmpeg-Builds ffnvcodec script*. https://raw.githubusercontent.com/BtbN/FFmpeg-Builds/master/scripts.d/50-ffnvcodec.sh
7. BtbN. *FFmpeg-Builds README*. https://github.com/BtbN/FFmpeg-Builds
8. FFmpeg. *Legal*. https://ffmpeg.org/legal.html
9. NVIDIA. *Movie Capture settings*. https://docs.omniverse.nvidia.com/kit/docs/omni.kit.window.movie_capture/latest/SETTINGS.html
10. NVIDIA. *Movie Capture changelog*. https://docs.omniverse.nvidia.com/kit/docs/omni.kit.window.movie_capture/latest/CHANGELOG.html
11. gyan.dev. *FFmpeg Windows builds*. https://www.gyan.dev/ffmpeg/builds/
12. caniuse. *HEVC data*. https://raw.githubusercontent.com/Fyrd/caniuse/main/features-json/hevc.json
13. BtbN. *FFmpeg-Builds latest release (API)*. https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest
14. FFmpeg. *Download*. https://ffmpeg.org/download.html
15. Python Package Index. *PyNvVideoCodec* 2.2.3. https://pypi.org/pypi/PyNvVideoCodec/2.2.3/json
16. NVIDIA. *PyNvVideoCodec system requirements*. https://docs.nvidia.com/video-technologies/pynvvideocodec/read-me/system-requirements-common.html
17. FFmpeg. *Formats* (`movflags +faststart`). https://ffmpeg.org/ffmpeg-formats.html
18. MDN. *MediaCapabilities.decodingInfo()*. https://developer.mozilla.org/en-US/docs/Web/API/MediaCapabilities/decodingInfo
19. caniuse. *AV1 data*. https://raw.githubusercontent.com/Fyrd/caniuse/main/features-json/av1.json
20. caniuse. *MPEG-4/H.264 data*. https://raw.githubusercontent.com/Fyrd/caniuse/main/features-json/mpeg4.json
21. NVIDIA. *FFmpeg with NVIDIA GPU (SDK 13.1)*. https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/ffmpeg-with-nvidia-gpu/index.html
22. NVIDIA. *PyNvVideoCodec release notes*. https://docs.nvidia.com/video-technologies/pynvvideocodec/read-me/release-notes-v10.html

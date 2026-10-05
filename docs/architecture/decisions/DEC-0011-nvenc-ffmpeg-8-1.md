# DEC-0011: Video through NVENC with an FFmpeg 8.1 LGPL build

> Every studio video is encoded on the GPU's NVENC engine by an external FFmpeg 8.1 LGPL build, as an AV1 1080p plus an
> H.264 720p file whose bitrates are chosen by measured VMAF, so each pair fits 25 MB; FFmpeg 9.x is not used because its
> NVENC headers need a newer driver. · Part of: [decisions](README.md) · Related: [NVENC and FFmpeg](../../frameworks/nvenc-ffmpeg.md) ·
> [encode videos](../../guides/encode-videos.md) · [DEC-0006](DEC-0006-3d-and-simulation-on-static-web.md)

**Status:** Accepted, 2026-10-04

## Context

RTX renders, Kit captures, sensor replays and simulation clips reach visitors as video. The site budget allows about
150 MB of video in total, as six pairs of at most 25 MB ([budgets](../../web/budgets.md)), so quality per byte matters,
and encoding is a recurring studio stage (`st56_encode`).

- The RTX 5000 Ada laptop GPU has one NVENC engine with unrestricted concurrent sessions and encodes H.264, HEVC and AV1
  [1].
- FFmpeg reaches NVENC through the `nv-codec-headers`. The current headers (Video Codec SDK 13.1.15) require driver 610
  or newer [2]; the SDK 13.0 branch requires driver 570 or newer [3]. The reference machine runs driver 582.78, so an
  FFmpeg built against the 13.1 headers is expected to refuse NVENC, while one built against 13.0 works.
- BtbN's Windows builds select the header branch by FFmpeg version (FFmpeg ≤ 8.1 uses SDK 13.0) [4], publish GPL and LGPL
  variants with checksums (the LGPL variants exclude x264 and x265) [5], and enable libvmaf [6], which the bitrate search
  needs.
- A popular alternative Windows build is FFmpeg 9.0.2 under GPLv3 [7], which would require the newer driver.
- PyNvVideoCodec 2.2.3 encodes H.264, HEVC and AV1 in-process and ships Python 3.14 Windows wheels [8]; it is locked in
  the open studio environment, but its minimum driver for 2.2.x could not be confirmed.

## Decision

- **Encoder.** FFmpeg n8.1 LGPL (BtbN build), downloaded per user, verified by its published checksums and run as an
  external subprocess; never vendored. The manifest records `ffmpeg -version`, the encoder and its settings.
- **Outputs.** AV1 1080p as the primary file and H.264 720p as the fallback, MP4 with a WebP poster; the pair ≤ 25 MB.
  On the site, `MediaCapabilities` picks AV1 only where decoding is power-efficient; `preload="none"`; playback is synced
  to the shared `SimClock`.
- **Quality target.** The bitrate is chosen by a VMAF search against the lossless capture. The targets are set in
  `thresholds.yaml` during specification; the proposal is a mean VMAF ≥ 93 with the 5th percentile ≥ 85.
- **Lock.** The encode stage takes the `gpu0.nvenc` lock, so encoding can overlap CPU-only stages but never another
  encode.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| FFmpeg 9.x | Newest features | Its NVENC headers need driver ≥ 610 [2]; the reference driver is 582.78 | Would require an elevated driver install for no other gain |
| GPL FFmpeg builds | Include x264 and x265 | GPL binaries; not needed when NVENC does the encoding | LGPL suffices |
| Kit's MP4 capture as the publishing path | No separate encoder | No control over codecs, bitrate ladders or VMAF targets; tied to Kit | Kit captures image sequences; FFmpeg encodes them |
| H.264 only | Universal playback | Larger files at the same quality; fewer clips fit the budget | AV1 primary, H.264 fallback |

## Consequences

**Positive.** Hardware encoding on the installed driver; quality-targeted files that fit the budget; the encoder record
in every manifest makes videos reproducible.

**Negative, accepted.** An external binary to verify and pin; a VMAF search per clip (estimated 1–5 minutes per pair,
measured by the runner).

**Watch.** NVENC header versions in FFmpeg builds; the driver branch on the reference machine; PyNvVideoCodec's driver
requirements.

**Status.** FFmpeg n8.1.3 LGPL (shared build) is downloaded, verified and lists its NVENC encoders; the GPU encode smoke
test waits for the reference machine.

## References

1. NVIDIA. Video encode and decode GPU support matrix. https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new
2. FFmpeg nv-codec-headers README (master, SDK 13.1.15, driver ≥ 610). https://raw.githubusercontent.com/FFmpeg/nv-codec-headers/master/README
3. FFmpeg nv-codec-headers README (sdk/13.0, driver ≥ 570). https://raw.githubusercontent.com/FFmpeg/nv-codec-headers/sdk/13.0/README
4. BtbN FFmpeg-Builds: nv-codec-headers selection script. https://raw.githubusercontent.com/BtbN/FFmpeg-Builds/master/scripts.d/50-ffnvcodec.sh
5. BtbN FFmpeg-Builds. https://github.com/BtbN/FFmpeg-Builds
6. BtbN FFmpeg-Builds: libvmaf script. https://raw.githubusercontent.com/BtbN/FFmpeg-Builds/master/scripts.d/45-vmaf.sh
7. gyan.dev FFmpeg Windows builds. https://www.gyan.dev/ffmpeg/builds/
8. PyNvVideoCodec on PyPI. https://pypi.org/pypi/PyNvVideoCodec/json

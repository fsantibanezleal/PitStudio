"""Encoder records and the encode report (FR-006-06, FR-006-14).

The encoder record is the one of the manifest contract (`manifest.schema.json#/$defs/encoder`); the report is
DC-006-02. Only encoder data is written here: nothing of a producer's render or capture time, frame rate or
telemetry ever reaches a record.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from .search import (
    PAIR_BYTES_MAX,
    POSTER_BYTES_MAX,
    RELAXED_MEAN_FLOOR,
    VMAF_MEAN_MIN,
    VMAF_P5_MIN,
)

VMAF_MODEL = "vmaf_v0.6.1"
PROFILES = {"av1": "main", "h264": "high"}


def scrub_args(args: Sequence[str]) -> list[str]:
    """Reduce every path argument to its file name; every other argument is kept verbatim, in order."""
    out = []
    for a in args:
        a = str(a)
        if "/" in a or "\\" in a:
            out.append(re.split(r"[\\/]", a)[-1])
        else:
            out.append(a)
    return out


def build_encoder_record(
    codec: str,
    *,
    width: int,
    height: int,
    fps: float,
    frames: int,
    file_bytes: int,
    vmaf_mean: float,
    vmaf_p5: float,
    source_frames_sha256: str,
    ffmpeg_version: str,
    build_sha256: str,
    nvenc_api: str | None,
    args: Sequence[str],
    encode_seconds: float,
) -> dict:
    duration = frames / fps
    ok = isinstance(encode_seconds, (int, float)) and math.isfinite(encode_seconds) and encode_seconds > 0
    return {
        "codec": codec,
        "profile": PROFILES[codec],
        "pix_fmt": "yuv420p",
        "width": width,
        "height": height,
        "fps": fps,
        "frames": frames,
        "duration_s": duration,
        "bitrate_kbps": file_bytes * 8 / duration / 1000,
        "vmaf": {"mean": vmaf_mean, "p5": vmaf_p5, "model": VMAF_MODEL},
        "source_frames_sha256": source_frames_sha256,
        "encoder": {
            "ffmpeg_version": ffmpeg_version,
            "build_sha256": build_sha256,
            "nvenc_api": nvenc_api,
            "args": scrub_args(args),
        },
        "encode_fps": frames / encode_seconds if ok else None,
    }


TARGETS = {
    "vmaf_mean_min": int(VMAF_MEAN_MIN),
    "vmaf_p5_min": int(VMAF_P5_MIN),
    "relaxed_vmaf_mean_floor": int(RELAXED_MEAN_FLOOR),
    "pair_bytes_max": PAIR_BYTES_MAX,
    "poster_bytes_max": POSTER_BYTES_MAX,
}

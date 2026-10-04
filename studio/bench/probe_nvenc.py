"""Probe (studio env): FFmpeg 8.1 NVENC encodes (AV1 + H.264) of a synthetic 1080p30 clip, then a full decode check.

FFmpeg is an external tool: `PITSTUDIO_FFMPEG` (path to ffmpeg.exe) or `ffmpeg` on PATH. FFmpeg 9.x needs driver
>= 610, so the probe records the version and fails on a missing encoder instead of guessing.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import time
from importlib import metadata
from typing import Any

from _common import SkipProbe, run_probe, tmp_dir

SECONDS, FPS, SIZE = 10, 30, "1920x1080"
ENCODERS = {"av1_nvenc": ("-preset", "p5", "-cq", "30"), "h264_nvenc": ("-preset", "p5", "-cq", "23")}


def ffmpeg_exe() -> str:
    exe = os.environ.get("PITSTUDIO_FFMPEG") or shutil.which("ffmpeg")
    if not exe:
        raise SkipProbe("FFmpeg not found: set PITSTUDIO_FFMPEG or put ffmpeg on PATH")
    return exe


def body(r: dict[str, Any]) -> None:
    exe = ffmpeg_exe()
    first = subprocess.run([exe, "-hide_banner", "-version"], capture_output=True, text=True, check=True).stdout
    r["versions"]["ffmpeg"] = first.split()[2] if first.startswith("ffmpeg version") else first.splitlines()[0]
    with contextlib.suppress(metadata.PackageNotFoundError):
        r["versions"]["pynvvideocodec"] = metadata.version("pynvvideocodec")
    encoders = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True, check=True).stdout
    missing = [e for e in ENCODERS if f" {e} " not in encoders]
    if missing:
        raise RuntimeError(f"this FFmpeg build has no {missing}")
    src = ["-f", "lavfi", "-i", f"testsrc2=size={SIZE}:rate={FPS}:duration={SECONDS}"]
    frames = SECONDS * FPS
    for enc, opts in ENCODERS.items():
        out = tmp_dir("nvenc") / f"probe_{enc}.mp4"
        t0 = time.perf_counter()
        p = subprocess.run(
            [exe, "-hide_banner", "-v", "error", "-y", *src, "-c:v", enc, *opts, str(out)],
            capture_output=True,
            text=True,
        )
        wall = time.perf_counter() - t0
        if p.returncode != 0:
            raise RuntimeError(f"{enc} failed: {p.stderr.strip()[-300:]}")
        dec = subprocess.run(
            [exe, "-hide_banner", "-v", "error", "-i", str(out), "-f", "null", "-"], capture_output=True, text=True
        )
        if dec.returncode != 0 or dec.stderr.strip():
            raise RuntimeError(f"{enc} output does not decode cleanly: {dec.stderr.strip()[-300:]}")
        r["metrics"][f"{enc}_fps"] = round(frames / wall, 1)  # includes the CPU-side test-pattern generation
        r["metrics"][f"{enc}_kbps"] = round(out.stat().st_size * 8 / SECONDS / 1000)


if __name__ == "__main__":
    run_probe("nvenc", "public", body)

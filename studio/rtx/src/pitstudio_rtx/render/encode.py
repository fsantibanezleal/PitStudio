# SPDX-License-Identifier: Apache-2.0
"""FFmpeg encode of the flyover frames: H.264 on NVENC, libx264 only when NVENC is missing (and then said so).

FFmpeg is the external, pinned build named by `PITSTUDIO_FFMPEG` (spec 006): called as a subprocess with an argument
list, never vendored. The arguments recorded in the manifest carry no path.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
FALLBACK = "libx264"


class RenderEncodeError(RuntimeError):
    """FFmpeg is missing, lacks an H.264 encoder, or failed."""


@dataclass(frozen=True)
class EncodeInfo:
    name: str
    fallback: bool
    ffmpeg_version: str
    args: list[str]


def find_ffmpeg(env: Mapping[str, str] | None = None) -> str:
    """`PITSTUDIO_FFMPEG` when set (it must exist), else the first `ffmpeg` on the PATH."""
    env = os.environ if env is None else env
    named = env.get("PITSTUDIO_FFMPEG")
    if named:
        if not Path(named).is_file():
            raise RenderEncodeError(f"PITSTUDIO_FFMPEG points at a file that does not exist: {Path(named).name}")
        return named
    found = shutil.which("ffmpeg")
    if not found:
        raise RenderEncodeError("FFmpeg not found: set PITSTUDIO_FFMPEG or put ffmpeg on the PATH")
    return found


def pick_encoder(ffmpeg: str, wanted: str, runner: Runner = subprocess.run) -> tuple[str, bool]:
    """(encoder name, fell back): `wanted` when listed by `ffmpeg -encoders`, else libx264, else an error."""
    listing = runner(
        [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, check=False, timeout=30
    ).stdout
    names = {line.split()[1] for line in listing.splitlines() if len(line.split()) > 1}
    if wanted in names:
        return wanted, False
    if FALLBACK in names:
        return FALLBACK, True
    raise RenderEncodeError(f"no H.264 encoder in this FFmpeg build ({wanted} and {FALLBACK} are both missing)")


def encode_command(
    ffmpeg: str, frames_dir: Path, pattern: str, fps: int, out: Path, output: Mapping[str, Any], encoder: str
) -> list[str]:
    """The FFmpeg argument list for a numbered PNG sequence starting at frame 0."""
    cfg = output["encoder"]
    head = [ffmpeg, "-hide_banner", "-y", "-framerate", str(fps), "-start_number", "0", "-i", str(frames_dir / pattern)]
    if encoder == FALLBACK:
        codec = ["-c:v", FALLBACK, "-preset", "medium", "-crf", str(cfg["cq"])]
    else:
        codec = ["-c:v", encoder, "-preset", cfg["preset"], "-rc", "vbr", "-cq", str(cfg["cq"]), "-b:v", "0"]
    tail = ["-g", str(cfg["gop_frames"]), "-pix_fmt", cfg["pix_fmt"], "-movflags", "+faststart", str(out)]
    return head + codec + tail


def _recorded(cmd: list[str], pattern: str, out: Path) -> list[str]:
    """The arguments without the executable, with the input given as its file pattern and the output as its name."""
    args = cmd[1:-1]
    args[args.index("-i") + 1] = pattern
    return [*args, out.name]


def encode_clip(
    frames_dir: Path,
    pattern: str,
    fps: int,
    out: Path,
    output: Mapping[str, Any],
    *,
    ffmpeg: str | None = None,
    runner: Runner = subprocess.run,
) -> EncodeInfo:
    """Encode `frames_dir/pattern` into `out`; raises `RenderEncodeError` with the FFmpeg error tail on failure."""
    exe = ffmpeg or find_ffmpeg()
    name, fell_back = pick_encoder(exe, output["encoder"]["name"], runner)
    version_text = runner(
        [exe, "-hide_banner", "-version"], capture_output=True, text=True, check=False, timeout=30
    ).stdout
    found = re.search(r"ffmpeg version (n?\d+(?:\.\d+){0,3})", version_text)
    cmd = encode_command(exe, frames_dir, pattern, fps, out, output, name)
    done = runner(cmd, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        tail = "\n".join((done.stderr or "").strip().splitlines()[-5:])
        raise RenderEncodeError(f"FFmpeg exited with {done.returncode}: {tail}")
    return EncodeInfo(
        name=name,
        fallback=fell_back,
        ffmpeg_version=found.group(1) if found else "unknown",
        args=_recorded(cmd, pattern, out),
    )

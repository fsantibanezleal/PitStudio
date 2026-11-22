"""FFmpeg discovery and gates for `st56_encode` (FR-006-09 to FR-006-11).

FFmpeg is resolved from `PITSTUDIO_FFMPEG`, else from `PATH`; its version, executable digest, encoders, filters
and options are checked within 10 s. Every failure is a `NotRun` with a one-line reason: the stage cannot run, it
did not fail.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pitstudio_stagekit import NotRun

BUDGET_S = 10.0
DRIVER_FLOOR_FOR_9 = 610
NOT_FOUND = "FFmpeg not found: set PITSTUDIO_FFMPEG or put ffmpeg on PATH"
REQUIRED_ENCODERS = ("av1_nvenc", "h264_nvenc", "libwebp")
REQUIRED_FILTER = "libvmaf"
DEFAULT_OPTIONS: dict[str, tuple[str, ...]] = {
    "av1_nvenc": ("preset", "rc", "cq"),
    "h264_nvenc": ("preset", "rc", "cq"),
    "libwebp": ("quality",),
}
_VERSION = re.compile(r"(n?[0-9]+(?:\.[0-9]+){0,3})(?=$|[-+~_])")
_CTRL = re.compile(r"[\x00-\x1f\x7f‪-‮⁦-⁩]")


@dataclass(frozen=True)
class FFmpegBuild:
    path: Path
    version: str
    major: int
    sha256: str


def parse_version(first_line: str) -> tuple[str, int]:
    """`(version, major)` from `ffmpeg version <token> ...`; ValueError for anything else."""
    parts = first_line.split()
    if len(parts) < 3 or parts[0] != "ffmpeg" or parts[1] != "version":
        raise ValueError("not an `ffmpeg version <token>` line")
    m = _VERSION.match(parts[2])
    if not m:
        raise ValueError(f"unrecognised FFmpeg version token {parts[2]!r}")
    version = m.group(1)
    return version, int(re.search(r"[0-9]+", version).group(0))  # type: ignore[union-attr]


def _clean(text: str, limit: int = 60) -> str:
    return _CTRL.sub(" ", text).strip()[:limit]


def _resolve(env: Mapping[str, str]) -> Path | None:
    explicit = env.get("PITSTUDIO_FFMPEG", "")
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    names = ("ffmpeg.exe", "ffmpeg") if os.name == "nt" else ("ffmpeg",)
    for folder in (env.get("PATH") or "").split(os.pathsep):
        if not folder:
            continue
        for name in names:
            p = Path(folder) / name
            if p.is_file():
                return p
    return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _driver_major(driver: object) -> int | None:
    m = re.match(r"\s*([0-9]+)", str(driver))
    return int(m.group(1)) if m else None


def discover(
    *,
    env: Mapping[str, str],
    runner: Callable[..., subprocess.CompletedProcess],
    pinned_sha256: str,
    driver_version: str,
    required_options: Mapping[str, Iterable[str]] | None = None,
    clock: Callable[[], float] | None = None,
) -> FFmpegBuild:
    """Resolve FFmpeg and check it; the checks run in the order of FR-006-09. Raises `NotRun` on any failure."""
    now = clock or time.monotonic
    deadline = now() + BUDGET_S
    path = _resolve(env)
    if path is None:
        raise NotRun(NOT_FOUND)

    def call(args: list[str]) -> str:
        remaining = deadline - now()
        if remaining <= 0:
            raise NotRun(f"FFmpeg checks exceeded the {BUDGET_S:g} s time budget")
        try:
            done = runner(
                [str(path), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=remaining,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise NotRun(f"FFmpeg did not answer within the {BUDGET_S:g} s time budget") from None
        except OSError as e:
            raise NotRun(f"FFmpeg could not be started: {_clean(str(e), 120)}") from None
        if done.returncode != 0:
            raise NotRun(f"FFmpeg {' '.join(args[:2])} exited with code {done.returncode}")
        return done.stdout or ""

    banner = call(["-version"])
    first = banner.splitlines()[0] if banner.strip() else ""
    try:
        version, major = parse_version(first)
    except ValueError:
        raise NotRun(f"FFmpeg version not recognised in {_clean(first)!r}") from None
    digest = _sha256(path)
    if digest != pinned_sha256:
        raise NotRun(
            f"FFmpeg executable is not the pinned build (sha256 {digest[:12]}..., pinned {str(pinned_sha256)[:12]}...)"
        )
    if major >= 9:
        found = _driver_major(driver_version)
        if found is None or found < DRIVER_FLOOR_FOR_9:
            raise NotRun(
                f"FFmpeg {version} needs NVIDIA driver >= {DRIVER_FLOOR_FOR_9} "
                f"(found {_clean(str(driver_version), 40)}); "
                "use the pinned FFmpeg 8.1 build"
            )
    encoders = set()
    for line in call(["-hide_banner", "-encoders"]).splitlines():
        cols = line.split()
        if len(cols) >= 2 and re.fullmatch(r"[A-Z.]{6}", cols[0]):
            encoders.add(cols[1])
    for name in REQUIRED_ENCODERS:
        if name not in encoders:
            raise NotRun(f"FFmpeg lacks the encoder {name}")
    filters = set()
    for line in call(["-hide_banner", "-filters"]).splitlines():
        cols = line.split()
        if len(cols) >= 2 and len(cols[0]) == 3:
            filters.add(cols[1])
    if REQUIRED_FILTER not in filters:
        raise NotRun(f"FFmpeg lacks the filter {REQUIRED_FILTER}")
    options = DEFAULT_OPTIONS if required_options is None else {k: tuple(v) for k, v in required_options.items()}
    for encoder, wanted in options.items():
        listed = {
            line.split()[0] for line in call(["-hide_banner", "-h", f"encoder={encoder}"]).splitlines() if line.strip()
        }
        for option in wanted:
            if f"-{option}" not in listed:
                raise NotRun(f"FFmpeg encoder {encoder} lacks the option {option}")
    return FFmpegBuild(path, version, major, digest)

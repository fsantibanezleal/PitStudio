"""Output verification of an encoded MP4: box order, a full decode, frame count and duration (FR-006-05)."""

from __future__ import annotations

import struct
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .errors import DecodeFailed

PROCESS_TIMEOUT_S = 3600.0


# ---------------------------------------------------------------------------------------------------------------------
# ISO base media boxes and the output verification (FR-006-05)
# ---------------------------------------------------------------------------------------------------------------------
def top_level_boxes(data: bytes) -> list[tuple[str, int]]:
    """The (type, size) of every top-level ISO/IEC 14496-12 box; size 1 reads a 64-bit size, size 0 runs to the end."""
    out: list[tuple[str, int]] = []
    pos, n = 0, len(data)
    while pos < n:
        if n - pos < 8:
            raise DecodeFailed(f"{n - pos} trailing bytes are shorter than a box header")
        size, kind = struct.unpack(">I4s", data[pos : pos + 8])
        header = 8
        if size == 1:
            if n - pos < 16:
                raise DecodeFailed("a box announces a 64-bit size that is cut off")
            (size,) = struct.unpack(">Q", data[pos + 8 : pos + 16])
            header = 16
        elif size == 0:
            size = n - pos
        if size < header or pos + size > n:
            raise DecodeFailed(f"box {kind.decode('latin-1')!r} has an impossible size {size}")
        out.append((kind.decode("latin-1"), size))
        pos += size
    return out


def check_box_order(data: bytes) -> None:
    """`ftyp` first, then `moov` before the first `mdat` (progressive playback needs the index first)."""
    kinds = [k for k, _ in top_level_boxes(data)]
    if not kinds or kinds[0] != "ftyp":
        raise DecodeFailed("the first box is not ftyp")
    if "moov" not in kinds or "mdat" not in kinds:
        raise DecodeFailed("the file has no moov or no mdat box")
    if kinds.index("moov") > kinds.index("mdat"):
        raise DecodeFailed("mdat comes before moov (encode without +faststart)")


@dataclass(frozen=True)
class Verification:
    frames: int
    duration_s: float


def _last_value(text: str, key: str) -> str | None:
    value = None
    for line in text.splitlines():
        if line.startswith(f"{key}="):
            value = line.split("=", 1)[1].strip()
    return value


def verify_output(
    path: Path,
    *,
    ffmpeg: Path,
    runner: Callable[..., subprocess.CompletedProcess],
    source_frames: int,
    fps: float,
) -> Verification:
    """Box order, a clean decode, the source frame count, the duration within a frame period; else delete and fail."""
    path = Path(path)
    try:
        check_box_order(path.read_bytes())
        done = runner(
            [str(ffmpeg), "-v", "error", "-nostdin", "-i", str(path), "-f", "null", "-progress", "pipe:1", "-"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROCESS_TIMEOUT_S,
            check=False,
        )
        if done.returncode != 0:
            raise DecodeFailed(f"the decode exited with code {done.returncode}")
        if (done.stderr or "").strip():
            raise DecodeFailed(f"the decode reported errors: {(done.stderr or '').strip()[:120]}")
        frames_text, time_text = _last_value(done.stdout or "", "frame"), _last_value(done.stdout or "", "out_time_us")
        if frames_text is None or time_text is None:
            raise DecodeFailed("the decode reported no frame count or time")
        try:
            frames, duration = int(frames_text), int(time_text) / 1e6
        except ValueError:
            raise DecodeFailed("the decode progress is not numeric") from None
        if frames != source_frames:
            raise DecodeFailed(f"decoded {frames} frames, the source has {source_frames}")
        if abs(duration - source_frames / fps) > 1.0 / fps:
            raise DecodeFailed(
                f"duration {duration:.4f} s differs from {source_frames / fps:.4f} s by more than a frame"
            )
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return Verification(frames, duration)

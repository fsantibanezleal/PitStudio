"""Frame sequences of `st56_encode`: names, paths, PNG checks and the frame-list digest (FR-006-12, FR-006-13,
P-006-06)."""

from __future__ import annotations

import hashlib
import math
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from .digest import digest_of_digests
from .digest import frame_digests as frame_digests  # re-exported: the frame API of the stage
from .digest import source_frames_sha256 as source_frames_sha256
from .errors import FramesInvalid, NameInvalid

ALLOWED_FPS = (24, 25, 30, 50, 60)
MIN_WIDTH, MIN_HEIGHT = 1920, 1080
_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_DRIVE = re.compile(r"^[A-Za-z]:")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_VALID_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}


@dataclass(frozen=True)
class ValidatedSequence:
    paths: list[Path]
    width: int
    height: int
    bit_depth: int
    fps: int
    frames: int
    source_frames_sha256: str


# ---------------------------------------------------------------------------------------------------------------------
# names and paths (FR-006-13)
# ---------------------------------------------------------------------------------------------------------------------
def validate_clip_name(name: object) -> None:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise NameInvalid("a clip name is 1 to 64 characters of a-z, 0-9 and '-', starting with a letter or digit")


def _relative_folder(directory: object) -> str:
    if not isinstance(directory, str) or not directory:
        raise NameInvalid("the frame directory must be a non-empty relative path")
    if "\\" in directory or directory.startswith("/") or _DRIVE.match(directory) or "\x00" in directory:
        raise NameInvalid("the frame directory must be a relative path with forward slashes")
    if ".." in directory.split("/"):
        raise NameInvalid("the frame directory must not contain '..'")
    return directory


def _frame_name(pattern: object, number: int) -> str:
    if not isinstance(pattern, str) or not pattern:
        raise NameInvalid("the frame pattern must be a non-empty string")
    if "/" in pattern or "\\" in pattern or ".." in pattern or "\x00" in pattern or _DRIVE.match(pattern):
        raise NameInvalid("the frame pattern must name a file inside the frame directory")
    try:
        name = pattern % number
    except TypeError, ValueError:
        raise FramesInvalid(f"the frame pattern {pattern!r} does not format a frame index") from None
    if not name or "/" in name or "\\" in name:
        raise NameInvalid("a frame name must be a plain file name")
    return name


# ---------------------------------------------------------------------------------------------------------------------
# PNG (ISO/IEC 15948) decode check, without an image library and without allocating the image
# ---------------------------------------------------------------------------------------------------------------------
def _png_check(data: bytes, width: int, height: int, depth: int) -> str | None:
    """None when `data` is a complete, consistent PNG of the stated size and depth, else the reason."""
    if data[:8] != _PNG_SIGNATURE:
        return "not a PNG (bad signature)"
    pos, n = 8, len(data)
    seen_ihdr = seen_iend = False
    inflater = zlib.decompressobj()
    raw_len = 0
    expected_raw = 0
    while pos < n:
        if pos + 12 > n:
            return "truncated chunk header"
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        end = pos + 8 + length
        if end + 4 > n:
            return "truncated chunk"
        body = data[pos + 8 : end]
        (crc,) = struct.unpack(">I", data[end : end + 4])
        if zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            return f"bad CRC in chunk {kind.decode('latin-1')!r}"
        if not seen_ihdr:
            if kind != b"IHDR" or length != 13:
                return "the first chunk is not IHDR"
            w, h, bit_depth, colour, _compression, _filter, interlace = struct.unpack(">IIBBBBB", body)
            if (w, h) != (width, height):
                return f"size {w}x{h}, the manifest says {width}x{height}"
            if bit_depth != depth:
                return f"bit depth {bit_depth}, the manifest says {depth}"
            if colour not in _CHANNELS or bit_depth not in _VALID_DEPTHS[colour]:
                return "invalid colour type or bit depth"
            if interlace != 0:
                return "interlaced PNG is not supported"
            row_bytes = math.ceil(w * _CHANNELS[colour] * bit_depth / 8)
            expected_raw = h * (row_bytes + 1)
            seen_ihdr = True
        elif kind == b"IDAT":
            try:
                raw_len += len(inflater.decompress(body, expected_raw - raw_len + 1))
            except zlib.error:
                return "corrupt zlib stream"
            if raw_len > expected_raw:
                return "image data longer than the header allows"
        elif kind == b"IEND":
            seen_iend = True
            pos = end + 4
            break
        pos = end + 4
    if not seen_iend:
        return "no IEND chunk"
    try:
        raw_len += len(inflater.flush())
    except zlib.error:
        return "corrupt zlib stream"
    if not inflater.eof:
        return "incomplete zlib stream"
    if raw_len != expected_raw:
        return f"image data is {raw_len} bytes, the header needs {expected_raw}"
    return None


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_sequence(manifest: dict, input_dir: Path) -> ValidatedSequence:
    """Check a DC-006-01 frame manifest and the frames it names: name, paths, size, rate, then frame by frame."""
    validate_clip_name(manifest.get("clip"))
    directory = _relative_folder(manifest.get("directory", "."))
    pattern = manifest.get("frame_pattern")
    first_index = manifest.get("first_index", 0)
    if not _is_int(first_index) or first_index < 0:
        raise FramesInvalid("first_index must be a non-negative integer")
    root = Path(input_dir).resolve()
    folder = Path(input_dir) / directory
    frames = manifest.get("frames")
    if not _is_int(frames) or frames < 2:
        raise FramesInvalid(f"at least 2 frames are needed, the manifest says {frames!r}")
    # every frame path first: a hostile pattern or directory is refused before any file is touched
    paths: list[Path] = []
    for k in range(frames):
        p = folder / _frame_name(pattern, first_index + k)
        try:
            p.resolve().relative_to(root)
        except ValueError:
            raise NameInvalid(f"frame path {p.name} resolves outside the input folder") from None
        paths.append(p)
    width, height, depth, fps = (
        manifest.get("width"),
        manifest.get("height"),
        manifest.get("bit_depth"),
        manifest.get("fps"),
    )
    if not (_is_int(width) and _is_int(height) and width >= MIN_WIDTH and height >= MIN_HEIGHT):
        raise FramesInvalid(f"the resolution must be at least {MIN_WIDTH}x{MIN_HEIGHT}, got {width!r}x{height!r}")
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or fps not in ALLOWED_FPS:
        raise FramesInvalid(f"the frame rate must be one of {ALLOWED_FPS}, got {fps!r}")
    if not _is_int(depth) or depth not in (8, 16):
        raise FramesInvalid(f"the bit depth must be 8 or 16, got {depth!r}")
    listed = manifest.get("frame_sha256")
    if listed is not None and (not isinstance(listed, list) or len(listed) != frames):
        raise FramesInvalid("frame_sha256 must list one digest per frame")
    digests: list[str] = []
    for k, p in enumerate(paths):
        if not p.is_file():
            raise FramesInvalid(f"frame {p.name} is missing")
        data = p.read_bytes()
        problem = _png_check(data, width, height, depth)
        if problem:
            raise FramesInvalid(f"frame {p.name}: {problem}")
        digest = hashlib.sha256(data).hexdigest()
        if listed is not None and listed[k] != digest:
            raise FramesInvalid(f"frame {p.name}: its SHA-256 differs from the frame manifest")
        digests.append(digest)
    expected = manifest.get("source_frames_sha256")
    if digest_of_digests(digests) != expected:
        raise FramesInvalid("the frame-list SHA-256 differs from the frame manifest")
    return ValidatedSequence(paths, width, height, depth, int(fps), frames, digest_of_digests(digests))

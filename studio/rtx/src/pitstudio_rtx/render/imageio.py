# SPDX-License-Identifier: Apache-2.0
"""PNG output with the standard library and numpy only (no imaging dependency), written atomically."""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path

import numpy as np

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
IEND = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def write_png(path: str | Path, rgb: np.ndarray) -> None:
    """Write an 8-bit RGB image (height, width, 3) as a PNG: to `<path>.part` first, then renamed into place."""
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"write_png needs a uint8 array of shape (height, width, 3), got {rgb.dtype} {rgb.shape}")
    height, width, _ = rgb.shape
    rows = np.zeros((height, 1 + 3 * width), dtype=np.uint8)  # filter type 0 (none) at the start of each scanline
    rows[:, 1:] = rgb.reshape(height, 3 * width)
    data = (
        PNG_SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(rows.tobytes(), 3))
        + IEND
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    part.write_bytes(data)
    os.replace(part, target)


def is_complete_png(path: str | Path) -> bool:
    """True when the file starts with the PNG signature and ends with the IEND chunk (a partial write fails both)."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return False
    return data.startswith(PNG_SIGNATURE) and data.endswith(IEND)

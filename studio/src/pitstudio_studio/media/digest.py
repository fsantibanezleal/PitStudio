"""Frame digests (P-006-06): SHA-256 per frame and of the ordered list of per-frame digests."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path

_HEX = re.compile(r"[0-9a-f]{64}")


# ---------------------------------------------------------------------------------------------------------------------
# digests (P-006-06)
# ---------------------------------------------------------------------------------------------------------------------
def frame_digests(paths: Sequence[Path]) -> list[str]:
    """Lowercase hex SHA-256 of each file's bytes, in the order given."""
    out = []
    for p in paths:
        h = hashlib.sha256()
        with Path(p).open("rb") as f:
            for block in iter(lambda f=f: f.read(1 << 20), b""):
                h.update(block)
        out.append(h.hexdigest())
    return out


def digest_of_digests(digests: Sequence[str]) -> str:
    """SHA-256 of the raw 32-byte per-frame digests concatenated in frame order (the reading the tests fix)."""
    raw = []
    for d in digests:
        if not isinstance(d, str) or not _HEX.fullmatch(d):
            raise ValueError("a frame digest is 64 lowercase hexadecimal characters")
        raw.append(bytes.fromhex(d))
    return hashlib.sha256(b"".join(raw)).hexdigest()


def source_frames_sha256(paths: Sequence[Path]) -> str:
    if not paths:
        raise ValueError("no frames")
    return digest_of_digests(frame_digests(paths))

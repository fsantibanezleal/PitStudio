"""Streaming digests (P-008-01): `hashlib.file_digest` reads fixed blocks, so memory does not grow with the file."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path | str, *, chunk_size: int = 1 << 20) -> str:
    """Hex SHA-256 of a file, streamed. `chunk_size` only sizes the read buffer; the digest never depends on it."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256", _bufsize=chunk_size).hexdigest()


def md5_file(path: Path | str) -> str:
    """Hex MD5 of a file, streamed. Only checks a publisher checksum (Zenodo publishes MD5), never an identity."""
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, lambda: hashlib.md5(usedforsecurity=False)).hexdigest()

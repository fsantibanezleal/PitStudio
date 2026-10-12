"""Payload digests of DC-011-01 / DC-011-03 and the contract schemas (spec 011).

A Parquet payload is digested as the SHA-256 of the file. A Zarr payload is a directory: its digest is the SHA-256 of the
sorted chunk-digest listing, one line `<relative posix path> <sha256 of the file>\\n` for every file of the store, sorted by
path (spec 011 section 8; this is the form the rollout generator writes, checked against its output). Paths are relative to
the store, so the digest does not depend on where the store lives.
"""

from __future__ import annotations

import hashlib
import json
from functools import cache
from pathlib import Path
from typing import Any

_CHUNK = 1 << 20


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(_CHUNK):
            h.update(block)
    return h.hexdigest()


def zarr_digest(store: str | Path) -> str:
    """SHA-256 of the sorted listing `<relative path> <file sha256>\\n` of every file of the Zarr store."""
    root = Path(store)
    if not root.is_dir():
        raise FileNotFoundError(f"Zarr store {root} is not a directory")
    listing = sorted((p.relative_to(root).as_posix(), p) for p in root.rglob("*") if p.is_file())
    h = hashlib.sha256()
    for rel, path in listing:
        h.update(f"{rel} {file_sha256(path)}\n".encode())
    return h.hexdigest()


@cache
def load_schema(name: str) -> dict[str, Any]:
    """The JSON Schema of a contract (`granular-rollout`, `field-dataset`, `surrogate-io`, `calibration-result`).

    Looks for the promoted `contracts/<name>.schema.json` first, then the draft under `specs/011-surrogates/contracts/`,
    walking up from this module (a checkout); `PITSTUDIO_CONTRACTS` names a directory that overrides the search.
    """
    import os

    relative = [Path("contracts") / f"{name}.schema.json", Path("specs") / "011-surrogates" / "contracts" / f"{name}.schema.json"]
    override = os.environ.get("PITSTUDIO_CONTRACTS")
    candidates = [Path(override) / f"{name}.schema.json"] if override else [
        parent / rel for parent in Path(__file__).resolve().parents for rel in relative
    ]
    for path in candidates:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"schema {name}.schema.json not found (set PITSTUDIO_CONTRACTS)")

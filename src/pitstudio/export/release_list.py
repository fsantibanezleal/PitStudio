"""The release-asset upload list, DC-016-02 (FR-016-15, FR-016-16)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_TAG = re.compile(r"^assets-v\d+\.\d{2}\.\d{3}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_DRIVE = re.compile(r"^[A-Za-z]:")
_BYTES_LIMIT = 2**31


class ReleaseListError(Exception):
    """A release list entry, tag or digest that fails FR-016-16; `.entry` is the offending value."""

    def __init__(self, message: str, entry: object) -> None:
        super().__init__(f"{message}: {entry!r}")
        self.entry = entry


def _check_path(path: Any, root: Path) -> str:
    if not isinstance(path, str) or not path:
        raise ReleaseListError("release path must be a non-empty string", path)
    parts = path.split("/")
    if (
        path.startswith("/")
        or "\\" in path
        or "\x00" in path
        or _DRIVE.match(path)
        or any(p in ("", ".", "..") for p in parts)
    ):
        raise ReleaseListError("release path is absolute or has `..`, a backslash, a drive or an empty segment", path)
    base = root.resolve()
    if not (base / path).resolve().is_relative_to(base):
        raise ReleaseListError("release path resolves outside the bake root", path)
    return path


def build_release_list(entries: Sequence[Mapping[str, Any]], *, tag: str, root: Path) -> dict[str, Any]:
    """The DC-016-02 document, entries sorted by path; raises ReleaseListError for the FR-016-16 conditions."""
    if not isinstance(tag, str) or not _TAG.fullmatch(tag):
        raise ReleaseListError("release tag does not match assets-vX.YY.ZZZ", tag)
    out = []
    for entry in entries:
        path = _check_path(entry.get("path"), root)
        nbytes, sha = entry.get("bytes"), entry.get("sha256")
        if isinstance(nbytes, bool) or not isinstance(nbytes, int) or nbytes < 0:
            raise ReleaseListError("bytes must be a non-negative integer", path)
        if nbytes >= _BYTES_LIMIT:
            raise ReleaseListError("file of 2^31 bytes or more", path)
        if not isinstance(sha, str) or not _SHA.fullmatch(sha):
            raise ReleaseListError("sha256 must be 64 lower-case hex digits", path)
        out.append({"path": path, "bytes": nbytes, "sha256": sha})
    out.sort(key=lambda e: e["path"])
    return {"schema_version": "1.0", "tag": tag, "entries": out}


def release_list_bytes(doc: Mapping[str, Any]) -> bytes:
    """Deterministic UTF-8 serialisation of the document."""
    return (json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

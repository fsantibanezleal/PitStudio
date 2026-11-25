"""The local name of a downloaded file and its safety rules (FR-008-11)."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from pitstudio_pipeline.errors import UnsafePath

MAX_NAME = 200
DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)
_DRIVE = re.compile(r"^[A-Za-z]:")


def local_name(url: str, name: str | None = None) -> str:
    """The entry's `name` when given, else the percent-decoded last segment of the URL path; `UnsafePath` if unsafe."""
    candidate = name if name is not None else unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    reason = unsafe_reason(candidate)
    if reason:
        raise UnsafePath(f"local file name rejected ({reason}) for {url}"[:300])
    return candidate


def unsafe_reason(name: str) -> str | None:
    """Why `name` is not an acceptable local file name, or None."""
    if not name or name in {".", ".."}:
        return "empty or dot name"
    if "/" in name or "\\" in name:
        return "path separator"
    if _DRIVE.match(name):
        return "drive letter"
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        return "control character"
    if name.split(".", 1)[0].upper() in DEVICE_NAMES:
        return "Windows reserved device name"
    if len(name) > MAX_NAME:
        return f"longer than {MAX_NAME} characters"
    return None

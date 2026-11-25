"""TensorRT licence gate and local-only policy for bench records (FR-016-23, FR-016-33, ADR-0037).

Performance data of NVIDIA software under SLA 8.9 or TensorRT for RTX is local-only; so is every TensorRT result of a
run whose installed licence text differs from the reviewed one. A local-only record keeps its parity and fingerprint but
carries the shared constant in place of every performance value.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

PINNED_TENSORRT_LICENCE_SHA256 = "c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4"
LOCAL_ONLY_TEXT = "measured locally, not published (licence)"
LICENCE_CHANGED_NOTE = "TensorRT licence text changed since review"

_PERFORMANCE_FIELDS = (
    "latency",
    "throughput",
    "joules_per_inference",
    "energy_window_s",
    "vram_peak_bytes",
    "thermal_slowdown",
    "camera_streams",
)
_TENSORRT_BACKENDS = ("tensorrt", "ort-tensorrt")
_WITH_NUMBERS = ("pass", "rejected")


@dataclass(frozen=True)
class LicenceCheck:
    ok: bool
    sha256: str | None
    note: str | None


def read_installed_licence(dist: Any) -> bytes | None:
    """The bytes of the file named exactly `LICENSE.txt` in a distribution's file list, or None."""
    for item in dist.files or ():
        if item.name == "LICENSE.txt":
            return bytes(item.read_binary())
    return None


def check_tensorrt_licence(text: bytes | None, *, pinned_sha256: str = PINNED_TENSORRT_LICENCE_SHA256) -> LicenceCheck:
    """Compare the SHA-256 of the installed licence text with the reviewed one; a missing file fails."""
    if text is None:
        return LicenceCheck(False, None, LICENCE_CHANGED_NOTE)
    digest = hashlib.sha256(text).hexdigest()
    if digest == pinned_sha256:
        return LicenceCheck(True, digest, None)
    return LicenceCheck(False, digest, LICENCE_CHANGED_NOTE)


def apply_licence_policy(
    records: Sequence[Mapping[str, Any]],
    check: LicenceCheck,
    *,
    restricted_backends: Collection[str] = ("tensorrt-rtx",),
) -> list[dict[str, Any]]:
    """New records in input order; records that may not be published become `performance: local-only`."""
    out: list[dict[str, Any]] = []
    for record in records:
        new = copy.deepcopy(dict(record))
        restricted = new.get("backend") in restricted_backends
        licence_changed = (
            not check.ok and new.get("backend") in _TENSORRT_BACKENDS and new.get("status") in _WITH_NUMBERS
        )
        if (restricted or licence_changed) and new.get("status") in _WITH_NUMBERS:
            new["performance"] = "local-only"
            for name in _PERFORMANCE_FIELDS:
                new[name] = LOCAL_ONLY_TEXT
            if licence_changed and not restricted and check.note:
                new["notes"] = [*new.get("notes", []), check.note]
        out.append(new)
    return out

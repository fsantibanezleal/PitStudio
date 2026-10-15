"""Stale-input guard of the forecaster stages (FR-010-48, FR-002-69).

A training or evaluation manifest records the SHA-256 of every displacement series and slope section it was built from.
``run_stage`` re-reads each input before the work function is called; the first digest that differs (or a file that is
gone)
raises ``InputStaleError`` (class ``input-stale``) naming the series with the expected and the actual digest, and
nothing is
trained, predicted or scored.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

GUARDED_STAGES = ("s30_train", "s40_infer", "s50_evaluate")
_BLOCK = 1 << 20


class InputStaleError(Exception):
    """An input file no longer has the digest recorded in the manifest (``actual`` is None for a missing file)."""

    error_class = "input-stale"

    def __init__(self, series: str, expected: str, actual: str | None) -> None:
        shown = "missing" if actual is None else f"has digest {actual}"
        super().__init__(f"input-stale: {series} {shown}, the manifest records {expected}")
        self.series, self.expected, self.actual = series, expected, actual


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(_BLOCK):
            h.update(block)
    return h.hexdigest()


def verify_inputs(inputs: Sequence[Mapping[str, Any]], *, root: str | Path) -> None:
    """Check every input in manifest order and stop at the first mismatch; reads only, writes nothing."""
    base = Path(root)
    for entry in inputs:
        path = base / entry["path"]
        actual = file_digest(path) if path.is_file() else None
        if actual is None or actual != entry["sha256"]:
            raise InputStaleError(entry["id"], entry["sha256"], actual)


def run_stage(stage: str, manifest: Mapping[str, Any], *, root: str | Path, work: Callable[[], Any]) -> Any:
    """Verify ``manifest["inputs"]``, then return ``work()``; ``work`` is never called when an input is stale."""
    if stage not in GUARDED_STAGES:
        raise ValueError(f"stage must be one of {list(GUARDED_STAGES)}, got {stage!r}")
    verify_inputs(manifest.get("inputs", []), root=root)
    return work()

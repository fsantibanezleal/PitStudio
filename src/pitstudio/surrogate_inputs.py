"""Stale-input guard of the training and evaluation stages (FR-011-51).

A training manifest records the SHA-256 of every rollout file and field dataset it was built from. `run_stage` re-reads each
file before the work function is called; the first digest that differs raises `InputStaleError` (class `input-stale`,
FR-002-69) naming the file with the expected and the actual digest, and nothing is trained or scored.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

GUARDED_STAGES = ("s30_train", "s50_evaluate")
_BLOCK = 1 << 20


class InputStaleError(Exception):
    """An input file no longer has the digest recorded in the manifest."""

    error_class = "input-stale"

    def __init__(self, file: str, expected: str, actual: str) -> None:
        super().__init__(f"input-stale: {file} has digest {actual}, the manifest records {expected}")
        self.file, self.expected, self.actual = file, expected, actual


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(_BLOCK):
            h.update(block)
    return h.hexdigest()


def verify_inputs(inputs: Sequence[Mapping[str, Any]], *, root: str | Path) -> None:
    """Check every input in manifest order and stop at the first mismatch; reads only, writes nothing."""
    base = Path(root)
    for entry in inputs:
        actual = _digest(base / entry["path"])
        if actual != entry["sha256"]:
            raise InputStaleError(entry["id"], entry["sha256"], actual)


def run_stage(stage: str, manifest: Mapping[str, Any], *, root: str | Path, work: Callable[[], Any]) -> Any:
    """Verify `manifest["inputs"], then return `work()`; `work` is never called when an input is stale."""
    if stage not in GUARDED_STAGES:
        raise ValueError(f"stage must be one of {list(GUARDED_STAGES)}, got {stage!r}")
    verify_inputs(manifest.get("inputs", []), root=root)
    return work()

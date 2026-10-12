"""Fixture propagation (FR-011-49): a contract-fixture dataset runs through the stages but publishes no result.

The flag is read from the dataset manifest (`fixture`, FR-000-23); it must be a JSON boolean, never coerced.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def is_fixture(dataset_manifest: Mapping[str, Any] | None) -> bool:
    """True iff `dataset_manifest["fixture"]` is True; absent (or no manifest) is False; a non-boolean raises
    ValueError."""
    if not dataset_manifest or "fixture" not in dataset_manifest:
        return False
    flag = dataset_manifest["fixture"]
    if not isinstance(flag, bool):
        raise ValueError(f"fixture must be a boolean, got {flag!r}")
    return flag


def stamp(artefact: Mapping[str, Any], dataset_manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    """A shallow copy of `artefact` flagged `fixture: True` when the dataset is a fixture (the argument is
    untouched)."""
    out = dict(artefact)
    if is_fixture(dataset_manifest):
        out["fixture"] = True
    return out


def publishable(report: dict[str, Any]) -> dict[str, Any] | None:
    """None for a report whose `fixture` is True (the publish step drops it), else the report itself."""
    return None if report.get("fixture") is True else report

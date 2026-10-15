"""Fixture propagation of the forecaster stages (FR-010-46): a contract-fixture series or section runs through the
stages
but nothing computed from it is published.

The flag is read from the dataset manifest (``fixture``, FR-000-23); it must be a JSON boolean, never coerced.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def is_fixture(dataset_manifest: Mapping[str, Any] | None) -> bool:
    """True iff ``dataset_manifest["fixture"]`` is True; absent is False; a non-boolean raises ``ValueError``."""
    if not dataset_manifest or "fixture" not in dataset_manifest:
        return False
    flag = dataset_manifest["fixture"]
    if not isinstance(flag, bool):
        raise ValueError(f"fixture must be a boolean, got {flag!r}")
    return flag


def section_is_fixture(section: Mapping[str, Any]) -> bool:
    """True iff a slope-section document has ``source.kind == "fixture"``."""
    return section.get("source", {}).get("kind") == "fixture"


def stamp(artefact: Mapping[str, Any], dataset_manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    """A shallow copy of the artefact flagged ``fixture: True`` for a fixture dataset (the argument is untouched)."""
    out = dict(artefact)
    if is_fixture(dataset_manifest):
        out["fixture"] = True
    return out


def publishable(result: dict[str, Any]) -> dict[str, Any] | None:
    """None for a result whose ``fixture`` is True (the publish step drops it), else the result itself."""
    return None if result.get("fixture") is True else result


def lead_time_claims(
    alarm_summary: Sequence[Mapping[str, Any]], *, dataset_manifest: Mapping[str, Any] | None
) -> list[dict[str, Any]]:
    """The lead-time statements that may be published: none for a fixture, else one per row with a median lead time."""
    if is_fixture(dataset_manifest):
        return []
    return [
        {"method": r["method"], "stratum": r["stratum"], "median_lead_time_h": r["median_lead_time_h"]}
        for r in alarm_summary
        if "median_lead_time_h" in r
    ]

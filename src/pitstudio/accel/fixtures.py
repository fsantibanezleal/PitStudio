"""Fixture propagation (FR-016-40): an output is a fixture while any input is."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def inputs_are_fixture(*artefacts: Mapping[str, Any]) -> bool:
    """True iff any artefact mapping has `fixture is True` (only the boolean counts)."""
    return any(a.get("fixture") is True for a in artefacts)

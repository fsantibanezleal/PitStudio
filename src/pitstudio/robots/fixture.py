# SPDX-License-Identifier: Apache-2.0
"""Contract-fixture status of the IL stage inputs (FR-014-48, FR-000-23).

An IL task file, a machine parameter file or a policy handoff that is a contract fixture is run against, but every policy,
episode table and report written from it carries ``fixture: true`` and is never published as a result.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

__all__ = ["is_fixture", "is_publishable"]

_FIXTURE_FOLDERS = (("contracts", "examples"), ("data", "samples"))


def is_fixture(path: str | Path | None = None, *, flag: bool | None = None) -> bool:
    """True for an explicit flag, else for a file under ``contracts/examples/`` or ``data/samples/``."""
    if flag is not None:
        if not isinstance(flag, bool):
            raise TypeError(f"flag must be a bool or None, got {flag!r}")
        return flag
    if path is None:
        return False
    parts = [p for p in str(path).replace("\\", "/").split("/") if p]
    for folder in _FIXTURE_FOLDERS:
        for i in range(len(parts) - len(folder)):  # the file name itself is never a folder
            if tuple(parts[i : i + len(folder)]) == folder:
                return True
    return False


def is_publishable(artefact: Mapping[str, Any]) -> bool:
    """False when the artefact is marked ``fixture: true`` (only the boolean True counts)."""
    return artefact.get("fixture") is not True

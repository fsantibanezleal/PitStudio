"""Contract fixtures in the VLM stages (FR-015-50, convention of spec 008 FR-008-49).

A frame-state set or query set is a fixture when the caller says so or when its file lies under a fixture folder of the
repository: `specs/*/contracts/examples/`, `tests/` or `data/samples/`. A fixture run exercises the whole code path but
marks every record and metric `fixture: true`, computes no accuracy claim and is never published.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _parts(path: Path | str) -> tuple[str, ...]:
    return Path(os.path.normpath(os.path.abspath(path))).parts


def is_fixture(path: Path | str, *, fixture: bool | None = None, repo_root: Path) -> bool:
    """True when `fixture is True` or `path` (normalised, so `..` cannot climb out) lies in a fixture folder."""
    if fixture is not None and not isinstance(fixture, bool):
        raise TypeError("fixture must be a bool or None")
    if fixture is True:
        return True
    root, target = _parts(repo_root), _parts(path)
    if target[: len(root)] != root:
        return False
    rel = target[len(root) :]
    if rel[:1] == ("tests",) and len(rel) > 1:
        return True
    if rel[:2] == ("data", "samples") and len(rel) > 2:
        return True
    return len(rel) > 4 and rel[0] == "specs" and rel[2:4] == ("contracts", "examples")


def publishable(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The records or metrics tables not marked `fixture: true`."""
    return [dict(i) for i in items if i.get("fixture") is not True]


def assert_publishable(obj: Mapping[str, Any]) -> None:
    """Raise ValueError when a record or metrics table is marked as a fixture."""
    if obj.get("fixture") is True:
        raise ValueError("a fixture record or metrics table must not be published")

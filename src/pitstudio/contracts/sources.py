"""Strict loader of the source registry with the per-file licence-class rule (FR-001-58)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitstudio.contracts.io import ContractError, load_yaml
from pitstudio.contracts.licence import RANK, source_class_of
from pitstudio.contracts.validate import validate

SOURCES_MAX_BYTES = 1_048_576  # data-model 1.4
TOO_PERMISSIVE = "source-class-too-permissive"


def too_permissive_entries(registry: Any) -> list[tuple[int, str, str]]:
    """(entry index, entry id, message) of every entry whose class is lower than one of its per-file overrides."""
    out: list[tuple[int, str, str]] = []
    entries = registry.get("sources") if isinstance(registry, dict) else None
    for index, entry in enumerate(entries if isinstance(entries, list) else []):
        if not isinstance(entry, dict) or entry.get("licence_class") not in RANK:
            continue
        for file_index, file in enumerate(entry.get("files") or []):
            override = file.get("spdx") if isinstance(file, dict) else None
            file_class = source_class_of(override, entry.get("kind", "")) if isinstance(override, str) else None
            if file_class and RANK[entry["licence_class"]] < RANK[file_class]:
                out.append(
                    (
                        index,
                        str(entry.get("id")),
                        f"entry {entry.get('id')}: licence_class {entry['licence_class']} is less restrictive than "
                        f"{file_class} of file {file_index} ({override})",
                    )
                )
                break
    return out


def load_sources(path: Path) -> dict[str, Any]:
    """Load and validate ``data/sources.yaml``; a rejected file returns no partial registry."""
    path = Path(path)
    registry = load_yaml(path, max_bytes=SOURCES_MAX_BYTES)
    errors = validate(registry, "sources")
    if errors:
        first = errors[0]
        raise ContractError(
            f"{first.message} (and {len(errors) - 1} more)" if len(errors) > 1 else first.message,
            file=path.name,
            pointer=first.pointer,
        )
    for _, _entry_id, message in too_permissive_entries(registry):
        raise ContractError(message, file=path.name, error_class=TOO_PERMISSIVE)
    assert isinstance(registry, dict)
    return registry

"""Contract documents of this lane: schema lookup (promoted folder first, then the spec drafts) and validation.

The four schemas of spec 008 (`fetch-record`, `ingestion-report`, `split`, `data-card`) are drafts under
`specs/008-data-pipeline/contracts/` until T-008-001 promotes them to `contracts/`; both places are searched, so the
promotion needs no code change. Schemas refer to each other by `$id`, so one registry holds them all.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from pitstudio_pipeline.paths import find_repo_root


def _folders() -> list[Path]:
    root = find_repo_root()
    return [
        root / "specs" / "001-contracts" / "contracts",
        root / "specs" / "008-data-pipeline" / "contracts",
        root / "contracts",
    ]


def schema_path(name: str) -> Path:
    """Path of `<name>` (e.g. `split.schema.json`): the promoted copy when it exists, else the spec draft."""
    for folder in reversed(_folders()):
        if (folder / name).is_file():
            return folder / name
    raise FileNotFoundError(name)


@cache
def _registry() -> Registry:
    registry: Registry = Registry()
    for folder in _folders():  # later folders win: the promoted schemas replace the drafts
        for path in sorted(folder.glob("*.schema.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            registry = registry.with_resource(doc["$id"], Resource.from_contents(doc, DRAFT202012))
    return registry


@cache
def _validator(name: str) -> Draft202012Validator:
    schema = json.loads(schema_path(name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=_registry())


def schema_errors(name: str, document: Any) -> list[tuple[str, str]]:
    """Every violation of `document` against the schema `name` as (JSON pointer, message), sorted by pointer."""
    out = []
    for error in _validator(name).iter_errors(document):
        pointer = "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in error.absolute_path)
        out.append((pointer, error.message[:200]))
    return sorted(out)

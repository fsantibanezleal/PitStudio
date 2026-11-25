"""Test support: JSON Schema registry over the contracts folder (reference validator: Python `jsonschema`).

`validator(stem, target="#")` returns a Draft 2020-12 validator for `contracts/<stem>.schema.json` (or one of its
`$defs`), with every sibling schema registered by `$id` so cross-file `$ref`s such as
`manifest.schema.json#/$defs/stage_key` resolve. A schema that is not promoted to `contracts/` yet is read from its
spec's draft folder (specs/00N-*/contracts/), so tests of the behaviour can run before the promotion task is done.
Never imports first-party runner code.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[2]
DRAFT_DIRS = [
    ROOT / "specs" / "001-contracts" / "contracts",
    ROOT / "specs" / "002-runner" / "contracts",
    ROOT / "specs" / "003-console" / "contracts",
]


def schema_path(stem: str) -> Path:
    promoted = ROOT / "contracts" / f"{stem}.schema.json"
    if promoted.is_file():
        return promoted
    for d in DRAFT_DIRS:
        if (d / f"{stem}.schema.json").is_file():
            return d / f"{stem}.schema.json"
    raise FileNotFoundError(f"no schema {stem}")


@cache
def _registry() -> Registry:
    reg: Registry = Registry()
    stems = {
        p.name.removesuffix(".schema.json")
        for d in [ROOT / "contracts", *DRAFT_DIRS]
        if d.is_dir()
        for p in d.glob("*.schema.json")
    }
    for stem in sorted(stems):
        doc = json.loads(schema_path(stem).read_text(encoding="utf-8"))
        reg = reg.with_resource(doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012))
    return reg


def validator(stem: str, target: str = "#") -> Draft202012Validator:
    doc = json.loads(schema_path(stem).read_text(encoding="utf-8"))
    schema: dict[str, Any] = doc if target == "#" else {"$ref": f"{doc['$id']}{target}"}
    return Draft202012Validator(schema, registry=_registry(), format_checker=FormatChecker())


def errors(stem: str, instance: Any, target: str = "#") -> list[str]:
    """Sorted `pointer: message` strings; an empty list means valid."""
    v = validator(stem, target)
    return sorted(f"/{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in v.iter_errors(instance))

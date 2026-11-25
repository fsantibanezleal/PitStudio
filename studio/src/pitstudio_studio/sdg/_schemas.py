"""Schema lookup of the SDG modules: the promoted contracts of the repository (`contracts/`), one registry for all."""

from __future__ import annotations

import json
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from pitstudio.contracts.io import pointer_of
from pitstudio.contracts.validate import CONTRACTS_DIR


@cache
def _registry() -> Registry:
    registry: Registry = Registry()
    for path in sorted(CONTRACTS_DIR.glob("*.schema.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(doc["$id"], Resource.from_contents(doc, DRAFT202012))
    return registry


@cache
def validator(name: str, definition: str | None = None) -> Draft202012Validator:
    """Validator of the schema file `<name>.schema.json`, or of its `$defs/<definition>`."""
    schema = json.loads((CONTRACTS_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    if definition is not None:
        schema = {"$ref": schema["$id"] + "#/$defs/" + definition}
    return Draft202012Validator(schema, registry=_registry())


def best_error(name: str, document: Any, definition: str | None = None) -> tuple[str, str] | None:
    """The most relevant violation (jsonschema `best_match`: descends into `oneOf` branches) as (pointer, message)."""
    error = best_match(validator(name, definition).iter_errors(document))
    if error is None:
        return None
    return pointer_of(list(error.absolute_path)), error.message[:300]


def schema_errors(name: str, document: Any, definition: str | None = None) -> list[tuple[str, str]]:
    """Every violation of `document` as (JSON pointer, message), shallowest pointer first then by pointer."""
    found = [
        (pointer_of(list(e.absolute_path)), e.message[:300]) for e in validator(name, definition).iter_errors(document)
    ]
    found.sort(key=lambda item: (item[0].count("/"), item[0], item[1]))
    return found

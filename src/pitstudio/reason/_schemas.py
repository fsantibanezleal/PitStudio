"""One schema registry for the reason package: every contract in `contracts/` is a resource, so cross-schema `$ref`s
(for example `frame-state.schema.json#/$defs/condition`) resolve. Validators are built once per schema file."""

from __future__ import annotations

import functools
import json
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from pitstudio.contracts.validate import CONTRACTS_DIR


@functools.cache
def registry() -> Registry:
    reg: Registry = Registry()
    for path in sorted(CONTRACTS_DIR.glob("*.schema.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        reg = reg.with_resource(doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012))
    return reg


@functools.cache
def validator(name: str, fragment: str = "") -> Draft202012Validator:
    """Validator of `contracts/<name>`, or of one definition of it (`fragment` such as `#/$defs/row_a`)."""
    schema = json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))
    if fragment:
        schema = {"$ref": schema["$id"] + fragment}
    return Draft202012Validator(schema, registry=registry())


def errors(doc: Any, name: str, fragment: str = "") -> list[Any]:
    """Every violation of the schema by `doc`, sorted by path (empty list: valid)."""
    found = list(validator(name, fragment).iter_errors(doc))
    return sorted(found, key=lambda e: [str(p) for p in e.absolute_path])


def pointer(error: Any) -> str:
    return "/".join(str(p) for p in error.absolute_path) or "<document>"

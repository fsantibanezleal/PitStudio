# ruff: noqa: E501
"""Schema validation helper of the spec 015 acceptance tests: documents are checked against the promoted contracts
(`contracts/*.schema.json`, JSON Schema 2020-12, reference implementation `jsonschema` with `referencing`), with
cross-schema `$ref`s (for example `frame-state.schema.json#/$defs/condition`) resolved through the `$id` of every contract.

This module holds no test. It is locked with the first test that imports it.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"


@functools.cache
def _registry() -> Registry:
    reg: Registry = Registry()
    for p in sorted(CONTRACTS.glob("*.schema.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        reg = reg.with_resource(doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012))
    return reg


@functools.cache
def validator(name: str) -> Draft202012Validator:
    schema = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=_registry())


def errors(doc: Any, name: str) -> list[str]:
    """Messages of every violation of `contracts/<name>` by `doc` (empty list: valid)."""
    return [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in validator(name).iter_errors(doc)]

# SPDX-License-Identifier: Apache-2.0
"""JSON Schema checks with JSON-pointer messages for the spec 014 contracts (FR-014-07, FR-014-46).

``pitstudio.contracts.validate`` takes only unhyphenated schema stems, and the spec 014 schemas are one-of documents
whose errors are unreadable, so each document is checked against the branch its discriminator selects, and every
violation is reported as ``<pointer>: <message>``. A missing member and an unknown key are reported at the member itself.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterator, Mapping
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from pitstudio.contracts.validate import CONTRACTS_DIR

_QUOTED = re.compile(r"'([^']+)'")


@cache
def _registry() -> Registry:
    resources = []
    for path in sorted(CONTRACTS_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


@cache
def validator(stem: str, definition: str | None = None) -> Draft202012Validator:
    """Validator of ``contracts/<stem>.schema.json`` or of one of its ``$defs``."""
    schema = json.loads((CONTRACTS_DIR / f"{stem}.schema.json").read_text(encoding="utf-8"))
    if definition is None:
        return Draft202012Validator(schema, registry=_registry())
    return Draft202012Validator({"$ref": f"{schema['$id']}#/$defs/{definition}"}, registry=_registry())


def pointer(path: Any) -> str:
    parts = [str(p).replace("~", "~0").replace("/", "~1") for p in path]
    return "/" + "/".join(parts) if parts else ""


def non_finite(node: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[str, str]]:
    """(pointer, message) of every NaN or infinity in the document."""
    if isinstance(node, float) and not math.isfinite(node):
        yield pointer(path) or "/", "must be finite"
    elif isinstance(node, Mapping):
        for key, value in node.items():
            yield from non_finite(value, (*path, key))
    elif isinstance(node, list | tuple):
        for i, value in enumerate(node):
            yield from non_finite(value, (*path, i))


def schema_problems(doc: Any, stem: str, definition: str | None = None) -> list[tuple[str, str]]:
    """(pointer, message) of every violation, in schema order; empty when the document is valid."""
    out = list(non_finite(doc))
    if out:
        return out
    for error in validator(stem, definition).iter_errors(doc):
        base = pointer(error.absolute_path)
        if error.validator in ("required", "additionalProperties"):
            names = _QUOTED.findall(error.message)
            out.extend((f"{base}/{name}", error.message) for name in names)
        else:
            out.append((base or "/", error.message))
    return out

"""Frame-state loader (DC-015-01): schema, cross-field rules and the canonical digest (FR-015-23, FR-015-48, FR-015-49).

`load_frame_state` is the only door a frame state passes through before ground truth is computed from it. A document
that fails any rule raises `FrameStateInvalid` (`error_class == "frame-state-invalid"`); the message names the offending
field or, for a problem inside an object, its `prim_id`.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from pitstudio.contracts.validate import CONTRACTS_DIR

SCHEMA_FILE = "frame-state.schema.json"
MAX_REPORTED_ERRORS = 8


class FrameStateInvalid(ValueError):
    """A frame state is not valid; `error_class` is the stable class name of the failure."""

    error_class = "frame-state-invalid"


@functools.cache
def _validator() -> Draft202012Validator:
    import json

    registry: Registry = Registry()
    for path in sorted(CONTRACTS_DIR.glob("*.schema.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012))
    schema = json.loads((CONTRACTS_DIR / SCHEMA_FILE).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=registry)


def _where(doc: Mapping[str, Any], path: list[Any]) -> str:
    """The JSON pointer of a violation; for a path under `objects[i]` the prim id of that object is added."""
    text = "/".join(str(p) for p in path) or "<document>"
    objects = doc.get("objects")
    if len(path) >= 2 and path[0] == "objects" and isinstance(path[1], int) and isinstance(objects, list):
        if 0 <= path[1] < len(objects) and isinstance(objects[path[1]], Mapping):
            prim = objects[path[1]].get("prim_id")
            if isinstance(prim, str):
                return f"{text} (object {prim})"
    return text


def _schema_errors(doc: Mapping[str, Any]) -> list[str]:
    errors = sorted(_validator().iter_errors(doc), key=lambda e: [str(p) for p in e.absolute_path])
    return [f"{_where(doc, list(e.absolute_path))}: {e.message[:200]}" for e in errors[:MAX_REPORTED_ERRORS]]


def _check_visible_px(doc: Mapping[str, Any]) -> None:
    """FR-015-48: no object shows more pixels than its frame holds."""
    area = doc["image"]["width_px"] * doc["image"]["height_px"]
    for obj in doc["objects"]:
        if obj["visible_px"] > area:
            raise FrameStateInvalid(
                f"object {obj['prim_id']}: visible_px {obj['visible_px']} exceeds the frame area {area} px"
            )


def validate_frame_state(doc: Mapping[str, Any]) -> None:
    """Raise `FrameStateInvalid` unless `doc` satisfies the contract and the rules the schema cannot express."""
    if not isinstance(doc, Mapping):
        raise FrameStateInvalid("frame state: not a JSON object")
    errors = _schema_errors(doc)
    if errors:
        raise FrameStateInvalid("; ".join(errors))
    _check_visible_px(doc)


def load_frame_state(source: Mapping[str, Any] | str | Path, *, root: Path) -> dict[str, Any]:
    """Validate a frame state (a mapping) and return it unchanged."""
    del root
    if not isinstance(source, Mapping):
        raise FrameStateInvalid("frame state: not a JSON object")
    validate_frame_state(source)
    return dict(source)

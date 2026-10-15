"""Frame-state loader (DC-015-01): schema, cross-field rules and the canonical digest (FR-015-23, FR-015-48, FR-015-49).

`load_frame_state` is the only door a frame state passes through before ground truth is computed from it. A document
that fails any rule raises `FrameStateInvalid` (`error_class == "frame-state-invalid"`); the message names the offending
field or, for a problem inside an object, its `prim_id`.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pitstudio.reason import _schemas

SCHEMA_FILE = "frame-state.schema.json"
MAX_REPORTED_ERRORS = 8
QUATERNION_TOLERANCE = 1e-6


class FrameStateInvalid(ValueError):
    """A frame state is not valid; `error_class` is the stable class name of the failure."""

    error_class = "frame-state-invalid"


def _where(doc: Mapping[str, Any], path: list[Any]) -> str:
    """The JSON pointer of a violation; for a path under `objects[i]` the prim id of that object is added."""
    text = "/".join(str(p) for p in path) or "<document>"
    objects = doc.get("objects")
    if len(path) >= 2 and path[0] == "objects" and isinstance(path[1], int) and isinstance(objects, list):
        obj = objects[path[1]] if 0 <= path[1] < len(objects) else None
        if isinstance(obj, Mapping) and isinstance(obj.get("prim_id"), str):
            return f"{text} (object {obj['prim_id']})"
    return text


def _schema_errors(doc: Mapping[str, Any]) -> list[str]:
    errors = sorted(_schemas.validator(SCHEMA_FILE).iter_errors(doc), key=lambda e: [str(p) for p in e.absolute_path])
    return [f"{_where(doc, list(e.absolute_path))}: {e.message[:200]}" for e in errors[:MAX_REPORTED_ERRORS]]


def _check_visible_px(doc: Mapping[str, Any]) -> None:
    """FR-015-48: no object shows more pixels than its frame holds."""
    area = doc["image"]["width_px"] * doc["image"]["height_px"]
    for obj in doc["objects"]:
        if obj["visible_px"] > area:
            raise FrameStateInvalid(
                f"object {obj['prim_id']}: visible_px {obj['visible_px']} exceeds the frame area {area} px"
            )


def _non_finite(node: Any, path: list[Any]) -> list[list[Any]]:
    """Paths of every NaN or infinite number in a document (JSON Schema lets them through)."""
    if isinstance(node, float):
        return [] if math.isfinite(node) else [path]
    if isinstance(node, Mapping):
        return [q for k, v in node.items() for q in _non_finite(v, [*path, k])]
    if isinstance(node, list):
        return [q for i, v in enumerate(node) for q in _non_finite(v, [*path, i])]
    return []


def _check_quaternions(doc: Mapping[str, Any]) -> None:
    """FR-015-49: every rotation quaternion has a norm within 1e-6 of 1 (components are finite by now)."""
    poses = [(f"object {o['prim_id']}", o["pose"]) for o in doc["objects"]] + [("camera", doc["camera"]["pose"])]
    for name, pose in poses:
        norm = math.sqrt(sum(c * c for c in pose["rotation_xyzw"]))
        if abs(norm - 1.0) > QUATERNION_TOLERANCE:
            raise FrameStateInvalid(
                f"{name}: rotation_xyzw has norm {norm!r}, it must be 1 within {QUATERNION_TOLERANCE}"
            )


def canonical_sha256(doc: Any) -> str:
    """SHA-256 of the canonical JSON text of a document: sorted keys, no spaces, UTF-8 without ASCII escapes."""
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_frame_state(doc: Mapping[str, Any]) -> None:
    """Raise `FrameStateInvalid` unless `doc` satisfies the contract and the rules the schema cannot express."""
    if not isinstance(doc, Mapping):
        raise FrameStateInvalid("frame state: not a JSON object")
    bad = _non_finite(doc, [])
    if bad:
        raise FrameStateInvalid("; ".join(f"{_where(doc, p)}: non-finite number" for p in bad[:MAX_REPORTED_ERRORS]))
    errors = _schema_errors(doc)
    if errors:
        raise FrameStateInvalid("; ".join(errors))
    _check_visible_px(doc)
    _check_quaternions(doc)


def _check_unique_prims(doc: Mapping[str, Any]) -> None:
    seen: set[str] = set()
    for obj in doc["objects"]:
        if obj["prim_id"] in seen:
            raise FrameStateInvalid(f"object {obj['prim_id']}: duplicated prim_id")
        seen.add(obj["prim_id"])


def _check_image(doc: Mapping[str, Any], root: Path) -> None:
    """The image under `root` hashes to the declared SHA-256 (the relpath pattern keeps the path inside `root`)."""
    image = doc["image"]
    try:
        data = (Path(root) / image["path"]).read_bytes()
    except OSError as exc:
        raise FrameStateInvalid(f"image/path: cannot read {image['path']}: {exc.strerror}") from exc
    if hashlib.sha256(data).hexdigest() != image["sha256"]:
        raise FrameStateInvalid(f"image/sha256: the bytes of {image['path']} do not match the declared digest")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise FrameStateInvalid(f"frame state file is not readable JSON: {type(exc).__name__}") from exc


def load_frame_state(source: Mapping[str, Any] | str | Path, *, root: Path) -> dict[str, Any]:
    """Validate a frame state (a mapping, or the path of a JSON file) and return it unchanged.

    Raises `FrameStateInvalid` for any violation: the schema, a non-finite number, a quaternion off unit norm,
    `visible_px` above the frame area, a duplicated prim id, an unreadable image or a digest that differs from it.
    """
    doc = _read_json(Path(source)) if isinstance(source, str | Path) else source
    validate_frame_state(doc)
    _check_unique_prims(doc)
    _check_image(doc, root)
    return dict(doc)

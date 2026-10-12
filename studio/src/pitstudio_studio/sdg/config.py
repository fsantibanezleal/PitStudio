"""The randomisation config guard of `st55_sdg` (FR-009-09): a bad config is rejected before any rendering.

`validate_config` reports the JSON pointer of the first error: a non-finite number, then any violation of
`sdg-randomisation.schema.json`, then a texture id of a lithology list that is not in the texture pool.
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pitstudio.contracts.io import pointer_of
from pitstudio_studio.sdg._schemas import schema_errors

_SCHEMA = "sdg-randomisation"
_REJECTED = 2  # exit status of a rejected config


class SdgConfigError(ValueError):
    """The config is rejected: `pointer` is the RFC 6901 pointer of the first error ("" for the root)."""

    def __init__(self, pointer: str, reason: str) -> None:
        self.pointer = pointer
        self.reason = reason
        super().__init__(f"{pointer or '<root>'}: {reason}")


def _non_finite(node: Any, path: list[Any]) -> list[Any] | None:
    """Path of the first non-finite number below `node`, depth first in document order."""
    if isinstance(node, float) and not math.isfinite(node):
        return path
    if isinstance(node, dict):
        for key, value in node.items():
            found = _non_finite(value, [*path, key])
            if found is not None:
                return found
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found = _non_finite(value, [*path, i])
            if found is not None:
                return found
    return None


def validate_config(doc: object) -> None:
    """Raise `SdgConfigError` for the first error of `doc`; return `None` when it is a valid config."""
    bad = _non_finite(doc, [])
    if bad is not None:
        raise SdgConfigError(pointer_of(bad), "number is not finite")
    errors = schema_errors(_SCHEMA, doc)
    if errors:
        pointer, message = errors[0]
        raise SdgConfigError(pointer, message)
    assert isinstance(doc, dict)  # the schema root is an object
    pool = {t["id"] for t in doc["texture_pool"]}
    for litho, ids in doc["structured"]["rock_textures"]["lithologies"].items():
        for i, texture_id in enumerate(ids):
            if texture_id not in pool:
                pointer = pointer_of(["structured", "rock_textures", "lithologies", litho, i])
                raise SdgConfigError(pointer, f"texture id {texture_id!r} is not in the texture pool")


def load_config(path: Path) -> dict[str, Any]:
    """Read and validate the config file at `path`; every failure is a `SdgConfigError`."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise SdgConfigError("", f"cannot read the config file: {exc.strerror or type(exc).__name__}") from None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise SdgConfigError("", "the config file is not UTF-8") from None
    if not text.strip():
        raise SdgConfigError("", "the config file is empty")
    try:
        # NaN / Infinity tokens become floats, so that `validate_config` reports the pointer of the number
        doc = json.loads(text, parse_constant=float)
    except ValueError, RecursionError:
        raise SdgConfigError("", "the config file is not valid JSON") from None
    validate_config(doc)
    assert isinstance(doc, dict)
    return doc


def run_guarded(config_path: Path, render: Callable[[dict[str, Any]], object]) -> int:
    """Stage entry: validate the config, then render. A rejected config never reaches `render`; status 2."""
    try:
        config = load_config(config_path)
    except SdgConfigError as exc:
        print(f"sdg config rejected at {exc.pointer or '<root>'}: {exc.reason}", file=sys.stderr)
        return _REJECTED
    render(config)
    return 0

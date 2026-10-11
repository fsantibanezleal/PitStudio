"""Schema validation plus the post-schema rules of data-model 1.3 (FR-001-08, -54, -55, -56, -57).

``validate(document, schema_name)`` reports every violation, each with its JSON pointer, the failing keyword and a
message of at most 300 characters without an absolute path, sorted by pointer. ``schema_name`` is the stem of a file
in ``contracts/`` (``recipe``) or a definition of it (``recipe#/$defs/job_request``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from pitstudio.contracts.io import ContractError, pointer_of
from pitstudio.contracts.privacy import scrub_paths

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts"
MAX_MESSAGE = 300
WINDOWS_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)
_CONTROL = re.compile(r"[\x00-\x1f]")
_INPUT_OUTPUT_REF = re.compile(r"/inputs/[0-9]+/output$")
_PATH_PATTERNS = ("^data/cards/", "^docs/frameworks/")
_DUPLICATE_LISTS = {"manifest": ("artefacts",), "tools": ("tools",), "sources": ("sources",)}


@dataclass(frozen=True)
class ValidationError:
    """One violation: JSON pointer, failing keyword, bounded message."""

    pointer: str
    keyword: str
    message: str


@lru_cache(maxsize=1)
def _registry() -> Registry:
    resources = []
    for path in sorted(CONTRACTS_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


@cache
def _schema(stem: str) -> dict[str, Any]:
    path = CONTRACTS_DIR / f"{stem}.schema.json"
    if not re.fullmatch(r"[a-z]+", stem) or not path.is_file():
        raise ContractError(f"unknown schema {stem!r}")
    schema: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return schema


@cache
def _validator(name: str) -> tuple[Draft202012Validator, str]:
    stem, _, fragment = name.partition("#")
    schema = _schema(stem)
    if fragment:
        return Draft202012Validator({"$ref": schema["$id"] + "#" + fragment}, registry=_registry()), stem
    return Draft202012Validator(schema, registry=_registry()), stem


def _short(instance: Any) -> str:
    if isinstance(instance, str):
        return f"<string of {len(instance)} characters>"
    if isinstance(instance, dict):
        return "<object>"
    if isinstance(instance, list):
        return "<array>"
    return repr(instance)


def _bounded(message: str) -> str:
    message = scrub_paths(message)
    return message if len(message) <= MAX_MESSAGE else message[: MAX_MESSAGE - 3] + "..."


def _schema_message(error: Any) -> str:
    message: str = error.message
    for shown in (repr(error.instance), json.dumps(error.instance, ensure_ascii=False, default=str)):
        if len(shown) > 24 and shown in message:
            message = message.replace(shown, _short(error.instance))
    return _bounded(message)


# ----------------------------------------------------------------------------------------------------------------
# schema-driven walk: strings with a pattern, and relative paths
# ----------------------------------------------------------------------------------------------------------------
Leaf = tuple[list[Any], bool, bool]  # (path, the schema constrains it by pattern, it is a relative path)


def _walk(schema: Any, instance: Any, path: list[Any], base: Any, out: list[Leaf], depth: int = 0) -> None:
    """Collect every string leaf of ``instance``; every branch of a combinator is visited (over-approximation)."""
    if depth > 40 or not isinstance(schema, dict):
        return
    ref = schema.get("$ref")
    if ref is not None:
        resolved = base.lookup(ref)
        is_path = ref.rsplit("/", 1)[-1] in ("relpath", "relglob")
        found: list[Leaf] = []
        _walk(resolved.contents, instance, path, resolved.resolver, found, depth + 1)
        out.extend((p, pattern, rel or is_path) for p, pattern, rel in found)
    if isinstance(instance, str) and "pattern" in schema:
        out.append((path, True, schema["pattern"].startswith(_PATH_PATTERNS)))
    for key in ("allOf", "anyOf", "oneOf"):
        for branch in schema.get(key, ()):
            _walk(branch, instance, path, base, out, depth + 1)
    for key in ("if", "then", "else"):
        if key in schema:
            _walk(schema[key], instance, path, base, out, depth + 1)
    if isinstance(instance, dict):
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties")
        for key, value in instance.items():
            if key in props:
                _walk(props[key], value, [*path, key], base, out, depth + 1)
            elif isinstance(extra, dict):
                _walk(extra, value, [*path, key], base, out, depth + 1)
    elif isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, value in enumerate(instance):
                _walk(items, value, [*path, index], base, out, depth + 1)


def _at(document: Any, path: list[Any]) -> Any:
    node = document
    for part in path:
        node = node[part]
    return node


def _device_segment(value: str) -> bool:
    return any(seg.split(".", 1)[0].upper() in WINDOWS_DEVICE_NAMES for seg in value.split("/"))


def _post_strings(stem: str, document: Any, validator: Draft202012Validator) -> Iterator[ValidationError]:
    """FR-001-56 (device names, case-folded duplicates in one list) and FR-001-57 (control characters)."""
    leaves: list[Leaf] = []
    _walk(validator.schema, document, [], _registry().resolver(_schema(stem)["$id"]), leaves)
    seen: dict[tuple[str, str], dict[str, str]] = {}
    done: set[tuple[str, str]] = set()
    for path, has_pattern, is_path in leaves:
        value = _at(document, path)
        pointer = pointer_of(path)
        if has_pattern and (match := _CONTROL.search(value)):
            yield ValidationError(
                pointer, "control-char", f"control character U+{ord(match.group(0)):04X} in a string with a pattern"
            )
        if not is_path:
            continue
        if _device_segment(value):
            yield ValidationError(pointer, "device-name", "a path segment is a Windows reserved device name")
        numeric = [i for i, part in enumerate(path) if isinstance(part, int)]
        if not numeric or _INPUT_OUTPUT_REF.search(pointer):
            continue
        cut = numeric[-1]
        group = (pointer_of(path[:cut]), pointer_of(path[cut + 1 :]))
        folded = value.casefold()
        if (pointer, folded) in done:
            continue
        done.add((pointer, folded))
        known = seen.setdefault(group, {})
        if folded in known:
            yield ValidationError(
                pointer, "duplicate-path", _bounded(f"path equal after case folding to the one at {known[folded]}")
            )
        else:
            known[folded] = pointer


def _post_duplicates(stem: str, document: Any) -> Iterator[ValidationError]:
    """FR-001-54: an id used twice in one list is reported at the later entry and names the first."""
    if not isinstance(document, dict):
        return
    for key in _DUPLICATE_LISTS.get(stem, ()):
        entries = document.get(key)
        if not isinstance(entries, list):
            continue
        first: dict[str, int] = {}
        for index, entry in enumerate(entries):
            ident = entry.get("id") if isinstance(entry, dict) else None
            if not isinstance(ident, str):
                continue
            if ident in first:
                yield ValidationError(
                    f"/{key}/{index}", "duplicate-id", _bounded(f"id {ident!r} already used at /{key}/{first[ident]}")
                )
            else:
                first[ident] = index


def _post_shards(document: Any) -> Iterator[ValidationError]:
    """FR-001-55: ``shards.done`` may not exceed ``shards.total``."""
    stages = document.get("stages") if isinstance(document, dict) else None
    if not isinstance(stages, list):
        return
    for index, stage in enumerate(stages):
        shards = stage.get("shards") if isinstance(stage, dict) else None
        if not isinstance(shards, dict):
            continue
        done, total = shards.get("done"), shards.get("total")
        if all(isinstance(v, int) and not isinstance(v, bool) for v in (done, total)) and done > total:
            yield ValidationError(
                f"/stages/{index}/shards/done", "shards", f"shards.done ({done}) is greater than shards.total ({total})"
            )


def validate(document: Any, schema_name: str) -> list[ValidationError]:
    """Every violation of ``document`` against ``schema_name``, sorted by pointer."""
    validator, stem = _validator(schema_name)
    if stem == "manifest" and "#" not in schema_name and isinstance(document, dict):
        kind = document.get("kind")
        if kind in ("run", "web-index"):
            validator, stem = _validator("manifest#/$defs/" + kind.replace("-", "_"))
    errors = [
        ValidationError(pointer_of(list(error.absolute_path)), str(error.validator), _schema_message(error))
        for error in validator.iter_errors(document)
    ]
    errors.extend(_post_strings(stem, document, validator))
    errors.extend(_post_duplicates(stem, document))
    errors.extend(_post_shards(document))
    errors.sort(key=lambda e: (e.pointer, e.keyword, e.message))
    return errors

"""Schema validation plus the post-schema rules of data-model 1.3 (FR-001-08, -54, -55, -56, -57).

``validate(document, schema_name)`` reports every violation, each with its JSON pointer, the failing keyword and a
message of at most 300 characters without an absolute path, sorted by pointer. ``schema_name`` is the stem of a file
in ``contracts/`` (``recipe``) or a definition of it (``recipe#/$defs/job_request``).
"""

from __future__ import annotations

import json
import re
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
    errors.sort(key=lambda e: (e.pointer, e.keyword, e.message))
    return errors

"""FoS and PoF results loader with the section digest check (FR-010-45, DC-010-04).

``section_sha256`` of every ``slope-results`` entry must be the SHA-256 of the RFC 8785 canonical JSON of the section it
names (``pitstudio.contracts.jcs.canonicalize``); a different value is rejected with error class
``section-digest-mismatch`` naming the field.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator

from pitstudio.contracts.io import pointer_of
from pitstudio.contracts.jcs import canonicalize
from pitstudio.contracts.validate import CONTRACTS_DIR


class ResultsError(ValueError):
    """A results document that cannot be trusted: ``error_class`` is ``section-digest-mismatch``, ``section-missing`` or
    ``results-invalid``; ``field`` is the JSON pointer."""

    def __init__(self, error_class: str, field: str, message: str) -> None:
        super().__init__(f"{error_class}: {field}: {message}")
        self.error_class = error_class
        self.field = field


@dataclass(frozen=True)
class Results:
    document: dict[str, Any]
    sections: dict[str, dict[str, Any]]


def section_digest(section: dict[str, Any]) -> str:
    """SHA-256 (hex) of the RFC 8785 canonical JSON of a section document."""
    return hashlib.sha256(canonicalize(section)).hexdigest()


@cache
def _validator() -> Draft202012Validator:
    schema = json.loads((CONTRACTS_DIR / "slope-results.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def load_results(document: Any, *, sections: dict[str, dict[str, Any]]) -> Results:
    """Validate a results document and check every ``section_sha256`` against the section it names."""
    errors = sorted(_validator().iter_errors(document), key=lambda e: list(map(str, e.absolute_path)))
    if errors:
        e = errors[0]
        raise ResultsError("results-invalid", pointer_of(list(e.absolute_path)), e.message[:200])
    for i, entry in enumerate(document["sections"]):
        section_id = entry["section_id"]
        if section_id not in sections:
            raise ResultsError(
                "section-missing", f"/sections/{i}/section_id", f"no document for section {section_id!r}"
            )
        if entry["section_sha256"] != section_digest(sections[section_id]):
            raise ResultsError(
                "section-digest-mismatch",
                f"/sections/{i}/section_sha256",
                f"the digest does not match section {section_id!r}",
            )
    return Results(document, sections)

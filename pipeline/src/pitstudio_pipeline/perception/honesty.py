"""The sim-to-real honesty rules of the evaluation report and the B2 baked data (FR-009-32, SC-009-07).

While no labelled real probe exists, every report and every B2 baked data file carries `sim_to_real: "not measured"` and the
label "calibrated synthetic — not validated against real data" (U+2014) for every class, and holds no real-domain metric
field: no key whose snake_case words include `real` or `probe`, other than `sim_to_real` itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pitstudio.contracts.io import pointer_of

HONESTY_LABEL = "calibrated synthetic — not validated against real data"
NOT_MEASURED = "not measured"


class HonestyError(ValueError):
    """A violation of the honesty rules: `pointer` is the RFC 6901 pointer of the first one ("" for the root)."""

    def __init__(self, pointer: str, reason: str) -> None:
        self.pointer, self.reason = pointer, reason
        super().__init__(f"{pointer or '<root>'}: {reason}")


def _real_domain_key(key: object) -> bool:
    if not isinstance(key, str) or key == "sim_to_real":
        return False
    words = key.lower().split("_")
    return "real" in words or "probe" in words


def _walk(node: Any, path: list[Any]) -> None:
    if isinstance(node, Mapping):
        if "class" in node:
            if node.get("honesty_label") != HONESTY_LABEL:
                raise HonestyError(pointer_of(path), "an object that names a class lacks the honesty label")
            if node.get("sim_to_real") != NOT_MEASURED:
                raise HonestyError(pointer_of(path), 'an object that names a class lacks sim_to_real "not measured"')
        for key, value in node.items():
            if _real_domain_key(key):
                raise HonestyError(pointer_of([*path, key]), "a real-domain field without a labelled real probe")
            _walk(value, [*path, key])
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _walk(value, [*path, i])


def check_sim_to_real_labels(document: Mapping[str, Any]) -> None:
    """Raise `HonestyError` for the first violation of the unlabelled-document rules; a document with a `real_probe`
    object is the labelled-probe case and is not judged here (the probe block is aggregate-only by construction,
    `probe.evaluate_probe`)."""
    if not isinstance(document, Mapping):
        raise HonestyError("", "the document is not an object")
    if isinstance(document.get("real_probe"), Mapping):
        return
    if document.get("sim_to_real") != NOT_MEASURED:
        raise HonestyError("", 'sim_to_real must be "not measured" while no real probe is labelled')
    if document.get("honesty_label") != HONESTY_LABEL:
        raise HonestyError("", "the honesty label is missing or altered")
    _walk(document, [])

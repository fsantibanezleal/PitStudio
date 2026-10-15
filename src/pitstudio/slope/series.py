"""Displacement-series loader with its self-consistency rules (FR-010-44, DC-010-02), standard library plus jsonschema.

Every kind of DC-010-02 document that carries samples (synthetic event, real event, radar pixel) must have arrays of one
length, equal to ``sampling.n_samples`` where that exists, and ``t_0_h`` before ``t_f_h`` where both exist. The check
runs
first and names the offending field with error class ``series-inconsistent``; a document that fails for any other reason
(unknown kind, a schema violation) raises ``ValueError``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator

from pitstudio.contracts.io import load_json, pointer_of
from pitstudio.contracts.validate import CONTRACTS_DIR

KINDS = ("synthetic-event", "real-event", "radar-pixel", "radar-map")
_ARRAYS = ("t_h", "los_displacement_mm", "measured_los_displacement_mm", "wrap_flags")


class InvalidSeriesError(ValueError):
    """A series whose arrays, sample count or time bounds disagree (error class ``series-inconsistent``)."""

    error_class = "series-inconsistent"

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


@dataclass(frozen=True)
class Series:
    """A validated displacement series; ``t`` and ``omega`` are the sample arrays (empty for a radar map)."""

    kind: str
    document: dict[str, Any]

    @property
    def t(self) -> np.ndarray:
        return np.asarray(self.document.get("t_h", []), dtype=float)

    @property
    def omega(self) -> np.ndarray:
        return np.asarray(self.document.get("los_displacement_mm", []), dtype=float)


@cache
def _validator() -> Draft202012Validator:
    schema = json.loads((CONTRACTS_DIR / "displacement-series.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _consistency(document: dict[str, Any]) -> None:
    kind = document.get("kind")
    if kind in ("radar-map",):
        return
    arrays = {k: document[k] for k in _ARRAYS if isinstance(document.get(k), list)}
    sampling = document.get("sampling")
    n_samples = sampling.get("n_samples") if isinstance(sampling, dict) else None
    if arrays:
        lengths = {k: len(v) for k, v in arrays.items()}
        counted = isinstance(n_samples, int) and not isinstance(n_samples, bool)
        reference = n_samples if counted else lengths.get("t_h", next(iter(lengths.values())))
        for name, length in lengths.items():
            if length != reference:
                if len(set(lengths.values())) == 1:  # the arrays agree with each other, so n_samples is the odd one
                    raise InvalidSeriesError(
                        "/sampling/n_samples", f"n_samples is {n_samples} but the arrays hold {length} values"
                    )
                raise InvalidSeriesError(pointer_of([name]), f"{name} has {length} values, expected {reference}")
    t0, tf = document.get("t_0_h"), document.get("t_f_h")
    if isinstance(t0, int | float) and isinstance(tf, int | float) and not t0 < tf:
        raise InvalidSeriesError("/t_0_h", f"t_0_h {t0} must be before t_f_h {tf}")


def parse_series(document: Any) -> Series:
    """Validate a DC-010-02 document: self-consistency first (FR-010-44), then the schema."""
    if not isinstance(document, dict):
        raise ValueError("a displacement series is a JSON object")
    if document.get("kind") not in KINDS:
        raise ValueError(f"unknown series kind {document.get('kind')!r}; expected one of {list(KINDS)}")
    _consistency(document)
    errors = sorted(_validator().iter_errors(document), key=lambda e: list(map(str, e.absolute_path)))
    if errors:
        e = errors[0]
        raise ValueError(f"{pointer_of(list(e.absolute_path)) or '/'}: {e.message[:200]}")
    return Series(document["kind"], document)


def load_series(path: str | Path) -> Series:
    """Read a series file through the strict contract loader, then ``parse_series`` it."""
    return parse_series(load_json(Path(path)))

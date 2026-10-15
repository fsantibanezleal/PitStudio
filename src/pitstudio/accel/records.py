"""Bench records (DC-016-01): cell keys, the record builder and uniqueness (FR-016-32, FR-016-36)."""

from __future__ import annotations

BACKENDS = ("pytorch", "ort-cpu", "ort-cuda", "ort-tensorrt", "tensorrt", "tensorrt-rtx")
PRECISIONS = ("fp32", "fp16", "int8", "fp8")


class InvalidRecord(ValueError):
    """A record or cell key that is discarded; `.reason` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def check_cell_key(backend: str, precision: str) -> None:
    """Backend and precision must be in their enums, otherwise the measurement is discarded."""
    if backend not in BACKENDS:
        raise InvalidRecord(f"invalid measurement: backend {backend!r} is not one of {', '.join(BACKENDS)}")
    if precision not in PRECISIONS:
        raise InvalidRecord(f"invalid measurement: precision {precision!r} is not one of {', '.join(PRECISIONS)}")

"""Canonical serialisation, duplicate-row check, writer and reader of the detection evaluation report (NFR-009-04,
FR-009-50).

A report is written as UTF-8 JSON with sorted keys, separators `,` and `:`, no ASCII escaping and one trailing
newline, so two runs on the same input give byte-identical files. The writer and the reader both refuse a report in
which two rows of `per_class` share the key (model, precision, training_arm, family, task, class).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

KEY_FIELDS = ("model", "precision", "training_arm", "family", "task", "class")


class ReportError(ValueError):
    """`code`: report-duplicate-row (with `key`, the six values of the first duplicated row) or report-invalid."""

    def __init__(self, code: str, message: str, key: tuple[str, ...] | None = None) -> None:
        self.code = code
        self.key = key
        shown = f" [{', '.join(key)}]" if key else ""
        super().__init__(f"{code}: {message}{shown}")


def dumps_report(report: Mapping[str, Any]) -> bytes:
    """The canonical bytes of a report; ValueError for a NaN or infinity anywhere."""
    try:
        text = json.dumps(report, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except ValueError:
        raise ValueError("the report holds a non-finite number (NaN or infinity)") from None
    return (text + "\n").encode("utf-8")


def check_unique_rows(report: Mapping[str, Any]) -> None:
    """Raise `ReportError("report-duplicate-row")` for the first row (by its second occurrence) whose key repeats."""
    rows = report.get("per_class") if isinstance(report, Mapping) else None
    if not rows:
        return
    if not isinstance(rows, list):
        raise ReportError("report-invalid", "per_class is not a list")
    seen: set[tuple[str, ...]] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ReportError("report-invalid", f"per_class row {i} is not an object")
        values = tuple(row.get(f) for f in KEY_FIELDS)
        if not all(isinstance(v, str) for v in values):
            raise ReportError("report-invalid", f"per_class row {i} lacks one of {KEY_FIELDS}")
        key = tuple(str(v) for v in values)
        if key in seen:
            raise ReportError("report-duplicate-row", f"per_class row {i} repeats a key", key)
        seen.add(key)


def write_report(report: Mapping[str, Any], path: Path) -> None:
    """Write the canonical bytes of `report` to `path`; a refused report creates or changes nothing."""
    check_unique_rows(report)
    data = dumps_report(report)
    target = Path(path)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)


def _refuse_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name}")


def read_report(path: Path) -> dict[str, Any]:
    """Read a report file; unreadable, empty, non-JSON or non-object content and a duplicate row are refused."""
    raw = Path(path).read_bytes()  # FileNotFoundError for a missing file
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ReportError("report-invalid", "the file is not UTF-8") from None
    if not text.strip():
        raise ReportError("report-invalid", "the file is empty")
    try:
        doc = json.loads(text, parse_constant=_refuse_constant)
    except ValueError, RecursionError:
        raise ReportError("report-invalid", "the file is not valid JSON without NaN or infinity") from None
    if not isinstance(doc, dict):
        raise ReportError("report-invalid", "the report is not a JSON object")
    check_unique_rows(doc)
    return doc

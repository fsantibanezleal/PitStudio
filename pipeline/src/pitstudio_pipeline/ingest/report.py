"""Ingestion-report building blocks (DC-008-03): violations, file entries and the report document."""

from __future__ import annotations

import datetime as dt
import math
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPORT_SCHEMA_VERSION = "1.0"
MAX_TEXT = 200
_RELPATH_SEGMENT = re.compile(r"[^A-Za-z0-9._-]")


def utc_text(moment: dt.datetime) -> str:
    return moment.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def clip(text: str, limit: int = MAX_TEXT) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def report_value(value: Any) -> Any:
    """A found value as the report holds it: numbers, booleans, null and text; non-finite numbers become text."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    return clip(str(value))


def violation(
    file: str,
    field: str,
    rule: str,
    *,
    row: int | None = None,
    pixel: tuple[int, int] | None = None,
    field_kind: str = "column",
    value: Any = None,
    expected: str | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    """One report violation: file, row or pixel, field and its kind, found value, expected value, rule and unit."""
    return {
        "file": file,
        "row": row,
        "pixel": None if pixel is None else {"x": int(pixel[0]), "y": int(pixel[1])},
        "field": clip(field or "(unnamed)", 128),
        "field_kind": field_kind,
        "value": report_value(value),
        "expected": None if expected is None else clip(expected) or None,
        "rule": clip(rule) or "rule",
        "unit": unit,
    }


def relative_to_root(data_root: Path, path: Path) -> str:
    """POSIX path of `path` relative to the data root; a path outside it is reported by its file name."""
    try:
        return Path(path).resolve().relative_to(Path(data_root).resolve()).as_posix()
    except ValueError:
        return Path(path).name


def safe_relpath(text: str) -> str:
    """A name usable as a report `relpath` segment (series ids and other labels)."""
    cleaned = _RELPATH_SEGMENT.sub("_", text).strip("._-") or "unnamed"
    return cleaned[:99]


def resolve_fixture(path: Path, fixture: Any, samples_dir: Path | str | None) -> bool:
    """FR-008-49: a source is a fixture when asked to be (`fixture=True`) or when its file lies under `samples_dir`."""
    if fixture is not None and not isinstance(fixture, bool):
        raise TypeError(f"fixture must be a bool or None, not {type(fixture).__name__}")
    if fixture:
        return True
    return samples_dir is not None and Path(path).resolve().is_relative_to(Path(samples_dir).resolve())


def build_report(
    *,
    source: str,
    stage: str,
    run_id: str,
    now: dt.datetime,
    files: Sequence[Mapping[str, Any]],
    violations: Sequence[Mapping[str, Any]],
    outputs: Sequence[Mapping[str, str]],
    fixture: bool = False,
    partial: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "source": source,
        "stage": stage,
        "run_id": run_id,
        "created": utc_text(now),
        "status": "rejected" if any(f["status"] == "rejected" for f in files) else "accepted",
        "files": [dict(f) for f in files],
        "violations": [dict(v) for v in violations],
        "outputs": [dict(o) for o in outputs],
    }
    if fixture:
        report["fixture"] = True
    if partial:
        report["partial"] = True
    return report


def atomic_write(path: Path, data: bytes) -> None:
    """Write `data` to `path` through a temporary sibling, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)

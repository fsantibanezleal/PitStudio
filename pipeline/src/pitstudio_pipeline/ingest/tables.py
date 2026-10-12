"""Tabular validation: reject, never coerce (FR-008-20, FR-008-21, P-008-03)."""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandera.errors
import pandera.polars as pa
import polars as pl

from pitstudio_pipeline.download.hashing import sha256_file
from pitstudio_pipeline.errors import IngestionRejected
from pitstudio_pipeline.ingest.report import build_report, relative_to_root, violation
from pitstudio_pipeline.ingest.schemas import SCHEMAS
from pitstudio_pipeline.paths import check_data_root

STAGE = "s10_preprocess"


def _resolve(schema: pa.DataFrameSchema | str) -> pa.DataFrameSchema:
    return SCHEMAS[schema] if isinstance(schema, str) else schema


def _expected_of(check: Any) -> str:
    stats = getattr(check, "statistics", None) or {}
    name = getattr(check, "name", "check")
    low, high = stats.get("min_value"), stats.get("max_value")
    if name == "greater_than_or_equal_to":
        return f">= {low}"
    if name == "greater_than":
        return f"> {low}"
    if name == "less_than_or_equal_to":
        return f"<= {high}"
    if name == "less_than":
        return f"< {high}"
    if name == "in_range":
        return f"in [{low}, {high}]"
    return f"{name} {stats}" if stats else str(name)


def _key_fields(schema: pa.DataFrameSchema) -> list[str]:
    if not schema.unique:
        return []
    return [schema.unique] if isinstance(schema.unique, str) else list(schema.unique)


def _violations(frame: pl.DataFrame, schema: pa.DataFrameSchema, file: str) -> list[dict[str, Any]]:
    """Every violation of `schema` by `frame` as report violations, row-less ones first (empty when valid)."""
    try:
        schema.validate(frame, lazy=True)
    except pandera.errors.SchemaErrors as exc:
        cases = exc.failure_cases.to_dicts()
    except pandera.errors.SchemaError as exc:
        cases = [
            {"failure_case": str(exc)[:200], "column": None, "check": "schema", "index": None, "check_number": None}
        ]
    else:
        return []
    keys = _key_fields(schema)
    found = []
    for case in cases:
        column, check, index = case.get("column"), str(case.get("check")), case.get("index")
        spec = schema.columns.get(column) if column else None
        unit = (spec.metadata or {}).get("unit") if spec is not None else None
        expected: str | None = None
        field = column
        value: Any = case.get("failure_case")
        in_frame = column in frame.columns and isinstance(index, int)
        if check in ("column_in_schema", "column_in_dataframe"):
            field, value = str(value), None
            expected = "no such column" if check == "column_in_schema" else "column present"
        elif check == "multiple_fields_uniqueness" or (check.endswith("uniqueness") and not column):
            field = ", ".join(keys) or "key"
            expected = "unique key"
            value = ", ".join(str(frame[k][index]) for k in keys if k in frame.columns and isinstance(index, int))
        elif check.startswith("dtype("):
            dtype = spec.dtype.type if spec is not None and spec.dtype is not None else "?"
            expected = f"dtype {dtype}"
        elif check == "not_nullable":
            expected = "not null (NaN counts as null)"
            value = frame[column][index] if in_frame else value
        elif in_frame:
            value = frame[column][index]  # the found cell with its own type (the case holds its text)
            number = case.get("check_number")
            if spec is not None and number is not None and number < len(spec.checks):
                expected = _expected_of(spec.checks[number])
        found.append(
            violation(
                file,
                str(field),
                check,
                row=index if isinstance(index, int) else None,
                value=value,
                expected=expected,
                unit=unit,
            )
        )
    found.sort(key=lambda v: (-1 if v["row"] is None else v["row"], v["field"], v["rule"]))
    return found


def validate_table(frame: pl.DataFrame, schema: pa.DataFrameSchema | str, *, file: str) -> pl.DataFrame:
    """The frame itself when it satisfies `schema`; otherwise `IngestionRejected` listing every violation.

    Nothing is cast, clipped, imputed or dropped: a valid frame comes back equal to its input (P-008-03).
    """
    found = _violations(frame, _resolve(schema), file)
    if found:
        raise IngestionRejected(found)
    return frame


def write_parquet(frame: pl.DataFrame, out: Path, root: Path, metadata: dict[str, str] | None = None) -> dict[str, str]:
    """Write `frame` to `out` through a temporary sibling; return its `outputs` entry (relative path, SHA-256)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_name(out.name + ".tmp")
    frame.write_parquet(temporary, compression="zstd", statistics=False, metadata=metadata or None)
    os.replace(temporary, out)
    return {"path": relative_to_root(root, out), "sha256": sha256_file(out)}


def ingest_table(
    path: Path | str,
    schema: pa.DataFrameSchema | str,
    *,
    schema_name: str | None = None,
    source: str,
    data_root: Path | str,
    run_id: str,
    now: Callable[[], dt.datetime],
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Validate one Parquet file and write its output; the ingestion report (DC-008-03) says what happened."""
    root = check_data_root(data_root, repo_root=repo_root)
    path = Path(path)
    name = schema_name or (schema if isinstance(schema, str) else "table")
    rel = relative_to_root(root, path)
    entry: dict[str, Any] = {
        "path": rel,
        "sha256": sha256_file(path),
        "validator": "tabular",
        "schema_name": name,
        "status": "accepted",
        "records": None,
    }
    outputs: list[dict[str, str]] = []
    try:
        frame = pl.read_parquet(path)
    except Exception as exc:
        entry["status"] = "rejected"
        found = [violation(rel, "file", "readable Parquet file", field_kind="property", value=type(exc).__name__)]
    else:
        entry["records"] = frame.height
        found = _violations(frame, _resolve(schema), rel)
        if found:
            entry["status"] = "rejected"
        else:
            outputs.append(write_parquet(frame, root / "processed" / source / f"{path.stem}.parquet", root))
    return build_report(
        source=source, stage=STAGE, run_id=run_id, now=now(), files=[entry], violations=found, outputs=outputs
    )

"""Tabular validation: reject, never coerce (FR-008-20, FR-008-21, P-008-03)."""

from __future__ import annotations

import datetime as dt
import json
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pandera.errors
import pandera.polars as pa
import polars as pl

from pitstudio_pipeline.download.hashing import sha256_file
from pitstudio_pipeline.errors import IngestionRejected
from pitstudio_pipeline.ingest.exclusions import apply_exclusions
from pitstudio_pipeline.ingest.report import build_report, relative_to_root, resolve_fixture, violation
from pitstudio_pipeline.ingest.schemas import SCHEMAS
from pitstudio_pipeline.paths import check_data_root, default_data_root

STAGE = "s10_preprocess"


def default_samples_dir(repo_root: Path | str | None) -> Path:
    """`<repo>/data/samples`: the folder whose files are fixtures by location."""
    return default_data_root(repo_root) / "samples"


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
    exclusions: Sequence[Mapping[str, Any]] | None = None,
    fixture: bool | None = None,
    samples_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Validate one Parquet file and write its output; the ingestion report (DC-008-03) says what happened.

    `exclusions` are the declared rules of FR-008-22; they run after validation, and their removal counts are stored in
    the output's Parquet metadata entry `exclusions` (the manifest of the run records them too). A fixture source
    (`fixture=True`, or a file under `samples_dir`, default `<repo>/data/samples`) is processed the same way and
    every output is marked: `fixture: true` on the report and the Parquet metadata entry `fixture` (FR-008-49).
    """
    root = check_data_root(data_root, repo_root=repo_root)
    path = Path(path)
    is_fixture = resolve_fixture(
        path, fixture, samples_dir if samples_dir is not None else default_samples_dir(repo_root)
    )
    name = schema_name or (schema if isinstance(schema, str) else "table")
    rel = relative_to_root(root, path)
    entry, frame, found = _check_file(path, schema, name, rel)
    outputs: list[dict[str, str]] = []
    if frame is not None:
        metadata: dict[str, str] = {"fixture": "true"} if is_fixture else {}
        if exclusions:
            excluded = apply_exclusions(frame, exclusions)
            frame = excluded.frame
            metadata["exclusions"] = json.dumps(excluded.removed, sort_keys=True)
        outputs.append(write_parquet(frame, root / "processed" / source / f"{path.stem}.parquet", root, metadata))
    return build_report(
        source=source,
        stage=STAGE,
        run_id=run_id,
        now=now(),
        files=[entry],
        violations=found,
        outputs=outputs,
        fixture=is_fixture,
    )


def ingest_source(
    source: str,
    schema: pa.DataFrameSchema | str,
    fetch_records: Sequence[Mapping[str, Any]],
    *,
    schema_name: str | None = None,
    data_root: Path | str,
    run_id: str,
    now: Callable[[], dt.datetime],
    repo_root: Path | str | None = None,
    exclusions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Ingest the verified files of a multi-file source and list the rest as `unavailable` (FR-008-50).

    `fetch_records` are the records `s00_download` wrote for the source. Every record that stored a verified file is
    validated like `ingest_table` does; every other record becomes a file entry with status `unavailable`, and the
    report is marked `partial`. Outputs are written only when no file of the source was rejected.
    """
    root = check_data_root(data_root, repo_root=repo_root)
    name = schema_name or (schema if isinstance(schema, str) else "table")
    files: list[dict[str, Any]] = []
    found: list[dict[str, Any]] = []
    accepted: list[tuple[Path, pl.DataFrame]] = []
    partial = False
    for record in fetch_records:
        stored = record.get("stored_as")
        if record.get("status") not in ("verified", "pin-proposed") or not stored:
            partial = True
            rel = stored or f"raw/{record.get('source', source)}/{record['name']}"
            files.append(
                {
                    "path": rel,
                    "sha256": None,
                    "validator": "tabular",
                    "schema_name": name,
                    "status": "unavailable",
                    "records": None,
                }
            )
            continue
        path = root / stored
        entry, frame, violations = _check_file(path, schema, name, stored)
        files.append(entry)
        found.extend(violations)
        if frame is not None:
            accepted.append((path, frame))
    outputs: list[dict[str, str]] = []
    if not found:
        for path, frame in accepted:
            metadata: dict[str, str] = {}
            if exclusions:
                excluded = apply_exclusions(frame, exclusions)
                frame = excluded.frame
                metadata["exclusions"] = json.dumps(excluded.removed, sort_keys=True)
            outputs.append(write_parquet(frame, root / "processed" / source / f"{path.stem}.parquet", root, metadata))
    return build_report(
        source=source,
        stage=STAGE,
        run_id=run_id,
        now=now(),
        files=files,
        violations=found,
        outputs=outputs,
        partial=partial,
    )


def _check_file(
    path: Path, schema: pa.DataFrameSchema | str, name: str, rel: str
) -> tuple[dict[str, Any], pl.DataFrame | None, list[dict[str, Any]]]:
    """(file entry, the frame when it is valid, its violations) for one Parquet file."""
    entry: dict[str, Any] = {
        "path": rel,
        "sha256": sha256_file(path),
        "validator": "tabular",
        "schema_name": name,
        "status": "accepted",
        "records": None,
    }
    try:
        frame = pl.read_parquet(path)
    except Exception as exc:
        entry["status"] = "rejected"
        return (
            entry,
            None,
            [violation(rel, "file", "readable Parquet file", field_kind="property", value=type(exc).__name__)],
        )
    entry["records"] = frame.height
    found = _violations(frame, _resolve(schema), rel)
    if found:
        entry["status"] = "rejected"
        return entry, None, found
    return entry, frame, []

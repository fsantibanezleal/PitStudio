# ruff: noqa: E501, PT018
"""The `ghcnh_hourly` schema accepts the calm-or-variable direction value 999 and nothing else outside 0 to 360 (pipeline environment).

Requirements: FR-008-20.

Evidence: the real station files of 2015 to 2024 (USW00024127, read on 2026-11-24) hold wind direction 999 on every calm and
variable hour with `wind_direction_Measurement_Code` C or V (see T-008-101), so the bound 0 to 360 rejected the files whole. The NCEI
GHCNh documentation (version 1.1.0, Table 1 p. 7 and Table 2) gives the direction in whole degrees with "000" for calm winds and
lists the measurement codes C (calm), N (normal) and V (variable) for wind direction; it does not mention 999, so 999 is a sentinel
of the files that the schema documents (UNVERIFIED in the documentation text). Change protocol of ADR-0039: the schema has no
generated types (it is a pandera schema); the examples of the ingestion report keep their rejected value 361.

Oracles: hand-written values (the bound 0 to 360 and the sentinel 999) and the example files of the ingestion report.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandera.polars as pa
import polars as pl
import pytest
from pitstudio_pipeline.ingest.schemas import SCHEMAS

ROOT = Path(__file__).resolve().parents[2]


def _probe(values: list[float]) -> tuple[pa.DataFrameSchema, pl.DataFrame]:
    col = SCHEMAS["ghcnh_hourly"].columns["wind_direction"]
    return pa.DataFrameSchema({"wind_direction": col}, strict=True), pl.DataFrame({"wind_direction": values}).cast(
        col.dtype.type
    )


@pytest.mark.req("FR-008-20")
@pytest.mark.parametrize("values", [[0.0, 180.0, 360.0], [999.0], [999.0, 0.0, 270.0, 360.0], [None, 999.0]])
def test_directions_in_range_and_the_calm_or_variable_sentinel_are_accepted(values) -> None:
    schema, frame = _probe(values)
    schema.validate(frame)


@pytest.mark.req("FR-008-20")
@pytest.mark.parametrize("values", [[-1.0], [361.0], [998.0], [1000.0], [999.5], [999.0, 361.0], [-999.0]])
def test_every_other_value_outside_0_to_360_is_still_rejected(values) -> None:
    schema, frame = _probe(values)
    with pytest.raises(pa.errors.SchemaError):
        schema.validate(frame)


@pytest.mark.req("FR-008-20")
def test_the_column_metadata_says_what_999_means_and_where_the_documentation_stops() -> None:
    md = SCHEMAS["ghcnh_hourly"].columns["wind_direction"].metadata or {}
    assert md.get("unit") == "deg"
    note = md.get("sentinel", "")
    assert "999" in note and "calm" in note and "variable" in note and "UNVERIFIED" in note
    assert "Table 2" in md.get("source", "") or "Table 2" in note


@pytest.mark.req("FR-008-20")
def test_a_whole_station_file_with_calm_hours_validates_and_the_documented_rejection_example_still_fails() -> None:
    example = json.loads(
        (ROOT / "specs/008-data-pipeline/contracts/examples/ingestion-report.valid.json").read_text(encoding="utf-8")
    )
    wind = [v for v in example["violations"] if v["field"] == "wind_direction"]
    assert wind and wind[0]["value"] == 361
    assert "999" in wind[0]["expected"] and "999" in wind[0]["rule"]  # the example states the rule as it is now
    schema, frame = _probe([float(wind[0]["value"])])
    with pytest.raises(pa.errors.SchemaError):
        schema.validate(frame)

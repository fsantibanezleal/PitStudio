# ruff: noqa: E501, PT018
"""T-008-020: pandera (Polars) schemas that reject and never coerce; one ingestion report per rejected file; valid frames unchanged.

Requirements: FR-008-20, FR-008-21, P-008-03.

Spec: specs/008-data-pipeline/spec.md FR-008-20, FR-008-21, P-008-03 and section 7 (NOAA GHCNh documentation v1.1.0,
2026-03-10: 329 columns, section X p.18; `wind_direction` in whole degrees, range [0, 360], Table 1 p.7; `wind_speed` in
m/s with range >= 0, Table 1 p.7; `DATE` ISO 8601 UTC); contract `contracts/ingestion-report.schema.json` (DC-008-03).

Oracle: hand-built frames with one injected violation each, compared with the violations the spec requires (file, row,
column, value, rule, unit); Hypothesis-generated valid frames compared with themselves; the NCEI documentation facts above
(329 columns, the two ranges); the ingestion-report JSON Schema (validated with `jsonschema`). Row indices are 0-based
(the ingestion-report schema allows 0 and the same index convention as polars).

Expected API of the implementation:
- `pitstudio_pipeline.ingest.schemas.SCHEMAS`: dict schema name -> `pandera.polars.DataFrameSchema`, with at least the keys
  `ghcnh_hourly`, `era5_hourly`, `dewit_slope_failure`, `egms_hambach`, `xu_expansion_v3`. Settings: `strict=True`,
  `coerce=False` (schema and every column), every column's dtype declared, `nullable=False` unless the column declares
  otherwise, and every column that has a check carries `metadata={"unit": <SI unit>, "source": <citation>}`.
- `pitstudio_pipeline.ingest.validate_table(frame, schema, *, file) -> polars.DataFrame`: `schema` is a pandera schema object
  or a key of `SCHEMAS`; validates lazily (every violation) and returns a frame equal to the input (values, dtypes, column
  order, row order) or raises `pitstudio_pipeline.errors.IngestionRejected` with `.violations`, a list of dicts with the
  keys of `$defs/violation` of the ingestion-report schema (`file`, `row`, `pixel`, `field`, `field_kind`, `value`, `expected`,
  `rule`, `unit`): cell violations have the 0-based `row`; column-level violations (dtype, extra or missing column) have
  `row: None`; `unit` comes from the column metadata; non-finite values are text; `value` is at most 200 characters.
- `pitstudio_pipeline.ingest.ingest_table(path, schema, *, schema_name=None, source, data_root, run_id, now,
  repo_root=None, exclusions=None, fixture=None, samples_dir=None) -> dict`: reads the Parquet file `path` (under
  `<data_root>/raw/...`), validates it and returns an ingestion report dict valid against the schema: rejected = status
  `rejected`, the violations, `outputs: []` and no file written under `<data_root>/processed`; accepted = status `accepted`,
  the frame written to `processed/<source>/<stem>.parquet` and listed in `outputs` with its SHA-256.
"""

from __future__ import annotations

from pathlib import Path

import _p008_kit as kit
import pandera.polars as pa
import polars as pl
import pytest
from pitstudio_pipeline.errors import IngestionRejected
from pitstudio_pipeline.ingest import ingest_table, validate_table
from pitstudio_pipeline.ingest.schemas import SCHEMAS

# isort: split
from hypothesis import given, settings
from hypothesis import strategies as st

FILE = "raw/t/x.parquet"
NAMES = ["ghcnh_hourly", "era5_hourly", "dewit_slope_failure", "egms_hambach", "xu_expansion_v3"]


def local_schema() -> pa.DataFrameSchema:
    """A schema built the way FR-008-20 prescribes, with physical bounds that cite their unit and source."""
    return pa.DataFrameSchema(
        {
            "station": pa.Column(pl.String, nullable=False),
            "wind_speed": pa.Column(
                pl.Float64,
                pa.Check.ge(0.0),
                nullable=False,
                metadata={"unit": "m/s", "source": "NCEI GHCNh documentation v1.1.0, Table 1, p.7"},
            ),
            "n": pa.Column(pl.Int64, nullable=False),
        },
        strict=True,
        coerce=False,
        unique=["station"],
    )


def good(rows: int = 3) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "station": [f"s{i}" for i in range(rows)],
            "wind_speed": [float(i) for i in range(rows)],
            "n": list(range(rows)),
        }
    )


def rejected(frame: pl.DataFrame) -> list[dict]:
    with pytest.raises(IngestionRejected) as info:
        validate_table(frame, local_schema(), file=FILE)
    return info.value.violations


def as_report(violations: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "source": "t",
        "stage": "s10_preprocess",
        "run_id": "20261011T120000Z-t",
        "created": kit.NOW_TEXT,
        "status": "rejected",
        "files": [
            {
                "path": FILE,
                "sha256": kit.HEX64,
                "validator": "tabular",
                "schema_name": "local_test",
                "status": "rejected",
                "records": 3,
            }
        ],
        "violations": violations,
        "outputs": [],
    }


# ------------------------------------------------------------------------------------------------ FR-008-20
@pytest.mark.req("FR-008-20")
@pytest.mark.parametrize("name", NAMES)
def test_registered_schemas_follow_the_declared_settings(name: str) -> None:
    schema = SCHEMAS[name]
    assert schema.strict is True and schema.coerce is False
    assert len(schema.columns) > 0
    for cname, col in schema.columns.items():
        assert col.dtype is not None, f"{name}.{cname}: dtype must be declared"
        assert col.coerce is False, f"{name}.{cname}: coerce must be False"
        assert isinstance(col.nullable, bool)
        if col.checks:
            md = col.metadata or {}
            assert isinstance(md.get("unit"), str) and md["unit"], (
                f"{name}.{cname}: range metadata must name the SI unit"
            )
            assert isinstance(md.get("source"), str) and md["source"], (
                f"{name}.{cname}: range metadata must cite the source"
            )


@pytest.mark.req("FR-008-20")
def test_ghcnh_schema_has_the_329_columns_of_the_ncei_documentation_and_a_non_null_date() -> None:
    schema = SCHEMAS["ghcnh_hourly"]
    assert len(schema.columns) == 329  # NCEI GHCNh documentation v1.1.0, section X, p.18
    assert schema.columns["DATE"].nullable is False


def _probe(column_name: str, values: list[int]) -> pl.DataFrame:
    col = SCHEMAS["ghcnh_hourly"].columns[column_name]
    return pa.DataFrameSchema({column_name: col}, strict=True), pl.DataFrame({column_name: values}).cast(col.dtype.type)


@pytest.mark.req("FR-008-20")
@pytest.mark.parametrize(("values", "ok"), [([0, 180, 360], True), ([-1], False), ([361], False)])
def test_ghcnh_wind_direction_range_is_0_to_360_degrees(values: list[int], ok: bool) -> None:
    schema, frame = _probe("wind_direction", values)
    if ok:
        schema.validate(frame)
    else:
        with pytest.raises(pa.errors.SchemaError):
            schema.validate(frame)
    assert (SCHEMAS["ghcnh_hourly"].columns["wind_direction"].metadata or {}).get("unit") in {
        "deg",
        "degree",
        "degrees",
    }


@pytest.mark.req("FR-008-20")
@pytest.mark.parametrize(("values", "ok"), [([0, 5, 60], True), ([-1], False)])
def test_ghcnh_wind_speed_is_non_negative_in_metres_per_second(values: list[int], ok: bool) -> None:
    schema, frame = _probe("wind_speed", values)
    if ok:
        schema.validate(frame)
    else:
        with pytest.raises(pa.errors.SchemaError):
            schema.validate(frame)
    assert (SCHEMAS["ghcnh_hourly"].columns["wind_speed"].metadata or {}).get("unit") == "m/s"


# ------------------------------------------------------------------------------------------------ FR-008-21
@pytest.mark.req("FR-008-21")
def test_valid_frame_comes_back_unchanged() -> None:
    df = good(5)
    out = validate_table(df, local_schema(), file=FILE)
    assert out.equals(df) and out.dtypes == df.dtypes and out.columns == df.columns


@pytest.mark.req("FR-008-21")
def test_out_of_range_cell_is_named_with_row_column_value_rule_and_unit() -> None:
    df = good(3).with_columns(pl.Series("wind_speed", [1.0, -0.5, 2.0]))
    (v,) = rejected(df)
    assert (v["file"], v["row"], v["field"], v["field_kind"], v["value"], v["unit"]) == (
        FILE,
        1,
        "wind_speed",
        "column",
        -0.5,
        "m/s",
    )
    assert "greater_than_or_equal_to" in v["rule"] and v["pixel"] is None
    assert kit.schema_errors("ingestion-report.schema.json", as_report([v])) == []


@pytest.mark.req("FR-008-21")
def test_wrong_dtype_is_rejected_not_cast() -> None:
    df = good(3).with_columns(pl.col("wind_speed").cast(pl.Int64))
    before = df.clone()
    (v,) = rejected(df)
    assert v["field"] == "wind_speed" and v["row"] is None and "Int64" in str(v["value"])
    assert df.equals(before) and df.dtypes == before.dtypes, "the input is never repaired"


@pytest.mark.req("FR-008-21")
def test_null_and_nan_are_violations_with_their_rows() -> None:
    df = pl.DataFrame({"station": ["a", "b", "c"], "wind_speed": [1.0, None, float("nan")], "n": [1, 2, 3]})
    viol = rejected(df)
    rows = {v["row"] for v in viol if v["field"] == "wind_speed"}
    assert rows == {1, 2}
    nan_value = next(v["value"] for v in viol if v["row"] == 2)
    assert isinstance(nan_value, str) and "nan" in nan_value.lower(), "non-finite values are written as text"
    assert kit.schema_errors("ingestion-report.schema.json", as_report(viol)) == []


@pytest.mark.req("FR-008-21")
def test_extra_and_missing_columns_are_violations() -> None:
    extra = good(2).with_columns(pl.lit(1).alias("surplus"))
    assert [v["field"] for v in rejected(extra)] == ["surplus"]
    missing = good(2).drop("wind_speed")
    (v,) = rejected(missing)
    assert v["field"] == "wind_speed" and v["field_kind"] == "column" and v["row"] is None


@pytest.mark.req("FR-008-21")
def test_duplicate_key_is_a_violation() -> None:
    df = pl.DataFrame({"station": ["a", "a", "b"], "wind_speed": [1.0, 2.0, 3.0], "n": [1, 2, 3]})
    viol = rejected(df)
    assert any(v["field"] == "station" and v["row"] == 1 for v in viol)


@pytest.mark.req("FR-008-21")
def test_every_violation_is_listed_not_only_the_first() -> None:
    df = pl.DataFrame(
        {"station": ["a", "a", "c"], "wind_speed": [-1.0, 2.0, None], "n": [1, 2, 3], "surplus": [0, 0, 0]}
    )
    viol = rejected(df)
    fields = {v["field"] for v in viol}
    assert {"station", "wind_speed", "surplus"} <= fields
    assert {v["row"] for v in viol if v["field"] == "wind_speed"} >= {0, 2}


@pytest.mark.req("FR-008-21")
def test_hostile_values_are_truncated_to_the_report_limits() -> None:
    schema = pa.DataFrameSchema(
        {
            "label": pa.Column(
                pl.String, pa.Check.str_length(max_value=5), nullable=False, metadata={"unit": "1", "source": "test"}
            )
        },
        strict=True,
        coerce=False,
    )
    df = pl.DataFrame({"label": ["ok", "é☃" * 5000]})
    with pytest.raises(IngestionRejected) as info:
        validate_table(df, schema, file=FILE)
    (v,) = info.value.violations
    assert v["row"] == 1 and len(str(v["value"])) <= 200 and len(v["rule"]) <= 200
    assert kit.schema_errors("ingestion-report.schema.json", as_report(info.value.violations)) == []


@pytest.mark.req("FR-008-21")
def test_unicode_column_names_are_reported_verbatim() -> None:
    df = good(2).with_columns(pl.lit(1).alias("ñandú"))
    (v,) = rejected(df)
    assert v["field"] == "ñandú"


@pytest.mark.req("FR-008-21")
def test_stage_writes_one_rejected_report_and_no_output(tmp_path: Path) -> None:
    raw = tmp_path / "data" / "raw" / "t"
    raw.mkdir(parents=True)
    df = good(3).with_columns(pl.Series("wind_speed", [1.0, -0.5, 2.0]))
    df.write_parquet(raw / "x.parquet")
    report = ingest_table(
        raw / "x.parquet",
        local_schema(),
        schema_name="local_test",
        source="t",
        data_root=tmp_path / "data",
        run_id="20261011T120000Z-t",
        now=kit.NOW,
    )
    assert kit.schema_errors("ingestion-report.schema.json", report) == []
    assert report["status"] == "rejected" and report["outputs"] == []
    assert report["files"][0]["path"] == FILE and report["files"][0]["sha256"] == kit.sha256_hex(
        (raw / "x.parquet").read_bytes()
    )
    assert report["files"][0]["records"] == 3 and report["files"][0]["validator"] == "tabular"
    assert [v["row"] for v in report["violations"]] == [1]
    assert kit.files_under(tmp_path / "data" / "processed") == [], "no output for a rejected source"


@pytest.mark.req("FR-008-21")
def test_stage_accepts_a_valid_file_and_writes_the_frame_unchanged(tmp_path: Path) -> None:
    raw = tmp_path / "data" / "raw" / "t"
    raw.mkdir(parents=True)
    df = good(4)
    df.write_parquet(raw / "x.parquet")
    report = ingest_table(
        raw / "x.parquet",
        local_schema(),
        schema_name="local_test",
        source="t",
        data_root=tmp_path / "data",
        run_id="20261011T120000Z-t",
        now=kit.NOW,
    )
    assert kit.schema_errors("ingestion-report.schema.json", report) == []
    assert report["status"] == "accepted" and report["violations"] == []
    (out,) = report["outputs"]
    written = tmp_path / "data" / out["path"]
    assert out["path"].startswith("processed/t/") and kit.sha256_hex(written.read_bytes()) == out["sha256"]
    assert pl.read_parquet(written).equals(df)


# ------------------------------------------------------------------------------------------------ P-008-03
frames = st.integers(min_value=1, max_value=12).flatmap(
    lambda n: st.tuples(
        st.just(n),
        st.lists(st.sampled_from([0.0, 1e-300, 0.5, 17.25, 1e6, 1.7976931348623157e308]), min_size=n, max_size=n),
        st.lists(st.integers(min_value=-(2**62), max_value=2**62), min_size=n, max_size=n),
    )
)


def _frame(n: int, speeds: list[float], counts: list[int]) -> pl.DataFrame:
    return pl.DataFrame({"station": [f"s{i}" for i in range(n)], "wind_speed": speeds, "n": counts})


@pytest.mark.req("P-008-03")
@settings(max_examples=80, deadline=None)
@given(frames)
def test_valid_frames_are_returned_equal_including_values_at_the_bounds(data) -> None:
    df = _frame(*data)
    out = validate_table(df, local_schema(), file=FILE)
    assert out.equals(df) and out.dtypes == df.dtypes and out.columns == df.columns


@pytest.mark.req("P-008-03")
@settings(max_examples=80, deadline=None)
@given(frames, st.data())
def test_one_injected_violation_raises_and_is_reported_at_its_cell(data, draw) -> None:
    n, speeds, counts = data
    row = draw.draw(st.integers(0, n - 1))
    kind = draw.draw(st.sampled_from(["negative", "null", "nan"]))
    bad = list(speeds)
    bad_value = {"negative": -1e-9, "null": None, "nan": float("nan")}[kind]
    bad[row] = bad_value  # type: ignore[call-overload]
    df = pl.DataFrame(
        {"station": [f"s{i}" for i in range(n)], "wind_speed": pl.Series(bad, dtype=pl.Float64), "n": counts}
    )
    viol = rejected(df)
    assert any(v["row"] == row and v["field"] == "wind_speed" for v in viol)
    # no validation ever returns or leaves behind a modified frame
    assert df["wind_speed"].dtype == pl.Float64 and df.height == n


@pytest.mark.req("FR-008-15")
def test_preprocessing_refuses_an_unsafe_data_root(tmp_path: Path) -> None:
    from pitstudio_pipeline.errors import UnsafeDataRoot

    repo = kit.make_repo(tmp_path)
    raw = tmp_path / "somewhere"
    raw.mkdir()
    good().write_parquet(raw / "x.parquet")
    with pytest.raises(UnsafeDataRoot):
        ingest_table(
            raw / "x.parquet",
            local_schema(),
            schema_name="local_test",
            source="t",
            data_root=repo / "data",
            repo_root=repo,
            run_id="20261011T120000Z-t",
            now=kit.NOW,
        )
    assert kit.files_under(repo / "data") == []

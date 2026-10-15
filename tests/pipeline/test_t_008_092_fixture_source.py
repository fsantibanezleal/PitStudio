# ruff: noqa: E501, PT018
"""T-008-092: fixture sources: outputs marked `fixture: true`, the card says "fixture".

Requirements: FR-008-49.

Spec: specs/008-data-pipeline/spec.md FR-008-49 (while a source is a fixture, i.e. a registry entry with `fixture: true` or a
file under `data/samples/` used in place of a downloaded source, `s10_preprocess` and `s20_feature_extraction` process it,
mark every output `fixture: true`, and the card check requires the card to say "fixture"); plan.md test strategy ("a fixture
entry gives ingestion report, split and features all `fixture: true`; a card without the word fails the check naming the
card"); the module map's availability states (ADR-0040).

Oracle: hand-built inputs. The expected marks are the literal `True` / absent values; the processed numbers are those of the
hand calculation of test_t_008_050 (series x = i^2); a file under a `samples_dir` is a fixture by location.

Expected API of the implementation (added to the signatures of test_t_008_020 and test_t_008_050):
- `ingest_table(..., fixture=None, samples_dir=None)` and `run_series_stage(..., fixture=None, samples_dir=None)`: the returned
  ingestion report dict carries `"fixture": True` when `fixture=True` or when the input file lies under `samples_dir`; otherwise
  the key is absent or False. The stage still processes the input exactly as for a real source (same outputs). The written
  Parquet outputs carry the file-level metadata entry `fixture` = `"true"` (readable with
  `polars.read_parquet_metadata`). `fixture` must be a bool or None, anything else raises `TypeError` or `ValueError`.
- The card check of FR-008-49 is tested in tests/contract/test_t_008_060_data_cards.py; the split schema has no `fixture`
  field, so a split of a fixture source is marked through its dataset `version`/id and is not tested here (see the report).
"""

from __future__ import annotations

import json
from pathlib import Path

import _p008_kit as kit
import pandera.polars as pa
import polars as pl
import pytest
from pitstudio_pipeline.features import run_series_stage
from pitstudio_pipeline.ingest import ingest_table


def schema() -> pa.DataFrameSchema:
    return pa.DataFrameSchema(
        {"v": pa.Column(pl.Float64, pa.Check.ge(0.0), nullable=False, metadata={"unit": "m", "source": "test"})},
        strict=True,
        coerce=False,
    )


def table(tmp: Path, folder: str) -> Path:
    d = tmp / "data" / folder
    d.mkdir(parents=True, exist_ok=True)
    p = d / "x.parquet"
    pl.DataFrame({"v": [0.0, 1.5, 3.0]}).write_parquet(p)
    return p


def table_stage(tmp: Path, p: Path, **kw):
    return ingest_table(
        p,
        schema(),
        schema_name="fixture_test",
        source="t",
        data_root=tmp / "data",
        run_id="20261011T120000Z-t",
        now=kit.NOW,
        **kw,
    )


def series(tmp: Path, folder: str) -> Path:
    d = tmp / "data" / folder
    d.mkdir(parents=True, exist_ok=True)
    p = d / "s1.json"
    p.write_text(
        json.dumps({"t": [float(i) for i in range(10)], "x": [float(i * i) for i in range(10)]}), encoding="utf-8"
    )
    return p


def series_stage(tmp: Path, p: Path, **kw):
    return run_series_stage(
        p,
        windows=[3, 5],
        step=2,
        features=["displacement"],
        source="t",
        data_root=tmp / "data",
        run_id="20261011T120000Z-t",
        now=kit.NOW,
        **kw,
    )


@pytest.mark.req("FR-008-49")
def test_explicit_fixture_flag_marks_the_ingestion_report_and_the_outputs(tmp_path: Path) -> None:
    report = table_stage(tmp_path, table(tmp_path, "raw/t"), fixture=True)
    assert report["status"] == "accepted" and report["fixture"] is True
    (out,) = report["outputs"]
    assert pl.read_parquet_metadata(tmp_path / "data" / out["path"]).get("fixture") == "true"


@pytest.mark.req("FR-008-49")
def test_a_file_under_the_samples_folder_is_a_fixture_by_location(tmp_path: Path) -> None:
    p = table(tmp_path, "samples")
    report = table_stage(tmp_path, p, samples_dir=tmp_path / "data" / "samples")
    assert report["fixture"] is True


@pytest.mark.req("FR-008-49")
def test_a_real_source_is_not_marked(tmp_path: Path) -> None:
    report = table_stage(tmp_path, table(tmp_path, "raw/t"), samples_dir=tmp_path / "data" / "samples")
    assert not report.get("fixture", False)
    (out,) = report["outputs"]
    assert "fixture" not in pl.read_parquet_metadata(tmp_path / "data" / out["path"])


@pytest.mark.req("FR-008-49")
def test_a_fixture_is_processed_exactly_like_a_real_source(tmp_path: Path) -> None:
    real = table_stage(tmp_path / "a", table(tmp_path / "a", "raw/t"))
    fixt = table_stage(tmp_path / "b", table(tmp_path / "b", "raw/t"), fixture=True)
    assert real["status"] == fixt["status"] == "accepted"
    a = pl.read_parquet(tmp_path / "a" / "data" / real["outputs"][0]["path"])
    b = pl.read_parquet(tmp_path / "b" / "data" / fixt["outputs"][0]["path"])
    assert a.equals(b)


@pytest.mark.req("FR-008-49")
def test_a_rejected_fixture_is_still_rejected_and_marked(tmp_path: Path) -> None:
    d = tmp_path / "data" / "raw" / "t"
    d.mkdir(parents=True)
    pl.DataFrame({"v": [1.0, -2.0]}).write_parquet(d / "x.parquet")
    report = table_stage(tmp_path, d / "x.parquet", fixture=True)
    assert report["status"] == "rejected" and report["fixture"] is True and report["outputs"] == []


@pytest.mark.req("FR-008-49")
def test_feature_extraction_marks_fixture_outputs_too(tmp_path: Path) -> None:
    report = series_stage(tmp_path, series(tmp_path, "raw/t"), fixture=True)
    assert report["stage"] == "s20_feature_extraction" and report["fixture"] is True
    (out,) = report["outputs"]
    df = pl.read_parquet(tmp_path / "data" / out["path"])
    assert df["displacement_w3"].to_list() == [12.0, 20.0, 28.0]  # the hand calculation of test_t_008_050
    assert pl.read_parquet_metadata(tmp_path / "data" / out["path"]).get("fixture") == "true"


@pytest.mark.req("FR-008-49")
def test_feature_extraction_of_a_sample_series_is_a_fixture_by_location(tmp_path: Path) -> None:
    report = series_stage(tmp_path, series(tmp_path, "samples"), samples_dir=tmp_path / "data" / "samples")
    assert report["fixture"] is True


@pytest.mark.req("FR-008-49")
@pytest.mark.parametrize("bad", ["yes", 1, 0, "true", [True]])
def test_a_non_boolean_fixture_flag_is_rejected(bad: object, tmp_path: Path) -> None:
    with pytest.raises((TypeError, ValueError)):
        table_stage(tmp_path, table(tmp_path, "raw/t"), fixture=bad)
    with pytest.raises((TypeError, ValueError)):
        series_stage(tmp_path, series(tmp_path, "raw/t"), fixture=bad)

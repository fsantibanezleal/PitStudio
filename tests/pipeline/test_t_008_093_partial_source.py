# ruff: noqa: E501, PT018
"""T-008-093: partial multi-file sources: ingest what is verified, list the rest as unavailable.

Requirements: FR-008-50.

Spec: specs/008-data-pipeline/spec.md FR-008-50 (while only some files of a multi-file source are verified, `s10_preprocess`
ingests the verified files, lists each missing file with status `unavailable`, marks the ingestion report `partial`, and
`s00_download` does not record the source as complete); plan.md ("3 of 5 fixture tiles verified give an ingestion report with
3 accepted, 2 `unavailable` and `partial`; the fetch record of the source is not `complete`"); the module map's availability
states (ADR-0040).

Oracle: hand calculation on a five-tile source: tiles 1, 3 and 5 are served, tiles 2 and 4 answer 404, so exactly 3 records
are `verified` and 2 `unavailable`; the report must then hold 3 accepted and 2 unavailable files. The same source fully served
is the control (5 accepted, not partial, complete). Transport: `httpx.MockTransport`, no network.

Expected API of the implementation:
- `run_download(...)`: `result.complete` is a dict source id -> bool, True only when every file of the source is verified;
  the failed files (here HTTP 404) get a record with `status: unavailable` while the remaining files of the source are still
  fetched.
- `pitstudio_pipeline.ingest.ingest_source(source, schema, fetch_records, *, schema_name=None, data_root, run_id, now,
  repo_root=None, exclusions=None) -> dict`: ingests, as `ingest_table` does, every record of `fetch_records` (the
  `result.records` of `run_download`) whose status is `verified` (file at `<data_root>/<stored_as>`), and lists every other
  record as a file entry with `status: "unavailable"` and `path` = `raw/<source>/<name>`; the returned report has the key
  `partial: True` when at least one record was not verified (else `partial: False` or the key absent), `files` in record order,
  one `outputs` entry per accepted file (`processed/<source>/<stem>.parquet`), and no violation for an unavailable file.
  (The ingestion-report draft schema has neither `partial` nor the file status `unavailable`: that gap is reported, so these
  tests do not validate the partial report against the schema.)
"""

from __future__ import annotations

import io
from pathlib import Path

import _p008_kit as kit
import pandera.polars as pa
import polars as pl
import pytest
from pitstudio_pipeline.ingest import ingest_source

URL = "https://example.org/tiles/tile-{i}.parquet"


def tile_bytes(i: int) -> bytes:
    buf = io.BytesIO()
    pl.DataFrame({"v": [float(i), float(i) + 0.5]}).write_parquet(buf)
    return buf.getvalue()


def schema() -> pa.DataFrameSchema:
    return pa.DataFrameSchema(
        {"v": pa.Column(pl.Float64, pa.Check.ge(0.0), nullable=False, metadata={"unit": "m", "source": "test"})},
        strict=True,
        coerce=False,
    )


def fetch(tmp: Path, served: set[int]):
    files = [kit.file_rec(URL.format(i=i), tile_bytes(i), kind="table") for i in range(1, 6)]
    net = kit.Net({URL.format(i=i): tile_bytes(i) for i in served})
    return kit.run(tmp, [kit.entry("tiles", files)], net)


def ingest(tmp: Path, result):
    return ingest_source(
        "tiles",
        schema(),
        result.records,
        schema_name="tile_test",
        data_root=tmp / "data",
        run_id="20261011T120000Z-t",
        now=kit.NOW,
    )


@pytest.mark.req("FR-008-50")
def test_download_records_the_verified_tiles_and_does_not_mark_the_source_complete(tmp_path: Path) -> None:
    result = fetch(tmp_path, {1, 3, 5})
    by_name = {r["name"]: r["status"] for r in result.records}
    assert by_name == {f"tile-{i}.parquet": ("verified" if i in {1, 3, 5} else "unavailable") for i in range(1, 6)}
    assert result.complete["tiles"] is False
    for i in (1, 3, 5):
        assert (tmp_path / "data" / "raw" / "tiles" / f"tile-{i}.parquet").read_bytes() == tile_bytes(i)
    for i in (2, 4):
        assert not (tmp_path / "data" / "raw" / "tiles" / f"tile-{i}.parquet").exists()


@pytest.mark.req("FR-008-50")
def test_a_fully_served_source_is_complete(tmp_path: Path) -> None:
    result = fetch(tmp_path, {1, 2, 3, 4, 5})
    assert result.complete["tiles"] is True and all(r["status"] == "verified" for r in result.records)


@pytest.mark.req("FR-008-50")
def test_ingestion_ingests_three_lists_two_unavailable_and_marks_the_report_partial(tmp_path: Path) -> None:
    report = ingest(tmp_path, fetch(tmp_path, {1, 3, 5}))
    assert report["partial"] is True
    files = report["files"]
    assert [f["status"] for f in files] == ["accepted", "unavailable", "accepted", "unavailable", "accepted"]
    assert [f["path"] for f in files] == [f"raw/tiles/tile-{i}.parquet" for i in range(1, 6)]
    assert len(report["outputs"]) == 3 and report["violations"] == []
    for out in report["outputs"]:
        written = tmp_path / "data" / out["path"]
        assert out["path"].startswith("processed/tiles/") and kit.sha256_hex(written.read_bytes()) == out["sha256"]
    assert sorted(pl.read_parquet(tmp_path / "data" / o["path"])["v"][0] for o in report["outputs"]) == [1.0, 3.0, 5.0]


@pytest.mark.req("FR-008-50")
def test_a_complete_source_gives_a_report_that_is_not_partial(tmp_path: Path) -> None:
    report = ingest(tmp_path, fetch(tmp_path, {1, 2, 3, 4, 5}))
    assert not report.get("partial", False)
    assert [f["status"] for f in report["files"]] == ["accepted"] * 5 and len(report["outputs"]) == 5


@pytest.mark.req("FR-008-50")
def test_nothing_verified_means_nothing_ingested_and_everything_listed_unavailable(tmp_path: Path) -> None:
    report = ingest(tmp_path, fetch(tmp_path, set()))
    assert [f["status"] for f in report["files"]] == ["unavailable"] * 5
    assert report["outputs"] == [] and report["partial"] is True
    assert kit.files_under(tmp_path / "data" / "processed") == []

# ruff: noqa: E501
"""T-009-096 - FR-009-50: duplicate evaluation report rows are rejected by the writer and the reader (`report-duplicate-row`).

Oracle (independent of the code under test; plan 009 test strategy row FR-009-50): a hand-built report in which one key (model, precision, arm, family, task, class) occurs twice is
rejected with the class `report-duplicate-row` naming that key; rows that differ in any ONE of the six key fields are not duplicates; the spec's own valid contract example
(`detection-eval.valid.json`) is the clean baseline (its four rows have four different keys). The writer must also write nothing when it refuses, and the reader sees the same
verdict on a file written by hand (the duplicate arrives from outside the writer).

Expected public API (module `pitstudio_pipeline.perception.report`, see tests/unit/test_t_009_033_support_determinism.py for `dumps_report`):

    ReportError(ValueError)          .code: "report-duplicate-row" | "report-invalid"; .key: tuple[str, ...] | None (the six key values (model, precision, training_arm, family, task, class)
                                     of the first duplicated row, in per_class order of its SECOND occurrence; None for report-invalid); str(error) contains the code and every key value
    check_unique_rows(report: Mapping) -> None
        Raises ReportError("report-duplicate-row") when two rows of report["per_class"] have the same (model, precision, training_arm, family, task, class); returns None otherwise
        (also when per_class is absent or empty). Rows that are not mappings or lack a key field are ReportError("report-invalid").
    write_report(report: Mapping, path: pathlib.Path) -> None
        check_unique_rows, then writes dumps_report(report) to `path` (parent folders must exist); on any ReportError nothing is created or modified at `path`.
    read_report(path: pathlib.Path) -> dict
        Reads the UTF-8 JSON file (NaN / Infinity tokens refused), requires a JSON object, then check_unique_rows. ReportError("report-invalid") for an unreadable, non-UTF-8, empty, non-JSON or
        non-object file; FileNotFoundError for a missing file. Returns the parsed report unchanged.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
from pitstudio_pipeline.perception import report  # noqa: E402

KEY_FIELDS = ("model", "precision", "training_arm", "family", "task", "class")


def _row(**kw) -> dict:
    base = {
        "model": "d-fine-s",
        "precision": "fp32",
        "training_arm": "S",
        "family": "pit",
        "task": "box",
        "class": "person",
        "support": 400,
        "ap50": 0.8,
        "ap50_95": 0.5,
        "descriptive": False,
        "honesty_label": kit.HONESTY_LABEL,
        "sim_to_real": "not measured",
    }
    return base | kw


def _report(rows: list[dict]) -> dict:
    return {"run_id": "20261012T100000Z-s50", "per_class": rows}


@pytest.mark.req("FR-009-50")
def test_the_valid_contract_example_has_four_distinct_keys_and_passes() -> None:
    assert report.check_unique_rows(kit.example("detection-eval.valid.json")) is None


@pytest.mark.req("FR-009-50")
def test_a_key_that_occurs_twice_is_rejected_naming_the_key() -> None:
    rows = [
        _row(),
        _row(**{"class": "boulder"}),
        _row(ap50=0.1),
    ]  # the third row repeats the first row's key with other values
    with pytest.raises(report.ReportError) as exc:
        report.check_unique_rows(_report(rows))
    assert exc.value.code == "report-duplicate-row"
    assert exc.value.key == ("d-fine-s", "fp32", "S", "pit", "box", "person")
    assert "report-duplicate-row" in str(exc.value)
    for part in exc.value.key:
        assert part in str(exc.value)
    assert isinstance(exc.value, ValueError)


@pytest.mark.req("FR-009-50")
@pytest.mark.parametrize(
    ("field", "other"),
    [
        ("model", "d-fine-n"),
        ("precision", "fp16"),
        ("training_arm", "U"),
        ("family", "crusher"),
        ("task", "mask"),
        ("class", "shovel"),
    ],
)
def test_rows_that_differ_in_any_one_key_field_are_not_duplicates(field: str, other: str) -> None:
    assert report.check_unique_rows(_report([_row(), _row(**{field: other})])) is None


@pytest.mark.req("FR-009-50")
def test_identical_rows_twice_and_three_copies_are_rejected() -> None:
    for rows in ([_row(), _row()], [_row(), _row(), _row()]):
        with pytest.raises(report.ReportError) as exc:
            report.check_unique_rows(_report(rows))
        assert exc.value.code == "report-duplicate-row"


@pytest.mark.req("FR-009-50")
def test_the_first_duplicate_in_row_order_of_the_second_occurrence_is_named() -> None:
    a, b = {"class": "shovel"}, {"class": "boulder"}
    rows = [_row(**a), _row(**b), _row(**b), _row(**a)]  # b repeats first (position 2), a later (position 3)
    with pytest.raises(report.ReportError) as exc:
        report.check_unique_rows(_report(rows))
    assert exc.value.key[-1] == "boulder"


@pytest.mark.req("FR-009-50")
@pytest.mark.parametrize("doc", [{}, {"per_class": []}, {"per_class": None}, {"other": 1}])
def test_a_report_without_rows_has_no_duplicates(doc: dict) -> None:
    assert report.check_unique_rows(doc) is None


@pytest.mark.req("FR-009-50")
@pytest.mark.parametrize(
    "rows",
    [
        [None],
        ["row"],
        [{"model": "d-fine-s"}],
        [_row(), {**_row(), "class": None}],
        [{k: v for k, v in _row().items() if k != "task"}],
    ],
)
def test_malformed_rows_are_a_report_invalid_error(rows: list) -> None:
    with pytest.raises(report.ReportError) as exc:
        report.check_unique_rows(_report(rows))
    assert exc.value.code == "report-invalid"
    assert exc.value.key is None


@pytest.mark.req("FR-009-50")
def test_the_writer_refuses_a_duplicate_and_writes_nothing(tmp_path: Path) -> None:
    p = tmp_path / "detection-eval.json"
    with pytest.raises(report.ReportError) as exc:
        report.write_report(_report([_row(), _row()]), p)
    assert exc.value.code == "report-duplicate-row"
    assert not p.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.req("FR-009-50")
def test_the_writer_leaves_an_existing_file_untouched_when_it_refuses(tmp_path: Path) -> None:
    p = tmp_path / "detection-eval.json"
    p.write_bytes(b"previous")
    with pytest.raises(report.ReportError):
        report.write_report(_report([_row(), _row()]), p)
    assert p.read_bytes() == b"previous"


@pytest.mark.req("FR-009-50")
def test_the_writer_writes_the_canonical_bytes_of_a_clean_report_and_the_reader_returns_it(tmp_path: Path) -> None:
    doc = _report([_row(), _row(**{"class": "boulder"}), _row(task="mask", model="rf-detr-seg-n")])
    p = tmp_path / "detection-eval.json"
    report.write_report(doc, p)
    assert p.read_bytes() == report.dumps_report(doc)
    assert report.read_report(p) == doc


@pytest.mark.req("FR-009-50")
def test_the_reader_rejects_a_duplicate_in_a_file_written_by_hand(tmp_path: Path) -> None:
    doc = _report([_row(), _row(**{"class": "boulder"}), _row(ap50=0.3)])
    p = tmp_path / "hand.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(report.ReportError) as exc:
        report.read_report(p)
    assert exc.value.code == "report-duplicate-row"
    assert exc.value.key == ("d-fine-s", "fp32", "S", "pit", "box", "person")


@pytest.mark.req("FR-009-50")
@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"   ",
        b"{",
        b"[]",
        b"null",
        b'"report"',
        b"\xff\xfe\x00{}",
        b'{"per_class": [], "x": NaN}',
        b'{"per_class": [], "x": Infinity}',
        b"\x89PNG\r\n\x1a\n",
    ],
)
def test_the_reader_rejects_unreadable_and_non_object_files(tmp_path: Path, content: bytes) -> None:
    p = tmp_path / "bad.json"
    p.write_bytes(content)
    with pytest.raises(report.ReportError) as exc:
        report.read_report(p)
    assert exc.value.code == "report-invalid"


@pytest.mark.req("FR-009-50")
def test_a_missing_report_file_is_a_file_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        report.read_report(tmp_path / "absent.json")


@pytest.mark.req("FR-009-50")
def test_checking_does_not_modify_the_report() -> None:
    doc = _report([_row(), _row(**{"class": "boulder"})])
    before = copy.deepcopy(doc)
    report.check_unique_rows(doc)
    assert doc == before

# ruff: noqa: E501
"""T-009-092 - FR-009-46: a repeated `record_id` in a dataset index is rejected with `index-duplicate-record`.

Oracle (independent of the code under test; plan 009 test strategy row FR-009-46): a hand-built index fixture in which `r1` occurs twice (plus unique records around
it) is rejected with the class `index-duplicate-record` naming `r1`; the same index with the duplicate renamed `r2` is accepted. Records are the spec's valid contract
example (DC-009-01) with only the `record_id` changed, so every record is schema-valid on its own and the duplicate is the only fault.

Expected public API (module `pitstudio_pipeline.perception.loader`, see tests/unit/test_t_009_019_coco_loader.py for `read_index` and `IndexRecordError`):

    DatasetIndexError(ValueError)    .code == "index-duplicate-record"; .record_id: str (the repeated id); .lines: tuple[int, ...] (the 1-based file lines of every occurrence, () for
                                     check_unique_record_ids); str(error) contains the code and the id
    check_unique_record_ids(records: Sequence[Mapping]) -> None
        Raises DatasetIndexError naming the FIRST id (in index order) that occurs more than once; the id is named once however many copies exist. A record without a `record_id` string is ignored here
        (it fails validate_index_record elsewhere). Returns None when all ids are distinct. Ids are compared exactly (case-sensitive).
    read_index(path) -> IndexReadResult      (extension of T-009-019) additionally rejects the WHOLE index: it raises DatasetIndexError (with .lines) when two lines carry the same record_id, whether or
                                     not the lines are otherwise valid; lines that failed validation do not count towards a duplicate unless their record_id can be read.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
from pitstudio_pipeline.perception import loader  # noqa: E402


def _rec(rid: str, kind: str = "valid") -> dict:
    r = kit.index_record(kind)
    r["record_id"] = rid
    return r


def _write(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


@pytest.mark.req("FR-009-46")
def test_an_index_with_r1_twice_is_rejected_naming_r1() -> None:
    recs = [_rec("r0"), _rec("r1"), _rec("r2"), _rec("r1")]
    with pytest.raises(loader.DatasetIndexError) as exc:
        loader.check_unique_record_ids(recs)
    assert exc.value.code == "index-duplicate-record"
    assert exc.value.record_id == "r1"
    assert "index-duplicate-record" in str(exc.value)
    assert "r1" in str(exc.value)
    assert isinstance(exc.value, ValueError)


@pytest.mark.req("FR-009-46")
def test_the_same_index_with_the_duplicate_renamed_is_accepted() -> None:
    assert loader.check_unique_record_ids([_rec("r0"), _rec("r1"), _rec("r2"), _rec("r3")]) is None
    assert loader.check_unique_record_ids([]) is None
    assert loader.check_unique_record_ids([_rec("only")]) is None


@pytest.mark.req("FR-009-46")
def test_adjacent_and_distant_duplicates_and_three_copies_are_all_caught_and_named_once() -> None:
    for recs in (
        [_rec("a"), _rec("a")],
        [_rec("a"), _rec("b"), _rec("c"), _rec("d"), _rec("a")],
        [_rec("a"), _rec("a"), _rec("a")],
    ):
        with pytest.raises(loader.DatasetIndexError) as exc:
            loader.check_unique_record_ids(recs)
        assert exc.value.record_id == "a"
        assert str(exc.value).count("a") >= 1


@pytest.mark.req("FR-009-46")
def test_the_first_repeated_id_in_index_order_is_named() -> None:
    recs = [_rec("x1"), _rec("y1"), _rec("y1"), _rec("x1")]  # y1 repeats first (position 2), x1 later (position 3)
    with pytest.raises(loader.DatasetIndexError) as exc:
        loader.check_unique_record_ids(recs)
    assert exc.value.record_id == "y1"


@pytest.mark.req("FR-009-46")
def test_two_records_with_the_same_id_but_different_content_are_still_duplicates() -> None:
    with pytest.raises(loader.DatasetIndexError) as exc:
        loader.check_unique_record_ids([_rec("same", "valid"), _rec("same", "valid-crusher")])
    assert exc.value.record_id == "same"


@pytest.mark.req("FR-009-46")
def test_ids_are_compared_exactly_so_a_different_case_is_not_a_duplicate() -> None:
    assert loader.check_unique_record_ids([_rec("r1"), {**_rec("r2"), "record_id": "R1"}]) is None


@pytest.mark.req("FR-009-46")
@pytest.mark.parametrize("junk", [None, 7, "r1", [], {}, {"record_id": 5}, {"record_id": None}])
def test_entries_without_a_string_record_id_are_ignored_by_the_uniqueness_check(junk: object) -> None:
    assert loader.check_unique_record_ids([junk, junk, _rec("r1")]) is None  # type: ignore[list-item]


@pytest.mark.req("FR-009-46")
def test_reading_an_index_file_with_a_repeated_id_rejects_the_whole_index_listing_the_lines(tmp_path: Path) -> None:
    p = _write(tmp_path / "index.jsonl", [_rec("r0"), _rec("r1"), _rec("r2"), _rec("r1")])
    with pytest.raises(loader.DatasetIndexError) as exc:
        loader.read_index(p)
    assert exc.value.code == "index-duplicate-record"
    assert exc.value.record_id == "r1"
    assert exc.value.lines == (2, 4)


@pytest.mark.req("FR-009-46")
def test_a_duplicate_is_rejected_even_when_one_copy_is_otherwise_invalid(tmp_path: Path) -> None:
    bad = _rec("r1")
    bad["synthetic"] = False
    p = _write(tmp_path / "index.jsonl", [_rec("r0"), _rec("r1"), bad])
    with pytest.raises(loader.DatasetIndexError) as exc:
        loader.read_index(p)
    assert exc.value.record_id == "r1"


@pytest.mark.req("FR-009-46")
def test_an_index_file_without_duplicates_is_read_normally(tmp_path: Path) -> None:
    recs = [_rec("r0"), _rec("r1"), _rec("r2", "valid-crusher")]
    res = loader.read_index(_write(tmp_path / "index.jsonl", recs))
    assert [r["record_id"] for r in res.records] == ["r0", "r1", "r2"]
    assert res.rejected == ()

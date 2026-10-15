"""T-016-092: fixture propagation through export and bench (unit, fake GPU).

Requirements: FR-016-40.

Spec: specs/016-export-acceleration/spec.md FR-016-40: while an exported model, a golden set or a bench record is a
contract fixture, `s60_export`, `s62_accel` and `s64_bench` write `fixture: true` on every parity report, bench record
and table row, and the publication filter drops them from the Acceleration table. plan.md test strategy row FR-016-40:
a fixture golden set gives a parity report and a bench row `fixture: true`; the table bake has none of them.

Oracles: hand calculation (a fixture input yields exactly the non-fixture document plus the key `fixture: true`; a
non-fixture run adds no key; a table baked from the publication filter has no fixture row); the spec's own
bench-record examples as the base documents; the promoted schemas `contracts/bench-record.schema.json`,
`contracts/export-parity-report.schema.json` and `contracts/accel-table.schema.json`, which must declare the optional
boolean `fixture` (their draft versions reject unknown properties, so FR-016-40 needs the property in the contract).

Expected public API (root environment):
module `pitstudio.accel.fixtures`
    inputs_are_fixture(*artefacts: Mapping) -> bool        # True iff any artefact mapping has `fixture is True`
module `pitstudio.export.reports`
    make_layer1_report(result, *, run_id: str, git_sha: str, model: str, variant: str, onnx_sha256: str,
                       golden_set: Mapping, fixture: bool = False) -> dict
        `result` is a `pitstudio.export.comparator.ComparisonResult`; returns the DC-016-03 layer-1 document (layer 1,
        precision fp32, backend ort-cpu, tensorrt_version and engine_sha256 null, the constant layer-1 tolerances,
        max_abs_error, mismatch_fraction, argmax block when class scores were compared else null, metric and mask_iou
        null, verdict "pass" for a comparator `pass` else "rejected" with the reason); `fixture: true` is added only
        when `fixture` is true.
module `pitstudio.accel.layer4`
    make_parity_report(..., fixture: bool = False) -> dict     # as in tests/unit/test_t_016_044_engine_parity.py
module `pitstudio.accel.records`
    make_bench_record(cell, *, run, fingerprint, fixture: bool = False) -> dict
module `pitstudio.accel.table`
    rows_from_records(records) -> list[dict]       # a record with `fixture: true` gives a row with `fixture: true`
    publishable(records) -> list[dict]             # keeps `performance == "public"` records that are not fixtures
    bake_table(records, *, generated) -> dict      # raises ValueError for a record with `fixture: true`
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from pitstudio.accel.fixtures import inputs_are_fixture
from pitstudio.accel.layer4 import check_cell, make_parity_report
from pitstudio.accel.records import make_bench_record
from pitstudio.accel.table import bake_table, publishable, rows_from_records
from pitstudio.export.comparator import compare
from pitstudio.export.reports import make_layer1_report

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "016-export-acceleration" / "contracts" / "examples"
META = {"schema_version", "run_id", "git_sha", "date", "fingerprint", "performance"}


def _load(name: str) -> dict:
    return json.loads((EX / name).read_text(encoding="utf-8"))


def _golden() -> dict:
    return {
        "id": "b2-pit-golden-v1",
        "split": "held-out",
        "inputs": [hashlib.sha256(f"g{i}".encode()).hexdigest() for i in range(200)],
    }


def _layer1(fixture: bool) -> dict:
    ref = [np.linspace(-1, 1, 200), np.eye(4)]
    result = compare(ref, [a.copy() for a in ref], class_scores=(1,))
    return make_layer1_report(
        result,
        run_id="20261019T230000Z-b2",
        git_sha="0" * 40,
        model="d-fine-n",
        variant="parity",
        onnx_sha256=hashlib.sha256(b"onnx").hexdigest(),
        golden_set=_golden(),
        fixture=fixture,
    )


def _layer4(fixture: bool) -> dict:
    ref = [np.linspace(-1, 1, 200)]
    cell = check_cell(precision="fp32", reference=ref, candidate=[ref[0].copy()])
    return make_parity_report(
        cell,
        precision="fp32",
        run_id="20261019T230000Z-b2",
        git_sha="0" * 40,
        model="d-fine-s",
        backend="tensorrt",
        tensorrt_version="11.3.0.99",
        onnx_sha256=hashlib.sha256(b"onnx").hexdigest(),
        engine_sha256=hashlib.sha256(b"engine").hexdigest(),
        golden_set=_golden(),
        fixture=fixture,
    )


def _record(name: str, fixture: bool) -> dict:
    example = _load(name)
    cell = {k: v for k, v in example.items() if k not in META}
    run = {k: example[k] for k in ("run_id", "git_sha", "date")}
    return make_bench_record(cell, run=run, fingerprint=example["fingerprint"], fixture=fixture)


# ----------------------------------------------------------------------------------------------------------------------
# the contract must carry the field
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-40")
def test_the_promoted_schemas_declare_the_optional_boolean_fixture_property() -> None:
    bench = json.loads((ROOT / "contracts" / "bench-record.schema.json").read_text(encoding="utf-8"))
    parity = json.loads((ROOT / "contracts" / "export-parity-report.schema.json").read_text(encoding="utf-8"))
    table = json.loads((ROOT / "contracts" / "accel-table.schema.json").read_text(encoding="utf-8"))
    for name, props in (
        ("bench-record", bench["properties"]),
        ("export-parity-report", parity["properties"]),
        ("accel-table row", table["$defs"]["row"]["properties"]),
    ):
        assert props.get("fixture") == {"type": "boolean"} or props.get("fixture", {}).get("const") is True, name
    for schema in (bench, parity):
        assert "fixture" not in schema["required"]  # optional: absent for real runs


# ----------------------------------------------------------------------------------------------------------------------
# propagation
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-40")
def test_inputs_are_fixture_when_any_input_is_a_fixture() -> None:
    assert inputs_are_fixture({"fixture": True}, {}) is True
    assert inputs_are_fixture({}, {"fixture": False}, {"id": "x"}) is False
    assert inputs_are_fixture() is False
    assert inputs_are_fixture({"fixture": "true"}) is False  # only the boolean true counts


@pytest.mark.req("FR-016-40")
def test_a_fixture_golden_set_gives_a_layer1_report_marked_fixture_and_nothing_else_changes() -> None:
    real, fixture = _layer1(False), _layer1(True)
    assert "fixture" not in real
    assert fixture["fixture"] is True
    assert {k: v for k, v in fixture.items() if k != "fixture"} == real
    assert real["layer"] == 1
    assert real["verdict"] == "pass"
    assert real["argmax"]["output"]  # class scores were compared


@pytest.mark.req("FR-016-40")
def test_a_fixture_engine_gives_a_layer4_report_marked_fixture() -> None:
    real, fixture = _layer4(False), _layer4(True)
    assert "fixture" not in real
    assert fixture["fixture"] is True
    assert {k: v for k, v in fixture.items() if k != "fixture"} == real
    assert real["layer"] == 4


@pytest.mark.req("FR-016-40")
def test_a_fixture_bench_record_is_marked_fixture_and_a_real_one_is_not() -> None:
    real = _record("bench-record.valid.json", False)
    fixture = _record("bench-record.valid.json", True)
    assert real == _load("bench-record.valid.json")
    assert fixture["fixture"] is True
    assert {k: v for k, v in fixture.items() if k != "fixture"} == real


@pytest.mark.req("FR-016-40")
def test_a_fixture_record_gives_a_fixture_table_row() -> None:
    real = _record("bench-record.valid.json", False)
    fixture = _record("bench-record.valid-rejected.json", True)
    rows = rows_from_records([real, fixture])
    assert "fixture" not in rows[0]
    assert rows[1]["fixture"] is True


@pytest.mark.req("FR-016-40")
def test_the_publication_filter_drops_fixture_records_and_the_table_bake_has_none_of_them() -> None:
    real = _record("bench-record.valid.json", False)
    fixture = _record("bench-record.valid-rejected.json", True)
    not_run = _record("bench-record.valid-not-run.json", False)
    kept = publishable([real, fixture, not_run])
    assert [r["model"] + "/" + r["backend"] for r in kept] == ["d-fine-n/tensorrt", "d-fine-n/ort-tensorrt"]
    table = bake_table(kept, generated="2026-10-21")
    assert all("fixture" not in row for row in table["rows"])
    assert len(table["rows"]) == 2


@pytest.mark.req("FR-016-40")
def test_baking_a_table_from_a_fixture_record_is_refused() -> None:
    real = _record("bench-record.valid.json", False)
    fixture = _record("bench-record.valid-rejected.json", True)
    with pytest.raises(ValueError, match=r"fixture"):
        bake_table([real, fixture], generated="2026-10-21")


@pytest.mark.req("FR-016-40")
def test_publishable_does_not_mutate_its_input() -> None:
    records = [_record("bench-record.valid.json", True)]
    snapshot = copy.deepcopy(records)
    assert publishable(records) == []
    assert records == snapshot

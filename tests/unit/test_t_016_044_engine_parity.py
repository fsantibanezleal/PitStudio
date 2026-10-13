"""T-016-044: layer-4 parity per engine, kept rejected cells, bench records (unit, fake GPU, contract).

Requirements: FR-016-30, FR-016-31, FR-016-32.

Spec: specs/016-export-acceleration/spec.md
- FR-016-30: the layer-4 parity check compares every engine, on every TensorRT version and execution provider, with
  the stored PyTorch fp32 golden outputs: fp32 cells pass if every element satisfies |y - y_pt| <= 1e-5 + 1e-3 |y_pt|
  with TF32 cleared on both sides; fp16, int8 and fp8 cells pass if |delta task metric| <= 1 percentage point on the
  evaluation set (and mask IoU >= 0.99; detectors also re-run the spec 009 corruption curves); each cell gets the
  verdict `pass` or `rejected` with its maximum error, mismatch fraction and metric change;
- FR-016-31: the bench records and the published table list every `rejected`, `build-failed` or "not run" cell with its
  numbers (where measured) and its reason, and drop no cell;
- FR-016-32: one bench record (DC-016-01) per model x backend x precision x TensorRT version, with the fingerprint (GPU
  name, driver, TensorRT, ONNX Runtime and torch versions, ONNX and engine SHA-256, enforced power limit, power source,
  operating-system power mode), and a web table (DC-016-05) baked from the publishable records.
plan.md test strategy rows FR-016-30 (a fake engine adding 1e-2 to one output -> `rejected` with that maximum error; an
exact engine -> `pass`), FR-016-31 (a matrix with one rejected, one build-failed and one not-run cell -> all three
rows present with reasons), FR-016-32 (`jsonschema` on fixture records; fingerprint fields present).

Oracles:
- hand calculation for the fake engine (one element of an `n`-element output moved by exactly 1e-2: maximum error 1e-2,
  mismatch fraction 1/n);
- the spec's own example corpus (`contracts/examples/bench-record.valid*.json`, `accel-table.valid.json`,
  `export-parity-report.valid-layer4.json`): the three public bench-record examples (pass, rejected, not_run) are the
  expected output of `make_bench_record`, and the three rows of the valid table are the expected output of
  `rows_from_records` on those records (the table row fields are the record fields plus the fingerprint's power limit,
  power source and licence hash);
- JSON Schema validation (reference implementation `jsonschema`, with the contract schemas as a `referencing`
  registry) of the layer-4 parity reports against `contracts/export-parity-report.schema.json`.

Expected public API (root environment):
module `pitstudio.accel.layer4`
    check_cell(*, precision: str, reference: Sequence[np.ndarray] | None = None,
               candidate: Sequence[np.ndarray] | None = None, tf32_cleared: bool = True,
               metric: Mapping | None = None, mask_iou: float | None = None,
               requires_mask_iou: bool = False, requires_robustness: bool = False,
               robustness_ok: bool | None = None) -> CellParity
        fp32: elementwise rtol 1e-3, atol 1e-5 on `reference` vs `candidate` (no max_abs, no argmax rule); a cell whose
        TF32 flag was not cleared (`tf32_cleared` False) is rejected with a reason containing "TF32".
        other precisions: `metric` = {"id": str, "fp32": pct, "variant": pct}; pass iff |variant - fp32| <= 1 and the
        mask IoU (when required) >= 0.99 and the robustness criterion (when required) holds.
        CellParity: verdict "pass" | "rejected", reason (None iff pass), max_abs_error, mismatch_fraction,
        metric_delta_pp, mask_iou (floats or None where not applicable).
    make_parity_report(cell: CellParity, *, precision: str, run_id: str, git_sha: str, model: str, backend: str,
                       tensorrt_version: str | None, onnx_sha256: str, engine_sha256: str | None, golden_set: Mapping,
                       metric: Mapping | None = None, variant: str = "deployed") -> dict
        the DC-016-03 document of layer 4 (schema_version "1.0", layer 4, the constant tolerances of the precision).
module `pitstudio.accel.records`
    make_bench_record(cell: Mapping, *, run: Mapping, fingerprint: Mapping) -> dict
        `run` = {run_id, git_sha, date}; `cell` = the measured fields (model, backend, precision, tensorrt_version,
        status, optional reason, latency, throughput, joules_per_inference, energy_window_s, vram_peak_bytes,
        thermal_slowdown, telemetry_hz, camera_streams, parity); returns schema_version "1.0" + run + cell +
        `performance` ("public" for these fixtures) + `fingerprint`. Raises InvalidRecord for a fingerprint missing one
        of its required fields.
    check_unique_records(records: Sequence[Mapping]) -> None    # ValueError on a repeated (model, backend, precision,
                                                                # tensorrt_version) key
module `pitstudio.accel.table`
    rows_from_records(records: Sequence[Mapping]) -> list[dict]
        one table row per record, in input order, none dropped; fields as in the example table row.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from pitstudio.accel.layer4 import check_cell, make_parity_report
from pitstudio.accel.records import InvalidRecord, check_unique_records, make_bench_record
from pitstudio.accel.table import rows_from_records

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "016-export-acceleration" / "contracts" / "examples"
META = {"schema_version", "run_id", "git_sha", "date", "fingerprint", "performance"}


def _load(name: str) -> dict:
    return json.loads((EX / name).read_text(encoding="utf-8"))


def _validator(schema_file: str):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    schemas = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "contracts").glob("*.schema.json")}
    registry = Registry().with_resources([(s["$id"], Resource.from_contents(s)) for s in schemas.values()])
    return Draft202012Validator(schemas[schema_file], registry=registry)


def _golden() -> dict:
    return {
        "id": "b2-pit-golden-v1",
        "split": "held-out",
        "inputs": [hashlib.sha256(f"g{i}".encode()).hexdigest() for i in range(200)],
    }


def _report(cell, **kw) -> dict:
    base = {
        "run_id": "20261020T010000Z-b2",
        "git_sha": "0" * 40,
        "model": "d-fine-s",
        "backend": "tensorrt",
        "tensorrt_version": "11.3.0.99",
        "onnx_sha256": hashlib.sha256(b"onnx").hexdigest(),
        "engine_sha256": hashlib.sha256(b"engine").hexdigest(),
        "golden_set": _golden(),
    }
    base.update(kw)
    return make_parity_report(cell, **base)


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-30
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-30")
def test_an_exact_fp32_engine_passes() -> None:
    ref = [np.linspace(-1, 1, 200, dtype=np.float32), np.arange(12, dtype=np.float32).reshape(3, 4)]
    cell = check_cell(precision="fp32", reference=ref, candidate=[a.copy() for a in ref])
    assert cell.verdict == "pass"
    assert cell.reason is None
    assert cell.max_abs_error == 0.0
    assert cell.mismatch_fraction == 0.0


@pytest.mark.req("FR-016-30")
def test_a_fake_engine_adding_1e_minus_2_to_one_output_element_is_rejected_with_that_maximum_error() -> None:
    ref = [np.linspace(-1, 1, 200, dtype=np.float64)]
    bad = ref[0].copy()
    bad[17] += 1e-2
    cell = check_cell(precision="fp32", reference=ref, candidate=[bad])
    assert cell.verdict == "rejected"
    assert cell.reason
    assert cell.max_abs_error == pytest.approx(1e-2, rel=1e-9)
    assert cell.mismatch_fraction == pytest.approx(1 / 200)


@pytest.mark.req("FR-016-30")
def test_the_fp32_tolerance_is_elementwise_1e_minus_5_plus_1e_minus_3_abs_y_with_no_max_abs_cap() -> None:
    # reference 1000: bound = 1e-5 + 1.0 = 1.00001, so an absolute error of 0.5 (>> 1e-4) is within tolerance at layer 4
    ok = check_cell(precision="fp32", reference=[np.array([1000.0])], candidate=[np.array([1000.5])])
    assert ok.verdict == "pass"
    bad = check_cell(precision="fp32", reference=[np.array([1000.0])], candidate=[np.array([1001.1])])
    assert bad.verdict == "rejected"


@pytest.mark.req("FR-016-30")
def test_an_fp32_cell_built_without_clearing_tf32_is_rejected_naming_tf32() -> None:
    ref = [np.ones(10)]
    cell = check_cell(precision="fp32", reference=ref, candidate=[a.copy() for a in ref], tf32_cleared=False)
    assert cell.verdict == "rejected"
    assert "TF32" in cell.reason


@pytest.mark.req("FR-016-30")
@pytest.mark.parametrize("precision", ["fp16", "int8", "fp8"])
@pytest.mark.parametrize(
    ("variant", "verdict"), [(70.5, "pass"), (72.5, "pass"), (70.49, "rejected"), (72.51, "rejected")]
)
def test_reduced_precision_cells_are_judged_on_the_task_metric_change_of_one_point(precision, variant, verdict) -> None:
    metric = {"id": "map50", "fp32": 71.5, "variant": variant}  # dyadic fp32 value: the 1 pp boundary is exact
    cell = check_cell(precision=precision, metric=metric)
    assert cell.verdict == verdict
    assert cell.metric_delta_pp == pytest.approx(variant - 71.5, abs=1e-12)
    assert (cell.reason is None) == (verdict == "pass")


@pytest.mark.req("FR-016-30")
def test_reduced_precision_mask_iou_and_robustness_criteria() -> None:
    m = {"id": "miou", "fp32": 80.0, "variant": 80.0}
    assert check_cell(precision="int8", metric=m, mask_iou=0.99, requires_mask_iou=True).verdict == "pass"
    assert check_cell(precision="int8", metric=m, mask_iou=0.989, requires_mask_iou=True).verdict == "rejected"
    assert check_cell(precision="int8", metric=m, mask_iou=None, requires_mask_iou=True).verdict == "rejected"
    assert check_cell(precision="fp16", metric=m, requires_robustness=True, robustness_ok=False).verdict == "rejected"
    assert check_cell(precision="fp16", metric=m, requires_robustness=True, robustness_ok=True).verdict == "pass"


@pytest.mark.req("FR-016-30")
def test_a_non_finite_engine_output_is_rejected_never_passed() -> None:
    ref = [np.ones(50)]
    bad = np.ones(50)
    bad[3] = np.nan
    assert check_cell(precision="fp32", reference=ref, candidate=[bad]).verdict == "rejected"


@pytest.mark.req("FR-016-30")
def test_the_layer4_report_of_an_exact_fp32_engine_validates_against_dc_016_03() -> None:
    ref = [np.linspace(-1, 1, 200)]
    cell = check_cell(precision="fp32", reference=ref, candidate=[ref[0].copy()])
    doc = _report(cell, precision="fp32")
    assert list(_validator("export-parity-report.schema.json").iter_errors(doc)) == []
    assert doc["layer"] == 4
    assert doc["precision"] == "fp32"
    assert doc["verdict"] == "pass"
    assert doc["tolerances"]["rtol"] == 0.001
    assert doc["tolerances"]["atol"] == 1e-05
    assert doc["mismatch_fraction"] == 0
    assert doc["golden_set"]["inputs"] == _golden()["inputs"]


@pytest.mark.req("FR-016-30")
def test_the_layer4_report_of_a_rejected_fp32_engine_keeps_its_numbers_and_reason() -> None:
    ref = [np.linspace(-1, 1, 200)]
    bad = ref[0].copy()
    bad[0] += 1e-2
    cell = check_cell(precision="fp32", reference=ref, candidate=[bad])
    doc = _report(cell, precision="fp32")
    assert list(_validator("export-parity-report.schema.json").iter_errors(doc)) == []
    assert doc["verdict"] == "rejected"
    assert doc["reason"]
    assert doc["max_abs_error"] == pytest.approx(1e-2, rel=1e-9)
    assert doc["mismatch_fraction"] == pytest.approx(1 / 200)


@pytest.mark.req("FR-016-30")
@pytest.mark.parametrize(("variant", "verdict"), [(70.8, "pass"), (68.0, "rejected")])
def test_the_layer4_report_of_a_reduced_precision_engine_carries_the_metric_change(variant, verdict) -> None:
    metric = {"id": "map50", "fp32": 71.4, "variant": variant}
    cell = check_cell(precision="int8", metric=metric)
    doc = _report(cell, precision="int8", metric=metric)
    assert list(_validator("export-parity-report.schema.json").iter_errors(doc)) == []
    assert doc["verdict"] == verdict
    assert doc["metric"]["fp32"] == 71.4
    assert doc["metric"]["variant"] == variant
    assert doc["metric"]["delta_pp"] == pytest.approx(variant - 71.4)
    assert doc["tolerances"]["metric_delta_pp_max"] == 1
    assert doc["tolerances"]["mask_iou_min"] == 0.99


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-31 and FR-016-32
# ----------------------------------------------------------------------------------------------------------------------


def _examples() -> list[dict]:
    return [
        _load("bench-record.valid.json"),
        _load("bench-record.valid-rejected.json"),
        _load("bench-record.valid-not-run.json"),
    ]


@pytest.mark.req("FR-016-31")
def test_the_table_rows_equal_the_spec_example_rows_and_drop_no_cell() -> None:
    rows = rows_from_records(_examples())
    assert rows == _load("accel-table.valid.json")["rows"]
    assert len(rows) == 3


@pytest.mark.req("FR-016-31")
def test_rejected_build_failed_and_not_run_cells_all_appear_with_reasons_and_their_numbers() -> None:
    passed, rejected, not_run = _examples()
    build_failed = copy.deepcopy(not_run)
    build_failed.update(
        model="d-fine-m", backend="tensorrt", precision="fp8", status="build-failed", tensorrt_version="11.3.0.99"
    )
    build_failed["reason"] = "engine build failed: Internal error: plugin 'GridSample' failed"
    rows = rows_from_records([passed, rejected, not_run, build_failed])
    by_status = {r["status"]: r for r in rows}
    assert set(by_status) == {"pass", "rejected", "not_run", "build-failed"}
    assert len(rows) == 4
    assert by_status["rejected"]["reason"] == rejected["reason"]
    assert by_status["rejected"]["parity"]["max_abs_error"] == 0.83  # its measured numbers are kept
    assert by_status["rejected"]["latency"] == rejected["latency"]
    assert by_status["not_run"]["reason"] == not_run["reason"]
    assert by_status["not_run"]["latency"] is None
    assert by_status["build-failed"]["reason"].startswith("engine build failed")
    assert "reason" not in by_status["pass"]


@pytest.mark.req("FR-016-31")
def test_an_empty_record_list_gives_no_rows() -> None:
    assert rows_from_records([]) == []


@pytest.mark.req("FR-016-32")
@pytest.mark.parametrize(
    "name", ["bench-record.valid.json", "bench-record.valid-rejected.json", "bench-record.valid-not-run.json"]
)
def test_make_bench_record_reproduces_the_spec_example_with_its_fingerprint(name: str) -> None:
    example = _load(name)
    cell = {k: v for k, v in example.items() if k not in META}
    run = {k: example[k] for k in ("run_id", "git_sha", "date")}
    record = make_bench_record(cell, run=run, fingerprint=example["fingerprint"])
    assert record == example
    for field in (
        "gpu_name",
        "driver",
        "ort_version",
        "torch_version",
        "onnx_sha256",
        "engine_sha256",
        "power_limit_enforced_w",
        "power_source",
        "os_power_mode",
    ):
        assert field in record["fingerprint"]


@pytest.mark.req("FR-016-32")
@pytest.mark.parametrize(
    "missing", ["gpu_name", "driver", "ort_version", "torch_version", "power_source", "os_power_mode"]
)
def test_a_fingerprint_missing_a_required_field_is_refused(missing: str) -> None:
    example = _load("bench-record.valid.json")
    cell = {k: v for k, v in example.items() if k not in META}
    run = {k: example[k] for k in ("run_id", "git_sha", "date")}
    fingerprint = {k: v for k, v in example["fingerprint"].items() if k != missing}
    with pytest.raises(InvalidRecord):
        make_bench_record(cell, run=run, fingerprint=fingerprint)


@pytest.mark.req("FR-016-32")
def test_one_record_per_model_backend_precision_and_tensorrt_version() -> None:
    a = _load("bench-record.valid.json")
    b = copy.deepcopy(a)
    b["tensorrt_version"] = "10.14.1.48"  # another TensorRT version is another record
    assert check_unique_records([a, b]) is None
    with pytest.raises(ValueError, match=r"d-fine-n"):
        check_unique_records([a, copy.deepcopy(a)])

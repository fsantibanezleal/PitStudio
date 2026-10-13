"""T-016-045: engine acceptance and matrix wall time on the bench records (pipeline, acceptance).

Requirements: SC-016-01, NFR-016-02.

Spec: specs/016-export-acceleration/spec.md
- SC-016-01: per-engine parity on every TensorRT version and execution provider: fp32 rtol 1e-3 / atol 1e-5, reduced
  precision |delta| <= 1 percentage point; failing variants are reported as rejected, none dropped (measured by the
  `s64_bench` records);
- NFR-016-02: `s62_accel` + `s64_bench` for the full model matrix take at most 8 h of wall time (one overnight slot;
  estimate 4 to 7 GPU-hours, measured and recorded), every cell being a resumable, cached unit (measured by the run
  manifest). plan.md: NFR-016-02 is a contract test: run manifest wall time <= 8 h; cells cached individually.

Oracles:
- the spec's own bench-record examples (`contracts/examples/bench-record.valid.json`: d-fine-n / tensorrt / fp16, pass,
  metric change -0.4 pp; `bench-record.valid-rejected.json`: d-fine-s / tensorrt / fp32, rejected, mismatch 0.41;
  `bench-record.valid-not-run.json`: d-fine-n / ort-tensorrt / int8, not_run) and one-field variations written by hand;
- the criteria are recomputed from the numbers in the record (the stored `status` and `parity.verdict` are never
  trusted): fp32 `pass` needs parity rtol 0.001, atol 1e-05, mismatch fraction 0 and a measured maximum error; reduced
  precision `pass` needs |metric_delta_pp| <= 1 and mask IoU >= 0.99 when measured;
- 8 h = 28,800 s (hand arithmetic); a run manifest stage carries `key`, `status`, `wall_s` and `cache` ("hit" or
  "miss"; contracts/manifest.schema.json `$defs/stage`).

Expected public API (module `pitstudio.accel.acceptance`, root environment, pure Python):
    @dataclass EngineAcceptance                   # ok: bool, problems: list[str]
    engine_acceptance(records: Sequence[Mapping], expected_cells: Sequence[tuple[str, str, str, str | None]])
        -> EngineAcceptance
        `expected_cells` = (model, backend, precision, tensorrt_version) keys of the full matrix. Problems (strings
        naming the cell, containing one of "missing", "parity", "reason", "verdict"): an expected cell with no
        record (a dropped cell); a record with status "pass" whose numbers violate the criteria above; a record with
        status "rejected", "build-failed" or "not_run" and no reason. A record that failed its parity numbers and is
        stored as "rejected" with a reason is correct (not a problem).
    @dataclass MatrixTime                         # wall_s: float, ok: bool, problems: list[str]
    matrix_wall_time(run_manifest: Mapping) -> MatrixTime
        wall_s = sum of `wall_s` over the stages whose `key` starts with "s62_accel" or "s64_bench"; ok iff wall_s <=
        28,800 and every such stage has `cache` in {"hit", "miss"} and a finite non-negative `wall_s`; problems name the
        stage key and contain "wall" or "cache".
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest
from pitstudio.accel.acceptance import engine_acceptance, matrix_wall_time

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "016-export-acceleration" / "contracts" / "examples"
CELLS = [
    ("d-fine-n", "tensorrt", "fp16", "11.3.0.99"),
    ("d-fine-s", "tensorrt", "fp32", "11.3.0.99"),
    ("d-fine-n", "ort-tensorrt", "int8", None),
]


def _load(name: str) -> dict:
    return json.loads((EX / name).read_text(encoding="utf-8"))


def _records() -> list[dict]:
    return [
        _load("bench-record.valid.json"),
        _load("bench-record.valid-rejected.json"),
        _load("bench-record.valid-not-run.json"),
    ]


def _fp32_pass() -> dict:
    rec = _load("bench-record.valid-rejected.json")
    rec["status"] = "pass"
    del rec["reason"]
    rec["parity"].update(
        verdict="pass", rtol=0.001, atol=1e-05, max_abs_error=3e-6, mismatch_fraction=0, metric_delta_pp=None
    )
    return rec


def _problems(records: list[dict], cells=CELLS) -> list[str]:
    result = engine_acceptance(records, cells)
    assert result.ok == (not result.problems)
    return result.problems


# ----------------------------------------------------------------------------------------------------------------------
# SC-016-01
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("SC-016-01")
def test_the_spec_example_matrix_is_accepted_with_its_rejected_and_not_run_cells_kept() -> None:
    assert _problems(_records()) == []


@pytest.mark.req("SC-016-01")
def test_a_cell_with_no_record_is_a_dropped_cell_and_a_problem_naming_it() -> None:
    problems = _problems(_records()[:2])  # the not_run cell was dropped
    assert len(problems) == 1
    assert "missing" in problems[0]
    assert "ort-tensorrt" in problems[0]
    assert "int8" in problems[0]


@pytest.mark.req("SC-016-01")
def test_every_tensorrt_version_is_its_own_cell() -> None:
    cells = [*CELLS, ("d-fine-n", "tensorrt", "fp16", "10.14.1.48")]
    problems = _problems(_records(), cells)
    assert len(problems) == 1
    assert "10.14" in problems[0]


@pytest.mark.req("SC-016-01")
def test_a_passing_fp32_engine_with_the_preregistered_tolerances_and_zero_mismatch_is_accepted() -> None:
    records = [_records()[0], _fp32_pass(), _records()[2]]
    assert _problems(records) == []


@pytest.mark.req("SC-016-01")
@pytest.mark.parametrize(
    ("field", "value"),
    [("mismatch_fraction", 1e-6), ("rtol", 0.01), ("atol", 1e-4), ("max_abs_error", None)],
)
def test_a_pass_record_whose_fp32_numbers_violate_the_criteria_is_a_problem(field: str, value: object) -> None:
    bad = _fp32_pass()
    bad["parity"][field] = value
    problems = _problems([_records()[0], bad, _records()[2]])
    assert problems
    assert all("d-fine-s" in p for p in problems)
    assert any("parity" in p or "verdict" in p for p in problems)


@pytest.mark.req("SC-016-01")
@pytest.mark.parametrize(("delta", "ok"), [(1.0, True), (-1.0, True), (0.0, True), (1.01, False), (-1.5, False)])
def test_reduced_precision_pass_needs_the_metric_change_within_one_point(delta: float, ok: bool) -> None:
    rec = _records()[0]
    rec["parity"]["metric_delta_pp"] = delta
    problems = _problems([rec, _records()[1], _records()[2]])
    assert (problems == []) is ok


@pytest.mark.req("SC-016-01")
@pytest.mark.parametrize(("iou", "ok"), [(0.99, True), (1.0, True), (0.98, False)])
def test_reduced_precision_pass_with_a_measured_mask_iou_needs_at_least_099(iou: float, ok: bool) -> None:
    rec = _records()[0]
    rec["parity"]["mask_iou"] = iou
    assert (_problems([rec, _records()[1], _records()[2]]) == []) is ok


@pytest.mark.req("SC-016-01")
def test_a_failing_engine_stored_as_pass_is_a_verdict_problem_but_stored_as_rejected_it_is_correct() -> None:
    lying = _records()[1]  # d-fine-s fp32 with mismatch 0.41, stored as rejected with a reason: correct
    assert _problems(_records()) == []
    lying["status"] = "pass"  # the same numbers stored as pass
    del lying["reason"]
    lying["parity"]["verdict"] = "pass"
    problems = _problems([_records()[0], lying, _records()[2]])
    assert problems
    assert any("parity" in p or "verdict" in p for p in problems)


@pytest.mark.req("SC-016-01")
@pytest.mark.parametrize("status", ["rejected", "build-failed", "not_run"])
def test_a_non_pass_cell_without_a_reason_is_a_problem(status: str) -> None:
    rec = copy.deepcopy(_records()[2])  # the not_run example, re-labelled
    rec["status"] = status
    rec.pop("reason", None)
    problems = _problems([_records()[0], _records()[1], rec])
    assert any("reason" in p for p in problems)


@pytest.mark.req("SC-016-01")
def test_a_build_failed_cell_with_a_reason_is_accepted_and_counts_as_present() -> None:
    rec = copy.deepcopy(_records()[2])
    rec["status"] = "build-failed"
    rec["reason"] = "engine build failed: out of memory"
    assert _problems([_records()[0], _records()[1], rec]) == []


# ----------------------------------------------------------------------------------------------------------------------
# NFR-016-02
# ----------------------------------------------------------------------------------------------------------------------


def _stage(key: str, wall_s: float, cache: str | None = "miss") -> dict:
    stage = {"key": key, "status": "succeeded", "wall_s": wall_s}
    if cache is not None:
        stage["cache"] = cache
    return stage


@pytest.mark.req("NFR-016-02")
def test_matrix_wall_time_sums_the_accel_and_bench_stages_only() -> None:
    manifest = {
        "stages": [
            _stage("s60_export", 90_000.0),  # not part of the matrix
            _stage("s62_accel:d-fine-n:fp32", 3_600.0),
            _stage("s64_bench:d-fine-n:fp32", 7_200.0, "hit"),
        ]
    }
    result = matrix_wall_time(manifest)
    assert result.wall_s == 10_800.0
    assert result.ok
    assert result.problems == []


@pytest.mark.req("NFR-016-02")
def test_eight_hours_is_the_limit() -> None:
    at = {"stages": [_stage("s62_accel:a", 20_000.0), _stage("s64_bench:a", 8_800.0)]}  # exactly 28,800 s
    over = {"stages": [_stage("s62_accel:a", 20_000.0), _stage("s64_bench:a", 8_800.5)]}
    assert matrix_wall_time(at).ok
    assert matrix_wall_time(at).wall_s == 28_800.0
    result = matrix_wall_time(over)
    assert not result.ok
    assert any("wall" in p for p in result.problems)


@pytest.mark.req("NFR-016-02")
def test_every_matrix_cell_must_record_whether_it_was_a_cache_hit_or_miss() -> None:
    manifest = {"stages": [_stage("s62_accel:a:fp32", 10.0, None), _stage("s64_bench:a:fp32", 10.0, "hit")]}
    result = matrix_wall_time(manifest)
    assert not result.ok
    assert any("cache" in p and "s62_accel:a:fp32" in p for p in result.problems)


@pytest.mark.req("NFR-016-02")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_a_non_finite_or_negative_stage_time_is_a_problem_not_a_total(bad: float) -> None:
    result = matrix_wall_time({"stages": [_stage("s64_bench:a", bad)]})
    assert not result.ok
    assert any("wall" in p for p in result.problems)
    assert math.isfinite(result.wall_s)


@pytest.mark.req("NFR-016-02")
def test_a_manifest_without_matrix_stages_has_zero_wall_time() -> None:
    result = matrix_wall_time({"stages": [_stage("s60_export", 5.0)]})
    assert (result.wall_s, result.ok) == (0.0, True)

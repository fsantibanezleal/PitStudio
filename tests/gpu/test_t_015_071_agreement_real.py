# ruff: noqa: E501
"""T-015-071 (GPU, reference machine): the agreement gate on the real 500-query subset. Marked `gpu`: never run in CI and not run in the red phase.

Requirements: FR-015-14.

Spec: specs/015-vlm/spec.md FR-015-14 (the gate compares Q8_0 and BF16 on a fixed subset of 500 binary task-A queries - 100 per binary type, 50 yes and 50 no, conditions stratified - with greedy
decoding, reasoning off and identical prompts and image preprocessing; agreement a is the fraction of queries with identical normalised answers; the gate passes if and only if a >= 0.95, and its
Wilson 95 % interval is reported); SC-015-01; FR-015-15 (a failed gate is a legitimate outcome: the Q8_0 path is then published only as rejected).

This test does NOT assert that the quantisation passes: that is the measured outcome of the run, pre-registered and reported either way. It asserts that the real run follows the protocol and that
its report is internally consistent: the subset has the prescribed composition, both paths answered every query, the decision equals the threshold rule, the Wilson interval is the closed-form one of
the measured count, and the gate object follows the metrics contract.

Oracle: the composition rules written in the spec; agreement recomputed here by counting equal answers of the two answer lists the stage wrote; the Wilson score interval written out in `_p015_kit.wilson`
(checked against SciPy in tests/pipeline/test_t_015_036_reference_parity.py); the metrics schema (`jsonschema`).

Prerequisites (asserted with a message, never skipped): a CUDA device; `PITSTUDIO_MODELS`, `PITSTUDIO_TMP` as in tests/gpu/test_t_015_070_reason_local.py; `PITSTUDIO_DATA` holding the committed query set and
frame states of the SDG stage (`reason/task_a/queries.json`, `reason/task_a/frames/`), which the scheduled job produces from spec 009.

Expected API of the implementation: `pitstudio_pipeline.reason.stages.run_stage("st59_reason_bench", ..., gate_queries=<query set path>, frames=<frame state folder>)` as in test_t_015_070_reason_local.py; it
writes `out_dir / "gate.json"` (the metrics `gate` object) and `out_dir / "gate_answers.json"` (`{"q8_0": {query_id: label}, "bf16": {query_id: label}, "query_ids": [...]}` in query order).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pitstudio.reason.gate import validate_gate_subset
from pitstudio_pipeline.reason import runtime, stages

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "unit"))  # the shared kit lives in tests/unit
import _p015_contracts as contracts  # noqa: E402
import _p015_kit as kit  # noqa: E402


def _need(var: str) -> Path:
    val = os.environ.get(var)
    assert val, f"{var} must be set by the scheduled GPU job"
    p = Path(val)
    assert p.is_dir(), f"{var}={val} is not a folder"
    return p


@pytest.fixture(scope="module")
def gate_run() -> dict:
    import torch

    assert torch.cuda.is_available(), (
        "this test needs a CUDA device (it is marked gpu and runs only in the scheduled GPU job)"
    )
    models, tmp, data = _need("PITSTUDIO_MODELS"), _need("PITSTUDIO_TMP"), _need("PITSTUDIO_DATA")
    pins_path = ROOT / "studio" / "reason" / "pins.json"
    runtime.load_pins(pins_path)
    queries = data / "reason" / "task_a" / "queries.json"
    assert queries.is_file(), f"{queries} is missing: the SDG stage of spec 009 must have written the task-A query set"
    out = tmp / "reason-gate"
    code = stages.run_stage(
        "st59_reason_bench",
        pins_path=pins_path,
        archive_dir=models / "llama.cpp" / "archives",
        runtime_dir=models / "llama.cpp" / "b11381",
        repo_root=ROOT,
        launcher=subprocess.Popen,
        out_dir=out,
        models_dir=models,
        hub_dir=models / "hub",
        gate_queries=queries,
        frames=data / "reason" / "task_a" / "frames",
    )
    assert code == 0
    doc = json.loads(queries.read_text(encoding="utf-8"))
    return {
        "gate": json.loads((out / "gate.json").read_text(encoding="utf-8")),
        "answers": json.loads((out / "gate_answers.json").read_text(encoding="utf-8")),
        "queries": [q for q in doc["queries"] if q["gate_subset"]],
    }


@pytest.mark.gpu
@pytest.mark.req("FR-015-14")
def test_the_real_gate_subset_has_the_prescribed_composition(gate_run: dict) -> None:
    qs = gate_run["queries"]
    validate_gate_subset(qs)  # 500 queries, 100 per binary type, 50 yes and 50 no, none of type 3
    assert Counter(q["type"] for q in qs) == dict.fromkeys((1, 2, 4, 5, 6), 100)
    for t in (1, 2, 4, 5, 6):
        cond = Counter(q["condition"] for q in qs if q["type"] == t)
        assert set(cond) == {"day", "night", "dust", "rain"}
        assert min(cond.values()) >= 20  # conditions stratified: at least 20 % of the 100 queries of a type


@pytest.mark.gpu
@pytest.mark.req("FR-015-14")
def test_both_paths_answered_every_query_of_the_subset_in_the_same_order(gate_run: dict) -> None:
    ans = gate_run["answers"]
    ids = [q["query_id"] for q in gate_run["queries"]]
    assert ans["query_ids"] == ids
    for path in ("q8_0", "bf16"):
        assert set(ans[path]) == set(ids)
        assert len(ans[path]) == 500
        assert set(ans[path].values()) <= {"yes", "no", "unparseable"}


@pytest.mark.gpu
@pytest.mark.req("FR-015-14")
@pytest.mark.req("SC-015-01")
def test_the_reported_gate_is_consistent_with_the_answers_the_threshold_rule_and_the_wilson_interval(
    gate_run: dict,
) -> None:
    gate, ans = gate_run["gate"], gate_run["answers"]
    agree = sum(1 for qid in ans["query_ids"] if ans["q8_0"][qid] == ans["bf16"][qid])
    assert gate["n"] == 500
    assert gate["agree"] == agree
    assert gate["agreement"] == pytest.approx(agree / 500, abs=1e-12)
    assert gate["threshold"] == 0.95
    assert gate["status"] == (
        "pass" if agree / 500 >= 0.95 else "fail"
    )  # the decision is the point-estimate rule, whatever the measured value is
    assert gate["q8_0_path"] == ("accepted" if gate["status"] == "pass" else "rejected")
    lo, hi = kit.wilson(agree, 500)
    assert gate["wilson95"]["lo"] == pytest.approx(lo, abs=1e-9)
    assert gate["wilson95"]["hi"] == pytest.approx(hi, abs=1e-9)


@pytest.mark.gpu
@pytest.mark.req("FR-015-14")
def test_the_reported_gate_object_follows_the_metrics_contract(gate_run: dict) -> None:
    base = contracts.validator("vlm-metrics.schema.json").schema["$id"]
    v = Draft202012Validator({"$ref": base + "#/$defs/gate"}, registry=contracts._registry())
    assert [e.message for e in v.iter_errors(gate_run["gate"])] == []

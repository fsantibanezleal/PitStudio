# ruff: noqa: E501
"""T-009-050 (acceptance half): SC-009-04 and FR-009-31 on the published evaluation report (data-and-models phase).

Requirements: SC-009-04, FR-009-31.

Spec: specs/009-perception/spec.md section 5 (SC-009-04: "structured DR better" is stated only when the FR-009-31 interval excludes 0 in its favour, otherwise "no significant
difference" (or "worse")) and FR-009-31 (d = mAP50(S) - mAP50(U) of D-FINE-S on the pit-family test images, 95 % paired cluster-bootstrap percentile interval over test scenario seeds,
B = 10,000, identical resample indices; verdict "better" if lower > 0, "worse" if upper < 0, else "no significant difference"), run layout as in tests/pipeline/test_t_009_034_acceptance.py.

Oracle: the published report read with `json`; the verdict is re-derived from the stored interval by the decision rule typed out here, and the difference is re-derived from the per-class rows
(unweighted mean of AP50 over classes with support >= 100, arms S and U, D-FINE-S fp32, family pit). Red until the data-and-models phase publishes the first evaluation run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "web" / "public" / "assets" / "runs"


def _report() -> dict:
    found = []
    if RUNS.is_dir():
        for m in sorted(RUNS.glob("*/manifest.json")):
            doc = json.loads(m.read_text(encoding="utf-8"))
            stages = doc.get("stages", []) if doc.get("kind") == "run" else []
            if (
                any(s["key"]["id"] == "s50_evaluate" and s["status"] == "succeeded" for s in stages)
                and (m.parent / "detection-eval.json").is_file()
            ):
                found.append(json.loads((m.parent / "detection-eval.json").read_text(encoding="utf-8")))
    assert found, f"no published evaluation run under {RUNS.relative_to(ROOT)} (data-and-models phase)"
    return found[-1]


def _derived_verdict(lower: float, upper: float) -> str:
    if lower > 0:
        return "better"
    if upper < 0:
        return "worse"
    return "no significant difference"


def _pit_map50(rep: dict, arm: str) -> float:
    rows = [
        r
        for r in rep["per_class"]
        if (r["model"], r["precision"], r["training_arm"], r["family"], r["task"])
        == ("d-fine-s", "fp32", arm, "pit", "box")
        and r["support"] >= 100
    ]
    assert rows, f"no pit-family box rows with support >= 100 for D-FINE-S fp32 arm {arm}"
    return sum(r["ap50"] for r in rows) / len(rows)


@pytest.mark.req("FR-009-31")
def test_the_report_carries_the_dr_ablation_of_d_fine_s_on_the_pit_family() -> None:
    abl = _report()["dr_ablation"]
    assert (abl["model"], abl["precision"], abl["metric"], abl["family"], abl["arm_a"], abl["arm_b"]) == (
        "d-fine-s",
        "fp32",
        "map50",
        "pit",
        "S",
        "U",
    )
    assert abl["bootstrap"]["resamples"] == 10000
    assert abl["bootstrap"]["method"] == "paired-cluster-percentile"
    assert abl["bootstrap"]["cluster"] == "test-scenario-seed"
    assert abl["bootstrap"]["level"] == 0.95
    assert abl["bootstrap"]["identical_resample_indices"] is True
    assert abl["training_runs_per_arm"] >= 1
    assert abl["test_seeds"] >= 2
    assert abl["test_images"] >= abl["test_seeds"]


@pytest.mark.req("FR-009-31")
def test_the_difference_equals_the_two_arms_pit_map50_re_derived_from_the_per_class_rows() -> None:
    rep = _report()
    assert rep["dr_ablation"]["difference"] == pytest.approx(_pit_map50(rep, "S") - _pit_map50(rep, "U"), abs=1e-9)


@pytest.mark.req("SC-009-04")
def test_the_stored_verdict_follows_from_the_interval_by_the_decision_rule() -> None:
    abl = _report()["dr_ablation"]
    lo, hi = abl["interval"]["lower"], abl["interval"]["upper"]
    assert -1.0 <= lo <= hi <= 1.0
    assert abl["verdict"] == _derived_verdict(lo, hi)


@pytest.mark.req("SC-009-04")
def test_structured_dr_better_is_stated_only_when_the_interval_excludes_zero_in_its_favour() -> None:
    abl = _report()["dr_ablation"]
    if abl["verdict"] == "better":
        assert abl["interval"]["lower"] > 0.0
        assert abl["difference"] > 0.0
    else:
        assert abl["verdict"] in {"worse", "no significant difference"}
    text = json.dumps(_report()).lower()
    assert ("structured dr better" not in text) or abl["verdict"] == "better"

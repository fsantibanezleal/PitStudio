# ruff: noqa: E501
"""T-009-034: acceptance on the published evaluation report (data-and-models phase): SC-009-01, SC-009-02, SC-009-05, SC-009-06.

Requirements: SC-009-01, SC-009-02, SC-009-05, SC-009-06.

Spec: specs/009-perception/spec.md section 5 (SC-009-01: D-FINE-S fp32, arm S, pooled synthetic held-out set, mAP50 >= 0.80 (point
estimate, 95 % interval reported); SC-009-02: D-FINE-N fp32 mAP50 >= 0.70; SC-009-05: RF-DETR-Seg-N fp32 mask AP50 >= 0.70 on pit-family
held-out images; SC-009-06: RF-DETR-Seg-N fp16 against fp32 |delta mask AP50| <= 1 percentage point), FR-009-22 (mAP50 = unweighted mean over the
classes with >= 100 test instances), FR-009-23 (mask AP on pit-family images), and spec 002 (a published run manifest is
`web/public/assets/runs/<run_id>/manifest.json`, FR-002-48, DC-002-03).

Oracle: the published report itself, read with `json` and re-derived by an independent script in this file: the mAP50 of a model is the
unweighted mean of the per-class AP50 values of its rows whose support is >= 100 (no code under test is used), compared with the thresholds typed
out from the spec. This acceptance test is red until the data-and-models phase publishes the first evaluation run: it asserts that such a run exists.

Expected layout: `web/public/assets/runs/<run_id>/manifest.json` (a run manifest of `contracts/manifest.schema.json`) whose `stages` hold a
succeeded `s50_evaluate` stage (`key.id`, `status`), and next to it `detection-eval.json` (DC-009-05, `contracts/detection-eval.schema.json`).
The latest such run (by run id) is judged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "web" / "public" / "assets" / "runs"
MIN_SUPPORT = 100
SC = {
    "SC-009-01": 0.80,
    "SC-009-02": 0.70,
    "SC-009-05": 0.70,
}  # point-estimate thresholds typed from spec 009 section 5
SC06_PP = 1.0


def _evaluation_runs() -> list[tuple[Path, dict]]:
    if not RUNS.is_dir():
        return []
    out = []
    for m in sorted(RUNS.glob("*/manifest.json")):
        doc = json.loads(m.read_text(encoding="utf-8"))
        stages = doc.get("stages", []) if doc.get("kind") == "run" else []
        if (
            any(s["key"]["id"] == "s50_evaluate" and s["status"] == "succeeded" for s in stages)
            and (m.parent / "detection-eval.json").is_file()
        ):
            out.append((m.parent, json.loads((m.parent / "detection-eval.json").read_text(encoding="utf-8"))))
    return out


def _report() -> dict:
    runs = _evaluation_runs()
    assert runs, (
        f"no published run under {RUNS.relative_to(ROOT)} has a succeeded s50_evaluate stage with a detection-eval.json (data-and-models phase)"
    )
    return runs[-1][1]


def _mean_ap50(report: dict, *, model: str, precision: str, family: str, task: str) -> tuple[float, list[str]]:
    rows = [
        r
        for r in report["per_class"]
        if (r["model"], r["precision"], r["training_arm"], r["family"], r["task"])
        == (model, precision, "S", family, task)
        and r["support"] >= MIN_SUPPORT
    ]
    assert rows, f"no per-class rows with support >= {MIN_SUPPORT} for {model} {precision} arm S {family} {task}"
    return sum(r["ap50"] for r in rows) / len(rows), sorted(r["class"] for r in rows)


def _row(report: dict, criterion: str) -> dict:
    rows = [r for r in report["acceptance"] if r["criterion"] == criterion and "corruption" not in r]
    assert len(rows) == 1, f"{criterion}: expected exactly one acceptance row, found {len(rows)}"
    return rows[0]


@pytest.mark.req("SC-009-01")
def test_the_data_phase_has_published_an_evaluation_run() -> None:
    assert _evaluation_runs(), f"no published evaluation run under {RUNS.relative_to(ROOT)}"


@pytest.mark.req("SC-009-01")
def test_the_published_report_validates_against_the_detection_eval_schema() -> None:
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "contracts" / "detection-eval.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(_report())) == []


@pytest.mark.req("SC-009-01")
def test_d_fine_s_fp32_arm_s_reaches_a_pooled_map50_of_at_least_0_80() -> None:
    rep = _report()
    value, classes = _mean_ap50(rep, model="d-fine-s", precision="fp32", family="pooled", task="box")
    assert value >= SC["SC-009-01"], f"mAP50 {value:.4f} over {classes} is below 0.80"
    row = _row(rep, "SC-009-01")
    assert row["verdict"] == "pass"
    assert row["value"] == pytest.approx(value, abs=1e-9)  # the stored value is the independently re-derived one
    assert (row["model"], row["precision"], row["statistic"], row["threshold"]) == ("d-fine-s", "fp32", "map50", 0.8)


@pytest.mark.req("SC-009-01")
def test_the_95_percent_interval_of_the_d_fine_s_map50_is_reported_around_the_point_estimate() -> None:
    rep = _report()
    value, _ = _mean_ap50(rep, model="d-fine-s", precision="fp32", family="pooled", task="box")
    (summary,) = [
        s
        for s in rep["summary"]
        if (s["model"], s["precision"], s["training_arm"], s["family"], s["task"], s["metric"])
        == ("d-fine-s", "fp32", "S", "pooled", "box", "map50")
    ]
    assert summary["value"] == pytest.approx(value, abs=1e-9)
    assert summary["interval"]["lower"] <= summary["interval"]["upper"]
    assert 0.0 <= summary["interval"]["lower"] <= 1.0
    assert 0.0 <= summary["interval"]["upper"] <= 1.0
    assert rep["bootstrap"]["level"] == 0.95
    assert rep["bootstrap"]["resamples"] == 2000


@pytest.mark.req("SC-009-02")
def test_d_fine_n_fp32_reaches_a_pooled_map50_of_at_least_0_70() -> None:
    rep = _report()
    value, classes = _mean_ap50(rep, model="d-fine-n", precision="fp32", family="pooled", task="box")
    assert value >= SC["SC-009-02"], f"mAP50 {value:.4f} over {classes} is below 0.70"
    row = _row(rep, "SC-009-02")
    assert row["verdict"] == "pass"
    assert row["value"] == pytest.approx(value, abs=1e-9)
    assert (row["model"], row["precision"], row["statistic"], row["threshold"]) == ("d-fine-n", "fp32", "map50", 0.7)


@pytest.mark.req("SC-009-05")
def test_rf_detr_seg_n_fp32_reaches_a_pit_family_mask_ap50_of_at_least_0_70() -> None:
    rep = _report()
    value, classes = _mean_ap50(rep, model="rf-detr-seg-n", precision="fp32", family="pit", task="mask")
    assert value >= SC["SC-009-05"], f"mask AP50 {value:.4f} over {classes} is below 0.70"
    row = _row(rep, "SC-009-05")
    assert row["verdict"] == "pass"
    assert row["value"] == pytest.approx(value, abs=1e-9)
    assert (row["model"], row["precision"], row["statistic"], row["threshold"]) == (
        "rf-detr-seg-n",
        "fp32",
        "mask_ap50",
        0.7,
    )
    assert all(
        r["descriptive"] is False
        for r in rep["per_class"]
        if r["model"] == "rf-detr-seg-n" and r["task"] == "mask" and r["family"] == "pit"
    )  # the pit-family mask metrics are acceptance metrics; only the crusher family is descriptive (FR-009-23)


@pytest.mark.req("SC-009-06")
def test_rf_detr_seg_n_fp16_differs_from_fp32_by_at_most_one_percentage_point_of_mask_ap50() -> None:
    rep = _report()
    m32, _ = _mean_ap50(rep, model="rf-detr-seg-n", precision="fp32", family="pit", task="mask")
    m16, _ = _mean_ap50(rep, model="rf-detr-seg-n", precision="fp16", family="pit", task="mask")
    delta_pp = abs(100.0 * (m16 - m32))
    assert delta_pp <= SC06_PP, f"|delta mask AP50| = {delta_pp:.3f} pp exceeds 1 pp"
    row = _row(rep, "SC-009-06")
    assert row["verdict"] == "pass"
    assert row["value"] == pytest.approx(delta_pp, abs=1e-6)
    assert (row["model"], row["precision"], row["statistic"], row["threshold"]) == (
        "rf-detr-seg-n",
        "fp16",
        "abs_delta_mask_ap50_pp",
        1,
    )


@pytest.mark.req("SC-009-01")
@pytest.mark.req("SC-009-02")
@pytest.mark.req("SC-009-05")
@pytest.mark.req("SC-009-06")
def test_every_stored_verdict_follows_from_its_value_and_the_pre_registered_threshold() -> None:
    rep = _report()
    for crit in ("SC-009-01", "SC-009-02", "SC-009-05", "SC-009-06"):
        row = _row(rep, crit)
        assert row["verdict"] in {"pass", "fail"}, (
            f"{crit} is {row['verdict']!r}: the acceptance is not met unless it is evaluable and passes"
        )
        ok = row["value"] <= row["threshold"] if crit == "SC-009-06" else row["value"] >= row["threshold"]
        assert (row["verdict"] == "pass") is ok

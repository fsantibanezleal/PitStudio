# ruff: noqa: E501
"""T-009-044 (acceptance half): SC-009-03 and FR-009-30 on the published evaluation report (data-and-models phase).

Requirements: SC-009-03, FR-009-30.

Spec: specs/009-perception/spec.md section 5 (SC-009-03: D-FINE-S and D-FINE-N, fp32 and every live variant (D-FINE-N fp16, D-FINE-S int8): delta_rel(c, s) <= 10 %
of the clean score for c in {dust, night, rain}, s in {1, 2}), FR-009-30 (every model and precision variant re-scored under dust, night and rain at severities 1-5,
delta_rel = 100 (m_clean - m_c,s) / m_clean with m = mAP50, or mask AP50 for RF-DETR-Seg-N, descriptive), and the run layout of tests/pipeline/test_t_009_034_acceptance.py
(`web/public/assets/runs/<run_id>/manifest.json` with a succeeded `s50_evaluate` stage, and `detection-eval.json` beside it).

Oracle: the published report read with `json`; delta_rel is re-derived here from the stored m_clean and m_corrupted (no code under test); the thresholds are typed out from the spec.
Red until the data-and-models phase publishes the first evaluation run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "web" / "public" / "assets" / "runs"
LIVE = {("d-fine-n", "fp32"), ("d-fine-n", "fp16"), ("d-fine-s", "fp32"), ("d-fine-s", "int8")}
CORR = ("dust", "night", "rain")


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


def _derived(row: dict) -> float:
    return 100.0 * (row["m_clean"] - row["m_corrupted"]) / row["m_clean"]


@pytest.mark.req("FR-009-30")
def test_every_stored_relative_drop_equals_the_one_re_derived_from_its_scores() -> None:
    rows = _report()["corruption"]
    assert rows, "the report has no corruption rows"
    for r in rows:
        assert r["delta_rel_pct"] == pytest.approx(_derived(r), abs=1e-9), r


@pytest.mark.req("FR-009-30")
def test_the_report_covers_every_model_precision_corruption_and_severity_of_the_grid() -> None:
    rep = _report()
    have = {(r["model"], r["precision"], r["training_arm"], r["corruption"], r["severity"]) for r in rep["corruption"]}
    models = {r["model"] for r in rep["corruption"]}
    assert {"d-fine-n", "d-fine-s"} <= models
    for model in sorted(models):
        precisions = {r["precision"] for r in rep["corruption"] if r["model"] == model}
        assert "fp32" in precisions
        for precision in precisions:
            for c in CORR:
                for s in range(1, 6):
                    assert (model, precision, "S", c, s) in have, f"missing {model} {precision} {c} severity {s}"


@pytest.mark.req("FR-009-30")
def test_rf_detr_seg_n_corruption_rows_use_the_mask_metric_and_are_descriptive() -> None:
    rows = [r for r in _report()["corruption"] if r["model"] == "rf-detr-seg-n"]
    assert rows, "no RF-DETR-Seg-N corruption rows"
    assert all(r["metric"] == "mask_ap50" and r["descriptive"] is True for r in rows)
    assert all(
        r["metric"] == "map50" and r["descriptive"] is False
        for r in _report()["corruption"]
        if r["model"] != "rf-detr-seg-n"
    )


@pytest.mark.req("SC-009-03")
def test_d_fine_s_and_d_fine_n_lose_at_most_ten_percent_of_their_clean_score_at_severities_one_and_two() -> None:
    rep = _report()
    pts = {
        (r["model"], r["precision"], r["corruption"], r["severity"]): r
        for r in rep["corruption"]
        if r["training_arm"] == "S"
    }
    for model, precision in sorted(LIVE):
        for c in CORR:
            for s in (1, 2):
                row = pts.get((model, precision, c, s))
                assert row is not None, f"no corruption point for {model} {precision} {c} {s}"
                assert _derived(row) <= 10.0, (
                    f"{model} {precision} {c} s={s}: delta_rel {_derived(row):.2f} % exceeds 10 %"
                )


@pytest.mark.req("SC-009-03")
def test_the_acceptance_rows_of_sc_009_03_are_present_pass_and_agree_with_the_scores() -> None:
    rep = _report()
    rows = [r for r in rep["acceptance"] if r["criterion"] == "SC-009-03"]
    assert len(rows) == 24, (
        f"expected 4 model-precision pairs x 3 corruptions x 2 severities = 24 rows, found {len(rows)}"
    )
    assert {(r["model"], r["precision"]) for r in rows} == LIVE
    pts = {
        (r["model"], r["precision"], r["corruption"], r["severity"]): r
        for r in rep["corruption"]
        if r["training_arm"] == "S"
    }
    for r in rows:
        assert r["verdict"] == "pass", (
            f"{r['model']} {r['precision']} {r['corruption']} {r['severity']}: {r['verdict']}"
        )
        assert r["threshold"] == 10
        assert r["value"] <= 10.0
        assert r["value"] == pytest.approx(
            _derived(pts[(r["model"], r["precision"], r["corruption"], r["severity"])]), abs=1e-9
        )

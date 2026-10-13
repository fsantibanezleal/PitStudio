# ruff: noqa: E501
"""T-009-098 - FR-009-52: partial evaluations list the models and compute no pooled claim over incomplete sets.

Oracles (independent of the code under test; plan 009 test strategy row FR-009-52): hand-built scenarios on the fraction fixture of `_p009_s50_kit`:
- 2 of 3 named models evaluated (D-FINE-S fp32 and D-FINE-N fp32 present, RF-DETR-Seg-N fp32 absent) -> the report is labelled `partial`, lists the two evaluated models with their provenance and the third as
  `not run (absent)`, carries NO pooled-family row, NO pooled summary row, NO DR ablation and NO pass / fail verdict (every acceptance row is "not run" with a reason naming the partial evaluation), while the per-family
  rows (pit, crusher) of the two evaluated models are still reported;
- D-FINE-S arm S present but arm U absent -> the DR ablation is not computed (no `dr_ablation`), the missing arm is listed `not run (absent)`;
- a complete set (both named models present) is not partial, lists every model as evaluated, has the pooled rows and a verdict other than "not run" for SC-009-01 / SC-009-02.
Reported contract gap: detection-eval.schema.json has no `partial` or `models` property and closes the top level, so these fields need a schema change (spec 009 owner) before a partial report can validate.

Expected public API (module `pitstudio_pipeline.perception.s50_evaluate`, see tests/unit/test_t_009_033_support_determinism.py): `run_s50_evaluate(spec)` takes in addition
    spec["expected"]: list of (model, precision, arm) the evaluation names (default: [("d-fine-s", "fp32", "S"), ("d-fine-n", "fp32", "S"), ("rf-detr-seg-n", "fp32", "S")]);
    each prediction set may carry "provenance": {"checkpoint_sha256": str, "training_set_sha256": str, ...} (a mapping copied into the report; default {}).
  The report (and S50Result.partial) then has: report["partial"] (True iff at least one expected triple has no prediction set; False otherwise), report["models"] = one entry per expected triple, in the
  order of spec["expected"], then one per extra evaluated triple: {"model", "precision", "arm", "status": "evaluated" | "not run (absent)", "provenance": dict (only for evaluated)}. When partial: no per_class or
  summary row of family "pooled", no report["dr_ablation"] key, and every acceptance row is {"criterion", ..., "verdict": "not run", "reason": <text containing "partial">} without "value". Per-family rows of the
  evaluated models stay. S50Result.partial mirrors report["partial"].
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_s50_kit as k50  # noqa: E402
from pitstudio_pipeline.perception import s50_evaluate  # noqa: E402

THREE = [("d-fine-s", "fp32", "S"), ("d-fine-n", "fp32", "S"), ("rf-detr-seg-n", "fp32", "S")]
TWO = THREE[:2]
PROV_S = {"checkpoint_sha256": "a" * 64, "training_set_sha256": "b" * 64}
PROV_N = {"checkpoint_sha256": "c" * 64, "training_set_sha256": "b" * 64}


def _run(expected, present, **extra):
    gt, family, cluster = k50.fraction_gt(100, 100)
    dets = k50.perfect_detections(gt, set(range(1, 181)))
    provs = {"d-fine-s": PROV_S, "d-fine-n": PROV_N}
    preds = [
        k50.prediction(m, p, a, list(dets), gt, provenance=provs.get(m, {"checkpoint_sha256": "d" * 64}))
        for (m, p, a) in present
    ]
    return s50_evaluate.run_s50_evaluate(k50.spec(gt, family, cluster, preds, expected=expected, **extra))


def _status(rep: dict, model: str, arm: str = "S") -> dict:
    (e,) = [m for m in rep["models"] if m["model"] == model and m["arm"] == arm]
    return e


@pytest.mark.req("FR-009-52")
def test_two_of_three_models_give_a_partial_report_listing_the_third_as_not_run_absent() -> None:
    res = _run(THREE, TWO)
    rep = res.report
    assert res.partial is True
    assert rep["partial"] is True
    assert [(m["model"], m["precision"], m["arm"], m["status"]) for m in rep["models"]] == [
        ("d-fine-s", "fp32", "S", "evaluated"),
        ("d-fine-n", "fp32", "S", "evaluated"),
        ("rf-detr-seg-n", "fp32", "S", "not run (absent)"),
    ]
    assert _status(rep, "d-fine-s")["provenance"] == PROV_S
    assert _status(rep, "d-fine-n")["provenance"] == PROV_N
    assert "provenance" not in _status(rep, "rf-detr-seg-n")


@pytest.mark.req("FR-009-52")
def test_a_partial_report_has_no_pooled_metric_no_ablation_and_no_verdict() -> None:
    rep = _run(THREE, TWO).report
    assert not [r for r in rep["per_class"] if r["family"] == "pooled"]
    assert not [s for s in rep["summary"] if s["family"] == "pooled"]
    assert "dr_ablation" not in rep
    assert rep["acceptance"]
    for row in rep["acceptance"]:
        assert row["verdict"] == "not run"
        assert "partial" in row["reason"]
        assert "value" not in row
        assert "insufficient_support" not in row


@pytest.mark.req("FR-009-52")
def test_a_partial_report_still_reports_each_evaluated_model_per_family() -> None:
    rep = _run(THREE, TWO).report
    for model in ("d-fine-s", "d-fine-n"):
        for family in ("pit", "crusher"):
            rows = k50.find_rows(rep, model=model, family=family, task="box")
            assert len(rows) == 5
            assert all(r["support"] == 100 for r in rows)
            assert all(r["ap50"] == pytest.approx(1.0, abs=1e-9) for r in rows)
        assert any(s["model"] == model and s["family"] == "pit" for s in rep["summary"])
    assert not k50.find_rows(rep, model="rf-detr-seg-n")


@pytest.mark.req("FR-009-52")
def test_a_missing_ablation_arm_blocks_the_ablation_and_is_listed() -> None:
    expected = [("d-fine-s", "fp32", "S"), ("d-fine-s", "fp32", "U")]
    res = _run(expected, [("d-fine-s", "fp32", "S")])
    rep = res.report
    assert res.partial is True
    assert "dr_ablation" not in rep
    assert _status(rep, "d-fine-s", "S")["status"] == "evaluated"
    assert _status(rep, "d-fine-s", "U")["status"] == "not run (absent)"


@pytest.mark.req("FR-009-52")
def test_a_complete_set_is_not_partial_and_computes_the_pooled_rows_and_the_verdicts() -> None:
    res = _run(TWO, TWO)
    rep = res.report
    assert res.partial is False
    assert not rep.get("partial", False)
    assert {m["status"] for m in rep["models"]} == {"evaluated"}
    assert [m["model"] for m in rep["models"]] == ["d-fine-s", "d-fine-n"]
    assert len(k50.find_rows(rep, model="d-fine-s", family="pooled", task="box")) == 5
    assert k50.acceptance_row(rep, "SC-009-01")["verdict"] == "pass"
    assert k50.acceptance_row(rep, "SC-009-02")["verdict"] == "pass"


@pytest.mark.req("FR-009-52")
def test_every_expected_model_absent_gives_a_partial_report_with_nothing_evaluated() -> None:
    res = _run(THREE, [])
    rep = res.report
    assert res.partial is True
    assert {m["status"] for m in rep["models"]} == {"not run (absent)"}
    assert rep["per_class"] == []
    assert rep["summary"] == []
    assert all(r["verdict"] == "not run" for r in rep["acceptance"])


@pytest.mark.req("FR-009-52")
def test_a_prediction_set_with_zero_detections_is_evaluated_not_absent() -> None:
    gt, family, cluster = k50.fraction_gt(100, 100)
    preds = [k50.prediction("d-fine-s", "fp32", "S", [], gt, provenance=PROV_S)]
    rep = s50_evaluate.run_s50_evaluate(
        k50.spec(gt, family, cluster, preds, expected=[("d-fine-s", "fp32", "S")])
    ).report
    assert _status(rep, "d-fine-s")["status"] == "evaluated"
    assert not rep.get("partial", False)
    assert k50.find_rows(rep, model="d-fine-s", family="pooled", task="box", **{"class": "person"})[0]["ap50"] == 0.0


@pytest.mark.req("FR-009-52")
@pytest.mark.parametrize(
    "expected",
    [
        [("d-fine-s", "fp32")],
        [("yolo", "fp32", "S")],
        [("d-fine-s", "fp64", "S")],
        [("d-fine-s", "fp32", "Q")],
        "d-fine-s",
        [None],
        [("d-fine-s", "fp32", "S"), ("d-fine-s", "fp32", "S")],
    ],
)
def test_a_malformed_expected_list_is_refused(expected: object) -> None:
    with pytest.raises(ValueError, match="expected"):
        _run(expected, [])

# ruff: noqa: E501
"""T-009-033 - FR-009-24, FR-009-43, NFR-009-04: insufficient-support verdicts, hostile prediction files, deterministic reports.

Oracles (independent of the code under test):
- FR-009-24, hand calculation (plan 009 test strategy row): 99 instances of a class -> the affected criterion is "not evaluable
  (insufficient support)" naming the class and its count; 100 instances -> evaluable. Verdict rules typed out from spec 009 section 5:
  SC-009-01 mAP50 >= 0.80 (D-FINE-S fp32), SC-009-02 mAP50 >= 0.70 (D-FINE-N fp32), SC-009-05 mask AP50 >= 0.70 (RF-DETR-Seg-N fp32, pit
  family), SC-009-06 |delta mask AP50| <= 1 pp (RF-DETR-Seg-N fp16 against fp32), SC-009-03 delta_rel <= 10 %; a value equal to its
  threshold passes (">=" / "<=");
- the fraction fixture of `_p009_s50_kit` (closed-form AP, see its docstring): D-FINE-S detecting the first 175 of 200 images has
  AP50 (pooled) = 88 / 101 per class (recall 0.875: the grid points 0.00 .. 0.87), pit 1.0, crusher 76 / 101 (75 of 100: points 0.00 .. 0.75);
- FR-009-43, hand calculation (plan 009): a NaN score, an unknown image id, category 7, 301 detections for one image, and arms on different
  images are each rejected with their reason and no metric;
- NFR-009-04, definition written out here: a report is serialised as UTF-8 JSON with sorted keys, separators (",", ":"), no ASCII
  escaping and one trailing newline; two runs on the same input must give byte-identical output.

Expected public API (package `pitstudio_pipeline.perception`, under `pipeline/src/`):

module `evaluate` (additions to tests/unit/test_t_009_032_ap_eval.py)
    PredictionError(ValueError)      .code ("schema", "non-finite", "unknown-image", "unknown-category", "too-many-detections",
                                     "arms-mismatch"), .reason: str (names the offending id / count / field), .index: int | None (position
                                     of the offending detection)
    validate_predictions(gt: Mapping, detections: Sequence[Mapping]) -> None
        Checks, per detection in order: it is a mapping with int image_id, int category_id (bool excluded), a 4-number bbox and a numeric
        score ("schema"); score and bbox finite ("non-finite"); image_id is an image of `gt` ("unknown-image"); category_id in 1..5
        ("unknown-category"); then, for the whole list, at most 300 detections per image ("too-many-detections", reason contains the image id
        and the count). An empty list is valid. evaluate_boxes, evaluate_masks and bootstrap_intervals call it first and raise before any
        metric is computed.
    validate_arm_coverage(image_ids_a: Collection[int], image_ids_b: Collection[int]) -> None
        PredictionError("arms-mismatch") when the two sets of test image ids differ; the reason lists the ids in only one of them.

module `acceptance`
    acceptance_row(criterion: str, *, value: float | None, support: Sequence[tuple[str, str, int]], model: str | None = None,
                   precision: str | None = None, corruption: str | None = None, severity: int | None = None, min_support: int = 100) -> dict
        One row of the `acceptance` array of DC-009-05 (it validates against #/$defs/acceptance of detection-eval.schema.json).
        Criteria and what the schema pins: SC-009-01 (d-fine-s, fp32, map50, threshold 0.8), SC-009-02 (d-fine-n, fp32, map50, 0.7), SC-009-05
        (rf-detr-seg-n, fp32, mask_ap50, 0.7), SC-009-06 (rf-detr-seg-n, fp16, abs_delta_mask_ap50_pp, 1), SC-009-03 (model d-fine-n or d-fine-s given,
        precision given, delta_rel_pct, 10, corruption and severity 1 or 2 given). `model` / `precision` default to the pinned ones.
        `support` lists (family, class name, instance count) of every class the criterion's statistic is computed over. A count in
        1..min_support-1 is a shortfall: the verdict is "not evaluable (insufficient support)", "insufficient_support" lists every shortfall as
        {"family", "class", "count"} in input order, and there is no "value". Counts of 0 (class absent) and >= min_support are fine.
        Otherwise value >= threshold passes the map50 / mask_ap50 criteria and value <= threshold passes the delta criteria ("pass" / "fail",
        with "value"). ValueError (message names the argument) for an unknown criterion, a model / precision that differs from the pinned one,
        value None or non-finite when there is no shortfall, SC-009-03 without corruption / severity.

module `report`
    dumps_report(report: Mapping) -> bytes        the canonical serialisation defined above (ValueError for NaN / inf anywhere)

module `s50_evaluate`
    S50Result                         frozen dataclass: report: dict (DC-009-05 document), partial: bool, fixture: bool
    run_s50_evaluate(spec: Mapping) -> S50Result
        spec (see tests/unit/_p009_s50_kit.py `spec`): {"run_id", "gt" (pooled held-out COCO document, DC-009-02), "image_family": {image id: "pit" |
        "crusher"}, "image_cluster": {image id: scenario seed}, "predictions": [{"model", "precision", "arm", "image_ids", "detections", ...}],
        "bootstrap": {"seed", "resamples" (default 2000)}, "min_support" (default 100)}. For every prediction set it validates the detections
        (PredictionError propagates, no report), then fills report["per_class"] (box rows for the families pit, crusher, pooled and every class 1..5;
        zero support has no AP fields), report["summary"] (mAP50 over classes with >= 100 instances) and report["acceptance"] (SC-009-01/02/05/06 via
        acceptance_row). Rows follow DC-009-05 field names ("model", "precision", "training_arm" = the set's arm, "family", "task", "class" =
        category name, "support", "ap50", "ap50_95", "ap50_interval", "ap50_95_interval", "descriptive", ...). Deterministic.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_ap_kit as apkit  # noqa: E402
import _p009_s50_kit as k50  # noqa: E402
from pitstudio_pipeline.perception import acceptance, evaluate, report, s50_evaluate  # noqa: E402

TOL = 1e-9
NAMES = {1: "haul_truck", 2: "shovel", 3: "light_vehicle", 4: "person", 5: "boulder"}


def _acceptance_validator():
    from jsonschema import Draft202012Validator

    for p in (
        ROOT / "contracts" / "detection-eval.schema.json",
        ROOT / "specs" / "009-perception" / "contracts" / "detection-eval.schema.json",
    ):
        if p.is_file():
            s = json.loads(p.read_text(encoding="utf-8"))
            return Draft202012Validator({"$ref": "#/$defs/acceptance", "$defs": s["$defs"]})
    raise AssertionError("detection-eval.schema.json not found")


# ---------------------------------------------------------------- FR-009-24: acceptance rows


@pytest.mark.req("FR-009-24")
def test_99_instances_of_a_class_make_the_criterion_not_evaluable_naming_class_and_count() -> None:
    row = acceptance.acceptance_row(
        "SC-009-01",
        value=0.91,
        support=[("pooled", "haul_truck", 5000), ("pooled", "boulder", 99), ("pooled", "person", 400)],
    )
    assert row["verdict"] == "not evaluable (insufficient support)"
    assert row["insufficient_support"] == [{"family": "pooled", "class": "boulder", "count": 99}]
    assert "value" not in row
    assert (row["criterion"], row["model"], row["precision"], row["statistic"], row["threshold"]) == (
        "SC-009-01",
        "d-fine-s",
        "fp32",
        "map50",
        0.8,
    )
    assert list(_acceptance_validator().iter_errors(row)) == []


@pytest.mark.req("FR-009-24")
def test_100_instances_are_enough_and_zero_means_the_class_is_absent_not_short() -> None:
    row = acceptance.acceptance_row(
        "SC-009-01", value=0.91, support=[("pooled", "boulder", 100), ("pooled", "shovel", 0)]
    )
    assert row["verdict"] == "pass"
    assert row["value"] == pytest.approx(0.91)
    assert "insufficient_support" not in row


@pytest.mark.req("FR-009-24")
def test_every_shortfall_is_listed_in_input_order() -> None:
    row = acceptance.acceptance_row(
        "SC-009-05",
        value=0.9,
        support=[("pit", "person", 50), ("pit", "boulder", 99), ("pit", "haul_truck", 1000), ("crusher", "shovel", 1)],
    )
    assert row["verdict"] == "not evaluable (insufficient support)"
    assert row["insufficient_support"] == [
        {"family": "pit", "class": "person", "count": 50},
        {"family": "pit", "class": "boulder", "count": 99},
        {"family": "crusher", "class": "shovel", "count": 1},
    ]
    assert list(_acceptance_validator().iter_errors(row)) == []


@pytest.mark.req("FR-009-24")
@pytest.mark.parametrize(
    ("criterion", "value", "verdict", "extra"),
    [
        ("SC-009-01", 0.80, "pass", {}),  # equal to the threshold passes
        ("SC-009-01", 0.7999, "fail", {}),
        ("SC-009-02", 0.70, "pass", {}),
        ("SC-009-02", 0.6999, "fail", {}),
        ("SC-009-05", 0.7001, "pass", {}),
        ("SC-009-05", 0.69, "fail", {}),
        ("SC-009-06", 1.0, "pass", {}),
        ("SC-009-06", 1.01, "fail", {}),
        ("SC-009-03", 10.0, "pass", {"model": "d-fine-s", "precision": "fp32", "corruption": "dust", "severity": 2}),
        ("SC-009-03", 10.01, "fail", {"model": "d-fine-n", "precision": "int8", "corruption": "rain", "severity": 1}),
        ("SC-009-03", -3.0, "pass", {"model": "d-fine-s", "precision": "fp16", "corruption": "night", "severity": 1}),
    ],
)
def test_the_verdict_follows_the_pre_registered_threshold(
    criterion: str, value: float, verdict: str, extra: dict
) -> None:
    row = acceptance.acceptance_row(criterion, value=value, support=[("pooled", "person", 500)], **extra)
    assert row["verdict"] == verdict
    assert row["value"] == pytest.approx(value)
    assert list(_acceptance_validator().iter_errors(row)) == []


@pytest.mark.req("FR-009-24")
@pytest.mark.parametrize(
    ("criterion", "kwargs", "arg"),
    [
        ("SC-009-99", {}, "criterion"),
        ("SC-009-01", {"model": "d-fine-n"}, "model"),
        ("SC-009-01", {"precision": "fp16"}, "precision"),
        ("SC-009-05", {"model": "d-fine-s"}, "model"),
        ("SC-009-01", {"value": None}, "value"),
        ("SC-009-01", {"value": float("nan")}, "value"),
        ("SC-009-01", {"value": float("inf")}, "value"),
        ("SC-009-03", {"model": "d-fine-s", "precision": "fp32"}, "corruption"),
        ("SC-009-03", {"model": "d-fine-s", "precision": "fp32", "corruption": "dust"}, "severity"),
        ("SC-009-03", {"model": "d-fine-s", "precision": "fp32", "corruption": "dust", "severity": 3}, "severity"),
        ("SC-009-03", {"model": "rf-detr-seg-n", "precision": "fp32", "corruption": "dust", "severity": 1}, "model"),
    ],
)
def test_hostile_acceptance_arguments_are_rejected_naming_the_argument(criterion: str, kwargs: dict, arg: str) -> None:
    args = {"value": 0.9, "support": [("pooled", "person", 500)]} | kwargs
    with pytest.raises(ValueError, match=arg):
        acceptance.acceptance_row(criterion, **args)


@pytest.mark.req("FR-009-24")
def test_a_shortfall_makes_a_missing_value_acceptable() -> None:
    row = acceptance.acceptance_row("SC-009-02", value=None, support=[("pooled", "boulder", 99)])
    assert row["verdict"] == "not evaluable (insufficient support)"


# ---------------------------------------------------------------- FR-009-24 through s50_evaluate (fraction fixture)


def _run(detected_pit_crusher: int, **gt_kwargs):
    gt, family, cluster = k50.fraction_gt(**gt_kwargs)
    detected = set(range(1, detected_pit_crusher + 1))
    preds = [
        k50.prediction("d-fine-s", "fp32", "S", k50.perfect_detections(gt, detected), gt),
        k50.prediction("d-fine-n", "fp32", "S", k50.perfect_detections(gt, detected), gt),
    ]
    return s50_evaluate.run_s50_evaluate(k50.spec(gt, family, cluster, preds)), gt


@pytest.mark.req("FR-009-24")
def test_the_report_rows_match_the_closed_form_of_the_fraction_fixture() -> None:
    res, _ = _run(175)
    rep = res.report
    pooled = k50.find_rows(
        rep, model="d-fine-s", precision="fp32", training_arm="S", family="pooled", task="box", **{"class": "person"}
    )
    (row,) = pooled
    assert row["support"] == 200
    assert row["ap50"] == pytest.approx(88 / 101, abs=TOL)
    assert row["ap50_95"] == pytest.approx(88 / 101, abs=TOL)
    (pit,) = k50.find_rows(rep, model="d-fine-s", family="pit", task="box", **{"class": "boulder"})
    assert (pit["support"], pit["descriptive"]) == (100, False)
    assert pit["ap50"] == pytest.approx(1.0, abs=TOL)
    (cru,) = k50.find_rows(rep, model="d-fine-s", family="crusher", task="box", **{"class": "boulder"})
    assert cru["ap50"] == pytest.approx(76 / 101, abs=TOL)
    s = k50.summary_row(rep, model="d-fine-s", precision="fp32", family="pooled", task="box", metric="map50")
    assert s["value"] == pytest.approx(88 / 101, abs=TOL)
    assert s["classes_included"] == [NAMES[i] for i in (1, 2, 3, 4, 5)]
    assert 0.0 <= s["interval"]["lower"] <= s["interval"]["upper"] <= 1.0


@pytest.mark.req("FR-009-24")
def test_with_enough_support_the_acceptance_rows_pass_or_fail_on_the_pooled_map() -> None:
    res, _ = _run(175)  # pooled mAP50 = 88/101 = 0.8713 -> SC-009-01 (>= 0.8) passes
    row = k50.acceptance_row(res.report, "SC-009-01")
    assert row["verdict"] == "pass"
    assert row["value"] == pytest.approx(88 / 101, abs=TOL)
    # 150 of 200 detected: recall 0.75, grid points 0.00 .. 0.75 = 76 / 101 = 0.7525 -> SC-009-01 fails, SC-009-02 (>= 0.7) passes
    res2, _ = _run(150)
    assert k50.acceptance_row(res2.report, "SC-009-01")["verdict"] == "fail"
    assert k50.acceptance_row(res2.report, "SC-009-02")["verdict"] == "pass"


@pytest.mark.req("FR-009-24")
def test_a_class_with_99_test_instances_makes_sc_009_01_and_sc_009_02_not_evaluable() -> None:
    res, _ = _run(200, class_limit={5: 99})  # boulder appears in 99 images only
    for crit in ("SC-009-01", "SC-009-02"):
        row = k50.acceptance_row(res.report, crit)
        assert row["verdict"] == "not evaluable (insufficient support)"
        assert {"family": "pooled", "class": "boulder", "count": 99} in row["insufficient_support"]
        assert "value" not in row
    (boulder,) = k50.find_rows(res.report, model="d-fine-s", family="pooled", task="box", **{"class": "boulder"})
    assert boulder["support"] == 99  # the per-class row is still reported
    assert boulder["ap50"] == pytest.approx(1.0, abs=TOL)


@pytest.mark.req("FR-009-24")
def test_a_class_with_exactly_100_test_instances_is_evaluable() -> None:
    res, _ = _run(200, class_limit={5: 100})
    assert k50.acceptance_row(res.report, "SC-009-01")["verdict"] == "pass"


# ---------------------------------------------------------------- FR-009-43: hostile predictions


def _gt():
    return k50.fraction_gt(10, 10)[0]


def _det(image_id: int = 1, category: int = 1, bbox=(4, 20, 10, 10), score: float = 0.9) -> dict:
    return apkit.detection(image_id, category, bbox, score)


def _bad(detections: list, code: str, **expect) -> evaluate.PredictionError:
    with pytest.raises(evaluate.PredictionError) as exc:
        evaluate.validate_predictions(_gt(), detections)
    assert exc.value.code == code
    assert isinstance(exc.value, ValueError)
    assert exc.value.reason
    for text in expect.get("contains", []):
        assert text in exc.value.reason
    return exc.value


@pytest.mark.req("FR-009-43")
def test_clean_and_empty_prediction_lists_are_valid() -> None:
    assert evaluate.validate_predictions(_gt(), [_det(), _det(2, 5)]) is None
    assert evaluate.validate_predictions(_gt(), []) is None


@pytest.mark.req("FR-009-43")
@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_score_is_rejected(score: float) -> None:
    err = _bad([_det(), _det(2, 1, score=score)], "non-finite")
    assert err.index == 1


@pytest.mark.req("FR-009-43")
@pytest.mark.parametrize("slot", [0, 1, 2, 3])
@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_a_non_finite_box_is_rejected(slot: int, bad: float) -> None:
    box = [4.0, 20.0, 10.0, 10.0]
    box[slot] = bad
    assert _bad([_det(bbox=box)], "non-finite").index == 0


@pytest.mark.req("FR-009-43")
@pytest.mark.parametrize("image_id", [999, 0, -1, 21])
def test_an_image_id_absent_from_the_test_set_is_rejected_naming_it(image_id: int) -> None:
    _bad([_det(image_id=image_id)], "unknown-image", contains=[str(image_id)])


@pytest.mark.req("FR-009-43")
@pytest.mark.parametrize("category", [0, 6, 7, -1, 100])
def test_an_unknown_category_id_is_rejected_naming_it(category: int) -> None:
    _bad([_det(category=category)], "unknown-category", contains=[str(category)])


@pytest.mark.req("FR-009-43")
def test_more_than_300_detections_for_one_image_are_rejected_and_300_are_fine() -> None:
    ok = [_det(1, 1 + i % 5, (i % 50, 30 + i // 50, 5, 5), 0.5 + i / 10_000) for i in range(300)]
    assert evaluate.validate_predictions(_gt(), ok) is None
    err = _bad([*ok, _det(1, 2, (1, 1, 5, 5), 0.999)], "too-many-detections", contains=["301"])
    assert "1" in err.reason  # the image id
    spread = [_det(1 + i % 10, 1, (i % 50, 30, 5, 5), 0.5 + i / 10_000) for i in range(900)]  # 90 per image: fine
    assert evaluate.validate_predictions(_gt(), spread) is None


@pytest.mark.req("FR-009-43")
@pytest.mark.parametrize(
    "bad",
    [
        None,
        "detection",
        7,
        [],
        {},
        {"image_id": 1, "category_id": 1, "bbox": [4, 20, 10], "score": 0.9},
        {"image_id": 1, "category_id": 1, "bbox": [4, 20, 10, 10]},
        {"image_id": 1, "category_id": 1, "bbox": [4, 20, 10, 10], "score": "0.9"},
        {"image_id": "1", "category_id": 1, "bbox": [4, 20, 10, 10], "score": 0.9},
        {"image_id": 1, "category_id": True, "bbox": [4, 20, 10, 10], "score": 0.9},
        {"image_id": 1, "category_id": 1.5, "bbox": [4, 20, 10, 10], "score": 0.9},
        {"image_id": 1, "category_id": 1, "bbox": "4 20 10 10", "score": 0.9},
    ],
)
def test_a_malformed_detection_is_a_schema_rejection(bad: object) -> None:
    assert _bad([bad], "schema").index == 0  # type: ignore[list-item]


@pytest.mark.req("FR-009-43")
def test_the_first_bad_detection_names_the_error() -> None:
    err = _bad([_det(), _det(999), _det(category=9), _det(score=float("nan"))], "unknown-image")
    assert err.index == 1


@pytest.mark.req("FR-009-43")
def test_arms_that_do_not_cover_the_same_test_images_are_rejected_listing_the_difference() -> None:
    assert evaluate.validate_arm_coverage({1, 2, 3}, [3, 2, 1]) is None
    with pytest.raises(evaluate.PredictionError) as exc:
        evaluate.validate_arm_coverage({1, 2, 3, 4}, {1, 2, 5})
    assert exc.value.code == "arms-mismatch"
    for image_id in ("3", "4", "5"):
        assert image_id in exc.value.reason
    with pytest.raises(evaluate.PredictionError):
        evaluate.validate_arm_coverage(set(), {1})


@pytest.mark.req("FR-009-43")
def test_the_evaluators_reject_hostile_input_before_computing_any_metric() -> None:
    gt = _gt()
    bad = [_det(), _det(2, 1, score=float("nan"))]
    with pytest.raises(evaluate.PredictionError):
        evaluate.evaluate_boxes(gt, bad, min_support=1)
    with pytest.raises(evaluate.PredictionError):
        evaluate.evaluate_masks(
            gt,
            [{**_det(score=float("nan")), "segmentation": np.zeros((64, 64), dtype=np.uint8)}],
            family="pit",
            min_support=1,
        )
    cluster = {i: 1000 + i for i in range(1, 21)}
    with pytest.raises(evaluate.PredictionError):
        evaluate.bootstrap_intervals(gt, bad, cluster, seed=1, resamples=5, min_support=1)


@pytest.mark.req("FR-009-43")
@pytest.mark.parametrize(
    "make_bad",
    [lambda d: {**d, "score": float("nan")}, lambda d: {**d, "image_id": 4242}, lambda d: {**d, "category_id": 7}],
)
def test_s50_evaluate_rejects_a_bad_prediction_set_and_returns_no_report(make_bad) -> None:
    gt, family, cluster = k50.fraction_gt(10, 10)
    dets = k50.perfect_detections(gt, set(range(1, 21)))
    dets[3] = make_bad(dets[3])
    with pytest.raises(evaluate.PredictionError):
        s50_evaluate.run_s50_evaluate(
            k50.spec(gt, family, cluster, [k50.prediction("d-fine-s", "fp32", "S", dets, gt)])
        )


# ---------------------------------------------------------------- NFR-009-04: determinism


@pytest.mark.req("NFR-009-04")
def test_the_canonical_serialisation_is_sorted_compact_utf8_with_one_newline() -> None:
    doc = {"b": [1, 2.5, None, True], "a": {"z": "— label", "y": 0.1}}
    expected = (json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    assert report.dumps_report(doc) == expected
    assert report.dumps_report(doc).endswith(b"}\n")
    assert "—".encode() in report.dumps_report(doc)  # not escaped
    assert report.dumps_report({"k": 1, "j": 2}) == report.dumps_report({"j": 2, "k": 1})


@pytest.mark.req("NFR-009-04")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_number_cannot_be_serialised(bad: float) -> None:
    with pytest.raises(ValueError, match=r"nan|inf|finite|NaN|Infinity"):
        report.dumps_report({"a": [1, {"b": bad}]})


@pytest.mark.req("NFR-009-04")
def test_two_s50_evaluate_runs_on_the_same_predictions_give_byte_identical_reports() -> None:
    gt, family, cluster = k50.fraction_gt(20, 20, images_per_seed=5)
    dets = k50.perfect_detections(gt, set(range(1, 33)))
    s1 = k50.spec(
        gt, family, cluster, [k50.prediction("d-fine-s", "fp32", "S", copy.deepcopy(dets), gt)], min_support=10
    )
    s2 = copy.deepcopy(s1)
    a = report.dumps_report(s50_evaluate.run_s50_evaluate(s1).report)
    b = report.dumps_report(s50_evaluate.run_s50_evaluate(s2).report)
    assert a == b
    assert json.loads(a.decode("utf-8"))["run_id"] == "20261012T100000Z-s50"
    other = k50.spec(
        gt,
        family,
        cluster,
        [k50.prediction("d-fine-s", "fp32", "S", copy.deepcopy(dets), gt)],
        min_support=10,
        bootstrap={"seed": 1, "resamples": 6},
    )
    c = report.dumps_report(s50_evaluate.run_s50_evaluate(other).report)
    assert (
        json.loads(c.decode("utf-8"))["bootstrap"]["seed"] == 1
    )  # the seed is recorded: a different seed is a different report

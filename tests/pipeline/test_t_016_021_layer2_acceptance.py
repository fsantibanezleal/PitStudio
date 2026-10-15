"""T-016-021: layer-2 acceptance on the parity reports (pipeline, acceptance).

Requirements: SC-016-03.

Spec: specs/016-export-acceleration/spec.md SC-016-03 ("every published reduced-precision variant passes layer 2:
|delta task metric| <= 1 percentage point; mask IoU >= 0.99", measured by the parity reports); FR-016-09 (a variant that
fails is `rejected` and does not ship); plan.md test strategy row SC-016-03.

Oracles:
- the pre-registered thresholds of `specs/000-foundation/thresholds.yaml` (`models.quantized_task_metric_delta_max_pp`
  = 1.0, `models.mask_iou_min_vs_fp32` = 0.99), read with PyYAML;
- the spec's own valid layer-2 report `contracts/examples/export-parity-report.valid-layer2.json` (model d-fine-s, int8,
  metric map50 fp32 71.4, variant 70.8, delta -0.6, verdict pass) and one-field variations written here by hand;
- the delta is recomputed as `metric.variant - metric.fp32` (never taken from the stored `delta_pp` or `verdict`).

Expected public API (module `pitstudio_pipeline.export.acceptance`, `pipeline/` environment):
    @dataclass Layer2Acceptance        # ok: bool, problems: list[str]   (ok iff problems is empty)
    layer2_acceptance(published: Sequence[tuple[str, str]], reports: Sequence[Mapping]) -> Layer2Acceptance
        `published` lists (model, precision) pairs of the shipped reduced-precision variants (precision in fp16, int8,
        fp8). For each pair there must be a layer-2 report of that model and precision, and every such report must
        satisfy, from its numbers: `tolerances.metric_delta_pp_max == 1` and `tolerances.mask_iou_min` is null or 0.99,
        `abs(metric.variant - metric.fp32) <= 1`, `mask_iou` null or >= 0.99 (and, when `tolerances.mask_iou_min` is
        not null, `mask_iou` present), and `verdict == "pass"`. Problems are strings naming model and precision and
        containing one of "missing", "tolerance", "delta", "mask", "verdict". A `rejected` report for a variant that is
        NOT listed as published is not a problem (it correctly does not ship). Reports of layers 1 and 4 are ignored.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pitstudio_pipeline.export.acceptance import layer2_acceptance

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "specs" / "016-export-acceleration" / "contracts" / "examples"
MODELS = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))["models"]
PUBLISHED = [("d-fine-s", "int8")]


def _valid() -> dict:
    return json.loads((EXAMPLES / "export-parity-report.valid-layer2.json").read_text(encoding="utf-8"))


def _problems(published: list[tuple[str, str]], reports: list[dict]) -> list[str]:
    result = layer2_acceptance(published, reports)
    assert result.ok == (not result.problems)
    return result.problems


@pytest.mark.req("SC-016-03")
def test_the_pre_registered_thresholds_are_the_spec_values() -> None:
    assert MODELS["quantized_task_metric_delta_max_pp"] == 1.0
    assert MODELS["mask_iou_min_vs_fp32"] == 0.99


@pytest.mark.req("SC-016-03")
def test_a_passing_layer2_report_for_the_published_variant_is_accepted() -> None:
    assert _problems(PUBLISHED, [_valid()]) == []


@pytest.mark.req("SC-016-03")
def test_a_published_variant_without_a_layer2_report_is_missing() -> None:
    problems = _problems([("d-fine-s", "int8"), ("d-fine-s", "fp16")], [_valid()])
    assert len(problems) == 1
    assert "fp16" in problems[0]
    assert "missing" in problems[0]


@pytest.mark.req("SC-016-03")
def test_a_report_of_another_precision_does_not_satisfy_the_variant() -> None:
    other = _valid()
    other["precision"] = "fp16"
    problems = _problems(PUBLISHED, [other])
    assert len(problems) == 1
    assert "missing" in problems[0]


@pytest.mark.req("SC-016-03")
@pytest.mark.parametrize(
    ("variant", "ok"),
    [(70.5, True), (72.5, True), (70.49, False), (72.51, False), (71.5, True), (80.0, False)],
)
def test_the_metric_change_is_recomputed_and_bounded_by_one_percentage_point(variant: float, ok: bool) -> None:
    report = _valid()
    report["metric"]["fp32"] = 71.5  # dyadic, so the one-point boundary is exact in binary64
    report["metric"]["variant"] = variant  # delta_pp and verdict still say -0.6 / pass: they must not be trusted
    problems = _problems(PUBLISHED, [report])
    assert (problems == []) is ok
    if not ok:
        assert any("delta" in p for p in problems)


@pytest.mark.req("SC-016-03")
@pytest.mark.parametrize(("iou", "ok"), [(0.99, True), (1.0, True), (0.989, False), (0.5, False)])
def test_mask_iou_at_least_099_is_required_for_mask_outputs(iou: float, ok: bool) -> None:
    report = _valid()
    report["mask_iou"] = iou
    assert (_problems(PUBLISHED, [report]) == []) is ok


@pytest.mark.req("SC-016-03")
def test_a_mask_report_without_a_measured_iou_is_a_problem() -> None:
    report = _valid()
    report["tolerances"]["mask_iou_min"] = 0.99
    report["mask_iou"] = None
    assert any("mask" in p for p in _problems(PUBLISHED, [report]))


@pytest.mark.req("SC-016-03")
@pytest.mark.parametrize(("key", "loose"), [("metric_delta_pp_max", 2), ("mask_iou_min", 0.9)])
def test_a_loosened_tolerance_is_a_problem(key: str, loose: float) -> None:
    report = _valid()
    report["tolerances"][key] = loose
    assert any("tolerance" in p for p in _problems(PUBLISHED, [report]))


@pytest.mark.req("SC-016-03")
def test_a_stored_rejected_verdict_is_a_problem_for_a_published_variant() -> None:
    report = _valid()
    report["verdict"] = "rejected"
    report["reason"] = "fixture"
    assert any("verdict" in p for p in _problems(PUBLISHED, [report]))


@pytest.mark.req("SC-016-03")
def test_a_rejected_variant_that_is_not_published_is_not_a_problem() -> None:
    rejected = _valid()
    rejected["precision"] = "fp8"
    rejected["metric"]["variant"] = 60.0
    rejected["verdict"] = "rejected"
    rejected["reason"] = "delta 11.4 pp"
    assert _problems(PUBLISHED, [_valid(), rejected]) == []


@pytest.mark.req("SC-016-03")
def test_layer1_and_layer4_reports_are_ignored() -> None:
    layer4 = json.loads((EXAMPLES / "export-parity-report.valid-layer4.json").read_text(encoding="utf-8"))
    layer1 = json.loads((EXAMPLES / "export-parity-report.valid.json").read_text(encoding="utf-8"))
    assert _problems(PUBLISHED, [_valid(), layer4, layer1]) == []
    assert len(_problems(PUBLISHED, [layer4, layer1])) == 1  # still missing

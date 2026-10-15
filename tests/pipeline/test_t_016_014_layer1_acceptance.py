"""T-016-014: layer-1 acceptance on the parity reports (pipeline, acceptance).

Requirements: SC-016-02.

Spec: specs/016-export-acceleration/spec.md SC-016-02 ("every published ONNX model passes layer 1: rtol 1e-3, atol
1e-5, max abs 1e-4, argmax 100 % on rows with a top-2 gap > 2e-4", measured by the parity reports); plan.md test
strategy row SC-016-02 (pre-registered tolerances read from the parity reports).

Oracles:
- the pre-registered tolerances come from `specs/000-foundation/thresholds.yaml` `models.onnx_cpu_fp32`
  (rtol 1e-3, atol 1e-5, max_abs 1e-4), read here with PyYAML;
- the report documents are the spec's own valid example `contracts/examples/export-parity-report.valid.json` (a layer-1
  pass: max error 3.1e-05, mismatch 0, argmax agreement 1) and variants of it written in this test by changing one
  field at a time (hand-built: the field value that must make the acceptance fail is chosen from the spec's thresholds);
- the acceptance recomputes the verdict from the numbers and never trusts a stored `verdict` (a report that says
  `pass` with a maximum error of 1.2e-4 is a lie the check must catch).

Expected public API (module `pitstudio_pipeline.export.acceptance`, `pipeline/` environment):
    @dataclass Layer1Acceptance        # ok: bool, problems: list[str]   (ok iff problems is empty)
    layer1_acceptance(published_models: Sequence[str], reports: Sequence[Mapping]) -> Layer1Acceptance
        For every published model there must be at least one layer-1 report (`layer == 1`) of that model, and every
        layer-1 report of a published model must satisfy, from its numbers: `tolerances` equal to the pre-registered
        triple, `max_abs_error` <= max_abs, `mismatch_fraction == 0`, `argmax` null or `argmax.agreement == 1`, and
        `verdict == "pass"`. Each problem is a string naming the model and the failed criterion (containing one of
        "missing", "tolerance", "max_abs", "mismatch", "argmax", "verdict"). Reports of layers 2 and 4 and of
        unpublished models are ignored.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from pitstudio_pipeline.export.acceptance import layer1_acceptance

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "specs" / "016-export-acceleration" / "contracts" / "examples"
THRESHOLDS = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))
TOL = THRESHOLDS["models"]["onnx_cpu_fp32"]


def _valid() -> dict:
    return json.loads((EXAMPLES / "export-parity-report.valid.json").read_text(encoding="utf-8"))


def _problems(models: list[str], reports: list[dict]) -> list[str]:
    result = layer1_acceptance(models, reports)
    assert result.ok == (not result.problems)
    return result.problems


@pytest.mark.req("SC-016-02")
def test_the_pre_registered_tolerances_are_the_spec_values() -> None:
    assert TOL == {"rtol": 1.0e-3, "atol": 1.0e-5, "max_abs": 1.0e-4}


@pytest.mark.req("SC-016-02")
def test_a_layer1_pass_report_for_the_published_model_is_accepted() -> None:
    assert _problems(["d-fine-n"], [_valid()]) == []


@pytest.mark.req("SC-016-02")
def test_a_published_model_without_a_layer1_report_is_a_problem_naming_the_model() -> None:
    problems = _problems(["d-fine-n", "unet-frag"], [_valid()])
    assert len(problems) == 1
    assert "unet-frag" in problems[0]
    assert "missing" in problems[0]


@pytest.mark.req("SC-016-02")
def test_no_reports_at_all_fails_every_published_model() -> None:
    assert len(_problems(["a", "b"], [])) == 2


@pytest.mark.req("SC-016-02")
def test_unpublished_models_and_other_layers_are_ignored() -> None:
    other = _valid()
    other["model"] = "scratch-model"
    other["max_abs_error"] = 0.5  # would fail, but the model is not published
    layer2 = json.loads((EXAMPLES / "export-parity-report.valid-layer2.json").read_text(encoding="utf-8"))
    layer2["model"] = "d-fine-n"
    assert _problems(["d-fine-n"], [_valid(), other, layer2]) == []


@pytest.mark.req("SC-016-02")
def test_a_layer2_report_alone_does_not_satisfy_layer1() -> None:
    layer2 = json.loads((EXAMPLES / "export-parity-report.valid-layer2.json").read_text(encoding="utf-8"))
    problems = _problems([layer2["model"]], [layer2])
    assert len(problems) == 1
    assert "missing" in problems[0]


@pytest.mark.req("SC-016-02")
@pytest.mark.parametrize(
    ("field", "value", "word"),
    [
        ("max_abs_error", 1.2e-4, "max_abs"),
        ("max_abs_error", 1.0000001e-4, "max_abs"),
        ("mismatch_fraction", 1e-6, "mismatch"),
        ("verdict", "rejected", "verdict"),
    ],
)
def test_each_criterion_is_checked_from_the_numbers_even_when_the_stored_verdict_says_pass(
    field: str, value: object, word: str
) -> None:
    report = _valid()
    report[field] = value
    problems = _problems(["d-fine-n"], [report])
    assert problems
    assert any(word in p for p in problems)
    assert all("d-fine-n" in p for p in problems)


@pytest.mark.req("SC-016-02")
def test_the_maximum_error_exactly_at_max_abs_is_accepted() -> None:
    report = _valid()
    report["max_abs_error"] = TOL["max_abs"]
    assert _problems(["d-fine-n"], [report]) == []


@pytest.mark.req("SC-016-02")
@pytest.mark.parametrize("agreement", [0.0, 0.99999, 0.5])
def test_argmax_agreement_below_one_fails(agreement: float) -> None:
    report = _valid()
    report["argmax"]["agreement"] = agreement
    problems = _problems(["d-fine-n"], [report])
    assert any("argmax" in p for p in problems)


@pytest.mark.req("SC-016-02")
def test_a_report_without_class_scores_has_no_argmax_criterion() -> None:
    report = _valid()
    report["argmax"] = None
    assert _problems(["d-fine-n"], [report]) == []


@pytest.mark.req("SC-016-02")
@pytest.mark.parametrize(("key", "loose"), [("rtol", 1e-2), ("atol", 1e-4), ("max_abs", 1e-3)])
def test_a_loosened_tolerance_triple_is_a_problem(key: str, loose: float) -> None:
    report = _valid()
    report["tolerances"][key] = loose
    problems = _problems(["d-fine-n"], [report])
    assert any("tolerance" in p for p in problems)


@pytest.mark.req("SC-016-02")
def test_every_layer1_report_of_a_published_model_must_pass_not_only_one() -> None:
    good, bad = _valid(), copy.deepcopy(_valid())
    bad["variant"] = "deployed"
    bad["max_abs_error"] = 3e-4
    assert _problems(["d-fine-n"], [good, bad])  # the deployed variant fails even though the parity variant passed

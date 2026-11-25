# ruff: noqa: E501
"""T-009-060 - FR-009-32, SC-009-07: "not measured" and "calibrated synthetic" labels in reports and B2 data.

Oracles (independent of the code under test):
- the two exact texts of spec 009 FR-009-32, typed out: `sim_to_real: "not measured"` and the label "calibrated synthetic — not validated against real data" (U+2014 em dash,
  identical to FR-008-36 and to the const of `honesty_label` in contracts/detection-eval.schema.json, which is read here as a control);
- hand-built documents: a clean report passes; each tampered variant (missing label, hyphen for the em dash, `sim_to_real: "measured"` with no probe, a real-domain metric key with
  no probe, a class entry without its label) is a violation at a known JSON pointer;
- structural rule from the spec: EVERY object that names a class (a `class` key) carries the label and `sim_to_real: "not measured"`, in the report and in every B2 baked data file;
  no key anywhere is a real-domain metric field (any key whose snake_case words include `real` or `probe`, other than `sim_to_real` itself and the labelled-probe block name `real_probe`,
  which is absent until the probe is labelled).

Expected public API (package `pitstudio_pipeline.perception`, under `pipeline/src/`):

module `honesty`
    HONESTY_LABEL: str                      the label above (with the em dash)
    NOT_MEASURED: str                       "not measured"
    HonestyError(ValueError)                .pointer: str (RFC 6901 pointer of the first violation, "" for the root), .reason: str
    check_sim_to_real_labels(document: Mapping) -> None
        Raises HonestyError for the first violation, walking the document in key order: (a) a top-level `sim_to_real` missing or not "not measured" while the document has no
        `real_probe` object, or a top-level `honesty_label` missing or different from HONESTY_LABEL; (b) any object with a `class` key whose `honesty_label` is missing / different or whose
        `sim_to_real` is missing / not "not measured" (pointer to that object) while the document has no `real_probe`; (c) any key whose snake_case words include `real` or `probe`
        (other than `sim_to_real` itself) anywhere, while the document has no top-level `real_probe` object. A document WITH a `real_probe` object is the labelled-probe
        case and is judged by the rules of T-009-061 (not checked here: this task only has unlabelled documents).
        A non-mapping document raises HonestyError with pointer "".

module `b2`
    build_b2_data(report: Mapping) -> dict[str, dict]
        The B2 baked data files of the perception case as {relative file name: JSON document}: at least one file with the per-class metrics ("class" entries) and one with the corruption
        curves; each document carries top-level `sim_to_real` and `honesty_label` copied from the report and every class entry carries both labels; it contains image counts, metrics
        and verdicts but no real-domain field and (FR-009-41) no throughput, timing or telemetry key. Pure; does not modify the report.

module `s50_evaluate` (see tests/unit/test_t_009_033_support_determinism.py): the report of a run without a labelled probe has the top-level labels and every per_class row labelled.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
import _p009_s50_kit as k50  # noqa: E402
from pitstudio_pipeline.perception import b2, honesty, s50_evaluate  # noqa: E402

LABEL = "calibrated synthetic — not validated against real data"


def _report() -> dict:
    gt, family, cluster = k50.fraction_gt(100, 100)
    dets = k50.perfect_detections(gt, set(range(1, 181)))
    preds = [k50.prediction("d-fine-s", "fp32", "S", dets, gt), k50.prediction("d-fine-n", "fp32", "S", dets, gt)]
    return s50_evaluate.run_s50_evaluate(k50.spec(gt, family, cluster, preds)).report


def _walk(node, path=""):
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from _walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}/{i}")


def _violation(doc: dict) -> honesty.HonestyError:
    with pytest.raises(honesty.HonestyError) as exc:
        honesty.check_sim_to_real_labels(doc)
    assert isinstance(exc.value, ValueError)
    assert exc.value.reason
    return exc.value


# ---------------------------------------------------------------- the texts


@pytest.mark.req("FR-009-32")
def test_the_label_texts_are_the_exact_spec_strings_and_match_the_schema_const() -> None:
    assert honesty.HONESTY_LABEL == LABEL
    assert honesty.NOT_MEASURED == "not measured"
    schema = json.loads((ROOT / "contracts" / "detection-eval.schema.json").read_text(encoding="utf-8"))
    assert schema["$defs"]["honesty_label"]["const"] == LABEL
    assert kit.HONESTY_LABEL == LABEL


# ---------------------------------------------------------------- the evaluation report


@pytest.mark.req("FR-009-32")
def test_a_report_without_a_probe_carries_the_labels_everywhere_and_passes_the_check() -> None:
    rep = _report()
    assert rep["sim_to_real"] == "not measured"
    assert rep["honesty_label"] == LABEL
    assert rep["per_class"]
    for row in rep["per_class"]:
        assert row["honesty_label"] == LABEL
        assert row["sim_to_real"] == "not measured"
    assert "real_probe" not in rep
    assert honesty.check_sim_to_real_labels(rep) is None


@pytest.mark.req("FR-009-32")
def test_the_report_has_a_label_for_every_class_of_every_model_family_and_task() -> None:
    rep = _report()
    classes = {r["class"] for r in rep["per_class"]}
    assert classes == {"haul_truck", "shovel", "light_vehicle", "person", "boulder"}
    for _, node in _walk(rep):
        if "class" in node:
            assert node.get("honesty_label") == LABEL
            assert node.get("sim_to_real") == "not measured"


@pytest.mark.req("FR-009-32")
def test_the_report_holds_no_real_domain_metric_field() -> None:
    rep = _report()
    for _, node in _walk(rep):
        for key in node:
            words = key.lower().split("_")
            assert key == "sim_to_real" or ("real" not in words and "probe" not in words), key


# ---------------------------------------------------------------- the checker on tampered documents


def _clean() -> dict:
    return {
        "sim_to_real": "not measured",
        "honesty_label": LABEL,
        "per_class": [{"class": "person", "honesty_label": LABEL, "sim_to_real": "not measured", "support": 500}],
    }


@pytest.mark.req("FR-009-32")
def test_a_clean_document_passes() -> None:
    assert honesty.check_sim_to_real_labels(_clean()) is None


@pytest.mark.req("FR-009-32")
@pytest.mark.parametrize(
    ("mutate", "pointer"),
    [
        (lambda d: d.pop("sim_to_real"), ""),
        (lambda d: d.update(sim_to_real="measured"), ""),
        (lambda d: d.update(sim_to_real="Not measured"), ""),
        (lambda d: d.update(sim_to_real=None), ""),
        (lambda d: d.pop("honesty_label"), ""),
        (lambda d: d.update(honesty_label="calibrated synthetic - not validated against real data"), ""),
        (lambda d: d.update(honesty_label="calibrated synthetic"), ""),
        (lambda d: d.update(honesty_label=LABEL + "."), ""),
        (lambda d: d["per_class"][0].pop("honesty_label"), "/per_class/0"),
        (lambda d: d["per_class"][0].update(honesty_label="validated against real data"), "/per_class/0"),
        (lambda d: d["per_class"][0].pop("sim_to_real"), "/per_class/0"),
        (lambda d: d["per_class"][0].update(sim_to_real="measured"), "/per_class/0"),
    ],
    ids=[
        "no-s2r",
        "measured",
        "case",
        "null",
        "no-label",
        "hyphen",
        "short",
        "extra-dot",
        "class-no-label",
        "class-wrong-label",
        "class-no-s2r",
        "class-measured",
    ],
)
def test_each_tampered_label_is_a_violation_at_its_pointer(mutate, pointer: str) -> None:
    doc = _clean()
    mutate(doc)
    assert _violation(doc).pointer == pointer


@pytest.mark.req("FR-009-32")
@pytest.mark.parametrize(
    "key", ["real_map50", "real_domain_ap", "map50_real", "probe_results", "real", "probe", "domain_probe_f1"]
)
def test_a_real_domain_key_without_a_labelled_probe_is_a_violation(key: str) -> None:
    doc = _clean()
    doc["per_class"][0][key] = 0.5
    err = _violation(doc)
    assert err.pointer == f"/per_class/0/{key}"
    top = _clean()
    top[key] = {"map50": 0.4}
    assert _violation(top).pointer == f"/{key}"


@pytest.mark.req("FR-009-32")
def test_the_key_sim_to_real_itself_is_not_a_real_domain_field() -> None:
    doc = _clean()
    doc["per_class"][0]["note"] = "synthetic"
    assert honesty.check_sim_to_real_labels(doc) is None


@pytest.mark.req("FR-009-32")
@pytest.mark.parametrize("doc", [None, [], "report", 7])
def test_a_document_that_is_not_a_mapping_is_a_violation_at_the_root(doc: object) -> None:
    assert _violation(doc).pointer == ""  # type: ignore[arg-type]


@pytest.mark.req("FR-009-32")
def test_the_checker_does_not_modify_the_document() -> None:
    doc = _clean()
    before = copy.deepcopy(doc)
    honesty.check_sim_to_real_labels(doc)
    assert doc == before


# ---------------------------------------------------------------- the B2 baked data


@pytest.mark.req("FR-009-32")
@pytest.mark.req("SC-009-07")
def test_every_b2_baked_file_built_without_a_probe_carries_the_labels_and_no_real_domain_field() -> None:
    rep = _report()
    before = copy.deepcopy(rep)
    files = b2.build_b2_data(rep)
    assert rep == before
    assert files
    for name, doc in files.items():
        assert isinstance(name, str)
        assert name
        assert not name.startswith("/")
        assert ".." not in name.split("/")
        assert doc["sim_to_real"] == "not measured", name
        assert doc["honesty_label"] == LABEL, name
        assert honesty.check_sim_to_real_labels(doc) is None, name
        for _, node in _walk(doc):
            if "class" in node:
                assert node.get("honesty_label") == LABEL, name
                assert node.get("sim_to_real") == "not measured", name
            for key in node:
                words = key.lower().split("_")
                assert key == "sim_to_real" or ("real" not in words and "probe" not in words), (name, key)
    text = json.dumps(files)
    assert "class" in text  # at least one file lists classes
    assert "corruption" in text  # and one holds the corruption curves


@pytest.mark.req("FR-009-32")
def test_the_b2_data_is_json_serialisable_and_holds_no_non_finite_number() -> None:
    files = b2.build_b2_data(_report())
    for doc in files.values():
        json.dumps(doc, allow_nan=False)

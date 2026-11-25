# ruff: noqa: E501
"""T-009-044 (unit half) - FR-009-30, P-009-10, SC-009-03: relative drop under corruption, curve rows and the robustness criterion.

Oracles (independent of the code under test):
- hand calculation of plan 009 (test strategy row FR-009-30): m_clean = 0.80 and m_corrupted = 0.75 give delta_rel = 100 (0.80 - 0.75) / 0.80 = 6.25 %;
  further hand values: 0.76 -> 0.646 is 15.0 %, equal scores 0.0 %, an improvement 0.60 -> 0.66 is -10.0 %, a collapse to 0 is 100 %;
- P-009-10 (analytical): the ratio form is unit-free, delta_rel(k m_clean, k m_s) = delta_rel(m_clean, m_s) for k > 0 (rtol 1e-12), and equals 0 when m_s = m_clean;
- the grid of FR-009-30: every model (d-fine-n, d-fine-s, rf-detr-seg-n) x precision (fp32, fp16, int8) x corruption (dust, night, rain) x severity 1..5 = 135 rows,
  each valid against `#/$defs/corruption_point` of detection-eval.schema.json (reference validator `jsonschema`); RF-DETR-Seg-N rows use the metric
  mask_ap50 and are descriptive (schema rule), D-FINE rows use map50;
- SC-009-03 (spec 009 section 5): delta_rel <= 10 % for D-FINE-S and D-FINE-N, fp32 and the live variants (D-FINE-N fp16, D-FINE-S int8), c in {dust, night, rain},
  s in {1, 2}: 4 model-precision pairs x 3 x 2 = 24 rows; 10.0 passes, 10.01 fails.

Expected public API (module `pitstudio_pipeline.perception.robustness`, package under `pipeline/src/`):

    delta_rel(m_clean: float, m_corrupted: float) -> float
        100 * (m_clean - m_corrupted) / m_clean. ValueError (message names the argument) for m_clean not finite or <= 0, m_corrupted not finite or < 0, or non-numbers (bool excluded).
    corruption_rows(clean: Mapping[tuple[str, str, str], float], corrupted: Mapping[tuple[str, str, str, str, int], float]) -> list[dict]
        clean[(model, precision, arm)] = clean score (mAP50, or mask AP50 for rf-detr-seg-n); corrupted[(model, precision, arm, corruption, severity)] = score under that
        corruption. One row per corrupted entry, sorted by (model, precision, arm, corruption, severity): {"model", "precision", "training_arm" = arm, "metric" ("map50", or
        "mask_ap50" for rf-detr-seg-n), "corruption", "severity", "m_clean", "m_corrupted", "delta_rel_pct" (= delta_rel), "descriptive" (True for rf-detr-seg-n)}.
        ValueError (message contains "m_clean") when a corrupted entry has no clean score; ValueError (message names the field) for an unknown model, precision,
        arm ("S" / "U"), corruption or a severity outside 1..5.
    sc03_rows(points: Sequence[Mapping], *, support: Sequence[tuple[str, str, int]]) -> list[dict]
        The 24 SC-009-03 rows (order: model, precision, corruption, severity; pairs d-fine-n fp32, d-fine-n fp16, d-fine-s fp32, d-fine-s int8; arm S points only): each is
        acceptance_row("SC-009-03", value=delta_rel_pct, support=support, model=..., precision=..., corruption=..., severity=...) from tests/unit/test_t_009_033_support_determinism.py;
        a missing point gives {"criterion": "SC-009-03", model, precision, corruption, severity, "statistic": "delta_rel_pct", "threshold": 10, "verdict": "not run",
        "reason": <non-empty text>} with no value.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.perception import robustness as rob  # noqa: E402

EXAMPLES = 200
MODELS = ("d-fine-n", "d-fine-s", "rf-detr-seg-n")
PRECISIONS = ("fp32", "fp16", "int8")
CORRUPTIONS = ("dust", "night", "rain")
LIVE = [("d-fine-n", "fp32"), ("d-fine-n", "fp16"), ("d-fine-s", "fp32"), ("d-fine-s", "int8")]


def _validator(name: str):
    from jsonschema import Draft202012Validator

    for p in (
        ROOT / "contracts" / "detection-eval.schema.json",
        ROOT / "specs" / "009-perception" / "contracts" / "detection-eval.schema.json",
    ):
        if p.is_file():
            s = json.loads(p.read_text(encoding="utf-8"))
            return Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": s["$defs"]})
    raise AssertionError("detection-eval.schema.json not found")


# ---------------------------------------------------------------- delta_rel


@pytest.mark.req("FR-009-30")
@pytest.mark.parametrize(
    ("clean", "corrupted", "expected"),
    [
        (0.80, 0.75, 6.25),
        (0.76, 0.646, 15.0),
        (0.5, 0.5, 0.0),
        (0.60, 0.66, -10.0),
        (0.9, 0.0, 100.0),
        (1.0, 0.9, 10.0),
    ],
)
def test_delta_rel_hand_values(clean: float, corrupted: float, expected: float) -> None:
    assert rob.delta_rel(clean, corrupted) == pytest.approx(expected, abs=1e-9)


@pytest.mark.req("FR-009-30")
@pytest.mark.parametrize(
    ("clean", "corrupted", "arg"),
    [
        (0.0, 0.5, "m_clean"),
        (-0.1, 0.5, "m_clean"),
        (float("nan"), 0.5, "m_clean"),
        (float("inf"), 0.5, "m_clean"),
        (0.8, float("nan"), "m_corrupted"),
        (0.8, float("inf"), "m_corrupted"),
        (0.8, -0.01, "m_corrupted"),
        ("0.8", 0.5, "m_clean"),
        (None, 0.5, "m_clean"),
        (True, 0.5, "m_clean"),
        (0.8, "0.5", "m_corrupted"),
    ],
)
def test_hostile_scores_are_rejected_naming_the_argument(clean: object, corrupted: object, arg: str) -> None:
    with pytest.raises(ValueError, match=arg):
        rob.delta_rel(clean, corrupted)  # type: ignore[arg-type]


@pytest.mark.req("P-009-10")
@given(clean=st.floats(1e-3, 1.0), frac=st.floats(0.0, 1.0), k=st.floats(0.01, 100.0))
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_delta_rel_is_unit_free_and_zero_at_equal_scores(clean: float, frac: float, k: float) -> None:
    m_s = clean * frac
    base = rob.delta_rel(clean, m_s)
    assert rob.delta_rel(k * clean, k * m_s) == pytest.approx(base, rel=1e-12, abs=1e-12)
    assert rob.delta_rel(clean, clean) == 0.0
    assert rob.delta_rel(k * clean, k * clean) == 0.0
    assert base == pytest.approx(100.0 * (1.0 - frac), rel=1e-12, abs=1e-12)  # closed form: 100 (1 - m_s / m_clean)


# ---------------------------------------------------------------- the curve rows


def _grid(drop: float = 0.05) -> tuple[dict, dict]:
    clean = {(m, p, "S"): 0.80 for m in MODELS for p in PRECISIONS}
    corrupted = {
        (m, p, "S", c, s): 0.80 - drop * s * 0.1
        for m in MODELS
        for p in PRECISIONS
        for c in CORRUPTIONS
        for s in range(1, 6)
    }
    return clean, corrupted


@pytest.mark.req("FR-009-30")
def test_the_full_grid_gives_135_sorted_rows_that_validate_against_the_schema() -> None:
    clean, corrupted = _grid()
    rows = rob.corruption_rows(clean, corrupted)
    assert len(rows) == 3 * 3 * 3 * 5
    keys = [(r["model"], r["precision"], r["training_arm"], r["corruption"], r["severity"]) for r in rows]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)
    v = _validator("corruption_point")
    for r in rows:
        assert list(v.iter_errors(r)) == []
        assert r["m_clean"] == 0.80
        assert r["delta_rel_pct"] == pytest.approx(100.0 * (0.80 - r["m_corrupted"]) / 0.80, abs=1e-9)


@pytest.mark.req("FR-009-30")
def test_a_row_carries_the_hand_value_and_the_metric_and_descriptive_flags() -> None:
    clean = {("d-fine-s", "fp32", "S"): 0.80, ("rf-detr-seg-n", "fp16", "S"): 0.76}
    corrupted = {("d-fine-s", "fp32", "S", "dust", 1): 0.75, ("rf-detr-seg-n", "fp16", "S", "rain", 3): 0.646}
    a, b = rob.corruption_rows(clean, corrupted)
    assert (a["model"], a["metric"], a["descriptive"]) == ("d-fine-s", "map50", False)
    assert a["delta_rel_pct"] == pytest.approx(6.25, abs=1e-9)
    assert (a["m_clean"], a["m_corrupted"]) == (0.80, 0.75)
    assert (b["model"], b["metric"], b["descriptive"]) == ("rf-detr-seg-n", "mask_ap50", True)
    assert b["delta_rel_pct"] == pytest.approx(15.0, abs=1e-9)
    assert rob.corruption_rows(clean, {}) == []


@pytest.mark.req("FR-009-30")
@pytest.mark.parametrize(
    ("key", "arg"),
    [
        (("d-fine-x", "fp32", "S", "dust", 1), "model"),
        (("d-fine-s", "fp64", "S", "dust", 1), "precision"),
        (("d-fine-s", "fp32", "Q", "dust", 1), "arm"),
        (("d-fine-s", "fp32", "S", "fog", 1), "corruption"),
        (("d-fine-s", "fp32", "S", "dust", 0), "severity"),
        (("d-fine-s", "fp32", "S", "dust", 6), "severity"),
        (("d-fine-s", "fp16", "S", "dust", 1), "m_clean"),  # no clean score for this precision
    ],
)
def test_hostile_curve_inputs_are_rejected_naming_the_field(key: tuple, arg: str) -> None:
    with pytest.raises(ValueError, match=arg):
        rob.corruption_rows({("d-fine-s", "fp32", "S"): 0.8}, {key: 0.7})


# ---------------------------------------------------------------- SC-009-03


def _points(overrides: dict | None = None, omit: set | None = None) -> list[dict]:
    clean = {
        (m, p, "S"): 1.0 for m in MODELS for p in PRECISIONS
    }  # clean score 1.0: a 10 % drop is exactly 0.90 (no rounding at the boundary)
    corrupted = {
        (m, p, "S", c, s): 0.95 for m in MODELS for p in PRECISIONS for c in CORRUPTIONS for s in range(1, 6)
    }  # 5 % drop everywhere
    corrupted.update(overrides or {})
    for k in omit or set():
        corrupted.pop(k)
    return rob.corruption_rows(clean, corrupted)


SUPPORT = [("pooled", "person", 500)]


@pytest.mark.req("SC-009-03")
def test_all_24_rows_pass_when_every_drop_is_five_percent() -> None:
    rows = rob.sc03_rows(_points(), support=SUPPORT)
    assert len(rows) == 24
    assert {(r["model"], r["precision"]) for r in rows} == set(LIVE)
    assert {(r["corruption"], r["severity"]) for r in rows} == set(itertools.product(CORRUPTIONS, (1, 2)))
    assert all(r["verdict"] == "pass" and r["criterion"] == "SC-009-03" and r["threshold"] == 10 for r in rows)
    assert all(r["value"] == pytest.approx(5.0, abs=1e-9) for r in rows)
    keys = [(r["model"], r["precision"], r["corruption"], r["severity"]) for r in rows]
    assert keys == sorted(keys)
    v = _validator("acceptance")
    assert all(list(v.iter_errors(r)) == [] for r in rows)


@pytest.mark.req("SC-009-03")
def test_a_drop_of_ten_percent_passes_and_just_above_fails_only_that_row() -> None:
    at = ("d-fine-s", "int8", "S", "dust", 2)
    over = ("d-fine-n", "fp16", "S", "night", 1)
    rows = rob.sc03_rows(_points({at: 0.90, over: 0.8999}), support=SUPPORT)
    verdicts = {(r["model"], r["precision"], r["corruption"], r["severity"]): r["verdict"] for r in rows}
    assert verdicts[("d-fine-s", "int8", "dust", 2)] == "pass"  # exactly 10 %
    assert verdicts[("d-fine-n", "fp16", "night", 1)] == "fail"  # 10.01 %
    assert sum(v == "fail" for v in verdicts.values()) == 1


@pytest.mark.req("SC-009-03")
def test_severities_three_to_five_and_rf_detr_do_not_enter_the_criterion() -> None:
    bad = {
        ("d-fine-s", "fp32", "S", "dust", 4): 0.10,
        ("rf-detr-seg-n", "fp32", "S", "rain", 1): 0.10,
        ("d-fine-s", "fp16", "S", "dust", 1): 0.10,
    }
    rows = rob.sc03_rows(_points(bad), support=SUPPORT)
    assert all(
        r["verdict"] == "pass" for r in rows
    )  # s = 4, RF-DETR and d-fine-s fp16 (not a live variant) are outside SC-009-03


@pytest.mark.req("SC-009-03")
def test_a_missing_point_is_a_not_run_row_with_a_reason_and_no_value() -> None:
    gone = ("d-fine-n", "fp16", "S", "rain", 2)
    rows = rob.sc03_rows(_points(omit={gone}), support=SUPPORT)
    assert len(rows) == 24
    (row,) = [
        r
        for r in rows
        if (r["model"], r["precision"], r["corruption"], r["severity"]) == ("d-fine-n", "fp16", "rain", 2)
    ]
    assert row["verdict"] == "not run"
    assert row["reason"]
    assert "value" not in row
    assert list(_validator("acceptance").iter_errors(row)) == []
    assert sum(r["verdict"] == "not run" for r in rows) == 1


@pytest.mark.req("SC-009-03")
def test_insufficient_support_makes_every_row_not_evaluable() -> None:
    rows = rob.sc03_rows(_points(), support=[("pooled", "boulder", 99)])
    assert {r["verdict"] for r in rows} == {"not evaluable (insufficient support)"}
    assert all(r["insufficient_support"] == [{"family": "pooled", "class": "boulder", "count": 99}] for r in rows)

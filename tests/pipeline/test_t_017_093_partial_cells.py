"""T-017-093: partial survey cells: listed, no summary over incomplete groups (pipeline).

Requirements: FR-017-53.

Spec: specs/017-planning-survey/spec.md FR-017-53: while only some of the flights, survey methods or deposits that
a survey
or planning evaluation names exist, `s50_evaluate` reports the existing (method, flight, seed) cells, lists each
missing cell
as `not run (absent)`, labels the survey volumes `partial`, and computes the error summary only over complete
(method, design)
groups. plan.md test strategy row FR-017-53: 2 of 3 methods present for a design give `partial`, the third listed,
and no
summary for that design.

Oracles (hand calculation): a fixture of 3 methods x 2 designs x 3 seeds = 18 expected cells of which the test
supplies 14
(photogrammetric complete for both designs: 6 cells; splat complete for design f01 (3 cells) and 2 of 3 seeds for f02;
DEM differencing complete for f01 (3 cells) and absent for f02: see `_present`); the summary of a complete (method,
design) group is the
mean of the absolute errors of its seeds (by hand: errors 1, -2, 3 -> 2.0); the label is `partial` as soon as one
expected
cell is absent and `complete` otherwise.
Reading note (flagged ambiguity): the spec text computes summaries "over complete (method, design) groups", while
the plan row
says "no summary for that design" when 2 of 3 methods are present; these tests follow the spec text: a (method,
design) group is
summarised exactly when every seed of it is present, and a design's *method comparisons* need all methods (reported as
`comparable: False` otherwise).

Expected public API (module `pitstudio.survey.partial`, root environment, pure Python):
    evaluate_cells(expected: Sequence[tuple[str, str, int]], present: Mapping[tuple[str, str, int], float]) ->
    PartialReport
        `expected`: every (method, design, seed) the evaluation names (design = the flight / deposit id);
        `present`: the
        cells that exist, with their signed volume error in percent. PartialReport:
          rows: one dict per expected cell, in the order of `expected`: existing -> {"method", "design", "seed",
          "status":
            "ok", "error_pct"}; absent -> {"method", "design", "seed", "status": "not_run", "reason": "absent",
            "label":
            "not run (absent)"}
          coverage: "partial" when any expected cell is absent else "complete"
          summary: {(method, design): {"n": seeds, "mean_abs_error_pct": mean of |error|}} for the complete groups
          only
          incomplete_groups: sorted list of the (method, design) groups with an absent cell
          comparable: {design: bool} True iff every method has all its seeds for that design
        ValueError for a present cell that is not expected, a duplicate expected cell, a non-finite error, or an empty
        `expected` list.
"""

from __future__ import annotations

import math

import pytest
from pitstudio.survey.partial import evaluate_cells

METHODS = ("dem-differencing", "photogrammetric", "splat")
DESIGNS = ("f01", "f02")
EXPECTED = [(m, d, s) for m in METHODS for d in DESIGNS for s in range(3)]  # 18 cells


def _present() -> dict:
    present = {}
    for d in DESIGNS:  # photogrammetric: all six cells
        for s, err in enumerate((1.0, -2.0, 3.0)):
            present[("photogrammetric", d, s)] = err
    for s, err in enumerate((0.5, 0.5, -0.5)):  # splat: f01 complete, f02 only seeds 0 and 1
        present[("splat", "f01", s)] = err
    present[("splat", "f02", 0)] = 4.0
    present[("splat", "f02", 1)] = -4.0
    for s in range(3):  # DEM differencing: f01 complete, f02 absent
        present[("dem-differencing", "f01", s)] = 0.1
    return present


@pytest.mark.req("FR-017-53")
def test_existing_cells_are_reported_and_each_absent_cell_is_listed_as_not_run_absent() -> None:
    report = evaluate_cells(EXPECTED, _present())
    assert len(report.rows) == 18
    assert [(r["method"], r["design"], r["seed"]) for r in report.rows] == EXPECTED  # the order of `expected`
    absent = [r for r in report.rows if r["status"] == "not_run"]
    assert len(absent) == 18 - len(_present()) == 18 - 14
    assert {(r["method"], r["design"], r["seed"]) for r in absent} == {
        ("splat", "f02", 2),
        ("dem-differencing", "f02", 0),
        ("dem-differencing", "f02", 1),
        ("dem-differencing", "f02", 2),
    }
    assert all(r["reason"] == "absent" and r["label"] == "not run (absent)" for r in absent)
    ok = {(r["method"], r["design"], r["seed"]): r for r in report.rows if r["status"] == "ok"}
    assert ok[("photogrammetric", "f01", 1)]["error_pct"] == -2.0
    assert all("label" not in r and "reason" not in r for r in ok.values())


@pytest.mark.req("FR-017-53")
def test_the_survey_is_labelled_partial_while_any_cell_is_absent_and_complete_otherwise() -> None:
    assert evaluate_cells(EXPECTED, _present()).coverage == "partial"
    full = {cell: 1.0 for cell in EXPECTED}
    assert evaluate_cells(EXPECTED, full).coverage == "complete"
    assert [r["status"] for r in evaluate_cells(EXPECTED, full).rows] == ["ok"] * 18


@pytest.mark.req("FR-017-53")
def test_the_error_summary_covers_only_the_complete_method_design_groups() -> None:
    report = evaluate_cells(EXPECTED, _present())
    assert set(report.summary) == {
        ("photogrammetric", "f01"),
        ("photogrammetric", "f02"),
        ("splat", "f01"),
        ("dem-differencing", "f01"),
    }
    assert report.summary[("photogrammetric", "f01")] == {
        "n": 3,
        "mean_abs_error_pct": pytest.approx(2.0),
    }  # (1 + 2 + 3) / 3
    assert report.summary[("splat", "f01")]["mean_abs_error_pct"] == pytest.approx(0.5)
    assert report.summary[("dem-differencing", "f01")]["mean_abs_error_pct"] == pytest.approx(0.1)
    assert ("splat", "f02") not in report.summary  # 2 of 3 seeds: no summary, the missing seed is listed
    assert ("dem-differencing", "f02") not in report.summary
    assert report.incomplete_groups == [("dem-differencing", "f02"), ("splat", "f02")]


@pytest.mark.req("FR-017-53")
def test_a_design_is_comparable_between_methods_only_when_every_method_is_complete_for_it() -> None:
    report = evaluate_cells(EXPECTED, _present())
    assert report.comparable == {"f01": True, "f02": False}


@pytest.mark.req("FR-017-53")
def test_two_of_three_methods_present_for_a_design_lists_the_third_and_marks_the_design_not_comparable() -> None:
    expected = [(m, "f01", s) for m in METHODS for s in range(3)]
    present = {(m, "f01", s): 1.0 for m in METHODS[:2] for s in range(3)}
    report = evaluate_cells(expected, present)
    assert report.coverage == "partial"
    assert [r["method"] for r in report.rows if r["status"] == "not_run"] == ["splat"] * 3
    assert report.comparable == {"f01": False}
    assert set(report.summary) == {("dem-differencing", "f01"), ("photogrammetric", "f01")}


@pytest.mark.req("FR-017-53")
def test_planning_deposits_use_the_same_rule() -> None:
    deposits = ("porphyry", "vein", "layered", "core_halo")
    expected = [("e1-pit", d, 0) for d in deposits]
    report = evaluate_cells(expected, {("e1-pit", d, 0): 0.0 for d in deposits[:3]})
    assert report.coverage == "partial"
    assert [r["design"] for r in report.rows if r["status"] == "not_run"] == ["core_halo"]
    assert set(report.summary) == {("e1-pit", d) for d in deposits[:3]}


@pytest.mark.req("FR-017-53")
def test_nothing_present_gives_a_partial_report_with_every_cell_listed_and_no_summary() -> None:
    report = evaluate_cells(EXPECTED, {})
    assert report.coverage == "partial"
    assert all(r["status"] == "not_run" for r in report.rows)
    assert report.summary == {}
    assert report.comparable == {"f01": False, "f02": False}


@pytest.mark.req("FR-017-53")
def test_hostile_inputs_are_refused() -> None:
    with pytest.raises(ValueError, match=r"."):
        evaluate_cells([], {})
    with pytest.raises(ValueError, match=r"."):
        evaluate_cells(EXPECTED[:3] + EXPECTED[:1], {})  # a duplicate expected cell
    with pytest.raises(ValueError, match=r"."):
        evaluate_cells(EXPECTED[:3], {("splat", "f99", 0): 1.0})  # a present cell nobody expected
    with pytest.raises(ValueError, match=r"."):
        evaluate_cells(EXPECTED[:3], {EXPECTED[0]: math.nan})
    with pytest.raises(ValueError, match=r"."):
        evaluate_cells(EXPECTED[:3], {EXPECTED[0]: math.inf})

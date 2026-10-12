"""T-011-096 - FR-011-50: partial evaluation sets are reported with provenance, with no claim over the missing cases.

Oracles (independent of the code under test; plan 011 test strategy FR-011-50: "40 of 50 calibration trials give
    `partial` with 10 missing and no
coverage claim; 50 give the coverage"): hand arithmetic and the spec text.
- GNS: the evaluation names 20 held-out geometries (8 collapses, 6 piles, 6 dumps); when only 14 exist (all 6 dumps
    absent) the report has the
  cases it has, lists each absent geometry as "not run (absent)", lists the family with no present geometry
      ("dump-over-crest") as not run, is
  labelled "partial" and makes no SC-011-01 claim (the verdict is None), while each present geometry keeps its own
      pass or fail;
- FNO: 10 expected held-out terrains, 8 present: partial, 2 missing, no SC-011-03 verdict;
- calibration: 40 of 50 trials give `partial` with 10 missing, covering counted over the 40 present trials, no
    coverage fraction, no Wilson interval and
  no SC-011-02 verdict; 50 of 50 give coverage = covering / 50, its Wilson interval and the verdict (the same
      numbers as tests/pipeline/
  test_t_011_035_coverage_study.py);
- a complete set is labelled "complete" with an empty `missing` list.

Expected public API (package under `pipeline/src/`, `src/pitstudio/calibration/`):

  pitstudio_pipeline.surrogates.gns.evaluate.evaluate_held_out(geometries, surrogate, *, expected=None,
      dataset_manifest=None) -> dict
      expected: list of {"geometry_id", "family"} naming every held-out geometry of the evaluation; None = the
          geometries given are the set.
      Adds to the report of T-011-015: "status" ("complete" | "partial"), "missing" (list of {"geometry_id",
          "family", "status": "not run (absent)"}),
      "families_not_run" (families with no present geometry, sorted); for a partial report "sc_011_01" is None and
          "all_pass" is None; the per-geometry
      records of the present geometries are unchanged. A geometry given but not expected is refused (ValueError).
  pitstudio_pipeline.surrogates.fno.evaluate.evaluate_fno(preds, truths, field_names, *, model, patch_ids=None,
      expected_patches=None, ...) -> dict
      patch_ids: the patch id of each scenario (len S); expected_patches: the held-out patch ids the evaluation
          names. Adds "status", "missing_patches"
      (list of {"patch_id", "status": "not run (absent)"}); a partial report has "sc_011_03" None. Both None = complete.
  pitstudio.calibration.study.summarise_arm(trials, *, parameter=0, expected_trials=None) -> dict
      expected_trials: the number of trials the study names (50); None = len(trials). Adds "status" ("complete" |
          "partial"), "missing" (int); for a partial
      summary "coverage", "wilson" and "sc_011_02" are None, "covering" and "n_trials" still count the present trials.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))
sys.path.insert(0, str(ROOT / "tests"))

torch = pytest.importorskip("torch")

import _surrogate_fixtures as fx  # noqa: E402
from pitstudio_pipeline.surrogates.fno import evaluate as fno_evaluate  # noqa: E402
from pitstudio_pipeline.surrogates.gns import evaluate as gns_evaluate  # noqa: E402

from pitstudio.calibration import study  # noqa: E402

NOT_RUN = "not run (absent)"


def present(ids: list[str]) -> list[dict]:
    return [fx.collapse_geometry(i) for i in ids]


# ------------------------------------------------------------------ GNS


@pytest.mark.req("FR-011-50")
def test_a_complete_gns_set_is_labelled_complete_with_nothing_missing() -> None:
    exp = [{"geometry_id": f"col-{k:02d}", "family": "column-collapse"} for k in range(3)]
    geoms = present([e["geometry_id"] for e in exp])
    rep = gns_evaluate.evaluate_held_out(geoms, fx.identity_surrogate(geoms), expected=exp)
    assert rep["status"] == "complete"
    assert rep["missing"] == []
    assert rep["families_not_run"] == []
    assert rep["sc_011_01"] == "pass"
    assert rep["all_pass"] is True


@pytest.mark.req("FR-011-50")
def test_missing_geometries_make_the_report_partial_and_remove_the_claim() -> None:
    exp = [{"geometry_id": f"col-{k:02d}", "family": "column-collapse"} for k in range(4)] + [
        {"geometry_id": f"dum-{k:02d}", "family": "dump-over-crest"} for k in range(2)
    ]
    have = [e["geometry_id"] for e in exp if e["family"] == "column-collapse"]
    geoms = present(have)
    rep = gns_evaluate.evaluate_held_out(geoms, fx.identity_surrogate(geoms), expected=exp)
    assert rep["status"] == "partial"
    assert rep["missing"] == [
        {"geometry_id": "dum-00", "family": "dump-over-crest", "status": NOT_RUN},
        {"geometry_id": "dum-01", "family": "dump-over-crest", "status": NOT_RUN},
    ]
    assert rep["families_not_run"] == ["dump-over-crest"]
    assert rep["sc_011_01"] is None  # no claim over the missing cases
    assert rep["all_pass"] is None
    assert [g["geometry_id"] for g in rep["geometries"]] == have  # the cases it has are reported
    assert all(g["pass"] is True for g in rep["geometries"])
    assert rep["n_geometries"] == 4


@pytest.mark.req("FR-011-50")
def test_a_family_that_is_only_partly_present_is_not_listed_as_a_missing_family() -> None:
    exp = [{"geometry_id": f"col-{k:02d}", "family": "column-collapse"} for k in range(3)]
    geoms = present(["col-00", "col-02"])
    rep = gns_evaluate.evaluate_held_out(geoms, fx.identity_surrogate(geoms), expected=exp)
    assert rep["status"] == "partial"
    assert [m["geometry_id"] for m in rep["missing"]] == ["col-01"]
    assert rep["families_not_run"] == []  # the family has present geometries; only one case is absent


@pytest.mark.req("FR-011-50")
def test_fourteen_of_twenty_geometries_with_every_dump_absent() -> None:
    # the analytic clouds are collapses, so the 14 present geometries are declared collapses; the 6 absent ones are
    #   the dumps of the spec's 8 / 6 / 6 split
    exp = [{"geometry_id": f"col-{k:02d}", "family": "column-collapse"} for k in range(14)] + [
        {"geometry_id": f"dum-{k:02d}", "family": "dump-over-crest"} for k in range(6)
    ]
    assert len(exp) == 20
    geoms = present([e["geometry_id"] for e in exp[:14]])
    rep = gns_evaluate.evaluate_held_out(geoms, fx.identity_surrogate(geoms), expected=exp)
    assert rep["status"] == "partial"
    assert len(rep["missing"]) == 6
    assert {m["family"] for m in rep["missing"]} == {"dump-over-crest"}
    assert [m["geometry_id"] for m in rep["missing"]] == [f"dum-{k:02d}" for k in range(6)]
    assert rep["families_not_run"] == ["dump-over-crest"]
    assert rep["sc_011_01"] is None
    assert rep["n_geometries"] == 14


@pytest.mark.req("FR-011-50")
def test_an_absent_failing_geometry_cannot_be_hidden_a_present_failing_one_still_fails() -> None:
    exp = [{"geometry_id": f"col-{k:02d}", "family": "column-collapse"} for k in range(3)]
    geoms = present(["col-00", "col-01"])

    def one_bad(state, n_steps):
        ref = fx.identity_surrogate(geoms)(state, n_steps)
        if state["geometry_id"] == "col-01":
            ref.positions = ref.positions + 0.5  # far off: |dL| too large
        return ref

    rep = gns_evaluate.evaluate_held_out(geoms, one_bad, expected=exp)
    assert rep["status"] == "partial"
    assert [g["pass"] for g in rep["geometries"]] == [True, False]
    assert rep["sc_011_01"] is None


@pytest.mark.req("FR-011-50")
def test_a_geometry_that_is_not_expected_is_refused() -> None:
    exp = [{"geometry_id": "col-00", "family": "column-collapse"}]
    geoms = present(["col-00", "col-99"])
    with pytest.raises(ValueError, match="col-99"):
        gns_evaluate.evaluate_held_out(geoms, fx.identity_surrogate(geoms), expected=exp)


@pytest.mark.req("FR-011-50")
def test_nothing_present_is_an_error_not_an_empty_complete_report() -> None:
    exp = [{"geometry_id": "col-00", "family": "column-collapse"}]
    with pytest.raises(ValueError, match=r"."):
        gns_evaluate.evaluate_held_out([], fx.identity_surrogate([]), expected=exp)


# ------------------------------------------------------------------ FNO


@pytest.mark.req("FR-011-50")
def test_missing_terrains_make_the_fno_report_partial_without_a_verdict() -> None:
    pred, truth = fx.tailings_set(8)
    patches = [f"p{i:02d}" for i in range(8)]
    expected = [f"p{i:02d}" for i in range(10)]
    rep = fno_evaluate.evaluate_fno(
        pred, truth, fx.TAILINGS_FIELDS, model="tailings", patch_ids=patches, expected_patches=expected
    )
    assert rep["status"] == "partial"
    assert rep["missing_patches"] == [{"patch_id": "p08", "status": NOT_RUN}, {"patch_id": "p09", "status": NOT_RUN}]
    assert rep["sc_011_03"] is None
    assert rep["fields"]["depth_max"]["mean"] == pytest.approx(0.01, rel=1e-9)  # the cases it has are still scored
    assert rep["n_scenarios"] == 8


@pytest.mark.req("FR-011-50")
def test_a_complete_fno_set_keeps_its_verdict() -> None:
    pred, truth = fx.tailings_set(10)
    patches = [f"p{i:02d}" for i in range(10)]
    rep = fno_evaluate.evaluate_fno(
        pred, truth, fx.TAILINGS_FIELDS, model="tailings", patch_ids=patches, expected_patches=patches
    )
    assert rep["status"] == "complete"
    assert rep["missing_patches"] == []
    assert rep["sc_011_03"] == "pass"


@pytest.mark.req("FR-011-50")
def test_scenario_and_patch_lists_of_different_length_or_unexpected_patches_are_refused() -> None:
    pred, truth = fx.tailings_set(3)
    with pytest.raises(ValueError, match=r"."):
        fno_evaluate.evaluate_fno(
            pred, truth, fx.TAILINGS_FIELDS, model="tailings", patch_ids=["p00", "p01"], expected_patches=["p00", "p01"]
        )
    with pytest.raises(ValueError, match="p77"):
        fno_evaluate.evaluate_fno(
            pred,
            truth,
            fx.TAILINGS_FIELDS,
            model="tailings",
            patch_ids=["p00", "p01", "p77"],
            expected_patches=["p00", "p01", "p02"],
        )


# ------------------------------------------------------------------ calibration


def trial(k: int, covers: bool) -> dict:
    return {
        "trial_id": f"t{k:03d}",
        "arm": "cma-es",
        "simulations": 40,
        "wall_time_s": 1.0,
        "parameters": [
            {
                "name": "sliding_friction",
                "truth": 0.5,
                "estimate": 0.51,
                "identification": "identified",
                "covers_truth": covers,
                "interval": {"lower": 0.4, "upper": 0.6},
            }
        ],
    }


@pytest.mark.req("FR-011-50")
def test_forty_of_fifty_trials_give_partial_with_ten_missing_and_no_coverage_claim() -> None:
    trials = [trial(k, k < 38) for k in range(40)]  # 38 of the 40 present trials cover
    s = study.summarise_arm(trials, expected_trials=50)
    assert s["status"] == "partial"
    assert s["missing"] == 10
    assert s["n_trials"] == 40
    assert s["covering"] == 38
    assert s["coverage"] is None
    assert s["wilson"] is None
    assert s["sc_011_02"] is None


@pytest.mark.req("FR-011-50")
def test_fifty_of_fifty_trials_give_the_coverage() -> None:
    trials = [trial(k, k < 46) for k in range(50)]
    s = study.summarise_arm(trials, expected_trials=50)
    assert s["status"] == "complete"
    assert s["missing"] == 0
    assert s["coverage"] == pytest.approx(0.92)
    assert s["wilson"] is not None
    assert s["wilson"][0] < 0.92 < s["wilson"][1]
    assert s["sc_011_02"] == "pass"


@pytest.mark.req("FR-011-50")
def test_without_expected_trials_the_given_trials_are_the_set() -> None:
    s = study.summarise_arm([trial(k, True) for k in range(50)])
    assert s["status"] == "complete"
    assert s["missing"] == 0


@pytest.mark.req("FR-011-50")
@pytest.mark.parametrize("n_present", [1, 25, 49])
def test_every_shortfall_below_the_expected_count_is_partial(n_present: int) -> None:
    s = study.summarise_arm([trial(k, True) for k in range(n_present)], expected_trials=50)
    assert s["status"] == "partial"
    assert s["missing"] == 50 - n_present
    assert s["sc_011_02"] is None


@pytest.mark.req("FR-011-50")
def test_no_trial_at_all_is_an_error_not_an_empty_report() -> None:
    with pytest.raises(ValueError, match=r"."):
        study.summarise_arm([], expected_trials=50)


@pytest.mark.req("FR-011-50")
def test_more_trials_than_expected_are_refused() -> None:
    with pytest.raises(ValueError, match=r"."):
        study.summarise_arm([trial(k, True) for k in range(51)], expected_trials=50)


@pytest.mark.req("FR-011-50")
def test_the_partial_summary_does_not_mutate_its_input() -> None:
    trials = [trial(k, True) for k in range(40)]
    before = copy.deepcopy(trials)
    study.summarise_arm(trials, expected_trials=50)
    assert trials == before

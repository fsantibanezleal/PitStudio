"""T-011-062 - NFR-011-04: GPU hours are recorded for every training and calibration stage; overruns are stated.

Oracles (independent of the code under test; plan 011 test strategy NFR-011-04: "GPU-hours present in the training
    and calibration manifests"):
hand arithmetic on injected measured seconds against the estimates of NFR-011-04 (GNS <= 15 GPU-h, each FNO <= 2
    GPU-h, each full-scale calibration
<= 2 GPU-h):
  gns          54,000 s = 15.0 h (at the estimate: within), 54,001 s = 15.000278 h (over)
  fno-tailings  7,200 s =  2.0 h (within), 7,500 s = 2.083333 h (over by 0.083333 h)
  fno-dust      3,600 s =  1.0 h (within)
  calibration   7,200 s =  2.0 h (within), 10,800 s = 3.0 h (over by 1.0 h)
The statement of an overrun names the measured hours, the estimate and the word "overrun"; a stage within its
    estimate has an empty statement.
The estimates are estimates, not limits (NFR-011-04: "measured values recorded and overruns stated in the cards").

Expected public API (module `pitstudio.surrogate_budget`, under `src/pitstudio/`, standard library only):

    BUDGET_GPU_HOURS: dict   {"gns": 15.0, "fno-tailings": 2.0, "fno-dust": 2.0, "calibration": 2.0}
    gpu_hours_record(stage, seconds) -> dict
        {"stage", "gpu_hours" (= seconds / 3600), "budget_gpu_hours", "budget_kind": "estimate", "within_budget"
            (bool, hours <= budget),
         "overrun_gpu_hours" (0.0 when within), "statement" ("" when within, else a sentence with "overrun", the
             measured hours and the estimate)}
        Raises ValueError for an unknown stage, or seconds that are negative, non-finite, a bool or not a number.
    attach_gpu_hours(manifest, stage, seconds) -> dict
        returns the manifest (the same object) with manifest["gpu_hours"][stage] = gpu_hours_record(...); a second
            call for a stage replaces its record.
    missing_gpu_hours(manifest, stages_run) -> list[str]
        the stages of `stages_run` (in order) that have no record in manifest["gpu_hours"]; ValueError for an
            unknown stage in `stages_run`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio import surrogate_budget as budget  # noqa: E402

STAGES = ["gns", "fno-tailings", "fno-dust", "calibration"]


@pytest.mark.req("NFR-011-04")
def test_the_estimates_are_the_spec_values() -> None:
    assert budget.BUDGET_GPU_HOURS == {"gns": 15.0, "fno-tailings": 2.0, "fno-dust": 2.0, "calibration": 2.0}


@pytest.mark.req("NFR-011-04")
@pytest.mark.parametrize(
    ("stage", "seconds", "hours", "within"),
    [
        ("gns", 54_000, 15.0, True),
        ("gns", 54_001, 54_001 / 3600, False),
        ("gns", 0, 0.0, True),
        ("fno-tailings", 7_200, 2.0, True),
        ("fno-tailings", 7_500, 7_500 / 3600, False),
        ("fno-dust", 3_600, 1.0, True),
        ("calibration", 7_200, 2.0, True),
        ("calibration", 10_800, 3.0, False),
    ],
)
def test_the_record_converts_seconds_to_hours_and_compares_with_the_estimate(
    stage: str, seconds: float, hours: float, within: bool
) -> None:
    rec = budget.gpu_hours_record(stage, seconds)
    assert rec["stage"] == stage
    assert rec["gpu_hours"] == pytest.approx(hours, rel=1e-12, abs=1e-15)
    assert rec["budget_gpu_hours"] == budget.BUDGET_GPU_HOURS[stage]
    assert rec["budget_kind"] == "estimate"
    assert rec["within_budget"] is within
    assert rec["overrun_gpu_hours"] == pytest.approx(max(0.0, hours - budget.BUDGET_GPU_HOURS[stage]), abs=1e-12)


@pytest.mark.req("NFR-011-04")
def test_a_stage_within_its_estimate_has_an_empty_statement() -> None:
    assert budget.gpu_hours_record("gns", 3_600 * 14)["statement"] == ""


@pytest.mark.req("NFR-011-04")
@pytest.mark.parametrize(
    ("stage", "seconds", "measured", "estimate"),
    [("fno-tailings", 7_500, "2.08", "2"), ("calibration", 10_800, "3.0", "2"), ("gns", 64_800, "18", "15")],
)
def test_an_overrun_is_stated_with_the_measured_hours_and_the_estimate(
    stage: str, seconds: float, measured: str, estimate: str
) -> None:
    text = budget.gpu_hours_record(stage, seconds)["statement"]
    assert "overrun" in text.lower()
    assert measured in text
    assert re.search(rf"\b{estimate}(\.0+)?\b", text)
    assert stage in text


@pytest.mark.req("NFR-011-04")
@pytest.mark.parametrize("stage", ["", "gns ", "GNS", "perception", "fno", "calibration-trial"])
def test_an_unknown_stage_is_refused(stage: str) -> None:
    with pytest.raises(ValueError, match="stage"):
        budget.gpu_hours_record(stage, 100)


@pytest.mark.req("NFR-011-04")
@pytest.mark.parametrize("seconds", [-1, -0.001, float("nan"), float("inf"), float("-inf"), True, "3600", None])
def test_negative_non_finite_or_non_numeric_seconds_are_refused(seconds) -> None:
    with pytest.raises(ValueError, match="seconds"):
        budget.gpu_hours_record("gns", seconds)


@pytest.mark.req("NFR-011-04")
def test_attaching_records_to_a_manifest_and_replacing_a_record() -> None:
    manifest = {"run_id": "20261011T000000Z-a3-gns"}
    out = budget.attach_gpu_hours(manifest, "gns", 3_600)
    assert out is manifest
    assert manifest["gpu_hours"]["gns"]["gpu_hours"] == pytest.approx(1.0)
    budget.attach_gpu_hours(manifest, "calibration", 7_200)
    budget.attach_gpu_hours(manifest, "gns", 7_200)
    assert set(manifest["gpu_hours"]) == {"gns", "calibration"}
    assert manifest["gpu_hours"]["gns"]["gpu_hours"] == pytest.approx(2.0)
    assert manifest["run_id"] == "20261011T000000Z-a3-gns"  # nothing else is touched


@pytest.mark.req("NFR-011-04")
def test_every_stage_that_ran_must_have_a_record() -> None:
    manifest: dict = {}
    assert budget.missing_gpu_hours(manifest, STAGES) == STAGES
    budget.attach_gpu_hours(manifest, "gns", 100)
    budget.attach_gpu_hours(manifest, "calibration", 100)
    assert budget.missing_gpu_hours(manifest, STAGES) == ["fno-tailings", "fno-dust"]
    budget.attach_gpu_hours(manifest, "fno-tailings", 100)
    budget.attach_gpu_hours(manifest, "fno-dust", 100)
    assert budget.missing_gpu_hours(manifest, STAGES) == []
    assert budget.missing_gpu_hours(manifest, []) == []


@pytest.mark.req("NFR-011-04")
def test_a_stage_that_did_not_run_is_not_reported_missing() -> None:
    manifest: dict = {}
    budget.attach_gpu_hours(manifest, "gns", 100)
    assert budget.missing_gpu_hours(manifest, ["gns"]) == []


@pytest.mark.req("NFR-011-04")
def test_an_unknown_stage_in_the_stage_list_is_refused() -> None:
    with pytest.raises(ValueError, match="stage"):
        budget.missing_gpu_hours({}, ["gns", "perception"])

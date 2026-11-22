# ruff: noqa: E501, PT018
"""T-009-016 (fix): the gate of the SDG frames after the carved surface: more annotated frames and two geometry checks.

Requirements: FR-009-02, FR-009-54.

The exposure thresholds of the gate stay (`exposure_qa.GATE`, locked by its own tests); `geometry_qa.evaluate_gate` is the
gate of sdg-geometry-2026-11-22: the annotated share rises to 85 percent (visibility is now constructed by the table), no
frame has a median finite depth below the table's `VIEW_NEAR_M` (10 m), and at least 90 percent of the objects the table
marks visible have at least `MIN_INSTANCE_PX` visible pixels in the render (renderer and table agree).

Oracles: counts and shares written out by hand in each case.

Expected API (`pitstudio_isaac.sdg.geometry_qa`):
- `evaluate_gate(frames) -> dict`: `frames` hold `rgb_std`, `clipped_fraction`, `annotations`, `haze_limited`,
  `median_depth_m` and `objects` (a list of `{"table_visible": bool, "visible_px": int}`); the result has the thresholds
  of `exposure_qa.evaluate_gate` with the annotated limit 0.85, plus `near_median_depth` (value: frames below 10 m,
  limit 0) and `table_render_agreement` (value: share of table-visible objects with at least 16 visible pixels, limit
  0.90), and `passed`.
- `ANNOTATED_SHARE`, `MIN_MEDIAN_DEPTH_M`, `AGREEMENT_SHARE`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
from pitstudio_isaac.sdg import exposure_qa, geometry_qa  # noqa: E402


def frame(**kw):
    base = {
        "rgb_std": 40.0,
        "clipped_fraction": 0.0,
        "annotations": 1,
        "haze_limited": False,
        "median_depth_m": 30.0,
        "objects": [{"table_visible": True, "visible_px": 500}],
    }
    return base | kw


@pytest.mark.req("FR-009-54")
def test_the_limits_are_the_decided_ones() -> None:
    assert geometry_qa.ANNOTATED_SHARE == 0.85
    assert geometry_qa.MIN_MEDIAN_DEPTH_M == 10.0
    assert geometry_qa.AGREEMENT_SHARE == 0.90
    assert exposure_qa.GATE["annotated_share"] == 0.78  # the exposure gate itself is unchanged


@pytest.mark.req("FR-009-54")
def test_a_clean_sample_passes_every_threshold() -> None:
    out = geometry_qa.evaluate_gate([frame() for _ in range(20)])
    assert out["passed"] is True
    assert out["thresholds"]["near_median_depth"] == {"value": 0, "limit": 0, "passed": True}
    assert out["thresholds"]["table_render_agreement"]["value"] == 1.0


@pytest.mark.req("FR-009-54")
def test_the_annotated_share_needs_85_percent_not_78() -> None:
    frames = [frame() for _ in range(81)] + [frame(annotations=0) for _ in range(19)]  # 81 percent
    out = geometry_qa.evaluate_gate(frames)
    assert out["thresholds"]["annotated"]["limit"] == 0.85 and out["thresholds"]["annotated"]["passed"] is False
    assert out["passed"] is False
    frames = [frame() for _ in range(85)] + [frame(annotations=0) for _ in range(15)]  # exactly 85 percent passes
    assert geometry_qa.evaluate_gate(frames)["thresholds"]["annotated"]["passed"] is True


@pytest.mark.req("FR-009-54")
def test_one_frame_with_a_median_depth_below_10_m_fails_and_exactly_10_m_passes() -> None:
    frames = [frame() for _ in range(30)]
    assert geometry_qa.evaluate_gate([*frames, frame(median_depth_m=10.0)])["thresholds"]["near_median_depth"]["passed"]
    out = geometry_qa.evaluate_gate([*frames, frame(median_depth_m=9.99)])
    assert out["thresholds"]["near_median_depth"] == {"value": 1, "limit": 0, "passed": False}
    assert out["passed"] is False


@pytest.mark.req("FR-009-54")
def test_a_frame_without_a_finite_depth_counts_as_too_near() -> None:
    out = geometry_qa.evaluate_gate([frame(median_depth_m=float("nan")), *[frame() for _ in range(10)]])
    assert out["thresholds"]["near_median_depth"]["value"] == 1


@pytest.mark.req("FR-009-54")
def test_the_table_and_the_render_must_agree_on_90_percent_of_the_visible_objects() -> None:
    def objects(good: int, bad: int):
        return [{"table_visible": True, "visible_px": 16}] * good + [{"table_visible": True, "visible_px": 15}] * bad

    ok = geometry_qa.evaluate_gate([frame(objects=objects(90, 10))])
    check = ok["thresholds"]["table_render_agreement"]
    assert (check["value"], check["limit"], check["passed"]) == (0.9, 0.9, True)
    bad = geometry_qa.evaluate_gate([frame(objects=objects(89, 11))])
    assert bad["thresholds"]["table_render_agreement"]["passed"] is False and bad["passed"] is False


@pytest.mark.req("FR-009-54")
def test_objects_the_table_marks_not_visible_do_not_enter_the_agreement() -> None:
    hidden = {"table_visible": False, "visible_px": 0}
    out = geometry_qa.evaluate_gate([frame(objects=[{"table_visible": True, "visible_px": 100}, hidden, hidden])])
    assert out["thresholds"]["table_render_agreement"]["value"] == 1.0
    assert out["thresholds"]["table_render_agreement"]["objects"] == 1


@pytest.mark.req("FR-009-54")
def test_the_exposure_thresholds_still_apply() -> None:
    frames = [frame() for _ in range(20)] + [frame(rgb_std=0.5)]  # one flat frame that is not haze-limited
    out = geometry_qa.evaluate_gate(frames)
    assert out["thresholds"]["flat_not_haze"]["passed"] is False and out["passed"] is False
    assert {"rgb_std_median", "rgb_std_p10", "clipped_over_25pct", "haze_limited"} <= set(out["thresholds"])

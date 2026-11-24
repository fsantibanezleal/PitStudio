"""T-010-111: the real-event table of case C1 at the cut-offs 0.5 and 0.8 (FR-010-26, FR-010-27, SC-010-03).

Spec: specs/010-slope/spec.md section 3.3. Runs in the `pipeline/` environment.

Expected API (module `pitstudio_pipeline.slope.c1_real_eval`):
- `evaluate(document, forecasters, *, seed) -> dict`: `evaluate.real_event_report` on the real-event document (12 rows
  in
  the fixed order, signed error t_hat - t_f and its ratio to t_f - t_c) with, on every row that has a forecast,
  `signed_error_interval_h` {"lower", "upper"} and `error_ratio_interval` {"lower", "upper"}: the day uncertainty
  `t_f_uncertainty_h` of the failure time applied to the same forecast (the windows are not re-run); the instants
  `t_0_instant`, `t_f_instant`, the uncertainty, the zone and the label. No rank, verdict, interval of the estimate or
  significance field exists anywhere.
- `evaluate_pair(primary, sensitivity, forecasters, *, seed) -> dict`: {"primary", "sensitivity", "label"}: the two
  documents are evaluated alike, the sensitivity one is never ranked against the primary.
- `blast_marker(events_csv: str, local_date: str, *, utc_offset_h: float) -> dict | None`: the largest event of the
  seismic list of the archive on a local date: {"instant", "magnitude", "basis"} (None when the day has no event).
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from pitstudio.slope import evaluate as ev
from pitstudio_pipeline.slope import c1_real_eval

T_F = 1200.0
LABEL = "single real event — no significance test"


def _doc(t_f_h: float = T_F, *, t_f_instant: str = "2014-02-23T00:00:00") -> dict:
    t = np.arange(0.0, t_f_h - 20.0, 6.0)
    rng = np.random.default_rng(7)
    omega = 400.0 * (t / t_f_h) ** 3 + rng.normal(0.0, 0.3, t.size)
    return {
        "kind": "real-event",
        "synthetic": False,
        "event_id": "dewit-2025-event",
        "stratum": "real",
        "t_0_h": 0.0,
        "t_f_h": t_f_h,
        "t_0_instant": "2014-01-01T12:00:00",
        "t_f_instant": t_f_instant,
        "t_f_uncertainty_h": 24.0,
        "zone": "local time of the archive",
        "snr_obs": 12.5,
        "t_h": [float(x) for x in t],
        "los_displacement_mm": [float(x) for x in omega],
    }


def _crossing(_x: np.ndarray) -> np.ndarray:
    return np.tile(np.linspace(1.0, -1.0, 64, dtype=np.float32), (9, 1))[None]


def _flat(_x: np.ndarray) -> np.ndarray:
    return np.full((1, 9, 64), 0.5, dtype=np.float32)


def _broken(_x: np.ndarray) -> np.ndarray:
    return np.full((1, 9, 64), np.nan, dtype=np.float32)


FORECASTERS = {"tcn": _crossing, "patchtst": _flat, "chronos_bolt_fine_tuned": _broken}


@pytest.fixture(scope="module")
def result() -> dict:
    return c1_real_eval.evaluate(_doc(), FORECASTERS, seed=20261007)


@pytest.mark.req("FR-010-26")
def test_twelve_rows_in_the_fixed_order_cutoff_first(result) -> None:
    rows = result["rows"]
    assert [(r["cutoff"], r["method"]) for r in rows] == [(c, m) for c in (0.5, 0.8) for m in ev.METHODS]
    assert result["status"] == "run"
    assert result["label"] == LABEL
    assert result["snr_obs"] == 12.5


@pytest.mark.req("FR-010-26")
def test_the_signed_error_and_its_ratio_follow_the_definition(result) -> None:
    for r in result["rows"]:
        if "t_hat_f_h" not in r:
            continue
        t_c = r["cutoff"] * T_F
        assert r["t_c_h"] == pytest.approx(t_c)
        assert r["signed_error_h"] == pytest.approx(r["t_hat_f_h"] - T_F)
        assert r["error_ratio"] == pytest.approx((r["t_hat_f_h"] - T_F) / (T_F - t_c))


@pytest.mark.req("FR-010-26")
def test_the_day_interval_of_t_f_is_applied_to_every_error_with_the_forecast_fixed(result) -> None:
    n = 0
    for r in result["rows"]:
        if "t_hat_f_h" not in r:
            assert "signed_error_interval_h" not in r
            continue
        n += 1
        t_c = r["t_c_h"]
        lo, hi = r["signed_error_interval_h"]["lower"], r["signed_error_interval_h"]["upper"]
        # t_f in [T_F - 24, T_F + 24]: the error t_hat - t_f is largest at the earliest t_f
        assert lo == pytest.approx(r["t_hat_f_h"] - (T_F + 24.0))
        assert hi == pytest.approx(r["t_hat_f_h"] - (T_F - 24.0))
        ratios = [(r["t_hat_f_h"] - tf) / (tf - t_c) for tf in (T_F - 24.0, T_F + 24.0)]
        assert r["error_ratio_interval"]["lower"] == pytest.approx(min(ratios))
        assert r["error_ratio_interval"]["upper"] == pytest.approx(max(ratios))
        assert lo <= r["signed_error_h"] <= hi
    assert n >= 6
    assert result["t_f_uncertainty_h"] == 24.0
    assert result["t_f_instant"] == "2014-02-23T00:00:00"


@pytest.mark.req("FR-010-26")
def test_the_zero_shot_arm_is_not_run_a_failed_arm_has_no_number_and_the_reason_is_kept(result) -> None:
    by = {(r["cutoff"], r["method"]): r for r in result["rows"]}
    for c in (0.5, 0.8):
        zs = by[(c, "chronos_bolt_zero_shot")]
        assert zs["outcome"] == "not run"
        assert "t_hat_f_h" not in zs
        assert zs["reason"]
        bad = by[(c, "chronos_bolt_fine_tuned")]
        assert bad["outcome"] == "no forecast"
        assert "t_hat_f_h" not in bad
        assert bad["reason"]
        assert by[(c, "tcn")]["outcome"] == "predicted"
        assert by[(c, "patchtst")]["scored_at_cap"] is True


@pytest.mark.req("FR-010-27")
def test_nothing_is_ranked_judged_or_tested(result) -> None:
    text = json.dumps(result).lower()
    for word in ("rank", "verdict", "best", "better", "winner", "p_value", "significan"):
        # the label itself says "no significance test"
        assert word not in text.replace("no significance test", ""), word
    for r in result["rows"]:
        assert not {"rank", "verdict", "highlight", "interval"} & set(r)


@pytest.mark.req("FR-010-26")
def test_the_evaluation_is_deterministic_for_its_seed() -> None:
    a = c1_real_eval.evaluate(_doc(), FORECASTERS, seed=5)
    b = c1_real_eval.evaluate(_doc(), FORECASTERS, seed=5)
    assert a == b


@pytest.mark.req("FR-010-26")
def test_the_sensitivity_failure_time_is_evaluated_alike_with_its_own_cut_offs_and_never_ranked() -> None:
    primary = _doc(1200.0)
    sens = _doc(1130.0, t_f_instant="2014-02-20T00:00:00")
    out = c1_real_eval.evaluate_pair(primary, sens, FORECASTERS, seed=3)
    assert out["label"] == LABEL
    assert out["primary"]["t_f_h"] == 1200.0
    assert out["sensitivity"]["t_f_h"] == 1130.0
    a = {(r["cutoff"], r["method"]): r for r in out["primary"]["rows"]}
    b = {(r["cutoff"], r["method"]): r for r in out["sensitivity"]["rows"]}
    assert a[(0.5, "tcn")]["t_c_h"] == pytest.approx(600.0)
    assert b[(0.5, "tcn")]["t_c_h"] == pytest.approx(565.0)
    assert out["sensitivity"]["t_f_instant"] == "2014-02-20T00:00:00"
    text = json.dumps(out).lower()
    assert "rank" not in text
    assert "verdict" not in text


@pytest.mark.req("FR-010-26")
def test_a_non_positive_snr_or_a_missing_instant_is_refused() -> None:
    bad = _doc()
    bad["snr_obs"] = 0.0
    with pytest.raises(ValueError, match="snr_obs"):
        c1_real_eval.evaluate(bad, FORECASTERS, seed=1)
    bad2 = _doc()
    del bad2["t_f_uncertainty_h"]
    with pytest.raises(ValueError, match="t_f_uncertainty_h"):
        c1_real_eval.evaluate(bad2, FORECASTERS, seed=1)


EVENTS = (
    "#Index,EventTimeEpochSeconds,Local Magnitude,Potency [m^3],LocE [m],LocN [m],LocU [m]\n"
    "1,1392075642.5,1.3,1E-3,46495.5,27565.9,858.4\n"  # 2014-02-10T23:40:42Z = 2014-02-11T09:40:42 at UTC+10
    "2,1392070000.0,-2.0,1E-3,46000.0,27000.0,800.0\n"  # 2014-02-10T22:06:40Z = 2014-02-11T08:06:40
    "3,1392300000.0,0.5,1E-3,46000.0,27000.0,800.0\n"  # 2014-02-13
)


@pytest.mark.req("FR-010-26")
def test_the_blast_marker_is_the_largest_archive_event_of_the_local_date() -> None:
    m = c1_real_eval.blast_marker(EVENTS, "2014-02-11", utc_offset_h=10.0)
    assert m is not None
    assert m["instant"] == "2014-02-11T09:40:42"
    assert m["magnitude"] == 1.3
    assert "UNVERIFIED" in m["basis"]
    assert c1_real_eval.blast_marker(EVENTS, "2014-02-12", utc_offset_h=10.0) is None

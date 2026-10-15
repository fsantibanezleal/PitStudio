"""T-010-030: relative TTF errors, lead time at alarm, median with a percentile-bootstrap interval.

Requirements: FR-010-23, FR-010-24.
Spec: specs/010-slope/spec.md section 3.3 (FR-010-23, FR-010-24); plan.md rows FR-010-23 and FR-010-24 ("hand-computed
errors and lead times on a 5-event fixture; percentiles of injected bootstrap resamples computed with numpy").

Expected API (module `pitstudio.slope.evaluate`, numpy only):
- `relative_error(t_hat, t_f, t_c) = |t_hat - t_f| / (t_f - t_c)`; `cutoff_time(t_0, t_f, c) = t_0 + c (t_f - t_0)`.
- `score_events(predictions) -> list[dict]`: each prediction is {event_id, stratum, method, cutoff, t_0_h, t_f_h,
  outcome,
  t_hat_f_h (absent for "no forecast"), interval_80_h (optional), reason (for "no forecast")}; each result row follows
  `ttf-results.schema.json#/$defs/event_result`: t_c_h, t_f_h, outcome, t_hat_f_h, rel_error, error_h (signed, t_hat -
  t_f),
  scored_at_cap (True exactly for "no failure predicted"), the interval and no error fields for "no forecast".
- `summarise(rows) -> list[dict]`: one row per (method, stratum, cutoff) shaped as `#/$defs/summary`: n_events (the
  scored
  rows), median_rel_error, mean_rel_error, p90_rel_error (numpy percentile, linear interpolation), median_abs_error_h.
- `alarm(forecast_at, t_0, t_f, *, t_alarm_h=24.0) -> dict`: over the cut-off grid 0.30, 0.31, ..., 0.99 the first
  cut-off c
  with `forecast_at(c)` not None (a failure predicted) and t_hat - t_c <= t_alarm_h; returns {"alarmed": True,
  "alarm_cutoff": c,
  "lead_time_h": t_f - t_c} or {"alarmed": False}.
- `alarm_summary(alarm_rows) -> dict`: never_alarmed_fraction and median_lead_time_h (absent when no event alarmed).
- `acceptance_row(method, cutoff, errors, *, seed, resamples=10000, indices=None, threshold=0.10) -> dict` shaped as
  `#/$defs/acceptance` (stratum snr_obs): n_events, median_rel_error, interval {lower, upper} (percentile bootstrap of
  the
  median, level 0.95: numpy percentiles 2.5 and 97.5 of the resampled medians), bootstrap {resamples, method
  "percentile",
  level 0.95, seed}, threshold, verdict "pass" when the median <= threshold else "fail". `indices` (an int array
  (resamples, n)) injects the resample indices for exact tests; otherwise they come from
  `np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))`.

Oracles: hand calculation on a 5-event fixture (written out below), the alarm example of the DC-010-03 contract
(cut-off 0.62
of a 240 h record: lead time 91.2 h), numpy percentiles of injected resamples, the closed-form standard error of a
sample
mean for the bootstrap width.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_lem_ref as lem_ref
from pitstudio.slope import evaluate

# five events, t_0 = 0, cut-off 0.5: t_f = 100, 200, 100, 300, 200 -> t_c = 50, 100, 50, 150, 100
T_F = [100.0, 200.0, 100.0, 300.0, 200.0]
T_HAT = [110.0, 190.0, 90.0, 330.0, 612.0]  # the last forecast is "no failure predicted", scored at the cap
# hand: errors |t_hat - t_f| = 10, 10, 10, 30, 412 h; leads t_f - t_c = 50, 100, 50, 150, 100 h
REL = [0.2, 0.1, 0.2, 0.2, 4.12]


def _predictions(method="tcn", cutoff=0.5):
    out = []
    for i, (t_f, t_hat) in enumerate(zip(T_F, T_HAT, strict=True)):
        out.append(
            {
                "event_id": f"voight-test-snr-obs-{i:06d}",
                "stratum": "snr_obs",
                "method": method,
                "cutoff": cutoff,
                "t_0_h": 0.0,
                "t_f_h": t_f,
                "outcome": "no failure predicted" if i == 4 else "predicted",
                "t_hat_f_h": t_hat,
            }
        )
    return out


@pytest.mark.req("FR-010-23")
def test_relative_error_and_cutoff_time_by_hand() -> None:
    assert evaluate.cutoff_time(10.0, 110.0, 0.8) == pytest.approx(90.0)
    assert evaluate.relative_error(247.2, 240.0, 120.0) == pytest.approx(7.2 / 120.0)  # the contract example, 0.06
    assert evaluate.relative_error(236.4, 240.0, 120.0) == pytest.approx(0.03)
    assert evaluate.relative_error(240.0, 240.0, 120.0) == 0.0


@pytest.mark.req("FR-010-23")
def test_scored_rows_carry_the_signed_error_the_relative_error_and_the_cap_flag() -> None:
    rows = evaluate.score_events(_predictions())
    assert [r["rel_error"] for r in rows] == pytest.approx(REL, rel=1e-12)
    assert [r["error_h"] for r in rows] == pytest.approx([10.0, -10.0, -10.0, 30.0, 412.0])
    assert [r["t_c_h"] for r in rows] == pytest.approx([50.0, 100.0, 50.0, 150.0, 100.0])
    assert [r["scored_at_cap"] for r in rows] == [False, False, False, False, True]
    assert rows[4]["outcome"] == "no failure predicted"
    for r in rows:
        assert lem_ref.schema_errors(r, "ttf-results", "event_result") == []


@pytest.mark.req("FR-010-23")
def test_a_no_forecast_row_has_a_reason_and_no_error_fields() -> None:
    pred = {
        "event_id": "voight-test-snr-obs-000009",
        "stratum": "snr_obs",
        "method": "chronos_bolt_zero_shot",
        "cutoff": 0.5,
        "t_0_h": 0.0,
        "t_f_h": 203.0,
        "outcome": "no forecast",
        "reason": "no positive velocity in the window",
    }
    (row,) = evaluate.score_events([pred])
    assert row["outcome"] == "no forecast"
    assert row["reason"] == "no positive velocity in the window"
    assert row["t_c_h"] == pytest.approx(101.5)
    assert not {"rel_error", "error_h", "t_hat_f_h", "scored_at_cap"} & set(row)
    assert lem_ref.schema_errors(row, "ttf-results", "event_result") == []


@pytest.mark.req("FR-010-23")
def test_summary_median_mean_and_ninetieth_percentile_by_hand() -> None:
    (s,) = evaluate.summarise(evaluate.score_events(_predictions()))
    assert (s["method"], s["stratum"], s["cutoff"], s["n_events"]) == ("tcn", "snr_obs", 0.5, 5)
    assert s["median_rel_error"] == pytest.approx(0.2, rel=1e-12)
    assert s["mean_rel_error"] == pytest.approx((0.2 + 0.1 + 0.2 + 0.2 + 4.12) / 5, rel=1e-12)  # 0.964
    assert s["p90_rel_error"] == pytest.approx(
        0.2 + 0.6 * (4.12 - 0.2), rel=1e-12
    )  # rank 0.9 x 4 = 3.6 between 0.2 and 4.12
    assert s["median_abs_error_h"] == pytest.approx(10.0)
    assert lem_ref.schema_errors(s, "ttf-results", "summary") == []


@pytest.mark.req("FR-010-23")
def test_summary_groups_by_method_stratum_and_cutoff() -> None:
    preds = _predictions("tcn", 0.5) + _predictions("patchtst", 0.5)
    for p in _predictions("tcn", 0.8):
        p["t_hat_f_h"] = p["t_f_h"]  # perfect forecasts at the second cut-off
        p["outcome"] = "predicted"
        preds.append(p)
    rows = {(s["method"], s["cutoff"]): s for s in evaluate.summarise(evaluate.score_events(preds))}
    assert set(rows) == {("tcn", 0.5), ("patchtst", 0.5), ("tcn", 0.8)}
    assert rows[("tcn", 0.8)]["median_rel_error"] == 0.0
    assert rows[("tcn", 0.8)]["p90_rel_error"] == 0.0
    assert rows[("patchtst", 0.5)]["n_events"] == 5


@pytest.mark.req("FR-010-23")
def test_alarm_is_the_first_cutoff_with_a_prediction_within_t_alarm() -> None:
    t_f = 240.0

    def forecast_at(c):  # predicts failure 24 h after the cut-off from c = 0.62 on, nothing before
        return c * t_f + 24.0 if c >= 0.62 - 1e-9 else None

    got = evaluate.alarm(forecast_at, 0.0, t_f)
    assert got["alarmed"] is True
    assert got["alarm_cutoff"] == pytest.approx(0.62)
    assert got["lead_time_h"] == pytest.approx(91.2, rel=1e-12)  # 240 - 0.62 x 240, the contract example
    # a predicted failure beyond the alarm horizon is not an alarm; a looser horizon alarms earlier
    far = lambda c: c * t_f + 40.0 if c >= 0.5 - 1e-9 else None  # noqa: E731
    assert evaluate.alarm(far, 0.0, t_f)["alarmed"] is False
    wide = evaluate.alarm(far, 0.0, t_f, t_alarm_h=48.0)
    assert wide["alarm_cutoff"] == pytest.approx(0.50)
    assert wide["lead_time_h"] == pytest.approx(120.0)


@pytest.mark.req("FR-010-23")
def test_alarm_grid_is_030_to_099_and_never_alarmed_events_carry_no_cutoff() -> None:
    seen: list[float] = []

    def forecast_at(c):
        seen.append(c)

    out = evaluate.alarm(forecast_at, 0.0, 100.0)
    assert out == {"alarmed": False}
    assert len(seen) == 70
    assert seen[0] == pytest.approx(0.30)
    assert seen[-1] == pytest.approx(0.99)
    assert seen == pytest.approx(np.arange(30, 100) / 100.0)
    late = evaluate.alarm(lambda c: c * 100.0 + 5.0 if c > 0.989 else None, 0.0, 100.0)  # only the last grid point
    assert late["alarm_cutoff"] == pytest.approx(0.99)
    assert late["lead_time_h"] == pytest.approx(1.0)


@pytest.mark.req("FR-010-23")
def test_alarm_summary_fraction_never_alarmed_and_median_lead_time() -> None:
    rows = [
        {"alarmed": True, "alarm_cutoff": 0.5, "lead_time_h": 40.0},
        {"alarmed": True, "alarm_cutoff": 0.6, "lead_time_h": 10.0},
        {"alarmed": False},
        {"alarmed": True, "alarm_cutoff": 0.9, "lead_time_h": 25.0},
    ]
    s = evaluate.alarm_summary(rows)
    assert s["never_alarmed_fraction"] == pytest.approx(0.25)
    assert s["median_lead_time_h"] == pytest.approx(25.0)
    none = evaluate.alarm_summary([{"alarmed": False}, {"alarmed": False}])
    assert none["never_alarmed_fraction"] == 1.0
    assert "median_lead_time_h" not in none


@pytest.mark.req("FR-010-24")
def test_acceptance_interval_is_the_numpy_percentile_of_the_injected_resampled_medians() -> None:
    errors = {f"e{i}": v for i, v in enumerate([0.02, 0.03, 0.05, 0.08, 0.30])}
    idx = np.array(
        [[0, 1, 2, 3, 4], [4, 4, 4, 0, 1], [0, 0, 1, 1, 2], [3, 3, 3, 3, 3], [2, 4, 1, 0, 3], [1, 1, 1, 0, 0]]
    )
    vals = np.array(list(errors.values()))
    medians = np.median(vals[idx], axis=1)  # [0.05, 0.30, 0.03, 0.08, 0.05, 0.03]
    lo, hi = np.percentile(medians, [2.5, 97.5])
    row = evaluate.acceptance_row("tcn", 0.5, errors, seed=4242, indices=idx)
    assert row["median_rel_error"] == pytest.approx(0.05)
    assert row["interval"]["lower"] == pytest.approx(lo, rel=1e-12)
    assert row["interval"]["upper"] == pytest.approx(hi, rel=1e-12)
    assert (row["method"], row["cutoff"], row["stratum"], row["n_events"]) == ("tcn", 0.5, "snr_obs", 5)
    assert row["threshold"] == 0.10
    assert row["verdict"] == "pass"
    assert row["bootstrap"]["method"] == "percentile"
    assert row["bootstrap"]["level"] == 0.95
    assert row["bootstrap"]["seed"] == 4242


@pytest.mark.req("FR-010-24")
def test_acceptance_verdict_follows_the_median_not_the_mean_and_the_threshold_is_inclusive() -> None:
    skewed = {f"e{i}": v for i, v in enumerate([0.01, 0.02, 0.03, 0.04, 9.0])}  # mean 1.82, median 0.03
    assert evaluate.acceptance_row("tcn", 0.5, skewed, seed=1, resamples=500)["verdict"] == "pass"
    bad = {f"e{i}": v for i, v in enumerate([0.2, 0.3, 0.4, 0.5, 0.6])}
    assert evaluate.acceptance_row("tcn", 0.8, bad, seed=1, resamples=500)["verdict"] == "fail"
    edge = {f"e{i}": 0.10 for i in range(9)}
    assert (
        evaluate.acceptance_row("patchtst", 0.5, edge, seed=1, resamples=100)["verdict"] == "pass"
    )  # median 0.10 <= 0.10


@pytest.mark.req("FR-010-24")
def test_default_bootstrap_uses_10000_resamples_is_seeded_and_order_independent() -> None:
    rng = np.random.default_rng(8)
    errors = {f"ev-{i:04d}": float(v) for i, v in enumerate(rng.lognormal(-2.5, 0.5, 500))}
    a = evaluate.acceptance_row("tcn", 0.5, errors, seed=77)
    b = evaluate.acceptance_row("tcn", 0.5, dict(reversed(list(errors.items()))), seed=77)
    c = evaluate.acceptance_row("tcn", 0.5, errors, seed=78)
    assert a["bootstrap"]["resamples"] == 10_000
    assert a == b  # resampling is over the sorted event ids
    assert a["interval"] != c["interval"]
    # the interval brackets the sample median and its width is that of the sampling distribution of the median
    # (about 1.2533 sigma / sqrt(n) for a smooth density; a factor-2 band is enough to catch a wrong statistic)
    vals = np.array(list(errors.values()))
    assert a["interval"]["lower"] < np.median(vals) < a["interval"]["upper"]
    width = a["interval"]["upper"] - a["interval"]["lower"]
    approx_width = 2 * 1.96 * 1.2533 * vals.std(ddof=1) / np.sqrt(len(vals))
    assert 0.5 * approx_width < width < 2.0 * approx_width


@pytest.mark.req("FR-010-24")
@pytest.mark.parametrize(
    "bad", [{}, {"a": float("nan"), "b": 0.1}, {"a": -0.1, "b": 0.1}, {"a": float("inf"), "b": 0.1}]
)
def test_acceptance_rejects_hostile_error_sets(bad) -> None:
    with pytest.raises(ValueError, match=r"."):
        evaluate.acceptance_row("tcn", 0.5, bad, seed=1, resamples=100)

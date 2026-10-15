"""T-010-042: the descriptive real-event report (one event, no interval, no ranking, no verdict).

Requirements: FR-010-26, SC-010-03.
Spec: specs/010-slope/spec.md section 3.3 (FR-010-26), section 5 (SC-010-03), FR-010-14 (the "Not run" state);
plan.md row FR-010-26 ("contract: the real-event block has no interval, rank or verdict field; order fixed").

Expected API (module `pitstudio.slope.evaluate`, numpy only):
- `real_event_report(*, event_id, t_0_h, t_f_h, snr_obs, forecasts) -> dict`: the `real_event` block of
  `ttf-results.schema.json` for a run: {event_id, status "run", label "single real event - no significance test" (with
  the
  em dash), snr_obs, t_0_h, t_f_h, rows}. `forecasts` maps (method, cutoff) to {"outcome": "predicted" | "no failure
  predicted" | "no forecast", "t_hat_f_h": ..., "reason": ...}. `rows` has exactly 12 entries in the fixed order:
  cut-off 0.5 then
  0.8, each with the methods inverse_velocity, bayesian_ttf, tcn, patchtst, chronos_bolt_zero_shot,
  chronos_bolt_fine_tuned.
  A row carries cutoff, method, t_c_h = t_0 + c (t_f - t_0), outcome and, when a forecast exists, t_hat_f_h,
  signed_error_h =
  t_hat - t_f, error_ratio = signed_error_h / (t_f - t_c) and scored_at_cap (True exactly for "no failure predicted"); a
  method without a forecast entry is a "not run" row with a reason; "no forecast" keeps its reason; neither has error
  fields.
- `real_event_not_run(event_id, reason) -> dict`: {event_id, status "not run", label, reason}: no TTF number, no rows,
  no SNR.
  ValueError for t_f <= t_0, an unknown method or cut-off key, or a non-finite value.

Oracles: hand calculation from the contract example (t_0 = 0, t_f = 410 h: at c = 0.5, t_c = 205 and an inverse-velocity
forecast of 431 h has signed error 21 h and ratio 21 / 205 = 0.102439; at c = 0.8, t_c = 328 and 414.1 h gives 4.1 h
and 0.05);
the schema (jsonschema); a recursive scan for any interval / rank / verdict / significance field.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_lem_ref as lem_ref
from pitstudio.slope import evaluate

LABEL = "single real event — no significance test"
METHODS = ["inverse_velocity", "bayesian_ttf", "tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned"]
FORBIDDEN = {
    "interval",
    "interval_80_h",
    "ci",
    "rank",
    "ranking",
    "verdict",
    "p_value",
    "better",
    "winner",
    "best",
    "significance",
}


def _forecasts() -> dict:
    f = {
        ("inverse_velocity", 0.5): {"outcome": "predicted", "t_hat_f_h": 431.0},
        ("bayesian_ttf", 0.5): {"outcome": "predicted", "t_hat_f_h": 436.5},
        ("tcn", 0.5): {"outcome": "predicted", "t_hat_f_h": 401.2},
        ("patchtst", 0.5): {"outcome": "predicted", "t_hat_f_h": 418.9},
        ("chronos_bolt_zero_shot", 0.5): {"outcome": "no failure predicted", "t_hat_f_h": 615.8023},
        ("inverse_velocity", 0.8): {"outcome": "predicted", "t_hat_f_h": 414.1},
        ("bayesian_ttf", 0.8): {"outcome": "predicted", "t_hat_f_h": 415.0},
        ("tcn", 0.8): {"outcome": "predicted", "t_hat_f_h": 408.3},
        ("patchtst", 0.8): {"outcome": "predicted", "t_hat_f_h": 411.6},
        ("chronos_bolt_zero_shot", 0.8): {"outcome": "predicted", "t_hat_f_h": 405.0},
    }  # no chronos_bolt_fine_tuned forecasts: that arm did not run
    return f


def _report(forecasts=None, **kw):
    return evaluate.real_event_report(
        event_id="dewit-2025-event",
        t_0_h=0.0,
        t_f_h=410.0,
        snr_obs=63.5,
        forecasts=_forecasts() if forecasts is None else forecasts,
        **kw,
    )


def _keys(node, found=None):
    found = set() if found is None else found
    if isinstance(node, dict):
        for k, v in node.items():
            found.add(k)
            _keys(v, found)
    elif isinstance(node, list):
        for v in node:
            _keys(v, found)
    return found


@pytest.mark.req("FR-010-26")
def test_twelve_rows_in_the_fixed_order_with_the_signed_errors_by_hand() -> None:
    block = _report()
    assert block["status"] == "run"
    assert block["label"] == LABEL
    assert (block["event_id"], block["snr_obs"], block["t_0_h"], block["t_f_h"]) == (
        "dewit-2025-event",
        63.5,
        0.0,
        410.0,
    )
    rows = block["rows"]
    assert [(r["cutoff"], r["method"]) for r in rows] == [(c, m) for c in (0.5, 0.8) for m in METHODS]
    first = rows[0]
    assert first["t_c_h"] == pytest.approx(205.0)
    assert first["signed_error_h"] == pytest.approx(21.0)
    assert first["error_ratio"] == pytest.approx(21.0 / 205.0, rel=1e-12)  # 0.102439
    assert first["scored_at_cap"] is False
    iv8 = rows[6]
    assert iv8["t_c_h"] == pytest.approx(328.0)
    assert iv8["signed_error_h"] == pytest.approx(4.1)
    assert iv8["error_ratio"] == pytest.approx(0.05, rel=1e-12)
    tcn = rows[2]
    assert tcn["signed_error_h"] == pytest.approx(-8.8)  # undershoot is negative
    assert tcn["error_ratio"] == pytest.approx(-8.8 / 205.0, rel=1e-12)
    cap = rows[4]
    assert cap["outcome"] == "no failure predicted"
    assert cap["scored_at_cap"] is True
    assert cap["signed_error_h"] == pytest.approx(615.8023 - 410.0)
    assert cap["error_ratio"] == pytest.approx((615.8023 - 410.0) / 205.0, rel=1e-12)


@pytest.mark.req("FR-010-26")
def test_a_method_without_a_forecast_is_a_not_run_row_without_error_fields() -> None:
    rows = _report()["rows"]
    for r in (rows[5], rows[11]):
        assert r["method"] == "chronos_bolt_fine_tuned"
        assert r["outcome"] == "not run"
        assert r["reason"]
        assert not {"t_hat_f_h", "signed_error_h", "error_ratio", "scored_at_cap"} & set(r)
    forecasts = _forecasts()
    forecasts[("tcn", 0.5)] = {"outcome": "no forecast", "reason": "no positive velocity in the window"}
    row = _report(forecasts)["rows"][2]
    assert row["outcome"] == "no forecast"
    assert row["reason"] == "no positive velocity in the window"
    assert "signed_error_h" not in row


@pytest.mark.req("FR-010-26")
def test_the_row_order_does_not_depend_on_the_order_of_the_input() -> None:
    forecasts = dict(reversed(list(_forecasts().items())))
    assert _report(forecasts) == _report()


@pytest.mark.req("SC-010-03")
def test_the_block_has_no_interval_ranking_or_verdict_anywhere_and_validates() -> None:
    block = _report()
    assert _keys(block) & FORBIDDEN == set()
    assert block["label"] == LABEL
    ttf = {
        "schema_version": "1.0",
        "run_id": "20261115T101500Z-c1",
        "snr_basis": "observed",
        "snr_obs": 63.5,
        "t_alarm_h": 24,
        "horizon_cap_steps": 1024,
        "events": [],
        "alarms": [],
        "summary": [],
        "alarm_summary": [],
        "acceptance": [],
        "comparisons": [],
        "multiplicity": {"comparisons": 8, "family_wise_claim": False},
        "real_event": block,
    }
    assert lem_ref.schema_errors(ttf, "ttf-results") == []


@pytest.mark.req("FR-010-26")
def test_when_the_real_series_is_absent_the_block_is_not_run_with_no_ttf_number() -> None:
    block = evaluate.real_event_not_run("dewit-2025-event", "archive checksum mismatch")
    assert block == {
        "event_id": "dewit-2025-event",
        "status": "not run",
        "label": LABEL,
        "reason": "archive checksum mismatch",
    }
    assert _keys(block) & {"rows", "snr_obs", "t_f_h", "t_hat_f_h", "signed_error_h", "error_ratio"} == set()


@pytest.mark.req("FR-010-26")
@pytest.mark.parametrize(
    "change",
    [
        {"t_f_h": 0.0},  # t_f = t_0
        {"t_f_h": -5.0},
        {"t_f_h": float("nan")},
        {"snr_obs": float("inf")},
        {"snr_obs": -1.0},
    ],
)
def test_hostile_inputs_are_rejected(change) -> None:
    kw = {
        "event_id": "dewit-2025-event",
        "t_0_h": 0.0,
        "t_f_h": 410.0,
        "snr_obs": 63.5,
        "forecasts": _forecasts(),
    } | change
    with pytest.raises(ValueError, match=r"."):
        evaluate.real_event_report(**kw)


@pytest.mark.req("FR-010-26")
def test_unknown_method_or_cutoff_keys_are_rejected() -> None:
    for bad in (("xgboost", 0.5), ("tcn", 0.6)):
        forecasts = _forecasts() | {bad: {"outcome": "predicted", "t_hat_f_h": 400.0}}
        with pytest.raises(ValueError, match=r"."):
            _report(forecasts)

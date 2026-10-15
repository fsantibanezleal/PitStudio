"""T-010-033: SC-010-01 acceptance statement per learned arm and cut-off, on fixture results (stage `s50_evaluate`).

Requirements: SC-010-01 (and the SC-010-01 half of FR-010-17: "not run (observed SNR unavailable)").
Spec: specs/010-slope/spec.md section 5 (SC-010-01), section 3.2 (FR-010-17), section 3.3 (FR-010-24, FR-010-25);
plan.md row SC-010-01 ("report logic on fixture results that pass and fail by construction"). Runs in the `pipeline/`
environment.

Expected API (module `pitstudio_pipeline.slope.s50`, built on `pitstudio.slope.evaluate`; shared with T-010-042, 052,
095,
096, 097 and 060):
- `evaluate(*, run_id, snr_basis, snr_obs, predictions, alarms=(), t_alarm_h=24.0, seeds, real_event=None, s4b=None,
  expected_strata=None, fixture=False) -> S50Result` with attributes `document` (a DC-010-03 document valid against
  `contracts/ttf-results.schema.json`), `fixture` (bool), `partial` (bool), `missing_strata` (list of stratum names) and
  `pooled_claims_allowed` (bool).
  `predictions`: rows as in `pitstudio.slope.evaluate.score_events` for every method (inverse_velocity, bayesian_ttf,
  tcn,
  patchtst, chronos_bolt_zero_shot, chronos_bolt_fine_tuned), stratum and cut-off 0.5 / 0.8. `seeds` = {"acceptance":
  int,
  "comparison": int}. `snr_basis` "observed" (with `snr_obs`) or "nominal" (`snr_obs` None).
- The document has `events`, `summary`, `alarms`, `alarm_summary`, `acceptance` (one row per learned arm and cut-off
  on the
  stratum snr_obs: 8 rows, verdict "pass" when the median relative error is <= `models.slope_ttf_rel_error_median_max`
  (0.10), else "fail"; the percentile-bootstrap interval of FR-010-24 with B = 10,000 and the acceptance seed; an arm
  without
  predictions gets verdict "not run" with a reason), `comparisons` + `multiplicity` (FR-010-25) and a `real_event` block
  (status "not run" with a reason when none is given). With snr_basis "nominal" every acceptance row is "not run" with a
  reason containing "observed SNR unavailable" and the document has no `snr_obs`.

Oracles: errors planted by construction (every event's forecast is t_f + e x (t_f - t_c) with a chosen e) so that the
median is
known exactly; the threshold read from thresholds.yaml; the schema of DC-010-03 (jsonschema).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

import _slope_lem_ref as lem_ref  # noqa: E402
from pitstudio_pipeline.slope import s50  # noqa: E402

THRESHOLD = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "models"
]["slope_ttf_rel_error_median_max"]
ARMS = ["tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned"]
N = 40


def _rows(method, cutoff, errors, stratum="snr_obs"):
    out = []
    for i, e in enumerate(errors):
        t_f = 200.0 + i
        t_c = cutoff * t_f
        out.append(
            {
                "event_id": f"voight-test-{stratum.replace('_', '-')}-{i:06d}",
                "stratum": stratum,
                "method": method,
                "cutoff": cutoff,
                "t_0_h": 0.0,
                "t_f_h": t_f,
                "outcome": "predicted",
                "t_hat_f_h": t_f + e * (t_f - t_c),
            }
        )
    return out


def _plant(spec: dict, stratum="snr_obs"):
    """spec: {(method, cutoff): list of relative errors}."""
    preds = []
    for (m, c), errs in spec.items():
        preds += _rows(m, c, errs, stratum)
    return preds


def _spec():
    rng = np.random.default_rng(1)
    spec = {}
    for c in (0.5, 0.8):
        spec[("inverse_velocity", c)] = list(0.3 + 0.05 * rng.standard_normal(N))
        spec[("bayesian_ttf", c)] = list(0.25 + 0.05 * rng.standard_normal(N))
    spec[("tcn", 0.5)] = [0.04] * N  # median 0.04: pass
    spec[("tcn", 0.8)] = [0.08] * N  # pass
    spec[("patchtst", 0.5)] = [0.05] * N  # pass
    spec[("patchtst", 0.8)] = [0.12] * N  # fail at the second cut-off
    spec[("chronos_bolt_zero_shot", 0.5)] = [0.30] * N  # fail
    spec[("chronos_bolt_zero_shot", 0.8)] = [0.5] * N  # fail
    return spec  # chronos_bolt_fine_tuned: no predictions at all (did not resolve)


def _evaluate(preds, **kw):
    kw.setdefault("run_id", "20261115T101500Z-c1")
    kw.setdefault("snr_basis", "observed")
    kw.setdefault("snr_obs", 63.5)
    kw.setdefault("seeds", {"acceptance": 4242, "comparison": 4243})
    return s50.evaluate(predictions=preds, **kw)


@pytest.mark.req("SC-010-01")
def test_each_arm_and_cutoff_gets_a_pass_or_fail_from_the_median_relative_error() -> None:
    res = _evaluate(_plant(_spec()))
    rows = {(r["method"], r["cutoff"]): r for r in res.document["acceptance"]}
    assert len(rows) == 8
    expected = {
        ("tcn", 0.5): "pass",
        ("tcn", 0.8): "pass",
        ("patchtst", 0.5): "pass",
        ("patchtst", 0.8): "fail",
        ("chronos_bolt_zero_shot", 0.5): "fail",
        ("chronos_bolt_zero_shot", 0.8): "fail",
    }
    for key, verdict in expected.items():
        r = rows[key]
        assert r["verdict"] == verdict, key
        assert r["criterion"] == "SC-010-01"
        assert r["stratum"] == "snr_obs"
        assert r["threshold"] == THRESHOLD == 0.10
        assert r["n_events"] == N
        assert r["median_rel_error"] == pytest.approx(_spec()[key][0], rel=1e-9)
        assert r["interval"]["lower"] <= r["median_rel_error"] <= r["interval"]["upper"]
        assert r["bootstrap"] == {"resamples": 10_000, "method": "percentile", "level": 0.95, "seed": 4242}


@pytest.mark.req("SC-010-01")
def test_an_arm_without_predictions_is_reported_not_run_with_a_reason() -> None:
    res = _evaluate(_plant(_spec()))
    rows = [r for r in res.document["acceptance"] if r["method"] == "chronos_bolt_fine_tuned"]
    assert {r["cutoff"] for r in rows} == {0.5, 0.8}
    for r in rows:
        assert r["verdict"] == "not run"
        assert r["reason"]
        assert "median_rel_error" not in r
        assert "interval" not in r


@pytest.mark.req("SC-010-01")
def test_the_verdict_is_the_median_not_the_mean() -> None:
    spec = _spec()
    spec[("tcn", 0.5)] = [0.02] * 30 + [5.0] * 10  # mean 1.27, median 0.02: the horizon-cap outliers do not decide
    r = next(r for r in _evaluate(_plant(spec)).document["acceptance"] if (r["method"], r["cutoff"]) == ("tcn", 0.5))
    assert r["verdict"] == "pass"
    assert r["median_rel_error"] == pytest.approx(0.02)


@pytest.mark.req("SC-010-01")
def test_the_whole_document_validates_and_states_eight_comparisons() -> None:
    res = _evaluate(_plant(_spec()))
    assert lem_ref.schema_errors(res.document, "ttf-results") == []
    assert res.document["multiplicity"] == {"comparisons": 8, "family_wise_claim": False}
    assert res.document["snr_basis"] == "observed"
    assert res.document["snr_obs"] == 63.5
    assert res.document["real_event"]["status"] == "not run"
    assert res.document["horizon_cap_steps"] == 1024
    assert len(res.document["comparisons"]) == 6  # the fine-tuned arm has no predictions to pair


@pytest.mark.req("FR-010-17")
def test_without_the_observed_snr_every_sc_010_01_row_is_not_run() -> None:
    spec = {k: v for k, v in _spec().items() if k[0] != "chronos_bolt_fine_tuned"}
    preds = []
    for stratum in ("nominal_10", "nominal_30", "nominal_100"):
        preds += _plant(spec, stratum)
    res = _evaluate(preds, snr_basis="nominal", snr_obs=None)
    doc = res.document
    assert "snr_obs" not in doc
    assert doc["snr_basis"] == "nominal"
    assert len(doc["acceptance"]) == 8
    for r in doc["acceptance"]:
        assert r["verdict"] == "not run"
        assert "observed SNR unavailable" in r["reason"]
        assert "median_rel_error" not in r
    assert {s["stratum"] for s in doc["summary"]} == {
        "nominal_10",
        "nominal_30",
        "nominal_100",
    }  # results still reported
    assert lem_ref.schema_errors(doc, "ttf-results") == []


@pytest.mark.req("SC-010-01")
def test_acceptance_uses_only_the_snr_obs_stratum() -> None:
    spec = _spec()
    preds = _plant(spec)
    preds += _plant({("tcn", 0.5): [9.0] * N}, "half_snr_obs")  # a bad result in another stratum must not leak in
    r = next(r for r in _evaluate(preds).document["acceptance"] if (r["method"], r["cutoff"]) == ("tcn", 0.5))
    assert r["n_events"] == N
    assert r["verdict"] == "pass"

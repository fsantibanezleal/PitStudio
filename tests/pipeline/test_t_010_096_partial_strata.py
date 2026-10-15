"""T-010-096: partial strata are reported with provenance and no pooled claim.

Requirement: FR-010-47 ("While only some of the displacement series or strata that a forecaster comparison names exist
(the
de Wit event not ingested, or a stratum not generated), `s50_evaluate` shall report each existing stratum, list each
missing
one as `not run (absent)`, label the TTF results `partial`, and compute no pooled claim or SC-010 verdict over the
incomplete
set").
Spec: specs/010-slope/spec.md section 3.4 (availability states of ADR-0040); plan.md row FR-010-47 ("2 of 3 strata
present
give `partial`, the third `not run (absent)`, and no pooled verdict"). Runs in the `pipeline/` environment.

Expected API (module `pitstudio_pipeline.slope.s50`, see T-010-033): `evaluate(..., expected_strata=None,
real_event_expected=False)`:
- `expected_strata`: the strata the comparison names (None = those present). `real_event_expected`: True when the
  comparison
  also names the real de Wit event (the `real_event` argument is then None when it is absent).
- the `S50Result` gains `status` ("complete" or "partial"), `label` (the same word), `strata_status` (stratum ->
  "present" or
  "not run (absent)"; the key "real_event" when expected), `missing_strata` (list in the order named; contains
  "real_event"
  when expected and absent), `partial` (bool) and `pooled_claims_allowed` (False for a partial result).
- For a result missing at least one expected stratum: `document["summary"]` and `document["events"]` hold the existing
  strata
  only; every `acceptance` row is "not run" with a reason containing "partial"; `comparisons` is empty; no pooled field.
  A result missing only the real event is also labelled partial and withholds pooled claims (its real_event block is
  "not run").
- A complete result: status "complete", `strata_status` all "present", acceptance and comparisons computed as in
  T-010-033.

Oracle: hand calculation (3 strata named, 2 generated; then 3 of 3).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

import _slope_lem_ref as lem_ref  # noqa: E402
from pitstudio_pipeline.slope import s50  # noqa: E402

NAMED = ["snr_obs", "half_snr_obs", "double_snr_obs"]


def _row(stratum, i, method, e, cutoff):
    t_f = 200.0 + i
    return {
        "event_id": f"voight-test-{stratum.replace('_', '-')}-{i:06d}",
        "stratum": stratum,
        "method": method,
        "cutoff": cutoff,
        "t_0_h": 0.0,
        "t_f_h": t_f,
        "outcome": "predicted",
        "t_hat_f_h": t_f + e * (t_f - cutoff * t_f),
    }


def _preds(strata):
    return [
        _row(stratum, i, method, e, cutoff)
        for stratum in strata
        for i in range(12)
        for method, e in (("inverse_velocity", 0.30), ("tcn", 0.05))
        for cutoff in (0.5, 0.8)
    ]


def _run(present, **kw):
    return s50.evaluate(
        run_id="20261115T101500Z-c1", snr_basis="observed", snr_obs=63.5, predictions=_preds(present),
        seeds={"acceptance": 1, "comparison": 2}, expected_strata=NAMED, **kw,
    )  # fmt: skip


@pytest.mark.req("FR-010-47")
def test_two_of_three_strata_give_partial_and_the_third_is_not_run_absent() -> None:
    res = _run(["snr_obs", "half_snr_obs"])
    assert res.status == res.label == "partial"
    assert res.partial is True
    assert res.missing_strata == ["double_snr_obs"]
    assert res.strata_status == {"snr_obs": "present", "half_snr_obs": "present", "double_snr_obs": "not run (absent)"}
    assert {s["stratum"] for s in res.document["summary"]} == {
        "snr_obs",
        "half_snr_obs",
    }  # each existing stratum is reported
    assert {e["stratum"] for e in res.document["events"]} == {"snr_obs", "half_snr_obs"}
    assert lem_ref.schema_errors(res.document, "ttf-results") == []


@pytest.mark.req("FR-010-47")
def test_a_partial_result_computes_no_pooled_claim_and_no_verdict() -> None:
    res = _run(["snr_obs", "half_snr_obs"])
    assert res.pooled_claims_allowed is False
    assert res.document["comparisons"] == []  # no SC-010-02 verdict
    assert len(res.document["acceptance"]) == 8
    for row in res.document["acceptance"]:
        assert row["verdict"] == "not run"  # no SC-010-01 verdict
        assert "partial" in row["reason"]
        assert "median_rel_error" not in row
        assert "interval" not in row


@pytest.mark.req("FR-010-47")
def test_with_every_named_stratum_present_the_result_is_complete() -> None:
    res = _run(NAMED)
    assert res.status == res.label == "complete"
    assert res.partial is False
    assert res.missing_strata == []
    assert set(res.strata_status.values()) == {"present"}
    assert res.pooled_claims_allowed is True
    rows = {(r["method"], r["cutoff"]): r for r in res.document["acceptance"]}
    assert rows[("tcn", 0.5)]["verdict"] == "pass"  # median error 0.05 <= 0.10, computed
    assert any(c["method"] == "tcn" and c["verdict"] == "better" for c in res.document["comparisons"])


@pytest.mark.req("FR-010-47")
def test_several_missing_strata_are_listed_in_the_named_order() -> None:
    res = _run(["double_snr_obs"])
    assert res.missing_strata == ["snr_obs", "half_snr_obs"]
    assert res.strata_status["snr_obs"] == "not run (absent)"
    assert res.strata_status["double_snr_obs"] == "present"
    assert {s["stratum"] for s in res.document["summary"]} == {"double_snr_obs"}


@pytest.mark.req("FR-010-47")
def test_the_real_event_not_ingested_makes_the_result_partial_too() -> None:
    res = _run(NAMED, real_event_expected=True, real_event=None)
    assert res.partial is True
    assert res.missing_strata == ["real_event"]
    assert res.strata_status["real_event"] == "not run (absent)"
    assert res.document["real_event"]["status"] == "not run"
    assert res.pooled_claims_allowed is False
    assert set(res.strata_status) == {*NAMED, "real_event"}


@pytest.mark.req("FR-010-47")
def test_nothing_present_reports_every_stratum_absent_and_stays_well_formed() -> None:
    res = _run([])
    assert res.missing_strata == NAMED
    assert res.document["summary"] == []
    assert res.document["events"] == []
    assert res.pooled_claims_allowed is False
    assert lem_ref.schema_errors(res.document, "ttf-results") == []

"""T-010-095 (stage half): `s50_evaluate` on a contract-fixture input.

Requirement: FR-010-46.
Spec: specs/010-slope/spec.md section 3.4; plan.md row FR-010-46 ("a fixture series gives a TTF result row `fixture:
true` and
the publish step drops it"). Runs in the `pipeline/` environment. The helper half is in tests/unit/test_t_010_095_*.

Expected API (module `pitstudio_pipeline.slope.s50`, see T-010-033): `evaluate(..., fixture=bool)` runs to completion
on fixture
input and returns an `S50Result` with `fixture` True; the result's numbers are computed (development builds may look
at them);
- `write_result(result, path) -> Path`: writes the DC-010-03 document as JSON; for a fixture the top-level object also
  carries
  `"fixture": true` (the draft schema has additionalProperties false at the top level, so a conforming file cannot carry
  the flag: spec finding recorded in the report, the flag is written next to the document keys regardless);
- `publish(result) -> dict | None`: None for a fixture result (no lead-time or any other claim is published from it),
  the
  document otherwise;
- `lead_time_claims(result) -> list[dict]`: [] for a fixture, one {method, stratum, median_lead_time_h} per
  alarm-summary row with
  a median otherwise.

Oracle: hand calculation (one fixture and one real run over the same predictions; the alarm rows are planted).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from pitstudio_pipeline.slope import s50  # noqa: E402


def _preds():
    out = []
    for i in range(6):
        t_f = 200.0 + i
        for method, e in (("inverse_velocity", 0.30), ("tcn", 0.05)):
            out.append(
                {
                    "event_id": f"voight-test-snr-obs-{i:06d}",
                    "stratum": "snr_obs",
                    "method": method,
                    "cutoff": 0.5,
                    "t_0_h": 0.0,
                    "t_f_h": t_f,
                    "outcome": "predicted",
                    "t_hat_f_h": t_f + e * (t_f - 0.5 * t_f),
                }
            )
    return out


ALARMS = [
    {"event_id": f"voight-test-snr-obs-{i:06d}", "stratum": "snr_obs", "method": "tcn", "alarmed": True,
     "alarm_cutoff": 0.6, "lead_time_h": 80.0 + i}
    for i in range(6)
]  # fmt: skip


def _run(fixture: bool):
    return s50.evaluate(
        run_id="20261115T101500Z-c1", snr_basis="observed", snr_obs=63.5, predictions=_preds(), alarms=ALARMS,
        seeds={"acceptance": 1, "comparison": 2}, fixture=fixture,
    )  # fmt: skip


@pytest.mark.req("FR-010-46")
def test_a_fixture_run_completes_computes_its_numbers_and_is_flagged() -> None:
    res = _run(True)
    assert res.fixture is True
    assert res.document["summary"]  # computed for development builds
    assert {s["method"] for s in res.document["summary"]} == {"inverse_velocity", "tcn"}
    assert any(a["method"] == "tcn" for a in res.document["alarm_summary"])


@pytest.mark.req("FR-010-46")
def test_the_written_result_of_a_fixture_run_carries_fixture_true_and_a_real_one_does_not(tmp_path: Path) -> None:
    fixture_file = s50.write_result(_run(True), tmp_path / "fixture.json")
    real_file = s50.write_result(_run(False), tmp_path / "real.json")
    assert json.loads(Path(fixture_file).read_text(encoding="utf-8"))["fixture"] is True
    assert json.loads(Path(real_file).read_text(encoding="utf-8")).get("fixture", False) is False


@pytest.mark.req("FR-010-46")
def test_publish_drops_a_fixture_result_and_keeps_a_real_one() -> None:
    assert s50.publish(_run(True)) is None
    real = s50.publish(_run(False))
    assert real is not None
    assert real["multiplicity"]["comparisons"] == 8


@pytest.mark.req("FR-010-46")
def test_no_lead_time_claim_comes_out_of_a_fixture_result() -> None:
    assert s50.lead_time_claims(_run(True)) == []
    claims = s50.lead_time_claims(_run(False))
    assert claims == [{"method": "tcn", "stratum": "snr_obs", "median_lead_time_h": pytest.approx(82.5)}]

"""T-010-095: fixture propagation helpers of the forecaster stages and `s50_evaluate` (root part).

Requirement: FR-010-46 ("While a displacement series or slope section (DC-010-01, DC-010-02) is a contract fixture, the
forecaster stages and `s50_evaluate` shall run against it, shall write `fixture: true` on every checkpoint, prediction
file and
TTF result, and shall publish no lead-time claim computed from it").
Spec: specs/010-slope/spec.md section 3.4 (FR-010-46, availability states of ADR-0040); plan.md row FR-010-46 ("a
fixture
series gives a TTF result row `fixture: true` and the publish step drops it"). The stage-level half (`s50.evaluate`,
`s50.write_result`, `s50.publish`) is in tests/pipeline/test_t_010_095_fixture_stages.py (same task).

Expected API (module `pitstudio.slope.fixture`, standard library only; same shape as spec 011's helper):
- `is_fixture(dataset_manifest) -> bool`: True iff `manifest["fixture"] is True`; absent or False -> False; any other
  value
  (a string, a number, None, a list) raises ValueError naming `fixture` (no coercion).
- `section_is_fixture(section) -> bool`: True iff a slope-section document has `source.kind == "fixture"`.
- `stamp(artefact, dataset_manifest) -> dict`: a shallow copy of the artefact with `"fixture": True` for a fixture
  dataset; for a
  real one the key stays absent (or False); the input is never modified.
- `publishable(result) -> dict | None`: None for a result whose `fixture` is True (the publish step drops it), else
  the result.
- `lead_time_claims(alarm_summary, *, dataset_manifest) -> list[dict]`: the lead-time statements that may be
  published, one per
  alarm-summary row with a `median_lead_time_h` ({"method", "stratum", "median_lead_time_h"}); an empty list for a
  fixture.

Oracle: hand calculation from the spec text (flag in, flag out; nothing published from a fixture).
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio.slope.fixture import is_fixture, lead_time_claims, publishable, section_is_fixture, stamp  # noqa: E402

FIXTURE = {"id": "series-fixture", "fixture": True}
REAL = {"id": "series-real", "fixture": False}
ABSENT = {"id": "series-no-flag"}
SUMMARY = [
    {
        "method": "tcn",
        "stratum": "snr_obs",
        "n_events": 500,
        "never_alarmed_fraction": 0.02,
        "median_lead_time_h": 41.5,
    },
    {"method": "inverse_velocity", "stratum": "snr_obs", "n_events": 500, "never_alarmed_fraction": 1.0},
]


@pytest.mark.req("FR-010-46")
@pytest.mark.parametrize(("manifest", "expected"), [(FIXTURE, True), (REAL, False), (ABSENT, False), ({}, False)])
def test_the_fixture_flag_is_read_from_the_dataset_manifest(manifest, expected) -> None:
    assert is_fixture(manifest) is expected


@pytest.mark.req("FR-010-46")
@pytest.mark.parametrize("flag", ["true", "yes", 1, 0, None, [], "fixture"])
def test_a_flag_that_is_not_a_boolean_is_refused_not_coerced(flag) -> None:
    with pytest.raises(ValueError, match="fixture"):
        is_fixture({"fixture": flag})


@pytest.mark.req("FR-010-46")
def test_a_slope_section_of_kind_fixture_is_a_fixture() -> None:
    assert section_is_fixture({"source": {"kind": "fixture"}}) is True
    assert section_is_fixture({"source": {"kind": "dem", "source_id": "bingham"}}) is False
    assert section_is_fixture({"source": {"kind": "editor"}}) is False


@pytest.mark.req("FR-010-46")
def test_stamp_flags_fixture_artefacts_and_leaves_the_others_alone() -> None:
    checkpoint = {"kind": "checkpoint", "model": "tcn", "epoch": 3}
    original = copy.deepcopy(checkpoint)
    flagged = stamp(checkpoint, FIXTURE)
    assert flagged["fixture"] is True
    assert {k: v for k, v in flagged.items() if k != "fixture"} == original
    assert checkpoint == original  # not modified
    for manifest in (REAL, ABSENT):
        assert stamp(checkpoint, manifest).get("fixture", False) is False


@pytest.mark.req("FR-010-46")
def test_a_fixture_result_is_dropped_by_the_publish_step_and_a_real_one_is_kept() -> None:
    assert publishable({"fixture": True, "summary": []}) is None
    result = {"fixture": False, "summary": [1]}
    assert publishable(result) is result
    untouched = {"summary": [1]}
    assert publishable(untouched) is untouched


@pytest.mark.req("FR-010-46")
def test_no_lead_time_claim_is_published_from_a_fixture() -> None:
    assert lead_time_claims(SUMMARY, dataset_manifest=FIXTURE) == []
    claims = lead_time_claims(SUMMARY, dataset_manifest=REAL)
    assert claims == [
        {"method": "tcn", "stratum": "snr_obs", "median_lead_time_h": 41.5}
    ]  # never-alarmed row: no claim
    assert lead_time_claims(SUMMARY, dataset_manifest=ABSENT) == claims

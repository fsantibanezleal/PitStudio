"""T-010-022: nominal-SNR fallback of the synthesizer when SNR_obs is unavailable.

Requirement: FR-010-17 ("If SNR_obs is unavailable (the real series was not ingested), then the synthesizer shall
generate
the strata at the nominal SNR grid {10, 30, 100} labelled 'observed SNR not available - nominal SNR', and SC-010-01
shall
be reported 'not run (observed SNR unavailable)'"; the SC-010-01 half is tested with the acceptance report in
T-010-033).
Spec: specs/010-slope/spec.md section 3.2; DC-010-02 (`stratum` nominal_10 / nominal_30 / nominal_100, `snr_note`).

Expected API (module `pitstudio.slope.events`, as in T-010-020): `default_config(None)` (SNR_obs unavailable),
`make_splits(config)`, `synthesize_event(seed, stratum=..., snr_obs=None, ...)`, `generate_event_set(config, sink)`.
With `snr_obs = None` the test strata are `nominal_10`, `nominal_30`, `nominal_100` (500 seeds each, consecutive
blocks from the
test start in that order); every document of such a stratum has `snr_note == "observed SNR not available - nominal SNR"`
(with the em dash of the schema constant) and `parameters.snr_target` equal to the nominal value; train and validation
events
use the nominal SNR of the middle stratum, 30. Requesting the stratum `snr_obs` without an SNR_obs raises ValueError.

Oracle: hand-stated values of the spec (grid {10, 30, 100}, label text from the schema constant); the documents are
validated against `contracts/displacement-series.schema.json`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_lem_ref as lem_ref
from pitstudio.slope import events

LABEL = "observed SNR not available — nominal SNR"
NOMINAL = {"nominal_10": 10.0, "nominal_30": 30.0, "nominal_100": 100.0}


@pytest.mark.req("FR-010-17")
def test_without_snr_obs_the_test_strata_are_the_nominal_grid() -> None:
    cfg = events.default_config(None)
    s = events.make_splits(cfg)
    assert list(s["test"]) == ["nominal_10", "nominal_30", "nominal_100"]
    assert all(len(v) == 500 for v in s["test"].values())
    assert len(s["train"]) == 20_000
    assert len(s["validation"]) == 1_000
    everything = [*s["train"], *s["validation"], *[x for v in s["test"].values() for x in v]]
    assert len(everything) == len(set(everything))


@pytest.mark.req("FR-010-17")
@pytest.mark.parametrize("stratum", list(NOMINAL))
def test_nominal_strata_carry_the_label_the_nominal_snr_and_validate(stratum) -> None:
    ev = events.synthesize_event(5, stratum=stratum, snr_obs=None, n_samples=300, split="test")
    assert ev["stratum"] == stratum
    assert ev["snr_note"] == LABEL
    assert ev["parameters"]["snr_target"] == NOMINAL[stratum]
    assert lem_ref.schema_errors(ev, "displacement-series") == []


@pytest.mark.req("FR-010-17")
def test_the_whole_generated_set_is_labelled_and_none_is_an_observed_stratum() -> None:
    cfg = events.default_config(None)
    cfg["n_samples"] = 64
    cfg["splits"] = {
        "train": {"start": 0, "count": 4},
        "validation": {"start": 10, "count": 2},
        "test": {"start": 20, "count_per_stratum": 2},
    }
    docs: list[dict] = []
    events.generate_event_set(cfg, docs.append)
    test_docs = [d for d in docs if d["split"] == "test"]
    assert len(test_docs) == 6
    assert {d["stratum"] for d in test_docs} == set(NOMINAL)
    for d in test_docs:
        assert d["snr_note"] == LABEL
        assert d["parameters"]["snr_target"] == NOMINAL[d["stratum"]]
    for d in docs:
        assert d["stratum"] in NOMINAL  # no event is generated at an observed-SNR stratum
        assert d["snr_note"] == LABEL
        assert lem_ref.schema_errors(d, "displacement-series") == []
    assert {d["parameters"]["snr_target"] for d in docs if d["split"] != "test"} == {30.0}


@pytest.mark.req("FR-010-17")
def test_requesting_an_observed_stratum_without_snr_obs_is_rejected_and_vice_versa() -> None:
    with pytest.raises(ValueError, match=r"."):
        events.synthesize_event(1, stratum="snr_obs", snr_obs=None, n_samples=100)
    with pytest.raises(ValueError, match=r"."):
        events.synthesize_event(1, stratum="snr_obs_atmospheric", snr_obs=None, n_samples=100)
    with pytest.raises(ValueError, match=r"."):
        events.synthesize_event(1, stratum="nominal_30", snr_obs=63.5, n_samples=100)  # observed SNR is available


@pytest.mark.req("FR-010-17")
def test_with_snr_obs_present_no_nominal_label_appears() -> None:
    ev = events.synthesize_event(2, stratum="snr_obs", snr_obs=63.5, n_samples=100)
    assert "snr_note" not in ev
    assert ev["stratum"] == "snr_obs"

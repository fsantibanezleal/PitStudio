"""T-010-112: the chart series of the real event of case C1 (FR-010-26, FR-010-27, SC-010-03, FR-020-55).

Spec: specs/020-web-knowledge/contracts/chart-series.schema.json (the contract), specs/010-slope/spec.md section 3.3.
Runs in the `pipeline/` environment.

Expected API:
- `c1_real_eval.bake(document, forecasters, *, seed) -> dict`: per cut-off the observed window, the inverse-velocity fit,
  the Bayesian band and the learned medians, as `c1_curves.bake_event` does for a synthetic event, plus the whole
  displacement record `displacement_t_h` and `displacement_mm`.
- `c1_real_charts.real_event_charts(pair, detail, *, producer, failure_time, blast, archive_table) -> list[dict]`: the
  charts `c1-real-event` (the table of FR-010-26, 12 rows in the fixed order), `c1-real-event-sensitivity` (the same
  table for the sensitivity failure time), `c1-real-event-failure-time` (the failure time, its day uncertainty, the zone
  and its two sources), `c1-real-event-iv` (inverse velocity with the failure time, the blast, the cut-offs and every
  method's predicted time), `c1-real-event-disp` (the displacement record with the same markers) and the archive
  table. Every chart validates against the contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from pitstudio_pipeline.slope import c1_charts, c1_real_charts, c1_real_eval

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "specs/020-web-knowledge/contracts/chart-series.schema.json").read_text(encoding="utf-8"))
VALID = Draft202012Validator(SCHEMA)
LABEL = "single real event — no significance test"
LABEL_ES = "evento real único — sin prueba de significancia"
SOURCES = [
    {"citation": "de Wit and Snieder, Seismica 5(1), doi 10.26443/seismica.v5i1.1902", "locator": "Fig. 4"},
    {"citation": "Taylor and de Wit, SSIM 2023, doi 10.36487/ACG_repo/2335_50", "locator": "text"},
]
FAILURE = {
    "instant": "2014-02-23T00:00:00",
    "uncertainty_h": 24.0,
    "zone": "local time of the archive",
    "sources": SOURCES,
}
BLAST = {"instant": "2014-02-11T10:40:42", "magnitude": 1.3, "basis": "archive event, UNVERIFIED as the blast"}


def _crossing(_x):
    return np.tile(np.linspace(1.0, -1.0, 64, dtype=np.float32), (9, 1))[None]


def _flat(_x):
    return np.full((1, 9, 64), 0.5, dtype=np.float32)


FORECASTERS = {"tcn": _crossing, "patchtst": _flat, "chronos_bolt_fine_tuned": _crossing}


def _doc(t_f_h: float, instant: str) -> dict:
    t = np.arange(0.0, t_f_h - 20.0, 6.0)
    rng = np.random.default_rng(7)
    omega = 400.0 * (t / t_f_h) ** 3 + rng.normal(0.0, 0.3, t.size)
    return {
        "event_id": "dewit-2025-event",
        "stratum": "real",
        "t_0_h": 0.0,
        "t_f_h": t_f_h,
        "t_0_instant": "2014-01-01T14:31:36",
        "t_f_instant": instant,
        "t_f_uncertainty_h": 24.0,
        "zone": "local time of the archive",
        "snr_obs": 12.5,
        "t_h": [float(x) for x in t],
        "los_displacement_mm": [float(x) for x in omega],
    }


@pytest.fixture(scope="module")
def charts() -> list[dict]:
    primary, sens = _doc(1257.5, "2014-02-23T00:00:00"), _doc(1185.5, "2014-02-20T00:00:00")
    pair = c1_real_eval.evaluate_pair(primary, sens, FORECASTERS, seed=11)
    detail = c1_real_eval.bake(primary, FORECASTERS, seed=11)
    table = c1_charts.real_charts(
        {
            "evidence": {"checksum_ok": True, "members": [{"name": "a.csv", "bytes": 3}]},
            "state": {"label": LABEL, "label_es": LABEL_ES},
        },
        producer=c1_charts.producer("m", "l"),
    )[1]
    prod = c1_charts.producer("Prism-median real series, five methods, one record", LABEL)
    return c1_real_charts.real_event_charts(
        pair, detail, producer=prod, failure_time=FAILURE, blast=BLAST, archive_table=table
    )


def _by_id(charts: list[dict]) -> dict[str, dict]:
    return {c["id"]: c for c in charts}


@pytest.mark.req("FR-020-55")
def test_every_chart_validates_against_the_contract_and_the_size_cap(charts) -> None:
    assert [c["id"] for c in charts] == [
        "c1-real-event",
        "c1-real-event-sensitivity",
        "c1-real-event-failure-time",
        "c1-real-event-iv",
        "c1-real-event-disp",
        "c1-real-event-archive",
    ]
    for chart in charts:
        errors = sorted(VALID.iter_errors(chart), key=lambda e: list(e.path))
        assert not errors, (chart["id"], [(list(e.path), e.message[:120]) for e in errors[:3]])
        assert len(json.dumps(chart)) <= 524_288
        assert chart["case"] == "C1" and chart["status"] == "ok"


@pytest.mark.req("FR-010-27")
def test_the_real_event_table_has_the_twelve_rows_in_the_fixed_order_under_the_label(charts) -> None:
    c = _by_id(charts)["c1-real-event"]
    assert c["chart_type"] == "table"
    assert LABEL in c["caption"]["en"] and LABEL_ES in c["caption"]["es"]
    cols = [x["id"] for x in c["table"]["columns"]]
    assert cols[:2] == ["cutoff", "method"]
    rows = c["table"]["rows"]
    assert [(r[0], r[1]) for r in rows] == [
        (cut, name)
        for cut in (0.5, 0.8)
        for name in (
            "Inverse velocity",
            "Bayesian time to failure",
            "TCN",
            "PatchTST",
            "Chronos-Bolt zero-shot",
            "Chronos-Bolt fine-tuned",
        )
    ]
    for need in ("signed-error", "error-lower", "error-upper", "ratio", "ratio-lower", "ratio-upper", "outcome"):
        assert need in cols
    assert not {"rank", "verdict", "highlight"} & set(cols)
    zero_shot = next(r for r in rows if r[1] == "Chronos-Bolt zero-shot")
    assert zero_shot[cols.index("outcome")] == "not run"
    assert zero_shot[cols.index("signed-error")] is None


@pytest.mark.req("FR-010-26")
def test_the_table_values_are_the_evaluated_ones_and_the_interval_brackets_the_error(charts) -> None:
    c = _by_id(charts)["c1-real-event"]
    cols = [x["id"] for x in c["table"]["columns"]]
    n = 0
    for r in c["table"]["rows"]:
        err = r[cols.index("signed-error")]
        if err is None:
            continue
        n += 1
        assert r[cols.index("error-lower")] == pytest.approx(err - 24.0)
        assert r[cols.index("error-upper")] == pytest.approx(err + 24.0)
    assert n >= 6


@pytest.mark.req("FR-010-26")
def test_the_sensitivity_table_names_its_failure_time_and_says_it_is_not_ranked(charts) -> None:
    c = _by_id(charts)["c1-real-event-sensitivity"]
    assert "2014-02-20" in c["title"]["en"] + c["caption"]["en"]
    assert "not ranked" in c["caption"]["en"].lower()
    assert LABEL in c["caption"]["en"]
    assert len(c["table"]["rows"]) == 12


@pytest.mark.req("FR-010-13")
def test_the_failure_time_table_carries_the_instant_the_uncertainty_the_zone_and_both_citations(charts) -> None:
    c = _by_id(charts)["c1-real-event-failure-time"]
    text = json.dumps(c["table"]["rows"])
    assert "2014-02-23T00:00:00" in text and "24" in text
    assert "local time of the archive" in text
    assert "10.26443/seismica.v5i1.1902" in text and "10.36487/ACG_repo/2335_50" in text
    assert "2014-02-20" in text  # the sensitivity value, with its source named


@pytest.mark.req("FR-010-27")
def test_the_curve_chart_marks_the_failure_the_blast_the_cut_offs_and_every_forecast(charts) -> None:
    c = _by_id(charts)["c1-real-event-iv"]
    ids = [m["id"] for m in c["markers"]]
    assert "failure-time" in ids and "blast-2014-02-11" in ids
    assert {"cutoff-05", "cutoff-08"} <= set(ids)
    preds = [i for i in ids if i.startswith("pred-")]
    assert len(preds) == 10  # five methods at two cut-offs (the failed or absent ones are not drawn)
    assert len(ids) == len(set(ids)) <= 24
    assert all(len(m["value_text"]) <= 60 for m in c["markers"])
    blast = next(m for m in c["markers"] if m["id"] == "blast-2014-02-11")
    assert "11 Feb" in blast["value_text"] or "2014-02-11" in blast["value_text"]
    assert any(s["id"] == "observed" for s in c["series"])
    d = _by_id(charts)["c1-real-event-disp"]
    assert {m["id"] for m in d["markers"]} >= {"failure-time", "blast-2014-02-11"}
    assert d["series"][0]["draw"] == "points"


@pytest.mark.req("FR-010-27")
def test_nothing_is_highlighted_in_the_curve_charts_and_the_label_is_in_the_producer(charts) -> None:
    for c in charts:
        assert LABEL in c["producer"]["label"]
        assert not {"highlight", "best", "rank", "verdict"} & set(c)
        for m in c.get("markers", []):
            assert "best" not in json.dumps(m).lower()

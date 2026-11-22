"""T-018-097 [red] FR-018-74: a published summary names the case KPI of a headline value in an explicit `kpi` field.

Oracles: hand-written source files (the numbers below are computed by hand) and the case KPI ids of the case registry
(specs/018-web-cases/contracts/examples/cases.valid.json). The other headline entries carry no `kpi` key.
"""

from __future__ import annotations

import json
from pathlib import Path

from pitstudio.runner import import_summaries

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "specs/018-web-cases/contracts/examples/cases.valid.json").read_text(encoding="utf-8"))[
    "cases"
]


def _c1_source(tmp_path: Path) -> Path:
    events = []
    for method, err in (("inverse_velocity", 100.0), ("tcn", -20.0), ("patchtst", 30.0)):
        events.extend({"method": method, "error_h": err, "event_id": f"e{i}", "cutoff": 0.5} for i in range(4))
    arms = [{"arm": a, "validation_pinball": 0.5} for a in ("tcn", "patchtst")]
    docs = {
        "training-manifest.json": {"arms": arms, "budget": {"total_gpu_hours": 0.4, "budget_gpu_hours": 2.0}},
        "ttf-results.json": {"events": events},
        "export-report.json": {"arms": {"tcn": {"lane": "LIVE"}, "patchtst": {"lane": "LIVE"}}},
    }
    for name, doc in docs.items():
        (tmp_path / name).write_text(json.dumps(doc), encoding="utf-8")
    return tmp_path


def test_c1_summary_names_the_forecast_error_kpi_on_the_best_method_headline(tmp_path: Path) -> None:
    summary = json.loads(import_summaries.build("c1-summary", _c1_source(tmp_path), "20261013T171809Z-c1-demo"))
    named = [h for h in summary["headline"] if "kpi" in h]
    assert len(named) == 1
    assert named[0]["kpi"] == "forecast_error"
    assert named[0]["name"] == "Mean absolute forecast error, TCN"
    assert named[0]["value"] == 20.0
    assert named[0]["unit"] == "h"


def test_the_kpi_named_by_a_headline_is_a_kpi_of_the_case_with_the_same_unit(tmp_path: Path) -> None:
    summary = json.loads(import_summaries.build("c1-summary", _c1_source(tmp_path), "20261013T171809Z-c1-demo"))
    by_id = {k["id"]: k for k in CASES["C1"]["kpis"]}
    for h in summary["headline"]:
        if "kpi" in h:
            assert h["kpi"] in by_id
            assert by_id[h["kpi"]]["unit"] == h["unit"]


def test_a_headline_that_measures_no_kpi_carries_no_kpi_key(tmp_path: Path) -> None:
    summary = json.loads(import_summaries.build("c1-summary", _c1_source(tmp_path), "20261013T171809Z-c1-demo"))
    unnamed = [h["name"] for h in summary["headline"] if "kpi" not in h]
    assert unnamed == ["Mean absolute forecast error, inverse velocity", "Training GPU-hours, three arms"]

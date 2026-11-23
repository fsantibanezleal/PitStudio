"""T-010-106: the C1 run folders, their summaries and their import specs (C1-U1 to C1-U4 of the 2026-11-23 plan).

Requirements: FR-010-26, FR-010-27, FR-020-55, FR-018-74.
Runs in the `pipeline/` environment.

Expected API (module `pitstudio_pipeline.slope.c1_assemble`):
- `RUNS`: the four run slugs c1-error-results, c1-event-curves, c1-real-event, c1-wall-sections.
- `summary_of(slug, data) -> dict`: the "Published results" summary of a run (`title`, `label`, `methods`, `verdict`,
  `headline`, `rows`); a headline entry carries `kpi` only for the case KPIs fos (unit 1) and pof (unit %), never for
  the real event; the real-event run has verdict "partial" and no forecast number.
- `import_spec(slug, charts, extra_outputs, *, inputs) -> dict`: the import spec of a run: one chart-series output per
  chart (publish true, budget class studio-showcase, unique slug ids), raw data outputs with publish false, the summary
  output with publish true, `producer_paths` naming the stage code and the recipe.
"""

from __future__ import annotations

import re

import pytest

from pitstudio_pipeline.slope import c1_assemble


def _walls():
    def one(k, fos, pof):
        return {
            "section": {"section_id": f"usgs-3dep-bingham-s{k}"},
            "fos": [
                {"method": "bishop", "status": "ok", "fos": fos},
                {"method": "spencer", "status": "ok", "fos": fos - 0.01},
            ],
            "pof": {"samples": 2000, "candidates": 64, "failures": int(pof * 2000), "pof": pof,
                    "wilson_95": {"lower": 0.0, "upper": 0.002}},
        }

    return [one(1, 2.75, 0.0), one(2, 1.9, 0.0005), one(3, 2.2, 0.0)]


@pytest.mark.req("FR-018-74")
def test_the_wall_summary_feeds_the_fos_and_pof_kpis_from_the_lowest_section_with_the_kpi_units() -> None:
    s = c1_assemble.summary_of("c1-wall-sections", {"walls": _walls()})
    kpis = {h["kpi"]: h for h in s["headline"] if "kpi" in h}
    assert set(kpis) == {"fos", "pof"}
    assert kpis["fos"]["value"] == pytest.approx(1.9) and kpis["fos"]["unit"] == "1"
    assert kpis["pof"]["value"] == pytest.approx(0.05) and kpis["pof"]["unit"] == "%"  # 0.0005 as a percentage
    assert "section 2" in kpis["fos"]["note"]
    assert s["methods"] == ["M13"] and s["verdict"] == "ok"
    assert "UNVERIFIED" in s["label"] and "not design software" in s["label"]
    assert len(s["rows"]) == 3


@pytest.mark.req("FR-010-27")
def test_the_real_event_summary_is_partial_has_the_label_and_no_forecast_number() -> None:
    s = c1_assemble.summary_of(
        "c1-real-event",
        {"real": {"evidence": {"members": [{"name": "a.csv", "bytes": 3}, {"name": "b.csv", "bytes": 4}], "checksum_ok": True}, "state": {"status": "not run", "reason": "x"}}},
    )
    assert s["verdict"] == "partial"
    assert "single real event" in s["label"] and "not run" in s["title"].lower()
    assert all("kpi" not in h for h in s["headline"])
    assert not any("error" in h["name"].lower() for h in s["headline"])


@pytest.mark.req("FR-010-25")
def test_the_error_summary_counts_the_better_comparisons_and_makes_no_kpi_claim() -> None:
    comparisons = [
        {"stratum": "nominal_30", "method": "tcn", "cutoff": 0.5, "mean_difference": 0.9, "interval": {"lower": 0.6, "upper": 1.2}, "verdict": "better"},
        {"stratum": "nominal_30", "method": "patchtst", "cutoff": 0.5, "mean_difference": -0.1, "interval": {"lower": -0.4, "upper": 0.2}, "verdict": "no significant difference"},
    ]
    data = {"errors": {"comparisons": comparisons, "statement": {"comparisons": 2, "family_wise_claim": False}, "median_intervals": [], "summary": []}}
    s = c1_assemble.summary_of("c1-error-results", data)
    better = next(h for h in s["headline"] if "better" in h["name"].lower())
    assert better["value"] == 1 and "2 comparisons" in better["note"] and "family-wise" in better["note"]
    assert all("kpi" not in h for h in s["headline"])
    assert len(s["rows"]) == 2 and s["rows"][0]["verdict"] == "better"


@pytest.mark.req("FR-020-55")
def test_the_import_spec_lists_every_chart_once_with_unique_ids_and_the_producer_paths() -> None:
    charts = [{"id": "c1-a", "serves": ["FR-010-23"]}, {"id": "c1-b", "serves": ["FR-010-25"]}]
    spec = c1_assemble.import_spec(
        "c1-error-results", charts, [("error-results.json", "error-results.json")], inputs=[{"id": "src", "sha256": "0" * 64, "kind": "source"}]
    )
    outs = [o for st in spec["stages"] for o in st["outputs"]]
    names = [o["name"] for o in outs]
    assert len(names) == len(set(names))
    cs = [o for o in outs if o["kind"] == "chart-series"]
    assert [o["name"] for o in cs] == ["charts/c1-a.json", "charts/c1-b.json"]
    assert all(o["publish"] is True and o["budget_class"] == "studio-showcase" and o["media_type"] == "application/json" for o in cs)
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", o["id"]) for o in cs) and len({o["id"] for o in cs}) == 2
    raw = next(o for o in outs if o["name"] == "error-results.json")
    assert raw["publish"] is False
    summary = next(o for o in outs if o["name"] == "results-summary.json")
    assert summary["publish"] is True
    assert spec["case"] == "C1" and spec["recipe"] == "cases/c1.yaml" and spec["slug"] == "c1-error-results"
    assert spec["producer_paths"] == ["pipeline/src/pitstudio_pipeline/slope", "studio/recipes/cases/c1.yaml"]
    assert "CPU" in spec["label"] or "synthetic" in spec["label"]


@pytest.mark.req("FR-020-55")
def test_an_unknown_run_slug_is_refused() -> None:
    with pytest.raises(ValueError):
        c1_assemble.summary_of("c1-other", {})
    assert c1_assemble.RUNS == ("c1-error-results", "c1-event-curves", "c1-real-event", "c1-wall-sections")

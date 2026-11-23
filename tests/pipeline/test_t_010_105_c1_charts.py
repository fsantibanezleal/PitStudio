"""T-010-105: the C1 charts as chart-series documents of the contract DC-020-05 (C1-U1 to C1-U4 of the 2026-11-23 plan).

Requirements: FR-010-23, FR-010-24, FR-010-25, FR-010-26, FR-010-27, FR-010-28, SC-010-02, SC-010-03, FR-020-55.
Spec: specs/020-web-knowledge/contracts/chart-series.schema.json (the contract), specs/010-slope/spec.md section 3.3.
Runs in the `pipeline/` environment.

Expected API (module `pitstudio_pipeline.slope.c1_charts`; every builder returns validated chart-series dicts):
- `error_charts(results, *, producer) -> list[dict]`: median error with its interval per cut-off (bar with error bars),
  paired mean difference with its interval per cut-off (bar with error bars and the zero line), the empirical CDFs per
  stratum and cut-off, the error table and the SC-010-01 chart in the state "not-run".
- `event_charts(baked, *, producer) -> list[dict]`: per event the inverse-velocity chart (truth, observed points, the
  fits, the Bayesian band, the learned forecasts, the failure markers) and the displacement chart.
- `wall_charts(walls, oracles, *, producer) -> list[dict]`: per section the section chart (ground, face, critical
  circle) and the PoF chart (histogram of the minimum factor with the FoS = 1 marker), then one table.
- `real_charts(real, *, producer) -> list[dict]`: the real-event chart in the state "not-run" with the label and the
  archive table.
- `producer(method, label)`: the producer object (tool, method, version, label).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from pitstudio.slope import events
from pitstudio_pipeline.slope import c1_charts, c1_curves, c1_errors, c1_real

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "specs/020-web-knowledge/contracts/chart-series.schema.json").read_text(encoding="utf-8"))
VALID = Draft202012Validator(SCHEMA)
PRODUCER = c1_charts.producer(
    "Paired percentile bootstrap, B = 10,000", "calibrated synthetic, not validated against real data"
)


def _check(chart):
    errors = sorted(VALID.iter_errors(chart), key=lambda e: list(e.path))
    assert not errors, [(list(e.path), e.message[:120]) for e in errors[:3]]
    assert len(json.dumps(chart)) <= 524_288
    return chart


def _rows():
    rows = []
    for stratum in ("nominal_10", "nominal_30"):
        for i in range(30):
            for method in ("inverse_velocity", "bayesian_ttf", *c1_errors.ev.LEARNED):
                for cutoff in (0.5, 0.8):
                    err = 0.6 + 0.01 * i - (0.0 if method in ("inverse_velocity", "bayesian_ttf") else 0.1 + 0.001 * i)
                    rows.append(
                        {
                            "event_id": f"voight-test-{stratum.replace('_', '-')}-{2_000_000 + i:06d}",
                            "stratum": stratum,
                            "method": method,
                            "cutoff": cutoff,
                            "outcome": "predicted",
                            "rel_error": err,
                            "error_h": err * 10.0,
                            "scored_at_cap": False,
                        }
                    )
    return rows


def _results():
    rows = _rows()
    from pitstudio.slope import evaluate as ev

    return {
        "source_run_id": "20261012T000000Z-c1-gpu",
        "snr_basis": "nominal",
        "summary": ev.summarise(rows),
        "median_intervals": c1_errors.median_intervals(rows, seed=3, resamples=200),
        "comparisons": c1_errors.paired_intervals(rows, seed=4, resamples=200),
        "distributions": c1_errors.error_distributions(rows),
        "statement": c1_errors.comparison_statement(c1_errors.paired_intervals(rows, seed=4, resamples=50)),
        "acceptance": [],
    }


@pytest.mark.req("FR-020-55")
def test_the_producer_carries_tool_method_version_and_label() -> None:
    assert set(PRODUCER) == {"tool", "method", "version", "label"}
    assert PRODUCER["tool"] == "pitstudio"
    assert PRODUCER["version"]


@pytest.mark.req("FR-010-25")
def test_error_charts_validate_and_the_paired_chart_draws_the_stored_intervals_and_the_zero_line() -> None:
    res = _results()
    charts = c1_charts.error_charts(res, producer=PRODUCER)
    for c in charts:
        _check(c)
    by_id = {c["id"]: c for c in charts}
    paired = by_id["c1-paired-difference-cutoff-05"]
    assert paired["chart_type"] == "bar"
    assert [m["orientation"] for m in paired["markers"]] == ["horizontal"]
    assert paired["markers"][0]["y"] == 0.0
    assert [c["id"] for c in paired["categories"]] == [
        "tcn",
        "patchtst",
        "chronos-bolt-zero-shot",
        "chronos-bolt-fine-tuned",
    ]
    for s in paired["series"]:
        stratum = s["id"].replace("-", "_")
        for i, arm in enumerate(["tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned"]):
            c = next(
                x for x in res["comparisons"] if x["stratum"] == stratum and x["method"] == arm and x["cutoff"] == 0.5
            )
            assert s["y"][i] == pytest.approx(c["mean_difference"])
            assert s["lo"][i] == pytest.approx(c["interval"]["lower"])
            assert s["hi"][i] == pytest.approx(c["interval"]["upper"])
    assert "no family-wise" in paired["caption"]["en"].lower() or "family-wise" in paired["caption"]["en"].lower()


@pytest.mark.req("FR-010-24")
def test_the_median_chart_has_a_band_per_stratum_and_every_method_as_a_category() -> None:
    charts = {c["id"]: c for c in c1_charts.error_charts(_results(), producer=PRODUCER)}
    c = charts["c1-median-error-cutoff-08"]
    assert len(c["categories"]) == 6
    assert {s["id"] for s in c["series"]} == {"nominal-10", "nominal-30"}
    for s in c["series"]:
        assert len(s["y"]) == len(s["lo"]) == len(s["hi"]) == 6
        assert all(lo <= y <= hi for lo, y, hi in zip(s["lo"], s["y"], s["hi"], strict=True))


@pytest.mark.req("FR-010-23")
def test_the_ecdf_charts_are_one_per_stratum_and_cutoff_with_a_step_series_per_method() -> None:
    charts = {c["id"]: c for c in c1_charts.error_charts(_results(), producer=PRODUCER)}
    e = charts["c1-error-ecdf-nominal-30-cutoff-05"]
    assert e["chart_type"] == "ecdf"
    assert len(e["series"]) == 6
    assert all(s["draw"] == "step" for s in e["series"])
    assert all(s["y"][-1] <= 1.0 and s["n"] == 30 for s in e["series"])
    assert "c1-error-ecdf-nominal-10-cutoff-08" in charts


@pytest.mark.req("FR-010-23")
def test_the_error_table_has_one_row_per_method_stratum_and_cutoff() -> None:
    charts = {c["id"]: c for c in c1_charts.error_charts(_results(), producer=PRODUCER)}
    t = charts["c1-error-table"]
    assert t["chart_type"] == "table"
    assert len(t["table"]["rows"]) == 6 * 2 * 2
    cols = [c["id"] for c in t["table"]["columns"]]
    row = t["table"]["rows"][0]
    assert row[cols.index("n-events")] == 30


@pytest.mark.req("SC-010-01")
def test_the_acceptance_chart_is_not_run_with_a_reason_and_no_data() -> None:
    charts = {c["id"]: c for c in c1_charts.error_charts(_results(), producer=PRODUCER)}
    a = charts["c1-acceptance-sc-010-01"]
    assert a["status"] == "not-run"
    assert "observed snr unavailable" in a["not_run_reason"]["en"].lower()
    assert not any(k in a for k in ("series", "table", "categories"))


def _baked():
    cfg = events.default_config(None)
    cfg["n_samples"] = 2000
    doc = events.synthesize_event(
        2_000_003, stratum="nominal_30", snr_obs=None, n_samples=2000, split="test", config=cfg
    )

    def fake(_ctx):
        steps = np.linspace(0.9, -0.2, 64)
        return np.stack([steps + 0.05 * (q - 4) for q in range(9)])[None].astype(np.float32)

    return c1_curves.bake_event(doc, {"tcn": fake, "patchtst": fake, "chronos_bolt_fine_tuned": fake}, seed=1)


@pytest.mark.req("FR-010-21")
def test_the_event_charts_validate_and_carry_the_markers_of_the_true_and_the_predicted_failure() -> None:
    baked = _baked()
    iv, disp = c1_charts.event_charts(baked, producer=PRODUCER)
    _check(iv)
    _check(disp)
    assert iv["chart_type"] == "line"
    assert len(iv["series"]) <= 12
    labels = {m["id"] for m in iv["markers"]}
    assert "true-failure" in labels
    assert "cutoff-05" in labels
    assert "cutoff-08" in labels
    true = next(m for m in iv["markers"] if m["id"] == "true-failure")
    assert true["x"] == pytest.approx(baked["t_f_h"])
    predicted = [m for m in iv["markers"] if m["id"].startswith("pred-")]
    assert len(predicted) == 5 * 2  # inverse velocity, Bayesian, three learned arms, at two cut-offs
    tcn = next(m for m in predicted if m["id"] == "pred-tcn-05")
    assert tcn["x"] == pytest.approx(baked["cutoffs"][0]["methods"]["tcn"]["t_hat_f_h"])
    bayes = [s for s in iv["series"] if s["id"].startswith("bayes")]
    assert bayes
    assert all(len(s["lo"]) == len(s["hi"]) == len(s["y"]) for s in bayes)
    assert all(np.all(np.asarray(s["lo"]) <= np.asarray(s["hi"]) + 1e-9) for s in bayes)
    assert disp["chart_type"] == "line"
    assert disp["series"][0]["draw"] == "points"


@pytest.mark.req("FR-010-29")
def test_an_arm_without_a_forecast_is_left_out_of_the_chart_with_its_reason_in_the_caption() -> None:
    baked = _baked()
    baked["cutoffs"][0]["methods"]["tcn"] = {"status": "no forecast", "reason": "no positive velocity at all"}
    iv, _ = c1_charts.event_charts(baked, producer=PRODUCER)
    _check(iv)
    assert not any(m["id"] == "pred-tcn-05" for m in iv["markers"])
    assert "no positive velocity" in iv["caption"]["en"]


def _wall(k=1, pof=0.0):
    ground = [[float(x), 1800.0 - 0.3 * x] for x in range(0, 900, 30)]
    return {
        "section": {
            "section_id": f"usgs-3dep-bingham-s{k}",
            "ground": ground,
            "crest_x_m": 150.0,
            "toe_x_m": 480.0,
            "source": {"site_label": "Bingham Canyon west wall, 3DEP 2018 (provisional)"},
        },
        "fos": [
            {
                "method": "bishop",
                "status": "ok",
                "fos": 1.87,
                "slices": 50,
                "circles_evaluated": 12792,
                "rejected_circles": 100,
                "critical_circle": {
                    "centre_x_m": 400.0,
                    "centre_z_m": 1900.0,
                    "radius_m": 380.0,
                    "entry_x_m": 100.0,
                    "exit_x_m": 470.0,
                },
                "iterations": 17,
            },
            {
                "method": "spencer",
                "status": "ok",
                "fos": 1.86,
                "slices": 50,
                "circles_evaluated": 12792,
                "rejected_circles": 100,
                "critical_circle": {
                    "centre_x_m": 400.0,
                    "centre_z_m": 1900.0,
                    "radius_m": 380.0,
                    "entry_x_m": 100.0,
                    "exit_x_m": 470.0,
                },
                "iterations": 13,
                "theta_deg": -30.7,
            },
        ],
        "pof": {
            "samples": 2000,
            "candidates": 64,
            "failures": int(pof * 2000),
            "pof": pof,
            "wilson_95": {"lower": 0.0, "upper": 0.0019, "z": 1.96},
            "seed": 20261007,
        },
        "pof_min_factor_histogram": {
            "edges": [1.5 + 0.01 * i for i in range(41)],
            "centres": [1.505 + 0.01 * i for i in range(40)],
            "counts": [1] * 40,
        },
        "pof_min_factor_summary": {"min": 1.5, "median": 1.7, "max": 1.9},
    }


def _oracle(k=1):
    return {
        "section_id": f"usgs-3dep-bingham-s{k}",
        "planar_reduction": {"height_m": 100.0, "angle_deg": 38.0, "run_m": 120.0},
        "fixed_max_rel_diff": 0.003,
        "fixed_pass": True,
        "search_pass": True,
        "search": {"mine": 1.5, "pyslope_own_search": 1.52, "rtol": 0.02},
        "pyslope_version": "1.4.0",
    }


@pytest.mark.req("FR-010-01")
def test_the_wall_charts_validate_and_show_the_ground_the_face_the_critical_circle_and_fos_one() -> None:
    charts = c1_charts.wall_charts([_wall(1), _wall(2)], [_oracle(1), _oracle(2)], producer=PRODUCER)
    for c in charts:
        _check(c)
    by_id = {c["id"]: c for c in charts}
    sec = by_id["c1-wall-s1-section"]
    assert sec["chart_type"] == "section"
    assert {p["role"] for p in sec["section"]["polylines"]} >= {"ground"}
    (circle,) = sec["section"]["circles"]
    assert circle["role"] == "critical"
    assert circle["r"] == pytest.approx(380.0)
    pof = by_id["c1-wall-s1-pof"]
    one = next(m for m in pof["markers"] if m["id"] == "fos-one")
    assert one["orientation"] == "vertical"
    assert one["x"] == 1.0
    assert "0 of 2,000" in pof["caption"]["en"] or "0 of 2000" in pof["caption"]["en"]
    table = by_id["c1-wall-table"]
    assert len(table["table"]["rows"]) == 2


@pytest.mark.req("SC-010-05")
def test_the_wall_table_states_the_oracle_check_and_the_unverified_inputs() -> None:
    charts = {c["id"]: c for c in c1_charts.wall_charts([_wall(1)], [_oracle(1)], producer=PRODUCER)}
    t = charts["c1-wall-table"]
    cols = [c["id"] for c in t["table"]["columns"]]
    row = t["table"]["rows"][0]
    assert row[cols.index("oracle-fixed-pass")] == "pass"
    assert row[cols.index("oracle-search-pass")] == "pass"
    assert "UNVERIFIED" in t["producer"]["label"]
    assert "design" in t["caption"]["en"].lower()


@pytest.mark.req("SC-010-03")
def test_the_real_event_chart_is_not_run_with_the_label_and_the_archive_table_lists_the_members() -> None:
    evidence = {
        "checksum_ok": True,
        "bytes": 8943265,
        "members": [
            {"name": "radar-deformation-data/slopeMovement.dat", "bytes": 12795137, "header": "%Prism,day,month"},
            {"name": "weather-data/x.csv", "bytes": 14012, "header": "Product code,Station"},
        ],
        "ingest": {"accepted": False, "reason": "archive has no supported member (a series CSV or a map stack)"},
        "prism_export": {
            "member": "radar-deformation-data/slopeMovement.dat",
            "prisms": 160,
            "rows": 82401,
            "first": "01-Jan-14 16:16:55",
            "last": "06-Aug-14 05:40:38",
            "units_evidence": {"easting_diff_unit": "mm", "max_abs_residual": 5e-8},
        },
        "failure_time_in_archive": False,
    }
    real = {"evidence": evidence, "state": c1_real.real_event_state({**evidence, "checksum_ok": True})}
    charts = c1_charts.real_charts(real, producer=PRODUCER)
    for c in charts:
        _check(c)
    by_id = {c["id"]: c for c in charts}
    r = by_id["c1-real-event"]
    assert r["status"] == "not-run"
    assert "single real event" in r["caption"]["en"]
    assert "evento real único" in r["caption"]["es"]
    assert "failure time" in r["not_run_reason"]["en"]
    t = by_id["c1-real-event-archive"]
    assert len(t["table"]["rows"]) == 2

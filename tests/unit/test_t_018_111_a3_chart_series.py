"""T-018-111: the A3 chart series derived from the files of the published A3 runs (FR-018-86, DC-020-05).

The repose chart is built from the results.json of the DEM repose job (one angle per seed, the Student t interval of the
mean); the GNS chart from the evaluation of the graph network simulator (the mean per-grain position error against the
rollout step, per geometry). Oracles: values computed by hand from the small input files this test writes (the median of
three numbers, the min and max, the counts), the chart-series contract and the importer's own semantic check.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitstudio.runner import chart_series, import_summaries

PRODUCER = {"tool": "warp", "version": "1.17.0"}


def write(tmp: Path, name: str, doc: dict) -> None:
    (tmp / name).write_text(json.dumps(doc), encoding="utf-8")


def repose_inputs(tmp: Path) -> None:
    write(
        tmp,
        "results.json",
        {
            "protocol": "funnel",
            "n_particles": 20000,
            "seeds": [10, 11, 12],
            "repose_angles_deg": [27.0, 26.0, 28.0],
            "complete": True,
            "summary": {
                "n_seeds": 3,
                "mean_deg": 27.0,
                "std_deg": 1.0,
                "ci95_half_width_deg": 2.5,
                "ci95_deg": [24.5, 29.5],
                "t_975": 4.303,
            },
        },
    )


def gns_inputs(tmp: Path) -> None:
    def geo(i: str, growth: list[float], at: int | None) -> dict:
        return {
            "geometry_id": i,
            "family": "column-collapse",
            "position_error_growth": growth,
            "diverged": at is not None,
            "diverged_at_step": at,
        }

    write(
        tmp,
        "evaluation.published.json",
        {
            "n_geometries": 3,
            "limits": {"repose_abs_deg_max": 1.5},
            "geometries": [
                geo("g1", [0.0, 0.1, 0.4, 0.9], 5),
                geo("g2", [0.0, 0.2, 0.6, 1.0], 6),
                geo("g3", [0.0, 0.3], 3),
            ],
        },
    )


@pytest.mark.req("FR-018-86")
def test_the_repose_chart_has_one_bar_per_seed_and_the_mean_with_its_interval(tmp_path: Path) -> None:
    repose_inputs(tmp_path)
    doc = json.loads(import_summaries.build("a3-repose-chart", tmp_path, "r", {"producer": PRODUCER}))
    assert chart_series.check(json.dumps(doc).encode(), "A3", "repose") == []
    assert doc["chart_type"] == "bar" and doc["case"] == "A3" and doc["y_axis"]["unit"] == "deg"
    (series,) = doc["series"]
    assert [c["id"] for c in doc["categories"]] == ["seed-10", "seed-11", "seed-12", "mean"]
    assert series["y"] == [27.0, 26.0, 28.0, 27.0]
    assert series["lo"] == [None, None, None, 24.5] and series["hi"] == [None, None, None, 29.5]
    assert doc["producer"]["tool"] == "warp" and doc["producer"]["version"] == "1.17.0"
    assert doc["producer"]["label"] == "calibrated synthetic, not validated against real data"


@pytest.mark.req("FR-018-86")
def test_an_incomplete_repose_run_is_published_as_not_run_with_its_reason(tmp_path: Path) -> None:
    repose_inputs(tmp_path)
    doc = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    doc["complete"] = False
    del doc["summary"]
    write(tmp_path, "results.json", doc)
    out = json.loads(import_summaries.build("a3-repose-chart", tmp_path, "r", {"producer": PRODUCER}))
    assert out["status"] == "not-run" and out["not_run_reason"]["en"] and out["not_run_reason"]["es"]
    assert "series" not in out


@pytest.mark.req("FR-018-86")
def test_the_gns_chart_is_the_error_against_the_step_with_the_band_of_the_geometries(tmp_path: Path) -> None:
    gns_inputs(tmp_path)
    doc = json.loads(
        import_summaries.build("a3-gns-chart", tmp_path, "r", {"producer": {"tool": "pitstudio", "version": "0.1.0"}})
    )
    assert chart_series.check(json.dumps(doc).encode(), "A3", "gns") == []
    assert doc["chart_type"] == "line" and doc["x_axis"]["unit"] == "1" and doc["y_axis"]["unit"] == "m"
    (series,) = doc["series"]
    assert series["x"] == [0, 1, 2, 3]
    # step 0: values 0, 0, 0; step 1: 0.1, 0.2, 0.3; step 2: 0.4, 0.6 (g3 stopped); step 3: 0.9, 1.0
    assert series["y"] == pytest.approx([0.0, 0.2, 0.5, 0.95])
    assert series["lo"] == [0.0, 0.1, 0.4, 0.9] and series["hi"] == [0.0, 0.3, 0.6, 1.0]
    marks = {m["id"]: m for m in doc["markers"]}
    assert marks["first-divergence"]["x"] == 3 and marks["last-divergence"]["x"] == 6
    assert "3 of 3" in doc["caption"]["en"] and "3 de 3" in doc["caption"]["es"]


@pytest.mark.req("FR-018-86")
def test_the_gns_chart_without_any_curve_is_not_run(tmp_path: Path) -> None:
    write(tmp_path, "evaluation.published.json", {"geometries": [{"geometry_id": "g1", "position_error_growth": []}]})
    out = json.loads(import_summaries.build("a3-gns-chart", tmp_path, "r", {"producer": PRODUCER}))
    assert out["status"] == "not-run" and "series" not in out


@pytest.mark.req("FR-018-86")
def test_a_builder_without_its_producer_is_refused(tmp_path: Path) -> None:
    repose_inputs(tmp_path)
    with pytest.raises(import_summaries.Missing, match="producer"):
        import_summaries.build("a3-repose-chart", tmp_path, "r", {})

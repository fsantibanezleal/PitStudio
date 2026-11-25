"""C2 breach run (spec 005 FR-005-30, FR-005-31; spec 020 DC-020-05): outputs of `pitstudio_studio.physics.c2_breach`.

Oracles: the chart-series JSON Schema of the contract and the semantic rules of `studio import-run`
(`pitstudio.runner.chart_series`); a synthetic terrain with a known constant slope, a known pit outline and a known
hydrograph volume, so the volume balance, the units and the labels can be checked without the real DEM.
The run is on the Warp CPU device with 20 m cells (400 cells) and finishes in seconds.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "src"))

import jsonschema  # noqa: E402
import rasterio  # noqa: E402
from pitstudio_studio.physics import c2_breach  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

from pitstudio.runner import chart_series  # noqa: E402

SCHEMA = json.loads((ROOT / "specs/020-web-knowledge/contracts/chart-series.schema.json").read_text(encoding="utf-8"))
X0, Y0, SIZE = 500000.0, 4000000.0, 400


def write_terrain(root: Path) -> None:
    (root / "raw").mkdir(parents=True)
    x = np.arange(SIZE)[None, :].repeat(SIZE, axis=0)
    z = (1500.0 - 0.05 * x).astype("float32")  # falls 5 cm per metre towards +x
    with rasterio.open(
        root / "raw" / "dem.tif",
        "w",
        driver="GTiff",
        height=SIZE,
        width=SIZE,
        count=1,
        dtype="float32",
        crs="EPSG:26912",
        transform=from_origin(X0, Y0 + SIZE, 1.0, 1.0),
        nodata=-999999.0,
    ) as dst:
        dst.write(z, 1)
    outline = {
        "type": "Polygon",
        "coordinates": [[[250.0, 100.0], [380.0, 100.0], [380.0, 300.0], [250.0, 300.0], [250.0, 100.0]]],
    }
    (root / "pit.geojson").write_text(json.dumps(outline), encoding="utf-8")


def recipe() -> dict:
    scenario = {
        "volume_m3": 20000.0,
        "peak_discharge_m3_s": 20.0,
        "tau_y_pa": 50.0,
        "mu_b_pa_s": 0.5,
        "rho_kg_m3": 1800.0,
        "source": "synthetic test scenario",
    }
    return {
        "dem": "raw/dem.tif",
        "pit_outline": "pit.geojson",
        "pit_outline_origin_m": [X0, Y0],
        "min_coverage": 0.95,
        "window": {"x_min": X0, "x_max": X0 + SIZE, "y_min": Y0, "y_max": Y0 + SIZE},
        "run": {
            "cell_m": 20,
            "t_end_s": 2100,
            "snapshot_s": 300,
            "max_dt_s": 2.0,
            "headline_scenario": "a",
            "breach": {"x_m": X0 + 70.0, "y_m": Y0 + 190.0, "width_cells": 1},
        },
        "scenarios": [
            {"id": "a", "label": "Test A", "label_es": "Prueba A", **scenario},
            {
                "id": "b",
                "label": "Test B",
                "label_es": "Prueba B",
                **{**scenario, "tau_y_pa": 5.0, "volume_m3": 30000.0, "peak_discharge_m3_s": 30.0},
            },
        ],
        "limits": ["synthetic"],
    }


@pytest.fixture(scope="module")
def outputs(tmp_path_factory):
    root = tmp_path_factory.mktemp("c2")
    write_terrain(root)
    out = root / "out"
    summary = c2_breach.run_c2(out, recipe(), root, "cpu", None)
    return root, out, summary


def charts(out: Path) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / "charts").glob("*.json"))}


def test_every_chart_validates_against_the_contract_and_the_import_rules(outputs):
    _, out, _ = outputs
    found = charts(out)
    assert len(found) == 12  # 4 maps, 4 line charts, 2 bars, 2 tables
    for name, doc in found.items():
        jsonschema.validate(doc, SCHEMA)
        assert chart_series.semantic_problems(doc, f"{name}.json") == []
        assert (out / "charts" / f"{name}.json").stat().st_size <= chart_series.MAX_BYTES


def test_every_map_has_units_a_colour_scale_and_an_extent(outputs):
    _, out, _ = outputs
    maps = {n: d for n, d in charts(out).items() if d["chart_type"] == "raster"}
    assert set(maps) == {"c2-depth-map-a", "c2-depth-map-b", "c2-arrival-map-a", "c2-arrival-map-b"}
    for doc in maps.values():
        colour = doc["raster"]["colour"]
        assert colour["unit"] in {"m", "min"}
        assert colour["colormap"] in {"viridis", "cividis", "inferno", "magma"}
        assert doc["x_axis"]["unit"] == doc["y_axis"]["unit"] == "m"
        ext = doc["raster"]["extent"]
        assert (ext["x1"] - ext["x0"], ext["y1"] - ext["y0"]) == (SIZE, SIZE)
        assert doc["raster"]["nx"] * doc["raster"]["ny"] == len(doc["raster"]["values"])
    depth = np.array([v for v in maps["c2-depth-map-a"]["raster"]["values"] if v is not None])
    assert depth.size > 0
    assert depth.min() >= 0.05  # cells below the threshold are blank, not zero (values are rounded to 3 decimals)
    arrival = np.array([v for v in maps["c2-arrival-map-a"]["raster"]["values"] if v is not None])
    assert arrival.min() >= 0.0
    assert arrival.max() <= 2100 / 60.0


def test_every_chart_carries_producer_method_version_and_label(outputs):
    _, out, _ = outputs
    for doc in charts(out).values():
        p = doc["producer"]
        assert p["tool"] == "warp"
        assert p["method"].startswith("depth-averaged shallow water")
        assert p["version"].startswith("warp-")
        assert "not validated against real data" in p["label"]


def test_the_kpi_links_name_registry_kpis(outputs):
    _, out, _ = outputs
    kpis = {n: d.get("kpi") for n, d in charts(out).items() if d.get("kpi")}
    assert set(kpis.values()) == {"arrival_time", "max_depth", "inundated_area"}
    assert kpis["c2-arrival-map-a"] == "arrival_time"
    assert "c2-arrival-map-b" not in kpis  # only the headline scenario links a KPI


def test_the_volume_balance_and_the_released_volume_are_exact(outputs):
    _, _, summary = outputs
    for sc, released in zip(summary["scenarios"], (20000.0, 30000.0), strict=True):
        b = sc["balance"]
        assert b["injected_m3"] == pytest.approx(released, rel=1e-6)
        assert abs(b["residual"]) <= 1e-12
        assert b["clipped_m3"] <= 1e-9
        assert b["domain_m3"] + b["boundary_outflow_m3"] == pytest.approx(b["injected_m3"], rel=1e-9)


def test_every_scenario_publishes_its_inputs_and_source(outputs):
    _, _, summary = outputs
    for sc in summary["scenarios"]:
        assert sc["source"]
        assert {"volume_m3", "peak_discharge_m3_s", "tau_y_pa", "mu_b_pa_s", "rho_kg_m3"} <= set(sc)
    assert "hypothetical" not in json.dumps(summary["terrain"])  # the recipe wording is the recipe's, not invented here
    assert summary["label"].startswith("synthetic breach scenario")


def test_a_lower_yield_stress_runs_further_and_the_pit_receives_flow(outputs):
    _, _, summary = outputs
    a, b = summary["scenarios"]
    assert b["kpi"]["run_out_m"] >= a["kpi"]["run_out_m"]
    assert b["kpi"]["inundated_area_km2"] >= a["kpi"]["inundated_area_km2"]
    assert b["kpi"]["pit_volume_end_m3"] > 0.0
    assert b["kpi"]["arrival_time_pit_min"] is not None


def test_no_output_holds_an_absolute_path_or_machine_name(outputs):
    root, out, _ = outputs
    needles = (str(root), str(root).replace("\\", "/"), "C:\\", "C:/Users", "/home/")
    for f in [*out.rglob("*.json")]:
        text = f.read_text(encoding="utf-8")
        assert not any(n in text for n in needles), f.name


def test_the_outputs_are_deterministic_for_the_same_inputs(outputs, tmp_path):
    root, out, _ = outputs
    again = tmp_path / "again"
    c2_breach.run_c2(again, recipe(), root, "cpu", None)
    for f in sorted((out / "charts").glob("*.json")):
        assert f.read_bytes() == (again / "charts" / f.name).read_bytes(), f.name


def test_a_missing_benchmark_report_gives_a_not_run_verification_table(outputs):
    _, out, _ = outputs
    doc = charts(out)["c2-solver-verification"]
    assert doc["status"] == "not-run"
    assert doc["not_run_reason"]["en"]


def test_a_benchmark_report_becomes_the_verification_table(outputs, tmp_path):
    root, _, _ = outputs
    report = {
        "device": "cpu",
        "rows": [
            {
                "id": "x",
                "name": "Ritter L1",
                "value": 0.0128,
                "unit": "1",
                "tolerance": 0.05,
                "status": "pass",
                "known_limit": False,
            },
            {
                "id": "y",
                "name": "Front",
                "value": -0.2,
                "unit": "1",
                "tolerance": 0.05,
                "status": "fail",
                "known_limit": True,
            },
        ],
        "n_pass": 1,
        "n_fail": 0,
        "n_known_limit": 1,
        "wall_s": 1.0,
        "version": "swe-benchmarks-1.0",
    }
    c2_breach.run_c2(tmp_path / "o", recipe(), root, "cpu", report)
    doc = json.loads((tmp_path / "o" / "charts" / "c2-solver-verification.json").read_text(encoding="utf-8"))
    jsonschema.validate(doc, SCHEMA)
    assert [r[3] for r in doc["table"]["rows"]] == ["pass", "fail (known limit)"]


def test_a_flow_that_never_exceeds_the_threshold_gives_a_not_run_arrival_chart_and_valid_files(tmp_path):
    root = tmp_path / "thin"
    write_terrain(root)
    thin = recipe()
    thin["scenarios"] = [{**thin["scenarios"][0], "id": "t", "volume_m3": 200.0, "peak_discharge_m3_s": 0.1}]
    thin["run"] = {**thin["run"], "headline_scenario": "t", "h_thr_m": 5.0}
    c2_breach.run_c2(root / "out", thin, root, "cpu", None)
    found = charts(root / "out")
    assert found["c2-arrival-distance"]["status"] == "not-run"
    assert "threshold" in found["c2-arrival-distance"]["not_run_reason"]["en"]
    for name, doc in found.items():
        jsonschema.validate(doc, SCHEMA)
        assert chart_series.semantic_problems(doc, f"{name}.json") == [], name

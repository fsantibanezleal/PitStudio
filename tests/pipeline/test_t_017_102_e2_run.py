"""T-017-102: the E2 run writes the real-volume document, the bar chart, the difference map and the table
(pipeline test of the studio environment).

Requirements: FR-017-30, FR-017-31, FR-017-33, FR-017-34, FR-017-51.

Spec: specs/017-planning-survey/spec.md section 3.3; plan.md data flow of E2 (`st10_terrain` DEMs, `dem_prepare`,
differencing, DC-017-04); the chart-series contract (DC-020-05).

Oracles (none of them is the code under test), on GeoTIFFs written by the test with `rasterio`:
- a 200 x 200 m flat 2018 surface at 100 m with 1 m cells; the 2023 surface lowers a 100 x 60 m rectangle by 10 m
  (V_cut = 100 x 60 x 10 = 60,000 m^3 exactly) and raises a 20 x 20 m square by 5 m (V_fill = 400 x 5 = 2,000 m^3);
  V_net = -58,000 m^3, with every rectangle edge on a cell edge so no cell is split;
- the uncertainty bounds by hand: N = 40,000 valid cells, A_c = 1, sigma = 0.1 m per epoch:
  sqrt(0.02) x sqrt(40,000) = 28.2843 (uncorrelated), sqrt(0.02) x 40,000 = 5,656.85 (fully correlated);
- the footprint triangle clipped to the query box: its overlap ratio by hand;
- a datum mismatch without a declared transform is "not run" with its reason and no number.

Expected public API (module `pitstudio_studio.survey.real_run`, studio environment):
    run_e2(out_dir: Path, *, path_2018: Path, path_2023: Path, recipe: Mapping) -> dict
        recipe: {"id", "dem_metadata", "vertical_transform"?, "licence", "areas": [{"id", "label", "footprint"?
        (CRS coordinates, x then y)}], "map_area": id of the area whose bounding box the map shows}; the query box is
        the extent of the 2023 grid. Writes `survey-volume.json` (DC-017-04), `charts/e2-*.json` (chart-series, case
        E2) and `e2-run.json`; returns the content of `e2-run.json`.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
SCHEMA = json.loads((ROOT / "contracts" / "chart-series.schema.json").read_text("utf-8"))
VOLUME_SCHEMA = json.loads((ROOT / "contracts" / "survey-volume.schema.json").read_text("utf-8"))

from pitstudio_studio.survey.real_run import run_e2  # noqa: E402


def _write(path: Path, z: np.ndarray, *, tags: dict | None = None) -> Path:
    import rasterio
    from rasterio.transform import from_origin

    profile = {
        "driver": "GTiff", "height": z.shape[0], "width": z.shape[1], "count": 1, "dtype": "float32",
        "crs": "EPSG:26912", "transform": from_origin(400_000.0, 4_490_200.0, 1.0, 1.0), "nodata": -999999.0,
    }  # fmt: skip
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(z.astype(np.float32), 1)
        if tags:
            dst.update_tags(**tags)
    return path


def _pair(tmp: Path, *, datum_2018: str = "NAVD88") -> tuple[Path, Path]:
    z18 = np.full((200, 200), 100.0)
    z23 = z18.copy()
    z23[20:80, 30:130] -= 10.0  # rows 20..79 (60), columns 30..129 (100)
    z23[150:170, 150:170] += 5.0  # 20 x 20
    return (
        _write(tmp / "2018.tif", z18, tags={"VERTICAL_DATUM": datum_2018}),
        _write(tmp / "2023.tif", z23, tags={"VERTICAL_DATUM": "NAVD88"}),
    )


RECIPE = {
    "id": "bingham-2018-2023",
    "licence": {
        "spdx": "LicenseRef-USGov-PD",
        "licence_class": "public-domain",
        "attribution": "U.S. Geological Survey, 3D Elevation Program (public domain)",
    },
    "dem_metadata": {
        "2018": {"rmse_z_m": 0.1, "project": "UT Test 2018", "source": "test"},
        "2023": {"rmse_z_m": 0.1, "project": "UT Test 2023", "source": "test"},
    },
    "areas": [
        {"id": "query-box", "label": "whole query box"},
        {
            "id": "footprint",
            "label": "test footprint",
            "footprint": [[400_000.0, 4_490_000.0], [400_200.0, 4_490_000.0], [400_000.0, 4_490_200.0]],
        },
    ],
    "map_area": "query-box",
}


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2")
    p18, p23 = _pair(tmp)
    out = tmp / "out"
    return out, run_e2(out, path_2018=p18, path_2023=p23, recipe=RECIPE)


def _volumes(out: Path) -> dict:
    doc = json.loads((out / "survey-volume.json").read_text("utf-8"))
    assert list(Draft202012Validator(VOLUME_SCHEMA).iter_errors(doc)) == []
    return {v["id"]: v for v in doc["volumes"]}


@pytest.mark.req("FR-017-30")
def test_cut_fill_and_net_over_the_whole_query_box_equal_the_hand_volumes(run) -> None:
    out, _ = run
    v = _volumes(out)["bingham-2018-2023-query-box"]
    assert v["v_cut_m3"] == pytest.approx(60_000.0, rel=1e-12)
    assert v["v_fill_m3"] == pytest.approx(2_000.0, rel=1e-12)
    assert v["v_net_m3"] == pytest.approx(-58_000.0, rel=1e-12)
    assert v["cells"]["valid"] == 40_000


@pytest.mark.req("FR-017-33")
def test_both_uncertainty_bounds_follow_the_spec_formulas(run) -> None:
    out, _ = run
    v = _volumes(out)["bingham-2018-2023-query-box"]
    s = math.sqrt(0.02)
    assert v["uncertainty_m3"]["uncorrelated"] == pytest.approx(s * math.sqrt(40_000), rel=1e-12)
    assert v["uncertainty_m3"]["correlated"] == pytest.approx(s * 40_000, rel=1e-12)


@pytest.mark.req("FR-017-34")
def test_a_footprint_clips_the_area_of_interest_and_reports_its_overlap_ratio(run) -> None:
    out, _ = run
    v = _volumes(out)["bingham-2018-2023-footprint"]
    assert v["polygon"]["overlap_ratio"] == pytest.approx(1.0, rel=1e-12)  # the triangle lies inside the query box
    # cells whose centre lies below the diagonal x + y < 400200 + 4490000 - ... counted independently
    inside = 0
    cut = 0.0
    for r in range(200):
        for c in range(200):
            x, y = 400_000.5 + c, 4_490_199.5 - r
            if (x - 400_000.0) + (y - 4_490_000.0) < 200.0:
                inside += 1
                cut += 10.0 if (20 <= r < 80 and 30 <= c < 130) else 0.0
    assert v["cells"]["valid"] == inside
    assert v["v_cut_m3"] == pytest.approx(cut, rel=1e-12)


@pytest.mark.req("FR-017-34")
def test_a_volume_without_a_footprint_says_provisional_and_every_volume_carries_the_label(run) -> None:
    out, summary = run
    vols = _volumes(out)
    assert "provisional" in vols["bingham-2018-2023-query-box"]["polygon"]["source"]
    assert all(v["label"] == "measurement, not validation" and v["scope"] == "real" for v in vols.values())
    assert summary["status"] == "ok"


@pytest.mark.req("FR-017-31")
def test_the_inputs_digests_and_the_grid_are_recorded(run) -> None:
    out, summary = run
    v = _volumes(out)["bingham-2018-2023-query-box"]
    assert len(v["surfaces"]["before"]["sha256"]) == 64
    assert len(v["surfaces"]["after"]["sha256"]) == 64
    assert v["surfaces"]["before"]["project"] == "UT Test 2018"
    assert v["grid"]["cell_m"] == 1.0
    assert v["grid"]["shape"] == [200, 200]
    assert summary["prepare"]["resampling"] == "none"


@pytest.mark.req("FR-017-34")
def test_the_charts_validate_and_the_map_and_bars_repeat_the_document_numbers(run) -> None:
    out, _ = run
    charts = {f.stem: json.loads(f.read_text("utf-8")) for f in sorted((out / "charts").glob("e2-*.json"))}
    assert set(charts) == {"e2-volume-bars", "e2-difference-map", "e2-volume-table"}
    for name, chart in charts.items():
        assert list(Draft202012Validator(SCHEMA).iter_errors(chart)) == [], name
        assert chart["case"] == "E2"
        assert chart["status"] == "ok"
    v = _volumes(out)["bingham-2018-2023-query-box"]
    bars = charts["e2-volume-bars"]
    assert [c["id"] for c in bars["categories"]] == ["cut", "fill", "net"]
    query = next(s for s in bars["series"] if s["id"] == "query-box")
    assert query["y"] == pytest.approx([v["v_cut_m3"], v["v_fill_m3"], v["v_net_m3"]], rel=1e-12)
    assert query["hi"][0] - query["y"][0] == pytest.approx(v["uncertainty_m3"]["correlated"], rel=1e-9)


@pytest.mark.req("FR-017-30")
def test_the_difference_map_conserves_the_net_volume_to_the_cell_mean_rounding(run) -> None:
    out, _ = run
    raster = json.loads((out / "charts" / "e2-difference-map.json").read_text("utf-8"))["raster"]
    nx, ny, ext = raster["nx"], raster["ny"], raster["extent"]
    assert nx <= 200
    assert ny <= 200
    cell_area = (ext["x1"] - ext["x0"]) / nx * (ext["y1"] - ext["y0"]) / ny
    total = sum(v for v in raster["values"] if v is not None) * cell_area
    assert total == pytest.approx(-58_000.0, rel=1e-6)  # the grid is 200 m over 100 cells: exact block means
    assert min(v for v in raster["values"] if v is not None) == pytest.approx(-10.0)
    assert max(raster["values"]) == pytest.approx(5.0)


@pytest.mark.req("FR-017-31")
def test_a_vertical_datum_mismatch_gives_not_run_with_its_reason_and_no_volume(tmp_path: Path) -> None:
    p18, p23 = _pair(tmp_path, datum_2018="NGVD29")
    summary = run_e2(tmp_path / "out", path_2018=p18, path_2023=p23, recipe=RECIPE)
    assert summary["status"] == "not_run"
    assert "vertical datums differ" in summary["label"]
    doc = json.loads((tmp_path / "out" / "survey-volume.json").read_text("utf-8"))
    assert [v["status"] for v in doc["volumes"]] == ["not_run"]
    assert "v_cut_m3" not in doc["volumes"][0]
    assert doc["volumes"][0]["reason"]
    assert list(Draft202012Validator(VOLUME_SCHEMA).iter_errors(doc)) == []
    bars = json.loads((tmp_path / "out" / "charts" / "e2-volume-bars.json").read_text("utf-8"))
    assert bars["status"] == "not-run"
    assert "series" not in bars
    assert list(Draft202012Validator(SCHEMA).iter_errors(bars)) == []


@pytest.mark.req("FR-017-34")
def test_an_area_without_a_valid_cell_in_both_epochs_is_not_run_and_the_other_areas_still_run(tmp_path: Path) -> None:
    z18 = np.full((200, 200), 100.0)
    z23 = z18 - 1.0
    z23[
        :, :100
    ] = -999999.0  # the 2023 epoch has no data in the west half (as the real 2023 tile has none over the pit)
    p18 = _write(tmp_path / "2018.tif", z18, tags={"VERTICAL_DATUM": "NAVD88"})
    p23 = _write(tmp_path / "2023.tif", z23, tags={"VERTICAL_DATUM": "NAVD88"})
    west = [[400_000.0, 4_490_000.0], [400_090.0, 4_490_000.0], [400_090.0, 4_490_200.0], [400_000.0, 4_490_200.0]]
    recipe = {
        **RECIPE,
        "areas": [{"id": "west", "label": "west", "footprint": west}, {"id": "all", "label": "all"}],
        "map_area": "west",
    }
    summary = run_e2(tmp_path / "out", path_2018=p18, path_2023=p23, recipe=recipe)
    vols = {v["id"]: v for v in json.loads((tmp_path / "out" / "survey-volume.json").read_text("utf-8"))["volumes"]}
    assert vols["bingham-2018-2023-west"]["status"] == "not_run"
    assert "no valid cell" in vols["bingham-2018-2023-west"]["reason"]
    assert vols["bingham-2018-2023-all"]["status"] == "ok"
    assert vols["bingham-2018-2023-all"]["v_cut_m3"] == pytest.approx(100 * 200 * 1.0, rel=1e-12)
    assert vols["bingham-2018-2023-all"]["cells"]["nodata_fraction"] == pytest.approx(0.5)
    assert summary["status"] == "ok"
    assert (
        list(Draft202012Validator(VOLUME_SCHEMA).iter_errors({"schema_version": "1.0", "volumes": list(vols.values())}))
        == []
    )
    for f in (tmp_path / "out" / "charts").glob("e2-*.json"):
        assert list(Draft202012Validator(SCHEMA).iter_errors(json.loads(f.read_text("utf-8")))) == [], f.name

# ruff: noqa: E501, PT018
"""T-017-103: the coarse E2 pair, SRTM GL1 (February 2000) against a 1 m lidar DEM aggregated to a 30 m grid (pipeline
test of the studio environment).

Requirements: FR-017-30, FR-017-31, FR-017-32, FR-017-33, FR-017-34, FR-017-51.

Spec: specs/017-planning-survey/spec.md FR-017-30..34 (differencing, grid preparation, datum conversion, bounds, the real
result); the older DEM is a 1 arc-second geographic grid in EGM96 heights, the newer one a 1 m UTM grid in NAVD88 heights.

Oracles (none of them is the code under test), on GeoTIFFs written by the test with `rasterio` and `pyproj`:
- the 2000 surface is the plane z = 1500 + 0.05 (x - x0) + 0.02 (y - y0) in UTM metres, sampled at the centres of a
  1 arc-second geographic grid; bilinear interpolation reproduces a plane exactly, so after resampling the older DEM is the
  plane at every 30 m cell centre;
- the 2018 surface is the same plane plus a vertical offset `shift` everywhere, minus a 300 x 300 m pit of depth 40 m whose
  edges lie on 30 m cell edges; block means of 30 x 30 one-metre cells are then exact, so V_cut inside the pit footprint is
  300 x 300 x 40 = 3,600,000 m^3 and, outside the pit, the surface difference is the shift only;
- the datum conversion is a declared constant function (the test passes `offset_fn`), added to the older DEM, so on stable
  ground the difference is `shift - offset` with a standard deviation of zero (float32 storage: tolerance 1e-3 m);
- the uncertainty bounds from the spec formulas with sigma_0 and sigma_1 written in the test.

Expected public API (module `pitstudio_studio.survey.coarse_pair`, studio environment):
    run_coarse(out_dir: Path, *, srtm: Path, dem: Path, recipe: Mapping, scratch: Path, offset_fn=None) -> dict
        recipe: run_e2 keys (`id`, `licence`, `areas`, `map_area`, `epochs`, `period`, `run_label`, `surface_paths`) plus
        `dem_metadata` ({"before": {...}, "after": {...}}), `grid` {"cell_m", "min_coverage"}, `stable_ground`
        {"min_distance_m", "area": id of the area whose footprint it keeps away from}, `srtm_rmse_nominal_m`.
        offset_fn(x, y, crs) -> float array: the height of NAVD88 minus EGM96 at the cell centres (default: PROJ grids).
        Writes the coarse DEM and the datum grid to `scratch`, then the `run_e2` outputs to `out_dir`; the sigma of the older
        DEM in the bounds is the larger of the nominal figure and the standard deviation measured on stable ground; returns
        the `e2-run.json` content with `stable_ground` {mean_m, sd_m, median_m, n_cells, min_distance_m} and `sigma_srtm_m`.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.survey.coarse_pair import run_coarse  # noqa: E402

X0, Y0, N = 400_020.0, 4_484_010.0, 3000  # 2018 grid: 3 km square, origin on a 30 m multiple
SHIFT = 0.30


def _write(path: Path, z: np.ndarray, transform, crs: str, nodata: float) -> Path:
    import rasterio

    profile = {"driver": "GTiff", "height": z.shape[0], "width": z.shape[1], "count": 1, "dtype": "float32",
               "crs": crs, "transform": transform, "nodata": nodata}  # fmt: skip
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(z.astype(np.float32), 1)
    return path


def _inputs(tmp: Path) -> tuple[Path, Path]:
    from pyproj import Transformer
    from rasterio.transform import from_origin

    def plane(x, y):
        return 1500.0 + 0.05 * (x - X0) + 0.02 * (y - Y0)

    # the 2018 lidar DEM: plane + shift, minus a pit at x 1,500..1,800 m, y 1,500..1,800 m of the grid (30 m cell edges)
    xs = X0 + (np.arange(N) + 0.5)
    ys = Y0 + N - (np.arange(N) + 0.5)
    z18 = plane(xs[None, :], ys[:, None]) + SHIFT
    z18[N - 1800 : N - 1500, 1500:1800] -= 40.0
    dem = _write(tmp / "dem.tif", z18, from_origin(X0, Y0 + N, 1.0, 1.0), "EPSG:26912", -999999.0)
    # the 2000 SRTM-like grid: 1 arc-second cells, centres on integer arc-seconds, covering the area with a margin
    to_utm = Transformer.from_crs(4326, 26912, always_xy=True)
    lon0, lat0 = -112.1760, 40.4850
    nx = ny = 200  # 200 arc-seconds is about 4.7 km by 6.2 km: a margin around the 3 km square
    lon = lon0 + np.arange(nx) / 3600.0
    lat = lat0 + (ny - 1 - np.arange(ny)) / 3600.0
    lo, la = np.meshgrid(lon, lat)
    xu, yu = to_utm.transform(lo, la)
    zs = plane(xu, yu)
    half = 0.5 / 3600.0
    srtm = _write(
        tmp / "srtm.tif", zs, from_origin(lon0 - half, lat[0] + half, 1 / 3600.0, 1 / 3600.0), "EPSG:4326", -32768.0
    )
    return srtm, dem


def _recipe() -> dict:
    return {
        "id": "coarse-test",
        "licence": {
            "spdx": "LicenseRef-USGov-PD",
            "licence_class": "public-domain",
            "attribution": "NASA and USGS, public domain",
        },
        "epochs": ["2000", "2018"],
        "period": "2000 to 2018",
        "run_label": "coarse 30 m, 2000 to 2018",
        "surface_paths": ["data/raw/srtm-gl1-test/srtm.tif", "data/raw/lidar-test/dem.tif"],
        "dem_metadata": {
            "before": {"project": "SRTM GL1 test", "vertical_datum": "EGM96", "geoid": "EGM96", "source": "test"},
            "after": {
                "project": "lidar test",
                "vertical_datum": "NAVD88",
                "geoid": "GEOID18",
                "rmse_z_m": 0.1,
                "source": "test",
            },
        },
        "grid": {"cell_m": 30.0, "min_coverage": 0.95},
        "stable_ground": {"min_distance_m": 600.0, "area": "pit"},
        "srtm_rmse_nominal_m": 0.5,
        "areas": [
            {
                "id": "pit",
                "label": "test pit",
                "footprint": [
                    [X0 + 1440, Y0 + 1440],
                    [X0 + 1860, Y0 + 1440],
                    [X0 + 1860, Y0 + 1860],
                    [X0 + 1440, Y0 + 1860],
                ],
            }
        ],
        "map_area": "pit",
    }


OFFSET = -0.424


def _offset(x, y, crs):  # the declared conversion of the test: NAVD88 minus EGM96, constant
    return np.full(np.shape(x), OFFSET)


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("coarse")
    srtm, dem = _inputs(tmp)
    out = tmp / "out"
    return out, run_coarse(out, srtm=srtm, dem=dem, recipe=_recipe(), scratch=tmp / "scratch", offset_fn=_offset)


def _volume(out: Path) -> dict:
    return json.loads((out / "survey-volume.json").read_text("utf-8"))["volumes"][0]


@pytest.mark.req("FR-017-30")
def test_the_pit_cut_is_the_hand_volume_over_the_footprint_net_of_the_shift(run) -> None:
    out, _ = run
    v = _volume(out)
    # footprint 420 x 420 m (cell edges) holds the 300 x 300 x 40 m pit; every other footprint cell differs by shift - offset (fill)
    ground = 420 * 420 - 300 * 300
    assert v["v_cut_m3"] == pytest.approx(300 * 300 * (40.0 - (SHIFT - OFFSET)), rel=1e-3)
    assert v["v_fill_m3"] == pytest.approx(ground * (SHIFT - OFFSET), rel=1e-3)


@pytest.mark.req("FR-017-32")
def test_the_stable_ground_check_reports_the_residual_offset_with_its_mean_and_sd(run) -> None:
    _, summary = run
    s = summary["stable_ground"]
    assert s["mean_m"] == pytest.approx(SHIFT - OFFSET, abs=1e-3)
    assert s["sd_m"] == pytest.approx(0.0, abs=1e-3)
    assert s["n_cells"] > 1000
    assert s["min_distance_m"] == 600.0


@pytest.mark.req("FR-017-33")
def test_the_bounds_combine_the_larger_of_the_nominal_and_the_measured_sigma_with_the_lidar_rmse(run) -> None:
    out, summary = run
    v = _volume(out)
    assert summary["sigma_srtm_m"] == pytest.approx(0.5)  # the nominal figure is larger than the measured sd (0)
    s = math.hypot(0.5, 0.1)
    n = v["cells"]["valid"]
    assert v["uncertainty_m3"]["uncorrelated"] == pytest.approx(900.0 * math.sqrt(n) * s, rel=1e-9)
    assert v["uncertainty_m3"]["correlated"] == pytest.approx(900.0 * n * s, rel=1e-9)


@pytest.mark.req("FR-017-34")
def test_the_volume_carries_the_epochs_the_datum_conversion_the_grid_and_the_label(run) -> None:
    out, summary = run
    v = _volume(out)
    assert v["label"] == "measurement, not validation"
    assert (v["surfaces"]["before"]["epoch"], v["surfaces"]["after"]["epoch"]) == ("2000", "2018")
    assert v["surfaces"]["before"]["crs"] == "EPSG:4326"
    assert v["surfaces"]["after"]["crs"] == "EPSG:26912"
    assert v["surfaces"]["before"]["vertical_datum"] == "EGM96"
    assert v["vertical_transform"]["kind"] == "grid"
    assert v["vertical_transform"]["source"]
    assert v["grid"]["cell_m"] == 30.0
    assert summary["status"] == "ok"
    chart = json.loads((out / "charts" / "e2-volume-bars.json").read_text("utf-8"))
    assert "2000 to 2018" in chart["title"]["en"]
    assert "coarse 30 m, 2000 to 2018" in chart["producer"]["label"]


@pytest.mark.req("FR-017-51")
def test_every_written_file_has_lf_line_ends(run) -> None:
    out, _ = run
    files = [out / "survey-volume.json", out / "e2-run.json", *sorted((out / "charts").glob("e2-*.json"))]
    assert all(b"\r" not in f.read_bytes() for f in files)

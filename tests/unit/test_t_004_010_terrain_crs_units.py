# ruff: noqa: E501
"""T-004-010: CRS, vertical datum and unit record of DEM and LAZ inputs; foot conversion; feet-vs-metres invariance.

Requirements: FR-004-01, FR-004-03, P-004-04 (spec specs/004-scene-pipeline/spec.md; plan.md test strategy).

Oracle: fixture files are written here with a known CRS, so the expected record is the one written into the file (hand
written, plan.md "FR-004-01"); the foot factors are the definitions 1200/3937 m (US survey foot) and 0.3048 m
(international foot); P-004-04 is a metamorphic relation between a metre run and a feet run of the same terrain.

Expected API of the implementation (studio environment, package `pitstudio_studio.scene.terrain`):
- `terrain.io.read_dem(path) -> DemTile` with attributes `array` (float64, source units, row 0 = north edge),
  `x_min`, `y_max`, `cell_x`, `cell_y` (source horizontal units), `nodata` (float | None), `crs` (a DC-004-03
  `crs_record` dict: `horizontal` / `vertical` = `{"epsg": int | None, "wkt": str (when epsg is None)}`,
  `horizontal_unit` / `vertical_unit` = `{"name": "metre" | "us-survey-foot" | "international-foot", "factor_to_m": float}`).
  The record is read from the file's own metadata, never from a default.
- `terrain.io.read_laz(path) -> LazTile` with `x`, `y`, `z` (float64), `classification` (uint8), `crs` (same record).
- `terrain.build_terrain_grid(spec, inputs) -> TerrainGrid` where `spec` is a DC-004-01 SceneSpec dict and `inputs` maps a
  terrain source id to a list of file paths; `TerrainGrid` has `elevation` (float32 [rows, cols], row 0 = north, site
  frame, metres), `valid_mask`, `fill_mask` (bool), `cell_size_m`, `x_min_m`, `y_max_m`, `rows`, `cols`, `crs`, `counts`.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import terrain  # noqa: E402

SRC = "usgs-3dep-bingham"


def _dem(
    tmp: Path,
    name: str,
    wkt: str | None,
    *,
    unit_scale: float = 1.0,
    cell: float = 1.0,
    n: int = 4,
    z: np.ndarray | None = None,
) -> Path:
    """DEM of n x n cells whose SW corner sits at site (10, 16) m; `unit_scale` re-encodes metres as feet."""
    arr = (kit.Z0 + (np.arange(n * n, dtype=np.float64).reshape(n, n) if z is None else z)) / unit_scale
    return kit.write_dem(
        tmp / name,
        arr,
        x_min=(kit.E0 + 10.0) / unit_scale,
        y_max=(kit.N0 + 16.0 + n * cell) / unit_scale,
        cell=cell / unit_scale,
        wkt=wkt,
    )


@pytest.mark.req("FR-004-01")
def test_dem_record_holds_the_epsg_codes_and_units_written_in_the_file(tmp_path: Path) -> None:
    dem = terrain.io.read_dem(_dem(tmp_path, "m.tif", kit.crs_wkt("utm12-m")))
    assert dem.crs["horizontal"]["epsg"] == 26912
    assert dem.crs["vertical"]["epsg"] == 5703
    assert dem.crs["horizontal_unit"] == {"name": "metre", "factor_to_m": 1.0}
    assert dem.crs["vertical_unit"] == {"name": "metre", "factor_to_m": 1.0}


@pytest.mark.req("FR-004-01")
def test_record_follows_the_file_and_never_a_default(tmp_path: Path) -> None:
    dem = terrain.io.read_dem(_dem(tmp_path, "z13.tif", kit.crs_wkt("utm13-m")))
    assert dem.crs["horizontal"]["epsg"] == 26913  # not the default zone 12 of the recipe origin
    dem2 = terrain.io.read_dem(_dem(tmp_path, "z12_2011.tif", kit.crs_wkt("utm12-2011-m")))
    assert dem2.crs["horizontal"]["epsg"] == 6341  # NAD83(2011): a different realisation is a different code


@pytest.mark.req("FR-004-01")
def test_crs_without_epsg_code_is_recorded_as_wkt(tmp_path: Path) -> None:
    dem = terrain.io.read_dem(_dem(tmp_path, "ft.tif", kit.crs_wkt("utm12-ftus"), unit_scale=kit.FT_US))
    horizontal = dem.crs["horizontal"]
    assert horizontal["epsg"] is None
    assert isinstance(horizontal["wkt"], str)
    assert "UTM" in horizontal["wkt"]
    assert dem.crs["vertical"]["epsg"] == 6360  # NAVD88 height (ftUS) has a code


@pytest.mark.req("FR-004-01")
def test_laz_record_is_read_from_the_wkt_vlr(tmp_path: Path) -> None:
    x = np.array([kit.E0 + 11.5, kit.E0 + 12.5, kit.E0 + 13.5])
    y = np.array([kit.N0 + 17.5, kit.N0 + 18.5, kit.N0 + 19.5])
    z = np.array([kit.Z0 + 1.0, kit.Z0 + 2.0, kit.Z0 + 3.0])
    tile = terrain.io.read_laz(kit.write_laz(tmp_path / "t.laz", x, y, z, np.array([2, 2, 2])))
    assert tile.crs["horizontal"]["epsg"] == 26912
    assert tile.crs["vertical"]["epsg"] == 5703
    assert tile.crs["horizontal_unit"]["name"] == "metre"
    np.testing.assert_allclose(tile.x, x, atol=1e-3)  # LAS scale 0.001 m
    assert tile.classification.tolist() == [2, 2, 2]


@pytest.mark.req("FR-004-03")
def test_us_survey_foot_is_converted_with_the_exact_factor_and_the_factor_is_recorded(tmp_path: Path) -> None:
    dem = terrain.io.read_dem(_dem(tmp_path, "ft.tif", kit.crs_wkt("utm12-ftus"), unit_scale=kit.FT_US))
    assert dem.crs["horizontal_unit"]["name"] == "us-survey-foot"
    assert dem.crs["vertical_unit"]["name"] == "us-survey-foot"
    assert dem.crs["horizontal_unit"]["factor_to_m"] == 1200 / 3937  # exact definition, not 0.3048
    assert dem.crs["vertical_unit"]["factor_to_m"] == 1200 / 3937


@pytest.mark.req("FR-004-03")
def test_international_foot_horizontal_and_metre_vertical_are_recorded_separately(tmp_path: Path) -> None:
    arr = kit.Z0 + np.arange(16, dtype=np.float64).reshape(4, 4)  # heights stay in metres (vertical CRS 5703)
    path = kit.write_dem(
        tmp_path / "ftintl.tif",
        arr,
        x_min=(kit.E0 + 10.0) / kit.FT_INTL,
        y_max=(kit.N0 + 20.0) / kit.FT_INTL,
        cell=1.0 / kit.FT_INTL,
        wkt=kit.crs_wkt("utm12-ftintl-vm"),
    )
    dem = terrain.io.read_dem(path)
    assert dem.crs["horizontal_unit"] == {"name": "international-foot", "factor_to_m": 0.3048}
    assert dem.crs["vertical_unit"] == {"name": "metre", "factor_to_m": 1.0}


@pytest.mark.req("FR-004-03")
def test_feet_dem_gives_the_hand_calculated_site_grid(tmp_path: Path) -> None:
    """4 x 4 cells, 1 m cells, SW corner at site (10, 16): elevation = z - z0 = 10 r + c (hand calculation)."""
    spec = kit.with_aoi(kit.scene_spec(), 10.0, 16.0, 14.0, 20.0, 1.0)
    z = (10.0 * np.arange(4)[:, None] + np.arange(4)[None, :]).astype(np.float64)
    grid = terrain.build_terrain_grid(
        spec,
        {SRC: [_dem(tmp_path, "ft.tif", kit.crs_wkt("utm12-ftus"), unit_scale=kit.FT_US, z=z)]},
    )
    assert (grid.rows, grid.cols) == (4, 4)
    assert grid.x_min_m == pytest.approx(10.0, abs=1e-3)
    assert grid.y_max_m == pytest.approx(20.0, abs=1e-3)
    np.testing.assert_allclose(grid.elevation, z, atol=1e-3)
    assert grid.elevation.dtype == np.float32


@pytest.mark.req("P-004-04")
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    cell=st.sampled_from([0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
def test_unit_change_invariance_feet_vs_metres(cell: float, seed: int) -> None:
    """P-004-04: the same terrain in US survey feet or in metres gives the same site-local grid (atol 1e-3 m)."""
    n = 9
    rng = np.random.default_rng(seed)
    z = rng.uniform(0.0, 100.0, size=(n, n))
    extent = n * cell
    spec = kit.with_aoi(
        kit.scene_spec(),
        10.0 + 0.25 * cell,
        16.0 + 0.25 * cell,
        10.0 + extent - 0.25 * cell,
        16.0 + extent - 0.25 * cell,
        cell,
    )
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g_m = terrain.build_terrain_grid(spec, {SRC: [_dem(tmp, "m.tif", kit.crs_wkt("utm12-m"), cell=cell, n=n, z=z)]})
        g_ft = terrain.build_terrain_grid(
            spec,
            {SRC: [_dem(tmp, "ft.tif", kit.crs_wkt("utm12-ftus"), unit_scale=kit.FT_US, cell=cell, n=n, z=z)]},
        )
    assert g_m.elevation.shape == g_ft.elevation.shape
    assert g_m.x_min_m == pytest.approx(g_ft.x_min_m, abs=1e-3)
    assert g_m.y_max_m == pytest.approx(g_ft.y_max_m, abs=1e-3)
    np.testing.assert_allclose(g_m.elevation, g_ft.elevation, atol=1e-3)

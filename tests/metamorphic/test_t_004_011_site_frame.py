# ruff: noqa: PT018
"""T-004-011: site-local ENU transform with float32 offsets; translation invariance.

Requirements: FR-004-02, P-004-03.

Oracle: PROJ called directly through `pyproj.Transformer` (reference implementation, plan.md "FR-004-02") on five
control points, plus hand-calculated origin subtraction; P-004-03 is a metamorphic relation (shifted inputs and shifted
origin give the same site-local grid, atol 1e-3 m).

Expected API (package `pitstudio_studio.scene.terrain`, studio environment):
- `terrain.frame.site_frame(x, y, z, *, crs, origin)`: `x`, `y`, `z` float64 arrays in the source CRS and units;
  `crs` a DC-004-03 `crs_record` dict (see test_t_004_010); `origin` = `{"epsg", "easting_m", "northing_m", "z0_m"}`.
  Returns `(xs, ys, zs)`: X east, Y north, Z up in metres relative to the origin, computed in float64
  (pyproj `Transformer.from_crs(source, origin epsg, always_xy=True)`, then origin subtraction).
- `terrain.frame.site_frame_f32(...)`: same arguments, returns float32 arrays (the float64 result cast to float32).
- `terrain.build_terrain_grid(spec, inputs)` as in test_t_004_010.
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

ORIGIN = {"epsg": 26912, "easting_m": kit.E0, "northing_m": kit.N0, "z0_m": kit.Z0}
CRS_M = {
    "horizontal": {"epsg": 26912},
    "vertical": {"epsg": 5703},
    "horizontal_unit": {"name": "metre", "factor_to_m": 1.0},
    "vertical_unit": {"name": "metre", "factor_to_m": 1.0},
}
CRS_UTAH = {**CRS_M, "horizontal": {"epsg": 32143}}  # NAD83 / Utah Central (metres)
SRC = "usgs-3dep-bingham"


@pytest.mark.req("FR-004-02")
def test_same_zone_is_origin_subtraction_by_hand() -> None:
    """Hand calculation: (406600.5, 4484700.25, 1850.5) minus (406500, 4484500, 1800) = (100.5, 200.25, 50.5)."""
    xs, ys, zs = terrain.frame.site_frame(
        np.array([406600.5]), np.array([4484700.25]), np.array([1850.5]), crs=CRS_M, origin=ORIGIN
    )
    assert (float(xs[0]), float(ys[0]), float(zs[0])) == pytest.approx((100.5, 200.25, 50.5), abs=1e-9)
    assert xs.dtype == ys.dtype == zs.dtype == np.float64


@pytest.mark.req("FR-004-02")
def test_other_projection_matches_proj_on_five_control_points() -> None:
    """Reference implementation: PROJ (pyproj). Five geodetic control points near the site are projected to the
    source CRS (NAD83 / Utah Central, EPSG:32143) and, directly, to the origin's UTM zone; `site_frame` must map the
    first set onto the second minus the origin."""
    import pyproj

    lon = np.array([-112.160, -112.152, -112.145, -112.138, -112.131])
    lat = np.array([40.505, 40.512, 40.520, 40.527, 40.534])
    z = np.array([1650.0, 1800.25, 2100.5, 2400.0, 2900.75])
    x, y = pyproj.Transformer.from_crs(4269, 32143, always_xy=True).transform(lon, lat)
    e, n = pyproj.Transformer.from_crs(4269, 26912, always_xy=True).transform(lon, lat)
    got = terrain.frame.site_frame(x, y, z, crs=CRS_UTAH, origin=ORIGIN)
    for g, want in zip(got, (e - kit.E0, n - kit.N0, z - kit.Z0), strict=True):
        np.testing.assert_allclose(g, want, atol=1e-6)  # float64 transform: error far below 1 micrometre


@pytest.mark.req("FR-004-02")
def test_feet_inputs_are_converted_before_the_origin_is_subtracted() -> None:
    crs_ft = {
        "horizontal": {"epsg": None, "wkt": kit.crs_wkt("utm12-ftus")},
        "vertical": {"epsg": 6360},
        "horizontal_unit": {"name": "us-survey-foot", "factor_to_m": 1200 / 3937},
        "vertical_unit": {"name": "us-survey-foot", "factor_to_m": 1200 / 3937},
    }
    # metres (406600, 4484700, 1850) expressed in US survey feet
    x, y, z = np.array([406600.0 / kit.FT_US]), np.array([4484700.0 / kit.FT_US]), np.array([1850.0 / kit.FT_US])
    xs, ys, zs = terrain.frame.site_frame(x, y, z, crs=crs_ft, origin=ORIGIN)
    assert (float(xs[0]), float(ys[0]), float(zs[0])) == pytest.approx((100.0, 200.0, 50.0), abs=1e-6)


@pytest.mark.req("FR-004-02")
def test_stored_offsets_are_float32_and_keep_sub_millimetre_precision() -> None:
    rng = np.random.default_rng(7)
    x = kit.E0 + rng.uniform(-900, 900, 200)
    y = kit.N0 + rng.uniform(-900, 900, 200)
    z = kit.Z0 + rng.uniform(-300, 600, 200)
    wide = terrain.frame.site_frame(x, y, z, crs=CRS_M, origin=ORIGIN)
    narrow = terrain.frame.site_frame_f32(x, y, z, crs=CRS_M, origin=ORIGIN)
    for w, nrw in zip(wide, narrow, strict=True):
        assert nrw.dtype == np.float32
        np.testing.assert_array_equal(nrw, w.astype(np.float32))  # the float64 result, cast once
        assert np.all(np.abs(nrw.astype(np.float64) - w) <= np.spacing(np.abs(nrw)))  # one float32 ulp
    # Absolute float32 coordinates would be off by up to 0.25 m at 4.4e6 m; offsets are not.
    assert np.max(np.abs(x.astype(np.float32).astype(np.float64) - x)) > 0.01
    assert np.max(np.abs(narrow[0].astype(np.float64) - wide[0])) < 1e-4
    # FR-004-02 bounds for stored offsets
    assert np.all(np.abs(narrow[0]) <= 1.0e5) and np.all(np.abs(narrow[1]) <= 1.0e5)
    assert np.all(np.abs(narrow[2]) <= 5.0e3)


@pytest.mark.req("P-004-03")
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    dx=st.floats(min_value=-5000, max_value=5000),
    dy=st.floats(min_value=-5000, max_value=5000),
    dz=st.floats(min_value=-100, max_value=100),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
def test_translation_invariance_of_the_site_grid(dx: float, dy: float, dz: float, seed: int) -> None:
    """Shifting the DEM by (dx, dy, dz) in the source CRS and the site origin by the same vector changes nothing."""
    n = 9
    z = np.random.default_rng(seed).uniform(0.0, 80.0, size=(n, n))
    spec = kit.with_aoi(kit.scene_spec(), 10.0, 16.0, 10.0 + n, 16.0 + n, 1.0)
    shifted = kit.with_origin(spec, kit.E0 + dx, kit.N0 + dy, kit.Z0 + dz)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        base = kit.write_dem(
            tmp / "a.tif",
            kit.Z0 + z,
            x_min=kit.E0 + 10.0,
            y_max=kit.N0 + 16.0 + n,
            cell=1.0,
            wkt=kit.crs_wkt("utm12-m"),
        )
        moved = kit.write_dem(
            tmp / "b.tif",
            kit.Z0 + dz + z,
            x_min=kit.E0 + dx + 10.0,
            y_max=kit.N0 + dy + 16.0 + n,
            cell=1.0,
            wkt=kit.crs_wkt("utm12-m"),
        )
        g0 = terrain.build_terrain_grid(spec, {SRC: [base]})
        g1 = terrain.build_terrain_grid(shifted, {SRC: [moved]})
    assert g0.elevation.shape == g1.elevation.shape == (n, n)
    np.testing.assert_allclose(g1.elevation, g0.elevation, atol=1e-3)
    assert g1.x_min_m == pytest.approx(g0.x_min_m, abs=1e-3)
    assert g1.y_max_m == pytest.approx(g0.y_max_m, abs=1e-3)

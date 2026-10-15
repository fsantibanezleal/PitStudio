# ruff: noqa: E501, PT018
"""T-004-023: carving, cut and fill volumes, identity residual, analytic benched pit.

Requirements: FR-004-19, P-004-07.

Oracle: (1) the identity V_cut - V_fill = sum over cells of (z_terrain - z_final) x cell area, recomputed here in
float64 from the returned arrays (P-004-07); (2) the hand-calculated sum of conical-frustum volumes of a circular benched
pit on flat ground, V = sum_k (H / 3) (A_c + sqrt(A_c A_t) + A_t) (exact for similar polygons, areas from the regular
n-gon formula A = n a^2 tan(pi / n)), within the rasterisation bound sum_k P_k dx H and 1 % (spec P-004-07: rim radius
500 m, H = 15 m, alpha = 70 deg, b = 10 m, 10 benches, dx = 1 m); (3) the carving rule z_final = min(z_terrain, z_design)
inside the outline, windrows added on top; (4) the measured bench table against the spec tolerances of FR-004-35
(height +/- 0.5 m, face angle +/- 1 deg).

Expected API (package `pitstudio_studio.scene.design`, studio environment):
- `design.build_design(grid, spec, *, outline_xy, include_ramp=True, include_windrows=True) -> DesignResult`.
  `grid`: any object with `elevation` (float [rows, cols], row 0 = north, site-frame metres), `x_min_m`, `y_max_m`,
  `cell_size_m`. `spec`: a SceneSpec dict (its `design`, `assets` and `fleet` blocks are used). `outline_xy`: the pit
  outline ring in the site frame (from `design.outline.rim_contour` or an upstream shell). The two flags exist so that
  the analytic fixture can be built without the ramp and the windrows.
- `DesignResult` has `benches` (list of `Bench`), `ramp` (`Ramp` or None), `windrows` (list), `z_design` (float64
  [rows, cols], the design surface inside the outline, NaN outside), `windrow_mask` (bool), `z_final` (array like
  `grid.elevation`), `report` (a dict valid against DC-004-05, `pit-design-report.schema.json`) and `road_network`.
  Inside the outline `z_final = min(z_terrain, z_design) + windrow height on windrow cells`; outside it equals the terrain.
- `report["volumes"]`: `cut_m3` = sum of max(z_terrain - z_final, 0) x cell area, `fill_m3` = sum of max(z_final -
  z_terrain, 0) x cell area, `carved_sum_m3` = sum of (z_terrain - z_final) x cell area, `cell_area_m2`,
  `identity_residual_rel` = |V_cut - V_fill - carved_sum| / max(V_cut, V_fill, 1), all in float64.
"""

from __future__ import annotations

import hashlib
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import common, design  # noqa: E402


def _cell_centres(grid):
    rows, cols = grid.elevation.shape
    xs = grid.x_min_m + (np.arange(cols) + 0.5) * grid.cell_size_m
    ys = grid.y_max_m - (np.arange(rows) + 0.5) * grid.cell_size_m
    return np.meshgrid(xs, ys)


def _volumes(zt: np.ndarray, zf: np.ndarray, cell: float) -> tuple[float, float, float]:
    d = zt.astype(np.float64) - zf.astype(np.float64)
    a = cell * cell
    return float(np.maximum(d, 0).sum() * a), float(np.maximum(-d, 0).sum() * a), float(d.sum() * a)


def _inside(poly, grid, margin: float):
    import shapely

    xx, yy = _cell_centres(grid)
    return shapely.contains_xy(poly.buffer(-margin), xx, yy), ~shapely.contains_xy(poly.buffer(margin), xx, yy)


@pytest.mark.req("P-004-07")
def test_analytic_benched_pit_matches_the_frustum_sum_within_the_rasterisation_bound() -> None:
    n, r0, h, alpha, b, nb = 720, 500.0, 15.0, 70.0, 10.0, 10
    d = h / math.tan(math.radians(alpha))
    grid = kit.flat_grid(520.0, 1.0, 0.0)
    spec = kit.design_spec(h=h, alpha=alpha, b=b, rim_z=0.0, floor_z=-150.0)
    res = design.build_design(
        grid, spec, outline_xy=kit.regular_polygon(n, r0), include_ramp=False, include_windrows=False
    )
    a0, t = r0 * math.cos(math.pi / n), math.tan(math.pi / n)
    expected, bound = 0.0, 0.0
    for k in range(nb):
        a_c = a0 - k * (d + b)
        area_c, area_t = n * a_c**2 * t, n * (a_c - d) ** 2 * t
        expected += h / 3.0 * (area_c + math.sqrt(area_c * area_t) + area_t)  # conical frustum
        bound += 2 * n * a_c * t * 1.0 * h  # P_k * dx * H
    cut, fill, carved = _volumes(grid.elevation, res.z_final, 1.0)
    assert abs(cut - expected) <= bound
    assert abs(cut - expected) <= 0.01 * expected
    assert fill == 0.0 and carved == pytest.approx(cut, rel=1e-12)
    vol = res.report["volumes"]
    assert vol["cut_m3"] == pytest.approx(cut, rel=1e-12) and vol["fill_m3"] == 0.0
    # the flat floor lies exactly at the declared floor elevation
    assert float(res.z_final[res.z_final.shape[0] // 2, res.z_final.shape[1] // 2]) == pytest.approx(-150.0, abs=1e-4)


@pytest.mark.req("FR-004-19")
def test_carving_rule_and_unchanged_terrain_outside_the_outline() -> None:
    rng = np.random.default_rng(4)
    grid = kit.flat_grid(130.0, 1.0, 0.0)
    grid.elevation = (rng.normal(0.0, 0.3, grid.elevation.shape)).astype(np.float32)  # a slightly rough rim plane
    spec = kit.design_spec(h=12.0, alpha=70.0, b=10.0, g=8.0, w=20.0, windrow=2.0, floor_z=-36.0)
    outline = kit.regular_polygon(180, 100.0)
    res = design.build_design(grid, spec, outline_xy=outline)
    from shapely.geometry import Polygon

    deep_in, far_out = _inside(Polygon(outline), grid, 2.0)
    zt = grid.elevation.astype(np.float64)
    np.testing.assert_array_equal(np.asarray(res.z_final)[far_out], grid.elevation[far_out])  # terrain untouched
    expected = np.minimum(zt, res.z_design) + np.where(res.windrow_mask, 2.0, 0.0)
    np.testing.assert_allclose(np.asarray(res.z_final, dtype=np.float64)[deep_in], expected[deep_in], atol=1e-4)
    assert res.windrow_mask.any() and not res.windrow_mask[far_out].any()


def _check_volumes(res, grid) -> None:
    vol = res.report["volumes"]
    cut, fill, carved = _volumes(grid.elevation, res.z_final, grid.cell_size_m)
    assert vol["cell_area_m2"] == pytest.approx(grid.cell_size_m**2, rel=1e-12)
    assert vol["cut_m3"] == pytest.approx(cut, rel=1e-12)
    assert vol["fill_m3"] == pytest.approx(fill, rel=1e-12, abs=1e-9)
    assert vol["carved_sum_m3"] == pytest.approx(carved, rel=1e-12)
    # P-004-07: V_cut - V_fill = sum (z_terrain - z_final) dA, exactly (rtol 1e-12)
    assert cut - fill == pytest.approx(carved, rel=1e-12)
    assert vol["identity_residual_rel"] <= 1e-12
    assert vol["identity_residual_rel"] == pytest.approx(abs(cut - fill - carved) / max(cut, fill, 1.0), abs=1e-12)


@pytest.mark.req("P-004-07")
@pytest.mark.req("FR-004-19")
@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])
@given(
    seed=st.integers(0, 2**31 - 1),
    radius=st.floats(70.0, 100.0),
    h=st.floats(5.0, 12.0),
    alpha=st.floats(55.0, 85.0),
    b=st.floats(3.0, 12.0),
    g=st.floats(5.0, 12.0),
    w=st.floats(8.0, 20.0),
    windrow=st.floats(1.7, 3.0),  # at least the 1.6 m mid-axle height of the example haul truck
    nb=st.integers(2, 3),
    star=st.booleans(),
)
def test_volume_identity_holds_for_any_outline_and_parameters(
    seed: int, radius: float, h: float, alpha: float, b: float, g: float, w: float, windrow: float, nb: int, star: bool
) -> None:
    rng = np.random.default_rng(seed)
    grid = kit.flat_grid(125.0, 1.0, 0.0)
    grid.elevation = (rng.normal(0.0, 1.0, grid.elevation.shape)).astype(np.float32)
    outline = kit.star_polygon(seed, 12, 0.85 * radius, radius) if star else kit.regular_polygon(90, radius)
    spec = kit.design_spec(h=h, alpha=alpha, b=b, g=g, w=w, windrow=windrow, floor_z=-nb * h)
    try:
        res = design.build_design(grid, spec, outline_xy=outline)
    except common.SceneStageError as exc:
        assume(exc.error_class not in ("design-infeasible", "outline-invalid"))
        raise
    _check_volumes(res, grid)
    assert res.report["volumes"]["fill_m3"] > 0.0  # the windrows add material on top


@pytest.mark.req("FR-004-19")
def test_report_is_schema_valid_and_carries_the_per_bench_table() -> None:
    grid = kit.flat_grid(130.0, 1.0, 0.0)
    spec = kit.design_spec(h=12.0, alpha=70.0, b=10.0, g=8.0, w=20.0, windrow=2.5, floor_z=-48.0)
    res = design.build_design(grid, spec, outline_xy=kit.regular_polygon(360, 100.0))
    rep = res.report
    assert kit.schema_errors("pit-design-report.schema.json", rep) == []
    assert (
        rep["terrain_grid_sha256"]
        == hashlib.sha256(np.ascontiguousarray(grid.elevation, dtype="<f4").tobytes()).hexdigest()
    )
    assert rep["parameters"] == {
        "bench_height_m": 12.0,
        "face_angle_deg": 70.0,
        "berm_width_m": 10.0,
        "ramp_grade_pct": 8.0,
        "ramp_width_m": 20.0,
        "windrow_height_m": 2.5,
    }
    benches = rep["benches"]
    assert [x["index"] for x in benches] == [0, 1, 2, 3]
    for k, row in enumerate(benches):
        assert row["crest_z_m"] == pytest.approx(-12.0 * k, abs=0.5)  # measured on the carved raster
        assert row["toe_z_m"] == pytest.approx(-12.0 * (k + 1), abs=0.5)
        assert row["height_m"] == pytest.approx(12.0, abs=0.5)  # FR-004-35 tolerance
        assert row["face_angle_deg"] == pytest.approx(70.0, abs=1.0)
        assert row["widened_for_ramp"] is True  # a rim-to-floor ramp crosses every bench
        assert row["crest_perimeter_m"] == pytest.approx(res.benches[k].crest.length, rel=0.01)
    assert [x["berm_width_m"] is None for x in benches] == [False, False, False, True]  # null for the floor bench
    assert all(x["berm_width_m"] == pytest.approx(10.0, abs=1.0) for x in benches[:-1])
    assert rep["ramp"]["max_grade_pct"] <= 8.1 + 1e-9 and rep["ramp"]["min_width_m"] >= 20.0
    assert rep["ramp"]["sample_spacing_m"] <= 1.0 and rep["ramp"]["connected"] is True
    assert rep["ramp"]["length_m"] == pytest.approx(kit.polyline_length_3d(res.ramp.centreline), rel=1e-9)
    assert rep["windrows"]["height_m"] == 2.5 and rep["windrows"]["mid_axle_height_m"] == 1.6  # the example truck
    assert rep["outline"]["area_m2"] == pytest.approx(math.pi * 100.0**2, rel=2e-3)
    assert rep["outline"]["vertices"] == 360
    assert (rep["outline"]["rim_z_m"], rep["outline"]["floor_z_m"]) == (0.0, -48.0)
    _check_volumes(res, grid)


@pytest.mark.req("FR-004-19")
def test_without_the_ramp_no_bench_is_widened() -> None:
    grid = kit.flat_grid(130.0, 1.0, 0.0)
    spec = kit.design_spec(h=12.0, floor_z=-36.0)
    res = design.build_design(grid, spec, outline_xy=kit.regular_polygon(180, 100.0), include_ramp=False)
    assert res.ramp is None
    assert not any(row["widened_for_ramp"] for row in res.report["benches"])

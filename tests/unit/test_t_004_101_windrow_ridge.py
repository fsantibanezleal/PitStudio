# ruff: noqa: PT018, E501
"""T-004-101: windrows are continuous ridges at the angle of repose on the carved surface and in the design layer.

Requirements: FR-004-52 (extends FR-004-18 and FR-004-50: the windrow height, the carved surface and the design meshes are
unchanged; the cross-section of the windrow is new).

Oracles: the trapezoid section written here from the requirement (crest of 1 m, side slopes at 37 degrees, height h, so
the base half width is 0.5 + h / tan(37 degrees)) evaluated by hand at cells of a straight line along x, the height step
of a slope of 37 degrees over one cell (tan 37 * 1 m = 0.7536 m, so no neighbour differs by more than that on an axis),
and the vertices of the design ridge mesh.

Expected API (`pitstudio_studio.scene.design`, studio environment):
- `carved.WINDROW_REPOSE_DEG == 37.0`, `carved.WINDROW_CREST_HALF_WIDTH_M == 0.5`;
- `carved.windrow_raise(lines, shape, x_min_m, y_max_m, cell_m, height_m)`: float array, the raise in metres of every cell
  (cell centres at `x_min + (col + 0.5) * cell`, `y_max - (row + 0.5) * cell`) for the shapely lines;
- `carved.carve(z_design, windrow_mask, height, terrain, inside, raise_m=None)`: with `raise_m` the raise replaces the
  mask times the height;
- `DesignResult.windrow_raise` (float array) with `windrow_mask` the crest cells (raise equal to the height);
- `usd._ridge(points, height)` has the same section (crest 1 m, base half width 0.5 + h / tan 37 degrees).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import design  # noqa: E402
from pitstudio_studio.scene.design import usd as design_usd  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

TAN = math.tan(math.radians(37.0))
H = 2.5
RUN = H / TAN


def _expected(distance: float) -> float:
    return float(np.clip(H - max(distance - 0.5, 0.0) * TAN, 0.0, H))


@pytest.mark.req("FR-004-52")
def test_the_profile_constants_are_the_angle_of_repose_and_a_one_metre_crest() -> None:
    assert design.carved.WINDROW_REPOSE_DEG == 37.0
    assert design.carved.WINDROW_CREST_HALF_WIDTH_M == 0.5


@pytest.mark.req("FR-004-52")
def test_the_raise_across_a_straight_windrow_is_the_trapezoid_section() -> None:
    shape = (41, 81)
    line = LineString([(0.0, 20.0), (80.0, 20.0)])  # row 20 centre is y = 40 - 20.5 = 19.5: 0.5 m off the line
    raise_m = design.carved.windrow_raise([line], shape, 0.0, 40.0, 1.0, H)
    assert raise_m.shape == shape and raise_m.dtype.kind == "f"
    for row in range(41):
        y = 40.0 - (row + 0.5)
        for col in (10, 40, 70):
            assert raise_m[row, col] == pytest.approx(_expected(abs(y - 20.0)), abs=1e-6), (row, col)
    assert raise_m.max() == pytest.approx(H)
    wide = np.nonzero(raise_m[:, 40] > 0)[0]
    assert (wide.max() - wide.min() + 1) * 1.0 >= 2.0 * (0.5 + RUN) - 2.0  # the base is about 2 * (0.5 + run) wide


@pytest.mark.req("FR-004-52")
def test_a_diagonal_windrow_has_no_pillar_the_neighbour_step_is_at_most_a_slope_of_repose() -> None:
    shape = (120, 120)
    line = LineString([(5.0, 5.0), (110.0, 100.0)])
    raise_m = design.carved.windrow_raise([line], shape, 0.0, 120.0, 1.0, H)
    step_x = np.abs(np.diff(raise_m, axis=1)).max()
    step_y = np.abs(np.diff(raise_m, axis=0)).max()
    assert max(step_x, step_y) <= TAN * 1.0 + 1e-6, (
        step_x,
        step_y,
    )  # the 1 cell comb of the cell mask stepped by 2.5 m
    assert raise_m.max() == pytest.approx(H) and (raise_m == H).sum() >= 100


@pytest.mark.req("FR-004-52")
def test_no_windrow_gives_no_raise_and_the_raise_never_exceeds_the_height() -> None:
    assert design.carved.windrow_raise([], (10, 10), 0.0, 10.0, 1.0, H).max() == 0.0
    two = [LineString([(0.0, 5.0), (30.0, 5.0)]), LineString([(0.0, 7.0), (30.0, 7.0)])]
    both = design.carved.windrow_raise(two, (12, 30), 0.0, 12.0, 1.0, H)
    assert both.max() == pytest.approx(H) and both.min() >= 0.0  # two ridges: the higher section, not the sum


@pytest.mark.req("FR-004-52")
def test_carve_adds_the_raise_inside_the_outline_only() -> None:
    terrain = np.full((3, 3), 5.0)
    inside = np.zeros((3, 3), dtype=bool)
    inside[1, 1:] = True
    z_design = np.full((3, 3), np.nan)
    z_design[1, 1], z_design[1, 2] = -1.0, -2.0
    raise_m = np.array([[1.0, 1.0, 1.0], [1.0, 2.5, 0.75], [1.0, 1.0, 1.0]])
    out = design.carved.carve(z_design, np.zeros((3, 3), dtype=bool), 2.5, terrain, inside, raise_m=raise_m)
    assert out[1, 1] == pytest.approx(1.5) and out[1, 2] == pytest.approx(-1.25) and out[0, 0] == 5.0


@pytest.fixture(scope="module")
def pit():
    grid = kit.flat_grid(130.0, 1.0, 0.0)
    spec = kit.design_spec(h=12.0, alpha=70.0, b=10.0, g=8.0, w=20.0, windrow=2.5, floor_z=-36.0)
    return design.build_design(grid, spec, outline_xy=kit.regular_polygon(180, 100.0))


@pytest.mark.req("FR-004-52")
def test_the_built_surface_carries_the_ridge_and_the_mask_is_its_crest(pit) -> None:
    raise_m = pit.windrow_raise
    inside = pit.inside
    assert np.allclose(pit.z_carved[inside] - pit.z_design[inside], raise_m[inside], atol=1e-5)
    assert raise_m.max() == pytest.approx(2.5) and raise_m[~inside].max() == 0.0
    crest = pit.windrow_mask & inside
    assert crest.sum() > 100 and np.allclose(raise_m[crest], 2.5)
    assert ((raise_m > 0) & inside).sum() > 3 * crest.sum()  # the ridge is wider than its crest cells


@pytest.mark.req("FR-004-52")
def test_the_carved_surface_has_fewer_spikes_than_a_pillar_comb(pit) -> None:
    from scipy import ndimage as ndi

    z = np.where(pit.inside, pit.z_carved.astype(np.float64), 0.0)
    excess = z - ndi.median_filter(z, size=3, mode="nearest")
    windrow = (pit.windrow_raise > 0) & pit.inside
    assert (excess[windrow] > 1.2).sum() <= 0.1 * windrow.sum()


@pytest.mark.req("FR-004-52")
def test_the_design_layer_ridge_has_the_same_section() -> None:
    points = np.array([[0.0, 0.0, 10.0], [20.0, 0.0, 10.0]])
    triangles = np.asarray(design_usd._ridge(points, H)).reshape(-1, 3)
    section = sorted({(round(abs(float(y)), 6), round(float(z) - 10.0, 6)) for _, y, z in triangles})
    assert section == sorted({(round(0.5 + RUN, 6), 0.0), (0.5, H)})
    assert {round(float(y), 6) for _, y, _ in triangles} == {round(0.5 + RUN, 6), 0.5, -0.5, -round(0.5 + RUN, 6)}

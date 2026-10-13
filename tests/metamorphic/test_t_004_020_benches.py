# ruff: noqa: E501, PT018
"""T-004-020: crest and toe offsets; rim contour; rotation invariance; monotonicity in face angle and berm width.

Requirements: FR-004-16, P-004-08, P-004-09.

Oracle: hand calculation on a circular pit (toe radius = crest radius - H / tan(alpha), next crest = toe - b; exact for
a regular polygon, whose inward mitre offset is a scaled copy) and on a rectangle (square corners, hand-computed side
lengths); shapely `affinity.rotate` as the reference rotation (plan.md "P-004-08"); the vector cut volume is computed
here from the generated polygons with Simpson's rule on the area function (exact for convex outlines, where the area of
the inset polygon is quadratic in the inset); P-004-09 is a metamorphic ordering of paired runs.

Expected API (package `pitstudio_studio.scene.design`, studio environment):
- `design.benches.generate_benches(outline_xy, *, bench_height_m, face_angle_deg, berm_width_m, rim_z_m, floor_z_m)`
  -> list of `Bench` (index 0 at the rim). `outline_xy` is a polygon ring of [x, y] in the site frame (either
  orientation, not closed). A `Bench` has `index`, `crest` and `toe` (shapely `Polygon`), `crest_z` and `toe_z` (m).
  `toe` is `crest` offset inward by H / tan(alpha) with mitre joins; the next crest is the toe offset inward by the berm
  width (mitre joins); `crest_z` of bench k is `rim_z_m - k * H`; `toe_z = crest_z - H`; benches continue to `floor_z_m`.
- `design.outline.rim_contour(elevation, *, x_min_m, y_max_m, cell_size_m, rim_z_m)` -> a polygon ring of [x, y]
  (site frame): the outline of the region of the grid that lies below `rim_z_m` around the lowest cell.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import design  # noqa: E402


def _benches(outline, h=15.0, alpha=70.0, b=10.0, rim=0.0, floor=-150.0):
    return design.benches.generate_benches(
        outline, bench_height_m=h, face_angle_deg=alpha, berm_width_m=b, rim_z_m=rim, floor_z_m=floor
    )


def _regular(n: int, circumradius: float):
    from shapely.geometry import Polygon

    return Polygon(kit.regular_polygon(n, circumradius))


def _hausdorff(a, b) -> float:
    return float(a.hausdorff_distance(b))


def _vector_cut_volume(benches, h: float, alpha: float) -> float:
    """Pit volume below a flat rim from the bench polygons: sum over faces of Simpson's rule on the area function."""
    d = h / math.tan(math.radians(alpha))
    total = 0.0
    for bch in benches:
        mid = bch.crest.buffer(-d / 2.0, join_style="mitre", mitre_limit=10.0)
        total += h / 6.0 * (bch.crest.area + 4.0 * mid.area + bch.toe.area)
    return total


@pytest.mark.req("FR-004-16")
def test_circular_pit_benches_follow_the_hand_formula() -> None:
    n, r0, h, alpha, b = 720, 500.0, 15.0, 70.0, 10.0
    d = h / math.tan(math.radians(alpha))  # 5.4596 m horizontal run of a face
    benches = _benches(kit.regular_polygon(n, r0), h, alpha, b)
    assert len(benches) == 10  # 150 m / 15 m
    apothem0 = r0 * math.cos(math.pi / n)
    for k, bench in enumerate(benches):
        crest_r = (apothem0 - k * (d + b)) / math.cos(math.pi / n)
        toe_r = (apothem0 - k * (d + b) - d) / math.cos(math.pi / n)
        assert bench.index == k
        assert (bench.crest_z, bench.toe_z) == pytest.approx((-k * h, -(k + 1) * h), abs=1e-9)
        assert _hausdorff(bench.crest, _regular(n, crest_r)) < 1e-5
        assert _hausdorff(bench.toe, _regular(n, toe_r)) < 1e-5
        # toe is inside the crest, and the next crest is a berm width inside the toe
        assert bench.crest.contains(bench.toe)
        if k + 1 < len(benches):
            assert bench.toe.contains(benches[k + 1].crest)
            assert bench.toe.exterior.distance(benches[k + 1].crest.exterior) == pytest.approx(b, abs=1e-5)


@pytest.mark.req("FR-004-16")
def test_rectangle_offsets_have_square_mitre_corners_by_hand() -> None:
    """400 x 300 m rectangle, H = 15, alpha = 70: toe = 400 - 2d by 300 - 2d; next crest = a further b = 10 m inside."""
    d = 15.0 / math.tan(math.radians(70.0))
    outline = [[-200.0, -150.0], [200.0, -150.0], [200.0, 150.0], [-200.0, 150.0]]
    benches = _benches(outline, 15.0, 70.0, 10.0, rim=0.0, floor=-45.0)
    assert len(benches) == 3
    for k, bench in enumerate(benches):
        s = k * (d + 10.0)
        w, hh = 400.0 - 2 * s, 300.0 - 2 * s
        assert bench.crest.bounds == pytest.approx((-w / 2, -hh / 2, w / 2, hh / 2), abs=1e-9)
        assert bench.crest.area == pytest.approx(w * hh, rel=1e-12)
        assert bench.toe.bounds == pytest.approx(
            (-(w - 2 * d) / 2, -(hh - 2 * d) / 2, (w - 2 * d) / 2, (hh - 2 * d) / 2), abs=1e-9
        )
        assert len(bench.crest.exterior.coords) == 5  # four corners: mitre joins keep the corner vertices
        assert bench.toe.area == pytest.approx((w - 2 * d) * (hh - 2 * d), rel=1e-12)


@pytest.mark.req("FR-004-16")
def test_clockwise_and_counter_clockwise_outlines_give_the_same_benches() -> None:
    ccw = kit.star_polygon(7, 12, 300.0, 420.0)
    a = _benches(ccw, 10.0, 65.0, 8.0, floor=-40.0)
    b = _benches(ccw[::-1], 10.0, 65.0, 8.0, floor=-40.0)
    assert len(a) == len(b) == 4
    for x, y in zip(a, b, strict=True):
        assert _hausdorff(x.crest, y.crest) < 1e-6 and _hausdorff(x.toe, y.toe) < 1e-6


@pytest.mark.req("FR-004-16")
def test_bench_polygons_of_a_concave_outline_are_valid_and_nested() -> None:
    outline = kit.star_polygon(3, 12, 340.0, 440.0)
    benches = _benches(outline, 12.0, 70.0, 12.0, floor=-48.0)
    for k, bench in enumerate(benches):
        assert bench.crest.is_valid and bench.toe.is_valid
        assert bench.crest.buffer(1e-6).contains(bench.toe)
        if k + 1 < len(benches):
            assert bench.toe.buffer(1e-6).contains(benches[k + 1].crest)


@pytest.mark.req("FR-004-16")
def test_rim_contour_outline_of_a_conical_pit() -> None:
    """z = 0.1 r on a 1 m grid: the level z = 25 m is the circle r = 250 m (hand calculation)."""
    from shapely.geometry import Polygon

    n = 1200
    xs = np.arange(n) + 0.5 - n / 2  # cell centres, site frame
    ys = (n / 2 - 0.5) - np.arange(n)
    z = 0.1 * np.hypot(xs[None, :], ys[:, None])
    ring = design.outline.rim_contour(
        z.astype(np.float32), x_min_m=-n / 2, y_max_m=n / 2, cell_size_m=1.0, rim_z_m=25.0
    )
    poly = Polygon(ring)
    assert poly.is_valid and len(ring) >= 100
    assert poly.area == pytest.approx(math.pi * 250.0**2, rel=0.01)
    assert abs(poly.centroid.x) < 1.0 and abs(poly.centroid.y) < 1.0
    radii = np.hypot(*np.array(ring).T)
    assert np.all(np.abs(radii - 250.0) < 1.5)  # within about one cell of the circle


@pytest.mark.req("P-004-08")
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    theta=st.floats(0.0, 360.0, exclude_max=True),
    seed=st.integers(0, 2**31 - 1),
    n=st.integers(6, 16),
    h=st.floats(8.0, 14.0),
    alpha=st.floats(60.0, 85.0),
    b=st.floats(5.0, 15.0),
    convex=st.booleans(),
)
def test_rotating_the_outline_rotates_every_polygon_and_keeps_the_measures(
    theta: float, seed: int, n: int, h: float, alpha: float, b: float, convex: bool
) -> None:
    """P-004-08: Hausdorff <= 1e-6 x extent between the rotated bench polygons and the benches of the rotated outline."""
    from shapely import affinity
    from shapely.geometry import Polygon

    outline = kit.regular_polygon(n, 400.0) if convex else kit.star_polygon(seed, n, 340.0, 440.0)
    kwargs = dict(h=h, alpha=alpha, b=b, rim=0.0, floor=-3 * h)
    base = _benches(outline, **kwargs)
    rotated_outline = [list(p) for p in affinity.rotate(Polygon(outline), theta, origin=(0, 0)).exterior.coords][:-1]
    turned = _benches(rotated_outline, **kwargs)
    assert len(base) == len(turned) == 3
    extent = 2 * 440.0
    for x, y in zip(base, turned, strict=True):
        for a_poly, b_poly in ((x.crest, y.crest), (x.toe, y.toe)):
            assert _hausdorff(affinity.rotate(a_poly, theta, origin=(0, 0)), b_poly) <= 1e-6 * extent
            assert b_poly.area == pytest.approx(a_poly.area, rel=1e-9)
            assert b_poly.length == pytest.approx(a_poly.length, rel=1e-9)
    if convex:
        assert _vector_cut_volume(turned, h, alpha) == pytest.approx(_vector_cut_volume(base, h, alpha), rel=1e-9)


def _ellipse(n: int = 360, a: float = 700.0, b: float = 520.0) -> list[list[float]]:
    t = 2 * math.pi * np.arange(n) / n
    return [[a * math.cos(x), b * math.sin(x)] for x in t]


@pytest.mark.req("P-004-09")
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(a1=st.floats(50.0, 84.0), da=st.floats(0.5, 1.0), b=st.floats(3.0, 30.0), h=st.floats(8.0, 20.0))
def test_steeper_faces_never_decrease_the_cut_volume(a1: float, da: float, b: float, h: float) -> None:
    kwargs = dict(h=h, b=b, rim=0.0, floor=-5 * h)
    low = _benches(_ellipse(), alpha=a1, **kwargs)
    high = _benches(_ellipse(), alpha=a1 + da, **kwargs)
    assert len(low) == len(high) == 5
    assert _vector_cut_volume(high, h, a1 + da) >= _vector_cut_volume(low, h, a1)


@pytest.mark.req("P-004-09")
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(b1=st.floats(3.0, 28.0), db=st.floats(0.5, 2.0), alpha=st.floats(55.0, 85.0), h=st.floats(8.0, 20.0))
def test_wider_berms_never_increase_the_cut_volume(b1: float, db: float, alpha: float, h: float) -> None:
    kwargs = dict(h=h, alpha=alpha, rim=0.0, floor=-5 * h)
    narrow = _benches(_ellipse(), b=b1, **kwargs)
    wide = _benches(_ellipse(), b=b1 + db, **kwargs)
    assert _vector_cut_volume(wide, h, alpha) <= _vector_cut_volume(narrow, h, alpha)


def _overall_slope_deg(benches, h: float, n: int) -> float:
    """Overall slope from the crests of a regular n-gon: atan(H / horizontal step between successive crests)."""
    apothem = [math.sqrt(b.crest.area / (n * math.tan(math.pi / n))) for b in benches]
    step = float(np.mean(-np.diff(apothem)))
    return math.degrees(math.atan2(h, step))


@pytest.mark.req("P-004-09")
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(alpha=st.floats(50.0, 84.0), da=st.floats(0.5, 1.0), b=st.floats(3.0, 30.0), db=st.floats(0.5, 2.0))
def test_overall_slope_angle_is_monotone_and_matches_the_formula(alpha: float, da: float, b: float, db: float) -> None:
    n, h = 360, 12.0

    def slope(al: float, be: float) -> float:
        bs = _benches(kit.regular_polygon(n, 600.0), h=h, alpha=al, b=be, floor=-48.0)
        return _overall_slope_deg(bs, h, n)

    def formula(al: float, be: float) -> float:
        return math.degrees(math.atan(h / (h / math.tan(math.radians(al)) + be)))

    s0 = slope(alpha, b)
    assert s0 == pytest.approx(formula(alpha, b), abs=1e-6)
    assert slope(alpha + da, b) >= s0  # non-decreasing in alpha
    assert slope(alpha, b + db) <= s0  # non-increasing in the berm width

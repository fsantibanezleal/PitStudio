"""T-017-044: known-volume scene: closed forms, mesh volume, gridding floor (property).

Requirements: FR-017-35, P-017-15.

Spec: specs/017-planning-survey/spec.md
- FR-017-35: the known-volume scene contains a conical-frustum stockpile and a trapezoidal pushback cut on a flat
  base,
  with exact volumes from their closed forms, a closed USD mesh whose divergence-theorem volume equals them, and
  the exact
  surface rasterised on the survey grid (cell 0.25 m) so that the gridding error of an exact surface is reported as
  the
  floor of the survey error;
- P-017-15: the divergence-theorem volume of a closed polyhedral mesh equals the closed form of a cube, a prism and a
  frustum mesh; it is unchanged by translation and scales as k^3 (edge lengths in [0.1, 10^3] m; rtol 1e-12; meshes of
  <= 10^3 faces).
plan.md test strategy row FR-017-35: closed forms: frustum V = pi h (R^2 + R r + r^2) / 3, trapezoidal prism V = L h
(b_1 + b_2) / 2; divergence-theorem mesh volume (P-017-15).

Oracles (closed forms and exact relations written in the test):
- cube a^3, box lx ly lz, triangular prism (a b / 2) h with the base triangle (0,0), (a,0), (0,b);
- the regular n-gon frustum: base areas A(R) = (n / 2) R^2 sin(2 pi / n), V = (h / 3)(A(R) + sqrt(A(R) A(r)) +
  A(r)); as
  the area of the n-gon is sin(theta) / theta times that of the circle (theta = 2 pi / n) for both radii, the
  polygonal
  frustum volume is exactly the circular closed form times sin(theta) / theta (and within 2e-5 of it for n = 720);
- the scene of the test: frustum h = 6, R = 15, r = 7 m: V = pi 6 (225 + 105 + 49) / 3 = 2 pi 379 m^3; trapezoidal
  cut of
  length 60 m, depth 4 m, bottom width 8 m, top width 16 m: V = 60 x 4 x (8 + 16) / 2 = 2,880 m^3; the 0.25 m
  raster of
  the exact surface (heights evaluated at cell centres) summed by numpy in the test gives the gridded volumes and the
  floor percentages 100 (V_grid - V) / V;
- an open mesh (a face removed) is not closed, so its divergence-theorem volume is undefined: refused.

Expected public API (root environment, numpy only):
module `pitstudio.survey.meshvolume`
    box_mesh(lx, ly, lz) -> (vertices (8, 3), faces (12, 3))                    # outward-oriented, one corner at
    the origin
    prism_mesh(polygon_xy: np.ndarray, height: float) -> (vertices, faces)      # a convex polygon extruded along z
    frustum_mesh(r_bottom: float, r_top: float, height: float, n: int = 720) -> (vertices, faces)
        a regular n-gon frustum, bottom at z = 0 (radius r_bottom), top at z = height (radius r_top), closed
        (a triangle fan on each cap), outward-oriented
    mesh_volume(vertices, faces) -> float
        divergence theorem sum over faces of v0 . (v1 x v2) / 6 (evaluated about the mesh centroid or first vertex
        so that
        translation does not cost precision); ValueError for a mesh that is not closed (every undirected edge must be
        shared by exactly two faces), an index out of range, a non-finite vertex, or fewer than 4 faces.
    frustum_volume(r_bottom, r_top, height) -> float                            # pi h (R^2 + R r + r^2) / 3
    trapezoid_cut_volume(length, depth, bottom_width, top_width) -> float       # L h (b1 + b2) / 2
module `pitstudio.survey.scene`
    @dataclass Scene: frustum_volume_m3, cut_volume_m3, before (Surface: flat 0 m), after (Surface with the frustum
    and
        the cut), meshes ({"frustum": (v, f), "trench": (v, f)}), floor ({"fill_pct", "cut_pct"}: 100 (V_grid - V)
        / V of
        the rasterised exact surface against the closed form)
    known_volume_scene(*, cell_m: float = 0.25, extent_m: tuple[float, float] = (200.0, 200.0),
                       frustum: Mapping = {"centre": (60, 100), "r_bottom": 15, "r_top": 7, "height": 6},
                       trench: Mapping = {"x_centre": 150, "y_start": 70, "length": 60, "depth": 4,
                                          "bottom_width": 8, "top_width": 16}) -> Scene
        heights at cell centres: the frustum rises linearly from 0 at radius R to h at radius r and is flat h
        inside; the
        trench has bottom width b1 at depth h, top width b2 at z = 0, linear walls, vertical end walls at y_start and
        y_start + length; ValueError for a frustum with r_top >= r_bottom or non-positive sizes, a feature outside the
        extent, or features that overlap.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.survey.difference import difference
from pitstudio.survey.meshvolume import (
    box_mesh,
    frustum_mesh,
    frustum_volume,
    mesh_volume,
    prism_mesh,
    trapezoid_cut_volume,
)
from pitstudio.survey.scene import known_volume_scene

edge = st.floats(0.1, 1000.0)


# ----------------------------------------------------------------------------------------------------------------------
# closed forms and the scene
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-35")
def test_the_closed_forms_by_hand() -> None:
    assert frustum_volume(15.0, 7.0, 6.0) == pytest.approx(2 * math.pi * 379, rel=1e-12)
    assert frustum_volume(3.0, 3.0, 2.0) == pytest.approx(math.pi * 9 * 2, rel=1e-12)  # a cylinder
    assert trapezoid_cut_volume(60.0, 4.0, 8.0, 16.0) == 2880.0
    assert trapezoid_cut_volume(10.0, 2.0, 5.0, 5.0) == 100.0  # a rectangular trench


@pytest.mark.req("FR-017-35")
def test_the_scene_has_the_exact_closed_form_volumes() -> None:
    scene = known_volume_scene()
    assert scene.frustum_volume_m3 == pytest.approx(2 * math.pi * 379, rel=1e-12)
    assert scene.cut_volume_m3 == pytest.approx(2880.0, rel=1e-12)


@pytest.mark.req("FR-017-35")
def test_the_closed_meshes_of_the_scene_have_the_divergence_theorem_volumes_of_the_closed_forms() -> None:
    scene = known_volume_scene()
    theta = 2 * math.pi / 720
    assert mesh_volume(*scene.meshes["frustum"]) == pytest.approx(
        scene.frustum_volume_m3 * math.sin(theta) / theta, rel=1e-12
    )
    assert mesh_volume(*scene.meshes["frustum"]) == pytest.approx(
        scene.frustum_volume_m3, rel=2e-5
    )  # tessellation only
    assert mesh_volume(*scene.meshes["trench"]) == pytest.approx(scene.cut_volume_m3, rel=1e-12)


@pytest.mark.req("FR-017-35")
def test_the_surfaces_are_rasterised_at_0_25_m_and_the_floor_is_the_gridding_error_of_the_exact_surface() -> None:
    scene = known_volume_scene()
    assert scene.before.cell_size_m == scene.after.cell_size_m == 0.25
    assert scene.before.z.shape == scene.after.z.shape == (800, 800)
    assert np.all(scene.before.z == 0.0)
    result = difference(scene.before, scene.after)
    area = 0.25**2
    d = scene.after.z - scene.before.z
    fill_grid = area * float(np.maximum(d, 0).sum())
    cut_grid = area * float(np.maximum(-d, 0).sum())
    assert result.v_fill == pytest.approx(fill_grid, rel=1e-10)
    assert result.v_cut == pytest.approx(cut_grid, rel=1e-10)
    assert scene.floor["fill_pct"] == pytest.approx(
        100 * (fill_grid - scene.frustum_volume_m3) / scene.frustum_volume_m3, abs=1e-9
    )
    assert scene.floor["cut_pct"] == pytest.approx(
        100 * (cut_grid - scene.cut_volume_m3) / scene.cut_volume_m3, abs=1e-9
    )
    assert abs(scene.floor["fill_pct"]) < 0.5  # a smooth cone on a 0.25 m grid: well below one percent
    assert abs(scene.floor["cut_pct"]) < 0.5


@pytest.mark.req("FR-017-35")
def test_a_coarser_grid_has_a_larger_floor_than_the_survey_grid() -> None:
    fine, coarse = known_volume_scene(cell_m=0.25), known_volume_scene(cell_m=4.0)
    assert abs(coarse.floor["fill_pct"]) > abs(fine.floor["fill_pct"])


@pytest.mark.req("FR-017-35")
def test_the_frustum_heights_follow_the_cone_exactly_at_cell_centres() -> None:
    scene = known_volume_scene()
    cx, cy = 60.0, 100.0
    for row, col in [(400, 240), (400, 240 + 20), (400, 240 + 36), (400, 240 + 60), (400, 240 + 61)]:
        x, y = (col + 0.5) * 0.25, (row + 0.5) * 0.25
        rho = math.hypot(x - cx, y - cy)
        expected = 6.0 * min(1.0, max(0.0, (15.0 - rho) / (15.0 - 7.0)))
        assert scene.after.z[row, col] == pytest.approx(expected, abs=1e-9)


@pytest.mark.req("FR-017-35")
@pytest.mark.parametrize(
    "bad",
    [
        {"frustum": {"centre": (60, 100), "r_bottom": 5, "r_top": 7, "height": 6}},
        {"frustum": {"centre": (60, 100), "r_bottom": 15, "r_top": 7, "height": 0}},
        {"frustum": {"centre": (10, 10), "r_bottom": 15, "r_top": 7, "height": 6}},
        {"trench": {"x_centre": 150, "y_start": 70, "length": 60, "depth": 4, "bottom_width": 16, "top_width": 8}},
        {"trench": {"x_centre": 60, "y_start": 70, "length": 60, "depth": 4, "bottom_width": 8, "top_width": 16}},
    ],
    ids=["cone-inverted", "zero-height", "outside-extent", "trench-inverted", "overlap"],
)
def test_invalid_scene_parameters_are_refused(bad: dict) -> None:
    with pytest.raises(ValueError, match=r"."):
        known_volume_scene(**bad)


# ----------------------------------------------------------------------------------------------------------------------
# P-017-15
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("P-017-15")
@settings(max_examples=200, deadline=None)
@given(lx=edge, ly=edge, lz=edge)
def test_the_volume_of_a_box_mesh_is_lx_ly_lz(lx, ly, lz):
    assert mesh_volume(*box_mesh(lx, ly, lz)) == pytest.approx(lx * ly * lz, rel=1e-12)


@pytest.mark.req("P-017-15")
@settings(max_examples=200, deadline=None)
@given(a=edge)
def test_the_volume_of_a_cube_mesh_is_a_cubed(a):
    assert mesh_volume(*box_mesh(a, a, a)) == pytest.approx(a**3, rel=1e-12)


@pytest.mark.req("P-017-15")
@settings(max_examples=200, deadline=None)
@given(a=edge, b=edge, h=edge)
def test_the_volume_of_a_triangular_prism_mesh_is_base_area_times_height(a, b, h):
    triangle = np.array([[0.0, 0.0], [a, 0.0], [0.0, b]])
    assert mesh_volume(*prism_mesh(triangle, h)) == pytest.approx(a * b / 2 * h, rel=1e-12)


@pytest.mark.req("P-017-15")
@settings(max_examples=200, deadline=None)
@given(big=edge, small_frac=st.floats(0.05, 0.95), h=edge, n=st.integers(3, 200))
def test_the_volume_of_a_polygonal_frustum_mesh_is_its_closed_form(big, small_frac, h, n):
    r = big * small_frac
    area = lambda radius: n / 2 * radius**2 * math.sin(2 * math.pi / n)  # noqa: E731
    expected = h / 3 * (area(big) + math.sqrt(area(big) * area(r)) + area(r))
    assert mesh_volume(*frustum_mesh(big, r, h, n)) == pytest.approx(expected, rel=1e-12)
    theta = 2 * math.pi / n
    assert mesh_volume(*frustum_mesh(big, r, h, n)) == pytest.approx(
        frustum_volume(big, r, h) * math.sin(theta) / theta, rel=1e-12
    )


@pytest.mark.req("P-017-15")
@settings(max_examples=200, deadline=None)
@given(
    lx=edge,
    ly=edge,
    lz=edge,
    shift=st.tuples(st.floats(-10, 10), st.floats(-10, 10), st.floats(-10, 10)),
)
def test_the_volume_is_unchanged_by_translation(lx, ly, lz, shift):
    v, f = box_mesh(lx, ly, lz)
    scale = max(lx, ly, lz)
    moved = v + np.array(shift) * scale  # up to ten edge lengths away from the origin
    assert mesh_volume(moved, f) == pytest.approx(mesh_volume(v, f), rel=1e-12)


@pytest.mark.req("P-017-15")
@settings(max_examples=200, deadline=None)
@given(big=edge, small_frac=st.floats(0.05, 0.95), h=edge, k=st.floats(0.1, 10.0))
def test_the_volume_scales_as_k_cubed(big, small_frac, h, k):
    v, f = frustum_mesh(big, big * small_frac, h, 36)
    assert mesh_volume(v * k, f) == pytest.approx(k**3 * mesh_volume(v, f), rel=1e-12)


@pytest.mark.req("P-017-15")
def test_open_or_malformed_meshes_are_refused() -> None:
    v, f = box_mesh(1.0, 2.0, 3.0)
    with pytest.raises(ValueError, match="closed"):
        mesh_volume(v, f[1:])  # a face missing: the mesh is open
    with pytest.raises(ValueError, match=r"."):
        mesh_volume(v, np.vstack([f[:-1], [[0, 1, 99]]]))  # an index out of range
    bad = v.copy()
    bad[3, 1] = np.nan
    with pytest.raises(ValueError, match="finite"):
        mesh_volume(bad, f)
    with pytest.raises(ValueError, match=r"."):
        mesh_volume(v, f[:3])

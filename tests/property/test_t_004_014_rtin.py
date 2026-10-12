# ruff: noqa: E501, PT018, PT011
"""T-004-014: right-triangulated irregular network (RTIN) meshes per level of detail with the max-error bound.

Requirements: FR-004-06, P-004-01.

Oracle: brute-force evaluation of the mesh against every grid sample by barycentric interpolation in float64
(`scene_kit.mesh_errors`, independent of the mesher); exact analytical cases (a flat or tilted plane needs only the two
root triangles); exact metamorphic relations on dyadic heights (z shift, power-of-two scaling) and monotonicity in
`max_error`. Tolerance for the bound: `max_error` + 2.5e-4 m (plan.md: float32 vertex rounding at |z| <= 1000 m).

Expected API (package `pitstudio_studio.scene.terrain`, studio environment):
- `terrain.rtin.build_rtin(heights, max_error) -> Mesh` for a float64 array of (2^k + 1)^2 samples (k >= 1; NaN = nodata).
  `Mesh` has `rc` (int32 [n, 2], the (row, col) grid position of each vertex), `z` (float32 [n], vertex heights, the
  sample values cast to float32) and `triangles` (int32 [m, 3] vertex indices). The triangles tile the sampled square
  without overlap (total area (2^k)^2) and no triangle contains (closed) a nodata sample. A non-square or
  non-(2^k + 1) shape, a non-positive or non-finite `max_error` raises `ValueError`.
- `terrain.rtin.DEFAULT_MAX_ERROR_M == (0.25, 1.0, 4.0)` (LOD 0, 1, 2).
- `terrain.rtin.build_lods(heights, lods) -> dict[int, Mesh]` where `lods` is the SceneSpec `terrain.lods` list.
"""

from __future__ import annotations

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
from pitstudio_studio.scene import terrain  # noqa: E402

TOL = 2.5e-4


def _check_bound(heights: np.ndarray, max_error: float) -> terrain.rtin.Mesh:
    mesh = terrain.rtin.build_rtin(heights, max_error)
    worst, covered, area = kit.mesh_errors(mesh.rc, mesh.z, mesh.triangles, heights)
    n = heights.shape[0]
    assert area == pytest.approx((n - 1) ** 2, abs=1e-9)  # tiles the square exactly
    assert covered.all()  # every sample of a fully valid grid lies on the mesh
    assert worst <= max_error + TOL, (worst, max_error)
    return mesh


@pytest.mark.req("FR-004-06")
def test_defaults_per_lod_are_the_spec_values() -> None:
    assert tuple(terrain.rtin.DEFAULT_MAX_ERROR_M) == (0.25, 1.0, 4.0)


@pytest.mark.req("FR-004-06")
@pytest.mark.parametrize("k", [1, 3, 5])
def test_flat_grid_needs_only_the_two_root_triangles(k: int) -> None:
    mesh = terrain.rtin.build_rtin(np.full((2**k + 1,) * 2, 123.5), 0.05)
    assert len(mesh.triangles) == 2
    assert {tuple(map(int, rc)) for rc in mesh.rc} == {(0, 0), (0, 2**k), (2**k, 0), (2**k, 2**k)}


@pytest.mark.req("FR-004-06")
def test_tilted_plane_is_exact_with_two_triangles() -> None:
    n = 33
    rr, cc = np.mgrid[0:n, 0:n].astype(np.float64)
    mesh = terrain.rtin.build_rtin(0.5 * cc - 0.25 * rr + 7.0, 0.05)
    assert len(mesh.triangles) == 2


@pytest.mark.req("FR-004-06")
def test_single_peak_is_refined_where_the_error_is_and_meets_the_bound() -> None:
    h = np.zeros((17, 17))
    h[8, 8] = 10.0  # a spike: needs the vertex at the centre; the corners alone err by 10 m at (8, 8)
    mesh = _check_bound(h, 0.5)
    assert any(tuple(map(int, rc)) == (8, 8) for rc in mesh.rc)
    assert len(mesh.triangles) < 2 * 16 * 16  # coarser than the full grid


@pytest.mark.req("FR-004-06")
def test_nodata_cells_are_never_inside_a_triangle() -> None:
    h = kit.fbm_grid(4, seed=2, amplitude=20.0)
    h[5:8, 9:11] = np.nan
    mesh = terrain.rtin.build_rtin(h, 0.25)
    _, covered, _ = kit.mesh_errors(mesh.rc, mesh.z, mesh.triangles, h)
    assert not covered[np.isnan(h)].any()
    worst, _, _ = kit.mesh_errors(mesh.rc, mesh.z, mesh.triangles, h)
    assert worst <= 0.25 + TOL  # the covered valid samples keep the bound
    assert len(mesh.triangles) > 0


@pytest.mark.req("FR-004-06")
def test_one_mesh_per_lod_with_its_declared_bound() -> None:
    h = kit.fbm_grid(6, seed=4, amplitude=60.0)
    lods = [
        {"lod": 0, "max_error_m": 0.25, "skirt_depth_m": 0.5},
        {"lod": 1, "max_error_m": 1.0, "skirt_depth_m": 2.0},
        {"lod": 2, "max_error_m": 4.0, "skirt_depth_m": 8.0},
    ]
    meshes = terrain.rtin.build_lods(h, lods)
    assert sorted(meshes) == [0, 1, 2]
    counts = []
    for spec in lods:
        m = meshes[spec["lod"]]
        worst, covered, _ = kit.mesh_errors(m.rc, m.z, m.triangles, h)
        assert covered.all() and worst <= spec["max_error_m"] + TOL
        counts.append(len(m.triangles))
    assert counts[0] >= counts[1] >= counts[2]


@pytest.mark.req("FR-004-06")
@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_bad_max_error_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError):
        terrain.rtin.build_rtin(np.zeros((9, 9)), bad)


@pytest.mark.req("FR-004-06")
@pytest.mark.parametrize("shape", [(8, 8), (9, 5), (10, 10), (1, 1), (0, 0)])
def test_shapes_other_than_2k_plus_1_squares_are_rejected(shape: tuple[int, int]) -> None:
    with pytest.raises(ValueError):
        terrain.rtin.build_rtin(np.zeros(shape), 1.0)


@pytest.mark.req("P-004-01")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    k=st.sampled_from([3, 4, 5, 5, 6, 6, 7]),
    seed=st.integers(0, 2**31 - 1),
    kind=st.sampled_from(["fbm", "stepped"]),
    amplitude=st.floats(1.0, 400.0),
    base=st.floats(-600.0, 600.0),
    max_error=st.floats(0.05, 8.0),
)
def test_mesh_interpolates_every_sample_within_max_error(
    k: int, seed: int, kind: str, amplitude: float, base: float, max_error: float
) -> None:
    """P-004-01 on fractal and stepped-bench grids, heights within [-1000, 1000] m."""
    if kind == "fbm":
        h = kit.fbm_grid(k, seed, amplitude=amplitude, base=base)
    else:
        noise = np.random.default_rng(seed).normal(0, 0.02, (2**k + 1,) * 2)
        h = base + kit.stepped_bench_grid(k, height=min(amplitude, 30.0)) + noise
    assert np.abs(h).max() <= 1000.0
    _check_bound(h, max_error)


@pytest.mark.req("P-004-01")
@settings(max_examples=3, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1), max_error=st.sampled_from([0.05, 0.25, 1.0, 4.0]))
def test_bound_holds_on_the_largest_tile_k8(seed: int, max_error: float) -> None:
    _check_bound(kit.fbm_grid(8, seed, amplitude=300.0), max_error)


@pytest.mark.req("P-004-01")
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1), e1=st.floats(0.05, 4.0), factor=st.floats(1.0, 4.0))
def test_larger_max_error_never_adds_triangles(seed: int, e1: float, factor: float) -> None:
    """Metamorphic: relaxing the bound can only coarsen the mesh."""
    h = kit.fbm_grid(5, seed, amplitude=80.0)
    fine = terrain.rtin.build_rtin(h, e1)
    coarse = terrain.rtin.build_rtin(h, e1 * factor)
    assert len(coarse.triangles) <= len(fine.triangles)


@pytest.mark.req("P-004-01")
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1), shift=st.integers(-512, 512), exponent=st.integers(-3, 3))
def test_triangulation_is_invariant_to_z_shift_and_power_of_two_scaling(seed: int, shift: int, exponent: int) -> None:
    """Dyadic heights (multiples of 1/16, |z| < 64): shifting by an integer or scaling by 2^e changes no decision."""
    h = np.round(np.random.default_rng(seed).uniform(-32, 32, (17, 17)) * 16) / 16
    ref = _tri_set(terrain.rtin.build_rtin(h, 1.0))
    assert _tri_set(terrain.rtin.build_rtin(h + float(shift), 1.0)) == ref
    assert _tri_set(terrain.rtin.build_rtin(h * 2.0**exponent, 2.0**exponent)) == ref


def _tri_set(mesh: terrain.rtin.Mesh) -> set[frozenset[tuple[int, int]]]:
    """Triangulation as a set of vertex-position triples, independent of vertex and triangle numbering."""
    return {frozenset((int(r), int(c)) for r, c in mesh.rc[tri]) for tri in mesh.triangles}

"""T-005-016 - FR-005-13: repose-angle measurement on analytic cones, ridges and particle-sampled cones.

Oracle: the angle used to generate each surface (plan 005 test strategy: "analytical cones and ridges generated in
the test (tan of the known angle)"). Noise-free fields: h(x, y) = max(0, H - rho tan(alpha)) with rho the distance
to the cone axis, or rho = |coordinate - crest| across a ridge; the expected result is alpha within 0.1 deg.
Particle-sampled cones: spheres of diameter d whose centres sit on a jittered horizontal lattice of pitch d/4 and
whose tops lie between the analytic surface and d/2 below it (uniform, seeded); expected alpha within 0.5 deg.
Fixture check done while writing this test (scratch, outside the repository): a straightforward implementation of
the FR-005-13 procedure recovers 20, 35 and 50 deg on these fixtures within 0.05 deg, both when each sphere only
marks the cell holding its centre and when each sphere's cap is rasterised over its footprint.

Expected public API (module `pitstudio_studio.physics.measure`):
    surface_height_field(positions, radii, spacing, *, origin=None) -> HeightField
        HeightField: .heights (nx, ny) float64, .spacing (float), .origin (x0, y0); cell (i, j) covers
        [x0 + i s, x0 + (i + 1) s) x [y0 + j s, y0 + (j + 1) s); its height is the top z + r of the highest particle
        in it (a particle contributes at least to the cell holding its centre); cells without particles are NaN;
        origin defaults to the lower corner of the particles' footprint
    repose_angle_from_heightfield(heights, spacing, *, origin=(0.0, 0.0), geometry="cone", axis_xy=None,
                                  ridge_along="x", crest=0.0) -> float
        heights[i, j] is the surface at the cell centre (x0 + (i + 1/2) s, y0 + (j + 1/2) s), base level 0, NaN = no
        data; geometry "cone" averages radially about axis_xy (required), "ridge" averages along the ridge
        direction `ridge_along` ("x" or "y") about the crest coordinate `crest`; fits a line to the flank where
        0.1 h_max <= h <= 0.8 h_max; returns atan(|slope|) in degrees
    repose_angle(positions, radii, *, geometry="cone", axis_xy=None, ridge_along="x", crest=0.0,
                 spacing=None) -> float
        builds the height field with spacing <= d/2 (default d/2, d the particle diameter) and measures it as above
    Refusals raise ValueError whose message names the offending input: "spacing" (coarser than d/2), "positions"
    (none, or non-finite), "radii" (non-finite or <= 0), "axis_xy" (a cone without an axis), "heights" (no data).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)

from pitstudio_studio.physics.measure import (  # noqa: E402
    repose_angle,
    repose_angle_from_heightfield,
    surface_height_field,
)

ANGLES = [20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0]  # the FR-005-13 range, 5 deg apart
D = 0.01  # particle diameter, m


def analytic_field(alpha: float, height: float, spacing: float, *, geometry: str, axis=(0.0, 0.0), along="x"):
    """Noise-free surface sampled at cell centres; returns (heights, origin)."""
    t = math.tan(math.radians(alpha))
    reach = height / t + 5.0 * spacing
    ax, ay = axis
    x0, y0 = ax - reach, ay - reach
    n = math.ceil(2.0 * reach / spacing)
    xc = x0 + (np.arange(n) + 0.5) * spacing
    yc = y0 + (np.arange(n) + 0.5) * spacing
    xx, yy = np.meshgrid(xc, yc, indexing="ij")
    rho = distance_to_axis(xx, yy, ax, ay, geometry=geometry, along=along)
    return np.maximum(0.0, height - rho * t), (x0, y0)


def distance_to_axis(xx, yy, ax, ay, *, geometry: str, along: str) -> np.ndarray:
    """Distance to the cone axis, or across a ridge running along `along` with its crest through (ax, ay)."""
    if geometry == "cone":
        return np.hypot(xx - ax, yy - ay)
    if along == "x":
        return np.abs(yy - ay)
    return np.abs(xx - ax)


def sampled_pile(alpha: float, *, ridge: bool, seed: int) -> np.ndarray:
    """Sphere centres (N, 3) of a cone (axis at the origin) or a ridge (along y, crest x = 0) of diameter-d spheres."""
    rng = np.random.default_rng(seed)
    t = math.tan(math.radians(alpha))
    height = 15.0 * D
    rb = height / t
    pitch = D / 4.0
    xs = np.arange(-rb - 2.0 * D, rb + 2.0 * D, pitch)
    ys = np.arange(0.0, 20.0 * D, pitch) if ridge else xs
    xx, yy = np.meshgrid(xs, ys, indexing="ij")
    xx = xx + rng.uniform(-pitch / 2.0, pitch / 2.0, xx.shape)
    yy = yy + rng.uniform(-pitch / 2.0, pitch / 2.0, yy.shape)
    rho = np.abs(xx) if ridge else np.hypot(xx, yy)
    surface = height - rho * t
    keep = surface > 0.0
    top = surface[keep] - rng.uniform(0.0, D / 2.0, int(keep.sum()))
    return np.c_[xx[keep], yy[keep], top - D / 2.0]


@pytest.mark.req("FR-005-13")
@pytest.mark.parametrize("alpha", ANGLES)
def test_noise_free_cone(alpha: float) -> None:
    h, origin = analytic_field(alpha, 0.15, 1.0e-3, geometry="cone", axis=(0.3, -0.2))
    got = repose_angle_from_heightfield(h, 1.0e-3, origin=origin, geometry="cone", axis_xy=(0.3, -0.2))
    assert abs(got - alpha) <= 0.1


@pytest.mark.req("FR-005-13")
@pytest.mark.parametrize("alpha", ANGLES)
@pytest.mark.parametrize("along", ["x", "y"])
def test_noise_free_ridge(alpha: float, along: str) -> None:
    axis = (0.0, 0.25)
    crest = axis[1] if along == "x" else axis[0]
    h, origin = analytic_field(alpha, 0.15, 1.0e-3, geometry="ridge", axis=axis, along=along)
    got = repose_angle_from_heightfield(h, 1.0e-3, origin=origin, geometry="ridge", ridge_along=along, crest=crest)
    assert abs(got - alpha) <= 0.1


@pytest.mark.req("FR-005-13")
@settings(max_examples=200, deadline=None)  # thresholds.yaml property_tests.ci_examples_per_test
@given(
    alpha=st.floats(20.0, 50.0),
    height=st.floats(0.05, 5.0),
    cells_across=st.integers(150, 400),
    ax=st.floats(-100.0, 100.0),
    ay=st.floats(-100.0, 100.0),
    ridge=st.booleans(),
)
def test_noise_free_surfaces_any_size_and_position(alpha, height, cells_across, ax, ay, ridge) -> None:
    spacing = 2.0 * height / math.tan(math.radians(alpha)) / cells_across
    geometry = "ridge" if ridge else "cone"
    h, origin = analytic_field(alpha, height, spacing, geometry=geometry, axis=(ax, ay), along="x")
    if ridge:
        got = repose_angle_from_heightfield(h, spacing, origin=origin, geometry="ridge", ridge_along="x", crest=ay)
    else:
        got = repose_angle_from_heightfield(h, spacing, origin=origin, geometry="cone", axis_xy=(ax, ay))
    assert abs(got - alpha) <= 0.1


@pytest.mark.req("FR-005-13")
@pytest.mark.parametrize("alpha", [20.0, 30.0, 40.0, 50.0])
def test_cone_sampled_with_particles(alpha: float) -> None:
    pos = sampled_pile(alpha, ridge=False, seed=int(alpha))
    radii = np.full(len(pos), D / 2.0)
    got = repose_angle(pos, radii, geometry="cone", axis_xy=(0.0, 0.0))
    assert abs(got - alpha) <= 0.5


@pytest.mark.req("FR-005-13")
@pytest.mark.parametrize("alpha", [20.0, 35.0, 50.0])
def test_ridge_sampled_with_particles(alpha: float) -> None:
    pos = sampled_pile(alpha, ridge=True, seed=100 + int(alpha))
    radii = np.full(len(pos), D / 2.0)
    got = repose_angle(pos, radii, geometry="ridge", ridge_along="y", crest=0.0)
    assert abs(got - alpha) <= 0.5


@pytest.mark.req("FR-005-13")
def test_explicit_spacing_up_to_half_a_diameter() -> None:
    pos = sampled_pile(35.0, ridge=False, seed=7)
    radii = np.full(len(pos), D / 2.0)
    for spacing in (D / 2.0, D / 3.0):
        assert abs(repose_angle(pos, radii, geometry="cone", axis_xy=(0.0, 0.0), spacing=spacing) - 35.0) <= 0.5


@pytest.mark.req("FR-005-13")
def test_spacing_coarser_than_half_a_diameter_is_refused() -> None:
    pos = sampled_pile(35.0, ridge=False, seed=7)
    radii = np.full(len(pos), D / 2.0)
    with pytest.raises(ValueError, match="spacing"):
        repose_angle(pos, radii, geometry="cone", axis_xy=(0.0, 0.0), spacing=0.75 * D)


@pytest.mark.req("FR-005-13")
def test_height_field_holds_the_top_of_the_highest_particle() -> None:
    s = D / 2.0
    # three spheres stacked in the cell [0, s) x [0, s); one sphere alone in the cell [4s, 5s) x [4s, 5s)
    pos = np.array([[s / 2, s / 2, 0.005], [s / 2, s / 2, 0.015], [s / 2, s / 2, 0.025], [4.5 * s, 4.5 * s, 0.005]])
    radii = np.full(4, D / 2.0)
    hf = surface_height_field(pos, radii, s, origin=(0.0, 0.0))
    heights = np.asarray(hf.heights)
    assert hf.spacing == s
    assert tuple(hf.origin) == (0.0, 0.0)
    assert heights[0, 0] == pytest.approx(0.025 + D / 2.0, rel=1e-6)
    assert heights[4, 4] == pytest.approx(0.005 + D / 2.0, rel=1e-6)
    assert heights.dtype == np.float64


@pytest.mark.req("FR-005-13")
@pytest.mark.parametrize(
    ("case", "field"),
    [
        ("empty", "positions"),
        ("nan-position", "positions"),
        ("inf-position", "positions"),
        ("nan-radius", "radii"),
        ("zero-radius", "radii"),
    ],
)
def test_hostile_particle_inputs_are_refused(case: str, field: str) -> None:
    pos = sampled_pile(35.0, ridge=False, seed=3)[:500].copy()
    radii = np.full(len(pos), D / 2.0)
    if case == "empty":
        pos, radii = np.zeros((0, 3)), np.zeros(0)
    elif case == "nan-position":
        pos[10, 2] = math.nan
    elif case == "inf-position":
        pos[10, 0] = math.inf
    elif case == "nan-radius":
        radii[3] = math.nan
    elif case == "zero-radius":
        radii[3] = 0.0
    with pytest.raises(ValueError, match=field):
        repose_angle(pos, radii, geometry="cone", axis_xy=(0.0, 0.0))


@pytest.mark.req("FR-005-13")
def test_cone_without_an_axis_is_refused() -> None:
    h, origin = analytic_field(30.0, 0.15, 1.0e-3, geometry="cone")
    with pytest.raises(ValueError, match="axis_xy"):
        repose_angle_from_heightfield(h, 1.0e-3, origin=origin, geometry="cone", axis_xy=None)


@pytest.mark.req("FR-005-13")
def test_field_without_data_is_refused() -> None:
    with pytest.raises(ValueError, match="heights"):
        repose_angle_from_heightfield(np.full((50, 50), np.nan), 1.0e-3, geometry="cone", axis_xy=(0.0, 0.0))

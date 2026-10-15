"""GNS v2 diagnosis (FR-011-05, P-011-06): the repose extractor is not the cause of the flat reference piles.

The v1 reference piles measured 1 to 10 degrees against 27.2 degrees of the 3-D DEM of the same material. Before
the physics
was touched, the extractor was checked against an independent geometric fit written here (a different binning, d /
2 columns
instead of 2 d bins, and an orthogonal least-squares line instead of a regression of height on abscissa) on packed discs
whose free surface has a known slope, and its mirror symmetry was checked on asymmetric piles.

Oracles: heaps of equal discs on a hexagonal lattice (spacing d), every lattice point kept that lies below the
analytic line
y = H - tan(theta) |x - x_ref| and above the floor (the stair-stepped free surface of a real settled
pile), for theta of 10,
18, 27.2 and 35 degrees; the lattice discretisation and the 2 d bins allow 1.5 degrees on the analytic angle, and
the two
independent measurements must agree within 1.0 degree (two binnings of a stair-stepped surface).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pitstudio.granular import observables as obs

D = 0.01


def lattice_heap(
    theta_deg: float, height_d: float, x_ref: float, *, both_flanks: bool, left_theta_deg: float | None = None
) -> np.ndarray:
    """Hexagonal-lattice disc centres under the analytic surface; rows at spacing d, a half-spacing shift on odd
    rows."""
    right = math.tan(math.radians(theta_deg))
    left = math.tan(math.radians(left_theta_deg if left_theta_deg is not None else theta_deg))
    h = height_d * D
    pts = []
    nrow = int(height_d / (math.sqrt(3) / 2.0)) + 1
    for j in range(nrow):
        y = D / 2 + j * D * math.sqrt(3) / 2.0
        shift = 0.5 * D if j % 2 else 0.0
        for i in range(-int(3 * height_d / right), int(3 * height_d / right)):
            x = x_ref + i * D + shift
            dx = x - x_ref
            if dx < 0 and not both_flanks:
                continue
            slope = right if dx >= 0 else left
            if y + D / 2 <= h - slope * abs(dx):  # the top of the disc lies under the analytic surface
                pts.append((x, y))
    pts = np.array(pts)
    pts[:, 0] += np.random.default_rng(7).uniform(-0.03, 0.03, len(pts)) * D  # no lattice offset sits on a bin edge
    return pts


def independent_repose(pos: np.ndarray, d: float, ref: float, sign: float) -> float:
    """d / 2 columns, the top of the highest disc per column, orthogonal least squares through the 20 to 80 percent
    band."""
    x = (pos[:, 0] - ref) * sign
    keep = x >= 0
    x, top = x[keep], pos[keep, 1] + d / 2
    col = np.floor(x / (d / 2)).astype(int)
    env = np.full(col.max() + 1, -np.inf)
    np.maximum.at(env, col, top)
    centre = (np.arange(len(env)) + 0.5) * d / 2
    ok = np.isfinite(env)
    centre, env = centre[ok], env[ok]
    h = env.max()
    sel = (env >= 0.2 * h) & (env <= 0.8 * h)
    pts = np.stack([centre[sel], env[sel]], axis=1)
    _, _, vt = np.linalg.svd(pts - pts.mean(axis=0), full_matrices=False)
    return math.degrees(math.atan(abs(vt[0][1] / vt[0][0])))


@pytest.mark.req("FR-011-05")
@pytest.mark.parametrize("theta", [10.0, 18.0, 27.2, 35.0])
def test_011_the_extractor_and_an_independent_fit_agree_on_a_packed_heap_of_known_slope(theta: float) -> None:
    pos = lattice_heap(theta, 40.0, 0.0, both_flanks=False)
    geo = {"column_width_m": 0.0}
    got = obs.repose_angle_deg(pos, d=D, family="column-collapse", geometry=geo)
    other = independent_repose(pos, D, 0.0, 1.0)
    assert abs(got - theta) < 1.5
    assert abs(other - theta) < 1.5
    assert abs(got - other) < 1.0


@pytest.mark.req("FR-011-05")
def test_011_a_pile_and_its_mirror_image_have_the_same_repose_and_it_is_the_mean_of_the_two_flanks() -> None:
    pos = lattice_heap(20.0, 40.0, 0.3, both_flanks=True, left_theta_deg=30.0)
    mirror = pos.copy()
    mirror[:, 0] = 2 * 0.3 - mirror[:, 0]  # reflect about the pour point
    geo = {"pour_point_x_m": 0.3}
    a = obs.repose_angle_deg(pos, d=D, family="pile-formation", geometry=geo)
    b = obs.repose_angle_deg(mirror, d=D, family="pile-formation", geometry=geo)
    assert a == pytest.approx(b, abs=1e-9)
    flanks = 0.5 * (independent_repose(pos, D, 0.3, 1.0) + independent_repose(pos, D, 0.3, -1.0))
    assert abs(a - 25.0) < 1.5
    assert abs(a - flanks) < 1.0


@pytest.mark.req("FR-011-05")
def test_011_a_flat_layer_reads_as_a_flat_pile_not_as_an_extractor_artefact() -> None:
    """The v1 failure mode: a 2-D pile whose flank is lower than 3 degrees must be reported as such by both
    measurements."""
    pos = lattice_heap(2.0, 32.0, 0.0, both_flanks=False)
    got = obs.repose_angle_deg(pos, d=D, family="dump-over-crest", geometry={"crest_x_m": 0.0})
    other = independent_repose(pos, D, 0.0, 1.0)
    assert 0.0 <= got < 3.5
    assert abs(got - other) < 1.0

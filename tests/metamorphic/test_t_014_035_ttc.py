# ruff: noqa: E501
"""T-014-035: time to collision between oriented footprints.

Requirements: FR-014-34, P-014-08.

Spec: specs/014-robot-learning/spec.md FR-014-34: "TTC between two agents shall be r / (-r_dot) when r_dot < 0 and +infinity
otherwise, with r (m) the gap between their oriented 2-D footprints (0 at contact) and r_dot the relative velocity projected
on the unit vector between the closest points." P-014-08: (MR1) a common rigid motion of both agents leaves TTC unchanged;
(MR2) scaling all positions and velocities by the same k leaves TTC unchanged; (MR3) scaling velocities only by k divides TTC by
k; (MR4) swapping the agents leaves TTC unchanged; non-closing pairs give +infinity. Footprints 2-15 m, speeds 0-20 m/s,
rtol 1e-12.

Oracle: closed-form gaps of rectangles (hand calculations below) and the closed-form TTC of three geometries:
 - head-on, axis aligned: gap = d - (L_a + L_b) / 2, closing speed |v_a - v_b|, TTC = gap / closing speed;
 - corner to corner: A = 10 x 4 m at the origin (x in [-5, 5], y in [-2, 2]) moving at (5, 0) m/s, B = 4 x 2 m centred (20, 15)
   with its long axis along y (x in [19, 21], y in [13, 17]) moving at (0, -3) m/s. The closest points are the corners
   (5, 2) and (19, 13): r = sqrt(14^2 + 11^2) = sqrt(317), n = (14, 11) / r, r_dot = (v_b - v_a) . n = (-5 * 14 - 3 * 11) / r =
   -103 / r, so TTC = r / (-r_dot) = 317 / 103 = 3.0776699 s;
 - a unit square and a 45-degree diamond: gap = 3 - sqrt(2).
The relations are the metamorphic relations above, evaluated by Hypothesis (>= 200 examples) with the transforms written here.
MR2 scales the footprint sizes together with the positions (a footprint that does not scale breaks r -> k r).

Expected API of the implementation (module `pitstudio.robots.ttc`, NumPy float64, SI units):
    Agent: frozen dataclass (x, y, yaw, vx, vy, length, width): centre (m), heading (rad, the long side of the footprint is
        along the heading), world velocity (m/s), footprint size (m)
    footprint_gap(a, b) -> float
        r >= 0 between the two oriented rectangles, 0 when they touch or overlap
    time_to_collision(a, b) -> float
        r / (-r_dot) when r_dot < 0, else math.inf; r_dot = (v_b - v_a) . n with n the unit vector from the closest point of a to
        the closest point of b. Overlapping footprints (a collision in progress) give 0.0.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pitstudio.robots.ttc import Agent, footprint_gap, time_to_collision


def agent(x, y, yaw, vx, vy, length, width) -> Agent:
    return Agent(float(x), float(y), float(yaw), float(vx), float(vy), float(length), float(width))


# ---------------------------------------------------------------------------------------------------- gaps
@pytest.mark.req("FR-014-34")
def test_gap_of_axis_aligned_rectangles_is_the_distance_between_facing_edges() -> None:
    a = agent(0, 0, 0, 0, 0, 10, 4)
    b = agent(40, 0, 0, 0, 0, 4, 2)
    assert footprint_gap(a, b) == pytest.approx(40.0 - 5.0 - 2.0, rel=1e-12)
    assert footprint_gap(b, a) == pytest.approx(33.0, rel=1e-12)


@pytest.mark.req("FR-014-34")
def test_gap_corner_to_corner_is_the_euclidean_distance_of_the_corners() -> None:
    a = agent(0, 0, 0, 0, 0, 10, 4)
    b = agent(20, 15, math.pi / 2, 0, 0, 4, 2)  # long axis along y: x in [19, 21], y in [13, 17]
    assert footprint_gap(a, b) == pytest.approx(math.sqrt(317.0), rel=1e-12)


@pytest.mark.req("FR-014-34")
def test_gap_of_a_unit_square_and_a_rotated_diamond() -> None:
    a = agent(0, 0, 0, 0, 0, 2, 2)
    b = agent(4, 0, math.pi / 4, 0, 0, 2, 2)  # leftmost vertex at x = 4 - sqrt(2)
    assert footprint_gap(a, b) == pytest.approx(3.0 - math.sqrt(2.0), rel=1e-12)


@pytest.mark.req("FR-014-34")
def test_gap_is_zero_at_contact_and_for_overlap() -> None:
    a = agent(0, 0, 0, 0, 0, 10, 4)
    assert footprint_gap(a, agent(7.0, 0, 0, 0, 0, 4, 2)) == pytest.approx(0.0, abs=1e-12)  # faces touch at x = 5
    assert footprint_gap(a, agent(6.0, 0, 0, 0, 0, 4, 2)) == 0.0  # overlapping
    assert footprint_gap(a, agent(0.0, 0, 0, 0, 0, 4, 2)) == 0.0  # contained


@pytest.mark.req("FR-014-34")
def test_gap_uses_the_heading_to_orient_the_long_side() -> None:
    a = agent(0, 0, 0, 0, 0, 10, 4)
    along_x = agent(0, 10, 0, 0, 0, 10, 4)  # long side along x: gap in y is 10 - 2 - 2 = 6
    along_y = agent(0, 10, math.pi / 2, 0, 0, 10, 4)  # long side along y: half-extent 5 in y: gap 10 - 2 - 5 = 3
    assert footprint_gap(a, along_x) == pytest.approx(6.0, rel=1e-12)
    assert footprint_gap(a, along_y) == pytest.approx(3.0, rel=1e-12)


# ----------------------------------------------------------------------------------------------- TTC values
@pytest.mark.req("FR-014-34")
def test_head_on_ttc_is_the_gap_over_the_closing_speed() -> None:
    a = agent(0, 0, 0, 5.0, 0, 10, 4)
    b = agent(40, 0, math.pi, -2.0, 0, 4, 2)
    assert time_to_collision(a, b) == pytest.approx(33.0 / 7.0, rel=1e-12)


@pytest.mark.req("FR-014-34")
def test_a_stationary_obstacle_ahead() -> None:
    a = agent(0, 0, 0, 10.0, 0, 10, 4)
    b = agent(60, 0, 0, 0.0, 0, 4, 2)  # gap 53 m, closing 10 m/s
    assert time_to_collision(a, b) == pytest.approx(5.3, rel=1e-12)


@pytest.mark.req("FR-014-34")
def test_corner_to_corner_crossing_ttc_is_317_over_103() -> None:
    a = agent(0, 0, 0, 5.0, 0, 10, 4)
    b = agent(20, 15, math.pi / 2, 0.0, -3.0, 4, 2)
    assert time_to_collision(a, b) == pytest.approx(317.0 / 103.0, rel=1e-12)


@pytest.mark.req("P-014-08")
@pytest.mark.parametrize(
    ("va", "vb"),
    [
        ((5.0, 0.0), (9.0, 0.0)),  # the one ahead is faster: opening
        ((5.0, 0.0), (5.0, 0.0)),  # same velocity: r_dot = 0
        ((0.0, 0.0), (0.0, 0.0)),  # both stationary
        ((0.0, 0.0), (0.0, 8.0)),  # relative velocity perpendicular to the line between the closest points
        ((-3.0, 0.0), (0.0, 0.0)),  # the first one drives away from the second
    ],
)
def test_non_closing_pairs_give_positive_infinity(va, vb) -> None:
    a = agent(0, 0, 0, va[0], va[1], 10, 4)
    b = agent(40, 0, 0, vb[0], vb[1], 4, 2)
    assert time_to_collision(a, b) == math.inf


@pytest.mark.req("FR-014-34")
def test_ttc_at_contact_is_zero_when_closing_and_infinite_when_not() -> None:
    a = agent(0, 0, 0, 5.0, 0, 10, 4)
    closing = agent(7.0, 0, math.pi, -2.0, 0, 4, 2)  # touching along x with a closing speed of 7 m/s
    # (a touching pair has no gap: TTC = 0 / 7 = 0); a 0.35 m gap gives 0.35 / 7 = 0.05 s
    assert time_to_collision(a, agent(7.35, 0, math.pi, -2.0, 0, 4, 2)) == pytest.approx(0.05, rel=1e-12)
    assert time_to_collision(a, closing) == pytest.approx(0.0, abs=1e-9)
    assert time_to_collision(a, agent(7.0, 0, 0, 9.0, 0, 4, 2)) == math.inf


@pytest.mark.req("FR-014-34")
def test_overlapping_footprints_give_zero() -> None:
    a = agent(0, 0, 0, 5.0, 0, 10, 4)
    assert time_to_collision(a, agent(3.0, 0, 0, 0.0, 0, 4, 2)) == 0.0


# --------------------------------------------------------------------------------------------- relations
sizes = st.floats(2.0, 15.0)
speeds = st.floats(0.0, 20.0)
angles = st.floats(-math.pi, math.pi)
coords = st.floats(-100.0, 100.0)


@st.composite
def pairs(draw):
    a = agent(draw(coords), draw(coords), draw(angles), 0, 0, draw(sizes), draw(sizes))
    sp_a, dir_a = draw(speeds), draw(angles)
    a = Agent(a.x, a.y, a.yaw, sp_a * math.cos(dir_a), sp_a * math.sin(dir_a), a.length, a.width)
    b0 = agent(draw(coords), draw(coords), draw(angles), 0, 0, draw(sizes), draw(sizes))
    sp_b, dir_b = draw(speeds), draw(angles)
    b = Agent(b0.x, b0.y, b0.yaw, sp_b * math.cos(dir_b), sp_b * math.sin(dir_b), b0.length, b0.width)
    assume(footprint_gap(a, b) > 0.5)  # separated, so that the closest-point direction is well defined
    return a, b


def transformed(ag: Agent, angle: float, sx: float, sy: float, k_len: float = 1.0, k_vel: float = 1.0) -> Agent:
    c, s = math.cos(angle), math.sin(angle)
    x = (c * ag.x - s * ag.y) * k_len + sx
    y = (s * ag.x + c * ag.y) * k_len + sy
    vx = (c * ag.vx - s * ag.vy) * k_vel
    vy = (s * ag.vx + c * ag.vy) * k_vel
    return Agent(x, y, ag.yaw + angle, vx, vy, ag.length * k_len, ag.width * k_len)


BIG = 1e8  # a TTC this large stands for "relative velocity numerically perpendicular": +inf or rounding noise


def same_ttc(got: float, want: float) -> None:
    if want > BIG:
        assert got > BIG
    elif got > BIG:
        assert want > BIG
    else:
        assert got == pytest.approx(want, rel=1e-9, abs=1e-12)


SETTINGS = settings(max_examples=300, deadline=None)


@pytest.mark.req("P-014-08")
@given(pairs(), angles, coords, coords)
@SETTINGS
def test_mr1_a_common_rigid_motion_leaves_ttc_unchanged(pair, angle, sx, sy) -> None:
    a, b = pair
    same_ttc(time_to_collision(transformed(a, angle, sx, sy), transformed(b, angle, sx, sy)), time_to_collision(a, b))
    assert footprint_gap(transformed(a, angle, sx, sy), transformed(b, angle, sx, sy)) == pytest.approx(
        footprint_gap(a, b), rel=1e-9
    )


@pytest.mark.req("P-014-08")
@given(pairs(), st.floats(0.1, 10.0))
@SETTINGS
def test_mr2_scaling_lengths_and_velocities_by_the_same_k_leaves_ttc_unchanged(pair, k) -> None:
    a, b = pair
    same_ttc(
        time_to_collision(transformed(a, 0.0, 0.0, 0.0, k, k), transformed(b, 0.0, 0.0, 0.0, k, k)),
        time_to_collision(a, b),
    )


@pytest.mark.req("P-014-08")
@given(pairs(), st.floats(0.1, 10.0))
@SETTINGS
def test_mr3_scaling_the_velocities_alone_by_k_divides_ttc_by_k(pair, k) -> None:
    a, b = pair
    base = time_to_collision(a, b)
    fast = time_to_collision(transformed(a, 0.0, 0.0, 0.0, 1.0, k), transformed(b, 0.0, 0.0, 0.0, 1.0, k))
    if base > BIG:
        assert fast > BIG
    else:
        assert fast == pytest.approx(base / k, rel=1e-9, abs=1e-12)


@pytest.mark.req("P-014-08")
@given(pairs())
@SETTINGS
def test_mr4_swapping_the_agents_leaves_ttc_unchanged(pair) -> None:
    a, b = pair
    same_ttc(time_to_collision(b, a), time_to_collision(a, b))
    assert footprint_gap(b, a) == pytest.approx(footprint_gap(a, b), rel=1e-12)


@pytest.mark.req("P-014-08")
@given(pairs())
@SETTINGS
def test_ttc_is_never_negative_and_never_nan(pair) -> None:
    a, b = pair
    t = time_to_collision(a, b)
    assert not math.isnan(t)
    assert t >= 0.0


@pytest.mark.req("FR-014-34")
@given(pairs())
@SETTINGS
def test_gap_never_exceeds_the_centre_distance_and_is_at_least_the_distance_minus_the_circumscribed_radii(pair) -> None:
    a, b = pair
    r = footprint_gap(a, b)
    d = float(np.hypot(a.x - b.x, a.y - b.y))
    ra = 0.5 * math.hypot(a.length, a.width)
    rb = 0.5 * math.hypot(b.length, b.width)
    assert r <= d + 1e-9
    assert r >= d - ra - rb - 1e-9

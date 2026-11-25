# ruff: noqa: E501
"""T-014-036: pure pursuit + PID baseline, its metamorphic relations and its hostile paths.

Requirements: FR-014-29, FR-014-31, P-014-07.

Spec: specs/014-robot-learning/spec.md FR-014-29: "The IL-1 baseline shall steer by pure pursuit - curvature kappa = 2 x / la^2 toward
the path point at look-ahead la, with x its lateral offset in the vehicle frame, and steering angle delta = arctan(L kappa) for
wheelbase L - with la = clamp(l0 + k_v v, l_min, l_max), and control speed by a discrete PID on v_lim with output clamping and
anti-windup; all gains are fixed in the task configuration before evaluation, and its outputs pass through the same action limits as
the policy." FR-014-31: "If the pure-pursuit look-ahead is <= 0 or non-finite, the path has fewer than two points, or no path point
lies beyond the look-ahead, then the controller shall use the path end as the goal point when the path is valid, and raise ValueError
otherwise." P-014-07: (MR1) mirroring the goal negates kappa and delta; (MR2) x = 0 gives kappa = 0; (MR3) scaling x and la by k scales
kappa by 1/k; hand calculation la = 20 m, x = 1 m, L = 6 m gives kappa = 0.005 1/m, delta = 1.7184 deg; rtol 1e-12.

Oracle: Coulter (1992), CMU-RI-TR-92-01, eqs. 2.1-2.2 as pinned in spec section 7 (kappa = 2 x / la^2); the hand calculation above
(arctan(0.03) = 0.0299910 rad = 1.71847 deg); the discrete PID difference equation u_k = Kp e_k + Ki sum_{j<=k} e_j dt written out for a
constant error (u_k = 0.5 + 0.02 k with Kp = 0.5, Ki = 0.2, dt = 0.1 until the output reaches 1); the action mapping by hand.

Reading of FR-014-31 (see the red report): the literal text makes the path end the fallback in all three cases whenever the path is
valid (at least two finite points), and ValueError only for an invalid path; a look-ahead that is <= 0 or non-finite therefore also falls
back to the path end. The tests follow that reading.

Expected API of the implementation (module `pitstudio.robots.baselines`, see T-014-027 for the scripted dig):
    lookahead_distance(speed, *, l0, kv, l_min, l_max) -> float        clamp(l0 + kv * speed, l_min, l_max)
    pure_pursuit_goal(path, lookahead) -> np.ndarray (2,)
        path: (N, 2) polyline in the vehicle frame (x forward, y left, metres), the first point near the origin. The goal is the first
        point, scanning the polyline from its start, at Euclidean distance `lookahead` from the origin (linear interpolation inside a
        segment); when the first path point is already farther than the look-ahead it is the goal. When no point of the path reaches
        the look-ahead, or the look-ahead is <= 0 or non-finite, the goal is the last path point. ValueError naming `path` when the
        path has fewer than two points, is not (N, 2), or holds a non-finite coordinate.
    curvature(lateral_offset, lookahead) -> float                       2 x / la^2 (ValueError naming `lookahead` unless it is finite and > 0)
    steering_angle(kappa, wheelbase) -> float                           arctan(wheelbase * kappa) (ValueError naming `wheelbase` unless > 0)
    PidSpeed(kp, ki, dt, out_min=-1.0, out_max=1.0): discrete PID (kd = 0) with .step(error) -> float and .reset()
        integral += error * dt (current error included), u = kp * error + ki * integral clamped to [out_min, out_max]; anti-windup: while
        the clamped output is saturated in the direction of the error the integral does not grow, so that a sign change of the error leaves
        saturation within one step. ValueError naming `dt` for dt <= 0 or non-finite, `out_min` for out_min >= out_max.
    PurePursuitPid(*, wheelbase, l0, kv, l_min, l_max, kp, ki, dt, max_steer_rate): .act(path, speed, v_target, steer_angle) ->
        np.ndarray (2,) = [steer-rate action, combined drive/brake action], each clipped to [-1, 1] (the policy's action limits):
        steer-rate action = (delta_cmd - steer_angle) / (dt * max_steer_rate) with delta_cmd from the goal and look-ahead
        lookahead_distance(speed, ...); combined action = PidSpeed.step(v_target - speed).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.robots.baselines import (
    PidSpeed,
    PurePursuitPid,
    curvature,
    lookahead_distance,
    pure_pursuit_goal,
    steering_angle,
)

# ---------------------------------------------------------------------------------------------------- P-014-07
SMALL = st.floats(2.0, 60.0)
OFFSET = st.floats(-20.0, 20.0)


@pytest.mark.req("P-014-07")
def test_the_hand_calculation_l_20_x_1_wheelbase_6() -> None:
    k = curvature(1.0, 20.0)
    assert k == pytest.approx(0.005, rel=1e-12)  # 2 * 1 / 400
    assert math.degrees(steering_angle(k, 6.0)) == pytest.approx(1.7184, abs=1e-4)  # arctan(0.03)
    assert steering_angle(k, 6.0) == pytest.approx(math.atan(0.03), rel=1e-12)


@pytest.mark.req("P-014-07")
@given(OFFSET, SMALL, st.floats(2.0, 12.0))
@settings(max_examples=300, deadline=None)
def test_mr1_mirroring_the_goal_negates_curvature_and_steering_angle(x, la, wheelbase) -> None:
    assert curvature(-x, la) == pytest.approx(-curvature(x, la), rel=1e-12, abs=0.0)
    assert steering_angle(curvature(-x, la), wheelbase) == pytest.approx(
        -steering_angle(curvature(x, la), wheelbase), rel=1e-12, abs=0.0
    )


@pytest.mark.req("P-014-07")
@given(SMALL, st.floats(2.0, 12.0))
@settings(max_examples=100, deadline=None)
def test_mr2_a_goal_straight_ahead_gives_zero_curvature_and_zero_steering(la, wheelbase) -> None:
    assert curvature(0.0, la) == 0.0
    assert steering_angle(curvature(0.0, la), wheelbase) == 0.0


@pytest.mark.req("P-014-07")
@given(OFFSET, SMALL, st.floats(0.1, 10.0))
@settings(max_examples=300, deadline=None)
def test_mr3_scaling_the_offset_and_the_lookahead_by_k_scales_curvature_by_one_over_k(x, la, k) -> None:
    assert curvature(k * x, k * la) == pytest.approx(curvature(x, la) / k, rel=1e-12, abs=1e-300)


@pytest.mark.req("FR-014-29")
@pytest.mark.parametrize(
    ("speed", "want"),
    [(0.0, 10.0), (4.0, 14.0), (10.0, 20.0), (30.0, 40.0), (100.0, 40.0), (-20.0, 5.0)],
)
def test_the_lookahead_is_clamped_between_l_min_and_l_max(speed, want) -> None:
    assert lookahead_distance(speed, l0=10.0, kv=1.0, l_min=5.0, l_max=40.0) == pytest.approx(want, rel=1e-15)


# ---------------------------------------------------------------------------------------------------- goal point
@pytest.mark.req("FR-014-29")
def test_the_goal_is_the_first_path_point_at_the_lookahead_distance() -> None:
    path = np.array(
        [[0.0, 0.0], [math.sqrt(399.0), 1.0], [40.0, 1.0]]
    )  # the second point is exactly 20 m from the origin
    goal = pure_pursuit_goal(path, 20.0)
    np.testing.assert_allclose(goal, [math.sqrt(399.0), 1.0], rtol=1e-12)
    assert curvature(float(goal[1]), 20.0) == pytest.approx(0.005, rel=1e-12)


@pytest.mark.req("FR-014-29")
def test_the_goal_is_interpolated_inside_a_segment() -> None:
    path = np.array([[0.0, 0.0], [100.0, 0.0]])
    np.testing.assert_allclose(pure_pursuit_goal(path, 20.0), [20.0, 0.0], atol=1e-12)
    slanted = np.array([[0.0, 0.0], [30.0, 1.5]])  # direction (30, 1.5) / sqrt(902.25)
    want = 20.0 * np.array([30.0, 1.5]) / math.sqrt(902.25)
    np.testing.assert_allclose(pure_pursuit_goal(slanted, 20.0), want, rtol=1e-12)


@pytest.mark.req("FR-014-29")
def test_the_goal_scan_starts_at_the_beginning_of_the_path() -> None:
    # a path that leaves the circle of radius 10, returns inside it and leaves again: the first crossing counts
    path = np.array([[0.0, 0.0], [20.0, 0.0], [0.0, 5.0], [30.0, 5.0]])
    goal = pure_pursuit_goal(path, 10.0)
    np.testing.assert_allclose(goal, [10.0, 0.0], atol=1e-12)


@pytest.mark.req("FR-014-29")
def test_a_first_point_already_beyond_the_lookahead_is_the_goal() -> None:
    path = np.array([[25.0, 3.0], [40.0, 3.0]])
    np.testing.assert_allclose(pure_pursuit_goal(path, 20.0), [25.0, 3.0], atol=1e-12)


@pytest.mark.req("FR-014-29")
@given(
    st.lists(st.tuples(st.floats(1.0, 15.0), st.floats(-0.4, 0.4)), min_size=8, max_size=20),
    st.floats(2.0, 30.0),
)
@settings(max_examples=200, deadline=None)
def test_property_the_goal_lies_on_the_path_at_the_lookahead_distance(steps, la) -> None:
    pts = [np.zeros(2)]
    h = 0.0
    for length, dh in steps:
        h += dh
        pts.append(pts[-1] + length * np.array([math.cos(h), math.sin(h)]))
    path = np.array(pts)
    reach = float(np.max(np.hypot(path[:, 0], path[:, 1])))
    goal = pure_pursuit_goal(path, la)
    if reach >= la:
        assert float(np.hypot(*goal)) == pytest.approx(la, rel=1e-9)
        d = np.min([_point_segment_distance(goal, path[i], path[i + 1]) for i in range(len(path) - 1)])
        assert d < 1e-9
    else:
        np.testing.assert_array_equal(goal, path[-1])


def _point_segment_distance(p, a, b) -> float:
    d = b - a
    t = min(max(float(np.dot(p - a, d)) / float(np.dot(d, d)), 0.0), 1.0)
    return float(np.linalg.norm(p - (a + t * d)))


# ---------------------------------------------------------------------------------------------------- FR-014-31
@pytest.mark.req("FR-014-31")
def test_a_path_that_never_reaches_the_lookahead_falls_back_to_the_path_end() -> None:
    path = np.array([[0.0, 0.0], [5.0, 0.5], [9.0, 1.0]])  # the farthest point is 9.06 m away
    np.testing.assert_array_equal(pure_pursuit_goal(path, 20.0), path[-1])


@pytest.mark.req("FR-014-31")
@pytest.mark.parametrize("bad", [0.0, -5.0, -1e-9, math.nan, math.inf, -math.inf])
def test_a_non_positive_or_non_finite_lookahead_with_a_valid_path_uses_the_path_end(bad) -> None:
    path = np.array([[0.0, 0.0], [30.0, 2.0], [60.0, 8.0]])
    np.testing.assert_array_equal(pure_pursuit_goal(path, bad), path[-1])


@pytest.mark.req("FR-014-31")
@pytest.mark.parametrize(
    "path",
    [
        np.zeros((0, 2)),
        np.array([[1.0, 2.0]]),
        np.zeros((5, 3)),
        np.zeros(6),
        np.array([[0.0, 0.0], [math.nan, 1.0]]),
        np.array([[0.0, 0.0], [10.0, math.inf]]),
        None,
    ],
    ids=["empty", "one-point", "xyz", "1d", "nan", "inf", "none"],
)
def test_an_invalid_path_raises_value_error_naming_path(path) -> None:
    with pytest.raises(ValueError, match=r"\bpath\b"):
        pure_pursuit_goal(path, 20.0)
    with pytest.raises(ValueError, match=r"\bpath\b"):
        pure_pursuit_goal(path, math.nan)  # an invalid path is invalid whatever the look-ahead


@pytest.mark.req("FR-014-31")
@pytest.mark.parametrize("bad", [0.0, -3.0, math.nan, math.inf])
def test_the_curvature_formula_itself_rejects_a_non_positive_or_non_finite_lookahead(bad) -> None:
    with pytest.raises(ValueError, match=r"\blookahead\b"):
        curvature(1.0, bad)


@pytest.mark.req("FR-014-31")
@pytest.mark.parametrize("bad", [0.0, -6.0, math.nan])
def test_the_steering_law_rejects_a_non_positive_wheelbase(bad) -> None:
    with pytest.raises(ValueError, match=r"\bwheelbase\b"):
        steering_angle(0.005, bad)


# ---------------------------------------------------------------------------------------------------- PID
@pytest.mark.req("FR-014-29")
def test_the_pid_follows_the_discrete_difference_equation_until_it_saturates() -> None:
    pid = PidSpeed(kp=0.5, ki=0.2, dt=0.1)
    for k in range(1, 25):  # u_k = 0.5 + 0.2 * 0.1 * k stays below 1 for k < 25
        assert pid.step(1.0) == pytest.approx(0.5 + 0.02 * k, rel=1e-12)
    assert pid.step(1.0) == pytest.approx(1.0, rel=1e-12)  # k = 25 reaches the output limit
    assert pid.step(1.0) == 1.0  # and stays clamped
    assert pid.step(-1.0) < 1.0


@pytest.mark.req("FR-014-29")
def test_the_pid_output_is_clamped_to_its_limits_in_both_directions() -> None:
    pid = PidSpeed(kp=10.0, ki=0.0, dt=0.1)
    assert pid.step(5.0) == 1.0
    assert pid.step(-5.0) == -1.0
    assert PidSpeed(kp=10.0, ki=0.0, dt=0.1, out_min=-0.5, out_max=0.25).step(5.0) == 0.25


@pytest.mark.req("FR-014-29")
def test_anti_windup_a_sign_change_leaves_saturation_within_one_step() -> None:
    pid = PidSpeed(kp=0.5, ki=0.2, dt=0.1)
    for _ in range(300):  # a long saturated phase: without anti-windup the integral would reach 30
        pid.step(1.0)
    first = pid.step(-1.0)
    assert first <= 0.5  # leaves saturation at once; a wound-up integral would hold the output at +1
    for _ in range(40):
        last = pid.step(-1.0)
    assert last < 0.0  # and the output follows the error on within a few seconds


@pytest.mark.req("FR-014-29")
def test_reset_clears_the_integral() -> None:
    pid = PidSpeed(kp=0.5, ki=0.2, dt=0.1)
    for _ in range(10):
        pid.step(1.0)
    pid.reset()
    assert pid.step(1.0) == pytest.approx(0.52, rel=1e-12)


@pytest.mark.req("FR-014-29")
@pytest.mark.parametrize(
    ("kw", "name"),
    [
        ({"dt": 0.0}, "dt"),
        ({"dt": -0.1}, "dt"),
        ({"dt": math.nan}, "dt"),
        ({"out_min": 1.0, "out_max": 1.0}, "out_min"),
        ({"out_min": 2.0, "out_max": 1.0}, "out_min"),
    ],
)
def test_pid_rejects_invalid_configuration(kw, name) -> None:
    base = {"kp": 0.5, "ki": 0.2, "dt": 0.1}
    base.update(kw)
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        PidSpeed(**base)


@pytest.mark.req("FR-014-29")
def test_the_pid_rejects_a_non_finite_error() -> None:
    with pytest.raises(ValueError, match=r"\berror\b"):
        PidSpeed(kp=0.5, ki=0.2, dt=0.1).step(math.nan)


# -------------------------------------------------------------------------------------- controller and limits
CFG = {
    "wheelbase": 6.0,
    "l0": 10.0,
    "kv": 1.0,
    "l_min": 5.0,
    "l_max": 40.0,
    "kp": 0.1,
    "ki": 0.0,
    "dt": 0.05,
    "max_steer_rate": math.radians(20.0),
}
PATH = np.array(
    [[0.0, 0.0], [math.sqrt(399.0), 1.0], [60.0, 1.0]]
)  # goal 20 m ahead, 1 m to the left at speed 10 (la = 10 + 10)


@pytest.mark.req("FR-014-29")
def test_the_steering_action_tracks_the_goal_through_the_steering_rate_limit() -> None:
    ctl = PurePursuitPid(**CFG)
    delta = math.atan(0.03)  # the pure-pursuit steering angle of the hand calculation
    # already steering at delta - 0.005 rad: the needed rate is 0.005 / 0.05 = 0.1 rad/s, i.e. 0.1 / 0.349066 of the maximum
    act = ctl.act(PATH, speed=10.0, v_target=10.0, steer_angle=delta - 0.005)
    assert act.shape == (2,)
    assert act[0] == pytest.approx(0.1 / math.radians(20.0), rel=1e-6)  # 0.28648
    assert act[1] == pytest.approx(0.0, abs=1e-12)  # at the target speed


@pytest.mark.req("FR-014-29")
def test_the_outputs_pass_through_the_same_action_limits_as_the_policy() -> None:
    ctl = PurePursuitPid(**CFG)
    act = ctl.act(
        PATH, speed=10.0, v_target=10.0, steer_angle=0.0
    )  # needs 0.59982 rad/s = 1.718 of the maximum: clipped
    assert act[0] == 1.0
    fast = PurePursuitPid(**CFG).act(PATH, speed=0.0, v_target=50.0, steer_angle=0.0)
    assert fast[1] == 1.0  # kp * 50 = 5 clipped to +1
    brake = PurePursuitPid(**CFG).act(PATH, speed=30.0, v_target=0.0, steer_angle=0.0)
    assert brake[1] == -1.0


@pytest.mark.req("FR-014-29")
def test_the_drive_action_is_the_pid_of_the_speed_error() -> None:
    ctl = PurePursuitPid(**CFG)
    act = ctl.act(PATH, speed=8.0, v_target=10.0, steer_angle=0.0)
    assert act[1] == pytest.approx(0.1 * 2.0, rel=1e-12)  # kp * (10 - 8)


@pytest.mark.req("FR-014-31")
def test_the_controller_uses_the_path_end_when_the_path_is_short_and_raises_on_an_invalid_path() -> None:
    ctl = PurePursuitPid(**CFG)
    short = np.array([[0.0, 0.0], [4.0, 0.4]])  # shorter than the look-ahead of 20 m
    act = ctl.act(short, speed=10.0, v_target=10.0, steer_angle=0.0)
    assert np.all(np.isfinite(act))
    with pytest.raises(ValueError, match=r"\bpath\b"):
        ctl.act(np.array([[0.0, 0.0]]), speed=10.0, v_target=10.0, steer_angle=0.0)
    with pytest.raises(ValueError, match=r"\bspeed\b"):
        ctl.act(PATH, speed=math.nan, v_target=10.0, steer_angle=0.0)

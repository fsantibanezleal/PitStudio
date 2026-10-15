# ruff: noqa: E501, PT018
"""T-014-033: IL-1 terminations, success rule, light-vehicle scenarios and the 25/25/25/25 evaluation mix.

Requirements: FR-014-12, FR-014-14.

Spec: specs/014-robot-learning/spec.md FR-014-12: "An IL-1 episode shall end as success when the truck reaches arc length >= L_route -
2 m with no collision; it shall end as a failure on a collision (contact between any truck link and a light vehicle, or between a
non-wheel truck link and terrain or a berm), on |e_lat| > 5 m, or at the time limit T_max = 2 L_route / v_lim_mean." FR-014-14: "IL-1
shall place 0-3 kinematic light vehicles at 20-40 km/h on paths that conflict with the route at least once (crossing or oncoming at a
junction); the evaluation seed set shall hold exactly 25 episodes each with 0, 1, 2 and 3 light vehicles." FR-014-10 (invalid values
end an episode as `invalid_value`).

Oracle: scripted single-condition trajectories (hand-chosen numbers: a 500 m route, T_max = 2 * 500 / 10 = 100 s); the contact table of
the requirement written out as a truth table; a segment-intersection test written here (orientation predicates) to check that every
generated light-vehicle path meets the route; counting of the evaluation mix.

Conventions chosen where the spec is silent (see the red report): when several conditions hold in one step the reason is the first of
invalid_value, collision, success, lateral_error, time_limit; the time limit is reached when t >= T_max.

Expected API of the implementation (module `pitstudio.robots.episodes`, NumPy):
    SUCCESS_MARGIN = 2.0 ; LATERAL_LIMIT = 5.0
    time_limit(route_length, mean_speed_limit) -> float               2 L / v
    is_collision_pair(link, other) -> bool
        link in {"wheel", "chassis", "dump_body", "other"}, other in {"light_vehicle", "terrain", "berm"}: True for any link
        against a light vehicle; True for a non-wheel link against terrain or a berm; False for a wheel against terrain or a berm.
        ValueError naming `link` or `other` for an unknown value.
    classify_step(*, arc_length, route_length, e_lat, t, t_max, collided) -> str | None
        None while the episode continues, else "success", "collision", "lateral_error" or "time_limit"; "invalid_value" when any
        of arc_length, e_lat, t is NaN or infinite. ValueError naming `route_length` or `t_max` for a non-positive or non-finite
        value.
    LvPath: frozen dataclass (waypoints: (K, 2) float array in the world frame, speed_kmh: float, kind: "crossing" | "oncoming")
    light_vehicle_scenario(seed, n_light, route_xy) -> list[LvPath]
        n_light in 0..3 paths (ValueError naming `n_light` otherwise), speed_kmh in [20, 40], each path meeting the route polyline at
        least once; the result is a pure function of (seed, n_light, route_xy).
    eval_light_vehicle_counts(eval_start, count=100) -> list[int]
        the number of light vehicles of each evaluation seed eval_start .. eval_start + count - 1, with exactly count / 4 episodes of
        each of 0, 1, 2 and 3 (ValueError naming `count` unless it is 100).
"""

from __future__ import annotations

import math
from collections import Counter

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.robots.episodes import (
    LATERAL_LIMIT,
    SUCCESS_MARGIN,
    LvPath,
    classify_step,
    eval_light_vehicle_counts,
    is_collision_pair,
    light_vehicle_scenario,
    time_limit,
)

L = 500.0
T_MAX = 100.0  # 2 * 500 / 10


def step(**over):
    kw = {"arc_length": 100.0, "route_length": L, "e_lat": 0.5, "t": 20.0, "t_max": T_MAX, "collided": False}
    kw.update(over)
    return classify_step(**kw)


# --------------------------------------------------------------------------------------------- terminations
@pytest.mark.req("FR-014-12")
def test_constants_and_the_time_limit_formula() -> None:
    assert SUCCESS_MARGIN == 2.0
    assert LATERAL_LIMIT == 5.0
    assert time_limit(500.0, 10.0) == pytest.approx(100.0, rel=1e-15)
    assert time_limit(1234.0, 8.0) == pytest.approx(308.5, rel=1e-15)  # 2 * 1234 / 8


@pytest.mark.req("FR-014-12")
def test_a_running_episode_has_no_termination() -> None:
    assert step() is None
    assert step(arc_length=497.9, e_lat=-4.99, t=99.9) is None


@pytest.mark.req("FR-014-12")
def test_success_at_two_metres_before_the_end_without_collision() -> None:
    assert step(arc_length=498.0) == "success"  # L - 2 m exactly
    assert step(arc_length=500.0) == "success"
    assert step(arc_length=497.999) is None
    assert step(arc_length=520.0) == "success"


@pytest.mark.req("FR-014-12")
def test_a_collision_ends_the_episode_and_blocks_success() -> None:
    assert step(collided=True) == "collision"
    assert step(arc_length=499.0, collided=True) == "collision"  # arrival with a collision is not a success


@pytest.mark.req("FR-014-12")
def test_lateral_error_beyond_five_metres_ends_the_episode_on_either_side() -> None:
    assert step(e_lat=5.0) is None  # the limit is strict: |e_lat| > 5 m
    assert step(e_lat=5.001) == "lateral_error"
    assert step(e_lat=-5.001) == "lateral_error"
    assert step(e_lat=-5.0) is None


@pytest.mark.req("FR-014-12")
def test_the_time_limit_ends_the_episode() -> None:
    assert step(t=99.99) is None
    assert step(t=100.0) == "time_limit"
    assert step(t=250.0) == "time_limit"


@pytest.mark.req("FR-014-12")
def test_when_several_conditions_hold_the_documented_order_decides() -> None:
    assert step(collided=True, e_lat=9.0, t=500.0) == "collision"
    assert step(arc_length=499.0, e_lat=9.0, t=500.0) == "success"
    assert step(e_lat=9.0, t=500.0) == "lateral_error"


@pytest.mark.req("FR-014-10")
@pytest.mark.parametrize("field", ["arc_length", "e_lat", "t"])
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_a_non_finite_step_value_ends_the_episode_as_invalid_value(field, bad) -> None:
    assert step(**{field: bad}) == "invalid_value"
    assert step(**{field: bad}, collided=True) == "invalid_value"


@pytest.mark.req("FR-014-12")
@pytest.mark.parametrize(
    ("over", "name"),
    [
        ({"route_length": 0.0}, "route_length"),
        ({"route_length": -5.0}, "route_length"),
        ({"route_length": math.nan}, "route_length"),
        ({"route_length": math.inf}, "route_length"),
        ({"t_max": 0.0}, "t_max"),
        ({"t_max": -1.0}, "t_max"),
        ({"t_max": math.nan}, "t_max"),
    ],
)
def test_invalid_episode_constants_raise_value_error_naming_the_argument(over, name) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        step(**over)


@pytest.mark.req("FR-014-12")
@pytest.mark.parametrize(
    ("link", "other", "want"),
    [
        ("chassis", "light_vehicle", True),
        ("wheel", "light_vehicle", True),  # any truck link against a light vehicle
        ("dump_body", "light_vehicle", True),
        ("other", "light_vehicle", True),
        ("chassis", "terrain", True),
        ("dump_body", "terrain", True),
        ("other", "terrain", True),
        ("wheel", "terrain", False),  # wheels are meant to touch the ground
        ("chassis", "berm", True),
        ("other", "berm", True),
        ("wheel", "berm", False),
    ],
)
def test_the_collision_contact_table(link, other, want) -> None:
    assert is_collision_pair(link, other) is want


@pytest.mark.req("FR-014-12")
@pytest.mark.parametrize(
    ("link", "other", "name"), [("rotor", "terrain", "link"), ("wheel", "tree", "other"), ("", "berm", "link")]
)
def test_an_unknown_contact_kind_raises_value_error_naming_it(link, other, name) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        is_collision_pair(link, other)


# ---------------------------------------------------------------------------------------- light-vehicle paths
def _orient(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a, b, c, tol=1e-6) -> bool:
    return (
        abs(_orient(a, b, c)) <= tol * max(1.0, np.linalg.norm(np.subtract(b, a)))
        and min(a[0], b[0]) - tol <= c[0] <= max(a[0], b[0]) + tol
        and min(a[1], b[1]) - tol <= c[1] <= max(a[1], b[1]) + tol
    )


def segments_meet(p1, p2, q1, q2, tol=1e-6) -> bool:
    d1, d2 = _orient(q1, q2, p1), _orient(q1, q2, p2)
    d3, d4 = _orient(p1, p2, q1), _orient(p1, p2, q2)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True
    return any(
        (
            _on_segment(q1, q2, p1, tol),
            _on_segment(q1, q2, p2, tol),
            _on_segment(p1, p2, q1, tol),
            _on_segment(p1, p2, q2, tol),
        )
    )


def polylines_meet(a: np.ndarray, b: np.ndarray) -> bool:
    return any(segments_meet(a[i], a[i + 1], b[j], b[j + 1]) for i in range(len(a) - 1) for j in range(len(b) - 1))


ROUTE = np.array([[0.0, 0.0], [120.0, 10.0], [260.0, 60.0], [380.0, 55.0], [500.0, 120.0]])


@pytest.mark.req("FR-014-14")
def test_the_intersection_oracle_is_sound_on_hand_cases() -> None:
    cross = np.array([[60.0, -30.0], [60.0, 30.0]])
    miss = np.array([[60.0, 30.0], [60.0, 60.0]])
    assert polylines_meet(ROUTE, cross)
    assert not polylines_meet(ROUTE, miss)
    assert polylines_meet(ROUTE, ROUTE[::-1].copy())  # an oncoming path along the route


@pytest.mark.req("FR-014-14")
@pytest.mark.parametrize("n", [0, 1, 2, 3])
def test_a_scenario_holds_n_paths_each_meeting_the_route_at_20_to_40_km_h(n) -> None:
    for seed in range(40):
        paths = light_vehicle_scenario(seed, n, ROUTE)
        assert len(paths) == n
        for p in paths:
            assert isinstance(p, LvPath)
            assert 20.0 <= p.speed_kmh <= 40.0
            assert p.kind in ("crossing", "oncoming")
            wp = np.asarray(p.waypoints, dtype=float)
            assert wp.ndim == 2 and wp.shape[1] == 2 and len(wp) >= 2
            assert np.all(np.isfinite(wp))
            assert polylines_meet(ROUTE, wp), f"seed {seed}: path does not conflict with the route"


@pytest.mark.req("FR-014-14")
@given(st.integers(0, 2**32 - 1), st.integers(0, 3))
@settings(max_examples=200, deadline=None)
def test_property_scenarios_are_reproducible_and_always_conflict_with_the_route(seed, n) -> None:
    first = light_vehicle_scenario(seed, n, ROUTE)
    again = light_vehicle_scenario(seed, n, ROUTE)
    assert len(first) == n
    for a, b in zip(first, again, strict=True):
        np.testing.assert_array_equal(a.waypoints, b.waypoints)
        assert a.speed_kmh == b.speed_kmh
        assert a.kind == b.kind
        assert 20.0 <= a.speed_kmh <= 40.0
        assert polylines_meet(ROUTE, np.asarray(a.waypoints, dtype=float))


@pytest.mark.req("FR-014-14")
def test_different_seeds_give_different_scenarios() -> None:
    seen = {
        tuple(np.round(np.asarray(light_vehicle_scenario(s, 1, ROUTE)[0].waypoints, dtype=float).ravel(), 6))
        for s in range(30)
    }
    assert len(seen) > 20


@pytest.mark.req("FR-014-14")
def test_both_conflict_kinds_occur_over_many_seeds() -> None:
    kinds = {p.kind for s in range(200) for p in light_vehicle_scenario(s, 3, ROUTE)}
    assert kinds == {"crossing", "oncoming"}


@pytest.mark.req("FR-014-14")
@pytest.mark.parametrize("n", [-1, 4, 10])
def test_a_light_vehicle_count_outside_zero_to_three_raises_value_error(n) -> None:
    with pytest.raises(ValueError, match=r"\bn_light\b"):
        light_vehicle_scenario(1, n, ROUTE)


@pytest.mark.req("FR-014-14")
@pytest.mark.parametrize("route", [np.array([[0.0, 0.0]]), np.zeros((4, 3)), np.array([[0.0, 0.0], [math.nan, 1.0]])])
def test_a_route_that_is_not_a_finite_polyline_raises_value_error_naming_route_xy(route) -> None:
    with pytest.raises(ValueError, match=r"\broute_xy\b"):
        light_vehicle_scenario(1, 1, route)


# ----------------------------------------------------------------------------------------------- evaluation mix
@pytest.mark.req("FR-014-14")
@pytest.mark.parametrize("start", [0, 1_000_000, 4_294_967_195, 7])
def test_the_evaluation_seed_set_has_25_episodes_of_each_light_vehicle_count(start) -> None:
    counts = eval_light_vehicle_counts(start)
    assert len(counts) == 100
    assert Counter(counts) == {0: 25, 1: 25, 2: 25, 3: 25}


@pytest.mark.req("FR-014-14")
def test_the_evaluation_mix_is_deterministic() -> None:
    assert eval_light_vehicle_counts(1_000_000) == eval_light_vehicle_counts(1_000_000)


@pytest.mark.req("FR-014-14")
@pytest.mark.parametrize("count", [0, 99, 101, 400, -100])
def test_the_evaluation_mix_is_defined_for_100_episodes_only(count) -> None:
    with pytest.raises(ValueError, match=r"\bcount\b"):
        eval_light_vehicle_counts(0, count)

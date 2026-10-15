# ruff: noqa: E501
"""T-014-030: IL-1 observation builder (63 elements) and its rigid-motion, mirror and permutation relations.

Requirements: FR-014-08, P-014-09.

Spec: specs/014-robot-learning/spec.md FR-014-08: "The IL-1 observation shall be a 63-element body-frame vector: speed, yaw
rate, pitch (3); signed lateral error (left positive) and heading error wrapped to (-pi, pi] (2); the next 10 path points at
5 m arc-length spacing as (x, y) (20); payload fraction of rated (1); 32 ray-cast ranges over +-90 deg of the heading,
clipped to 60 m (32); the nearest light vehicle's relative position (2) and velocity (2) and its TTC clipped to [0, 30] s
(1)." P-014-09: (MR1) a common SE(2) motion of truck, route, obstacles and light vehicles leaves the observation unchanged;
(MR2) mirroring the world about the truck's longitudinal axis negates e_lat, e_psi, yaw rate, the path and light-vehicle y
components and reverses the ray order, and leaves TTC unchanged; (MR3) permuting light vehicles leaves it unchanged;
tolerance atol 1e-6 (float32).

Oracle: (1) hand-calculated scenes (straight route along +x, a vertical wall at x = 30 m, a light vehicle head-on at 40 m)
whose 63 elements are written out below from rotation and distance formulas, including TTC = gap / closing speed
(33 m / 7 m/s); (2) the three metamorphic relations, applied to random generic scenes by Hypothesis (>= 200 examples) with
the SE(2) and mirror transforms written here. Tolerance: the spec's atol 1e-6, plus rtol 2e-7 (about 1.7 float32 ulp)
because two adjacent float32 numbers near 60 m differ by 3.8e-6, which no absolute 1e-6 bound can absorb.

Conventions chosen where the spec is silent (see the red report): the body frame has x forward and y left; e_lat is the
signed distance of the truck from the route, positive when the truck is to the left of the route direction; e_psi = wrap(
route heading at the projection - truck yaw) to (-pi, pi]; the path points are at arc lengths s0 + 5 k, k = 1 .. 10, from the
projection s0 of the truck on the route (the last route point is repeated beyond the route end); ray i points at the body
angle -pi/2 + pi i / 31 (so index 0 looks right, index 31 left) from the truck reference point in the horizontal plane
and returns the distance to the nearest obstacle segment or light-vehicle footprint edge, 60 m when nothing is hit; the nearest
light vehicle is the one with the smallest centre distance; its relative velocity is its world velocity minus the truck's
world velocity (speed along the heading), both rotated into the body frame; with no light vehicle the TTC element is 30.

Expected API of the implementation (module `pitstudio.robots.obs`, NumPy):
    IL1_OBS_SIZE = 63
    IL1_LAYOUT = (("speed_yaw_rate_pitch", 3), ("lateral_heading_error", 2), ("path_points", 20), ("payload_fraction", 1),
                  ("ray_ranges", 32), ("lv_relative_position", 2), ("lv_relative_velocity", 2), ("lv_ttc", 1))
    RAY_ANGLES: np.ndarray (32,), np.linspace(-pi/2, pi/2, 32)
    RAY_MAX_RANGE = 60.0 ; PATH_SPACING = 5.0 ; N_PATH_POINTS = 10 ; TTC_CLIP = 30.0
    LightVehicle: frozen dataclass (x, y, yaw, vx, vy, length, width), world frame, SI units
    il1_observation(*, x, y, yaw, speed, yaw_rate, pitch, payload_fraction, route_xy, truck_size, obstacles=None,
                    light_vehicles=()) -> np.ndarray float32 (63,)
        route_xy: (N, 2) polyline, N >= 2, no repeated consecutive points; truck_size: (length, width) of the truck
        footprint; obstacles: None or (M, 2, 2) wall segments [[x0, y0], [x1, y1]]; light_vehicles: sequence of LightVehicle.
        ValueError naming the argument for a wrong shape (`route_xy`, `obstacles`, `truck_size`).
"""

from __future__ import annotations

import math
from itertools import pairwise

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pitstudio.robots.obs import (
    IL1_LAYOUT,
    IL1_OBS_SIZE,
    N_PATH_POINTS,
    PATH_SPACING,
    RAY_ANGLES,
    RAY_MAX_RANGE,
    TTC_CLIP,
    LightVehicle,
    il1_observation,
)

TRUCK = (10.0, 4.0)
STRAIGHT = np.array([[0.0, 0.0], [100.0, 0.0]])
ATOL = 1e-6
RTOL = 2e-7
S_PSI = slice(3, 5)
S_PATH = slice(5, 25)
S_RAYS = slice(26, 58)


def obs(**over):
    kw = {
        "x": 10.0, "y": 2.0, "yaw": 0.3, "speed": 3.0, "yaw_rate": 0.1, "pitch": 0.05, "payload_fraction": 0.5,
        "route_xy": STRAIGHT, "truck_size": TRUCK,
    }  # fmt: skip
    kw.update(over)
    return il1_observation(**kw)


def rot(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s], [s, c]])


@pytest.mark.req("FR-014-08")
def test_layout_constants() -> None:
    assert IL1_OBS_SIZE == 63
    assert sum(size for _name, size in IL1_LAYOUT) == 63
    assert [n for n, _ in IL1_LAYOUT] == [
        "speed_yaw_rate_pitch", "lateral_heading_error", "path_points", "payload_fraction", "ray_ranges",
        "lv_relative_position", "lv_relative_velocity", "lv_ttc",
    ]  # fmt: skip
    assert RAY_ANGLES.shape == (32,)
    np.testing.assert_allclose(RAY_ANGLES, np.linspace(-math.pi / 2, math.pi / 2, 32), rtol=0, atol=1e-15)
    assert (RAY_MAX_RANGE, PATH_SPACING, N_PATH_POINTS, TTC_CLIP) == (60.0, 5.0, 10, 30.0)


# ------------------------------------------------------------------------------------- hand-calculated scenes
@pytest.mark.req("FR-014-08")
def test_straight_route_scene_without_obstacles_matches_the_hand_calculation() -> None:
    o = obs()
    assert o.dtype == np.float32
    assert o.shape == (63,)
    np.testing.assert_allclose(o[0:3], [3.0, 0.1, 0.05], rtol=RTOL, atol=ATOL)  # speed, yaw rate, pitch
    # truck at (10, 2), yaw 0.3, route along +x through the origin: the truck is 2 m left of the route
    np.testing.assert_allclose(o[3], 2.0, rtol=RTOL, atol=ATOL)  # e_lat, left positive
    np.testing.assert_allclose(o[4], 0.0 - 0.3, rtol=RTOL, atol=ATOL)  # e_psi = route heading - yaw
    # path points at s = 15, 20, ..., 60 on the route: world (s, 0); body frame by the rotation of -yaw
    c, s = math.cos(0.3), math.sin(0.3)
    want = []
    for k in range(1, 11):
        dx, dy = 5.0 * k, -2.0  # (s - 10, 0 - 2)
        want += [dx * c + dy * s, -dx * s + dy * c]
    np.testing.assert_allclose(o[S_PATH], want, rtol=RTOL, atol=ATOL)
    assert o[25] == pytest.approx(0.5, abs=ATOL)  # payload fraction
    np.testing.assert_allclose(o[S_RAYS], 60.0, rtol=0, atol=ATOL)  # nothing to hit: clipped at 60 m
    np.testing.assert_allclose(o[58:62], o[58:62])  # finite (no light vehicle)
    assert np.all(np.isfinite(o[58:62]))
    assert o[62] == pytest.approx(30.0, abs=ATOL)  # no light vehicle: TTC clipped at 30 s


@pytest.mark.req("FR-014-08")
def test_a_truck_on_the_route_has_zero_lateral_error_and_the_points_lie_ahead_on_the_x_axis() -> None:
    o = obs(x=20.0, y=0.0, yaw=0.0)
    assert o[3] == pytest.approx(0.0, abs=ATOL)
    assert o[4] == pytest.approx(0.0, abs=ATOL)
    np.testing.assert_allclose(o[S_PATH].reshape(10, 2), np.c_[5.0 * np.arange(1, 11), np.zeros(10)], atol=ATOL)


@pytest.mark.req("FR-014-08")
def test_the_route_end_repeats_when_fewer_than_ten_points_remain() -> None:
    o = obs(x=80.0, y=0.0, yaw=0.0)  # 20 m left on a 100 m route: points at 85, 90, 95, 100, then 100 repeated
    pts = o[S_PATH].reshape(10, 2)
    np.testing.assert_allclose(pts[:, 0], [5.0, 10.0, 15.0, 20.0] + [20.0] * 6, atol=ATOL)
    np.testing.assert_allclose(pts[:, 1], 0.0, atol=ATOL)


@pytest.mark.req("FR-014-08")
@pytest.mark.parametrize(
    ("yaw", "route_heading", "want"),
    [
        (0.0, 0.0, 0.0),
        (3.0, -3.0, -6.0 + 2.0 * math.pi),  # raw difference -6.0 wraps to 0.2832
        (-3.0, 3.0, 6.0 - 2.0 * math.pi),
        (math.pi, 0.0, math.pi),  # raw -pi wraps to +pi: the interval is (-pi, pi]
        (-math.pi, 0.0, math.pi),  # raw +pi stays +pi
        (0.5, 0.0, -0.5),
    ],
)
def test_heading_error_is_wrapped_to_minus_pi_exclusive_pi_inclusive(yaw, route_heading, want) -> None:
    route = np.array([[0.0, 0.0], [100.0 * math.cos(route_heading), 100.0 * math.sin(route_heading)]])
    o = obs(x=0.0, y=0.0, yaw=yaw, route_xy=route)
    assert o[4] == pytest.approx(want, abs=3e-6)
    assert -math.pi < float(o[4]) <= math.pi + 1e-6


@pytest.mark.req("FR-014-08")
def test_lateral_error_sign_is_positive_to_the_left_of_the_route_direction() -> None:
    assert obs(x=30.0, y=1.5, yaw=0.0)[3] == pytest.approx(1.5, abs=ATOL)
    assert obs(x=30.0, y=-1.5, yaw=0.0)[3] == pytest.approx(-1.5, abs=ATOL)
    reverse = STRAIGHT[::-1].copy()  # route direction -x: the left side is now -y
    assert obs(x=30.0, y=1.5, yaw=math.pi, route_xy=reverse)[3] == pytest.approx(-1.5, abs=ATOL)


@pytest.mark.req("FR-014-08")
def test_rays_hit_a_wall_at_the_distance_given_by_trigonometry() -> None:
    wall = np.array([[[30.0, -100.0], [30.0, 100.0]]])  # x = 30
    o = obs(x=10.0, y=0.0, yaw=0.0, obstacles=wall)
    want = []
    for th in np.linspace(-math.pi / 2, math.pi / 2, 32):
        d = 20.0 / math.cos(th) if math.cos(th) > 1e-9 else 60.0
        want.append(min(d, 60.0))
    np.testing.assert_allclose(o[S_RAYS], want, rtol=RTOL, atol=ATOL)
    # the central rays (angles +-2.9 deg) hit at 20 / cos(2.903 deg) = 20.026 m; the outer ones are clipped at 60 m
    assert o[26 + 15] == pytest.approx(20.0 / math.cos(math.radians(2.9032258)), abs=2e-4)
    assert o[26] == pytest.approx(60.0, abs=ATOL)
    assert o[26 + 31] == pytest.approx(60.0, abs=ATOL)


@pytest.mark.req("FR-014-08")
def test_rays_are_cast_from_the_truck_heading_not_from_the_world_axes() -> None:
    wall = np.array([[[-50.0, 20.0], [100.0, 20.0]]])  # the wall y = 20 is on the truck's left when it heads along +x
    o = obs(x=0.0, y=0.0, yaw=0.0, obstacles=wall)
    # ray 31 looks 90 deg left (parallel direction +y): hits at 20 m; ray 0 looks right: nothing
    assert o[26 + 31] == pytest.approx(20.0, abs=ATOL)
    assert o[26] == pytest.approx(60.0, abs=ATOL)
    turned = obs(x=0.0, y=0.0, yaw=math.pi, obstacles=wall)  # now the same wall is on the right: ray 0 hits at 20 m
    assert turned[26] == pytest.approx(20.0, abs=ATOL)
    assert turned[26 + 31] == pytest.approx(60.0, abs=ATOL)


@pytest.mark.req("FR-014-08")
def test_head_on_light_vehicle_gives_position_velocity_and_ttc_by_hand_calculation() -> None:
    lv = LightVehicle(x=40.0, y=0.0, yaw=math.pi, vx=-2.0, vy=0.0, length=4.0, width=2.0)
    o = obs(x=0.0, y=0.0, yaw=0.0, speed=5.0, light_vehicles=[lv])
    np.testing.assert_allclose(o[58:60], [40.0, 0.0], rtol=RTOL, atol=ATOL)  # relative position, body frame
    np.testing.assert_allclose(o[60:62], [-7.0, 0.0], rtol=RTOL, atol=ATOL)  # (-2) - (+5) along x
    # footprints: truck half-length 5, light vehicle half-length 2 -> gap 40 - 5 - 2 = 33 m, closing 7 m/s
    assert o[62] == pytest.approx(33.0 / 7.0, rel=1e-6)


@pytest.mark.req("FR-014-08")
def test_the_light_vehicle_state_is_expressed_in_the_body_frame_of_a_turned_truck() -> None:
    # truck at (10, 10) heading +y (yaw 90 deg), speed 4 -> world velocity (0, 4); light vehicle at (10, 50), v = (0, 0)
    lv = LightVehicle(x=10.0, y=50.0, yaw=0.0, vx=0.0, vy=0.0, length=4.0, width=2.0)
    o = obs(x=10.0, y=10.0, yaw=math.pi / 2, speed=4.0, light_vehicles=[lv])
    np.testing.assert_allclose(o[58:60], [40.0, 0.0], rtol=RTOL, atol=1e-5)  # straight ahead in the body frame
    np.testing.assert_allclose(o[60:62], [-4.0, 0.0], rtol=RTOL, atol=1e-5)  # it approaches at the truck speed


@pytest.mark.req("FR-014-08")
def test_ttc_is_clipped_to_the_interval_zero_to_thirty_seconds() -> None:
    far = LightVehicle(x=400.0, y=0.0, yaw=math.pi, vx=-2.0, vy=0.0, length=4.0, width=2.0)  # 393 / 7 = 56 s
    assert obs(x=0.0, y=0.0, yaw=0.0, speed=5.0, light_vehicles=[far])[62] == pytest.approx(30.0, abs=ATOL)
    receding = LightVehicle(
        x=40.0, y=0.0, yaw=0.0, vx=9.0, vy=0.0, length=4.0, width=2.0
    )  # faster and ahead: not closing
    assert obs(x=0.0, y=0.0, yaw=0.0, speed=5.0, light_vehicles=[receding])[62] == pytest.approx(30.0, abs=ATOL)
    close = LightVehicle(
        x=7.35, y=0.0, yaw=math.pi, vx=-2.0, vy=0.0, length=4.0, width=2.0
    )  # 0.35 m gap, closing 7 m/s
    assert obs(x=0.0, y=0.0, yaw=0.0, speed=5.0, light_vehicles=[close])[62] == pytest.approx(0.05, abs=ATOL)


@pytest.mark.req("FR-014-08")
def test_the_nearest_light_vehicle_by_centre_distance_is_the_one_reported() -> None:
    near = LightVehicle(x=0.0, y=20.0, yaw=0.0, vx=0.0, vy=0.0, length=4.0, width=2.0)
    far = LightVehicle(x=40.0, y=0.0, yaw=0.0, vx=0.0, vy=0.0, length=4.0, width=2.0)
    for lvs in ([near, far], [far, near]):
        o = obs(x=0.0, y=0.0, yaw=0.0, speed=0.0, light_vehicles=lvs)
        np.testing.assert_allclose(o[58:60], [0.0, 20.0], rtol=RTOL, atol=ATOL)


@pytest.mark.req("FR-014-08")
def test_a_light_vehicle_in_front_shortens_the_central_rays() -> None:
    wide = LightVehicle(x=20.0, y=0.0, yaw=0.0, vx=0.0, vy=0.0, length=4.0, width=6.0)  # x in [18, 22], y in [-3, 3]
    o = obs(x=0.0, y=0.0, yaw=0.0, speed=0.0, light_vehicles=[wide])
    for i in (14, 15, 16, 17):  # body angles -8.71, -2.90, +2.90, +8.71 deg all hit the front face x = 18
        th = -math.pi / 2 + math.pi * i / 31
        assert o[26 + i] == pytest.approx(18.0 / math.cos(th), rel=1e-6)
    assert o[26 + 5] == pytest.approx(60.0, abs=ATOL)  # a ray pointing well to the right misses it


@pytest.mark.req("FR-014-08")
@pytest.mark.parametrize(
    ("over", "name"),
    [
        ({"route_xy": np.array([[0.0, 0.0]])}, "route_xy"),
        ({"route_xy": np.zeros((5, 3))}, "route_xy"),
        ({"route_xy": np.array([[0.0, 0.0], [0.0, 0.0]])}, "route_xy"),
        ({"obstacles": np.zeros((3, 2))}, "obstacles"),
        ({"truck_size": (10.0,)}, "truck_size"),
        ({"truck_size": (0.0, 4.0)}, "truck_size"),
    ],
    ids=["one-point", "xyz", "repeated-point", "bad-obstacles", "short-size", "zero-length"],
)
def test_wrong_shapes_raise_value_error_naming_the_argument(over, name) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        obs(**over)


# --------------------------------------------------------------------------------------------- metamorphic scenes
def point_segment_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    d = b - a
    t = min(max(float(np.dot(p - a, d)) / float(np.dot(d, d)), 0.0), 1.0)
    return float(np.linalg.norm(p - (a + t * d)))


@st.composite
def scenes(draw):
    """A generic scene: a curving route, a truck near it, 0-4 wall segments, 0-3 light vehicles."""
    p0 = np.array([draw(st.floats(-200, 200)), draw(st.floats(-200, 200))])
    h = draw(st.floats(-math.pi, math.pi))
    pts = [p0]
    for _ in range(14):
        h += draw(st.floats(-0.3, 0.3))
        pts.append(pts[-1] + draw(st.floats(8.0, 15.0)) * np.array([math.cos(h), math.sin(h)]))
    route = np.array(pts)
    k = draw(st.integers(0, 8))
    seg = route[k + 1] - route[k]
    heading = math.atan2(seg[1], seg[0])
    t = draw(st.floats(0.05, 0.95))
    base = route[k] + t * seg
    normal = np.array([-math.sin(heading), math.cos(heading)])
    pos = base + draw(st.floats(-3.0, 3.0)) * normal
    yaw = heading + draw(st.floats(-0.6, 0.6))
    n_walls = draw(st.integers(0, 4))
    walls = []
    for _ in range(n_walls):
        c = pos + np.array([draw(st.floats(-50, 50)), draw(st.floats(-50, 50))])
        a = draw(st.floats(-math.pi, math.pi))
        half = draw(st.floats(3.0, 30.0)) * np.array([math.cos(a), math.sin(a)])
        assume(point_segment_distance(pos, c - half, c + half) >= 1.0)  # the ray origin is never on a wall
        walls.append([c - half, c + half])
    lvs = []
    for _ in range(draw(st.integers(0, 3))):
        d = draw(st.floats(15.0, 70.0))
        a = draw(st.floats(-math.pi, math.pi))
        c = pos + d * np.array([math.cos(a), math.sin(a)])
        sp = draw(st.floats(0.0, 10.0))
        ly = draw(st.floats(-math.pi, math.pi))
        lvs.append(
            LightVehicle(
                float(c[0]),
                float(c[1]),
                ly,
                sp * math.cos(ly),
                sp * math.sin(ly),
                draw(st.floats(3.0, 6.0)),
                draw(st.floats(1.5, 2.5)),
            )
        )
    dists = sorted(math.hypot(v.x - pos[0], v.y - pos[1]) for v in lvs)
    if any(b - a < 0.5 for a, b in pairwise(dists)):
        lvs = lvs[:1]  # keep the nearest light vehicle unambiguous
    return {
        "x": float(pos[0]), "y": float(pos[1]), "yaw": float(yaw), "speed": draw(st.floats(0.0, 15.0)),
        "yaw_rate": draw(st.floats(-0.5, 0.5)), "pitch": draw(st.floats(-0.2, 0.2)), "payload_fraction": draw(st.floats(0.0, 1.0)),
        "route_xy": route, "truck_size": TRUCK, "obstacles": np.array(walls).reshape(-1, 2, 2) if walls else None,
        "light_vehicles": lvs,
    }  # fmt: skip


def se2_transform(scene: dict, angle: float, shift: np.ndarray) -> dict:
    r = rot(angle)

    def p(v):
        return r @ np.asarray(v, dtype=float) + shift

    out = dict(scene)
    out["x"], out["y"] = (float(c) for c in p([scene["x"], scene["y"]]))
    out["yaw"] = scene["yaw"] + angle
    out["route_xy"] = (r @ scene["route_xy"].T).T + shift
    if scene["obstacles"] is not None:
        out["obstacles"] = np.einsum("ij,mkj->mki", r, scene["obstacles"]) + shift
    lvs = []
    for v in scene["light_vehicles"]:
        c = p([v.x, v.y])
        vel = r @ np.array([v.vx, v.vy])
        lvs.append(
            LightVehicle(float(c[0]), float(c[1]), v.yaw + angle, float(vel[0]), float(vel[1]), v.length, v.width)
        )
    out["light_vehicles"] = lvs
    return out


def mirror(scene: dict) -> dict:
    """Reflect the world about the longitudinal axis of the truck (the line through its position along its heading)."""
    psi = scene["yaw"]
    origin = np.array([scene["x"], scene["y"]])
    to_local = rot(-psi)
    to_world = rot(psi)
    flip = np.diag([1.0, -1.0])

    def point(v):
        return to_world @ (flip @ (to_local @ (np.asarray(v, dtype=float) - origin))) + origin

    def vector(v):
        return to_world @ (flip @ (to_local @ np.asarray(v, dtype=float)))

    out = dict(scene)
    out["route_xy"] = np.array([point(p) for p in scene["route_xy"]])
    out["yaw_rate"] = -scene["yaw_rate"]
    if scene["obstacles"] is not None:
        out["obstacles"] = np.array([[point(a), point(b)] for a, b in scene["obstacles"]])
    lvs = []
    for v in scene["light_vehicles"]:
        c = point([v.x, v.y])
        vel = vector([v.vx, v.vy])
        lvs.append(
            LightVehicle(float(c[0]), float(c[1]), 2.0 * psi - v.yaw, float(vel[0]), float(vel[1]), v.length, v.width)
        )
    out["light_vehicles"] = lvs
    return out


SETTINGS = settings(max_examples=200, deadline=None)


@pytest.mark.req("P-014-09")
@given(scenes(), st.floats(-math.pi, math.pi), st.floats(-500.0, 500.0), st.floats(-500.0, 500.0))
@SETTINGS
def test_p09_mr1_a_common_se2_motion_leaves_the_observation_unchanged(scene, angle, sx, sy) -> None:
    base = il1_observation(**scene)
    moved = il1_observation(**se2_transform(scene, angle, np.array([sx, sy])))
    np.testing.assert_allclose(moved, base, rtol=RTOL, atol=ATOL)


@pytest.mark.req("P-014-09")
@given(scenes())
@SETTINGS
def test_p09_mr2_mirroring_about_the_longitudinal_axis_flips_the_signed_entries_and_the_ray_order(scene) -> None:
    base = il1_observation(**scene)
    mir = il1_observation(**mirror(scene))
    np.testing.assert_allclose(mir[0], base[0], rtol=RTOL, atol=ATOL)  # speed
    np.testing.assert_allclose(mir[1], -base[1], rtol=RTOL, atol=ATOL)  # yaw rate
    np.testing.assert_allclose(mir[2], base[2], rtol=RTOL, atol=ATOL)  # pitch
    np.testing.assert_allclose(mir[3], -base[3], rtol=RTOL, atol=ATOL)  # e_lat
    # e_psi flips except on the wrap boundary +pi, where -pi is represented as +pi
    if abs(abs(float(base[4])) - math.pi) > 1e-4:
        np.testing.assert_allclose(mir[4], -base[4], rtol=RTOL, atol=ATOL)
    pts, mpts = base[S_PATH].reshape(10, 2), mir[S_PATH].reshape(10, 2)
    np.testing.assert_allclose(mpts[:, 0], pts[:, 0], rtol=RTOL, atol=ATOL)  # path x unchanged
    np.testing.assert_allclose(mpts[:, 1], -pts[:, 1], rtol=RTOL, atol=ATOL)  # path y negated
    np.testing.assert_allclose(mir[25], base[25], rtol=RTOL, atol=ATOL)  # payload
    np.testing.assert_allclose(mir[S_RAYS], base[S_RAYS][::-1], rtol=RTOL, atol=ATOL)  # ray order reversed
    np.testing.assert_allclose(mir[58], base[58], rtol=RTOL, atol=ATOL)  # LV relative x
    np.testing.assert_allclose(mir[59], -base[59], rtol=RTOL, atol=ATOL)  # LV relative y
    np.testing.assert_allclose(mir[60], base[60], rtol=RTOL, atol=ATOL)
    np.testing.assert_allclose(mir[61], -base[61], rtol=RTOL, atol=ATOL)
    np.testing.assert_allclose(mir[62], base[62], rtol=1e-5, atol=ATOL)  # TTC unchanged


@pytest.mark.req("P-014-09")
@given(scenes(), st.randoms(use_true_random=False))
@SETTINGS
def test_p09_mr3_permuting_the_light_vehicles_leaves_the_observation_unchanged(scene, rnd) -> None:
    base = il1_observation(**scene)
    lvs = list(scene["light_vehicles"])
    rnd.shuffle(lvs)
    np.testing.assert_array_equal(il1_observation(**{**scene, "light_vehicles": lvs}), base)


@pytest.mark.req("P-014-09")
@given(scenes())
@SETTINGS
def test_every_element_is_finite_and_within_its_documented_range(scene) -> None:
    o = il1_observation(**scene)
    assert np.all(np.isfinite(o))
    assert np.all((o[S_RAYS] >= 0.0) & (o[S_RAYS] <= 60.0 + 1e-5))
    assert 0.0 <= float(o[62]) <= 30.0 + 1e-5
    assert -math.pi - 1e-6 < float(o[4]) <= math.pi + 1e-6

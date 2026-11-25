# ruff: noqa: E501, PT018
"""Case B1 footprints (docs M20, spec 018 FR-018-55): `pitstudio.haulage.ttc.obb_pairs`, the time to contact and the separation of two
oriented rectangles that translate at constant velocity.

Oracles, none of them the code under test:
- axis-aligned encounters worked by hand (gap over closing speed of the two half lengths, passing lanes that never close, an overlap);
- `shapely` polygons: a fine scan of the time at which the two translated rectangles first share area, on random pairs with random headings;
- rigid-motion invariance (spec 018 section 4, P-018-20): rotating the whole scene leaves the time to contact unchanged.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import shapely.affinity
import shapely.geometry

from pitstudio.haulage.ttc import obb_pairs

TRUCK = (13.36 / 2, 8.563 / 2)  # half length, half width: the asset specification of the 793F class
LV = (5.275 / 2, 1.96 / 2)  # the light vehicle of the asset specification


def unit(deg):
    a = math.radians(deg)
    return np.array([math.cos(a), math.sin(a)])


def one(d, w, ha, hb, ea=TRUCK, eb=LV):
    t, s = obb_pairs(
        np.array([d], float),
        np.array([w], float),
        np.array([unit(ha)]),
        np.array([unit(hb)]),
        np.array([ea]),
        np.array([eb]),
    )
    return float(t[0]), float(s[0])


def test_head_on_in_one_lane_is_the_gap_between_the_bodies_over_the_closing_speed():
    # b is 50 m ahead of a on the x axis, closing at 10 m/s: contact when the centres are 6.68 + 2.6375 m apart
    t, s = one((50.0, 0.0), (-10.0, 0.0), 0.0, 0.0)
    assert t == pytest.approx((50.0 - 6.68 - 2.6375) / 10.0, rel=1e-12)
    assert s == pytest.approx(50.0 - 6.68 - 2.6375, rel=1e-12)


def test_passing_lanes_further_apart_than_the_half_widths_never_close():
    t, s = one((60.0, 15.0), (-20.0, 0.0), 0.0, 180.0)
    assert math.isinf(t) and s == pytest.approx(
        60.0 - 6.68 - 2.6375, rel=1e-12
    )  # the largest axis gap; the lateral gap is 9.7385 m


def test_a_crossing_at_a_right_angle_touches_when_the_light_vehicle_reaches_the_truck_side():
    # truck heading east at the origin, light vehicle heading north from 40 m south of the truck centre line at 8 m/s, 5 m east of the truck centre
    t, _ = one((5.0, -40.0), (0.0, 8.0), 0.0, 90.0)
    assert t == pytest.approx((40.0 - 4.2815 - 2.6375) / 8.0, rel=1e-12)


def test_overlapping_bodies_have_no_time_to_contact_and_a_negative_separation():
    t, s = one((3.0, 1.0), (-5.0, 0.0), 0.0, 0.0)
    assert math.isnan(t) and s < 0.0  # an overlap is not a TTC of 0: it has none


def test_touching_bodies_are_not_overlapping():
    t, s = one((6.68 + 2.6375, 0.0), (-5.0, 0.0), 0.0, 0.0)
    assert not math.isnan(t) and s == pytest.approx(0.0, abs=1e-12)


def test_diverging_bodies_never_touch():
    t, _ = one((20.0, 0.0), (5.0, 0.0), 0.0, 0.0)
    assert math.isinf(t)


def test_a_pair_that_is_parallel_in_relative_motion_and_separated_never_touches():
    t, _ = one((0.0, 12.0), (7.0, 0.0), 0.0, 0.0)
    assert math.isinf(t)


def shapely_box(c, head_deg, half):
    box = shapely.geometry.box(-half[0], -half[1], half[0], half[1])
    box = shapely.affinity.rotate(box, head_deg, origin=(0, 0))
    return shapely.affinity.translate(box, c[0], c[1])


def scan_first_contact(d, w, ha, hb, ea, eb, horizon=12.0, dt=0.01):
    a = shapely_box((0.0, 0.0), ha, ea)
    for k in range(int(horizon / dt) + 1):
        t = k * dt
        b = shapely_box((d[0] + w[0] * t, d[1] + w[1] * t), hb, eb)
        if a.intersection(b).area > 1e-9:
            return None if k == 0 else t
    return math.inf


def test_random_pairs_agree_with_a_shapely_time_scan():
    rng = np.random.default_rng(20261125)
    checked = 0
    for _ in range(120):
        d = rng.uniform(-45, 45, 2)
        w = rng.uniform(-14, 14, 2)
        ha, hb = rng.uniform(0, 360, 2)
        ea, eb = (TRUCK, LV) if rng.random() < 0.5 else (LV, TRUCK)
        t, s = one(d, w, ha, hb, ea, eb)
        ref = scan_first_contact(d, w, ha, hb, ea, eb)
        if ref is None:  # already overlapping at t = 0
            assert math.isnan(t) and s < 0
            continue
        checked += 1
        if math.isinf(ref):
            assert math.isinf(t)
        else:
            assert t == pytest.approx(ref, abs=0.012)
    assert checked > 70


def test_the_separation_is_a_lower_bound_of_the_true_distance():
    rng = np.random.default_rng(7)
    for _ in range(150):
        d = rng.uniform(-30, 30, 2)
        ha, hb = rng.uniform(0, 360, 2)
        _, s = one(d, (0.0, 0.0), ha, hb)
        true = shapely_box((0, 0), ha, TRUCK).distance(shapely_box(d, hb, LV))
        if true > 0:
            assert 0 <= s <= true + 1e-9
        else:
            assert s <= 1e-9


def test_rotating_the_whole_scene_leaves_the_time_to_contact_unchanged():
    rng = np.random.default_rng(3)
    for _ in range(60):
        d = rng.uniform(-40, 40, 2)
        w = rng.uniform(-12, 12, 2)
        ha, hb, rot = rng.uniform(0, 360, 3)
        t0, s0 = one(d, w, ha, hb)
        r = np.array(
            [
                [math.cos(math.radians(rot)), -math.sin(math.radians(rot))],
                [math.sin(math.radians(rot)), math.cos(math.radians(rot))],
            ]
        )
        t1, s1 = one(r @ d, r @ w, ha + rot, hb + rot)
        assert s1 == pytest.approx(s0, abs=1e-9)
        if math.isinf(t0) or math.isnan(t0):
            assert (math.isinf(t1) and math.isinf(t0)) or (math.isnan(t1) and math.isnan(t0))
        else:
            assert t1 == pytest.approx(t0, abs=1e-9)


def test_arrays_of_pairs_equal_the_pair_by_pair_values():
    rng = np.random.default_rng(11)
    n = 40
    d, w = rng.uniform(-40, 40, (n, 2)), rng.uniform(-12, 12, (n, 2))
    ha, hb = rng.uniform(0, 360, (2, n))
    ea, eb = np.tile(TRUCK, (n, 1)), np.tile(LV, (n, 1))
    t, s = obb_pairs(d, w, np.stack([unit(x) for x in ha]), np.stack([unit(x) for x in hb]), ea, eb)
    for k in range(n):
        tk, sk = one(d[k], w[k], ha[k], hb[k])
        assert (math.isnan(tk) and math.isnan(t[k])) or t[k] == tk
        assert s[k] == sk

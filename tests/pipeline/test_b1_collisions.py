# ruff: noqa: E501, PT018
"""Case B1 vehicles that do not overlap (docs M20, spec 018 FR-018-55): the footprints and collision events of `pitstudio_pipeline.haulage.traffic`.

Oracles, none of them the code under test:
- `shapely` rectangles of the footprints placed at every recorded position with the heading of the straight path (the paths here are straight, so the heading is known by construction);
- analytical encounters worked by hand (a crossing at a right angle without interaction, a stopped body in a lane);
- the asset specification of the vehicles (13.36 x 8.563 m truck, 5.275 x 1.96 m light vehicle) for the default footprints.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import shapely.affinity
import shapely.geometry
from pitstudio_pipeline.haulage import traffic as T

TRUCK_L, TRUCK_W, LV_L, LV_W = 13.36, 8.563, 5.275, 1.96


def line(p0, p1, t0, t1):
    tl = T.Timeline()
    tl.stay(0.0, p0)
    tl.move(t0, t1, p0, p1)
    return tl


def at_rest(p):
    tl = T.Timeline()
    tl.stay(0.0, p)
    return tl


def veh(vid, kind, tl, auton=False):
    return T.Vehicle(vid, kind, auton, tl)


def box(c, head_deg, length, width):
    b = shapely.geometry.box(-length / 2, -width / 2, length / 2, width / 2)
    return shapely.affinity.translate(shapely.affinity.rotate(b, head_deg, origin=(0, 0)), c[0], c[1])


def max_overlap_area(r, heads, sizes):
    """The largest area shared by the footprints of vehicles 0 and 1 over every recorded step."""
    worst = 0.0
    for step in range(r.trace_pos.shape[0]):
        a = box(r.trace_pos[step, 0], heads[0], *sizes[0])
        b = box(r.trace_pos[step, 1], heads[1], *sizes[1])
        worst = max(worst, a.intersection(b).area)
    return worst


def test_the_default_footprints_are_the_asset_specification_dimensions():
    assert T.DEFAULTS["footprint_m"]["haul-truck"] == [TRUCK_L, TRUCK_W]
    assert T.DEFAULTS["footprint_m"]["light-vehicle"] == [LV_L, LV_W]
    assert "radius_m" not in T.DEFAULTS  # the disc radii of the first version are gone


def test_a_crossing_without_interaction_is_one_collision_event_and_no_encounter_has_a_ttc_of_zero():
    truck = line((-100.0, 0.0), (100.0, 0.0), 0.5, 0.5 + 200 / 8)
    lv = line((0.0, -112.0), (0.0, 112.0), 0.5, 0.5 + 224 / 9)
    r = T.simulate(
        [veh(1, T.TRUCK, truck), veh(1000, T.LIGHT, lv)], horizon_s=60.0, warmup_s=0.0, interactions=False, trace=True
    )
    assert r.collisions == 1 and len(r.encounters) == 1
    e = r.encounters
    assert e["collisions"][0] == 1
    assert 0.0 < e["min_ttc"][0] < 3.0  # the closest approach before the contact; the overlap itself has no TTC
    assert not np.any(e["min_ttc"] == 0.0)
    assert (
        max_overlap_area(r, (0.0, 90.0), ((TRUCK_L, TRUCK_W), (LV_L, LV_W))) > 1.0
    )  # without interaction the bodies do overlap, and it is counted


def test_with_interaction_the_light_vehicle_yields_and_the_bodies_never_overlap():
    truck = line((-100.0, 0.0), (100.0, 0.0), 0.5, 0.5 + 200 / 8)
    lv = line((0.0, -112.0), (0.0, 112.0), 0.5, 0.5 + 224 / 9)
    r = T.simulate([veh(1, T.TRUCK, truck), veh(1000, T.LIGHT, lv)], horizon_s=60.0, warmup_s=0.0, trace=True)
    assert r.collisions == 0
    assert max_overlap_area(r, (0.0, 90.0), ((TRUCK_L, TRUCK_W), (LV_L, LV_W))) == 0.0
    assert np.all(r.encounters["min_ttc"] > 0.0)


@pytest.mark.parametrize("reaction", [10.0, 30.0])
def test_a_late_reaction_ends_in_a_collision_event_and_a_held_body_not_in_an_overlap(reaction):
    slow = line((100.0, 0.0), (1500.0, 0.0), 0.0, 280.0)  # 5 m/s
    fast = line((0.0, 0.0), (2000.0, 0.0), 0.0, 200.0)  # 10 m/s
    r = T.simulate(
        [veh(1, T.TRUCK, fast), veh(1000, T.LIGHT, slow)], horizon_s=40.0, warmup_s=0.0, trace=True,
        params={"reaction_s": {"autonomous": reaction, "manned": reaction}},
    )  # fmt: skip
    assert r.collisions >= 1
    assert max_overlap_area(r, (0.0, 0.0), ((TRUCK_L, TRUCK_W), (LV_L, LV_W))) == 0.0
    assert r.trace_m[:, 0].min() == 0.0  # the truck was stopped by the body ahead
    assert np.all(r.encounters["min_ttc"] > 0.0)  # no TTC of 0 and no TTC through an overlap


def test_a_collision_event_is_counted_once_per_episode_not_once_per_step():
    slow = line((100.0, 0.0), (1500.0, 0.0), 0.0, 280.0)
    fast = line((0.0, 0.0), (2000.0, 0.0), 0.0, 200.0)
    r = T.simulate(
        [veh(1, T.TRUCK, fast), veh(1000, T.LIGHT, slow)], horizon_s=40.0, warmup_s=0.0, interactions=False, trace=True
    )
    steps_overlapping = sum(
        box(r.trace_pos[s, 0], 0, TRUCK_L, TRUCK_W).intersects(box(r.trace_pos[s, 1], 0, LV_L, LV_W))
        for s in range(r.trace_pos.shape[0])
    )
    assert steps_overlapping > 3 and r.collisions == 1


def test_an_overlap_at_the_start_is_counted_has_no_ttc_and_does_not_freeze_a_body_that_moves_away():
    parked = at_rest((0.0, 0.0))
    lv = T.Timeline()
    lv.stay(0.0, (3.0, 0.0))
    lv.move(1.0, 101.0, (3.0, 0.0), (503.0, 0.0))  # drives away east at 5 m/s from inside the truck's footprint
    r = T.simulate([veh(1, T.TRUCK, parked), veh(1000, T.LIGHT, lv)], horizon_s=60.0, warmup_s=0.0, trace=True)
    assert r.collisions == 1
    assert not np.any(r.encounters["min_ttc"] == 0.0)
    assert r.final_tau[1] > 50.0 and r.trace_pos[-1, 1, 0] > 100.0  # it left


def test_a_light_vehicle_stops_short_of_a_truck_at_rest_in_its_lane():
    parked = at_rest((100.0, 0.0))
    lv = line((0.0, 0.0), (1000.0, 0.0), 0.0, 100.0)
    r = T.simulate([veh(1, T.TRUCK, parked), veh(1000, T.LIGHT, lv)], horizon_s=60.0, warmup_s=0.0, trace=True)
    assert r.collisions == 0
    assert max_overlap_area(r, (0.0, 0.0), ((TRUCK_L, TRUCK_W), (LV_L, LV_W))) == 0.0
    assert r.trace_pos[-1, 1, 0] < 100.0 - TRUCK_L / 2 - LV_L / 2  # stopped short of the body
    assert r.trace_m[:, 1].min() < 1.0


def test_a_light_vehicle_at_rest_off_the_road_is_not_an_obstacle():
    dwelling = at_rest((100.0, 0.0))
    truck = line((0.0, 0.0), (1000.0, 0.0), 0.0, 100.0)
    r = T.simulate([veh(1, T.TRUCK, truck), veh(1000, T.LIGHT, dwelling)], horizon_s=40.0, warmup_s=0.0, trace=True)
    assert len(r.encounters) == 0 and r.trace_m.min() == 1.0


def test_vehicles_that_would_overlap_cross_the_same_point_one_after_the_other_in_a_run_with_many_light_vehicles():
    # four light vehicles converge on one point from four sides while a truck passes: nobody overlaps anybody at any step
    truck = line((-150.0, 0.0), (150.0, 0.0), 1.0, 1.0 + 300 / 8)
    lvs = [
        line((0.0, -120.0), (0.0, 120.0), 1.0, 1.0 + 240 / 9),
        line((0.0, 120.0), (0.0, -120.0), 1.0, 1.0 + 240 / 9),
        line((-120.0, 12.0), (120.0, 12.0), 1.0, 1.0 + 240 / 9),
        line((120.0, -12.0), (-120.0, -12.0), 1.0, 1.0 + 240 / 9),
    ]
    vs = [veh(1, T.TRUCK, truck)] + [veh(1000 + k, T.LIGHT, tl) for k, tl in enumerate(lvs)]
    r = T.simulate(vs, horizon_s=90.0, warmup_s=0.0, trace=True)
    heads = [0.0, 90.0, -90.0, 0.0, 180.0]
    sizes = [(TRUCK_L, TRUCK_W)] + [(LV_L, LV_W)] * 4
    for step in range(r.trace_pos.shape[0]):
        boxes = [box(r.trace_pos[step, k], heads[k], *sizes[k]) for k in range(5)]
        for i in range(5):
            for j in range(i + 1, 5):
                assert boxes[i].intersection(boxes[j]).area < 1e-6, (step, i, j)
    assert np.all(np.isfinite(r.final_tau)) and np.all(r.encounters["min_ttc"] > 0.0)
    assert not any(math.isnan(x) for x in r.encounters["min_ttc"])

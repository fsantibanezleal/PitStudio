# ruff: noqa: E501, PT018, RUF059
"""Case B1 traffic layer (docs M20, spec 018 FR-018-55): `pitstudio_pipeline.haulage.traffic`.

Oracles, none of them the code under test:
- analytical encounters with straight paths, written here (a crossing at a right angle, a slow vehicle ahead in the same lane, a head-on pass in two lanes,
  a vehicle that cannot yield), with the minimum distance and the contact counted by a direct scan of the positions the layer returned;
- `networkx` shortest paths for the light-vehicle router;
- the engine's own KPI layer for the tonnes (no interaction: the delivered tonnes of the window equal the engine's production), and the engine's fleet
  for the conservation of vehicles;
- geometry written by hand for the lane offset (a straight road offset to the right; two opposing lanes at twice the offset).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _b1_kit as kit
from pitstudio_pipeline.haulage import traffic as T
from pitstudio_pipeline.haulage.legs import run_shift_with_legs


def line(p0, p1, t0, t1):
    tl = T.Timeline()
    tl.stay(0.0, p0)
    tl.move(t0, t1, p0, p1)
    return tl


def veh(vid, kind, tl, auton=False):
    return T.Vehicle(vid, kind, auton, tl)


def cross2(a, b):
    return float(a[0] * b[1] - a[1] * b[0])


def scan_min_dist(r, i=0, j=1):
    return float(np.hypot(*(r.trace_pos[:, j] - r.trace_pos[:, i]).T).min())


# ---------------------------------------------------------------- geometry


def test_a_straight_road_is_offset_to_the_right_by_the_lane_offset():
    pts = np.array([[0.0, 0.0], [100.0, 0.0]])
    assert np.allclose(
        T.offset_polyline(pts, 6.5), [[0.0, -6.5], [100.0, -6.5]]
    )  # driving east, the right-hand side is south
    assert np.allclose(T.offset_polyline(pts[::-1], 6.5), [[100.0, 6.5], [0.0, 6.5]])


def test_opposing_lanes_are_twice_the_offset_apart_on_a_bent_road():
    pts = np.array([[0.0, 0.0], [100.0, 200.0], [130.0, 300.0]])
    fwd, back = T.offset_polyline(pts, 6.5), T.offset_polyline(pts[::-1], 6.5)[::-1]
    for a, b in zip(fwd, back, strict=True):
        assert math.hypot(*(a - b)) == pytest.approx(13.0, rel=0.01)


def test_a_right_angle_corner_is_mitered_at_the_offset_distance_from_both_edges():
    pts = np.array(
        [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0]]
    )  # east then north: a left turn, the right-hand lane is the outside
    off = T.offset_polyline(pts, 5.0)
    assert np.allclose(off[1], [105.0, -5.0])
    assert np.allclose(off[0], [0.0, -5.0]) and np.allclose(off[2], [105.0, 100.0])


def test_a_repeated_vertex_has_no_offset_and_a_u_turn_does_not_blow_up():
    with pytest.raises(ValueError, match="repeated"):
        T.offset_polyline(np.array([[0.0, 0.0], [0.0, 0.0], [1.0, 0.0]]), 5.0)
    out = T.offset_polyline(np.array([[0.0, 0.0], [50.0, 0.0], [0.0, 0.0]]), 5.0)
    assert np.all(np.isfinite(out))


def test_shortest_path_equals_networkx_on_the_pit_like_network(tmp_path):
    _, bundle = kit.write_bundle(tmp_path)
    net = T.road_net(bundle)
    g = nx.Graph()
    for sid, s in net.segments.items():
        g.add_edge(s["a"], s["b"], weight=s["length_m"], sid=sid)
    for a in net.nodes:
        for b in net.nodes:
            if a == b:
                continue
            path = T.shortest_path(net, a, b)
            length = sum(net.segments[sid]["length_m"] for sid, _ in path)
            assert length == pytest.approx(nx.shortest_path_length(g, a, b, weight="weight"), rel=1e-12)
            node = a  # the path is connected and ends at b
            for sid, d in path:
                s = net.segments[sid]
                assert node == (s["a"] if d > 0 else s["b"])
                node = s["b"] if d > 0 else s["a"]
            assert node == b


def test_no_road_path_is_an_error():
    net = T.RoadNet({1: (0.0, 0.0), 2: (1.0, 0.0)}, {}, {})
    with pytest.raises(ValueError, match="no road path"):
        T.shortest_path(net, 1, 2)


# ---------------------------------------------------------------- analytical encounters


def test_a_crossing_conflict_is_avoided_by_the_light_vehicle_and_happens_without_interaction():
    truck = line((-100.0, 0.0), (100.0, 0.0), 0.5, 0.5 + 200 / 8)
    lv = line((0.0, -112.0), (0.0, 112.0), 0.5, 0.5 + 224 / 9)
    for auton in (False, True):
        r = T.simulate(
            [veh(1, T.TRUCK, truck, auton), veh(1000, T.LIGHT, lv)], horizon_s=60.0, warmup_s=0.0, trace=True
        )
        assert r.contacts == 0 and r.near_misses == 0
        assert scan_min_dist(r) > 7.0  # the disc radii of a truck and a light vehicle sum to 7 m
        assert r.trace_m[:, 1].min() < 1.0  # it was the light vehicle that braked
    r0 = T.simulate(
        [veh(1, T.TRUCK, truck), veh(1000, T.LIGHT, lv)], horizon_s=60.0, warmup_s=0.0, interactions=False, trace=True
    )
    assert r0.contacts == 1 and r0.near_misses == 1
    assert scan_min_dist(r0) < 7.0
    assert r0.encounters["min_ttc"][0] == pytest.approx(0.0)


def test_head_on_vehicles_in_their_own_lanes_never_close():
    a = T.Timeline()
    b = T.Timeline()
    pts = np.array([[0.0, 0.0], [400.0, 0.0]])
    fwd, back = T.offset_polyline(pts, 6.5), T.offset_polyline(pts[::-1], 6.5)
    a.stay(0.0, fwd[0])
    a.move(1.0, 41.0, fwd[0], fwd[1])
    b.stay(0.0, back[0])
    b.move(1.0, 41.0, back[0], back[1])
    r = T.simulate([veh(1, T.TRUCK, a), veh(1000, T.LIGHT, b)], horizon_s=45.0, warmup_s=0.0, trace=True)
    assert len(r.encounters) == 1 and math.isinf(
        r.encounters["min_ttc"][0]
    )  # an encounter (they pass within 60 m) without a TTC
    assert r.near_misses == 0 and r.contacts == 0
    assert scan_min_dist(r) == pytest.approx(13.0, abs=0.01)
    assert r.trace_m.min() == 1.0  # nobody braked


def test_a_vehicle_behind_a_slower_one_in_the_same_lane_stops_short_of_it_and_a_shorter_reaction_stops_shorter():
    slow = line((100.0, 0.0), (1500.0, 0.0), 0.0, 280.0)  # 5 m/s
    gaps = {}
    for reaction in (0.5, 1.5, 3.0):
        fast = line((0.0, 0.0), (2000.0, 0.0), 0.0, 200.0)  # 10 m/s
        r = T.simulate(
            [veh(1, T.TRUCK, fast, True), veh(1000, T.LIGHT, slow)], horizon_s=40.0, warmup_s=0.0, trace=True,
            params={"reaction_s": {"autonomous": reaction, "manned": reaction}},
        )  # fmt: skip
        gaps[reaction] = scan_min_dist(r)
        assert r.trace_m[:, 0].min() < 1.0  # the truck braked
    assert gaps[0.5] > gaps[1.5] > gaps[3.0]
    assert gaps[0.5] > 7.0  # no overlap with the autonomous reaction time, discs of 5 m and 2 m
    free = T.simulate(
        [veh(1, T.TRUCK, line((0.0, 0.0), (2000.0, 0.0), 0.0, 200.0)), veh(1000, T.LIGHT, slow)],
        horizon_s=40.0,
        warmup_s=0.0,
        interactions=False,
        trace=True,
    )
    assert scan_min_dist(free) < 7.0 and free.contacts == 1


def test_the_autonomous_flag_acts_only_through_the_reaction_time():
    def run(auton, react_a, react_m):
        slow = line((100.0, 0.0), (1500.0, 0.0), 0.0, 280.0)
        fast = line((0.0, 0.0), (2000.0, 0.0), 0.0, 200.0)
        return T.simulate(
            [veh(1, T.TRUCK, fast, auton), veh(1000, T.LIGHT, slow)],
            horizon_s=40.0,
            warmup_s=0.0,
            trace=True,
            params={"reaction_s": {"autonomous": react_a, "manned": react_m}},
        )

    a = run(True, 1.5, 0.5)  # an autonomous truck whose reaction time was set to the manned value ...
    b = run(False, 0.5, 1.5)  # ... is the manned truck of the other setting
    assert np.array_equal(a.trace_pos, b.trace_pos) and np.array_equal(a.trace_m, b.trace_m)


def test_a_block_longer_than_the_release_time_ends_with_a_negotiated_go():
    crawler = line(
        (60.0, 0.0), (200.0, 0.0), 0.0, 700.0
    )  # 0.2 m/s, planned moving, in the lane of a 10 m/s truck behind it
    truck = line((0.0, 0.0), (5000.0, 0.0), 0.0, 500.0)
    r = T.simulate(
        [veh(1, T.TRUCK, truck), veh(1000, T.LIGHT, crawler)],
        horizon_s=200.0,
        warmup_s=0.0,
        trace=True,
        params={"release_s": 20.0},
    )
    assert r.releases >= 1
    held = (r.trace_m[:, 0] < 0.5).sum() * 0.5
    assert 15.0 < held < 120.0  # blocked for about the release time, not for the whole run


# ---------------------------------------------------------------- the whole network


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    path, bundle = kit.write_bundle(tmp_path_factory.mktemp("b1traffic"), n_trucks=4, horizon_s=3600.0)
    run = run_shift_with_legs(path, seed=5)
    net = T.road_net(bundle)
    return path, bundle, run, net, [t["id"] for t in bundle["fleet"]]


def fleet(world, share, n_lv, seed=5):
    _, bundle, run, net, ids = world
    cfg = T._params(None)
    trucks = T.truck_vehicles(net, run, bundle, cfg["lane_offset_m"], T.autonomous_trucks(ids, share, seed))
    return trucks + T.light_vehicles(net, list(range(1, 7)), seed, n_lv, bundle["horizon_s"], cfg, 1000)


def test_without_interaction_the_delivered_tonnes_equal_the_engine_production(world):
    _, bundle, run, net, _ = world
    r = T.simulate(fleet(world, 0.5, 0), horizon_s=3600.0, warmup_s=600.0, net=net, interactions=False)
    window_h = (3600.0 - 600.0) / 3600.0
    assert r.tonnes_des == pytest.approx(run.result.kpis["fleet"]["production_tph"] * window_h, rel=1e-9)
    assert r.tonnes_delivered == pytest.approx(r.tonnes_des, rel=1e-9)
    assert r.n_vehicles == len(bundle["fleet"])  # vehicles are neither created nor lost
    assert np.all(np.isfinite(r.final_tau)) and r.held_truck_s == 0.0 and len(r.encounters) == 0


def test_vehicles_are_conserved_and_tonnes_never_exceed_the_engine_schedule(world):
    _, bundle, _, net, ids = world
    for share in (0.0, 1.0):
        r = T.simulate(fleet(world, share, 8), horizon_s=3600.0, warmup_s=600.0, net=net, trace=True)
        assert r.n_vehicles == len(ids) + 8
        assert r.trace_pos.shape[1] == len(ids) + 8 and np.all(np.isfinite(r.trace_pos))
        assert r.tonnes_delivered <= r.tonnes_des + 1e-9
        assert np.all(
            r.final_tau <= 3600.0 + 0.5 + 1e-9
        )  # no vehicle runs ahead of its schedule (the last step ends one step past the horizon)
        assert r.trace_m.min() >= 0.0 and r.trace_m.max() <= 1.0


def test_light_vehicles_stay_on_the_road_network_with_the_lane_offset(world):
    _, bundle, _, net, _ = world
    cfg = T._params(None)
    lv = T.light_vehicles(net, list(range(1, 7)), 5, 3, 3600.0, cfg, 1000)
    segs = list(net.segments.values())
    for v in lv:
        t, p, vel = v.timeline.arrays()
        for k in range(0, len(t), 3):
            q = p[k]
            dmin = min(
                abs(cross2(s["pts"][i + 1] - s["pts"][i], q - s["pts"][i])) / np.hypot(*(s["pts"][i + 1] - s["pts"][i]))
                for s in segs for i in range(len(s["pts"]) - 1)
            )  # fmt: skip
            assert dmin < cfg["lane_offset_m"] * 3.0 + 1e-6  # within the miter cap of a road polyline


def test_a_run_is_deterministic_and_the_light_vehicle_and_autonomous_sets_nest(world):
    _, bundle, _, net, ids = world
    a = T.simulate(fleet(world, 0.5, 8), horizon_s=3600.0, warmup_s=600.0, net=net)
    b = T.simulate(fleet(world, 0.5, 8), horizon_s=3600.0, warmup_s=600.0, net=net)
    assert (
        np.array_equal(a.encounters, b.encounters)
        and a.tonnes_delivered == b.tonnes_delivered
        and a.held_truck_s == b.held_truck_s
    )
    cfg = T._params(None)
    small = T.light_vehicles(net, list(range(1, 7)), 5, 4, 3600.0, cfg, 1000)
    big = T.light_vehicles(net, list(range(1, 7)), 5, 8, 3600.0, cfg, 1000)
    for x, y in zip(small, big[:4], strict=True):
        assert np.array_equal(x.timeline.arrays()[1], y.timeline.arrays()[1])
    sets = [T.autonomous_trucks(ids + list(range(100, 116)), s, 5) for s in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert [len(x) for x in sets] == [0, 5, 10, 15, 20]
    assert all(sets[k] <= sets[k + 1] for k in range(4))


def test_hostile_arguments():
    with pytest.raises(ValueError, match="share"):
        T.autonomous_trucks([1, 2], 1.5, 0)
    with pytest.raises(ValueError, match="no vehicles"):
        T.simulate([], horizon_s=10.0, warmup_s=0.0)
    with pytest.raises(ValueError, match="unknown traffic parameter"):
        T.simulate([veh(1, T.TRUCK, line((0, 0), (1, 0), 0.0, 1.0))], horizon_s=10.0, warmup_s=0.0, params={"nope": 1})
    with pytest.raises(ValueError, match="unique"):
        T.simulate(
            [veh(1, T.TRUCK, line((0, 0), (1, 0), 0.0, 1.0)), veh(1, T.LIGHT, line((0, 0), (1, 0), 0.0, 1.0))],
            horizon_s=10.0,
            warmup_s=0.0,
        )
    tl = T.Timeline()
    tl.stay(5.0, (0.0, 0.0))
    with pytest.raises(ValueError, match="backwards"):
        tl.stay(1.0, (0.0, 0.0))
    with pytest.raises(ValueError, match="t1 > t0"):
        tl.move(5.0, 5.0, (0, 0), (1, 0))


def test_vehicles_on_roads_that_share_no_node_do_not_interact():
    # two roads side by side 3 m apart without a shared node: a pass would be a conflict if they were one road
    segs = {
        1: {"a": 1, "b": 2, "pts": np.array([[0.0, 0.0], [400.0, 0.0]]), "length_m": 400.0, "limit_kmh": 40.0},
        2: {"a": 3, "b": 4, "pts": np.array([[0.0, 3.0], [400.0, 3.0]]), "length_m": 400.0, "limit_kmh": 40.0},
    }
    two = T.RoadNet({1: (0, 0), 2: (400, 0), 3: (0, 3), 4: (400, 3)}, segs, {})
    a, b = T.Timeline(), T.Timeline()
    a.stay(0.0, (0.0, 0.0))
    a.move(1.0, 41.0, (0.0, 0.0), (400.0, 0.0), 1)
    b.stay(0.0, (400.0, 3.0))
    b.move(1.0, 41.0, (400.0, 3.0), (0.0, 3.0), 2)
    r = T.simulate([veh(1, T.TRUCK, a), veh(1000, T.LIGHT, b)], horizon_s=45.0, warmup_s=0.0, net=two)
    assert len(r.encounters) == 0
    segs[2]["a"] = 2  # now the roads meet at a node: the same pair is evaluated and touches
    joined = T.RoadNet(two.nodes, segs, {})
    r = T.simulate(
        [veh(1, T.TRUCK, a), veh(1000, T.LIGHT, b)], horizon_s=45.0, warmup_s=0.0, net=joined, interactions=False
    )
    assert len(r.encounters) == 1 and r.contacts == 1

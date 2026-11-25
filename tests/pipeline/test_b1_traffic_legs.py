# ruff: noqa: E501, B007
"""Case B1 leg recorder (docs M20 "haul trucks follow trajectories from the DES"): `pitstudio_pipeline.haulage.legs`.

Oracles, none of them the code under test:
- the same shift run through `adapter.run_shift` without the recorder (equality of the whole trace and of the KPIs: the recorder only reads);
- the engine's own arrival hook (the arrivals of every loader and dump), which must equal the exit time of the last segment of the leg that ends there;
- the bundle's node coordinates: a truck placed by its timeline (lane offset 0) is at the node of its leg's end at the arrival time;
- the road graph: consecutive passes of a leg share a node, and the passes lie on segments of the bundle.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _b1_kit as kit
from minehaulsim.des import sim, traversal
from pitstudio_pipeline.haulage import traffic as T
from pitstudio_pipeline.haulage.adapter import run_shift
from pitstudio_pipeline.haulage.legs import run_shift_with_legs


@pytest.fixture(scope="module")
def shift(tmp_path_factory):
    path, bundle = kit.write_bundle(tmp_path_factory.mktemp("b1legs"), n_trucks=4, horizon_s=3600.0)
    return path, bundle, run_shift_with_legs(path, seed=3), run_shift(path, seed=3)


def test_the_recorder_changes_nothing_in_the_trace_or_the_kpis(shift):
    _, _, rec, plain = shift
    assert rec.result.trace == plain.trace
    assert rec.result.kpis == plain.kpis
    assert rec.result.cyclelog == plain.cyclelog


def test_the_engine_methods_are_restored_after_the_run_and_after_an_error(shift, tmp_path):
    path, _, _, _ = shift
    before = (sim._Sim._go, traversal.TrafficState.traverse, sim._Sim._go_load, sim._Sim._arrive_dump)
    run_shift_with_legs(path, seed=1)
    assert (sim._Sim._go, traversal.TrafficState.traverse, sim._Sim._go_load, sim._Sim._arrive_dump) == before
    with pytest.raises(Exception):  # noqa: B017, PT011  (an invalid seed is refused by the adapter after the wrappers are installed)
        run_shift_with_legs(path, seed=-1)
    assert (sim._Sim._go, traversal.TrafficState.traverse, sim._Sim._go_load, sim._Sim._arrive_dump) == before


def test_the_last_segment_of_a_leg_exits_at_the_engine_arrival(shift):
    _, bundle, rec, _ = shift
    arrivals: dict[int, list[float]] = {}
    for kind, t, truck, _node in rec.arrivals:
        arrivals.setdefault(truck, []).append(t)
    ends: dict[int, list[float]] = {}
    for leg in rec.legs:
        if leg.passes:
            ends.setdefault(leg.truck, []).append(leg.passes[-1].t_exit_s)
    assert ends, "no leg was recorded"
    checked = 0
    for truck, times in ends.items():
        unmatched = [t for t in times if not any(abs(t - a) < 1e-9 for a in arrivals.get(truck, []))]
        # at most the leg still under way at the horizon has no arrival (its recorded passes stop where the shift stops)
        assert len(unmatched) <= 1, (truck, unmatched)
        if unmatched:
            assert unmatched[0] == max(times)
        checked += len(times) - len(unmatched)
    assert checked >= 8
    assert set(ends) <= {t["id"] for t in bundle["fleet"]}


def test_passes_follow_the_road_graph_in_time_order(shift):
    _, bundle, rec, _ = shift
    seg = {s["id"]: s for s in bundle["network"]["segments"]}
    for leg in rec.legs:
        prev_exit, prev_node = leg.t_call_s, None
        for p in leg.passes:
            s = seg[p.segment_id]
            entry, exit_ = (s["a"], s["b"]) if p.direction > 0 else (s["b"], s["a"])
            if prev_node is not None:
                assert entry == prev_node
            assert p.t_request_s >= prev_exit - 1e-9
            assert (
                p.t_exit_s >= p.t_request_s + p.t_kinematic_s - 1e-6
            )  # the engine never exits before request + kinematic time
            assert p.t_kinematic_s > 0
            prev_exit, prev_node = p.t_exit_s, exit_


def test_a_truck_timeline_without_lane_offset_is_at_the_arrival_node_at_the_arrival_time(shift):
    _, bundle, rec, _ = shift
    net = T.road_net(bundle)
    by_truck = {}
    for leg in rec.legs:
        by_truck.setdefault(leg.truck, []).append(leg)
    node_of = {}
    for leg in rec.legs:
        if leg.passes:
            last = leg.passes[-1]
            s = net.segments[last.segment_id]
            node_of[(leg.truck, last.t_exit_s)] = s["b"] if last.direction > 0 else s["a"]
    checked = 0
    for truck, legs in by_truck.items():
        start = next(t["start_loader"] for t in bundle["fleet"] if t["id"] == truck)
        t, p, v = T.truck_timeline(net, legs, start, 0.0).arrays()
        for (tr, te), node in node_of.items():
            if tr != truck:
                continue
            k = int(np.searchsorted(t, te, side="right")) - 1
            pos = p[k] + v[k] * (te - t[k])
            assert np.hypot(*(pos - np.array(net.nodes[node]))) < 1e-6, (truck, te, node)
            checked += 1
    assert checked >= 8


def test_two_runs_record_the_same_legs(shift, tmp_path):
    path, _, rec, _ = shift
    again = run_shift_with_legs(path, seed=3)
    assert [(g.truck, g.t_call_s, g.loaded, g.passes) for g in again.legs] == [
        (g.truck, g.t_call_s, g.loaded, g.passes) for g in rec.legs
    ]
    assert again.arrivals == rec.arrivals

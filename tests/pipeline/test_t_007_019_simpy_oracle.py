# ruff: noqa: E501, PT018
"""T-007-019: an independent SimPy model of small fast-mode scenarios, fed by the same variate streams, compared with the reference cyclelog.

Requirements: P-007-12.

Spec: specs/007-haulage-dispatch/spec.md P-007-12 (on scenarios with <= 2 loaders, 1 dump, <= 8 trucks, fast mode and `fixed` or `nearest` dispatch, an independent SimPy model fed by the
same variate streams gives the same cyclelog: identical events, cycles and tonnes, and times within 1e-6 s; 20 random small scenarios x 3 seeds), plan.md (oracle: independent SimPy model
written in the test; times within 1e-6 s because the SimPy clock may accumulate in a different order) and the cycle semantics of the engine (docstring of `minehaulsim/des/sim.py`).

Oracle: the SimPy model below. It re-implements the haul cycle with SimPy resources (FIFO queues: capacity n_spots at a loader, 1 at the dump) and draws from `VariateSource` in the same
per-purpose streams the engine's `RngManager` names (`init` for the stagger, `loadtime`, `payload`, `dumptime`); the free-flow leg times are the reference router's (`minehaulsim.network.routing.Router`,
the kinematics are not under test here); no number is taken from the adapter. Cycle rules: a truck arrives at its start loader after a stagger of uniform(0, stagger window); loading takes
mean x unit-mean lognormal(sigma = loader time_cv) with mean = ceil(payload_mean / pass_t) x pass_time + spot_time; the payload is normal(mean, sd) clipped to [0.5 mean, 400]; the loaded truck
leaves at the end of loading and releases the spot; the dump takes dump_mean_s x unit-mean lognormal(dump_cv); `fixed` returns to the start loader, `nearest` goes to the loader with the smallest
free-flow time from the dump (ties: lowest node id).

Expected API: `pitstudio_pipeline.haulage.adapter.run_shift` (test_t_007_013), `pitstudio_pipeline.haulage.variates.VariateSource` and `decode_table` (test_t_007_011). SimPy is imported inside the
test functions (it is a dev dependency of the pipeline environment, T-007-002).
"""

from __future__ import annotations

import math
import random
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit as kit
from pitstudio_pipeline.haulage.adapter import run_shift
from pitstudio_pipeline.haulage.variates import VariateSource, decode_table

TIME_TOL = 1e-6


def random_scenario(k: int) -> dict:
    """Scenario k of 20: a star network (loaders - junction - dump), 1 or 2 loaders, 1 to 8 trucks, `fixed` or `nearest`, fast mode, engine profile."""
    rnd = random.Random(7000 + k)
    n_loaders = rnd.choice([1, 2])
    b = kit.smoke_bundle()
    pos = {1: (0.0, 0.0, 1500.0), 2: (0.0, 900.0, 1500.0), 3: (1100.0, 450.0, 1520.0), 4: (2300.0, 450.0, 1540.0)}
    nodes = (
        [{"id": 1, "kind": "face", "pos_m": list(pos[1])}]
        + ([{"id": 2, "kind": "face", "pos_m": list(pos[2])}] if n_loaders == 2 else [])
        + [{"id": 3, "kind": "junction", "pos_m": list(pos[3])}, {"id": 4, "kind": "dump", "pos_m": list(pos[4])}]
    )
    edges = [(1, 3)] + ([(2, 3)] if n_loaders == 2 else []) + [(3, 4)]
    segs = []
    for i, (a, c) in enumerate(edges, start=1):
        pa, pc = pos[a], pos[c]
        if rnd.random() < 0.5:  # scatter the heights so that grades differ per segment
            pc = (pc[0], pc[1], pc[2] + rnd.uniform(-40.0, 60.0))
        segs.append(
            kit.segment_entry(
                i,
                a,
                c,
                pa,
                pc,
                speed_limit_kmh=rnd.choice([25.0, 30.0, 40.0, 50.0]),
                rolling_resistance_pct=rnd.choice([2.0, 2.5, 3.0]),
            )
        )
    n_trucks = rnd.randint(1, 8)
    b["network"] = {"nodes": nodes, "segments": segs, "zones": [], "junctions": []}
    b["loaders"] = [
        {"node": n, "loader_class": "SHOVEL_45", "n_spots": 1, "destination_dump": 4} for n in range(1, n_loaders + 1)
    ]
    b["dumps"] = [4]
    b["fleet"] = [
        {"id": i + 1, "truck_class": "CAT_793F", "start_loader": rnd.randint(1, n_loaders)} for i in range(n_trucks)
    ]
    b["dispatcher"] = {"id": rnd.choice(["fixed", "nearest"])}
    b["mode"] = "fast"
    b["horizon_s"] = float(rnd.choice([7200, 10800, 14400]))
    b["id"] = f"simpy-oracle-{k}"
    return kit.with_engine_profile(b)


def engine_router(b: dict):
    from minehaulsim.network.graph import NodeSite, RoadNetwork, Segment
    from minehaulsim.network.routing import Router

    net = RoadNetwork()
    for n in b["network"]["nodes"]:
        net.add_node(NodeSite(n["id"], n["kind"], tuple(n["pos_m"])))
    for s in b["network"]["segments"]:
        net.add_segment(
            Segment(
                id=s["id"], a=s["a"], b=s["b"], polyline=np.asarray(s["polyline_m"], dtype=float), length_m=s["length_m"], grade_pct=s["grade_pct"],
                width_class=s["width_class"], one_way=s["one_way"], speed_limit_kmh=s["speed_limit_kmh"], zone_id=s["zone_id"],
                rolling_resistance_pct=s["rolling_resistance_pct"], single_lane_op=s["single_lane_op"],
            )
        )  # fmt: skip
    return Router(net.freeze())


def simpy_cyclelog(b: dict, seed: int) -> list[tuple[float, int, int, str, float]]:
    import simpy
    from minehaulsim.equipment.catalog import LOADERS, TRUCKS

    tables = {(t["family"], t.get("sigma")): decode_table(t) for t in b["quantile_tables"]}
    src = VariateSource(seed, profile="engine", tables=tables)
    router = engine_router(b)
    consts = b["engine_constants"]
    env = simpy.Environment()
    loader_nodes = [ld["node"] for ld in b["loaders"]]
    spot = {ld["node"]: simpy.Resource(env, capacity=ld["n_spots"]) for ld in b["loaders"]}
    lclass = {ld["node"]: LOADERS[ld["loader_class"]] for ld in b["loaders"]}
    dump_node = b["dumps"][0]
    dump = simpy.Resource(env, capacity=1)
    rows: list[tuple[float, int, int, str, float]] = []
    truck_cls = {t["id"]: TRUCKS[t["truck_class"]] for t in b["fleet"]}
    stagger = {
        t["id"]: src.uniform("init", 0.0, consts["stagger_window_s"]) for t in sorted(b["fleet"], key=lambda t: t["id"])
    }  # drawn in sorted id order

    def leg(a, c, unit, loaded):
        return router.route(a, c, unit, loaded=loaded).time_s

    def truck(t):
        tid, unit, loader = t["id"], truck_cls[t["id"]], t["start_loader"]
        yield env.timeout(stagger[tid])
        while True:
            with spot[loader].request() as req:  # arrival at the loader: FIFO
                yield req
                lc = lclass[loader]
                mean = math.ceil(unit.payload_mean_t / lc.pass_t) * lc.pass_time_s + lc.spot_time_s
                rows.append((env.now, tid, loader, "load", 0.0))
                yield env.timeout(mean * src.lognormal_unit_mean("loadtime", lc.time_cv))
                payload = float(
                    max(
                        0.5 * unit.payload_mean_t,
                        min(400.0, src.normal("payload", unit.payload_mean_t, unit.payload_sd_t)),
                    )
                )
                rows.append((env.now, tid, loader, "haul", payload))
            yield env.timeout(leg(loader, dump_node, unit, True))
            with dump.request() as dreq:
                yield dreq
                rows.append((env.now, tid, dump_node, "dump", payload))
                yield env.timeout(consts["dump_mean_s"] * src.lognormal_unit_mean("dumptime", consts["dump_cv"]))
                rows.append((env.now, tid, dump_node, "return", 0.0))
            if b["dispatcher"]["id"] == "fixed":
                loader = t["start_loader"]
            else:
                loader = min(loader_nodes, key=lambda n: (leg(dump_node, n, unit, False), n))
            yield env.timeout(leg(dump_node, loader, unit, False))

    for t in b["fleet"]:
        env.process(truck(t))
    env.run(until=b["horizon_s"])
    return sorted((r for r in rows if r[0] <= b["horizon_s"]), key=lambda r: (r[0], r[1]))


@pytest.mark.req("P-007-12")
@pytest.mark.parametrize("k", range(20))
def test_the_simpy_model_reproduces_the_reference_cyclelog(k):
    b = random_scenario(k)
    with tempfile.TemporaryDirectory() as d:
        path = kit.write_bundle(Path(d), b)
        for seed in (1, 2, 3):
            res = run_shift(path, seed=seed)
            model = simpy_cyclelog(b, seed)
            ours = [(r["t_s"], r["truck"], r["node"], r["event"], r["payload_t"]) for r in res.cyclelog]
            assert [(r[1], r[2], r[3]) for r in model] == [(r[1], r[2], r[3]) for r in ours], (
                k,
                seed,
            )  # identical events, trucks and nodes in the same order
            assert all(abs(m[0] - o[0]) <= TIME_TOL for m, o in zip(model, ours, strict=True)), (k, seed)
            assert all(abs(m[4] - o[4]) <= 1e-9 for m, o in zip(model, ours, strict=True)), (k, seed)
            cycles = sum(1 for r in model if r[3] == "return")
            assert res.trace["results"]["cycles"] == cycles
            completed = (
                0.0  # tonnes of the dumps that completed (a dump still in service at the horizon is not counted)
            )
            pend = {}
            for r in model:
                if r[3] == "dump":
                    pend[r[1]] = r[4]
                elif r[3] == "return":
                    completed += pend.pop(r[1])
            assert res.trace["results"]["tonnes_t"] == pytest.approx(completed, rel=1e-12)
            assert cycles >= 1


@pytest.mark.req("P-007-12")
def test_the_scenarios_cover_the_stated_range():
    ks = [random_scenario(k) for k in range(20)]
    assert {len(s["loaders"]) for s in ks} == {1, 2}
    assert {s["dispatcher"]["id"] for s in ks} == {"fixed", "nearest"}
    assert all(1 <= len(s["fleet"]) <= 8 and len(s["dumps"]) == 1 and s["mode"] == "fast" for s in ks)
    assert max(len(s["fleet"]) for s in ks) >= 5 and min(len(s["fleet"]) for s in ks) <= 3

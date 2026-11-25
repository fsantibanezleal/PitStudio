# ruff: noqa: E501
"""The haulage adapter: one shift of the pinned `minehaulsim` reference engine with PitStudio's counter-based variate source
and a canonical event recorder (FR-007-01, FR-007-09, FR-007-13, P-007-05, P-007-21).

The seam: for the duration of a run `minehaulsim.des.sim.RngManager` is replaced by a manager whose streams draw from the
Philox variate source, and `minehaulsim.des.sim.Engine` by a recording subclass that lists every executed callback of the
pinned name map as (t_s, seq, kind, truck, node) and enforces the event budget. Both are restored on exit, also on error. The
version and module-hash guard of FR-007-02 runs first; a mismatch writes nothing.
"""

from __future__ import annotations

import functools
import hashlib
import heapq
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .dispatchers import make_dispatcher
from .errors import EventBudgetExceeded, InvalidScenario, InvalidSeed
from .honesty import stamp
from .kpi import compute_kpis
from .pin import load_pin, pin_sha256, verify_engine
from .scenario import check_connectivity, load_bundle
from .variates import VariateSource, decode_table

DEFAULT_EVENT_BUDGET = 2_000_000
MAX_SEED = 1 << 63
CLASSICAL = ("fixed", "nearest", "sptf", "sq", "random", "min-idle")


def _engine_cls():
    from minehaulsim.des.engine import Engine

    return Engine


class RecordingEngine(_engine_cls()):  # type: ignore[misc]
    """The engine's event loop with a recorder: `.records` lists every executed callback whose `__name__` is a pinned callback."""

    def __init__(self, kinds: Mapping[str, str], event_budget: int | None = None) -> None:
        super().__init__()
        self._kinds = dict(kinds)
        self._budget = event_budget
        self.records: list[dict] = []
        self.loaded_at: dict[int, int] = {}  # truck -> loader node of its last loading (read by the dump rule)

    def run(self, until_s: float) -> None:
        heap = self._heap
        while heap:
            t, seq, cb, args = heap[0]
            if t > until_s:
                break
            heapq.heappop(heap)
            if seq in self._cancelled:
                self._cancelled.discard(seq)
                continue
            if self._budget is not None and self.events_executed >= self._budget:
                raise EventBudgetExceeded(f"more than {self._budget} events executed")
            self.now = t
            name = getattr(cb, "__name__", "")
            kind = self._kinds.get(name)
            if kind is not None:
                with_truck = name in (
                    "_go_load",
                    "_loaded",
                    "_depart_loaded",
                    "_arrive_dump",
                    "_dumped",
                    "_dispatch_next",
                )
                self.records.append(
                    {
                        "t_s": t,
                        "seq": seq,
                        "kind": kind,
                        "truck": args[0] if with_truck else None,
                        "node": args[1] if with_truck else None,
                    }
                )
            if name in ("_loaded", "_depart_loaded"):
                self.loaded_at[args[0]] = args[1]
            cb(*args)
            self.events_executed += 1
        self.now = max(self.now, until_s)


class _Stream:
    """The engine's numpy-generator interface (uniform, normal, lognormal, exponential, integers) over one purpose."""

    def __init__(self, source: VariateSource, purpose: str) -> None:
        self._s, self._p = source, purpose

    def uniform(self, low: float, high: float) -> float:
        return self._s.uniform(self._p, low, high)

    def normal(self, loc: float = 0.0, scale: float = 1.0) -> float:
        return self._s.normal(self._p, loc, scale)

    def lognormal(self, mean: float = 0.0, sigma: float = 1.0) -> float:
        if abs(mean + 0.5 * sigma * sigma) > 1e-12:
            raise ValueError("only the unit-mean lognormal(-sigma^2/2, sigma) is supported by the variate source")
        return self._s.lognormal_unit_mean(self._p, sigma)

    def exponential(self, scale: float = 1.0) -> float:
        return self._s.exponential(self._p, scale)

    def integers(self, low: int, high: int) -> int:
        return self._s.integers(self._p, low, high)


class CounterRngManager:
    """Drop-in for `minehaulsim.rng.RngManager`: every stream draws from the counter-based variate source."""

    def __init__(self, source: VariateSource) -> None:
        self.source = source
        self.seed = source.seed

    def stream(self, purpose: str) -> _Stream:
        return _Stream(self.source, purpose)

    fresh = stream


@dataclass
class RunResult:
    trace: dict
    events: list[dict]
    cyclelog: list[dict]
    events_executed: int
    kpis: dict = field(default_factory=dict)


class _EnginePolicy:
    """The engine's policy interface over a Dispatcher: the dump is the declared destination of the loader just served."""

    def __init__(self, dispatcher: Any, engine: RecordingEngine) -> None:
        self.name = dispatcher.name
        self._d, self._engine = dispatcher, engine

    def next_loader(self, truck, mine) -> int:
        return self._d.next_loader(truck, mine)

    def next_dump(self, truck, mine) -> int:
        return self._d.next_dump(truck, mine, from_loader=self._engine.loaded_at.get(truck.truck_id))


def _check_seed(seed: Any) -> None:
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < MAX_SEED:
        raise InvalidSeed(f"seed must be an integer in [0, 2^63): {seed!r}")


def _check_budget(budget: Any) -> None:
    if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
        raise ValueError(f"event_budget must be a positive integer: {budget!r}")


def _check_engine_constants(bundle: dict) -> None:
    """The constants the bundle carries must equal the pinned engine's (spec section 8 (b), (d))."""
    import inspect

    from minehaulsim.des.sim import CLOSURE_RETRY_S, DUMP_CV, NOMINAL_DUMP_MEAN_S
    from minehaulsim.des.traversal import HEADWAY_S, TrafficState

    c = bundle["engine_constants"]
    pinned = {
        "stagger_window_s": 60.0,
        "dump_mean_s": NOMINAL_DUMP_MEAN_S,
        "dump_cv": DUMP_CV,
        "closure_retry_s": CLOSURE_RETRY_S,
        "headway_m": inspect.signature(TrafficState.__init__).parameters["headway_m"].default,
        "headway_s": HEADWAY_S,
        "payload_min_frac_of_mean": 0.5,
        "payload_max_t": 400.0,
    }
    bad = [
        (f"/engine_constants/{k}", c.get(k), f"must equal the pinned engine value {v!r}")
        for k, v in pinned.items()
        if c.get(k) != v
    ]
    if bad:
        raise InvalidScenario(bad)


def _network(bundle: dict):
    from minehaulsim.network.constraints import DirectionZone, Junction
    from minehaulsim.network.graph import NodeSite, RoadNetwork, Segment

    net = RoadNetwork()
    for n in bundle["network"]["nodes"]:
        net.add_node(NodeSite(n["id"], n["kind"], tuple(n["pos_m"])))
    for s in bundle["network"]["segments"]:
        net.add_segment(
            Segment(
                id=s["id"], a=s["a"], b=s["b"], polyline=np.asarray(s["polyline_m"], dtype=float), length_m=s["length_m"],
                grade_pct=s["grade_pct"], width_class=s["width_class"], one_way=s["one_way"], speed_limit_kmh=s["speed_limit_kmh"],
                zone_id=s["zone_id"], rolling_resistance_pct=s["rolling_resistance_pct"], single_lane_op=s["single_lane_op"],
            )
        )  # fmt: skip
    net.freeze()
    zones = {z["id"]: DirectionZone.from_dict(z) for z in bundle["network"]["zones"]}
    junctions = {j["node"]: Junction(j["node"], j["capacity"], j["cross_s"]) for j in bundle["network"]["junctions"]}
    return net, zones, junctions


def free_flow_cycle_s(bundle: dict, net=None, junctions=None) -> dict[str, float]:
    """T_c* per truck class: mean over loaders of loading + loaded leg to the declared dump + dumping + empty leg back, free flow."""
    from minehaulsim.equipment.catalog import LOADERS, TRUCKS
    from minehaulsim.network.routing import Router

    if net is None:
        net, _, junctions = _network(bundle)
    router = Router(net, junctions=junctions)
    consts = bundle["engine_constants"]
    out: dict[str, float] = {}
    for cls in sorted({t["truck_class"] for t in bundle["fleet"]}):
        unit = TRUCKS[cls]
        totals = []
        for ld in bundle["loaders"]:
            lc = LOADERS[ld["loader_class"]]
            load_s = math.ceil(unit.payload_mean_t / lc.pass_t) * lc.pass_time_s + lc.spot_time_s
            dump = ld.get("destination_dump", bundle["dumps"][0])
            haul = router.route(ld["node"], dump, unit, loaded=True)
            back = router.route(dump, ld["node"], unit, loaded=False)
            totals.append(load_s + haul.time_s + consts["dump_mean_s"] + back.time_s)
        out[cls] = float(sum(totals) / len(totals))
    return out


def run_shift(
    bundle_path: Path,
    *,
    seed: int,
    dispatcher: str | None = None,
    profile: str | None = None,
    trace_path: Path | None = None,
    pin_path: Path | None = None,
    variate_source: str = "counter",
    event_budget: int = DEFAULT_EVENT_BUDGET,
) -> RunResult:
    """Run one shift of the reference engine and return its trace, cyclelog, executed-event count and KPIs."""
    _check_seed(seed)
    _check_budget(event_budget)
    pin = load_pin(pin_path)
    verify_engine(pin)
    bundle_path = Path(bundle_path)
    bundle = load_bundle(bundle_path)
    if dispatcher is not None and dispatcher != bundle["dispatcher"]["id"]:
        raise InvalidScenario(
            [("/dispatcher/id", dispatcher, f"differs from the bundle's {bundle['dispatcher']['id']!r}")]
        )
    if profile is not None and profile != bundle["variate_profile"]:
        raise InvalidScenario(
            [("/variate_profile", profile, f"differs from the bundle's {bundle['variate_profile']!r}")]
        )
    did = bundle["dispatcher"]["id"]
    if did not in CLASSICAL:
        raise InvalidScenario(
            [
                (
                    "/dispatcher/id",
                    did,
                    "only the classical dispatchers run in this build; lp, ppo and attention arrive with T-007-042 and T-007-053",
                )
            ]
        )
    if variate_source not in ("counter", "engine"):
        raise ValueError(f"variate_source must be 'counter' or 'engine': {variate_source!r}")
    check_connectivity(bundle)
    _check_engine_constants(bundle)

    from minehaulsim.des import sim
    from minehaulsim.des.failures import FailureConfig
    from minehaulsim.equipment.catalog import TRUCKS  # noqa: F401  (the catalog is pinned with the engine)

    net, zones, junctions = _network(bundle)
    tables = {(t["family"], t.get("sigma")): decode_table(t) for t in bundle["quantile_tables"]}
    source = VariateSource(seed, profile=bundle["variate_profile"], tables=tables)
    engine = RecordingEngine(pin["callbacks"], event_budget)
    loaders = [sim.LoaderSpec(ld["node"], ld["loader_class"], ld["n_spots"]) for ld in bundle["loaders"]]
    trucks = [sim.TruckSpec(t["id"], t["truck_class"], t["start_loader"]) for t in bundle["fleet"]]
    destinations = {ld["node"]: ld.get("destination_dump") for ld in bundle["loaders"]}
    disp = make_dispatcher(did, destinations=destinations, rng=_Stream(source, "policy") if did == "random" else None)
    f = bundle["failures"]
    failures = None
    if f is not None:
        failures = FailureConfig(
            truck_mtbf_h=f["truck_mtbf_h"], truck_repair_mean_s=f["truck_repair_mean_s"], truck_repair_cv=f["truck_repair_cv"],
            loader_mtbf_h=f["loader_mtbf_h"], loader_repair_mean_s=f["loader_repair_mean_s"], loader_repair_cv=f["loader_repair_cv"],
            closures=tuple((c["start_s"], c["duration_s"], tuple(c["segment_ids"])) for c in f["closures"]),
        )  # fmt: skip
    original_rng, original_engine = sim.RngManager, sim.Engine
    original_go_load, original_arrive_dump = sim._Sim._go_load, sim._Sim._arrive_dump
    arrivals: list[
        tuple[str, float, int, int]
    ] = []  # every arrival at a loader or a dump, also those of a traffic traversal

    @functools.wraps(original_go_load)
    def go_load(self, tid, loader):
        arrivals.append(("arrive-loader", self.engine.now, tid, loader))
        return original_go_load(self, tid, loader)

    @functools.wraps(original_arrive_dump)
    def arrive_dump(self, tid, dump, payload):
        arrivals.append(("arrive-dump", self.engine.now, tid, dump))
        return original_arrive_dump(self, tid, dump, payload)

    if variate_source == "counter":
        sim.RngManager = lambda s: CounterRngManager(source)
    sim.Engine = lambda: engine
    sim._Sim._go_load, sim._Sim._arrive_dump = go_load, arrive_dump
    try:
        result = sim.run_shift(
            net, loaders, list(bundle["dumps"]), trucks, _EnginePolicy(disp, engine), seed, until_s=bundle["horizon_s"],
            zones=zones, junctions=junctions, fast_mode=bundle["mode"] == "fast", failures=failures,
        )  # fmt: skip
    finally:
        sim.RngManager, sim.Engine = original_rng, original_engine
        sim._Sim._go_load, sim._Sim._arrive_dump = original_go_load, original_arrive_dump

    cyclelog = [
        {
            "t_s": e["t"],
            "truck": e["truck_id"],
            "node": e["shovel_id"],
            "event": e["event"],
            "payload_t": e["payload_t"],
        }
        for e in result.events
    ]
    downtime = None
    if failures is not None:
        downtime = {
            "truck_s": [{"truck": k, "downtime_s": v} for k, v in sorted(result.downtime.get("truck_s", {}).items())],
            "loader_s": [
                {"loader": k, "downtime_s": v} for k, v in sorted(result.downtime.get("loader_s", {}).items())
            ],
        }
    trace = {
        "schema_version": "1.0",
        "header": {
            "scenario_id": bundle["id"],
            "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
            "seed": seed,
            "dispatcher": did,
            "variate_profile": bundle["variate_profile"],
            "mode": bundle["mode"],
            "horizon_s": bundle["horizon_s"],
            "kpi_window": bundle["kpi_window"],
            "engine": {"package": pin["package"], "version": pin["version"], "pin_sha256": pin_sha256(pin_path)},
            "variates": {"generator": "philox4x64-10", "key_hash": "fnv-1a-64"},
            "producer": "python-reference",
            "synthetic": True,
            "honesty": stamp(),
        },
        "events": engine.records,
        "cyclelog": cyclelog,
        "results": {
            "tonnes_t": result.tonnes,
            "cycles": result.cycles,
            "truck_wait_s": result.truck_wait_s,
            "loader_wait_s": [{"loader": k, "wait_s": v} for k, v in sorted(result.loader_wait_s.items())],
            "events_executed": result.events_executed,
            "downtime": downtime,
        },
    }
    if bundle.get("fixture") is True:
        trace["header"]["fixture"] = True
    cost = bundle.get("cost_rates")
    kpis = compute_kpis(
        trace,
        fleet=[{"id": t["id"], "truck_class": t["truck_class"]} for t in bundle["fleet"]],
        loaders=[{"node": ld["node"], "n_spots": ld["n_spots"]} for ld in bundle["loaders"]],
        free_flow_cycle_s=free_flow_cycle_s(bundle, net, junctions),
        cost_rates=cost,
        arrivals=arrivals,
    )
    if trace_path is not None:
        Path(trace_path).write_text(json.dumps(trace, indent=1, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
    return RunResult(
        trace=trace, events=trace["events"], cyclelog=cyclelog, events_executed=result.events_executed, kpis=kpis
    )

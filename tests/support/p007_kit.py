# ruff: noqa: E501
"""Shared test kit of spec 007 (haulage and dispatch): paths, contract examples, bundle builders, hashing helpers.

This is test support, not a test; it is locked with the first test file that uses it (T-007-003). Nothing here imports the code under
test. Oracles come from the spec's own contract examples (`specs/007-haulage-dispatch/contracts/examples/`, which the spec declares valid
and which were produced from the pinned reference engine), from hashing with `hashlib`, and from hand calculation in the tests.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "specs" / "007-haulage-dispatch"
EXAMPLES = SPEC / "contracts" / "examples"
FIXTURES = ROOT / "tests" / "fixtures" / "haulage"
LABEL = "calibrated synthetic — not validated against real data"  # the em dash is U+2014 (FR-007-41)
BIAS_NOTE = (
    "Known DES bias: simulated truck cycle times tend to underestimate short hauls and overestimate long hauls; "
    "no real haul telemetry exists to correct it."
)
ENGINE_VERSION = "0.12.1"
PIN_MODULES = (
    "des/sim.py",
    "des/engine.py",
    "des/dispatch.py",
    "des/failures.py",
    "des/traversal.py",
    "des/resources.py",
    "network/kinematics.py",
    "network/routing.py",
    "network/graph.py",
    "equipment/catalog.py",
)  # FR-007-02
KINDS = (
    "arrive-loader",
    "load-end",
    "depart-loaded",
    "arrive-dump",
    "dump-end",
    "dispatch",
    "loader-repair-end",
    "segment-exit",
    "junction-cross-end",
    "zone-probe",
    "bin-dump",
    "lhd-start",
    "lhd-dig",
    "lhd-to-tip",
    "lhd-at-tip",
    "lhd-after-tip",
)  # fmt: skip  (canonical vocabulary of contracts/des-trace.schema.json, spec 007 section 8 (f))

for _p in (ROOT / "pipeline" / "src", ROOT / "src"):  # first-party packages that tests of this spec import
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def example_path(name: str) -> Path:
    return EXAMPLES / name


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(Path(p).read_bytes())


def engine_root() -> Path:
    """The installed `minehaulsim` package folder (reference engine, locked at 0.12.1 in pipeline/uv.lock)."""
    import minehaulsim

    return Path(minehaulsim.__file__).parent


def write_bundle(tmp: Path, bundle: dict, name: str = "bundle.json") -> Path:
    p = tmp / name
    p.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return p


def schema_validator(stem: str, defs: str | None = None):
    """A Draft 2020-12 validator for `contracts/<stem>.schema.json` (or one of its `$defs`), with every contract registered by `$id`."""
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    reg = Registry()
    for f in (ROOT / "contracts").glob("*.schema.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        reg = reg.with_resource(d["$id"], Resource.from_contents(d))
    root = json.loads((ROOT / "contracts" / f"{stem}.schema.json").read_text(encoding="utf-8"))
    schema = root if defs is None else {"$ref": f"{root['$id']}#/$defs/{defs}"}
    return Draft202012Validator(schema, registry=reg)


def truck_class_entry(name: str) -> dict:
    """The bundle entry of an engine catalog truck class (the parameters the twin carries must equal the engine pin, spec 007 section 8 (b))."""
    from minehaulsim.equipment.catalog import TRUCKS

    t = TRUCKS[name]
    return {
        "name": t.name,
        "kind": t.kind,
        "payload_mean_t": t.payload_mean_t,
        "payload_sd_t": t.payload_sd_t,
        "empty_t": t.empty_t,
        "width_class": t.width_class,
        "power_kw": t.power_kw,
        "max_speed_kmh": t.max_speed_kmh,
        "rimpull_kn": [{"speed_kmh": v, "force_kn": f} for v, f in t.rimpull_kn],
        "retarder_kn": [{"speed_kmh": v, "force_kn": f} for v, f in t.retarder_kn],
    }


def segment_entry(
    sid: int,
    a: int,
    b: int,
    pa: tuple[float, float, float],
    pb: tuple[float, float, float],
    *,
    width_class: int = 2,
    one_way: bool = False,
    speed_limit_kmh: float = 50.0,
    rolling_resistance_pct: float = 2.0,
) -> dict:
    """A segment dict with the 3-D length and the signed grade (%) computed from its end points, as in the spec's examples."""
    dx, dy, dz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
    horiz = (dx * dx + dy * dy) ** 0.5
    return {
        "id": sid,
        "a": a,
        "b": b,
        "polyline_m": [list(pa), list(pb)],
        "length_m": round((horiz * horiz + dz * dz) ** 0.5, 3),
        "grade_pct": round(100.0 * dz / horiz, 3),
        "width_class": width_class,
        "one_way": one_way,
        "speed_limit_kmh": speed_limit_kmh,
        "rolling_resistance_pct": rolling_resistance_pct,
        "zone_id": None,
        "single_lane_op": False,
    }


class DeterministicRng:
    """Stand-in for `minehaulsim.rng.RngManager` answering every request with the distribution mean (the `deterministic` profile of FR-007-07)."""

    class _Stream:
        def uniform(self, lo, hi):
            return (lo + hi) / 2

        def lognormal(self, mean=0.0, sigma=1.0):
            return 1.0  # the engine asks for a unit-mean lognormal(-sigma^2/2, sigma)

        def normal(self, loc=0.0, scale=1.0):
            return loc

        def integers(self, lo, hi):
            return lo

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        self._s = self._Stream()

    def stream(self, purpose: str):
        return self._s

    fresh = stream


def reference_engine_run(bundle: dict, rng_cls=DeterministicRng, *, until_s: float | None = None):
    """Run the pinned reference engine directly (no adapter): converts the bundle to the engine's objects here, with its own rng stand-in.

    Independent oracle for the adapter in fast or traffic mode with the `deterministic` profile and a classical dispatcher (`fixed`, `nearest`, `sptf`, `sq`).
    Returns the engine's `ShiftResult` (events are cyclelog/v1 rows with keys t, truck_id, shovel_id, event, payload_t).
    """
    import numpy as np
    from minehaulsim.des import sim
    from minehaulsim.des.dispatch import FixedPolicy, MinQueuePolicy, MinSaturationPolicy, NearestPolicy
    from minehaulsim.network.constraints import DirectionZone, Junction
    from minehaulsim.network.graph import NodeSite, RoadNetwork, Segment

    net = RoadNetwork()
    for n in bundle["network"]["nodes"]:
        net.add_node(NodeSite(n["id"], n["kind"], tuple(n["pos_m"])))
    for s in bundle["network"]["segments"]:
        net.add_segment(
            Segment(
                id=s["id"], a=s["a"], b=s["b"], polyline=np.asarray(s["polyline_m"], dtype=float), length_m=s["length_m"], grade_pct=s["grade_pct"],
                width_class=s["width_class"], one_way=s["one_way"], speed_limit_kmh=s["speed_limit_kmh"], zone_id=s["zone_id"],
                rolling_resistance_pct=s["rolling_resistance_pct"], single_lane_op=s["single_lane_op"],
            )
        )  # fmt: skip
    net.freeze()
    loaders = [sim.LoaderSpec(ld["node"], ld["loader_class"], ld["n_spots"]) for ld in bundle["loaders"]]
    trucks = [sim.TruckSpec(t["id"], t["truck_class"], t["start_loader"]) for t in bundle["fleet"]]
    policy = {"fixed": FixedPolicy, "nearest": NearestPolicy, "sptf": MinSaturationPolicy, "sq": MinQueuePolicy}[
        bundle["dispatcher"]["id"]
    ]()
    zones = {z["id"]: DirectionZone.from_dict(z) for z in bundle["network"]["zones"]}
    junctions = {j["node"]: Junction(j["node"], j["capacity"], j["cross_s"]) for j in bundle["network"]["junctions"]}
    original = sim.RngManager
    sim.RngManager = rng_cls
    try:
        return sim.run_shift(
            net, loaders, list(bundle["dumps"]), trucks, policy, 0, until_s=until_s or bundle["horizon_s"], zones=zones, junctions=junctions,
            fast_mode=bundle["mode"] == "fast",
        )  # fmt: skip
    finally:
        sim.RngManager = original


def engine_tables() -> dict:
    """Standard-form quantile tables (normal, unit-mean lognormal sigma 0.18 and 0.15, exponential) as bundle entries: tests/fixtures/haulage/variate_tables.json."""
    d = json.loads((FIXTURES / "variate_tables.json").read_text(encoding="utf-8"))
    return {k: v for k, v in d.items() if not k.startswith("_")}


def with_engine_profile(bundle: dict) -> dict:
    """The bundle switched to the `engine` variate profile, carrying the tables that profile needs for SHOVEL_45 (sigma 0.18) and the dump time (sigma 0.15)."""
    t = engine_tables()
    bundle["variate_profile"] = "engine"
    bundle["quantile_tables"] = [t["normal"], t["lognormal-0.18"], t["lognormal-0.15"]]
    return bundle


def make_trace(
    events,
    cyclelog,
    *,
    horizon_s: float,
    warmup_s: float = 0.0,
    dispatcher: str = "fixed",
    scenario_id: str = "kpi-hand",
    seed: int = 0,
) -> dict:
    """A schema-valid des-trace document (contracts/des-trace.schema.json) from hand-written rows.

    `events`: iterable of (t_s, kind, truck, node) already in execution order; `seq` is assigned 1, 2, 3, ... in that order.
    `cyclelog`: iterable of (t_s, truck, node, event, payload_t). The header is the spec example's, with the fields given here replaced;
    the results block is filled consistently (tonnes of `dump` rows, number of `return` rows, zero waits).
    """
    doc = copy.deepcopy(example("des-trace.valid.json"))
    h = doc["header"]
    h.update(
        {
            "scenario_id": scenario_id,
            "seed": seed,
            "dispatcher": dispatcher,
            "horizon_s": horizon_s,
            "kpi_window": {"warmup_s": warmup_s},
        }
    )
    doc["events"] = [
        {"t_s": t, "seq": i + 1, "kind": k, "truck": tr, "node": nd} for i, (t, k, tr, nd) in enumerate(events)
    ]
    doc["cyclelog"] = [
        {"t_s": t, "truck": tr, "node": nd, "event": ev, "payload_t": p} for t, tr, nd, ev, p in cyclelog
    ]
    loaders = sorted({r["node"] for r in doc["cyclelog"] if r["event"] == "load"})
    doc["results"] = {
        "tonnes_t": float(sum(r["payload_t"] for r in doc["cyclelog"] if r["event"] == "dump")),
        "cycles": sum(1 for r in doc["cyclelog"] if r["event"] == "return"),
        "truck_wait_s": 0.0,
        "loader_wait_s": [{"loader": n, "wait_s": 0.0} for n in loaders],
        "events_executed": len(doc["events"]),
        "downtime": None,
    }
    return doc


def smoke_bundle() -> dict:
    """A deep copy of the spec's minimal live bundle: 2 loaders, 2 dumps, 1 junction, deterministic profile, fast mode, 900 s."""
    return copy.deepcopy(example("haul-scenario.valid.json"))


def exponential_bundle() -> dict:
    """A deep copy of the spec's MVA oracle family member: 1 loader, 1 dump, exponential profile, fast mode, fixed dispatcher."""
    return copy.deepcopy(example("haul-scenario.valid-exponential.json"))


def traffic_lp_bundle() -> dict:
    return copy.deepcopy(example("haul-scenario.valid-traffic-lp.json"))

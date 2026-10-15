# ruff: noqa: E501, PT018
"""T-007-013: the adapter seam (random-stream substitution + engine event recorder with the canonical kinds); the recorder is cross-checked against the engine's
own cyclelog; determinism across processes; the seam does not change the model (Welch 99 % CI against the engine's own random streams).

Requirements: FR-007-01, FR-007-09, P-007-05, P-007-21.

Spec: specs/007-haulage-dispatch/spec.md FR-007-01 (the adapter runs one shift of the `minehaulsim` reference engine at the locked version, from a scenario bundle valid against
`contracts/haul-scenario.schema.json`, a seed (integer, 0 <= seed < 2^63), a dispatcher id and a variate profile; throughout the run it replaces the engine's random-stream manager with
the counter-based variate source; it returns the event trace, the cyclelog rows, the engine's executed-event count and the KPIs of FR-007-08), FR-007-09 (the trace lists every
executed engine event in execution order as (t, seq, kind, truck, node), the kind from the canonical vocabulary of `contracts/des-trace.schema.json`, mapped from the engine's callbacks
by the pinned name map; cancelled events are not executed and do not appear, but they consume a seq; the cyclelog rows (t, truck, node, event, payload) are sorted stably by (t, truck), as
the reference engine sorts them), P-007-05 (the same (bundle, seed, dispatcher, profile) gives byte-identical trace files in two separate processes), P-007-21 (under the `engine` profile,
traffic mode and `sptf`, the mean t/h over 30 seeds with the counter variate source and with the engine's own random-stream manager differ by an amount whose Welch 99 % CI contains 0),
section 8 (a) (the trace header repeats the values that ran; adapter arguments that differ from the bundle's are rejected) and the header fields of the trace schema.

Oracle: the pinned reference engine called directly with a test-side stand-in for its random-stream manager (`tests/support/p007_kit.py`: `reference_engine_run`, answering every request with
the distribution mean, which is exactly the `deterministic` profile), compared with equality of every float; hand calculation for the first events of the smoke bundle (stagger window 60 s:
midpoint 30 s; loading of a 227 t payload with a 45 t bucket is ceil(227 / 45) = 6 passes x 38 s + 30 s spot = 258 s, so the first load ends at 288 s; payload 227 t; the horizon of 900 s ends
the shift after 2 dumps, 8 executed events); the JSON Schema validator of the trace contract; `scipy.stats.ttest_ind(equal_var=False)` for the Welch interval.
(The spec's example trace `des-trace.valid.json` matches the first four events exactly, but its later travel times are not the engine's: it is a schema example, not an oracle for travel times.)

Expected API (module `pitstudio_pipeline.haulage.adapter`; errors in `pitstudio_pipeline.haulage.errors`):
    run_shift(bundle_path, *, seed, dispatcher=None, profile=None, trace_path=None, pin_path=None, variate_source="counter", event_budget=2_000_000) -> RunResult
        `bundle_path` is a Path to the bundle file (its SHA-256 is `header.bundle_sha256`); the bundle is loaded with `load_bundle` and `check_connectivity` (test_t_007_014); `dispatcher` and `profile`, when given,
        must equal the bundle's (else InvalidScenario at `/dispatcher/id` or `/variate_profile`); `trace_path`, when given, receives the trace as UTF-8 JSON, LF only, written
        deterministically (the same document gives the same bytes); `variate_source="engine"` leaves the engine's own random-stream manager in place (only for the equivalence check of P-007-21);
        `event_budget` caps executed events (EventBudgetExceeded, test_t_007_022).
        RunResult(trace: dict, events: list[dict], cyclelog: list[dict], events_executed: int, kpis: dict) with `trace` valid against the trace schema (header, events, cyclelog, results), `events`
        = `trace["events"]`, `cyclelog` = `trace["cyclelog"]` (rows {t_s, truck, node, event, payload_t}), `kpis` as `compute_kpis` returns (test_t_007_016).
        While it runs, `minehaulsim.des.sim.RngManager` is replaced by a counter-based manager and `minehaulsim.des.sim.Engine` by a recording subclass; both are restored on exit, also on error.
        Header: scenario_id, bundle_sha256, seed, dispatcher, variate_profile, mode, horizon_s, kpi_window, engine {package "minehaulsim", version "0.12.1", pin_sha256 = pin_sha256()}, variates
        {generator "philox4x64-10", key_hash "fnv-1a-64"}, producer "python-reference", synthetic true, honesty {label, bias_note}.
    RecordingEngine(kinds: Mapping[str, str], event_budget=None)   a subclass of `minehaulsim.des.engine.Engine`; `.records` lists {t_s, seq, kind, truck, node} for every executed callback whose
        `__name__` is a key of `kinds` (the value is the kind); for the callbacks `_go_load`, `_loaded`, `_depart_loaded`, `_arrive_dump`, `_dumped` and `_dispatch_next` the first two positional arguments are the
        truck and the node, for every other callback truck and node are None; a cancelled event is skipped but its seq is used.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit as kit
from minehaulsim.des import sim
from pitstudio_pipeline.haulage.adapter import RecordingEngine, run_shift
from pitstudio_pipeline.haulage.errors import EventBudgetExceeded, InvalidScenario
from pitstudio_pipeline.haulage.pin import pin_sha256

TRACE_SCHEMA = kit.schema_validator("des-trace")
SMOKE = kit.example_path("haul-scenario.valid.json")


def busy_bundle(dispatcher="sptf", mode="fast", n_trucks=6, horizon=3 * 3600.0, profile="deterministic") -> dict:
    b = kit.smoke_bundle()
    b["dispatcher"] = {"id": dispatcher}
    b["mode"] = mode
    b["horizon_s"] = horizon
    b["fleet"] = [
        {"id": i + 1, "truck_class": "CAT_793F", "start_loader": 1 if i % 2 == 0 else 2} for i in range(n_trucks)
    ]
    for ld in b["loaders"]:
        ld["destination_dump"] = (
            4  # the engine's own policies always use the first dump: with this declaration the direct engine run is an oracle
        )
    if profile == "engine":
        kit.with_engine_profile(b)
    return b


def cyclelog_tuples(res):
    return [(r["t_s"], r["truck"], r["node"], r["event"], r["payload_t"]) for r in res.cyclelog]


def engine_tuples(ref):
    return [(e["t"], e["truck_id"], e["shovel_id"], e["event"], e["payload_t"]) for e in ref.events]


# ---------------------------------------------------------------------------------------------------------------------
# the smoke bundle: hand-derived first events and the spec example
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-01")
def test_the_smoke_shift_matches_the_hand_derived_first_events_and_totals():
    res = run_shift(SMOKE, seed=42)
    first = [(e["t_s"], e["seq"], e["kind"], e["truck"], e["node"]) for e in res.events[:4]]
    assert first == [
        (30.0, 1, "arrive-loader", 1, 1),
        (30.0, 2, "arrive-loader", 2, 2),
        (288.0, 3, "load-end", 1, 1),
        (288.0, 4, "load-end", 2, 2),
    ]
    haul = [r for r in res.cyclelog if r["event"] == "haul"]
    assert [(r["t_s"], r["payload_t"]) for r in haul] == [(288.0, 227.0), (288.0, 227.0)]
    r = res.trace["results"]
    assert (r["tonnes_t"], r["cycles"], r["truck_wait_s"], r["events_executed"], r["downtime"]) == (
        454.0,
        2,
        0.0,
        8,
        None,
    )
    assert [x["wait_s"] for x in r["loader_wait_s"]] == [0.0, 0.0]


@pytest.mark.req("FR-007-09")
def test_the_event_kinds_trucks_and_nodes_of_the_smoke_shift_match_the_spec_example():
    res = run_shift(SMOKE, seed=42)
    ex = kit.example("des-trace.valid.json")["events"]
    assert [(e["seq"], e["kind"], e["truck"], e["node"]) for e in res.events] == [
        (e["seq"], e["kind"], e["truck"], e["node"]) for e in ex
    ]
    assert [r["event"] for r in res.cyclelog] == [r["event"] for r in kit.example("des-trace.valid.json")["cyclelog"]]


@pytest.mark.req("FR-007-01")
def test_the_kpis_of_the_smoke_shift_are_returned():
    k = run_shift(SMOKE, seed=42).kpis
    assert (
        k["fleet"]["cycles"] == 2
        and k["fleet"]["tonnes_t"] == pytest.approx(454.0)
        and k["fleet"]["production_tph"] == pytest.approx(454.0 / 0.25)
    )  # window [0 s, 900 s] = 0.25 h


# ---------------------------------------------------------------------------------------------------------------------
# against the reference engine (deterministic profile)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-01")
@pytest.mark.parametrize("mode", ["fast", "traffic"])
@pytest.mark.parametrize("dispatcher", ["fixed", "nearest", "sptf", "sq"])
def test_a_busy_deterministic_shift_equals_the_reference_engine_run_directly(tmp_path, dispatcher, mode):
    b = busy_bundle(dispatcher, mode)
    path = kit.write_bundle(tmp_path, b)
    res = run_shift(path, seed=7)
    ref = kit.reference_engine_run(b)
    assert cyclelog_tuples(res) == engine_tuples(ref)  # every row, every float, exactly
    assert res.events_executed == ref.events_executed == res.trace["results"]["events_executed"]
    r = res.trace["results"]
    assert r["tonnes_t"] == ref.tonnes and r["cycles"] == ref.cycles and r["truck_wait_s"] == ref.truck_wait_s
    assert {x["loader"]: x["wait_s"] for x in r["loader_wait_s"]} == ref.loader_wait_s
    assert (
        ref.cycles > 20
    )  # the scenario is busy enough to queue: queues at loaders or the dump are part of what is compared


@pytest.mark.req("FR-007-09")
@pytest.mark.parametrize("mode", ["fast", "traffic"])
def test_every_executed_event_is_listed_in_order_with_a_canonical_kind(tmp_path, mode):
    res = run_shift(kit.write_bundle(tmp_path, busy_bundle("sptf", mode)), seed=3)
    ev = res.events
    assert all(e["kind"] in kit.KINDS for e in ev)
    keys = [(e["t_s"], e["seq"]) for e in ev]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)  # strictly increasing
    assert len({e["seq"] for e in ev}) == len(ev) and min(e["seq"] for e in ev) >= 1
    kinds = {e["kind"] for e in ev}
    if mode == "fast":
        assert (
            len(ev) == res.events_executed
        )  # in fast mode every executed callback is a lifecycle callback of the pinned map
        assert {
            "arrive-loader",
            "load-end",
            "arrive-dump",
            "dump-end",
        } <= kinds  # the arrivals the queue statistics need
    else:
        assert (
            kinds & {"segment-exit", "junction-cross-end"}
        )  # per-segment traffic events are recorded too (arrivals at the end of a traversal are not heap events: see the report)


@pytest.mark.req("FR-007-09")
def test_the_cyclelog_is_sorted_by_time_then_truck_and_agrees_with_the_event_list(tmp_path):
    res = run_shift(kit.write_bundle(tmp_path, busy_bundle("sq", "fast")), seed=11)
    rows = res.cyclelog
    assert [(r["t_s"], r["truck"]) for r in rows] == sorted((r["t_s"], r["truck"]) for r in rows)
    index = {(e["kind"], e["t_s"], e["truck"], e["node"]) for e in res.events}
    for r in rows:  # the engine's own rows against the recorded callbacks: `haul` is written when `load-end` fires, `return` when `dump-end` fires
        if r["event"] == "haul":
            assert ("load-end", r["t_s"], r["truck"], r["node"]) in index
        if r["event"] == "return":
            assert ("dump-end", r["t_s"], r["truck"], r["node"]) in index
    n_haul = sum(1 for r in rows if r["event"] == "haul")
    assert n_haul == sum(1 for e in res.events if e["kind"] == "load-end")
    assert (
        sum(1 for r in rows if r["event"] == "return")
        == sum(1 for e in res.events if e["kind"] == "dump-end")
        == res.trace["results"]["cycles"]
    )


@pytest.mark.req("FR-007-09")
def test_a_cancelled_event_is_not_listed_but_consumes_its_seq():
    kinds = {"_go_load": "arrive-loader", "_loaded": "load-end", "_arrive_dump": "arrive-dump", "leave": "segment-exit"}
    eng = RecordingEngine(kinds)
    ran = []

    def _go_load(tid, node):
        ran.append(("go", tid, node))

    def _loaded(tid, node):
        ran.append(("loaded", tid, node))

    def _arrive_dump(tid, node, payload):
        ran.append(("dump", tid, node))

    def leave():
        ran.append(("leave",))

    def unrelated():
        ran.append(("unrelated",))

    eng.schedule(10.0, _go_load, 5, 1)  # seq 1
    h2 = eng.schedule(20.0, _loaded, 5, 1)  # seq 2, cancelled below
    eng.schedule(20.0, _arrive_dump, 6, 4, 227.0)  # seq 3
    eng.schedule(30.0, leave)  # seq 4: a closure without truck or node
    eng.cancel(h2)
    eng.run(100.0)
    assert ran == [("go", 5, 1), ("dump", 6, 4), ("leave",)]
    assert eng.records == [
        {"t_s": 10.0, "seq": 1, "kind": "arrive-loader", "truck": 5, "node": 1},
        {"t_s": 20.0, "seq": 3, "kind": "arrive-dump", "truck": 6, "node": 4},
        {"t_s": 30.0, "seq": 4, "kind": "segment-exit", "truck": None, "node": None},
    ]
    assert eng.events_executed == 3  # the cancelled event never executed


# ---------------------------------------------------------------------------------------------------------------------
# header, schema, arguments
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-01")
def test_the_trace_is_schema_valid_and_the_header_repeats_what_ran(tmp_path):
    b = busy_bundle("nearest", "fast", n_trucks=4, horizon=1800.0)
    path = kit.write_bundle(tmp_path, b)
    res = run_shift(path, seed=99)
    assert not list(TRACE_SCHEMA.iter_errors(res.trace)), [e.message for e in TRACE_SCHEMA.iter_errors(res.trace)][:3]
    h = res.trace["header"]
    assert (
        h["scenario_id"],
        h["seed"],
        h["dispatcher"],
        h["variate_profile"],
        h["mode"],
        h["horizon_s"],
        h["kpi_window"],
    ) == (b["id"], 99, "nearest", "deterministic", "fast", 1800.0, {"warmup_s": 0.0})
    assert h["bundle_sha256"] == kit.sha256_file(path)
    assert h["engine"] == {"package": "minehaulsim", "version": "0.12.1", "pin_sha256": pin_sha256()}
    assert (
        h["variates"] == {"generator": "philox4x64-10", "key_hash": "fnv-1a-64"}
        and h["producer"] == "python-reference"
        and h["synthetic"] is True
    )
    assert h["honesty"] == {"label": kit.LABEL, "bias_note": kit.BIAS_NOTE}
    assert res.events is res.trace["events"] or res.events == res.trace["events"]
    assert res.cyclelog == res.trace["cyclelog"]


@pytest.mark.req("FR-007-01")
def test_adapter_arguments_that_differ_from_the_bundle_are_rejected(tmp_path):
    with pytest.raises(InvalidScenario) as e1:
        run_shift(SMOKE, seed=1, dispatcher="nearest")  # the bundle declares sptf
    assert "/dispatcher/id" in [v[0] for v in e1.value.violations]
    with pytest.raises(InvalidScenario) as e2:
        run_shift(SMOKE, seed=1, profile="exponential")  # the bundle declares deterministic
    assert "/variate_profile" in [v[0] for v in e2.value.violations]
    assert (
        run_shift(SMOKE, seed=1, dispatcher="sptf", profile="deterministic").events_executed == 8
    )  # equal values are fine


@pytest.mark.req("FR-007-01")
def test_a_trace_file_is_valid_json_equal_to_the_returned_trace_and_written_deterministically(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    r1 = run_shift(SMOKE, seed=5, trace_path=a)
    run_shift(SMOKE, seed=5, trace_path=b)
    raw = a.read_bytes()
    assert raw == b.read_bytes() and b"\r" not in raw
    assert json.loads(raw.decode("utf-8")) == r1.trace


# ---------------------------------------------------------------------------------------------------------------------
# the seam is restored
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-01")
def test_the_engines_rng_manager_and_engine_class_are_restored_after_a_run_and_after_an_error(tmp_path):
    rng0, eng0 = sim.RngManager, sim.Engine
    run_shift(SMOKE, seed=1)
    assert sim.RngManager is rng0 and sim.Engine is eng0
    with pytest.raises(EventBudgetExceeded):
        run_shift(kit.write_bundle(tmp_path, busy_bundle()), seed=1, event_budget=5)
    assert sim.RngManager is rng0 and sim.Engine is eng0


@pytest.mark.req("FR-007-01")
def test_seeds_change_the_engine_profile_shift_and_equal_seeds_do_not(tmp_path):
    path = kit.write_bundle(tmp_path, busy_bundle("sptf", "fast", profile="engine"))
    a, a2, b = run_shift(path, seed=1), run_shift(path, seed=1), run_shift(path, seed=2)
    assert a.trace == a2.trace
    assert a.trace["events"] != b.trace["events"]
    stagger = [e["t_s"] for e in a.events if e["kind"] == "arrive-loader"][:6]
    assert all(0.0 <= t <= 60.0 for t in stagger) and len(set(stagger)) > 1  # uniform(0, 60) draws, not the midpoint
    payloads = {r["payload_t"] for r in a.cyclelog if r["event"] == "haul"}
    assert len(payloads) > 5  # normal payloads, not the mean


# ---------------------------------------------------------------------------------------------------------------------
# P-007-05: byte-identical across processes
# ---------------------------------------------------------------------------------------------------------------------
CODE = (
    "import sys\n"
    "from pathlib import Path\n"
    "from pitstudio_pipeline.haulage.adapter import run_shift\n"
    "run_shift(Path(sys.argv[1]), seed=int(sys.argv[2]), trace_path=Path(sys.argv[3]))\n"
)


def run_in_new_process(bundle: Path, seed: int, out: Path) -> None:
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            [str(kit.ROOT / "pipeline" / "src"), str(kit.ROOT / "src"), os.environ.get("PYTHONPATH", "")]
        ),
        "PYTHONHASHSEED": str(seed),
    }
    subprocess.run([sys.executable, "-c", CODE, str(bundle), str(seed), str(out)], check=True, env=env, timeout=300)


@pytest.mark.req("P-007-05")
@pytest.mark.parametrize(("profile", "mode"), [("deterministic", "fast"), ("engine", "traffic")])
def test_the_same_run_gives_byte_identical_trace_files_in_two_separate_processes(tmp_path, profile, mode):
    path = kit.write_bundle(tmp_path, busy_bundle("sptf", mode, n_trucks=6, horizon=3600.0, profile=profile))
    p1, p2, p3 = tmp_path / "p1.json", tmp_path / "p2.json", tmp_path / "p3.json"
    run_in_new_process(path, 13, p1)
    run_in_new_process(
        path, 13, p2
    )  # another process, another PYTHONHASHSEED is irrelevant: same seed here, so same bytes
    run_shift(path, seed=13, trace_path=p3)  # and the test process itself
    assert p1.read_bytes() == p2.read_bytes() == p3.read_bytes()
    assert p1.stat().st_size > 1000


# ---------------------------------------------------------------------------------------------------------------------
# P-007-21: the seam does not change the model
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.slow
@pytest.mark.req("P-007-21")
def test_the_counter_variate_source_and_the_engines_own_streams_give_the_same_mean_throughput(tmp_path):
    b = busy_bundle("sptf", "traffic", n_trucks=8, horizon=8 * 3600.0, profile="engine")
    b["kpi_window"] = {"warmup_s": 3600.0}
    path = kit.write_bundle(tmp_path, b)
    ours = [run_shift(path, seed=s, variate_source="counter").kpis["fleet"]["production_tph"] for s in range(30)]
    theirs = [run_shift(path, seed=s, variate_source="engine").kpis["fleet"]["production_tph"] for s in range(30)]
    ci = stats.ttest_ind(ours, theirs, equal_var=False).confidence_interval(confidence_level=0.99)
    assert ci.low <= 0.0 <= ci.high, (sum(ours) / 30, sum(theirs) / 30, ci)
    assert min(ours) > 0 and min(theirs) > 0

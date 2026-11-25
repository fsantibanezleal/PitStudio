# ruff: noqa: E501, PT018
"""T-007-042: the lower stage of the LP dispatch (hand-calculated need values), re-solve triggers, the SPTF fallback, all-masked parking, and the LP throughput bound for every dispatcher.

Requirements: FR-007-22, FR-007-33, FR-007-21 (the fallback record), P-007-10.

Spec: specs/007-haulage-dispatch/spec.md FR-007-22 (when a truck becomes free the LP dispatcher assigns it to the feasible path with the largest need, need_p = f_p (t - t0) - loads_sent_p; ties go to the lowest
expected arrival time, then the lowest path id; it re-solves the LP only when a loader or a truck changes availability, never at every event), FR-007-21 (an infeasible, unbounded or invalid LP makes the LP dispatcher fall back to
`sptf` and record the status and the fallback in the trace header), FR-007-33 (if every target of a decision is masked, the learned and LP dispatchers raise `NoServiceableLoader` and the engine parks the truck as it does for
the classical dispatchers), P-007-10 (for any dispatcher, under the `deterministic` profile the loads completed in [0, H] are <= LP* x H + N_T, where LP* is the optimum of FR-007-19 in loads/h; under the `engine` profile the
30-seed mean satisfies the same bound plus 3 SE) and section 8 item 8 (LP paths are loader -> declared destination).

Oracle: (1) the need values of a 5-decision script worked out by hand below (flows 12 and 7.5 loads/h from the worked example of spec section 7, t0 = 0, need = f t / 3600 - sent); (2) the sptf run of the same bundle for the
fallback; (3) the LP bound computed here from hand-derived data: loader rate 3600 / 258 s per spot (6 passes x 38 s + 30 s), dump rate 3600 / 55 s, round trip T_p = 258 + 55 + the free-flow legs of the reference router; the LP is
solved by `solve_dispatch_lp` (test_t_007_040, validated against scipy/HiGHS there); (4) a counter wrapped around the solver for the re-solve rule.

Hand script (two paths, path 1 = loader 1 with f = 12 / h, path 2 = loader 2 with f = 7.5 / h; the first two ETAs are 100 s for loader 1 and 80 s for loader 2):
    t = 0:   need 0, 0, a tie, the lower ETA wins: path 2 (sent 2 = 1)
    t = 120: need 12 x 120 / 3600 = 0.4 and 7.5 x 120 / 3600 - 1 = -0.75: path 1 (sent 1 = 1)
    t = 240: need 0.8 - 1 = -0.2 and 0.5 - 1 = -0.5: path 1 (sent 1 = 2)
    t = 300: need 1.0 - 2 = -1.0 and 0.625 - 1 = -0.375: path 2 (sent 2 = 2)
    t = 600: need 2.0 - 2 = 0.0 and 1.25 - 2 = -0.75: path 1 (sent 1 = 3)

Expected API (module `pitstudio_pipeline.haulage.lp`, errors in `pitstudio_pipeline.haulage.errors`, adapter as in test_t_007_013):
    errors.NoServiceableLoader(HaulError, RuntimeError)
    LpDispatcher(paths, flows, *, t0=0.0)      paths: [{"id", "loader", "dump"}]; flows: {path id: loads/h}; `name` == "lp"; `loads_sent: dict[int, int]` (0 for every path at the start)
        next_loader(truck, mine) -> int      t = mine.now (seconds); feasible = the path's loader is `diggable` and its ETA `mine.eta_s[(truck.truck_id, loader)]` is finite; picks the largest need (f (t - t0) / 3600 - loads_sent),
            ties by the lowest ETA then the lowest path id, increments `loads_sent` of the chosen path and returns its loader; raises NoServiceableLoader when no path is feasible
        next_dump(truck, mine, *, from_loader=None) -> int    the dump of the path of `from_loader` (the first path of that loader), else `mine.dumps[0]`
    adapter.run_shift with `dispatcher.id == "lp"`: solves the LP once at the start from the bundle (loader rates, dump rates, round trips, the bundle's blend floors, margin 1 per load) by calling
        `pitstudio_pipeline.haulage.lp.solve_dispatch_lp` (looked up on the module at call time) and again only when a loader or a truck changes availability (failures); header `lp` = {"status", "fallback"}
        with fallback "none" for an optimal solve and "sptf" otherwise, after which the run is an `sptf` run.
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from minehaulsim.des.dispatch import LoaderView, MineView, TruckView
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_busy as busy
import p007_kit as kit
from pitstudio_pipeline.haulage import lp as lp_module
from pitstudio_pipeline.haulage.adapter import run_shift
from pitstudio_pipeline.haulage.errors import NoServiceableLoader
from pitstudio_pipeline.haulage.lp import LpDispatcher, solve_dispatch_lp

PATHS = [{"id": 1, "loader": 1, "dump": 4}, {"id": 2, "loader": 2, "dump": 5}]
FLOWS = {1: 12.0, 2: 7.5}


def view(now, etas, *, diggable=(True, True), dumps=(4, 5)):
    loaders = tuple(
        LoaderView(node_id=n, queue_len=0, inbound=0, in_service=False, est_free_s=0.0, load_mean_s=258.0, diggable=d)
        for n, d in zip((1, 2), diggable, strict=True)
    )
    return MineView(now=now, loaders=loaders, dumps=tuple(dumps), eta_s={(1, 1): etas[0], (1, 2): etas[1]})


TRUCK = TruckView(truck_id=1, unit_name="CAT_793F", home_loader=1)


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-22: the lower stage
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-22")
def test_the_five_decision_script_by_hand():
    d = LpDispatcher(PATHS, FLOWS)
    assert d.name == "lp" and d.loads_sent == {1: 0, 2: 0}
    steps = [
        (0.0, 2, {1: 0, 2: 1}),
        (120.0, 1, {1: 1, 2: 1}),
        (240.0, 1, {1: 2, 2: 1}),
        (300.0, 2, {1: 2, 2: 2}),
        (600.0, 1, {1: 3, 2: 2}),
    ]
    for t, loader, sent in steps:
        assert d.next_loader(TRUCK, view(t, (100.0, 80.0))) == loader, t
        assert d.loads_sent == sent, t


@pytest.mark.req("FR-007-22")
def test_a_non_zero_t0_shifts_the_clock():
    d = LpDispatcher(PATHS, FLOWS, t0=1000.0)
    # at t = 1120 s: need1 = 12 x 120 / 3600 = 0.4, need2 = 0.25: path 1
    assert d.next_loader(TRUCK, view(1120.0, (100.0, 80.0))) == 1


@pytest.mark.req("FR-007-22")
def test_ties_go_to_the_lowest_eta_then_the_lowest_path_id():
    assert (
        LpDispatcher(PATHS, {1: 10.0, 2: 10.0}).next_loader(TRUCK, view(0.0, (200.0, 50.0))) == 2
    )  # equal needs: loader 2 is nearer
    assert (
        LpDispatcher(PATHS, {1: 10.0, 2: 10.0}).next_loader(TRUCK, view(0.0, (90.0, 90.0))) == 1
    )  # equal ETAs too: path 1
    reversed_paths = [{"id": 5, "loader": 2, "dump": 5}, {"id": 3, "loader": 1, "dump": 4}]
    assert (
        LpDispatcher(reversed_paths, {5: 4.0, 3: 4.0}).next_loader(TRUCK, view(0.0, (90.0, 90.0))) == 1
    )  # path id 3 < 5, whatever the list order


@pytest.mark.req("FR-007-22")
def test_infeasible_paths_are_skipped_whatever_their_need():
    d = LpDispatcher(PATHS, {1: 100.0, 2: 1.0})
    t = 3600.0  # path 1 needs 100, path 2 needs 1
    assert d.next_loader(TRUCK, view(t, (100.0, 80.0), diggable=(False, True))) == 2  # loader 1 cannot serve
    d2 = LpDispatcher(PATHS, {1: 100.0, 2: 1.0})
    assert d2.next_loader(TRUCK, view(t, (math.inf, 80.0))) == 2  # loader 1 is unreachable
    assert d2.loads_sent == {1: 0, 2: 1}


@pytest.mark.req("FR-007-33")
@pytest.mark.parametrize(
    ("diggable", "etas"),
    [((False, False), (10.0, 10.0)), ((True, True), (math.inf, math.inf)), ((False, True), (10.0, math.inf))],
)
def test_when_every_target_is_masked_the_dispatcher_raises_no_serviceable_loader(diggable, etas):
    d = LpDispatcher(PATHS, FLOWS)
    with pytest.raises(NoServiceableLoader) as ei:
        d.next_loader(TRUCK, view(500.0, etas, diggable=diggable))
    assert isinstance(
        ei.value, RuntimeError
    )  # the engine parks a truck whose dispatcher raises a RuntimeError, as for the classical dispatchers
    assert d.loads_sent == {1: 0, 2: 0}  # nothing was assigned


@pytest.mark.req("FR-007-22")
def test_the_dump_is_the_declared_destination_of_the_loaders_path():
    d = LpDispatcher(PATHS, FLOWS)
    m = view(0.0, (1.0, 1.0), dumps=(5, 4))
    assert d.next_dump(TRUCK, m, from_loader=1) == 4 and d.next_dump(TRUCK, m, from_loader=2) == 5
    assert d.next_dump(TRUCK, m) == 5  # no loader context: the first dump of the view


@pytest.mark.req("FR-007-22")
@pytest.mark.parametrize("bad", [{}, {1: 12.0}, {1: -1.0, 2: 1.0}, {1: float("nan"), 2: 1.0}])
def test_flows_must_cover_every_path_with_finite_non_negative_values(bad):
    with pytest.raises(ValueError):  # noqa: PT011
        LpDispatcher(PATHS, bad)


# ---------------------------------------------------------------------------------------------------------------------
# the run: re-solve triggers, the fallback record
# ---------------------------------------------------------------------------------------------------------------------
def lp_bundle(*, horizon=4 * 3600.0, n_trucks=6, blend_min=None, failures=False, mode="fast", profile="deterministic"):
    b = busy.busy_bundle("lp", mode, n_trucks=n_trucks, horizon=horizon, profile=profile)
    for ld, dump in zip(b["loaders"], (4, 5), strict=True):
        ld["destination_dump"] = dump  # two declared destinations: paths 1 -> 4 and 2 -> 5
    floors = (
        []
        if blend_min is None
        else [{"terms": [{"loader": 1, "coef": 0.15}, {"loader": 2, "coef": -0.25}], "min": blend_min}]
    )
    b["dispatcher"] = {"id": "lp", "lp": {"blend_floors": floors}}
    if failures:
        b["failures"] = {
            "truck_mtbf_h": 1.0,
            "truck_repair_mean_s": 600.0,
            "truck_repair_cv": 0.3,
            "loader_mtbf_h": 1.0,
            "loader_repair_mean_s": 600.0,
            "loader_repair_cv": 0.3,
            "closures": [],
        }
    return b


class Counter:
    def __init__(self, monkeypatch):
        self.n = 0
        real = lp_module.solve_dispatch_lp

        def wrapped(*a, **k):
            self.n += 1
            return real(*a, **k)

        monkeypatch.setattr(lp_module, "solve_dispatch_lp", wrapped)


@pytest.mark.req("FR-007-22")
def test_without_failures_the_lp_is_solved_once_and_never_again(tmp_path, monkeypatch):
    c = Counter(monkeypatch)
    res = run_shift(kit.write_bundle(tmp_path, lp_bundle()), seed=1)
    assert len(res.events) > 300 and res.trace["results"]["cycles"] > 10
    assert c.n == 1  # one solve at the start, not one per event


@pytest.mark.req("FR-007-22")
def test_with_failures_it_is_re_solved_only_when_availability_changes(tmp_path, monkeypatch):
    c = Counter(monkeypatch)
    b = lp_bundle(
        horizon=8 * 3600.0, failures=True
    )  # deterministic profile: failures at the mean times, no table needed for the repair spreads
    res = run_shift(kit.write_bundle(tmp_path, b), seed=3)
    assert len(res.events) > 500
    assert 2 <= c.n < len(res.events) / 10  # re-solved on repairs and breakdowns, still far fewer solves than events


@pytest.mark.req("FR-007-21")
def test_an_optimal_lp_is_recorded_without_fallback(tmp_path):
    res = run_shift(kit.write_bundle(tmp_path, lp_bundle(blend_min=0.0)), seed=1)
    assert res.trace["header"]["dispatcher"] == "lp" and res.trace["header"]["lp"] == {
        "status": "optimal",
        "fallback": "none",
    }


@pytest.mark.req("FR-007-21")
def test_an_infeasible_lp_falls_back_to_sptf_and_records_both(tmp_path):
    lp = lp_bundle(blend_min=1000.0)  # 0.15 x1 - 0.25 x2 >= 1000 loads/h cannot hold
    res = run_shift(kit.write_bundle(tmp_path, lp, "lp.json"), seed=1)
    assert res.trace["header"]["dispatcher"] == "lp" and res.trace["header"]["lp"] == {
        "status": "infeasible",
        "fallback": "sptf",
    }
    sptf = lp_bundle()
    sptf["dispatcher"] = {"id": "sptf"}
    ref = run_shift(kit.write_bundle(tmp_path, sptf, "sptf.json"), seed=1)
    assert (
        res.cyclelog == ref.cyclelog and res.trace["results"] == ref.trace["results"]
    )  # after the fallback the run is the sptf run


# ---------------------------------------------------------------------------------------------------------------------
# P-007-10: the LP bound
# ---------------------------------------------------------------------------------------------------------------------
def lp_star(b: dict) -> float:
    """LP* in loads/h from hand-derived rates and the reference router's free-flow legs."""
    from minehaulsim.equipment.catalog import TRUCKS
    from minehaulsim.network.graph import NodeSite, RoadNetwork, Segment
    from minehaulsim.network.routing import Router

    net = RoadNetwork()
    for n in b["network"]["nodes"]:
        net.add_node(NodeSite(n["id"], n["kind"], tuple(n["pos_m"])))
    for s in b["network"]["segments"]:
        net.add_segment(
            Segment(id=s["id"], a=s["a"], b=s["b"], polyline=np.asarray(s["polyline_m"], dtype=float), length_m=s["length_m"], grade_pct=s["grade_pct"], width_class=s["width_class"], one_way=s["one_way"], speed_limit_kmh=s["speed_limit_kmh"], zone_id=s["zone_id"], rolling_resistance_pct=s["rolling_resistance_pct"], single_lane_op=s["single_lane_op"])
        )  # fmt: skip
    router = Router(net.freeze())
    unit = TRUCKS["CAT_793F"]
    paths, loader_caps, dump_caps = [], {}, {}
    load_s, dump_s = 6 * 38.0 + 30.0, b["engine_constants"]["dump_mean_s"]  # hand: ceil(227 / 45) = 6 passes
    for k, ld in enumerate(b["loaders"], start=1):
        dump = ld["destination_dump"]
        haul = router.route(ld["node"], dump, unit, loaded=True).time_s
        back = router.route(dump, ld["node"], unit, loaded=False).time_s
        paths.append(
            {
                "id": k,
                "loader": ld["node"],
                "dump": dump,
                "margin": 1.0,
                "trip_time_h": (load_s + haul + dump_s + back) / 3600.0,
            }
        )
        loader_caps[ld["node"]] = ld["n_spots"] * 3600.0 / load_s
        dump_caps[dump] = 3600.0 / dump_s
    r = solve_dispatch_lp(paths, loader_caps, dump_caps, float(len(b["fleet"])))
    assert r.status == "optimal"
    return r.optimum


@pytest.mark.req("P-007-10")
@pytest.mark.parametrize("dispatcher", ["fixed", "nearest", "sptf", "sq", "min-idle", "lp"])
@pytest.mark.parametrize("n_trucks", [2, 6, 12])
def test_the_loads_completed_never_exceed_the_lp_bound_in_the_deterministic_profile(tmp_path, dispatcher, n_trucks):
    b = lp_bundle(n_trucks=n_trucks)
    b["dispatcher"] = b["dispatcher"] if dispatcher == "lp" else {"id": dispatcher}
    res = run_shift(kit.write_bundle(tmp_path, b), seed=1)
    hours = b["horizon_s"] / 3600.0
    assert res.trace["results"]["cycles"] <= lp_star(b) * hours + n_trucks, (dispatcher, n_trucks)


@pytest.mark.slow
@pytest.mark.req("P-007-10")
@pytest.mark.parametrize("dispatcher", ["sptf", "nearest", "lp"])
def test_the_thirty_seed_mean_respects_the_bound_plus_three_standard_errors(dispatcher):
    b = lp_bundle(n_trucks=8, horizon=4 * 3600.0, profile="engine")
    b["dispatcher"] = b["dispatcher"] if dispatcher == "lp" else {"id": dispatcher}
    with tempfile.TemporaryDirectory() as d:
        path = kit.write_bundle(Path(d), b)
        loads = [run_shift(path, seed=s).trace["results"]["cycles"] for s in range(30)]
    se = (
        stats.tstd(loads) / math.sqrt(len(loads))
        if hasattr(stats, "tstd")
        else float(np.std(loads, ddof=1) / math.sqrt(len(loads)))
    )
    assert float(np.mean(loads)) <= lp_star(b) * 4.0 + 8 + 3 * se

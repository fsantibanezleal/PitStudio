# ruff: noqa: E501, PT018
"""T-007-016: KPI layer on a hand-written 3-truck trace (t/h, queue mean/P90, utilisation, match factor, hours per kt, cost only with rates), its unit and
homogeneity relations, and malformed traces rejected with `InvalidTrace`.

Requirements: FR-007-08, FR-007-42, P-007-20.

Spec: specs/007-haulage-dispatch/spec.md FR-007-08 (from a trace, per loader and for the fleet, over the evaluation window [warm-up, horizon] declared in the bundle:
production (t/h); cycles per hour; queue time at loaders and dumps (mean and P90, min per cycle); loader utilisation (busy fraction); match factor; truck-hours and
loader-hours per kilotonne; the match factor comes from `minephys.haulage` with t_L the mean loading time and T_c* the free-flow cycle time, the heterogeneous form when the
fleet mixes classes; cost per tonne only when truck and loader hourly rates are supplied, otherwise `not-computed (rates not supplied)`), FR-007-42 (a trace that fails its schema,
is not strictly ordered by (t, seq), contains a non-finite time or payload, or whose window has warm-up >= horizon is rejected with `InvalidTrace` naming the first offending
row, and no KPI is returned), P-007-20 ((i) KPIs with trace times in seconds or hours give the same t/h, match factor and utilisation; (ii) the match factor is unchanged when
N_T and N_L are multiplied by the same integer k; (iii) fleet tonnes equal the sum of per-loader tonnes; rtol 1e-12), section 7 and plan.md ("each dump is linked to the truck's last
load, queue times from arrival/service pairs"), section 8 item 6 (the trace records the arrival events that queue times need) and `contracts/haul-scenario.schema.json` `cost_rates`.

Oracle: hand calculation on the trace written out below (3 trucks, 2 loaders, 1 dump, window [600 s, 4200 s] = exactly 1 h); NumPy `percentile(..., method="linear")` (Hyndman-Fan
type 7) for the P90; the match-factor formula of `minephys.haulage.match_factor` (spec 001 FR-001-18: n_trucks x load_time / (n_loaders x cycle_time)) written out; the three relations of P-007-20.

Hand trace (seconds; D is the single dump, node 4; payloads in tonnes). Columns: truck, loader node, arrive-loader, load start, haul (load end), arrive-dump, dump start, return.
    3 at L2: 0, 0, 100, 300, 300, 340  (completes before the window: excluded everywhere)
    1 at L1: 700, 700, 1000, 1600, 1600, 1660 (200 t)     2 at L1: 800, 1000, 1300, 1900, 1900, 1960 (220 t; waits 200 s for the loader)
    3 at L2: 900, 900, 1200, 1800, 1800, 1860 (210 t)     1 at L1: 2260, 2260, 2560, 3160, 3160, 3220 (200 t)     3 at L2: 2460, 2460, 2760, 3360, 3360, 3420 (210 t)
    2 at L1: 2560, 2560, 2860, 3460, 3460, 3520 (220 t)   1 at L1: 3820, 3820, 4120 (loaded when the horizon cuts the run: no dump)
    Counting rules used: tonnes and cycles by `return` row inside the window; queue wait of a loader visit = load start - arrive-loader for load starts inside the window, of a dump visit =
    dump start - arrive-dump for dump starts inside the window; busy time = sum of (haul - load) intersected with the window; t_L = mean (haul - load) over load starts inside the window.
    Results: window 3600 s; fleet 1260 t, 6 cycles; L1 840 t / 4 cycles, L2 420 t / 2 cycles; loader waits L1 [0, 200, 0, 0, 0] s, L2 [0, 0] s; busy L1 1500 s, L2 600 s; t_L = 300 s.

Expected API (module `pitstudio_pipeline.haulage.kpi`; errors in `pitstudio_pipeline.haulage.errors`):
    errors.InvalidTrace(HaulError)    attributes `section` ("trace" for a document-level schema failure, "header", "events" or "cyclelog") and `row` (index into that list, or None)
    match_factor(n_trucks, n_loaders, load_time, cycle_time) -> float          n_trucks * load_time / (n_loaders * cycle_time), from `minephys.haulage`
    compute_kpis(trace, *, fleet, loaders, free_flow_cycle_s, cost_rates=None, time_unit="s") -> dict
        `section` is the first segment of the failing JSON pointer when it is events, cyclelog or header, else "trace"; `row` is the first row of that list that fails
    (for the order rule: the first row whose (t_s, seq) is not strictly greater than its predecessor's);
        `trace`: a des-trace document; `fleet`: [{"id", "truck_class"}]; `loaders`: [{"node", "n_spots"}]; `free_flow_cycle_s`: {truck class: T_c*} in the trace's time unit;
        `cost_rates`: {"truck_per_h", "loader_per_h", "currency"} or None; `time_unit`: "s" (default) or "h" (every time in the trace, the window and T_c* are hours).
        Validates the trace first (schema `des-trace`, strict (t_s, seq) order of `events`, finite times and payloads, warm-up < horizon) and raises InvalidTrace.
        Returns {"label": <the honesty label>, "bias_note": <the bias note>, "window": {"start": s, "end": e, "hours": h},
                 "fleet": {"tonnes_t", "production_tph", "cycles", "cycles_per_h", "queue_loader_min": {"mean", "p90"}, "queue_dump_min": {"mean", "p90"}, "loader_utilisation",
                           "match_factor", "truck_h_per_kt", "loader_h_per_kt", "cost_per_t"},
                 "loaders": [{"loader", "tonnes_t", "production_tph", "cycles", "cycles_per_h", "queue_min": {"mean", "p90"}, "utilisation"}, ...] sorted by node}
        Queue statistics are in minutes (seconds / 60) over all visits, P90 by the Hyndman-Fan type 7 rule; `loader_utilisation` of the fleet is total busy time / (window x total spots);
        a loader's `utilisation` is its busy time / (window x its spots); match_factor = (sum over trucks of t_L / T_c*(class of the truck)) / n_loaders (which is the homogeneous formula
        n_trucks x t_L / (n_loaders x T_c*) for one class); truck_h_per_kt = n_trucks x window hours / (tonnes / 1000); loader_h_per_kt likewise with the loaders;
        cost_per_t = (n_trucks x truck_per_h + n_loaders x loader_per_h) x window hours / tonnes, or the string "not-computed (rates not supplied)" when `cost_rates` is None.
        Percentages are fractions (0.5 is 50 %).
"""

from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit as kit
from pitstudio_pipeline.haulage.errors import InvalidTrace
from pitstudio_pipeline.haulage.kpi import compute_kpis, match_factor

SETTINGS = settings(
    max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)
DUMP = 4
CYCLES = [  # truck, loader, arrive-loader, load start, haul, arrive-dump, dump start, return, payload
    (3, 2, 0, 0, 100, 300, 300, 340, 205.0),
    (1, 1, 700, 700, 1000, 1600, 1600, 1660, 200.0),
    (2, 1, 800, 1000, 1300, 1900, 1900, 1960, 220.0),
    (3, 2, 900, 900, 1200, 1800, 1800, 1860, 210.0),
    (1, 1, 2260, 2260, 2560, 3160, 3160, 3220, 200.0),
    (3, 2, 2460, 2460, 2760, 3360, 3360, 3420, 210.0),
    (2, 1, 2560, 2560, 2860, 3460, 3460, 3520, 220.0),
]
OPEN = (1, 1, 3820, 3820, 4120)  # loading ends inside the window, the horizon cuts the run before the dump
FLEET = [
    {"id": 1, "truck_class": "CAT_793F"},
    {"id": 2, "truck_class": "CAT_793F"},
    {"id": 3, "truck_class": "CAT_793F"},
]
LOADERS = [{"node": 1, "n_spots": 1}, {"node": 2, "n_spots": 1}]
FREE_FLOW = {"CAT_793F": 1560.0}
RATES = {"truck_per_h": 450.0, "loader_per_h": 900.0, "currency": "USD"}


def hand_trace(*, horizon=4200.0, warmup=600.0, cycles=CYCLES, open_cycle=OPEN) -> dict:
    ev, cl = [], []
    for tr, ld, a, s, h, d, e, r, p in cycles:
        ev += [
            (a, "arrive-loader", tr, ld),
            (h, "load-end", tr, ld),
            (d, "arrive-dump", tr, DUMP),
            (r, "dump-end", tr, DUMP),
        ]
        cl += [(s, tr, ld, "load", 0.0), (h, tr, ld, "haul", p), (e, tr, DUMP, "dump", p), (r, tr, DUMP, "return", 0.0)]
    if open_cycle:
        tr, ld, a, s, h = open_cycle
        ev += [(a, "arrive-loader", tr, ld), (h, "load-end", tr, ld)]
        cl += [(s, tr, ld, "load", 0.0), (h, tr, ld, "haul", 200.0)]
    ev = [x for _, x in sorted(enumerate(ev), key=lambda ix: (ix[1][0], ix[0]))]
    cl = [x for _, x in sorted(enumerate(cl), key=lambda ix: (ix[1][0], ix[1][1], ix[0]))]
    return kit.make_trace(ev, cl, horizon_s=horizon, warmup_s=warmup)


def kpis(trace=None, **kw):
    kw.setdefault("fleet", FLEET)
    kw.setdefault("loaders", LOADERS)
    kw.setdefault("free_flow_cycle_s", FREE_FLOW)
    return compute_kpis(trace or hand_trace(), **kw)


def loader(k, node):
    return next(x for x in k["loaders"] if x["loader"] == node)


# ---------------------------------------------------------------------------------------------------------------------
# the hand-calculated table
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-08")
def test_the_window_and_the_honesty_label():
    k = kpis()
    assert k["window"] == {"start": 600.0, "end": 4200.0, "hours": 1.0}
    assert k["label"] == kit.LABEL and k["bias_note"] == kit.BIAS_NOTE


@pytest.mark.req("FR-007-08")
def test_fleet_production_and_cycles_per_hour():
    f = kpis()["fleet"]
    assert f["tonnes_t"] == pytest.approx(
        1260.0, rel=1e-12
    )  # 200 + 220 + 210 + 200 + 210 + 220; the cycle returning at 340 s is outside the window
    assert (
        f["production_tph"] == pytest.approx(1260.0, rel=1e-12)
        and f["cycles"] == 6
        and f["cycles_per_h"] == pytest.approx(6.0, rel=1e-12)
    )


@pytest.mark.req("FR-007-08")
def test_each_dump_is_attributed_to_the_loader_of_the_trucks_last_load():
    k = kpis()
    l1, l2 = loader(k, 1), loader(k, 2)
    assert (l1["tonnes_t"], l1["cycles"]) == (pytest.approx(840.0, rel=1e-12), 4)  # 200 + 220 + 200 + 220
    assert (l2["tonnes_t"], l2["cycles"]) == (pytest.approx(420.0, rel=1e-12), 2)  # 210 + 210
    assert l1["production_tph"] == pytest.approx(840.0, rel=1e-12) and l2["production_tph"] == pytest.approx(
        420.0, rel=1e-12
    )
    assert l1["cycles_per_h"] == pytest.approx(4.0, rel=1e-12) and l2["cycles_per_h"] == pytest.approx(2.0, rel=1e-12)
    assert [x["loader"] for x in k["loaders"]] == [1, 2]


@pytest.mark.req("FR-007-08")
def test_queue_time_mean_and_p90_in_minutes_per_loader_and_for_the_fleet():
    k = kpis()
    p90 = lambda xs: float(np.percentile(xs, 90, method="linear"))  # noqa: E731  (Hyndman-Fan type 7)
    waits_l1, waits_all = [0, 200, 0, 0, 0], [0, 200, 0, 0, 0, 0, 0]  # loader 2 has two visits with no wait
    assert loader(k, 1)["queue_min"]["mean"] == pytest.approx(40 / 60, rel=1e-12)  # 200 s / 5 visits
    assert p90(waits_l1) == pytest.approx(120.0)  # the oracle itself: 0.6 x 200 s
    assert loader(k, 1)["queue_min"]["p90"] == pytest.approx(2.0, rel=1e-12)
    assert loader(k, 2)["queue_min"] == {"mean": 0.0, "p90": 0.0}
    q = k["fleet"]["queue_loader_min"]
    assert p90(waits_all) == pytest.approx(80.0)  # 0.4 x 200 s
    assert q["mean"] == pytest.approx(200 / 7 / 60, rel=1e-12) and q["p90"] == pytest.approx(80 / 60, rel=1e-12)
    assert k["fleet"]["queue_dump_min"] == {"mean": 0.0, "p90": 0.0}  # every truck arrived at a free dump


@pytest.mark.req("FR-007-08")
def test_dump_queue_time_comes_from_arrival_and_dump_start():
    cycles = [
        (1, 1, 700, 700, 1000, 1600, 1720, 1780, 200.0),
        (2, 1, 1000, 1000, 1300, 1900, 1900, 1960, 220.0),
    ]  # truck 1 waits 120 s at the dump
    k = kpis(hand_trace(cycles=cycles, open_cycle=None), fleet=FLEET[:2], loaders=[LOADERS[0]])
    q = k["fleet"]["queue_dump_min"]
    assert q["mean"] == pytest.approx(60 / 60, rel=1e-12) and q["p90"] == pytest.approx(
        (120 * 0.9) / 60, rel=1e-12
    )  # waits [120, 0] s: mean 60 s; p90 = 0 + 0.9 x 120 s


@pytest.mark.req("FR-007-08")
def test_loader_utilisation_is_busy_time_over_window_times_spots():
    k = kpis()
    assert loader(k, 1)["utilisation"] == pytest.approx(1500 / 3600, rel=1e-12)  # 300 s x 5 loadings
    assert loader(k, 2)["utilisation"] == pytest.approx(600 / 3600, rel=1e-12)
    assert k["fleet"]["loader_utilisation"] == pytest.approx(2100 / 7200, rel=1e-12)
    k2 = kpis(loaders=[{"node": 1, "n_spots": 2}, {"node": 2, "n_spots": 1}])
    assert loader(k2, 1)["utilisation"] == pytest.approx(1500 / 7200, rel=1e-12)  # two spots share the busy time


@pytest.mark.req("FR-007-08")
def test_match_factor_homogeneous_and_heterogeneous():
    # t_L = 300 s, T_c* = 1560 s: MF = 3 x 300 / (2 x 1560)
    assert kpis()["fleet"]["match_factor"] == pytest.approx(900 / 3120, rel=1e-12)
    # trucks 1 and 2 are CAT_793F (T_c* 1000 s), truck 3 a CAT_777G (T_c* 2000 s): MF = (300/1000 + 300/1000 + 300/2000) / 2 loaders
    het_fleet = [FLEET[0], FLEET[1], {"id": 3, "truck_class": "CAT_777G"}]
    k = kpis(fleet=het_fleet, free_flow_cycle_s={"CAT_793F": 1000.0, "CAT_777G": 2000.0})
    assert k["fleet"]["match_factor"] == pytest.approx(0.375, rel=1e-12)


@pytest.mark.req("FR-007-08")
def test_resource_hours_per_kilotonne():
    f = kpis()["fleet"]
    assert f["truck_h_per_kt"] == pytest.approx(3.0 / 1.26, rel=1e-12)  # 3 trucks x 1 h over 1.26 kt
    assert f["loader_h_per_kt"] == pytest.approx(2.0 / 1.26, rel=1e-12)


@pytest.mark.req("FR-007-08")
def test_cost_per_tonne_only_with_both_rates():
    assert (
        kpis(cost_rates=RATES)["fleet"]["cost_per_t"]
        == pytest.approx((3 * 450.0 + 2 * 900.0) / 1260.0, rel=1e-12)
        == pytest.approx(2.5, rel=1e-12)
    )
    assert kpis()["fleet"]["cost_per_t"] == "not-computed (rates not supplied)"
    assert kpis(cost_rates=None)["fleet"]["cost_per_t"] == "not-computed (rates not supplied)"
    for partial in ({"truck_per_h": 450.0, "currency": "USD"}, {"loader_per_h": 900.0, "currency": "USD"}, {}):
        assert kpis(cost_rates=partial)["fleet"]["cost_per_t"] == "not-computed (rates not supplied)"


@pytest.mark.req("FR-007-08")
def test_the_window_is_closed_at_both_ends_and_rows_outside_it_do_not_count():
    cycles = [
        (1, 1, 100, 100, 200, 300, 300, 599.999, 1.0),  # truck 1 returns just before the warm-up
        (1, 1, 600, 600, 650, 680, 680, 700.0, 2.0),  # returns at 700: inside
        (1, 1, 750, 750, 800, 850, 850, 4200.0, 4.0),  # returns exactly at the horizon: inside (the window is closed)
        (2, 1, 1200, 1200, 1300, 1400, 1400, 4200.001, 8.0),  # truck 2 returns just after the horizon: outside
    ]
    tr = hand_trace(cycles=cycles, open_cycle=None)
    k = compute_kpis(tr, fleet=FLEET[:2], loaders=[LOADERS[0]], free_flow_cycle_s=FREE_FLOW)
    assert k["fleet"]["tonnes_t"] == pytest.approx(6.0, rel=1e-12) and k["fleet"]["cycles"] == 2  # 2 t + 4 t


@pytest.mark.req("FR-007-08")
def test_an_empty_window_gives_zero_production_and_no_division_by_zero():
    tr = hand_trace(cycles=[], open_cycle=None)
    k = compute_kpis(tr, fleet=FLEET, loaders=LOADERS, free_flow_cycle_s=FREE_FLOW, cost_rates=RATES)
    f = k["fleet"]
    assert f["tonnes_t"] == 0.0 and f["production_tph"] == 0.0 and f["cycles"] == 0
    for key in (
        "truck_h_per_kt",
        "loader_h_per_kt",
        "match_factor",
        "cost_per_t",
    ):  # undefined ratios are None or a text, never NaN or infinity
        assert f[key] is None or isinstance(f[key], str) or math.isfinite(f[key]), key


# ---------------------------------------------------------------------------------------------------------------------
# P-007-20
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("P-007-20")
@SETTINGS
@given(st.integers(1, 40), st.integers(1, 40), st.floats(1.0, 1e4), st.floats(1.0, 1e5), st.integers(1, 50))
def test_match_factor_is_homogeneous_of_degree_zero_in_trucks_and_loaders(n_t, n_l, t_l, t_c, k):
    assert match_factor(k * n_t, k * n_l, t_l, t_c) == pytest.approx(match_factor(n_t, n_l, t_l, t_c), rel=1e-12)
    assert match_factor(n_t, n_l, t_l, t_c) == pytest.approx(n_t * t_l / (n_l * t_c), rel=1e-12)


def hours(tr: dict) -> dict:
    h = copy.deepcopy(tr)
    h["header"]["horizon_s"] = tr["header"]["horizon_s"] / 3600.0
    h["header"]["kpi_window"]["warmup_s"] = tr["header"]["kpi_window"]["warmup_s"] / 3600.0
    for e in h["events"]:
        e["t_s"] /= 3600.0
    for r in h["cyclelog"]:
        r["t_s"] /= 3600.0
    return h


@pytest.mark.req("P-007-20")
def test_the_kpis_do_not_depend_on_whether_times_are_in_seconds_or_hours():
    tr = hand_trace()
    a = kpis(tr)
    b = compute_kpis(
        hours(tr), fleet=FLEET, loaders=LOADERS, free_flow_cycle_s={"CAT_793F": 1560.0 / 3600.0}, time_unit="h"
    )
    assert b["fleet"]["production_tph"] == pytest.approx(a["fleet"]["production_tph"], rel=1e-12)
    assert b["fleet"]["match_factor"] == pytest.approx(a["fleet"]["match_factor"], rel=1e-12)
    assert b["fleet"]["loader_utilisation"] == pytest.approx(a["fleet"]["loader_utilisation"], rel=1e-12)
    assert b["fleet"]["queue_loader_min"]["mean"] == pytest.approx(
        a["fleet"]["queue_loader_min"]["mean"], rel=1e-9
    )  # minutes in both


@st.composite
def random_traces(draw):
    n_trucks, n_loaders = draw(st.integers(1, 4)), draw(st.integers(1, 3))
    cycles, nodes = [], list(range(1, n_loaders + 1))
    for tr in range(1, n_trucks + 1):
        t = draw(st.integers(0, 200))
        for _ in range(draw(st.integers(1, 5))):
            ld = draw(st.sampled_from(nodes))
            wait = draw(st.integers(0, 120))
            load = draw(st.integers(30, 400))
            haul = draw(st.integers(100, 900))
            dwait = draw(st.integers(0, 60))
            dump = draw(st.integers(20, 120))
            a = t
            s = a + wait
            h = s + load
            d = h + haul
            e = d + dwait
            r = e + dump
            cycles.append((tr, ld, a, s, h, d, e, r, float(draw(st.integers(50, 300)))))
            t = r + draw(st.integers(100, 900))
    horizon = float(max(c[7] for c in cycles) + 50)
    return (
        hand_trace(horizon=horizon, warmup=float(draw(st.integers(0, 300))), cycles=cycles, open_cycle=None),
        n_trucks,
        n_loaders,
    )


@pytest.mark.req("P-007-20")
@SETTINGS
@given(random_traces())
def test_fleet_tonnes_and_cycles_equal_the_sum_over_loaders(case):
    tr, n_t, n_l = case
    k = compute_kpis(
        tr,
        fleet=[{"id": i, "truck_class": "CAT_793F"} for i in range(1, n_t + 1)],
        loaders=[{"node": n, "n_spots": 1} for n in range(1, n_l + 1)],
        free_flow_cycle_s={"CAT_793F": 1500.0},
    )
    assert sum(x["tonnes_t"] for x in k["loaders"]) == pytest.approx(k["fleet"]["tonnes_t"], rel=1e-12, abs=1e-12)
    assert sum(x["cycles"] for x in k["loaders"]) == k["fleet"]["cycles"]
    assert sum(x["production_tph"] for x in k["loaders"]) == pytest.approx(
        k["fleet"]["production_tph"], rel=1e-12, abs=1e-12
    )


@pytest.mark.req("P-007-20")
@SETTINGS
@given(random_traces())
def test_random_traces_give_the_same_kpis_in_hours(case):
    tr, n_t, n_l = case
    fleet = [{"id": i, "truck_class": "CAT_793F"} for i in range(1, n_t + 1)]
    loaders = [{"node": n, "n_spots": 1} for n in range(1, n_l + 1)]
    a = compute_kpis(tr, fleet=fleet, loaders=loaders, free_flow_cycle_s={"CAT_793F": 1500.0})
    b = compute_kpis(
        hours(tr), fleet=fleet, loaders=loaders, free_flow_cycle_s={"CAT_793F": 1500.0 / 3600.0}, time_unit="h"
    )
    assert b["fleet"]["production_tph"] == pytest.approx(a["fleet"]["production_tph"], rel=1e-12, abs=1e-12)
    assert b["fleet"]["loader_utilisation"] == pytest.approx(a["fleet"]["loader_utilisation"], rel=1e-9, abs=1e-12)
    ma, mb = a["fleet"]["match_factor"], b["fleet"]["match_factor"]
    assert (ma is None and mb is None) or mb == pytest.approx(ma, rel=1e-9)


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-42: malformed traces
# ---------------------------------------------------------------------------------------------------------------------
def bad(mutate) -> InvalidTrace:
    tr = hand_trace()
    mutate(tr)
    with pytest.raises(InvalidTrace) as ei:
        kpis(tr)
    return ei.value


@pytest.mark.req("FR-007-42")
def test_a_valid_hand_trace_is_accepted():
    assert kpis()["fleet"]["cycles"] == 6


@pytest.mark.req("FR-007-42")
def test_events_not_strictly_ordered_by_t_and_seq_name_the_first_offending_row():
    def swap(tr):
        tr["events"][5], tr["events"][6] = tr["events"][6], tr["events"][5]

    e = bad(swap)
    assert (e.section, e.row) == ("events", 6)  # the first row whose (t_s, seq) is not greater than its predecessor's
    e2 = bad(
        lambda tr: tr["events"].__setitem__(8, dict(tr["events"][7]))
    )  # an exact duplicate of the previous row (same t, same seq)
    assert (e2.section, e2.row) == ("events", 8)
    base = hand_trace()["events"]
    i = next(
        i for i in range(1, len(base)) if base[i]["t_s"] == base[i - 1]["t_s"]
    )  # simultaneous events: only seq orders them
    e3 = bad(lambda tr: tr["events"][i].__setitem__("seq", tr["events"][i - 1]["seq"] - 1))
    assert (e3.section, e3.row) == ("events", i)


@pytest.mark.req("FR-007-42")
def test_equal_times_are_fine_when_seq_increases():
    tr = hand_trace()
    same_t = [i for i in range(1, len(tr["events"])) if tr["events"][i]["t_s"] == tr["events"][i - 1]["t_s"]]
    assert same_t, "the hand trace has simultaneous events (2560 s: a load end and an arrival)"
    assert kpis(tr)["fleet"]["cycles"] == 6


@pytest.mark.req("FR-007-42")
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_time_or_payload_is_rejected_naming_the_row(value):
    e = bad(lambda tr: tr["events"][4].__setitem__("t_s", value))
    assert (e.section, e.row) == ("events", 4)
    e2 = bad(lambda tr: (tr["events"][11].__setitem__("t_s", value), tr["events"][4].__setitem__("t_s", value)))
    assert (e2.section, e2.row) == ("events", 4)  # the first offending row, not the last
    e3 = bad(lambda tr: tr["cyclelog"][7].__setitem__("payload_t", value))
    assert (e3.section, e3.row) == ("cyclelog", 7)
    e4 = bad(lambda tr: tr["cyclelog"][3].__setitem__("t_s", value))
    assert (e4.section, e4.row) == ("cyclelog", 3)


@pytest.mark.req("FR-007-42")
@pytest.mark.parametrize("warmup", [4200.0, 5000.0])
def test_a_window_with_warmup_at_or_after_the_horizon_is_rejected(warmup):
    e = bad(lambda tr: tr["header"]["kpi_window"].__setitem__("warmup_s", warmup))
    assert e.section == "header" and e.row is None


@pytest.mark.req("FR-007-42")
@pytest.mark.parametrize(
    ("mutate", "section"),
    [
        (lambda tr: tr["events"][2].__setitem__("kind", "teleport"), "events"),
        (lambda tr: tr["events"][2].pop("truck"), "events"),
        (lambda tr: tr["events"][2].__setitem__("extra", 1), "events"),
        (lambda tr: tr["events"][2].__setitem__("t_s", -1.0), "events"),
        (lambda tr: tr["events"][2].__setitem__("seq", 0), "events"),
        (lambda tr: tr["cyclelog"][1].__setitem__("event", "park"), "cyclelog"),
        (lambda tr: tr["cyclelog"][1].__setitem__("payload_t", 1001.0), "cyclelog"),
        (lambda tr: tr.pop("results"), "trace"),
        (lambda tr: tr.pop("events"), "trace"),
        (lambda tr: tr["header"].__setitem__("synthetic", False), "header"),
        (lambda tr: tr.__setitem__("extra", 1), "trace"),
    ],
)
def test_schema_violations_are_rejected_with_their_section(mutate, section):
    assert bad(mutate).section == section


@pytest.mark.req("FR-007-42")
@pytest.mark.parametrize("doc", [None, [], "trace", 3, {}])
def test_documents_that_are_not_traces_are_rejected(doc):
    with pytest.raises(InvalidTrace):
        compute_kpis(doc, fleet=FLEET, loaders=LOADERS, free_flow_cycle_s=FREE_FLOW)


@pytest.mark.req("FR-007-42")
def test_no_partial_kpis_are_returned_for_a_rejected_trace():
    tr = hand_trace()
    tr["events"][4]["t_s"] = float("nan")
    result = None
    with pytest.raises(InvalidTrace):
        result = kpis(tr)
    assert result is None

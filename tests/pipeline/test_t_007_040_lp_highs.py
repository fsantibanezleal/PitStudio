# ruff: noqa: E501, PT018
"""T-007-040: the HiGHS upper stage of the two-stage LP dispatch: the worked example (19.5 and 19.2 loads/h; duals 0.375 / 1.25 and 1.6 / 4), typed statuses for hostile LPs, the metamorphic relations.

Requirements: FR-007-19, FR-007-21, P-007-11.

Spec: specs/007-haulage-dispatch/spec.md FR-007-19 (the LP upper stage maximises sum m f_p over the declared loader -> destination paths p, with loader capacity sum f <= mu_s, dump capacity sum f <= kappa_d, the fleet
constraint sum f_p T_p <= N_T (Little's law, T_p the queue-free round trip) and the optional blend floors; HiGHS (`highspy`) in the pipeline; it returns the status, the optimum, f_p and the dual value of every constraint),
FR-007-21 (an infeasible or unbounded LP, a non-finite coefficient, a negative capacity, T_p <= 0 or no path gives the typed status `infeasible`, `unbounded` or `invalid-input` within 1 s), P-007-11 (relaxing any capacity
never lowers the optimum; scaling every loader and dump capacity and N_T by k in {0.5, 2, 3} scales the optimum by k; removing a path never raises the optimum; expressing times in minutes and rates per minute divides the
optimum by 60; random feasible instances of <= 64 paths; rtol 1e-7) and the LP worked example of section 7 (hand calculation).

Oracle: (1) the worked example. Two paths x1 (loader 1) and x2 (loader 2), margin m = 1 load per load, loader capacities mu1 = 12 and mu2 = 10 loads/h, dump capacity 30, round trips T1 = 0.5 h and T2 = 0.8 h, N_T = 12
trucks. Without a blend floor the optimum is 19.5 at (12, 7.5): loader 1 and the fleet constraint bind; the duals y satisfy 1 = y_L1 + 0.5 y_F and 1 = 0.8 y_F, so y_F = 1.25 and y_L1 = 0.375, all others 0; the fleet row
reads 12 x 0.5 + 7.5 x 0.8 = 12. With the blend floor 0.15 x1 - 0.25 x2 >= 0 the optimum is 19.2 at (12, 7.2): the fleet row reads 6 + 5.76 = 11.76 < 12 so y_F = 0, and 1 = y_L1 - 0.15 y_B, 1 = 0.25 y_B give y_B = 4 and
y_L1 = 1.6 (these are the numbers of spec 007 section 7). (2) `scipy.optimize.linprog(method="highs")` called directly on random instances (reference implementation). (3) LP duality: the returned duals are checked for dual
feasibility, complementary slackness and strong duality with the primal. (4) The relations of P-007-11.

Expected API (module `pitstudio_pipeline.haulage.lp`):
    solve_lp(c, a_ub, b_ub) -> LpResult           maximise c.x subject to a_ub x <= b_ub, x >= 0 (lists of floats; a_ub a list of rows). LpResult(status, optimum, x, duals): status in "optimal", "infeasible", "unbounded",
        "invalid-input"; optimum, x and duals are None unless optimal; duals[i] >= 0 is the shadow price of row i (the increase of the optimum per unit increase of b_ub[i]).
        invalid-input: empty c, ragged rows, a non-finite number anywhere. Never raises for hostile numbers.
    solve_dispatch_lp(paths, loader_caps, dump_caps, n_trucks, blend_floors=()) -> DispatchLpResult(status, optimum, flows, duals)
        paths: [{"id": int, "loader": int, "dump": int, "margin": float, "trip_time_h": float}]; loader_caps / dump_caps: {node: capacity (loads/h)}; n_trucks: float; blend_floors:
        [{"terms": [{"loader": int, "coef": float}, ...], "min": float}] meaning sum over terms of coef x (flow of the loader's paths) >= min. flows: {path id: f}; duals: {"loader:<node>": y, "dump:<node>": y, "fleet": y,
        "blend:<index>": y} for every constraint, in the "<=" form (a blend floor is written -sum coef f <= -min), all >= 0. Status `invalid-input` for: no path, a non-finite number, a negative capacity or n_trucks,
        trip_time_h <= 0, a path whose loader or dump has no capacity entry, duplicate path ids; `infeasible` when no flow satisfies the blend floors (e.g. a positive floor on a loader with capacity 0).
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit  # noqa: F401
from pitstudio_pipeline.haulage.lp import solve_dispatch_lp, solve_lp

SETTINGS = settings(
    max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)
RTOL = 1e-7

PATHS = [
    {"id": 1, "loader": 1, "dump": 9, "margin": 1.0, "trip_time_h": 0.5},
    {"id": 2, "loader": 2, "dump": 9, "margin": 1.0, "trip_time_h": 0.8},
]
CAPS_L = {1: 12.0, 2: 10.0}
CAPS_D = {9: 30.0}
BLEND = [{"terms": [{"loader": 1, "coef": 0.15}, {"loader": 2, "coef": -0.25}], "min": 0.0}]


def example(**kw):
    args = {"paths": PATHS, "loader_caps": CAPS_L, "dump_caps": CAPS_D, "n_trucks": 12.0}
    args.update(kw)
    return solve_dispatch_lp(**args)


# ---------------------------------------------------------------------------------------------------------------------
# the worked example
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-19")
def test_worked_example_without_a_blend_floor():
    r = example()
    assert r.status == "optimal"
    assert r.optimum == pytest.approx(19.5, rel=1e-9)
    assert r.flows[1] == pytest.approx(12.0, rel=1e-9) and r.flows[2] == pytest.approx(7.5, rel=1e-9)
    assert r.duals["loader:1"] == pytest.approx(0.375, abs=1e-9) and r.duals["fleet"] == pytest.approx(1.25, abs=1e-9)
    assert r.duals["loader:2"] == pytest.approx(0.0, abs=1e-9) and r.duals["dump:9"] == pytest.approx(0.0, abs=1e-9)
    assert set(r.duals) == {"loader:1", "loader:2", "dump:9", "fleet"}  # the dual value of every constraint


@pytest.mark.req("FR-007-19")
def test_worked_example_with_the_blend_floor():
    r = example(blend_floors=BLEND)
    assert r.status == "optimal"
    assert r.optimum == pytest.approx(19.2, rel=1e-9)
    assert r.flows[1] == pytest.approx(12.0, rel=1e-9) and r.flows[2] == pytest.approx(7.2, rel=1e-9)
    assert r.duals["loader:1"] == pytest.approx(1.6, abs=1e-9) and r.duals["blend:0"] == pytest.approx(4.0, abs=1e-9)
    assert r.duals["fleet"] == pytest.approx(0.0, abs=1e-9) and r.duals["loader:2"] == pytest.approx(0.0, abs=1e-9)
    assert set(r.duals) == {"loader:1", "loader:2", "dump:9", "fleet", "blend:0"}


@pytest.mark.req("FR-007-19")
def test_the_generic_form_solves_a_textbook_lp():
    # max 3x + 2y s.t. x + y <= 4, x + 3y <= 7, x <= 3: optimum 11 at (3, 1); the second row (3 + 3 = 6 < 7) is slack; duals (2, 0, 1) (by hand: 3 = y1 + y3, 2 = y1)
    r = solve_lp([3.0, 2.0], [[1.0, 1.0], [1.0, 3.0], [1.0, 0.0]], [4.0, 7.0, 3.0])
    assert r.status == "optimal" and r.optimum == pytest.approx(11.0, rel=1e-9)
    assert r.x == pytest.approx([3.0, 1.0], rel=1e-9) and r.duals == pytest.approx([2.0, 0.0, 1.0], abs=1e-9)


# ---------------------------------------------------------------------------------------------------------------------
# random instances: against scipy/HiGHS, and duality
# ---------------------------------------------------------------------------------------------------------------------
@st.composite
def instances(draw, max_paths=64):
    n_loaders, n_dumps = draw(st.integers(1, 4)), draw(st.integers(1, 3))
    paths, pid = [], 0
    for ld in range(1, n_loaders + 1):
        for dp in draw(st.lists(st.integers(1, n_dumps), min_size=1, max_size=2, unique=True)):
            pid += 1
            paths.append(
                {
                    "id": pid,
                    "loader": ld,
                    "dump": 100 + dp,
                    "margin": draw(st.integers(2, 12)) / 4,
                    "trip_time_h": draw(st.integers(2, 30)) / 20,
                }
            )
    caps_l = {ld: float(draw(st.integers(5, 40))) for ld in range(1, n_loaders + 1)}
    caps_d = {100 + dp: float(draw(st.integers(10, 80))) for dp in range(1, n_dumps + 1)}
    blends = []
    if draw(st.booleans()) and n_loaders >= 2:
        blends = [
            {
                "terms": [
                    {"loader": 1, "coef": draw(st.integers(1, 6)) / 20},
                    {"loader": 2, "coef": -draw(st.integers(1, 6)) / 20},
                ],
                "min": 0.0,
            }
        ]
    return {
        "paths": paths[:max_paths],
        "loader_caps": caps_l,
        "dump_caps": caps_d,
        "n_trucks": float(draw(st.integers(3, 40))),
        "blend_floors": blends,
    }


def rows_of(inst):
    """The constraint rows in the documented `<=` form, with their names (independent of the solver under test)."""
    paths = inst["paths"]
    rows, rhs, names = [], [], []
    for ld, cap in inst["loader_caps"].items():
        rows.append([1.0 if p["loader"] == ld else 0.0 for p in paths])
        rhs.append(cap)
        names.append(f"loader:{ld}")
    for dp, cap in inst["dump_caps"].items():
        rows.append([1.0 if p["dump"] == dp else 0.0 for p in paths])
        rhs.append(cap)
        names.append(f"dump:{dp}")
    rows.append([p["trip_time_h"] for p in paths])
    rhs.append(inst["n_trucks"])
    names.append("fleet")
    for k, b in enumerate(inst["blend_floors"]):
        coef = {t["loader"]: t["coef"] for t in b["terms"]}
        rows.append([-coef.get(p["loader"], 0.0) for p in paths])
        rhs.append(-b["min"])
        names.append(f"blend:{k}")
    return rows, rhs, names


@pytest.mark.req("FR-007-19")
@SETTINGS
@given(instances())
def test_the_optimum_equals_scipy_highs_and_the_duals_satisfy_lp_duality(inst):
    from scipy.optimize import linprog

    rows, rhs, names = rows_of(inst)
    c = [-p["margin"] for p in inst["paths"]]
    ref = linprog(c, A_ub=rows, b_ub=rhs, bounds=(0, None), method="highs")
    r = solve_dispatch_lp(**inst)
    assert ref.status == 0 and r.status == "optimal"
    assert r.optimum == pytest.approx(-ref.fun, rel=RTOL, abs=1e-9)
    f = np.array([r.flows[p["id"]] for p in inst["paths"]])
    assert np.all(f >= -1e-9) and np.all(np.array(rows) @ f <= np.array(rhs) + 1e-7)  # primal feasibility
    assert float(np.dot([p["margin"] for p in inst["paths"]], f)) == pytest.approx(r.optimum, rel=RTOL, abs=1e-9)
    y = np.array([r.duals[n] for n in names])
    a = np.array(rows)
    assert np.all(y >= -1e-9)  # dual feasibility
    reduced = np.array([p["margin"] for p in inst["paths"]]) - a.T @ y
    assert np.all(reduced <= 1e-7)
    assert float(y @ np.array(rhs)) == pytest.approx(r.optimum, rel=1e-6, abs=1e-7)  # strong duality
    assert np.all(np.abs(y * (np.array(rhs) - a @ f)) <= 1e-6)  # complementary slackness on the rows
    assert np.all(np.abs(f * reduced) <= 1e-6)  # and on the variables


@pytest.mark.req("FR-007-19")
@SETTINGS
@given(instances(), st.data())
def test_the_generic_form_agrees_with_the_dispatch_form(inst, data):
    rows, rhs, names = rows_of(inst)
    g = solve_lp([p["margin"] for p in inst["paths"]], rows, rhs)
    d = solve_dispatch_lp(**inst)
    assert g.status == d.status == "optimal"
    assert g.optimum == pytest.approx(d.optimum, rel=RTOL, abs=1e-9)
    assert len(g.duals) == len(names) and set(d.duals) == set(
        names
    )  # (the duals of a degenerate optimum are not unique, so only their number is compared)


# ---------------------------------------------------------------------------------------------------------------------
# P-007-11 relations
# ---------------------------------------------------------------------------------------------------------------------
def opt(inst):
    r = solve_dispatch_lp(**inst)
    assert r.status == "optimal"
    return r.optimum


@pytest.mark.req("P-007-11")
@SETTINGS
@given(instances(), st.sampled_from(["loader", "dump", "fleet"]), st.floats(0.0, 20.0), st.data())
def test_relaxing_a_capacity_never_lowers_the_optimum(inst, kind, delta, data):
    base = opt(inst)
    relaxed = {**inst, "loader_caps": dict(inst["loader_caps"]), "dump_caps": dict(inst["dump_caps"])}
    if kind == "loader":
        ld = data.draw(st.sampled_from(sorted(inst["loader_caps"])))
        relaxed["loader_caps"][ld] += delta
    elif kind == "dump":
        dp = data.draw(st.sampled_from(sorted(inst["dump_caps"])))
        relaxed["dump_caps"][dp] += delta
    else:
        relaxed["n_trucks"] = inst["n_trucks"] + delta
    assert opt(relaxed) >= base - 1e-9


@pytest.mark.req("P-007-11")
@SETTINGS
@given(instances(), st.sampled_from([0.5, 2.0, 3.0]))
def test_scaling_every_capacity_and_the_fleet_by_k_scales_the_optimum_by_k(inst, k):
    scaled = {
        **inst,
        "loader_caps": {n: c * k for n, c in inst["loader_caps"].items()},
        "dump_caps": {n: c * k for n, c in inst["dump_caps"].items()},
        "n_trucks": inst["n_trucks"] * k,
    }
    assert opt(scaled) == pytest.approx(k * opt(inst), rel=RTOL, abs=1e-9)


@pytest.mark.req("P-007-11")
@SETTINGS
@given(instances(), st.data())
def test_removing_a_path_never_raises_the_optimum(inst, data):
    if len(inst["paths"]) < 2:
        return
    drop = data.draw(st.sampled_from([p["id"] for p in inst["paths"]]))
    smaller = {**inst, "paths": [p for p in inst["paths"] if p["id"] != drop], "blend_floors": []}
    full = {**inst, "blend_floors": []}  # compare without blend floors: a floor can make a smaller set infeasible
    assert opt(smaller) <= opt(full) + 1e-9


@pytest.mark.req("P-007-11")
@SETTINGS
@given(instances())
def test_times_in_minutes_and_rates_per_minute_divide_the_optimum_by_60(inst):
    minutes = {
        **inst,
        "paths": [{**p, "trip_time_h": p["trip_time_h"] * 60.0} for p in inst["paths"]],
        "loader_caps": {n: c / 60.0 for n, c in inst["loader_caps"].items()},
        "dump_caps": {n: c / 60.0 for n, c in inst["dump_caps"].items()},
    }
    assert opt(minutes) == pytest.approx(opt(inst) / 60.0, rel=RTOL, abs=1e-12)


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-21: typed statuses
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-21")
def test_an_infeasible_blend_floor_is_the_typed_status_infeasible():
    r = solve_dispatch_lp(
        PATHS,
        {1: 0.0, 2: 10.0},
        CAPS_D,
        12.0,
        blend_floors=[{"terms": [{"loader": 1, "coef": 0.15}, {"loader": 2, "coef": -0.25}], "min": 1.0}],
    )
    assert r.status == "infeasible" and r.optimum is None and r.flows is None and r.duals is None


@pytest.mark.req("FR-007-21")
def test_generic_infeasible_and_unbounded_lps_are_typed():
    inf = solve_lp([1.0], [[1.0]], [-1.0])  # x <= -1 with x >= 0
    assert inf.status == "infeasible" and inf.optimum is None and inf.x is None and inf.duals is None
    unb = solve_lp([1.0, 0.0], [[-1.0, 1.0]], [1.0])  # max x with -x + y <= 1: x grows with y
    assert unb.status == "unbounded" and unb.optimum is None


BAD_DISPATCH = [
    {"paths": []},
    {"paths": [{**PATHS[0], "margin": float("nan")}]},
    {"paths": [{**PATHS[0], "margin": float("inf")}]},
    {"paths": [{**PATHS[0], "trip_time_h": 0.0}]},
    {"paths": [{**PATHS[0], "trip_time_h": -0.5}]},
    {"paths": [{**PATHS[0], "trip_time_h": float("nan")}]},
    {"paths": [PATHS[0], {**PATHS[1], "id": 1}]},  # duplicate path id
    {"paths": [{**PATHS[0], "loader": 7}]},  # no capacity entry for the loader
    {"paths": [{**PATHS[0], "dump": 7}]},
    {"loader_caps": {1: -1.0, 2: 10.0}},
    {"loader_caps": {1: float("nan"), 2: 10.0}},
    {"dump_caps": {9: -5.0}},
    {"dump_caps": {9: float("inf")}},
    {"n_trucks": -1.0},
    {"n_trucks": float("nan")},
    {"n_trucks": float("inf")},
    {"blend_floors": [{"terms": [{"loader": 1, "coef": float("nan")}], "min": 0.0}]},
    {"blend_floors": [{"terms": [{"loader": 1, "coef": 1.0}], "min": float("inf")}]},
]


@pytest.mark.req("FR-007-21")
@pytest.mark.parametrize("bad", BAD_DISPATCH, ids=[str(i) for i in range(len(BAD_DISPATCH))])
def test_hostile_dispatch_inputs_return_invalid_input_within_one_second(bad):
    t0 = time.perf_counter()
    r = example(**bad)
    assert r.status == "invalid-input" and r.optimum is None and r.flows is None and r.duals is None
    assert time.perf_counter() - t0 < 1.0


@pytest.mark.req("FR-007-21")
@pytest.mark.parametrize(
    "args",
    [
        ([], [], []),
        ([1.0], [[1.0, 2.0]], [1.0]),
        ([1.0], [[1.0]], [float("nan")]),
        ([float("inf")], [[1.0]], [1.0]),
        ([1.0], [[float("nan")]], [1.0]),
        ([1.0, 2.0], [[1.0], [1.0, 1.0]], [1.0, 1.0]),
    ],
)
def test_hostile_generic_inputs_return_invalid_input(args):
    r = solve_lp(*args)
    assert r.status == "invalid-input" and r.optimum is None


@pytest.mark.req("FR-007-21")
def test_a_capacity_of_zero_is_valid_and_forces_a_zero_flow():
    r = example(loader_caps={1: 0.0, 2: 10.0})
    assert r.status == "optimal" and r.flows[1] == pytest.approx(0.0, abs=1e-12) and math.isfinite(r.optimum)
    assert r.optimum == pytest.approx(10.0, rel=1e-9)  # loader 2 alone: min(10, (12 - 0) / 0.8 = 15) = 10

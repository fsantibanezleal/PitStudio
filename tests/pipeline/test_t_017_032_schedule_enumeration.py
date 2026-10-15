"""T-017-032: tiny-instance exactness by enumeration; capacity monotonicity (pipeline).

Requirements: FR-017-20, P-017-08 (and the scheduler half of P-017-07).

Spec: specs/017-planning-survey/spec.md
- FR-017-20: on tiny instances (<= 8 units, <= 3 periods) the scheduler's objective equals the optimum found by
  exhaustive enumeration of every feasible assignment;
- P-017-08: on tiny instances, raising a capacity never lowers the optimal NPV (<= 8 units, <= 3 periods; exact
  order, at
  gap 0);
- P-017-07 (scheduler half): every scheduler output on random feasible instances passes the independent checker of
  FR-017-19 (see tests/property/test_t_017_031_schedule_checker.py for the checker itself).
plan.md test strategy row FR-017-20: exhaustive enumeration of all assignments (<= 4^8 = 65,536).

Oracle: exhaustive enumeration written in the test: every assignment of each unit to "not mined" or to one of the T
periods ((T + 1)^n <= 65,536 assignments), keeping those with every precedence respected in time (a required unit is
mined in the same or an earlier period) and every period within its mining and processing capacity; the objective is
sum_t CF_t / (1 + delta)^t over periods t = 1 .. T, with CF_t the sum of `value_cents / 100` of the units mined in
t; the
optimum is the maximum over the feasible assignments (the empty assignment is always feasible, NPV 0).

Expected API: `pitstudio_pipeline.planning.schedule.solve_schedule` (see tests/pipeline/test_t_017_030_schedule.py;
here
called with `mip_rel_gap` 0 so that the optimum is exact) and `pitstudio.planning.checker.check_schedule` (see
tests/property/test_t_017_031_schedule_checker.py).
"""

from __future__ import annotations

import itertools
from types import SimpleNamespace

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.planning.checker import check_schedule
from pitstudio_pipeline.planning.schedule import solve_schedule


@st.composite
def tiny_instances(draw):
    n = draw(st.integers(1, 8))
    t = draw(st.integers(1, 3))
    seed = draw(st.integers(0, 2**32 - 1))
    rate = draw(st.sampled_from([0.0, 0.05, 0.1, 0.3]))
    rng = np.random.default_rng(seed)
    units = [
        {
            "id": i,
            "pushback": 0,
            "bench": n - i,
            "ore_t": float(rng.integers(0, 6) * 100),
            "waste_t": float(rng.integers(0, 6) * 100),
            "value_cents": int(rng.integers(-5_000, 8_001)),
        }
        for i in range(n)
    ]
    arcs = [(i, int(rng.integers(0, i))) for i in range(1, n) if rng.random() < 0.6]
    mining = [float(rng.integers(3, 20) * 100) for _ in range(t)]
    processing = [float(rng.integers(1, 12) * 100) for _ in range(t)]
    return units, arcs, mining, processing, rate


def _config(mining, processing, rate) -> dict:
    return {
        "lambdas": [1.0],
        "t_min_t": 100.0,
        "periods": len(mining),
        "mining_capacity_t": list(mining),
        "processing_capacity_t": list(processing),
        "discount_rate": rate,
        "time_limit_s": 60.0,
        "mip_rel_gap": 0.0,
    }


def _enumerate_optimum(units, arcs, mining, processing, rate) -> float:
    n, periods = len(units), len(mining)
    best = 0.0
    for assignment in itertools.product(range(periods + 1), repeat=n):  # 0 = not mined, k = mined in period k
        if any(assignment[u] > 0 and not (0 < assignment[v] <= assignment[u]) for u, v in arcs):
            continue
        ok = True
        cash = [0.0] * periods
        for k in range(1, periods + 1):
            members = [u for u in range(n) if assignment[u] == k]
            tonnes = sum(units[u]["ore_t"] + units[u]["waste_t"] for u in members)
            ore = sum(units[u]["ore_t"] for u in members)
            if tonnes > mining[k - 1] or ore > processing[k - 1]:
                ok = False
                break
            cash[k - 1] = sum(units[u]["value_cents"] for u in members) / 100.0
        if ok:
            best = max(best, sum(cf / (1 + rate) ** (k + 1) for k, cf in enumerate(cash)))
    return best


def _solve(units, arcs, mining, processing, rate):
    return solve_schedule(SimpleNamespace(units=units, arcs=arcs), _config(mining, processing, rate))


@pytest.mark.req("FR-017-20")
def test_a_hand_instance_matches_the_enumeration() -> None:
    # unit 0 (waste, -5 USD) must precede unit 1 (ore, +20 USD); capacity lets one unit per period be mined
    units = [
        {"id": 0, "pushback": 0, "bench": 1, "ore_t": 0.0, "waste_t": 500.0, "value_cents": -500},
        {"id": 1, "pushback": 0, "bench": 0, "ore_t": 400.0, "waste_t": 0.0, "value_cents": 2000},
    ]
    schedule = _solve(units, [(1, 0)], [500.0, 500.0], [400.0, 400.0], 0.1)
    assert schedule.status == "optimal"
    assert schedule.npv_usd == pytest.approx(-5 / 1.1 + 20 / 1.21, rel=1e-9)  # period 1 then 2, by hand
    assert schedule.npv_usd == pytest.approx(_enumerate_optimum(units, [(1, 0)], [500.0, 500.0], [400.0, 400.0], 0.1))


@pytest.mark.req("FR-017-20")
@settings(max_examples=200, deadline=None)
@given(instance=tiny_instances())
def test_the_scheduler_objective_equals_the_exhaustive_optimum(instance):
    units, arcs, mining, processing, rate = instance
    schedule = _solve(units, arcs, mining, processing, rate)
    assert schedule.status == "optimal"
    assert schedule.npv_usd == pytest.approx(
        _enumerate_optimum(units, arcs, mining, processing, rate), abs=1e-6, rel=1e-9
    )


@pytest.mark.req("P-017-07")
@settings(max_examples=200, deadline=None)
@given(instance=tiny_instances())
def test_every_scheduler_output_passes_the_independent_checker_and_its_npv_is_recomputed(instance):
    units, arcs, mining, processing, rate = instance
    schedule = _solve(units, arcs, mining, processing, rate)
    config = _config(mining, processing, rate)
    result = check_schedule(units, arcs, schedule.periods, config, reported_npv_usd=schedule.npv_usd, npv_rtol=1e-9)
    assert result.ok, result.violations
    assert result.npv_usd == pytest.approx(schedule.npv_usd, rel=1e-9, abs=1e-9)


@pytest.mark.req("P-017-08")
@settings(max_examples=200, deadline=None)
@given(
    instance=tiny_instances(),
    which=st.sampled_from(["mining", "processing"]),
    period=st.integers(0, 2),
    extra=st.integers(1, 20),
)
def test_raising_a_capacity_never_lowers_the_optimal_npv(instance, which, period, extra):
    units, arcs, mining, processing, rate = instance
    k = period % len(mining)
    base = _solve(units, arcs, mining, processing, rate)
    bigger_mining, bigger_processing = list(mining), list(processing)
    if which == "mining":
        bigger_mining[k] += extra * 100.0
    else:
        bigger_processing[k] += extra * 100.0
    raised = _solve(units, arcs, bigger_mining, bigger_processing, rate)
    assert raised.npv_usd >= base.npv_usd - 1e-9

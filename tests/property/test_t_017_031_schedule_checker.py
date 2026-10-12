"""T-017-031: independent schedule checker and NPV recomputation (property).

Requirements: FR-017-19, P-017-07, SC-017-04.

Spec: specs/017-planning-survey/spec.md
- FR-017-19: every produced schedule passes an independent checker that verifies each unit is mined at most once, each
  precedence holds in time, each period's mining and processing tonnage are within capacity, and the reported NPV
  equals
  sum_t CF_t / (1 + delta)^t recomputed from the schedule;
- P-017-07: every scheduler output on random feasible instances passes the checker, and its NPV recomputed from cash
  flows equals the reported NPV (<= 300 units, <= 20 periods, |NPV| >= 0.1 sum |CF_t|; NPV rtol 1e-12);
- SC-017-04: every schedule satisfies every precedence and capacity constraint (the checker).
plan.md test strategy row FR-017-19: schedules violating each constraint once (each must be rejected); "Tolerances":
the plain binary64 sum of <= 300 terms carries <= 3.3e-14 error relative to sum |CF|, the exactly rounded
recomputation
uses `math.fsum`, and instances with |NPV| < 0.1 sum |CF| are discarded.

Oracles:
- `math.fsum` (exactly rounded summation) of the discounted cash flows written in the test: CF_t = sum of the
  `value_cents / 100` of the units mined in period t, NPV = fsum(CF_t / (1 + delta)^t) for t = 1, 2, ...;
- the spec's four-block example (units, one arc, schedule): -3 / 1.1 + 5 / 1.21 = 1.4049586776859504 (the example file
  stores the rounded 1.404959);
- hand-built schedules that violate exactly one constraint each (a unit mined twice, a precedence violated in time,
  one
  tonne over the mining capacity, one over the processing capacity, an NPV off by 1e-6, an unknown unit id);
- random feasible schedules built by the test with a simple greedy rule (periods in order; mine random eligible units
  while the capacities allow), which are feasible by construction.
The scheduler's own outputs are checked in tests/pipeline/test_t_017_032_schedule_enumeration.py.

Expected public API (module `pitstudio.planning.checker`, root environment, pure Python):
    @dataclass CheckResult      # ok: bool, violations: list[str], npv_usd: float (recomputed), cash_flows:
    list[float]
    check_schedule(units: Sequence[Mapping], arcs: Sequence[tuple[int, int]], periods: Sequence[Mapping],
                   config: Mapping, *, reported_npv_usd: float | None = None, npv_rtol: float = 1e-12) -> CheckResult
        units: {"id", "ore_t", "waste_t", "value_cents"}; arcs: (u, v) "u requires v" (v mined in the same or an
        earlier period); periods: [{"t", "units": [ids]}] for t = 1 ..; config: mining_capacity_t,
        processing_capacity_t
        (per period) and discount_rate. Violations are strings containing one of "twice" (a unit mined more than
        once),
        "unknown unit", "precedence", "mining capacity", "processing capacity", "period" (periods not numbered 1..n or
        more than the capacities), "npv" (the reported NPV differs from the recomputation by more than npv_rtol).
        npv_usd = math.fsum(CF_t / (1 + delta) ** t).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pitstudio.planning.checker import check_schedule

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads((ROOT / "specs/017-planning-survey/contracts/examples/pit-shells.valid.json").read_text("utf-8"))
UNITS = EXAMPLE["units"]
ARCS = [(1, 0)]
CONFIG = {"mining_capacity_t": [3000.0, 3000.0], "processing_capacity_t": [1000.0, 1000.0], "discount_rate": 0.1}
GOOD = [{"t": 1, "units": [0]}, {"t": 2, "units": [1]}]
NPV = -3.0 / 1.1 + 5.0 / 1.21


def _violations(periods, *, reported=NPV, units=UNITS, arcs=ARCS, config=CONFIG) -> list[str]:
    result = check_schedule(units, arcs, periods, config, reported_npv_usd=reported)
    assert result.ok == (not result.violations)
    return result.violations


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-19 and SC-017-04: each constraint
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-19")
@pytest.mark.req("SC-017-04")
def test_the_four_block_example_schedule_passes_and_its_npv_is_recomputed_by_hand() -> None:
    result = check_schedule(UNITS, ARCS, GOOD, CONFIG, reported_npv_usd=NPV)
    assert result.ok
    assert result.cash_flows == [-3.0, 5.0]
    assert result.npv_usd == pytest.approx(1.4049586776859504, rel=1e-12)


@pytest.mark.req("FR-017-19")
def test_the_rounded_npv_stored_in_the_example_file_differs_at_1e_minus_12_but_not_at_1e_minus_6() -> None:
    stored = EXAMPLE["schedule"]["npv_usd"]  # 1.404959
    assert any("npv" in v for v in _violations(GOOD, reported=stored))
    result = check_schedule(UNITS, ARCS, GOOD, CONFIG, reported_npv_usd=stored, npv_rtol=1e-6)
    assert result.ok


@pytest.mark.req("FR-017-19")
@pytest.mark.req("SC-017-04")
def test_a_unit_mined_twice_is_rejected() -> None:
    periods = [{"t": 1, "units": [0]}, {"t": 2, "units": [0, 1]}]
    assert any("twice" in v for v in _violations(periods, reported=None))
    same_period = [{"t": 1, "units": [0, 0]}, {"t": 2, "units": []}]
    assert any("twice" in v for v in _violations(same_period, reported=None))


@pytest.mark.req("FR-017-19")
@pytest.mark.req("SC-017-04")
def test_a_precedence_violated_in_time_is_rejected_and_the_same_period_is_allowed() -> None:
    # unit 1 requires unit 0: mining unit 1 in period 1 and unit 0 in period 2 breaks it
    wrong_order = [{"t": 1, "units": [1]}, {"t": 2, "units": [0]}]
    assert any("precedence" in v for v in _violations(wrong_order, reported=None))
    # unit 1 mined without its required unit 0 ever being mined
    missing = [{"t": 1, "units": [1]}, {"t": 2, "units": []}]
    assert any("precedence" in v for v in _violations(missing, reported=None))
    # same period is fine when the capacity allows it
    cfg = {**CONFIG, "mining_capacity_t": [4000.0, 4000.0], "processing_capacity_t": [1000.0, 1000.0]}
    same = [{"t": 1, "units": [0, 1]}, {"t": 2, "units": []}]
    assert _violations(same, reported=None, config=cfg) == []


@pytest.mark.req("FR-017-19")
@pytest.mark.req("SC-017-04")
def test_a_period_over_the_mining_capacity_by_one_tonne_is_rejected() -> None:
    cfg = {**CONFIG, "mining_capacity_t": [2999.0, 3000.0]}  # unit 0 mines 3,000 t in period 1
    assert any("mining capacity" in v for v in _violations(GOOD, reported=None, config=cfg))
    cfg_ok = {**CONFIG, "mining_capacity_t": [3000.0, 1000.0]}  # exactly at the capacity: allowed
    assert _violations(GOOD, reported=None, config=cfg_ok) == []


@pytest.mark.req("FR-017-19")
@pytest.mark.req("SC-017-04")
def test_a_period_over_the_processing_capacity_by_one_tonne_is_rejected() -> None:
    cfg = {**CONFIG, "processing_capacity_t": [1000.0, 999.0]}  # unit 1 processes 1,000 t of ore in period 2
    assert any("processing capacity" in v for v in _violations(GOOD, reported=None, config=cfg))


@pytest.mark.req("FR-017-19")
def test_a_reported_npv_that_is_wrong_is_rejected_and_the_exact_one_passes() -> None:
    assert _violations(GOOD, reported=NPV) == []
    assert any("npv" in v for v in _violations(GOOD, reported=NPV + 1e-6))
    assert any("npv" in v for v in _violations(GOOD, reported=-NPV))
    assert _violations(GOOD, reported=None) == []  # nothing reported: nothing to compare


@pytest.mark.req("FR-017-19")
def test_unknown_unit_ids_and_malformed_period_numbering_are_rejected() -> None:
    assert any("unknown unit" in v for v in _violations([{"t": 1, "units": [7]}, {"t": 2, "units": []}], reported=None))
    assert any("period" in v for v in _violations([{"t": 2, "units": [0]}, {"t": 1, "units": [1]}], reported=None))
    assert any(
        "period" in v for v in _violations([{"t": 1, "units": []}] * 3, reported=None)
    )  # 3 periods, 2 capacities


@pytest.mark.req("FR-017-19")
def test_an_empty_schedule_is_valid_with_npv_zero() -> None:
    empty = [{"t": 1, "units": []}, {"t": 2, "units": []}]
    result = check_schedule(UNITS, ARCS, empty, CONFIG, reported_npv_usd=0.0)
    assert result.ok
    assert result.npv_usd == 0.0


# ----------------------------------------------------------------------------------------------------------------------
# P-017-07: random feasible schedules
# ----------------------------------------------------------------------------------------------------------------------


@st.composite
def feasible_schedules(draw):
    n = draw(st.integers(1, 300))
    n_periods = draw(st.integers(1, 20))
    seed = draw(st.integers(0, 2**32 - 1))
    rate = draw(st.floats(0.0, 0.5))
    rng = np.random.default_rng(seed)
    units = [
        {
            "id": i,
            "ore_t": float(rng.integers(0, 500)),
            "waste_t": float(rng.integers(0, 500)),
            "value_cents": int(rng.integers(-20_000, 60_000)),
        }
        for i in range(n)
    ]
    arcs = [(i, int(rng.integers(0, i))) for i in range(1, n) if rng.random() < 0.6]  # unit i requires an earlier unit
    mining = [float(rng.integers(500, 6_000)) for _ in range(n_periods)]
    processing = [float(rng.integers(300, 3_000)) for _ in range(n_periods)]
    required = {i: [v for u, v in arcs if u == i] for i in range(n)}
    mined_in: dict[int, int] = {}
    periods = []
    for t in range(n_periods):  # greedy: random eligible units while the capacities allow
        mine_left, ore_left, today = mining[t], processing[t], []
        for u in rng.permutation(n):
            u = int(u)
            if u in mined_in or any(v not in mined_in and v not in today for v in required[u]):
                continue
            tonnes = units[u]["ore_t"] + units[u]["waste_t"]
            if tonnes <= mine_left and units[u]["ore_t"] <= ore_left and rng.random() < 0.5:
                today.append(u)
                mine_left -= tonnes
                ore_left -= units[u]["ore_t"]
        for u in today:
            mined_in[u] = t
        periods.append({"t": t + 1, "units": today})
    return (
        units,
        arcs,
        periods,
        {"mining_capacity_t": mining, "processing_capacity_t": processing, "discount_rate": rate},
    )


@pytest.mark.req("P-017-07")
@pytest.mark.req("FR-017-19")
@settings(max_examples=200, deadline=None)
@given(instance=feasible_schedules())
def test_a_feasible_schedule_passes_and_the_recomputed_npv_equals_the_fsum_oracle(instance):
    units, arcs, periods, config = instance
    cash = [math.fsum(units[u]["value_cents"] / 100.0 for u in p["units"]) for p in periods]
    oracle = math.fsum(cf / (1.0 + config["discount_rate"]) ** (t + 1) for t, cf in enumerate(cash))
    assume(abs(oracle) >= 0.1 * math.fsum(abs(cf) for cf in cash) and any(cash))  # the spec's generator condition
    result = check_schedule(units, arcs, periods, config, reported_npv_usd=oracle)
    assert result.ok, result.violations
    assert result.npv_usd == pytest.approx(oracle, rel=1e-12)
    assert result.cash_flows == pytest.approx(cash, rel=1e-12, abs=1e-9)


@pytest.mark.req("P-017-07")
@settings(max_examples=200, deadline=None)
@given(instance=feasible_schedules(), bump=st.floats(1e-3, 10.0))
def test_a_perturbed_reported_npv_is_always_caught(instance, bump):
    units, arcs, periods, config = instance
    cash = [math.fsum(units[u]["value_cents"] / 100.0 for u in p["units"]) for p in periods]
    oracle = math.fsum(cf / (1.0 + config["discount_rate"]) ** (t + 1) for t, cf in enumerate(cash))
    assume(abs(oracle) + bump > 1e-6)
    result = check_schedule(units, arcs, periods, config, reported_npv_usd=oracle + bump)
    assert not result.ok
    assert any("npv" in v for v in result.violations)


@pytest.mark.req("SC-017-04")
@settings(max_examples=200, deadline=None)
@given(instance=feasible_schedules(), pick=st.integers(0, 10**6))
def test_remining_a_mined_unit_in_a_later_period_is_always_caught(instance, pick):
    units, arcs, periods, config = instance
    mined = [(p["t"], u) for p in periods for u in p["units"]]
    assume(mined and len(periods) > 1)
    t, u = mined[pick % len(mined)]
    later = [p for p in periods if p["t"] != t]
    target = later[pick % len(later)]
    broken = [{"t": p["t"], "units": [*p["units"], u] if p is target else list(p["units"])} for p in periods]
    result = check_schedule(units, arcs, broken, config)
    assert not result.ok
    assert any("twice" in v for v in result.violations)

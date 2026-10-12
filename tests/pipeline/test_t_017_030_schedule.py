"""T-017-030: bench-phase units, HiGHS formulation, solver status, hostile configurations (pipeline).

Requirements: FR-017-18, FR-017-28.

Spec: specs/017-planning-survey/spec.md
- FR-017-18: the scheduler (`pipeline/`, HiGHS) solves the time-indexed program of the planning theory page on
  bench-phase units (blocks grouped by pushback and bench; a unit requires the unit above it in the same pushback
  and the
  same bench in the previous pushback) with binary x_{u,t}, mining capacity M_t, processing capacity P_t and discount
  delta per period, with `mip_rel_gap` <= 1e-4 and a recorded time limit, and writes the schedule, its NPV, its gap
  and
  its solver status (DC-017-03);
- FR-017-28: a shell or schedule configuration with an empty, non-increasing or outside-(0, 2] revenue-factor grid,
  T_min <= 0, a period count outside [1, 50], a capacity <= 0, delta outside [0, 1), or more than 2 x 10^5 binary
  variables is rejected before solving.
plan.md test strategy row FR-017-18: the planning page's formulation written independently in the test as a dense
matrix
for a 4-unit instance; solver status values. Edge case of spec section 7: a capacity too small to mine any unit
gives a
valid empty schedule with NPV 0.

Oracles:
- the spec's four-block example `contracts/examples/pit-shells.valid.json` (units, schedule, config): the ore block
  0 sits
  at bench 0 (level 0) under the three waste blocks at bench 1; the units are listed top bench first (unit 0 =
  bench 1,
  waste 3,000 t, -300 cents; unit 1 = bench 0, ore 1,000 t); with mining capacity 3,000 t, processing capacity 1,000 t
  and delta = 0.1 the optimum is unit 0 in period 1 and unit 1 in period 2: NPV = -3 / 1.1 + 5 / 1.21 = 1.404959 USD;
- the dense matrix formulation written out in the test for a 4-unit, 3-period instance and solved with
  `scipy.optimize.milp` (reference implementation; HiGHS inside SciPy): variables x[u, t], rows: each unit at most
  once;
  x[u, t] - sum_{tau <= t} x[v, tau] <= 0 for every arc "u requires v"; mining and processing capacity per period;
  objective max sum_t sum_u cf_u x[u, t] / (1 + delta)^(t + 1) (periods t = 1, 2, ...);
- the bounds of FR-017-28 by hand (50 periods ok, 51 not; 10,000 units x 20 periods = 200,000 binaries ok, x 21 not).

Expected public API (module `pitstudio_pipeline.planning.schedule`, `pipeline/` environment):
    class PlanConfigError(ValueError)        # `.reason`; the message names the offending key
    validate_plan_config(config: Mapping, *, n_units: int | None = None) -> None
        config keys as the DC-017-03 `config`: lambdas, t_min_t, periods, mining_capacity_t, processing_capacity_t,
        discount_rate, time_limit_s, mip_rel_gap. Raises PlanConfigError naming `lambdas`, `t_min_t`, `periods`,
        `mining_capacity_t`, `processing_capacity_t`, `discount_rate`, `time_limit_s`, `mip_rel_gap` (> 1e-4) or
        `binaries` (n_units x periods > 200,000).
    build_units(pushback, level, tonnage, is_ore, value_cents) -> UnitSet
        per-block arrays (pushback index, -1 for a block outside the pit; level = bench); UnitSet.units: list of
        {"id", "pushback", "bench", "ore_t", "waste_t", "value_cents"} ordered by pushback, then bench from the top
        (highest level first); UnitSet.arcs: list of (u, v) pairs "u requires v": the unit above in the same pushback
        and the same bench in the previous pushback.
    solve_schedule(units: UnitSet, config: Mapping, *, solver=None) -> Schedule
        validates the config first (nothing is solved for a bad one); `solver` optionally replaces the MILP backend
        (a callable the function must not call for a rejected configuration). Schedule: status ("optimal" |
        "time-limit" | "infeasible" | "unbounded" | "error"), npv_usd (float | None), gap (float | None), binaries
        (units x periods), time_limit_s (the configured limit), solver {"name", "version"} (name "highs" or
        "scipy-milp"), periods: [{"t", "units": [ids], "mined_t", "ore_t", "cash_flow_usd", "strip_ratio"}] for t =
        1 ..
        periods (empty unit lists for idle periods); an optimal status has gap <= 1e-4.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.planning.schedule import PlanConfigError, build_units, solve_schedule, validate_plan_config

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads((ROOT / "specs/017-planning-survey/contracts/examples/pit-shells.valid.json").read_text("utf-8"))


def _config(**over) -> dict:
    cfg = {
        "lambdas": [0.5, 1.0],
        "t_min_t": 1000.0,
        "periods": 2,
        "mining_capacity_t": [3000.0, 3000.0],
        "processing_capacity_t": [1000.0, 1000.0],
        "discount_rate": 0.1,
        "time_limit_s": 600.0,
        "mip_rel_gap": 1e-4,
    }
    cfg.update(over)
    return cfg


def _four_block_units():
    pushback = np.array([0, 0, 0, 0])
    level = np.array([0, 1, 1, 1])
    tonnage = np.full(4, 1000.0)
    is_ore = np.array([True, False, False, False])
    value_cents = np.array([500, -100, -100, -100])
    return build_units(pushback, level, tonnage, is_ore, value_cents)


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-18: units
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-18")
def test_the_four_block_example_groups_into_the_two_spec_units() -> None:
    units = _four_block_units()
    assert units.units == EXAMPLE["units"]
    assert units.arcs == [(1, 0)]  # the bench-0 unit requires the bench-1 unit above it


@pytest.mark.req("FR-017-18")
def test_a_unit_requires_the_unit_above_in_its_pushback_and_the_same_bench_of_the_previous_pushback() -> None:
    # two pushbacks x two benches; blocks listed as (pushback, level)
    spec = [(0, 1), (0, 0), (1, 1), (1, 0)]
    units = build_units(
        np.array([p for p, _ in spec]),
        np.array([b for _, b in spec]),
        np.full(4, 100.0),
        np.array([False, True, False, True]),
        np.array([-10, 50, -10, 50]),
    )
    ids = {(u["pushback"], u["bench"]): u["id"] for u in units.units}
    assert [u["id"] for u in units.units] == [0, 1, 2, 3]
    assert [(u["pushback"], u["bench"]) for u in units.units] == [(0, 1), (0, 0), (1, 1), (1, 0)]  # top bench first
    expected = {
        (ids[(0, 0)], ids[(0, 1)]),  # same pushback: bench 0 requires the bench above
        (ids[(1, 0)], ids[(1, 1)]),
        (ids[(1, 1)], ids[(0, 1)]),  # next pushback: same bench of the previous pushback
        (ids[(1, 0)], ids[(0, 0)]),
    }
    assert set(units.arcs) == expected


@pytest.mark.req("FR-017-18")
def test_blocks_outside_the_pit_form_no_unit_and_tonnage_splits_by_destination() -> None:
    units = build_units(
        np.array([0, 0, -1, 0]),
        np.array([0, 0, 0, 0]),
        np.array([100.0, 200.0, 999.0, 300.0]),
        np.array([True, False, True, True]),
        np.array([40, -10, 77, 60]),
    )
    (unit,) = units.units
    assert (unit["ore_t"], unit["waste_t"], unit["value_cents"]) == (400.0, 200.0, 90)  # the outside block is ignored
    assert units.arcs == []


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-18: the MILP
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-18")
def test_the_four_block_example_schedule_is_the_spec_schedule() -> None:
    schedule = solve_schedule(_four_block_units(), _config())
    expected = EXAMPLE["schedule"]
    assert schedule.status == "optimal"
    assert schedule.npv_usd == pytest.approx(expected["npv_usd"], abs=1e-6)  # -3 / 1.1 + 5 / 1.21 = 1.404959
    assert schedule.npv_usd == pytest.approx(-3 / 1.1 + 5 / 1.21, rel=1e-9)
    assert schedule.binaries == expected["binaries"] == 4
    assert schedule.gap <= 1e-4
    assert schedule.time_limit_s == 600.0
    assert schedule.solver["name"] in {"highs", "scipy-milp"}
    assert schedule.solver["version"]
    assert schedule.periods == expected["periods"]


def _dense_reference(units: list[dict], arcs: list[tuple[int, int]], periods: int, mining, processing, rate):
    """The time-indexed program as a dense matrix, solved with scipy.optimize.milp."""
    from scipy.optimize import Bounds, LinearConstraint, milp

    n = len(units)
    var = lambda u, t: u * periods + t  # noqa: E731
    rows, lo, hi = [], [], []
    for u in range(n):  # each unit at most once
        row = np.zeros(n * periods)
        row[[var(u, t) for t in range(periods)]] = 1
        rows.append(row), lo.append(0), hi.append(1)
    for u, v in arcs:  # x[u, t] - sum_{tau <= t} x[v, tau] <= 0
        for t in range(periods):
            row = np.zeros(n * periods)
            row[var(u, t)] = 1
            for tau in range(t + 1):
                row[var(v, tau)] -= 1
            rows.append(row), lo.append(-np.inf), hi.append(0)
    for t in range(periods):
        mine, ore = np.zeros(n * periods), np.zeros(n * periods)
        for u, unit in enumerate(units):
            mine[var(u, t)] = unit["ore_t"] + unit["waste_t"]
            ore[var(u, t)] = unit["ore_t"]
        rows.append(mine), lo.append(-np.inf), hi.append(mining[t])
        rows.append(ore), lo.append(-np.inf), hi.append(processing[t])
    c = np.zeros(n * periods)
    for u, unit in enumerate(units):
        for t in range(periods):
            c[var(u, t)] = -(unit["value_cents"] / 100.0) / (1 + rate) ** (t + 1)
    res = milp(
        c, constraints=LinearConstraint(np.array(rows), lo, hi), integrality=np.ones(n * periods), bounds=Bounds(0, 1)
    )
    assert res.status == 0
    return -res.fun


@pytest.mark.req("FR-017-18")
def test_the_npv_equals_the_dense_matrix_formulation_of_a_4_unit_instance() -> None:
    units = [
        {"id": 0, "pushback": 0, "bench": 3, "ore_t": 0.0, "waste_t": 1000.0, "value_cents": -500},
        {"id": 1, "pushback": 0, "bench": 2, "ore_t": 500.0, "waste_t": 500.0, "value_cents": 2000},
        {"id": 2, "pushback": 0, "bench": 1, "ore_t": 800.0, "waste_t": 0.0, "value_cents": 1800},
        {"id": 3, "pushback": 0, "bench": 0, "ore_t": 0.0, "waste_t": 800.0, "value_cents": -400},
    ]
    arcs = [(1, 0), (2, 1), (3, 2)]
    from types import SimpleNamespace

    unit_set = SimpleNamespace(units=units, arcs=arcs)
    config = _config(periods=3, mining_capacity_t=[1000.0] * 3, processing_capacity_t=[600.0] * 3, discount_rate=0.05)
    schedule = solve_schedule(unit_set, config)
    reference = _dense_reference(units, arcs, 3, [1000.0] * 3, [600.0] * 3, 0.05)
    assert schedule.status == "optimal"
    assert schedule.npv_usd == pytest.approx(
        reference, rel=1e-3, abs=1e-6
    )  # within the 1e-4 relative MIP gap, with margin
    assert schedule.binaries == 12
    # the schedule it returns mines every unit at most once
    mined = [u for p in schedule.periods for u in p["units"]]
    assert len(mined) == len(set(mined))


@pytest.mark.req("FR-017-18")
def test_a_capacity_too_small_to_mine_any_unit_gives_a_valid_empty_schedule_with_npv_zero() -> None:
    schedule = solve_schedule(
        _four_block_units(), _config(mining_capacity_t=[1.0, 1.0], processing_capacity_t=[1.0, 1.0])
    )
    assert schedule.status == "optimal"
    assert schedule.npv_usd == 0.0
    assert all(p["units"] == [] for p in schedule.periods)
    assert [p["t"] for p in schedule.periods] == [1, 2]


@pytest.mark.req("FR-017-18")
def test_an_unprofitable_instance_is_not_mined() -> None:
    units = build_units(np.array([0]), np.array([0]), np.array([1000.0]), np.array([False]), np.array([-500]))
    schedule = solve_schedule(units, _config(periods=1, mining_capacity_t=[5000.0], processing_capacity_t=[1000.0]))
    assert schedule.npv_usd == 0.0
    assert schedule.periods[0]["units"] == []


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-28: hostile configurations
# ----------------------------------------------------------------------------------------------------------------------


class _NeverCalled:
    def __call__(self, *args, **kwargs):
        raise AssertionError("the MILP backend must not be called for a rejected configuration")


HOSTILE = [
    ({"lambdas": []}, "lambdas"),
    ({"lambdas": [0.5, 0.5]}, "lambdas"),
    ({"lambdas": [1.0, 0.5]}, "lambdas"),
    ({"lambdas": [0.0, 1.0]}, "lambdas"),
    ({"lambdas": [0.5, 2.0001]}, "lambdas"),
    ({"lambdas": [-0.5, 1.0]}, "lambdas"),
    ({"lambdas": [0.5, float("nan")]}, "lambdas"),
    ({"t_min_t": 0.0}, "t_min_t"),
    ({"t_min_t": -1.0}, "t_min_t"),
    ({"periods": 0, "mining_capacity_t": [], "processing_capacity_t": []}, "periods"),
    ({"mining_capacity_t": [3000.0, 0.0]}, "mining_capacity_t"),
    ({"mining_capacity_t": [3000.0, -1.0]}, "mining_capacity_t"),
    ({"processing_capacity_t": [0.0, 1000.0]}, "processing_capacity_t"),
    ({"processing_capacity_t": [1000.0, float("inf")]}, "processing_capacity_t"),
    ({"mining_capacity_t": [3000.0]}, "mining_capacity_t"),
    ({"discount_rate": -0.01}, "discount_rate"),
    ({"discount_rate": 1.0}, "discount_rate"),
    ({"discount_rate": float("nan")}, "discount_rate"),
    ({"time_limit_s": 0.0}, "time_limit_s"),
    ({"time_limit_s": -5.0}, "time_limit_s"),
    ({"mip_rel_gap": 1e-3}, "mip_rel_gap"),
]


@pytest.mark.req("FR-017-28")
@pytest.mark.parametrize(("over", "key"), HOSTILE, ids=[f"{k}-{i}" for i, (_, k) in enumerate(HOSTILE)])
def test_hostile_configurations_are_rejected_before_solving_naming_the_key(over: dict, key: str) -> None:
    with pytest.raises(PlanConfigError, match=key):
        validate_plan_config(_config(**over))
    with pytest.raises(PlanConfigError, match=key):
        solve_schedule(_four_block_units(), _config(**over), solver=_NeverCalled())


@pytest.mark.req("FR-017-28")
@pytest.mark.parametrize(("periods", "ok"), [(1, True), (50, True), (51, False), (0, False), (-3, False)])
def test_the_period_count_must_be_between_1_and_50(periods: int, ok: bool) -> None:
    cfg = _config(
        periods=periods, mining_capacity_t=[3000.0] * max(periods, 0), processing_capacity_t=[1000.0] * max(periods, 0)
    )
    if ok:
        assert validate_plan_config(cfg) is None
    else:
        with pytest.raises(PlanConfigError, match="periods"):
            validate_plan_config(cfg)


@pytest.mark.req("FR-017-28")
@pytest.mark.parametrize(
    ("n_units", "periods", "ok"), [(10_000, 20, True), (10_000, 21, False), (200_001, 1, False), (200_000, 1, True)]
)
def test_more_than_200000_binary_variables_are_rejected(n_units: int, periods: int, ok: bool) -> None:
    cfg = _config(periods=periods, mining_capacity_t=[3000.0] * periods, processing_capacity_t=[1000.0] * periods)
    if ok:
        assert validate_plan_config(cfg, n_units=n_units) is None
    else:
        with pytest.raises(PlanConfigError, match="binaries"):
            validate_plan_config(cfg, n_units=n_units)


@pytest.mark.req("FR-017-28")
def test_boundary_values_are_accepted() -> None:
    assert validate_plan_config(_config(lambdas=[0.025, 2.0], discount_rate=0.0, mip_rel_gap=0.0)) is None
    assert validate_plan_config(_config(discount_rate=0.999999)) is None

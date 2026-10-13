# ruff: noqa: E501, PT018
"""T-007-022 (Python half): unsupported features, invalid seeds and horizons, and the event budget in the Python adapter: typed errors within 2 s and no partial KPIs.

Requirements: FR-007-12, FR-007-13.

Spec: specs/007-haulage-dispatch/spec.md FR-007-12 (a scenario that uses a reference-engine feature outside the twin's declared feature set is refused by the twin with
`UnsupportedFeature` naming the feature, and the web falls back to the baked trace with that reason; the features outside the set are underground units (LHDs), ore passes, shaft bins, a planning
overlay and a routing zone penalty other than 0) and FR-007-13 (a seed that is not an integer in [0, 2^63), a horizon <= 0 s or > 7 days, or a run past 2 x 10^6 executed events stops within 2 s with
`InvalidSeed`, `InvalidHorizon` or `EventBudgetExceeded` and returns no partial KPIs); section 8 (e) (the horizon range (0, 604,800] s is in the schema and a violation at `/horizon_s` is
reported as `InvalidHorizon`); `contracts/haul-scenario.schema.json` (`reference_only`: lhds, ore_passes, shaft_bin, planning_overlay, zone_penalty_s). The TypeScript twin half is
web/src/engines/des/twin.hostile.test.ts.

Oracle: hand-built hostile seeds and horizons (the boundaries 0, 2^63 - 1, 2^63 and 604,800 written out); a stopwatch (`time.perf_counter`); the reference-only feature names of the contract;
the adapter must neither return nor write anything when it refuses.

Expected API (module `pitstudio_pipeline.haulage.scenario`; adapter as in test_t_007_013; errors in `pitstudio_pipeline.haulage.errors`):
    errors.UnsupportedFeature(HaulError)   attribute `features: list[str]`; message names every feature
    errors.InvalidSeed, errors.InvalidHorizon, errors.EventBudgetExceeded (HaulError subclasses)
    unsupported_features(bundle: dict) -> list[str]     the twin-unsupported features the bundle uses, in the order lhds, ore_passes, shaft_bin, planning_overlay, zone_penalty_s;
        `reference_only` absent or empty: []; `zone_penalty_s` counts only when != 0; an empty `lhds` or `ore_passes` list counts as unused
    check_twin_features(bundle: dict) -> None          raises UnsupportedFeature(features) when `unsupported_features` is not empty
    adapter.run_shift(..., event_budget=2_000_000): raises EventBudgetExceeded as soon as more than `event_budget` events have executed; `event_budget` must be a positive int (ValueError otherwise);
        the seed is checked first (InvalidSeed: bool, non-int, negative, >= 2^63); nothing is written to `trace_path` when any of these is raised.
    adapter.DEFAULT_EVENT_BUDGET == 2_000_000
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_busy as busy
import p007_kit as kit
from pitstudio_pipeline.haulage import adapter
from pitstudio_pipeline.haulage.adapter import run_shift
from pitstudio_pipeline.haulage.errors import EventBudgetExceeded, InvalidHorizon, InvalidSeed, UnsupportedFeature
from pitstudio_pipeline.haulage.scenario import check_twin_features, unsupported_features, validate_bundle

SMOKE = kit.example_path("haul-scenario.valid.json")


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-12: the twin's declared feature set
# ---------------------------------------------------------------------------------------------------------------------
LHD = {"id": 1, "lhd_class": "LHD_14", "drawpoints": [1], "tip_node": 3, "pass_id": 1}
PASS = {"id": 1, "chute_node": 3, "capacity_t": 500.0}
BIN = {"node": 4, "capacity_t": 800.0, "hoist_t_per_h": 600.0}
OVERLAY = {"path": "plans/pit-plan.json", "sha256": "a" * 64}


@pytest.mark.req("FR-007-12")
@pytest.mark.parametrize(
    ("reference_only", "expected"),
    [
        (None, []),
        ({"zone_penalty_s": 0}, []),
        ({"zone_penalty_s": 0.0}, []),
        ({"lhds": [], "ore_passes": []}, []),
        ({"lhds": [LHD]}, ["lhds"]),
        ({"ore_passes": [PASS]}, ["ore_passes"]),
        ({"shaft_bin": BIN}, ["shaft_bin"]),
        ({"planning_overlay": OVERLAY}, ["planning_overlay"]),
        ({"zone_penalty_s": 5.0}, ["zone_penalty_s"]),
        ({"zone_penalty_s": 0.001}, ["zone_penalty_s"]),
        (
            {"zone_penalty_s": 30, "lhds": [LHD], "shaft_bin": BIN, "ore_passes": [PASS], "planning_overlay": OVERLAY},
            ["lhds", "ore_passes", "shaft_bin", "planning_overlay", "zone_penalty_s"],
        ),
    ],
)
def test_unsupported_features_are_named_in_the_documented_order(reference_only, expected):
    b = kit.smoke_bundle()
    if reference_only is not None:
        b["reference_only"] = reference_only
    assert unsupported_features(b) == expected
    if expected:
        with pytest.raises(UnsupportedFeature) as ei:
            check_twin_features(b)
        assert ei.value.features == expected and all(f in str(ei.value) for f in expected)
    else:
        check_twin_features(b)


@pytest.mark.req("FR-007-12")
def test_the_valid_examples_use_no_unsupported_feature():
    for name in (
        "haul-scenario.valid.json",
        "haul-scenario.valid-exponential.json",
        "haul-scenario.valid-traffic-lp.json",
    ):
        assert unsupported_features(kit.example(name)) == []


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-13: seeds
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-13")
@pytest.mark.parametrize(
    "seed", [-1, 2**63, 2**63 + 1, 2**100, 1.5, 3.0, float("nan"), float("inf"), "7", None, True, False, [1], b"1"]
)
def test_a_seed_outside_the_integers_below_2_to_the_63_is_invalid_seed_within_two_seconds(tmp_path, seed):
    out = tmp_path / "trace.json"
    t0 = time.perf_counter()
    with pytest.raises(InvalidSeed):
        run_shift(SMOKE, seed=seed, trace_path=out)
    assert time.perf_counter() - t0 < 2.0
    assert not out.exists()


@pytest.mark.req("FR-007-13")
@pytest.mark.parametrize("seed", [0, 1, 2**63 - 1])
def test_the_boundary_seeds_are_accepted(seed):
    assert run_shift(SMOKE, seed=seed).events_executed == 8


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-13: horizons
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-13")
@pytest.mark.parametrize("horizon", [0.0, 0, -1.0, -3600.0, 604800.001, 1e9, float("nan"), float("inf"), "900", None])
def test_a_horizon_outside_zero_to_seven_days_is_invalid_horizon_within_two_seconds(tmp_path, horizon):
    b = kit.smoke_bundle()
    b["horizon_s"] = horizon
    path = kit.write_bundle(tmp_path, b)
    out = tmp_path / "trace.json"
    t0 = time.perf_counter()
    with pytest.raises(InvalidHorizon):
        run_shift(path, seed=1, trace_path=out)
    assert time.perf_counter() - t0 < 2.0
    assert not out.exists()


@pytest.mark.req("FR-007-13")
@pytest.mark.parametrize("horizon", [0.001, 1.0, 604800.0])
def test_the_boundary_horizons_pass_validation(horizon):
    b = kit.smoke_bundle()
    b["horizon_s"] = horizon
    validate_bundle(b)


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-13: the event budget
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-13")
def test_the_default_event_budget_is_two_million():
    assert adapter.DEFAULT_EVENT_BUDGET == 2_000_000


@pytest.mark.req("FR-007-13")
@pytest.mark.parametrize("budget", [1, 8, 500, 5000])
def test_a_run_past_the_budget_stops_with_event_budget_exceeded_within_two_seconds_and_no_partial_kpis(
    tmp_path, budget
):
    b = busy.busy_bundle(
        "sptf", "traffic", n_trucks=8, horizon=7 * 24 * 3600.0, profile="engine"
    )  # a week of traffic: far more than any budget here
    path = kit.write_bundle(tmp_path, b)
    out = tmp_path / "trace.json"
    result = None
    t0 = time.perf_counter()
    with pytest.raises(EventBudgetExceeded):
        result = run_shift(path, seed=1, trace_path=out, event_budget=budget)
    assert time.perf_counter() - t0 < 2.0
    assert result is None and not out.exists()


@pytest.mark.req("FR-007-13")
def test_a_run_exactly_at_the_budget_completes():
    n = run_shift(SMOKE, seed=1).events_executed
    assert (
        run_shift(SMOKE, seed=1, event_budget=n).events_executed == n
    )  # `more than` the budget stops the run, not `as many as`
    with pytest.raises(EventBudgetExceeded):
        run_shift(SMOKE, seed=1, event_budget=n - 1)


@pytest.mark.req("FR-007-13")
@pytest.mark.parametrize("budget", [0, -1, 1.5, True, None, "100"])
def test_an_invalid_event_budget_is_a_value_error(budget):
    with pytest.raises(ValueError):  # noqa: PT011
        run_shift(SMOKE, seed=1, event_budget=budget)

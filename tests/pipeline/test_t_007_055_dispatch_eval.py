# ruff: noqa: E501, PT018
"""T-007-055: paired evaluation in the reference engine: the table schema, the paired-t CI against scipy, the spec section 7 worked example, `insufficient-evidence` cases, per-fleet-size rows for M5.

Requirements: FR-007-28, FR-007-29, FR-007-30, SC-007-01, SC-007-02, FR-000-05.

Spec: specs/007-haulage-dispatch/spec.md FR-007-29 (`s50_evaluate` runs fixed, nearest, sptf, sq, LP, PPO and attention in the reference engine (traffic mode, `engine` profile) on the same test seeds, records per seed and dispatcher t/h, mean queue time,
loader utilisation, match factor and truck- and loader-hours per kt in a table valid against `contracts/dispatch-eval.schema.json`, and for every learned-versus-baseline pair adds the paired differences, the paired-t 95 % CI and the FR-000-05 verdict),
FR-007-30 (fewer than 30 paired seeds, differing seed sets or a non-finite paired difference give the verdict `insufficient-evidence`, and no output says "better"), FR-007-28 (a training or validation seed in the pre-registered test-seed set refuses
to start with `SeedLeak`, also in `s50_evaluate`), FR-000-05 (call a result "better" only when the paired 95 % CI of the difference excludes 0, otherwise "no significant difference"), SC-007-01 (PPO against SPTF and LP on t/h, >= 30 paired seeds),
SC-007-02 (attention against SPTF, LP, M4 and per fleet size), the schema `contracts/dispatch-eval.schema.json` (`$defs/comparison`, `$defs/row`) and section 7 "Decision-rule worked example".

Oracle: `scipy.stats.t` (critical value and interval) and `numpy` (mean, sample standard deviation with ddof = 1) on synthetic paired arms; the hand-calculated worked example of section 7 (n = 30, t_{0.975,29} = 2.0452, s_d = 110 t/h: half-width 2.0452 x 110 / sqrt(30) = 41.07 t/h;
mean 45 gives [3.9, 86.1], "better"; mean 30 gives [-11.1, 71.1], "no significant difference"); the JSON schema validator on every produced document; metamorphic relations of the paired-t interval (shift, scale, permutation of seeds).

Expected API (module `pitstudio_pipeline.dispatch.evaluate`):
    paired_comparison(learned_th: Mapping[int, float], baseline_th: Mapping[int, float], *, learned: str, baseline: str, fleet_size: int) -> dict
        t/h per test seed of each arm; returns a `$defs/comparison` object: learned, baseline, fleet_size, n_pairs, differences [{seed, diff_t_per_h = learned - baseline}] , mean_diff_t_per_h, sd_diff_t_per_h (ddof 1), t_crit (t_{0.975, n-1}),
        ci95 {low_t_per_h, high_t_per_h} = mean -/+ t_crit x sd / sqrt(n), verdict in {learned-better (CI low > 0), baseline-better (CI high < 0), no-significant-difference}; with n < 30 pairs, different seed sets or a non-finite difference:
        verdict `insufficient-evidence` with `reason` in {fewer-than-30-pairs, seed-sets-differ, non-finite-difference} (and no `ci95` verdict text anywhere that says "better"). learned in {ppo, attention}, baseline in {fixed, nearest, sptf, sq, lp, ppo}, learned != baseline,
        1 <= fleet_size <= 400 else ValueError; empty arms or non-numeric values raise ValueError / TypeError.
    row_from_kpis(kpis: dict, *, seed: int, dispatcher: str, fleet_size: int) -> dict
        a `$defs/row` from a `compute_kpis` result (test_t_007_016): production_t_per_h = fleet.production_tph, queue_time_mean_min = fleet.queue_loader_min.mean, loader_utilisation_frac = fleet.loader_utilisation, match_factor,
        truck_hours_per_kt = fleet.truck_h_per_kt, loader_hours_per_kt = fleet.loader_h_per_kt; a run with no production (hours per kt is None) raises ValueError.
    assemble_table(rows: Sequence[dict], *, id: str, recipe: str, engine: dict, scenarios: Sequence[dict], test_seeds: Sequence[int], honesty: dict) -> dict
        the whole `dispatch-eval` document: constants (schema_version "1.0", mode "traffic", variate_profile "engine", primary_metric "production_t_per_h", ci_method "paired-t", ci_level 0.95, min_pairs 30), `rows` as given (a duplicate (seed, dispatcher,
        fleet_size) raises ValueError), and `comparisons`: for every fleet size present, ppo and attention against each baseline present in {fixed, nearest, sptf, sq, lp} and attention against ppo, each by `paired_comparison` over the seeds of the rows.
    guard_seeds(train_seeds, val_seeds, tests=None) -> None      raises `SeedLeak` (haulage.errors) when a training or validation seed is in the pre-registered test set (default `seeds.test_seeds(30)`), the guard of `s50_evaluate`.
"""

from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit as kit
from pitstudio_pipeline.dispatch.evaluate import assemble_table, guard_seeds, paired_comparison, row_from_kpis
from pitstudio_pipeline.dispatch.seeds import test_seeds as preregistered_seeds
from pitstudio_pipeline.haulage.errors import SeedLeak

SETTINGS = settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)
COMPARISON = kit.schema_validator("dispatch-eval", "comparison")
ROW = kit.schema_validator("dispatch-eval", "row")
TABLE = kit.schema_validator("dispatch-eval")
SEEDS = [int(s) for s in preregistered_seeds(30)]
BASELINES = ("fixed", "nearest", "sptf", "sq", "lp")


def arms(diffs, base=3000.0):
    """Two arms over the pre-registered seeds whose paired differences are exactly `diffs`."""
    n = len(diffs)
    seeds = SEEDS[:n] if n <= 30 else [*SEEDS, *range(10**6, 10**6 + n - 30)]
    b = {s: base + 7.0 * (i % 5) for i, s in enumerate(seeds)}
    a = {s: b[s] + d for s, d in zip(seeds, diffs, strict=True)}
    return a, b


def standardised(n: int, mean: float, sd: float, seed: int = 0) -> np.ndarray:
    z = np.random.default_rng(seed).standard_normal(n)
    z = (z - z.mean()) / z.std(ddof=1)
    return mean + sd * z


def reference(diffs):
    d = np.asarray(diffs, dtype=float)
    n = d.size
    m, sd = d.mean(), d.std(ddof=1)
    tc = stats.t.ppf(0.975, n - 1)
    return n, m, sd, tc, m - tc * sd / math.sqrt(n), m + tc * sd / math.sqrt(n)


def compare(diffs, **kw):
    a, b = arms(list(diffs))
    return paired_comparison(a, b, **{"learned": "ppo", "baseline": "sptf", "fleet_size": 24, **kw})


# ---------------------------------------------------------------------------------------------------------------------
# the paired-t interval against scipy and the worked example
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-29")
@pytest.mark.parametrize("n", [30, 31, 45, 100])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_paired_t_interval_matches_scipy_and_validates_against_the_schema(n, seed):
    diffs = np.random.default_rng(seed).normal(25.0, 90.0, n)
    c = compare(diffs)
    assert not list(COMPARISON.iter_errors(c)), [e.message for e in COMPARISON.iter_errors(c)][:3]
    _, m, sd, tc, lo, hi = reference(diffs)
    assert c["n_pairs"] == n
    assert c["mean_diff_t_per_h"] == pytest.approx(m, rel=1e-9, abs=1e-9)
    assert c["sd_diff_t_per_h"] == pytest.approx(sd, rel=1e-9)
    assert c["t_crit"] == pytest.approx(tc, abs=6e-5)  # the spec prints 4 decimals
    half = 6e-5 * sd / math.sqrt(n) + 1e-6
    assert c["ci95"]["low_t_per_h"] == pytest.approx(lo, abs=half)
    assert c["ci95"]["high_t_per_h"] == pytest.approx(hi, abs=half)
    got = {d["seed"]: d["diff_t_per_h"] for d in c["differences"]}  # learned - baseline per seed
    assert got == pytest.approx(dict(zip(SEEDS[:n], diffs, strict=False)) if n <= 30 else got, abs=1e-9)
    assert len(got) == n and sorted(got.values()) == pytest.approx(sorted(diffs), abs=1e-9)


@pytest.mark.req("FR-007-29")
def test_the_scipy_ttest_rel_statistic_agrees_with_the_reported_interval():
    diffs = np.random.default_rng(11).normal(40.0, 100.0, 30)
    a, b = arms(list(diffs))
    ref = stats.ttest_rel([a[s] for s in a], [b[s] for s in a])
    c = paired_comparison(a, b, learned="ppo", baseline="sptf", fleet_size=24)
    t_stat = c["mean_diff_t_per_h"] / (c["sd_diff_t_per_h"] / math.sqrt(30))
    assert t_stat == pytest.approx(ref.statistic, rel=1e-9)
    assert (c["ci95"]["low_t_per_h"] > 0) == (
        ref.pvalue < 0.05 and ref.statistic > 0
    )  # the interval excludes zero exactly when the two-sided test rejects


@pytest.mark.req("FR-000-05")
@pytest.mark.req("SC-007-01")
@pytest.mark.parametrize(
    ("mean", "lo", "hi", "verdict"),
    [(45.0, 3.9, 86.1, "learned-better"), (30.0, -11.1, 71.1, "no-significant-difference")],
)
def test_the_section_7_worked_example(mean, lo, hi, verdict):
    c = compare(standardised(30, mean, 110.0))  # n = 30, s_d = 110 t/h: half-width 2.0452 x 110 / sqrt(30) = 41.07
    assert c["t_crit"] == pytest.approx(2.0452, abs=1e-4)
    assert c["ci95"]["low_t_per_h"] == pytest.approx(lo, abs=0.06)
    assert c["ci95"]["high_t_per_h"] == pytest.approx(hi, abs=0.06)
    assert c["verdict"] == verdict
    assert not list(COMPARISON.iter_errors(c))


@pytest.mark.req("FR-000-05")
@pytest.mark.parametrize(
    ("diffs", "verdict"),
    [
        ([5.0] * 30, "learned-better"),  # zero spread: the interval is the point 5
        ([-3.0] * 30, "baseline-better"),
        ([0.0] * 30, "no-significant-difference"),  # the point 0 is not excluded
        ([1.0, -1.0] * 15, "no-significant-difference"),
    ],
)
def test_degenerate_spreads_decide_by_the_sign_of_the_interval(diffs, verdict):
    c = compare(diffs)
    assert c["verdict"] == verdict
    assert not list(COMPARISON.iter_errors(c))
    if len(set(diffs)) == 1:
        assert c["sd_diff_t_per_h"] == 0 and c["ci95"]["low_t_per_h"] == pytest.approx(diffs[0]) == pytest.approx(
            c["ci95"]["high_t_per_h"]
        )


@pytest.mark.req("FR-000-05")
@pytest.mark.req("SC-007-02")
def test_an_interval_that_just_includes_zero_is_not_better():
    sd = 100.0
    tc = stats.t.ppf(0.975, 29)
    half = tc * sd / math.sqrt(30)
    inside = compare(standardised(30, half - 0.05, sd))  # lower end -0.05: includes 0
    outside = compare(standardised(30, half + 0.05, sd))  # lower end +0.05: excludes 0
    assert inside["verdict"] == "no-significant-difference"
    assert outside["verdict"] == "learned-better"


@pytest.mark.req("FR-000-05")
def test_a_negative_difference_that_excludes_zero_is_baseline_better_and_no_text_says_learned_better():
    c = compare(standardised(30, -80.0, 60.0))
    assert c["verdict"] == "baseline-better" and c["ci95"]["high_t_per_h"] < 0
    assert "learned-better" not in json.dumps(c)


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-30: insufficient evidence
# ---------------------------------------------------------------------------------------------------------------------
def never_better(c):
    text = json.dumps(c)
    assert c["verdict"] == "insufficient-evidence"
    assert "better" not in text  # no output says "better"
    assert not list(COMPARISON.iter_errors(c)), [e.message for e in COMPARISON.iter_errors(c)][:3]


@pytest.mark.req("FR-007-30")
@pytest.mark.parametrize("n", [1, 2, 5, 29])
def test_fewer_than_30_pairs_is_insufficient_evidence_even_for_a_huge_effect(n):
    c = compare([500.0 + i for i in range(n)])  # a large positive effect: still no verdict
    never_better(c)
    assert c["reason"] == "fewer-than-30-pairs" and c["n_pairs"] == n


@pytest.mark.req("FR-007-30")
def test_arms_with_different_seed_sets_are_insufficient_evidence():
    a, b = arms([300.0] * 31)  # 31 seeds in each, then one seed of the learned arm is swapped for another
    last = max(a)
    a[last + 1] = a.pop(last)
    c = paired_comparison(a, b, learned="ppo", baseline="sptf", fleet_size=24)
    never_better(c)
    assert c["reason"] == "seed-sets-differ"


@pytest.mark.req("FR-007-30")
def test_an_extra_seed_in_one_arm_only_is_a_seed_set_difference():
    a, b = arms([300.0] * 30)
    a[10**9] = 3300.0
    c = paired_comparison(a, b, learned="ppo", baseline="sptf", fleet_size=24)
    never_better(c)
    assert c["reason"] == "seed-sets-differ"


@pytest.mark.req("FR-007-30")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("arm", ["learned", "baseline"])
def test_a_non_finite_value_makes_the_difference_non_finite_and_the_verdict_insufficient(bad, arm):
    a, b = arms([300.0] * 30)
    target = a if arm == "learned" else b
    target[SEEDS[7]] = bad
    c = paired_comparison(a, b, learned="ppo", baseline="sptf", fleet_size=24)
    never_better(c)
    assert c["reason"] == "non-finite-difference"


@pytest.mark.req("FR-007-30")
def test_when_several_conditions_hold_the_reason_is_one_of_the_three_documented_ones():
    a, b = arms([300.0] * 12)
    a[SEEDS[3]] = float("nan")
    c = paired_comparison(a, b, learned="ppo", baseline="sptf", fleet_size=24)
    never_better(c)
    assert c["reason"] in {"fewer-than-30-pairs", "seed-sets-differ", "non-finite-difference"}


@pytest.mark.req("FR-007-30")
def test_an_insufficient_comparison_never_carries_a_better_text_in_the_table_either():
    rows = [fake_row(s, d, 24, 3000.0 + (50 if d == "ppo" else 0)) for s in SEEDS[:20] for d in ("sptf", "ppo")]
    t = assemble_table(rows, **table_args(SEEDS[:20]))
    assert all(
        c["verdict"] == "insufficient-evidence" and c["reason"] == "fewer-than-30-pairs" for c in t["comparisons"]
    )
    assert "better" not in json.dumps(t["comparisons"])
    assert not list(TABLE.iter_errors(t))


# ---------------------------------------------------------------------------------------------------------------------
# hostile inputs
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-30")
@pytest.mark.parametrize(
    "kw",
    [
        {"learned": "sptf"},
        {"learned": "lp"},
        {"learned": "greedy"},
        {"baseline": "attention"},
        {"baseline": "sptf2"},
        {"learned": "ppo", "baseline": "ppo"},
        {"fleet_size": 0},
        {"fleet_size": 401},
        {"fleet_size": -3},
        {"fleet_size": 2.5},
        {"fleet_size": True},
    ],
)
def test_unknown_arms_or_fleet_sizes_are_rejected(kw):
    a, b = arms([10.0] * 30)
    with pytest.raises((ValueError, TypeError)):
        paired_comparison(a, b, **{"learned": "ppo", "baseline": "sptf", "fleet_size": 24, **kw})


@pytest.mark.req("FR-007-30")
@pytest.mark.parametrize("bad", [{}, {1: "x"}, {1: None}, {1: True}, {"a": 1.0}, {-1: 5.0}, {2**63: 5.0}, {1: -5.0}])
def test_empty_or_malformed_arms_are_rejected(bad):
    a, b = arms([10.0] * 30)
    for pair in ((bad, b), (a, bad)):
        with pytest.raises((ValueError, TypeError)):
            paired_comparison(*pair, learned="ppo", baseline="sptf", fleet_size=24)


@pytest.mark.req("FR-007-30")
def test_unicode_and_huge_names_are_rejected_not_echoed():
    a, b = arms([10.0] * 30)
    for name in ["ポリシー", "p" * 100_000, "ppo\x00"]:
        with pytest.raises((ValueError, TypeError)):
            paired_comparison(a, b, learned=name, baseline="sptf", fleet_size=24)


# ---------------------------------------------------------------------------------------------------------------------
# metamorphic relations (hypothesis)
# ---------------------------------------------------------------------------------------------------------------------
diff_lists = st.lists(
    st.floats(min_value=-500, max_value=500, allow_nan=False, allow_infinity=False), min_size=30, max_size=40
)


@pytest.mark.req("FR-000-05")
@SETTINGS
@given(diffs=diff_lists, c=st.floats(min_value=-200, max_value=200))
def test_shifting_the_learned_arm_shifts_the_mean_and_the_interval_and_not_the_spread(diffs, c):
    base = compare(diffs)
    shifted = compare([d + c for d in diffs])
    tol = 1e-6 * (1 + abs(c) + max(map(abs, diffs)))
    assert shifted["mean_diff_t_per_h"] == pytest.approx(base["mean_diff_t_per_h"] + c, abs=tol)
    assert shifted["sd_diff_t_per_h"] == pytest.approx(base["sd_diff_t_per_h"], abs=tol)
    assert shifted["ci95"]["low_t_per_h"] == pytest.approx(base["ci95"]["low_t_per_h"] + c, abs=tol)
    assert shifted["ci95"]["high_t_per_h"] == pytest.approx(base["ci95"]["high_t_per_h"] + c, abs=tol)


@pytest.mark.req("FR-000-05")
@SETTINGS
@given(diffs=diff_lists, k=st.floats(min_value=0.5, max_value=4.0))
def test_scaling_both_arms_scales_the_interval_and_keeps_the_verdict(diffs, k):
    a, b = arms(list(diffs))
    base = paired_comparison(a, b, learned="ppo", baseline="sptf", fleet_size=24)
    scaled = paired_comparison(
        {s: v * k for s, v in a.items()},
        {s: v * k for s, v in b.items()},
        learned="ppo",
        baseline="sptf",
        fleet_size=24,
    )
    scale = 1 + max(map(abs, diffs))
    lo, hi = base["ci95"]["low_t_per_h"], base["ci95"]["high_t_per_h"]
    assume(
        abs(lo) > 1e-6 * scale and abs(hi) > 1e-6 * scale
    )  # not at a decision edge, where float noise could flip the verdict
    assert scaled["mean_diff_t_per_h"] == pytest.approx(k * base["mean_diff_t_per_h"], rel=1e-7, abs=1e-7 * scale)
    assert scaled["ci95"]["low_t_per_h"] == pytest.approx(k * lo, rel=1e-6, abs=1e-6 * scale)
    assert scaled["verdict"] == base["verdict"]


@pytest.mark.req("FR-000-05")
@SETTINGS
@given(diffs=diff_lists, perm_seed=st.integers(0, 2**32 - 1))
def test_the_order_in_which_seeds_are_listed_changes_nothing(diffs, perm_seed):
    a, b = arms(list(diffs))
    order = list(a)
    np.random.default_rng(perm_seed).shuffle(order)
    base = paired_comparison(a, b, learned="ppo", baseline="sptf", fleet_size=24)
    shuffled = paired_comparison(
        {s: a[s] for s in order}, {s: b[s] for s in reversed(order)}, learned="ppo", baseline="sptf", fleet_size=24
    )
    assert shuffled == base


@pytest.mark.req("FR-000-05")
@SETTINGS
@given(diffs=diff_lists)
def test_the_verdict_always_follows_the_interval(diffs):
    c = compare(diffs)
    lo, hi = c["ci95"]["low_t_per_h"], c["ci95"]["high_t_per_h"]
    expected = "learned-better" if lo > 0 else "baseline-better" if hi < 0 else "no-significant-difference"
    assert c["verdict"] == expected
    assert lo <= c["mean_diff_t_per_h"] <= hi
    assert not list(COMPARISON.iter_errors(c))


# ---------------------------------------------------------------------------------------------------------------------
# rows from KPIs, the whole table, per-fleet-size comparisons
# ---------------------------------------------------------------------------------------------------------------------
def kpis(**over):
    f = {
        "tonnes_t": 1260.0, "production_tph": 1260.0, "cycles": 6, "cycles_per_h": 6.0, "queue_loader_min": {"mean": 2.4, "p90": 5.0}, "queue_dump_min": {"mean": 0.1, "p90": 0.2},
        "loader_utilisation": 0.8559, "match_factor": 0.93, "truck_h_per_kt": 8.2474, "loader_h_per_kt": 0.6873, "cost_per_t": "not-computed (rates not supplied)",
    }  # fmt: skip
    f.update(over)
    return {
        "label": "calibrated synthetic",
        "bias_note": "x",
        "window": {"start": 0.0, "end": 3600.0, "hours": 1.0},
        "fleet": f,
        "loaders": [],
    }


@pytest.mark.req("FR-007-29")
def test_a_row_is_built_from_the_kpi_layer_output_and_validates():
    r = row_from_kpis(kpis(), seed=SEEDS[0], dispatcher="sptf", fleet_size=24)
    assert r == {
        "seed": SEEDS[0], "dispatcher": "sptf", "fleet_size": 24, "production_t_per_h": 1260.0, "queue_time_mean_min": 2.4, "loader_utilisation_frac": 0.8559,
        "match_factor": 0.93, "truck_hours_per_kt": 8.2474, "loader_hours_per_kt": 0.6873,
    }  # fmt: skip
    assert not list(ROW.iter_errors(r))


@pytest.mark.req("FR-007-29")
@pytest.mark.parametrize(
    "bad",
    [
        {"truck_h_per_kt": None, "loader_h_per_kt": None, "production_tph": 0.0, "tonnes_t": 0.0},
        {"production_tph": float("nan")},
        {"loader_utilisation": 1.5},
        {"match_factor": -0.1},
    ],
)
def test_a_run_without_production_or_with_out_of_range_kpis_yields_no_row(bad):
    with pytest.raises(ValueError):  # noqa: PT011
        row_from_kpis(kpis(**bad), seed=SEEDS[0], dispatcher="sptf", fleet_size=24)


@pytest.mark.req("FR-007-29")
@pytest.mark.parametrize("kw", [{"dispatcher": "greedy"}, {"seed": -1}, {"seed": 2**63}, {"fleet_size": 0}])
def test_a_row_with_an_unknown_dispatcher_or_out_of_range_identity_is_rejected(kw):
    with pytest.raises((ValueError, TypeError)):
        row_from_kpis(kpis(), **{"seed": SEEDS[0], "dispatcher": "sptf", "fleet_size": 24, **kw})


def fake_row(seed, dispatcher, fleet, th):
    return {
        "seed": seed, "dispatcher": dispatcher, "fleet_size": fleet, "production_t_per_h": th, "queue_time_mean_min": 2.0, "loader_utilisation_frac": 0.85,
        "match_factor": 0.9, "truck_hours_per_kt": 8.0, "loader_hours_per_kt": 0.7,
    }  # fmt: skip


def table_args(seeds, fleets=(24,)):
    ex = kit.example("dispatch-eval.valid.json")
    return {
        "id": "a1-dispatch-eval", "recipe": "a1-dispatch-evaluate", "engine": ex["engine"], "scenarios": [{"fleet_size": f, "bundle_sha256": "ab" * 32} for f in fleets],
        "test_seeds": seeds, "honesty": ex["honesty"],
    }  # fmt: skip


def synthetic(fleets=(12, 24), dispatchers=(*BASELINES, "ppo", "attention"), n=30, seed=5):
    rng = np.random.default_rng(seed)
    effects = {
        "fixed": -300.0,
        "nearest": -150.0,
        "sptf": 0.0,
        "sq": -20.0,
        "lp": 40.0,
        "ppo": 60.0,
        "attention": 110.0,
    }
    rows, th = [], {}
    for f in fleets:
        for s in SEEDS[:n]:
            common = rng.normal(0, 80)
            for d in dispatchers:
                v = 2000.0 + 40.0 * f + effects[d] + common + rng.normal(0, 25)
                th[(f, d, s)] = v
                rows.append(fake_row(s, d, f, v))
    return rows, th


@pytest.mark.req("FR-007-29")
@pytest.mark.req("SC-007-02")
def test_the_table_has_every_learned_versus_baseline_pair_per_fleet_size_computed_by_scipy():
    rows, th = synthetic()
    t = assemble_table(rows, **table_args(SEEDS, (12, 24)))
    assert not list(TABLE.iter_errors(t)), [e.message for e in TABLE.iter_errors(t)][:3]
    assert (
        t["schema_version"],
        t["mode"],
        t["variate_profile"],
        t["primary_metric"],
        t["ci_method"],
        t["ci_level"],
        t["min_pairs"],
    ) == ("1.0", "traffic", "engine", "production_t_per_h", "paired-t", 0.95, 30)
    assert t["rows"] == rows and t["test_seeds"] == SEEDS
    expected = {(f, "ppo", b) for f in (12, 24) for b in BASELINES} | {
        (f, "attention", b) for f in (12, 24) for b in (*BASELINES, "ppo")
    }
    got = {(c["fleet_size"], c["learned"], c["baseline"]) for c in t["comparisons"]}
    assert got == expected and len(t["comparisons"]) == len(expected) == 22
    for c in t["comparisons"]:
        f, lr, bs = c["fleet_size"], c["learned"], c["baseline"]
        diffs = [th[(f, lr, s)] - th[(f, bs, s)] for s in SEEDS]
        n, m, sd, _tc, lo, hi = reference(diffs)
        half = 6e-5 * sd / math.sqrt(n) + 1e-6
        assert c["n_pairs"] == 30 and c["mean_diff_t_per_h"] == pytest.approx(m, rel=1e-9)
        assert c["ci95"]["low_t_per_h"] == pytest.approx(lo, abs=half) and c["ci95"]["high_t_per_h"] == pytest.approx(
            hi, abs=half
        )
        assert {d["seed"]: d["diff_t_per_h"] for d in c["differences"]} == pytest.approx(
            dict(zip(SEEDS, diffs, strict=True)), abs=1e-9
        )
        assert c["verdict"] == (
            "learned-better" if lo > 0 else "baseline-better" if hi < 0 else "no-significant-difference"
        )


@pytest.mark.req("SC-007-02")
def test_attention_against_ppo_and_per_fleet_size_rows_are_present_with_the_expected_verdicts():
    rows, _ = synthetic(fleets=(12, 24, 36), dispatchers=("sptf", "lp", "ppo", "attention"))
    t = assemble_table(rows, **table_args(SEEDS, (12, 24, 36)))
    by = {(c["fleet_size"], c["learned"], c["baseline"]): c for c in t["comparisons"]}
    assert len(by) == 3 * (
        2 * 2 + 1
    )  # ppo and attention against sptf and lp, plus attention against ppo, in three fleets
    for f in (12, 24, 36):
        assert (
            by[(f, "attention", "sptf")]["verdict"] == "learned-better"
        )  # effect 110 t/h against noise sd of about 25 on the paired difference
        assert by[(f, "ppo", "sptf")]["verdict"] == "learned-better"
        assert by[(f, "attention", "ppo")]["verdict"] in {"learned-better", "no-significant-difference"}


@pytest.mark.req("SC-007-01")
def test_no_comparison_is_produced_for_an_arm_that_has_no_rows():
    rows, _ = synthetic(fleets=(24,), dispatchers=("sptf", "ppo"))
    t = assemble_table(rows, **table_args(SEEDS))
    assert [(c["learned"], c["baseline"]) for c in t["comparisons"]] == [("ppo", "sptf")]


@pytest.mark.req("FR-007-29")
def test_a_missing_seed_in_one_arm_of_a_pair_gives_insufficient_evidence_for_that_pair_only():
    rows, _ = synthetic(fleets=(24,), dispatchers=("sptf", "lp", "ppo"))
    rows = [r for r in rows if not (r["dispatcher"] == "lp" and r["seed"] == SEEDS[4])]
    t = assemble_table(rows, **table_args(SEEDS))
    by = {c["baseline"]: c for c in t["comparisons"]}
    assert by["lp"]["verdict"] == "insufficient-evidence" and by["lp"]["reason"] in {
        "seed-sets-differ",
        "fewer-than-30-pairs",
    }  # both conditions hold for 29 common seeds
    assert by["sptf"]["verdict"] != "insufficient-evidence"
    assert not list(TABLE.iter_errors(t))


@pytest.mark.req("FR-007-29")
def test_duplicate_rows_and_empty_row_lists_are_rejected():
    rows, _ = synthetic(fleets=(24,), dispatchers=("sptf", "ppo"))
    with pytest.raises(ValueError):  # noqa: PT011
        assemble_table([*rows, copy.deepcopy(rows[0])], **table_args(SEEDS))
    with pytest.raises(ValueError):  # noqa: PT011
        assemble_table([], **table_args(SEEDS))


@pytest.mark.req("FR-007-29")
def test_the_honesty_block_and_engine_pin_are_carried_unchanged():
    rows, _ = synthetic(fleets=(24,), dispatchers=("sptf", "ppo"))
    args = table_args(SEEDS)
    t = assemble_table(rows, **args)
    assert t["honesty"] == args["honesty"] and t["engine"] == args["engine"] and t["id"] == "a1-dispatch-eval"


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-28 in s50_evaluate
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-28")
def test_the_evaluation_guard_refuses_a_training_or_validation_seed_from_the_test_set():
    guard_seeds([1, 2, 3], [4, 5])  # disjoint: fine
    with pytest.raises(SeedLeak):
        guard_seeds([1, SEEDS[2]], [4])
    with pytest.raises(SeedLeak):
        guard_seeds([1], [SEEDS[29]])
    with pytest.raises(SeedLeak):
        guard_seeds([1], [4], tests=[4, 99])  # a custom pre-registered set is honoured
    guard_seeds([], [])  # nothing to leak

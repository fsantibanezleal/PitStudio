# ruff: noqa: E501
"""T-014-042: evaluation protocol, IL-1 metrics, Wilson intervals, paired t-intervals and hostile episode tables.

Requirements: FR-014-32, FR-014-33, FR-014-39, P-014-11.

Spec: specs/014-robot-learning/spec.md FR-014-32 (100 seeded episodes whose seeds are disjoint from the training and tuning seeds, the same seeds for
the policy and its baseline, deterministic actions), FR-014-33 (per episode: success, collision, RMS and maximum lateral error, minimum TTC (+inf if never
closing; clipped at 30 s for statistics), energy per gross tonne-kilometre and the fraction of steps within v_lim; over the 100 episodes: the success rate
with its Wilson 95 % interval, the RMS lateral error pooled over all control steps, and the fraction of episodes with minimum TTC >= 3 s), FR-014-39 (an
invalid episode table, a duplicated seed within an arm, seed sets that differ between paired arms, a NaN metric, or fewer than 100 episodes for an
acceptance verdict give no verdict and the report "incomplete evaluation" with the failing check), P-014-11 (MR1 Wilson(k, n) mirrors Wilson(n - k, n) as
[1 - U, 1 - L]; MR2 swapping arms negates the paired t-interval; MR3 adding a constant to both arms leaves the difference interval unchanged; MR4
permuting episodes leaves every statistic unchanged; hand calculation Wilson(95, 100) = [0.8882, 0.9785], t_{0.975,99} = 1.9842; rtol 1e-9).

Oracle: (1) the reference implementations `scipy.stats.binomtest(k, n).proportion_ci(method="wilson")` and `scipy.stats.ttest_rel(a, b).confidence_interval()`
(the plan's "statsmodels Wilson" is not in the pipeline environment; SciPy's Wilson is the same formula) and `scipy.stats.t.ppf`; (2) published values
(Wilson 95/100 = [0.8882, 0.9785]; t_{0.975,99} = 1.9842, SciPy `t.ppf(0.975, 99)` = 1.98422); (3) a hand-calculated 3-episode table: steps (100, 200, 300), sums of
squared lateral errors (4, 12, 9) m2 give a pooled RMS sqrt(25 / 600) = 0.2041241; success (T, T, F), minimum TTC (inf, 2.5 s, 3.0 s) give a fraction
2 / 3 with TTC >= 3 s and a clipped mean (30 + 2.5 + 3.0) / 3 = 11.8333 s; energy (0.10, 0.20, 0.30) gives 0.20; (4) hostile tables built by hand.

Expected API of the implementation (module `pitstudio_pipeline.evaluate.il`, pipeline environment). Tables are dicts {"meta": <il-episodes sidecar>, "rows": [...]}.
    wilson_interval(k, n, confidence=0.95) -> tuple[float, float]       ValueError naming k or n unless 0 <= k <= n and n >= 1
    PairedInterval: frozen dataclass (mean, lo, hi, n)                   interval of the mean of (a - b)
    paired_t_interval(a, b, confidence=0.95) -> PairedInterval          Student-t, n - 1 degrees of freedom; ValueError naming a or b for unequal
                                                                         lengths, fewer than 2 pairs or a non-finite value
    il1_summary(table) -> dict                                           keys: n, success_rate, success_wilson (lo, hi), collision_rate,
                                                                         pooled_rms_lateral_error_m, fraction_min_ttc_ge_3s, min_ttc_mean_clipped_s,
                                                                         energy_mean_kwh_per_t_km, frac_within_v_lim_mean
    check_pair(policy, baseline, *, seeds=None, acceptance=True) -> str | None
        the name of the first failing check, or None. Names: "schema", "seed_set_sha256", "duplicate_seed", "nan_metric", "fewer_than_100"
        (only when acceptance), "seed_sets_differ", "seeds_overlap_training", "seeds_not_evaluation_range" (the last two only when `seeds`, the
        `seeds` block of the task, is given). The check order is the order of this list.
    evaluate_il1(policy, baseline, *, seeds, twin=None) -> dict
        report: {"status": "complete" | "incomplete evaluation", "failed_check": None | name, "fixture": bool, "policy": summary, "baseline": summary, ...};
        when a check fails, status is "incomplete evaluation", failed_check names it, and neither "verdicts" nor "sim_to_sim" is present.
    load_table(sidecar_path, root) -> dict
        reads the sidecar JSON and the Parquet file at root / table.path with pyarrow; ValueError naming `sha256`, `rows`, `path` or the missing column.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio_pipeline.evaluate.il import (
    check_pair,
    evaluate_il1,
    il1_summary,
    load_table,
    paired_t_interval,
    wilson_interval,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import il_tables as kit


# ------------------------------------------------------------------------------------------------ Wilson
@pytest.mark.req("P-014-11")
def test_wilson_published_hand_calculation_95_of_100() -> None:
    lo, hi = wilson_interval(95, 100)
    assert lo == pytest.approx(0.8882, abs=5e-5)
    assert hi == pytest.approx(0.9785, abs=5e-5)


@pytest.mark.req("P-014-11")
def test_wilson_matches_scipy_over_a_grid() -> None:
    from scipy.stats import binomtest

    for n in (1, 2, 3, 5, 10, 17, 50, 100, 101, 400, 1000):
        for k in sorted({0, 1, n // 3, n // 2, n - 1, n}):
            if not 0 <= k <= n:
                continue
            ref = binomtest(k, n).proportion_ci(confidence_level=0.95, method="wilson")
            lo, hi = wilson_interval(k, n)
            assert lo == pytest.approx(ref.low, rel=1e-9, abs=1e-12)
            assert hi == pytest.approx(ref.high, rel=1e-9, abs=1e-12)


@pytest.mark.req("P-014-11")
@given(st.integers(1, 10_000), st.data())
@settings(max_examples=300, deadline=None)
def test_mr1_wilson_mirrors_under_k_to_n_minus_k(n, data) -> None:
    k = data.draw(st.integers(0, n))
    lo, hi = wilson_interval(k, n)
    lo2, hi2 = wilson_interval(n - k, n)
    assert lo2 == pytest.approx(1.0 - hi, rel=1e-9, abs=1e-12)
    assert hi2 == pytest.approx(1.0 - lo, rel=1e-9, abs=1e-12)
    assert 0.0 <= lo <= k / n <= hi <= 1.0


@pytest.mark.req("P-014-11")
def test_wilson_other_confidence_levels_match_scipy() -> None:
    from scipy.stats import binomtest

    for conf in (0.80, 0.90, 0.99):
        ref = binomtest(37, 120).proportion_ci(confidence_level=conf, method="wilson")
        lo, hi = wilson_interval(37, 120, confidence=conf)
        assert (lo, hi) == pytest.approx((ref.low, ref.high), rel=1e-9)


@pytest.mark.req("FR-014-39")
@pytest.mark.parametrize(
    ("k", "n", "name"), [(-1, 10, "k"), (11, 10, "k"), (0, 0, "n"), (5, -3, "n"), (1.5, 10, "k"), (math.nan, 10, "k")]
)
def test_wilson_rejects_invalid_counts(k, n, name) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        wilson_interval(k, n)


# ------------------------------------------------------------------------------------------------ paired t
def pairs(n: int, seed: int = 0):
    rng = random.Random(seed)
    a = [rng.gauss(1.0, 0.5) for _ in range(n)]
    b = [rng.gauss(0.8, 0.5) for _ in range(n)]
    return a, b


@pytest.mark.req("P-014-11")
def test_the_t_quantile_for_100_pairs_is_1_9842() -> None:
    d = [1.0, -1.0] * 50  # n = 100, mean 0, sd = sqrt(100 / 99)
    r = paired_t_interval(d, [0.0] * 100)
    half = 1.9842 * math.sqrt(100.0 / 99.0) / 10.0
    assert r.mean == pytest.approx(0.0, abs=1e-12)
    assert r.hi - r.mean == pytest.approx(half, rel=1e-4)
    assert r.mean - r.lo == pytest.approx(half, rel=1e-4)
    assert r.n == 100


@pytest.mark.req("P-014-11")
@pytest.mark.parametrize("n", [2, 3, 5, 20, 100, 250])
def test_the_paired_t_interval_matches_scipy(n) -> None:
    from scipy.stats import ttest_rel

    a, b = pairs(n, seed=n)
    ref = ttest_rel(a, b).confidence_interval(0.95)
    r = paired_t_interval(a, b)
    assert r.lo == pytest.approx(ref.low, rel=1e-9)
    assert r.hi == pytest.approx(ref.high, rel=1e-9)
    assert r.mean == pytest.approx(sum(x - y for x, y in zip(a, b, strict=True)) / n, rel=1e-12)


@pytest.mark.req("P-014-11")
@given(
    st.lists(st.tuples(st.floats(-1e3, 1e3), st.floats(-1e3, 1e3)), min_size=2, max_size=60),
    st.floats(-1e3, 1e3),
    st.randoms(use_true_random=False),
)
@settings(max_examples=200, deadline=None)
def test_mr2_mr3_mr4_swap_shift_and_permutation(ps, c, rnd) -> None:
    a, b = [p[0] for p in ps], [p[1] for p in ps]
    base = paired_t_interval(a, b)
    swapped = paired_t_interval(b, a)  # MR2: negates
    assert swapped.lo == pytest.approx(-base.hi, rel=1e-9, abs=1e-9)
    assert swapped.hi == pytest.approx(-base.lo, rel=1e-9, abs=1e-9)
    assert swapped.mean == pytest.approx(-base.mean, rel=1e-9, abs=1e-9)
    shifted = paired_t_interval([x + c for x in a], [y + c for y in b])  # MR3: a constant added to both arms
    assert shifted.lo == pytest.approx(base.lo, rel=1e-6, abs=1e-6)
    assert shifted.hi == pytest.approx(base.hi, rel=1e-6, abs=1e-6)
    idx = list(range(len(a)))
    rnd.shuffle(idx)  # MR4: permuting the episodes
    permuted = paired_t_interval([a[i] for i in idx], [b[i] for i in idx])
    assert permuted.lo == pytest.approx(base.lo, rel=1e-9, abs=1e-9)
    assert permuted.hi == pytest.approx(base.hi, rel=1e-9, abs=1e-9)


@pytest.mark.req("FR-014-39")
@pytest.mark.parametrize(
    ("a", "b", "name"),
    [
        ([1.0], [2.0], "a"),
        ([], [], "a"),
        ([1.0, 2.0], [1.0], "b"),
        ([1.0, math.nan], [1.0, 2.0], "a"),
        ([1.0, 2.0], [1.0, math.inf], "b"),
    ],
)
def test_the_paired_interval_rejects_invalid_pairs(a, b, name) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        paired_t_interval(a, b)


# ---------------------------------------------------------------------------------------------- IL-1 summary
THREE = [
    kit.il1_row(
        1,
        steps=100,
        sum_sq_lateral_error_m2=4.0,
        success=True,
        min_ttc_s=math.inf,
        energy_kwh_per_t_km=0.10,
        frac_within_v_lim=1.0,
    ),
    kit.il1_row(
        2,
        steps=200,
        sum_sq_lateral_error_m2=12.0,
        success=True,
        min_ttc_s=2.5,
        energy_kwh_per_t_km=0.20,
        frac_within_v_lim=0.9,
    ),
    kit.il1_row(
        3,
        steps=300,
        sum_sq_lateral_error_m2=9.0,
        success=False,
        collision=True,
        termination="collision",
        min_ttc_s=3.0,
        energy_kwh_per_t_km=0.30,
        frac_within_v_lim=0.8,
    ),
]


@pytest.mark.req("FR-014-33")
def test_the_three_episode_hand_calculation() -> None:
    s = il1_summary(kit.table("IL-1", "policy", THREE))
    assert s["n"] == 3
    assert s["success_rate"] == pytest.approx(2.0 / 3.0, rel=1e-12)
    lo, hi = wilson_interval(2, 3)
    assert s["success_wilson"] == pytest.approx((lo, hi), rel=1e-12)
    assert s["collision_rate"] == pytest.approx(1.0 / 3.0, rel=1e-12)
    assert s["pooled_rms_lateral_error_m"] == pytest.approx(
        math.sqrt(25.0 / 600.0), rel=1e-12
    )  # 0.2041241: pooled over all control steps, not a mean of RMS
    assert s["fraction_min_ttc_ge_3s"] == pytest.approx(2.0 / 3.0, rel=1e-12)  # inf and 3.0 count, 2.5 does not
    assert s["min_ttc_mean_clipped_s"] == pytest.approx((30.0 + 2.5 + 3.0) / 3.0, rel=1e-12)
    assert s["energy_mean_kwh_per_t_km"] == pytest.approx(0.20, rel=1e-12)
    assert s["frac_within_v_lim_mean"] == pytest.approx(0.9, rel=1e-12)


@pytest.mark.req("FR-014-33")
def test_the_pooled_rms_differs_from_the_mean_of_the_per_episode_rms() -> None:
    rows = [
        kit.il1_row(1, steps=10, sum_sq_lateral_error_m2=10.0, rms_lateral_error_m=1.0),
        kit.il1_row(2, steps=1000, sum_sq_lateral_error_m2=10.0, rms_lateral_error_m=0.1),
    ]
    s = il1_summary(kit.table("IL-1", "policy", rows))
    assert s["pooled_rms_lateral_error_m"] == pytest.approx(math.sqrt(20.0 / 1010.0), rel=1e-12)
    assert abs(s["pooled_rms_lateral_error_m"] - 0.55) > 0.3  # the mean of the two per-episode values would be 0.55


@pytest.mark.req("FR-014-33")
def test_a_hundred_episode_summary_and_the_ttc_threshold_edge() -> None:
    rows = kit.il1_rows(100)
    for i in range(5):
        rows[i] = kit.il1_row(rows[i]["seed"], success=False, collision=True, termination="collision", min_ttc_s=0.8)
    for i in range(5, 8):
        rows[i] = kit.il1_row(rows[i]["seed"], min_ttc_s=3.0)  # exactly 3 s counts as >= 3 s
    for i in range(8, 10):
        rows[i] = kit.il1_row(rows[i]["seed"], min_ttc_s=2.999)
    s = il1_summary(kit.table("IL-1", "policy", rows))
    assert s["success_rate"] == pytest.approx(0.95, rel=1e-12)
    assert s["success_wilson"] == pytest.approx((0.8882, 0.9785), abs=5e-5)  # the published Wilson(95, 100)
    assert s["fraction_min_ttc_ge_3s"] == pytest.approx(0.93, rel=1e-12)  # 5 + 2 episodes below 3 s


@pytest.mark.req("P-014-11")
@given(st.randoms(use_true_random=False))
@settings(max_examples=50, deadline=None)
def test_mr4_permuting_the_episodes_leaves_every_summary_statistic_unchanged(rnd) -> None:
    rows = [
        kit.il1_row(
            kit.EVAL_START + i, success=i % 7 != 0, steps=500 + 3 * i, sum_sq_lateral_error_m2=10.0 + i,
            min_ttc_s=math.inf if i % 5 == 0 else 1.0 + 0.1 * i, energy_kwh_per_t_km=0.1 + 0.001 * i,
        )
        for i in range(100)
    ]  # fmt: skip
    base = il1_summary(kit.table("IL-1", "policy", rows))
    shuffled = rows[:]
    rnd.shuffle(shuffled)
    again = il1_summary(kit.table("IL-1", "policy", shuffled))
    assert again.keys() == base.keys()
    for key, value in base.items():
        if isinstance(value, tuple | list):
            assert list(again[key]) == pytest.approx(list(value), rel=1e-9)
        else:
            assert again[key] == pytest.approx(value, rel=1e-9)


# ---------------------------------------------------------------------------------------------- pair checks
def pair(n=100, policy_rows=None, baseline_rows=None):
    p = policy_rows if policy_rows is not None else kit.il1_rows(n)
    b = baseline_rows if baseline_rows is not None else kit.il1_rows(n)
    return kit.table("IL-1", "policy", p), kit.table("IL-1", "baseline", b)


@pytest.mark.req("FR-014-32")
def test_a_valid_paired_pair_passes_every_check() -> None:
    p, b = pair()
    assert check_pair(p, b, seeds=kit.IL1_SEEDS_BLOCK) is None


@pytest.mark.req("FR-014-39")
def test_fewer_than_100_episodes_fail_the_acceptance_check_but_pass_without_acceptance() -> None:
    p, b = pair(99)
    assert check_pair(p, b) == "fewer_than_100"
    assert check_pair(p, b, acceptance=False) is None


@pytest.mark.req("FR-014-39")
def test_a_duplicated_seed_within_an_arm_is_detected() -> None:
    rows = kit.il1_rows(100)
    rows[50] = kit.il1_row(rows[49]["seed"])  # seed repeated, one seed of the set now missing
    p, b = pair(policy_rows=rows)
    assert check_pair(p, b) == "duplicate_seed"
    p2, b2 = pair(baseline_rows=rows)
    assert check_pair(p2, b2) == "duplicate_seed"


@pytest.mark.req("FR-014-39")
def test_seed_sets_that_differ_between_the_paired_arms_are_detected() -> None:
    other = kit.il1_rows(100, start=kit.EVAL_START + 1)  # shifted by one: 99 shared seeds
    p, b = pair(policy_rows=kit.il1_rows(100), baseline_rows=other)
    assert check_pair(p, b) == "seed_sets_differ"
    shuffled = kit.il1_rows(100)
    random.Random(3).shuffle(shuffled)
    p, b = pair(policy_rows=kit.il1_rows(100), baseline_rows=shuffled)
    assert check_pair(p, b, seeds=kit.IL1_SEEDS_BLOCK) is None  # the same set in another order is a valid pairing


@pytest.mark.req("FR-014-39")
@pytest.mark.parametrize(
    "column",
    [
        "rms_lateral_error_m",
        "max_lateral_error_m",
        "energy_kwh_per_t_km",
        "frac_within_v_lim",
        "sum_sq_lateral_error_m2",
        "min_ttc_s",
    ],
)
def test_a_nan_metric_is_detected(column) -> None:
    rows = kit.il1_rows(100)
    rows[17] = {**rows[17], column: math.nan}
    p, b = pair(policy_rows=rows)
    assert check_pair(p, b) == "nan_metric"


@pytest.mark.req("FR-014-39")
def test_an_infinite_minimum_ttc_is_valid_but_other_infinite_metrics_are_rejected() -> None:
    rows = kit.il1_rows(100, min_ttc_s=math.inf)
    p, b = pair(policy_rows=rows)
    assert check_pair(p, b) is None
    rows = kit.il1_rows(100)
    rows[3] = {**rows[3], "energy_kwh_per_t_km": math.inf}
    p, b = pair(policy_rows=rows)
    assert check_pair(p, b) in ("nan_metric", "schema")  # rejected whichever of the two checks sees it first
    rows = kit.il1_rows(100)
    rows[4] = {**rows[4], "min_ttc_s": -math.inf}
    p, b = pair(policy_rows=rows)
    assert check_pair(p, b) in ("nan_metric", "schema")


@pytest.mark.req("FR-014-39")
def test_an_invalid_sidecar_is_a_schema_failure() -> None:
    p, b = pair()
    p["meta"]["arm"] = "twinned"
    assert check_pair(p, b) == "schema"
    p, b = pair()
    p["meta"]["deterministic_actions"] = False
    assert check_pair(p, b) == "schema"  # FR-014-32: deterministic (mean) actions only
    p, b = pair()
    p["meta"]["column_set"] = "dig-episode"
    assert check_pair(p, b) == "schema"
    p, b = pair()
    del p["meta"]["controller"]
    assert check_pair(p, b) == "schema"
    p, b = pair()
    p["meta"]["table"]["path"] = "../escape.parquet"
    assert check_pair(p, b) == "schema"


@pytest.mark.req("FR-014-39")
def test_a_row_that_violates_the_row_schema_is_a_schema_failure() -> None:
    rows = kit.il1_rows(100)
    rows[9] = {**rows[9], "termination": "exploded"}
    p, b = pair(policy_rows=rows)
    assert check_pair(p, b) == "schema"
    rows = kit.il1_rows(100)
    rows[9] = {**rows[9], "frac_within_v_lim": 1.5}
    p, b = pair(policy_rows=rows)
    assert check_pair(p, b) == "schema"
    rows = kit.il1_rows(100)
    rows[9] = {**rows[9], "unexpected_column": 1}
    p, b = pair(policy_rows=rows)
    assert check_pair(p, b) == "schema"


@pytest.mark.req("FR-014-39")
def test_a_seed_set_digest_that_does_not_match_the_rows_is_detected() -> None:
    p, b = pair()
    p["meta"]["seed_set_sha256"] = "1" * 64
    assert check_pair(p, b) == "seed_set_sha256"
    assert (
        kit.seed_digest(r["seed"] for r in p["rows"])
        == hashlib.sha256(json.dumps(sorted(r["seed"] for r in p["rows"]), separators=(",", ":")).encode()).hexdigest()
    )


@pytest.mark.req("FR-014-32")
def test_evaluation_seeds_must_be_disjoint_from_training_and_tuning_seeds_and_be_the_evaluation_range() -> None:
    train_like = kit.il1_rows(100, start=100)  # seeds 100..199 lie inside the training range 0..4095
    p, b = pair(policy_rows=train_like, baseline_rows=kit.il1_rows(100, start=100))
    assert check_pair(p, b, seeds=kit.IL1_SEEDS_BLOCK) == "seeds_overlap_training"
    shifted = kit.il1_rows(
        100, start=kit.EVAL_START + 5
    )  # disjoint from training but not the declared evaluation range
    p, b = pair(policy_rows=shifted, baseline_rows=kit.il1_rows(100, start=kit.EVAL_START + 5))
    assert check_pair(p, b, seeds=kit.IL1_SEEDS_BLOCK) == "seeds_not_evaluation_range"
    tune_like = kit.il1_rows(100, start=1_999_950)  # overlaps the tuning range of an IL-2 block
    p, b = pair(policy_rows=tune_like, baseline_rows=kit.il1_rows(100, start=1_999_950))
    assert check_pair(p, b, seeds=kit.IL2_SEEDS_BLOCK) == "seeds_overlap_training"


# ---------------------------------------------------------------------------------------------- evaluate_il1
@pytest.mark.req("FR-014-32")
@pytest.mark.req("FR-014-33")
def test_a_complete_evaluation_reports_both_arms_and_no_failed_check() -> None:
    p = kit.table("IL-1", "policy", kit.il1_rows(100, success=True))
    rows = kit.il1_rows(100)
    for i in range(10):
        rows[i] = kit.il1_row(rows[i]["seed"], success=False, collision=True, termination="collision")
    b = kit.table("IL-1", "baseline", rows)
    rep = evaluate_il1(p, b, seeds=kit.IL1_SEEDS_BLOCK)
    assert rep["status"] == "complete"
    assert rep["failed_check"] is None
    assert rep["fixture"] is False
    assert rep["policy"]["success_rate"] == 1.0
    assert rep["baseline"]["success_rate"] == pytest.approx(0.90, rel=1e-12)
    assert rep["policy"]["n"] == rep["baseline"]["n"] == 100


@pytest.mark.req("FR-014-39")
@pytest.mark.parametrize(
    ("case", "check"),
    [
        ("few", "fewer_than_100"),
        ("duplicate", "duplicate_seed"),
        ("differ", "seed_sets_differ"),
        ("nan", "nan_metric"),
        ("schema", "schema"),
        ("training", "seeds_overlap_training"),
    ],
)
def test_an_invalid_pair_gives_incomplete_evaluation_with_the_failing_check_and_no_verdict(case, check) -> None:
    p, b = pair()
    if case == "few":
        p, b = pair(60)
    elif case == "duplicate":
        rows = kit.il1_rows(100)
        rows[1] = kit.il1_row(rows[0]["seed"])
        p, b = pair(policy_rows=rows)
    elif case == "differ":
        p, b = pair(baseline_rows=kit.il1_rows(100, start=kit.EVAL_START + 3))
    elif case == "nan":
        rows = kit.il1_rows(100)
        rows[0] = {**rows[0], "energy_kwh_per_t_km": math.nan}
        p, b = pair(policy_rows=rows)
    elif case == "schema":
        p["meta"]["arm"] = "nonsense"
    elif case == "training":
        p, b = pair(policy_rows=kit.il1_rows(100, start=50), baseline_rows=kit.il1_rows(100, start=50))
    rep = evaluate_il1(p, b, seeds=kit.IL1_SEEDS_BLOCK)
    assert rep["status"] == "incomplete evaluation"
    assert rep["failed_check"] == check
    assert "verdicts" not in rep
    assert "sim_to_sim" not in rep


# --------------------------------------------------------------------------------------------- load_table
def write_parquet(tmp_path: Path, rows: list[dict], name="il/il1/episodes-policy.parquet"):
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = {k: [r[k] for r in rows] for k in rows[0]}
    pq.write_table(pa.table(cols), path)
    side = kit.meta("IL-1", "policy", rows)
    side["table"] = {
        "path": name,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": len(rows),
    }
    sidecar = tmp_path / "il/il1/episodes-policy.json"
    sidecar.write_text(json.dumps(side), encoding="utf-8")
    return sidecar, path


@pytest.mark.req("FR-014-39")
def test_load_table_round_trips_parquet_including_infinite_minimum_ttc(tmp_path: Path) -> None:
    rows = kit.il1_rows(100)
    rows[0] = kit.il1_row(rows[0]["seed"], min_ttc_s=math.inf)
    rows[1] = kit.il1_row(rows[1]["seed"], min_ttc_s=2.25)
    sidecar, _ = write_parquet(tmp_path, rows)
    doc = load_table(sidecar, tmp_path)
    assert doc["meta"]["table"]["rows"] == 100
    assert len(doc["rows"]) == 100
    assert doc["rows"][0]["min_ttc_s"] == math.inf
    assert doc["rows"][1]["min_ttc_s"] == 2.25
    assert [r["seed"] for r in doc["rows"]] == [r["seed"] for r in rows]
    assert doc["rows"][5]["success"] is True


@pytest.mark.req("FR-014-39")
def test_load_table_rejects_a_changed_parquet_file(tmp_path: Path) -> None:
    sidecar, path = write_parquet(tmp_path, kit.il1_rows(100))
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    path.write_bytes(bytes(data))
    with pytest.raises(ValueError, match="sha256"):
        load_table(sidecar, tmp_path)


@pytest.mark.req("FR-014-39")
def test_load_table_rejects_a_row_count_that_differs_from_the_sidecar(tmp_path: Path) -> None:
    sidecar, _ = write_parquet(tmp_path, kit.il1_rows(100))
    side = json.loads(sidecar.read_text("utf-8"))
    side["table"]["rows"] = 99
    sidecar.write_text(json.dumps(side), encoding="utf-8")
    with pytest.raises(ValueError, match="rows"):
        load_table(sidecar, tmp_path)


@pytest.mark.req("FR-014-39")
def test_load_table_rejects_a_missing_file_a_traversal_path_and_a_missing_column(tmp_path: Path) -> None:
    sidecar, path = write_parquet(tmp_path, kit.il1_rows(100))
    side = json.loads(sidecar.read_text("utf-8"))
    path.unlink()
    with pytest.raises(ValueError, match="path"):
        load_table(sidecar, tmp_path)
    side["table"]["path"] = "../outside.parquet"
    sidecar.write_text(json.dumps(side), encoding="utf-8")
    with pytest.raises(ValueError, match="path"):
        load_table(sidecar, tmp_path)
    rows = [{k: v for k, v in r.items() if k != "energy_kwh_per_t_km"} for r in kit.il1_rows(100)]
    sidecar2, _ = write_parquet(tmp_path / "second", rows)
    side2 = json.loads(sidecar2.read_text("utf-8"))
    side2["table"]["sha256"] = hashlib.sha256((tmp_path / "second" / side2["table"]["path"]).read_bytes()).hexdigest()
    sidecar2.write_text(json.dumps(side2), encoding="utf-8")
    with pytest.raises(ValueError, match="energy_kwh_per_t_km"):
        load_table(sidecar2, tmp_path / "second")


@pytest.mark.req("FR-014-39")
def test_load_table_rejects_a_sidecar_that_is_not_json_or_not_a_valid_sidecar(tmp_path: Path) -> None:
    sidecar, _ = write_parquet(tmp_path, kit.il1_rows(100))
    sidecar.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match=r".+"):
        load_table(sidecar, tmp_path)
    sidecar.write_text(json.dumps({"policy": "IL-1"}), encoding="utf-8")
    with pytest.raises(ValueError, match=r".+"):
        load_table(sidecar, tmp_path)
    with pytest.raises(ValueError, match=r"path|sidecar"):
        load_table(tmp_path / "does-not-exist.json", tmp_path)

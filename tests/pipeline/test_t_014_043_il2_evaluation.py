# ruff: noqa: E501
"""T-014-043: IL-2 metrics (fill factor k_f, cycle time t_c, productivity, stalls, lift-off).

Requirements: FR-014-35, FR-014-39 (dig tables).

Spec: specs/014-robot-learning/spec.md FR-014-35: "For IL-2 the evaluation shall compute per episode: the fill factor k_f at dig completion (bucket lifted >= 0.5 m
above the local terrain after cutting) or at the 30 s time limit, the cycle time t_c from episode start to dig completion (30 s if not completed), the
productivity P = k_f / t_c (1/s), the stall flag and the lift-off flag; and over the episodes: the fraction with k_f >= 0.8 and the fraction stalled, each with a
Wilson 95 % interval." FR-014-39 applies to the dig tables as to the IL-1 tables (T-014-042).

Oracle: hand calculation on scripted traces (time step 0.5 s, 60 steps = the 30 s limit): the lift reaches 0.5 m at step index 28, whose state is at t = (28 + 1) * 0.5 =
14.5 s, so t_c = 14.5 s and P = 0.9 / 14.5 = 0.0620690 1/s; a trace that never lifts gives t_c = 30 s and P = k_f / 30; stall events by the rule of FR-014-20 (>= 1.0 s at
|tau| >= 0.99 tau_max, here two samples of 0.5 s); the summary of a 10-episode table counted by hand; Wilson intervals by `scipy.stats.binomtest(...).proportion_ci(method=
"wilson")`.

Conventions (the spec is silent; see the red report): sample k of a trace is the state after step k, at time (k + 1) dt; "after cutting" means at a sample index strictly after the first step with the FEE force
active; the stall flag looks at the samples up to and including the completion sample (the whole trace when not completed).

Expected API of the implementation (module `pitstudio_pipeline.evaluate.il`, see T-014-042):
    dig_episode_metrics(*, dt, fill, lift_height, cutting, torque, tau_max, time_limit=30.0) -> dict
        fill: (T,) k_f after each step; lift_height: (T,) bucket lip height above the local terrain (m); cutting: (T,) bool, the FEE force was active;
        torque: (T, J) joint torques (N m); tau_max: (J,). Returns {"termination": "completed" | "time_limit", "fill_factor", "cycle_time_s",
        "productivity_per_s", "stalled": bool, "lift_off": bool}. ValueError naming `fill`, `lift_height`, `cutting`, `torque`, `tau_max` or `dt` for
        a wrong shape, a non-finite value or dt <= 0.
    il2_summary(table) -> dict                                       keys: n, kf_mean, cycle_time_mean_s, productivity_mean_per_s, lift_off_rate,
                                                                     fraction_kf_ge_0_8, fraction_kf_ge_0_8_wilson, fraction_stalled, fraction_stalled_wilson
    check_pair, evaluate_il2(policy, baseline, *, seeds, mpm=None, il3=None) -> dict
        check_pair works on dig tables as on IL-1 tables; evaluate_il2 returns the report of evaluate_il1 with the IL-2 summaries ("policy", "baseline") and the same
        incomplete-evaluation behaviour.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.evaluate.il import check_pair, dig_episode_metrics, evaluate_il2, il2_summary, wilson_interval

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import il_tables as kit

DT = 0.5
T = 60
TAU = np.array([100.0, 200.0, 300.0, 400.0])


def trace(*, lift_from: int | None = 25, fill_final: float = 0.9, cut_from: int = 4, cut_to: int = 20):
    k = np.arange(T)
    fill = np.minimum(0.05 * np.maximum(k - (cut_from - 1), 0), 1.0)
    fill = np.where(k >= cut_to, fill[cut_to - 1], fill)
    fill = np.minimum(fill, fill_final)
    lift = np.zeros(T) if lift_from is None else np.where(k >= lift_from, 0.125 * (k - (lift_from - 1)), 0.0)
    cutting = (k >= cut_from) & (k < cut_to)
    torque = np.zeros((T, 4))
    return {"dt": DT, "fill": fill, "lift_height": lift, "cutting": cutting, "torque": torque, "tau_max": TAU}


@pytest.mark.req("FR-014-35")
def test_completion_time_fill_factor_and_productivity_by_hand_calculation() -> None:
    tr = trace(lift_from=25, fill_final=0.9)
    # lift = 0.125 * (k - 24) for k >= 25: 0.125 at k = 25, 0.5 at k = 28 (state after step 28, at t = 29 * 0.5 = 14.5 s)
    assert tr["lift_height"][28] == 0.5
    m = dig_episode_metrics(**tr)
    assert m["termination"] == "completed"
    assert m["lift_off"] is True
    assert m["cycle_time_s"] == pytest.approx(14.5, rel=1e-12)
    kf = float(tr["fill"][28])
    assert m["fill_factor"] == pytest.approx(kf, rel=1e-12)
    assert m["productivity_per_s"] == pytest.approx(kf / 14.5, rel=1e-12)
    assert m["stalled"] is False


@pytest.mark.req("FR-014-35")
def test_the_fill_factor_is_read_at_the_completion_sample_not_at_the_end() -> None:
    tr = trace(lift_from=25)
    tr["fill"] = np.linspace(0.0, 1.0, T)  # still rising after completion: the value at index 28 counts
    m = dig_episode_metrics(**tr)
    assert m["fill_factor"] == pytest.approx(28 / (T - 1), rel=1e-12)


@pytest.mark.req("FR-014-35")
def test_a_bucket_that_never_lifts_ends_at_the_time_limit_with_30_seconds() -> None:
    tr = trace(lift_from=None, fill_final=0.7)
    m = dig_episode_metrics(**tr)
    assert m["termination"] == "time_limit"
    assert m["lift_off"] is False
    assert m["cycle_time_s"] == 30.0
    assert m["fill_factor"] == pytest.approx(float(tr["fill"][-1]), rel=1e-12)
    assert m["productivity_per_s"] == pytest.approx(float(tr["fill"][-1]) / 30.0, rel=1e-12)


@pytest.mark.req("FR-014-35")
def test_a_lift_before_any_cutting_is_not_a_dig_completion() -> None:
    tr = trace(lift_from=None, fill_final=0.6)
    tr["lift_height"] = np.full(T, 0.8)  # the lip is high from the start, but nothing has been cut when it is high
    tr["cutting"] = np.zeros(T, dtype=bool)
    m = dig_episode_metrics(**tr)
    assert m["termination"] == "time_limit"
    assert m["lift_off"] is False
    tr["cutting"][10] = True  # one cutting step: from then on a high lip completes the dig
    m = dig_episode_metrics(**tr)
    assert m["termination"] == "completed"
    assert m["cycle_time_s"] == pytest.approx(
        12 * DT, rel=1e-12
    )  # the first sample after the cutting step 10 is index 11, at t = (11 + 1) * 0.5 = 6.0 s
    assert m["lift_off"] is True


@pytest.mark.req("FR-014-35")
def test_the_lift_threshold_is_inclusive() -> None:
    tr = trace(lift_from=None)
    tr["cutting"][:] = False
    tr["cutting"][2] = True
    tr["lift_height"] = np.where(np.arange(T) >= 30, 0.5, 0.4999)
    m = dig_episode_metrics(**tr)
    assert m["termination"] == "completed"
    assert m["cycle_time_s"] == pytest.approx(31 * DT, rel=1e-12)  # state after step 30 at t = 31 * 0.5


@pytest.mark.req("FR-014-35")
def test_a_stall_before_completion_flags_the_episode_and_a_late_one_does_not() -> None:
    tr = trace(lift_from=25)
    tr["torque"][10:12, 1] = 0.995 * 200.0  # two samples = 1.0 s at >= 0.99 tau_max, before the completion sample 28
    assert dig_episode_metrics(**tr)["stalled"] is True
    tr = trace(lift_from=25)
    tr["torque"][40:44, 2] = 300.0  # long after the dig completed
    assert dig_episode_metrics(**tr)["stalled"] is False
    tr = trace(lift_from=25)
    tr["torque"][10, 1] = 200.0  # a single 0.5 s sample is below the 1.0 s rule
    assert dig_episode_metrics(**tr)["stalled"] is False


@pytest.mark.req("FR-014-35")
def test_the_productivity_is_zero_for_an_empty_bucket() -> None:
    tr = trace(lift_from=25)
    tr["fill"] = np.zeros(T)
    m = dig_episode_metrics(**tr)
    assert m["fill_factor"] == 0.0
    assert m["productivity_per_s"] == 0.0


@pytest.mark.req("FR-014-35")
@pytest.mark.parametrize(
    ("field", "value", "name"),
    [
        ("dt", 0.0, "dt"), ("dt", -0.5, "dt"), ("dt", math.nan, "dt"),
        ("fill", np.zeros(T - 1), "fill|lift_height"), ("fill", np.full(T, math.nan), "fill"),  # a length mismatch may be reported on either array
        ("lift_height", np.zeros(T + 1), "lift_height|fill"), ("lift_height", np.full(T, math.inf), "lift_height"),
        ("cutting", np.zeros(T - 2, dtype=bool), "cutting|fill"),
        ("torque", np.zeros((T, 3)), "torque|tau_max"), ("torque", np.full((T, 4), math.nan), "torque"),
        ("tau_max", np.array([1.0, 1.0, 0.0, 1.0]), "tau_max"),
    ],
)  # fmt: skip
def test_hostile_traces_raise_value_error_naming_the_input(field, value, name) -> None:
    tr = trace()
    tr[field] = value
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        dig_episode_metrics(**tr)


# ------------------------------------------------------------------------------------------------- summary
def ten_rows():
    spec = [
        # (k_f, t_c, stalled, lift_off)
        (0.95, 12.0, False, True), (0.80, 14.0, False, True), (0.79, 15.0, False, True), (0.60, 30.0, True, False), (1.05, 11.0, False, True),
        (0.85, 13.0, True, True), (0.90, 16.0, False, True), (0.40, 30.0, False, False), (1.10, 10.0, False, True), (0.82, 17.0, False, True),
    ]  # fmt: skip
    return [
        kit.dig_row(
            kit.EVAL_START + i,
            fill_factor=kf,
            cycle_time_s=tc,
            productivity_per_s=kf / tc,
            stalled=st,
            lift_off=lo,
            termination="completed" if lo else "time_limit",
        )
        for i, (kf, tc, st, lo) in enumerate(spec)
    ]


@pytest.mark.req("FR-014-35")
def test_the_ten_episode_summary_by_hand_counting() -> None:
    s = il2_summary(kit.table("IL-2", "policy", ten_rows()))
    assert s["n"] == 10
    assert s["fraction_kf_ge_0_8"] == pytest.approx(
        0.7, rel=1e-12
    )  # 0.95, 0.80 (inclusive), 1.05, 0.85, 0.90, 1.10, 0.82 -> 7 of 10; 0.79, 0.60, 0.40 are below
    assert s["fraction_stalled"] == pytest.approx(0.2, rel=1e-12)
    assert s["lift_off_rate"] == pytest.approx(0.8, rel=1e-12)
    assert s["kf_mean"] == pytest.approx(
        sum([0.95, 0.80, 0.79, 0.60, 1.05, 0.85, 0.90, 0.40, 1.10, 0.82]) / 10.0, rel=1e-12
    )  # 0.826
    assert s["cycle_time_mean_s"] == pytest.approx(
        sum([12, 14, 15, 30, 11, 13, 16, 30, 10, 17]) / 10.0, rel=1e-12
    )  # 16.8
    assert s["productivity_mean_per_s"] == pytest.approx(
        sum(
            kf / tc
            for kf, tc in [
                (0.95, 12),
                (0.80, 14),
                (0.79, 15),
                (0.60, 30),
                (1.05, 11),
                (0.85, 13),
                (0.90, 16),
                (0.40, 30),
                (1.10, 10),
                (0.82, 17),
            ]
        )
        / 10.0,
        rel=1e-12,
    )


@pytest.mark.req("FR-014-35")
def test_the_wilson_intervals_of_the_two_fractions_match_scipy() -> None:
    from scipy.stats import binomtest

    s = il2_summary(kit.table("IL-2", "policy", ten_rows()))
    ref = binomtest(7, 10).proportion_ci(confidence_level=0.95, method="wilson")
    assert s["fraction_kf_ge_0_8_wilson"] == pytest.approx((ref.low, ref.high), rel=1e-9)
    ref2 = binomtest(2, 10).proportion_ci(confidence_level=0.95, method="wilson")
    assert s["fraction_stalled_wilson"] == pytest.approx((ref2.low, ref2.high), rel=1e-9)
    assert s["fraction_kf_ge_0_8_wilson"] == pytest.approx(wilson_interval(7, 10), rel=1e-12)


@pytest.mark.req("FR-014-35")
def test_a_hundred_episode_summary_and_the_acceptance_style_counts() -> None:
    rows = kit.dig_rows(100)
    for i in range(18):
        rows[i] = kit.dig_row(rows[i]["seed"], fill_factor=0.5, productivity_per_s=0.5 / 18.0)
    for i in range(18, 23):
        rows[i] = kit.dig_row(rows[i]["seed"], stalled=True)
    s = il2_summary(kit.table("IL-2", "policy", rows))
    assert s["fraction_kf_ge_0_8"] == pytest.approx(0.82, rel=1e-12)
    assert s["fraction_stalled"] == pytest.approx(0.05, rel=1e-12)
    assert s["fraction_kf_ge_0_8_wilson"][0] < 0.82 < s["fraction_kf_ge_0_8_wilson"][1]


# ----------------------------------------------------------------------------------------------- dig tables
def dig_pair(n=100, policy_rows=None, baseline_rows=None, policy="IL-2"):
    p = policy_rows if policy_rows is not None else kit.dig_rows(n)
    b = baseline_rows if baseline_rows is not None else kit.dig_rows(n)
    return kit.table(policy, "policy", p), kit.table(policy, "baseline", b)


@pytest.mark.req("FR-014-39")
def test_a_valid_dig_pair_passes_and_the_checks_apply_to_dig_tables() -> None:
    p, b = dig_pair()
    assert check_pair(p, b, seeds=kit.IL2_SEEDS_BLOCK) is None
    p, b = dig_pair(99)
    assert check_pair(p, b) == "fewer_than_100"
    rows = kit.dig_rows(100)
    rows[1] = kit.dig_row(rows[0]["seed"])
    p, b = dig_pair(policy_rows=rows)
    assert check_pair(p, b) == "duplicate_seed"
    p, b = dig_pair(baseline_rows=kit.dig_rows(100, start=kit.EVAL_START + 2))
    assert check_pair(p, b) == "seed_sets_differ"
    tuned = kit.dig_rows(
        100, start=2_000_000 - 80
    )  # eval-like count but overlapping the tuning range 2,000,000..2,000,019
    p, b = dig_pair(policy_rows=tuned, baseline_rows=kit.dig_rows(100, start=2_000_000 - 80))
    assert check_pair(p, b, seeds=kit.IL2_SEEDS_BLOCK) == "seeds_overlap_training"


@pytest.mark.req("FR-014-39")
@pytest.mark.parametrize("column", ["fill_factor", "cycle_time_s", "productivity_per_s"])
def test_a_nan_dig_metric_is_detected(column) -> None:
    rows = kit.dig_rows(100)
    rows[20] = {**rows[20], column: math.nan}
    p, b = dig_pair(policy_rows=rows)
    assert check_pair(p, b) == "nan_metric"


@pytest.mark.req("FR-014-39")
@pytest.mark.parametrize(
    "bad",
    [
        {"cycle_time_s": 0.0},  # exclusive minimum
        {"cycle_time_s": 31.0},  # above the 30 s limit
        {"fill_factor": 3.5},  # above the bound of 3
        {"fill_factor": -0.1},
        {"termination": "exploded"},
        {"stalled": "yes"},
        {"extra": 1},
    ],
)
def test_a_dig_row_that_violates_the_row_schema_is_a_schema_failure(bad) -> None:
    rows = kit.dig_rows(100)
    rows[3] = {**rows[3], **bad}
    p, b = dig_pair(policy_rows=rows)
    assert check_pair(p, b) == "schema"


@pytest.mark.req("FR-014-39")
def test_an_il1_column_set_on_a_dig_table_is_a_schema_failure() -> None:
    p, b = dig_pair()
    p["meta"]["column_set"] = "il1-episode"
    assert check_pair(p, b) == "schema"


@pytest.mark.req("FR-014-35")
def test_a_complete_il2_evaluation_reports_both_arms() -> None:
    p, b = dig_pair()
    rep = evaluate_il2(p, b, seeds=kit.IL2_SEEDS_BLOCK)
    assert rep["status"] == "complete"
    assert rep["failed_check"] is None
    assert rep["policy"]["n"] == rep["baseline"]["n"] == 100
    assert rep["policy"]["fraction_kf_ge_0_8"] == 1.0


@pytest.mark.req("FR-014-39")
def test_an_incomplete_il2_evaluation_gives_no_verdict() -> None:
    p, b = dig_pair(50)
    rep = evaluate_il2(p, b, seeds=kit.IL2_SEEDS_BLOCK)
    assert rep["status"] == "incomplete evaluation"
    assert rep["failed_check"] == "fewer_than_100"
    assert "verdicts" not in rep
    assert "sim_to_sim" not in rep

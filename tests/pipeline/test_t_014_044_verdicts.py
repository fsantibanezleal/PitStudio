# ruff: noqa: E501
"""T-014-044: per-metric verdicts: paired t for continuous metrics, Clopper-Pearson on the discordant episodes for binary metrics; no composite.

Requirements: FR-014-36, SC-014-04, SC-014-09.

Spec: specs/014-robot-learning/spec.md FR-014-36: "Each policy-versus-baseline comparison shall give a per-metric verdict by the decision rule of FR-000-05, with differences
oriented so that positive means the policy is better: for continuous metrics (IL-1 per-episode RMS lateral error, minimum TTC, energy; IL-2 productivity P), the paired
Student-t 95 % interval of the mean difference over the 100 episodes; for binary metrics (IL-1 success, IL-2 k_f >= 0.8), the exact Clopper-Pearson 95 % interval of b / (b +
c) over the discordant episodes, where 'better' requires its lower bound > 0.5; otherwise 'no significant difference'. No composite verdict shall be computed." FR-000-05: "better
than" only when the paired 95 % interval excludes 0, else "no significant difference". SC-014-04: "beats pure pursuit + PID" only by the decision rule, per metric. SC-014-09:
"beats scripted dig" only by the decision rule on the per-episode productivity P = k_f / t_c. Spec 8 (clarifications): there is no composite verdict (several axes, never one number).

Oracle: `scipy.stats.ttest_rel(...).confidence_interval(0.95)` and `scipy.stats.binomtest(b, b + c).proportion_ci(method="exact")` (the reference implementations named by the
plan), the plan's hand calculations (b = 8, c = 1 gives a lower bound 0.518 and "better"; b = 5, c = 0 gives 0.478 and "no significant difference"), and orientation by hand
(RMS lateral error and energy: a smaller value is better, so the difference is baseline - policy; minimum TTC clipped at 30 s and productivity: policy - baseline).

Convention (see the red report): a one-sided win of the baseline is reported as "worse" (the interval lies entirely on the unfavourable side); the spec defines only "better" and
"no significant difference".

Expected API of the implementation (module `pitstudio_pipeline.evaluate.il`, see T-014-042):
    verdicts_il1(policy, baseline, *, confidence=0.95) -> dict[str, dict]       keys exactly "rms_lateral_error", "min_ttc", "energy", "success"
    verdicts_il2(policy, baseline, *, confidence=0.95) -> dict[str, dict]       keys exactly "productivity", "fill_ge_0_8"
        each value: {"kind": "continuous" | "binary", "verdict": "better" | "worse" | "no significant difference", "ci": (lo, hi) | None, ...}
        continuous: "mean_difference" (positive = the policy is better), "ci" the Student-t interval of that mean, n = 100 pairs;
        binary: "b" (policy succeeds, baseline fails), "c" (the reverse), "ci" the exact Clopper-Pearson interval of b / (b + c) (None when b + c = 0).
        The verdict is "better" when ci[0] > 0 (continuous) or ci[0] > 0.5 (binary), "worse" when ci[1] < 0 or ci[1] < 0.5, else "no significant difference".
        The pair must pass check_pair (ValueError otherwise). No other key (no composite, no overall score) is present.
    evaluate_il1 / evaluate_il2 reports of a complete evaluation carry the same dict under "verdicts".
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.evaluate.il import evaluate_il1, evaluate_il2, verdicts_il1, verdicts_il2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import il_tables as kit

N = 100


def il1_pair(rms_p, rms_b, ttc_p, ttc_b, en_p, en_b, ok_p, ok_b):
    rows_p, rows_b = [], []
    for i in range(N):
        s = kit.EVAL_START + i
        rows_p.append(
            kit.il1_row(
                s,
                rms_lateral_error_m=float(rms_p[i]),
                min_ttc_s=float(ttc_p[i]),
                energy_kwh_per_t_km=float(en_p[i]),
                success=bool(ok_p[i]),
                collision=not bool(ok_p[i]),
                termination="success" if ok_p[i] else "collision",
            )
        )
        rows_b.append(
            kit.il1_row(
                s,
                rms_lateral_error_m=float(rms_b[i]),
                min_ttc_s=float(ttc_b[i]),
                energy_kwh_per_t_km=float(en_b[i]),
                success=bool(ok_b[i]),
                collision=not bool(ok_b[i]),
                termination="success" if ok_b[i] else "collision",
            )
        )
    return kit.table("IL-1", "policy", rows_p), kit.table("IL-1", "baseline", rows_b)


def base_arrays(seed=0):
    rng = np.random.default_rng(seed)
    return {
        "rms_b": rng.uniform(0.2, 0.8, N), "ttc_b": rng.uniform(1.0, 30.0, N), "en_b": rng.uniform(0.1, 0.3, N), "ok_b": np.ones(N, dtype=bool),
        "noise": rng.normal(0.0, 0.05, N),
    }  # fmt: skip


def clip30(x):
    return np.minimum(np.asarray(x, dtype=float), 30.0)


# ------------------------------------------------------------------------------------------ continuous metrics
@pytest.mark.req("FR-014-36")
def test_continuous_intervals_match_scipy_with_the_orientation_policy_better_is_positive() -> None:
    from scipy.stats import ttest_rel

    a = base_arrays(1)
    rms_p = a["rms_b"] - 0.10 + a["noise"]  # clearly lower than the baseline (better)
    ttc_p = np.minimum(a["ttc_b"] + 2.0 + a["noise"] * 10, 40.0)  # higher TTC (better), some above the 30 s clip
    en_p = a["en_b"] + 0.05 + a["noise"] * 0.1  # higher energy (worse)
    p, b = il1_pair(rms_p, a["rms_b"], ttc_p, a["ttc_b"], en_p, a["en_b"], a["ok_b"], a["ok_b"])
    v = verdicts_il1(p, b)
    assert set(v) == {"rms_lateral_error", "min_ttc", "energy", "success"}

    ref = ttest_rel(a["rms_b"], rms_p).confidence_interval(
        0.95
    )  # baseline - policy: positive means the policy is better
    assert v["rms_lateral_error"]["kind"] == "continuous"
    assert v["rms_lateral_error"]["ci"] == pytest.approx((ref.low, ref.high), rel=1e-9)
    assert v["rms_lateral_error"]["mean_difference"] == pytest.approx(float(np.mean(a["rms_b"] - rms_p)), rel=1e-12)
    assert v["rms_lateral_error"]["verdict"] == "better"

    ref = ttest_rel(clip30(ttc_p), clip30(a["ttc_b"])).confidence_interval(
        0.95
    )  # policy - baseline on the 30 s clipped values
    assert v["min_ttc"]["ci"] == pytest.approx((ref.low, ref.high), rel=1e-9)
    assert v["min_ttc"]["verdict"] == "better"

    ref = ttest_rel(a["en_b"], en_p).confidence_interval(
        0.95
    )  # baseline - policy: negative, the policy spends more energy
    assert v["energy"]["ci"] == pytest.approx((ref.low, ref.high), rel=1e-9)
    assert v["energy"]["ci"][1] < 0.0
    assert v["energy"]["verdict"] == "worse"


@pytest.mark.req("FR-014-36")
def test_an_interval_that_contains_zero_is_no_significant_difference() -> None:
    a = base_arrays(2)
    rms_p = a["rms_b"] + a["noise"]  # pure noise around the baseline
    p, b = il1_pair(rms_p, a["rms_b"], a["ttc_b"], a["ttc_b"], a["en_b"], a["en_b"], a["ok_b"], a["ok_b"])
    v = verdicts_il1(p, b)
    lo, hi = v["rms_lateral_error"]["ci"]
    assert lo < 0.0 < hi
    assert v["rms_lateral_error"]["verdict"] == "no significant difference"
    # identical TTC and energy arms: a zero-width interval at 0 is not "better"
    assert v["min_ttc"]["verdict"] == "no significant difference"
    assert v["energy"]["verdict"] == "no significant difference"
    assert v["energy"]["mean_difference"] == 0.0


@pytest.mark.req("FR-014-36")
def test_swapping_the_arms_negates_the_interval_and_exchanges_better_and_worse() -> None:
    a = base_arrays(3)
    rms_p = a["rms_b"] - 0.08 + a["noise"]
    p, b = il1_pair(rms_p, a["rms_b"], a["ttc_b"], a["ttc_b"], a["en_b"], a["en_b"], a["ok_b"], a["ok_b"])
    fwd = verdicts_il1(p, b)["rms_lateral_error"]
    rev_p, rev_b = il1_pair(a["rms_b"], rms_p, a["ttc_b"], a["ttc_b"], a["en_b"], a["en_b"], a["ok_b"], a["ok_b"])
    rev = verdicts_il1(rev_p, rev_b)["rms_lateral_error"]
    assert fwd["verdict"] == "better"
    assert rev["verdict"] == "worse"
    assert rev["ci"] == pytest.approx((-fwd["ci"][1], -fwd["ci"][0]), rel=1e-9)
    assert rev["mean_difference"] == pytest.approx(-fwd["mean_difference"], rel=1e-12)


@pytest.mark.req("FR-014-36")
def test_the_minimum_ttc_is_clipped_at_30_seconds_before_the_statistics() -> None:
    from scipy.stats import ttest_rel

    a = base_arrays(4)
    ttc_b = np.full(N, 31.0)  # an unclipped difference would show a large effect
    ttc_p = np.full(N, math.inf)
    ttc_p[:50] = 1000.0
    ttc_p[50:] = 45.0
    p, b = il1_pair(a["rms_b"], a["rms_b"], ttc_p, ttc_b, a["en_b"], a["en_b"], a["ok_b"], a["ok_b"])
    m = verdicts_il1(p, b)["min_ttc"]
    assert m["mean_difference"] == 0.0  # both clip to 30 s
    assert m["verdict"] == "no significant difference"
    ttc_p2 = a["ttc_b"] - 1.0 + a["noise"]
    p, b = il1_pair(a["rms_b"], a["rms_b"], ttc_p2, a["ttc_b"], a["en_b"], a["en_b"], a["ok_b"], a["ok_b"])
    ref = ttest_rel(clip30(ttc_p2), clip30(a["ttc_b"])).confidence_interval(0.95)
    assert verdicts_il1(p, b)["min_ttc"]["ci"] == pytest.approx((ref.low, ref.high), rel=1e-9)


# --------------------------------------------------------------------------------------------- binary metric
def success_pair(b_wins: int, c_wins: int, both_ok: int = 20):
    """b_wins episodes: policy succeeds, baseline fails; c_wins: the reverse; both_ok: both succeed; the rest both fail."""
    ok_p = np.zeros(N, dtype=bool)
    ok_b = np.zeros(N, dtype=bool)
    ok_p[:b_wins] = True
    ok_b[b_wins : b_wins + c_wins] = True
    ok_p[b_wins + c_wins : b_wins + c_wins + both_ok] = True
    ok_b[b_wins + c_wins : b_wins + c_wins + both_ok] = True
    a = base_arrays(5)
    return il1_pair(a["rms_b"], a["rms_b"], a["ttc_b"], a["ttc_b"], a["en_b"], a["en_b"], ok_p, ok_b)


@pytest.mark.req("FR-014-36")
@pytest.mark.parametrize(
    ("b_wins", "c_wins", "verdict"),
    [
        (8, 1, "better"),
        (5, 0, "no significant difference"),
        (1, 8, "worse"),
        (3, 3, "no significant difference"),
        (30, 2, "better"),
    ],
)
def test_the_exact_clopper_pearson_interval_on_the_discordant_episodes(b_wins, c_wins, verdict) -> None:
    from scipy.stats import binomtest

    p, b = success_pair(b_wins, c_wins)
    s = verdicts_il1(p, b)["success"]
    ref = binomtest(b_wins, b_wins + c_wins).proportion_ci(confidence_level=0.95, method="exact")
    assert s["kind"] == "binary"
    assert (s["b"], s["c"]) == (b_wins, c_wins)
    assert s["ci"] == pytest.approx((ref.low, ref.high), rel=1e-9)
    assert s["verdict"] == verdict


@pytest.mark.req("FR-014-36")
def test_the_plan_hand_calculations_8_to_1_is_better_and_5_to_0_is_not() -> None:
    p, b = success_pair(8, 1)
    s = verdicts_il1(p, b)["success"]
    assert s["ci"][0] == pytest.approx(0.518, abs=1e-3)  # lower bound 0.518 > 0.5
    assert s["verdict"] == "better"
    p, b = success_pair(5, 0)
    s = verdicts_il1(p, b)["success"]
    assert s["ci"][0] == pytest.approx(
        0.478, abs=1e-3
    )  # the exact lower bound of 5 / 5 is 0.025 ** (1 / 5) = 0.478 < 0.5
    assert s["verdict"] == "no significant difference"


@pytest.mark.req("FR-014-36")
def test_without_discordant_episodes_the_binary_verdict_is_no_significant_difference() -> None:
    p, b = success_pair(0, 0, both_ok=90)
    s = verdicts_il1(p, b)["success"]
    assert (s["b"], s["c"]) == (0, 0)
    assert s["ci"] is None
    assert s["verdict"] == "no significant difference"


@pytest.mark.req("FR-014-36")
def test_concordant_episodes_do_not_enter_the_binary_interval() -> None:
    p1, b1 = success_pair(8, 1, both_ok=0)
    p2, b2 = success_pair(8, 1, both_ok=70)
    s1, s2 = verdicts_il1(p1, b1)["success"], verdicts_il1(p2, b2)["success"]
    assert s1["ci"] == pytest.approx(s2["ci"], rel=1e-12)
    assert s1["verdict"] == s2["verdict"]


# --------------------------------------------------------------------------------------------- no composite
@pytest.mark.req("FR-014-36")
@pytest.mark.req("SC-014-04")
def test_there_is_no_composite_verdict_and_every_entry_has_its_own_rule() -> None:
    a = base_arrays(6)
    p, b = il1_pair(
        a["rms_b"] - 0.1, a["rms_b"], a["ttc_b"], a["ttc_b"], a["en_b"] + 0.1, a["en_b"], a["ok_b"], a["ok_b"]
    )
    v = verdicts_il1(p, b)
    assert not {"overall", "composite", "score", "winner", "beats", "total"} & set(v)
    assert {x["verdict"] for x in v.values()} <= {"better", "worse", "no significant difference"}
    assert v["rms_lateral_error"]["verdict"] == "better"
    assert v["energy"]["verdict"] == "worse"  # the axes disagree: no single number summarises them


# ------------------------------------------------------------------------------------------------- IL-2
def dig_pair(kf_p, kf_b, tc_p, tc_b):
    rows_p, rows_b = [], []
    for i in range(N):
        s = kit.EVAL_START + i
        rows_p.append(
            kit.dig_row(
                s, fill_factor=float(kf_p[i]), cycle_time_s=float(tc_p[i]), productivity_per_s=float(kf_p[i] / tc_p[i])
            )
        )
        rows_b.append(
            kit.dig_row(
                s, fill_factor=float(kf_b[i]), cycle_time_s=float(tc_b[i]), productivity_per_s=float(kf_b[i] / tc_b[i])
            )
        )
    return kit.table("IL-2", "policy", rows_p), kit.table("IL-2", "baseline", rows_b)


@pytest.mark.req("SC-014-09")
@pytest.mark.req("FR-014-36")
def test_il2_productivity_is_k_f_over_t_c_per_episode_and_not_the_product() -> None:
    from scipy.stats import ttest_rel

    rng = np.random.default_rng(7)
    kf_b = rng.uniform(0.6, 1.0, N)
    tc_b = rng.uniform(12.0, 20.0, N)
    kf_p = np.clip(kf_b + rng.normal(0.02, 0.05, N), 0.1, 1.1)
    tc_p = tc_b * rng.uniform(0.7, 0.9, N)  # faster cycles
    p, b = dig_pair(kf_p, kf_b, tc_p, tc_b)
    v = verdicts_il2(p, b)
    assert set(v) == {"productivity", "fill_ge_0_8"}
    ref = ttest_rel(kf_p / tc_p, kf_b / tc_b).confidence_interval(0.95)
    assert v["productivity"]["ci"] == pytest.approx((ref.low, ref.high), rel=1e-9)
    assert v["productivity"]["verdict"] == "better"
    # a literal product k_f * t_c would reward SLOWER cycles: the verdict must not follow that statistic
    wrong = ttest_rel(kf_p * tc_p, kf_b * tc_b).confidence_interval(0.95)
    assert (
        wrong.high < v["productivity"]["ci"][0]
    )  # the product statistic points the other way (slower cycles score higher)
    assert v["productivity"]["mean_difference"] > 0.0


@pytest.mark.req("FR-014-36")
def test_il2_fill_binary_metric_uses_the_k_f_threshold_0_8_on_discordant_episodes() -> None:
    from scipy.stats import binomtest

    kf_p = np.full(N, 0.9)
    kf_b = np.full(N, 0.9)
    kf_b[:12] = 0.7  # policy >= 0.8, baseline below: 12 discordant in the policy's favour
    kf_p[12:14] = 0.79  # policy below 0.8, baseline above: 2 discordant the other way
    kf_b[14] = 0.8  # exactly 0.8 counts as filled
    kf_p[14] = 0.8
    tc = np.full(N, 15.0)
    p, b = dig_pair(kf_p, kf_b, tc, tc)
    s = verdicts_il2(p, b)["fill_ge_0_8"]
    assert (s["b"], s["c"]) == (12, 2)
    ref = binomtest(12, 14).proportion_ci(confidence_level=0.95, method="exact")
    assert s["ci"] == pytest.approx((ref.low, ref.high), rel=1e-9)
    assert s["verdict"] == ("better" if ref.low > 0.5 else "no significant difference")


@pytest.mark.req("FR-014-36")
def test_equal_il2_arms_give_no_significant_difference_everywhere() -> None:
    rng = np.random.default_rng(8)
    kf = rng.uniform(0.6, 1.0, N)
    tc = rng.uniform(12.0, 20.0, N)
    p, b = dig_pair(kf, kf, tc, tc)
    v = verdicts_il2(p, b)
    assert v["productivity"]["verdict"] == "no significant difference"
    assert v["fill_ge_0_8"]["verdict"] == "no significant difference"
    assert v["productivity"]["mean_difference"] == 0.0


# ------------------------------------------------------------------------------------- reports and hostile
@pytest.mark.req("FR-014-36")
def test_a_complete_evaluation_carries_the_verdicts_and_an_incomplete_one_does_not() -> None:
    a = base_arrays(9)
    p, b = il1_pair(a["rms_b"] - 0.1, a["rms_b"], a["ttc_b"], a["ttc_b"], a["en_b"], a["en_b"], a["ok_b"], a["ok_b"])
    rep = evaluate_il1(p, b, seeds=kit.IL1_SEEDS_BLOCK)
    assert rep["status"] == "complete"
    assert rep["verdicts"] == verdicts_il1(p, b)
    p_short = kit.table("IL-1", "policy", p["rows"][:50])
    b_short = kit.table("IL-1", "baseline", b["rows"][:50])
    rep = evaluate_il1(p_short, b_short, seeds=kit.IL1_SEEDS_BLOCK)
    assert rep["status"] == "incomplete evaluation"
    assert "verdicts" not in rep
    with pytest.raises(ValueError, match=r"fewer_than_100|100"):
        verdicts_il1(p_short, b_short)


@pytest.mark.req("FR-014-36")
def test_il2_reports_carry_verdicts_too() -> None:
    kf = np.full(N, 0.9)
    tc = np.full(N, 15.0)
    p, b = dig_pair(kf, kf, tc, tc)
    rep = evaluate_il2(p, b, seeds=kit.IL2_SEEDS_BLOCK)
    assert rep["status"] == "complete"
    assert set(rep["verdicts"]) == {"productivity", "fill_ge_0_8"}


@pytest.mark.req("FR-014-36")
@pytest.mark.parametrize("bad", [0.0, 1.0, -0.5, 1.5, math.nan])
def test_an_invalid_confidence_level_raises_value_error_naming_it(bad) -> None:
    a = base_arrays(10)
    p, b = il1_pair(a["rms_b"], a["rms_b"], a["ttc_b"], a["ttc_b"], a["en_b"], a["en_b"], a["ok_b"], a["ok_b"])
    with pytest.raises(ValueError, match=r"\bconfidence\b"):
        verdicts_il1(p, b, confidence=bad)


@pytest.mark.req("FR-014-36")
def test_a_wider_confidence_level_gives_a_wider_interval() -> None:
    a = base_arrays(11)
    p, b = il1_pair(
        a["rms_b"] - 0.02 + a["noise"], a["rms_b"], a["ttc_b"], a["ttc_b"], a["en_b"], a["en_b"], a["ok_b"], a["ok_b"]
    )
    narrow = verdicts_il1(p, b, confidence=0.90)["rms_lateral_error"]["ci"]
    wide = verdicts_il1(p, b, confidence=0.99)["rms_lateral_error"]["ci"]
    assert wide[0] < narrow[0] < narrow[1] < wide[1]

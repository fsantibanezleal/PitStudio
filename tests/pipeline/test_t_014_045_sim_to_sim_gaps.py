# ruff: noqa: E501
"""T-014-045: sim-to-sim gaps (twin and MPM) with paired t-intervals.

Requirements: FR-014-37, FR-014-38, SC-014-05, SC-014-08.

Spec: specs/014-robot-learning/spec.md FR-014-37: "The IL-1 sim-to-sim gap shall run the exported policy on the Python reference twin (FR-014-40) with the same 100 seeds, and
report for success, per-episode RMS lateral error and minimum TTC the mean paired difference Delta = twin - Isaac Lab with its paired 95 % t-interval, labelled 'sim-to-sim gap'
and never tested for superiority." FR-014-38: "The FEE -> MPM gap shall be the mean of Delta_j = k_f,MPM,j - k_f,FEE,j over the n paired MPM episodes (16 <= n <= 64) with the 95 %
interval Delta_bar +- t_{0.975,n-1} s_Delta / sqrt(n), labelled 'sim-to-sim gap'." FR-014-23: with fewer than 16 completed MPM episodes IL-2b is "not run" and no gap is published.
SC-014-05, SC-014-08: the gaps are reported with their 95 % CI (or "not run").

Oracle: (1) hand calculation on 5-pair fixtures (plan: "t-interval by hand on 5-pair fixtures"): RMS differences (0.1, 0.2, 0.0, -0.1, 0.3) have mean 0.1, deviations (0, 0.1, -0.1,
-0.2, 0.2), sum of squares 0.10, variance 0.025, s = 0.158114, se = 0.0707107, and t_{0.975,4} = 2.776445, so the interval is 0.1 +- 0.196324 = (-0.096324, 0.296324); success 0/1
differences (0, -1, 0, 0, 0): mean -0.2, s = 0.447214, se = 0.2, interval -0.2 +- 0.555289; minimum TTC clipped at 30 s: policy (inf, 10, 5, 40, 2) and twin (30, 12, 4, 20, 3)
clip to (30, 10, 5, 30, 2) and (30, 12, 4, 20, 3), differences (0, 2, -1, -10, 1), mean -1.6; (2) n = 16 MPM pairs with Delta = +0.1 (8 times) and -0.1 (8 times): mean 0, s =
0.1 sqrt(16 / 15) = 0.103280, se = 0.0258199, t_{0.975,15} = 2.131450, half-width 0.055033; (3) `scipy.stats.t.ppf` and `ttest_rel(...).confidence_interval` for the generic cases.

Expected API of the implementation (module `pitstudio_pipeline.evaluate.il`, see T-014-042):
    sim_to_sim_gap_il1(policy, twin) -> dict
        policy: the IL-1 policy table (Isaac Lab arm), twin: the table of the same policy on the reference twin (meta arm "twin"). Returns {"label": "sim-to-sim gap", "status":
        "complete", "n": int, "success": G, "rms_lateral_error": G, "min_ttc": G} with G = {"mean_difference": Delta_bar, "ci": (lo, hi)}, Delta = twin - policy per episode (success as
        0 / 1, minimum TTC clipped at 30 s) and the paired Student-t 95 % interval; no "verdict" and no "p_value" key anywhere (never tested for superiority). When the pair fails a check of
        check_pair (acceptance=False, the seed block not needed) the result is {"label": ..., "status": "incomplete evaluation", "failed_check": name} without a metric key.
    fee_mpm_gap(fee, mpm) -> dict
        fee: the IL-2 policy table on FEE soil (100 episodes), mpm: the IL-2b table (meta arm "mpm", 16 to 64 rows) whose seeds are the first n seeds of the FEE table in ascending seed
        order. Returns {"label": "sim-to-sim gap", "status": "complete", "n": n, "mean_difference": Delta_bar, "ci": (lo, hi)}, Delta_j = k_f,MPM,j - k_f,FEE,j paired by seed, the
        interval Delta_bar +- t_{0.975,n-1} s / sqrt(n). mpm is None, or fewer than 16 MPM rows (checked before the schema, which also demands 16): {"label": ..., "status": "not run", "reason": <text>} without "mean_difference" or "ci". MPM seeds that are not the first
        n seeds of the FEE table: status "incomplete evaluation" with failed_check "mpm_seeds_not_first_n"; a NaN metric: "nan_metric"; a schema failure: "schema".
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.evaluate.il import fee_mpm_gap, sim_to_sim_gap_il1

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import il_tables as kit

SEEDS5 = list(range(10, 15))


def five(policy_vals, twin_vals, field, make=kit.il1_row):
    rp = [make(s, **{field: v}) for s, v in zip(SEEDS5, policy_vals, strict=True)]
    rt = [make(s, **{field: v}) for s, v in zip(SEEDS5, twin_vals, strict=True)]
    return kit.table("IL-1", "policy", rp), kit.table("IL-1", "twin", rt)


# ------------------------------------------------------------------------------------------------ IL-1 twin gap
@pytest.mark.req("FR-014-37")
def test_the_rms_gap_of_the_five_pair_hand_fixture() -> None:
    pol = [0.30, 0.25, 0.40, 0.35, 0.20]
    twin = [p + d for p, d in zip(pol, [0.1, 0.2, 0.0, -0.1, 0.3], strict=True)]
    p, t = five(pol, twin, "rms_lateral_error_m")
    g = sim_to_sim_gap_il1(p, t)
    assert g["label"] == "sim-to-sim gap"
    assert g["status"] == "complete"
    assert g["n"] == 5
    r = g["rms_lateral_error"]
    assert r["mean_difference"] == pytest.approx(0.1, rel=1e-9)
    assert r["ci"] == pytest.approx((-0.096324, 0.296324), abs=2e-6)  # 0.1 +- 2.776445 * 0.0707107 = 0.1 +- 0.196324


@pytest.mark.req("FR-014-37")
def test_the_success_gap_uses_zero_one_differences_twin_minus_policy() -> None:
    ok_p, ok_t = [True, True, True, False, True], [True, False, True, False, True]
    rp = [
        kit.il1_row(s, success=o, collision=not o, termination="success" if o else "collision")
        for s, o in zip(SEEDS5, ok_p, strict=True)
    ]
    rt = [
        kit.il1_row(s, success=o, collision=not o, termination="success" if o else "collision")
        for s, o in zip(SEEDS5, ok_t, strict=True)
    ]
    g = sim_to_sim_gap_il1(kit.table("IL-1", "policy", rp), kit.table("IL-1", "twin", rt))
    assert g["success"]["mean_difference"] == pytest.approx(
        -0.2, rel=1e-9
    )  # (0 - 1 + 0 + 0 + 0) / 5: the twin fails one more episode
    assert g["success"]["ci"] == pytest.approx((-0.755289, 0.355289), abs=2e-6)  # -0.2 +- 2.776445 * 0.2


@pytest.mark.req("FR-014-37")
def test_the_minimum_ttc_gap_clips_at_30_seconds_before_differencing() -> None:
    p, t = five([math.inf, 10.0, 5.0, 40.0, 2.0], [30.0, 12.0, 4.0, 20.0, 3.0], "min_ttc_s")
    g = sim_to_sim_gap_il1(p, t)
    assert g["min_ttc"]["mean_difference"] == pytest.approx(-1.6, rel=1e-9)  # clipped differences (0, 2, -1, -10, 1)


@pytest.mark.req("FR-014-37")
def test_generic_gaps_match_scipy_and_the_difference_is_twin_minus_policy() -> None:
    from scipy.stats import ttest_rel

    rng = np.random.default_rng(3)
    n = 100
    rms_p = rng.uniform(0.2, 0.6, n)
    rms_t = rms_p + rng.normal(0.05, 0.03, n)
    rows_p = [kit.il1_row(kit.EVAL_START + i, rms_lateral_error_m=float(rms_p[i])) for i in range(n)]
    rows_t = [kit.il1_row(kit.EVAL_START + i, rms_lateral_error_m=float(rms_t[i])) for i in range(n)]
    g = sim_to_sim_gap_il1(kit.table("IL-1", "policy", rows_p), kit.table("IL-1", "twin", rows_t))
    ref = ttest_rel(rms_t, rms_p).confidence_interval(0.95)  # twin - policy
    assert g["rms_lateral_error"]["ci"] == pytest.approx((ref.low, ref.high), rel=1e-9)
    assert g["rms_lateral_error"]["mean_difference"] == pytest.approx(float(np.mean(rms_t - rms_p)), rel=1e-12)
    assert (
        g["rms_lateral_error"]["mean_difference"] > 0.0
    )  # the sign is NOT flipped to "positive means better": a gap, not a verdict


@pytest.mark.req("FR-014-37")
def test_the_gap_is_never_tested_for_superiority() -> None:
    p, t = five([0.3] * 5, [0.5, 0.6, 0.4, 0.55, 0.45], "rms_lateral_error_m")
    g = sim_to_sim_gap_il1(p, t)

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)

    assert not {"verdict", "p_value", "pvalue", "significant", "better", "worse"} & set(keys(g))
    assert g["label"] == "sim-to-sim gap"


@pytest.mark.req("FR-014-39")
@pytest.mark.parametrize("case", ["differ", "duplicate", "nan", "schema"])
def test_an_invalid_pair_gives_incomplete_evaluation_and_no_gap(case) -> None:
    p, t = five([0.3] * 5, [0.4] * 5, "rms_lateral_error_m")
    want = {"differ": "seed_sets_differ", "duplicate": "duplicate_seed", "nan": "nan_metric", "schema": "schema"}[case]
    if case == "differ":
        t = kit.table("IL-1", "twin", [kit.il1_row(s + 1, rms_lateral_error_m=0.4) for s in SEEDS5])
    elif case == "duplicate":
        rows = [kit.il1_row(s, rms_lateral_error_m=0.4) for s in [10, 11, 12, 13, 13]]
        t = kit.table("IL-1", "twin", rows)
    elif case == "nan":
        rows = [kit.il1_row(s, rms_lateral_error_m=0.4) for s in SEEDS5]
        rows[2] = {**rows[2], "rms_lateral_error_m": math.nan}
        t = kit.table("IL-1", "twin", rows)
    else:
        t["meta"]["arm"] = "nonsense"
    g = sim_to_sim_gap_il1(p, t)
    assert g["status"] == "incomplete evaluation"
    assert g["failed_check"] == want
    assert g["label"] == "sim-to-sim gap"
    assert not {"success", "rms_lateral_error", "min_ttc"} & set(g)


@pytest.mark.req("FR-014-37")
def test_a_single_episode_pair_cannot_give_an_interval() -> None:
    rp = [kit.il1_row(10)]
    rt = [kit.il1_row(10, rms_lateral_error_m=0.9)]
    g = sim_to_sim_gap_il1(kit.table("IL-1", "policy", rp), kit.table("IL-1", "twin", rt))
    assert g["status"] == "incomplete evaluation"


# ---------------------------------------------------------------------------------------------- FEE -> MPM gap
def fee_table(kfs=None, n=100):
    kfs = kfs if kfs is not None else [0.9] * n
    rows = [
        kit.dig_row(kit.EVAL_START + i, fill_factor=float(kfs[i]), productivity_per_s=float(kfs[i]) / 18.0)
        for i in range(n)
    ]
    return kit.table("IL-2", "policy", rows)


def mpm_table(kfs, seeds=None):
    seeds = seeds if seeds is not None else [kit.EVAL_START + i for i in range(len(kfs))]
    rows = [
        kit.dig_row(s, fill_factor=float(k), productivity_per_s=float(k) / 18.0)
        for s, k in zip(seeds, kfs, strict=True)
    ]
    return kit.table("IL-2", "mpm", rows)


@pytest.mark.req("FR-014-38")
def test_the_gap_of_16_pairs_by_hand_calculation() -> None:
    kf_mpm = [1.0] * 8 + [0.8] * 8  # Delta = +0.1 and -0.1 against the FEE value 0.9
    g = fee_mpm_gap(fee_table(), mpm_table(kf_mpm))
    assert g["label"] == "sim-to-sim gap"
    assert g["status"] == "complete"
    assert g["n"] == 16
    assert g["mean_difference"] == pytest.approx(0.0, abs=1e-12)
    half = 2.131450 * 0.1 * math.sqrt(16.0 / 15.0) / 4.0  # 0.055033
    assert g["ci"] == pytest.approx((-half, half), abs=2e-6)


@pytest.mark.req("FR-014-38")
@pytest.mark.parametrize("n", [16, 17, 32, 63, 64])
def test_the_interval_is_mean_plus_minus_t_s_over_root_n_for_every_allowed_n(n) -> None:
    from scipy.stats import t

    rng = np.random.default_rng(n)
    kf_fee = rng.uniform(0.6, 1.1, 100)
    kf_mpm = np.clip(kf_fee[:n] + rng.normal(-0.1, 0.08, n), 0.0, 2.9)
    g = fee_mpm_gap(fee_table(kf_fee), mpm_table(kf_mpm))
    d = kf_mpm - kf_fee[:n]
    half = float(t.ppf(0.975, n - 1) * d.std(ddof=1) / math.sqrt(n))
    assert g["n"] == n
    assert g["mean_difference"] == pytest.approx(float(d.mean()), rel=1e-9)
    assert g["ci"] == pytest.approx((float(d.mean()) - half, float(d.mean()) + half), rel=1e-9)


@pytest.mark.req("FR-014-38")
def test_the_pairing_is_by_seed_and_not_by_row_order() -> None:
    rng = np.random.default_rng(1)
    kf_fee = rng.uniform(0.6, 1.1, 100)
    seeds = [kit.EVAL_START + i for i in range(20)]
    kf_mpm = kf_fee[:20] - 0.2
    order = list(range(20))[::-1]  # the MPM table lists its episodes in reverse order
    g = fee_mpm_gap(fee_table(kf_fee), mpm_table([kf_mpm[i] for i in order], seeds=[seeds[i] for i in order]))
    assert g["status"] == "complete"
    assert g["mean_difference"] == pytest.approx(-0.2, rel=1e-9)


@pytest.mark.req("FR-014-38")
def test_an_mpm_fill_above_the_fee_cap_is_accepted_up_to_three() -> None:
    g = fee_mpm_gap(fee_table(), mpm_table([1.4] * 16))
    assert g["status"] == "complete"
    assert g["mean_difference"] == pytest.approx(0.5, rel=1e-9)


@pytest.mark.req("FR-014-23")
@pytest.mark.parametrize("n", [0, 1, 8, 15])
def test_fewer_than_16_mpm_episodes_is_not_run_and_publishes_no_gap(n) -> None:
    mpm = (
        kit.table("IL-2", "mpm", [kit.dig_row(kit.EVAL_START + i) for i in range(n)])
        if n
        else {"meta": kit.meta("IL-2", "mpm", []), "rows": []}
    )
    g = fee_mpm_gap(fee_table(), mpm)
    assert g["status"] == "not run"
    assert g["label"] == "sim-to-sim gap"
    assert isinstance(g["reason"], str)
    assert g["reason"]
    assert not {"mean_difference", "ci"} & set(g)


@pytest.mark.req("FR-014-23")
def test_a_missing_mpm_table_is_not_run() -> None:
    g = fee_mpm_gap(fee_table(), None)
    assert g["status"] == "not run"
    assert g["reason"]
    assert not {"mean_difference", "ci"} & set(g)


@pytest.mark.req("FR-014-38")
def test_mpm_seeds_that_are_not_the_first_n_fee_seeds_are_rejected() -> None:
    g = fee_mpm_gap(
        fee_table(), mpm_table([0.9] * 16, seeds=[kit.EVAL_START + 1 + i for i in range(16)])
    )  # shifted by one
    assert g["status"] == "incomplete evaluation"
    assert g["failed_check"] == "mpm_seeds_not_first_n"
    g = fee_mpm_gap(
        fee_table(), mpm_table([0.9] * 16, seeds=[kit.EVAL_START + 2 * i for i in range(16)])
    )  # every second seed
    assert g["failed_check"] == "mpm_seeds_not_first_n"
    g = fee_mpm_gap(fee_table(), mpm_table([0.9] * 16, seeds=[5_000_000 + i for i in range(16)]))  # unrelated seeds
    assert g["failed_check"] == "mpm_seeds_not_first_n"


@pytest.mark.req("FR-014-39")
def test_hostile_mpm_tables_give_incomplete_evaluation() -> None:
    kf = [0.9] * 16
    kf[3] = math.nan
    assert fee_mpm_gap(fee_table(), mpm_table(kf))["failed_check"] == "nan_metric"
    bad = mpm_table([0.9] * 16)
    bad["meta"]["arm"] = "twin"  # the twin arm belongs to IL-1
    assert fee_mpm_gap(fee_table(), bad)["failed_check"] == "schema"
    too_many = mpm_table([0.9] * 65)
    assert fee_mpm_gap(fee_table(), too_many)["failed_check"] == "schema"  # the contract allows 16 to 64 rows
    dup = mpm_table([0.9] * 16, seeds=[kit.EVAL_START] * 16)
    assert fee_mpm_gap(fee_table(), dup)["failed_check"] == "duplicate_seed"
    fee_nan = fee_table([0.9] * 3 + [math.nan] + [0.9] * 96)
    assert fee_mpm_gap(fee_nan, mpm_table([0.9] * 16))["failed_check"] == "nan_metric"
    short_fee = fee_table(n=10)
    assert fee_mpm_gap(short_fee, mpm_table([0.9] * 16))["status"] in ("incomplete evaluation", "not run")

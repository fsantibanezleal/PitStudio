# ruff: noqa: E501
"""T-014-047: acceptance table builder: observed rates against the pre-registered thresholds, with intervals reported alongside.

Requirements: SC-014-01, SC-014-02, SC-014-03, SC-014-06, SC-014-07 (and SC-014-05, SC-014-08 as reported rows).

Spec: specs/014-robot-learning/spec.md section 5: SC-014-01 IL-1 route success >= 95 % over 100 seeded episodes (observed rate; Wilson interval reported with it); SC-014-02 pooled RMS lateral
error <= 0.5 m; SC-014-03 minimum TTC >= 3 s in >= 99 % of episodes (at most 1 of 100 below 3 s); SC-014-06 fill factor >= 0.8 in >= 80 % of FEE episodes; SC-014-07 stalls <= 5 % of
episodes; SC-014-05 the sim-to-sim gap reported with its 95 % CI; SC-014-08 the FEE -> MPM gap reported with its CI or "not run". "Pre-registered": the thresholds are constants fixed in the
specification, never derived from a run.

Oracle: hand-built 100-episode tables whose rates are set to the boundary (95 of 100, 94 of 100, a pooled RMS of exactly 0.5 m, 1 and 2 of 100 episodes below 3 s, 80 and 79 filled,
5 and 6 stalled) and the Wilson interval of `scipy.stats.binomtest(...).proportion_ci(method="wilson")` for the intervals reported alongside.

Expected API of the implementation (module `pitstudio_pipeline.evaluate.il`, see T-014-042):
    ACCEPTANCE_THRESHOLDS: dict {"SC-014-01": 0.95, "SC-014-02": 0.5, "SC-014-03": 0.99, "SC-014-06": 0.80, "SC-014-07": 0.05}
    check_table(table, *, acceptance=True) -> str | None          the single-table form of check_pair (schema, seed_set_sha256, duplicate_seed, nan_metric, fewer_than_100)
    acceptance_table_il1(table, *, gap=None) -> dict
    acceptance_table_il2(table, *, mpm_gap=None) -> dict
        {"status": "complete", "failed_check": None, "rows": [row, ...]} ordered by id, or {"status": "incomplete evaluation", "failed_check": name} without rows.
        row: {"id", "metric", "observed", "threshold", "comparison" (">=" or "<="), "met" (bool, decided on the OBSERVED value), "interval" ((lo, hi) Wilson 95 % for a rate, None for the pooled
        RMS)}. IL-1 rows: SC-014-01, SC-014-02, SC-014-03, SC-014-05. IL-2 rows: SC-014-06, SC-014-07, SC-014-08. SC-014-05 / SC-014-08 rows have "reported" (True only when the
        given gap dict has status "complete") and "interval" (the gap's ci or None), "state" ("complete", "not run" or "incomplete evaluation" copied from the gap, "missing" when the gap is None),
        and no "met".
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest
from pitstudio_pipeline.evaluate.il import (
    ACCEPTANCE_THRESHOLDS,
    acceptance_table_il1,
    acceptance_table_il2,
    check_table,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import il_tables as kit


def by_id(rows):
    return {r["id"]: r for r in rows}


def il1_with(n_success=95, n_below_3s=0, pooled_rms=0.1):
    rows = kit.il1_rows(100)
    out = []
    steps = 1000
    for i, r in enumerate(rows):
        ok = i < n_success
        out.append(
            kit.il1_row(
                r["seed"], success=ok, collision=not ok, termination="success" if ok else "collision", steps=steps,
                sum_sq_lateral_error_m2=pooled_rms**2 * steps, rms_lateral_error_m=pooled_rms,
                min_ttc_s=1.0 if i >= 100 - n_below_3s else math.inf,
            )
        )  # fmt: skip
    return kit.table("IL-1", "policy", out)


def il2_with(n_filled=80, n_stalled=5):
    rows = [
        kit.dig_row(kit.EVAL_START + i, fill_factor=0.9 if i < n_filled else 0.5, stalled=i < n_stalled)
        for i in range(100)
    ]
    return kit.table("IL-2", "policy", rows)


# ------------------------------------------------------------------------------------------------ thresholds
@pytest.mark.req("SC-014-01")
def test_the_thresholds_are_the_pre_registered_constants() -> None:
    assert ACCEPTANCE_THRESHOLDS == {
        "SC-014-01": 0.95,
        "SC-014-02": 0.5,
        "SC-014-03": 0.99,
        "SC-014-06": 0.80,
        "SC-014-07": 0.05,
    }


@pytest.mark.req("SC-014-01")
def test_the_thresholds_do_not_depend_on_the_data() -> None:
    a = acceptance_table_il1(il1_with(100, 0, 0.01))
    b = acceptance_table_il1(il1_with(10, 50, 3.0))
    for key, want in (("SC-014-01", 0.95), ("SC-014-02", 0.5), ("SC-014-03", 0.99)):
        assert by_id(a["rows"])[key]["threshold"] == want
        assert by_id(b["rows"])[key]["threshold"] == want


# ------------------------------------------------------------------------------------------------ IL-1
@pytest.mark.req("SC-014-01")
@pytest.mark.parametrize(("n_ok", "met"), [(100, True), (96, True), (95, True), (94, False), (50, False), (0, False)])
def test_sc_014_01_route_success_at_least_95_percent_on_the_observed_rate(n_ok, met) -> None:
    from scipy.stats import binomtest

    row = by_id(acceptance_table_il1(il1_with(n_success=n_ok))["rows"])["SC-014-01"]
    assert row["observed"] == pytest.approx(n_ok / 100.0, rel=1e-12)
    assert row["comparison"] == ">="
    assert row["met"] is met
    ref = binomtest(n_ok, 100).proportion_ci(confidence_level=0.95, method="wilson")
    assert row["interval"] == pytest.approx(
        (ref.low, ref.high), rel=1e-9
    )  # reported alongside, not used for the decision
    if n_ok == 95:
        assert (
            row["interval"][0] < 0.95
        )  # the point estimate meets the threshold although the interval reaches below it


@pytest.mark.req("SC-014-02")
@pytest.mark.parametrize(("rms", "met"), [(0.1, True), (0.5, True), (0.5001, False), (2.0, False)])
def test_sc_014_02_pooled_rms_at_most_half_a_metre(rms, met) -> None:
    row = by_id(acceptance_table_il1(il1_with(pooled_rms=rms))["rows"])["SC-014-02"]
    assert row["observed"] == pytest.approx(rms, rel=1e-9)
    assert row["comparison"] == "<="
    assert row["met"] is met
    assert row["interval"] is None


@pytest.mark.req("SC-014-03")
@pytest.mark.parametrize(("below", "met"), [(0, True), (1, True), (2, False), (10, False)])
def test_sc_014_03_minimum_ttc_at_least_3_s_in_at_least_99_percent_of_episodes(below, met) -> None:
    from scipy.stats import binomtest

    row = by_id(acceptance_table_il1(il1_with(n_below_3s=below))["rows"])["SC-014-03"]
    assert row["observed"] == pytest.approx((100 - below) / 100.0, rel=1e-12)
    assert row["comparison"] == ">="
    assert row["met"] is met
    ref = binomtest(100 - below, 100).proportion_ci(confidence_level=0.95, method="wilson")
    assert row["interval"] == pytest.approx((ref.low, ref.high), rel=1e-9)


@pytest.mark.req("SC-014-03")
def test_episodes_without_a_closing_light_vehicle_count_as_at_least_3_s() -> None:
    rows = kit.il1_rows(100, min_ttc_s=math.inf)
    row = by_id(acceptance_table_il1(kit.table("IL-1", "policy", rows))["rows"])["SC-014-03"]
    assert row["observed"] == 1.0
    assert row["met"] is True


@pytest.mark.req("SC-014-01")
def test_the_il1_table_has_exactly_the_documented_rows_in_id_order() -> None:
    t = acceptance_table_il1(il1_with())
    assert t["status"] == "complete"
    assert t["failed_check"] is None
    assert [r["id"] for r in t["rows"]] == ["SC-014-01", "SC-014-02", "SC-014-03", "SC-014-05"]
    for r in t["rows"][:3]:
        assert set(r) >= {"id", "metric", "observed", "threshold", "comparison", "met", "interval"}
        assert isinstance(r["met"], bool)


@pytest.mark.req("SC-014-05")
def test_the_sim_to_sim_row_reports_the_gap_interval_and_never_a_verdict() -> None:
    gap = {
        "label": "sim-to-sim gap",
        "status": "complete",
        "n": 100,
        "rms_lateral_error": {"mean_difference": 0.05, "ci": (0.02, 0.08)},
    }
    row = by_id(acceptance_table_il1(il1_with(), gap=gap)["rows"])["SC-014-05"]
    assert row["reported"] is True
    assert row["state"] == "complete"
    assert "met" not in row
    assert acceptance_table_il1(il1_with(), gap=None)["rows"][3]["reported"] is False
    assert acceptance_table_il1(il1_with(), gap=None)["rows"][3]["state"] == "missing"
    bad = {"label": "sim-to-sim gap", "status": "incomplete evaluation", "failed_check": "seed_sets_differ"}
    r = by_id(acceptance_table_il1(il1_with(), gap=bad)["rows"])["SC-014-05"]
    assert r["reported"] is False
    assert r["state"] == "incomplete evaluation"


# ------------------------------------------------------------------------------------------------ IL-2
@pytest.mark.req("SC-014-06")
@pytest.mark.parametrize(("n_filled", "met"), [(100, True), (81, True), (80, True), (79, False), (0, False)])
def test_sc_014_06_fill_factor_at_least_0_8_in_at_least_80_percent_of_episodes(n_filled, met) -> None:
    from scipy.stats import binomtest

    row = by_id(acceptance_table_il2(il2_with(n_filled=n_filled))["rows"])["SC-014-06"]
    assert row["observed"] == pytest.approx(n_filled / 100.0, rel=1e-12)
    assert row["comparison"] == ">="
    assert row["met"] is met
    ref = binomtest(n_filled, 100).proportion_ci(confidence_level=0.95, method="wilson")
    assert row["interval"] == pytest.approx((ref.low, ref.high), rel=1e-9)


@pytest.mark.req("SC-014-07")
@pytest.mark.parametrize(("n_stalled", "met"), [(0, True), (4, True), (5, True), (6, False), (50, False)])
def test_sc_014_07_stalls_at_most_5_percent_of_episodes(n_stalled, met) -> None:
    from scipy.stats import binomtest

    row = by_id(acceptance_table_il2(il2_with(n_stalled=n_stalled))["rows"])["SC-014-07"]
    assert row["observed"] == pytest.approx(n_stalled / 100.0, rel=1e-12)
    assert row["comparison"] == "<="
    assert row["met"] is met
    ref = binomtest(n_stalled, 100).proportion_ci(confidence_level=0.95, method="wilson")
    assert row["interval"] == pytest.approx((ref.low, ref.high), rel=1e-9)


@pytest.mark.req("SC-014-08")
def test_the_il2_table_has_the_documented_rows_and_the_mpm_row_reports_the_gap_or_not_run() -> None:
    t = acceptance_table_il2(il2_with())
    assert [r["id"] for r in t["rows"]] == ["SC-014-06", "SC-014-07", "SC-014-08"]
    gap = {"label": "sim-to-sim gap", "status": "complete", "n": 32, "mean_difference": -0.05, "ci": (-0.09, -0.01)}
    row = by_id(acceptance_table_il2(il2_with(), mpm_gap=gap)["rows"])["SC-014-08"]
    assert row["reported"] is True
    assert row["state"] == "complete"
    assert row["interval"] == (-0.09, -0.01)
    assert "met" not in row
    nr = {"label": "sim-to-sim gap", "status": "not run", "reason": "fewer than 16 MPM episodes completed"}
    row = by_id(acceptance_table_il2(il2_with(), mpm_gap=nr)["rows"])["SC-014-08"]
    assert row["reported"] is False
    assert row["state"] == "not run"
    assert row["interval"] is None
    assert by_id(acceptance_table_il2(il2_with(), mpm_gap=None)["rows"])["SC-014-08"]["state"] == "missing"


# ------------------------------------------------------------------------------------------- incomplete tables
@pytest.mark.req("SC-014-01")
def test_a_table_with_fewer_than_100_episodes_gives_no_acceptance_rows() -> None:
    short = kit.table("IL-1", "policy", kit.il1_rows(60))
    t = acceptance_table_il1(short)
    assert t["status"] == "incomplete evaluation"
    assert t["failed_check"] == "fewer_than_100"
    assert "rows" not in t
    assert check_table(short) == "fewer_than_100"
    assert check_table(short, acceptance=False) is None


@pytest.mark.req("SC-014-01")
@pytest.mark.parametrize(
    ("case", "check"),
    [("duplicate", "duplicate_seed"), ("nan", "nan_metric"), ("schema", "schema"), ("digest", "seed_set_sha256")],
)
def test_hostile_single_tables_give_no_rows(case, check) -> None:
    rows = kit.il1_rows(100)
    tab = kit.table("IL-1", "policy", rows)
    if case == "duplicate":
        rows[5] = kit.il1_row(rows[4]["seed"])
        tab = kit.table("IL-1", "policy", rows)
    elif case == "nan":
        rows[5] = {**rows[5], "rms_lateral_error_m": math.nan}
        tab = kit.table("IL-1", "policy", rows)
    elif case == "schema":
        tab["meta"]["arm"] = "nonsense"
    else:
        tab["meta"]["seed_set_sha256"] = "2" * 64
    assert check_table(tab) == check
    t = acceptance_table_il1(tab)
    assert t["status"] == "incomplete evaluation"
    assert t["failed_check"] == check
    assert "rows" not in t


@pytest.mark.req("SC-014-06")
def test_the_il2_incomplete_table_gives_no_rows_either() -> None:
    t = acceptance_table_il2(kit.table("IL-2", "policy", kit.dig_rows(40)))
    assert t["status"] == "incomplete evaluation"
    assert "rows" not in t


@pytest.mark.req("SC-014-01")
def test_an_il1_table_given_to_the_il2_builder_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\bpolicy\b|column_set"):
        acceptance_table_il2(il1_with())
    with pytest.raises(ValueError, match=r"\bpolicy\b|column_set"):
        acceptance_table_il1(il2_with())

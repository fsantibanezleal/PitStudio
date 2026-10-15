# ruff: noqa: E501
"""T-014-048: optional IL-3 loader: evaluated with IL-2's metrics and protocol when trained, "not run" otherwise.

Requirements: FR-014-24.

Spec: specs/014-robot-learning/spec.md FR-014-24: "Where IL-3 is trained, it shall be evaluated and published with IL-2's metrics and protocol; otherwise its panel shall show 'not run'." IL-3 shares IL-2's dig
code and has no MPM tier and no twin (clarification of 2026-10-07: task id `Pit-Loader-Dig-FEE`, 46 observations, 4 actions, no MPM tier or twin).

Oracle: the IL-2 evaluation of T-014-043/044/047 (the same functions on the same tables give the same numbers: equality of the reports is the check that IL-3 "uses IL-2's metrics and protocol");
hand-built tables; the "not run" state as the literal status text.

Expected API of the implementation (module `pitstudio_pipeline.evaluate.il`, see T-014-042/043):
    evaluate_il3(policy, baseline, *, seeds, mpm=None) -> dict
        policy and baseline: IL-3 tables (meta policy "IL-3", column_set "dig-episode", arms policy / baseline, scripted-dig baseline), or both None for an IL-3 that was not trained.
        Both None: {"status": "not run", "policy_id": "IL-3", "reason": <non-empty text>}, no metric, no verdict. Otherwise the report of evaluate_il2 on the same tables (same keys, same numbers)
        with "policy_id": "IL-3". Exactly one of the two tables None, an IL-2 table, an IL-1 table, or a non-None `mpm` (IL-3 has no MPM tier): ValueError naming `policy`, `baseline` or `mpm`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pitstudio_pipeline.evaluate.il import acceptance_table_il2, evaluate_il2, evaluate_il3

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import il_tables as kit


def il3_pair(n=100, kf_p=0.9, kf_b=0.7):
    rp = kit.dig_rows(n, fill_factor=kf_p, productivity_per_s=kf_p / 18.0)
    rb = kit.dig_rows(n, fill_factor=kf_b, productivity_per_s=kf_b / 18.0)
    return kit.table("IL-3", "policy", rp), kit.table("IL-3", "baseline", rb)


@pytest.mark.req("FR-014-24")
def test_an_untrained_il3_is_not_run_with_a_reason_and_no_metrics() -> None:
    rep = evaluate_il3(None, None, seeds=kit.IL2_SEEDS_BLOCK)
    assert rep["status"] == "not run"
    assert rep["policy_id"] == "IL-3"
    assert isinstance(rep["reason"], str)
    assert rep["reason"]
    assert not {"policy", "baseline", "verdicts", "sim_to_sim", "failed_check"} & set(rep)


@pytest.mark.req("FR-014-24")
def test_a_trained_il3_is_evaluated_with_the_il2_metrics_and_protocol() -> None:
    p, b = il3_pair()
    rep = evaluate_il3(p, b, seeds=kit.IL2_SEEDS_BLOCK)
    p2 = kit.table("IL-2", "policy", p["rows"])
    b2 = kit.table("IL-2", "baseline", b["rows"])
    ref = evaluate_il2(p2, b2, seeds=kit.IL2_SEEDS_BLOCK)
    assert rep["status"] == "complete"
    assert rep["policy_id"] == "IL-3"
    assert rep["policy"] == ref["policy"]  # the same summaries
    assert rep["baseline"] == ref["baseline"]
    assert rep["verdicts"] == ref["verdicts"]  # the same per-metric decision rule on productivity and k_f >= 0.8
    assert set(rep["verdicts"]) == {"productivity", "fill_ge_0_8"}


@pytest.mark.req("FR-014-24")
def test_the_il3_protocol_still_demands_100_paired_episodes() -> None:
    p, b = il3_pair(n=60)
    rep = evaluate_il3(p, b, seeds=kit.IL2_SEEDS_BLOCK)
    assert rep["status"] == "incomplete evaluation"
    assert rep["failed_check"] == "fewer_than_100"
    assert "verdicts" not in rep


@pytest.mark.req("FR-014-24")
def test_the_il2_acceptance_rows_can_be_built_from_an_il3_table() -> None:
    p, _b = il3_pair()
    t = acceptance_table_il2(p)
    assert t["status"] == "complete"
    assert [r["id"] for r in t["rows"]] == ["SC-014-06", "SC-014-07", "SC-014-08"]


@pytest.mark.req("FR-014-24")
def test_il3_has_no_mpm_tier() -> None:
    p, b = il3_pair()
    mpm = kit.table("IL-2", "mpm", kit.dig_rows(16))
    with pytest.raises(ValueError, match=r"\bmpm\b"):
        evaluate_il3(p, b, seeds=kit.IL2_SEEDS_BLOCK, mpm=mpm)


@pytest.mark.req("FR-014-24")
def test_the_il3_evaluator_rejects_tables_of_another_policy_or_a_missing_arm() -> None:
    p, b = il3_pair()
    il2_p = kit.table("IL-2", "policy", p["rows"])
    il1_b = kit.table("IL-1", "baseline", kit.il1_rows(100))
    with pytest.raises(ValueError, match=r"\bpolicy\b"):
        evaluate_il3(il2_p, b, seeds=kit.IL2_SEEDS_BLOCK)
    with pytest.raises(ValueError, match=r"\bbaseline\b"):
        evaluate_il3(p, il1_b, seeds=kit.IL2_SEEDS_BLOCK)
    with pytest.raises(ValueError, match=r"\bbaseline\b"):
        evaluate_il3(p, None, seeds=kit.IL2_SEEDS_BLOCK)
    with pytest.raises(ValueError, match=r"\bpolicy\b"):
        evaluate_il3(None, b, seeds=kit.IL2_SEEDS_BLOCK)

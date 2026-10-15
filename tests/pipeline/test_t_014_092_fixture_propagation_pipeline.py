# ruff: noqa: E501
"""T-014-092 (pipeline half): fixture propagation through `s50_evaluate`, the gaps, the acceptance tables and the export.

Requirements: FR-014-48.

Spec: specs/014-robot-learning/spec.md FR-014-48: "While an IL task file, a machine parameter file or a policy handoff (DC-014-01 to DC-014-03) is a contract fixture, the IL stages, the twin runner and `s50_evaluate` shall
run against it, shall write `fixture: true` on every policy, episode table and report, and shall publish no sim-to-sim gap computed from it." Plan: "a fixture task gives an episode table and a report `fixture: true` and the
publish step drops them".

Oracle: hand construction. A table document is a fixture when its dict holds `"fixture": True` (the sidecar schema has no such member, so the mark lives beside it, as the Parquet file-level metadata `fixture` does on disk);
a fixture anywhere in the inputs marks the output; the gaps of a fixture are withheld (status "fixture", no number); a real evaluation is unchanged (the same numbers as T-014-042 to T-014-045 give, with the gap present).

Expected API of the implementation (module `pitstudio_pipeline.evaluate.il`, see T-014-042, T-014-045, T-014-047 and `pitstudio_pipeline.export.il` of T-014-041):
    evaluate_il1(policy, baseline, *, seeds, twin=None, fixture=None) -> dict
    evaluate_il2(policy, baseline, *, seeds, mpm=None, il3=None, fixture=None) -> dict
        report["fixture"] is True when `fixture` is True or any input table document (policy, baseline, twin, mpm) has "fixture": True, else False. Real input with `twin` / `mpm`: report["sim_to_sim"] =
        sim_to_sim_gap_il1(policy, twin) (IL-1) / report["fee_mpm_gap"] = fee_mpm_gap(policy, mpm) (IL-2). Fixture input: no "sim_to_sim" and no "fee_mpm_gap" key; the per-metric verdicts are still computed.
    sim_to_sim_gap_il1(policy, twin), fee_mpm_gap(fee, mpm): when either table document is a fixture the result is {"label": "sim-to-sim gap", "status": "fixture", "reason": <text>} with no "mean_difference", "ci" or per-metric key.
    acceptance_table_il1(table, ...), acceptance_table_il2(table, ...): the result dict carries "fixture": True / False from the table document.
    is_publishable(artefact) -> bool                          False when artefact.get("fixture") is True (the same rule as pitstudio.robots.fixture.is_publishable)
    export_il_policy(handoff, *, root, out_dir, fixture=None, handoff_path=None) -> ExportResult
        ExportResult.fixture is True when `fixture` is True, or `fixture` is None and `handoff_path` lies in a `contracts/examples` or `data/samples` folder; an explicit False overrides the location. The export itself is unchanged.
"""

from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path

import pytest
from pitstudio_pipeline.evaluate.il import (
    acceptance_table_il1,
    acceptance_table_il2,
    evaluate_il1,
    evaluate_il2,
    fee_mpm_gap,
    is_publishable,
    sim_to_sim_gap_il1,
)
from pitstudio_pipeline.export.il import export_il_policy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import il_export_kit as xkit
import il_tables as kit


def il1_set(*, fixture_in=()):
    p = kit.table("IL-1", "policy", kit.il1_rows(100))
    b = kit.table("IL-1", "baseline", kit.il1_rows(100, rms_lateral_error_m=0.5))
    t = kit.table("IL-1", "twin", kit.il1_rows(100, rms_lateral_error_m=0.4))
    docs = {"policy": p, "baseline": b, "twin": t}
    for name in fixture_in:
        docs[name]["fixture"] = True
    return p, b, t


def il2_set(*, fixture_in=()):
    fee = kit.table("IL-2", "policy", kit.dig_rows(100))
    base = kit.table("IL-2", "baseline", kit.dig_rows(100, fill_factor=0.7, productivity_per_s=0.7 / 18.0))
    mpm = kit.table("IL-2", "mpm", kit.dig_rows(32, fill_factor=0.8, productivity_per_s=0.8 / 18.0))
    docs = {"policy": fee, "baseline": base, "mpm": mpm}
    for name in fixture_in:
        docs[name]["fixture"] = True
    return fee, base, mpm


# ------------------------------------------------------------------------------------------------ IL-1 report
@pytest.mark.req("FR-014-48")
def test_a_real_il1_evaluation_is_not_a_fixture_and_carries_the_sim_to_sim_gap() -> None:
    p, b, t = il1_set()
    rep = evaluate_il1(p, b, seeds=kit.IL1_SEEDS_BLOCK, twin=t)
    assert rep["fixture"] is False
    assert rep["status"] == "complete"
    assert rep["sim_to_sim"]["status"] == "complete"
    assert rep["sim_to_sim"]["label"] == "sim-to-sim gap"
    assert rep["sim_to_sim"]["rms_lateral_error"]["mean_difference"] == pytest.approx(
        0.4 - math.sqrt(0.1), abs=1e-12
    )  # twin 0.4 minus the policy's default sqrt(100 / 1000)
    assert is_publishable(rep) is True


@pytest.mark.req("FR-014-48")
@pytest.mark.parametrize("which", ["policy", "baseline", "twin"])
def test_a_fixture_in_any_input_marks_the_report_and_withholds_the_gap(which) -> None:
    p, b, t = il1_set(fixture_in=(which,))
    rep = evaluate_il1(p, b, seeds=kit.IL1_SEEDS_BLOCK, twin=t)
    assert rep["fixture"] is True
    assert rep["status"] == "complete"  # the stage ran against the fixture
    assert "verdicts" in rep
    assert "sim_to_sim" not in rep  # no sim-to-sim gap computed from a fixture is published
    assert is_publishable(rep) is False


@pytest.mark.req("FR-014-48")
def test_an_explicit_fixture_flag_marks_a_report_of_real_tables() -> None:
    p, b, t = il1_set()
    rep = evaluate_il1(p, b, seeds=kit.IL1_SEEDS_BLOCK, twin=t, fixture=True)
    assert rep["fixture"] is True
    assert "sim_to_sim" not in rep
    rep = evaluate_il1(p, b, seeds=kit.IL1_SEEDS_BLOCK, twin=t, fixture=False)
    assert rep["fixture"] is False
    assert "sim_to_sim" in rep


@pytest.mark.req("FR-014-48")
def test_an_incomplete_fixture_evaluation_is_still_marked() -> None:
    p, b, _t = il1_set(fixture_in=("policy",))
    b = kit.table("IL-1", "baseline", kit.il1_rows(40))
    rep = evaluate_il1(p, b, seeds=kit.IL1_SEEDS_BLOCK)
    assert rep["status"] == "incomplete evaluation"
    assert rep["fixture"] is True


# ------------------------------------------------------------------------------------------------ IL-2 report
@pytest.mark.req("FR-014-48")
def test_a_real_il2_evaluation_carries_the_fee_mpm_gap() -> None:
    fee, base, mpm = il2_set()
    rep = evaluate_il2(fee, base, seeds=kit.IL2_SEEDS_BLOCK, mpm=mpm)
    assert rep["fixture"] is False
    assert rep["fee_mpm_gap"]["status"] == "complete"
    assert rep["fee_mpm_gap"]["mean_difference"] == pytest.approx(-0.1, abs=1e-12)  # 0.8 (MPM) - 0.9 (FEE)


@pytest.mark.req("FR-014-48")
@pytest.mark.parametrize("which", ["policy", "baseline", "mpm"])
def test_a_fixture_in_any_il2_input_marks_the_report_and_withholds_the_gap(which) -> None:
    fee, base, mpm = il2_set(fixture_in=(which,))
    rep = evaluate_il2(fee, base, seeds=kit.IL2_SEEDS_BLOCK, mpm=mpm)
    assert rep["fixture"] is True
    assert "fee_mpm_gap" not in rep
    assert "verdicts" in rep
    assert is_publishable(rep) is False


# ------------------------------------------------------------------------------------------------ gap functions
@pytest.mark.req("FR-014-48")
def test_the_gap_functions_withhold_every_number_for_a_fixture() -> None:
    p, _b, t = il1_set(fixture_in=("twin",))
    g = sim_to_sim_gap_il1(p, t)
    assert g["label"] == "sim-to-sim gap"
    assert g["status"] == "fixture"
    assert isinstance(g["reason"], str)
    assert g["reason"]
    assert not {"mean_difference", "ci", "success", "rms_lateral_error", "min_ttc", "n"} & set(g)
    fee, _base, mpm = il2_set(fixture_in=("mpm",))
    g2 = fee_mpm_gap(fee, mpm)
    assert g2["status"] == "fixture"
    assert not {"mean_difference", "ci", "n"} & set(g2)
    fee, _base, mpm = il2_set(fixture_in=("policy",))
    assert fee_mpm_gap(fee, mpm)["status"] == "fixture"


@pytest.mark.req("FR-014-48")
def test_a_fixture_pair_that_is_also_invalid_reports_the_failed_check_not_a_gap() -> None:
    p, _b, t = il1_set(fixture_in=("twin",))
    t["rows"] = t["rows"][:3]
    t["meta"] = kit.meta("IL-1", "twin", t["rows"])
    g = sim_to_sim_gap_il1(p, t)
    assert g["status"] in ("fixture", "incomplete evaluation")
    assert "mean_difference" not in g
    assert "ci" not in g


# ------------------------------------------------------------------------------------------ acceptance tables
@pytest.mark.req("FR-014-48")
def test_the_acceptance_tables_carry_the_fixture_mark() -> None:
    p, _b, _t = il1_set()
    assert acceptance_table_il1(p)["fixture"] is False
    p["fixture"] = True
    t1 = acceptance_table_il1(p)
    assert t1["fixture"] is True
    assert t1["status"] == "complete"  # rows are computed (the stage ran against the fixture) but marked
    assert is_publishable(t1) is False
    fee, _base, _mpm = il2_set()
    assert acceptance_table_il2(fee)["fixture"] is False
    fee["fixture"] = True
    assert acceptance_table_il2(fee)["fixture"] is True


@pytest.mark.req("FR-014-48")
def test_is_publishable_rule() -> None:
    assert is_publishable({"fixture": True}) is False
    assert is_publishable({"fixture": False, "status": "complete"}) is True
    assert is_publishable({}) is True


# ------------------------------------------------------------------------------------------------ export
@pytest.mark.req("FR-014-48")
def test_a_fixture_handoff_exports_like_a_real_one_and_the_result_is_marked(tmp_path: Path) -> None:
    handoff, root = xkit.make_run(tmp_path)
    real = export_il_policy(handoff, root=root, out_dir=tmp_path / "real")
    assert real.fixture is False
    fix = export_il_policy(handoff, root=root, out_dir=tmp_path / "fix", fixture=True)
    assert fix.fixture is True
    assert fix.onnx_path.is_file()
    assert fix.parity["ok"] is True  # run against it exactly as for a real handoff
    assert is_publishable({"fixture": fix.fixture}) is False


@pytest.mark.req("FR-014-48")
def test_a_handoff_file_in_a_contract_examples_folder_is_a_fixture_by_location(tmp_path: Path) -> None:
    import json

    handoff, root = xkit.make_run(tmp_path)
    in_examples = tmp_path / "specs" / "014-robot-learning" / "contracts" / "examples" / "handoff.json"
    in_examples.parent.mkdir(parents=True)
    in_examples.write_text(json.dumps(handoff), encoding="utf-8")
    elsewhere = tmp_path / "runs" / "r1" / "handoff.json"
    elsewhere.parent.mkdir(parents=True)
    shutil.copy(in_examples, elsewhere)
    assert export_il_policy(handoff, root=root, out_dir=tmp_path / "a", handoff_path=in_examples).fixture is True
    assert export_il_policy(handoff, root=root, out_dir=tmp_path / "b", handoff_path=elsewhere).fixture is False
    assert (
        export_il_policy(handoff, root=root, out_dir=tmp_path / "c", handoff_path=in_examples, fixture=False).fixture
        is False
    )


@pytest.mark.req("FR-014-48")
def test_a_non_boolean_export_fixture_argument_is_rejected_naming_it(tmp_path: Path) -> None:
    handoff, root = xkit.make_run(tmp_path)
    with pytest.raises((TypeError, ValueError), match=r"\bfixture\b|\bflag\b"):
        export_il_policy(handoff, root=root, out_dir=tmp_path / "out", fixture="yes")
    assert xkit.out_files(tmp_path / "out") == []


@pytest.mark.req("FR-014-48")
def test_hostile_fixture_values_in_a_table_document_are_not_treated_as_a_mark() -> None:
    p, b, _t = il1_set()
    p["fixture"] = "true"  # only the boolean True is a mark
    rep = evaluate_il1(p, b, seeds=kit.IL1_SEEDS_BLOCK)
    assert rep["fixture"] is False
    p["fixture"] = math.nan
    assert evaluate_il1(p, b, seeds=kit.IL1_SEEDS_BLOCK)["fixture"] is False

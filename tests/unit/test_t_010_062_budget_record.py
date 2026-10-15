"""T-010-062: GPU-hours recorded for every training stage and the budget statement.

Requirement: NFR-010-06 ("Forecaster training budget: <= 2 GPU-h in total (estimate); the measured value is recorded
in the
manifests and an overrun is stated in the card").
Spec: specs/010-slope/spec.md section 5; plan.md row NFR-010-06 ("manifest of each training stage carries GPU-hours").

Expected API (module `pitstudio.slope.budget`, standard library only; the same shape as spec 011's helper):
- `BUDGET_GPU_HOURS = 2.0`.
- `gpu_hours_record(arm, seconds, *, device) -> dict`: {"arm", "gpu_hours", "device", "seconds"} with gpu_hours =
  seconds / 3600
  for a CUDA device and 0.0 for "cpu" (a CPU training is recorded as such: `"note": "trained on the CPU"`). ValueError
  for a
  negative or non-finite duration, an unknown arm (tcn, patchtst, chronos_bolt_fine_tuned: the zero-shot arm is not
  trained) or an
  unknown device (cpu, cuda).
- `attach_gpu_hours(manifest, record) -> dict`: a copy of the training-stage manifest with the record under
  `manifest["gpu_hours"]`; the input is not modified.
- `missing_gpu_hours(manifests) -> list[str]`: the `id` of every training-stage manifest (stage "s30_train") without a
  numeric
  non-negative `gpu_hours.gpu_hours`.
- `budget_report(records) -> dict`: {"total_gpu_hours", "budget_gpu_hours": 2.0, "overrun": bool, "statement": str |
  None}; the
  statement is None within the budget and otherwise names the measured total and the 2 GPU-h estimate
  ("training used 2.08 GPU-h against an estimate of 2 GPU-h").

Oracle: hand calculation (3,600 s = 1 h; 1,800 + 2,700 + 3,000 s = 7,500 s = 2.0833 h).
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pitstudio.slope import budget


@pytest.mark.req("NFR-010-06")
def test_the_budget_constant_is_two_gpu_hours() -> None:
    assert budget.BUDGET_GPU_HOURS == 2.0


@pytest.mark.req("NFR-010-06")
def test_a_cuda_training_records_hours_and_a_cpu_training_records_zero_with_a_note() -> None:
    r = budget.gpu_hours_record("tcn", 5400.0, device="cuda")
    assert r == {"arm": "tcn", "gpu_hours": pytest.approx(1.5), "device": "cuda", "seconds": 5400.0}
    cpu = budget.gpu_hours_record("patchtst", 7200.0, device="cpu")
    assert cpu["gpu_hours"] == 0.0
    assert cpu["note"] == "trained on the CPU"
    assert cpu["seconds"] == 7200.0


@pytest.mark.req("NFR-010-06")
@pytest.mark.parametrize(
    ("arm", "seconds", "device"),
    [
        ("tcn", -1.0, "cuda"),
        ("tcn", float("nan"), "cuda"),
        ("tcn", float("inf"), "cuda"),
        ("chronos_bolt_zero_shot", 10.0, "cuda"),  # never trained
        ("lstm", 10.0, "cuda"),
        ("tcn", 10.0, "tpu"),
        ("", 10.0, "cpu"),
    ],
)
def test_hostile_records_are_rejected(arm, seconds, device) -> None:
    with pytest.raises(ValueError, match=r"."):
        budget.gpu_hours_record(arm, seconds, device=device)


@pytest.mark.req("NFR-010-06")
def test_attach_adds_the_record_without_modifying_the_manifest() -> None:
    manifest = {"id": "tcn-checkpoint", "stage": "s30_train", "inputs": []}
    before = copy.deepcopy(manifest)
    rec = budget.gpu_hours_record("tcn", 3600.0, device="cuda")
    out = budget.attach_gpu_hours(manifest, rec)
    assert out["gpu_hours"] == rec
    assert manifest == before
    assert out["id"] == "tcn-checkpoint"


@pytest.mark.req("NFR-010-06")
def test_missing_gpu_hours_names_every_training_manifest_without_a_value() -> None:
    ok = {"id": "tcn-run", "stage": "s30_train", "gpu_hours": {"arm": "tcn", "gpu_hours": 0.5}}
    cpu = {"id": "patchtst-run", "stage": "s30_train", "gpu_hours": {"arm": "patchtst", "gpu_hours": 0.0}}
    none = {"id": "chronos-run", "stage": "s30_train"}
    bad = {"id": "tcn-run-2", "stage": "s30_train", "gpu_hours": {"arm": "tcn", "gpu_hours": -1.0}}
    text = {"id": "tcn-run-3", "stage": "s30_train", "gpu_hours": {"arm": "tcn", "gpu_hours": "1"}}
    other = {"id": "ttf-results", "stage": "s50_evaluate"}  # not a training stage: not required
    assert budget.missing_gpu_hours([ok, cpu, none, bad, text, other]) == ["chronos-run", "tcn-run-2", "tcn-run-3"]
    assert budget.missing_gpu_hours([]) == []


@pytest.mark.req("NFR-010-06")
def test_total_within_the_budget_has_no_statement() -> None:
    records = [
        budget.gpu_hours_record("tcn", 1800.0, device="cuda"),
        budget.gpu_hours_record("patchtst", 2700.0, device="cuda"),
        budget.gpu_hours_record("chronos_bolt_fine_tuned", 900.0, device="cuda"),
    ]  # 0.5 + 0.75 + 0.25 = 1.5 h
    rep = budget.budget_report(records)
    assert rep["total_gpu_hours"] == pytest.approx(1.5)
    assert rep["budget_gpu_hours"] == 2.0
    assert rep["overrun"] is False
    assert rep["statement"] is None


@pytest.mark.req("NFR-010-06")
def test_an_overrun_is_stated_with_the_measured_total() -> None:
    records = [
        budget.gpu_hours_record("tcn", 1800.0, device="cuda"),
        budget.gpu_hours_record("patchtst", 2700.0, device="cuda"),
        budget.gpu_hours_record("chronos_bolt_fine_tuned", 3000.0, device="cuda"),
    ]  # 7,500 s = 2.0833 h
    rep = budget.budget_report(records)
    assert rep["total_gpu_hours"] == pytest.approx(7500 / 3600)
    assert rep["overrun"] is True
    assert rep["statement"] == "training used 2.08 GPU-h against an estimate of 2 GPU-h"


@pytest.mark.req("NFR-010-06")
def test_the_budget_is_inclusive_and_cpu_only_training_costs_no_gpu_hours() -> None:
    exact = [budget.gpu_hours_record("tcn", 7200.0, device="cuda")]
    assert budget.budget_report(exact)["overrun"] is False  # exactly 2 h is within "<= 2 GPU-h"
    cpu = [budget.gpu_hours_record("tcn", 99999.0, device="cpu")]
    rep = budget.budget_report(cpu)
    assert rep["total_gpu_hours"] == 0.0
    assert rep["statement"] is None
    assert budget.budget_report([])["total_gpu_hours"] == 0.0

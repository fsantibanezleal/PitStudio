# ruff: noqa: E501
"""T-014-062 (GPU, local): MJCF compile, short training run with resume, VRAM and time budget checks.

Requirements: FR-014-05, FR-014-25, NFR-014-01, NFR-014-02.

Spec: specs/014-robot-learning/spec.md FR-014-05 (verification "gpu (local: MuJoCo compiles)": the generated truck MJCF compiles); FR-014-25 (checkpoint every 100 iterations; `--resume` continues from the last checkpoint with the same
iteration count, optimiser state and normaliser statistics); NFR-014-01 (device-peak VRAM during training: IL-1 <= 5 GB, IL-2 <= 6 GB; the number of environments is reduced until it fits, NVML telemetry in the manifest);
NFR-014-02 (GPU time recorded per run; a run that exceeds 2 x its upper estimate (IL-1 8 h, IL-2 16 h) is stopped and recorded as such). Marked `gpu`: runs on the reference machine under the `gpu0.compute` lock, not in CI.

Oracle: MuJoCo's own compiler (the reference implementation of MJCF) through the child process; the parameter file as the source of the model's mass (within 0.1 %); the closed-form fake-free quantities of a short real run: the
iteration counter, the number of checkpoint files (every 100 iterations => with `--checkpoint-every 2` and 6 iterations: 2, 4, 6) and the NVML peak read from the manifest; the budgets of the requirements.

Expected API of the implementation (modules of the studio/isaaclab project, `python -m pitstudio_isaaclab.<module>`, last stdout line JSON):
    mjcf_check --model <xml> : {"compiled": bool, "nbody": int, "njnt": int, "total_mass_kg": float, "error": str | null}  (MuJoCo `MjModel.from_xml_path`)
    train --task <Pit-HaulTruck-Ramp | Pit-Excavator-Dig-FEE> --params <il-task json> --out <dir> [--max-iterations N] [--checkpoint-every K] [--resume <checkpoint>] [--num-envs M]
        runs the task with rsl_rl PPO (T-014-040's wrapper around the real runner) and prints {"exit_code": int, "iterations_completed": int, "checkpoints": [file names], "state": {"iteration", "optimiser_steps",
        "normaliser_count"}, "num_envs": int, "peak_vram_gb": float (NVML device peak), "gpu_hours": float, "manifest": <path of the stage manifest>, "oom_fallback": null | {...}}
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "support"))
import il_gpu_kit as kit  # noqa: E402

EX = ROOT / "specs" / "014-robot-learning" / "contracts" / "examples"
TRUCK = json.loads((EX / "machine-params.valid.json").read_text("utf-8"))
IL1 = json.loads((EX / "il-task.valid.json").read_text("utf-8"))
IL2 = json.loads((EX / "il-task.valid-il2.json").read_text("utf-8"))


def short_params(base: dict, tmp: Path, name: str, num_envs: int) -> Path:
    p = copy.deepcopy(base)
    p["training"]["iterations"] = 6
    p["training"]["num_envs"] = num_envs
    path = tmp / f"{name}.json"
    path.write_text(json.dumps(p), encoding="utf-8")
    return path


@pytest.mark.gpu
@pytest.mark.req("FR-014-05")
def test_the_generated_truck_mjcf_compiles_in_mujoco_and_its_mass_matches_the_file(tmp_path: Path) -> None:
    from pitstudio.robots.machines import write_truck_mjcf

    model = write_truck_mjcf(TRUCK, tmp_path / "model")
    r = kit.run_module("mjcf_check", "--model", str(model), timeout=600)
    assert r["error"] is None
    assert r["compiled"] is True
    assert r["nbody"] >= 8  # world, chassis and six wheels
    assert r["njnt"] >= 7  # the steering joint and six wheel spins
    assert r["total_mass_kg"] == pytest.approx(TRUCK["empty_mass_kg"], rel=1e-3)


@pytest.mark.gpu
@pytest.mark.req("FR-014-05")
def test_the_excavator_mjcf_compiles_in_mujoco(tmp_path: Path) -> None:
    from pitstudio.robots.machines import write_excavator_mjcf

    machine = json.loads((EX / "machine-params.valid-excavator.json").read_text("utf-8"))
    model = write_excavator_mjcf(machine, tmp_path / "model")
    r = kit.run_module("mjcf_check", "--model", str(model), timeout=600)
    assert r["compiled"] is True
    assert r["njnt"] == 4


@pytest.mark.gpu
@pytest.mark.req("FR-014-25")
def test_a_short_run_with_resume_ends_at_the_same_iteration_count_and_normaliser_statistics(tmp_path: Path) -> None:
    params = short_params(IL1, tmp_path, "il1", 256)
    straight = kit.run_module(
        "train",
        "--task",
        "Pit-HaulTruck-Ramp",
        "--params",
        str(params),
        "--out",
        str(tmp_path / "straight"),
        "--max-iterations",
        "6",
        "--checkpoint-every",
        "2",
        timeout=3600,
    )
    assert straight["exit_code"] == 0
    assert straight["iterations_completed"] == 6
    assert sorted(straight["checkpoints"]) == ["model_2.pt", "model_4.pt", "model_6.pt"]

    first = kit.run_module(
        "train",
        "--task",
        "Pit-HaulTruck-Ramp",
        "--params",
        str(params),
        "--out",
        str(tmp_path / "resumed"),
        "--max-iterations",
        "4",
        "--checkpoint-every",
        "2",
        timeout=3600,
    )
    assert first["iterations_completed"] == 4
    last = tmp_path / "resumed" / "checkpoints" / "model_4.pt"
    assert last.is_file()
    second = kit.run_module(
        "train",
        "--task",
        "Pit-HaulTruck-Ramp",
        "--params",
        str(params),
        "--out",
        str(tmp_path / "resumed"),
        "--max-iterations",
        "6",
        "--checkpoint-every",
        "2",
        "--resume",
        str(last),
        timeout=3600,
    )
    assert second["exit_code"] == 0
    assert second["iterations_completed"] == 6
    assert second["state"]["iteration"] == straight["state"]["iteration"] == 6
    assert (
        second["state"]["optimiser_steps"] == straight["state"]["optimiser_steps"]
    )  # the optimiser counter continues, it is not restarted
    assert (
        second["state"]["normaliser_count"] == straight["state"]["normaliser_count"]
    )  # the normaliser statistics continue, they are not recomputed


@pytest.mark.gpu
@pytest.mark.req("NFR-014-01")
@pytest.mark.parametrize(
    ("task", "base", "budget_gb"), [("Pit-HaulTruck-Ramp", IL1, 5.0), ("Pit-Excavator-Dig-FEE", IL2, 6.0)]
)
def test_the_device_peak_vram_stays_within_the_budget_and_is_recorded_from_nvml(
    tmp_path: Path, task, base, budget_gb
) -> None:
    params = short_params(base, tmp_path, task, base["training"]["num_envs"])
    r = kit.run_module(
        "train",
        "--task",
        task,
        "--params",
        str(params),
        "--out",
        str(tmp_path / "run"),
        "--max-iterations",
        "3",
        "--checkpoint-every",
        "3",
        timeout=7200,
    )
    assert r["exit_code"] == 0
    assert 0.0 < r["peak_vram_gb"] <= budget_gb
    manifest = json.loads(Path(r["manifest"]).read_text("utf-8"))
    assert manifest["telemetry"]["max_mem_used_mb"] / 1024.0 == pytest.approx(
        r["peak_vram_gb"], rel=0.05
    )  # the manifest holds the NVML summary
    assert r["num_envs"] <= base["training"]["num_envs"]  # reduced, never raised, to fit


@pytest.mark.gpu
@pytest.mark.req("NFR-014-02")
def test_the_gpu_time_is_recorded_and_far_below_twice_the_upper_estimate(tmp_path: Path) -> None:
    params = short_params(IL1, tmp_path, "il1-time", 256)
    r = kit.run_module(
        "train",
        "--task",
        "Pit-HaulTruck-Ramp",
        "--params",
        str(params),
        "--out",
        str(tmp_path / "run"),
        "--max-iterations",
        "3",
        "--checkpoint-every",
        "3",
        timeout=3600,
    )
    assert 0.0 < r["gpu_hours"] < 8.0  # 2 x the 4 h upper estimate of IL-1 (the budget of the task file)
    manifest = json.loads(Path(r["manifest"]).read_text("utf-8"))
    assert manifest["gpu_hours"] == pytest.approx(r["gpu_hours"], rel=1e-6)
    assert manifest.get("stopped_by_budget", False) is False

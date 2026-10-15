# ruff: noqa: E501
"""T-014-040: training wrapper with a fake trainer: PPO configuration, checkpoint cadence, resume equality, single OOM fallback.

Requirements: FR-014-25, FR-014-26.

Spec: specs/014-robot-learning/spec.md FR-014-25: "`st60_il_train` shall train with rsl_rl PPO using actor and critic MLPs of two hidden layers of
256 units, gamma = 0.99, lambda = 0.95, clip ratio 0.2 and 24 steps per environment per update, with the number of environments set from the bench
measurement within the VRAM budget (NFR-014-01); it shall save a checkpoint every 100 iterations, and `--resume` shall continue from the last
checkpoint with the same iteration count, optimiser state and normaliser statistics." FR-014-26: "If a CUDA out-of-memory error occurs during
training, then the stage shall retry once with the number of environments halved (the recipe's declared `oom_fallback`), resuming from the last
checkpoint, and record the fallback in the manifest; a second out-of-memory error shall fail the stage."

Oracle: the constants of the requirement; a deterministic fake trainer (tests/support/il_fake_trainer.py) whose state after i iterations is given by a
closed form written there (iteration i, 24 i optimiser steps, 1000 i normaliser samples, mean (i + 1) / 2): the state reached by an interrupted run
resumed from its last checkpoint must equal the closed form and the state of an uninterrupted run exactly; the OOM scenarios are scripted by hand
(an environment count above a threshold at a given iteration raises; a second raise fails the stage); the checkpoint cadence is counted.

Plan deviation (see the red report): the wrapper logic is torch-free and lives in the root package so that CI can run it; the Isaac Lab package supplies the real
trainer behind the same interface.

Expected API of the implementation (module `pitstudio.robots.training`):
    PpoConfig: frozen dataclass (hidden_units: tuple[int, ...], gamma, gae_lambda, clip_ratio, steps_per_env, num_envs)
    ppo_config(params, num_envs=None) -> PpoConfig            from a valid IL task document (`training` block); num_envs overrides
    is_oom(exc) -> bool                                       True for an exception whose class name is "OutOfMemoryError" or whose message contains
                                                              "CUDA out of memory"
    latest_checkpoint(out_dir) -> pathlib.Path | None         the checkpoint file with the highest iteration under <out_dir>/checkpoints
    run_stage(params, make_trainer, out_dir, *, resume=None) -> StageResult
        validates the task parameters (exit code 2 before any trainer is built, see T-014-049), then builds `make_trainer(ppo, num_envs)` and runs
        iterations 1 .. params["training"]["iterations"] through `trainer.train_iteration(i)` (1-based, consecutive). Checkpoints: after every iteration that
        is a multiple of training.checkpoint_every (100) the wrapper calls `trainer.save(<out_dir>/checkpoints/model_<i>.pt)` and writes the sidecar
        `model_<i>.json` {"iteration": i, "task_config_sha256": <config hash>, "num_envs": n}; a final checkpoint is written at the last iteration when it
        is not a multiple of 100. `resume=<path of a checkpoint>` builds a trainer, calls `trainer.load(path)` and continues from iteration load + 1.
        A non-OOM exception of the trainer propagates unchanged. An OOM (`is_oom`) triggers ONE fallback: a new trainer with num_envs // 2, loaded from the
        last checkpoint (or started from scratch when none exists), continuing to the end; a second OOM ends the stage with exit code 1.
        StageResult: frozen dataclass (exit_code: int, manifest: dict, checkpoints: list[Path], message: str).
        manifest keys: "num_envs" (the count of the last trainer), "iterations_completed", "oom_fallback" (None, or {"from": n, "to": n // 2,
        "at_iteration": i, "resumed_from": the checkpoint iteration or 0}), "ppo" (the PpoConfig as a dict), "failed" (None or "oom").
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from pitstudio.robots.training import PpoConfig, is_oom, latest_checkpoint, ppo_config, run_stage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import il_fake_trainer as fk

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "014-robot-learning" / "contracts" / "examples"
IL1 = json.loads((EX / "il-task.valid.json").read_text("utf-8"))
IL2 = json.loads((EX / "il-task.valid-il2.json").read_text("utf-8"))


def params(iterations: int, base=IL1, num_envs: int = 2048) -> dict:
    p = copy.deepcopy(base)
    p["training"]["iterations"] = iterations
    p["training"]["num_envs"] = num_envs
    return p


# ------------------------------------------------------------------------------------------------ PPO config
@pytest.mark.req("FR-014-25")
@pytest.mark.parametrize("base", [IL1, IL2], ids=["IL-1", "IL-2"])
def test_the_ppo_configuration_has_the_constants_of_the_requirement(base) -> None:
    cfg = ppo_config(params(300, base, 3072))
    assert isinstance(cfg, PpoConfig)
    assert tuple(cfg.hidden_units) == (256, 256)
    assert cfg.gamma == 0.99
    assert cfg.gae_lambda == 0.95
    assert cfg.clip_ratio == 0.2
    assert cfg.steps_per_env == 24
    assert cfg.num_envs == 3072


@pytest.mark.req("FR-014-25")
def test_the_number_of_environments_can_be_overridden_for_the_fallback() -> None:
    assert ppo_config(params(300), num_envs=1024).num_envs == 1024


@pytest.mark.req("FR-014-25")
def test_the_trainer_is_built_with_the_configuration_and_the_environment_count(tmp_path: Path) -> None:
    f = fk.Factory()
    res = run_stage(params(5), f, tmp_path)
    assert res.exit_code == 0
    assert len(f.trainers) == 1
    t = f.trainers[0]
    assert t.num_envs == 2048
    assert (tuple(t.ppo.hidden_units), t.ppo.gamma, t.ppo.gae_lambda, t.ppo.clip_ratio, t.ppo.steps_per_env) == (
        (256, 256),
        0.99,
        0.95,
        0.2,
        24,
    )
    assert res.manifest["ppo"]["gamma"] == 0.99
    assert res.manifest["num_envs"] == 2048
    assert res.manifest["iterations_completed"] == 5
    assert res.manifest["oom_fallback"] is None
    assert res.manifest["failed"] is None


@pytest.mark.req("FR-014-25")
def test_iterations_run_from_one_to_the_configured_count_in_order(tmp_path: Path) -> None:
    f = fk.Factory()
    run_stage(params(37), f, tmp_path)
    assert [i for kind, i in f.log if kind == "iteration"] == list(range(1, 38))
    assert f.trainers[0].state == fk.expected_state(37)


# ------------------------------------------------------------------------------------------- checkpoint cadence
@pytest.mark.req("FR-014-25")
def test_a_checkpoint_is_saved_every_100_iterations_plus_a_final_one(tmp_path: Path) -> None:
    f = fk.Factory()
    res = run_stage(params(350), f, tmp_path)
    assert f.trainers[0].saved == [100, 200, 300, 350]
    names = sorted(p.name for p in (tmp_path / "checkpoints").glob("model_*.pt"))
    assert names == ["model_100.pt", "model_200.pt", "model_300.pt", "model_350.pt"]
    assert [p.name for p in res.checkpoints] == names
    for it in (100, 200, 300, 350):
        side = json.loads((tmp_path / "checkpoints" / f"model_{it}.json").read_text("utf-8"))
        assert side["iteration"] == it
        assert side["num_envs"] == 2048
        assert len(side["task_config_sha256"]) == 64


@pytest.mark.req("FR-014-25")
def test_no_extra_final_checkpoint_when_the_last_iteration_is_a_multiple_of_100(tmp_path: Path) -> None:
    f = fk.Factory()
    run_stage(params(200), f, tmp_path)
    assert f.trainers[0].saved == [100, 200]


@pytest.mark.req("FR-014-25")
def test_a_short_run_saves_only_the_final_checkpoint(tmp_path: Path) -> None:
    f = fk.Factory()
    run_stage(params(60), f, tmp_path)
    assert f.trainers[0].saved == [60]


@pytest.mark.req("FR-014-25")
def test_the_latest_checkpoint_is_the_one_with_the_highest_iteration(tmp_path: Path) -> None:
    assert latest_checkpoint(tmp_path) is None
    run_stage(params(250), fk.Factory(), tmp_path)
    last = latest_checkpoint(tmp_path)
    assert last is not None
    assert last.name == "model_250.pt"  # 250 > 200 numerically, not alphabetically ("model_250" < "model_50" as text)


# --------------------------------------------------------------------------------------------- resume equality
class Crash(RuntimeError):
    pass


def crash_at(iteration: int):
    return lambda i, _n: Crash("simulated crash") if i == iteration else None


@pytest.mark.req("FR-014-25")
def test_resume_continues_with_the_same_iteration_count_optimiser_state_and_normaliser(tmp_path: Path) -> None:
    straight_dir = tmp_path / "straight"
    straight = fk.Factory()
    run_stage(params(300), straight, straight_dir)
    want = straight.trainers[0].state
    assert want == fk.expected_state(300)  # the closed form of the fake agrees with the uninterrupted run

    broken_dir = tmp_path / "broken"
    with pytest.raises(Crash):
        run_stage(
            params(300), fk.Factory(fail_at=crash_at(151)), broken_dir
        )  # dies in iteration 151, checkpoint 100 exists
    last = latest_checkpoint(broken_dir)
    assert last is not None
    assert last.name == "model_100.pt"

    resumed = fk.Factory()
    res = run_stage(params(300), resumed, broken_dir, resume=last)
    assert res.exit_code == 0
    t = resumed.trainers[0]
    assert t.state == want  # exact equality of iteration, optimiser steps, normaliser count and mean
    assert ("load", 100) in resumed.log
    assert [i for kind, i in resumed.log if kind == "iteration"] == list(range(101, 301))  # continues at 101, not at 1
    assert res.manifest["iterations_completed"] == 300


@pytest.mark.req("FR-014-25")
def test_the_normaliser_and_optimiser_state_are_restored_not_recomputed(tmp_path: Path) -> None:
    with pytest.raises(Crash):
        run_stage(
            params(250), fk.Factory(fail_at=crash_at(201)), tmp_path
        )  # checkpoint 200 exists, the config hash is that of params(250)
    f = fk.Factory()
    run_stage(params(250), f, tmp_path, resume=tmp_path / "checkpoints" / "model_200.pt")
    s = f.trainers[0].state
    assert s["normaliser_count"] == 1000 * 250  # 200 restored + 50 new, not 50
    assert s["optimiser_steps"] == 24 * 250
    assert s["normaliser_mean"] == pytest.approx((250 + 1) / 2, rel=1e-12)


@pytest.mark.req("FR-014-25")
def test_a_non_oom_error_propagates_unchanged_and_no_fallback_is_attempted(tmp_path: Path) -> None:
    f = fk.Factory(fail_at=crash_at(10))
    with pytest.raises(Crash, match="simulated crash"):
        run_stage(params(50), f, tmp_path)
    assert len(f.trainers) == 1


# ------------------------------------------------------------------------------------------ OOM recognition
@pytest.mark.req("FR-014-26")
def test_oom_is_recognised_by_class_name_or_message() -> None:
    assert is_oom(fk.OutOfMemoryError("anything"))
    assert is_oom(RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB"))
    assert is_oom(RuntimeError("torch.OutOfMemoryError: CUDA out of memory"))
    assert not is_oom(RuntimeError("shape mismatch"))
    assert not is_oom(ValueError("out of range"))
    assert not is_oom(KeyboardInterrupt())


# ------------------------------------------------------------------------------------------ OOM fallback
def oom_above(threshold_envs: int, at_iteration: int):
    return lambda i, n: (
        fk.OutOfMemoryError("CUDA out of memory") if (i == at_iteration and n >= threshold_envs) else None
    )


@pytest.mark.req("FR-014-26")
def test_one_oom_halves_the_environments_resumes_from_the_last_checkpoint_and_is_recorded(tmp_path: Path) -> None:
    f = fk.Factory(fail_at=oom_above(2048, 250))
    res = run_stage(params(400), f, tmp_path)
    assert res.exit_code == 0
    assert [t.num_envs for t in f.trainers] == [2048, 1024]
    second = f.trainers[1]
    assert ("load", 200) in f.log  # resumed from the last checkpoint (iteration 200), not from 250
    assert second.state == fk.expected_state(400)  # the trajectory continued exactly
    assert res.manifest["oom_fallback"] == {"from": 2048, "to": 1024, "at_iteration": 250, "resumed_from": 200}
    assert res.manifest["num_envs"] == 1024
    assert res.manifest["iterations_completed"] == 400
    assert res.manifest["failed"] is None
    assert [i for kind, i in f.log if kind == "iteration"][-200:] == list(range(201, 401))


@pytest.mark.req("FR-014-26")
def test_an_oom_before_the_first_checkpoint_restarts_from_scratch_with_half_the_environments(tmp_path: Path) -> None:
    f = fk.Factory(fail_at=oom_above(2048, 40))
    res = run_stage(params(150), f, tmp_path)
    assert res.exit_code == 0
    assert [t.num_envs for t in f.trainers] == [2048, 1024]
    assert not any(kind == "load" for kind, _ in f.log)
    assert res.manifest["oom_fallback"] == {"from": 2048, "to": 1024, "at_iteration": 40, "resumed_from": 0}
    assert f.trainers[1].state == fk.expected_state(150)


@pytest.mark.req("FR-014-26")
def test_a_second_oom_fails_the_stage(tmp_path: Path) -> None:
    f = fk.Factory(
        fail_at=lambda i, _n: fk.OutOfMemoryError("CUDA out of memory") if i == 250 else None
    )  # at 250 whatever the size
    res = run_stage(params(400), f, tmp_path)
    assert res.exit_code == 1
    assert [t.num_envs for t in f.trainers] == [2048, 1024]  # exactly one retry
    assert res.manifest["failed"] == "oom"
    assert res.manifest["oom_fallback"]["to"] == 1024
    assert res.manifest["iterations_completed"] < 400
    assert "out of memory" in res.message.lower()


@pytest.mark.req("FR-014-26")
def test_the_fallback_is_used_once_per_stage_even_when_the_second_oom_comes_much_later(tmp_path: Path) -> None:
    def fail(i, n):
        if i == 120 and n == 2048:
            return fk.OutOfMemoryError("CUDA out of memory")
        if i == 380 and n == 1024:
            return fk.OutOfMemoryError("CUDA out of memory")
        return None

    f = fk.Factory(fail_at=fail)
    res = run_stage(params(400), f, tmp_path)
    assert res.exit_code == 1
    assert len(f.trainers) == 2  # no second fallback
    assert res.manifest["failed"] == "oom"


@pytest.mark.req("FR-014-26")
def test_an_odd_environment_count_is_halved_by_integer_division(tmp_path: Path) -> None:
    f = fk.Factory(fail_at=oom_above(1001, 10))
    res = run_stage(params(30, num_envs=1001), f, tmp_path)
    assert [t.num_envs for t in f.trainers] == [1001, 500]
    assert res.manifest["oom_fallback"]["to"] == 500


@pytest.mark.req("FR-014-26")
def test_a_single_environment_cannot_be_halved_and_fails_the_stage(tmp_path: Path) -> None:
    f = fk.Factory(fail_at=lambda i, _n: fk.OutOfMemoryError("CUDA out of memory") if i == 3 else None)
    res = run_stage(params(10, num_envs=1), f, tmp_path)
    assert res.exit_code == 1
    assert len(f.trainers) == 1
    assert res.manifest["failed"] == "oom"

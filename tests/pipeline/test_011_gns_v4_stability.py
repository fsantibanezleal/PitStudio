"""GNS v4 (FR-011-04): the published stabilisation methods for rollouts that must reach the reference rest time.

run-003 (40 epochs of 1,500 samples at batch 2, 30,000 optimiser steps, learning rate 1e-3) diverged on 9 of 10
validation geometries. The methods added here, each with its primary source:

- Push-forward (Brandstetter, Worrall and Welling 2022, "Message Passing Neural PDE Solvers", ICLR, arXiv:2202.03376):
  the model is unrolled `pushforward_steps` times WITHOUT gradient on its own predictions, and the loss of the next step
  is taken from that perturbed state, added to the one-step loss ("unrolling the solver for 2 steps but only
  backpropagating errors on the last unroll step"). The target of the perturbed step is the noise-correcting target of
  Sanchez-Gonzalez et al. 2020 (arXiv:2002.09405): the acceleration that lands exactly on the reference frame.
- Training length and learning rate (Sanchez-Gonzalez et al. 2020: up to 20 M steps, rate 1e-4 decayed by 0.1 every
  5 M; Choi and Kumar 2023, arXiv:2305.05218: about 5 M steps for the best rollouts of a granular column collapse).

Oracles by hand (independent of the code): a model that adds the constant acceleration a0 to a reference of constant
velocity v has, after k unrolled steps, v_k = v + k a0 dt and x_k - x_ref_k = a0 dt^2 k (k + 1) / 2; the acceleration
that lands on x_ref_(k+1) is -a0 k (k + 3) / 2 (k = 1: -2 a0, k = 2: -5 a0).
"""

from __future__ import annotations

import numpy as np
import pytest
import torch
from pitstudio_pipeline.surrogates.gns import evaluate, stages, train
from pitstudio_pipeline.surrogates.gns.model import GnsStep
from torch import nn

D, DT = 0.01, 0.01
A0 = np.array([0.7, -1.3])


class ConstantAcceleration(nn.Module):
    """A stand-in model: every particle gets the acceleration A0 whatever the input (it has a parameter)."""

    frame_interval = DT

    def __init__(self) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.zeros(1))
        self.calls = 0

    def acceleration_unchecked(self, positions, velocities, particle_type, bounds, index, mask):
        self.calls += 1
        return torch.as_tensor(A0, dtype=torch.float32).expand(positions.shape[0], 2) + 0.0 * self.weight


def constant_velocity_rollout(frames: int = 14, n_grain: int = 5, n_wall: int = 3) -> dict:
    rng = np.random.default_rng(3)
    v = np.array([0.2, -0.1])
    x0 = rng.uniform(0.2, 0.4, (n_grain, 2))
    t = np.arange(frames)[:, None, None] * DT
    grains = x0[None] + v[None, None, :] * t
    wall = np.stack([np.linspace(0.1, 0.5, n_wall), np.full(n_wall, 0.05)], axis=1)
    wall = np.repeat(wall[None], frames, axis=0) + np.array([0.01, 0.0]) * t  # the wall moves: held at the reference
    pos = np.concatenate([grains, wall], axis=1).astype(np.float32)
    types = np.array([0] * n_grain + [1] * n_wall)
    return {
        "positions": pos,
        "particle_types": types,
        "boundary": types == 1,
        "bounds": np.array([-5, -5, 5, 5], dtype=np.float32),
        "d": D,
        "dt": DT,
        "geometry_id": "g",
        "family": "column-collapse",
        "seed": 1,
    }


@pytest.mark.req("FR-011-04")
@pytest.mark.parametrize(("k", "factor"), [(1, -2.0), (2, -5.0)])
def test_011_the_pushforward_target_is_the_acceleration_that_lands_on_the_reference_from_the_predicted_state(
    k: int, factor: float
) -> None:
    rollout = constant_velocity_rollout()
    model = ConstantAcceleration()
    t = 6
    sample = train.pushforward_sample(model, rollout, t, radius=0.1, unroll=k)
    grains = ~rollout["boundary"]
    np.testing.assert_allclose(
        np.asarray(sample["target_acceleration"])[grains],
        np.tile(factor * A0, (int(grains.sum()), 1)),
        rtol=2e-3,
        atol=2e-3,
    )
    # the perturbed state: x_k - x_ref_k = a0 dt^2 k (k + 1) / 2 for every grain
    ref = rollout["positions"][t + k]
    error = np.asarray(sample["positions"])[grains] - ref[grains]
    np.testing.assert_allclose(error, np.tile(A0 * DT**2 * k * (k + 1) / 2, (int(grains.sum()), 1)), atol=2e-6)
    assert model.calls == k  # k unrolled steps, no more


@pytest.mark.req("FR-011-04")
def test_011_the_pushforward_state_holds_the_boundary_at_the_reference_and_keeps_it_out_of_the_loss() -> None:
    rollout = constant_velocity_rollout()
    t = 6
    sample = train.pushforward_sample(ConstantAcceleration(), rollout, t, radius=0.1, unroll=1)
    wall = rollout["boundary"]
    np.testing.assert_allclose(np.asarray(sample["positions"])[wall], rollout["positions"][t + 1][wall], atol=1e-7)
    ref_velocity = (rollout["positions"][t + 1][wall] - rollout["positions"][t][wall]) / DT
    np.testing.assert_allclose(np.asarray(sample["velocities"])[wall][:, -1, :], ref_velocity, atol=1e-4)
    assert np.asarray(sample["loss_mask"]).tolist() == (~wall).tolist()
    assert np.asarray(sample["particle_type"]).tolist() == rollout["particle_types"].tolist()


@pytest.mark.req("FR-011-04")
def test_011_the_pushforward_unroll_carries_no_gradient_and_leaves_the_model_alone() -> None:
    rollout = constant_velocity_rollout()
    model = ConstantAcceleration()
    before = model.weight.detach().clone()
    sample = train.pushforward_sample(model, rollout, 6, radius=0.1, unroll=2)
    for key in ("positions", "velocities", "target_acceleration"):
        assert not torch.as_tensor(sample[key]).requires_grad
    assert model.weight.grad is None
    assert torch.equal(model.weight.detach(), before)


@pytest.mark.req("FR-011-04")
def test_011_the_pushforward_clamps_at_the_last_reference_frame() -> None:
    rollout = constant_velocity_rollout(frames=9)
    sample = train.pushforward_sample(
        ConstantAcceleration(), rollout, 7, radius=0.1, unroll=2
    )  # t + 3 is beyond frame 8
    assert np.isfinite(np.asarray(sample["target_acceleration"])).all()


@pytest.mark.req("FR-011-04")
def test_011_the_config_validates_the_pushforward_and_warmup_settings() -> None:
    base = {"noise_scales": [0.05], "epochs": 1, "batch_size": 1, "lr": 1e-4, "connectivity_radius": 0.1}
    cfg = train.validate_config(base)
    assert cfg["pushforward_steps"] == 0
    assert cfg["pushforward_warmup_steps"] == 0
    cfg = train.validate_config({**base, "pushforward_steps": 1, "pushforward_warmup_steps": 500})
    assert (cfg["pushforward_steps"], cfg["pushforward_warmup_steps"]) == (1, 500)
    for bad in (
        {"pushforward_steps": -1},
        {"pushforward_steps": 1.5},
        {"pushforward_steps": True},
        {"pushforward_steps": "1"},
        {"pushforward_warmup_steps": -1},
        {"pushforward_warmup_steps": 2.5},
    ):
        with pytest.raises(ValueError, match=r".+"):
            train.validate_config({**base, **bad})


class Splits:
    def __init__(self, train_r, val_r):
        self._data = {"train": train_r, "val": val_r}

    def rollouts(self, name: str):
        if name == "test":
            raise AssertionError("the test split was read during training")
        return self._data[name]


def small_run(**extra) -> train._Run:
    rollouts = [constant_velocity_rollout(frames=20)]
    cfg = train.validate_config(
        {
            "noise_scales": [0.05],
            "epochs": 1,
            "batch_size": 2,
            "lr": 1e-3,
            "latent": 8,
            "steps": 1,
            "connectivity_radius": 0.1,
            "samples_per_epoch": 8,
            "device": "cpu",
            **extra,
        }
    )
    stats = train.compute_stats(rollouts)
    return train._Run(cfg, rollouts, rollouts, stats, 2, DT, 0, 4)


@pytest.mark.req("FR-011-04")
def test_011_the_pushforward_term_is_added_after_the_warmup_steps_only() -> None:
    off = small_run()
    off.epoch(0.05, 0)
    assert off.pushforward_applied == 0  # the default is the one-step loss alone
    warm = small_run(pushforward_steps=1, pushforward_warmup_steps=2)
    warm.epoch(0.05, 0)
    assert warm.pushforward_applied == 2  # 4 optimiser steps in the epoch, the first 2 are the warm-up
    full = small_run(pushforward_steps=1)
    full.epoch(0.05, 0)
    assert full.pushforward_applied == 4
    assert np.isfinite(full.pushforward_loss_mean)
    assert full.pushforward_loss_mean > 0.0


@pytest.mark.req("FR-011-04")
def test_011_training_with_pushforward_logs_its_loss_and_never_reads_the_test_split() -> None:
    rollouts = [constant_velocity_rollout(frames=20)]
    res = train.train_gns(
        Splits(rollouts, rollouts),
        {
            "noise_scales": [0.05],
            "epochs": 2,
            "batch_size": 2,
            "lr": 1e-3,
            "latent": 8,
            "steps": 1,
            "connectivity_radius": 0.1,
            "samples_per_epoch": 6,
            "pushforward_steps": 1,
        },
        seed=0,
    )
    assert all(np.isfinite(e["pushforward_loss"]) for e in res.log["epochs"])
    assert res.checkpoint["config"]["pushforward_steps"] == 1
    plain = train.train_gns(
        Splits(rollouts, rollouts),
        {
            "noise_scales": [0.05],
            "epochs": 1,
            "batch_size": 2,
            "lr": 1e-3,
            "latent": 8,
            "steps": 1,
            "connectivity_radius": 0.1,
            "samples_per_epoch": 4,
        },
        seed=0,
    )
    assert all("pushforward_loss" not in e for e in plain.log["epochs"])


@pytest.mark.req("FR-011-04")
def test_011_the_learning_rate_falls_to_the_final_ratio_over_the_planned_steps() -> None:
    run = small_run(lr=1e-4, lr_final_ratio=0.01)
    for _ in range(4):  # total_steps_hint of small_run is 4
        run.scheduler.step()
    assert run.optimiser.param_groups[0]["lr"] == pytest.approx(1e-6, rel=1e-6)


def validation_report(rows: list[tuple[str, bool, int | None, int, list[float]]]) -> dict:
    """A trimmed `evaluation.validation.json`: (geometry, diverged_before_rest, step, rest step, error growth)."""
    return {
        "geometries": [{"geometry_id": g, "position_error_growth": growth} for g, _, _, _, growth in rows],
        "validation_rollouts": [
            {
                "geometry_id": g,
                "diverged": step is not None,
                "diverged_at_step": step,
                "reference_steps_to_rest": rest,
                "diverged_before_rest": before,
            }
            for g, before, step, rest, _ in rows
        ],
    }


@pytest.mark.req("FR-011-04")
def test_011_the_pilot_rule_counts_geometries_that_reach_rest_then_the_smaller_position_error() -> None:
    a = validation_report([("g1", True, 40, 100, [0.0, 0.5]), ("g2", False, None, 100, [0.0, 0.1])])  # 1 reaches rest
    b = validation_report([("g1", False, None, 100, [0.0, 0.9]), ("g2", False, None, 100, [0.0, 0.9])])  # 2 reach rest
    c = validation_report(
        [("g1", False, None, 100, [0.0, 0.3]), ("g2", False, None, 100, [0.0, 0.3])]
    )  # 2, smaller error
    scores = {name: evaluate.pilot_score(report) for name, report in {"a": a, "b": b, "c": c}.items()}
    assert scores["a"]["reached_rest"] == 1
    assert scores["b"]["reached_rest"] == 2
    assert scores["b"]["mean_position_error_m"] == pytest.approx(0.45)
    assert evaluate.choose_pilot({"a": a, "b": b, "c": c}) == "c"
    assert evaluate.choose_pilot({"a": a, "b": b}) == "b"


@pytest.mark.req("FR-011-04")
def test_011_pilots_are_compared_on_the_same_geometries_only() -> None:
    a = validation_report([("g1", False, None, 100, [0.0, 0.1]), ("g2", False, None, 100, [0.0, 0.1])])
    b = validation_report([("g1", False, None, 100, [0.0, 0.1])])
    with pytest.raises(ValueError, match="geometr"):
        evaluate.choose_pilot({"a": a, "b": b})
    with pytest.raises(ValueError, match=r".+"):
        evaluate.choose_pilot({})


@pytest.mark.req("FR-011-04")
def test_011_the_evaluate_stage_can_take_the_machine_lock_and_run_on_cuda(capsys) -> None:
    with pytest.raises(SystemExit) as stop:
        stages.main(["evaluate", "--help"])
    assert stop.value.code == 0
    assert "--lock-dir" in capsys.readouterr().out


@pytest.mark.req("FR-011-04")
def test_011_the_real_model_runs_through_the_pushforward_sample() -> None:
    rollout = constant_velocity_rollout()
    model = GnsStep(connectivity_radius=0.1, frame_interval=DT, n_particle_types=2, latent=8, steps=1)
    sample = train.pushforward_sample(model, rollout, 6, radius=0.1, unroll=1)
    batch = train.collate([sample, sample], torch.device("cpu"))
    loss = train.one_step_loss(model, batch, stats=train.compute_stats([rollout]))
    assert torch.isfinite(loss)
    loss.backward()
    assert any(p.grad is not None and bool(p.grad.abs().sum() > 0) for p in model.parameters())


@pytest.mark.req("FR-011-04")
def test_011_the_matmul_precision_is_a_validated_config_value_that_the_run_applies() -> None:
    base = {"noise_scales": [0.05], "epochs": 1, "batch_size": 1, "lr": 1e-4, "connectivity_radius": 0.1}
    assert train.validate_config(base)["matmul_precision"] == "highest"  # full float32 unless asked
    for bad in ("fast", 1, None):
        with pytest.raises(ValueError, match="matmul_precision"):
            train.validate_config({**base, "matmul_precision": bad})
    before = torch.get_float32_matmul_precision()
    try:
        small_run(matmul_precision="high")
        assert torch.get_float32_matmul_precision() == "high"
        small_run()
        assert torch.get_float32_matmul_precision() == "highest"
    finally:
        torch.set_float32_matmul_precision(before)


@pytest.mark.req("FR-011-04")
def test_011_the_final_config_is_the_winning_pilot_scaled_to_the_gpu_budget_by_its_measured_rate() -> None:
    pilot = {"epochs": 8, "samples_per_epoch": 2000, "batch_size": 2, "lr": 1e-4, "pushforward_steps": 1}
    # 8,000 steps in 2 GPU-hours is 4,000 steps per hour: 12 GPU-hours buy 48,000 steps = 48 epochs of 1,000 steps
    final = evaluate.scale_config(pilot, pilot_gpu_hours=2.0, budget_gpu_hours=12.0)
    assert final["epochs"] == 48
    assert {k: v for k, v in final.items() if k != "epochs"} == {k: v for k, v in pilot.items() if k != "epochs"}
    assert pilot["epochs"] == 8  # the pilot's config is not changed
    assert evaluate.scale_config(pilot, pilot_gpu_hours=2.0, budget_gpu_hours=0.01)["epochs"] == 1  # at least one epoch
    for bad in (0.0, -1.0, float("nan")):
        with pytest.raises(ValueError, match="gpu_hours"):
            evaluate.scale_config(pilot, pilot_gpu_hours=bad, budget_gpu_hours=12.0)
    with pytest.raises(ValueError, match="gpu_hours"):
        evaluate.scale_config(pilot, pilot_gpu_hours=2.0, budget_gpu_hours=0.0)


@pytest.mark.req("FR-011-04")
def test_011_the_choose_command_applies_the_pilot_rule_and_writes_the_final_config(tmp_path, capsys) -> None:
    import json

    def pilot(name: str, rows, config: dict, gpu_hours: float) -> None:
        run = tmp_path / "pilots" / name
        run.mkdir(parents=True)
        (run / "evaluation.validation.json").write_text(json.dumps(validation_report(rows)), encoding="utf-8")
        (run / "pilot.json").write_text(json.dumps({"gpu_hours_train": gpu_hours}), encoding="utf-8")
        (tmp_path / f"config-{name}.json").write_text(json.dumps(config), encoding="utf-8")

    base = {"epochs": 8, "samples_per_epoch": 2000, "batch_size": 2, "lr": 1e-4}
    pilot("pilot-a", [("g1", True, 40, 100, [0.0, 0.5])], {**base, "lr": 1e-3}, 1.0)
    pilot("pilot-b", [("g1", False, None, 100, [0.0, 0.2])], {**base, "pushforward_steps": 1}, 2.0)
    out = tmp_path / "config-004.json"
    code = stages.main(
        [
            "choose",
            "--pilots-dir", str(tmp_path / "pilots"),
            "--config-pattern", str(tmp_path / "config-{name}.json"),
            "--budget-gpu-hours", "12",
            "--out", str(out),
        ]
    )  # fmt: skip
    assert code == 0
    chosen = json.loads(out.read_text(encoding="utf-8"))
    assert chosen["pushforward_steps"] == 1  # pilot-b reaches rest on its geometry, pilot-a does not
    assert chosen["epochs"] == 48  # 8,000 steps in 2 GPU-hours scaled to 12 GPU-hours
    assert json.loads(capsys.readouterr().out)["winner"] == "pilot-b"
    assert chosen["chosen_from"] == {"pilot": "pilot-b", "reached_rest": 1, "n_geometries": 1}

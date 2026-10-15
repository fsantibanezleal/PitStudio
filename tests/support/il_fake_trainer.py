# ruff: noqa: E501
"""Shared fakes of the spec 014 training-wrapper tests (T-014-040, T-014-049, T-014-048, T-014-092 and T-014-093).

This module holds no test. It is imported by `tests/unit/test_t_014_0*.py` and is locked with the first of them.

`FakeTrainer` implements the trainer interface that `pitstudio.robots.training.run_stage` drives (see T-014-040 for the interface):
a deterministic stand-in for an rsl_rl PPO runner. Its whole state is plain integers and floats, so that "the same iteration count,
optimiser state and normaliser statistics" can be compared exactly. Nothing here imports torch, Isaac Lab or any code under test.

State after iteration i (a hand-written recurrence, the oracle of the resume-equality test):
    iteration = i
    optimiser_steps = 24 * num_envs_independent_constant * i      (here: 24 * i, the steps per update)
    normaliser_count = 1000 * i
    normaliser_mean = sum_{k=1..i} k / i   = (i + 1) / 2          (a running mean of the iteration numbers)
Independent of `num_envs`, so that a halved environment count (OOM fallback) continues the same trajectory.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


class OutOfMemoryError(RuntimeError):
    """Stands for torch.cuda.OutOfMemoryError (the wrapper recognises it by class name or by message)."""


class FakeTrainer:
    def __init__(
        self,
        ppo: Any,
        num_envs: int,
        *,
        fail_at: Callable[[int, int], Exception | None] | None = None,
        log: list[tuple[str, int]] | None = None,
    ) -> None:
        self.ppo = ppo
        self.num_envs = num_envs
        self.iteration = 0
        self.optimiser_steps = 0
        self.normaliser_count = 0
        self.normaliser_sum = 0.0
        self.fail_at = fail_at
        self.log = log if log is not None else []
        self.saved: list[int] = []

    # the interface driven by the wrapper ------------------------------------------------------------
    def train_iteration(self, iteration: int) -> dict[str, float]:
        """Run PPO iteration number `iteration` (1-based). Must be called with `self.iteration + 1`."""
        assert iteration == self.iteration + 1, f"iterations must be consecutive: {iteration} after {self.iteration}"
        if self.fail_at is not None:
            err = self.fail_at(iteration, self.num_envs)
            if err is not None:
                raise err
        self.iteration = iteration
        self.optimiser_steps += 24
        self.normaliser_count += 1000
        self.normaliser_sum += float(iteration)
        self.log.append(("iteration", iteration))
        return {"loss": 1.0 / iteration, "value_loss": 0.5 / iteration}

    def save(self, path: Path) -> None:
        path = Path(path)
        path.write_text(json.dumps({**self.state, "normaliser_sum": self.normaliser_sum}), encoding="utf-8")
        self.saved.append(self.iteration)
        self.log.append(("save", self.iteration))

    def load(self, path: Path) -> None:
        state = json.loads(Path(path).read_text(encoding="utf-8"))
        self.iteration = state["iteration"]
        self.optimiser_steps = state["optimiser_steps"]
        self.normaliser_count = state["normaliser_count"]
        self.normaliser_sum = state["normaliser_sum"]
        self.log.append(("load", self.iteration))

    # observable state ---------------------------------------------------------------------------------
    @property
    def state(self) -> dict[str, float]:
        mean = self.normaliser_sum / self.iteration if self.iteration else 0.0
        return {
            "iteration": self.iteration,
            "optimiser_steps": self.optimiser_steps,
            "normaliser_count": self.normaliser_count,
            "normaliser_mean": mean,
        }


def expected_state(iteration: int) -> dict[str, float]:
    """The hand-written recurrence of the module docstring in closed form."""
    return {
        "iteration": iteration,
        "optimiser_steps": 24 * iteration,
        "normaliser_count": 1000 * iteration,
        "normaliser_mean": (iteration + 1) / 2 if iteration else 0.0,
    }


class Factory:
    """A `make_trainer(ppo, num_envs)` callable that records every trainer it builds."""

    def __init__(self, fail_at: Callable[[int, int], Exception | None] | None = None) -> None:
        self.fail_at = fail_at
        self.trainers: list[FakeTrainer] = []
        self.log: list[tuple[str, int]] = []

    def __call__(self, ppo: Any, num_envs: int) -> FakeTrainer:
        trainer = FakeTrainer(ppo, num_envs, fail_at=self.fail_at, log=self.log)
        self.trainers.append(trainer)
        return trainer

# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""Training-stage wrapper (FR-014-25, FR-014-26, FR-014-46): PPO configuration, checkpoint cadence, resume, OOM fallback.

The wrapper is torch-free: it drives any trainer with ``train_iteration(i)``, ``save(path)`` and ``load(path)``. The Isaac
Lab package supplies the real rsl_rl runner behind the same interface. Iteration counters are 1-based. A checkpoint
``model_<i>.pt`` is written next to a sidecar ``model_<i>.json`` holding the iteration, the task-configuration hash and
the environment count; ``resume`` refuses a checkpoint whose hash differs from the current configuration.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pitstudio.robots.config import TaskParamsError, config_hash, validate_task_params
from pitstudio.robots.fixture import is_fixture

__all__ = ["PpoConfig", "StageResult", "is_oom", "latest_checkpoint", "ppo_config", "run_stage"]

_CHECKPOINT = re.compile(r"model_(\d+)\.pt$")


@dataclass(frozen=True)
class PpoConfig:
    hidden_units: tuple[int, ...]
    gamma: float
    gae_lambda: float
    clip_ratio: float
    steps_per_env: int
    num_envs: int


@dataclass(frozen=True)
class StageResult:
    exit_code: int
    manifest: dict[str, Any]
    checkpoints: list[Path]
    message: str


def ppo_config(params: dict[str, Any], num_envs: int | None = None) -> PpoConfig:
    """PPO settings of a valid IL task document; ``num_envs`` overrides the environment count."""
    t = params["training"]
    return PpoConfig(
        hidden_units=tuple(t["hidden_units"]),
        gamma=t["gamma"],
        gae_lambda=t["gae_lambda"],
        clip_ratio=t["clip_ratio"],
        steps_per_env=t["steps_per_env"],
        num_envs=int(t["num_envs"] if num_envs is None else num_envs),
    )


def is_oom(exc: BaseException) -> bool:
    return type(exc).__name__ == "OutOfMemoryError" or "CUDA out of memory" in str(exc)


def _checkpoints(out_dir: Path) -> list[tuple[int, Path]]:
    found = []
    for path in (Path(out_dir) / "checkpoints").glob("model_*.pt"):
        m = _CHECKPOINT.search(path.name)
        if m:
            found.append((int(m.group(1)), path))
    return sorted(found)


def latest_checkpoint(out_dir: Path | str) -> Path | None:
    """The checkpoint with the highest iteration under ``<out_dir>/checkpoints``."""
    found = _checkpoints(Path(out_dir))
    return found[-1][1] if found else None


def _refuse(message: str, params: Any = None) -> StageResult:
    return StageResult(exit_code=2, manifest={"failed": "invalid-input"}, checkpoints=[], message=message)


def _sidecar(checkpoint: Path, expected_hash: str) -> tuple[int | None, str | None]:
    """(iteration, error message) of the sidecar of a resume checkpoint."""
    side = checkpoint.with_suffix(".json")
    if not checkpoint.is_file() or not side.is_file():
        return None, f"checkpoint {checkpoint.name}: the file or its sidecar is missing"
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
        recorded, iteration = data["task_config_sha256"], int(data["iteration"])
    except OSError, ValueError, KeyError, TypeError:
        return None, f"checkpoint {checkpoint.name}: the sidecar is unreadable"
    if recorded != expected_hash:
        return None, (
            f"task_config_sha256 of checkpoint {checkpoint.name} ({recorded}) differs from the current configuration "
            f"({expected_hash})"
        )
    return iteration, None


def run_stage(
    params: dict[str, Any],
    make_trainer: Callable[[PpoConfig, int], Any],
    out_dir: Path | str,
    *,
    resume: Path | str | None = None,
    fixture: bool | None = None,
    params_path: Path | str | None = None,
) -> StageResult:
    """Validate, then train iterations 1 .. N with checkpoints, optional resume and one OOM fallback."""
    is_fix = is_fixture(params_path, flag=fixture)
    try:
        validate_task_params(params)
    except TaskParamsError as err:
        return _refuse(str(err))
    out = Path(out_dir)
    digest = config_hash(params)
    total = int(params["training"]["iterations"])
    every = int(params["training"]["checkpoint_every"])
    start = 0
    resume_path: Path | None = None
    if resume is not None:
        resume_path = Path(resume)
        start_it, error = _sidecar(resume_path, digest)
        if error is not None:
            return _refuse(error)
        start = int(start_it or 0)

    ppo = ppo_config(params)
    num_envs = ppo.num_envs
    manifest: dict[str, Any] = {
        "num_envs": num_envs,
        "iterations_completed": start,
        "oom_fallback": None,
        "ppo": asdict(ppo),
        "failed": None,
        "fixture": is_fix,
    }
    written: list[Path] = []

    def save(trainer: Any, iteration: int, envs: int) -> None:
        directory = out / "checkpoints"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"model_{iteration}.pt"
        trainer.save(path)
        side: dict[str, Any] = {"iteration": iteration, "task_config_sha256": digest, "num_envs": envs}
        if is_fix:
            side["fixture"] = True
        path.with_suffix(".json").write_text(json.dumps(side, sort_keys=True), encoding="utf-8")
        if path not in written:
            written.append(path)

    trainer = make_trainer(ppo_config(params, num_envs), num_envs)
    if resume_path is not None:
        trainer.load(resume_path)
    done = start
    while done < total:
        iteration = done + 1
        try:
            trainer.train_iteration(iteration)
        except Exception as exc:
            if not is_oom(exc):
                raise
            half = num_envs // 2
            if manifest["oom_fallback"] is not None or half < 1:
                manifest["failed"] = "oom"
                manifest["iterations_completed"] = done
                return StageResult(1, manifest, written, f"CUDA out of memory at iteration {iteration}: stage failed")
            last = latest_checkpoint(out)
            resumed_from = 0
            if last is not None:
                resumed_from = int(_CHECKPOINT.search(last.name).group(1))  # type: ignore[union-attr]
            manifest["oom_fallback"] = {
                "from": num_envs,
                "to": half,
                "at_iteration": iteration,
                "resumed_from": resumed_from,
            }
            num_envs = half
            manifest["num_envs"] = num_envs
            trainer = make_trainer(ppo_config(params, num_envs), num_envs)
            if last is not None:
                trainer.load(last)
            done = resumed_from
            continue
        done = iteration
        manifest["iterations_completed"] = done
        if done % every == 0 or done == total:
            save(trainer, done, num_envs)
    manifest["checkpoints"] = [p.name for p in written]
    return StageResult(0, manifest, written, "ok")

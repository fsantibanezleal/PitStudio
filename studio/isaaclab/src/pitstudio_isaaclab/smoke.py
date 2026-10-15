# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""Kit-less smoke of Isaac Lab's stock Cartpole direct task on the Newton MuJoCo-Warp backend (T-014-060, FR-014-02).

``python -m pitstudio_isaaclab.smoke --iterations 10 --num-envs 64`` trains the stock task for the requested PPO
iterations with Isaac Sim absent and prints, as its last line, one JSON object with the raw loss records. The pass rule is
the one of the capability probe: at least 10 iterations, every loss finite, no Kit module imported.
``--dry-run`` stops before any CUDA work: it asserts a CUDA device is visible, imports the Isaac Lab training entry point
and rsl_rl, mirrors the Cartpole assets locally and reports the versions read from the lock.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from pitstudio_isaaclab import runtime

TASK = "Isaac-Cartpole-Direct"
PHYSICS = "newton_mjwarp"
MIN_ITERATIONS = 10


def pass_rule(losses: list[dict[str, float]], requested: int) -> tuple[str, str | None]:
    if requested < MIN_ITERATIONS:
        return "fail", f"{requested} iterations requested, at least {MIN_ITERATIONS} are required"
    if len(losses) < requested:
        return "fail", f"only {len(losses)} of {requested} PPO iterations completed"
    for i, record in enumerate(losses):
        if not record or not all(math.isfinite(v) for v in record.values()):
            return "fail", f"empty or non-finite loss record at iteration {i}"
    return "pass", None


def _work_dir() -> Path:
    base = os.environ.get("PITSTUDIO_TMP") or tempfile.gettempdir()
    path = Path(base) / "isaaclab-smoke"
    path.mkdir(parents=True, exist_ok=True)
    return path


def dry_run() -> dict[str, Any]:
    device = runtime.require_cuda()
    guard_limit = runtime.check_guard_import()
    work = _work_dir()
    os.environ["ISAACSIM_ASSET_ROOT"] = str(runtime.local_asset_root(work))
    from isaaclab_rl.entrypoints.backends import train_rsl_rl  # noqa: F401  (the import is the check)
    from rsl_rl.algorithms import PPO  # noqa: F401

    return {
        "status": "dry-run-ok", "task": TASK, "physics": PHYSICS, "device": device, "versions": runtime.lock_versions(),
        "kit_modules": runtime.kit_modules(), "asset_root": "mirrored", "guard": guard_limit,
    }  # fmt: skip


def train(iterations: int, num_envs: int) -> dict[str, Any]:
    import torch

    device = runtime.require_cuda()
    versions = runtime.lock_versions()
    versions["cuda"] = torch.version.cuda or "none"
    work = _work_dir()
    os.environ["ISAACSIM_ASSET_ROOT"] = str(runtime.local_asset_root(work))
    os.chdir(work)  # the trainer writes logs and checkpoints relative to the working directory
    losses: list[dict[str, float]] = []
    error: str | None = None
    with runtime.gpu_session() as guard:
        from rsl_rl.algorithms import PPO

        real_update = PPO.update

        def recording_update(self: Any) -> dict[str, float]:
            guard.check()
            out = real_update(self)
            losses.append({k: float(v) for k, v in out.items()})
            return out

        PPO.update = recording_update  # type: ignore[method-assign]
        from isaaclab_rl.entrypoints.backends import train_rsl_rl

        argv = ["--task", TASK, "--max_iterations", str(iterations), "--num_envs", str(num_envs), f"physics={PHYSICS}"]
        t0 = time.perf_counter()
        try:
            train_rsl_rl.run(argv)
        except Exception as exc:  # reported in the JSON, never raised past it
            error = f"{type(exc).__name__}: {exc}"
        wall = time.perf_counter() - t0
    status, reason = pass_rule(losses, iterations)
    kit = runtime.kit_modules()
    if kit:
        status, reason = "fail", f"Isaac Sim / Kit modules were imported: {kit[:5]}"
    if error and status == "pass":
        status, reason = "fail", error
    return {
        "status": status, "reason": reason or error, "task": TASK, "physics": PHYSICS,
        "iterations_completed": len(losses), "losses": losses, "kit_modules": kit, "versions": versions,
        "device": device, "wall_s": round(wall, 2),
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=MIN_ITERATIONS)
    parser.add_argument("--num-envs", type=int, default=64)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = dry_run() if args.dry_run else train(args.iterations, args.num_envs)
    runtime.emit(result)
    return 0 if result["status"] in ("pass", "dry-run-ok") else 1


if __name__ == "__main__":
    sys.exit(main())

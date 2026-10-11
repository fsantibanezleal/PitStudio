"""Probe (studio/isaaclab env): Isaac Lab trains its stock Cartpole direct task kit-less on Newton (MuJoCo-Warp).

Runs Isaac Lab's own rsl_rl training entrypoint (isaaclab_rl.entrypoints.backends.train_rsl_rl) for a few PPO
iterations on the `newton_mjwarp` physics preset, with no Isaac Sim / Kit module loaded, and passes only when every
loss is finite. Versions are read from the installed distributions of this environment.
Publishing: "public" only when the environment lock holds no NVIDIA-licensed package (isaacsim*, omni*, ovrtx,
ovstage, ovphysx); otherwise "local-only".
"""

from __future__ import annotations

import math
import os
import re
import sys
import time
from importlib import metadata
from pathlib import Path
from typing import Any

from _common import run_probe, tmp_dir

TASK = "Isaac-Cartpole-Direct"
PHYSICS = "newton_mjwarp"
ITERATIONS = 10
NUM_ENVS = 256
RESTRICTED = re.compile(r"^(isaacsim|omni|ovrtx$|ovstage$|ovphysx$)")
DISTS = (
    "isaaclab",
    "isaaclab-newton",
    "isaaclab-tasks",
    "isaaclab-rl",
    "torch",
    "torchvision",
    "warp-lang",
    "newton",
    "mujoco",
    "mujoco-warp",
    "rsl-rl-lib",
)
KIT_PREFIXES = ("isaacsim", "omni", "carb", "ovrtx", "ovstage", "ovphysx")


def _version(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "missing"


def lock_restricted() -> list[str]:
    """Packages of studio/isaaclab/uv.lock covered by the NVIDIA licence terms (empty means publishable)."""
    lock = Path(__file__).resolve().parents[1] / "isaaclab" / "uv.lock"
    names = re.findall(r'^name = "([^"]+)"', lock.read_text(encoding="utf-8"), flags=re.M)
    return sorted(n for n in names if RESTRICTED.match(n.lower()))


def body(r: dict[str, Any]) -> None:
    import torch

    r["versions"].update({d.replace("-", "_"): _version(d) for d in DISTS})
    r["versions"]["cuda"] = torch.version.cuda or "none"
    if not torch.cuda.is_available():
        raise RuntimeError("torch sees no CUDA device")
    r["metrics"]["device"] = torch.cuda.get_device_name(0)
    r["metrics"]["arch"] = "sm_%d%d" % torch.cuda.get_device_capability(0)
    restricted = lock_restricted()
    r["metrics"]["restricted_packages_in_lock"] = restricted
    r["notes"].append("publishable: the environment lock holds no isaacsim/omni/ov* package" if not restricted else
                      "local-only: the environment lock holds licence-restricted packages")

    os.chdir(tmp_dir("isaaclab"))  # the trainer writes logs/ and checkpoints relative to the working directory
    from rsl_rl.algorithms import PPO

    losses: list[dict[str, float]] = []
    real_update = PPO.update

    def recording_update(self: Any) -> dict[str, float]:
        out = real_update(self)
        losses.append({k: float(v) for k, v in out.items()})
        return out

    PPO.update = recording_update  # type: ignore[method-assign]
    from isaaclab_rl.entrypoints.backends import train_rsl_rl

    argv = ["--task", TASK, "--max_iterations", str(ITERATIONS), "--num_envs", str(NUM_ENVS), f"physics={PHYSICS}"]
    t0 = time.perf_counter()
    train_rsl_rl.run(argv)
    wall = time.perf_counter() - t0

    r["metrics"].update(task=TASK, physics_preset=PHYSICS, num_envs=NUM_ENVS, iterations_requested=ITERATIONS)
    r["metrics"]["iterations_completed"] = len(losses)
    r["metrics"]["train_wall_s"] = round(wall, 2)
    if len(losses) < ITERATIONS:
        raise AssertionError(f"only {len(losses)} of {ITERATIONS} PPO iterations completed")
    bad = [i for i, d in enumerate(losses) if not all(math.isfinite(v) for v in d.values())]
    if bad:
        raise AssertionError(f"non-finite losses at iterations {bad}: {losses[bad[0]]}")
    r["metrics"]["final_losses"] = {k: round(v, 5) for k, v in losses[-1].items()}
    kit = sorted(m for m in sys.modules if m.split(".")[0] in KIT_PREFIXES)
    r["metrics"]["kit_modules_loaded"] = kit[:5]
    if kit:
        raise AssertionError(f"Isaac Sim / Kit modules were imported: {kit[:5]}")


if __name__ == "__main__":
    run_probe("isaaclab", "local-only" if lock_restricted() else "public", body)

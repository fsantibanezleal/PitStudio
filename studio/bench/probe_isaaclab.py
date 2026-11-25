# ruff: noqa: E501
"""Probe (studio/isaaclab env): Isaac Lab trains its stock Cartpole direct task kit-less on Newton (MuJoCo-Warp).

Runs Isaac Lab's own rsl_rl training entrypoint (isaaclab_rl.entrypoints.backends.train_rsl_rl) for a few PPO
iterations on the `newton_mjwarp` physics preset, with no Isaac Sim / Kit module loaded, and passes only when every
loss is finite. Publishing: "public" only when the environment lock holds no NVIDIA-licensed package (isaacsim*, omni*, ovrtx,
ovstage, ovphysx); otherwise "local-only".
Versions are read from studio/isaaclab/uv.lock (the single source of every manifest), not from what happens to be installed.
"""

from __future__ import annotations

import math
import os
import re
import sys
import time
import tomllib
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
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
CARTPOLE_ASSETS = (  # the files the stock Cartpole direct task loads (articulation, its meshes, ground plane)
    "Isaac/IsaacLab/Robots/Classic/Cartpole/cartpole.usd",
    "Isaac/IsaacLab/Robots/Classic/Cartpole/Props/instanceable_meshes.usd",
    "Isaac/IsaacLab/Environments/Grid/default_ground_plane_checker_v1/default_ground_plane.usda",
)
KIT_PREFIXES = ("isaacsim", "omni", "carb", "ovrtx", "ovstage", "ovphysx")


LOCK = Path(__file__).resolve().parents[1] / "isaaclab" / "uv.lock"


def _lock_packages() -> dict[str, str]:
    """Package name to version of studio/isaaclab/uv.lock (the first entry of a name listed twice)."""
    out: dict[str, str] = {}
    for entry in tomllib.loads(LOCK.read_text(encoding="utf-8"))["package"]:
        out.setdefault(entry["name"], entry["version"])
    return out


def lock_versions() -> dict[str, str]:
    """Versions of DISTS read from the lock, keyed with "-" written as "_"."""
    packages = _lock_packages()
    missing = [d for d in DISTS if d not in packages]
    if missing:
        raise RuntimeError(f"packages missing from {LOCK.name}: {missing}")
    return {d.replace("-", "_"): packages[d] for d in DISTS}


def lock_restricted() -> list[str]:
    """Packages of studio/isaaclab/uv.lock covered by the NVIDIA licence terms (empty means publishable)."""
    return sorted(n for n in _lock_packages() if RESTRICTED.match(n.lower()))


def publish_marker() -> str:
    """ "local-only" when the lock holds a package covered by SLA 8.9, else "public"."""
    return "local-only" if lock_restricted() else "public"


def kit_modules(module_names: Iterable[str]) -> list[str]:
    """The sorted Isaac Sim and Kit modules among module_names (first dotted component in KIT_PREFIXES)."""
    return sorted(m for m in module_names if m.split(".")[0] in KIT_PREFIXES)


def evaluate_losses(losses: Sequence[Mapping[str, float]], iterations_requested: int) -> tuple[str, str | None]:
    """("pass", None) only with at least ITERATIONS completed PPO iterations whose every loss value is finite."""
    if iterations_requested < ITERATIONS:
        return "fail", f"{iterations_requested} iterations requested, the requirement demands at least {ITERATIONS}"
    if len(losses) < iterations_requested:
        return "fail", f"only {len(losses)} of {iterations_requested} PPO iterations completed"
    for i, record in enumerate(losses):
        if not record:
            return "fail", f"no loss values were recorded at iteration {i}"
        for key, value in record.items():
            if not math.isfinite(value):
                return "fail", f"non-finite loss at iteration {i}: {key} = {value}"
    return "pass", None


def local_asset_root() -> Path:
    """Mirror the Cartpole USD files locally and return the asset root that serves them.

    Isaac Lab's remote-asset check (`isaaclab.utils.assets._remote_fingerprint`) imports `omni.client`, a Kit module, so
    a kit-less run must find its assets as local files: `check_file_path` returns before that import when the file
    exists (`os.path.isfile`), and `ISAACSIM_ASSET_ROOT` is the documented way to move the asset root
    (`_resolve_asset_root`). The remote root is the one the env's `apps/isaaclab.python.kit` configures.
    """
    kit = Path(sys.prefix) / "apps" / "isaaclab.python.kit"
    m = re.search(r'persistent\.isaac\.asset_root\.default\s*=\s*"([^"]+)"', kit.read_text(encoding="utf-8"))
    if not m:
        raise RuntimeError("no persistent.isaac.asset_root.default in isaaclab.python.kit (run fetch_kit_app.py)")
    remote = m.group(1).rstrip("/")
    root = tmp_dir("isaaclab") / "assets"
    for rel in CARTPOLE_ASSETS:
        dest = root / rel
        if not dest.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(f"{remote}/{rel}", timeout=120) as resp:
                dest.write_bytes(resp.read())
    return root


def body(r: dict[str, Any]) -> None:
    import torch

    r["versions"].update(lock_versions())
    r["versions"]["cuda"] = torch.version.cuda or "none"
    if not torch.cuda.is_available():
        raise RuntimeError("torch sees no CUDA device")
    r["metrics"]["device"] = torch.cuda.get_device_name(0)
    major, minor = torch.cuda.get_device_capability(0)
    r["metrics"]["arch"] = f"sm_{major}{minor}"
    restricted = lock_restricted()
    r["metrics"]["restricted_packages_in_lock"] = restricted
    r["notes"].append(
        "publishable: the environment lock holds no isaacsim/omni/ov* package"
        if not restricted
        else "local-only: the environment lock holds licence-restricted packages"
    )

    os.environ["ISAACSIM_ASSET_ROOT"] = str(local_asset_root())  # read when isaaclab.utils.assets is imported
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
    status, error = evaluate_losses(losses, ITERATIONS)
    if status != "pass":
        raise AssertionError(error)
    r["metrics"]["final_losses"] = {k: round(v, 5) for k, v in losses[-1].items()}
    kit = kit_modules(sys.modules)
    r["metrics"]["kit_modules_loaded"] = kit[:5]
    if kit:
        raise AssertionError(f"Isaac Sim / Kit modules were imported: {kit[:5]}")


if __name__ == "__main__":
    run_probe("isaaclab", publish_marker(), body)

# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""Shared runtime of the Isaac Lab lane entry points: lock versions, GPU lock and guard, Kit-module scan, JSON output.

Every entry point of this package prints one JSON object as the last line of stdout. A GPU run takes the machine lock
``gpu0.compute`` (a file under ``$GPU_LOCK_DIR``), refuses to start above 80 C, and calls ``Guard.check()`` between PPO
iterations (at most every few seconds of GPU work). Nothing here imports Isaac Sim or a Kit module.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import tomllib
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]  # studio/isaaclab
LOCK_FILE = PROJECT / "uv.lock"
BENCH = PROJECT.parent / "bench"
KIT_PREFIXES = ("isaacsim", "omni", "carb", "ovrtx", "ovstage", "ovphysx")
LOCK_NAME = "gpu0.compute"
VERSION_DISTS = {
    "isaaclab": "isaaclab",
    "isaaclab_newton": "isaaclab-newton",
    "isaaclab_tasks": "isaaclab-tasks",
    "isaaclab_rl": "isaaclab-rl",
    "torch": "torch",
    "torchvision": "torchvision",
    "warp_lang": "warp-lang",
    "newton": "newton",
    "mujoco": "mujoco",
    "mujoco_warp": "mujoco-warp",
    "rsl_rl_lib": "rsl-rl-lib",
}
CARTPOLE_ASSETS = (
    "Isaac/IsaacLab/Robots/Classic/Cartpole/cartpole.usd",
    "Isaac/IsaacLab/Robots/Classic/Cartpole/Props/instanceable_meshes.usd",
    "Isaac/IsaacLab/Environments/Grid/default_ground_plane_checker_v1/default_ground_plane.usda",
)


def lock_versions() -> dict[str, str]:
    """Versions of the pinned packages, read from studio/isaaclab/uv.lock (never from what is installed)."""
    packages: dict[str, str] = {}
    for entry in tomllib.loads(LOCK_FILE.read_text(encoding="utf-8"))["package"]:
        packages.setdefault(entry["name"], entry["version"])
    return {key: packages[dist] for key, dist in VERSION_DISTS.items()}


def kit_modules(names: Any = None) -> list[str]:
    """Sorted Isaac Sim and Kit modules among ``names`` (default: the imported modules)."""
    return sorted(m for m in (sys.modules if names is None else names) if m.split(".")[0] in KIT_PREFIXES)


def require_cuda() -> str:
    """The CUDA device name; raises when torch sees none (a dry run asserts this before any GPU work)."""
    import torch

    if not torch.cuda.is_available():
        raise SystemExit("torch sees no CUDA device: refusing to stage or start a GPU job")
    return torch.cuda.get_device_name(0)


def emit(result: dict[str, Any]) -> None:
    print(json.dumps(result, default=str), flush=True)


def _guard_module() -> Any:
    if str(BENCH) not in sys.path:
        sys.path.insert(0, str(BENCH))
    import gpu_guard

    return gpu_guard


@contextmanager
def gpu_session(wait_cool_s: float = 1800.0) -> Iterator[Any]:
    """Wait until the GPU is at most 80 C, take the machine lock, yield a ``Guard``; release the lock on exit."""
    from filelock import FileLock

    gpu_guard = _guard_module()
    lock_dir = os.environ.get("GPU_LOCK_DIR")
    if not lock_dir:
        raise SystemExit("GPU_LOCK_DIR is not set: the GPU lock folder is required for a GPU run")
    Path(lock_dir).mkdir(parents=True, exist_ok=True)
    guard = gpu_guard.Guard()
    deadline = time.monotonic() + wait_cool_s
    while guard.read_temp() > gpu_guard.START_MAX_C:
        if time.monotonic() > deadline:
            raise SystemExit(f"GPU stayed above {gpu_guard.START_MAX_C} C: not starting")
        time.sleep(30)
    lock = FileLock(str(Path(lock_dir) / LOCK_NAME))
    lock.acquire()
    try:
        yield gpu_guard.Guard()
    finally:
        lock.release()


def local_asset_root(work: Path) -> Path:
    """Mirror the stock Cartpole USD files locally and return the asset root (ISAACSIM_ASSET_ROOT).

    Isaac Lab's remote-asset check imports a Kit module, so a kit-less run must find its assets as local files. The remote
    root is the one the environment's ``apps/isaaclab.python.kit`` configures (written by ``fetch_kit_app.py``).
    """
    kit = Path(sys.prefix) / "apps" / "isaaclab.python.kit"
    m = re.search(r'persistent\.isaac\.asset_root\.default\s*=\s*"([^"]+)"', kit.read_text(encoding="utf-8"))
    if not m:
        raise RuntimeError("no persistent.isaac.asset_root.default in isaaclab.python.kit (run fetch_kit_app.py)")
    remote = m.group(1).rstrip("/")
    root = work / "assets"
    for rel in CARTPOLE_ASSETS:
        dest = root / rel
        if not dest.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(f"{remote}/{rel}", timeout=120) as resp:
                dest.write_bytes(resp.read())
    return root

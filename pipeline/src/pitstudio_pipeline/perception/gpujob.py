"""Common frame of a queued GPU job: CUDA assertion, start temperature, the machine lock and the in-run guard.

Every GPU stage runs under `gpu_session`: it asserts `torch.cuda.is_available()` (a CPU-only torch is a broken
environment,
not a reason to run on the CPU), refuses to start above 80 C, takes the machine lock `gpu0.compute` and gives the
caller the
guard whose `check()` must run at least every 30 s of GPU work (`studio/bench/gpu_guard.py`). A dry run asserts CUDA and
stops before touching it.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

LOCK_ENV = "PITSTUDIO_GPU_LOCK"
DEFAULT_LOCK = (
    r"C:\Users\felipe.santibanez\Data\_Temp\_locks\gpu0.compute"  # this machine; other machines set the env var
)


def assert_cuda() -> None:
    """Fail when the environment has no CUDA torch (a plain `uv sync` swaps it for the CPU build)."""
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("torch.cuda.is_available() is False: sync the environment with its CUDA extra (cu130)")


def _guard_module() -> Any:
    root = Path(__file__).resolve().parents[4]
    bench = str(root / "studio" / "bench")
    if bench not in sys.path:
        sys.path.insert(0, bench)
    import gpu_guard

    return gpu_guard


@contextlib.contextmanager
def gpu_session() -> Iterator[Any]:
    """Hold the GPU lock and yield the guard; the caller calls `guard.check()` between steps (at most 30 s apart)."""
    assert_cuda()
    gg = _guard_module()
    guard = gg.Guard()
    temp = guard.read_temp()
    if temp > gg.START_MAX_C:
        raise RuntimeError(f"GPU at {temp} C, above the start limit {gg.START_MAX_C} C")
    from filelock import FileLock

    with FileLock(os.environ.get(LOCK_ENV, DEFAULT_LOCK)):
        yield guard

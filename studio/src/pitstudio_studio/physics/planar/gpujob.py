"""GPU job plumbing of the planar generator: machine lock `gpu0.compute`, start temperature and the in-run guard.

A GPU stage of the reference-data generator is a queue job (spec 002 queue protocol): it refuses to start above 80 C,
waits
for the machine lock, and calls `Guard.check()` between frames (pause when hot, stop when too hot or on a hardware
error,
and a cool-down between GPU blocks). `Pacer` bundles those calls; the batch functions of `engine` only see `check`,
`idle_s` and `max_temp`.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path
from typing import Any

import filelock

LOCK_ENV = "PITSTUDIO_GPU_LOCK"
LOCK_TRIES = 36  # bounded wait: 36 x 10 min
START_WAIT_TRIES = 60  # bounded wait for the start temperature: 60 x 30 s


def load_guard_module() -> Any:
    """`studio/bench/gpu_guard.py` (standard library only), loaded from the checkout."""
    path = Path(__file__).resolve().parents[4] / "bench" / "gpu_guard.py"
    spec = importlib.util.spec_from_file_location("gpu_guard", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the GPU guard from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("gpu_guard", module)
    spec.loader.exec_module(module)
    return module


class Pacer:
    """Guard and lock handling shared by every GPU phase (a cool-down releases the lock and takes it again)."""

    def __init__(self, guard: Any, lock: Any, log: Any = print) -> None:
        self.guard, self.lock, self.log = guard, lock, log
        self.pauses_cool = 0
        self.cool_s = 0.0
        self.max_temp = -1

    @property
    def idle_s(self) -> float:
        """Seconds the GPU was deliberately idle (thermal pauses and cool-downs): not GPU time."""
        return self.guard.paused_s + self.cool_s

    def check(self) -> None:
        if self.guard.check() == "cooldown":
            self.pauses_cool += 1
            self.lock.release()
            c0 = time.perf_counter()
            self.guard.cool_down()
            self.cool_s += time.perf_counter() - c0
            acquire(self.lock)
        self.max_temp = max(self.max_temp, self.guard.max_temp)


def acquire(lock: Any, tries: int = LOCK_TRIES) -> None:
    """Take the machine lock, waiting at most `tries` x 10 min."""
    for _ in range(tries):
        try:
            lock.acquire(timeout=600)
            return
        except Exception:
            continue
    raise SystemExit("GPU lock not obtained within the bounded wait")


def lock_path() -> Path:
    path = os.environ.get(LOCK_ENV)
    if not path:
        raise RuntimeError(f"{LOCK_ENV} is not set: the job script names the machine lock file")
    return Path(path)


def start_session() -> tuple[Any, Any, Pacer]:
    """Wait for <= 80 C, take the machine lock, start a fresh guard: (guard, lock, pacer). The caller releases the
    lock."""
    gg = load_guard_module()
    guard = gg.Guard()
    for _ in range(START_WAIT_TRIES):
        if guard.read_temp() <= gg.START_MAX_C:
            break
        print(f"GPU at {guard.read_temp()} C, waiting to start <= {gg.START_MAX_C}", flush=True)
        time.sleep(30)
    else:
        raise SystemExit(3)
    lock = filelock.FileLock(str(lock_path()))
    print("waiting for the GPU lock ...", flush=True)
    acquire(lock)
    print("lock acquired", flush=True)
    guard = gg.Guard()  # the block starts now that the GPU is ours
    return guard, lock, Pacer(guard, lock, print)

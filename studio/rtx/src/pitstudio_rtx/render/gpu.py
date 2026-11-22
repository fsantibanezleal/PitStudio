# SPDX-License-Identifier: Apache-2.0
"""GPU frame of the render job: CUDA visibility, start temperature, the machine lock and the in-run guard.

Same rules as every GPU job of this machine (spec 002): refuse to start above 80 C, hold the machine lock
`gpu0.compute` (a `filelock` file, the one the queue runner waits on) for the whole session, and call the shared guard
`studio/bench/gpu_guard.py` `Guard.check()` between renderer steps (the caller ticks before every step, far below the
30 s bound). When the guard asks for a cool-down the lock is released while the GPU idles and taken again after.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from filelock import FileLock, Timeout

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class GpuError(RuntimeError):
    """The GPU is not usable: no CUDA device, too hot to start, or the machine lock is held elsewhere."""


@dataclass(frozen=True)
class CudaDevice:
    index: int
    name: str
    driver: str
    temperature_c: int


def cuda_devices(run: Runner = subprocess.run, env: Mapping[str, str] | None = None) -> list[CudaDevice]:
    """The NVIDIA devices `nvidia-smi` lists, none when `CUDA_VISIBLE_DEVICES` hides them all."""
    env = os.environ if env is None else env
    if env.get("CUDA_VISIBLE_DEVICES", "x").strip() in {"", "-1"}:
        return []
    query = "--query-gpu=index,name,driver_version,temperature.gpu"
    done = run(
        ["nvidia-smi", query, "--format=csv,noheader,nounits"], capture_output=True, text=True, check=False, timeout=30
    )
    if done.returncode != 0:
        raise GpuError(f"nvidia-smi failed with exit code {done.returncode}: no usable NVIDIA driver")
    devices = []
    for line in done.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 4 and parts[0].isdigit():
            devices.append(
                CudaDevice(
                    int(parts[0]),
                    parts[1],
                    parts[2],
                    int(float(parts[3])) if parts[3].replace(".", "").isdigit() else -1,
                )
            )
    return devices


def assert_cuda_visible(run: Runner = subprocess.run, env: Mapping[str, str] | None = None) -> CudaDevice:
    """The first CUDA device; a machine without one is a broken environment, never a reason to run elsewhere."""
    devices = cuda_devices(run, env)
    if not devices:
        raise GpuError("no CUDA device is visible (nvidia-smi lists none, or CUDA_VISIBLE_DEVICES hides it)")
    return devices[0]


def load_guard_module() -> ModuleType:
    """The shared `studio/bench/gpu_guard.py` (standard library only), imported from its folder."""
    bench = str(Path(__file__).resolve().parents[5] / "studio" / "bench")
    if bench not in sys.path:
        sys.path.insert(0, bench)
    import gpu_guard

    return gpu_guard


class GpuSession:
    """What a render run holds while it has the GPU: the device, the guard tick and the GPU time spent."""

    def __init__(
        self, device: CudaDevice, guard: Any, lock: FileLock, lock_timeout_s: float, clock: Callable[[], float]
    ) -> None:
        self.device, self.guard, self._lock, self._timeout, self._clock = device, guard, lock, lock_timeout_s, clock
        self._held_s = 0.0
        self._mark = clock()

    def _take(self) -> None:
        try:
            self._lock.acquire(timeout=self._timeout)
        except Timeout as error:
            raise GpuError("the machine lock gpu0.compute is held by another GPU job") from error
        self._mark = self._clock()

    def _drop(self) -> None:
        self._held_s += self._clock() - self._mark
        self._lock.release()

    def tick(self) -> None:
        """Run the guard (pauses when hot, raises GuardStop on overheating or a hardware error)."""
        if self.guard.check() == "cooldown":
            self._drop()
            self.guard.cool_down()
            self._take()

    def close(self) -> None:
        if self._lock.is_locked:
            self._drop()

    @property
    def gpu_seconds(self) -> float:
        """Seconds the session held the lock, without the time the guard paused the job."""
        held = self._held_s + (self._clock() - self._mark if self._lock.is_locked else 0.0)
        return max(0.0, held - float(getattr(self.guard, "paused_s", 0.0)))


@contextlib.contextmanager
def gpu_session(
    lock_path: str | Path,
    *,
    run: Runner = subprocess.run,
    guard: Any = None,
    lock_timeout_s: float = 3600.0,
    clock: Callable[[], float] = time.monotonic,
) -> Iterator[GpuSession]:
    """Assert CUDA, refuse above the start temperature, take `gpu0.compute`, yield the session, release on exit."""
    device = assert_cuda_visible(run)
    module = load_guard_module()
    guard = guard if guard is not None else module.Guard()
    temp = guard.read_temp()
    if temp > module.START_MAX_C:
        raise GpuError(f"GPU at {temp} C, above the start limit {module.START_MAX_C} C")
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(lock_path))
    try:
        lock.acquire(timeout=lock_timeout_s)
    except Timeout as error:
        raise GpuError("the machine lock gpu0.compute is held by another GPU job") from error
    session = GpuSession(device, guard, lock, lock_timeout_s, clock)
    try:
        yield session
    finally:
        session.close()

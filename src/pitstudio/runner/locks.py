"""Machine-wide GPU locks and the GPU hold (FR-002-15..18, 23). `filelock` is imported only when a lock is taken."""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from pathlib import Path

from pitstudio.runner.recipe import Usage


class LockTimeout(Exception):
    """The lock stayed taken for the whole wait."""


class GpuHold(Exception):
    """`gpu0.hold` exists: no GPU work may start; `reason` is its first line."""

    @property
    def reason(self) -> str:
        return self.args[0]


def lock_dir(*, strict: bool = False) -> Path:
    raw = os.environ.get("GPU_LOCK_DIR")
    d = Path(raw) if raw else Path(tempfile.gettempdir()) / "gpu-locks"
    if strict and raw and (not d.is_absolute() or (d.exists() and not d.is_dir())):
        raise Usage("GPU_LOCK_DIR must be an absolute path to a directory")
    return d


_default_dir = lock_dir


def hold_reason(directory: Path | None = None) -> str | None:
    p = (directory or lock_dir()) / "gpu0.hold"
    if not os.path.lexists(p):
        return None
    with contextlib.suppress(OSError), open(p, "rb") as fh:
        return fh.read(4096).decode("utf-8", "replace").strip()[:300] or "no reason given"
    return "no reason given"


@contextlib.contextmanager
def acquire(name: str, *, wait_s: float, lock_dir: Path | None = None, clock=time, on_wait=None):
    """Hold `<lock_dir>/<name>` for the block; poll every <= 5 s, re-checking the hold at every poll."""
    from filelock import FileLock, Timeout

    d = lock_dir or _default_dir()
    d.mkdir(parents=True, exist_ok=True)
    lock, deadline, waited = FileLock(d / name), clock.monotonic() + wait_s, False
    while True:
        if (reason := hold_reason(d)) is not None:
            raise GpuHold(reason)
        try:
            lock.acquire(timeout=0)
            break
        except Timeout:
            pass
        if (left := deadline - clock.monotonic()) <= 0:
            raise LockTimeout(f"{name} is held by another process")
        if on_wait and not waited:
            waited = True
            on_wait()
        clock.sleep(min(5, left))
    try:
        yield
    finally:
        lock.release()

"""Runner behaviour of surrogate training and calibration stages on a GPU (FR-011-44).

A CUDA stage must hold the `gpu<N>.compute` lock (the environment variable `PITSTUDIO_HELD_LOCKS` of FR-002-62: a
sorted,
comma-separated list of distinct lock names set by the runner), must not run while the `gpu0.hold` file exists, and on a
CUDA out-of-memory error applies the declared fallback: GNS and FNO training halve the batch at most twice, a
calibration
halves the particle count once; every halving is recorded in the manifest. Standard library only.

Spec 002's runner owns the stage kit; this module is the seam the surrogate stages call, kept small so it can be
replaced by
the runner's own when that lands.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

HELD_LOCKS_ENV = "PITSTUDIO_HELD_LOCKS"
_LOCK = re.compile(r"^gpu[0-9]{1,2}\.(compute|nvenc)$")
_DEVICE = re.compile(r"^cuda(?::([0-9]{1,2}))?$")
_MAX_LOCKS = 4
_MAX_VALUE = 64
# kind -> (halved parameter, allowed halvings)
FALLBACKS = {"gns": ("batch_size", 2), "fno": ("batch_size", 2), "calibration": ("particle_count", 1)}


class LockNotHeldError(Exception):
    error_class = "lock-not-held"


class GpuHoldError(Exception):
    error_class = "hold"


class OomExhaustedError(Exception):
    error_class = "oom"

    def __init__(self, message: str, *, attempts: int, params: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.params = dict(params)


def _device_index(device: str) -> int | None:
    """None for the CPU, the CUDA index otherwise; ValueError for anything else."""
    if device == "cpu":
        return None
    match = _DEVICE.fullmatch(device) if isinstance(device, str) else None
    if not match:
        raise ValueError(f"device must be 'cpu', 'cuda' or 'cuda:<N>', got {device!r}")
    return int(match.group(1) or 0)


def _held_locks(env: Mapping[str, str]) -> list[str]:
    raw = env.get(HELD_LOCKS_ENV, "")
    if not raw:
        return []
    if len(raw) > _MAX_VALUE:
        raise LockNotHeldError(f"{HELD_LOCKS_ENV} is longer than {_MAX_VALUE} characters")
    names = raw.split(",")
    if len(names) > _MAX_LOCKS or names != sorted(set(names)) or not all(_LOCK.fullmatch(n) for n in names):
        raise LockNotHeldError(f"{HELD_LOCKS_ENV} is malformed (sorted distinct names like gpu0.compute): {raw!r}")
    return names


def require_gpu_lock(device: str, *, env: Mapping[str, str]) -> None:
    """A CUDA device needs its `gpu<N>.compute` lock among the held locks; the CPU needs none."""
    index = _device_index(device)
    if index is None:
        return
    needed = f"gpu{index}.compute"
    if needed not in _held_locks(env):
        raise LockNotHeldError(f"the stage needs the {needed} lock; {HELD_LOCKS_ENV} does not hold it")


def check_hold(device: str, *, lock_dir: str | Path) -> None:
    """A CUDA stage is refused while `<lock_dir>/gpu0.hold` exists (thermal or crash hold); the CPU is unaffected."""
    if _device_index(device) is None:
        return
    hold = Path(lock_dir) / "gpu0.hold"
    if hold.exists():
        raise GpuHoldError(f"gpu0.hold exists in {lock_dir}: the GPU is on hold")


def is_cuda_oom(exc: BaseException) -> bool:
    """True for torch.cuda.OutOfMemoryError (by class name) and for RuntimeError or MemoryError saying "out of
    memory"."""
    if any(cls.__name__ == "OutOfMemoryError" for cls in type(exc).__mro__):
        return True
    return isinstance(exc, RuntimeError | MemoryError) and "out of memory" in str(exc).lower()


def run_with_oom_fallback(
    kind: str, params: Mapping[str, Any], attempt: Callable[[dict[str, Any]], Any], *, manifest: dict[str, Any]
) -> Any:
    """Call `attempt(params_copy)`, halving the declared parameter after each CUDA out-of-memory error (see module
    doc)."""
    if kind not in FALLBACKS:
        raise ValueError(f"kind must be one of {list(FALLBACKS)}, got {kind!r}")
    name, allowed = FALLBACKS[kind]
    value = params.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be an integer >= 1 for a {kind} stage, got {value!r}")
    current = dict(params)
    attempts = 0
    halvings = 0
    while True:
        attempts += 1
        try:
            result = attempt(dict(current))
        except BaseException as exc:
            if not is_cuda_oom(exc):
                raise
            if halvings >= allowed or current[name] // 2 < 1:
                raise OomExhaustedError(
                    f"{kind}: out of memory after {attempts} attempt(s) with {name} = {current[name]}",
                    attempts=attempts,
                    params=current,
                ) from exc
            halved = current[name] // 2
            manifest.setdefault("fallbacks", []).append(
                {"param": name, "from": current[name], "to": halved, "reason": "oom"}
            )
            manifest["oom_fallback"] = True
            current[name] = halved
            halvings += 1
            continue
        manifest.setdefault("oom_fallback", False)
        return result

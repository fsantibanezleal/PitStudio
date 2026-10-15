"""Stage-side helper (standard library only, Python 3.12+): job spec, NVTX range, VRAM cap, result.json, lock check."""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from pathlib import Path

_CTRL, _LOCK = re.compile(r"[\x00-\x1f\x7f]"), re.compile(r"gpu[0-9]{1,2}\.(compute|nvenc)")


class NotRun(Exception):
    """Raise when the stage cannot run for a reason outside its control (a missing tool, a driver below a floor)."""

    def __init__(self, reason: str) -> None:
        if not 1 <= len(reason) <= 300 or not reason.strip() or _CTRL.search(reason):
            raise ValueError("reason must be one line of 1..300 characters and not blank")
        super().__init__(reason)


class LockNotHeldError(Exception):
    """GPU work was about to start without the machine-wide lock it needs (FR-002-63)."""


def held_locks() -> frozenset[str]:
    return frozenset(x for x in os.environ.get("PITSTUDIO_HELD_LOCKS", "").split(",") if x)


def require_lock(kind: str, device: int) -> None:
    if (
        kind not in ("compute", "nvenc")
        or not isinstance(device, int)
        or isinstance(device, bool)
        or not 0 <= device <= 99
    ):
        raise ValueError(f"kind must be compute or nvenc and device an int in 0..99, got {kind!r}, {device!r}")
    need, raw = f"gpu{device}.{kind}", os.environ.get("PITSTUDIO_HELD_LOCKS") or ""
    names = raw.split(",")
    if not (
        raw
        and len(raw) <= 64
        and len(set(names)) == len(names) <= 4
        and all(map(_LOCK.fullmatch, names))
        and need in names
    ):
        raise LockNotHeldError(f"lock {need} is not held (PITSTUDIO_HELD_LOCKS={raw!r})")


def main(stage_fn, argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] != "--job":
        print("usage: --job <job.json>", file=sys.stderr)
        return 2
    job = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    doc: dict = {
        "schema_version": "1.0",
        "status": "succeeded",
        "error_class": None,
        "outputs": [],
        "checkpoint": False,
    }
    rng = None
    with contextlib.suppress(Exception):
        import nvtx

        rng = nvtx, nvtx.start_range(os.environ.get("PITSTUDIO_NVTX_RANGE", "pitstudio"))
    try:
        with contextlib.suppress(Exception):
            import torch

            if os.environ.get("PITSTUDIO_VRAM_FRACTION") and torch.cuda.is_available():
                torch.cuda.set_per_process_memory_fraction(float(os.environ["PITSTUDIO_VRAM_FRACTION"]))
        ret = stage_fn(job) or {}
        doc.update({k: ret[k] for k in ("outputs", "observables", "throughput", "checkpoint", "message") if k in ret})
    except NotRun as e:
        doc.update(status="not_run", reason=str(e))
    except Exception as e:
        oom = type(e).__name__ == "OutOfMemoryError" or "CUDA out of memory" in str(e)
        text = _CTRL.sub(" ", f"{type(e).__name__}: {e}").strip()[:300] or type(e).__name__
        error_class = "lock-not-held" if isinstance(e, LockNotHeldError) else "oom" if oom else "unknown"
        doc.update(status="failed", error_class=error_class, message=text, outputs=[])
    finally:
        if rng:
            with contextlib.suppress(Exception):
                rng[0].end_range(rng[1])
    (Path(job["output_dir"]) / "result.json").write_text(json.dumps(doc), encoding="utf-8")
    return 1 if doc["status"] == "failed" else 0

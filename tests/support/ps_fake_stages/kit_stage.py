"""A fake stage written against the real stage helper `pitstudio_stagekit` (standard library only).

Params: kind (compute | nvenc, default compute), device (default 0), files (list, default ["out.bin"]).
It calls `pitstudio_stagekit.require_lock(kind, device)` BEFORE the "GPU work" (a ledger line `gpu-work`), as a real GPU
stage must (FR-002-63), then writes its outputs.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pitstudio_stagekit as kit


def _ledger(event: str, **extra: object) -> None:
    path = os.environ.get("PS_FAKE_LEDGER")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {"event": event, "t_ns": time.time_ns(), "held": os.environ.get("PITSTUDIO_HELD_LOCKS"), **extra}
                )
                + "\n"
            )


def stage(job: dict) -> dict:
    p = job["params"]
    _ledger(
        "start",
        stage=job["stage"],
        shard=(job.get("shard") or {"index": 0})["index"],
        pid=os.getpid(),
        held_api=sorted(kit.held_locks()),
    )
    kit.require_lock(p.get("kind", "compute"), int(p.get("device", 0)))
    _ledger("gpu-work", kind=p.get("kind", "compute"))
    files = list(p.get("files", ["out.bin"]))
    for f in files:
        target = Path(job["output_dir"]) / f
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"{job['stage']['id']}|{job['seed']}|{f}\n".encode())
    return {"outputs": [{"path": f} for f in files]}


if __name__ == "__main__":
    sys.exit(kit.main(stage))

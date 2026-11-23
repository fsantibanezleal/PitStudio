"""Python min-cut wall time recorded per baked instance (NFR-017-06)."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

MINCUT_BUDGET_S = 60.0
BUDGET_BLOCKS = 100_000


def record_mincut_time(instance_id: str, n_blocks: int, solve: Callable[[], Any], *, clock: Any, cpu: str) -> dict:
    """Call `solve()` once and return its timing record; the solve result is under `result`."""
    if not isinstance(instance_id, str) or not instance_id:
        raise ValueError("instance id must be a non-empty string")
    if isinstance(n_blocks, bool) or not isinstance(n_blocks, int) or n_blocks <= 0:
        raise ValueError(f"n_blocks must be a positive integer, got {n_blocks!r}")
    t0 = clock.monotonic()
    result = solve()
    wall = clock.monotonic() - t0
    if not math.isfinite(wall) or wall < 0:
        raise ValueError(f"elapsed time is not a finite non-negative number: {wall!r}")
    over = n_blocks <= BUDGET_BLOCKS and wall > MINCUT_BUDGET_S
    return {
        "instance": instance_id,
        "n_blocks": n_blocks,
        "wall_s": wall,
        "cpu": cpu,
        "budget_s": MINCUT_BUDGET_S,
        "over_budget": over,
        "note": f"overrun of the {MINCUT_BUDGET_S:g} s budget" if over else None,
        "result": result,
    }


def timing_manifest_entries(records: Sequence[dict]) -> dict:
    """Manifest entry: wall time per instance and the sorted overruns; a duplicate instance id is refused."""
    seen: dict[str, float] = {}
    for r in records:
        if r["instance"] in seen:
            raise ValueError(f"duplicate instance id {r['instance']!r}")
        seen[r["instance"]] = r["wall_s"]
    return {"mincut_wall_s": seen, "overruns": sorted(r["instance"] for r in records if r["over_budget"])}

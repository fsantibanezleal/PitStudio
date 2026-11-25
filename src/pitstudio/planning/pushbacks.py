"""The pushback rule over distinct nested shells (FR-017-17, P-017-09)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np


def _ratio(waste: float, ore: float) -> float | None:
    return waste / ore if ore > 0 else None


def build_pushbacks(shells: Sequence[Mapping], *, t_min_t: float) -> list[dict]:
    """Close a pushback when its incremental ore reaches T_min; a final remainder below T_min / 2 merges back."""
    if isinstance(t_min_t, bool) or not isinstance(t_min_t, (int, float)) or not math.isfinite(t_min_t) or t_min_t <= 0:
        raise ValueError(f"t_min_t must be a finite number > 0, got {t_min_t!r}")
    distinct: list[tuple[int, Mapping]] = []
    prev: np.ndarray | None = None
    for idx, s in enumerate(shells):
        m = np.asarray(s["mask"], dtype=bool)
        if not m.any() or (prev is not None and np.array_equal(m, prev)):
            continue
        if prev is not None and (prev & ~m).any():
            raise ValueError("shells are not nested")
        distinct.append((idx, s))
        prev = m
    if not distinct:
        return []
    closed: list[tuple[int, Mapping]] = []  # (index, shell) at which each pushback closes
    base_ore = 0.0
    for idx, s in distinct:
        if s["ore_t"] - base_ore >= t_min_t:
            closed.append((idx, s))
            base_ore = s["ore_t"]
    last_idx, last = distinct[-1]
    if not closed:
        closed.append((last_idx, last))
    elif closed[-1][0] != last_idx:
        if last["ore_t"] - base_ore < t_min_t / 2:
            closed[-1] = (last_idx, last)  # merge the small remainder into the previous pushback
        else:
            closed.append((last_idx, last))
    out: list[dict] = []
    prev_mask = np.zeros_like(np.asarray(distinct[0][1]["mask"], dtype=bool))
    prev_ore = prev_waste = 0.0
    for idx, s in closed:
        mask = np.asarray(s["mask"], dtype=bool)
        ore, waste = float(s["ore_t"]) - prev_ore, float(s["waste_t"]) - prev_waste
        out.append(
            {
                "shell": idx,
                "mask": mask & ~prev_mask,
                "ore_t": ore,
                "waste_t": waste,
                "strip_ratio_incremental": _ratio(waste, ore),
                "strip_ratio_cumulative": _ratio(float(s["waste_t"]), float(s["ore_t"])),
            }
        )
        prev_mask, prev_ore, prev_waste = mask, float(s["ore_t"]), float(s["waste_t"])
    return out

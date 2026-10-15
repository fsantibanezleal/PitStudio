# SPDX-License-Identifier: Apache-2.0
"""Bucket fill model (FR-014-18, FR-014-47).

While cutting, each step adds ``width * depth * ds`` to the fill, capped at ``FILL_CAP * v_heaped``, and lowers the
terrain profile by the removed cross-section ``depth * ds`` (m2) over the strip the tip swept, ``[tip_x - ds, tip_x]``.
The strip is shifted inside the grid when it would leave it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pitstudio.robots._check import finite, non_negative, positive, vector

FILL_CAP = 1.15  # multiple of the rated heaped volume V_h

__all__ = ["FILL_CAP", "CutStep", "cut_step", "fill_factor"]


@dataclass(frozen=True)
class CutStep:
    v_fill: float
    heights: np.ndarray


def fill_factor(v_fill: float, v_heaped: float) -> float:
    """k_f = V_fill / V_h."""
    return v_fill / v_heaped


def _lower(heights: np.ndarray, dx: float, tip_x: float, ds: float, removed_area: float) -> np.ndarray:
    """Lower the cells under the strip swept by the tip so that sum(dh) * dx == removed_area."""
    out = heights.copy()
    if removed_area <= 0.0 or ds <= 0.0:
        return out
    length = out.shape[0] * dx
    lo = max(tip_x - ds, 0.0)
    hi = lo + ds
    if hi > length:
        hi = length
        lo = max(hi - ds, 0.0)
    span = hi - lo
    if span <= 0.0:
        return out
    first = int(np.floor(lo / dx))
    last = min(int(np.ceil(hi / dx)), out.shape[0])
    edges = np.arange(first, last + 1, dtype=np.float64) * dx
    overlap = np.minimum(edges[1:], hi) - np.maximum(edges[:-1], lo)
    overlap = np.clip(overlap, 0.0, None)
    total = float(overlap.sum())
    if total <= 0.0:
        return out
    # each cell loses removed_area * overlap / (total * dx): the sum times dx is exactly the removed area
    out[first:last] -= removed_area * overlap / (total * dx)
    return out


def cut_step(
    v_fill: float,
    heights: np.ndarray,
    *,
    dx: float,
    tip_x: float,
    depth: float,
    ds: float,
    width: float,
    v_heaped: float,
    cutting: bool = True,
) -> CutStep:
    """One fill step; returns the new volume and a new height profile (the input is not modified)."""
    v0 = non_negative("v_fill", v_fill)
    h = vector("heights", heights)
    dx_ = positive("dx", dx)
    x = finite("tip_x", tip_x)
    d = non_negative("depth", depth)
    s = non_negative("ds", ds)
    w = positive("width", width)
    vh = positive("v_heaped", v_heaped)
    if not cutting:
        return CutStep(v0, h)
    cap = FILL_CAP * vh
    gain = w * d * s
    v_new = min(v0 + gain, cap)
    applied = max(v_new - v0, 0.0)
    if gain > 0.0 and applied < gain:
        # the step crosses the cap: only the volume that fits leaves the terrain
        area = applied / w
    else:
        area = d * s
    return CutStep(v_new, _lower(h, dx_, x, s, area))

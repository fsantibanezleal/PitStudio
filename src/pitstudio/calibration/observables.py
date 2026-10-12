"""Smooth and hard repose observables of a poured heap (FR-011-18, P-011-08).

Radial bins of width 2 d are counted from the heap axis (index b: r in [2 d b, 2 d (b + 1)), centre r_b = 2 d (b + 1/2)).
The hard envelope is the maximum particle top height z + d / 2 per bin. The smooth envelope is the soft maximum

    h_b = (1 / beta) ln sum_i w_ib exp(beta z_i^top),   beta = 10 / d,   w_ib = exp(-(r_i - r_b)^2 / (2 (dr / 2)^2)),  dr = 2 d,

evaluated with the maximum subtracted so that nothing overflows. The repose angle is the arctan of minus the least-squares
slope of the envelope against r_b over the bins between 20 % and 80 % of the heap height; the bin range is frozen once, at the
start of the recorded window (`freeze_bin_range`), so that the smooth observable is a smooth function of the positions inside
the window.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

BETA_OVER_D = 10.0  # beta = 10 / d
LOW, HIGH = 0.2, 0.8  # fraction of the heap height bounding the fitted bins


def _check(positions: np.ndarray, d: float, axis_xy: Sequence[float]) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    pos = np.asarray(positions, dtype=np.float64)
    if pos.ndim != 2 or pos.shape[1] != 3 or pos.shape[0] == 0:
        raise ValueError(f"positions must have shape [N, 3] with N >= 1, got {list(pos.shape)}")
    if not np.isfinite(pos).all():
        raise ValueError("positions contain a non-finite value")
    if not isinstance(d, int | float | np.floating) or not math.isfinite(d) or d <= 0:
        raise ValueError(f"the particle diameter d must be a positive finite number, got {d!r}")
    axis = np.asarray(axis_xy, dtype=np.float64)
    if axis.shape != (2,) or not np.isfinite(axis).all():
        raise ValueError("axis_xy must be two finite numbers")
    r = np.hypot(pos[:, 0] - axis[0], pos[:, 1] - axis[1])
    return pos, r, pos[:, 2] + d / 2.0, float(d)


def smooth_envelope(positions: np.ndarray, *, d: float, axis_xy: Sequence[float], bin_centres: np.ndarray) -> np.ndarray:
    """Soft-max envelope height at each bin centre (nan where no particle has any weight)."""
    _, r, ztop, d = _check(positions, d, axis_xy)
    centres = np.asarray(bin_centres, dtype=np.float64)
    beta = BETA_OVER_D / d
    sigma = d  # dr / 2 with dr = 2 d
    top = ztop.max()
    weights = np.exp(-((r[None, :] - centres[:, None]) ** 2) / (2.0 * sigma**2))  # [bins, N]
    total = (weights * np.exp(beta * (ztop - top))[None, :]).sum(axis=1)
    with np.errstate(divide="ignore"):
        out = np.where(total > 0, np.log(np.where(total > 0, total, 1.0)) / beta + top, np.nan)
    return out


def hard_envelope(positions: np.ndarray, *, d: float, axis_xy: Sequence[float], bin_centres: np.ndarray) -> np.ndarray:
    """Maximum top height in each bin [r_b - d, r_b + d); nan for an empty bin."""
    _, r, ztop, d = _check(positions, d, axis_xy)
    centres = np.asarray(bin_centres, dtype=np.float64)
    out = np.full(centres.shape, np.nan)
    for k, rb in enumerate(centres):
        inside = (r >= rb - d) & (r < rb + d)
        if inside.any():
            out[k] = ztop[inside].max()
    return out


def _hard_per_index(r: np.ndarray, ztop: np.ndarray, d: float) -> np.ndarray:
    idx = np.floor(r / (2.0 * d)).astype(np.int64)
    out = np.full(int(idx.max()) + 1, np.nan)
    for b in np.unique(idx):
        out[b] = ztop[idx == b].max()
    return out


def freeze_bin_range(positions: np.ndarray, *, d: float, axis_xy: Sequence[float]) -> tuple[int, int]:
    """(first, last) bin indices, inclusive, whose hard envelope lies between 20 % and 80 % of the heap height."""
    _, r, ztop, d = _check(positions, d, axis_xy)
    env = _hard_per_index(r, ztop, d)
    height = float(ztop.max())
    chosen = np.flatnonzero(np.isfinite(env) & (env >= LOW * height) & (env <= HIGH * height))
    if chosen.size < 2:
        raise ValueError("fewer than two radial bins between 20 % and 80 % of the heap height: no repose angle")
    return int(chosen[0]), int(chosen[-1])


def _bins(bin_range: tuple[int, int]) -> np.ndarray:
    first, last = bin_range
    if first < 0 or last <= first:
        raise ValueError(f"bin_range must be (first, last) with 0 <= first < last, got {bin_range}")
    return np.arange(first, last + 1)


def _angle(centres: np.ndarray, heights: np.ndarray) -> float:
    ok = np.isfinite(heights)
    if int(ok.sum()) < 2:
        raise ValueError("fewer than two bins hold particles: no repose angle")
    slope = np.polyfit(centres[ok], heights[ok], 1)[0]
    return float(math.degrees(math.atan(-slope)))


def smooth_repose_deg(positions: np.ndarray, *, d: float, axis_xy: Sequence[float], bin_range: tuple[int, int]) -> float:
    """Repose angle (degrees) from the smooth envelope over the frozen bins."""
    _check(positions, d, axis_xy)
    indices = _bins(bin_range)
    centres = 2.0 * d * (indices + 0.5)
    return _angle(centres, smooth_envelope(positions, d=d, axis_xy=axis_xy, bin_centres=centres))


def hard_repose_deg(
    positions: np.ndarray, *, d: float, axis_xy: Sequence[float], bin_range: tuple[int, int] | None = None
) -> float:
    """The same angle from the hard envelope; with no `bin_range` the range is frozen from the positions themselves."""
    _check(positions, d, axis_xy)
    if bin_range is None:
        bin_range = freeze_bin_range(positions, d=d, axis_xy=axis_xy)
    indices = _bins(bin_range)
    centres = 2.0 * d * (indices + 0.5)
    return _angle(centres, hard_envelope(positions, d=d, axis_xy=axis_xy, bin_centres=centres))

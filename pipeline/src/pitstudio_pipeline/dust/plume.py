"""Gaussian plume of a road network: the sum of the ground-reflected point-source plumes of `minephys.environment`
(ISC3 equation 1-1 with the Pasquill-Gifford rural or Briggs urban dispersion coefficients) over the pieces of the road.

Screening model, not AERMOD: steady wind, flat terrain, no plume rise, deposition, building wake or chemistry. A source piece
contributes only to receptors downwind of it; the dispersion coefficients are evaluated at no less than `min_downwind_m`
(a receptor closer than that downwind of a piece sees the plume of that distance, finite and not a singularity).
Coordinates are metres east and north of the site origin; `wind_from_deg` is the meteorological direction (the wind blows
from it, 270 = from the west, towards the east).
"""
# ruff: noqa: E501

from __future__ import annotations

import math
import warnings
from collections.abc import Callable, Sequence
from itertools import pairwise
from typing import Any

import numpy as np
from minephys._errors import ValidityWarning
from minephys.environment import gaussian_plume, pasquill_sigmas

CHUNK = 3_000_000  # source-receptor pairs per block
Sigmas = Callable[[Any], tuple[Any, Any]]


def discretise(lines: Sequence[np.ndarray], spacing_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Midpoints and lengths of the pieces (each at most `spacing_m` long) of polylines given as (n, >= 2) arrays."""
    pts: list[np.ndarray] = []
    lens: list[np.ndarray] = []
    for line in lines:
        v = np.asarray(line, dtype=float)[:, :2]
        for a, b in pairwise(v):
            length = float(math.hypot(*(b - a)))
            if length == 0.0:
                continue
            k = max(1, math.ceil(length / spacing_m - 1e-12))
            t = (np.arange(k) + 0.5) / k
            pts.append(a + np.outer(t, b - a))
            lens.append(np.full(k, length / k))
    if not pts:
        return np.zeros((0, 2)), np.zeros(0)
    return np.vstack(pts), np.concatenate(lens)


def _default_sigmas(stability: str, terrain: str) -> Sigmas:
    def sigmas(x: Any) -> tuple[Any, Any]:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ValidityWarning)
            return pasquill_sigmas(x, stability, terrain)

    return sigmas


def concentration(
    sources: np.ndarray,
    q_kg_s: np.ndarray,
    receptors: np.ndarray,
    *,
    wind_speed_m_s: float,
    wind_from_deg: float,
    stability: str,
    release_height_m: float,
    receptor_height_m: float,
    terrain: str = "rural",
    min_downwind_m: float = 10.0,
    sigmas: Sigmas | None = None,
) -> np.ndarray:
    """Concentration in kg/m3 at each receptor: the sum over the source pieces (emission rates q_kg_s, in kg/s)."""
    src = np.asarray(sources, dtype=float).reshape(-1, 2)
    rec = np.asarray(receptors, dtype=float).reshape(-1, 2)
    q = np.asarray(q_kg_s, dtype=float).reshape(-1)
    sig = sigmas or _default_sigmas(stability, terrain)
    theta = math.radians(wind_from_deg)
    dx, dy = -math.sin(theta), -math.cos(theta)  # unit vector of the plume axis (east, north)
    out = np.zeros(len(rec))
    step = max(1, CHUNK // max(1, len(src)))
    for start in range(0, len(rec), step):
        r = rec[start : start + step]
        ex = r[:, None, 0] - src[None, :, 0]
        ey = r[:, None, 1] - src[None, :, 1]
        x = ex * dx + ey * dy
        y = -ex * dy + ey * dx
        ri, si = np.nonzero(x > 0.0)
        if ri.size == 0:
            continue
        xs = np.maximum(x[ri, si], min_downwind_m)
        sy, sz = sig(xs)
        c = gaussian_plume(q[si], wind_speed_m_s, y[ri, si], receptor_height_m, release_height_m, sy, sz)
        out[start : start + len(r)] += np.bincount(ri, weights=np.asarray(c), minlength=len(r))
    return out


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, p: float) -> float:
    order = np.argsort(values, kind="stable")
    cum = np.cumsum(weights[order]) / weights.sum()
    return float(values[order][int(np.searchsorted(cum, p - 1e-12, side="left"))])


def receptor_statistics(
    sources: np.ndarray,
    q_kg_s: np.ndarray,
    receptors: np.ndarray,
    speeds: np.ndarray,
    from_degs: np.ndarray,
    *,
    min_speed_m_s: float = 1.0,
    **plume_args: Any,
) -> dict[str, Any]:
    """Mean and 99th percentile over the modelled hours of the concentration at each receptor (kg/m3).

    An hour is modelled when its speed is at least `min_speed_m_s` and it has a direction; the others are counted and left out.
    Hours that share a speed and a direction share one plume evaluation, so the result is exact, not binned.
    """
    speeds = np.asarray(speeds, dtype=float)
    dirs = np.asarray(from_degs, dtype=float)
    ok = (speeds >= min_speed_m_s) & ~np.isnan(dirs)
    pairs, counts = np.unique(np.column_stack([speeds[ok], dirs[ok]]), axis=0, return_counts=True)
    conc = np.array(
        [
            concentration(sources, q_kg_s, receptors, wind_speed_m_s=float(u), wind_from_deg=float(d), **plume_args)
            for u, d in pairs
        ]
    ).reshape(len(pairs), len(np.asarray(receptors).reshape(-1, 2)))
    w = counts.astype(float)
    return {
        "mean_kg_per_m3": (w[:, None] * conc).sum(axis=0) / w.sum() if len(w) else np.zeros(conc.shape[1]),
        "p99_kg_per_m3": np.array([_weighted_quantile(conc[:, k], w, 0.99) for k in range(conc.shape[1])])
        if len(w)
        else np.zeros(conc.shape[1]),
        "n_modelled": int(ok.sum()),
        "n_not_modelled": int((~ok).sum()),
        "n_unique_winds": len(pairs),
    }

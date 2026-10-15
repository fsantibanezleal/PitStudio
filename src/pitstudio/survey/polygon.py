"""E2 polygon tool: hostile polygons are rejected, volumes come from `difference` and `volume_uncertainty`
(FR-017-46, FR-017-47, NFR-017-04)."""

from __future__ import annotations

from typing import Any

import numpy as np

from pitstudio.survey.difference import Surface, difference
from pitstudio.survey.uncertainty import volume_uncertainty

MAX_VERTICES = 10_000


class PolygonError(ValueError):
    """A polygon that is rejected; `.reason` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _on_segment(ax, ay, bx, by, px, py) -> np.ndarray:
    return (
        (np.minimum(ax, bx) <= px)
        & (px <= np.maximum(ax, bx))
        & (np.minimum(ay, by) <= py)
        & (py <= np.maximum(ay, by))
    )


def _self_intersects(p: np.ndarray) -> bool:
    n = len(p)
    ax, ay = p[:, 0], p[:, 1]
    bx, by = np.roll(ax, -1), np.roll(ay, -1)
    order = np.argsort(np.minimum(ax, bx), kind="stable")
    xmin, xmax = np.minimum(ax, bx)[order], np.maximum(ax, bx)[order]
    for pos in range(n):
        i = order[pos]
        end = np.searchsorted(xmin, xmax[pos], side="right")
        if end <= pos + 1:
            continue
        j = order[pos + 1 : end]
        cx, cy, dx, dy = ax[j], ay[j], bx[j], by[j]
        o = lambda px, py, qx, qy, rx, ry: (qx - px) * (ry - py) - (qy - py) * (rx - px)  # noqa: E731
        d1, d2 = o(cx, cy, dx, dy, ax[i], ay[i]), o(cx, cy, dx, dy, bx[i], by[i])
        d3, d4 = o(ax[i], ay[i], bx[i], by[i], cx, cy), o(ax[i], ay[i], bx[i], by[i], dx, dy)
        hit = (d1 * d2 < 0) & (d3 * d4 < 0)
        hit |= (d1 == 0) & _on_segment(cx, cy, dx, dy, ax[i], ay[i])
        hit |= (d2 == 0) & _on_segment(cx, cy, dx, dy, bx[i], by[i])
        hit |= (d3 == 0) & _on_segment(ax[i], ay[i], bx[i], by[i], cx, cy)
        hit |= (d4 == 0) & _on_segment(ax[i], ay[i], bx[i], by[i], dx, dy)
        adjacent = ((j + 1) % n == i) | ((i + 1) % n == j)
        if (hit & ~adjacent).any():
            return True
        for k in np.flatnonzero(hit & adjacent):
            # consecutive edges may only touch at their shared vertex: a fold-back along the edge is an overlap
            e, f = (i, j[k]) if (i + 1) % n == j[k] else (j[k], i)
            ux, uy = bx[e] - ax[e], by[e] - ay[e]
            vx, vy = bx[f] - ax[f], by[f] - ay[f]
            if ux * vy - uy * vx == 0 and ux * vx + uy * vy < 0:
                return True
    return False


def validate_polygon(vertices: Any, *, extent: tuple[float, float, float, float]) -> np.ndarray:
    """The polygon as an (n, 2) float64 array, or a PolygonError naming the problem."""
    try:
        arr = np.asarray(vertices, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise PolygonError("polygon is not an (n, 2) numeric array") from exc
    if arr.size == 0 and arr.ndim <= 2:
        arr = arr.reshape(0, 2)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise PolygonError("polygon is not an (n, 2) numeric array")
    if len(arr) < 3:
        raise PolygonError(f"polygon needs at least 3 vertices, got {len(arr)}")
    if len(arr) > MAX_VERTICES:
        raise PolygonError(f"polygon has {len(arr)} vertices, the limit is {MAX_VERTICES}")
    if not np.isfinite(arr).all():
        raise PolygonError("polygon has a non-finite coordinate (finite values only)")
    if _self_intersects(arr):
        raise PolygonError("polygon edges self-intersect")
    x_min, y_min, x_max, y_max = extent
    if arr[:, 0].max() < x_min or arr[:, 0].min() > x_max or arr[:, 1].max() < y_min or arr[:, 1].min() > y_max:
        raise PolygonError("polygon lies entirely outside the grid")
    return arr


def polygon_volumes(before: Surface, after: Surface, polygon: Any, *, rmse0_m: float, rmse1_m: float) -> dict[str, Any]:
    """V_cut, V_fill, V_net, no-data fraction and uncertainty bounds over a validated polygon."""
    ny, nx = before.z.shape
    c = before.cell_size_m
    x0, y0 = before.origin_xy
    poly = validate_polygon(polygon, extent=(x0, y0, x0 + nx * c, y0 + ny * c))
    result = difference(before, after, polygon=poly)
    bounds = volume_uncertainty(result.n_valid, c, rmse0_m, rmse1_m)
    return {
        "v_cut_m3": result.v_cut,
        "v_fill_m3": result.v_fill,
        "v_net_m3": result.v_net,
        "nodata_fraction": result.nodata_fraction,
        "n_valid": result.n_valid,
        "uncertainty_m3": {"uncorrelated": bounds.uncorrelated_m3, "correlated": bounds.correlated_m3},
    }

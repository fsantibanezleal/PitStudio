"""DEM differencing with exactly rounded sums and hostile-surface guards (FR-017-30, FR-017-48)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


class InvalidSurfaceError(ValueError):
    """Two surfaces that cannot be differenced; `.reason` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Surface:
    z: np.ndarray
    origin_xy: tuple[float, float]
    cell_size_m: float
    nodata: float | None = None


@dataclass(frozen=True)
class VolumeResult:
    v_fill: float
    v_cut: float
    v_net: float
    n_valid: int
    n_nodata_excluded: int
    nodata_fraction: float


def _valid_mask(surface: Surface) -> np.ndarray:
    ok = np.isfinite(surface.z)
    if surface.nodata is not None:
        ok &= surface.z != surface.nodata
    return ok


def _inside(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    """Strictly inside a simple polygon (even-odd rule; points on the boundary are outside)."""
    x, y = points[:, 0], points[:, 1]
    inside = np.zeros(len(points), dtype=bool)
    on_edge = np.zeros(len(points), dtype=bool)
    n = len(polygon)
    for k in range(n):
        x1, y1 = polygon[k]
        x2, y2 = polygon[(k + 1) % n]
        cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
        within = (np.minimum(x1, x2) <= x) & (x <= np.maximum(x1, x2)) & (np.minimum(y1, y2) <= y) & (y <= np.maximum(y1, y2))
        on_edge |= (cross == 0) & within
        crosses = (y1 > y) != (y2 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            x_at = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        inside ^= crosses & (x < x_at)
    return inside & ~on_edge


def difference(before: Surface, after: Surface, *, polygon: np.ndarray | None = None) -> VolumeResult:
    """V_fill, V_cut and V_net of `after - before` over the valid cells whose centre lies in the polygon."""
    for name, s in (("before", before), ("after", after)):
        c = s.cell_size_m
        if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) or c <= 0:
            raise InvalidSurfaceError(f"cell size of {name} is not a finite number > 0: {c!r}")
        if np.asarray(s.z).ndim != 2:
            raise InvalidSurfaceError(f"{name} surface is not a 2-D grid")
    if before.z.shape != after.z.shape:
        raise InvalidSurfaceError(f"shape differs: {before.z.shape} versus {after.z.shape}, no resampling declared")
    if tuple(before.origin_xy) != tuple(after.origin_xy):
        raise InvalidSurfaceError("origin differs, no resampling declared")
    if before.cell_size_m != after.cell_size_m:
        raise InvalidSurfaceError("cell size differs, no resampling declared")
    ny, nx = before.z.shape
    c = float(before.cell_size_m)
    cols, rows = np.meshgrid(np.arange(nx), np.arange(ny))
    centres = np.stack(
        [before.origin_xy[0] + (cols.ravel() + 0.5) * c, before.origin_xy[1] + (rows.ravel() + 0.5) * c], axis=1
    )
    if polygon is None:
        in_area = np.ones(ny * nx, dtype=bool)
    else:
        poly = np.asarray(polygon, dtype=np.float64)
        if poly.ndim != 2 or poly.shape[1] != 2 or len(poly) < 3 or not np.isfinite(poly).all():
            raise InvalidSurfaceError("polygon must be a (k, 2) array of at least 3 finite vertices")
        in_area = _inside(centres, poly)
    valid = (_valid_mask(before) & _valid_mask(after)).ravel()
    n_in_area = int(in_area.sum())
    n_valid = int((in_area & valid).sum())
    if n_valid == 0:
        raise InvalidSurfaceError("no valid cell inside the polygon")
    d = (after.z.astype(np.float64).ravel() - before.z.astype(np.float64).ravel())[in_area & valid]
    area = c * c
    fill = area * math.fsum(np.maximum(d, 0.0).tolist())
    cut = area * math.fsum(np.maximum(-d, 0.0).tolist())
    excluded = n_in_area - n_valid
    return VolumeResult(fill, cut, fill - cut, n_valid, excluded, excluded / n_in_area)

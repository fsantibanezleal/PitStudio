"""Level-cone precedence generator for regular block grids (FR-017-13)."""

from __future__ import annotations

import math

import numpy as np


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be an integer >= 1, got {value!r}")
    return value


def _positive_float(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite number > 0, got {value!r}")
    return float(value)


def level_cone_precedence(
    nx: int, ny: int, nz: int, *, dx: float, dy: float, dz: float, slope_deg: float, m: int = 1
) -> np.ndarray:
    """Arcs (block, block above): block (i, j, k) requires every block l = 1..m levels up whose horizontal centre
    offset is at most l dz / tan(alpha) (+ 1e-9 m). Block index is (k ny + j) nx + i; levels increase upward."""
    _positive_int(nx, "nx")
    _positive_int(ny, "ny")
    _positive_int(nz, "nz")
    _positive_float(dx, "dx")
    _positive_float(dy, "dy")
    _positive_float(dz, "dz")
    if (
        isinstance(slope_deg, bool)
        or not isinstance(slope_deg, (int, float))
        or not math.isfinite(slope_deg)
        or not 0 < slope_deg < 90
    ):
        raise ValueError(f"slope_deg must lie in (0, 90), got {slope_deg!r}")
    _positive_int(m, "m")
    tan = math.tan(math.radians(slope_deg))
    di, dj = np.meshgrid(np.arange(-(nx - 1), nx), np.arange(-(ny - 1), ny), indexing="xy")
    dist = np.hypot(di * dx, dj * dy)
    ii, jj, kk = np.meshgrid(np.arange(nx), np.arange(ny), np.arange(nz), indexing="ij")
    arcs: list[np.ndarray] = []
    for level in range(1, min(m, nz - 1) + 1):
        reach = level * dz / tan + 1e-9
        offsets = np.argwhere(dist <= reach)  # rows of (jdx, idx) into the offset grid
        for jo, io in offsets:
            ti, tj = ii + (io - (nx - 1)), jj + (jo - (ny - 1))
            ok = (ti >= 0) & (ti < nx) & (tj >= 0) & (tj < ny) & (kk + level < nz)
            src = (kk[ok] * ny + jj[ok]) * nx + ii[ok]
            dst = ((kk[ok] + level) * ny + tj[ok]) * nx + ti[ok]
            arcs.append(np.stack([src, dst], axis=1))
    if not arcs:
        return np.empty((0, 2), dtype=np.int64)
    out = np.concatenate(arcs).astype(np.int64)
    return out[np.lexsort((out[:, 1], out[:, 0]))]

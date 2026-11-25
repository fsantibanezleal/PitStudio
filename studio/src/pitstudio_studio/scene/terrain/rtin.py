"""Right-triangulated irregular networks (RTIN) with a true per-sample error bound (FR-004-06, P-004-01).

The tile is a (2^k + 1)^2 grid of heights; its triangle hierarchy is the one of Evans et al. 1997 (as in MARTINI): two
root triangles share the diagonal, each triangle splits at the midpoint of its hypotenuse into two children whose
hypotenuses are its legs. Every triangle has an *exact* error: the largest |sample - plane of its three vertices|
over all
grid samples inside it (closed), or infinity when one of them is nodata. A vertex error then takes the maximum over the
two triangles that share that hypotenuse and over the errors of the children's hypotenuse midpoints, so that a split is
always accompanied by the split of its partner (no cracks) and of its ancestors. A triangle whose vertex error is at
most
`max_error` is emitted, so every sample lies within `max_error` of the mesh.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

DEFAULT_MAX_ERROR_M = (0.25, 1.0, 4.0)  # LOD 0, 1, 2 (FR-004-06)


@dataclass
class Mesh:
    """A triangle mesh over grid positions: `rc` (row, col) per vertex, float32 heights, counter-clockwise triangles."""

    rc: np.ndarray
    z: np.ndarray
    triangles: np.ndarray


@dataclass
class _Level:
    ax: np.ndarray
    ay: np.ndarray
    bx: np.ndarray
    by: np.ndarray
    cx: np.ndarray
    cy: np.ndarray
    err: np.ndarray = field(default_factory=lambda: np.zeros(0))


def _tile_exponent(heights: np.ndarray) -> int:
    if heights.ndim != 2 or heights.shape[0] != heights.shape[1]:
        raise ValueError(f"RTIN needs a square grid, got shape {heights.shape}")
    n = heights.shape[0] - 1
    if n < 2 or n & (n - 1):
        raise ValueError(f"RTIN needs (2^k + 1)^2 samples with k >= 1, got shape {heights.shape}")
    return n.bit_length() - 1


def _hierarchy(k: int) -> list[_Level]:
    """The triangles of levels 0 .. 2k-1 (those whose hypotenuse midpoint is a grid vertex)."""
    t = 1 << k
    i32 = np.int32
    level = _Level(
        ax=np.array([0, t], i32),
        ay=np.array([0, t], i32),
        bx=np.array([t, 0], i32),
        by=np.array([t, 0], i32),
        cx=np.array([t, 0], i32),
        cy=np.array([0, t], i32),
    )
    levels = [level]
    for _ in range(1, 2 * k):
        mx, my = (level.ax + level.bx) >> 1, (level.ay + level.by) >> 1
        level = _Level(
            ax=np.concatenate([level.cx, level.bx]),
            ay=np.concatenate([level.cy, level.by]),
            bx=np.concatenate([level.ax, level.cx]),
            by=np.concatenate([level.ay, level.cy]),
            cx=np.concatenate([mx, mx]),
            cy=np.concatenate([my, my]),
        )
        levels.append(level)
    return levels


def _triangle_errors(heights: np.ndarray, lv: _Level) -> np.ndarray:
    """Exact error of every triangle of a level: max |h - plane| over its closed sample set, inf if one is nodata."""
    n = len(lv.ax)
    out = np.zeros(n, dtype=np.float64)
    ax, ay = lv.ax.astype(np.int64), lv.ay.astype(np.int64)
    bx, by = lv.bx.astype(np.int64), lv.by.astype(np.int64)
    cx, cy = lv.cx.astype(np.int64), lv.cy.astype(np.int64)
    xmin, xmax = np.minimum(np.minimum(ax, bx), cx), np.maximum(np.maximum(ax, bx), cx)
    ymin, ymax = np.minimum(np.minimum(ay, by), cy), np.maximum(np.maximum(ay, by), cy)
    width, height = xmax - xmin, ymax - ymin
    for w, h in sorted({(int(a), int(b)) for a, b in zip(width, height, strict=True)}):
        sel = np.flatnonzero((width == w) & (height == h))
        ox, oy = np.meshgrid(np.arange(w + 1, dtype=np.int64), np.arange(h + 1, dtype=np.int64))
        ox, oy = ox.ravel()[None, :], oy.ravel()[None, :]
        # chunk the triangles so that the candidate array stays small
        per = max(1, 4_000_000 // ox.size)
        for lo in range(0, len(sel), per):
            idx = sel[lo : lo + per]
            x = xmin[idx, None] + ox
            y = ymin[idx, None] + oy
            pax, pay = ax[idx, None], ay[idx, None]
            det = (bx[idx, None] - pax) * (cy[idx, None] - pay) - (cx[idx, None] - pax) * (by[idx, None] - pay)
            nb = (x - pax) * (cy[idx, None] - pay) - (cx[idx, None] - pax) * (y - pay)
            nc = (bx[idx, None] - pax) * (y - pay) - (x - pax) * (by[idx, None] - pay)
            na = det - nb - nc
            sign = np.where(det > 0, 1, -1)
            inside = (sign * na >= 0) & (sign * nb >= 0) & (sign * nc >= 0)
            sample = heights[y, x]
            ha, hb, hc = (
                heights[ay[idx], ax[idx]][:, None],
                heights[by[idx], bx[idx]][:, None],
                heights[cy[idx], cx[idx]][:, None],
            )
            with np.errstate(invalid="ignore"):
                plane = (na * ha + nb * hb + nc * hc) / det
                err = np.abs(sample - plane)
            bad = inside & np.isnan(sample)
            err = np.where(inside & ~np.isnan(sample), err, 0.0)
            err = np.where(np.isnan(err), 0.0, err)
            result = err.max(axis=1)
            result[bad.any(axis=1)] = np.inf
            out[idx] = result
    return out


@dataclass
class ErrorField:
    """Per-level exact triangle errors of one tile; `fold` turns them into the per-vertex split errors."""

    k: int
    levels: list[_Level]

    def fold(self, floor: np.ndarray | None = None) -> np.ndarray:
        """Vertex errors (shape `(2^k + 1)^2`, flat): max over the sharing pair, the children and the optional
        `floor`."""
        gs = (1 << self.k) + 1
        errors = np.zeros(gs * gs, dtype=np.float64)
        floor_flat = None if floor is None else np.asarray(floor, dtype=np.float64).ravel()
        for j in range(2 * self.k - 1, -1, -1):
            lv = self.levels[j]
            mid = ((lv.ay + lv.by) >> 1).astype(np.int64) * gs + ((lv.ax + lv.bx) >> 1)
            value = lv.err.copy()
            if j < 2 * self.k - 1:
                c1 = ((lv.ay + lv.cy) >> 1).astype(np.int64) * gs + ((lv.ax + lv.cx) >> 1)
                c2 = ((lv.by + lv.cy) >> 1).astype(np.int64) * gs + ((lv.bx + lv.cx) >> 1)
                value = np.maximum(value, np.maximum(errors[c1], errors[c2]))
            if floor_flat is not None:
                value = np.maximum(value, floor_flat[mid])
            np.maximum.at(errors, mid, value)
        return errors


def error_field(heights: np.ndarray) -> ErrorField:
    """The exact triangle errors of a tile of float64 heights (NaN = nodata)."""
    heights = np.asarray(heights, dtype=np.float64)
    k = _tile_exponent(heights)
    levels = _hierarchy(k)
    for lv in levels:
        lv.err = _triangle_errors(heights, lv)
    return ErrorField(k=k, levels=levels)


def mesh_from_errors(heights: np.ndarray, errors: np.ndarray, max_error: float) -> Mesh:
    """Emit the RTIN triangles whose vertex error is at most `max_error`; triangles with a nodata vertex are dropped."""
    heights = np.asarray(heights, dtype=np.float64)
    k = _tile_exponent(heights)
    gs = (1 << k) + 1
    levels = _hierarchy(k)
    active = np.arange(2)
    kept: list[tuple[np.ndarray, ...]] = []
    for j, lv in enumerate(levels):
        ax, ay, bx, by, cx, cy = (getattr(lv, name)[active] for name in ("ax", "ay", "bx", "by", "cx", "cy"))
        mid = ((ay + by) >> 1).astype(np.int64) * gs + ((ax + bx) >> 1)
        split = errors[mid] > max_error
        keep = ~split
        kept.append((ax[keep], ay[keep], bx[keep], by[keep], cx[keep], cy[keep]))
        n_level = len(lv.ax)
        active = np.concatenate([active[split], active[split] + n_level]) if j + 1 < len(levels) else active[split]
        if j + 1 == len(levels):
            # the leaves: children of the splitting triangles of the last level (legs of one grid unit)
            sx, sy = ax[split], ay[split]
            tx, ty = bx[split], by[split]
            ux, uy = cx[split], cy[split]
            mx, my = (sx + tx) >> 1, (sy + ty) >> 1
            leaves = [(ux, uy, sx, sy, mx, my), (tx, ty, ux, uy, mx, my)]
            for lax, lay, lbx, lby, lcx, lcy in leaves:
                ok = ~np.isnan(heights[lay, lax]) & ~np.isnan(heights[lby, lbx]) & ~np.isnan(heights[lcy, lcx])
                kept.append((lax[ok], lay[ok], lbx[ok], lby[ok], lcx[ok], lcy[ok]))
    ax, ay, bx, by, cx, cy = (np.concatenate([part[i] for part in kept]).astype(np.int64) for i in range(6))
    if not len(ax):
        return Mesh(np.zeros((0, 2), np.int32), np.zeros(0, np.float32), np.zeros((0, 3), np.int32))
    det = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)  # > 0 is clockwise in (east, north): swap b and c
    flip = det > 0
    bx2, cx2 = np.where(flip, cx, bx), np.where(flip, bx, cx)
    by2, cy2 = np.where(flip, cy, by), np.where(flip, by, cy)
    lin = np.stack([ay * gs + ax, by2 * gs + bx2, cy2 * gs + cx2], axis=1)
    uniq, inverse = np.unique(lin, return_inverse=True)
    triangles = inverse.reshape(-1, 3).astype(np.int32)
    rc = np.stack([uniq // gs, uniq % gs], axis=1).astype(np.int32)
    z = heights.ravel()[uniq].astype(np.float32)
    return Mesh(rc, z, triangles)


def build_rtin(heights: np.ndarray, max_error: float) -> Mesh:
    """The RTIN mesh of a (2^k + 1)^2 height grid whose vertical distance to every valid sample is at most
    `max_error`."""
    if not (isinstance(max_error, (int, float)) and math.isfinite(max_error) and max_error > 0):
        raise ValueError(f"max_error must be a positive finite number, got {max_error!r}")
    heights = np.asarray(heights, dtype=np.float64)
    field_ = error_field(heights)
    return mesh_from_errors(heights, field_.fold(), float(max_error))


def build_lods(heights: np.ndarray, lods: list[dict]) -> dict[int, Mesh]:
    """One mesh per LOD of the SceneSpec `terrain.lods` list (`lod`, `max_error_m`)."""
    heights = np.asarray(heights, dtype=np.float64)
    field_ = error_field(heights)
    errors = field_.fold()
    return {int(lod["lod"]): mesh_from_errors(heights, errors, float(lod["max_error_m"])) for lod in lods}

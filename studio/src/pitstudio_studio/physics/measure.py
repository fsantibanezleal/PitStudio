"""Measurements on DEM output (spec 005): the repose angle of a pile (FR-005-13).

The procedure of FR-005-13: build the surface height field on a grid of spacing <= d/2 (the top of the highest
particle per cell), average it radially about the pile axis (cone) or along the ridge, fit a line to the flank where
0.1 h_max <= h <= 0.8 h_max, and return atan of the slope magnitude in degrees.

Choices the spec leaves open (spec 005 section 8, ambiguity 6): a sphere contributes the height of its cap at every
cell centre inside its footprint and the full top z + r to the cell that holds its centre; d is the mean particle
diameter; the base level is z = 0 and h_max is the highest radially averaged height.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

FLANK_LOW, FLANK_HIGH = 0.1, 0.8  # flank window as fractions of h_max (FR-005-13)


@dataclass(frozen=True)
class HeightField:
    """Surface height on a regular grid: cell (i, j) covers [x0 + i s, x0 + (i + 1) s) x [y0 + j s, y0 + (j + 1) s)."""

    heights: np.ndarray  # (nx, ny) float64, NaN where no particle reaches the cell
    spacing: float
    origin: tuple[float, float]


def _check_particles(positions, radii) -> tuple[np.ndarray, np.ndarray]:
    pos = np.asarray(positions, dtype=np.float64)
    rad = np.asarray(radii, dtype=np.float64)
    if pos.ndim != 2 or pos.shape[1] != 3 or len(pos) == 0:
        raise ValueError("positions: expected a non-empty (N, 3) array")
    if not np.isfinite(pos).all():
        raise ValueError("positions: every coordinate must be finite")
    if rad.shape != (len(pos),) or not np.isfinite(rad).all() or not (rad > 0.0).all():
        raise ValueError("radii: expected one finite positive radius per particle")
    return pos, rad


def surface_height_field(positions, radii, spacing: float, *, origin=None) -> HeightField:
    """Height field of the top surface of a particle packing (the top z + r of the highest particle per cell)."""
    pos, rad = _check_particles(positions, radii)
    s = float(spacing)
    if not (math.isfinite(s) and s > 0.0):
        raise ValueError("spacing: must be a positive finite number")
    x0, y0 = (float((pos[:, 0] - rad).min()), float((pos[:, 1] - rad).min())) if origin is None else origin
    x0, y0 = float(x0), float(y0)
    nx = math.floor((float((pos[:, 0] + rad).max()) - x0) / s) + 1
    ny = math.floor((float((pos[:, 1] + rad).max()) - y0) / s) + 1
    heights = np.full((nx, ny), -np.inf)
    ci = np.floor((pos[:, 0] - x0) / s).astype(np.int64)
    cj = np.floor((pos[:, 1] - y0) / s).astype(np.int64)
    reach = math.ceil(float(rad.max()) / s) + 1
    for di in range(-reach, reach + 1):
        for dj in range(-reach, reach + 1):
            i, j = ci + di, cj + dj
            dx = x0 + (i + 0.5) * s - pos[:, 0]
            dy = y0 + (j + 0.5) * s - pos[:, 1]
            under = rad**2 - dx**2 - dy**2
            ok = (under > 0.0) & (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
            np.maximum.at(heights, (i[ok], j[ok]), pos[ok, 2] + np.sqrt(under[ok]))
    inside = (ci >= 0) & (ci < nx) & (cj >= 0) & (cj < ny)
    np.maximum.at(heights, (ci[inside], cj[inside]), pos[inside, 2] + rad[inside])  # the full top, in its own cell
    heights[np.isneginf(heights)] = np.nan
    return HeightField(heights=heights, spacing=s, origin=(x0, y0))


def repose_angle_from_heightfield(
    heights,
    spacing: float,
    *,
    origin=(0.0, 0.0),
    geometry: str = "cone",
    axis_xy=None,
    ridge_along: str = "x",
    crest: float = 0.0,
) -> float:
    """Repose angle in degrees of a pile surface given at the cell centres (base level 0, NaN = no data)."""
    h = np.asarray(heights, dtype=np.float64)
    s = float(spacing)
    if h.ndim != 2 or not np.isfinite(h).any():
        raise ValueError("heights: the field holds no finite data")
    if not (math.isfinite(s) and s > 0.0):
        raise ValueError("spacing: must be a positive finite number")
    x = origin[0] + (np.arange(h.shape[0]) + 0.5) * s
    y = origin[1] + (np.arange(h.shape[1]) + 0.5) * s
    if geometry == "cone":
        if axis_xy is None:
            raise ValueError("axis_xy: a cone needs the pile axis")
        rho = np.hypot(x[:, None] - axis_xy[0], y[None, :] - axis_xy[1])
    elif geometry == "ridge":
        if ridge_along not in ("x", "y"):
            raise ValueError("ridge_along: must be 'x' or 'y'")
        rho = (
            np.abs(y[None, :] - crest) * np.ones_like(h)
            if ridge_along == "x"
            else np.abs(x[:, None] - crest) * np.ones_like(h)
        )
    else:
        raise ValueError("geometry: must be 'cone' or 'ridge'")
    ok = np.isfinite(h)
    k = np.floor(rho[ok] / s).astype(np.int64)
    count = np.bincount(k)
    used = count > 0
    mean_h = np.bincount(k, weights=h[ok])[used] / count[used]
    mean_rho = np.bincount(k, weights=rho[ok])[used] / count[used]
    h_max = float(mean_h.max())
    flank = (mean_h >= FLANK_LOW * h_max) & (mean_h <= FLANK_HIGH * h_max)
    if h_max <= 0.0 or flank.sum() < 2:
        raise ValueError("heights: the flank window holds fewer than two radial bins")
    slope = float(np.polyfit(mean_rho[flank], mean_h[flank], 1)[0])
    return math.degrees(math.atan(abs(slope)))


def repose_angle(
    positions,
    radii,
    *,
    geometry: str = "cone",
    axis_xy=None,
    ridge_along: str = "x",
    crest: float = 0.0,
    spacing: float | None = None,
) -> float:
    """Repose angle (degrees) of a particle pile; the height field spacing is at most d/2 (default d/2)."""
    pos, rad = _check_particles(positions, radii)
    half_diameter = float(rad.mean())  # d / 2 with d the mean particle diameter
    if spacing is None:
        spacing = half_diameter
    elif not spacing <= half_diameter * (1.0 + 1e-9):
        raise ValueError(f"spacing: {spacing} is coarser than d/2 = {half_diameter}")
    if geometry == "cone" and axis_xy is None:
        raise ValueError("axis_xy: a cone needs the pile axis")
    field = surface_height_field(pos, rad, spacing)
    return repose_angle_from_heightfield(
        field.heights,
        field.spacing,
        origin=field.origin,
        geometry=geometry,
        axis_xy=axis_xy,
        ridge_along=ridge_along,
        crest=crest,
    )

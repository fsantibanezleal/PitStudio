"""The carved surface of `st20_pit_design` (FR-004-50) as the SDG sampler reads it: heights and lines of sight.

`CarvedSurface` holds the carved elevation grid (the terrain-grid contract: row 0 is the north row, the sample at row r,
column c sits at x = x_min + c * cell and y = y_max - r * cell, the position of the vertex of the carved USD layer that
carries it). `height` is bilinear and clamps at the border; a nodata cell has no height (NaN) and never blocks a ray.
`first_hit` and `segment_clear` march at half the cell size, so a sight line is judged on the surface the
renderer shows.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MARCH_STEP_CELLS = 0.5  # the ray is sampled every half cell


class CarvedSurfaceError(ValueError):
    """The carved grid cannot be used: a file is missing or its elevation digest differs from the recorded one."""


@dataclass(frozen=True)
class CarvedSurface:
    elevation: np.ndarray  # (rows, cols) metres, NaN = nodata
    x_min_m: float
    y_max_m: float
    cell_size_m: float

    def height(self, x: float | np.ndarray, y: float | np.ndarray) -> float | np.ndarray:
        """Bilinear height at x, y (arrays broadcast); queries outside the grid are clamped to its border."""
        rows, cols = self.elevation.shape
        xs, ys = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
        c = np.clip((xs - self.x_min_m) / self.cell_size_m, 0.0, cols - 1.0)
        r = np.clip((self.y_max_m - ys) / self.cell_size_m, 0.0, rows - 1.0)
        c0 = np.minimum(np.floor(c).astype(np.int64), cols - 2)
        r0 = np.minimum(np.floor(r).astype(np.int64), rows - 2)
        fc, fr = c - c0, r - r0
        e = self.elevation
        out = (
            e[r0, c0] * (1 - fr) * (1 - fc)
            + e[r0, c0 + 1] * (1 - fr) * fc
            + e[r0 + 1, c0] * fr * (1 - fc)
            + e[r0 + 1, c0 + 1] * fr * fc
        )
        return float(out) if np.ndim(out) == 0 else out

    def _below(self, origin: np.ndarray, direction: np.ndarray, distances: np.ndarray) -> np.ndarray:
        points = origin[None, :] + distances[:, None] * direction[None, :]
        with np.errstate(invalid="ignore"):
            return points[:, 2] < np.asarray(self.height(points[:, 0], points[:, 1]))

    def first_hit(self, origin: Sequence[float], direction: Sequence[float], max_range_m: float) -> float | None:
        """Distance along the ray to the first sample below the surface, or None when it meets the surface nowhere."""
        o = np.asarray(origin, dtype=np.float64)
        d = np.asarray(direction, dtype=np.float64)
        d = d / np.linalg.norm(d)
        step = MARCH_STEP_CELLS * self.cell_size_m
        distances = np.arange(0.0, float(max_range_m) + step, step)
        below = self._below(o, d, distances)
        if not below.any():
            return None
        return float(distances[int(np.argmax(below))])

    def segment_clear(self, p0: Sequence[float], p1: Sequence[float]) -> bool:
        """True when the segment from p0 to p1 meets the surface nowhere."""
        a = np.asarray(p0, dtype=np.float64)
        b = np.asarray(p1, dtype=np.float64)
        length = float(np.linalg.norm(b - a))
        if length == 0.0:
            return not bool(self._below(a, np.zeros(3), np.zeros(1))[0])
        steps = max(2, math.ceil(length / (MARCH_STEP_CELLS * self.cell_size_m)))
        distances = np.linspace(0.0, length, steps + 1)
        return not bool(self._below(a, (b - a) / length, distances).any())


def load_carved_surface(folder: Path | str) -> CarvedSurface:
    """Read `design/carved-grid.zarr` (the folder of the Zarr group) and check its elevation digest."""
    import zarr

    folder = Path(folder)
    meta = folder / "zarr.json"
    if not meta.is_file():
        raise CarvedSurfaceError(f"carved grid {folder.name}: zarr.json is absent")
    attrs = json.loads(meta.read_text(encoding="utf-8"))["attributes"]
    elevation = np.asarray(zarr.open_group(str(folder), mode="r")["elevation"][:], dtype=np.float32)
    digest = hashlib.sha256(np.ascontiguousarray(elevation, dtype="<f4").tobytes()).hexdigest()
    recorded = attrs["arrays"]["elevation"]["sha256"]
    if digest != recorded:
        raise CarvedSurfaceError(f"carved grid {folder.name}: the elevation digest differs from the recorded one")
    return CarvedSurface(
        elevation=elevation,
        x_min_m=float(attrs["x_min_m"]),
        y_max_m=float(attrs["y_max_m"]),
        cell_size_m=float(attrs["cell_size_m"]),
    )

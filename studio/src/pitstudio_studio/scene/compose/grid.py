"""The terrain grid the compose stage reads back from the scene folder: bilinear height and gradient normals.

Row 0 is the north row (`layout: north-up`): the cell at row r, column c sits at x = x_min + c * cell and
y = y_max - r * cell. Queries outside the grid are clamped to its border, never extrapolated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Grid:
    elevation: np.ndarray  # (rows, cols) metres
    x_min: float
    y_max: float
    cell: float

    def height(self, x: float | np.ndarray, y: float | np.ndarray) -> np.ndarray:
        """Bilinear terrain height at x, y (arrays broadcast)."""
        rows, cols = self.elevation.shape
        c = np.clip((np.asarray(x, dtype=np.float64) - self.x_min) / self.cell, 0.0, cols - 1.0)
        r = np.clip((self.y_max - np.asarray(y, dtype=np.float64)) / self.cell, 0.0, rows - 1.0)
        c0, r0 = np.minimum(np.floor(c).astype(int), cols - 2), np.minimum(np.floor(r).astype(int), rows - 2)
        fc, fr = c - c0, r - r0
        e = self.elevation
        return (
            e[r0, c0] * (1 - fr) * (1 - fc)
            + e[r0, c0 + 1] * (1 - fr) * fc
            + e[r0 + 1, c0] * fr * (1 - fc)
            + e[r0 + 1, c0 + 1] * fr * fc
        )

    def normals(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Unit surface normals `(-dz/dx, -dz/dy, 1)` from central differences one cell either side of each point."""
        h = self.cell
        dzdx = (self.height(x + h, y) - self.height(x - h, y)) / (2 * h)
        dzdy = (self.height(x, y + h) - self.height(x, y - h)) / (2 * h)
        n = np.stack([-dzdx, -dzdy, np.ones_like(dzdx)], axis=-1)
        return n / np.linalg.norm(n, axis=-1, keepdims=True)


def load_grid(scene: Path) -> Grid | None:
    """The grid of a composed scene folder (`terrain/grid.zarr`), or None when the elevation array is not there."""
    folder = Path(scene) / "terrain" / "grid.zarr"
    if not (folder / "elevation").is_dir() or not (folder / "zarr.json").is_file():
        return None
    import zarr

    attrs = json.loads((folder / "zarr.json").read_text(encoding="utf-8"))["attributes"]
    elevation = np.asarray(zarr.open_group(str(folder), mode="r")["elevation"][:], dtype=np.float64)
    return Grid(elevation, float(attrs["x_min_m"]), float(attrs["y_max_m"]), float(attrs["cell_size_m"]))

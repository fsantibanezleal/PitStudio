"""Gridding: AOI checks, ground-point means, sentinel and range rules, harmonic hole fill (FR-004-04, -05, -12, -13)."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from pitstudio_studio.scene.common import SceneStageError

ELEVATION_MIN_M = -500.0  # FR-004-12 hard range, inclusive
ELEVATION_MAX_M = 9000.0
GROUND_CLASS = 2  # ASPRS ground (FR-004-04)


# ----------------------------------------------------------------------------------------------------------------
# elevations
# ----------------------------------------------------------------------------------------------------------------
@dataclass
class Sanitised:
    """Elevations in metres with rejected samples set to NaN, and why each was rejected."""

    values: np.ndarray
    rejected_non_finite: int
    rejected_sentinel: int
    rejected_out_of_range: int


def sanitise_elevations(values_m: np.ndarray, *, nodata_m: float | None = None) -> Sanitised:
    """Treat NaN, +-inf, the file's nodata sentinel and values outside [-500, 9000] m as nodata (FR-004-12).

    A sample is counted once, under the first rule it breaks: non-finite, sentinel, out of range.
    """
    values = np.array(values_m, dtype=np.float64, copy=True)
    finite = np.isfinite(values)
    sentinel = (
        finite & (values == nodata_m) if nodata_m is not None and math.isfinite(nodata_m) else np.zeros_like(finite)
    )
    out_of_range = finite & ~sentinel & ((values < ELEVATION_MIN_M) | (values > ELEVATION_MAX_M))
    rejected = ~finite | sentinel | out_of_range
    values[rejected] = np.nan
    return Sanitised(
        values=values,
        rejected_non_finite=int((~finite).sum()),
        rejected_sentinel=int(sentinel.sum()),
        rejected_out_of_range=int(out_of_range.sum()),
    )


# ----------------------------------------------------------------------------------------------------------------
# AOI
# ----------------------------------------------------------------------------------------------------------------
def _cells(extent: float, cell: float) -> int:
    return max(1, math.ceil(extent / cell - 1e-9))


def aoi_polygon(aoi_xy_m: Sequence[Sequence[float]]) -> Any:
    """The AOI as a valid shapely polygon, or `aoi-invalid` (FR-004-13)."""
    from shapely.geometry import Polygon

    try:
        pts = [(float(x), float(y)) for x, y in aoi_xy_m]
    except (TypeError, ValueError) as error:
        raise SceneStageError("aoi-invalid", "the AOI is not a list of [x, y] vertices") from error
    if len(pts) < 3:
        raise SceneStageError("aoi-invalid", f"the AOI has {len(pts)} vertices, at least 3 are required")
    if not all(math.isfinite(c) for p in pts for c in p):
        raise SceneStageError("aoi-invalid", "the AOI has a non-finite coordinate")
    poly = Polygon(pts)
    if not poly.is_valid:
        raise SceneStageError("aoi-invalid", "the AOI polygon is self-intersecting or otherwise invalid")
    if poly.area <= 0.0:
        raise SceneStageError("aoi-invalid", "the AOI polygon has zero area")
    return poly


def check_aoi(
    aoi_xy_m: Sequence[Sequence[float]],
    *,
    cell_size_m: float,
    max_cells: int,
    extents_xy_m: Sequence[Sequence[float]],
) -> Any:
    """Validate the AOI before any pixel or point is read; returns the polygon (FR-004-13).

    `extents_xy_m` are `(x_min, y_min, x_max, y_max)` boxes of the inputs in the site frame. Raises `aoi-invalid`
    (shape, finiteness, area, outside every input) or `aoi-too-large` (more than `max_cells` grid cells).
    """
    poly = aoi_polygon(aoi_xy_m)
    x0, y0, x1, y1 = poly.bounds
    if not any(x0 <= ex1 and x1 >= ex0 and y0 <= ey1 and y1 >= ey0 for ex0, ey0, ex1, ey1 in extents_xy_m):
        raise SceneStageError("aoi-invalid", "the AOI lies outside the extent of every input")
    cells = _cells(x1 - x0, cell_size_m) * _cells(y1 - y0, cell_size_m)
    if cells > max_cells:
        raise SceneStageError("aoi-too-large", f"the AOI would produce {cells} grid cells, the limit is {max_cells}")
    return poly


def grid_shape(poly: Any, cell_size_m: float) -> tuple[int, int, float, float]:
    """`(rows, cols, x_min, y_max)` of the grid that covers the AOI bounding box at `cell_size_m`."""
    x0, y0, x1, y1 = poly.bounds
    return _cells(y1 - y0, cell_size_m), _cells(x1 - x0, cell_size_m), float(x0), float(y1)


def aoi_mask(poly: Any, rows: int, cols: int, x_min: float, y_max: float, cell: float) -> np.ndarray:
    """Cells whose centre lies inside the AOI polygon (all True for an axis-aligned rectangle covering the grid)."""
    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    if poly.equals(poly.envelope) and poly.bounds == (x_min, y_max - rows * cell, x_min + cols * cell, y_max):
        return np.ones((rows, cols), dtype=bool)
    mask = rasterize(
        [(poly, 1)], out_shape=(rows, cols), transform=from_origin(x_min, y_max, cell, cell), fill=0, dtype="uint8"
    )
    return mask.astype(bool)


# ----------------------------------------------------------------------------------------------------------------
# ground points
# ----------------------------------------------------------------------------------------------------------------
def grid_ground_points(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    classification: np.ndarray,
    *,
    x_min: float,
    y_max: float,
    rows: int,
    cols: int,
    cell_size_m: float,
) -> np.ndarray:
    """Per-cell mean elevation of the ASPRS class 2 points (FR-004-04); NaN where a cell has no ground point.

    Cell (r, c) holds the points with `x_min + c*cell <= x < x_min + (c+1)*cell` and `y_max - (r+1)*cell < y <= y_max
    - r*cell`.
    The mean is order independent: points are sorted by cell and elevation, then summed in float64.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)
    keep = np.asarray(classification) == GROUND_CLASS
    x, y, z = x[keep], y[keep], z[keep]
    col = np.floor((x - x_min) / cell_size_m)
    q = (y_max - y) / cell_size_m
    row = np.where(q > 0, np.ceil(q) - 1.0, np.where(q == 0, 0.0, -1.0))
    inside = (
        np.isfinite(z) & np.isfinite(col) & np.isfinite(row) & (col >= 0) & (col < cols) & (row >= 0) & (row < rows)
    )
    flat = row[inside].astype(np.int64) * cols + col[inside].astype(np.int64)
    z = z[inside]
    out = np.full(rows * cols, np.nan, dtype=np.float64)
    if flat.size:
        order = np.lexsort((z, flat))
        flat, z = flat[order], z[order]
        starts = np.flatnonzero(np.r_[True, flat[1:] != flat[:-1]])
        sums = np.add.reduceat(z, starts)
        counts = np.diff(np.r_[starts, flat.size])
        out[flat[starts]] = sums / counts
    return out.reshape(rows, cols)


# ----------------------------------------------------------------------------------------------------------------
# harmonic hole fill
# ----------------------------------------------------------------------------------------------------------------
@dataclass
class FillResult:
    elevation: np.ndarray
    fill_mask: np.ndarray
    unfilled_holes: int
    unfilled_cells: int


def _components(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """4-connected components of the True cells of `mask`."""
    rows, cols = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    found: list[list[tuple[int, int]]] = []
    for r0, c0 in zip(*np.nonzero(mask), strict=True):
        if seen[r0, c0]:
            continue
        cells = []
        queue = deque([(int(r0), int(c0))])
        seen[r0, c0] = True
        while queue:
            r, c = queue.popleft()
            cells.append((r, c))
            for rr, cc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if 0 <= rr < rows and 0 <= cc < cols and mask[rr, cc] and not seen[rr, cc]:
                    seen[rr, cc] = True
                    queue.append((rr, cc))
        found.append(cells)
    return found


def _small_hole_mask(nodata: np.ndarray, max_cells: int) -> np.ndarray:
    """Nodata cells that belong to a 4-connected hole of at most `max_cells` cells (GDAL sieve, connectivity 4)."""
    if int(nodata.sum()) <= 20_000 or max_cells + 1 >= nodata.size:
        small = np.zeros_like(nodata)
        for cells in _components(nodata):
            if len(cells) <= max_cells:
                for r, c in cells:
                    small[r, c] = True
        return small
    from rasterio.features import sieve

    kept = sieve(nodata.astype(np.uint8), size=max_cells + 1, connectivity=4)
    return nodata & (kept == 0)


def _count_regions(mask: np.ndarray) -> int:
    from rasterio.features import shapes

    return sum(1 for _, value in shapes(mask.astype(np.uint8), mask=mask, connectivity=4) if value == 1)


def fill_holes(elevation: np.ndarray, *, max_fill_cells: int = 16, domain: np.ndarray | None = None) -> FillResult:
    """Fill 4-connected nodata holes of at most `max_fill_cells` with the discrete harmonic interpolant (FR-004-05).

    Each unknown cell equals the mean of its four in-grid neighbours; valid neighbours give the Dirichlet values; the
    system of one hole (at most 16 unknowns by default) is solved with `numpy.linalg.solve` in float64. Larger holes
    stay NaN.
    `domain` (optional bool array) restricts the grid to the cells inside the AOI polygon: cells outside it are neither
    holes nor neighbours.
    """
    z = np.array(elevation, dtype=np.float64, copy=True)
    rows, cols = z.shape
    inside = np.ones(z.shape, dtype=bool) if domain is None else np.asarray(domain, dtype=bool)
    nodata = np.isnan(z) & inside
    fill_mask = np.zeros(z.shape, dtype=bool)
    if not nodata.any():
        return FillResult(z, fill_mask, 0, 0)
    small = _small_hole_mask(nodata, max_fill_cells) if max_fill_cells > 0 else np.zeros_like(nodata)
    for cells in _components(small):
        index = {cell: i for i, cell in enumerate(cells)}
        a = np.zeros((len(cells), len(cells)))
        b = np.zeros(len(cells))
        for (r, c), i in index.items():
            for rr, cc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if not (0 <= rr < rows and 0 <= cc < cols and inside[rr, cc]):
                    continue
                a[i, i] += 1.0
                if (rr, cc) in index:
                    a[i, index[(rr, cc)]] -= 1.0
                else:
                    b[i] += z[rr, cc]
        if not np.any(np.diag(a)):
            continue
        try:
            solution = np.linalg.solve(a, b)
        except np.linalg.LinAlgError:
            continue
        for (r, c), i in index.items():
            z[r, c] = solution[i]
            fill_mask[r, c] = True
    left = np.isnan(z) & inside
    return FillResult(z, fill_mask, _count_regions(left) if left.any() else 0, int(left.sum()))

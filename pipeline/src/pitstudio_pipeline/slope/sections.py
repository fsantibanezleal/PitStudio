"""Reference sections cut from a DEM (`s10_preprocess`, FR-010-06).

A north-up GeoTIFF (area registration: pixel (row, col) has its centre at x = x0 + (col + 0.5) cell, y = y0 - (row +
0.5)
cell) is sampled by bilinear interpolation along lines perpendicular to a wall line, at 1 m spacing; the ground
profile is
simplified by Douglas-Peucker with tolerance 0.25 m; one DC-010-01 section document is written per line with the DEM
SHA-256,
the profile end coordinates and the provisional site label in its ``source``.
"""

from __future__ import annotations

import copy
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import tifffile

SAMPLE_SPACING_M = 1
SIMPLIFY_TOLERANCE_M = 0.25
MIN_SECTIONS = 3


@dataclass
class Dem:
    z: np.ndarray
    x0: float
    y0: float
    cell: float
    crs: str
    nodata: float | None
    sha256: str


@dataclass
class SectionsResult:
    sections: list[dict[str, Any]]
    manifest: dict[str, Any]


def douglas_peucker(points: Any, tolerance: float) -> np.ndarray:
    """Subset of the polyline's vertices (ends kept): no dropped vertex is farther than ``tolerance`` from the chord."""
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2 or pts.shape[0] < 2:
        raise ValueError("a polyline needs at least 2 points of 2 coordinates")
    if not np.all(np.isfinite(pts)):
        raise ValueError("the polyline has a non-finite coordinate")
    if not (isinstance(tolerance, int | float) and math.isfinite(tolerance) and tolerance > 0.0):
        raise ValueError("the tolerance must be finite and > 0")
    keep = np.zeros(len(pts), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ab = pts[b] - pts[a]
        norm = float(np.hypot(*ab))
        mid = pts[a + 1 : b] - pts[a]
        dist = np.abs(ab[0] * mid[:, 1] - ab[1] * mid[:, 0]) / norm if norm > 0.0 else np.hypot(mid[:, 0], mid[:, 1])
        i = int(np.argmax(dist))
        if dist[i] > tolerance:
            k = a + 1 + i
            keep[k] = True
            stack.extend([(a, k), (k, b)])
    return pts[keep]


def read_dem(path: str | Path) -> Dem:
    """Read a north-up GeoTIFF with its georeferencing tags (33550, 33922, 34735, 42113)."""
    p = Path(path)
    raw = p.read_bytes()
    with tifffile.TiffFile(str(p)) as tf:
        page = tf.pages[0]
        z = np.asarray(page.asarray(), dtype=np.float64)
        tags = page.tags
        scale = tags[33550].value
        tie = tags[33922].value
        keys = tags[34735].value if 34735 in tags else ()
        nodata_tag = tags[42113].value if 42113 in tags else None
    crs = ""
    for i in range(4, len(keys) - 3, 4):
        if keys[i] in (3072, 2048):
            crs = f"EPSG:{keys[i + 3]}"
    if not crs:
        raise ValueError("the GeoTIFF states no EPSG code")
    cell = float(scale[0])
    x0 = float(tie[3] - tie[0] * scale[0])
    y0 = float(tie[4] + tie[1] * scale[1])
    nodata = float(str(nodata_tag).strip("\x00 ")) if nodata_tag not in (None, "") else None
    return Dem(z, x0, y0, cell, crs, nodata, hashlib.sha256(raw).hexdigest())


def sample_profile(dem: Dem, start_xy: Any, end_xy: Any, spacing: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Bilinear samples at distance 0, spacing, ... along the line; ValueError outside the DEM or on a nodata cell."""
    a, b = np.asarray(start_xy, dtype=float), np.asarray(end_xy, dtype=float)
    if not (np.all(np.isfinite(a)) and np.all(np.isfinite(b)) and spacing > 0.0):
        raise ValueError("the profile line and the spacing must be finite and positive")
    length = float(np.hypot(*(b - a)))
    if length == 0.0:
        raise ValueError("the profile line has zero length")
    d = np.arange(0.0, length + 1e-9, spacing)
    xy = a[None, :] + (b - a)[None, :] * (d / length)[:, None]
    col = (xy[:, 0] - dem.x0) / dem.cell - 0.5
    row = (dem.y0 - xy[:, 1]) / dem.cell - 0.5
    rows, cols = dem.z.shape
    if np.any(col < -1e-9) or np.any(row < -1e-9) or np.any(col > cols - 1 + 1e-9) or np.any(row > rows - 1 + 1e-9):
        raise ValueError("a sample falls outside the DEM")
    c0 = np.clip(np.floor(col + 1e-9).astype(int), 0, cols - 2 if cols > 1 else 0)
    r0 = np.clip(np.floor(row + 1e-9).astype(int), 0, rows - 2 if rows > 1 else 0)
    fc, fr = np.clip(col - c0, 0.0, 1.0), np.clip(row - r0, 0.0, 1.0)
    z = np.zeros(len(d))
    for dr, dc, w in ((0, 0, (1 - fr) * (1 - fc)), (0, 1, (1 - fr) * fc), (1, 0, fr * (1 - fc)), (1, 1, fr * fc)):
        v = dem.z[np.minimum(r0 + dr, rows - 1), np.minimum(c0 + dc, cols - 1)]
        used = w > 1e-12
        bad = used & ((~np.isfinite(v)) | (dem.nodata is not None and (v == dem.nodata)))
        if np.any(bad):
            raise ValueError("a sample touches a nodata cell")
        z += np.where(used, w * v, 0.0)
    return d, z


def extract_sections(
    dem_path: str | Path,
    *,
    source_id: str,
    site_label: str,
    wall_line: Any,
    half_length_m: float,
    defaults: dict[str, Any],
    n_sections: int = MIN_SECTIONS,
) -> SectionsResult:
    """Cut ``n_sections`` (>= 3) sections perpendicular to the wall line (see the module docstring)."""
    if n_sections < MIN_SECTIONS:
        raise ValueError(f"at least {MIN_SECTIONS} sections per site are needed, got {n_sections}")
    if not (isinstance(half_length_m, int | float) and math.isfinite(half_length_m) and half_length_m > 0.0):
        raise ValueError("half_length_m must be finite and > 0")
    p0, p1 = (np.asarray(p, dtype=float) for p in wall_line)
    wall = p1 - p0
    wall_len = float(np.hypot(*wall))
    if not (np.all(np.isfinite(wall)) and wall_len > 0.0):
        raise ValueError("the wall line needs two distinct finite points")
    dem = read_dem(dem_path)
    w = wall / wall_len
    normal = np.array([-w[1], w[0]])
    docs: list[dict[str, Any]] = []
    for k in range(n_sections):
        centre = p0 + wall * ((k + 0.5) / n_sections)
        start, end = centre - half_length_m * normal, centre + half_length_m * normal
        d, z = sample_profile(dem, start, end, float(SAMPLE_SPACING_M))
        if z[0] < z[-1]:  # distance 0 on the higher side: the face descends towards +x
            start, end = end, start
            d, z = sample_profile(dem, start, end, float(SAMPLE_SPACING_M))
        ground = douglas_peucker(np.column_stack([d, z]), SIMPLIFY_TOLERANCE_M)
        slopes = np.diff(ground[:, 1]) / np.diff(ground[:, 0])
        steepest = int(np.argmin(slopes))
        if not slopes[steepest] < 0.0:
            raise ValueError("the profile has no descending face")
        doc = {
            "schema_version": "1.0",
            "section_id": f"{source_id.lower()}-s{k + 1}",
            "source": {
                "kind": "dem",
                "source_id": source_id,
                "dem_sha256": dem.sha256,
                "crs": dem.crs,
                "profile_start_m": [float(x) for x in start],
                "profile_end_m": [float(x) for x in end],
                "sample_spacing_m": SAMPLE_SPACING_M,
                "simplify_tolerance_m": SIMPLIFY_TOLERANCE_M,
                "site_label": site_label,
            },
            "ground": [[float(x), float(y)] for x, y in ground],
            "crest_x_m": float(ground[steepest, 0]),
            "toe_x_m": float(ground[steepest + 1, 0]),
            "materials": copy.deepcopy(defaults["materials"]),
            "pore_pressure_ratio": defaults["pore_pressure_ratio"],
            "analysis": copy.deepcopy(defaults["analysis"]),
        }
        docs.append(doc)
    manifest = {
        "stage": "s10_preprocess",
        "inputs": [{"path": Path(dem_path).name, "sha256": dem.sha256}],
        "dem_sha256": dem.sha256,
        "site_label": site_label,
        "sections": [
            {
                "section_id": d["section_id"],
                "profile_start_m": d["source"]["profile_start_m"],
                "profile_end_m": d["source"]["profile_end_m"],
            }
            for d in docs
        ],
    }
    return SectionsResult(docs, manifest)

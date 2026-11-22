"""The orthophoto albedo of the terrain grid (FR-004-48).

An orthophoto source registered in the data root (spec 008) is resampled to the terrain grid: the acquisition year
nearest the year of the DEM is chosen, every file of that year is read through its own CRS, and each grid cell takes the
bilinear sample of bands 1 to 3 at its centre (a fourth band, near-infrared in NAIP, is never read). A cell no file
covers is an error, never a guess. The result is 8-bit sRGB (untagged JPEG) written as one image or, when a side exceeds
`MAX_SIDE_PX`, one image per LOD-0 tile window.
"""

from __future__ import annotations

import io
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_studio.scene import common
from pitstudio_studio.scene.common import SceneStageError
from pitstudio_studio.scene.terrain import frame, tiles
from pitstudio_studio.scene.terrain import io as terrain_io

MAX_SIDE_PX = 8192  # FR-004-48: larger extents are written as one image per LOD-0 tile
JPEG_QUALITY = 95
ALBEDO_DIR = "terrain/albedo"
SINGLE_IMAGE = f"{ALBEDO_DIR}/ortho.jpg"
_DATE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?!\d)")
_TAG_DATE = re.compile(r"^((?:19|20)\d{2}):\d{2}:\d{2}")


@dataclass(frozen=True)
class Resampled:
    """The orthophoto on the terrain grid: `rgb` is uint8 `(rows, cols, 3)`, row 0 the north row."""

    rgb: np.ndarray
    ground_resolution_m: float


@dataclass(frozen=True)
class Header:
    """What a georeferenced image says about itself, read without its pixels."""

    crs: dict[str, Any]
    x0: float
    y0: float
    dx: float
    dy: float
    width: int
    height: int
    metres_per_unit: float


def acquisition_year(path: Path | str) -> int:
    """The acquisition year of an image: the `yyyymmdd` date of its name (NAIP naming), else `TIFFTAG_DATETIME`."""
    path = Path(path)
    dates = _DATE.findall(path.stem)
    if dates:
        return int(dates[-1])
    import rasterio

    try:
        with rasterio.open(path) as ds:
            stamp = ds.tags().get("TIFFTAG_DATETIME", "")
    except Exception as error:
        raise SceneStageError(
            "input-corrupt", f"{path.name}: cannot open the image ({type(error).__name__})"
        ) from error
    match = _TAG_DATE.match(stamp)
    if match is None:
        raise SceneStageError(
            "input-corrupt",
            f"{path.name}: no readable acquisition year (no yyyymmdd date in the name, no TIFFTAG_DATETIME)",
        )
    return int(match.group(1))


def choose_year(years: Sequence[tuple[Path | str, int]], dem_year: int) -> int:
    """The acquisition year nearest `dem_year`; a tie goes to the earlier year."""
    candidates = sorted({int(year) for _, year in years})
    if not candidates:
        raise SceneStageError("input-corrupt", "no orthophoto file to choose a year from")
    return min(candidates, key=lambda year: (abs(year - int(dem_year)), year))


def read_header(path: Path | str) -> Header:
    """Header-only read: the horizontal CRS record, the north-up affine transform and the size."""
    import pyproj
    import rasterio

    path = Path(path)
    try:
        with rasterio.open(path) as ds:
            wkt = ds.crs.to_wkt() if ds.crs else None
            transform, width, height, count, dtype = ds.transform, ds.width, ds.height, ds.count, ds.dtypes[0]
    except Exception as error:
        raise SceneStageError(
            "input-corrupt", f"{path.name}: cannot open the image ({type(error).__name__})"
        ) from error
    if not wkt:
        raise SceneStageError("crs-mismatch", f"{path.name}: the image has no CRS")
    if count < 3 or dtype != "uint8":
        raise SceneStageError(
            "input-corrupt", f"{path.name}: expected 8-bit bands 1 to 3 as RGB, found {count} band(s) of {dtype}"
        )
    if transform.b != 0.0 or transform.d != 0.0 or transform.a <= 0.0 or transform.e >= 0.0:
        raise SceneStageError(
            "input-corrupt", f"{path.name}: the image is rotated or flipped; only north-up images are read"
        )
    crs = pyproj.CRS.from_wkt(wkt)
    horizontal = next((s for s in (crs.sub_crs_list if crs.is_compound else [crs]) if s.is_projected), None)
    if horizontal is None:
        raise SceneStageError(
            "crs-mismatch", f"{path.name}: the horizontal CRS is not projected (metres or feet required)"
        )
    unit = terrain_io._unit_record(horizontal.axis_info[0].unit_conversion_factor, "horizontal", path.name)
    record = {"horizontal": terrain_io._ref(horizontal), "horizontal_unit": unit}
    return Header(
        record,
        float(transform.c),
        float(transform.f),
        float(transform.a),
        float(-transform.e),
        int(width),
        int(height),
        float(unit["factor_to_m"]),
    )


def _sample(path: Path, header: Header, u: np.ndarray, v: np.ndarray, take: np.ndarray, out: np.ndarray) -> None:
    """Bilinear samples of bands 1 to 3 at the continuous pixel coordinates (u, v) of the cells in `take`."""
    import rasterio
    from rasterio.windows import Window

    fu = np.clip(u[take] - 0.5, 0.0, header.width - 1.0)
    fv = np.clip(v[take] - 0.5, 0.0, header.height - 1.0)
    c0 = np.minimum(np.floor(fu).astype(np.int64), max(header.width - 2, 0))
    r0 = np.minimum(np.floor(fv).astype(np.int64), max(header.height - 2, 0))
    c1 = np.minimum(c0 + 1, header.width - 1)
    r1 = np.minimum(r0 + 1, header.height - 1)
    col_off, row_off = int(c0.min()), int(r0.min())
    window = Window(col_off, row_off, int(c1.max()) - col_off + 1, int(r1.max()) - row_off + 1)
    with rasterio.open(path) as ds:
        block = ds.read([1, 2, 3], window=window).astype(np.float64)
    tc, tr = (fu - c0)[:, None], (fv - r0)[:, None]

    def px(r: np.ndarray, c: np.ndarray) -> np.ndarray:
        return block[:, r - row_off, c - col_off].T

    out[take] = (1 - tr) * ((1 - tc) * px(r0, c0) + tc * px(r0, c1)) + tr * ((1 - tc) * px(r1, c0) + tc * px(r1, c1))


def resample_orthophoto(
    files: Sequence[Path | str],
    *,
    rows: int,
    cols: int,
    x_min_m: float,
    y_max_m: float,
    cell_size_m: float,
    origin: Mapping[str, Any],
) -> Resampled:
    """Bilinear samples of `files` at the centre of each grid cell; files are mosaicked in name order (the first one
    that covers a cell wins). Raises `input-corrupt` (naming the count) when a cell is left uncovered."""
    cx, cy = np.meshgrid(
        x_min_m + (np.arange(cols) + 0.5) * cell_size_m, y_max_m - (np.arange(rows) + 0.5) * cell_size_m
    )
    out = np.zeros((rows, cols, 3), dtype=np.float64)
    covered = np.zeros((rows, cols), dtype=bool)
    resolutions: list[float] = []
    for path in sorted((Path(f) for f in files), key=lambda p: p.name):
        header = read_header(path)
        sx, sy = frame.to_source(cx, cy, crs=header.crs, origin=origin)
        u, v = (sx - header.x0) / header.dx, (header.y0 - sy) / header.dy
        take = (u >= 0) & (u <= header.width) & (v >= 0) & (v <= header.height) & ~covered
        if not take.any():
            continue
        _sample(path, header, u, v, take, out)
        covered |= take
        resolutions.append(max(header.dx, header.dy) * header.metres_per_unit)
    missing = int((~covered).sum())
    if missing:
        raise SceneStageError(
            "input-corrupt",
            f"the orthophoto leaves {missing} of {rows * cols} grid cells uncovered; a hole is never filled",
        )
    rgb = np.rint(np.clip(out, 0.0, 255.0)).astype(np.uint8)
    return Resampled(rgb, round(max(resolutions), 6))


def encode_jpeg(rgb: np.ndarray) -> bytes:
    """8-bit RGB JPEG at quality 95 without chroma subsampling or optimised tables (deterministic bytes)."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(rgb), "RGB").save(
        buffer, format="JPEG", quality=JPEG_QUALITY, subsampling=0, optimize=False, progressive=False
    )
    return buffer.getvalue()


def tile_window(tx: int, ty: int, rows: int, cols: int) -> tuple[int, int, int, int]:
    """`(row0, col0, height, width)` in cells of the image of LOD-0 tile `(tx, ty)` (x east, y north, 0 south-west)."""
    _, ny, _ = tiles.layout(rows, cols)
    r0, c0 = (ny - 1 - ty) * tiles.STRIDE, tx * tiles.STRIDE
    return r0, c0, min(tiles.TILE_SAMPLES, rows - r0), min(tiles.TILE_SAMPLES, cols - c0)


def albedo_images(rgb: np.ndarray) -> dict[str, bytes]:
    """Scene-relative path to JPEG bytes: `terrain/albedo/ortho.jpg`, or one `<lod>-<level>-<x>-<y>.jpg` per tile."""
    rows, cols = rgb.shape[:2]
    if max(rows, cols) <= MAX_SIDE_PX:
        return {SINGLE_IMAGE: encode_jpeg(rgb)}
    nx, ny, level = tiles.layout(rows, cols)
    images: dict[str, bytes] = {}
    for ty in range(ny):
        for tx in range(nx):
            r0, c0, height, width = tile_window(tx, ty, rows, cols)
            images[f"{ALBEDO_DIR}/0-{level}-{tx}-{ty}.jpg"] = encode_jpeg(rgb[r0 : r0 + height, c0 : c0 + width])
    return dict(sorted(images.items()))


def albedo_record(
    source_id: str, year: int, dem_year: int, resolution_m: float, images: Mapping[str, bytes], inputs: Sequence[Path]
) -> dict[str, Any]:
    """The `terrain.albedo` entry of the scene manifest (DC-004-02): digests of every image and every input file."""
    return {
        "source": source_id,
        "year": int(year),
        "dem_year": int(dem_year),
        "ground_resolution_m": float(resolution_m),
        "images": [{"path": rel, "sha256": common.sha256_bytes(data)} for rel, data in sorted(images.items())],
        "inputs": [
            {"path": f"{source_id}/{p.name}", "sha256": common.sha256_file(p)}
            for p in sorted(inputs, key=lambda p: p.name)
        ],
    }

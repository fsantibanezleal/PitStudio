"""File-level validators of `s10_preprocess`: rasters, point clouds, vectors, images and masks (FR-008-23, -24).

Each validator returns None for a valid file and raises `IngestionRejected` otherwise; every violation names the file,
the property, the found value and the expected value (a violation with `field_kind` `property`). The library reads
only headers and tags wherever the format allows it, so a validator never loads a whole raster or point cloud.
"""

from __future__ import annotations

import math
import sqlite3
import struct
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import laspy
import shapely
import tifffile
from PIL import Image, UnidentifiedImageError

from pitstudio_pipeline.errors import IngestionRejected
from pitstudio_pipeline.ingest.report import violation

Box = Sequence[float]
GEOKEY_PROJECTED, GEOKEY_GEOGRAPHIC = 3072, 2048  # GeoTIFF 1.0 ProjectedCSTypeGeoKey, GeographicTypeGeoKey
USER_DEFINED = 32767


def _prop(file: str, name: str, rule: str, found: Any, expected: str, *, row: int | None = None) -> dict[str, Any]:
    return violation(file, name, rule, row=row, field_kind="property", value=found, expected=expected)


def _unreadable(file: str, exc: Exception) -> IngestionRejected:
    return IngestionRejected([_prop(file, "file", "readable file", type(exc).__name__, "a well-formed file")])


def _inside(box: Box, aoi: Box) -> bool:
    return box[0] >= aoi[0] and box[1] >= aoi[1] and box[2] <= aoi[2] and box[3] <= aoi[3]


def _finite(*values: float) -> bool:
    return all(isinstance(v, int | float) and math.isfinite(v) for v in values)


# --------------------------------------------------------------------------------------------------------- rasters
def _geokey_crs(directory: Sequence[int] | None) -> int | None:
    """The EPSG code of the (projected or geographic) CRS key of a GeoKeyDirectory, or None."""
    if not directory or len(directory) < 4:
        return None
    for index in range(int(directory[3])):
        base = 4 + 4 * index
        if base + 3 >= len(directory):
            break
        key, location, _count, value = directory[base : base + 4]
        if key in (GEOKEY_PROJECTED, GEOKEY_GEOGRAPHIC) and location == 0 and 0 < value < USER_DEFINED:
            return int(value)
    return None


def validate_raster(path: Path | str, *, aoi: Box, dtype: str, nodata: float, file: str) -> None:
    """Rasters: CRS present, cell size positive and finite (metres), declared dtype and nodata, extent in the AOI."""
    found: list[dict[str, Any]] = []
    try:
        with tifffile.TiffFile(path) as tif:
            page = tif.pages[0]
            tags = {tag.code: tag.value for tag in page.tags.values()}
            shape = page.shape
            actual_dtype = str(page.dtype)
    except Exception as exc:
        raise _unreadable(file, exc) from None
    if _geokey_crs(tags.get(34735)) is None:
        found.append(_prop(file, "crs", "CRS present", None, "an EPSG coordinate reference system"))
    scale = tags.get(33550)
    cell = None if not scale else (float(scale[0]), float(scale[1]))
    if cell is None or not _finite(*cell) or min(cell) <= 0:
        found.append(_prop(file, "cell_size_m", "cell size positive and finite", cell, "> 0 m and finite"))
    if actual_dtype != str(dtype):
        found.append(_prop(file, "dtype", "declared data type", actual_dtype, str(dtype)))
    raw_nodata = tags.get(42113)
    try:
        actual_nodata = float(str(raw_nodata).strip("\x00 ")) if raw_nodata is not None else None
    except ValueError:
        actual_nodata = None
    if actual_nodata is None or actual_nodata != float(nodata):
        found.append(_prop(file, "nodata", "declared nodata value", actual_nodata, str(float(nodata))))
    tie = tags.get(33922)
    if cell is not None and _finite(*cell) and tie and len(tie) >= 6 and len(shape) >= 2:
        height, width = shape[-2], shape[-1]
        xmin, ymax = tie[3] - tie[0] * cell[0], tie[4] + tie[1] * cell[1]
        extent = (xmin, ymax - height * cell[1], xmin + width * cell[0], ymax)
        if not _inside(extent, aoi):
            found.append(
                _prop(file, "extent", "extent inside the area of interest", str(extent), f"inside {tuple(aoi)}")
            )
    if found:
        raise IngestionRejected(found)


# ------------------------------------------------------------------------------------------------------ point clouds
def _las_has_crs(header: laspy.LasHeader) -> bool:
    """A CRS is present when a WKT record (2112) or a GeoKeyDirectory (34735) with an EPSG key is in the header."""
    for vlr in header.vlrs:
        if vlr.record_id == 2112:
            return True
        if vlr.record_id == 34735:
            keys = getattr(vlr, "geo_keys", None)
            if keys is not None:
                directory = [1, 1, 0, len(keys)] + [
                    x for k in keys for x in (k.id, k.tiff_tag_location, k.count, k.value_offset)
                ]
            else:
                data = bytes(getattr(vlr, "record_data", b"") or b"")
                directory = list(struct.unpack_from(f"<{len(data) // 2}H", data)) if len(data) >= 8 else []
            if _geokey_crs(directory) is not None:
                return True
    return False


def validate_point_cloud(path: Path | str, *, aoi: Box, file: str) -> None:
    """Point clouds (LAS/LAZ): CRS present, point count > 0, classification codes present, bounds inside the AOI."""
    found: list[dict[str, Any]] = []
    try:
        with laspy.open(path) as reader:
            header = reader.header
            count = int(header.point_count)
            has_crs = _las_has_crs(header)
            bounds = (float(header.mins[0]), float(header.mins[1]), float(header.maxs[0]), float(header.maxs[1]))
            classified = False
            if count > 0:
                for points in reader.chunk_iterator(1_000_000):
                    if bool((points.classification != 0).any()):
                        classified = True
                        break
    except Exception as exc:
        raise _unreadable(file, exc) from None
    if not has_crs:
        found.append(_prop(file, "crs", "CRS present", None, "a GeoTIFF key or WKT record"))
    if count <= 0:
        found.append(_prop(file, "point_count", "at least one point", count, "> 0"))
    elif not classified:
        found.append(_prop(file, "classification", "classification codes present", "all 0", "some class other than 0"))
    if count > 0 and not _inside(bounds, aoi):
        found.append(_prop(file, "bounds", "bounds inside the area of interest", str(bounds), f"inside {tuple(aoi)}"))
    if found:
        raise IngestionRejected(found)


# ------------------------------------------------------------------------------------------------------ vector layers
_ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}  # GeoPackage binary header, envelope indicator -> envelope length


def _gpkg_wkb(blob: bytes) -> bytes:
    """The WKB inside a GeoPackage geometry blob (OGC 12-128r18, section 2.1.3)."""
    if len(blob) < 8 or blob[:2] != b"GP":
        raise ValueError("not a GeoPackage geometry blob")
    envelope = _ENVELOPE_BYTES.get((blob[3] >> 1) & 0b111)
    if envelope is None:
        raise ValueError("unknown envelope indicator")
    return blob[8 + envelope :]


def validate_vector(path: Path | str, *, required_attributes: Sequence[str], aoi: Box | None = None, file: str) -> None:
    """Vector layers (GeoPackage): valid geometries, CRS present, required attributes present."""
    found: list[dict[str, Any]] = []
    try:
        con = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
        try:
            table, column, srs_id = con.execute(
                "SELECT table_name, column_name, srs_id FROM gpkg_geometry_columns LIMIT 1"
            ).fetchone()
            attributes = {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}
            blobs = con.execute(f'SELECT "{column}" FROM "{table}" ORDER BY rowid').fetchall()
        finally:
            con.close()
    except Exception as exc:
        raise _unreadable(file, exc) from None
    if srs_id is None or int(srs_id) <= 0:
        found.append(
            _prop(file, "crs", "CRS present", None if srs_id is None else int(srs_id), "a defined SRS (id > 0)")
        )
    found.extend(
        violation(file, attribute, "required attribute present", expected="attribute present")
        for attribute in required_attributes
        if attribute not in attributes
    )
    for index, (blob,) in enumerate(blobs):
        try:
            geometry = shapely.from_wkb(_gpkg_wkb(bytes(blob)))
            valid, reason = shapely.is_valid(geometry), shapely.is_valid_reason(geometry)
        except Exception as exc:
            valid, reason, geometry = False, f"{type(exc).__name__}", None
        if not valid:
            found.append(_prop(file, "geometry", "valid geometry (OGC SFA)", reason, "a valid geometry", row=index))
        elif aoi is not None and not _inside(tuple(shapely.bounds(geometry)), aoi):
            found.append(
                _prop(
                    file, "extent", "geometry inside the area of interest", "outside", f"inside {tuple(aoi)}", row=index
                )
            )
    if found:
        raise IngestionRejected(found)


# ------------------------------------------------------------------------------------------------- images and masks
def _open_image(path: Path | str, file: str) -> Image.Image:
    try:
        image = Image.open(path)
        image.load()  # decode fully: a truncated file fails here, not later
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise _unreadable(file, exc) from None
    return image


def _check_image(image: Image.Image, file: str, *, fmt: str, size: tuple[int, int], mode: str) -> None:
    found = []
    if image.format != fmt:
        found.append(_prop(file, "format", "file format", image.format, fmt))
    if image.size != tuple(size):
        found.append(_prop(file, "size", "image size", f"{image.size[0]}x{image.size[1]}", f"{size[0]}x{size[1]}"))
    if image.mode != mode:
        found.append(_prop(file, "mode", "colour mode", image.mode, mode))
    if found:
        raise IngestionRejected(found)


def validate_image(path: Path | str, *, size: tuple[int, int] = (512, 512), file: str) -> None:
    """Mendeley images: JPEG, 512 x 512, RGB."""
    _check_image(_open_image(path, file), file, fmt="JPEG", size=size, mode="RGB")


def validate_mask(path: Path | str, *, size: tuple[int, int] = (512, 512), file: str) -> None:
    """Mendeley masks: PNG, 512 x 512, indexed `P` mode (0 = background, k = instance k, at most 255 instances)."""
    _check_image(_open_image(path, file), file, fmt="PNG", size=size, mode="P")


def validate_image_mask_set(images: Sequence[Path | str], masks: Sequence[Path | str], *, file_prefix: str) -> None:
    """Exactly one mask per image, paired by file stem; an image without a mask or a stray mask is a violation."""
    prefix = file_prefix.rstrip("/")
    image_stems = Counter(Path(i).stem for i in images)
    mask_stems = Counter(Path(m).stem for m in masks)
    found = []
    for image in images:
        stem = Path(image).stem
        if mask_stems[stem] == 0:
            found.append(_prop(f"{prefix}/{Path(image).name}", "mask", "one mask per image", 0, "exactly 1 mask"))
    for mask in masks:
        stem = Path(mask).stem
        name = f"{prefix}/{Path(mask).name}"
        if image_stems[stem] == 0:
            found.append(_prop(name, "mask", "one mask per image", "no image", "an image with the same stem"))
        elif mask_stems[stem] > 1:
            found.append(_prop(name, "mask", "one mask per image", mask_stems[stem], "exactly 1 mask"))
    if found:
        raise IngestionRejected(found)


__all__ = [
    "validate_image",
    "validate_image_mask_set",
    "validate_mask",
    "validate_point_cloud",
    "validate_raster",
    "validate_vector",
]

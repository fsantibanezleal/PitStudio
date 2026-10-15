"""Site-local frame: X east, Y north, Z up, metres, relative to the recipe's site origin (FR-004-02)."""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from typing import Any

import numpy as np


@cache
def _horizontal_crs(epsg: int | None, wkt: str | None) -> Any:
    import pyproj

    crs = pyproj.CRS.from_epsg(epsg) if epsg is not None else pyproj.CRS.from_wkt(wkt or "")
    if crs.is_compound:
        crs = next(s for s in crs.sub_crs_list if s.is_projected or s.is_geographic)
    return crs


@cache
def _transformer(source: Any, target_epsg: int) -> Any:
    import pyproj

    return pyproj.Transformer.from_crs(source, pyproj.CRS.from_epsg(target_epsg), always_xy=True)


def horizontal_crs(crs: Mapping[str, Any]) -> Any:
    """The pyproj horizontal CRS of a DC-004-03 `crs_record` (EPSG code, or the WKT when none exists)."""
    ref = crs["horizontal"]
    return _horizontal_crs(ref.get("epsg"), ref.get("wkt"))


def _same_frame(source: Any, origin_epsg: int) -> bool:
    import pyproj

    return bool(source.equals(pyproj.CRS.from_epsg(origin_epsg)))


def site_frame(
    x: np.ndarray, y: np.ndarray, z: np.ndarray, *, crs: Mapping[str, Any], origin: Mapping[str, Any]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Source-CRS coordinates to site-local metres, in float64.

    The horizontal transform is PROJ (`Transformer.from_crs(source, origin epsg, always_xy=True)`, which also converts
    feet to metres); the vertical one multiplies by the recorded unit factor; then the origin is subtracted.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)
    source = horizontal_crs(crs)
    if _same_frame(source, int(origin["epsg"])):
        east, north = x, y
    else:
        east, north = _transformer(source, int(origin["epsg"])).transform(x, y)
        east, north = np.asarray(east, dtype=np.float64), np.asarray(north, dtype=np.float64)
    factor = float(crs["vertical_unit"]["factor_to_m"])
    return (
        east - float(origin["easting_m"]),
        north - float(origin["northing_m"]),
        z * factor - float(origin["z0_m"]),
    )


def site_frame_f32(
    x: np.ndarray, y: np.ndarray, z: np.ndarray, *, crs: Mapping[str, Any], origin: Mapping[str, Any]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`site_frame` stored as float32 offsets: the float64 result, cast once."""
    east, north, up = site_frame(x, y, z, crs=crs, origin=origin)
    return east.astype(np.float32), north.astype(np.float32), up.astype(np.float32)


def to_source(
    xs: np.ndarray, ys: np.ndarray, *, crs: Mapping[str, Any], origin: Mapping[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    """Inverse horizontal transform: site-local metres to source-CRS coordinates (in the source's own units)."""
    import pyproj

    east = np.asarray(xs, dtype=np.float64) + float(origin["easting_m"])
    north = np.asarray(ys, dtype=np.float64) + float(origin["northing_m"])
    source = horizontal_crs(crs)
    if _same_frame(source, int(origin["epsg"])):
        return east, north
    inverse = pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(int(origin["epsg"])), source, always_xy=True)
    ex, ny = inverse.transform(east, north)
    return np.asarray(ex, dtype=np.float64), np.asarray(ny, dtype=np.float64)

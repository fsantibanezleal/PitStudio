"""Reading DEM (GeoTIFF) and LAZ inputs with their own CRS, unit and datum metadata (FR-004-01, -03, -10, -11, -14)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_studio.scene.common import SceneStageError, scrub, sha256_file

US_FOOT = 1200 / 3937  # exact definition: 1 US survey foot in metres
INTL_FOOT = 0.3048  # exact definition: 1 international foot in metres
_UNIT_NAMES = (("metre", 1.0), ("us-survey-foot", US_FOOT), ("international-foot", INTL_FOOT))


@dataclass
class DemTile:
    """A DEM read from a GeoTIFF: `array` is float64 in source units, row 0 is the north edge."""

    array: np.ndarray
    x_min: float
    y_max: float
    cell_x: float
    cell_y: float
    nodata: float | None
    crs: dict[str, Any]
    name: str = ""


@dataclass
class LazTile:
    """Points read from a LAZ tile (source CRS and units) with their ASPRS classification."""

    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    classification: np.ndarray
    crs: dict[str, Any]
    name: str = ""


# ----------------------------------------------------------------------------------------------------------------
# CRS record
# ----------------------------------------------------------------------------------------------------------------
def _unit_record(factor: float, what: str, name: str) -> dict[str, Any]:
    for unit, exact in _UNIT_NAMES:
        if abs(factor - exact) <= 1e-12:
            return {"name": unit, "factor_to_m": exact}
    raise SceneStageError("crs-mismatch", f"{name}: {what} axis unit with factor {factor!r} to metres is not supported")


def _ref(crs: Any) -> dict[str, Any]:
    epsg = crs.to_epsg(min_confidence=100)
    if epsg is not None:
        return {"epsg": int(epsg)}
    return {"epsg": None, "wkt": crs.to_wkt()}


def crs_record(crs: Any, name: str = "") -> dict[str, Any]:
    """The DC-004-03 `crs_record` of a pyproj CRS: EPSG codes (or WKT), units and their factors to metres."""
    subs = list(crs.sub_crs_list) if crs.is_compound else [crs]
    horizontal = next((s for s in subs if s.is_projected), None)
    vertical = next((s for s in subs if s.is_vertical), None)
    if horizontal is None:
        raise SceneStageError("crs-mismatch", f"{name}: the horizontal CRS is not projected (metres or feet required)")
    if vertical is None:
        raise SceneStageError("crs-mismatch", f"{name}: no vertical CRS in the file metadata")
    h_unit = _unit_record(horizontal.axis_info[0].unit_conversion_factor, "horizontal", name)
    v_unit = _unit_record(vertical.axis_info[0].unit_conversion_factor, "vertical", name)
    return {
        "horizontal": _ref(horizontal),
        "vertical": _ref(vertical),
        "horizontal_unit": h_unit,
        "vertical_unit": v_unit,
    }


def _describe(rec: dict[str, Any]) -> str:
    h, v = rec["horizontal"], rec["vertical"]
    return f"horizontal {h['epsg'] if h.get('epsg') else 'WKT'} / vertical {v['epsg'] if v.get('epsg') else 'WKT'}"


def check_crs_consistency(records: dict[str, dict[str, Any]], transformations: list[Any] | None = None) -> None:
    """Fail with `crs-mismatch` when two inputs differ in horizontal or vertical CRS (FR-004-11).

    `records` maps an input name to its CRS record. A difference is accepted only when the SceneSpec declares a
    transformation step (`terrain.transformations`).
    """
    if transformations:
        return
    items = list(records.items())
    if not items:
        return
    first_name, first = items[0]
    for name, rec in items[1:]:
        for part in ("horizontal", "vertical"):
            a, b = first[part], rec[part]
            same = (a.get("epsg") is not None and a["epsg"] == b.get("epsg")) or (
                a.get("epsg") is None and b.get("epsg") is None and a.get("wkt") == b.get("wkt")
            )
            if not same:
                raise SceneStageError(
                    "crs-mismatch",
                    f"{part} CRS differs: {first_name} has {_describe(first)}, {name} has {_describe(rec)}",
                )


# ----------------------------------------------------------------------------------------------------------------
# readers
# ----------------------------------------------------------------------------------------------------------------
def _corrupt(source_id: str, path: Path, why: str) -> SceneStageError:
    return SceneStageError("input-corrupt", scrub(f"{source_id or 'input'} {Path(path).name}: {why}", path))


def _check_digest(path: Path, source_id: str, expected: str | None) -> None:
    if expected is not None and sha256_file(path) != expected:
        raise _corrupt(source_id, path, "SHA-256 differs from the data registry entry")


def _pyproj_crs(wkt: str | None, name: str) -> Any:
    import pyproj

    if not wkt:
        raise SceneStageError("crs-mismatch", f"{name}: the file has no CRS")
    return pyproj.CRS.from_wkt(wkt)


def read_dem_metadata(path: Path | str) -> dict[str, Any]:
    """Header-only read: CRS record, extent in source units and cell size; never reads pixels."""
    import rasterio

    path = Path(path)
    try:
        with rasterio.open(path) as ds:
            wkt = ds.crs.to_wkt() if ds.crs else None
            transform = ds.transform
            width, height = ds.width, ds.height
            nodata = ds.nodata
    except Exception as error:
        raise _corrupt("", path, f"cannot open the GeoTIFF ({type(error).__name__})") from error
    return {
        "crs": crs_record(_pyproj_crs(wkt, path.name), path.name),
        "wkt": wkt,
        "x_min": float(transform.c),
        "y_max": float(transform.f),
        "cell_x": float(transform.a),
        "cell_y": float(-transform.e),
        "width": int(width),
        "height": int(height),
        "nodata": None if nodata is None else float(nodata),
    }


def read_laz_metadata(path: Path | str) -> dict[str, Any]:
    """Header-only read of a LAS/LAZ tile: CRS record, bounding box and declared point count; never reads points."""
    import laspy

    path = Path(path)
    try:
        with laspy.open(path) as reader:
            header = reader.header
            crs = header.parse_crs()
            mins = [float(v) for v in header.mins]
            maxs = [float(v) for v in header.maxs]
            count = int(header.point_count)
    except Exception as error:
        raise _corrupt("", path, f"cannot open the LAZ header ({type(error).__name__})") from error
    if crs is None:
        raise SceneStageError("crs-mismatch", f"{path.name}: the file has no CRS record")
    return {"crs": crs_record(crs, path.name), "mins": mins, "maxs": maxs, "point_count": count}


def read_dem(path: Path | str, *, source_id: str = "", expected_sha256: str | None = None) -> DemTile:
    """Read a GeoTIFF DEM; `input-corrupt` when it cannot be decoded or its SHA-256 differs (FR-004-10)."""
    import rasterio

    path = Path(path)
    _check_digest(path, source_id, expected_sha256)
    try:
        with rasterio.open(path) as ds:
            if ds.count < 1:
                raise ValueError("no band")
            array = ds.read(1).astype(np.float64)
            wkt = ds.crs.to_wkt() if ds.crs else None
            transform = ds.transform
            nodata = ds.nodata
    except SceneStageError:
        raise
    except Exception as error:
        raise _corrupt(source_id, path, f"the GeoTIFF cannot be decoded ({type(error).__name__})") from error
    return DemTile(
        array=array,
        x_min=float(transform.c),
        y_max=float(transform.f),
        cell_x=float(transform.a),
        cell_y=float(-transform.e),
        nodata=None if nodata is None else float(nodata),
        crs=crs_record(_pyproj_crs(wkt, path.name), path.name),
        name=path.name,
    )


def read_laz(path: Path | str, *, source_id: str = "", expected_sha256: str | None = None) -> LazTile:
    """Read a LAS/LAZ tile with the CRS of its WKT record; `input-corrupt` on any decoding or header defect."""
    import laspy

    path = Path(path)
    _check_digest(path, source_id, expected_sha256)
    try:
        with laspy.open(path) as reader:
            header = reader.header
            declared = int(header.point_count)
            crs = header.parse_crs()
            las = reader.read()
        if len(las.points) != declared:
            raise ValueError(f"{len(las.points)} points read, {declared} declared in the header")
        x, y, z = (
            np.asarray(las.x, dtype=np.float64),
            np.asarray(las.y, dtype=np.float64),
            np.asarray(las.z, dtype=np.float64),
        )
        classification = np.asarray(las.classification, dtype=np.uint8)
    except Exception as error:
        raise _corrupt(source_id, path, f"the LAZ file cannot be decoded ({type(error).__name__}: {error})") from error
    if crs is None:
        raise SceneStageError("crs-mismatch", f"{path.name}: the file has no CRS record")
    return LazTile(x=x, y=y, z=z, classification=classification, crs=crs_record(crs, path.name), name=path.name)


# ----------------------------------------------------------------------------------------------------------------
# job inputs
# ----------------------------------------------------------------------------------------------------------------
def resolve_input(path: Path | str, *, roots: list[Path | str], sha256: str | None) -> Path:
    """The resolved path of a job input; `input-path` outside every root, `input-corrupt` on a digest mismatch
    (FR-004-14).

    The location is checked first and nothing is read before both checks pass. `..` segments, UNC paths, another
    drive and
    links that leave the roots are refused.
    """
    text = str(path)
    name = re.split(r"[\\/]", text.rstrip("\\/"))[-1] or "input"
    if text.startswith(("\\\\", "//")) or ".." in re.split(r"[\\/]", text):
        raise SceneStageError("input-path", f"{name}: the path uses a UNC prefix or '..' segments")
    resolved = Path(text).resolve()
    allowed = [Path(r).resolve() for r in roots]
    if not any(resolved == r or r in resolved.parents for r in allowed):
        raise SceneStageError("input-path", f"{name}: the path resolves outside the store and the data root")
    if not resolved.is_file():
        raise SceneStageError("input-corrupt", f"{name}: the input file does not exist")
    if sha256 is not None and sha256_file(resolved) != sha256:
        raise SceneStageError("input-corrupt", f"{name}: SHA-256 differs from the job specification")
    return resolved

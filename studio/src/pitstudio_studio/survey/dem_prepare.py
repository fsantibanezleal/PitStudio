"""DEM grid preparation: CRS, vertical datum, RMSEz, bilinear reprojection onto the 2023 grid, datum mismatch
(FR-017-31, FR-017-32).

The metadata of a DEM is read from its GDAL dataset tags VERTICAL_DATUM, GEOID, RMSEZ_M and PROJECT_NAME. A real 3DEP
GeoTIFF carries none of them, so the recipe may name `dem_metadata` for an epoch ("2018" or "2023", or
`epoch_2018`): its fields fill
only what the file lacks, and the record says which fields came from the recipe and from what source. A field that
neither the file nor the recipe gives stays `None` and is never guessed.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

EM_DASH = "—"
DATUM_LABEL = f"Not run {EM_DASH} vertical datums differ"


@dataclass(frozen=True)
class DemInfo:
    z: np.ndarray  # float64 (ny, nx), north-up as stored, NaN for no data
    transform: tuple[float, float, float, float, float, float]
    crs: str
    vertical_datum: str | None
    geoid: str | None
    rmse_z_m: float | None
    project: str | None
    sha256: str


@dataclass
class PrepareResult:
    status: str  # "ok" | "not_run"
    label: str | None
    before: DemInfo | None
    after: DemInfo | None
    record: dict | None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _crs_string(crs: Any) -> str:
    epsg = crs.to_epsg()
    if epsg is None:  # a compound CRS (horizontal + vertical): the horizontal part names the grid
        from pyproj import CRS

        subs = CRS.from_wkt(crs.to_wkt()).sub_crs_list
        epsg = subs[0].to_epsg() if subs else None
    if epsg is None:
        raise ValueError("the DEM has no EPSG horizontal CRS")
    return f"EPSG:{epsg}"


def _number(text: Any) -> float | None:
    try:
        value = float(text)
    except TypeError, ValueError:
        return None
    return value if math.isfinite(value) else None


def read_dem(path: Path, *, fallback: Mapping[str, Any] | None = None) -> DemInfo:
    """Read the first band (no data as NaN), the affine, the horizontal CRS, the tags and the SHA-256 of the file."""
    import rasterio

    path = Path(path)
    with rasterio.open(path) as ds:
        if ds.crs is None:
            raise ValueError(f"{path.name} has no CRS")
        z = ds.read(1, masked=True).astype(np.float64).filled(np.nan)
        tags = ds.tags()
        t = tuple(float(v) for v in tuple(ds.transform)[:6])
        crs = _crs_string(ds.crs)
    fb = dict(fallback or {})

    def pick(tag: str, key: str) -> Any:
        return tags[tag] if tags.get(tag) else fb.get(key)

    rmse = pick("RMSEZ_M", "rmse_z_m")
    return DemInfo(
        z=z,
        transform=t,  # type: ignore[arg-type]
        crs=crs,
        vertical_datum=pick("VERTICAL_DATUM", "vertical_datum"),
        geoid=pick("GEOID", "geoid"),
        rmse_z_m=_number(rmse),
        project=pick("PROJECT_NAME", "project"),
        sha256=_sha256(path),
    )


def _declared_transform(recipe: Mapping[str, Any]) -> dict | None:
    """The recipe's vertical transform when it is complete: a finite constant or a grid, and a non-blank source."""
    vt = recipe.get("vertical_transform")
    if not isinstance(vt, Mapping):
        return None
    source = vt.get("source")
    if not isinstance(source, str) or not source.strip():
        return None
    if vt.get("kind") == "constant":
        offset = vt.get("offset_m")
        if isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset):
            return None
        return dict(vt)
    if vt.get("kind") == "grid" and isinstance(vt.get("path"), str) and vt["path"]:
        return dict(vt)
    return None


def _sample_bilinear(src: DemInfo, dst_transform: tuple, dst_crs: str, shape: tuple[int, int]) -> np.ndarray:
    """Point-sampled bilinear interpolation of a geographic grid at the cell centres of the target grid.

    GDAL's approximate transformer and kernel scaling displace cells by a fraction of a source pixel, which is a metre
    of height on a steep 30 m DEM; sampling at the exact centres is exact for a plane. A no-data neighbour gives
    no data.
    """
    from affine import Affine
    from pyproj import Transformer
    from scipy.ndimage import map_coordinates

    a, _b, c, _d, e, f = dst_transform
    xs = c + (np.arange(shape[1]) + 0.5) * a
    ys = f + (np.arange(shape[0]) + 0.5) * e
    gx, gy = np.meshgrid(xs, ys)
    lon, lat = Transformer.from_crs(dst_crs, src.crs, always_xy=True).transform(gx, gy)
    col, row = (~Affine(*src.transform)) @ (lon, lat)
    out = map_coordinates(src.z, [row - 0.5, col - 0.5], order=1, mode="constant", cval=np.nan, prefilter=False)
    return np.asarray(out, dtype=np.float64)


def _is_geographic(crs: str) -> bool:
    from pyproj import CRS

    return CRS.from_user_input(crs).is_geographic


def _resample(src: DemInfo, dst_transform: tuple, dst_crs: str, shape: tuple[int, int]) -> np.ndarray:
    if _is_geographic(src.crs) and not _is_geographic(dst_crs):
        return _sample_bilinear(src, dst_transform, dst_crs, shape)
    from affine import Affine
    from rasterio.warp import Resampling, reproject

    out = np.full(shape, np.nan, dtype=np.float64)
    reproject(
        source=src.z,
        destination=out,
        src_transform=Affine(*src.transform),
        src_crs=src.crs,
        dst_transform=Affine(*dst_transform),
        dst_crs=dst_crs,
        resampling=Resampling.bilinear,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    return out


def prepare_pair(path_2018: Path, path_2023: Path, *, recipe: Mapping[str, Any]) -> PrepareResult:
    """Both DEMs on the 2023 grid with a recorded transform, or "not run" when the vertical datums differ."""
    meta = recipe.get("dem_metadata") or {}
    # a YAML recipe cannot name a key "2018" (recipe parameter names start with a letter): `epoch_2018` is accepted too
    # `before` and `after` name the two DEMs by role (the older one is stored under the record key 2018)
    d18 = read_dem(path_2018, fallback=meta.get("before") or meta.get("2018") or meta.get("epoch_2018"))
    d23 = read_dem(path_2023, fallback=meta.get("after") or meta.get("2023") or meta.get("epoch_2023"))
    declared = _declared_transform(recipe)
    differ = (d18.vertical_datum, d18.geoid) != (d23.vertical_datum, d23.geoid)
    if differ and declared is None:
        return PrepareResult("not_run", DATUM_LABEL, None, None, None)
    same_grid = d18.transform == d23.transform and d18.crs == d23.crs and d18.z.shape == d23.z.shape
    z18 = d18.z if same_grid else _resample(d18, d23.transform, d23.crs, d23.z.shape)
    if declared is not None:
        if declared["kind"] == "constant":
            z18 = z18 + float(declared["offset_m"])
        else:
            grid = read_dem(Path(declared["path"]))
            if grid.z.shape != d23.z.shape or grid.transform != d23.transform:
                raise ValueError("the declared vertical grid is not on the 2023 grid")
            z18 = z18 + grid.z
    before = DemInfo(z18, d23.transform, d23.crs, d18.vertical_datum, d18.geoid, d18.rmse_z_m, d18.project, d18.sha256)
    record = {
        "crs": d23.crs,
        "transform": d23.transform,
        "resampling": "none" if same_grid else "bilinear",
        "sha256_2018": d18.sha256,
        "sha256_2023": d23.sha256,
        "project_2018": d18.project,
        "project_2023": d23.project,
        "vertical_datum_2018": d18.vertical_datum,
        "vertical_datum_2023": d23.vertical_datum,
        "geoid_2018": d18.geoid,
        "geoid_2023": d23.geoid,
        "rmse_z_2018_m": d18.rmse_z_m,
        "rmse_z_2023_m": d23.rmse_z_m,
        "source_crs_2018": d18.crs,
        "vertical_transform": declared,
        "metadata_from_recipe": {k: sorted(v) for k, v in meta.items() if isinstance(v, Mapping)},
    }
    return PrepareResult("ok", None, before, d23, record)

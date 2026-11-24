"""The coarse E2 pair: an old geographic DEM (SRTM GL1, February 2000, EGM96 heights) against a 1 m lidar DEM in UTM
(NAVD88 heights) aggregated to a 30 m grid (FR-017-30..34).

Steps: the lidar DEM is block-averaged onto a UTM grid of the cell size of the recipe (cells with less than the minimum
valid coverage are no data); the datum grid (NAVD88 height minus EGM96 height, from the PROJ grids us_nga_egm96_15 and
us_noaa_g2018u0 unless the caller passes its own function) is written on the same grid; `run_e2` then resamples the old
DEM bilinearly onto that grid, applies the declared grid transform and differences the pair over each area. A
stable-ground
check (cells farther than a minimum distance from an area of interest) gives the mean and standard deviation of the
difference, and the sigma of the old DEM in the bounds is the larger of its nominal figure and that measured standard
deviation, combined with the lidar RMSEz by the formula of FR-017-33.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_studio.survey.dem_prepare import prepare_pair
from pitstudio_studio.survey.real_run import _footprint, run_e2

OffsetFn = Callable[[np.ndarray, np.ndarray, str], np.ndarray]


def navd88_minus_egm96(x: np.ndarray, y: np.ndarray, crs: str) -> np.ndarray:
    """Height of NAVD88 minus height of EGM96 (metres) at points of `crs`, from the PROJ grids of NGA and NOAA.

    The pipeline is EGM96 height (WGS 84) to NAVD88 height (NAD83(2011)) through GEOID18 (`us_noaa_g2018u0`); the grids
    are fetched from the PROJ network on first use. A point outside the GEOID18 area is NaN.
    """
    import pyproj
    from pyproj import Transformer

    pyproj.network.set_network_enabled(True)
    to_geo = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    lon, lat = to_geo.transform(x, y)
    vert = Transformer.from_crs("EPSG:4326+5773", "EPSG:6318+5703", always_xy=True)
    _, _, h = vert.transform(lon, lat, np.zeros_like(np.asarray(lon, dtype=float)))
    h = np.asarray(h, dtype=np.float64)
    h[~np.isfinite(h)] = np.nan
    return h


def _write_tif(path: Path, z: np.ndarray, transform: Any, crs: str) -> Path:
    import rasterio

    profile = {
        "driver": "GTiff", "height": z.shape[0], "width": z.shape[1], "count": 1, "dtype": "float32",
        "crs": crs, "transform": transform, "nodata": -999999.0,
    }  # fmt: skip
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.where(np.isfinite(z), z, -999999.0).astype(np.float32), 1)
    return path


def aggregate_dem(dem: Path, transform: Any, crs: str, shape: tuple[int, int], min_coverage: float) -> np.ndarray:
    """Block mean of the valid cells of `dem` on the target grid; NaN where the valid share is below `min_coverage`."""
    import rasterio
    from rasterio.warp import Resampling, reproject

    with rasterio.open(dem) as ds:
        z = ds.read(1, masked=True)
        valid = (~np.ma.getmaskarray(z)).astype(np.float32)
        filled = np.where(valid > 0, z.filled(0.0), 0.0).astype(np.float32)
        kw = {"src_transform": ds.transform, "src_crs": ds.crs, "dst_transform": transform, "dst_crs": crs}
        mean_v = np.zeros(shape, dtype=np.float32)
        cover = np.zeros(shape, dtype=np.float32)
        # mean of the valid cells = mean of (value x valid) over mean of valid, both averaged over the same footprint
        reproject(filled * valid, mean_v, resampling=Resampling.average, **kw)
        reproject(valid, cover, resampling=Resampling.average, **kw)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(cover >= max(min_coverage, 1e-6), mean_v / cover, np.nan)
    return out.astype(np.float64)


def _grid(dem: Path, cell: float) -> tuple[Any, tuple[int, int], str]:
    """A UTM grid of `cell` metres over the valid bounding box of `dem`, on multiples of the cell size."""
    import rasterio
    from rasterio.transform import from_origin

    with rasterio.open(dem) as ds:
        crs = f"EPSG:{ds.crs.to_epsg()}"
        m = ds.read(1, masked=True)
        rows, cols = np.nonzero(~np.ma.getmaskarray(m))
        t = ds.transform
        x0 = t.c + cols.min() * t.a
        x1 = t.c + (cols.max() + 1) * t.a
        y1 = t.f + rows.min() * t.e
        y0 = t.f + (rows.max() + 1) * t.e
    gx0, gy1 = math.floor(x0 / cell) * cell, math.ceil(y1 / cell) * cell
    nx, ny = math.ceil((x1 - gx0) / cell), math.ceil((gy1 - y0) / cell)
    return from_origin(gx0, gy1, cell, cell), (ny, nx), crs


def _stable_stats(
    before: np.ndarray, after: np.ndarray, transform: tuple, footprint: np.ndarray, distance: float
) -> dict:
    """Mean, sd and median of after minus before on valid cells farther than `distance` from the footprint."""
    import shapely
    from shapely.geometry import Polygon

    a, _, c, _, e, f = transform
    ny, nx = after.shape
    xs = c + (np.arange(nx) + 0.5) * a
    ys = f + (np.arange(ny) + 0.5) * e
    gx, gy = np.meshgrid(xs, ys)
    near = shapely.contains_xy(Polygon(footprint).buffer(distance), gx.ravel(), gy.ravel()).reshape(after.shape)
    d = (after - before)[~near & np.isfinite(after) & np.isfinite(before)]
    if d.size < 2:
        raise ValueError("no stable-ground cell farther than the minimum distance from the area of interest")
    return {
        "mean_m": float(np.mean(d)),
        "sd_m": float(np.std(d, ddof=1)),
        "median_m": float(np.median(d)),
        "n_cells": int(d.size),
        "min_distance_m": float(distance),
    }


def run_coarse(
    out_dir: Path,
    *,
    srtm: Path,
    dem: Path,
    recipe: Mapping[str, Any],
    scratch: Path,
    offset_fn: OffsetFn | None = None,
    data_root: Path | None = None,
) -> dict:
    """Build the coarse grid and the datum grid, measure the stable ground, then run the E2 differencing."""
    scratch = Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    cell = float(recipe["grid"]["cell_m"])
    transform, shape, crs = _grid(dem, cell)
    coarse = aggregate_dem(dem, transform, crs, shape, float(recipe["grid"].get("min_coverage", 0.95)))
    t6 = tuple(float(v) for v in tuple(transform)[:6])
    coarse_path = _write_tif(scratch / "dem-coarse.tif", coarse, transform, crs)
    xs = t6[2] + (np.arange(shape[1]) + 0.5) * t6[0]
    ys = t6[5] + (np.arange(shape[0]) + 0.5) * t6[4]
    gx, gy = np.meshgrid(xs, ys)
    offset = (offset_fn or navd88_minus_egm96)(gx, gy, crs)
    offset_path = _write_tif(
        scratch / "datum-navd88-minus-egm96.tif", np.asarray(offset, dtype=np.float64), transform, crs
    )
    vt = {
        "kind": "grid",
        "path": str(offset_path),
        "source": recipe.get(
            "datum_source",
            "height of NAVD88 minus height of EGM96 from the PROJ grids us_nga_egm96_15 (EGM96, NGA) and "
            "us_noaa_g2018u0 "
            "(GEOID18, NOAA), evaluated at the cell centres",
        ),
    }
    meta = copy.deepcopy(dict(recipe["dem_metadata"]))
    prep_recipe = {"dem_metadata": meta, "vertical_transform": vt}
    prep = prepare_pair(srtm, coarse_path, recipe=prep_recipe)
    if prep.status != "ok" or prep.before is None or prep.after is None:
        sigma = float(recipe.get("srtm_rmse_nominal_m", 0.0))
        stable = None
    else:
        areas = {a["id"]: a for a in recipe["areas"]}
        sg = recipe["stable_ground"]
        footprint, _ = _footprint(areas[sg["area"]], data_root)
        stable = _stable_stats(
            prep.before.z, prep.after.z, prep.after.transform, footprint, float(sg["min_distance_m"])
        )
        sigma = max(float(recipe.get("srtm_rmse_nominal_m", 0.0)), stable["sd_m"])
    meta["before"]["rmse_z_m"] = sigma
    e2_recipe = {**recipe, "dem_metadata": meta, "vertical_transform": vt}
    summary = run_e2(Path(out_dir), path_2018=srtm, path_2023=coarse_path, recipe=e2_recipe, data_root=data_root)
    summary.update(
        {
            "stable_ground": stable,
            "sigma_srtm_m": sigma,
            "coarse_cell_m": cell,
            "dem_source_sha256": hashlib.sha256(Path(dem).read_bytes()).hexdigest(),
            "datum_grid_range_m": [float(np.nanmin(offset)), float(np.nanmax(offset))],
        }
    )
    (Path(out_dir) / "e2-run.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8", newline="\n")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    import yaml

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("recipe", type=Path, help="a recipe YAML: the params of its first stage are the run parameters")
    p.add_argument("out_dir", type=Path)
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--scratch", type=Path, required=True)
    a = p.parse_args(argv)
    doc = yaml.safe_load(a.recipe.read_text(encoding="utf-8"))
    recipe = doc["stages"][0]["params"] if "stages" in doc else doc
    summary = run_coarse(
        a.out_dir,
        srtm=a.data_root / recipe["srtm"],
        dem=a.data_root / recipe["dem"],
        recipe=recipe,
        scratch=a.scratch,
        data_root=a.data_root,
    )
    print(
        json.dumps(
            {k: summary[k] for k in ("status", "stable_ground", "sigma_srtm_m", "volumes") if k in summary}, indent=1
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

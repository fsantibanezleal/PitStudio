"""Generate the committed scene fixtures under tests/fixtures/scene/ (T-004-003); seeded, so they can be rebuilt.

Usage:  uv run --project studio --frozen python tools/make_scene_fixtures.py [--out DIR]
Writes (all under 1 MB in total):
  dem_utm12_m.tif       129 x 129 cells, 1 m, NAD83 / UTM 12N + NAVD88 height (metres)
  dem_utm12_ftus.tif    the same terrain in US survey feet, horizontal and vertical
  dem_nad83_2011.tif    the same terrain in NAD83(2011) / UTM 12N: a CRS-mismatched copy
  dem_truncated.tif     the first half of dem_utm12_m.tif: a corrupt DEM
  tile_a.laz, tile_b.laz   LAS 1.4 tiles of 10,000 points each (ground class 2 and others), side by side
  tile_bad_header.laz   tile_a.laz with a corrupt file signature
  pit_outline.json      a circular pit outline (radius 40 m, 180 vertices) in the site frame
The site origin is the one of the contract example (UTM 12N, easting 406500, northing 4484500, elevation 1800 m).
Exit:   0 written, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

SEED = 20261007
E0, N0, Z0 = 406500.0, 4484500.0, 1800.0
FT_US = 1200 / 3937
CELLS = 129


def terrain(n: int, rng: np.random.Generator) -> np.ndarray:
    """A smooth 129 x 129 height field (m above the origin elevation): two hills, a ridge and a little noise."""
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    z = 12.0 * np.exp(-(((xx - 40) ** 2 + (yy - 50) ** 2) / 600.0))
    z += 9.0 * np.exp(-(((xx - 95) ** 2 + (yy - 85) ** 2) / 450.0))
    z += 0.06 * (xx - 64) + 2.0 * np.sin(yy / 11.0)
    return z + rng.normal(0.0, 0.05, z.shape)


def write_dem(path: Path, heights: np.ndarray, *, x_min: float, y_max: float, cell: float, wkt: str) -> None:
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import from_origin

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=heights.shape[0],
        width=heights.shape[1],
        count=1,
        dtype="float32",
        crs=CRS.from_wkt(wkt),
        transform=from_origin(x_min, y_max, cell, cell),
        nodata=-9999.0,
        compress="deflate",
    ) as dst:
        dst.write(heights.astype("float32"), 1)


def write_laz(path: Path, x0: float, rng: np.random.Generator, n: int = 10_000) -> None:
    import laspy
    import pyproj

    x = x0 + rng.uniform(0.0, 64.0, n)
    y = N0 + rng.uniform(0.0, 128.0, n)
    z = Z0 + 5.0 + 0.05 * (x - x0) + rng.normal(0.0, 0.02, n)
    classification = rng.choice([1, 2, 2, 2, 2, 6], n).astype(np.uint8)
    header = laspy.LasHeader(point_format=6, version="1.4")
    header.offsets = np.array([math.floor(x.min()), math.floor(y.min()), math.floor(z.min())])
    header.scales = np.array([0.001, 0.001, 0.001])
    header.add_crs(pyproj.CRS.from_user_input("EPSG:26912+5703"))
    las = laspy.LasData(header)
    las.x, las.y, las.z = x, y, z
    las.classification = classification
    las.write(str(path))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "scene"))
    args = parser.parse_args(argv[1:])
    import pyproj

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    heights = Z0 + terrain(CELLS, rng)
    wkt_m = pyproj.CRS.from_user_input("EPSG:26912+5703").to_wkt()
    write_dem(out / "dem_utm12_m.tif", heights, x_min=E0, y_max=N0 + CELLS, cell=1.0, wkt=wkt_m)
    horizontal = pyproj.CRS.from_proj4("+proj=utm +zone=12 +datum=NAD83 +units=us-ft +no_defs")
    compound = pyproj.crs.CompoundCRS(
        name="UTM12N ftUS + NAVD88 ftUS", components=[horizontal, pyproj.CRS.from_epsg(6360)]
    )
    write_dem(
        out / "dem_utm12_ftus.tif",
        heights / FT_US,
        x_min=E0 / FT_US,
        y_max=(N0 + CELLS) / FT_US,
        cell=1.0 / FT_US,
        wkt=compound.to_wkt(),
    )
    write_dem(
        out / "dem_nad83_2011.tif",
        heights,
        x_min=E0,
        y_max=N0 + CELLS,
        cell=1.0,
        wkt=pyproj.CRS.from_user_input("EPSG:6341+5703").to_wkt(),
    )
    good = (out / "dem_utm12_m.tif").read_bytes()
    (out / "dem_truncated.tif").write_bytes(good[: len(good) // 2])
    write_laz(out / "tile_a.laz", E0, rng)
    write_laz(out / "tile_b.laz", E0 + 64.0, rng)
    broken = bytearray((out / "tile_a.laz").read_bytes())
    broken[0:4] = b"XXXX"
    (out / "tile_bad_header.laz").write_bytes(bytes(broken))
    ring = [
        [round(40.0 * math.cos(2 * math.pi * k / 180), 6), round(40.0 * math.sin(2 * math.pi * k / 180), 6)]
        for k in range(180)
    ]
    (out / "pit_outline.json").write_text(
        json.dumps({"vertices_xy_m": ring}, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    total = sum(p.stat().st_size for p in out.iterdir() if p.is_file())
    print(f"wrote {len(list(out.iterdir()))} files, {total} bytes, to {out.name}")
    return 0 if total <= 1_000_000 else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

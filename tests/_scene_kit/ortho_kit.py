# ruff: noqa: E501
"""Hand-written inputs of the orthophoto albedo and terrain ortho material tests (T-004-097, T-004-098).

The orthophoto fixtures are linear colour ramps over the site frame, so every expected pixel is a hand calculation, never
the code under test: with the site origin (E0, N0) a pixel centre at (E, N) holds `R = 60 + 2 (E - E0)`,
`G = 120 + 3 (N - N0)`, `B = 40` (and a fourth band, near-infrared, of 255 that must never reach the albedo). A bilinear
resample of a linear function is exact at every point inside the image, up to the 8-bit rounding of the source pixels.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402

SRC = "usgs-3dep-bingham"
IMG = "usda-naip-bingham"
E0, N0 = kit.E0, kit.N0


def ramp(east_m: np.ndarray, north_m: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The colour of the ramp at site-frame offsets (metres east and north of the origin)."""
    return 60.0 + 2.0 * east_m, 120.0 + 3.0 * north_m, np.full_like(east_m, 40.0)


def write_ortho(
    path: Path,
    *,
    x_min: float,
    y_max: float,
    cell: float,
    rows: int,
    cols: int,
    wkt: str | None = None,
    colour: Callable[[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray, np.ndarray]] | None = None,
    to_site: Callable[[np.ndarray], np.ndarray] | None = None,
    bands: int = 4,
) -> Path:
    """A uint8 GeoTIFF (R, G, B and, for `bands` 4, a near-infrared band of 255); `x_min`, `y_max` in the file's CRS.

    `colour(east_m, north_m)` gives the three colour bands from site-frame offsets of the pixel centres; `to_site` converts
    file-CRS coordinates to metres when the file is not in metres (default: the identity).
    """
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import from_origin

    colour = colour or ramp
    to_site = to_site or (lambda v: v)
    xs = x_min + (np.arange(cols) + 0.5) * cell
    ys = y_max - (np.arange(rows) + 0.5) * cell
    east = np.broadcast_to(to_site(xs)[None, :] - E0, (rows, cols))
    north = np.broadcast_to(to_site(ys)[:, None] - N0, (rows, cols))
    planes = [np.clip(np.rint(b), 0, 255).astype(np.uint8) for b in colour(east, north)]
    if bands == 4:
        planes.append(np.full((rows, cols), 255, dtype=np.uint8))
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=len(planes),
        dtype="uint8",
        crs=CRS.from_wkt(wkt or kit.crs_wkt("utm12-horizontal-only")),
        transform=from_origin(x_min, y_max, cell, cell),
    ) as dst:
        for index, plane in enumerate(planes, start=1):
            dst.write(plane, index)
    return Path(path)


def naip_name(year: int, quad: str = "4011231_se") -> str:
    """A file name in the NAIP form `m_<quad>_12_060_<yyyymmdd>.tif` (the acquisition date is part of the name)."""
    return f"m_{quad}_12_060_{year}0909.tif"


def dem_job(
    tmp: Path,
    monkeypatch,
    images: list[Path],
    *,
    width: int = 12,
    height: int = 12,
    epoch: int = 2018,
    imagery: list[dict] | None = None,
) -> dict:
    """A `st10_terrain` job over a flat DEM of `width` x `height` cells of 1 m at the site origin, with `images` as inputs."""
    store, data = tmp / "store", tmp / "data"
    store.mkdir(exist_ok=True)
    data.mkdir(exist_ok=True)
    monkeypatch.setenv("PITSTUDIO_STORE", str(store))
    monkeypatch.setenv("PITSTUDIO_DATA", str(data))
    z = kit.Z0 + np.zeros((height, width), dtype=np.float64)
    dem = kit.write_dem(
        data / "dem.tif", z, x_min=E0, y_max=N0 + height, cell=1.0, wkt=kit.crs_wkt("utm12-m")
    )
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, float(width), float(height))
    spec["terrain"]["sources"][0]["epoch"] = epoch
    spec["terrain"]["imagery"] = imagery if imagery is not None else [{"id": IMG, "kind": "orthophoto", "optional": False}]
    for path in images:
        if Path(path).parent != data:
            (data / Path(path).name).write_bytes(Path(path).read_bytes())
    inputs = [(SRC, dem), *((IMG, data / Path(p).name) for p in images)]
    return kit.make_job(store, "st10_terrain", spec, inputs)


def year_of(name: str) -> int:
    match = re.search(r"_(\d{4})\d{4}\.tif$", name)
    assert match, name
    return int(match.group(1))

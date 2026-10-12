"""The terrain stage `st10_terrain`: DEM or LAZ inputs to the site-local grid, tiles and USD layer (FR-004-01 ..
FR-004-15)."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from pitstudio_studio.scene import common
from pitstudio_studio.scene.common import SceneStageError, StageContext, StageRun
from pitstudio_studio.scene.terrain import frame, grid
from pitstudio_studio.scene.terrain import io as terrain_io

if TYPE_CHECKING:
    from pitstudio_studio.scene.terrain.sources import SourceStatus

CHUNK = 512  # Zarr chunk edge of the terrain grid arrays (DC-004-03)


@dataclass
class TerrainGrid:
    """The site-local terrain grid of one source (DC-004-03): float32 elevation (NaN = nodata), masks and attributes."""

    elevation: np.ndarray
    valid_mask: np.ndarray
    fill_mask: np.ndarray
    cell_size_m: float
    x_min_m: float
    y_max_m: float
    rows: int
    cols: int
    crs: dict[str, Any]
    counts: dict[str, int]
    nodata_frac: float
    attrs: dict[str, Any]
    fixture: bool
    source_id: str
    project: str = ""
    epoch: int = 0

    @property
    def elevation_sha256(self) -> str:
        return common.sha256_bytes(np.ascontiguousarray(self.elevation, dtype="<f4").tobytes())


@dataclass
class TerrainBuild:
    """The outcome of `build_terrain`: the status of every listed source and the grid of each source that ran."""

    sources: list[SourceStatus]
    grids: dict[str, TerrainGrid] = field(default_factory=dict)


@dataclass
class SiteName:
    name: str
    provisional: bool
    confirmation: dict[str, Any] | None


# ----------------------------------------------------------------------------------------------------------------
# checks
# ----------------------------------------------------------------------------------------------------------------
def check_terrain_sources(spec: Mapping[str, Any]) -> None:
    """Reject two LAZ projects for one terrain grid (one grid per source id) before any point is read (FR-004-42)."""
    seen: dict[str, str] = {}
    for source in spec["terrain"]["sources"]:
        if source.get("kind") != "laz":
            continue
        sid, project = source["id"], source["project"]
        if sid in seen and seen[sid] != project:
            raise SceneStageError(
                "terrain-source-ambiguous", f"grid {sid} lists two LAZ projects: {seen[sid]!r} and {project!r}"
            )
        seen.setdefault(sid, project)


def confirm_site_name(
    name: str, *, aoi_xy_m: Sequence[Sequence[float]], mine_polygons_xy_m: Mapping[str, Sequence[Sequence[float]]]
) -> SiteName:
    """The site name with " (provisional)" unless a mine polygon has at least 90 % of its area inside the AOI
    (FR-004-15)."""
    from shapely.geometry import Polygon

    aoi = Polygon([(float(x), float(y)) for x, y in aoi_xy_m])
    best: tuple[float, str] | None = None
    for dataset, ring in mine_polygons_xy_m.items():
        try:
            poly = Polygon([(float(x), float(y)) for x, y in ring])
        except ValueError:
            continue
        if len(ring) < 3 or not poly.is_valid or poly.area <= 0.0:
            continue
        overlap = poly.intersection(aoi).area / poly.area
        if overlap >= 0.9 - 1e-12 and (best is None or overlap > best[0]):
            best = (float(overlap), dataset)
    if best is None:
        return SiteName(f"{name} (provisional)", True, None)
    return SiteName(name, False, {"source": best[1], "overlap_frac": best[0]})


# ----------------------------------------------------------------------------------------------------------------
# extents
# ----------------------------------------------------------------------------------------------------------------
def _site_extent(
    xs: Sequence[float], ys: Sequence[float], crs: Mapping[str, Any], origin: Mapping[str, Any]
) -> tuple[float, ...]:
    e, n, _ = frame.site_frame(np.asarray(xs), np.asarray(ys), np.zeros(len(xs)), crs=crs, origin=origin)
    return (float(e.min()), float(n.min()), float(e.max()), float(n.max()))


def _dem_extent(meta: Mapping[str, Any], origin: Mapping[str, Any]) -> tuple[float, ...]:
    x0, y1 = meta["x_min"], meta["y_max"]
    x1, y0 = x0 + meta["width"] * meta["cell_x"], y1 - meta["height"] * meta["cell_y"]
    return _site_extent([x0, x1, x0, x1], [y0, y0, y1, y1], meta["crs"], origin)


def _laz_extent(meta: Mapping[str, Any], origin: Mapping[str, Any]) -> tuple[float, ...]:
    (x0, y0), (x1, y1) = meta["mins"][:2], meta["maxs"][:2]
    return _site_extent([x0, x1, x0, x1], [y0, y0, y1, y1], meta["crs"], origin)


# ----------------------------------------------------------------------------------------------------------------
# building one grid
# ----------------------------------------------------------------------------------------------------------------
def _sample_dem(
    tile: Any, xs: np.ndarray, ys: np.ndarray, origin: Mapping[str, Any], out: np.ndarray, counts: dict[str, int]
) -> None:
    """Fill the still-empty cells of `out` (site elevation, NaN = none) with the DEM sample under each cell centre."""
    cx, cy = np.meshgrid(xs, ys)
    sx, sy = frame.to_source(cx, cy, crs=tile.crs, origin=origin)
    col = np.floor((sx - tile.x_min) / tile.cell_x)
    row = np.floor((tile.y_max - sy) / tile.cell_y)
    h, w = tile.array.shape
    inside = (col >= 0) & (col < w) & (row >= 0) & (row < h) & np.isnan(out)
    if not inside.any():
        return
    raw = tile.array[row[inside].astype(np.int64), col[inside].astype(np.int64)]
    factor = float(tile.crs["vertical_unit"]["factor_to_m"])
    nodata_m = None if tile.nodata is None else tile.nodata * factor
    clean = grid.sanitise_elevations(raw * factor, nodata_m=nodata_m)
    counts["rejected_non_finite"] += clean.rejected_non_finite
    counts["rejected_sentinel"] += clean.rejected_sentinel
    counts["rejected_out_of_range"] += clean.rejected_out_of_range
    out[inside] = clean.values - float(origin["z0_m"])


def _grid_from_laz(
    tiles_: list[Any],
    shape: tuple[int, int, float, float],
    cell: float,
    origin: Mapping[str, Any],
    counts: dict[str, int],
) -> np.ndarray:
    rows, cols, x_min, y_max = shape
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    zs: list[np.ndarray] = []
    cl: list[np.ndarray] = []
    for tile in tiles_:
        factor = float(tile.crs["vertical_unit"]["factor_to_m"])
        clean = grid.sanitise_elevations(tile.z * factor)
        counts["rejected_non_finite"] += clean.rejected_non_finite
        counts["rejected_out_of_range"] += clean.rejected_out_of_range
        keep = ~np.isnan(clean.values)
        east, north, _ = frame.site_frame(tile.x[keep], tile.y[keep], tile.z[keep], crs=tile.crs, origin=origin)
        xs.append(east)
        ys.append(north)
        zs.append(clean.values[keep] - float(origin["z0_m"]))
        cl.append(tile.classification[keep])
    return grid.grid_ground_points(
        np.concatenate(xs),
        np.concatenate(ys),
        np.concatenate(zs),
        np.concatenate(cl),
        x_min=x_min,
        y_max=y_max,
        rows=rows,
        cols=cols,
        cell_size_m=cell,
    )


def _array_record(array: np.ndarray, dtype: str, unit: str | None) -> dict[str, Any]:
    rows, cols = array.shape
    data = np.ascontiguousarray(array, dtype="<f4" if dtype == "float32" else np.uint8)
    record: dict[str, Any] = {
        "dtype": dtype,
        "shape": [rows, cols],
        "chunk_shape": [min(CHUNK, rows), min(CHUNK, cols)],
        "sha256": common.sha256_bytes(data.tobytes()),
    }
    if unit:
        record["unit"] = unit
    return {k: record[k] for k in ("dtype", "unit", "shape", "chunk_shape", "sha256") if k in record}


def _build_grid(spec: Mapping[str, Any], source: Mapping[str, Any], files: Sequence[Path]) -> TerrainGrid:
    tspec = spec["terrain"]
    origin = spec["site"]["origin"]
    cell = float(tspec["cell_size_m"])
    kind = source["kind"]
    sid = source["id"]
    # header-only pass: CRS records and extents, before any pixel or point is read
    records: dict[str, dict[str, Any]] = {}
    metas: list[dict[str, Any]] = []
    for path in files:
        meta = terrain_io.read_dem_metadata(path) if kind == "dem" else terrain_io.read_laz_metadata(path)
        records[Path(path).name] = meta["crs"]
        metas.append(meta)
    terrain_io.check_crs_consistency(records, tspec.get("transformations"))
    extents = [(_dem_extent if kind == "dem" else _laz_extent)(m, origin) for m in metas]
    poly = grid.check_aoi(tspec["aoi_xy_m"], cell_size_m=cell, max_cells=int(tspec["max_cells"]), extents_xy_m=extents)
    rows, cols, x_min, y_max = grid.grid_shape(poly, cell)
    inside = grid.aoi_mask(poly, rows, cols, x_min, y_max, cell)

    counts = {"rejected_non_finite": 0, "rejected_sentinel": 0, "rejected_out_of_range": 0}
    if kind == "dem":
        tiles_ = [terrain_io.read_dem(p, source_id=sid) for p in files]
        elevation = np.full((rows, cols), np.nan)
        xs = x_min + (np.arange(cols) + 0.5) * cell
        ys = y_max - (np.arange(rows) + 0.5) * cell
        for tile in tiles_:
            _sample_dem(tile, xs, ys, origin, elevation, counts)
        method, input_kind = "dem-crop", "dem"
        crs = tiles_[0].crs
    else:
        laz = [terrain_io.read_laz(p, source_id=sid) for p in files]
        elevation = _grid_from_laz(laz, (rows, cols, x_min, y_max), cell, origin, counts)
        method, input_kind = "laz-ground-mean", "laz"
        crs = laz[0].crs
    elevation[~inside] = np.nan
    filled = grid.fill_holes(elevation, max_fill_cells=int(tspec["max_fill_cells"]), domain=inside)
    valid = np.isfinite(filled.elevation) & inside
    n_inside = int(inside.sum())
    nodata_cells = int((inside & ~valid).sum())
    frac = nodata_cells / n_inside if n_inside else 1.0
    if frac > float(tspec["max_nodata_frac"]):
        raise SceneStageError(
            "too-much-nodata",
            f"nodata fraction {frac:.4f} inside the AOI after hole filling exceeds {tspec['max_nodata_frac']}",
        )
    site_z = np.where(valid, filled.elevation, np.nan)
    elev32 = site_z.astype(np.float32)
    fixture = bool(spec.get("fixture", False))
    counts_out = {
        "valid_cells": int(valid.sum()),
        "filled_cells": int(filled.fill_mask.sum()),
        "nodata_cells": nodata_cells,
        "unfilled_holes": int(filled.unfilled_holes),
        "rejected_non_finite": counts["rejected_non_finite"],
        "rejected_sentinel": counts["rejected_sentinel"],
        "rejected_out_of_range": counts["rejected_out_of_range"],
    }
    z_valid = site_z[valid]
    attrs: dict[str, Any] = {
        "schema_version": "1.0",
        "kind": "terrain-grid",
        "frame": "site-enu",
        "layout": "north-up",
        "up_axis": "Z",
        "horizontal_unit": "m",
        "vertical_unit": "m",
        "cell_size_m": cell,
        "rows": rows,
        "cols": cols,
        "x_min_m": float(x_min),
        "y_max_m": float(y_max),
        "origin": dict(origin),
        "crs": crs,
        "input_kind": input_kind,
        "method": method,
        "source_ids": [sid],
        "project": source["project"],
        "epoch": int(source["epoch"]),
        "arrays": {
            "elevation": _array_record(elev32, "float32", "m"),
            "valid_mask": _array_record(valid, "bool", None),
            "fill_mask": _array_record(filled.fill_mask, "bool", None),
        },
        "counts": counts_out,
        "nodata_frac": frac,
        "max_fill_cells": int(tspec["max_fill_cells"]),
        "elevation_range_m": {"min": float(z_valid.min()), "max": float(z_valid.max())},
        "source_elevation_range_m": {
            "min": float(z_valid.min() + origin["z0_m"]),
            "max": float(z_valid.max() + origin["z0_m"]),
        },
        "fixture": fixture,
    }
    if method == "laz-ground-mean":
        attrs["ground_classes"] = [grid.GROUND_CLASS]
    return TerrainGrid(
        elevation=elev32,
        valid_mask=valid,
        fill_mask=filled.fill_mask,
        cell_size_m=cell,
        x_min_m=float(x_min),
        y_max_m=float(y_max),
        rows=rows,
        cols=cols,
        crs=crs,
        counts={**counts_out, "unfilled_cells": int(filled.unfilled_cells)},
        nodata_frac=frac,
        attrs=attrs,
        fixture=fixture,
        source_id=sid,
        project=source["project"],
        epoch=int(source["epoch"]),
    )


def _first_source(spec: Mapping[str, Any], source_id: str | None) -> Mapping[str, Any]:
    for source in spec["terrain"]["sources"]:
        if source_id is None or source["id"] == source_id:
            return source  # type: ignore[no-any-return]
    raise SceneStageError("input-corrupt", f"source {source_id} is not listed in the scene specification")


def build_terrain_grid(
    spec: Mapping[str, Any], inputs: Mapping[str, Sequence[Path | str]], *, source_id: str | None = None
) -> TerrainGrid:
    """The site-local terrain grid of a source (the first listed one unless `source_id` is given); see `_build_grid`.

    The rules run in the order of the spec: ambiguity, CRS records from headers, AOI, then the pixel or point readers.
    """
    check_terrain_sources(spec)
    source = _first_source(spec, source_id)
    files = [Path(p) for p in inputs.get(source["id"], [])]
    if not files:
        raise SceneStageError("input-corrupt", f"no input files for source {source['id']}")
    return _build_grid(spec, source, files)


def build_terrain(
    spec: Mapping[str, Any], inputs: Mapping[str, Sequence[Path | str]], *, env: Mapping[str, str] | None = None
) -> TerrainBuild:
    """Build the grid of every source that runs; an unavailable optional source is `not_run` and the rest completes."""
    from pitstudio_studio.scene.terrain import sources

    check_terrain_sources(spec)
    statuses = sources.resolve_sources(spec, env=env, available=inputs)
    build = TerrainBuild(sources=statuses)
    for source, status in zip(spec["terrain"]["sources"], statuses, strict=True):
        if status.status == "used":
            build.grids[source["id"]] = _build_grid(spec, source, [Path(p) for p in inputs[source["id"]]])
        elif not source.get("optional"):
            raise SceneStageError("input-corrupt", f"required source {source['id']}: {status.reason}")
    return build


# ----------------------------------------------------------------------------------------------------------------
# Zarr store and stage
# ----------------------------------------------------------------------------------------------------------------
def write_grid_zarr(grid_: TerrainGrid, path: Path) -> None:
    """Write the grid as a Zarr v3 group (attributes DC-004-03; arrays elevation, valid_mask, fill_mask), one shard
    per array."""
    import zarr

    root = zarr.open_group(store=str(path), mode="w", zarr_format=3, attributes=grid_.attrs)
    for name, array, dtype, fill in (
        ("elevation", grid_.elevation, "float32", float("nan")),
        ("valid_mask", grid_.valid_mask, "bool", False),
        ("fill_mask", grid_.fill_mask, "bool", False),
    ):
        chunks = (min(CHUNK, grid_.rows), min(CHUNK, grid_.cols))
        shards = (-(-grid_.rows // chunks[0]) * chunks[0], -(-grid_.cols // chunks[1]) * chunks[1])
        arr = root.create_array(name, shape=array.shape, chunks=chunks, shards=shards, dtype=dtype, fill_value=fill)
        arr[:] = array


def _dump(doc: Any) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _body(ctx: StageContext) -> str:
    from pitstudio_studio.scene.terrain import sources, tiles, usd

    spec = ctx.params
    roots = common.job_roots()
    if not roots:
        raise SceneStageError("input-path", "no store or data root is configured for the job inputs")
    files: dict[str, list[Path]] = {}
    for name, items in ctx.inputs.items():
        files[name] = [terrain_io.resolve_input(it["path"], roots=roots, sha256=it.get("sha256")) for it in items]
    env = dict(os.environ)
    built = build_terrain(spec, files, env=env)
    primary_id = spec["terrain"]["sources"][0]["id"]
    primary = built.grids[primary_id]
    registry = sources.load_registry()
    source_records = [
        sources.source_record(src, status, registry)
        for src, status in zip(spec["terrain"]["sources"], built.sources, strict=True)
    ]
    work = ctx.work
    grid_dir = work / "terrain" / "grid.zarr"
    write_grid_zarr(primary, grid_dir)
    for sid, extra in built.grids.items():
        if sid != primary_id:
            write_grid_zarr(extra, work / "terrain" / "optional" / sid / "grid.zarr")
    tileset = tiles.build_tiles(
        primary.elevation,
        cell_size_m=primary.cell_size_m,
        x_min_m=primary.x_min_m,
        y_max_m=primary.y_max_m,
        lods=spec["terrain"]["lods"],
        fixture=primary.fixture,
    )
    primary_record = next(r for r in source_records if r["id"] == primary_id)
    (work / "layers").mkdir(parents=True, exist_ok=True)
    usd.write_terrain_layer(
        work / "layers" / "terrain.usdc",
        tileset,
        source_id=primary_id,
        project=primary.project,
        epoch=primary.epoch,
        attribution=primary_record["attribution"],
    )
    tiles_path = work / "terrain" / "tiles.json"
    tiles_path.write_text(
        _dump(tileset.document(primary.elevation_sha256, "layers/terrain.usdc")), encoding="utf-8", newline="\n"
    )
    site = confirm_site_name(spec["site"]["name"], aoi_xy_m=spec["terrain"]["aoi_xy_m"], mine_polygons_xy_m={})
    input_records = [
        {
            "source": name,
            "file": f"{name}/{Path(item['path']).name}",
            "kind": next(s["kind"] for s in spec["terrain"]["sources"] if s["id"] == name),
            "sha256": item["sha256"],
            "crs": primary.crs,
        }
        for name, items in ctx.inputs.items()
        for item in items
    ]
    records = {
        "fixture": primary.fixture,
        "sources": source_records,
        "inputs": input_records,
        "terrain": {
            "grid": {"path": "terrain/grid.zarr/zarr.json", "sha256": common.sha256_file(grid_dir / "zarr.json")},
            "tiles": {"path": "terrain/tiles.json", "sha256": common.sha256_file(tiles_path)},
            "cell_size_m": primary.cell_size_m,
            "unfilled_holes": primary.counts["unfilled_holes"],
            "unfilled_cells": primary.counts["unfilled_cells"],
            "nodata_frac": primary.nodata_frac,
        },
        "site": {
            "name": site.name,
            "provisional": site.provisional,
            "confirmation": site.confirmation,
            "origin": dict(spec["site"]["origin"]),
        },
    }
    (work / "terrain" / "records.json").write_text(_dump(records), encoding="utf-8", newline="\n")
    return f"terrain {primary.rows} x {primary.cols} cells, {len(tileset.tiles)} tiles"


def run(job: Mapping[str, Any]) -> StageRun:
    """The stage entry `pitstudio_studio.scene.terrain`: job spec in, stage result out (see `common.run_stage`)."""
    return common.run_stage(job, _body)

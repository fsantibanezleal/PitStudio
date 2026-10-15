"""The pit-design stage `st20_pit_design`: benches, ramp, windrows, carving, report and road network (FR-004-16 ..
23)."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_studio.scene import common
from pitstudio_studio.scene.common import DESIGN_LABEL, SceneStageError, StageContext, StageRun
from pitstudio_studio.scene.design import benches as benches_mod
from pitstudio_studio.scene.design import ramp as ramp_mod
from pitstudio_studio.scene.design import roads
from pitstudio_studio.scene.design import windrows as windrow_mod
from pitstudio_studio.scene.design.checks import check_outline, check_parameters

SHOULDER_M = 2.0  # the ramp surface extends this far beyond its width on each side: the windrows stand on it


@dataclass
class DesignResult:
    """What the design stage produces (see `build_design`)."""

    benches: list[benches_mod.Bench]
    ramp: ramp_mod.Ramp | None
    windrows: list[windrow_mod.Windrow]
    z_design: np.ndarray
    windrow_mask: np.ndarray
    z_final: np.ndarray
    report: dict[str, Any]
    road_network: dict[str, Any] | None
    bench_roads: list[np.ndarray] = field(default_factory=list)
    outline: Any = None


def _mask(geometry: Any, shape: tuple[int, int], x_min: float, y_max: float, cell: float) -> np.ndarray:
    """Cells whose centre lies inside `geometry`."""
    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    out = rasterize(
        [(geometry, 1)], out_shape=shape, transform=from_origin(x_min, y_max, cell, cell), fill=0, dtype="uint8"
    )
    return out.astype(bool)


def _bench_surface(
    bench_list: Sequence[benches_mod.Bench],
    tan_alpha: float,
    xx: np.ndarray,
    yy: np.ndarray,
    masks: list[tuple[Any, Any]],
) -> np.ndarray:
    """The bench design surface: flat berm and floor levels, linear faces by distance from the crest."""
    import shapely

    z = np.full(xx.shape, np.nan)
    for bench, (m_crest, m_toe) in zip(bench_list, masks, strict=True):
        z[m_crest] = bench.toe_z
        band = m_crest & ~m_toe
        if band.any():
            height = bench.crest_z - bench.toe_z
            run = height / tan_alpha
            dist = shapely.distance(shapely.points(xx[band], yy[band]), bench.crest.exterior)
            z[band] = bench.crest_z - height * np.minimum(dist / run, 1.0)
    return z


def _stamp_ramp(
    z: np.ndarray, ramp: ramp_mod.Ramp, xx_axis: np.ndarray, yy_axis: np.ndarray, cell: float
) -> np.ndarray:
    """The ramp strip: for every cell within half the ramp width of the centreline, the elevation of the nearest
    sample."""
    rows, cols = z.shape
    best = np.full(z.shape, np.inf)
    level = np.full(z.shape, np.nan)
    half = float(ramp.width_m.min()) / 2.0 + SHOULDER_M
    x0, y0 = float(xx_axis[0]), float(yy_axis[0])
    reach = math.ceil(half / cell) + 1
    for x, y, h in ramp.centreline:
        c = round((x - x0) / cell)
        r = round((y0 - y) / cell)
        r0, r1, c0, c1 = max(r - reach, 0), min(r + reach + 1, rows), max(c - reach, 0), min(c + reach + 1, cols)
        if r0 >= r1 or c0 >= c1:
            continue
        d2 = (xx_axis[None, c0:c1] - x) ** 2 + (yy_axis[r0:r1, None] - y) ** 2
        better = (d2 < best[r0:r1, c0:c1]) & (d2 <= half * half)
        best[r0:r1, c0:c1] = np.where(better, d2, best[r0:r1, c0:c1])
        level[r0:r1, c0:c1] = np.where(better, h, level[r0:r1, c0:c1])
    return level


def _windrow_mask(
    wr: Sequence[windrow_mod.Windrow], shape: tuple[int, int], x_min: float, y_max: float, cell: float
) -> np.ndarray:
    import shapely

    mask = np.zeros(shape, dtype=bool)
    for w in wr:
        distances = np.arange(0.0, w.line.length + cell / 2.0, cell / 2.0)
        xy = shapely.get_coordinates(shapely.line_interpolate_point(w.line, distances))
        col = np.floor((xy[:, 0] - x_min) / cell).astype(np.int64)
        row = np.floor((y_max - xy[:, 1]) / cell).astype(np.int64)
        ok = (col >= 0) & (col < shape[1]) & (row >= 0) & (row < shape[0])
        mask[row[ok], col[ok]] = True
    return mask


def _measure(
    bench_list: Sequence[benches_mod.Bench],
    z_bench: np.ndarray,
    masks: list[tuple[Any, Any]],
    rim_ring: np.ndarray,
    terrain: np.ndarray,
    angle_deg: float,
    cell: float,
) -> list[dict[str, Any]]:
    """Measured crest/toe elevation, height, face angle and berm width of every bench on the design raster
    (FR-004-19)."""
    slope = np.hypot(*np.gradient(z_bench, cell))
    last = len(bench_list) - 1
    rows: list[dict[str, Any]] = []
    previous_toe = None
    for k, bench in enumerate(bench_list):
        m_crest, m_toe = masks[k]
        berm = m_toe & ~masks[k + 1][0] if k < last else m_toe
        toe_z = float(np.median(z_bench[berm])) if berm.any() else bench.toe_z
        if k == 0:
            ring = terrain[rim_ring & np.isfinite(terrain)]
            crest_z = float(np.median(ring)) if ring.size else bench.crest_z
        else:
            crest_z = previous_toe
        band = m_crest & ~m_toe
        inner = np.zeros_like(band)
        inner[1:-1, 1:-1] = band[1:-1, 1:-1] & band[:-2, 1:-1] & band[2:, 1:-1] & band[1:-1, :-2] & band[1:-1, 2:]
        values = slope[inner & np.isfinite(slope)]
        angle = math.degrees(math.atan(float(np.median(values)))) if values.size else angle_deg
        width = None
        if k < last:
            area = float(berm.sum()) * cell * cell
            mean_perimeter = 0.5 * (bench.toe.length + bench_list[k + 1].crest.length)
            width = area / mean_perimeter
        rows.append(
            {
                "index": bench.index,
                "crest_z_m": crest_z,
                "toe_z_m": toe_z,
                "height_m": crest_z - toe_z,
                "face_angle_deg": angle,
                "berm_width_m": width,
                "crest_perimeter_m": float(bench.crest.length),
            }
        )
        previous_toe = toe_z
    return rows


def _bench_roads(bench_list: Sequence[benches_mod.Bench], ramp: ramp_mod.Ramp, berm_width: float) -> list[np.ndarray]:
    """One level road along the middle of every berm, branching from the ramp where it passes the berm elevation."""
    import shapely
    from shapely.geometry import LinearRing, Point

    roads_out: list[np.ndarray] = []
    centre = ramp.centreline
    for k in range(len(bench_list) - 1):
        berm_ring = bench_list[k].toe.buffer(-berm_width / 2.0, join_style="mitre", mitre_limit=benches_mod.MITRE_LIMIT)
        if berm_ring.is_empty or berm_ring.geom_type != "Polygon":
            continue
        i = int(np.argmin(np.abs(centre[:, 2] - bench_list[k].toe_z)))
        if i == 0 or i == len(centre) - 1:
            continue
        start = centre[i]
        ring = LinearRing(berm_ring.exterior.coords)
        arc = ring.project(Point(start[0], start[1]))
        length = min(0.5 * ring.length, 300.0)
        distances = (arc + np.arange(0.0, length + 1e-9, 1.0)) % ring.length
        xy = shapely.get_coordinates(shapely.line_interpolate_point(ring, distances))
        road = np.vstack([start, np.column_stack([xy, np.full(len(xy), start[2])])])
        roads_out.append(road)
    return roads_out


def build_design(
    grid: Any,
    spec: Mapping[str, Any],
    *,
    outline_xy: Sequence[Sequence[float]],
    include_ramp: bool = True,
    include_windrows: bool = True,
) -> DesignResult:
    """Generate and carve the pit design of a terrain grid (FR-004-16 .. FR-004-23).

    `grid` needs `elevation` (float [rows, cols], row 0 north), `x_min_m`, `y_max_m` and `cell_size_m`; `spec` is a
    SceneSpec dict (its `design`, `assets` and `fleet` blocks are used). Inside the outline `z_final` is
    `min(z_terrain, z_design)` plus the windrow height on windrow cells; outside it equals the terrain.
    """

    design = spec["design"]
    values = check_parameters(design)
    poly = check_outline(outline_xy, ramp_width_m=values["ramp_width_m"], grid=grid)
    rim_z, floor_z = float(design["rim_z_m"]), float(design["floor_z_m"])
    bench_list = benches_mod.generate_benches(
        outline_xy,
        bench_height_m=values["bench_height_m"],
        face_angle_deg=values["face_angle_deg"],
        berm_width_m=values["berm_width_m"],
        rim_z_m=rim_z,
        floor_z_m=floor_z,
    )
    requirement = windrow_mod.windrow_requirement(spec["assets"], spec["fleet"], values["windrow_height_m"])
    if include_windrows and requirement.height_m < requirement.mid_axle_height_m:
        raise SceneStageError(
            "design-infeasible",
            f"windrow_height_m={requirement.height_m} is below the mid-axle height {requirement.mid_axle_height_m} m "
            f"of {requirement.governing_asset} (30 CFR 56.9300(b))",
        )
    ramp = (
        ramp_mod.generate_ramp(
            bench_list,
            ramp_grade_pct=values["ramp_grade_pct"],
            ramp_width_m=values["ramp_width_m"],
            rim_z_m=rim_z,
            floor_z_m=floor_z,
        )
        if include_ramp
        else None
    )
    wr = (
        windrow_mod.place_windrows(
            bench_list, ramp, height_m=values["windrow_height_m"], ramp_width_m=values["ramp_width_m"]
        )
        if include_windrows
        else []
    )
    terrain = np.asarray(grid.elevation)
    rows, cols = terrain.shape
    cell = float(grid.cell_size_m)
    x_min, y_max = float(grid.x_min_m), float(grid.y_max_m)
    x_axis = x_min + (np.arange(cols) + 0.5) * cell
    y_axis = y_max - (np.arange(rows) + 0.5) * cell
    xx, yy = np.meshgrid(x_axis, y_axis)
    shape = (rows, cols)
    masks = [(_mask(b.crest, shape, x_min, y_max, cell), _mask(b.toe, shape, x_min, y_max, cell)) for b in bench_list]
    inside = masks[0][0]
    tan_alpha = math.tan(math.radians(values["face_angle_deg"]))
    z_bench = _bench_surface(bench_list, tan_alpha, xx, yy, masks)
    z_design = z_bench.copy()
    if ramp is not None:
        level = _stamp_ramp(z_design, ramp, x_axis, y_axis, cell)
        strip = np.isfinite(level) & inside
        z_design[strip] = level[strip]
    z_design[~inside] = np.nan
    windrow_mask = _windrow_mask(wr, shape, x_min, y_max, cell) & inside
    zt = terrain.astype(np.float64)
    carved = np.fmin(zt, z_design) + np.where(windrow_mask, values["windrow_height_m"], 0.0)
    z_final = np.where(inside, carved, zt).astype(np.float32)
    zf = z_final.astype(np.float64)
    d = np.where(np.isfinite(zt) & np.isfinite(zf), zt - zf, 0.0)
    area = cell * cell
    cut, fill, carved_sum = (
        float(np.maximum(d, 0).sum() * area),
        float(np.maximum(-d, 0).sum() * area),
        float(d.sum() * area),
    )
    ring_mask = _mask(poly.buffer(3.0 * cell), shape, x_min, y_max, cell) & ~inside
    measured = _measure(bench_list, z_bench, masks, ring_mask, zt, values["face_angle_deg"], cell)
    widened = set(ramp.widened_bench_indices) if ramp is not None else set()
    for row in measured:
        row["widened_for_ramp"] = row["index"] in widened
    fixture = bool(getattr(grid, "fixture", False))
    outline_source = design.get("outline_source", "rim-contour")
    outline_block: dict[str, Any] = {
        "source": outline_source,
        "vertices": len(outline_xy),
        "area_m2": float(poly.area),
        "perimeter_m": float(poly.length),
        "rim_z_m": rim_z,
        "floor_z_m": floor_z,
    }
    if outline_source == "upstream-shell":
        outline_block["shell_sha256"] = common.sha256_bytes(json.dumps(np.asarray(outline_xy).tolist()).encode())
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "kind": "pit-design-report",
        "provenance": "design-code",
        "label": DESIGN_LABEL,
        "terrain_grid_sha256": common.sha256_bytes(np.ascontiguousarray(grid.elevation, dtype="<f4").tobytes()),
        "parameters": {key: values[key] for key in benches_mod_keys()},
        "outline": outline_block,
        "benches": measured,
        "windrows": {
            "height_m": requirement.height_m,
            "mid_axle_height_m": requirement.mid_axle_height_m,
            "governing_asset": requirement.governing_asset,
        },
        "volumes": {
            "cut_m3": cut,
            "fill_m3": fill,
            "carved_sum_m3": carved_sum,
            "cell_area_m2": area,
            "identity_residual_rel": abs(cut - fill - carved_sum) / max(cut, fill, 1.0),
        },
        "fixture": fixture,
    }
    network = None
    bench_roads: list[np.ndarray] = []
    if ramp is not None:
        centre = ramp.centreline
        steps = np.hypot(np.diff(centre[:, 0]), np.diff(centre[:, 1]))
        grades = 100.0 * np.abs(np.diff(centre[:, 2])) / np.maximum(steps, 1e-12)
        report["ramp"] = {
            "length_m": ramp.length_m,
            "max_grade_pct": float(grades.max()),
            "min_width_m": float(ramp.width_m.min()),
            "sample_spacing_m": ramp.sample_spacing_m,
            "connected": bool(steps.max() <= ramp.sample_spacing_m + 1e-9),
        }
        bench_roads = _bench_roads(bench_list, ramp, values["berm_width_m"])
        network = roads.build_road_network(centre, bench_roads, origin=spec["site"]["origin"])
        network["fixture"] = fixture
    return DesignResult(
        benches=bench_list,
        ramp=ramp,
        windrows=wr,
        z_design=z_design,
        windrow_mask=windrow_mask,
        z_final=z_final,
        report=report,
        road_network=network,
        bench_roads=bench_roads,
        outline=poly,
    )


def benches_mod_keys() -> tuple[str, ...]:
    return (
        "bench_height_m",
        "face_angle_deg",
        "berm_width_m",
        "ramp_grade_pct",
        "ramp_width_m",
        "windrow_height_m",
    )


# ----------------------------------------------------------------------------------------------------------------
# stage
# ----------------------------------------------------------------------------------------------------------------
class _ZarrGrid:
    """The terrain grid read back from the Zarr store of `st10_terrain` (duck-typed for `build_design`)."""

    def __init__(self, path: Path) -> None:
        import zarr

        group = zarr.open_group(store=str(path), mode="r")
        self.elevation = np.asarray(group["elevation"][:], dtype=np.float32)
        attrs = dict(group.attrs)
        self.cell_size_m = float(attrs["cell_size_m"])
        self.x_min_m = float(attrs["x_min_m"])
        self.y_max_m = float(attrs["y_max_m"])
        self.fixture = bool(attrs.get("fixture", False))


def _body(ctx: StageContext) -> str:
    from pitstudio_studio.scene.design import outline as outline_mod
    from pitstudio_studio.scene.design import usd as design_usd
    from pitstudio_studio.scene.terrain import io as terrain_io

    spec = ctx.params
    roots = common.job_roots()
    if not roots:
        raise SceneStageError("input-path", "no store or data root is configured for the job inputs")
    items = ctx.inputs.get("terrain-grid", [])
    if not items:
        raise SceneStageError("input-corrupt", "the job has no `terrain-grid` input")
    grid_path = terrain_io.resolve_input(items[0]["path"], roots=roots, sha256=None).parent
    grid = _ZarrGrid(grid_path)
    if spec.get("fixture"):
        grid.fixture = True
    shell = ctx.inputs.get("outline")
    if shell:
        ring = json.loads(
            terrain_io.resolve_input(shell[0]["path"], roots=roots, sha256=shell[0].get("sha256")).read_text("utf-8")
        )
        outline_xy = ring["coordinates"][0][:-1] if isinstance(ring, dict) else ring
    else:
        design = spec["design"]
        outline_xy = outline_mod.rim_contour(
            grid.elevation,
            x_min_m=grid.x_min_m,
            y_max_m=grid.y_max_m,
            cell_size_m=grid.cell_size_m,
            rim_z_m=float(design["rim_z_m"]),
        )
    result = build_design(grid, spec, outline_xy=outline_xy)
    (ctx.work / "layers").mkdir(parents=True, exist_ok=True)
    (ctx.work / "design").mkdir(parents=True, exist_ok=True)
    design_usd.write_design_layer(ctx.work / "layers" / "design.usda", result, rel_path="layers/design.usda")
    (ctx.work / "design" / "pit-design-report.json").write_text(
        json.dumps(result.report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (ctx.work / "design" / "road-network.geojson").write_text(
        json.dumps(result.road_network, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return f"{len(result.benches)} benches, cut {result.report['volumes']['cut_m3']:.0f} m3"


def run(job: Mapping[str, Any]) -> StageRun:
    """The stage entry `pitstudio_studio.scene.design`: job spec in, stage result out (see `common.run_stage`)."""
    return common.run_stage(job, _body)

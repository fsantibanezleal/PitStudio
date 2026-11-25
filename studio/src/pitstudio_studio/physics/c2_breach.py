"""Case C2: tailings breach runs over the Bingham Canyon terrain with the Warp shallow-water solver (spec 005,
FR-005-30,
FR-005-31; spec 018, FR-018-16; spec 020, DC-020-05).

Usage: python -m pitstudio_studio.physics.c2_breach RECIPE.yaml OUT_DIR --data-root DIR [--device cpu|cuda:0]
           [--benchmarks FILE] [--dry-run]

The params of the first stage of the recipe name the terrain window, the cell size, the hypothetical breach site
and the
scenarios (volume, hydrograph, rheology and their sources). The terrain is the 3DEP 2018 one-metre DEM
block-averaged to the
cell size. Each scenario is one `SweSimulation`; the maps, the front through time and the pit receptor are reduced to
chart-series files (DC-020-05) and a run summary. On a CUDA device the machine GPU lock and the thermal guard of the
reference-data generator are used (one GPU job at a time). `--dry-run` runs the same chain on the CPU at a coarse
cell and
a short time into OUT_DIR, to prove the chain before the queue job runs.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import warp as wp

from pitstudio_studio.physics.swe import Breach, SweParams, SweSimulation

MAX_CHART_BYTES = 524_288
RASTER_MAX = 200
SERVES = ["FR-018-16", "FR-005-30"]
LABEL = "synthetic breach scenario of a hypothetical facility on real terrain, not validated against real data"
GUARD_EVERY_S = 5.0


def _en_es(en: str, es: str) -> dict:
    return {"en": en, "es": es}


def producer() -> dict:
    return {
        "tool": "warp",
        "method": "depth-averaged shallow water, Rusanov flux with hydrostatic reconstruction, Bingham bed stress",
        "version": f"warp-{wp.__version__}-swe-1.0",
        "label": LABEL,
    }


# -- terrain -----------------------------------------------------
def prepare_terrain(dem: Path, window: Mapping[str, float], cell_m: float, min_coverage: float) -> dict[str, Any]:
    """Block-mean the DEM over `window` (UTM metres: x_min, x_max, y_min, y_max) to cells of `cell_m` metres.

    A cell needs at least `min_coverage` of valid fine cells; the few cells below it take the nearest valid value,
    and their
    number is reported. The array is [row, column] = [y, x] with row 0 at the south edge."""
    import rasterio
    from rasterio.windows import Window
    from scipy import ndimage

    with rasterio.open(dem) as r:
        t = r.transform
        if t.b != 0 or t.d != 0 or abs(t.a) != abs(t.e) or abs(t.a) != 1.0:
            raise ValueError("the C2 terrain expects a north-up one-metre DEM")
        k = round(cell_m)
        if k != cell_m or k < 1:
            raise ValueError("the cell size must be a whole number of metres")
        nx = int((window["x_max"] - window["x_min"]) // k)
        ny = int((window["y_max"] - window["y_min"]) // k)
        col0 = round(window["x_min"] - t.c)
        row0 = round(t.f - (window["y_min"] + ny * k))
        data = r.read(1, window=Window(col0, row0, nx * k, ny * k), masked=True).astype("float64")
    valid = ~np.ma.getmaskarray(data)
    filled = np.ma.filled(data, 0.0)
    blocks = filled.reshape(ny, k, nx, k)
    count = valid.reshape(ny, k, nx, k).sum(axis=(1, 3))
    mean = blocks.sum(axis=(1, 3)) / np.maximum(count, 1)
    ok = count >= min_coverage * k * k
    n_filled = int((~ok).sum())
    if n_filled:
        idx = ndimage.distance_transform_edt(~ok, return_distances=False, return_indices=True)
        mean = mean[tuple(idx)]
    z = mean[::-1].copy()  # row 0 is the south row
    return {
        "z": z,
        "x0": float(window["x_min"]),
        "y0": float(window["y_min"]),
        "cell_m": float(k),
        "cells_filled": n_filled,
        "shape": z.shape,
    }


def pit_mask(footprint: Path, origin_m: Sequence[float], terrain: Mapping[str, Any]) -> np.ndarray:
    """Cells whose centre lies inside the pit outline (a GeoJSON polygon in metres relative to `origin_m`)."""
    import shapely

    ring = json.loads(footprint.read_text(encoding="utf-8"))["coordinates"][0]
    poly = shapely.Polygon([(x + origin_m[0], y + origin_m[1]) for x, y in ring])
    ny, nx = terrain["shape"]
    c = terrain["cell_m"]
    xs = terrain["x0"] + (np.arange(nx) + 0.5) * c
    ys = terrain["y0"] + (np.arange(ny) + 0.5) * c
    gx, gy = np.meshgrid(xs, ys)
    return np.asarray(shapely.contains_xy(poly, gx, gy))


# -- one scenario ------------------------------------------------
def run_scenario(
    terrain: Mapping[str, Any],
    sc: Mapping[str, Any],
    run: Mapping[str, Any],
    pit: np.ndarray,
    device: str,
    guard: Any = None,
) -> dict[str, Any]:
    z = terrain["z"]
    ny, nx = z.shape
    c = terrain["cell_m"]
    bx, by = run["breach"]["x_m"], run["breach"]["y_m"]
    col = int((bx - terrain["x0"]) // c)
    row = int((by - terrain["y0"]) // c)
    half = int(run["breach"]["width_cells"]) // 2
    cells = [
        (r, q)
        for r in range(row - half, row - half + int(run["breach"]["width_cells"]))
        for q in range(col - half, col - half + int(run["breach"]["width_cells"]))
    ]
    q_peak = float(sc["peak_discharge_m3_s"])
    breach = Breach(cells=cells, volume=float(sc["volume_m3"]), peak_discharge=q_peak, peak_fraction=0.5)
    params = SweParams(
        rho=float(sc["rho_kg_m3"]),
        tau_y=float(sc["tau_y_pa"]),
        mu_b=float(sc["mu_b_pa_s"]),
        cfl=float(run.get("cfl", 0.45)),
        h_dry=float(run.get("h_dry_m", 1e-4)),
        h_thr=float(run.get("h_thr_m", 0.05)),
        max_dt=float(run.get("max_dt_s", 1.0)),
    )
    sides = {s: "open" for s in ("x-min", "x-max", "y-min", "y-max")}
    sim = SweSimulation(z, None, dx=c, params=params, boundaries=sides, breach=breach, device=device)
    t_end = float(run["t_end_s"])
    snap = float(run["snapshot_s"])
    xs = terrain["x0"] + (np.arange(nx) + 0.5) * c
    ys = terrain["y0"] + (np.arange(ny) + 0.5) * c
    dist = np.hypot(xs[None, :] - bx, ys[:, None] - by)
    cell_area = c * c
    series: list[dict[str, float]] = []
    last_guard = [time.perf_counter()]

    def between(_: SweSimulation) -> None:
        if guard is not None and time.perf_counter() - last_guard[0] >= GUARD_EVERY_S:
            guard()
            last_guard[0] = time.perf_counter()

    wall0 = time.perf_counter()
    k = 0
    while sim.time < t_end - 1e-9:
        k += 1
        sim.advance(min(k * snap, t_end), between=between)
        h = sim.h
        wet = h > params.h_thr
        series.append(
            {
                "t_s": sim.time,
                "wet_area_m2": float(wet.sum()) * cell_area,
                "front_distance_m": float(dist[wet].max()) if wet.any() else 0.0,
                "pit_volume_m3": float(h[pit].sum()) * cell_area,
                "domain_volume_m3": float(h.sum()) * cell_area,
            }
        )
    wall_s = time.perf_counter() - wall0
    maps = sim.maps()
    hmax = maps["max_depth_m"]
    arrival = maps["arrival_time_s"]
    near = dist <= float(run.get("depth_exclusion_m", 100.0))
    wet_max = hmax > params.h_thr
    pit_arrival = arrival[pit]
    pit_arrival = pit_arrival[np.isfinite(pit_arrival)]
    inside = float(pit_arrival.min()) / 60.0 if pit_arrival.size else None
    far_depth = hmax[~near]
    out_vol = sim.boundary_outflow()
    return {
        "id": sc["id"],
        "sim_time_s": sim.time,
        "steps": sim.steps,
        "wall_s": wall_s,
        "maps": maps,
        "dist": dist,
        "series": series,
        "kpi": {
            "arrival_time_pit_min": inside,
            "max_depth_beyond_exclusion_m": float(far_depth.max()),
            "max_depth_anywhere_m": float(hmax.max()),
            "inundated_area_km2": float(maps["inundated_area_m2"]) / 1e6,
            "run_out_m": float(dist[wet_max].max()) if wet_max.any() else 0.0,
            "pit_volume_end_m3": series[-1]["pit_volume_m3"],
            "max_speed_m_s": float(maps["max_speed_m_s"].max()),
        },
        "balance": {
            "injected_m3": sim.injected_volume(),
            "released_m3": breach.volume,
            "domain_m3": sim.volume(),
            "boundary_outflow_m3": out_vol,
            "clipped_m3": sim.clipped_volume(),
            "residual": sim.balance_residual(),
        },
        "breach_cells": len(cells),
        "breach_bed_m": float(z[row, col]),
    }


# -- chart-series files ------------------------------------------
def _chart(cid: str, ctype: str, title: dict, caption: dict | None, kpi: str | None, **body: Any) -> dict:
    doc: dict[str, Any] = {
        "schema_version": "1.0",
        "kind": "chart-series",
        "id": cid,
        "case": "C2",
        "chart_type": ctype,
        "status": "ok",
        "title": title,
        "producer": producer(),
        "serves": SERVES,
    }
    if caption:
        doc["caption"] = caption
    if kpi:
        doc["kpi"] = kpi
    doc.update(body)
    return doc


def _not_run(cid: str, ctype: str, title: dict, reason: dict) -> dict:
    return {
        "schema_version": "1.0",
        "kind": "chart-series",
        "id": cid,
        "case": "C2",
        "chart_type": ctype,
        "status": "not-run",
        "title": title,
        "producer": producer(),
        "serves": SERVES,
        "not_run_reason": reason,
    }


def _block(a: np.ndarray, k: int, how: str) -> np.ndarray:
    ny, nx = a.shape
    pad = ((0, (-ny) % k), (0, (-nx) % k))
    p = np.pad(a, pad, constant_values=np.nan)
    b = p.reshape(p.shape[0] // k, k, p.shape[1] // k, k)
    with np.errstate(all="ignore"):
        return np.nanmax(b, axis=(1, 3)) if how == "max" else np.nanmin(b, axis=(1, 3))


def _raster(
    terrain: Mapping[str, Any], a: np.ndarray, how: str, colormap: str, unit: str, label: dict, vmax: float
) -> dict:
    ny, nx = a.shape
    k = max(1, math.ceil(max(ny, nx) / RASTER_MAX))
    b = _block(a, k, how)[::-1]  # the first row of the file is the top (y1) row
    nyb, nxb = b.shape
    c = terrain["cell_m"] * k
    values = [None if not math.isfinite(v) else round(float(v), 3) for v in b.ravel()]
    return {
        "nx": nxb,
        "ny": nyb,
        "extent": {
            "x0": terrain["x0"],
            "x1": terrain["x0"] + nxb * c,
            "y0": terrain["y0"],
            "y1": terrain["y0"] + nyb * c,
        },
        "values": values,
        "colour": {"colormap": colormap, "vmin": 0.0, "vmax": round(vmax, 3), "unit": unit, "label": label},
    }


def _axes_en() -> dict:
    return {
        "x_axis": {"label": _en_es("Easting (UTM zone 12N)", "Este (UTM zona 12N)"), "unit": "m"},
        "y_axis": {"label": _en_es("Northing (UTM zone 12N)", "Norte (UTM zona 12N)"), "unit": "m"},
    }


def build_charts(
    run: Mapping[str, Any], scenarios: Sequence[Mapping[str, Any]], results: Sequence[Mapping[str, Any]],
    terrain: Mapping[str, Any], benchmarks: Mapping[str, Any] | None,
) -> dict[str, dict]:  # fmt: skip
    charts: dict[str, dict] = {}
    thr = float(run.get("h_thr_m", 0.05))
    label = lambda sc: _en_es(sc["label"], sc.get("label_es", sc["label"]))  # noqa: E731
    for sc, res in zip(scenarios, results, strict=True):
        sid = sc["id"]
        hmax = res["maps"]["max_depth_m"]
        shown = np.where(hmax > thr, hmax, np.nan)
        vmax = float(np.nanpercentile(shown, 99.0)) if np.isfinite(shown).any() else 1.0
        charts[f"c2-depth-map-{sid}"] = _chart(
            f"c2-depth-map-{sid}",
            "raster",
            _en_es(f"Maximum flow depth, {sc['label']}", f"Profundidad máxima del flujo, {sc['label_es']}"[:200]),
            _en_es(
                f"Largest depth reached in each cell over {run['t_end_s'] / 3600:.0f} h; "
                f"cells below {thr} m are blank; "
                f"blocks of {max(1, math.ceil(max(shown.shape) / RASTER_MAX))} cells keep the largest depth",
                f"Mayor profundidad alcanzada en cada celda en {run['t_end_s'] / 3600:.0f} h; las celdas bajo {thr} m "
                "quedan en blanco",
            ),
            "max_depth" if sid == run.get("headline_scenario") else None,
            **_axes_en(),
            raster=_raster(
                terrain, shown, "max", "viridis", "m", _en_es("Maximum depth", "Profundidad máxima"), max(vmax, thr)
            ),
        )
        arr_min = res["maps"]["arrival_time_s"] / 60.0
        top = float(np.nanmax(arr_min)) if np.isfinite(arr_min).any() else 1.0
        charts[f"c2-arrival-map-{sid}"] = _chart(
            f"c2-arrival-map-{sid}",
            "raster",
            _en_es(f"Arrival time of the flow, {sc['label']}", f"Tiempo de llegada del flujo, {sc['label_es']}"[:200]),
            _en_es(
                f"First time the depth exceeds {thr} m, in minutes after the breach starts; blank where it never does",
                f"Primer instante en que la profundidad supera {thr} m, en minutos desde el inicio de la rotura; "
                "en blanco donde nunca ocurre",
            ),
            "arrival_time" if sid == run.get("headline_scenario") else None,
            **_axes_en(),
            raster=_raster(terrain, arr_min, "min", "magma", "min", _en_es("Arrival time", "Tiempo de llegada"), top),
        )
    # arrival time against distance from the breach (first arrival in 100 m bins)
    bin_m = float(run.get("distance_bin_m", 100.0))
    arr_series = []
    for sc, res in zip(scenarios, results, strict=True):
        d, a = res["dist"].ravel(), res["maps"]["arrival_time_s"].ravel() / 60.0
        ok = np.isfinite(a)
        edges = np.arange(0.0, d[ok].max() + bin_m, bin_m) if ok.any() else np.array([0.0, bin_m])
        which = np.digitize(d[ok], edges) - 1
        xs, ys = [], []
        for b in range(len(edges) - 1):
            sel = a[ok][which == b]
            if sel.size:
                xs.append(round(float(edges[b] + 0.5 * bin_m) / 1000.0, 4))
                ys.append(round(float(sel.min()), 2))
        if xs:  # a scenario whose flow never exceeds the threshold has no arrival to draw
            arr_series.append({"id": sc["id"], "label": label(sc), "x": xs, "y": ys, "n": int(ok.sum())})
    arrival_chart = _chart(
        "c2-arrival-distance",
        "line",
        _en_es(
            "Arrival time of the flow against distance from the breach",
            "Tiempo de llegada del flujo según la distancia",
        ),
        _en_es(
            f"Earliest arrival over all cells in {bin_m:g} m distance bins (straight-line distance from the breach)",
            f"Llegada más temprana entre todas las celdas en intervalos de {bin_m:g} m de distancia en línea recta",
        ),
        None,
        x_axis={"label": _en_es("Distance from the breach", "Distancia desde la rotura"), "unit": "km"},
        y_axis={"label": _en_es("Arrival time", "Tiempo de llegada"), "unit": "min"},
        series=arr_series,
    )
    if arr_series:
        charts["c2-arrival-distance"] = arrival_chart
    else:
        reason = "no scenario's flow exceeded the depth threshold in the simulated time"
        charts["c2-arrival-distance"] = _not_run(
            "c2-arrival-distance",
            "line",
            arrival_chart["title"],
            _en_es(reason, "ningún escenario superó el umbral de profundidad"),
        )
    t_h = lambda res: [round(s["t_s"] / 3600.0, 4) for s in res["series"]]  # noqa: E731
    charts["c2-front-time"] = _chart(
        "c2-front-time",
        "line",
        _en_es("Flow front through time", "Frente del flujo en el tiempo"),
        _en_es(
            f"Largest straight-line distance from the breach of a cell deeper than {thr} m",
            f"Mayor distancia en línea recta desde la rotura de una celda con más de {thr} m",
        ),
        None,
        x_axis={"label": _en_es("Time since the breach starts", "Tiempo desde el inicio de la rotura"), "unit": "h"},
        y_axis={"label": _en_es("Front distance", "Distancia del frente"), "unit": "km"},
        series=[
            {
                "id": sc["id"],
                "label": label(sc),
                "x": t_h(res),
                "y": [round(s["front_distance_m"] / 1000.0, 4) for s in res["series"]],
            }
            for sc, res in zip(scenarios, results, strict=True)
        ],
    )
    charts["c2-area-time"] = _chart(
        "c2-area-time",
        "line",
        _en_es("Flooded area through time", "Área inundada en el tiempo"),
        _en_es(
            f"Area of cells deeper than {thr} m at each time", f"Área de celdas con más de {thr} m en cada instante"
        ),
        None,
        x_axis={"label": _en_es("Time since the breach starts", "Tiempo desde el inicio de la rotura"), "unit": "h"},
        y_axis={"label": _en_es("Flooded area", "Área inundada"), "unit": "km2"},
        series=[
            {
                "id": sc["id"],
                "label": label(sc),
                "x": t_h(res),
                "y": [round(s["wet_area_m2"] / 1e6, 5) for s in res["series"]],
            }
            for sc, res in zip(scenarios, results, strict=True)
        ],
    )
    charts["c2-pit-volume"] = _chart(
        "c2-pit-volume",
        "line",
        _en_es("Volume of flow inside the pit outline", "Volumen de flujo dentro del contorno del rajo"),
        _en_es(
            "Sum of depth times cell area over the cells inside the pit outline of scene A1",
            "Suma de profundidad por área de celda sobre las celdas dentro del contorno del rajo de la escena A1",
        ),
        None,
        x_axis={"label": _en_es("Time since the breach starts", "Tiempo desde el inicio de la rotura"), "unit": "h"},
        y_axis={"label": _en_es("Volume in the pit", "Volumen en el rajo"), "unit": "m3"},
        series=[
            {
                "id": sc["id"],
                "label": label(sc),
                "x": t_h(res),
                "y": [round(s["pit_volume_m3"], 1) for s in res["series"]],
            }
            for sc, res in zip(scenarios, results, strict=True)
        ],
    )
    cats = [{"id": sc["id"], "label": label(sc)} for sc in scenarios]
    charts["c2-area-bars"] = _chart(
        "c2-area-bars",
        "bar",
        _en_es("Inundated area by scenario", "Área inundada por escenario"),
        _en_es(
            f"Area of cells whose maximum depth exceeds {thr} m",
            f"Área de celdas cuya profundidad máxima supera {thr} m",
        ),
        "inundated_area",
        y_axis={"label": _en_es("Inundated area", "Área inundada"), "unit": "km2"},
        categories=cats,
        series=[
            {
                "id": "inundated-area",
                "label": _en_es("Inundated area", "Área inundada"),
                "y": [round(r["kpi"]["inundated_area_km2"], 4) for r in results],
            }
        ],
    )
    excl = float(run.get("depth_exclusion_m", 100.0))
    charts["c2-depth-bars"] = _chart(
        "c2-depth-bars",
        "bar",
        _en_es("Maximum flow depth by scenario", "Profundidad máxima del flujo por escenario"),
        _en_es(
            f"Largest depth in any cell farther than {excl:g} m from the breach "
            "(the breach cells hold the injected volume)",
            f"Mayor profundidad en una celda a más de {excl:g} m de la rotura "
            "(las celdas de rotura reciben el volumen)",
        ),
        "max_depth",
        y_axis={"label": _en_es("Maximum depth", "Profundidad máxima"), "unit": "m"},
        categories=cats,
        series=[
            {
                "id": "max-depth",
                "label": _en_es("Maximum depth", "Profundidad máxima"),
                "y": [round(r["kpi"]["max_depth_beyond_exclusion_m"], 3) for r in results],
            }
        ],
    )
    num = lambda cid, en, es, unit: {"id": cid, "label": _en_es(en, es), "type": "number", "unit": unit}  # noqa: E731
    text = lambda cid, en, es: {"id": cid, "label": _en_es(en, es), "type": "text"}  # noqa: E731
    cols = [
        text("scenario", "Scenario", "Escenario"),
        num("volume", "Released volume", "Volumen liberado", "m3"),
        num("peak", "Peak discharge", "Caudal peak", "m3/s"),
        num("tau-y", "Yield stress", "Tensión de fluencia", "Pa"),
        num("mu-b", "Plastic viscosity", "Viscosidad plástica", "Pa.s"),
        num("rho", "Density", "Densidad", "kg/m3"),
        num("arrival-pit", "First arrival at the pit outline", "Primera llegada al contorno del rajo", "min"),
        num("depth", "Maximum depth beyond the breach", "Profundidad máxima fuera de la rotura", "m"),
        num("area", "Inundated area", "Área inundada", "km2"),
        num("run-out", "Run-out distance", "Alcance", "km"),
        num("pit-volume", "Volume in the pit at the end", "Volumen en el rajo al final", "m3"),
        num("residual", "Volume balance residual", "Residuo del balance de volumen", "1"),
    ]
    rows = []
    for sc, r in zip(scenarios, results, strict=True):
        k = r["kpi"]
        arr = k["arrival_time_pit_min"]
        rows.append(
            [
                sc["label"],
                sc["volume_m3"],
                round(sc["peak_discharge_m3_s"], 3),
                sc["tau_y_pa"],
                sc["mu_b_pa_s"],
                sc["rho_kg_m3"],
                None if arr is None else round(arr, 1),
                round(k["max_depth_beyond_exclusion_m"], 3),
                round(k["inundated_area_km2"], 4),
                round(k["run_out_m"] / 1000.0, 3),
                round(k["pit_volume_end_m3"], 1),
                float(f"{abs(r['balance']['residual']):.3g}"),
            ]
        )
    charts["c2-kpi-table"] = _chart(
        "c2-kpi-table",
        "table",
        _en_es("Breach scenarios and their results", "Escenarios de rotura y sus resultados"),
        _en_es(
            "A blank arrival means the flow never reached the pit outline in the simulated time",
            "Una llegada en blanco significa que el flujo no alcanzó el contorno del rajo en el tiempo simulado",
        ),
        None,
        table={"columns": cols, "rows": rows},
    )
    if benchmarks is None:
        charts["c2-solver-verification"] = _not_run(
            "c2-solver-verification",
            "table",
            _en_es(
                "Solver verification against analytical solutions", "Verificación del solver con soluciones analíticas"
            ),
            _en_es(
                "The benchmark report was not part of this run", "El informe de benchmarks no fue parte de esta corrida"
            ),
        )
    else:
        bcols = [
            text("check", "Check", "Prueba"),
            num("value", "Measured", "Medido", "1"),
            num("tolerance", "Tolerance", "Tolerancia", "1"),
            text("status", "Status", "Estado"),
        ]
        brows = [
            [
                r["name"][:200],
                float(f"{r['value']:.4g}"),
                r["tolerance"],
                r["status"] + (" (known limit)" if r.get("known_limit") else ""),
            ]
            for r in benchmarks["rows"]
        ][:200]
        charts["c2-solver-verification"] = _chart(
            "c2-solver-verification",
            "table",
            _en_es(
                "Solver verification against analytical solutions", "Verificación del solver con soluciones analíticas"
            ),
            _en_es(
                f"Benchmark report on {benchmarks['device']}: Ritter, Stoker, radial dam break, lake at rest, "
                "volume balance, Bingham sheet flow",
                f"Informe de benchmarks en {benchmarks['device']}: Ritter, Stoker, rotura radial, lago en reposo, "
                "balance de volumen, flujo Bingham",
            ),
            None,
            table={"columns": bcols, "rows": brows},
        )
    return charts


def write_outputs(out_dir: Path, charts: Mapping[str, dict], summary: Mapping[str, Any]) -> None:
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)
    for cid, doc in charts.items():
        text = json.dumps(doc, indent=1) + "\n"
        if len(text.encode()) > MAX_CHART_BYTES:
            raise ValueError(
                f"charts/{cid}.json is {len(text.encode())} bytes, above the {MAX_CHART_BYTES} byte chart budget"
            )
        (out_dir / "charts" / f"{cid}.json").write_text(text, encoding="utf-8", newline="\n")
    (out_dir / "c2-run.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8", newline="\n")


def run_c2(
    out_dir: Path, recipe: Mapping[str, Any], data_root: Path, device: str, benchmarks: Mapping[str, Any] | None,
    guard: Any = None,
) -> dict[str, Any]:  # fmt: skip
    """Run every scenario of the recipe and write the chart-series files and `c2-run.json`; returns the summary."""
    run = dict(recipe["run"])
    terrain = prepare_terrain(
        data_root / recipe["dem"], recipe["window"], float(run["cell_m"]), float(recipe.get("min_coverage", 0.95))
    )
    pit = pit_mask(data_root / recipe["pit_outline"], recipe["pit_outline_origin_m"], terrain)
    scenarios = list(recipe["scenarios"])
    results = [run_scenario(terrain, sc, run, pit, device, guard) for sc in scenarios]
    charts = build_charts(run, scenarios, results, terrain, benchmarks)
    total_wall = sum(r["wall_s"] for r in results)
    summary = {
        "kind": "c2-run",
        "case": "C2",
        "label": LABEL,
        "solver": producer(),
        "device": device,
        "gpu_hours": round(total_wall / 3600.0, 5) if device != "cpu" else None,
        "terrain": {
            "dem": Path(recipe["dem"]).name,
            "cell_m": terrain["cell_m"],
            "shape": list(terrain["shape"]),
            "window_m": dict(recipe["window"]),
            "cells_filled": terrain["cells_filled"],
            "elevation_min_m": float(terrain["z"].min()),
            "elevation_max_m": float(terrain["z"].max()),
            "pit_cells": int(pit.sum()),
        },
        "breach": {**run["breach"], "bed_elevation_m": results[0]["breach_bed_m"], "cells": results[0]["breach_cells"]},
        "run": {k: v for k, v in run.items() if k != "breach"},
        "scenarios": [
            {
                "id": sc["id"],
                "label": sc["label"],
                "source": sc["source"],
                "volume_m3": sc["volume_m3"],
                "peak_discharge_m3_s": sc["peak_discharge_m3_s"],
                "tau_y_pa": sc["tau_y_pa"],
                "mu_b_pa_s": sc["mu_b_pa_s"],
                "rho_kg_m3": sc["rho_kg_m3"],
                "steps": r["steps"],
                "wall_s": round(r["wall_s"], 2),
                "kpi": r["kpi"],
                "balance": r["balance"],
            }
            for sc, r in zip(scenarios, results, strict=True)
        ],
        "benchmarks": None
        if benchmarks is None
        else {k: benchmarks[k] for k in ("device", "n_pass", "n_fail", "n_known_limit", "wall_s", "version")},
        "limits": recipe.get("limits", []),
    }
    write_outputs(out_dir, charts, summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    import yaml

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("recipe", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--device", default="cpu")
    p.add_argument("--benchmarks", type=Path, help="the swe-benchmarks.json of the same device")
    p.add_argument("--dry-run", action="store_true", help="coarse cell and short time on the CPU, into out_dir")
    a = p.parse_args(argv)
    doc = yaml.safe_load(a.recipe.read_text(encoding="utf-8"))
    recipe = doc["stages"][0]["params"] if "stages" in doc else doc
    benchmarks = json.loads(a.benchmarks.read_text(encoding="utf-8")) if a.benchmarks else None
    device = a.device
    guard = None
    session = None
    if a.dry_run:
        device = "cpu"
        recipe = {**recipe, "run": {**recipe["run"], **recipe["dry_run"]}}
    elif device != "cpu":
        from pitstudio_studio.physics.planar import gpujob

        session = gpujob.start_session()
        guard = session[2].check
    try:
        summary = run_c2(a.out_dir, recipe, a.data_root, device, benchmarks, guard)
    finally:
        if session is not None:
            session[1].release()
    for s in summary["scenarios"]:
        print(f"{s['id']}: {json.dumps(s['kpi'])} balance {json.dumps(s['balance'])}")
    print(f"c2 breach runs on {device}: {len(summary['scenarios'])} scenarios, gpu_hours {summary['gpu_hours']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

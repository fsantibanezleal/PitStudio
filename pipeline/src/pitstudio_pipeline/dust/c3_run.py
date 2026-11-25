"""Case C3 run (spec 018 FR-018-51, FR-018-16, spec 020 FR-020-08): AP-42 haul-road PM10 emission factors and the Gaussian
plume over the Bingham pit for ten years of real hourly wind, as chart-series files and a results summary.

Entry (`python -m pitstudio_pipeline.dust.c3_run --recipe studio/recipes/cases/c3.yaml --data-root DIR --out DIR`), CPU only.
From the recipe parameters it (1) reads the hourly wind of the NOAA GHCNh station, (2) computes the AP-42 equation 1a PM10
factor against silt and weight with the Table 13.2.2-3 validity ranges, (3) discretises the road network of the A1 pit design
into source pieces that emit factor x traffic x length, (4) draws the wind rose, the ground-level concentration map of the
prevailing wind, the concentration along the wind axis through the pit for three stability classes, and the long-term mean
and hourly 99th percentile at four hypothetical receptors. Every number is a number of `minephys.environment`; the scenario
(silt, traffic, release height, stability class, receptors) is illustrative and UNVERIFIED for the site, and the plume is a
screening model, not AERMOD. An input that is absent or unreadable makes the charts that need it `not-run` with the reason;
the others are still produced.
"""
# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from minephys import knowledge
from minephys.environment import controlled_emission_factor

from pitstudio.cases.d1.design_grid import minephys_identity
from pitstudio_pipeline import chartkit
from pitstudio_pipeline.dust import plume
from pitstudio_pipeline.dust.emission import (
    ap42_in_range,
    emission_factor_kg_per_vkt,
    fleet_mean_weight_kg,
    short_ton_kg,
    table_range,
)
from pitstudio_pipeline.dust.winds import WindRecords, read_ghcnh_wind, wind_rose

TOOL = "minephys"
METHOD = "US EPA AP-42 13.2.2 equation 1a unpaved-road PM10 factor; ISC3 Gaussian plume with ground reflection, Pasquill-Gifford rural dispersion"
LABEL = "screening Gaussian plume, not AERMOD; illustrative scenario, not validated against measured concentrations"
SERVES = ["FR-018-16", "FR-018-51"]
SERVES_MAP = ["FR-018-16", "FR-018-51", "FR-020-08"]
bi = chartkit.bi
COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
KG_PER_M3_TO_UG_PER_M3 = 1e9
MAP_FLOOR_UG_M3 = 1e-3  # a map cell below this is stored as zero: 1 ng/m3 is far under any reading of the scale
CLASS_ES = {"B": "B (muy inestable)", "D": "D (neutra)", "F": "F (estable)"}
CLASS_EN = {"B": "B (unstable)", "D": "D (neutral)", "F": "F (stable)"}
RECEPTORS = (("r-n", "N", "N"), ("r-e", "E", "E"), ("r-s", "S", "S"), ("r-w", "W", "O"))


def fmt(value: float) -> str:
    """A concentration for a label: whole numbers from 100 up, three significant digits below, `<0.001` under the map floor."""
    if value == 0:
        return "0"
    if value < MAP_FLOOR_UG_M3:
        return f"<{MAP_FLOOR_UG_M3:g}"
    return f"{value:.0f}" if value >= 100 else f"{value:.3g}"


def sig(value: float, digits: int = 4) -> float:
    return 0.0 if value == 0 else float(f"{value:.{digits}g}")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _geometries(doc: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if doc.get("type") == "FeatureCollection":
        return [f["geometry"] for f in doc["features"]]
    return [doc["geometry"] if doc.get("type") == "Feature" else doc]


def _road_lines(path: Path) -> list[np.ndarray]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return [np.asarray(g["coordinates"], dtype=float) for g in _geometries(doc) if g["type"] == "LineString"]


def _outline_box(path: Path) -> tuple[float, float, float, float]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    pts: list[list[float]] = []
    for g in _geometries(doc):
        if g["type"] == "Polygon":
            pts += [p for ring in g["coordinates"] for p in ring]
        elif g["type"] == "MultiPolygon":
            pts += [p for poly in g["coordinates"] for ring in poly for p in ring]
    a = np.asarray(pts, dtype=float)
    return float(a[:, 0].min()), float(a[:, 0].max()), float(a[:, 1].min()), float(a[:, 1].max())


def _read_wind(root: Path, inputs: Mapping[str, Any], wind: Mapping[str, Any]) -> tuple[WindRecords | None, str | None]:
    files = [root / f for f in inputs["wind_files"]]
    missing = [p.name for p in files if not p.is_file()]
    if missing:
        return None, f"the GHCNh wind file {missing[0]} is absent from the data root"
    try:
        rec = read_ghcnh_wind(files, station=wind["station"], good_quality=tuple(wind["good_quality_codes"]))
    except (OSError, pl.exceptions.PolarsError) as err:
        return None, f"the GHCNh wind files could not be read ({type(err).__name__})"
    if rec.counts["hours"] == 0:
        return None, "the GHCNh wind files hold no usable hour"
    return rec, None


def _prevailing(rec: WindRecords, min_speed: float) -> dict[str, Any]:
    ok = (rec.kind == "wind") & ~np.isnan(rec.direction_deg) & (rec.speed_m_s >= min_speed)
    sector = np.floor(np.mod(rec.direction_deg[ok] + 11.25, 360.0) / 22.5).astype(int)
    counts = np.bincount(sector, minlength=16)
    k = int(np.argmax(counts))
    speed = float(np.median(rec.speed_m_s[ok][sector == k]))
    return {
        "sector": COMPASS[k],
        "from_deg": 22.5 * k,
        "speed_m_s": speed,
        "hours": int(counts[k]),
        "share_percent": 100.0 * counts[k] / len(rec.speed_m_s),
    }


def _not_run(
    cid: str, kind: str, title: dict[str, str], prod: dict[str, str], serves: list[str], why: str
) -> dict[str, Any]:
    return chartkit.not_run(
        cid,
        "C3",
        kind,
        title,
        prod,
        serves,
        bi(why[:200], "Falta el registro de viento de GHCNh que este grafico necesita"),
    )


def _ef_charts(p: Mapping[str, Any], prod: dict[str, str], reference: dict[str, float]) -> list[dict[str, Any]]:
    short_ton = short_ton_kg()
    sw = p["ef_sweeps"]
    s_lo, s_hi = table_range("ap42_range_silt")
    w_lo, w_hi = table_range("ap42_range_weight")
    sp = sw["silt_percent"]
    xs = np.linspace(sp["min"], sp["max"], sp["n"])
    silt_series = [
        chartkit.series(
            f"w-{int(t)}",
            bi(f"Mean weight {t:g} t", f"Peso medio {t:g} t"),
            [sig(x, 6) for x in xs],
            [sig(float(y), 6) for y in emission_factor_kg_per_vkt(xs / 100.0, t * 1000.0)],
        )
        for t in sp["weights_t"]
    ]
    silt = chartkit.chart(
        "c3-ef-vs-silt",
        "C3",
        "line",
        bi("PM10 emission factor against road silt content", "Factor de emision de PM10 segun el limo del camino"),
        prod,
        SERVES,
        caption=bi(
            f"AP-42 13.2.2 equation 1a, one curve per mean weight; no speed term. Ranges marked: silt {s_lo:g} to {s_hi:g} %, weight {w_lo:g} to {w_hi:g} short tons.",
            f"AP-42 13.2.2 ecuacion 1a, una curva por peso medio; sin termino de velocidad. Rangos marcados: limo {s_lo:g} a {s_hi:g} %, peso {w_lo:g} a {w_hi:g} ton cortas.",
        ),
        kpi="pm10_per_vkt",
        x_axis=chartkit.axis("Road surface silt content", "Contenido de limo del camino", "%"),
        y_axis=chartkit.axis("PM10 emission factor", "Factor de emision de PM10", "kg/VKT"),
        series=silt_series,
        markers=[
            {
                "id": "valid-min",
                "label": bi("Lower end of the AP-42 silt range", "Limite inferior del rango de limo de AP-42"),
                "value_text": f"{s_lo:g} %",
                "orientation": "vertical",
                "x": s_lo,
            },
            {
                "id": "valid-max",
                "label": bi("Upper end of the AP-42 silt range", "Limite superior del rango de limo de AP-42"),
                "value_text": f"{s_hi:g} %",
                "orientation": "vertical",
                "x": s_hi,
            },
        ],
    )
    wp = sw["weight_t"]
    ws = np.linspace(wp["min"], wp["max"], wp["n"])
    weight_series = [
        chartkit.series(
            f"s-{int(s)}",
            bi(f"Silt {s:g} %", f"Limo {s:g} %"),
            [sig(x, 6) for x in ws],
            [sig(float(y), 6) for y in emission_factor_kg_per_vkt(s / 100.0, ws * 1000.0)],
        )
        for s in wp["silt_percent"]
    ]
    wlo_t, whi_t = w_lo * short_ton / 1000.0, w_hi * short_ton / 1000.0
    weight = chartkit.chart(
        "c3-ef-vs-weight",
        "C3",
        "line",
        bi(
            "PM10 emission factor against mean vehicle weight",
            "Factor de emision de PM10 segun el peso medio del vehiculo",
        ),
        prod,
        SERVES,
        caption=bi(
            f"AP-42 equation 1a, one curve per silt content. The point is this run's reference case ({reference['weight_t']:.0f} t, {reference['silt_percent']:g} % silt), {'inside' if reference['in_range'] else 'outside'} the weight range.",
            f"AP-42 ecuacion 1a, una curva por limo. El punto es el caso de referencia ({reference['weight_t']:.0f} t, {reference['silt_percent']:g} % de limo), {'dentro' if reference['in_range'] else 'fuera'} del rango de peso.",
        ),
        x_axis=chartkit.axis("Mean vehicle weight", "Peso medio del vehiculo", "t"),
        y_axis=chartkit.axis("PM10 emission factor", "Factor de emision de PM10", "kg/VKT"),
        series=weight_series,
        markers=[
            {
                "id": "valid-min",
                "label": bi("Lower end of the AP-42 weight range", "Limite inferior del rango de peso de AP-42"),
                "value_text": f"{wlo_t:.2f} t",
                "orientation": "vertical",
                "x": wlo_t,
            },
            {
                "id": "valid-max",
                "label": bi("Upper end of the AP-42 weight range", "Limite superior del rango de peso de AP-42"),
                "value_text": f"{whi_t:.1f} t",
                "orientation": "vertical",
                "x": whi_t,
            },
            {
                "id": "reference-case",
                "label": bi("Reference case of this run", "Caso de referencia de esta corrida"),
                "value_text": f"{reference['pm10_kg_per_vkt']:.3g} kg/VKT",
                "orientation": "point",
                "x": sig(reference["weight_t"], 6),
                "y": sig(reference["pm10_kg_per_vkt"], 6),
            },
        ],
    )
    pound, mile = knowledge.get_value("pound"), knowledge.get_value("ap42_mile_in_m")
    e0 = reference["pm10_kg_per_vkt"]
    rows = []
    for ce in p["control_percent"]:
        e = float(controlled_emission_factor(e0, ce / 100.0))
        rows.append(
            [
                float(ce),
                sig(e * mile / 1000.0 / pound, 6),
                sig(e, 6),
                "inside" if reference["in_range"] else "extrapolated",
            ]
        )
    table = chartkit.chart(
        "c3-ef-table",
        "C3",
        "table",
        bi(
            "PM10 emission factor of the reference case under dust control",
            "Factor de emision de PM10 del caso de referencia con control de polvo",
        ),
        prod,
        SERVES,
        caption=bi(
            f"Equation 1a for {reference['weight_t']:.0f} t and {reference['silt_percent']:g} % silt, times (1 minus control efficiency), levels of Table 13.2.2-5.",
            f"Ecuacion 1a para {reference['weight_t']:.0f} t y {reference['silt_percent']:g} % de limo, por (1 menos eficiencia de control), niveles de la Tabla 13.2.2-5.",
        ),
        table={
            "columns": [
                {
                    "id": "control-percent",
                    "label": bi("Control efficiency", "Eficiencia de control"),
                    "type": "number",
                    "unit": "%",
                },
                {
                    "id": "pm10-lb-per-vmt",
                    "label": bi("PM10 factor", "Factor de PM10"),
                    "type": "number",
                    "unit": "lb/VMT",
                },
                {
                    "id": "pm10-kg-per-vkt",
                    "label": bi("PM10 factor", "Factor de PM10"),
                    "type": "number",
                    "unit": "kg/VKT",
                },
                {
                    "id": "validity",
                    "label": bi("Against the AP-42 ranges", "Frente a los rangos de AP-42"),
                    "type": "text",
                },
            ],
            "rows": rows,
        },
    )
    return [silt, weight, table]


def _scenario(p: Mapping[str, Any]) -> dict[str, Any]:
    s = p["scenario"]
    t = s["truck"]
    weight = fleet_mean_weight_kg(t["empty_mass_kg"], t["payload_kg"], t["loaded_fraction"])
    e = emission_factor_kg_per_vkt(s["silt_fraction"], weight, s["size_class"])
    return {
        "weight_kg": weight,
        "weight_t": weight / 1000.0,
        "silt_percent": 100.0 * s["silt_fraction"],
        "pm10_kg_per_vkt": e,
        "in_range": bool(ap42_in_range(s["silt_fraction"], weight)),
    }


def compute(params: Mapping[str, Any], data_root: Path | str) -> dict[str, Any]:
    root = Path(data_root)
    p = params
    s = p["scenario"]
    version = minephys_identity()
    prod = chartkit.producer(TOOL, METHOD, version, LABEL)
    ref = _scenario(p)
    charts = _ef_charts(p, prod, ref)

    lines = _road_lines(root / p["inputs"]["road_network"])
    x0b, x1b, y0b, y1b = _outline_box(root / p["inputs"]["pit_outline"])
    per_m = ref["pm10_kg_per_vkt"] / 1000.0 * s["passes_per_hour_per_edge"] / 3600.0  # kg per metre of road per second
    rec_src, rec_len = plume.discretise(lines, p["receptors"]["source_spacing_m"])
    map_src, map_len = plume.discretise(lines, p["map"]["source_spacing_m"])
    q_rec, q_map = per_m * rec_len, per_m * map_len
    road_length = float(rec_len.sum())
    plume_args = {
        "stability": s["stability_class"],
        "terrain": s["terrain"],
        "release_height_m": s["release_height_m"],
        "receptor_height_m": s["receptor_height_m"],
    }
    wind, why = _read_wind(root, p["inputs"], p["wind"])
    titles = {
        "c3-wind-rose": bi("Wind rose of the station record", "Rosa de vientos del registro de la estacion"),
        "c3-plume-map": bi(
            "Ground-level PM10 over the pit for the prevailing wind",
            "PM10 a nivel del suelo sobre el pit con el viento predominante",
        ),
        "c3-conc-vs-distance": bi(
            "Ground-level PM10 along the wind axis through the pit",
            "PM10 a nivel del suelo a lo largo del eje del viento por el pit",
        ),
        "c3-receptor-concentration": bi(
            "PM10 at four hypothetical receptors over the wind record",
            "PM10 en cuatro receptores hipoteticos durante el registro de viento",
        ),
    }
    kinds = {
        "c3-wind-rose": "bar",
        "c3-plume-map": "raster",
        "c3-conc-vs-distance": "line",
        "c3-receptor-concentration": "bar",
    }
    extra: dict[str, Any] = {}
    headline = [
        {
            "kpi": "pm10_per_vkt",
            "name": "PM10 emission factor, reference case",
            "unit": "kg/VKT",
            "value": sig(ref["pm10_kg_per_vkt"], 6),
            "note": f"AP-42 equation 1a, {ref['weight_t']:.0f} t mean weight, {ref['silt_percent']:g} % silt (illustrative, UNVERIFIED for the site)"
            + (
                ""
                if ref["in_range"]
                else "; the weight lies above the Table 13.2.2-3 range, so the value is an extrapolation"
            ),
        }
    ]
    rows: list[dict[str, Any]] = []
    inputs = [
        {"name": Path(f).name, "sha256": _sha(root / f)} for f in p["inputs"]["wind_files"] if (root / f).is_file()
    ]
    inputs += [
        {"name": Path(p["inputs"][k]).name, "sha256": _sha(root / p["inputs"][k])}
        for k in ("road_network", "pit_outline")
    ]

    if wind is None:
        for cid in titles:
            charts.append(
                _not_run(cid, kinds[cid], titles[cid], prod, SERVES_MAP, f"{why}; this chart needs the wind record")
            )
    else:
        min_speed = float(p["wind"]["min_modelled_speed_m_s"])
        rose = wind_rose(wind)
        rf = np.array(rose["frequency"]) * 100.0
        charts.append(
            chartkit.chart(
                "c3-wind-rose",
                "C3",
                "bar",
                titles["c3-wind-rose"],
                prod,
                SERVES,
                caption=bi(
                    f"Share of {wind.counts['hours']} valid hours, {p['wind']['period']}, by direction the wind blows from and speed. Calm {100 * rose['calm_fraction']:.1f} %, variable {100 * rose['variable_fraction']:.1f} %.",
                    f"Porcentaje de {wind.counts['hours']} horas validas, {p['wind']['period'].replace(' to ', ' a ')}, por direccion de origen y velocidad. Calma {100 * rose['calm_fraction']:.1f} %, variable {100 * rose['variable_fraction']:.1f} %.",
                ),
                y_axis=chartkit.axis(
                    "Share of hours, wind from this direction", "Porcentaje de horas, viento desde esta direccion", "%"
                ),
                categories=[{"id": c.lower(), "label": bi(c, c.replace("W", "O"))} for c in COMPASS],
                series=[
                    chartkit.series(
                        f"speed-{i + 1}",
                        bi(lab, lab.replace(" to ", " a ").replace("above", "sobre")),
                        None,
                        [sig(v, 5) for v in rf[i]],
                    )
                    for i, lab in enumerate(rose["speed_labels"])
                ],
            )
        )
        prev = _prevailing(wind, min_speed)
        extra["prevailing_wind"] = {k: (sig(v, 5) if isinstance(v, float) else v) for k, v in prev.items()}
        kw = {"wind_speed_m_s": prev["speed_m_s"], "wind_from_deg": prev["from_deg"], **plume_args}
        hw, nx, ny = p["map"]["half_width_m"], p["map"]["nx"], p["map"]["ny"]
        dx, dy = 2 * hw / nx, 2 * hw / ny
        cx = -hw + (np.arange(nx) + 0.5) * dx
        cy = hw - (np.arange(ny) + 0.5) * dy  # the first row is the top row
        gx, gy = np.meshgrid(cx, cy)
        grid = (
            plume.concentration(map_src, q_map, np.column_stack([gx.ravel(), gy.ravel()]), **kw)
            * KG_PER_M3_TO_UG_PER_M3
        )
        grid = np.where(grid < MAP_FLOOR_UG_M3, 0.0, grid)
        vals = [sig(float(v), 4) for v in grid]
        arr = np.array(vals)
        imax = int(np.argmax(arr))
        top = float(arr[imax])
        vmax = sig(float(np.percentile(arr, 99.5)), 2) or top
        receptors = _receptors((x0b, x1b, y0b, y1b), p["receptors"]["offset_m"])
        at_map = plume.concentration(map_src, q_map, receptors[:, 1:], **kw) * KG_PER_M3_TO_UG_PER_M3
        markers = [
            {
                "id": "max-concentration",
                "label": bi("Maximum ground-level concentration", "Concentracion maxima a nivel del suelo"),
                "value_text": f"{fmt(top)} ug/m3",
                "orientation": "point",
                "x": float(gx.ravel()[imax]),
                "y": float(gy.ravel()[imax]),
            }
        ]
        for (rid, en, es), (_, rx, ry), c in zip(RECEPTORS, receptors, at_map, strict=True):
            markers.append(
                {
                    "id": f"map-{rid}",
                    "label": bi(f"Receptor {en}", f"Receptor {es}"),
                    "value_text": f"{fmt(float(c))} ug/m3",
                    "orientation": "point",
                    "x": round(float(rx), 1),
                    "y": round(float(ry), 1),
                }
            )
        charts.append(
            chartkit.chart(
                "c3-plume-map",
                "C3",
                "raster",
                titles["c3-plume-map"],
                prod,
                SERVES_MAP,
                caption=bi(
                    f"Prevailing wind (from {prev['sector']}, {prev['hours']} h, median {prev['speed_m_s']:.1f} m/s), class {s['stability_class']} assumed, {s['receptor_height_m']:g} m height; sources: A1 pit roads. Scale saturates at its maximum.",
                    f"Viento predominante (desde {prev['sector']}, {prev['hours']} h, mediana {prev['speed_m_s']:.1f} m/s), clase {s['stability_class']} supuesta, {s['receptor_height_m']:g} m de altura; fuentes: caminos del pit A1. La escala satura en su maximo.",
                ),
                x_axis=chartkit.axis("East of the site origin", "Este del origen del sitio", "m"),
                y_axis=chartkit.axis("North of the site origin", "Norte del origen del sitio", "m"),
                raster={
                    "nx": nx,
                    "ny": ny,
                    "extent": {"x0": -hw, "x1": hw, "y0": -hw, "y1": hw},
                    "values": vals,
                    "colour": {
                        "colormap": "viridis",
                        "vmin": 0.0,
                        "vmax": vmax,
                        "unit": "ug/m3",
                        "label": bi("PM10 concentration", "Concentracion de PM10"),
                    },
                },
                markers=markers,
            )
        )
        pr = p["profile"]
        axis_x = np.linspace(pr["x_min_m"], pr["x_max_m"], pr["n"])
        th = math.radians(prev["from_deg"] + 180.0)
        axis_pts = np.column_stack([axis_x * math.sin(th), axis_x * math.cos(th)])
        prof_series, prof_marks = [], []
        for cls in pr["classes"]:
            c = plume.concentration(map_src, q_map, axis_pts, **{**kw, "stability": cls}) * KG_PER_M3_TO_UG_PER_M3
            y = [sig(float(v), 4) for v in c]
            i = int(np.argmax(y))
            prof_series.append(
                chartkit.series(
                    f"class-{cls.lower()}",
                    bi(f"Stability class {CLASS_EN[cls]}", f"Clase de estabilidad {CLASS_ES[cls]}"),
                    [sig(float(v), 6) for v in axis_x],
                    y,
                )
            )
            prof_marks.append(
                {
                    "id": f"max-{cls.lower()}",
                    "label": bi(f"Maximum, class {cls}", f"Maximo, clase {cls}"),
                    "value_text": f"{fmt(y[i])} ug/m3 at {float(axis_x[i]):.0f} m",
                    "orientation": "point",
                    "x": sig(float(axis_x[i]), 6),
                    "y": y[i],
                }
            )
        charts.append(
            chartkit.chart(
                "c3-conc-vs-distance",
                "C3",
                "line",
                titles["c3-conc-vs-distance"],
                prod,
                SERVES_MAP,
                caption=bi(
                    f"Axis through the pit centre along the prevailing wind (from {prev['sector']}, {prev['speed_m_s']:.1f} m/s), three stability classes; each dot is the maximum.",
                    f"Eje por el centro del pit segun el viento predominante (desde {prev['sector']}, {prev['speed_m_s']:.1f} m/s), tres clases de estabilidad; cada punto es el maximo.",
                ),
                x_axis=chartkit.axis(
                    "Distance downwind of the pit centre", "Distancia a sotavento del centro del pit", "m"
                ),
                y_axis=chartkit.axis("PM10 concentration", "Concentracion de PM10", "ug/m3"),
                series=prof_series,
                markers=prof_marks,
            )
        )
        st = plume.receptor_statistics(
            rec_src, q_rec, receptors[:, 1:], wind.speed_m_s, wind.direction_deg, min_speed_m_s=min_speed, **plume_args
        )
        mean = [sig(float(v) * KG_PER_M3_TO_UG_PER_M3, 4) for v in st["mean_kg_per_m3"]]
        p99 = [sig(float(v) * KG_PER_M3_TO_UG_PER_M3, 4) for v in st["p99_kg_per_m3"]]
        total_hours = len(wind.speed_m_s)
        charts.append(
            chartkit.chart(
                "c3-receptor-concentration",
                "C3",
                "bar",
                titles["c3-receptor-concentration"],
                prod,
                SERVES,
                caption=bi(
                    f"Mean and hourly 99th percentile at four hypothetical receptors {p['receptors']['offset_m']:g} m outside the pit box; {st['n_modelled']} modelled hours, {st['n_not_modelled']} of {total_hours} not modelled.",
                    f"Media y percentil 99 horario en cuatro receptores hipoteticos a {p['receptors']['offset_m']:g} m del recuadro del pit; {st['n_modelled']} horas modeladas, {st['n_not_modelled']} de {total_hours} sin modelar.",
                ),
                kpi="receptor_concentration",
                y_axis=chartkit.axis("PM10 concentration", "Concentracion de PM10", "ug/m3"),
                categories=[{"id": rid, "label": bi(f"Receptor {en}", f"Receptor {es}")} for rid, en, es in RECEPTORS],
                series=[
                    chartkit.series("mean", bi("Mean over the record", "Media del registro"), None, mean),
                    chartkit.series("p99-hourly", bi("Hourly 99th percentile", "Percentil 99 horario"), None, p99),
                ],
            )
        )
        worst = int(np.argmax(mean))
        headline.append(
            {
                "kpi": "receptor_concentration",
                "name": f"PM10 mean at the most exposed hypothetical receptor ({RECEPTORS[worst][1]})",
                "unit": "ug/m3",
                "value": mean[worst],
                "note": f"mean over {st['n_modelled']} modelled hours of {p['wind']['period']}, stability class {s['stability_class']} assumed, hypothetical receptors (UNVERIFIED)",
            }
        )
        rows = [
            {"receptor": rid, "mean_ug_per_m3": m, "p99_hourly_ug_per_m3": q}
            for (rid, _, _), m, q in zip(RECEPTORS, mean, p99, strict=True)
        ]
        extra["wind"] = {
            "station": wind.station["id"],
            "name": wind.station["name"],
            "latitude": wind.station["latitude"],
            "longitude": wind.station["longitude"],
            "elevation_m": wind.station["elevation_m"],
            "period": p["wind"]["period"],
            "hours": wind.counts["hours"],
            "records": dict(wind.counts),
            "calm_percent": sig(100 * rose["calm_fraction"], 4),
            "variable_percent": sig(100 * rose["variable_fraction"], 4),
            "speed_median_m_s": sig(float(np.median(wind.speed_m_s)), 4),
            "good_quality_codes": list(p["wind"]["good_quality_codes"]),
            "modelled_hours": st["n_modelled"],
            "not_modelled_hours": st["n_not_modelled"],
            "unique_winds_evaluated": st["n_unique_winds"],
        }

    extra.update(
        {
            "inputs": inputs,
            "scenario": {
                k: s[k]
                for k in (
                    "size_class",
                    "silt_fraction",
                    "passes_per_hour_per_edge",
                    "release_height_m",
                    "receptor_height_m",
                    "stability_class",
                    "terrain",
                )
            },
            "road": {
                "length_m": sig(road_length, 6),
                "map_pieces": len(map_len),
                "receptor_pieces": len(rec_len),
                "total_emission_kg_per_s": sig(float(q_map.sum()), 6),
            },
            "reference": {k: (sig(v, 6) if isinstance(v, float) else v) for k, v in ref.items()},
            "minephys": f"minephys {version}",
            "assumptions": [
                "the scenario values (silt, passes per hour on every edge, release height, receptors) are illustrative and UNVERIFIED for the site",
                f"stability class {s['stability_class']} is assumed for every hour: GHCNh holds no insolation, so no hourly Pasquill class is derived",
                "the station anemometer height (10 m by the usual WMO siting) is UNVERIFIED and no height correction is applied",
                "GHCNh quality codes 1 and 5 are read as passed by the ISD convention; the documentation text of the codes could not be read (UNVERIFIED)",
                "steady wind, flat terrain, no plume rise, deposition or terrain wake: the pit walls are not modelled; screening, not AERMOD",
                "AP-42 equation 1a has no speed term, so no emission curve against speed is drawn",
            ],
            "water_use": "not computed: the water_use KPI needs the haulage schedule (spec 007) and a watering schedule",
        }
    )
    summary = {
        "title": "Haul-road dust: AP-42 PM10 emission factors and the Gaussian plume over the Bingham pit for real wind records",
        "label": LABEL,
        "methods": ["M16"],
        "verdict": "ok" if wind is not None else "partial",
        "headline": headline,
        "rows": rows,
        "extra": extra,
    }
    return {"summary": summary, "charts": charts}


def _receptors(box: tuple[float, float, float, float], offset: float) -> np.ndarray:
    x0, x1, y0, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    pts = {"r-n": (cx, y1 + offset), "r-e": (x1 + offset, cy), "r-s": (cx, y0 - offset), "r-w": (x0 - offset, cy)}
    return np.array([[i, *pts[rid]] for i, (rid, _, _) in enumerate(RECEPTORS)], dtype=float)


def write_outputs(result: Mapping[str, Any], out: Path) -> list[Path]:
    """Write results-summary.json and charts/*.json under `out`."""
    out.mkdir(parents=True, exist_ok=True)
    path = out / "results-summary.json"
    path.write_text(
        json.dumps(result["summary"], indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )
    return [path, *[chartkit.write(c, out / "charts") for c in result["charts"]]]


def stage(job: Mapping[str, Any]) -> dict[str, Any]:
    out = Path(job["output_dir"])
    root = Path(job.get("data_root") or os.environ["PITSTUDIO_DATA"])
    paths = write_outputs(compute(job["params"], root), out)
    return {"outputs": [{"path": p.relative_to(out).as_posix()} for p in paths]}


def main(argv: list[str] | None = None) -> int:
    import yaml

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--recipe", type=Path, required=True)
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    params = yaml.safe_load(a.recipe.read_text(encoding="utf-8"))["stages"][0]["params"]
    for path in write_outputs(compute(params, a.data_root), a.out):
        print(path.relative_to(a.out).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

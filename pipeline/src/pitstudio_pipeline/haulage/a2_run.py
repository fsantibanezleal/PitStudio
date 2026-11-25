"""Case A2 run (spec 007 FR-007-34 to FR-007-40, FR-018-16; plan 007 A2-U2): route energy, fuel and CO2e per tonne by drivetrain on the
real pit, as chart-series files and a results summary.

Entry (`python -m pitstudio_pipeline.haulage.a2_run --recipe studio/recipes/cases/a2.yaml --data-root DIR --out DIR`), CPU only.
From the recipe parameters it computes with `pitstudio.haulage.energy` (over `minephys.haulage`): (1) the energy of a straight
climb against its grade for diesel, trolley-assist and battery-electric trucks, and the diesel fuel and CO2e per tonne-kilometre;
(2) the same three drivetrains on the road route from the deepest bench to the pit exit in the road network of the A1 pit design
(the route is a path of design edges, so it cannot leave the network), with the saving of electrifying a share of the ramp length
and the energy the battery truck regenerates on the way down; (3) the least-energy grade-constrained A* route over the real
terrain model (3DEP 2018, averaged to the recipe's cell size) from the pit bottom to the pit exit for a sweep of the grade limit,
with its energy. Every constant (gravity, the four drivetrain efficiencies, the diesel lower heating value, the diesel CO2 factor) is
read from its `minephys` knowledge row (DC-001-01, DC-001-02 of minephys spec 001) with its citation, page and status; the recipe may
override one, and the constants table then says so. A route that does not exist at a grade limit is reported as such, never filled in.
"""
# ruff: noqa: E501, B007

from __future__ import annotations

import argparse
import heapq
import json
import math
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio.haulage.energy import route_energy
from pitstudio.haulage.network import douglas_peucker
from pitstudio.haulage.routing import Dem, NoFeasibleRoute, find_route
from pitstudio_pipeline import chartkit
from pitstudio_pipeline.haulage.honesty import BIAS_NOTE, LABEL

TOOL = "minephys"
METHOD = "wheel energy m g (RR + grade) L per segment, drivetrain efficiencies and regeneration, grade-constrained least-energy A*"
SERVES = ["FR-018-16", "FR-007-34", "FR-007-35"]
bi = chartkit.bi
DRIVETRAINS = ("diesel", "trolley", "bev")
DT_NAMES = {
    "diesel": ("Diesel", "Diesel"),
    "trolley": ("Trolley-assist", "Asistencia con trolley"),
    "bev": ("Battery-electric", "Electrico a bateria"),
}
CONSTANT_ROWS = [  # name, unit label, what it is
    ("g", "m/s2", "standard gravity"),
    ("diesel_co2_kg_per_m3", "kg/m3", "diesel combustion CO2 factor"),
    ("eta_diesel", "1", "marginal fuel-to-wheel efficiency of a diesel-electric truck"),
    ("fuel_energy_density_j_per_m3", "J/m3", "diesel lower heating value"),
    ("eta_electric", "1", "DC-bus-to-wheel efficiency of the electric drive (trolley-assisted truck)"),
    ("eta_drive", "1", "battery-to-wheel efficiency of a battery-electric truck"),
    ("eta_regen", "1", "wheel-to-battery electrical efficiency of regenerative braking"),
]


def constant_source(name: str, what: str, defaults: dict, consts: dict) -> tuple[str, str]:
    """(status, source note) of one constant: its knowledge row with citation, page and status, or the recipe override."""
    import minephys.knowledge as kn

    row = defaults[name]["row_id"]
    if name in consts:
        return "scenario input", f"{what}: recipe input that overrides the knowledge row {row}"
    r = kn.get_parameter(row)
    status = "verified table row" if r.verification == "verified" else "UNVERIFIED table row"
    return status, f"{what}: minephys knowledge row {row}, {r.citation}, {r.page}"


def sig(x: float | None, n: int = 6) -> float | None:
    return None if x is None else float(f"{x:.{n}g}")


def truck_of(p: dict, dt: str) -> dict:
    return {"empty_mass_t": p["truck"]["empty_mass_t"], "payload_t": p["truck"]["payload_t"], "drivetrain": dt}


def leg(route, p, dt, leg_name, consts, grid=None):
    return route_energy(route, truck_of(p, dt), leg=leg_name, constants=consts, grid_intensity_kg_per_j=grid)


def reverse(route):
    return [dict(s, grade_pct=-s["grade_pct"]) for s in reversed(route)]


def design_route(geo: dict, p: dict) -> tuple[list[dict], dict]:
    """The loaded route (uphill) from the deepest end node to the exit along the design network, as constant-grade segments."""
    feats = geo["features"]
    nodes = [f for f in feats if f["properties"]["kind"] == "node"]
    edges = [f for f in feats if f["properties"]["kind"] == "edge"]
    adj: dict[str, list[tuple[str, dict]]] = {}
    for e in edges:
        a, b = e["properties"]["from"], e["properties"]["to"]
        adj.setdefault(a, []).append((b, e))
        adj.setdefault(b, []).append((a, e))
    start = f"n{min(range(len(nodes)), key=lambda i: nodes[i]['geometry']['coordinates'][2])}"
    dist, prev, heap = {start: 0.0}, {}, [(0.0, start)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        for v, e in adj[u]:
            nd = d + e["properties"]["length_m"]
            if nd < dist.get(v, math.inf):
                dist[v], prev[v] = nd, (u, e)
                heapq.heappush(heap, (nd, v))
    path, cur = [], "n0"
    while cur != start:
        u, e = prev[cur]
        path.append((u, cur, e))
        cur = u
    path.reverse()  # deepest node to the exit: the loaded, uphill direction
    segs: list[dict] = []
    for u, v, e in path:
        pts = np.array(e["geometry"]["coordinates"], dtype=float)
        if e["properties"]["from"] != u:
            pts = pts[::-1]
        kept = douglas_peucker(pts, p["simplify_epsilon_m"])
        for i0, i1 in pairwise(kept):
            horiz = math.hypot(*(pts[i1][:2] - pts[i0][:2]))
            segs.append(
                {
                    "length_m": float(np.linalg.norm(pts[i1] - pts[i0])),
                    "grade_pct": 100.0 * float(pts[i1][2] - pts[i0][2]) / horiz,
                    "rr_pct": p["rr_pct"],
                    "trolley": False,
                    "class": e["properties"]["class"],
                }
            )
    info = {
        "start": start,
        "length_m": dist["n0"],
        "segments": len(segs),
        "ramp_length_m": sum(s["length_m"] for s in segs if s["class"] == "ramp"),
        "climb_m": float(nodes[0]["geometry"]["coordinates"][2] - nodes[int(start[1:])]["geometry"]["coordinates"][2]),
    }
    return segs, info


def coarse_dem(data_root: Path, p: dict) -> tuple[Dem, dict]:
    import zarr

    g = zarr.open(str(data_root / p["terrain_grid"]), mode="r")
    z, ok = np.asarray(g["elevation"][:], dtype=float), np.asarray(g["valid_mask"][:], dtype=bool)
    attrs = dict(g.attrs)
    k = int(p["cell_m"] / attrs["cell_size_m"])
    r, c = z.shape[0] // k, z.shape[1] // k
    zb = z[: r * k, : c * k].reshape(r, k, c, k).mean(axis=(1, 3))
    nodata = ~ok[: r * k, : c * k].reshape(r, k, c, k).all(axis=(1, 3))
    zb[nodata] = 0.0
    return Dem(zb, float(p["cell_m"]), nodata), {
        "x_min_m": attrs["x_min_m"],
        "y_max_m": attrs["y_max_m"],
        "cell_size_m": attrs["cell_size_m"],
        "source_ids": attrs.get("source_ids"),
        "epoch": attrs.get("epoch"),
        "project": attrs.get("project"),
    }


def reachable(dem: Dem, start: tuple[int, int], g_max: float) -> np.ndarray:
    """Cells a path of edges with |dz| / L <= g_max reaches from `start` (8-neighbour flood fill, no-data never entered)."""
    z, rows, cols = dem.z, dem.z.shape[0], dem.z.shape[1]
    seen = np.zeros(z.shape, dtype=bool)
    seen[start] = True
    stack = [start]
    while stack:
        r, c = stack.pop()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = r + dr, c + dc
                if (dr or dc) and 0 <= nr < rows and 0 <= nc < cols and not seen[nr, nc] and not dem.nodata[nr, nc]:
                    length = dem.cell_m * (math.sqrt(2.0) if dr and dc else 1.0)
                    if abs(float(z[nr, nc] - z[r, c])) / length <= g_max:
                        seen[nr, nc] = True
                        stack.append((nr, nc))
    return seen


def cells_to_segments(dem: Dem, cells, rr: float) -> list[dict]:
    out = []
    for (r0, c0), (r1, c1) in pairwise(cells):
        horiz = dem.cell_m * (math.sqrt(2.0) if r0 != r1 and c0 != c1 else 1.0)
        out.append(
            {
                "length_m": horiz,
                "grade_pct": 100.0 * float(dem.z[r1, c1] - dem.z[r0, c0]) / horiz,
                "rr_pct": rr,
                "trolley": False,
            }
        )
    return out


def compute(params: dict[str, Any], data_root: Path) -> dict[str, Any]:
    p = params["scenario"]
    consts = dict(params.get("constants") or {})  # optional overrides of the knowledge rows
    from pitstudio.haulage.energy import default_constants

    defaults = default_constants()
    effective = {n: consts.get(n, defaults[n]["value"]) for n, _, _ in CONSTANT_ROWS}
    geo = json.loads((data_root / params["inputs"]["road_network"]).read_text(encoding="utf-8"))
    from pitstudio.cases.d1.design_grid import minephys_identity

    version = minephys_identity()
    label = f"{LABEL}; known DES cycle-time bias, see the run summary"
    prod = chartkit.producer(TOOL, METHOD, version, label)
    charts: list[dict] = []
    ax = chartkit.axis
    grades = [float(g) for g in np.linspace(p["grade_min_pct"], p["grade_max_pct"], p["grade_n"])]

    def straight(g, rr, dt, trolley=True):
        return leg([{"length_m": 1000.0, "grade_pct": g, "rr_pct": rr, "trolley": trolley}], p, dt, "loaded", consts)

    # 1. fuel, energy and CO2e of a 1 km climb against the grade
    fuel_series = [
        chartkit.series(
            f"rr-{rr:g}".replace(".", "-"),
            bi(f"Rolling resistance {rr:g} %", f"Resistencia a la rodadura {rr:g} %"),
            grades,
            [sig(straight(g, rr, "diesel")["diesel_l_per_t_km"]["value"]) for g in grades],
        )
        for rr in p["rr_sweep_pct"]
    ]
    charts.append(
        chartkit.chart(
            "a2-fuel-vs-grade",
            "A2",
            "line",
            bi(
                "Diesel fuel per tonne-kilometre against grade",
                "Combustible diesel por tonelada-kilometro segun la pendiente",
            ),
            prod,
            SERVES,
            kpi="fuel_per_tkm",
            caption=bi(
                "Loaded climb of 1 km, diesel truck; basis: payload tonnes and along-road km. Constants: see the constants table.",
                "Subida cargada de 1 km, camion diesel; base: toneladas de carga util y km de camino. Constantes: ver la tabla de constantes.",
            ),
            x_axis=ax("Road grade", "Pendiente del camino", "%"),
            y_axis=ax("Diesel fuel", "Combustible diesel", "L/(t.km)"),
            series=fuel_series,
        )
    )
    energy_series = [
        chartkit.series(
            dt, bi(*DT_NAMES[dt]), grades, [sig(straight(g, p["rr_pct"], dt)["kwh_per_t"]["value"]) for g in grades]
        )
        for dt in DRIVETRAINS
    ]
    charts.append(
        chartkit.chart(
            "a2-energy-vs-grade",
            "A2",
            "line",
            bi(
                "Source energy per tonne-kilometre against grade",
                "Energia en la fuente por tonelada-kilometro segun la pendiente",
            ),
            prod,
            SERVES,
            caption=bi(
                f"Loaded climb of 1 km, rolling resistance {p['rr_pct']:g} %, all of it on the trolley line; the battery truck's figure is net of regeneration.",
                f"Subida cargada de 1 km, resistencia a la rodadura {p['rr_pct']:g} %, toda bajo linea de trolley; la cifra del camion a bateria es neta de regeneracion.",
            ),
            x_axis=ax("Road grade", "Pendiente del camino", "%"),
            y_axis=ax("Source energy", "Energia en la fuente", "kWh/(t.km)"),
            series=energy_series,
        )
    )
    co2 = [
        chartkit.series(
            "diesel",
            bi("Diesel", "Diesel"),
            grades,
            [sig(straight(g, p["rr_pct"], "diesel")["co2e_kg_per_t"]["value"]) for g in grades],
        )
    ]
    charts.append(
        chartkit.chart(
            "a2-co2-vs-grade",
            "A2",
            "line",
            bi("Diesel CO2e per tonne against grade", "CO2e del diesel por tonelada segun la pendiente"),
            prod,
            SERVES,
            kpi="co2e_per_tonne",
            caption=bi(
                "Loaded climb of 1 km, diesel truck. Electricity emissions need a grid intensity that has no default: none is shown for the other drivetrains.",
                "Subida cargada de 1 km, camion diesel. Las emisiones de la electricidad requieren una intensidad de red sin valor por defecto: no se muestran para los otros accionamientos.",
            ),
            x_axis=ax("Road grade", "Pendiente del camino", "%"),
            y_axis=ax("CO2e per payload tonne", "CO2e por tonelada de carga util", "kg/t"),
            series=co2,
        )
    )
    # 2. the design route: drivetrains and the trolley length
    loaded, info = design_route(geo, p)

    def trip(dt, route=loaded):
        up, down = leg(route, p, dt, "loaded", consts), leg(reverse(route), p, dt, "empty", consts)
        return up, down

    cats = [{"id": dt, "label": bi(*DT_NAMES[dt])} for dt in DRIVETRAINS]
    full = [dict(s, trolley=s["class"] == "ramp") for s in loaded]
    legs = {dt: trip(dt, full if dt == "trolley" else loaded) for dt in DRIVETRAINS}
    charts.append(
        chartkit.chart(
            "a2-drivetrain-energy",
            "A2",
            "bar",
            bi(
                "Energy per tonne by drivetrain on the pit road",
                "Energia por tonelada segun el accionamiento en el camino del pit",
            ),
            prod,
            SERVES,
            kpi="energy_per_tonne",
            caption=bi(
                f"Deepest bench to the exit, {info['length_m'] / 1000:.1f} km, loaded up and empty down; trolley on every ramp; battery figure net of regeneration.",
                f"Del banco mas profundo a la salida, {info['length_m'] / 1000:.1f} km, cargado subiendo y vacio bajando; trolley en toda rampa; cifra a bateria neta de regeneracion.",
            ),
            y_axis=ax("Source energy per payload tonne", "Energia en la fuente por tonelada de carga util", "kWh/t"),
            categories=cats,
            series=[
                chartkit.series(
                    "loaded",
                    bi("Loaded climb", "Subida cargada"),
                    None,
                    [sig(legs[dt][0]["kwh_per_t"]["value"]) for dt in DRIVETRAINS],
                ),
                chartkit.series(
                    "empty",
                    bi("Empty descent", "Bajada vacia"),
                    None,
                    [sig(legs[dt][1]["kwh_per_t"]["value"]) for dt in DRIVETRAINS],
                ),
                chartkit.series(
                    "round",
                    bi("Round trip", "Ciclo completo"),
                    None,
                    [sig(legs[dt][0]["kwh_per_t"]["value"] + legs[dt][1]["kwh_per_t"]["value"]) for dt in DRIVETRAINS],
                ),
            ],
        )
    )
    shares = [i / p["trolley_n"] for i in range(p["trolley_n"] + 1)]
    ramp_idx = [i for i, s in enumerate(loaded) if s["class"] == "ramp"]
    t_rows = []
    for sh in shares:
        target, cum, flags = sh * info["ramp_length_m"], 0.0, [False] * len(loaded)
        for i in ramp_idx:  # electrify the ramp from the pit bottom upward
            if cum < target - 1e-9:
                flags[i] = True
            cum += loaded[i]["length_m"]
        r = [dict(s, trolley=flags[i]) for i, s in enumerate(loaded)]
        u, d = trip("trolley", r)
        t_rows.append((u["diesel_kwh"] + d["diesel_kwh"], u["electric_kwh"] + d["electric_kwh"], u["payload_t"]))
    pl = p["truck"]["payload_t"]
    charts.append(
        chartkit.chart(
            "a2-trolley-length",
            "A2",
            "line",
            bi(
                "Diesel and line energy against the electrified ramp share",
                "Energia diesel y de linea segun la proporcion de rampa electrificada",
            ),
            prod,
            SERVES,
            caption=bi(
                "Round trip on the pit road; the ramp is electrified from the pit bottom upward. Descents draw nothing and regenerate nothing for a trolley truck.",
                "Ciclo completo en el camino del pit; la rampa se electrifica desde el fondo hacia arriba. Las bajadas no consumen ni regeneran en un camion con trolley.",
            ),
            x_axis=ax(
                "Share of the ramp length under the trolley line",
                "Proporcion de la rampa bajo la linea de trolley",
                "1",
            ),
            y_axis=ax("Energy per payload tonne", "Energia por tonelada de carga util", "kWh/t"),
            series=[
                chartkit.series(
                    "diesel", bi("From the tank", "Del estanque"), shares, [sig(d / pl) for d, e, _ in t_rows]
                ),
                chartkit.series(
                    "line", bi("From the line", "De la linea"), shares, [sig(e / pl) for d, e, _ in t_rows]
                ),
                chartkit.series(
                    "total",
                    bi("Total at the source", "Total en la fuente"),
                    shares,
                    [sig((d + e) / pl) for d, e, _ in t_rows],
                ),
            ],
        )
    )
    # 3. A* over the real terrain
    dem, grid = coarse_dem(data_root, p["a_star"])
    low = np.where(dem.nodata, np.inf, dem.z)
    start = tuple(int(i) for i in np.unravel_index(int(np.argmin(low)), low.shape))
    nodes = [f for f in geo["features"] if f["properties"]["kind"] == "node"]
    ex, ey, _ = nodes[0]["geometry"]["coordinates"]
    exit_cell = (int((grid["y_max_m"] - ey) / dem.cell_m), int((ex - grid["x_min_m"]) / dem.cell_m))
    gmaxes = [float(g) for g in p["a_star"]["g_max_sweep"]]
    exit_z = float(dem.z[exit_cell])
    mass_kg = (p["truck"]["empty_mass_t"] + p["truck"]["payload_t"]) * 1000.0
    goal, goal_limit = None, None
    for gm in sorted(
        gmaxes
    ):  # the goal: the cell nearest the design exit, no lower than it, that the tightest limit reaching any such cell reaches
        cand = np.argwhere(reachable(dem, start, gm) & (dem.z >= exit_z))
        if len(cand):
            d2 = (cand[:, 0] - exit_cell[0]) ** 2 + (cand[:, 1] - exit_cell[1]) ** 2
            goal, goal_limit = tuple(int(i) for i in cand[int(np.argmin(d2))]), gm
            break
    if goal is None:
        goal = exit_cell
    a_rows, lens, a_found = [], [], []
    for gm in gmaxes:
        res = find_route(dem, start, goal, mass_kg=mass_kg, rr_pct=p["rr_pct"], g_max=gm, eta=effective["eta_diesel"])
        if isinstance(res, NoFeasibleRoute):
            a_rows.append([f"{gm * 100:g}", "no feasible route", None, None, None, None, None])
            lens.append(None)
            continue
        segs = cells_to_segments(dem, res.cells, p["rr_pct"])
        up = leg(segs, p, "diesel", "loaded", consts)
        bev_up, bev_down = leg(segs, p, "bev", "loaded", consts), leg(reverse(segs), p, "bev", "empty", consts)
        length = sum(s["length_m"] for s in segs)
        lens.append(length / 1000.0)
        a_found.append(gm)
        a_rows.append(
            [
                f"{gm * 100:g}",
                "route",
                sig(length / 1000.0, 4),
                sig(float(dem.z[goal] - dem.z[start]), 4),
                sig(max(abs(s["grade_pct"]) for s in segs), 4),
                sig(up["kwh_per_t"]["value"], 4),
                sig(bev_up["kwh_per_t"]["value"] + bev_down["kwh_per_t"]["value"], 4),
            ]
        )
    ok = [(g * 100, lv) for g, lv in zip(gmaxes, lens, strict=True) if lv is not None]
    if ok:
        charts.append(
            chartkit.chart(
                "a2-route-length-vs-gmax",
                "A2",
                "line",
                bi(
                    "Least-energy route length against the grade limit",
                    "Largo de la ruta de minima energia segun el limite de pendiente",
                ),
                prod,
                SERVES,
                caption=bi(
                    f"A* over the real terrain model averaged to {p['a_star']['cell_m']:g} m cells, pit bottom to the design exit; limits with no feasible route are absent.",
                    f"A* sobre el modelo de terreno real promediado a celdas de {p['a_star']['cell_m']:g} m, del fondo del pit a la salida del diseno; los limites sin ruta factible no aparecen.",
                ),
                x_axis=ax("Grade limit", "Limite de pendiente", "%"),
                y_axis=ax("Route length", "Largo de la ruta", "km"),
                series=[
                    chartkit.series(
                        "length",
                        bi("Least-energy route", "Ruta de minima energia"),
                        [g for g, _ in ok],
                        [sig(lv, 5) for _, lv in ok],
                        draw="points",
                    )
                ],
            )
        )
    cols = [
        {"id": "limit", "label": bi("Grade limit", "Limite de pendiente"), "type": "text"},
        {"id": "status", "label": bi("Result", "Resultado"), "type": "text"},
        {"id": "km", "label": bi("Length", "Largo"), "type": "number", "unit": "km"},
        {"id": "dz", "label": bi("Net climb", "Ascenso neto"), "type": "number", "unit": "m"},
        {"id": "steepest", "label": bi("Steepest edge", "Arista mas empinada"), "type": "number", "unit": "%"},
        {
            "id": "diesel",
            "label": bi("Diesel loaded climb", "Diesel subida cargada"),
            "type": "number",
            "unit": "kWh/t",
        },
        {"id": "bev", "label": bi("Battery round trip", "Bateria ciclo completo"), "type": "number", "unit": "kWh/t"},
    ]
    charts.append(
        chartkit.chart(
            "a2-route-table",
            "A2",
            "table",
            bi("Least-energy routes over the real terrain", "Rutas de minima energia sobre el terreno real"),
            prod,
            SERVES,
            caption=bi(
                "Energy per payload tonne of the A* route at each grade limit (source energy; battery figure net of regeneration). A route over terrain is not a designed road.",
                "Energia por tonelada de carga util de la ruta A* por limite (energia en la fuente; bateria neta de regeneracion). Una ruta sobre el terreno no es un camino disenado.",
            ),
            table={"columns": cols, "rows": a_rows},
        )
    )
    # 4. the assumptions
    arows, notes = [], []
    for name, unit, what in CONSTANT_ROWS:
        status, note = constant_source(name, what, defaults, consts)
        arows.append([name, sig(effective[name], 8), unit, status, note[:190]])
        notes.append(note)
    acols = [
        {"id": "constant", "label": bi("Constant", "Constante"), "type": "text"},
        {"id": "value", "label": bi("Value", "Valor"), "type": "number", "unit": "as listed"},
        {"id": "unit", "label": bi("Unit", "Unidad"), "type": "text"},
        {"id": "status", "label": bi("Status", "Estado"), "type": "text"},
        {"id": "source", "label": bi("Source", "Fuente"), "type": "text"},
    ]
    charts.append(
        chartkit.chart(
            "a2-assumptions",
            "A2",
            "table",
            bi("Constants and their status", "Constantes y su estado"),
            prod,
            SERVES,
            caption=bi(
                "Every constant, read from its minephys knowledge row with citation and page. The efficiencies are parameters of one published truck model, not measurements of this fleet.",
                "Cada constante, leida de su fila de minephys con cita y pagina. Las eficiencias son parametros de un modelo publicado de camion, no mediciones de esta flota.",
            ),
            table={"columns": acols, "rows": arows},
        )
    )
    # headline: the diesel baseline on the pit road
    up, down = legs["diesel"]
    round_kwh = up["kwh_per_t"]["value"] + down["kwh_per_t"]["value"]
    round_co2 = up["co2e_kg_per_t"]["value"] + down["co2e_kg_per_t"]["value"]
    km = up["road_km"] + down["road_km"]
    fuel = (
        up["diesel_l_per_t_km"]["value"] * up["road_km"] + down["diesel_l_per_t_km"]["value"] * down["road_km"]
    ) / km
    where = f"diesel truck, deepest bench to the exit and back ({km:.1f} km), payload {pl:g} t, rolling resistance {p['rr_pct']:g} %"
    tag = "constants are minephys knowledge rows (the efficiencies are parameters of one published truck model); calibrated synthetic, not validated against real data"
    headline = [
        {
            "kpi": "fuel_per_tkm",
            "name": "Diesel fuel per tonne-kilometre",
            "unit": "L/(t.km)",
            "value": sig(fuel, 5),
            "note": f"{where}; basis payload tonnes and along-road km; {tag}",
        },
        {
            "kpi": "energy_per_tonne",
            "name": "Diesel source energy per tonne",
            "unit": "kWh/t",
            "value": sig(round_kwh, 5),
            "note": f"{where}; {tag}",
        },
        {
            "kpi": "co2e_per_tonne",
            "name": "Diesel CO2e per tonne",
            "unit": "kg/t",
            "value": sig(round_co2, 5),
            "note": f"{where}; the diesel CO2 factor is a verified table row; {tag}",
        },
    ]
    e_rows = []
    for dt in DRIVETRAINS:
        u, d = legs[dt]
        e_rows.append(
            {
                "drivetrain": dt,
                "loaded_kwh_per_t": sig(u["kwh_per_t"]["value"], 6),
                "empty_kwh_per_t": sig(d["kwh_per_t"]["value"], 6),
                "regenerated_kwh": sig(u["regen_kwh"] + d["regen_kwh"], 6),
                "unverified_rows": sorted({*u["unverified_rows"], *d["unverified_rows"]}),
            }
        )
    diesel_total = round_kwh
    saved = {
        dt: sig(
            100.0
            * (1.0 - (legs[dt][0]["source_kwh"] + legs[dt][1]["source_kwh"]) / (up["source_kwh"] + down["source_kwh"])),
            4,
        )
        for dt in ("trolley", "bev")
    }
    summary = {
        "title": "Haul-road energy by drivetrain on the Bingham pit road: diesel, trolley-assist and battery-electric trucks",
        "label": f"{LABEL}. {BIAS_NOTE}",
        "methods": ["M6"],
        "verdict": "ok",
        "headline": headline,
        "rows": e_rows,
        "extra": {
            "route": {
                "start": info["start"],
                "length_km": sig(info["length_m"] / 1000.0, 5),
                "segments": info["segments"],
                "ramp_length_km": sig(info["ramp_length_m"] / 1000.0, 5),
                "climb_m": sig(info["climb_m"], 5),
            },
            "source_energy_saving_vs_diesel_percent": saved,
            "a_star": {
                "cell_m": p["a_star"]["cell_m"],
                "start_cell": list(start),
                "goal_cell": list(goal),
                "design_exit_cell": list(exit_cell),
                "goal_limit": goal_limit,
                "goal_note": "the cell of the design exit lies on terrain that the tight limits do not reach from the pit bottom; the goal is the cell nearest the exit, no lower than it, that the tightest limit reaching any such cell reaches (the relation of that cell to the real pit exit has not been checked)",
                "grade_limits_with_a_route": a_found,
                "terrain": {k: grid[k] for k in ("source_ids", "epoch", "project")},
            },
            "truck": p["truck"],
            "constants": effective,
            "constant_rows": {n: defaults[n]["row_id"] for n, _, _ in CONSTANT_ROWS},
            "minephys": f"minephys {version}",
            "diesel_round_trip_kwh_per_t": sig(diesel_total, 6),
            "co2e_note": "kg CO2e per tonne is shown for diesel only: the emissions of electricity need a grid intensity that has no default and none was supplied",
            "assumptions": notes
            + [
                "the truck masses are those of the engine catalog class CAT_793F (public specification magnitudes)",
                "rolling resistance (swept) and the trolley layout are illustrative scenario assumptions, not measurements of this pit",
                "the A* route is a least-energy path over the terrain model, not a designed road; the design route follows the road network of the A1 pit design",
                BIAS_NOTE,
            ],
        },
    }
    return {"summary": summary, "charts": charts}


def write_outputs(result: dict, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    path = out / "results-summary.json"
    path.write_text(
        json.dumps(result["summary"], indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )
    return [path, *[chartkit.write(c, out / "charts") for c in result["charts"]]]


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

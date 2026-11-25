"""Case A1 run (spec 007 FR-007-17, FR-007-18, FR-018-16; plan 007 A1-U3): the fleet-size and dispatcher sweep of the discrete-event
haulage reference engine over the road network of the A1 pit design, and the DES-versus-exact-MVA throughput gap, as chart-series
files and a results summary.

Entry (`python -m pitstudio_pipeline.haulage.a1_run --recipe studio/recipes/cases/a1.yaml --data-root DIR --out DIR`), CPU only.
From the recipe parameters it (1) turns the road network of the pit design (ramps and bench roads, `road-network.geojson` of
spec 004) into a scenario bundle: every polyline is cut with Douglas-Peucker into straight segments of constant grade, the
declared loader faces sit on bench-road ends and the crusher at the pit exit; (2) runs one 8 h shift of the pinned `minehaulsim`
engine through the adapter for every (dispatcher, fleet size, seed) in traffic mode with the `engine` variate profile and
computes the KPIs of the KPI layer; (3) runs the single-loader oracle family under the same profile against exact mean-value
analysis. Every number is the engine's or the KPI layer's; the cycle times are calibrated synthetic, the engine's class
parameters are class-representative and not OEM-exact, and the speed limits and the rolling resistance are illustrative
(UNVERIFIED). No dispatch verdict is made: no learned dispatcher exists in this build and the comparison is descriptive.
"""
# ruff: noqa: E501, B007

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import statistics
from concurrent.futures import ProcessPoolExecutor
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from pitstudio.haulage.network import douglas_peucker
from pitstudio_pipeline import chartkit
from pitstudio_pipeline.haulage import oracles
from pitstudio_pipeline.haulage.adapter import run_shift
from pitstudio_pipeline.haulage.honesty import BIAS_NOTE, LABEL
from pitstudio_pipeline.haulage.pin import load_pin
from pitstudio_pipeline.haulage.scenario import _catalog_loader, _catalog_truck

TOOL = "minehaulsim"
METHOD = "seeded discrete-event haulage simulation, counter-based Philox variates, traffic mode, pit road network; exact MVA oracle"
SERVES = ["FR-018-16", "FR-007-17", "FR-007-18"]
bi = chartkit.bi
DISPATCHERS = ("fixed", "nearest", "sptf", "sq", "min-idle")
NAMES = {
    "fixed": ("Fixed", "Fijo"),
    "nearest": ("Nearest", "Mas cercano"),
    "sptf": ("SPTF", "SPTF"),
    "sq": ("Shortest queue", "Cola mas corta"),
    "min-idle": ("Min idle", "Min ocio"),
}
T95 = 0.975


def sig(x: float, n: int = 6) -> float:
    return float(f"{x:.{n}g}") if x == x and math.isfinite(x) else x


def design_bundle(geojson: dict, p: dict, n_trucks: int, dispatcher: str) -> dict:
    """The scenario bundle of the pit design network with `n_trucks` trucks (bundle schema DC-007-01)."""
    feats = geojson["features"]
    nodes_in = [f for f in feats if f["properties"]["kind"] == "node"]
    edges_in = [f for f in feats if f["properties"]["kind"] == "edge"]
    loader_ids = {int(k[1:]): v for k, v in p["loaders"].items()}  # design node index -> declared dump index
    dump_ids = [int(k[1:]) for k in p["dumps"]]
    kinds = {i: "waypoint" for i in range(len(nodes_in))}
    for i in loader_ids:
        kinds[i] = "face"
    for k, i in enumerate(dump_ids):
        kinds[i] = "crusher" if k == 0 else "dump"
    nodes = {
        i + 1: {"id": i + 1, "kind": kinds[i], "pos_m": [float(c) for c in nodes_in[i]["geometry"]["coordinates"]]}
        for i in range(len(nodes_in))
    }
    nid = len(nodes_in) + 1
    segments: list[dict] = []
    for e in edges_in:
        a, b = int(e["properties"]["from"][1:]) + 1, int(e["properties"]["to"][1:]) + 1
        pts = np.array(e["geometry"]["coordinates"], dtype=float)
        kept = douglas_peucker(pts, p["simplify_epsilon_m"])
        ids = [a]
        for k in kept[1:-1]:
            nodes[nid] = {"id": nid, "kind": "waypoint", "pos_m": pts[k].tolist()}
            ids.append(nid)
            nid += 1
        ids.append(b)
        speed = p["speed_limit_kmh"][e["properties"]["class"]]
        for (i0, i1), (u, v) in zip(pairwise(kept), pairwise(ids), strict=True):
            pa, pb = pts[i0], pts[i1]
            horiz = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
            segments.append(
                {
                    "id": len(segments) + 1, "a": u, "b": v, "polyline_m": [pa.tolist(), pb.tolist()],
                    "length_m": round(float(np.linalg.norm(pb - pa)), 3), "grade_pct": 100.0 * (pb[2] - pa[2]) / horiz,
                    "width_class": 2, "one_way": False, "speed_limit_kmh": speed,
                    "rolling_resistance_pct": p["rolling_resistance_pct"], "zone_id": None, "single_lane_op": False,
                }
            )  # fmt: skip
    truck, loader = p["truck_class"], p["loader_class"]
    loaders = [
        {"node": i + 1, "loader_class": loader, "n_spots": 1, "destination_dump": dump_ids[d] + 1}
        for i, d in sorted(loader_ids.items())
    ]
    return {
        "schema_version": "1.0", "id": f"a1-pit-{dispatcher}-n{n_trucks}",
        "description": "A1 pit design road network, three loader faces, a crusher and a waste dump.", "live": n_trucks <= 40,
        "mode": "traffic", "horizon_s": p["horizon_s"], "kpi_window": {"warmup_s": p["warmup_s"]},
        "network": {"nodes": [nodes[k] for k in sorted(nodes)], "segments": segments, "zones": [], "junctions": []},
        "equipment": {"truck_classes": [_catalog_truck(truck)], "loader_classes": [_catalog_loader(loader)]},
        "fleet": [{"id": k + 1, "truck_class": truck, "start_loader": loaders[k % len(loaders)]["node"]} for k in range(n_trucks)],
        "loaders": loaders, "dumps": [d + 1 for d in dump_ids], "dispatcher": {"id": dispatcher}, "variate_profile": "engine",
        "quantile_tables": oracles._tables("engine"), "engine_constants": dict(oracles.ENGINE_CONSTANTS), "failures": None,
    }  # fmt: skip


def _one(args: tuple[str, int, int]) -> dict:
    path, seed, _ = args
    k = run_shift(Path(path), seed=seed).kpis
    f = k["fleet"]
    return {
        "tph": f["production_tph"], "queue_min": f["queue_loader_min"]["mean"], "dump_queue_min": f["queue_dump_min"]["mean"],
        "match": f["match_factor"], "util": f["loader_utilisation"], "truck_h_kt": f["truck_h_per_kt"], "cycles": f["cycles"],
    }  # fmt: skip


def _summ(values: list[float | None]) -> dict[str, float | None]:
    xs = [v for v in values if v is not None]
    if len(xs) < 2:
        return {"mean": xs[0] if xs else None, "lo": None, "hi": None, "n": len(xs)}
    m, s = statistics.fmean(xs), statistics.stdev(xs)
    h = float(stats.t.ppf(T95, len(xs) - 1)) * s / math.sqrt(len(xs))
    return {"mean": m, "lo": m - h, "hi": m + h, "n": len(xs)}


def compute(params: dict[str, Any], data_root: Path, work: Path, workers: int) -> dict[str, Any]:
    p = params["scenario"]
    sw = params["sweep"]
    geo = json.loads((data_root / params["inputs"]["road_network"]).read_text(encoding="utf-8"))
    seeds = list(range(sw["seeds"]))
    work.mkdir(parents=True, exist_ok=True)
    jobs, paths = [], {}
    for d in sw["dispatchers"]:
        for n in sw["fleet_sizes"]:
            b = design_bundle(geo, p, n, d)
            path = work / f"{d}-{n}.json"
            path.write_text(json.dumps(b), encoding="utf-8")
            paths[d, n] = path
            jobs += [(str(path), s, 0) for s in seeds]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        res = list(pool.map(_one, jobs, chunksize=4))
    table: dict[tuple[str, int], list[dict]] = {}
    for (d, n), path in paths.items():
        table[d, n] = res[: len(seeds)]
        res = res[len(seeds) :]
    # the single-loader oracle family
    fam = params["family"]
    fam_jobs, fam_paths = [], {}
    for n in fam["fleet_sizes"]:
        b = oracles.exponential_family_bundle(n, profile="engine", horizon_s=fam["horizon_s"], warmup_s=fam["warmup_s"])
        path = work / f"family-{n}.json"
        path.write_text(json.dumps(b), encoding="utf-8")
        fam_paths[n] = (path, b)
        fam_jobs += [(str(path), s, 0) for s in range(fam["seeds"])]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        fres = list(pool.map(_one, fam_jobs, chunksize=4))
    family = {}
    for n, (path, b) in fam_paths.items():
        rows, fres = fres[: fam["seeds"]], fres[fam["seeds"] :]
        load_s, dump_s = oracles.family_services_s(b)
        family[n] = {
            "des": _summ([r["cycles"] / ((fam["horizon_s"] - fam["warmup_s"]) / 3600.0) for r in rows]),
            "mva": oracles.exact_mva(n, [load_s, dump_s], oracles.family_delay_s(b)) * 3600.0,
        }
    return build_outputs(params, geo, table, family, work)


def build_outputs(params: dict, geo: dict, table: dict, family: dict, work: Path) -> dict[str, Any]:
    sw, p = params["sweep"], params["scenario"]
    import minehaulsim

    pin = load_pin()
    from pitstudio.cases.d1.design_grid import minephys_identity

    version = f"{minehaulsim.__version__}+mp{minephys_identity()}"
    assert version.startswith(pin["version"])
    label = f"{LABEL}; known DES cycle-time bias, see the run summary"
    prod = chartkit.producer(TOOL, METHOD, version, label)
    sizes, disp = sw["fleet_sizes"], sw["dispatchers"]
    agg = {
        (d, n): {k: _summ([r[k] for r in table[d, n]]) for k in ("tph", "queue_min", "match", "util", "truck_h_kt")}
        for d in disp
        for n in sizes
    }
    charts = []

    def line(cid, title, kpi, key, y_en, y_es, unit, cap_en, cap_es, picked=disp):
        ser = []
        for d in picked:
            a = [agg[d, n][key] for n in sizes]
            ser.append(
                chartkit.series(
                    f"{d}",
                    bi(*NAMES[d]),
                    sizes,
                    [sig(x["mean"]) if x["mean"] is not None else None for x in a],
                    n=sw["seeds"],
                    lo=[sig(x["lo"]) if x["lo"] is not None else None for x in a],
                    hi=[sig(x["hi"]) if x["hi"] is not None else None for x in a],
                    band_label=bi(
                        f"95 % interval over {sw['seeds']} seeds (Student t)",
                        f"Intervalo de 95 % sobre {sw['seeds']} semillas (t de Student)",
                    ),
                )
            )
        return chartkit.chart(
            cid,
            "A1",
            "line",
            title,
            prod,
            SERVES,
            caption=bi(cap_en, cap_es),
            kpi=kpi,
            x_axis=chartkit.axis("Trucks in the fleet", "Camiones en la flota", "1"),
            y_axis=chartkit.axis(y_en, y_es, unit),
            series=ser,
        )

    shift = f"{p['horizon_s'] / 3600:g} h shift, first {p['warmup_s'] / 3600:g} h discarded"
    common_en = f"Calibrated synthetic DES, {shift}, three loader faces on the pit road network, traffic mode."
    common_es = f"DES sintetico calibrado, turno de {p['horizon_s'] / 3600:g} h (primeras {p['warmup_s'] / 3600:g} h descartadas), tres frentes en la red del pit, modo trafico."
    charts.append(
        line(
            "a1-throughput-vs-fleet",
            bi("Throughput against fleet size", "Rendimiento segun el tamano de la flota"),
            "throughput",
            "tph",
            "Throughput",
            "Rendimiento",
            "t/h",
            common_en,
            common_es,
        )
    )
    charts.append(
        line(
            "a1-queue-vs-fleet",
            bi(
                "Queue time at the loaders against fleet size",
                "Tiempo en cola en las palas segun el tamano de la flota",
            ),
            "queue_time",
            "queue_min",
            "Mean queue time at the loaders",
            "Tiempo medio en cola en las palas",
            "min",
            common_en,
            common_es,
        )
    )
    charts.append(
        line(
            "a1-match-factor-vs-fleet",
            bi("Match factor against fleet size", "Factor de acoplamiento segun el tamano de la flota"),
            "match_factor",
            "match",
            "Match factor",
            "Factor de acoplamiento",
            "1",
            common_en[:-1] + "; 1 means balanced.",
            common_es[:-1] + "; 1 es equilibrio.",
            picked=("sptf", "fixed"),
        )
    )
    charts.append(
        line(
            "a1-utilisation-vs-fleet",
            bi("Loader utilisation against fleet size", "Utilizacion de las palas segun el tamano de la flota"),
            None,
            "util",
            "Loader utilisation",
            "Utilizacion de las palas",
            "1",
            common_en,
            common_es,
        )
    )
    charts.append(
        line(
            "a1-hours-per-kt",
            bi(
                "Truck-hours per kilotonne against fleet size",
                "Horas-camion por kilotonelada segun el tamano de la flota",
            ),
            None,
            "truck_h_kt",
            "Truck-hours per kilotonne",
            "Horas-camion por kilotonelada",
            "h/kt",
            "Truck-hours per kilotonne, 8 h shift, traffic mode. Cost per tonne is not computed: no hourly rate was supplied.",
            "Horas-camion por kilotonelada, turno de 8 h, modo trafico. El costo por tonelada no se calcula: no hay tarifas horarias.",
        )
    )
    # DES versus MVA
    ns = sorted(family)
    f = [family[n] for n in ns]
    charts.append(
        chartkit.chart(
            "a1-des-vs-mva",
            "A1",
            "line",
            bi("Simulation against exact queueing theory", "Simulacion contra teoria de colas exacta"),
            prod,
            SERVES,
            caption=bi(
                f"One loader, one dump, one flat 1.5 km route, engine profile, traffic mode, {params['family']['seeds']} seeds. The gap to exponential-station theory is a result, not a check.",
                f"Una pala, un botadero, una ruta plana de 1,5 km, perfil del motor, modo trafico, {params['family']['seeds']} semillas. La brecha con la teoria exponencial es un resultado, no una verificacion.",
            ),
            x_axis=chartkit.axis("Trucks in the fleet", "Camiones en la flota", "1"),
            y_axis=chartkit.axis("Fleet cycle rate", "Ciclos de la flota", "cycles/h"),
            series=[
                chartkit.series(
                    "des",
                    bi("Simulation (engine profile)", "Simulacion (perfil del motor)"),
                    ns,
                    [sig(x["des"]["mean"]) for x in f],
                    n=params["family"]["seeds"],
                    lo=[sig(x["des"]["lo"]) for x in f],
                    hi=[sig(x["des"]["hi"]) for x in f],
                    band_label=bi(
                        "95 % interval over the seeds (Student t)",
                        "Intervalo de 95 % sobre las semillas (t de Student)",
                    ),
                ),
                chartkit.series(
                    "mva",
                    bi("Exact mean-value analysis", "Analisis de valor medio exacto"),
                    ns,
                    [sig(x["mva"]) for x in f],
                ),
            ],
        )
    )
    # dispatcher comparison table at three fleet sizes
    picks = [n for n in sw["table_sizes"] if n in sizes]
    cols = [
        {"id": "dispatcher", "label": bi("Dispatcher", "Despacho"), "type": "text"},
        {"id": "trucks", "label": bi("Trucks", "Camiones"), "type": "number", "unit": "1"},
    ]
    cols += [
        {"id": "tph", "label": bi("Throughput", "Rendimiento"), "type": "number", "unit": "t/h"},
        {"id": "half", "label": bi("95 % half-width", "Semiancho al 95 %"), "type": "number", "unit": "t/h"},
        {"id": "queue", "label": bi("Queue time", "Tiempo en cola"), "type": "number", "unit": "min"},
    ]
    rows = []
    for n in picks:
        for d in disp:
            a = agg[d, n]
            rows.append(
                [
                    NAMES[d][0],
                    n,
                    sig(a["tph"]["mean"], 5),
                    sig((a["tph"]["hi"] - a["tph"]["lo"]) / 2, 3),
                    sig(a["queue_min"]["mean"], 4),
                ]
            )
    charts.append(
        chartkit.chart(
            "a1-dispatcher-table",
            "A1",
            "table",
            bi("Dispatchers compared at three fleet sizes", "Despachos comparados en tres tamanos de flota"),
            prod,
            SERVES,
            caption=bi(
                f"Mean of {sw['seeds']} seeds with the 95 % Student-t half-width. No verdict: no learned dispatcher or paired rule in this build; an interval holding another mean is no difference.",
                f"Media de {sw['seeds']} semillas con semiancho de 95 % (t de Student). Sin veredicto: no hay despacho aprendido ni regla pareada; un intervalo que contiene otra media no es diferencia.",
            ),
            table={"columns": cols, "rows": rows},
        )
    )
    # headline: the peak of the mean throughput over every dispatcher and fleet size
    best = max(((d, n) for d in disp for n in sizes), key=lambda k: agg[k]["tph"]["mean"])
    a = agg[best]
    half = (a["tph"]["hi"] - a["tph"]["lo"]) / 2
    where = f"{NAMES[best[0]][0]} dispatch, {best[1]} trucks, {sw['seeds']} seeds, {shift}"
    headline = [
        {
            "kpi": "throughput",
            "name": "Peak mean throughput",
            "unit": "t/h",
            "value": sig(a["tph"]["mean"], 5),
            "note": f"{where}; 95 % half-width {half:.0f} t/h; calibrated synthetic, not validated against real data",
        },
        {
            "kpi": "queue_time",
            "name": "Mean queue time at the loaders at the peak",
            "unit": "min",
            "value": sig(a["queue_min"]["mean"], 4),
            "note": f"{where}",
        },
        {
            "kpi": "match_factor",
            "name": "Match factor at the peak",
            "unit": "1",
            "value": sig(a["match"]["mean"], 4),
            "note": f"{where}; 1 means balanced",
        },
    ]
    summary = {
        "title": "Fleet size and dispatch rule on the Bingham pit road network: throughput, queueing and the gap to exact queueing theory",
        "label": f"{LABEL}. {BIAS_NOTE}",
        "methods": ["M1", "M2"],
        "verdict": "ok",
        "headline": headline,
        "rows": [
            {
                "dispatcher": d,
                "trucks": n,
                "throughput_tph": sig(agg[d, n]["tph"]["mean"], 6),
                "queue_min": sig(agg[d, n]["queue_min"]["mean"], 5),
                "match_factor": sig(agg[d, n]["match"]["mean"], 5),
                "seeds": agg[d, n]["tph"]["n"],
            }
            for d in disp
            for n in sizes
        ],
        "extra": {
            "scenario": {
                k: p[k]
                for k in (
                    "horizon_s",
                    "warmup_s",
                    "truck_class",
                    "loader_class",
                    "rolling_resistance_pct",
                    "speed_limit_kmh",
                    "simplify_epsilon_m",
                )
            },
            "network": {
                "nodes": sum(1 for f in geo["features"] if f["properties"]["kind"] == "node"),
                "design_edges": sum(1 for f in geo["features"] if f["properties"]["kind"] == "edge"),
            },
            "engine": f"minehaulsim {version}",
            "variate_profile": "engine",
            "mode": "traffic",
            "seeds": sw["seeds"],
            "fleet_sizes": sizes,
            "dispatchers": list(disp),
            "cost_per_tonne": "not computed: no truck or loader hourly rate was supplied and none has a source (FR-007-08)",
            "assumptions": [
                "the engine's truck and loader classes are class-representative public-specification magnitudes, not OEM-exact (minehaulsim catalog)",
                "speed limits per road class and the rolling resistance of the roads are illustrative and UNVERIFIED for the site",
                "three loader faces on bench-road ends at three depths, a crusher at the pit exit and a waste dump near the rim; destinations are declared per loader",
                "traffic mode: per-segment slots, no-overtake headway and FIFO queues; no junction or direction-zone constraint is declared; no breakdowns",
                "the dispatchers are the engine's own policies and PitStudio's min-idle; no learned dispatcher exists in this build, so no verdict is made",
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
    ap.add_argument("--work", type=Path, required=True, help="scratch folder for the bundles (removed afterwards)")
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    a = ap.parse_args(argv)
    params = yaml.safe_load(a.recipe.read_text(encoding="utf-8"))["stages"][0]["params"]
    try:
        result = compute(params, a.data_root, a.work, a.workers)
    finally:
        shutil.rmtree(a.work, ignore_errors=True)
    for path in write_outputs(result, a.out):
        print(path.relative_to(a.out).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

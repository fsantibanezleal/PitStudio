"""Case B1 run (spec 018 FR-018-55, FR-018-16; docs M20): mixed autonomous and manned traffic on the road network of the A1 pit
design, the time to collision of every close pair, near-misses and throughput against the share of autonomous haul trucks and
the number of manned light vehicles, as chart-series files and a results summary.

Entry (`python -m pitstudio_pipeline.haulage.b1_run --recipe studio/recipes/cases/b1.yaml --data-root DIR --out DIR --work DIR`),
CPU only. For every seed one shift of the pinned `minehaulsim` engine runs through the adapter in traffic mode (the A1 pit
network bundle, `a1_run.design_bundle`) with the leg recorder of `legs.py`; the trucks of that shift are then replayed in the
traffic layer of `traffic.py` for every (autonomous share, number of light vehicles): the same engine seed gives every scenario
the same truck variates (paired seeds). Every number is the engine's or the traffic layer's. Behaviour is rule-based and
parameterised: the footprints, the lane offset, the manned reaction time and the decelerations come from cited sources (`INPUT_ROWS`
gives each with its page or table); the autonomous reaction time, the accelerations, the yielding thresholds and the light-vehicle
patrol are UNVERIFIED for any site; no proximity or incident data exists to calibrate or validate them. Vehicles are bodies with
their real footprints that never overlap: an overlap is a collision event, counted and reported, never a TTC of 0. Calibrated synthetic.
"""
# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from pitstudio.haulage.ttc import near_misses_per_1000h
from pitstudio_pipeline import chartkit
from pitstudio_pipeline.haulage import traffic as T
from pitstudio_pipeline.haulage.a1_run import design_bundle
from pitstudio_pipeline.haulage.honesty import BIAS_NOTE, LABEL
from pitstudio_pipeline.haulage.legs import run_shift_with_legs
from pitstudio_pipeline.haulage.pin import load_pin

TOOL = "minehaulsim"
METHOD = "seeded DES truck trajectories on the pit road network replayed with lane-based mixed traffic, constant-velocity TTC per encounter, paired seeds"
SERVES = ["FR-018-55", "FR-018-16"]
bi = chartkit.bi
T95 = 0.975

_T = "Tannant and Regensburg 2001 (Guidelines for Mine Haul Road Design, UBC), "
INPUT_ROWS: list[tuple[str, tuple[str, ...], str, str, str]] = [
    ("Footprint, haul truck (length x width)", ("footprint_m", "haul-truck"), "m", "Asset specification",
     "Cat 793F sheet, dimensions table (13,360 x 8,563 mm), as cited by the scene asset specification (FR-004-51); sheet not re-read"),
    ("Footprint, light vehicle (length x width)", ("footprint_m", "light-vehicle"), "m", "Asset specification",
     "Land Cruiser 79 sheet (5,235 x 1,800 mm), bounding box of the asset geometry (FR-004-51); sheet not re-read"),
    ("Lane offset from the road centre line", ("lane_offset_m",), "m", "Derived from a source",
     _T + "Eq. 5, p. 17 (3.5 x truck width, two lanes); vehicles centred: 0.875 x 8.563 m"),
    ("Reaction time, manned vehicle", ("reaction_s", "manned"), "s", "Sourced",
     _T + "p. 14, driver reaction t2, reasonable value 1.5 s (haul truck); applied to light-vehicle drivers"),
    ("Deceleration, haul truck", ("decel_mps2", "haul-truck"), "m/s2", "Sourced",
     _T + "p. 14, Kaufman and Ault (1977): friction 0.3, about 2.94 m/s2; Holman (1989) 9 % grade test consistent"),
    ("Deceleration, light vehicle", ("decel_mps2", "light-vehicle"), "m/s2", "Sourced",
     "AASHTO Green Book 11.2 ft/s2 (3.4 m/s2) as printed in TxDOT Roadway Design Manual 4.11.1; comfortable threshold, not a gravel maximum"),
    ("Reaction time, autonomous truck", ("reaction_s", "autonomous"), "s", "UNVERIFIED",
     "ISO 17757:2019 covers stop systems and late detection; its numbers are paywalled and were not read"),
    ("Acceleration, haul truck", ("accel_mps2", "haul-truck"), "m/s2", "UNVERIFIED", "No source read (re-acceleration after braking)"),
    ("Acceleration, light vehicle", ("accel_mps2", "light-vehicle"), "m/s2", "UNVERIFIED", "No source read (re-acceleration after braking)"),
    ("Yield when TTC is below", ("brake_ttc_s",), "s", "UNVERIFIED", "Model rule, no source read"),
    ("Brake for any moving vehicle when TTC is below", ("emergency_ttc_s",), "s", "UNVERIFIED", "Model rule, no source read"),
    ("Near-miss threshold", ("near_miss_ttc_s",), "s", "Specification", "FR-018-55 (spec 018) fixes the threshold"),
    ("Light-vehicle speed as a share of the limit", ("light_vehicle", "speed_factor"), "1", "UNVERIFIED", "No source read (patrol pattern)"),
    ("Light-vehicle dwell time at a node (mean)", ("light_vehicle", "dwell_mean_s"), "s", "UNVERIFIED", "No source read (patrol pattern)"),
]  # fmt: skip


def sig(x: float | None, n: int = 6) -> float | None:
    return float(f"{x:.{n}g}") if x is not None and x == x and math.isfinite(x) else None


def _t_interval(values: list[float]) -> tuple[float | None, float | None, float | None]:
    xs = [v for v in values if v is not None]
    if not xs:
        return None, None, None
    if len(xs) < 2:
        return xs[0], None, None
    m, s = statistics.fmean(xs), statistics.stdev(xs)
    h = float(stats.t.ppf(T95, len(xs) - 1)) * s / math.sqrt(len(xs))
    return m, m - h, m + h


def seed_job(args: tuple[str, str, int, dict]) -> dict[str, Any]:
    """One engine seed: the DES shift and every scenario of the sweep on its trucks. Runs in a worker process."""
    bundle_path, geo_path, seed, cfg = args
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    geo = json.loads(Path(geo_path).read_text(encoding="utf-8"))
    run = run_shift_with_legs(Path(bundle_path), seed=seed)
    net = T.road_net(bundle)
    tcfg = T._params(cfg["traffic"])
    design_nodes = [i + 1 for i, f in enumerate(f for f in geo["features"] if f["properties"]["kind"] == "node")]
    ids = [t["id"] for t in bundle["fleet"]]
    h, w = bundle["horizon_s"], bundle["kpi_window"]["warmup_s"]
    out: dict[str, Any] = {"seed": seed, "des_tph": run.result.kpis["fleet"]["production_tph"], "scenarios": {}}
    for share in cfg["sweep"]["autonomous_shares"]:
        auton = T.autonomous_trucks(ids, share, seed)
        trucks = T.truck_vehicles(net, run, bundle, tcfg["lane_offset_m"], auton)
        for n_lv in cfg["sweep"]["light_vehicles"]:
            lvs = T.light_vehicles(net, design_nodes, seed, n_lv, h, tcfg, 1000)
            r = T.simulate(trucks + lvs, horizon_s=h, warmup_s=w, net=net, params=cfg["traffic"])
            e = r.encounters
            pair = e["pair"]
            fin = np.isfinite(e["min_ttc"])
            out["scenarios"][f"{share}|{n_lv}"] = {
                "n_trucks": len(trucks),
                "vehicle_h": r.exposure_vehicle_h,
                "encounters": {"tl": int((pair == T.PAIR_TL).sum()), "ll": int((pair == T.PAIR_LL).sum())},
                "near_misses": {
                    "tl": int(((pair == T.PAIR_TL) & (e["min_ttc"] < tcfg["near_miss_ttc_s"])).sum()),
                    "ll": int(((pair == T.PAIR_LL) & (e["min_ttc"] < tcfg["near_miss_ttc_s"])).sum()),
                },
                "collisions": {
                    "tl": int(e["collisions"][pair == T.PAIR_TL].sum()),
                    "ll": int(e["collisions"][pair == T.PAIR_LL].sum()),
                },
                "contact_hold_s": r.contact_hold_s,
                "min_ttc_tl": e["min_ttc"][fin & (pair == T.PAIR_TL)].astype(np.float32).tolist(),
                "min_ttc_all": e["min_ttc"][fin].astype(np.float32).tolist(),
                "tonnes_des": r.tonnes_des,
                "tonnes_delivered": r.tonnes_delivered,
                "held_truck_s": r.held_truck_s,
                "releases": r.releases,
            }
    return out


def _bootstrap_percentile(
    per_seed: list[list[float]], q: float, n_boot: int, rng: np.random.Generator
) -> tuple[float | None, float | None, float | None]:
    pooled = np.concatenate([np.asarray(a, dtype=float) for a in per_seed]) if per_seed else np.zeros(0)
    if len(pooled) == 0:
        return None, None, None
    est = float(np.percentile(pooled, q))
    vals = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(per_seed), len(per_seed))
        sample = np.concatenate([np.asarray(per_seed[k], dtype=float) for k in pick])
        if len(sample):
            vals.append(float(np.percentile(sample, q)))
    lo, hi = (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))) if vals else (None, None)
    return est, lo, hi


def compute(params: dict[str, Any], data_root: Path, work: Path, workers: int) -> dict[str, Any]:
    sc, sw = params["scenario"], params["sweep"]
    geo_path = data_root / params["inputs"]["road_network"]
    geo = json.loads(geo_path.read_text(encoding="utf-8"))
    work.mkdir(parents=True, exist_ok=True)
    bundle = design_bundle(geo, sc, sw["fleet_size"], sw["dispatcher"])
    bpath = work / "b1-bundle.json"
    bpath.write_text(json.dumps(bundle), encoding="utf-8")
    cfg = {"traffic": params.get("traffic", {}), "sweep": sw}
    jobs = [(str(bpath), str(geo_path), s, cfg) for s in range(sw["seeds"])]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(seed_job, jobs, chunksize=1))
    return build_outputs(params, geo, bundle, results)


def build_outputs(params: dict, geo: dict, bundle: dict, results: list[dict]) -> dict[str, Any]:
    import minehaulsim

    sc, sw = params["scenario"], params["sweep"]
    tcfg = T._params(params.get("traffic"))
    pin = load_pin()
    from pitstudio.cases.d1.design_grid import minephys_identity

    version = f"{minehaulsim.__version__}+mp{minephys_identity()}"
    assert version.startswith(pin["version"])
    label = f"{LABEL}; rule-based agents, behaviour inputs sourced or UNVERIFIED as listed in the run summary"
    prod = chartkit.producer(TOOL, METHOD, version, label)
    shares, lvs, seeds = sw["autonomous_shares"], sw["light_vehicles"], sw["seeds"]
    ref_share, ref_lv = sw["reference"]["share"], sw["reference"]["light_vehicles"]
    rng = np.random.default_rng(20261125)
    win_h = (bundle["horizon_s"] - bundle["kpi_window"]["warmup_s"]) / 3600.0

    def sc_rows(share: float, n_lv: int) -> list[dict]:
        return [r["scenarios"][f"{share}|{n_lv}"] for r in results]

    def per_seed(share: float, n_lv: int, f) -> list[float]:
        return [f(x) for x in sc_rows(share, n_lv)]

    def nm_rate(x: dict) -> float:
        return near_misses_per_1000h(x["near_misses"]["tl"] + x["near_misses"]["ll"], x["vehicle_h"] * 3600.0)

    def tl_rate(x: dict) -> float:
        # truck-involved near-misses per 1,000 truck-hours (the exposure of the autonomous share question)
        return near_misses_per_1000h(x["near_misses"]["tl"], x["n_trucks"] * win_h * 3600.0)

    band = bi(
        f"95 % interval over {seeds} seeds (Student t)", f"Intervalo de 95 % sobre {seeds} semillas (t de Student)"
    )
    shift = f"{bundle['horizon_s'] / 3600:g} h shift, first {bundle['kpi_window']['warmup_s'] / 3600:g} h discarded"
    common_en = (
        f"Calibrated synthetic, {sw['fleet_size']} trucks, {shift}; behaviour inputs sourced or UNVERIFIED as listed."
    )
    common_es = f"Sintetico calibrado, {sw['fleet_size']} camiones, turno de {bundle['horizon_s'] / 3600:g} h (primeras {bundle['kpi_window']['warmup_s'] / 3600:g} h descartadas); parametros de comportamiento ilustrativos."
    pct = [100.0 * s for s in shares]
    charts: list[dict] = []

    def line_series(sid, label_bi, xs, values_by_x):
        mean, lo, hi = [], [], []
        for vals in values_by_x:
            m, a, b = _t_interval(vals)
            mean.append(sig(m)), lo.append(sig(a)), hi.append(sig(b))
        return chartkit.series(sid, label_bi, xs, mean, n=seeds, lo=lo, hi=hi, band_label=band)

    # 1 near-miss rate against the autonomous share, one series per number of light vehicles
    charts.append(
        chartkit.chart(
            "b1-near-miss-rate-vs-share",
            "B1",
            "line",
            bi(
                "Near-misses per 1,000 vehicle-hours against the autonomous share",
                "Cuasi-accidentes por 1.000 horas-vehiculo segun la proporcion de autonomos",
            ),
            prod,
            SERVES,
            caption=bi(
                common_en + f" Near-miss: minimum TTC of an encounter below {tcfg['near_miss_ttc_s']:g} s.",
                common_es + f" Cuasi-accidente: TTC minimo de un encuentro bajo {tcfg['near_miss_ttc_s']:g} s.",
            ),
            kpi="near_misses",
            x_axis=chartkit.axis("Autonomous share of the haul trucks", "Proporcion de camiones autonomos", "%"),
            y_axis=chartkit.axis("Near-misses", "Cuasi-accidentes", "1/(1000 h)"),
            series=[
                line_series(
                    f"lv{n}",
                    bi(f"{n} light vehicles", f"{n} vehiculos livianos"),
                    pct,
                    [per_seed(s, n, nm_rate) for s in shares],
                )
                for n in lvs
                if n > 0
            ],
        )
    )
    # 2 near-miss rate against traffic density, one series per share (selected)
    picked = [s for s in shares if s in (0.0, ref_share, 1.0)]
    charts.append(
        chartkit.chart(
            "b1-near-miss-rate-vs-density",
            "B1",
            "line",
            bi(
                "Near-misses per 1,000 vehicle-hours against the number of light vehicles",
                "Cuasi-accidentes por 1.000 horas-vehiculo segun la cantidad de vehiculos livianos",
            ),
            prod,
            SERVES,
            caption=bi(common_en, common_es),
            x_axis=chartkit.axis("Light vehicles on the network", "Vehiculos livianos en la red", "1"),
            y_axis=chartkit.axis("Near-misses", "Cuasi-accidentes", "1/(1000 h)"),
            series=[
                line_series(
                    f"share{round(100 * s)}",
                    bi(f"{round(100 * s)} % autonomous", f"{round(100 * s)} % autonomos"),
                    [n for n in lvs if n > 0],
                    [per_seed(s, n, nm_rate) for n in lvs if n > 0],
                )
                for s in picked
            ],
        )
    )
    # 3 percentiles of the minimum TTC of truck - light-vehicle encounters against the share
    ttc_series = []
    for q, name in (
        (5.0, ("5th percentile", "Percentil 5")),
        (25.0, ("25th percentile", "Percentil 25")),
        (50.0, ("Median", "Mediana")),
    ):
        est, lo, hi = [], [], []
        for s in shares:
            e, a, b = _bootstrap_percentile([x["min_ttc_tl"] for x in sc_rows(s, ref_lv)], q, 300, rng)
            est.append(sig(e)), lo.append(sig(a)), hi.append(sig(b))
        ttc_series.append(
            chartkit.series(
                f"p{round(q)}",
                bi(*name),
                pct,
                est,
                lo=lo,
                hi=hi,
                band_label=bi(
                    f"95 % bootstrap interval over the {seeds} seeds",
                    f"Intervalo bootstrap de 95 % sobre las {seeds} semillas",
                ),
            )
        )
    charts.append(
        chartkit.chart(
            "b1-min-ttc-percentiles-vs-share",
            "B1",
            "line",
            bi(
                "Minimum time to collision of truck - light-vehicle encounters",
                "Tiempo minimo a la colision de encuentros camion - vehiculo liviano",
            ),
            prod,
            SERVES,
            caption=bi(
                f"{ref_lv} light vehicles; smallest TTC of each encounter (pair within {tcfg['encounter_radius_m']:g} m); encounters that never close are left out.",
                f"{ref_lv} vehiculos livianos; menor TTC de cada encuentro (par a menos de {tcfg['encounter_radius_m']:g} m); se omiten los que nunca se acercan.",
            ),
            kpi="min_ttc",
            x_axis=chartkit.axis("Autonomous share of the haul trucks", "Proporcion de camiones autonomos", "%"),
            y_axis=chartkit.axis("Minimum TTC per encounter", "TTC minimo por encuentro", "s"),
            series=ttc_series,
        )
    )
    # 4 empirical distribution of the minimum TTC, one series per share, at the reference density
    grid = [round(0.25 * k, 2) for k in range(0, 61)]
    ecdf_series = []
    for s in shares:
        pooled = np.sort(
            np.concatenate([np.asarray(x["min_ttc_tl"], dtype=float) for x in sc_rows(s, ref_lv)] + [np.zeros(0)])
        )
        y = [float(np.searchsorted(pooled, g, side="right")) / len(pooled) if len(pooled) else None for g in grid]
        ecdf_series.append(
            chartkit.series(
                f"share{round(100 * s)}",
                bi(
                    f"{round(100 * s)} % autonomous (n = {len(pooled)})",
                    f"{round(100 * s)} % autonomos (n = {len(pooled)})",
                ),
                grid,
                [sig(v, 5) for v in y],
                draw="step",
                n=max(len(pooled), 1),
            )
        )
    charts.append(
        chartkit.chart(
            "b1-min-ttc-distribution",
            "B1",
            "ecdf",
            bi(
                "Distribution of the minimum TTC of truck - light-vehicle encounters",
                "Distribucion del TTC minimo de los encuentros camion - vehiculo liviano",
            ),
            prod,
            SERVES,
            caption=bi(
                f"{ref_lv} light vehicles, all seeds pooled: share of encounters with a minimum TTC at or below x. Near-miss threshold {tcfg['near_miss_ttc_s']:g} s.",
                f"{ref_lv} vehiculos livianos, todas las semillas: fraccion de encuentros con TTC minimo menor o igual a x. Umbral {tcfg['near_miss_ttc_s']:g} s.",
            ),
            x_axis=chartkit.axis("Minimum TTC per encounter", "TTC minimo por encuentro", "s"),
            y_axis=chartkit.axis("Share of encounters at or below", "Fraccion de encuentros menor o igual", "1"),
            series=ecdf_series,
        )
    )

    # 5 conflicts per shift by kind at the reference density
    def per_shift(kind_key: str, sub: str):
        return lambda x: float(x[kind_key][sub])

    conflict_series = [
        line_series(
            "nm-tl",
            bi("Near-misses, truck - light vehicle", "Cuasi-accidentes, camion - vehiculo liviano"),
            pct,
            [per_seed(s, ref_lv, per_shift("near_misses", "tl")) for s in shares],
        ),
        line_series(
            "nm-ll",
            bi("Near-misses, light vehicle - light vehicle", "Cuasi-accidentes, vehiculo liviano - vehiculo liviano"),
            pct,
            [per_seed(s, ref_lv, per_shift("near_misses", "ll")) for s in shares],
        ),
        line_series(
            "collision-tl",
            bi(
                "Collision events, truck - light vehicle",
                "Eventos de colision, camion - vehiculo liviano",
            ),
            pct,
            [per_seed(s, ref_lv, per_shift("collisions", "tl")) for s in shares],
        ),
        line_series(
            "collision-ll",
            bi(
                "Collision events, light vehicle - light vehicle",
                "Eventos de colision, vehiculo liviano - vehiculo liviano",
            ),
            pct,
            [per_seed(s, ref_lv, per_shift("collisions", "ll")) for s in shares],
        ),
    ]
    charts.append(
        chartkit.chart(
            "b1-conflicts-per-shift",
            "B1",
            "line",
            bi(
                "Conflicts per shift against the autonomous share",
                "Conflictos por turno segun la proporcion de autonomos",
            ),
            prod,
            SERVES,
            caption=bi(
                f"{ref_lv} light vehicles, {win_h:g} h window. A collision event is two vehicle footprints that would have overlapped in the model (the body is stopped); it has no TTC and is not a real collision.",
                f"{ref_lv} vehiculos livianos, ventana de {win_h:g} h. Un evento de colision es el solape que habrian tenido dos huellas de vehiculo en el modelo (el cuerpo se detiene); no tiene TTC y no es una colision real.",
            ),
            x_axis=chartkit.axis("Autonomous share of the haul trucks", "Proporcion de camiones autonomos", "%"),
            y_axis=chartkit.axis("Events per shift", "Eventos por turno", "1"),
            series=conflict_series,
        )
    )
    # 6 throughput against the share, one series per density, and the engine schedule as the no-interaction reference
    thr_series = [
        line_series(
            f"lv{n}",
            bi(f"{n} light vehicles", f"{n} vehiculos livianos"),
            pct,
            [per_seed(s, n, lambda x: x["tonnes_delivered"] / win_h) for s in shares],
        )
        for n in lvs
        if n > 0
    ]
    thr_series.append(
        chartkit.series(
            "engine",
            bi("Engine schedule, no light vehicles", "Programa del motor, sin vehiculos livianos"),
            pct,
            [sig(statistics.fmean(per_seed(s, lvs[0], lambda x: x["tonnes_des"] / win_h))) for s in shares],
        )
    )
    charts.append(
        chartkit.chart(
            "b1-throughput-vs-share",
            "B1",
            "line",
            bi(
                "Throughput against the share of autonomous trucks",
                "Rendimiento segun la proporcion de camiones autonomos",
            ),
            prod,
            SERVES,
            caption=bi(
                "Tonnes returned in the window after braking delays are applied to the engine schedule (first order: loader and dump queues are not re-simulated).",
                "Toneladas retornadas en la ventana tras aplicar las demoras de frenado al programa del motor (primer orden: no se re-simulan las colas).",
            ),
            x_axis=chartkit.axis("Autonomous share of the haul trucks", "Proporcion de camiones autonomos", "%"),
            y_axis=chartkit.axis("Throughput", "Rendimiento", "t/h"),
            series=thr_series,
        )
    )
    # 7 scenario table at the reference density
    cols = [
        {"id": "share", "label": bi("Autonomous trucks", "Camiones autonomos"), "type": "number", "unit": "%"},
        {
            "id": "enc",
            "label": bi("Truck - light-vehicle encounters per shift", "Encuentros camion - liviano por turno"),
            "type": "number",
            "unit": "1",
        },
        {
            "id": "nm",
            "label": bi("Near-misses per 1,000 vehicle-h", "Cuasi-accidentes por 1.000 h-vehiculo"),
            "type": "number",
            "unit": "1/(1000 h)",
        },
        {"id": "half", "label": bi("95 % half-width", "Semiancho al 95 %"), "type": "number", "unit": "1/(1000 h)"},
        {
            "id": "p5",
            "label": bi("5th percentile of the minimum TTC", "Percentil 5 del TTC minimo"),
            "type": "number",
            "unit": "s",
        },
        {"id": "thr", "label": bi("Throughput", "Rendimiento"), "type": "number", "unit": "t/h"},
        {
            "id": "held",
            "label": bi("Truck-hours braked per shift", "Horas-camion frenado por turno"),
            "type": "number",
            "unit": "h",
        },
    ]
    rows, summary_rows = [], []
    for i, s in enumerate(shares):
        m, a, b = _t_interval(per_seed(s, ref_lv, nm_rate))
        p5 = ttc_series[0]["y"][i]
        thr_m, _, _ = _t_interval(per_seed(s, ref_lv, lambda x: x["tonnes_delivered"] / win_h))
        enc_m = statistics.fmean(per_seed(s, ref_lv, lambda x: float(x["encounters"]["tl"])))
        held_m = statistics.fmean(per_seed(s, ref_lv, lambda x: x["held_truck_s"] / 3600.0))
        rows.append(
            [
                round(100 * s),
                sig(enc_m, 4),
                sig(m, 4),
                sig((b - a) / 2 if a is not None else None, 3),
                p5,
                sig(thr_m, 5),
                sig(held_m, 3),
            ]
        )
        summary_rows.append(
            {
                "autonomous_share": s,
                "light_vehicles": ref_lv,
                "near_misses_per_1000_vehicle_h": sig(m, 5),
                "p5_min_ttc_s": p5,
                "throughput_tph": sig(thr_m, 6),
                "seeds": seeds,
            }
        )
    charts.append(
        chartkit.chart(
            "b1-scenario-table",
            "B1",
            "table",
            bi(
                f"Autonomous share scenarios with {ref_lv} light vehicles",
                f"Escenarios de proporcion de autonomos con {ref_lv} vehiculos livianos",
            ),
            prod,
            SERVES,
            caption=bi(
                f"Mean of {seeds} paired seeds, 95 % Student-t half-width of the near-miss rate. No verdict: inputs are illustrative; model scenarios only.",
                f"Media de {seeds} semillas pareadas, semiancho de 95 % (t de Student). Sin veredicto: parametros ilustrativos; solo escenarios del modelo.",
            ),
            table={"columns": cols, "rows": rows},
        )
    )
    # 8 the behaviour inputs, each with its source or the UNVERIFIED label
    prm = tcfg
    rows_tbl = []
    for en, key, unit, status, source in INPUT_ROWS:
        v = prm
        for part in key:
            v = v[part]
        val = " x ".join(f"{x:g}" for x in v) if isinstance(v, list) else f"{v:g}"
        rows_tbl.append([en, f"{val} {unit}", status, source])
    charts.append(
        chartkit.chart(
            "b1-inputs-table",
            "B1",
            "table",
            bi("Behaviour inputs of the traffic model", "Parametros de comportamiento del modelo de trafico"),
            prod,
            SERVES,
            caption=bi(
                "Each value with its source and page or table, or marked UNVERIFIED when no source was read; the results move with the unverified ones.",
                "Cada valor con su fuente y pagina o tabla, o marcado UNVERIFIED cuando no se leyo una fuente; los resultados cambian con los no verificados.",
            ),
            table={
                "columns": [
                    {"id": "name", "label": bi("Input", "Parametro"), "type": "text"},
                    {"id": "value", "label": bi("Value", "Valor"), "type": "text"},
                    {"id": "status", "label": bi("Status", "Estado"), "type": "text"},
                    {"id": "source", "label": bi("Source", "Fuente"), "type": "text"},
                ],
                "rows": rows_tbl,
            },
        )
    )
    ref_idx = shares.index(ref_share)
    nm_m, nm_lo, nm_hi = _t_interval(per_seed(ref_share, ref_lv, nm_rate))
    where = f"{round(100 * ref_share)} % autonomous trucks, {sw['fleet_size']} trucks, {ref_lv} light vehicles, {seeds} seeds, {shift}"
    headline = [
        {
            "kpi": "min_ttc",
            "name": "5th percentile of the minimum time to collision of truck - light-vehicle encounters",
            "unit": "s",
            "value": ttc_series[0]["y"][ref_idx],
            "note": f"{where}; 95 % bootstrap interval {ttc_series[0]['lo'][ref_idx]} to {ttc_series[0]['hi'][ref_idx]} s; calibrated synthetic, behaviour inputs sourced or UNVERIFIED as listed",
        },
        {
            "kpi": "near_misses",
            "name": "Near-misses per 1,000 vehicle-hours",
            "unit": "1/(1000 h)",
            "value": sig(nm_m, 5),
            "note": f"{where}; 95 % half-width {sig((nm_hi - nm_lo) / 2, 3)}; TTC threshold {tcfg['near_miss_ttc_s']:g} s; calibrated synthetic, behaviour inputs sourced or UNVERIFIED as listed",
        },
    ]
    all_rel = sum(x["releases"] for r in results for x in r["scenarios"].values())
    summary = {
        "title": "Autonomous and manned traffic on the Bingham pit road network: time to collision, near-misses and throughput against the autonomous share",
        "label": f"{LABEL}. Rule-based agents, behaviour inputs sourced or UNVERIFIED as listed; no proximity data exists to calibrate or validate them. {BIAS_NOTE}",
        "methods": ["M2", "M20"],
        "verdict": "ok",
        "headline": headline,
        "rows": summary_rows,
        "extra": {
            "scenario": {
                k: sc[k]
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
            "traffic": tcfg,
            "network": {
                "nodes": sum(1 for f in geo["features"] if f["properties"]["kind"] == "node"),
                "design_edges": sum(1 for f in geo["features"] if f["properties"]["kind"] == "edge"),
            },
            "engine": f"minehaulsim {version}",
            "variate_profile": "engine",
            "mode": "traffic",
            "seeds": seeds,
            "fleet_size": sw["fleet_size"],
            "dispatcher": sw["dispatcher"],
            "autonomous_shares": shares,
            "light_vehicles": lvs,
            "reference": sw["reference"],
            "negotiated_goes": all_rel,
            "assumptions": [
                "haul trucks follow the engine trajectories (recorded per segment: request, exit and kinematic times); a truck that brakes lags its schedule and the delay is applied to the engine tonnes after the fact, so queueing at loaders and dumps is not re-simulated",
                "light vehicles are manned, drive seeded random trips between design nodes along the shortest road path at a share of the segment speed limit and dwell off the road at nodes",
                "vehicles drive in a lane offset from the road centre line; opposing vehicles pass at twice the offset; each vehicle is an oriented rectangle of its asset-specification footprint; two footprints never overlap: a pair about to overlap is a collision event (counted) and the body that would run into the other is stopped, an overlap has no TTC",
                "the share of autonomous trucks acts only through the reaction time before braking (the autonomous value is UNVERIFIED); the yielding rules and the other inputs are the same for every vehicle",
                "light vehicles at rest, truck against truck, and vehicles on roads that run side by side without a shared node are not evaluated",
                "constant-velocity TTC ignores braking and steering during the encounter; it is a screening metric",
                "the behaviour inputs marked UNVERIFIED in the inputs table have no source read; no incident or proximity record exists to calibrate or validate any of them",
                "the sensors and the Cosmos reasoning of case B1 are not part of this run",
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
    ap.add_argument("--work", type=Path, required=True, help="scratch folder for the bundle (removed afterwards)")
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

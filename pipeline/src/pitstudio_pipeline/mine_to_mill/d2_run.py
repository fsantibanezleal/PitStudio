"""Case D2 run (spec 017, FR-017-01, FR-017-02): the chain sweeps, their Sobol indices, the summary and the charts.

Stage entry (`python -m pitstudio_pipeline.mine_to_mill.d2_run --job job.json`), CPU only. From the recipe parameters
it (1) draws the seeded scrambled-Sobol sweeps of the chain `pitstudio.cases.d2.chain` (200 configurations x 64 blast
designs = 12,800 evaluations, split 140 / 20 / 40 by configuration), (2) estimates the Sobol first-order and total
indices of the three chain outputs over the box with a second seeded design, (3) evaluates a reference design with the
equation of every stage and (4) writes the results summary and the chart-series files of the Charts tab.

Every number is a number of `minephys` through the chain; nothing is read from memory. The box bounds are illustrative
and UNVERIFIED (spec 017 section 7), so every chart carries the label "calibrated synthetic, not validated against real
data".
"""
# ruff: noqa: E501

from __future__ import annotations

import json
import math
import warnings
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from minephys._errors import ValidityWarning

from pitstudio.cases.d1.design_grid import minephys_identity
from pitstudio.cases.d2.chain import ASSUMPTIONS, INPUT_NAMES, breakdown, crusher_f80_um, rom_x80_m, run_chain
from pitstudio_pipeline import chartkit
from pitstudio_pipeline.mine_to_mill.sensitivity import sobol_indices
from pitstudio_pipeline.mine_to_mill.sweeps import POINT_INPUTS, generate_sweeps, link_bounds

LABEL = "calibrated synthetic, not validated against real data"
TOOL = "minephys"
METHOD = "Kuz-Ram/KCO blast, Whiten crusher, Bond law and cost chain; scrambled-Sobol sweeps and Saltelli/Jansen Sobol indices"
SERVES = ["FR-017-01", "FR-017-02"]
bi = chartkit.bi
OUTPUT_NAMES = ("specific_energy_kwh_per_t", "throughput_t_per_h", "cost_usd_per_t")
OUTPUT_LABELS = {
    "specific_energy_kwh_per_t": bi("Specific energy", "Energia especifica"),
    "throughput_t_per_h": bi("Mill throughput", "Rendimiento de la planta"),
    "cost_usd_per_t": bi("Cost per tonne", "Costo por tonelada"),
}
OUTPUT_UNITS = {"specific_energy_kwh_per_t": "kWh/t", "throughput_t_per_h": "t/h", "cost_usd_per_t": "USD/t"}
INPUT_LABELS = {
    "burden_m": ("Burden", "Piedra"),
    "spacing_ratio": ("Spacing ratio S/B", "Razon de espaciamiento S/B"),
    "powder_factor_kg_per_m3": ("Powder factor", "Factor de carga"),
    "hole_diameter_mm": ("Hole diameter", "Diametro de perforacion"),
    "bench_height_m": ("Bench height", "Altura de banco"),
    "rock_factor": ("Rock factor", "Factor de roca"),
    "bond_work_index_kwh_per_t": ("Bond work index", "Indice de trabajo de Bond"),
    "crusher_css_mm": ("Crusher setting", "Abertura del chancador"),
    "target_p80_um": ("Target P80", "P80 objetivo"),
    "mill_power_kw": ("Mill power", "Potencia del molino"),
    "efficiency": ("Efficiency", "Eficiencia"),
    "energy_cap_kwh_per_t": ("Energy cap (not used by the chain)", "Tope de energia (no usado por la cadena)"),
    "explosive_cost_usd_per_kg": ("Explosive cost", "Costo del explosivo"),
    "energy_cost_usd_per_kwh": ("Energy cost", "Costo de la energia"),
    "consumables_usd_per_t": ("Consumables", "Consumibles"),
}
BINS = 15
BAND = (10.0, 90.0)
BASE_SERIES_ID = {"specific_energy_kwh_per_t": "energy", "throughput_t_per_h": "throughput", "cost_usd_per_t": "cost"}


class _Warnings:
    """Counts the ValidityWarning raised by minephys during a block, by argument, without printing them."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self._cm: Any = None
        self._log: Any = None

    def __enter__(self) -> _Warnings:
        self._cm = warnings.catch_warnings(record=True)
        self._log = self._cm.__enter__()
        warnings.simplefilter("always")
        return self

    def __exit__(self, *exc: object) -> None:
        for w in self._log:
            if isinstance(w.message, ValidityWarning):
                self.counts[w.message.argument] += 1
        self._cm.__exit__(*exc)


def _box_parts(params: Mapping[str, Any]) -> tuple[dict[str, tuple[float, float]], dict[str, str], dict[str, str]]:
    bounds = {k: (float(v["min"]), float(v["max"])) for k, v in params["box"].items()}
    rows = {k: str(v["row"]) for k, v in params["box"].items()}
    statuses = {str(v["row"]): str(v["status"]) for v in params["box"].values()}
    return bounds, rows, statuses


def smallest_feed_f80_um(box: Mapping[str, Mapping[str, float]], fixed: Mapping[str, float]) -> float:
    """The smallest crusher product F80 over the corners of the blast and crusher inputs of the box (um)."""
    names = (
        "burden_m",
        "spacing_ratio",
        "powder_factor_kg_per_m3",
        "hole_diameter_mm",
        "bench_height_m",
        "rock_factor",
        "crusher_css_mm",
    )
    best = math.inf
    for mask in range(2 ** len(names)):
        x = {**fixed, **{n: box[n]["max" if mask >> i & 1 else "min"] for i, n in enumerate(names)}}
        best = min(best, crusher_f80_um(x))
    return best


def _binned(
    x: np.ndarray, y: np.ndarray, edges: np.ndarray
) -> tuple[list[float], list[float], list[float], list[float]]:
    """Bin centre, median, 10th and 90th percentile of y inside each bin of x (empty bins are dropped)."""
    index = np.clip(np.digitize(x, edges) - 1, 0, len(edges) - 2)
    centre, med, lo, hi = [], [], [], []
    for b in range(len(edges) - 1):
        sel = y[index == b]
        if sel.size:
            centre.append(float(np.mean(x[index == b])))
            med.append(float(np.median(sel)))
            lo.append(float(np.percentile(sel, BAND[0])))
            hi.append(float(np.percentile(sel, BAND[1])))
    return centre, med, lo, hi


def _evaluate_matrix(names: tuple[str, ...], fixed: Mapping[str, float]):
    def func(x: np.ndarray) -> np.ndarray:
        out = np.empty((x.shape[0], 3))
        for i, row in enumerate(x):
            r = run_chain({**fixed, **dict(zip(names, map(float, row), strict=True))})
            out[i] = (r.kwh_per_t, r.t_per_h, r.cost_per_t)
        return out

    return func


def compute(params: Mapping[str, Any]) -> dict[str, Any]:
    """Run D2: returns the sweep document, the indices, the summary and the chart-series documents."""
    bounds, rows, statuses = _box_parts(params)
    box, _ = link_bounds(bounds, rows, statuses)
    design = {
        "seed": int(params["seed"]),
        "energy_model": "bond",
        "n_configurations": int(params["n_configurations"]),
        "points_per_configuration": int(params["points_per_configuration"]),
        "split": dict(params["split"]),
        "box": box,
    }
    reference = {k: float(v) for k, v in params["reference_design"].items()}
    mid = {k: 0.5 * (lo + hi) for k, (lo, hi) in bounds.items()}
    seen = _Warnings()
    with seen:
        f80_floor = smallest_feed_f80_um(box, mid)
        sweeps = generate_sweeps(design, chain=lambda x: run_chain(x), smallest_feed_f80_um=f80_floor)
        configs = sweeps["configurations"]
        x_p80, f80s, rom, pf, y = [], [], [], [], {k: [] for k in OUTPUT_NAMES}
        for c in configs:
            for p in c["points"]:
                full = {**c["inputs"], **{k: p[k] for k in POINT_INPUTS}}
                x_p80.append(c["inputs"]["target_p80_um"])
                f80s.append(crusher_f80_um(full))
                rom.append(rom_x80_m(full))
                pf.append(p["powder_factor_kg_per_m3"])
                for k in OUTPUT_NAMES:
                    y[k].append(p[k])
        names = tuple(INPUT_NAMES)
        sob = params["sobol"]
        indices = sobol_indices(
            _evaluate_matrix(names, {}),
            {n: bounds[n] for n in names},
            n_base=int(sob["n_base"]),
            seed=int(sob["seed"]),
            n_bootstrap=int(sob["n_bootstrap"]),
        )
        stages = breakdown(reference)
        result = run_chain(reference)
    version = minephys_identity()
    prod = chartkit.producer(TOOL, METHOD, version, LABEL)
    arrays = {k: np.array(v) for k, v in y.items()}
    x_p80_a, f80_a = np.array(x_p80), np.array(f80s)
    charts = []
    p80_edges = np.linspace(bounds["target_p80_um"][0], bounds["target_p80_um"][1], BINS + 1)
    for k in OUTPUT_NAMES:
        centre, med, lo, hi = _binned(x_p80_a, arrays[k], p80_edges)
        label = OUTPUT_LABELS[k]
        charts.append(
            chartkit.chart(
                f"d2-{BASE_SERIES_ID[k]}-vs-p80",
                "D2",
                "line",
                chartkit.bi(f"{label['en']} against the target P80", f"{label['es']} segun el P80 objetivo"),
                prod,
                SERVES,
                caption=chartkit.bi(
                    f"Median and 10 to 90 percent range of {len(x_p80)} chain evaluations of the sweep in {len(centre)} bins of "
                    "target P80; every other input varies over its box.",
                    f"Mediana y rango 10 a 90 por ciento de {len(x_p80)} evaluaciones de la cadena en {len(centre)} tramos de "
                    "P80 objetivo; las demas entradas varian en su caja.",
                ),
                x_axis=chartkit.axis("Target P80", "P80 objetivo", "um"),
                y_axis=chartkit.axis(label["en"], label["es"], OUTPUT_UNITS[k]),
                series=[
                    chartkit.series(
                        f"median-{BASE_SERIES_ID[k]}",
                        chartkit.bi("Median", "Mediana"),
                        centre,
                        med,
                        n=len(x_p80),
                        lo=lo,
                        hi=hi,
                        band_label=chartkit.bi("10th to 90th percentile", "Percentil 10 a 90"),
                    )
                ],
            )
        )
    f_edges = np.geomspace(float(f80_a.min()), float(f80_a.max()) * (1 + 1e-9), BINS + 1)
    centre, med, lo, hi = _binned(f80_a, arrays["specific_energy_kwh_per_t"], f_edges)
    rom_a, pf_a = np.array(rom), np.array(pf)
    pf_edges = np.linspace(bounds["powder_factor_kg_per_m3"][0], bounds["powder_factor_kg_per_m3"][1], BINS + 1)
    centre, med, lo, hi = _binned(pf_a, rom_a * 1000.0, pf_edges)
    charts.append(
        chartkit.chart(
            "d2-rom-x80-vs-powder-factor",
            "D2",
            "line",
            chartkit.bi("Run-of-mine x80 against the powder factor", "x80 de la pila segun el factor de carga"),
            prod,
            SERVES,
            caption=chartkit.bi(
                "Median and 10 to 90 percent range of the blast x80 (Kuz-Ram/KCO) in bins of powder factor over the same sweep.",
                "Mediana y rango 10 a 90 por ciento del x80 de la tronadura (Kuz-Ram/KCO) en tramos de factor de carga, en el mismo barrido.",
            ),
            x_axis=chartkit.axis("Powder factor", "Factor de carga", "kg/m3"),
            y_axis=chartkit.axis("Run-of-mine x80", "x80 de la pila", "mm"),
            series=[
                chartkit.series(
                    "median-rom-x80",
                    chartkit.bi("Median", "Mediana"),
                    centre,
                    med,
                    n=len(rom),
                    lo=lo,
                    hi=hi,
                    band_label=chartkit.bi("10th to 90th percentile", "Percentil 10 a 90"),
                )
            ],
        )
    )
    step = max(1, len(rom) // 2000)
    charts.append(
        chartkit.chart(
            "d2-f80-vs-rom-x80",
            "D2",
            "scatter",
            chartkit.bi(
                "Crusher product F80 against the run-of-mine x80",
                "F80 del producto del chancador segun el x80 de la pila",
            ),
            prod,
            SERVES,
            caption=chartkit.bi(
                f"Every {step}th point of the sweep. The crusher closed-side setting, not the blast, sets the mill feed size.",
                f"Un punto de cada {step} del barrido. La abertura del chancador, no la tronadura, fija el tamano de alimentacion al molino.",
            ),
            x_axis=chartkit.axis("Run-of-mine x80", "x80 de la pila", "mm", "log"),
            y_axis=chartkit.axis("Crusher product F80", "F80 del producto del chancador", "mm", "log"),
            series=[
                chartkit.series(
                    "sweep-points",
                    chartkit.bi("Sweep points", "Puntos del barrido"),
                    rom_a[::step] * 1000.0,
                    f80_a[::step] / 1000.0,
                    draw="points",
                    n=len(rom),
                )
            ],
        )
    )
    charts.append(
        chartkit.chart(
            "d2-energy-vs-f80",
            "D2",
            "line",
            chartkit.bi("Specific energy against the mill feed F80", "Energia especifica segun el F80 de alimentacion"),
            prod,
            SERVES,
            caption=chartkit.bi(
                "Median and 10 to 90 percent range of the specific energy in bins of the crusher product F80 (the blast "
                "fragmentation seen by the mill), over the same sweep.",
                "Mediana y rango 10 a 90 por ciento de la energia especifica en tramos del F80 del producto del chancador "
                "(la fragmentacion de la tronadura que ve el molino), en el mismo barrido.",
            ),
            x_axis=chartkit.axis("Mill feed F80", "F80 de alimentacion al molino", "um", "log"),
            y_axis=chartkit.axis("Specific energy", "Energia especifica", "kWh/t"),
            series=[
                chartkit.series(
                    "median-energy",
                    chartkit.bi("Median", "Mediana"),
                    centre,
                    med,
                    n=len(f80s),
                    lo=lo,
                    hi=hi,
                    band_label=chartkit.bi("10th to 90th percentile", "Percentil 10 a 90"),
                )
            ],
        )
    )
    categories = [{"id": n.replace("_", "-"), "label": chartkit.bi(*INPUT_LABELS[n])} for n in indices.names]
    for key, est, ci, title_en, title_es in (
        (
            "first-order",
            indices.first_order,
            indices.first_order_ci,
            "First-order Sobol index",
            "Indice de Sobol de primer orden",
        ),
        ("total", indices.total, indices.total_ci, "Total Sobol index", "Indice de Sobol total"),
    ):
        charts.append(
            chartkit.chart(
                f"d2-sobol-{key}",
                "D2",
                "bar",
                chartkit.bi(f"{title_en} of each input", f"{title_es} de cada entrada"),
                prod,
                SERVES,
                caption=chartkit.bi(
                    f"Saltelli/Jansen estimate with {indices.n_evaluations} chain evaluations (N = {indices.n_base}, seed "
                    f"{indices.seed}); bars show the 95 percent bootstrap interval.",
                    f"Estimacion Saltelli/Jansen con {indices.n_evaluations} evaluaciones (N = {indices.n_base}, semilla "
                    f"{indices.seed}); las barras muestran el intervalo bootstrap de 95 por ciento.",
                ),
                y_axis=chartkit.axis(title_en, title_es, "1"),
                categories=categories,
                series=[
                    chartkit.series(
                        f"{BASE_SERIES_ID[o]}",
                        OUTPUT_LABELS[o],
                        None,
                        est[:, j],
                        n=indices.n_evaluations,
                        lo=ci[:, j, 0],
                        hi=ci[:, j, 1],
                        band_label=chartkit.bi("95 percent bootstrap interval", "Intervalo bootstrap de 95 por ciento"),
                    )
                    for j, o in enumerate(OUTPUT_NAMES)
                ],
            )
        )
    charts.append(
        chartkit.chart(
            "d2-chain-stages",
            "D2",
            "table",
            chartkit.bi(
                "Chain stages of the reference design, each with its equation",
                "Etapas de la cadena del diseno de referencia, cada una con su ecuacion",
            ),
            prod,
            ["FR-017-01"],
            table={
                "columns": [
                    {"id": "stage", "label": chartkit.bi("Stage", "Etapa"), "type": "text"},
                    {"id": "quantity", "label": chartkit.bi("Quantity", "Magnitud"), "type": "text"},
                    {"id": "value", "label": chartkit.bi("Value", "Valor"), "type": "number", "unit": "1"},
                    {"id": "unit", "label": chartkit.bi("Unit", "Unidad"), "type": "text"},
                    {"id": "equation", "label": chartkit.bi("Equation", "Ecuacion"), "type": "text"},
                    {"id": "source", "label": chartkit.bi("Source", "Fuente"), "type": "text"},
                ],
                "rows": [
                    [r["stage"], r["quantity"], float(r["value"]), r["unit"], r["equation"], r["source"]]
                    for r in stages
                ],
            },
        )
    )
    for doc in charts:
        found = chartkit.problems(doc)
        if found:
            raise ValueError(f"chart {doc['id']}: {found[:3]}")
    blast_inputs = (
        "burden_m",
        "spacing_ratio",
        "powder_factor_kg_per_m3",
        "hole_diameter_mm",
        "bench_height_m",
        "rock_factor",
    )
    blast_total = float(sum(indices.total[indices.names.index(n), 0] for n in blast_inputs))
    log_corr = float(np.corrcoef(np.log(rom_a), np.log(f80_a))[0, 1])
    css_total = float(indices.total[indices.names.index("crusher_css_mm"), 0])
    finding = (
        f"With a primary crusher between the blast and the mill, the blast inputs together have a total Sobol index of "
        f"{blast_total:.4f} on the specific energy (the crusher setting {css_total:.4f}), and the correlation of the log "
        f"run-of-mine x80 with the log crusher product F80 is {log_corr:.3f}: in this Bond-law chain the mill feed size is set "
        "by the crusher, so the blast reaches the mill energy only through the crusher; the coarse-feed (SAG) circuits where "
        "fragmentation matters most are not part of this chain."
    )
    ranking = sorted(range(len(indices.names)), key=lambda i: -indices.total[i, 0])
    summary = {
        "methods": ["M12", "M17"],
        "title": "Mine-to-mill chain: blast fragmentation to mill throughput, energy and cost, with Sobol sensitivity sweeps",
        "label": LABEL,
        "verdict": "ok",
        "headline": [
            {
                "name": "Mill throughput, reference design",
                "value": round(result.t_per_h, 4),
                "unit": "t/h",
                "kpi": "mill_throughput",
            },
            {
                "name": "Specific energy, reference design",
                "value": round(result.kwh_per_t, 4),
                "unit": "kWh/t",
                "kpi": "specific_energy",
            },
            {
                "name": "Cost per tonne, reference design",
                "value": round(result.cost_per_t, 4),
                "unit": "USD/t",
                "kpi": "cost_per_tonne",
                "note": "illustrative unit costs and an assumed rock density (UNVERIFIED)",
            },
        ],
        "rows": [
            {
                "input": indices.names[i],
                "first_order_specific_energy": round(float(indices.first_order[i, 0]), 4),
                "total_specific_energy": round(float(indices.total[i, 0]), 4),
                "total_throughput": round(float(indices.total[i, 1]), 4),
                "total_cost": round(float(indices.total[i, 2]), 4),
            }
            for i in ranking
        ],
        "extra": {
            "sweep_evaluations": design["n_configurations"] * design["points_per_configuration"],
            "split": design["split"],
            "sobol_evaluations": indices.n_evaluations,
            "sobol_n_base": indices.n_base,
            "sobol_seed": indices.seed,
            "sweep_seed": design["seed"],
            "smallest_feed_f80_um": round(f80_floor, 3),
            "validity_warnings_by_argument": dict(seen.counts),
            "unverified_rows": sweeps["unverified_rows"],
            "assumptions": ASSUMPTIONS,
            "minephys": f"minephys {version}",
            "finding": finding,
            "blast_inputs_total_index_specific_energy": round(blast_total, 6),
            "log_correlation_rom_x80_crusher_f80": round(log_corr, 6),
            "m17_scope": "comminution chain only; the learned meta-model of M17 is not run",
            "pbm": "the population-balance mill product is not in the minephys chain (open question D2-Q1)",
        },
    }
    return {
        "sweeps": sweeps,
        "sensitivity": {
            "names": list(indices.names),
            "outputs": list(OUTPUT_NAMES),
            "first_order": indices.first_order.tolist(),
            "total": indices.total.tolist(),
            "first_order_ci": indices.first_order_ci.tolist(),
            "total_ci": indices.total_ci.tolist(),
            "variance": indices.variance.tolist(),
            "n_base": indices.n_base,
            "seed": indices.seed,
            "n_evaluations": indices.n_evaluations,
        },
        "summary": summary,
        "charts": charts,
        "breakdown": stages,
    }


def write_outputs(result: Mapping[str, Any], out: Path) -> list[Path]:
    """Write sweeps.json, sensitivity.json, results-summary.json and charts/*.json under `out`."""
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, doc in (
        ("sweeps.json", result["sweeps"]),
        ("sensitivity.json", result["sensitivity"]),
        ("results-summary.json", result["summary"]),
    ):
        path = out / name
        path.write_text(json.dumps(doc, indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        written.append(path)
    written += [chartkit.write(c, out / "charts") for c in result["charts"]]
    return written


def stage(job: Mapping[str, Any]) -> dict[str, Any]:
    """Stage function of the runner protocol: parameters from the job, files into its output folder."""
    out = Path(job["output_dir"])
    paths = write_outputs(compute(job["params"]), out)
    return {"outputs": [{"path": p.relative_to(out).as_posix()} for p in paths]}


def main(argv: list[str] | None = None) -> int:
    from pitstudio_stagekit import main as kit_main

    return kit_main(stage, argv)


if __name__ == "__main__":
    raise SystemExit(main())

"""Case D1 run (spec 012, FR-012-41, FR-012-29): the blast design grids and the per-fold TRTR results with their PSD curves.

Stage entry (`python -m pitstudio_pipeline.fragmentation.d1_run --job job.json`), CPU only:

1. three design grids (DC-012-05) from `minephys.blasting` through `pitstudio.cases.d1.design_grid`: fragmentation
   (burden x spacing x charge length), vibration (distance x charge per delay) and flyrock (launch speed x fragment size);
2. the per-fold TRTR report of `fold_report` (CPU inference of the five on-disk fold models on their test originals,
   recomputed IoU, instance PSD curves in pixels, training curves);
3. the results summary and the chart-series files of the Charts tab.

Only metrics leave this stage (FR-012-38). The size basis of every PSD is stated on the chart: sieve size in metres for the
blast model, equivalent-circle diameter in pixels for the image PSD.
"""
# ruff: noqa: E501, PERF401

from __future__ import annotations

import json
import os
import warnings
from collections import Counter
from collections.abc import Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np
from minephys import blasting
from minephys._errors import ValidityWarning

from pitstudio.cases.d1.design_grid import build_design_grid, minephys_identity
from pitstudio_pipeline import chartkit
from pitstudio_pipeline.fragmentation import fold_report

bi = chartkit.bi
DESIGN_LABEL = "model output with illustrative site constants (UNVERIFIED), not validated against real data"
TRTR_LABEL = "real images (Mendeley Data 78ht3pjsr4, CC BY 4.0); metrics only, no image is published"
DESIGN_METHOD = (
    "Kuz-Ram (Cunningham 2005) with KCO/Swebrec, scaled-distance PPV and ballistic flyrock of minephys.blasting"
)
TRTR_METHOD = "TRTR U-Net inference on the CPU, FR-012-19 instance decoder, area-weighted instance PSD (FR-012-24)"
SERVES_DESIGN = ["FR-012-41"]
SERVES_TRTR = ["FR-012-29", "FR-012-24"]
KPI_SCALE = {"p80": 1000.0, "ppv": 1000.0}  # m -> mm and m/s -> mm/s: the units of the case KPIs


def _axis_edges(values: Sequence[float]) -> tuple[float, float]:
    step = (values[-1] - values[0]) / (len(values) - 1) if len(values) > 1 else 1.0
    return values[0] - step / 2.0, values[-1] + step / 2.0


def _raster(
    cid: str,
    title: tuple[str, str],
    caption: tuple[str, str],
    prod: dict,
    grid: Mapping[str, Any],
    key: str,
    *,
    scale: float,
    unit: str,
    colour_label: tuple[str, str],
    x_name: str,
    y_name: str,
    cut: Mapping[str, float],
    reference: Mapping[str, float],
    marker_text: str,
    values_fn=None,
    colormap: str = "viridis",
) -> dict:
    axes = {a["input"]: a["values"] for a in grid["axes"]}
    xs, ys = axes[x_name], axes[y_name]
    by = {tuple(p["inputs"][k] for k in (x_name, y_name, *cut)): p for p in grid["points"]}
    rows = []
    for y in reversed(ys):  # first row is the top (largest y) row
        rows.append(
            [
                float(values_fn(by[(x, y, *cut.values())]) if values_fn else by[(x, y, *cut.values())][key] * scale)
                for x in xs
            ]
        )
    flat = [v for row in rows for v in row]
    x0, x1 = _axis_edges(xs)
    y0, y1 = _axis_edges(ys)
    labels = {"burden_m": ("Burden", "Piedra", "m"), "spacing_m": ("Spacing", "Espaciamiento", "m")}
    return chartkit.chart(
        cid,
        "D1",
        "raster",
        bi(*title),
        prod,
        SERVES_DESIGN,
        caption=bi(*caption),
        x_axis=chartkit.axis(labels[x_name][0], labels[x_name][1], labels[x_name][2]),
        y_axis=chartkit.axis(labels[y_name][0], labels[y_name][1], labels[y_name][2]),
        raster={
            "nx": len(xs),
            "ny": len(ys),
            "extent": {"x0": x0, "x1": x1, "y0": y0, "y1": y1},
            "values": flat,
            "colour": {
                "colormap": colormap,
                "vmin": min(flat),
                "vmax": max(flat),
                "unit": unit,
                "label": bi(*colour_label),
            },
        },
        markers=[
            {
                "id": "reference-design",
                "label": bi("Reference design", "Diseno de referencia"),
                "value_text": marker_text,
                "orientation": "point",
                "x": float(reference[x_name]),
                "y": float(reference[y_name]),
            }
        ],
    )


def design_outputs(params: Mapping[str, Any]) -> dict[str, Any]:
    """The three grids, the design charts and the reference design values."""
    fixed, variant, dist = params["fixed_inputs"], params["kuzram_variant"], params["distribution"]
    ref = params["reference_design"]
    with warnings.catch_warnings(record=True) as log:
        warnings.simplefilter("always")
        grids = {
            name: build_design_grid(fixed, params[f"grid_{name}"], kuzram_variant=variant, distribution=dist)
            for name in ("fragmentation", "vibration", "flyrock")
        }
    validity = Counter(w.message.argument for w in log if isinstance(w.message, ValidityWarning))
    prod = chartkit.producer("minephys", DESIGN_METHOD, minephys_identity(), DESIGN_LABEL)
    frag = grids["fragmentation"]
    cut = {"charge_length_m": float(ref["charge_length_m"])}
    inputs_ref = {**fixed, **{k: ref[k] for k in ("burden_m", "spacing_m", "charge_length_m")}}

    def powder(point: Mapping[str, Any]) -> float:
        x = {**inputs_ref, **point["inputs"], **cut}
        q = blasting.charge_per_hole(x["explosive_density_kg_per_m3"], x["hole_diameter_m"], x["charge_length_m"])
        return float(blasting.powder_factor(q, x["burden_m"], x["spacing_m"], x["bench_height_m"]))

    at_ref = next(
        p
        for p in frag["points"]
        if p["inputs"]["burden_m"] == ref["burden_m"]
        and p["inputs"]["spacing_m"] == ref["spacing_m"]
        and p["inputs"]["charge_length_m"] == ref["charge_length_m"]
    )
    reference_values = {
        "x80_m": at_ref["x80_m"],
        "x50_m": at_ref["x50_m"],
        "oversize_pct": at_ref["oversize_pct"],
        "powder_factor": powder(at_ref),
    }
    common = dict(x_name="burden_m", y_name="spacing_m", cut=cut, reference=ref)
    cap = (
        "Kuz-Ram/KCO prediction on a burden by spacing grid at the reference charge length; the other inputs are fixed "
        "(see the recipe).",
        "Prediccion Kuz-Ram/KCO en una malla piedra por espaciamiento con el largo de carga de referencia; "
        "las demas entradas son fijas (ver la receta).",
    )
    charts = [
        _raster(
            "d1-p80-map",
            (
                "Predicted P80 of the muck pile by burden and spacing",
                "P80 predicho de la pila segun piedra y espaciamiento",
            ),
            cap,
            prod,
            frag,
            "x80_m",
            scale=1000.0,
            unit="mm",
            colour_label=("P80 (sieve size)", "P80 (tamano de tamiz)"),
            marker_text=f"P80 {at_ref['x80_m'] * 1000.0:.0f} mm",
            **common,
        ),
        _raster(
            "d1-oversize-map",
            ("Oversize share by burden and spacing", "Sobretamano segun piedra y espaciamiento"),
            cap,
            prod,
            frag,
            "oversize_pct",
            scale=1.0,
            unit="%",
            colour_label=("Oversize above the limit", "Sobretamano sobre el limite"),
            marker_text=f"{at_ref['oversize_pct']:.1f} %",
            colormap="magma",
            **common,
        ),
        _raster(
            "d1-powder-factor-map",
            ("Powder factor by burden and spacing", "Factor de carga segun piedra y espaciamiento"),
            cap,
            prod,
            frag,
            "powder_factor",
            scale=1.0,
            unit="kg/m3",
            colour_label=("Powder factor", "Factor de carga"),
            marker_text=f"{reference_values['powder_factor']:.2f} kg/m3",
            values_fn=powder,
            colormap="cividis",
            **common,
        ),
    ]
    vib = grids["vibration"]
    ax = {a["input"]: a["values"] for a in vib["axes"]}
    series = []
    for q in ax["charge_per_delay_kg"]:
        pts = [p for p in vib["points"] if p["inputs"]["charge_per_delay_kg"] == q]
        series.append(
            chartkit.series(
                f"charge-{q:g}-kg".replace(".", "-"),
                bi(f"{q:g} kg per delay", f"{q:g} kg por retardo"),
                [p["inputs"]["distance_m"] for p in pts],
                [p["ppv_m_per_s"] * 1000.0 for p in pts],
                n=len(pts),
            )
        )
    limit = np.asarray(blasting.ppv_limit(np.array(ax["distance_m"]))) * 1000.0
    series.append(
        chartkit.series(
            "limit-30-cfr-816-67",
            bi("Limit, 30 CFR 816.67(d)(2)(i)", "Limite, 30 CFR 816.67(d)(2)(i)"),
            ax["distance_m"],
            limit,
            draw="step",
            n=len(limit),
        )
    )
    charts.append(
        chartkit.chart(
            "d1-ppv-curves",
            "D1",
            "line",
            bi("Peak particle velocity against distance", "Velocidad peak de particula segun distancia"),
            prod,
            SERVES_DESIGN,
            caption=bi(
                f"Square-root scaled-distance law with the illustrative site constants K = {fixed['k_site_m_per_s']:g} m/s and "
                f"beta = {fixed['beta']:g} (UNVERIFIED, not fitted on site data), against the regulatory limit.",
                f"Ley de distancia escalada con las constantes de sitio ilustrativas K = {fixed['k_site_m_per_s']:g} m/s y "
                f"beta = {fixed['beta']:g} (UNVERIFIED, no ajustadas con datos de sitio), contra el limite regulatorio.",
            ),
            x_axis=chartkit.axis("Distance to the receiver", "Distancia al receptor", "m", "log"),
            y_axis=chartkit.axis("Peak particle velocity", "Velocidad peak de particula", "mm/s", "log"),
            series=series,
        )
    )
    fly = grids["flyrock"]
    fx = {a["input"]: a["values"] for a in fly["axes"]}
    fseries = []
    for d in fx["fragment_diameter_m"]:
        pts = [p for p in fly["points"] if p["inputs"]["fragment_diameter_m"] == d]
        fseries.append(
            chartkit.series(
                f"fragment-{d * 1000:g}-mm".replace(".", "-"),
                bi(f"Fragment {d * 1000:g} mm", f"Fragmento {d * 1000:g} mm"),
                [p["inputs"]["launch_speed_m_per_s"] for p in pts],
                [p["flyrock_radius_m"] for p in pts],
                n=len(pts),
            )
        )
    charts.append(
        chartkit.chart(
            "d1-flyrock-curves",
            "D1",
            "line",
            bi("Flyrock radius against launch speed", "Radio de proyeccion segun velocidad de lanzamiento"),
            prod,
            SERVES_DESIGN,
            caption=bi(
                f"Ballistic range at a 45 degree launch with quadratic drag (C_D {fly['fixed_inputs']['drag_coefficient']:g}, air "
                f"{fly['fixed_inputs']['air_density_kg_per_m3']:g} kg/m3, rock {fly['fixed_inputs']['rock_density_kg_per_m3']:g} kg/m3).",
                f"Alcance balistico con lanzamiento a 45 grados y arrastre cuadratico (C_D {fly['fixed_inputs']['drag_coefficient']:g}, aire "
                f"{fly['fixed_inputs']['air_density_kg_per_m3']:g} kg/m3, roca {fly['fixed_inputs']['rock_density_kg_per_m3']:g} kg/m3).",
            ),
            x_axis=chartkit.axis("Launch speed", "Velocidad de lanzamiento", "m/s"),
            y_axis=chartkit.axis("Flyrock radius", "Radio de proyeccion", "m"),
            series=fseries,
        )
    )
    ppv_ref = next(
        p
        for p in vib["points"]
        if p["inputs"]["distance_m"] == ref["distance_m"]
        and p["inputs"]["charge_per_delay_kg"] == ref["charge_per_delay_kg"]
    )
    fly_ref = next(
        p
        for p in fly["points"]
        if p["inputs"]["launch_speed_m_per_s"] == ref["launch_speed_m_per_s"]
        and p["inputs"]["fragment_diameter_m"] == ref["fragment_diameter_m"]
    )
    reference_values |= {"ppv_m_per_s": ppv_ref["ppv_m_per_s"], "flyrock_radius_m": fly_ref["flyrock_radius_m"]}
    return {"grids": grids, "charts": charts, "reference": reference_values, "validity_warnings": dict(validity)}


def _pooled_markers(pooled: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for who, es, key in (("truth", "verdad", "gt"), ("U-Net", "U-Net", "unet")):
        for q in ("p50", "p80"):
            v = pooled[key][f"{q}_px"]
            out.append(
                {
                    "id": f"{key}-{q}",
                    "label": bi(f"{who} {q.upper()}", f"{es} {q.upper()}"),
                    "value_text": f"{v:.1f} px",
                    "orientation": "vertical",
                    "x": float(v),
                }
            )
    return out


def fold_outputs(report: Mapping[str, Any]) -> dict[str, Any]:
    """The TRTR charts and the rows of the summary from a `fold_report` document."""
    prod = chartkit.producer("pitstudio", TRTR_METHOD, _pitstudio_version(), TRTR_LABEL)
    folds = report["folds"]
    cats = [{"id": f"fold-{f['fold']}", "label": bi(f"Fold {f['fold']}", f"Particion {f['fold']}")} for f in folds]
    charts = [
        chartkit.chart(
            "d1-fold-iou",
            "D1",
            "bar",
            bi(
                "Foreground IoU of each fold, trained and tested on real images",
                "IoU de primer plano de cada particion, entrenado y probado en imagenes reales",
            ),
            prod,
            SERVES_TRTR,
            caption=bi(
                f"Mean per fold; the run evaluated in bf16, the CPU recomputes in fp32 (largest file difference "
                f"{report['iou_max_abs_difference_vs_run']:.4f}). {report['attribution']}",
                f"Media por particion; la corrida evaluo en bf16, la CPU recalcula en fp32 (mayor diferencia por archivo "
                f"{report['iou_max_abs_difference_vs_run']:.4f}). {report['attribution']}",
            ),
            y_axis=chartkit.axis("Foreground IoU", "IoU de primer plano", "1"),
            categories=cats,
            series=[
                chartkit.series(
                    "run",
                    bi("Stored by the training run", "Guardado por la corrida"),
                    None,
                    [f["test_fg_iou_mean_run"] for f in folds],
                ),
                chartkit.series(
                    "cpu",
                    bi("Recomputed on CPU", "Recalculado en CPU"),
                    None,
                    [f["test_fg_iou_mean_recomputed"] for f in folds],
                ),
            ],
        )
    ]
    pooled = report["pooled"]
    caption_psd = (
        f"Area-weighted passing by equivalent diameter in pixels (scale not recorded); {pooled['n_test']} test originals. "
        f"{report['attribution']}",
        f"Pasante por area segun diametro equivalente en pixeles (escala no registrada); {pooled['n_test']} originales de "
        f"prueba. {report['attribution']}",
    )
    grid = pooled["psd_curve"]["size_px"]
    psd_axes = {
        "x_axis": chartkit.axis("Equivalent diameter", "Diametro equivalente", "px", "log"),
        "y_axis": chartkit.axis("Passing, by area", "Pasante, por area", "1"),
    }
    charts.append(
        chartkit.chart(
            "d1-psd-pooled",
            "D1",
            "line",
            bi(
                "Instance size distribution: U-Net against the labelled truth",
                "Distribucion de tamanos de instancias: U-Net contra la verdad etiquetada",
            ),
            prod,
            SERVES_TRTR,
            caption=bi(*caption_psd),
            **psd_axes,
            series=[
                chartkit.series(
                    "truth",
                    bi("Labelled truth", "Verdad etiquetada"),
                    grid,
                    pooled["psd_curve"]["gt_passing"],
                    draw="step",
                    n=pooled["gt"]["n_instances"],
                ),
                chartkit.series(
                    "unet",
                    bi("U-Net (TRTR)", "U-Net (TRTR)"),
                    grid,
                    pooled["psd_curve"]["unet_passing"],
                    draw="step",
                    n=pooled["unet"]["n_instances"],
                ),
            ],
            markers=_pooled_markers(pooled),
        )
    )
    per_fold = [
        chartkit.series(
            "truth-pooled",
            bi("Labelled truth, all folds", "Verdad etiquetada, todas las particiones"),
            grid,
            pooled["psd_curve"]["gt_passing"],
            draw="step",
            n=pooled["gt"]["n_instances"],
        )
    ]
    per_fold += [
        chartkit.series(
            f"unet-fold-{f['fold']}",
            bi(f"U-Net, fold {f['fold']}", f"U-Net, particion {f['fold']}"),
            f["psd_curve"]["size_px"],
            f["psd_curve"]["unet_passing"],
            draw="step",
            n=f["unet"]["n_instances"],
        )
        for f in folds
    ]
    charts.append(
        chartkit.chart(
            "d1-psd-per-fold",
            "D1",
            "line",
            bi(
                "Instance size distribution of each fold's U-Net",
                "Distribucion de tamanos de instancias del U-Net de cada particion",
            ),
            prod,
            SERVES_TRTR,
            caption=bi(*caption_psd),
            **psd_axes,
            series=per_fold,
        )
    )
    charts.append(
        chartkit.chart(
            "d1-training-curves",
            "D1",
            "line",
            bi(
                "Validation foreground IoU during training",
                "IoU de primer plano de validacion durante el entrenamiento",
            ),
            prod,
            ["FR-012-29"],
            caption=bi(
                f"One point per epoch of each fold's stored training run. {report['attribution']}",
                f"Un punto por epoca de la corrida guardada de cada particion. {report['attribution']}",
            ),
            x_axis=chartkit.axis("Epoch", "Epoca", "1"),
            y_axis=chartkit.axis("Validation foreground IoU", "IoU de primer plano de validacion", "1"),
            series=[
                chartkit.series(
                    f"fold-{f['fold']}",
                    bi(f"Fold {f['fold']}", f"Particion {f['fold']}"),
                    f["training"]["epoch"],
                    f["training"]["val_fg_iou"],
                    n=len(f["training"]["epoch"]),
                )
                for f in folds
            ],
        )
    )
    cols = [
        ("fold", "Fold", "Particion", "text", None),
        ("n_test", "Test originals", "Originales de prueba", "number", "1"),
        ("iou", "IoU, CPU", "IoU, CPU", "number", "1"),
        ("p50_gt", "Truth P50", "P50 verdad", "number", "px"),
        ("p50_unet", "U-Net P50", "P50 U-Net", "number", "px"),
        ("p80_gt", "Truth P80", "P80 verdad", "number", "px"),
        ("p80_unet", "U-Net P80", "P80 U-Net", "number", "px"),
        ("over_gt", "Truth oversize", "Sobretamano verdad", "number", "1"),
        ("over_unet", "U-Net oversize", "Sobretamano U-Net", "number", "1"),
        ("x50_err", "Mean x50 error", "Error medio de x50", "number", "1"),
    ]
    rows = [
        [
            f"fold {f['fold']}",
            f["n_test"],
            f["test_fg_iou_mean_recomputed"],
            f["gt"]["p50_px"],
            f["unet"]["p50_px"],
            f["gt"]["p80_px"],
            f["unet"]["p80_px"],
            f["gt"]["oversize_share"],
            f["unet"]["oversize_share"],
            f["x50_relative_error_mean"],
        ]
        for f in folds
    ]
    rows.append(
        [
            "all folds",
            pooled["n_test"],
            report["recomputed_mean_iou"],
            pooled["gt"]["p50_px"],
            pooled["unet"]["p50_px"],
            pooled["gt"]["p80_px"],
            pooled["unet"]["p80_px"],
            pooled["gt"]["oversize_share"],
            pooled["unet"]["oversize_share"],
            float(np.mean(errs))
            if (errs := [f["x50_relative_error_mean"] for f in folds if f["x50_relative_error_mean"] is not None])
            else None,
        ]
    )
    charts.append(
        chartkit.chart(
            "d1-fold-table",
            "D1",
            "table",
            bi(
                "Per-fold TRTR results and instance size quantiles",
                "Resultados TRTR por particion y cuantiles de tamano de instancias",
            ),
            prod,
            SERVES_TRTR,
            caption=bi(
                f"Sizes in pixels; oversize = area share above {report['oversize_limit_px']:.0f} px. {report['attribution']}",
                f"Tamanos en pixeles; sobretamano = fraccion de area sobre {report['oversize_limit_px']:.0f} px. {report['attribution']}",
            ),
            table={
                "columns": [
                    {
                        "id": c[0].replace("_", "-"),
                        "label": bi(c[1], c[2]),
                        "type": c[3],
                        **({"unit": c[4]} if c[4] else {}),
                    }
                    for c in cols
                ],
                "rows": rows,
            },
        )
    )
    return {"charts": charts, "rows": rows}


def _pitstudio_version() -> str:
    try:
        return metadata.version("pitstudio")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def summary_document(design: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    ref = design["reference"]
    pooled = report["pooled"]
    coarser = pooled["unet"]["p50_px"] / pooled["gt"]["p50_px"] - 1.0
    return {
        "methods": ["M11", "M12"],
        "title": "Blast design grids (Kuz-Ram/KCO, vibration, flyrock) and the five-fold TRTR U-Net with its instance size distributions",
        "label": f"{DESIGN_LABEL}; {TRTR_LABEL}",
        "verdict": "ok",
        "headline": [
            {
                "name": "P80 of the muck pile, reference design",
                "value": round(ref["x80_m"] * 1000.0, 4),
                "unit": "mm",
                "kpi": "p80",
            },
            {
                "name": "Oversize, reference design",
                "value": round(ref["oversize_pct"], 4),
                "unit": "%",
                "kpi": "oversize",
            },
            {
                "name": "Peak particle velocity, reference design",
                "value": round(ref["ppv_m_per_s"] * 1000.0, 4),
                "unit": "mm/s",
                "kpi": "ppv",
                "note": "illustrative site constants (UNVERIFIED)",
            },
            {
                "name": "Flyrock radius, reference design",
                "value": round(ref["flyrock_radius_m"], 4),
                "unit": "m",
                "kpi": "flyrock_radius",
            },
            {
                "name": "Mean foreground IoU, five folds (CPU)",
                "value": round(report["recomputed_mean_iou"], 5),
                "unit": "1",
            },
            {
                "name": "Worst fold IoU (CPU)",
                "value": round(min(f["test_fg_iou_mean_recomputed"] for f in report["folds"]), 5),
                "unit": "1",
            },
        ],
        "rows": [
            {
                "fold": f["fold"],
                "test_fg_iou": round(f["test_fg_iou_mean_recomputed"], 5),
                "test_fg_iou_run": f["test_fg_iou_mean_run"],
                "n_train": f["n_train"],
                "n_test": f["n_test"],
                "truth_p50_px": round(f["gt"]["p50_px"], 2),
                "unet_p50_px": round(f["unet"]["p50_px"], 2),
                "unet_oversize_share": round(f["unet"]["oversize_share"], 4),
                "truth_oversize_share": round(f["gt"]["oversize_share"], 4),
            }
            for f in report["folds"]
        ],
        "extra": {
            "size_basis_design": "sieve size of the blasted rock, m (x50, x80), mass passing",
            "size_basis_image": report["size_basis"],
            "reference_design": ref,
            "finding": (
                f"The U-Net instance distribution is coarser than the labelled truth: pooled P50 {pooled['unet']['p50_px']:.1f} px "
                f"against {pooled['gt']['p50_px']:.1f} px ({coarser * 100:.0f} percent), oversize share {pooled['unet']['oversize_share']:.3f} "
                f"against {pooled['gt']['oversize_share']:.3f}. The cause (merged neighbouring fragments are a likely one) is UNVERIFIED: it was not tested."
            ),
            "iou_reproduction": {
                "max_abs_difference_per_file": report["iou_max_abs_difference_vs_run"],
                "files_within_1e-4": sum(f["iou_files_reproduced"] for f in report["folds"]),
                "files": sum(f["n_test"] for f in report["folds"]),
                "cause": "UNVERIFIED: the run evaluated in bf16 autocast, this stage in fp32 on the CPU",
            },
            "device": report["device"],
            "minephys": minephys_identity(),
            "design_validity_warnings_by_argument": design["validity_warnings"],
            "design_note": "grid points whose Kuz-Ram uniformity index lies outside the typical 0.8 to 1.5 (UNVERIFIED range) are counted here, not hidden",
        },
    }


def stage(job: Mapping[str, Any]) -> dict[str, Any]:
    """Runner stage: grids, per-fold report, charts and summary into the job's output folder."""
    params, out = job["params"], Path(job["output_dir"])
    models, data = Path(os.environ["PITSTUDIO_MODELS"]), Path(os.environ["PITSTUDIO_DATA"])
    design = design_outputs(params)
    images = np.load(data / params["folds"]["data"] / "images.npy", mmap_mode="r")
    labels = np.load(data / params["folds"]["data"] / "labels.npy", mmap_mode="r")
    report = fold_report.build_report(models / params["folds"]["run_dir"], images, labels)
    results = fold_outputs(report)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, doc in design["grids"].items():
        paths.append(out / f"design-grid-{name}.json")
        paths[-1].write_text(json.dumps(doc, indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    fold_report.write_report(report, out / "fold-report.json")
    paths.append(out / "fold-report.json")
    summary = summary_document(design, report)
    paths.append(out / "results-summary.json")
    paths[-1].write_text(json.dumps(summary, indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    paths += [chartkit.write(c, out / "charts") for c in (*design["charts"], *results["charts"])]
    return {"outputs": [{"path": p.relative_to(out).as_posix()} for p in paths]}


def main(argv: list[str] | None = None) -> int:
    from pitstudio_stagekit import main as kit_main

    return kit_main(stage, argv)


if __name__ == "__main__":
    raise SystemExit(main())

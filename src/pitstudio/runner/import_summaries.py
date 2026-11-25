"""Derived outputs of `studio import-run`: small published summaries and results bundles computed from the files of a
finished job (never from memory). A builder reads the job's `--from` folder and returns a JSON document; a source it
needs but cannot find raises `Missing`, which the import reports as a usage error naming the file.

A summary has one shape, read by the case page ("Published results"): `title`, `label` (the data label), `methods`
(registry method ids the result used), `verdict`
(`ok`, `partial` or `failed`), `headline` (named values with unit; an optional `kpi` names the case KPI the
value measures) and `rows` (small tables). A results bundle follows
contracts/results.schema.json (DC-020-02) and is written to web/public/results/ by `studio publish`.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Callable
from pathlib import Path
from typing import Any

SYNTH = "calibrated synthetic, not validated against real data"
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 9: 2.262, 29: 2.045}


class Missing(Exception):
    """A file or field the builder needs is absent."""


def _json(src: Path, name: str) -> Any:
    try:
        return json.loads((src / name).read_text(encoding="utf-8"))
    except OSError, ValueError:
        raise Missing(f"{name} is not readable in the --from folder") from None


def _hw(name: str, value: float, unit: str, note: str = "", kpi: str = "") -> dict:
    """One headline value; `kpi` is the id of the case KPI it measures, written only when it is that KPI (FR-018-74)."""
    return {
        "name": name,
        "value": round(value, 4),
        "unit": unit,
        **({"note": note} if note else {}),
        **({"kpi": kpi} if kpi else {}),
    }


def c1_summary(src: Path, run_id: str) -> dict:
    train, ttf, export = (_json(src, f) for f in ("training-manifest.json", "ttf-results.json", "export-report.json"))
    by: dict[str, list[float]] = {}
    for e in ttf["events"]:
        by.setdefault(e["method"], []).append(abs(e["error_h"]))
    names = {
        "inverse_velocity": "Inverse velocity",
        "bayesian_ttf": "Bayesian time to failure",
        "tcn": "TCN",
        "patchtst": "PatchTST",
        "chronos_bolt_fine_tuned": "Chronos-Bolt fine-tuned",
        "chronos_bolt_zero_shot": "Chronos-Bolt zero-shot",
    }
    rows: list[dict[str, Any]] = [
        {
            "method": names[m],
            "n": len(v),
            "mean_abs_error_h": round(statistics.fmean(v), 2),
            "median_abs_error_h": round(statistics.median(v), 2),
        }
        for m, v in by.items()
        if m in names
    ]
    best = min(rows, key=lambda r: r["mean_abs_error_h"])
    arms = {a["arm"]: a for a in train["arms"]}
    return {
        "methods": ["M14"],
        "title": "Slope time-to-failure forecasters: TCN, PatchTST and Chronos-Bolt against inverse velocity",
        "label": SYNTH + "; nominal signal-to-noise strata, no observed SNR; one real event not run",
        "verdict": "ok",
        "headline": [
            _hw(
                f"Mean absolute forecast error, {best['method']}",
                best["mean_abs_error_h"],
                "h",
                "best of the six methods",
                kpi="forecast_error",
            ),
            _hw(
                "Mean absolute forecast error, inverse velocity",
                next(r for r in rows if r["method"] == "Inverse velocity")["mean_abs_error_h"],
                "h",
                "classical baseline",
            ),
            _hw(
                "Training GPU-hours, three arms",
                train["budget"]["total_gpu_hours"],
                "h",
                f"budget {train['budget']['budget_gpu_hours']} h",
            ),
        ],
        "rows": rows,
        "extra": {
            "events_per_method": len(by["tcn"]),
            "validation_pinball": {a: round(arms[a]["validation_pinball"], 4) for a in arms},
            "onnx_export": {a: v["lane"] for a, v in export["arms"].items()},
            "acceptance": "SC-010-01 not run: the observed SNR is unavailable",
        },
    }


def _paired_t(a: list[float], b: list[float]) -> tuple[float, float, int]:
    d = [x - y for x, y in zip(a, b, strict=True)]
    n, m = len(d), statistics.fmean(d)
    half = 1.96 * statistics.stdev(d) / math.sqrt(n)
    return m - half, m + half, n


def c1_bundle(src: Path, run_id: str) -> dict:
    ttf = _json(src, "ttf-results.json")
    err: dict[str, dict[tuple[str, float], float]] = {}
    for e in ttf["events"]:
        err.setdefault(e["method"], {})[(e["event_id"], e["cutoff"])] = abs(e["error_h"])
    keys = sorted(err["inverse_velocity"])
    base = [err["inverse_velocity"][k] for k in keys]
    metric = {
        "id": "forecast_error",
        "name": {"en": "Forecast error (absolute, hours)", "es": "Error de pronóstico (absoluto, horas)"},
        "unit": "h",
        "orientation": "lower-is-better",
    }
    rows = []
    for m, label in (("tcn", "TCN"), ("patchtst", "PatchTST")):
        lo, hi, n = _paired_t([err[m][k] for k in keys], base)
        verdict = "challenger-better" if hi < 0 else "baseline-better" if lo > 0 else "no-significant-difference"
        rows.append(
            {
                "kind": "paired",
                "group": f"c1-{m}",
                "metric": metric,
                "challenger": label,
                "baseline": "Inverse velocity",
                "pairing_unit": {"en": "test event and cutoff", "es": "evento de prueba y corte"},
                "n": n,
                "interval": {"lo": round(lo, 3), "hi": round(hi, 3), "level": 0.95, "method": "paired-t"},
                "verdict": verdict,
            }
        )
    return {
        "schema_version": "1.0",
        "kind": "comparison",
        "id": "c1-slope-forecasters",
        "tab": "learned-vs-classical",
        "title": {
            "en": "C1 slope forecasters against inverse velocity",
            "es": "C1 pronosticadores de talud frente a velocidad inversa",
        },
        "cases": ["C1"],
        "run_ids": [run_id],
        "criteria": [],
        "rows": rows,
    }


def d1_summary(src: Path, run_id: str) -> dict:
    s = _json(src, "summary.json")
    folds = [_json(src, f"fold{i}/result.json") for i in range(len(s["folds"]))]
    return {
        "methods": ["M11"],
        "title": "Fragmentation U-Net, trained and tested on real images, five scene-grouped folds",
        "label": "real images (Mendeley Data 78ht3pjsr4, CC BY 4.0); metrics only, no image is published",
        "verdict": "ok",
        "headline": [
            _hw("Mean foreground IoU, five folds", s["mean"], "1"),
            _hw("Fold standard deviation", s["std"], "1"),
            _hw("Worst fold", s["min"], "1"),
        ],
        "rows": [
            {"fold": f["fold"], "test_fg_iou": f["test_fg_iou_mean"], "n_train": f["n_train"], "n_test": f["n_test"]}
            for f in folds
        ],
        "extra": {
            "arm": s["arm"],
            "encoder": folds[0]["encoder"],
            "loss": folds[0]["loss"],
            "precision": folds[0]["precision"],
            "train_gpu_hours": round(sum(f["train_s"] for f in folds) / 3600, 3),
        },
    }


def d1_bundle(src: Path, run_id: str) -> dict:
    s = _json(src, "summary.json")
    n, half = len(s["folds"]), T975[len(s["folds"]) - 1] * s["std"] / math.sqrt(len(s["folds"]))
    return {
        "schema_version": "1.0",
        "kind": "comparison",
        "id": "d1-unet-trtr-iou",
        "tab": "sim-to-real",
        "title": {
            "en": "D1 fragmentation U-Net, real-image IoU",
            "es": "D1 U-Net de fragmentación, IoU en imágenes reales",
        },
        "cases": ["D1"],
        "run_ids": [run_id],
        "criteria": [],
        "rows": [
            {
                "kind": "estimate",
                "group": "d1-trtr",
                "metric": {
                    "id": "tstr_trtr_iou",
                    "name": {
                        "en": "Foreground IoU, trained and tested on real images",
                        "es": "IoU de primer plano, entrenado y probado en imágenes reales",
                    },
                    "unit": "1",
                    "orientation": "higher-is-better",
                },
                "system": "U-Net, trained on real images (TRTR), five folds",
                "n": n,
                "value": s["mean"],
                "interval": {
                    "lo": round(s["mean"] - half, 5),
                    "hi": round(s["mean"] + half, 5),
                    "level": 0.95,
                    "method": "t",
                },
            }
        ],
    }


def a3_summary(src: Path, run_id: str) -> dict:
    r = _json(src, "results.json")
    sm = r["summary"]
    return {
        "methods": ["M7"],
        "title": "Granular repose angle of the discrete element model at 20,000 particles, five seeds",
        "label": SYNTH,
        "verdict": "ok" if r.get("complete") else "partial",
        "headline": [
            _hw("Mean repose angle", sm["mean_deg"], "deg", f"{sm['n_seeds']} seeds"),
            _hw("95 % interval half-width", sm["ci95_half_width_deg"], "deg", "Student t"),
            _hw("Seed standard deviation", sm["std_deg"], "deg"),
        ],
        "rows": [
            {"seed": s, "repose_deg": round(a, 3)} for s, a in zip(r["seeds"], r["repose_angles_deg"], strict=True)
        ],
        "extra": {
            "particles": r["n_particles"],
            "protocol": r["protocol"],
            "steps_per_s_mean": round(r["steps_per_s"]["mean_of_run_means"], 1),
        },
    }


def gns_summary(src: Path, run_id: str) -> dict:
    ev = _json(src, "evaluation.published.json")
    g = ev["geometries"]
    passed, diverged = sum(1 for x in g if x["pass"]), sum(1 for x in g if x.get("diverged"))
    card = _json(src, "export_card.json")
    return {
        "methods": ["M8"],
        "title": "Graph network simulator v1 against the discrete element reference: FAILED acceptance SC-011-01",
        "label": SYNTH,
        "verdict": "failed",
        "headline": [
            _hw("Geometries passing the criterion", passed, "of 20", "criterion SC-011-01: failed"),
            _hw("Geometries whose rollout diverged", diverged, "of 20"),
            _hw("Repose tolerance", ev["limits"]["repose_abs_deg_max"], "deg"),
        ],
        "rows": [
            {
                "geometry": x["geometry_id"],
                "family": x["family"],
                "pass": x["pass"],
                "diverged": bool(x.get("diverged")),
                "reason": x.get("reason"),
            }
            for x in g
        ],
        "extra": {
            "sc_011_01": ev["sc_011_01"],
            "verdict_text": "Not a working model: it does not meet SC-011-01, published only as a failed evaluation.",
            "export_parity_passed": card["parity"]["passed"],
        },
    }


def scene_summary(src: Path, run_id: str) -> dict:
    tiles = _json(src, "scene/terrain/tiles.json")
    report = _json(src, "scene/validation/scene-validation-report.json")
    manifest = _json(src, "scene/scene.manifest.json")
    boxes = [t["bbox"] for t in tiles["tiles"]]
    ext = {
        k: round(max(b[k] for b in boxes) - min(b[k.replace("max", "min")] for b in boxes), 1)
        for k in ("x_max_m", "y_max_m", "z_max_m")
    }
    dem = next(i for i in manifest["inputs"] if i["kind"] == "dem")
    return {
        "methods": [],
        "title": "Bingham Canyon pit terrain, real elevation model baked to a quadtree of terrain tiles",
        "label": "real USGS 3DEP terrain (QL2 elevation model, 2018 acquisition), public domain",
        "verdict": "ok" if report["passed"] else "failed",
        "headline": [
            _hw(
                "Terrain tiles per level of detail",
                tiles["lods"][0]["tile_count"],
                "tiles",
                f"{len(tiles['lods'])} levels",
            ),
            _hw("East-west extent", ext["x_max_m"], "m"),
            _hw("North-south extent", ext["y_max_m"], "m"),
            _hw("Relief", ext["z_max_m"], "m"),
        ],
        "rows": [
            {"lod": lod["lod"], "max_error_m": lod["max_error_m"], "tiles": lod["tile_count"]} for lod in tiles["lods"]
        ],
        "extra": {
            "scene_validation": report["status"],
            "dem_source": dem["source"],
            "dem_sha256": dem["sha256"],
            "horizontal_epsg": dem["crs"]["horizontal"]["epsg"],
            "grid_elevation_sha256": tiles["grid_elevation_sha256"],
            "fixture": bool(tiles.get("fixture")),
        },
    }


def _producer(args: dict | None, method: str) -> dict:
    """The producer block of a chart series: the tool and version of the import spec, the method, the data label."""
    given = (args or {}).get("producer")
    if not isinstance(given, dict) or not given.get("tool") or not given.get("version"):
        raise Missing("the chart builder needs derive_args.producer with a tool and a version")
    return {"tool": given["tool"], "method": method, "version": given["version"], "label": SYNTH}


def _chart(case: str, id_: str, chart_type: str, title: dict, producer: dict, serves: list[str], **rest: Any) -> dict:
    return {
        "schema_version": "1.0",
        "kind": "chart-series",
        "id": id_,
        "case": case,
        "chart_type": chart_type,
        "status": "ok",
        "title": title,
        "producer": producer,
        "serves": serves,
        **rest,
    }


def a3_repose_chart(src: Path, run_id: str, args: dict | None = None) -> dict:
    """A3: the repose angle of each seed and the mean with its Student t interval (FR-018-86)."""
    r = _json(src, "results.json")
    producer = _producer(args, "granular discrete element model, repose angle of the settled heap")
    title = {"en": "Angle of repose by seed", "es": "Ángulo de reposo por semilla"}
    serves = ["FR-018-86", "FR-018-16", "FR-020-56"]
    if not r.get("complete") or "summary" not in r:
        return _chart(
            "A3",
            "a3-repose-by-seed",
            "bar",
            title,
            producer,
            serves,
            status="not-run",
            not_run_reason={
                "en": "The five-seed run is not complete, so no repose angle is published.",
                "es": "La corrida de cinco semillas no está completa, así que no se publica ningún ángulo de reposo.",
            },
        )
    sm = r["summary"]
    seeds = list(r["seeds"])
    angles = [round(float(a), 4) for a in r["repose_angles_deg"]]
    lo, hi = (round(float(v), 4) for v in sm["ci95_deg"])
    return _chart(
        "A3",
        "a3-repose-by-seed",
        "bar",
        title,
        producer,
        serves,
        caption={
            "en": f"{r['n_particles']:,} particles, {sm['n_seeds']} seeds; "
            "the mean bar carries the 95 % interval of the mean.",
            "es": f"{r['n_particles']:,} partículas, {sm['n_seeds']} semillas; "
            "la barra de la media lleva su intervalo del 95 %.",
        },
        y_axis={"label": {"en": "Angle of repose", "es": "Ángulo de reposo"}, "unit": "deg"},
        categories=[
            *({"id": f"seed-{s}", "label": {"en": f"Seed {s}", "es": f"Semilla {s}"}} for s in seeds),
            {"id": "mean", "label": {"en": "Mean", "es": "Media"}},
        ],
        series=[
            {
                "id": "repose",
                "label": {"en": "Angle of repose", "es": "Ángulo de reposo"},
                "y": [*angles, round(float(sm["mean_deg"]), 4)],
                "lo": [*([None] * len(angles)), lo],
                "hi": [*([None] * len(angles)), hi],
                "band_label": {
                    "en": f"95 % interval of the mean, Student t, n = {sm['n_seeds']}",
                    "es": f"Intervalo del 95 % de la media, t de Student, n = {sm['n_seeds']}",
                },
            }
        ],
    )


def a3_gns_chart(src: Path, run_id: str, args: dict | None = None) -> dict:
    """A3: the rollout position error of the graph network simulator against the step, over the evaluated geometries."""
    ev = _json(src, "evaluation.published.json")
    producer = _producer(args, "graph network simulator rollout against the discrete element reference")
    title = {"en": "GNS v1 rollout error against steps", "es": "Error de rollout de GNS v1 contra pasos"}
    serves = ["FR-018-86", "FR-018-16", "FR-020-56"]
    curves = [g["position_error_growth"] for g in ev["geometries"] if g.get("position_error_growth")]
    if not curves:
        return _chart(
            "A3",
            "a3-gns-rollout-error",
            "line",
            title,
            producer,
            serves,
            status="not-run",
            not_run_reason={
                "en": "No geometry produced a rollout error curve.",
                "es": "Ninguna geometría produjo una curva de error de rollout.",
            },
        )
    steps = max(len(c) for c in curves)
    xs, med, lo, hi = [], [], [], []
    for k in range(steps):
        vals = sorted(float(c[k]) for c in curves if len(c) > k)
        xs.append(k)
        med.append(round(statistics.median(vals), 6))
        lo.append(round(vals[0], 6))
        hi.append(round(vals[-1], 6))
    geos = ev["geometries"]
    diverged = sorted(
        int(g["diverged_at_step"]) for g in geos if g.get("diverged") and g.get("diverged_at_step") is not None
    )
    markers = (
        [
            {
                "id": "first-divergence",
                "label": {"en": "First rollout to diverge", "es": "Primer rollout que diverge"},
                "value_text": f"step {diverged[0]}",
                "orientation": "vertical",
                "x": diverged[0],
            },
            {
                "id": "last-divergence",
                "label": {"en": "Last rollout to diverge", "es": "Último rollout que diverge"},
                "value_text": f"step {diverged[-1]}",
                "orientation": "vertical",
                "x": diverged[-1],
            },
        ]
        if diverged
        else []
    )
    n_div = sum(1 for g in geos if g.get("diverged"))
    return _chart(
        "A3",
        "a3-gns-rollout-error",
        "line",
        title,
        producer,
        serves,
        caption={
            "en": f"{n_div} of {len(geos)} geometries diverged; the curve is the median over the geometries still "
            "rolling out at each step, the band their minimum and maximum. Acceptance SC-011-01: failed.",
            "es": f"{n_div} de {len(geos)} geometrías divergieron; la curva es la mediana de las geometrías que aún "
            "avanzan en cada paso, la banda su mínimo y máximo. Criterio SC-011-01: no cumplido.",
        },
        x_axis={"label": {"en": "Rollout step", "es": "Paso de rollout"}, "unit": "1"},
        y_axis={
            "label": {"en": "Mean position error per grain", "es": "Error medio de posición por grano"},
            "unit": "m",
        },
        series=[
            {
                "id": "median-error",
                "label": {"en": "Median over geometries", "es": "Mediana entre geometrías"},
                "x": xs,
                "y": med,
                "lo": lo,
                "hi": hi,
                "band_label": {"en": "minimum to maximum over geometries", "es": "mínimo a máximo entre geometrías"},
            }
        ],
        **({"markers": markers} if markers else {}),
    )


BUILDERS: dict[str, Callable[..., dict]] = {
    "c1-summary": c1_summary,
    "c1-bundle": c1_bundle,
    "d1-summary": d1_summary,
    "d1-bundle": d1_bundle,
    "a3-summary": a3_summary,
    "gns-summary": gns_summary,
    "scene-summary": scene_summary,
    "a3-repose-chart": a3_repose_chart,
    "a3-gns-chart": a3_gns_chart,
}

TAKES_ARGS = {"a3-repose-chart", "a3-gns-chart"}


def build(name: str, src: Path, run_id: str, args: dict | None = None) -> bytes:
    if name not in BUILDERS:
        raise Missing(f"unknown builder {name}")
    doc = BUILDERS[name](src, run_id, args) if name in TAKES_ARGS else BUILDERS[name](src, run_id)
    return (json.dumps(doc, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")

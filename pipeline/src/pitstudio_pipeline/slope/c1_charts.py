"""The C1 charts as chart-series documents (DC-020-05, ``specs/020-web-knowledge/contracts/chart-series.schema.json``).

Each builder turns the JSON a ``c1_results`` sub-command wrote into chart documents that the generic chart reader of the
Charts tab draws; nothing here draws. Every chart carries its producer (tool, method, version, label) and the ids of the
requirements it serves; a value that was not computed is a chart in the state ``not-run`` with its reason and no data.
No interval is drawn without its paired or bootstrap source in the results, no verdict is drawn for the
single real event.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
METHODS = ("inverse_velocity", "bayesian_ttf", "tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned")
LEARNED = METHODS[2:]
NAMES = {
    "inverse_velocity": ("Inverse velocity", "Velocidad inversa"),
    "bayesian_ttf": ("Bayesian time to failure", "Tiempo a la falla bayesiano"),
    "tcn": ("TCN", "TCN"),
    "patchtst": ("PatchTST", "PatchTST"),
    "chronos_bolt_zero_shot": ("Chronos-Bolt zero-shot", "Chronos-Bolt sin ajuste"),
    "chronos_bolt_fine_tuned": ("Chronos-Bolt fine-tuned", "Chronos-Bolt ajustado"),
}
STRATUM_NAMES = {
    "nominal_10": ("Nominal SNR 10", "SNR nominal 10"),
    "nominal_30": ("Nominal SNR 30", "SNR nominal 30"),
    "nominal_100": ("Nominal SNR 100", "SNR nominal 100"),
}
WALL_METHOD = "Bishop and Spencer limit equilibrium over a circle grid, generalised Hoek-Brown, Monte Carlo PoF"
WALL_LABEL = "illustrative rock-mass inputs, UNVERIFIED; 3DEP 2018 DEM section; educational, not design software"
REAL_LABEL = "single real event — no significance test"
REAL_LABEL_ES = "evento real único — sin prueba de significancia"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _version() -> str:
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip() or "0"
    except OSError:
        return "0"


def producer(method: str, label: str) -> dict[str, str]:
    """The producer object of a chart: tool, method, version and the data label of the run."""
    return {"tool": "pitstudio", "method": method[:160], "version": _version(), "label": label[:200]}


def _t(en: str, es: str) -> dict[str, str]:
    for s in (en, es):
        if not 1 <= len(s) <= 200:
            raise ValueError(f"text of {len(s)} characters is outside 1..200: {s[:60]!r}")
    return {"en": en, "es": es}


def _num(v: Any) -> float | None:
    f = float(v)
    return f if math.isfinite(f) else None


def _nums(values: Sequence[Any]) -> list[float | None]:
    return [_num(v) for v in values]


def _base(
    chart_id: str, chart_type: str, title: dict[str, str], prod: Mapping[str, str], serves: list[str]
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "chart-series",
        "id": chart_id,
        "case": "C1",
        "chart_type": chart_type,
        "status": "ok",
        "title": title,
        "producer": dict(prod),
        "serves": serves,
    }


def _not_run(
    chart_id: str, title: dict[str, str], prod: Mapping[str, str], serves: list[str], reason: dict[str, str]
) -> dict[str, Any]:
    c = _base(chart_id, "table", title, prod, serves)
    c["status"] = "not-run"
    c["not_run_reason"] = reason
    return c


def _cat(method: str) -> dict[str, Any]:
    return {"id": slug(method), "label": _t(*NAMES[method])}


def _cut(c: float) -> str:
    return f"{round(c * 10):02d}"


# ---------------------------------------------------------------------------------------------------------- U1


def error_charts(results: Mapping[str, Any], *, producer: Mapping[str, str]) -> list[dict[str, Any]]:
    """Median error and paired differences with their intervals, the error CDFs, the error table, SC-010-01 not run."""
    out: list[dict[str, Any]] = []
    strata = [s for s in STRATUM_NAMES if any(r["stratum"] == s for r in results["summary"])]
    cutoffs = sorted({r["cutoff"] for r in results["summary"]})
    n_comp = results["statement"]["comparisons"]
    for c in cutoffs:
        cid = f"c1-median-error-cutoff-{_cut(c)}"
        chart = _base(
            cid,
            "bar",
            _t(f"Median TTF error by method, cut-off {c}", f"Error mediano de TTF por método, corte {c}"),
            producer,
            ["FR-010-23", "FR-010-24"],
        )
        chart["caption"] = _t(
            "Median relative error |t_hat - t_f| / (t_f - t_c) with its 95 % percentile bootstrap interval, per "
            "noise stratum. "
            "Nominal SNR: the observed SNR is not available.",
            "Error relativo mediano |t_hat - t_f| / (t_f - t_c) con su intervalo bootstrap percentil del 95 %, "
            "por estrato de ruido. "
            "SNR nominal: no hay SNR observado.",
        )
        chart["y_axis"] = {"label": _t("Median relative error", "Error relativo mediano"), "unit": "1"}
        chart["categories"] = [_cat(m) for m in METHODS]
        chart["series"] = []
        for s in strata:
            rows = {r["method"]: r for r in results["median_intervals"] if r["stratum"] == s and r["cutoff"] == c}
            chart["series"].append(
                {
                    "id": slug(s),
                    "label": _t(*STRATUM_NAMES[s]),
                    "y": [_num(rows[m]["median_rel_error"]) for m in METHODS],
                    "lo": [_num(rows[m]["interval"]["lower"]) for m in METHODS],
                    "hi": [_num(rows[m]["interval"]["upper"]) for m in METHODS],
                    "n": int(rows["tcn"]["n_events"]),
                    "band_label": _t(
                        "95 % percentile bootstrap interval of the median",
                        "Intervalo bootstrap percentil del 95 % de la mediana",
                    ),
                }
            )
        out.append(chart)
    for c in cutoffs:
        cid = f"c1-paired-difference-cutoff-{_cut(c)}"
        chart = _base(
            cid,
            "bar",
            _t(
                f"Paired difference to inverse velocity, cut-off {c}",
                f"Diferencia pareada con velocidad inversa, corte {c}",
            ),
            producer,
            ["FR-010-25", "SC-010-02"],
        )
        chart["caption"] = _t(
            f"Mean of e(inverse velocity) - e(model) over the same events, paired 95 % bootstrap interval; above "
            f"0 favours the "
            f"model. {n_comp} comparisons made, no family-wise claim.",
            f"Media de e(velocidad inversa) - e(modelo) sobre los mismos eventos, intervalo bootstrap pareado del "
            f"95 %; sobre 0 "
            f"favorece al modelo. {n_comp} comparaciones, sin afirmación conjunta.",
        )
        chart["y_axis"] = {
            "label": _t("Paired mean difference of the relative error", "Diferencia media pareada del error relativo"),
            "unit": "1",
        }
        chart["categories"] = [_cat(m) for m in LEARNED]
        chart["series"] = []
        for s in strata:
            rows = {r["method"]: r for r in results["comparisons"] if r["stratum"] == s and r["cutoff"] == c}
            if not all(m in rows and "interval" in rows[m] for m in LEARNED):
                continue
            chart["series"].append(
                {
                    "id": slug(s),
                    "label": _t(*STRATUM_NAMES[s]),
                    "y": [_num(rows[m]["mean_difference"]) for m in LEARNED],
                    "lo": [_num(rows[m]["interval"]["lower"]) for m in LEARNED],
                    "hi": [_num(rows[m]["interval"]["upper"]) for m in LEARNED],
                    "n": int(rows["tcn"]["n_pairs"]),
                    "band_label": _t(
                        "95 % paired percentile bootstrap interval", "Intervalo bootstrap percentil pareado del 95 %"
                    ),
                }
            )
        chart["markers"] = [
            {
                "id": "no-difference",
                "label": _t("No difference to inverse velocity", "Sin diferencia con velocidad inversa"),
                "value_text": "0",
                "orientation": "horizontal",
                "y": 0.0,
            }
        ]
        out.append(chart)
    for s in strata:
        for c in cutoffs:
            dist = [d for d in results["distributions"] if d["stratum"] == s and d["cutoff"] == c]
            if not dist:
                continue
            chart = _base(
                f"c1-error-ecdf-{slug(s)}-cutoff-{_cut(c)}",
                "ecdf",
                _t(
                    f"Error distribution, {STRATUM_NAMES[s][0]}, cut-off {c}",
                    f"Distribución del error, {STRATUM_NAMES[s][1]}, corte {c}",
                ),
                producer,
                ["FR-010-23"],
            )
            chart["caption"] = _t(
                "Share of the 500 test events whose relative TTF error is at most x, per method; steps at the "
                "horizon cap "
                "are events with no failure predicted.",
                "Fracción de los 500 eventos de prueba con error relativo de TTF menor o igual a x, por método; "
                "los escalones "
                "en el tope son eventos sin falla pronosticada.",
            )
            chart["x_axis"] = {"label": _t("Relative TTF error", "Error relativo de TTF"), "unit": "1"}
            chart["y_axis"] = {"label": _t("Share of events", "Fracción de eventos"), "unit": "1"}
            by = {d["method"]: d for d in dist}
            chart["series"] = [
                {
                    "id": slug(m),
                    "label": _t(*NAMES[m]),
                    "draw": "step",
                    "n": int(by[m]["n_events"]),
                    "x": list(by[m]["ecdf"]["x"]),
                    "y": list(by[m]["ecdf"]["p"]),
                }
                for m in METHODS
                if m in by
            ]
            out.append(chart)
    table = _base(
        "c1-error-table",
        "table",
        _t("Error by method, stratum and cut-off", "Error por método, estrato y corte"),
        producer,
        ["FR-010-23"],
    )
    table["caption"] = _t(
        "Median, mean and 90th percentile of the relative TTF error and the median absolute error in hours; "
        "nominal SNR strata.",
        "Mediana, media y percentil 90 del error relativo de TTF y mediana del error absoluto en horas; estratos "
        "de SNR nominal.",
    )
    table["table"] = {
        "columns": [
            {"id": "method", "label": _t("Method", "Método"), "type": "text"},
            {"id": "stratum", "label": _t("Stratum", "Estrato"), "type": "text"},
            {"id": "cutoff", "label": _t("Cut-off", "Corte"), "type": "number", "unit": "1"},
            {"id": "n-events", "label": _t("Events", "Eventos"), "type": "number", "unit": "1"},
            {"id": "median-error", "label": _t("Median error", "Error mediano"), "type": "number", "unit": "1"},
            {"id": "mean-error", "label": _t("Mean error", "Error medio"), "type": "number", "unit": "1"},
            {"id": "p90-error", "label": _t("90th percentile", "Percentil 90"), "type": "number", "unit": "1"},
            {
                "id": "median-abs-error-h",
                "label": _t("Median absolute error", "Error absoluto mediano"),
                "type": "number",
                "unit": "h",
            },
        ],
        "rows": [
            [
                NAMES[r["method"]][0],
                STRATUM_NAMES.get(r["stratum"], (r["stratum"], r["stratum"]))[0],
                r["cutoff"],
                r["n_events"],
                round(r["median_rel_error"], 4),
                round(r["mean_rel_error"], 4),
                round(r["p90_rel_error"], 4),
                round(r["median_abs_error_h"], 2),
            ]
            for r in results["summary"]
        ],
    }
    out.append(table)
    out.append(
        _not_run(
            "c1-acceptance-sc-010-01",
            _t("Acceptance at the observed SNR (SC-010-01)", "Aceptación con el SNR observado (SC-010-01)"),
            producer,
            ["SC-010-01", "FR-010-24"],
            _t(
                "Observed SNR unavailable: the real series was not ingested, the strata use the nominal SNR 10, "
                "30 and 100.",
                "SNR observado no disponible: la serie real no se ingirió, los estratos usan SNR nominal 10, 30 y 100.",
            ),
        )
    )
    return out


# ---------------------------------------------------------------------------------------------------------- U2

_ARM_ORDER = ("inverse_velocity", "bayesian_ttf", "tcn", "patchtst", "chronos_bolt_fine_tuned")


def _ordered(lo: Sequence[Any], mid: Sequence[Any], hi: Sequence[Any]) -> bool:
    """True when lo <= mid <= hi at every step (a band whose model quantile paths cross is not drawn)."""
    return all(a <= b + 1e-12 and b <= c + 1e-12 for a, b, c in zip(lo, mid, hi, strict=True))


def _hours(v: float) -> str:
    return f"{v:.1f} h"


def event_charts(baked: Mapping[str, Any], *, producer: Mapping[str, str]) -> list[dict[str, Any]]:
    """The inverse-velocity chart and the displacement chart of one baked event."""
    eid = slug(baked["event_id"])
    stratum = baked["stratum"]
    sname = STRATUM_NAMES.get(stratum, (stratum, stratum))
    t_f = float(baked["t_f_h"])
    notes: list[str] = []
    series: list[dict[str, Any]] = [
        {
            "id": "truth",
            "label": _t("Noise-free inverse velocity (truth)", "Velocidad inversa sin ruido (verdad)"),
            "x": [float(v) for v in baked["truth_t_h"]],
            "y": _nums(baked["truth_y"]),
        }
    ]
    last = baked["cutoffs"][-1]
    series.append(
        {
            "id": "observed",
            "label": _t(
                "Observed inverse velocity (window to the last cut-off)",
                "Velocidad inversa observada (ventana hasta el último corte)",
            ),
            "draw": "points",
            "x": [float(v) for v in last["observed_t_h"]],
            "y": _nums(last["observed_y"]),
        }
    )
    markers: list[dict[str, Any]] = [
        {
            "id": "true-failure",
            "label": _t("True failure time", "Tiempo de falla verdadero"),
            "value_text": _hours(t_f),
            "orientation": "vertical",
            "x": t_f,
        }
    ]
    for c in baked["cutoffs"]:
        tag = _cut(c["cutoff"])
        markers.append(
            {
                "id": f"cutoff-{tag}",
                "label": _t(f"Cut-off {c['cutoff']}", f"Corte {c['cutoff']}"),
                "value_text": _hours(c["t_c_h"]),
                "orientation": "vertical",
                "x": float(c["t_c_h"]),
            }
        )
    for c in baked["cutoffs"]:
        tag = _cut(c["cutoff"])
        m = c["methods"]
        iv = m["inverse_velocity"]
        fit_t, fit_y = list(iv["fit_t_h"]), list(iv["fit_y"])
        if iv["outcome"] == "predicted":
            fit_t, fit_y = [fit_t[0], float(iv["t_hat_f_h"])], [fit_y[0], 0.0]
        series.append(
            {
                "id": f"iv-fit-{tag}",
                "label": _t(
                    f"Inverse-velocity fit, cut-off {c['cutoff']}", f"Ajuste de velocidad inversa, corte {c['cutoff']}"
                ),
                "x": fit_t,
                "y": _nums(fit_y),
            }
        )
        b = m["bayesian_ttf"]
        if b["t_h"]:
            series.append(
                {
                    "id": f"bayes-{tag}",
                    "label": _t(f"Bayesian line, cut-off {c['cutoff']}", f"Recta bayesiana, corte {c['cutoff']}"),
                    "x": [float(v) for v in b["t_h"]],
                    "y": _nums(b["y_median"]),
                    "lo": _nums(b["y_lo"]),
                    "hi": _nums(b["y_hi"]),
                    "band_label": _t("10 % to 90 % of the posterior lines", "10 % a 90 % de las rectas posteriores"),
                }
            )
        for arm in ("tcn", "patchtst", "chronos_bolt_fine_tuned"):
            a = m.get(arm)
            if a is None:
                continue
            if a["status"] != "ok":
                notes.append(f"{NAMES[arm][0]} at {c['cutoff']}: no forecast ({a['reason']})")
                continue
            entry: dict[str, Any] = {
                "id": f"{slug(arm)}-{tag}",
                "label": _t(f"{NAMES[arm][0]}, cut-off {c['cutoff']}", f"{NAMES[arm][1]}, corte {c['cutoff']}"),
                "x": [float(v) for v in a["t_h"]],
                "y": _nums(a["y_median"]),
            }
            if _ordered(a["y_lo"], a["y_median"], a["y_hi"]):
                entry["lo"] = _nums(a["y_lo"])
                entry["hi"] = _nums(a["y_hi"])
                entry["band_label"] = _t("0.1 to 0.9 quantile path", "Trayectoria de cuantiles 0.1 a 0.9")
            else:
                notes.append(f"{NAMES[arm][0]} at {c['cutoff']}: band omitted, its quantile paths cross")
            series.append(entry)
        for method in _ARM_ORDER:
            a = m.get(method)
            if a is None or a["status"] != "ok":
                continue
            capped = bool(a.get("scored_at_cap"))
            markers.append(
                {
                    "id": f"pred-{slug(method)}-{tag}",
                    "label": _t(
                        f"{NAMES[method][0]}, predicted failure, cut-off {c['cutoff']}",
                        f"{NAMES[method][1]}, falla pronosticada, corte {c['cutoff']}",
                    ),
                    "value_text": (f"cap {a['t_hat_f_h']:.0f} h, none predicted" if capped else _hours(a["t_hat_f_h"])),
                    "orientation": "vertical",
                    "x": float(a["t_hat_f_h"]),
                }
            )
    caption_en = f"Synthetic Voight event {baked['event_id'][-6:]} ({sname[0]}): forecasts at the cut-offs 0.5 and 0.8."
    caption_es = (
        f"Evento de Voight sintético {baked['event_id'][-6:]} ({sname[1]}): pronósticos en los cortes 0.5 y 0.8."
    )
    if notes:
        extra = "; ".join(notes)
        caption_en = f"{caption_en} {extra}"[:200]
        caption_es = f"{caption_es} {extra}"[:200]
    iv_chart = _base(
        f"c1-iv-{eid}",
        "line",
        _t(
            f"Inverse velocity and forecasts, event {baked['event_id'][-6:]}",
            f"Velocidad inversa y pronósticos, evento {baked['event_id'][-6:]}",
        ),
        producer,
        ["FR-010-18", "FR-010-19", "FR-010-20", "FR-010-21", "FR-010-22"],
    )
    iv_chart["caption"] = _t(caption_en, caption_es)
    iv_chart["x_axis"] = {"label": _t("Time", "Tiempo"), "unit": "h"}
    iv_chart["y_axis"] = {"label": _t("Inverse velocity", "Velocidad inversa"), "unit": "h/mm"}
    iv_chart["series"] = series[:12]
    iv_chart["markers"] = markers[:24]
    disp = _base(
        f"c1-disp-{eid}",
        "line",
        _t(
            f"Line-of-sight displacement, event {baked['event_id'][-6:]}",
            f"Desplazamiento en línea de vista, evento {baked['event_id'][-6:]}",
        ),
        producer,
        ["FR-010-11", "FR-010-18"],
    )
    disp["caption"] = _t(
        f"Observed synthetic displacement ({sname[0]}) with the two cut-offs and the true failure time.",
        f"Desplazamiento sintético observado ({sname[1]}) con los dos cortes y el tiempo de falla verdadero.",
    )
    disp["x_axis"] = {"label": _t("Time", "Tiempo"), "unit": "h"}
    disp["y_axis"] = {"label": _t("Line-of-sight displacement", "Desplazamiento en línea de vista"), "unit": "mm"}
    disp["series"] = [
        {
            "id": "displacement",
            "label": _t("Observed displacement", "Desplazamiento observado"),
            "draw": "points",
            "x": [float(v) for v in baked["displacement_t_h"]],
            "y": _nums(baked["displacement_mm"]),
        }
    ]
    disp["markers"] = markers[:3]
    return [iv_chart, disp]


# ---------------------------------------------------------------------------------------------------------- U4


def _k(section_id: str) -> int:
    m = re.search(r"-s(\d+)$", section_id)
    if not m:
        raise ValueError(f"section id without a number: {section_id!r}")
    return int(m.group(1))


def _row(fos: Sequence[Mapping[str, Any]], method: str) -> Mapping[str, Any] | None:
    return next((r for r in fos if r["method"] == method and r.get("status") == "ok"), None)


def wall_charts(
    walls: Sequence[Mapping[str, Any]], oracles: Sequence[Mapping[str, Any]], *, producer: Mapping[str, str]
) -> list[dict[str, Any]]:
    """Per section the section chart and the PoF chart, then one table of the three sections."""
    prod = {**producer, "method": WALL_METHOD[:160], "label": WALL_LABEL}
    out: list[dict[str, Any]] = []
    oracle_by = {o["section_id"]: o for o in oracles}
    rows = []
    for w in walls:
        sec = w["section"]
        k = _k(sec["section_id"])
        bishop, spencer = _row(w["fos"], "bishop"), _row(w["fos"], "spencer")
        zc = float(np.interp(sec["crest_x_m"], [p[0] for p in sec["ground"]], [p[1] for p in sec["ground"]]))
        zt = float(np.interp(sec["toe_x_m"], [p[0] for p in sec["ground"]], [p[1] for p in sec["ground"]]))
        height = zc - zt
        angle = math.degrees(math.atan2(height, sec["toe_x_m"] - sec["crest_x_m"]))
        chart = _base(
            f"c1-wall-s{k}-section",
            "section",
            _t(
                f"Wall section {k} with the critical slip circle",
                f"Sección de talud {k} con el círculo de falla crítico",
            ),
            prod,
            ["FR-010-01", "FR-010-02", "FR-010-06"],
        )
        fos_text = f"Bishop {bishop['fos']:.2f}" if bishop else "no valid surface"
        if spencer:
            fos_text += f", Spencer {spencer['fos']:.2f}"
        chart["caption"] = _t(
            f"Ground profile from the 1 m DEM, analysed face {height:.0f} m high at {angle:.0f} degrees; minimum "
            f"FoS {fos_text}. "
            "Illustrative rock-mass inputs, UNVERIFIED.",
            f"Perfil del terreno del DEM de 1 m, cara analizada de {height:.0f} m a {angle:.0f} grados; FS mínimo "
            f"{fos_text}. "
            "Insumos de macizo ilustrativos, SIN VERIFICAR.",
        )
        chart["x_axis"] = {"label": _t("Distance along the section", "Distancia a lo largo de la sección"), "unit": "m"}
        chart["y_axis"] = {"label": _t("Elevation (NAVD88)", "Elevación (NAVD88)"), "unit": "m"}
        circles = []
        if bishop:
            cc = bishop["critical_circle"]
            circles.append(
                {
                    "id": "bishop-critical",
                    "label": _t(
                        f"Critical circle, Bishop FoS {bishop['fos']:.2f}",
                        f"Círculo crítico, Bishop FS {bishop['fos']:.2f}",
                    ),
                    "role": "critical",
                    "cx": float(cc["centre_x_m"]),
                    "cy": float(cc["centre_z_m"]),
                    "r": float(cc["radius_m"]),
                }
            )
        if spencer and bishop and spencer["critical_circle"] != bishop["critical_circle"]:
            sc = spencer["critical_circle"]
            circles.append(
                {
                    "id": "spencer-critical",
                    "label": _t(
                        f"Critical circle, Spencer FoS {spencer['fos']:.2f}",
                        f"Círculo crítico, Spencer FS {spencer['fos']:.2f}",
                    ),
                    "role": "other",
                    "cx": float(sc["centre_x_m"]),
                    "cy": float(sc["centre_z_m"]),
                    "r": float(sc["radius_m"]),
                }
            )
        chart["section"] = {
            "polylines": [
                {
                    "id": "ground",
                    "label": _t("Ground (3DEP 2018, 1 m)", "Terreno (3DEP 2018, 1 m)"),
                    "role": "ground",
                    "points": [[float(x), float(zz)] for x, zz in sec["ground"]],
                },
                {
                    "id": "face",
                    "label": _t("Analysed face, crest to toe", "Cara analizada, cresta a pie"),
                    "role": "other",
                    "points": [[float(sec["crest_x_m"]), zc], [float(sec["toe_x_m"]), zt]],
                },
            ],
            "circles": circles,
        }
        out.append(chart)
        pofd = w["pof"]
        hist = w["pof_min_factor_histogram"]
        pc = _base(
            f"c1-wall-s{k}-pof",
            "line",
            _t(f"Probability of failure, section {k}", f"Probabilidad de falla, sección {k}"),
            prod,
            ["FR-010-03", "FR-010-04"],
        )
        n, kk = int(pofd["samples"]), int(pofd["candidates"])
        pc["caption"] = _t(
            f"PoF {pofd['pof']:.4g}: {pofd['failures']} of {n:,} samples below FoS 1 (Wilson 95 %: "
            f"{pofd['wilson_95']['lower']:.4g} "
            f"to {pofd['wilson_95']['upper']:.4g}), over the {kk} most critical surfaces of the mean case.",
            f"PoF {pofd['pof']:.4g}: {pofd['failures']} de {n:,} muestras bajo FS 1 (Wilson 95 %: "
            f"{pofd['wilson_95']['lower']:.4g} "
            f"a {pofd['wilson_95']['upper']:.4g}), sobre las {kk} superficies más críticas del caso medio.",
        )
        pc["x_axis"] = {
            "label": _t("Minimum factor of safety of a sample", "Factor de seguridad mínimo de una muestra"),
            "unit": "1",
        }
        pc["y_axis"] = {"label": _t("Samples", "Muestras"), "unit": "1"}
        pc["series"] = [
            {
                "id": "min-factor-histogram",
                "label": _t("Samples by minimum factor of safety", "Muestras por factor de seguridad mínimo"),
                "draw": "step",
                "n": n,
                "x": [float(v) for v in hist["centres"]],
                "y": [float(v) for v in hist["counts"]],
            }
        ]
        pc["markers"] = [
            {
                "id": "fos-one",
                "label": _t("Factor of safety 1", "Factor de seguridad 1"),
                "value_text": "FoS 1",
                "orientation": "vertical",
                "x": 1.0,
            }
        ]
        if bishop:
            pc["markers"].append(
                {
                    "id": "mean-case-fos",
                    "label": _t("Mean-case minimum FoS (Bishop)", "FS mínimo del caso medio (Bishop)"),
                    "value_text": f"{bishop['fos']:.2f}",
                    "orientation": "vertical",
                    "x": float(bishop["fos"]),
                }
            )
        out.append(pc)
        o = oracle_by.get(sec["section_id"])
        rows.append(
            [
                sec["section_id"],
                round(height, 1),
                round(angle, 1),
                round(bishop["fos"], 3) if bishop else None,
                round(spencer["fos"], 3) if spencer else None,
                round(spencer["theta_deg"], 2) if spencer and "theta_deg" in spencer else None,
                round(pofd["pof"], 5),
                round(pofd["wilson_95"]["lower"], 5),
                round(pofd["wilson_95"]["upper"], 5),
                n,
                kk,
                "pass" if o and o["fixed_pass"] else ("fail" if o else "not run"),
                "pass" if o and o["search_pass"] else ("fail" if o else "not run"),
            ]
        )
    table = _base(
        "c1-wall-table",
        "table",
        _t(
            "Wall sections: FoS, PoF and the pySlope check", "Secciones de talud: FS, PoF y la verificación con pySlope"
        ),
        prod,
        ["FR-010-01", "FR-010-03", "SC-010-05"],
    )
    table["caption"] = _t(
        "Minimum FoS over a circle grid and PoF over the 64 most critical surfaces. Illustrative inputs, UNVERIFIED. "
        "Educational, not design software.",
        "FS mínimo sobre una grilla de círculos y PoF sobre las 64 superficies más críticas. Insumos "
        "ilustrativos, SIN VERIFICAR. "
        "Educativo, no software de diseño.",
    )
    table["table"] = {
        "columns": [
            {"id": "section", "label": _t("Section", "Sección"), "type": "text"},
            {"id": "face-height", "label": _t("Face height", "Altura de la cara"), "type": "number", "unit": "m"},
            {"id": "face-angle", "label": _t("Face angle", "Ángulo de la cara"), "type": "number", "unit": "deg"},
            {"id": "fos-bishop", "label": _t("FoS Bishop", "FS Bishop"), "type": "number", "unit": "1"},
            {"id": "fos-spencer", "label": _t("FoS Spencer", "FS Spencer"), "type": "number", "unit": "1"},
            {
                "id": "theta",
                "label": _t("Spencer interslice angle", "Ángulo entre dovelas de Spencer"),
                "type": "number",
                "unit": "deg",
            },
            {"id": "pof", "label": _t("PoF", "PoF"), "type": "number", "unit": "1"},
            {"id": "pof-lower", "label": _t("PoF Wilson lower", "PoF Wilson inferior"), "type": "number", "unit": "1"},
            {"id": "pof-upper", "label": _t("PoF Wilson upper", "PoF Wilson superior"), "type": "number", "unit": "1"},
            {"id": "samples", "label": _t("Samples N", "Muestras N"), "type": "number", "unit": "1"},
            {
                "id": "candidates",
                "label": _t("Candidate surfaces K", "Superficies candidatas K"),
                "type": "number",
                "unit": "1",
            },
            {"id": "oracle-fixed-pass", "label": _t("pySlope fixed circles", "pySlope círculos fijos"), "type": "text"},
            {
                "id": "oracle-search-pass",
                "label": _t("pySlope searched minimum", "pySlope mínimo buscado"),
                "type": "text",
            },
        ],
        "rows": rows,
    }
    out.append(table)
    return out


# ---------------------------------------------------------------------------------------------------------- U3


def real_charts(real: Mapping[str, Any], *, producer: Mapping[str, str]) -> list[dict[str, Any]]:
    """The real-event chart in the state not-run, with the label, and the table of the archive members."""
    ev = real["evidence"]
    state = real["state"]
    chart = _not_run(
        "c1-real-event",
        _t("Real event (de Wit): time-to-failure forecasts", "Evento real (de Wit): pronósticos de tiempo a la falla"),
        producer,
        ["FR-010-26", "FR-010-27", "SC-010-03"],
        _t(
            "No failure time is stated in the archive or on its record page, and its prism-survey layout is not "
            "one the "
            "ingestion accepts: no t_f, no SNR_obs, no forecast.",
            "El archivo y la página del registro no indican un tiempo de falla, y su formato de levantamiento de "
            "prismas no lo "
            "acepta la ingestión: sin t_f, sin SNR_obs, sin pronóstico.",
        ),
    )
    chart["caption"] = _t(state.get("label", REAL_LABEL), state.get("label_es", REAL_LABEL_ES))
    table = _base(
        "c1-real-event-archive",
        "table",
        _t("de Wit archive: what it holds", "Archivo de Wit: qué contiene"),
        producer,
        ["FR-010-13", "FR-010-14"],
    )
    px = ev.get("prism_export")
    extra_en = extra_es = ""
    if px:
        extra_en = f" Prism export: {px['prisms']} prisms, {px['rows']:,} rows, {px['first']} to {px['last']}."
        extra_es = (
            f" Exportación de prismas: {px['prisms']} prismas, {px['rows']:,} filas, {px['first']} a {px['last']}."
        )
    table["caption"] = _t(
        (
            "Members of Data.zip (checksum matches the Zenodo record)."
            if ev["checksum_ok"]
            else "Checksum does not match."
        )
        + extra_en,
        (
            "Contenido de Data.zip (la suma de verificación coincide con el registro de Zenodo)."
            if ev["checksum_ok"]
            else "La suma de verificación no coincide."
        )
        + extra_es,
    )
    table["table"] = {
        "columns": [
            {"id": "member", "label": _t("Member", "Elemento"), "type": "text"},
            {"id": "bytes", "label": _t("Size", "Tamaño"), "type": "number", "unit": "B"},
            {"id": "first-line", "label": _t("First data line", "Primera línea de datos"), "type": "text"},
        ],
        "rows": [[m["name"][:200], m["bytes"], m.get("header", "")[:200]] for m in ev["members"]][:200],
    }
    return [chart, table]

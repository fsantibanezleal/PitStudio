"""The chart series of the real event of case C1: the FR-010-26 table, its sensitivity row, the failure time, curves.

Every builder only shapes what ``c1_real_eval`` computed (DC-020-05, ``specs/020-web-knowledge/contracts/
chart-series.schema.json``). The table carries the 12 rows in the fixed order with no highlight under the label of
FR-010-27; the sensitivity failure time is a table of its own, never ranked against the primary one; the failure time
chart table carries the instant, its day uncertainty, the clock zone and both documentary sources.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from pitstudio_pipeline.slope import c1_charts
from pitstudio_pipeline.slope.c1_charts import NAMES, _base, _nums, _ordered, _t, slug

LABEL = c1_charts.REAL_LABEL
LABEL_ES = c1_charts.REAL_LABEL_ES
SERVES_TABLE = ["FR-010-26", "FR-010-27", "SC-010-03"]
LEARNED_ARMS = ("tcn", "patchtst", "chronos_bolt_fine_tuned")
ARM_ORDER = ("inverse_velocity", "bayesian_ttf", *LEARNED_ARMS)


def _cut(c: float) -> str:
    return f"{round(c * 10):02d}"


def _stamp(instant: str, hours: float = 0.0) -> str:
    return (datetime.fromisoformat(instant) + timedelta(hours=hours)).replace(microsecond=0).isoformat()


def _date(instant: str) -> str:
    return f"{datetime.fromisoformat(instant):%d %b %Y %H:%M}"


def _cell(v: Any) -> Any:
    return v[:200] if isinstance(v, str) else v


def _result_table(block: Mapping[str, Any], *, chart_id: str, title: dict[str, str], caption: dict[str, str], prod):
    t_0 = block["t_0_instant"]
    chart = _base(chart_id, "table", title, prod, SERVES_TABLE)
    chart["caption"] = caption
    cols = [
        ("cutoff", "Cut-off", "Corte", "number", "1"),
        ("method", "Method", "Método", "text", None),
        ("outcome", "Outcome", "Resultado", "text", None),
        ("t-hat", "Predicted failure time", "Tiempo de falla pronosticado", "number", "h"),
        ("t-hat-instant", "Predicted failure instant", "Instante de falla pronosticado", "text", None),
        ("signed-error", "Signed error", "Error con signo", "number", "h"),
        (
            "error-lower",
            "Error, t_f later by the uncertainty",
            "Error, t_f más tarde por la incertidumbre",
            "number",
            "h",
        ),
        (
            "error-upper",
            "Error, t_f earlier by the uncertainty",
            "Error, t_f antes por la incertidumbre",
            "number",
            "h",
        ),
        ("ratio", "Error over t_f - t_c", "Error sobre t_f - t_c", "number", "1"),
        ("ratio-lower", "Ratio, lower end", "Razón, extremo inferior", "number", "1"),
        ("ratio-upper", "Ratio, upper end", "Razón, extremo superior", "number", "1"),
        ("reason", "Reason", "Motivo", "text", None),
    ]
    chart["table"] = {
        "columns": [
            {"id": i, "label": _t(en, es), "type": ty, **({"unit": u} if u else {})} for i, en, es, ty, u in cols
        ],
        "rows": [],
    }
    for r in block["rows"]:
        has = "t_hat_f_h" in r
        ei, ri = r.get("signed_error_interval_h"), r.get("error_ratio_interval")
        chart["table"]["rows"].append(
            [
                _cell(v)
                for v in (
                    r["cutoff"],
                    NAMES[r["method"]][0],
                    r["outcome"],
                    r["t_hat_f_h"] if has else None,
                    _stamp(t_0, r["t_hat_f_h"]) if has else None,
                    r["signed_error_h"] if has else None,
                    ei["lower"] if ei else None,
                    ei["upper"] if ei else None,
                    r["error_ratio"] if has else None,
                    ri["lower"] if ri else None,
                    ri["upper"] if ri else None,
                    r.get("reason"),
                )
            ]
        )
    return chart


def _failure_table(pair: Mapping[str, Any], failure_time: Mapping[str, Any], blast: Mapping[str, Any] | None, prod):
    p, s = pair["primary"], pair["sensitivity"]
    chart = _base(
        "c1-real-event-failure-time",
        "table",
        _t(
            "de Wit failure time, its uncertainty and its sources",
            "Tiempo de falla de Wit, su incertidumbre y sus fuentes",
        ),
        prod,
        ["FR-010-13", "FR-010-14", "FR-010-26"],
    )
    chart["caption"] = _t(
        "The failure time is stated by the two sources below to the day; the archive itself states none.",
        "Las dos fuentes de abajo dan el tiempo de falla al día; el archivo mismo no indica ninguno.",
    )
    u = p["t_f_uncertainty_h"]
    rows: list[list[Any]] = [
        [
            "Failure time t_f (primary)",
            f"{p['t_f_instant']}, uncertainty +/- {u:g} h",
            failure_time["sources"][0]["citation"],
        ],
        ["Clock zone", failure_time["zone"], "the archive states none"],
        ["Start of the series t_0", p["t_0_instant"], "first epoch with enough prisms"],
        ["Record length t_f - t_0", f"{p['t_f_h']:.1f} h", "computed"],
        ["SNR_obs (FR-010-12)", f"{p['snr_obs']:.2f}", "computed on the series between t_0 and t_f"],
        [
            "Sensitivity failure time (not ranked)",
            f"{s['t_f_instant']}, uncertainty +/- {s['t_f_uncertainty_h']:g} h",
            failure_time["sources"][1]["citation"],
        ],
    ]
    for i, src in enumerate(failure_time["sources"], 1):
        rows.append([f"Source {i}", src["citation"], src["locator"]])
    if blast:
        rows.append(["Blast marked on the curves", blast["instant"], blast["basis"]])
    chart["table"] = {
        "columns": [
            {"id": "item", "label": _t("Item", "Elemento"), "type": "text"},
            {"id": "value", "label": _t("Value", "Valor"), "type": "text"},
            {"id": "source", "label": _t("Source or basis", "Fuente o base"), "type": "text"},
        ],
        "rows": [[_cell(c) for c in r] for r in rows],
    }
    return chart


def _markers(detail: Mapping[str, Any], pair: Mapping[str, Any], blast: Mapping[str, Any] | None, *, with_predictions):
    p = pair["primary"]
    t_0, t_f = p["t_0_instant"], float(detail["t_f_h"])
    u = p["t_f_uncertainty_h"]
    markers: list[dict[str, Any]] = [
        {
            "id": "failure-time",
            "label": _t("Failure time t_f (day resolution)", "Tiempo de falla t_f (resolución de un día)"),
            "value_text": f"{_date(p['t_f_instant'])} +/- {u:g} h"[:60],
            "orientation": "vertical",
            "x": t_f,
        }
    ]
    if blast:
        hours = (datetime.fromisoformat(blast["instant"]) - datetime.fromisoformat(t_0)).total_seconds() / 3600.0
        markers.append(
            {
                "id": f"blast-{blast['instant'][:10]}",
                "label": _t("Blast at the foot of the wall (not t_f)", "Tronadura al pie del muro (no es t_f)"),
                "value_text": f"{_date(blast['instant'])} (archive event)"[:60],
                "orientation": "vertical",
                "x": hours,
            }
        )
    markers.extend(
        {
            "id": f"cutoff-{_cut(c['cutoff'])}",
            "label": _t(f"Cut-off {c['cutoff']}", f"Corte {c['cutoff']}"),
            "value_text": f"{c['t_c_h']:.1f} h",
            "orientation": "vertical",
            "x": float(c["t_c_h"]),
        }
        for c in detail["cutoffs"]
    )
    if with_predictions:
        for c in detail["cutoffs"]:
            for method in ARM_ORDER:
                a = c["methods"].get(method)
                if a is None or a["status"] != "ok":
                    continue
                capped = bool(a.get("scored_at_cap"))
                markers.append(
                    {
                        "id": f"pred-{slug(method)}-{_cut(c['cutoff'])}",
                        "label": _t(
                            f"{NAMES[method][0]}, predicted failure, cut-off {c['cutoff']}",
                            f"{NAMES[method][1]}, falla pronosticada, corte {c['cutoff']}",
                        ),
                        "value_text": (
                            f"cap {a['t_hat_f_h']:.0f} h, none predicted" if capped else f"{a['t_hat_f_h']:.1f} h"
                        ),
                        "orientation": "vertical",
                        "x": float(a["t_hat_f_h"]),
                    }
                )
    return markers


def _curve_chart(detail: Mapping[str, Any], markers: list[dict[str, Any]], prod) -> dict[str, Any]:
    notes: list[str] = []
    last = detail["cutoffs"][-1]
    half = 0.5 * float(last["t_c_h"])
    shown = [(t, y) for t, y in zip(last["observed_t_h"], last["observed_y"], strict=True) if t >= half]
    series: list[dict[str, Any]] = [
        {
            "id": "observed",
            "label": _t(
                "Observed inverse velocity (second half of the window to the last cut-off)",
                "Velocidad inversa observada (segunda mitad de la ventana hasta el último corte)",
            ),
            "draw": "points",
            "x": [float(t) for t, _ in shown],
            "y": _nums([y for _, y in shown]),
        }
    ]
    for c in detail["cutoffs"]:
        tag, m = _cut(c["cutoff"]), c["methods"]
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
        for arm in LEARNED_ARMS:
            a = m.get(arm)
            if a is None:
                continue
            if a["status"] != "ok":
                notes.append(f"{NAMES[arm][0]} at {c['cutoff']}: no forecast")
                continue
            entry: dict[str, Any] = {
                "id": f"{slug(arm)}-{tag}",
                "label": _t(f"{NAMES[arm][0]}, cut-off {c['cutoff']}", f"{NAMES[arm][1]}, corte {c['cutoff']}"),
                "x": [float(v) for v in a["t_h"]],
                "y": _nums(a["y_median"]),
            }
            if _ordered(a["y_lo"], a["y_median"], a["y_hi"]):
                entry["lo"], entry["hi"] = _nums(a["y_lo"]), _nums(a["y_hi"])
                entry["band_label"] = _t("0.1 to 0.9 quantile path", "Trayectoria de cuantiles 0.1 a 0.9")
            else:
                notes.append(f"{NAMES[arm][0]} at {c['cutoff']}: band omitted, quantile paths cross")
            series.append(entry)
    chart = _base(
        "c1-real-event-iv",
        "line",
        _t("Real event: inverse velocity and forecasts", "Evento real: velocidad inversa y pronósticos"),
        prod,
        ["FR-010-18", "FR-010-19", "FR-010-26", "FR-010-27"],
    )
    en = f"de Wit prism series (median of the top 5 % prisms), forecasts at 0.5 and 0.8. {LABEL}."
    es = f"Serie de prismas de Wit (mediana del 5 % superior), pronósticos en 0.5 y 0.8. {LABEL_ES}."
    if notes:
        en, es = f"{en} {'; '.join(notes)}"[:200], f"{es} {'; '.join(notes)}"[:200]
    chart["caption"] = _t(en, es)
    chart["x_axis"] = {"label": _t("Time since t_0", "Tiempo desde t_0"), "unit": "h"}
    chart["y_axis"] = {"label": _t("Inverse velocity", "Velocidad inversa"), "unit": "h/mm"}
    chart["series"] = series[:12]
    chart["markers"] = markers[:24]
    return chart


def real_event_charts(
    pair: Mapping[str, Any],
    detail: Mapping[str, Any],
    *,
    producer: Mapping[str, str],
    failure_time: Mapping[str, Any],
    blast: Mapping[str, Any] | None,
    archive_table: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """The six charts of the real event (see the module docstring), in a fixed order."""
    p, s = pair["primary"], pair["sensitivity"]
    u = p["t_f_uncertainty_h"]
    main = _result_table(
        p,
        chart_id="c1-real-event",
        title=_t(
            "Real event (de Wit): time-to-failure forecasts", "Evento real (de Wit): pronósticos de tiempo a la falla"
        ),
        caption=_t(
            f"{LABEL}. t_f {_date(p['t_f_instant'])} +/- {u:g} h; SNR_obs {p['snr_obs']:.1f}; error = t_hat - t_f.",
            f"{LABEL_ES}. t_f {_date(p['t_f_instant'])} +/- {u:g} h; SNR_obs {p['snr_obs']:.1f}; error = t_hat - t_f.",
        ),
        prod=producer,
    )
    sens = _result_table(
        s,
        chart_id="c1-real-event-sensitivity",
        title=_t(
            f"Real event, sensitivity: t_f {s['t_f_instant'][:10]} (radar reading)",
            f"Evento real, sensibilidad: t_f {s['t_f_instant'][:10]} (lectura de radar)",
        ),
        caption=_t(
            f"{LABEL}. Sensitivity failure time of SSIM 2023, not ranked against the primary one; own cut-offs.",
            f"{LABEL_ES}. Tiempo de falla de sensibilidad de SSIM 2023, sin ordenar frente al principal; cortes "
            "propios.",
        ),
        prod=producer,
    )
    markers = _markers(detail, pair, blast, with_predictions=True)
    iv = _curve_chart(detail, markers, producer)
    disp = _base(
        "c1-real-event-disp",
        "line",
        _t("Real event: displacement of the prism series", "Evento real: desplazamiento de la serie de prismas"),
        producer,
        ["FR-010-11", "FR-010-13", "FR-010-27"],
    )
    disp["caption"] = _t(
        f"Median along-motion displacement of the top 5 % prisms with t_f, the blast and the cut-offs. {LABEL}.",
        f"Desplazamiento mediano a lo largo del movimiento del 5 % superior de prismas, con t_f, la tronadura "
        f"y los cortes. {LABEL_ES}.",
    )
    disp["x_axis"] = {"label": _t("Time since t_0", "Tiempo desde t_0"), "unit": "h"}
    disp["y_axis"] = {"label": _t("Displacement", "Desplazamiento"), "unit": "mm"}
    disp["series"] = [
        {
            "id": "displacement",
            "label": _t("Median displacement of the selected prisms", "Desplazamiento mediano de los prismas elegidos"),
            "draw": "points",
            "x": [float(v) for v in detail["displacement_t_h"]],
            "y": _nums(detail["displacement_mm"]),
        }
    ]
    disp["markers"] = _markers(detail, pair, blast, with_predictions=False)
    archive = dict(archive_table)
    archive["producer"] = dict(producer)
    return [main, sens, _failure_table(pair, failure_time, blast, producer), iv, disp, archive]

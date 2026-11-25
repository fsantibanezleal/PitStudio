"""The real-event evaluation of case C1: every method at the cut-offs 0.5 and 0.8 on the de Wit series (FR-010-26).

The series comes from ``dewit_prisms.ingest_prisms``; the methods are the ones of the synthetic evaluation, on the same
windows (``data.predict_events``): inverse velocity, Bayesian time to failure and the learned arms through the callables
given (the on-disk ONNX files on ONNX Runtime CPU). ``ev.real_event_report`` builds the 12 rows in the fixed order
with the signed error ``t_hat - t_f`` and its ratio to ``t_f - t_c``.

The failure time is known to the day only, so every row also carries the error for ``t_f`` anywhere in ``t_f +- u``
(``u`` = ``t_f_uncertainty_h``) with the forecast fixed: the windows are not re-run for another ``t_f``. A second
failure time (the sensitivity row) is evaluated by ``evaluate_pair`` as a whole separate run, with its own cut-offs,
and is never ranked against the first. There is no rank, verdict or significance test: it is one event (n = 1).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from pitstudio.slope import evaluate as ev
from pitstudio_pipeline.slope import c1_curves, data

LABEL = ev.SINGLE_EVENT_LABEL
ZERO_SHOT_REASON = (
    "not run: the zero-shot Chronos-Bolt arm has no exported ONNX file, so no baked forecast exists for it (FR-010-30)"
)
ZONE = "local clock of the archive (AEST, UTC+10, assumed: the archive states no zone, UNVERIFIED)"
ATTRIBUTION = (
    "de Wit (2025). Data used for the study of time-lapse velocity variations during an open-pit mine slope "
    "failure using seismic noise interferometry. Zenodo. https://doi.org/10.5281/zenodo.15003054. "
    "Licensed under CC BY 4.0."
)
SOURCE_SEISMICA = {
    "citation": "de Wit and Snieder, Seismica 5(1), doi 10.26443/seismica.v5i1.1902 "
    "(the article of Zenodo record 15003054)",
    "locator": "'a slope failure that occurred on the 23rd February 2014'; Fig. 4: 'The initialisation of slope "
    "failure on "
    "the 23rd of February 2014 is indicated by the dashed black line'",
}
SOURCE_SSIM = {
    "citation": "Taylor and de Wit, SSIM 2023, Perth, doi 10.36487/ACG_repo/2335_50",
    "locator": "2 March 2014 is '10 days after the slope was interpreted as failing, based on ground radar "
    "measurements'",
}
# the main-session decisions of 2026-11-23 (brief c1-dewit-2026-11-23): t_f is the date of the dataset article at day
# resolution with an uncertainty of one day; the SSIM 2023 radar interpretation (about 20 February) is the
# sensitivity row
PRIMARY_FAILURE = {
    "instant": "2014-02-23T00:00:00",
    "uncertainty_h": 24.0,
    "zone": ZONE,
    "sources": [SOURCE_SEISMICA, SOURCE_SSIM],
    "attribution": ATTRIBUTION,
}
SENSITIVITY_FAILURE = {
    "instant": "2014-02-20T00:00:00",
    "uncertainty_h": 24.0,
    "zone": ZONE,
    "sources": [SOURCE_SSIM, SOURCE_SEISMICA],
    "attribution": ATTRIBUTION,
}
BLAST_DATE = "2014-02-11"
BLAST_BASIS = (
    "date: Taylor and de Wit 2023 (a blast at the foot of the pit wall on 11 February 2014); time: the largest "
    "event of "
    "the archive's seismic list that day, UNVERIFIED as the blast (the list does not label blasts)"
)


def _need(document: Mapping[str, Any]) -> tuple[float, str, str]:
    unc = document.get("t_f_uncertainty_h")
    if isinstance(unc, bool) or not isinstance(unc, int | float) or not np.isfinite(unc) or unc < 0:
        raise ValueError("the real-event document needs t_f_uncertainty_h (hours, zero or more)")
    for key in ("t_0_instant", "t_f_instant"):
        if not isinstance(document.get(key), str):
            raise ValueError(f"the real-event document needs {key}")
    return float(unc), str(document["t_f_instant"]), str(document.get("zone", ""))


def evaluate(
    document: Mapping[str, Any], forecasters: Mapping[str, Callable[[np.ndarray], Any]], *, seed: int
) -> dict[str, Any]:
    unc, t_f_instant, zone = _need(document)
    rows = data.predict_events([{**document, "stratum": "real"}], forecasters, cutoffs=ev.CUTOFFS, seed=seed)
    forecasts = {(r["method"], r["cutoff"]): r for r in rows}
    report = ev.real_event_report(
        event_id=document["event_id"],
        t_0_h=document["t_0_h"],
        t_f_h=document["t_f_h"],
        snr_obs=document["snr_obs"],
        forecasts=forecasts,
    )
    t_f = float(document["t_f_h"])
    for row in report["rows"]:
        if row["method"] == "chronos_bolt_zero_shot" and row["outcome"] == "not run":
            row["reason"] = ZERO_SHOT_REASON
        if "t_hat_f_h" not in row:
            continue
        t_hat, t_c = row["t_hat_f_h"], row["t_c_h"]
        row["signed_error_interval_h"] = {"lower": t_hat - (t_f + unc), "upper": t_hat - (t_f - unc)}
        ratios = [(t_hat - tf) / (tf - t_c) for tf in (t_f - unc, t_f + unc)]
        row["error_ratio_interval"] = {"lower": min(ratios), "upper": max(ratios)}
    report.update(
        t_0_instant=document["t_0_instant"],
        t_f_instant=t_f_instant,
        t_f_uncertainty_h=unc,
        zone=zone,
        interval_note=(
            "the interval is the error for t_f anywhere within the stated uncertainty, with the forecast fixed "
            "(the windows are not re-run)"
        ),
    )
    return report


def evaluate_pair(
    primary: Mapping[str, Any],
    sensitivity: Mapping[str, Any],
    forecasters: Mapping[str, Callable[[np.ndarray], Any]],
    *,
    seed: int,
) -> dict[str, Any]:
    """The primary run and the sensitivity run, each a whole evaluation of its own; they are not compared."""
    return {
        "label": LABEL,
        "primary": evaluate(primary, forecasters, seed=seed),
        "sensitivity": evaluate(sensitivity, forecasters, seed=seed),
        "note": "the sensitivity failure time is reported beside the primary one and is not ordered against it",
    }


def blast_marker(events_csv: str, local_date: str, *, utc_offset_h: float) -> dict[str, Any] | None:
    """The largest event of the archive's seismic list on ``local_date`` (clock = UTC epoch + ``utc_offset_h``)."""
    epoch = datetime(1970, 1, 1)
    best: tuple[float, datetime, list[str]] | None = None
    for row in csv.reader(io.StringIO(events_csv)):
        if not row or row[0].startswith("#"):
            continue
        try:
            when = epoch + timedelta(seconds=float(row[1]) + 3600.0 * utc_offset_h)
            mag = float(row[2])
        except ValueError, IndexError:
            continue
        if when.date().isoformat() != local_date:
            continue
        if best is None or mag > best[0]:
            best = (mag, when, row)
    if best is None:
        return None
    mag, when, row = best
    return {
        "instant": when.replace(microsecond=0).isoformat(),
        "magnitude": mag,
        "easting_m": float(row[4]),
        "northing_m": float(row[5]),
        "basis": BLAST_BASIS,
    }


def bake(
    document: Mapping[str, Any],
    forecasters: Mapping[str, Callable[[np.ndarray], Any]],
    *,
    seed: int,
    cutoffs: tuple[float, ...] = ev.CUTOFFS,
) -> dict[str, Any]:
    """The observed window and every method's forecast at each cut-off, for the curve chart (as ``bake_event``)."""
    out_cutoffs = []
    for c in cutoffs:
        window, t_c = data.window_at(document, float(c))
        methods: dict[str, Any] = {}
        iv = c1_curves.iv_fit(window)
        methods["inverse_velocity"] = {
            "status": "ok",
            "outcome": iv["outcome"],
            "t_hat_f_h": iv["t_hat_f_h"],
            "scored_at_cap": iv["outcome"] != "predicted",
            "fit_t_h": iv["fit_t_h"],
            "fit_y": iv["fit_y"],
        }
        band = c1_curves.bayes_band(window, seed=seed)
        methods["bayesian_ttf"] = {
            "status": "ok",
            "outcome": band["outcome"],
            "t_hat_f_h": band["t_hat_f_h"],
            "scored_at_cap": band["outcome"] != "predicted",
            "t_h": band["t_h"],
            "y_median": band["y_median"],
            "y_lo": band["y_lo"],
            "y_hi": band["y_hi"],
        }
        for arm, model in forecasters.items():
            methods[arm] = c1_curves._learned(model, window)
        ok = np.isfinite(window.y)
        ot, oy = c1_curves.decimate(window.t[ok], window.y[ok], c1_curves.MAX_POINTS)
        out_cutoffs.append(
            {"cutoff": float(c), "t_c_h": float(t_c), "observed_t_h": ot, "observed_y": oy, "methods": methods}
        )
    dt, do = c1_curves.decimate(document["t_h"], document["los_displacement_mm"], c1_curves.MAX_POINTS)
    return {
        "event_id": document["event_id"],
        "t_0_h": float(document["t_0_h"]),
        "t_f_h": float(document["t_f_h"]),
        "displacement_t_h": dt,
        "displacement_mm": do,
        "cutoffs": out_cutoffs,
    }

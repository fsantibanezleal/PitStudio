"""Evaluation of the C1 forecasters (FR-010-23 to FR-010-28, FR-010-26), numpy only.

Relative error ``e = |t_hat - t_c_f| / (t_f - t_c)`` with ``t_c = t_0 + c (t_f - t_0)``; per (method, stratum, cut-off)
medians, means and 90th percentiles; the lead time at alarm over the cut-off grid 0.30 to 0.99; the SC-010-01 row per
learned
arm (median over the SNR_obs events with its percentile-bootstrap interval); the paired percentile bootstrap against
inverse
velocity (resampling the positions of the sorted event ids) with the verdict of the decision rule (better only when
the lower
bound is above zero); and the descriptive report of the one real event (no interval, no rank, no verdict).

Bootstrap resamples come from ``numpy.random.Generator(PCG64(SeedSequence(seed)))`` as ``integers(0, n, (B, n))``
unless the
caller injects an index matrix (the exact tests do).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

CUTOFFS = (0.5, 0.8)
METHODS = ("inverse_velocity", "bayesian_ttf", "tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned")
LEARNED = METHODS[2:]
ALARM_GRID = np.arange(30, 100) / 100.0
ALARM_TOLERANCE = 1e-9
RESAMPLES = 10_000
LEVEL = 0.95
THRESHOLD = 0.10
SINGLE_EVENT_LABEL = "single real event — no significance test"
SINGLE_PAIR_VERDICT = "single real event — no significance test"


class InsufficientPairsError(ValueError):
    """No paired unit: no interval, ranking or verdict can be formed (FR-010-28)."""


class UnpairedError(ValueError):
    """The two methods do not share the same event ids (FR-010-28)."""


# ----------------------------------------------------------------------------------------------------------------------
# errors


def cutoff_time(t_0: float, t_f: float, c: float) -> float:
    return t_0 + c * (t_f - t_0)


def relative_error(t_hat: float, t_f: float, t_c: float) -> float:
    """``|t_hat - t_f| / (t_f - t_c)``; the lead time must be positive."""
    lead = t_f - t_c
    if not lead > 0.0:
        raise ValueError(f"the lead time t_f - t_c = {lead!r} must be positive")
    return abs(t_hat - t_f) / lead


def score_events(predictions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Score each prediction (``event_result`` rows of the TTF schema); order and rows follow the input."""
    rows: list[dict[str, Any]] = []
    for p in predictions:
        t_c = cutoff_time(float(p["t_0_h"]), float(p["t_f_h"]), float(p["cutoff"]))
        row: dict[str, Any] = {
            "event_id": p["event_id"],
            "stratum": p["stratum"],
            "method": p["method"],
            "cutoff": p["cutoff"],
            "t_c_h": t_c,
            "t_f_h": float(p["t_f_h"]),
            "outcome": p["outcome"],
        }
        if p["outcome"] == "no forecast":
            row["reason"] = p["reason"]
        else:
            t_hat = float(p["t_hat_f_h"])
            row["t_hat_f_h"] = t_hat
            row["rel_error"] = relative_error(t_hat, float(p["t_f_h"]), t_c)
            row["error_h"] = t_hat - float(p["t_f_h"])
            row["scored_at_cap"] = p["outcome"] == "no failure predicted"
            if p.get("interval_80_h") is not None:
                row["interval_80_h"] = dict(p["interval_80_h"])
        rows.append(row)
    return rows


def summarise(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Median, mean and 90th percentile of the relative error per (method, stratum, cut-off) over the scored rows."""
    groups: dict[tuple[str, str, float], list[Mapping[str, Any]]] = {}
    for r in rows:
        if r["outcome"] == "no forecast":
            continue
        groups.setdefault((r["method"], r["stratum"], r["cutoff"]), []).append(r)
    out = []
    for (method, stratum, cutoff), group in groups.items():
        rel = np.array([g["rel_error"] for g in group], dtype=float)
        err = np.array([abs(g["error_h"]) for g in group], dtype=float)
        out.append(
            {
                "method": method,
                "stratum": stratum,
                "cutoff": cutoff,
                "n_events": len(group),
                "median_rel_error": float(np.median(rel)),
                "mean_rel_error": float(rel.mean()),
                "p90_rel_error": float(np.percentile(rel, 90.0)),
                "median_abs_error_h": float(np.median(err)),
            }
        )
    return out


# ----------------------------------------------------------------------------------------------------------------------
# lead time at alarm


def alarm(
    forecast_at: Callable[[float], float | None], t_0: float, t_f: float, *, t_alarm_h: float = 24.0
) -> dict[str, Any]:
    """First cut-off of the grid 0.30 to 0.99 whose forecast puts the failure within ``t_alarm_h`` of it."""
    limit = t_alarm_h + ALARM_TOLERANCE * max(1.0, abs(t_alarm_h))
    for c in ALARM_GRID:
        t_hat = forecast_at(float(c))
        if t_hat is None:
            continue
        t_c = cutoff_time(t_0, t_f, float(c))
        if t_hat - t_c <= limit:
            return {"alarmed": True, "alarm_cutoff": float(c), "lead_time_h": t_f - t_c}
    return {"alarmed": False}


def alarm_summary(alarm_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(alarm_rows)
    alarmed = [r["lead_time_h"] for r in alarm_rows if r["alarmed"]]
    out: dict[str, Any] = {"never_alarmed_fraction": (n - len(alarmed)) / n}
    if alarmed:
        out["median_lead_time_h"] = float(np.median(alarmed))
    return out


# ----------------------------------------------------------------------------------------------------------------------
# bootstrap


def _indices(n: int, resamples: int, seed: int, indices: Any) -> np.ndarray:
    if indices is not None:
        return np.asarray(indices, dtype=int)
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))
    return rng.integers(0, n, size=(resamples, n))


def _valid_errors(values: Mapping[str, float], what: str) -> None:
    for key, v in values.items():
        if not (isinstance(v, int | float | np.floating) and math.isfinite(v) and v >= 0.0):
            raise ValueError(f"{what}: error of event {key!r} must be a finite number >= 0, got {v!r}")


def acceptance_row(
    method: str,
    cutoff: float,
    errors: Mapping[str, float],
    *,
    seed: int,
    resamples: int = RESAMPLES,
    indices: Any = None,
    threshold: float = THRESHOLD,
) -> dict[str, Any]:
    """SC-010-01 for one learned arm and cut-off on the SNR_obs stratum: the median error and its interval."""
    if not errors:
        raise ValueError("no errors to evaluate")
    _valid_errors(errors, "acceptance")
    values = np.array([errors[k] for k in sorted(errors)], dtype=float)
    idx = _indices(values.size, resamples, seed, indices)
    medians = np.median(values[idx], axis=1)
    lo, hi = np.percentile(medians, [100.0 * (1 - LEVEL) / 2.0, 100.0 * (1 + LEVEL) / 2.0])
    median = float(np.median(values))
    return {
        "criterion": "SC-010-01",
        "method": method,
        "cutoff": cutoff,
        "stratum": "snr_obs",
        "n_events": int(values.size),
        "median_rel_error": median,
        "interval": {"lower": float(lo), "upper": float(hi)},
        "bootstrap": {"resamples": int(idx.shape[0]), "method": "percentile", "level": LEVEL, "seed": seed},
        "threshold": threshold,
        "verdict": "pass" if median <= threshold else "fail",
    }


def paired_comparison(
    baseline: Mapping[str, float],
    model: Mapping[str, float],
    *,
    method: str = "tcn",
    cutoff: float = 0.5,
    indices: Any = None,
    resamples: int = RESAMPLES,
    seed: int = 0,
) -> dict[str, Any]:
    """Paired percentile bootstrap of ``d_i = e_baseline(i) - e_model(i)`` (FR-010-25) and its verdict (FR-010-28)."""
    if not baseline and not model:
        raise InsufficientPairsError("no paired unit: no interval, ranking or verdict can be formed")
    if set(baseline) != set(model):
        raise UnpairedError("the two methods do not share the same event ids")
    _valid_errors(baseline, "baseline")
    _valid_errors(model, "model")
    if len(baseline) == 1:
        return {"n_pairs": 1, "verdict": SINGLE_PAIR_VERDICT}
    ids = sorted(baseline)
    d = np.array([baseline[i] - model[i] for i in ids], dtype=float)
    idx = _indices(d.size, resamples, seed, indices)
    means = d[idx].mean(axis=1)
    lo, hi = (float(v) for v in np.percentile(means, [100.0 * (1 - LEVEL) / 2.0, 100.0 * (1 + LEVEL) / 2.0]))
    verdict = "better" if lo > 0.0 else "worse" if hi < 0.0 else "no significant difference"
    return {
        "baseline": "inverse_velocity",
        "method": method,
        "cutoff": cutoff,
        "stratum": "snr_obs",
        "n_pairs": int(d.size),
        "mean_difference": float(d.mean()),
        "interval": {"lower": lo, "upper": hi},
        "bootstrap": {
            "resamples": int(idx.shape[0]),
            "method": "paired-percentile",
            "resample_unit": "sorted-event-id",
            "level": LEVEL,
            "seed": seed,
        },
        "verdict": verdict,
    }


def compare_all(
    inverse_velocity: Mapping[float, Mapping[str, float]],
    models: Mapping[str, Mapping[float, Mapping[str, float]]],
    *,
    seed: int,
    resamples: int = RESAMPLES,
) -> dict[str, Any]:
    """One comparison per available (learned method, cut-off); 8 are stated, no family-wise claim."""
    comparisons = []
    for method in LEARNED:
        for cutoff in CUTOFFS:
            arm = models.get(method, {}).get(cutoff)
            base = inverse_velocity.get(cutoff)
            if arm is None or base is None:
                continue
            comparisons.append(
                paired_comparison(base, arm, method=method, cutoff=cutoff, resamples=resamples, seed=seed)
            )
    return {"comparisons": comparisons, "multiplicity": {"comparisons": 8, "family_wise_claim": False}}


# ----------------------------------------------------------------------------------------------------------------------
# the one real event


def _finite(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | np.floating) or not math.isfinite(value):
        raise ValueError(f"{what} must be a finite number, got {value!r}")
    return float(value)


def real_event_report(
    *,
    event_id: str,
    t_0_h: float,
    t_f_h: float,
    snr_obs: float,
    forecasts: Mapping[tuple[str, float], Mapping[str, Any]],
) -> dict[str, Any]:
    """The descriptive ``real_event`` block: 12 rows in the fixed order, signed errors, no interval, rank or verdict."""
    t0, tf = _finite(t_0_h, "t_0_h"), _finite(t_f_h, "t_f_h")
    snr = _finite(snr_obs, "snr_obs")
    if not tf > t0:
        raise ValueError("t_f must be after t_0")
    if not snr > 0.0:
        raise ValueError("snr_obs must be positive")
    for method, cutoff in forecasts:
        if method not in METHODS:
            raise ValueError(f"unknown method {method!r}")
        if cutoff not in CUTOFFS:
            raise ValueError(f"unknown cut-off {cutoff!r}")
    rows = []
    for cutoff in CUTOFFS:
        t_c = cutoff_time(t0, tf, cutoff)
        for method in METHODS:
            row: dict[str, Any] = {"cutoff": cutoff, "method": method, "t_c_h": t_c}
            f = forecasts.get((method, cutoff))
            if f is None:
                row.update(outcome="not run", reason="this method produced no forecast for the real event")
            elif f["outcome"] == "no forecast":
                row.update(outcome="no forecast", reason=f["reason"])
            else:
                t_hat = _finite(f["t_hat_f_h"], "t_hat_f_h")
                signed = t_hat - tf
                row.update(
                    outcome=f["outcome"],
                    t_hat_f_h=t_hat,
                    signed_error_h=signed,
                    error_ratio=signed / (tf - t_c),
                    scored_at_cap=f["outcome"] == "no failure predicted",
                )
            rows.append(row)
    return {
        "event_id": event_id,
        "status": "run",
        "label": SINGLE_EVENT_LABEL,
        "snr_obs": snr,
        "t_0_h": t0,
        "t_f_h": tf,
        "rows": rows,
    }


def real_event_not_run(event_id: str, reason: str) -> dict[str, Any]:
    """The ``real_event`` block when the real series is not available: no TTF number, no rows, no SNR."""
    return {"event_id": event_id, "status": "not run", "label": SINGLE_EVENT_LABEL, "reason": reason}

"""Event curves of case C1: seeded events, the baselines and the on-disk ONNX forecasters at two cut-offs (C1-U2).

An event that the evaluation scored is rebuilt from its seed (``events.synthesize_event`` is deterministic), the shared
pre-processor builds the window at each cut-off, and every method forecasts on that same window: the inverse-velocity
line (FR-010-19), the Bayesian posterior band (FR-010-20) and the learned arms through ONNX Runtime CPU on the files
the GPU job exported (FR-010-21, FR-010-22). The zero-shot Chronos-Bolt arm has no ONNX file (FR-010-30 publishes it
as baked forecasts only), so it is never drawn here. Nothing is drawn from a model other than the named files.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio.slope import baselines, events, forecast
from pitstudio.slope.errors import InvalidWindowError
from pitstudio.slope.preprocess import Window
from pitstudio_pipeline.slope import data, infer

ONNX_FILES = {
    "tcn": "tcn-c1.onnx",
    "patchtst": "patchtst-c1.onnx",
    "chronos_bolt_fine_tuned": "chronos_bolt_fine_tuned-c1.onnx",
}
CUTOFFS = (0.5, 0.8)
QUANTILE_ROWS = (0, 4, 8)  # 0.1, 0.5, 0.9
MAX_POINTS = 240
_ID = re.compile(r"^voight-test-[a-z0-9-]+-(\d{6,})$")


class OnnxMissing(FileNotFoundError):
    """A forecaster file the GPU job exported is absent; no substitute model is used."""


def select_events(
    rows: Sequence[Mapping[str, Any]],
    *,
    per_stratum: int = 4,
    quantiles: Sequence[float] = (0.1, 0.4, 0.7, 0.95),
    method: str = "tcn",
    cutoff: float = 0.5,
) -> list[str]:
    """Per stratum the event ids at ``quantiles`` of the relative error of ``method`` at ``cutoff`` (by rank)."""
    if len(quantiles) != per_stratum:
        raise ValueError("one quantile per selected event is needed")
    picked: list[str] = []
    strata = sorted({r["stratum"] for r in rows})
    for stratum in strata:
        group = sorted(
            (float(r["rel_error"]), r["event_id"])
            for r in rows
            if r["stratum"] == stratum
            and r["method"] == method
            and r["cutoff"] == cutoff
            and r["outcome"] != "no forecast"
        )
        n = len(group)
        picked.extend(group[min(n - 1, round(q * (n - 1)))][1] for q in quantiles)
    return picked


def event_seed(event_id: str) -> int:
    m = _ID.match(event_id)
    if not m:
        raise ValueError(f"not a synthetic test event id: {event_id!r}")
    return int(m.group(1))


def rebuild_event(event_id: str, stratum: str, config: dict[str, Any]) -> dict[str, Any]:
    """The synthetic test event that the evaluation scored under ``event_id``."""
    doc = events.synthesize_event(
        event_seed(event_id),
        stratum=stratum,
        snr_obs=None,
        n_samples=int(config["n_samples"]),
        split="test",
        config=config,
    )
    if doc["event_id"] != event_id:
        raise ValueError(f"the rebuilt event is {doc['event_id']!r}, not {event_id!r}")
    return doc


def decimate(t: Any, y: Any, limit: int = MAX_POINTS) -> tuple[list[float], list[float]]:
    """At most ``limit`` evenly spaced samples of a series, both ends kept."""
    tt, yy = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    if tt.size <= limit:
        return [float(v) for v in tt], [float(v) for v in yy]
    idx = np.unique(np.round(np.linspace(0, tt.size - 1, limit)).astype(int))
    return [float(v) for v in tt[idx]], [float(v) for v in yy[idx]]


def _last_points(window: Window) -> tuple[np.ndarray, np.ndarray]:
    tt, yy = baselines._points(window.t, window.y, baselines.LAST_FRACTION, baselines.MIN_POINTS)
    return tt, yy


def iv_fit(window: Window) -> dict[str, Any]:
    """The OLS line over the last 25 % of the unmasked samples and its root (FR-010-19)."""
    tt, yy = _last_points(window)
    y_bar, slope, t_bar = baselines._ols(tt, yy)
    fit_y = y_bar + slope * (tt - t_bar)
    forecast_ = baselines.inverse_velocity(window)
    return {
        "t_hat_f_h": float(forecast_.t_hat_f),
        "outcome": forecast_.outcome,
        "fit_t_h": [float(v) for v in tt],
        "fit_y": [float(v) for v in fit_y],
    }


def bayes_band(window: Window, *, seed: int, draws: int = 4000, grid: int = 60) -> dict[str, Any]:
    """The 10 / 50 / 90 percent envelope of the posterior lines on the fit span (FR-010-20)."""
    tt, yy = _last_points(window)
    t_mu, t_sd = float(tt.mean()), float(tt.std())
    y_mu, y_sd = float(yy.mean()), float(yy.std())
    result = baselines.bayesian_ttf(window, seed=seed, draws=draws)
    base: dict[str, Any] = {"t_hat_f_h": float(result.t_hat_f), "outcome": result.outcome}
    if not (t_sd > 0.0 and y_sd > 0.0):
        return {**base, "t_h": [], "y_median": [], "y_lo": [], "y_hi": []}
    ts, ys = (tt - t_mu) / t_sd, (yy - y_mu) / y_sd
    x = np.column_stack([np.ones(ts.size), ts])
    beta, *_ = np.linalg.lstsq(x, ys, rcond=None)
    resid = ys - x @ beta
    sigma2 = max(float(resid @ resid) / max(ts.size - 2, 1), baselines.SIGMA2_FLOOR)
    mean, cov = baselines.bayes_posterior(ts, ys, sigma2, baselines.PRIOR_SD**2)
    chol = np.linalg.cholesky((cov + cov.T) / 2.0)
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))
    sample = mean[None, :] + rng.standard_normal((draws, 2)) @ chol.T
    b1 = y_sd * sample[:, 1] / t_sd
    b0 = y_mu + y_sd * sample[:, 0] - b1 * t_mu
    span = np.linspace(float(tt[0]), float(tt[-1]), grid)
    lines = b0[:, None] + b1[:, None] * span[None, :]
    lo, med, hi = np.percentile(lines, [10.0, 50.0, 90.0], axis=0)
    return {
        **base,
        "t_h": [float(v) for v in span],
        "y_median": [float(v) for v in med],
        "y_lo": [float(v) for v in lo],
        "y_hi": [float(v) for v in hi],
    }


def load_onnx_forecasters(onnx_dir: str | Path) -> dict[str, Callable[[np.ndarray], Any]]:
    """ONNX Runtime CPU sessions of the three exported arms; a missing file raises ``OnnxMissing`` naming it."""
    root = Path(onnx_dir)
    missing = [name for name in ONNX_FILES.values() if not (root / name).is_file()]
    if missing:
        raise OnnxMissing(f"missing exported forecaster file(s): {', '.join(missing)}")
    return {arm: infer.OrtForecaster(root / name) for arm, name in ONNX_FILES.items()}


def _learned(model: Callable[[np.ndarray], Any], window: Window) -> dict[str, Any]:
    try:
        f = forecast.learned_forecast(model, window)
    except InvalidWindowError as exc:
        return {"status": "no forecast", "reason": str(exc)[:290]}
    t, med = decimate(f.times, f.median_y, 80)
    _, lo = decimate(f.times, f.quantile_y[QUANTILE_ROWS[0]], 80)
    _, hi = decimate(f.times, f.quantile_y[QUANTILE_ROWS[2]], 80)
    return {
        "status": "ok",
        "outcome": f.outcome,
        "t_hat_f_h": float(f.t_hat_f),
        "interval_80_h": [float(f.interval_80[0]), float(f.interval_80[1])],
        "scored_at_cap": bool(f.scored_at_cap),
        "t_h": t,
        "y_median": med,
        "y_lo": lo,
        "y_hi": hi,
    }


def bake_event(
    doc: Mapping[str, Any],
    forecasters: Mapping[str, Callable[[np.ndarray], Any]],
    *,
    cutoffs: Sequence[float] = CUTOFFS,
    seed: int = 0,
) -> dict[str, Any]:
    """Observed series, noise-free truth, and every method's forecast on the window at each cut-off."""
    t = np.asarray(doc["t_h"], dtype=float)
    omega = np.asarray(doc["los_displacement_mm"], dtype=float)
    out_cutoffs = []
    for c in cutoffs:
        window, t_c = data.window_at(doc, float(c))
        methods: dict[str, Any] = {}
        iv = iv_fit(window)
        methods["inverse_velocity"] = {
            "status": "ok",
            "outcome": iv["outcome"],
            "t_hat_f_h": iv["t_hat_f_h"],
            "scored_at_cap": iv["outcome"] != "predicted",
            "fit_t_h": iv["fit_t_h"],
            "fit_y": iv["fit_y"],
        }
        band = bayes_band(window, seed=seed)
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
            methods[arm] = _learned(model, window)
        obs_mask = np.isfinite(window.y)
        ot, oy = decimate(window.t[obs_mask], window.y[obs_mask], MAX_POINTS)
        out_cutoffs.append(
            {
                "cutoff": float(c),
                "t_c_h": float(t_c),
                "observed_t_h": ot,
                "observed_y": oy,
                "methods": methods,
            }
        )
    dt, do = decimate(t, omega, MAX_POINTS)
    truth_t = np.linspace(float(t[0]), float(doc["t_f_h"]) * 0.995, MAX_POINTS)
    truth_y = data.true_inverse_velocity(doc, truth_t)
    return {
        "event_id": doc["event_id"],
        "stratum": doc["stratum"],
        "t_f_h": float(doc["t_f_h"]),
        "t_0_h": float(doc["t_0_h"]),
        "parameters": dict(doc["parameters"]),
        "displacement_t_h": dt,
        "displacement_mm": do,
        "truth_t_h": [float(v) for v in truth_t],
        "truth_y": [float(v) for v in truth_y],
        "cutoffs": out_cutoffs,
    }

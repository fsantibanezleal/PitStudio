"""Training pairs and the forecast stage of case C1 (`s30_train` inputs, `s40_infer`).

A training pair is a context (2, 128) built by the shared pre-processor at a cut-off of one synthetic event and the
target:
the next 64 steps of 4 delta of the inverse velocity, scaled by the context's mean |y|. The target comes from the
event's
noise-free Voight law (the generator knows it): y(t) = (1/ (cos psi v(t))) with the terminal-stage velocity
v(t) = [(alpha - 1) A (t_f - t)]^(-1/(alpha - 1)), continued below zero after t_f so that the median path crosses zero
at the
exact failure time; during the steady phase y is the constant 1 / (cos psi v_onset). Only training events ever reach
this
function for training (FR-010-15).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from pitstudio.slope import baselines, forecast, preprocess
from pitstudio.slope.context import build_context
from pitstudio.slope.errors import InvalidWindowError

TRAIN_CUTOFFS = tuple(np.round(np.arange(0.30, 0.9001, 0.05), 2))
EVAL_CUTOFFS = (0.5, 0.8)


def true_inverse_velocity(doc: Mapping[str, Any], t: np.ndarray) -> np.ndarray:
    """Noise-free inverse velocity (h/mm of LOS displacement) of a synthetic event at times ``t``."""
    p = doc["parameters"]
    alpha, a, t_f = p["alpha"], p["a_coefficient"], doc["t_f_h"]
    cos_psi = np.cos(np.radians(p["psi_deg"]))
    t_on = p["steady_phase_fraction"] * p["terminal_duration_h"]
    remaining = t_f - np.asarray(t, dtype=float)
    magnitude = ((alpha - 1.0) * a * np.abs(remaining)) ** (1.0 / (alpha - 1.0))
    terminal = np.sign(remaining) * magnitude
    v_on = p["onset_velocity_mm_per_day"] / 24.0
    y = np.where(np.asarray(t) < t_on, 1.0 / v_on, terminal)
    return np.asarray(y / cos_psi)


def window_at(doc: Mapping[str, Any], cutoff: float) -> tuple[preprocess.Window, float]:
    t = np.asarray(doc["t_h"], dtype=float)
    omega = np.asarray(doc["los_displacement_mm"], dtype=float)
    t_c = float(doc["t_0_h"] + cutoff * (doc["t_f_h"] - doc["t_0_h"]))
    end = min(int(np.searchsorted(t, t_c, side="right")) + 1, len(t))  # the sample after the cut-off interpolates it
    return preprocess.preprocess_window(t[:end], omega[:end], t_c), t_c


def training_pairs(
    events: Sequence[Mapping[str, Any]], cutoffs: Sequence[float] = TRAIN_CUTOFFS, split: str = "train"
) -> tuple[np.ndarray, np.ndarray]:
    """Contexts (N, 2, 128) float32 and targets (N, 64) float32 in scaled units from synthetic events of ``split``
    (training, or validation for the hyper-parameter choice); never a test or real event."""
    if split not in ("train", "validation"):
        raise ValueError(f"split must be train or validation, got {split!r}")
    contexts, targets = [], []
    for doc in events:
        if doc.get("split") != split or doc.get("synthetic") is not True:
            raise ValueError(f"only synthetic {split} events may be used here, got {doc.get('event_id')!r}")
        for c in cutoffs:
            try:
                w, t_c = window_at(doc, float(c))
                ctx = build_context(w)
            except InvalidWindowError, ValueError:
                continue
            times = t_c + 4.0 * w.delta * np.arange(1, 65)
            contexts.append(ctx.context)
            targets.append((true_inverse_velocity(doc, times) / ctx.scale).astype(np.float32))
    if not contexts:
        raise ValueError("no usable training window")
    return np.stack(contexts).astype(np.float32), np.stack(targets).astype(np.float32)


def predict_events(
    events: Sequence[Mapping[str, Any]],
    forecasters: Mapping[str, Callable[[np.ndarray], Any]],
    *,
    cutoffs: Sequence[float] = EVAL_CUTOFFS,
    seed: int = 0,
) -> list[dict[str, Any]]:
    """All methods on identical windows: prediction rows for ``evaluate.score_events``."""
    rows: list[dict[str, Any]] = []
    for doc in events:
        for c in cutoffs:
            base = {
                "event_id": doc["event_id"],
                "stratum": doc["stratum"],
                "cutoff": c,
                "t_0_h": doc["t_0_h"],
                "t_f_h": doc["t_f_h"],
            }
            try:
                w, _ = window_at(doc, c)
            except (InvalidWindowError, ValueError) as exc:
                reason = str(exc)[:290]
                rows += [
                    {**base, "method": m, "outcome": "no forecast", "reason": reason}
                    for m in ("inverse_velocity", "bayesian_ttf", *forecasters)
                ]
                continue
            for method, fn in (
                ("inverse_velocity", baselines.inverse_velocity),
                ("bayesian_ttf", lambda x: baselines.bayesian_ttf(x, seed=seed)),
            ):
                try:
                    f = fn(w)
                    row = {**base, "method": method, "outcome": f.outcome, "t_hat_f_h": f.t_hat_f}
                    if method == "bayesian_ttf" and f.q10 is not None:
                        row["interval_80_h"] = {"lower_h": f.q10, "upper_h": f.q90}
                    rows.append(row)
                except InvalidWindowError as exc:
                    rows.append({**base, "method": method, "outcome": "no forecast", "reason": str(exc)[:290]})
            for method, model in forecasters.items():
                try:
                    f2 = forecast.learned_forecast(model, w)
                    rows.append(
                        {
                            **base,
                            "method": method,
                            "outcome": f2.outcome,
                            "t_hat_f_h": f2.t_hat_f,
                            "interval_80_h": {"lower_h": f2.interval_80[0], "upper_h": f2.interval_80[1]},
                        }
                    )
                except InvalidWindowError as exc:
                    rows.append({**base, "method": method, "outcome": "no forecast", "reason": str(exc)[:290]})
    return rows

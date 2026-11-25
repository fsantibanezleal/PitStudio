"""The forecast loop of the learned forecasters with the shared read-out (FR-010-21, FR-010-22), numpy only.

``model(context)`` maps a float32 context (1, 2, 128) to float32 quantiles 0.1 ... 0.9 (1, 9, 64) of the next 64 steps
of 4
delta, in the units of the scaled context. The loop calls the model on the window's context, extends the forecast by
feeding the
median path back (previous channel 0 shifted left by 64 with the 64 median values appended, mask 1 for them) while the
median
path has no step <= 0 and fewer than ``max_blocks`` blocks exist, and reads the failure time of the concatenated paths
with
``pitstudio.slope.readout`` (the cap is t_c + 1,024 delta, four blocks). The same loop runs in the ``forecasters`` web
worker.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from pitstudio.slope import readout
from pitstudio.slope.context import BLOCK, CONTEXT_LENGTH, build_context
from pitstudio.slope.errors import InvalidWindowError
from pitstudio.slope.preprocess import Window

HORIZON_STEPS = 64
MAX_BLOCKS = 4
QUANTILES = readout.QUANTILES
MEDIAN_ROW = 4
CAP_STEPS = 1024


@dataclass(frozen=True)
class LearnedForecast:
    """The read-out failure time, its 80 % interval and the paths behind them (y units)."""

    outcome: str
    t_hat_f: float
    scored_at_cap: bool
    interval_80: tuple[float, float]
    n_model_calls: int
    times: np.ndarray
    median_y: np.ndarray
    quantile_y: np.ndarray


def learned_forecast(
    model: Callable[[np.ndarray], Any], window: Window, *, max_blocks: int = MAX_BLOCKS
) -> LearnedForecast:
    """Forecast with ``model`` on ``window`` and read the failure time (see the module docstring)."""
    if isinstance(max_blocks, bool) or not isinstance(max_blocks, int) or not 1 <= max_blocks <= MAX_BLOCKS:
        raise ValueError(f"max_blocks must be an integer in [1, {MAX_BLOCKS}], got {max_blocks!r}")
    ctx = build_context(window)
    current = ctx.context[None, :, :].copy()
    blocks: list[np.ndarray] = []
    calls = 0
    while True:
        out = np.asarray(model(current))
        calls += 1
        if out.shape != (1, len(QUANTILES), HORIZON_STEPS):
            raise InvalidWindowError(
                f"the model returned shape {out.shape}, expected (1, {len(QUANTILES)}, {HORIZON_STEPS})"
            )
        if not np.all(np.isfinite(out)):
            raise InvalidWindowError("the model returned a non-finite value")
        paths = out[0].astype(np.float64)
        blocks.append(paths)
        median = np.concatenate([b[MEDIAN_ROW] for b in blocks])
        if calls >= max_blocks or bool(np.any(median <= 0.0)):
            break
        nxt = np.empty_like(current)
        nxt[0, 0, : CONTEXT_LENGTH - HORIZON_STEPS] = current[0, 0, HORIZON_STEPS:]
        nxt[0, 0, CONTEXT_LENGTH - HORIZON_STEPS :] = paths[MEDIAN_ROW].astype(np.float32)
        nxt[0, 1, : CONTEXT_LENGTH - HORIZON_STEPS] = current[0, 1, HORIZON_STEPS:]
        nxt[0, 1, CONTEXT_LENGTH - HORIZON_STEPS :] = 1.0
        current = nxt
    quantile_y = np.concatenate(blocks, axis=1) * ctx.scale
    t_c = float(window.t[-1])
    step = BLOCK * window.delta
    times = t_c + step * np.arange(1, quantile_y.shape[1] + 1)
    cap = t_c + CAP_STEPS * window.delta
    median_y = quantile_y[MEDIAN_ROW]
    main = readout.read_out(median_y, times, cap)
    lo, hi = readout.read_out_interval(quantile_y, times, cap, QUANTILES)
    return LearnedForecast(
        main.outcome, main.t_hat_f, main.scored_at_cap, (lo.t_hat_f, hi.t_hat_f), calls, times, median_y, quantile_y
    )

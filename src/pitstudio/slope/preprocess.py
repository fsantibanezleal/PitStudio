"""The one pre-processor every C1 method receives (FR-010-18), numpy only.

For the observed window [t_0, t_c] (``t_0`` is the first timestamp; only samples with ``t <= t_c`` are used, a cut-off
that
falls between two samples is read by linear interpolation) the displacement is resampled to L = 512 uniform samples,
``delta = (t_c - t_0) / 511``, by linear interpolation; the velocity ``v_k`` is the least-squares slope over 9
consecutive
samples assigned to the centre sample (``sum_j j Omega_{k+j} / (60 delta)``, since the sum of ``j^2`` over -4..4 is 60);
``y_k = 1 / v_k`` where ``v_k > 0`` and masked (NaN) elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from pitstudio.slope.errors import InvalidWindowError

L = 512
HALF = 4  # the velocity window is 2 * HALF + 1 = 9 samples


@dataclass(frozen=True)
class Window:
    """The pre-processed observed window: 512 uniform samples of time, displacement, velocity and inverse velocity."""

    t: np.ndarray
    omega: np.ndarray
    delta: float
    v: np.ndarray
    y: np.ndarray
    mask: np.ndarray


def _series(t: Any, omega: Any, t_c: Any) -> tuple[np.ndarray, np.ndarray, float]:
    try:
        tt = np.asarray(t, dtype=float)
        om = np.asarray(omega, dtype=float)
        cut = float(t_c)
    except (TypeError, ValueError) as exc:
        raise InvalidWindowError(f"the window is not numeric: {exc}") from None
    if tt.ndim != 1 or om.ndim != 1 or tt.shape != om.shape:
        raise InvalidWindowError("time and displacement must be one-dimensional arrays of the same length")
    if tt.size < 2:
        raise InvalidWindowError("a window needs at least 2 samples")
    if not (np.all(np.isfinite(tt)) and np.all(np.isfinite(om)) and np.isfinite(cut)):
        raise InvalidWindowError("the window contains a non-finite value")
    if not np.all(np.diff(tt) > 0.0):
        raise InvalidWindowError("timestamps must be strictly increasing")
    if not cut > tt[0]:
        raise InvalidWindowError("the cut-off must be after the first timestamp")
    span = float(tt[-1] - tt[0])
    if cut > tt[-1] + 1e-9 * max(span, 1.0):
        raise InvalidWindowError("the cut-off is beyond the last sample")
    return tt, om, cut


def preprocess_window(t: Any, omega: Any, t_c: Any) -> Window:
    """Resample the window to 512 points and compute the centred velocity and the inverse velocity."""
    tt, om, cut = _series(t, omega, t_c)
    keep = tt <= cut
    t_use, om_use = tt[keep], om[keep]
    if t_use[-1] < cut:  # the cut-off lies between two samples: its value is the interpolation
        t_use = np.append(t_use, cut)
        om_use = np.append(om_use, float(np.interp(cut, tt, om)))
    t0 = float(tt[0])
    grid = np.linspace(t0, cut, L)
    resampled = np.interp(grid, t_use, om_use)
    delta = (cut - t0) / (L - 1)
    v = np.full(L, np.nan)
    j = np.arange(-HALF, HALF + 1, dtype=float)
    # (v_k) = sum_j j Omega_{k+j} / (60 delta) for k = 4 .. L - 5: a correlation with the offsets -4..4
    windows = np.lib.stride_tricks.sliding_window_view(resampled, 2 * HALF + 1)
    v[HALF : L - HALF] = windows @ j / (60.0 * delta)
    positive = np.zeros(L, dtype=bool)
    positive[HALF : L - HALF] = v[HALF : L - HALF] > 0.0
    y = np.full(L, np.nan)
    y[positive] = 1.0 / v[positive]
    return Window(t=grid, omega=resampled, delta=float(delta), v=v, y=y, mask=positive)

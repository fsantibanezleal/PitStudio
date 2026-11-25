# ruff: noqa: E501
"""Constant-velocity time to collision of two disc-shaped vehicles and the near-miss rate (spec 018 FR-018-55, docs M20).

With p the position of b minus the position of a, w the velocity of b minus the velocity of a and R the sum of the two disc
radii, the pair touches when |p + w tau| = R; the TTC is the smallest positive root of that quadratic. It is 0 when the discs
already overlap (|p| <= R), infinite when the pair does not close (p . w >= 0, or w = 0, or a negative discriminant) and
otherwise gap / (-p . w + sqrt(disc)), the form without cancellation near a grazing contact. The same formula is in the
browser engine `web/src/engines/traffic/ttc.ts`; this module is its numpy twin for the pipeline traffic layer (`ttc_pairs`
works on whole arrays of pairs).

Pure closed form: no randomness, no simulation. The model ignores braking and steering of the pair during the encounter; it is
a screening metric (docs M20, assumptions).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .errors import HaulError

POSITION_LIMIT_M = 1e5
VELOCITY_LIMIT_M_PER_S = 60.0


class TtcInputError(HaulError):
    """A TTC argument is malformed: `code` is E_SCHEMA (not a pair of numbers), E_NONFINITE or E_RANGE (as FR-018-38)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _pair(value: Any, name: str, limit: float) -> tuple[float, float]:
    if not isinstance(value, (list, tuple, np.ndarray)) or len(value) != 2:
        raise TtcInputError("E_SCHEMA", f"{name} must be a pair of numbers")
    out = []
    for v in value:
        if isinstance(v, bool) or not isinstance(v, (int, float, np.integer, np.floating)):
            raise TtcInputError("E_SCHEMA", f"{name} must hold numbers")
        f = float(v)
        if not math.isfinite(f):
            raise TtcInputError("E_NONFINITE", f"{name} holds a non-finite number")
        if abs(f) > limit:
            raise TtcInputError("E_RANGE", f"{name} component {f} is beyond +-{limit:g}")
        out.append(f)
    return out[0], out[1]


def ttc(relative_position_m: Any, relative_velocity_m_per_s: Any, radius_m: float) -> tuple[str, float]:
    """The TTC of one pair: ("closing", tau), ("overlapping", 0.0) or ("not-closing", inf)."""
    p = _pair(relative_position_m, "relative_position_m", POSITION_LIMIT_M)
    w = _pair(relative_velocity_m_per_s, "relative_velocity_m_per_s", VELOCITY_LIMIT_M_PER_S)
    if isinstance(radius_m, bool) or not isinstance(radius_m, (int, float, np.integer, np.floating)):
        raise TtcInputError("E_SCHEMA", "radius_m must be a number")
    r = float(radius_m)
    if not math.isfinite(r) or r <= 0:
        raise TtcInputError("E_RANGE", "radius_m must be positive and finite")
    value = float(ttc_pairs(np.array([p]), np.array([w]), r)[0])
    if value == 0.0:
        return "overlapping", 0.0
    if math.isinf(value):
        return "not-closing", math.inf
    return "closing", value


def ttc_pairs(p: np.ndarray, w: np.ndarray, radius_m: float | np.ndarray) -> np.ndarray:
    """TTC of arrays of pairs: `p` and `w` have shape (..., 2), `radius_m` is a scalar or broadcasts to (...). Returns an
    array of shape (...) with 0 for overlapping pairs and +inf for pairs that do not close."""
    p, w = np.asarray(p, dtype=float), np.asarray(w, dtype=float)
    r = np.asarray(radius_m, dtype=float)
    pp = p[..., 0] ** 2 + p[..., 1] ** 2
    ww = w[..., 0] ** 2 + w[..., 1] ** 2
    pw = p[..., 0] * w[..., 0] + p[..., 1] * w[..., 1]
    gap = pp - r * r
    disc = pw * pw - ww * gap
    closing = (gap > 0) & (ww > 0) & (pw < 0) & (disc >= 0)
    denom = np.where(closing, -pw + np.sqrt(np.where(closing, disc, 0.0)), 1.0)
    out = np.where(closing, gap / denom, np.inf)
    return np.where(pp <= r * r, 0.0, out)


def near_misses_per_1000h(near_misses: int, exposure_seconds: float) -> float:
    """Near-misses per 1,000 hours of exposure."""
    if isinstance(near_misses, bool) or not isinstance(near_misses, (int, np.integer)) or near_misses < 0:
        raise ValueError("the near-miss count must be a non-negative integer")
    if not math.isfinite(exposure_seconds) or exposure_seconds <= 0:
        raise ValueError("the exposure must be positive and finite")
    return near_misses * 1000.0 / (exposure_seconds / 3600.0)

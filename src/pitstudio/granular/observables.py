"""Repose-angle and run-out observables of the GNS evaluation (FR-011-05, P-011-06, P-011-07).

One function serves reference and surrogate rollouts. Conventions (spec section 7):
- the free surface is the maximum particle top height (y + d / 2) per bin of width 2 d, the bins counted outward from
the
  family's reference abscissa (wall x = 0 for the column collapse, the pour point x_p for the pile, the crest x_c for
  the dump);
- the repose angle is the arctan of the least-squares slope of the bin heights over the bins whose height lies between
20 % and
  80 % of the pile height (the highest bin of the flank); the pile averages its two flanks, the dump uses the flank on
  the
  side x > x_c;
- the run-out is built from the 99th (and 1st) percentile of the particle x (linear interpolation between order
statistics).
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

FAMILIES = ("column-collapse", "pile-formation", "dump-over-crest")
_REFERENCE_KEY = {
    "column-collapse": "column_width_m",
    "pile-formation": "pour_point_x_m",
    "dump-over-crest": "crest_x_m",
}
_MIN_BINS = 2


def _check_family(family: str) -> None:
    if family not in FAMILIES:
        raise ValueError(f"unknown family {family!r}; expected one of {list(FAMILIES)}")


def _positions(positions: np.ndarray) -> np.ndarray:
    arr = np.asarray(positions, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 2 or arr.shape[0] == 0:
        raise ValueError(f"positions must have shape [N, 2] with N >= 1, got {list(arr.shape)}")
    if not np.isfinite(arr).all():
        raise ValueError("positions contain a non-finite value")
    return arr


def _geometry_value(geometry: Mapping[str, float], family: str) -> float:
    key = _REFERENCE_KEY[family]
    if key not in geometry:
        raise ValueError(f"geometry of the {family} family needs {key!r}")
    value = float(geometry[key])
    if not math.isfinite(value):
        raise ValueError(f"geometry value {key!r} is not finite")
    return value


def _flank_angle_deg(positions: np.ndarray, *, d: float, reference_x: float, sign: float) -> float:
    """Repose angle of one flank: the particles on the `sign` side of `reference_x`, bins of 2 d counted from it."""
    offset = sign * (positions[:, 0] - reference_x)
    side = offset >= 0.0
    if not side.any():
        raise ValueError("no particle on the flank side of the reference abscissa")
    bins = np.floor(offset[side] / (2.0 * d)).astype(np.int64)
    tops = positions[side, 1] + d / 2.0
    n_bins = int(bins.max()) + 1
    surface = np.full(n_bins, -np.inf)
    np.maximum.at(surface, bins, tops)
    occupied = np.isfinite(surface)
    centres = (np.arange(n_bins) + 0.5) * 2.0 * d
    height = float(surface[occupied].max())
    window = occupied & (surface >= 0.2 * height) & (surface <= 0.8 * height)
    if int(window.sum()) < _MIN_BINS:
        raise ValueError("fewer than two surface bins between 20 % and 80 % of the pile height: no repose angle")
    slope = np.polyfit(centres[window], surface[window], 1)[0]
    return float(math.degrees(math.atan(-slope)))


def repose_angle_deg(positions: np.ndarray, *, d: float, family: str, geometry: Mapping[str, float]) -> float:
    """Repose angle (degrees) of the settled particles of `family` (FR-011-05)."""
    _check_family(family)
    pos = _positions(positions)
    if not isinstance(d, int | float | np.floating) or not math.isfinite(d) or d <= 0:
        raise ValueError(f"the particle diameter d must be a positive finite number, got {d!r}")
    ref = 0.0 if family == "column-collapse" else _geometry_value(geometry, family)
    if family == "column-collapse":
        _geometry_value(geometry, family)  # the wall is at x = 0; the width must still be recorded
    if family == "pile-formation":
        right = _flank_angle_deg(pos, d=d, reference_x=ref, sign=1.0)
        left = _flank_angle_deg(pos, d=d, reference_x=ref, sign=-1.0)
        return 0.5 * (right + left)
    return _flank_angle_deg(pos, d=d, reference_x=ref, sign=1.0)


def run_out(positions: np.ndarray, *, family: str, geometry: Mapping[str, float]) -> float:
    """Run-out (m): x99 - L0 (collapse), mean of (x99 - x_p) and (x_p - x1) (pile), x99 - x_c (dump)."""
    _check_family(family)
    pos = _positions(positions)
    ref = _geometry_value(geometry, family)
    x99 = float(np.percentile(pos[:, 0], 99))
    if family == "pile-formation":
        x1 = float(np.percentile(pos[:, 0], 1))
        return 0.5 * ((x99 - ref) + (ref - x1))
    return x99 - ref


def observables(positions: np.ndarray, *, d: float, family: str, geometry: Mapping[str, float]) -> dict[str, float]:
    """Both observables of one state: {"repose_deg", "run_out_m"}."""
    return {
        "repose_deg": repose_angle_deg(positions, d=d, family=family, geometry=geometry),
        "run_out_m": run_out(positions, family=family, geometry=geometry),
    }

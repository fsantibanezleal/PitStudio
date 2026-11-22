"""Measurements and the flow-aware rest test of the planar reference rollouts (spec 011, FR-011-03, FR-011-05,
FR-011-10).

Pure NumPy, total on every input a run can produce: a jammed hopper or an empty heap returns None or NaN, never raises
(the gns-v2 measurement raised on a jammed pour: a defect, not a result).
"""

from __future__ import annotations

import bisect
import dataclasses
import math
from collections.abc import Mapping

import numpy as np

from . import space
from .space import D

ORIFICE_MARGIN_D = 1.5  # a grain has been discharged once it is this far below the orifice plane
MIN_HEAP_GRAINS = 50  # fewer discharged grains than this give no heap to measure


def discharged_fraction(z: np.ndarray, z_orifice: float) -> float:
    """Fraction of the grains whose centre is below the orifice level minus the margin (z in metres, any shape)."""
    z = np.asarray(z, dtype=np.float64)
    if z.size == 0:
        return 0.0
    return float((z < z_orifice - ORIFICE_MARGIN_D * D).mean())


def measure_rate(frames_z: np.ndarray, t: np.ndarray, radii: np.ndarray, z_orifice: float) -> tuple[float, float]:
    """(rate m^2/s, discharged fraction) of a feed from the heights of the grains, frames_z[t, i].

    The rate is the slope of the cumulative solid area of the grains that crossed the orifice level, ordered by crossing
    time, between 20 % and 80 % of the discharged area. NaN when fewer than 20 grains crossed or the window is
    degenerate.
    """
    z = np.asarray(frames_z, dtype=np.float64)
    r = np.asarray(radii, dtype=np.float64)
    if z.ndim != 2 or z.shape[0] < 2 or z.shape[1] == 0:
        return float("nan"), 0.0
    below = z < z_orifice - ORIFICE_MARGIN_D * D
    crossed = below.any(axis=0)
    frac = float(crossed.mean())
    if crossed.sum() < 20:
        return float("nan"), frac
    first = below.argmax(axis=0)
    idx = np.where(crossed)[0]
    order = np.argsort(first[idx], kind="stable")
    area = math.pi * r[idx[order]] ** 2
    tc = np.asarray(t, dtype=np.float64)[first[idx[order]]]
    cum = np.cumsum(area)
    share = cum / cum[-1]
    window = (share >= 0.2) & (share <= 0.8)
    if window.sum() < 8 or np.ptp(tc[window]) <= 0.0:
        return float("nan"), frac
    return float(np.polyfit(tc[window], cum[window], 1)[0]), frac


def independent_repose(pos: np.ndarray, d: float, family: str, ref: float) -> float:
    """Independent fit (not the repo extractor): orthogonal least squares through the top envelope on d / 2 columns,
    20 to 80 %
    of the height; the pile averages its two flanks. NaN when a flank has too few columns."""
    pos = np.asarray(pos, dtype=np.float64)
    if pos.ndim != 2 or len(pos) < 3:
        return float("nan")
    flanks = (1.0,) if family != "pile-formation" else (1.0, -1.0)
    out = []
    for sign in flanks:
        x = (pos[:, 0] - ref) * sign
        m = x >= 0
        x, top = x[m], pos[m, 1] + d / 2
        if len(x) < 3:
            return float("nan")
        b = np.floor(x / (d / 2)).astype(int)
        env = np.full(b.max() + 1, -np.inf)
        np.maximum.at(env, b, top)
        c = (np.arange(len(env)) + 0.5) * d / 2
        ok = np.isfinite(env)
        c, env = c[ok], env[ok]
        if len(env) < 3:
            return float("nan")
        h = env.max()
        sel = (env >= 0.2 * h) & (env <= 0.8 * h)
        pts = np.stack([c[sel], env[sel]], 1)
        if len(pts) < 3:
            return float("nan")
        _, _, vt = np.linalg.svd(pts - pts.mean(0), full_matrices=False)
        if vt[0][0] == 0.0:
            return 90.0
        out.append(math.degrees(math.atan(abs(vt[0][1] / vt[0][0]))))
    return float(np.mean(out))


def heap_repose(
    pos: np.ndarray, *, family: str, geometry: Mapping[str, float], z_orifice: float | None = None
) -> dict[str, float] | None:
    """Repose of the final heap with the repo extractor (FR-011-05) and the independent fit, None when there is no heap.

    `z_orifice` keeps only the discharged grains (the heap), as the feed families can leave grains on the funnel plates.
    """
    from pitstudio.granular import observables as obs

    pos = np.asarray(pos, dtype=np.float64).reshape(-1, 2)
    if z_orifice is not None:
        pos = pos[pos[:, 1] < z_orifice - ORIFICE_MARGIN_D * D]
    if len(pos) < MIN_HEAP_GRAINS or not np.isfinite(pos).all():
        return None
    try:
        angle = float(obs.repose_angle_deg(pos, d=D, family=family, geometry=geometry))
    except ValueError:
        return None
    ref = {
        "column-collapse": geometry.get("column_width_m"),
        "pile-formation": geometry.get("pour_point_x_m"),
        "dump-over-crest": geometry.get("crest_x_m"),
    }[family]
    return {"repose_deg": angle, "repose_indep_deg": independent_repose(pos, D, family, float(ref or 0.0))}


@dataclasses.dataclass
class RestJudge:
    """Rest test of one rollout: static for `n_rest` frames, but only after the feed has run.

    update() returns "run", "rest" or "jammed". A feed (`discharged_min` set) declares rest only when the maximum grain
    speed is below `thr` for `n_rest` consecutive frames AND the discharged fraction exceeds `discharged_min`. Static
    with less discharged is a jam (a quasi-static feed cannot restart), reported at once instead of after the whole
    time cap; so is a feed whose discharged fraction gained less than `stall_gain` over the last `stall_s` seconds while
    still below the minimum (a creeping arch never goes static). Nothing is judged before `t_min` (a hopper at rest at
    t = 0 has not started).
    """

    thr: float
    n_rest: int = space.REST_FRAMES
    discharged_min: float | None = None
    t_min: float = 0.3
    stall_s: float | None = None
    stall_gain: float = 0.02
    static: int = 0
    _times: list[float] = dataclasses.field(default_factory=list)
    _values: list[float] = dataclasses.field(default_factory=list)

    def update(self, t: float, vmax: float, discharged: float = 1.0) -> str:
        self.static = self.static + 1 if (t >= self.t_min and vmax < self.thr) else 0
        if self.static >= self.n_rest:
            if self.discharged_min is not None and not discharged > self.discharged_min:
                return "jammed"
            return "rest"
        if self.stall_s is not None and self.discharged_min is not None:
            self._times.append(t)
            self._values.append(discharged)
            k = bisect.bisect_right(self._times, t - self.stall_s) - 1
            if k >= 0 and discharged <= self.discharged_min and discharged - self._values[k] < self.stall_gain:
                return "jammed"
        return "run"

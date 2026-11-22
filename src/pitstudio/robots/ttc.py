# SPDX-License-Identifier: Apache-2.0
"""Time to collision between oriented rectangular footprints (FR-014-34, FR-014-47, P-014-08).

TTC = r / (-r_dot) when r_dot < 0 and +inf otherwise, r the gap between the footprints (0 at contact) and r_dot the
relative velocity projected on the unit vector between the closest points. Footprints that overlap give 0.0; a pair that
touches (gap below 1e-9 m, no overlap) uses the centre-to-centre direction for r_dot.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from pitstudio.robots._check import finite, positive

__all__ = ["Agent", "footprint_gap", "time_to_collision"]

_TOUCH = 1e-9
_PERPENDICULAR = 1e-4  # |r_dot| below this fraction of |v_rel| is rounding noise, so TTC > 1e4 r / |v_rel| is +inf


@dataclass(frozen=True)
class Agent:
    x: float
    y: float
    yaw: float
    vx: float
    vy: float
    length: float
    width: float

    def __post_init__(self) -> None:
        for name in ("x", "y", "yaw", "vx", "vy"):
            finite(name, getattr(self, name))
        positive("length", self.length)
        positive("width", self.width)


def _corners(a: Agent) -> np.ndarray:
    c, s = math.cos(a.yaw), math.sin(a.yaw)
    hl, hw = 0.5 * a.length, 0.5 * a.width
    local = np.array([[hl, hw], [-hl, hw], [-hl, -hw], [hl, -hw]])
    rot = np.array([[c, -s], [s, c]])
    return local @ rot.T + np.array([a.x, a.y])


def _closest_on_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    t = float(np.dot(p - a, ab) / np.dot(ab, ab))
    return a + min(max(t, 0.0), 1.0) * ab


def _closest_points(ca: np.ndarray, cb: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    best = (math.inf, ca[0], cb[0])
    for p_set, e_set, p_first in ((ca, cb, True), (cb, ca, False)):
        for p in p_set:
            for i in range(4):
                q = _closest_on_segment(p, e_set[i], e_set[(i + 1) % 4])
                dist = float(np.hypot(*(p - q)))
                if dist < best[0]:
                    best = (dist, p, q) if p_first else (dist, q, p)
    return best


def _overlap(ca: np.ndarray, cb: np.ndarray) -> bool:
    """True when the rectangles interpenetrate by more than the touch tolerance (separating-axis test)."""
    for poly in (ca, cb):
        for i in range(4):
            edge = poly[(i + 1) % 4] - poly[i]
            axis = np.array([-edge[1], edge[0]])
            axis /= np.hypot(*axis)
            pa, pb = ca @ axis, cb @ axis
            if pa.max() <= pb.min() + _TOUCH or pb.max() <= pa.min() + _TOUCH:
                return False
    return True


def footprint_gap(a: Agent, b: Agent) -> float:
    """Distance r >= 0 between the two oriented rectangles (0 on contact or overlap)."""
    ca, cb = _corners(a), _corners(b)
    if _overlap(ca, cb):
        return 0.0
    return _closest_points(ca, cb)[0]


def time_to_collision(a: Agent, b: Agent) -> float:
    ca, cb = _corners(a), _corners(b)
    if _overlap(ca, cb):
        return 0.0
    r, pa, pb = _closest_points(ca, cb)
    if r < _TOUCH:
        direction = np.array([b.x - a.x, b.y - a.y])
        norm = float(np.hypot(*direction))
        if norm == 0.0:
            return 0.0
        n = direction / norm
        r = 0.0
    else:
        n = (pb - pa) / r
    dvx, dvy = b.vx - a.vx, b.vy - a.vy
    r_dot = float(dvx * n[0] + dvy * n[1])
    # a relative velocity numerically perpendicular to n carries only rounding noise: not closing
    if r_dot < -_PERPENDICULAR * math.hypot(dvx, dvy):
        return r / (-r_dot)
    return math.inf

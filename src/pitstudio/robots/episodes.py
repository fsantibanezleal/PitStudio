# SPDX-License-Identifier: Apache-2.0
"""IL-1 terminations, contact table, light-vehicle scenarios and the evaluation mix (FR-014-12, FR-014-14)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from pitstudio.robots._check import positive

SUCCESS_MARGIN = 2.0  # m before the route end
LATERAL_LIMIT = 5.0  # m

_LINKS = frozenset({"wheel", "chassis", "dump_body", "other"})
_OTHERS = frozenset({"light_vehicle", "terrain", "berm"})

__all__ = [
    "LATERAL_LIMIT",
    "SUCCESS_MARGIN",
    "LvPath",
    "classify_step",
    "eval_light_vehicle_counts",
    "is_collision_pair",
    "light_vehicle_scenario",
    "time_limit",
]


def time_limit(route_length: float, mean_speed_limit: float) -> float:
    """T_max = 2 L_route / v_lim_mean."""
    return 2.0 * positive("route_length", route_length) / positive("mean_speed_limit", mean_speed_limit)


def is_collision_pair(link: str, other: str) -> bool:
    if link not in _LINKS:
        raise ValueError(f"link must be one of {sorted(_LINKS)}, got {link!r}")
    if other not in _OTHERS:
        raise ValueError(f"other must be one of {sorted(_OTHERS)}, got {other!r}")
    if other == "light_vehicle":
        return True
    return link != "wheel"


def classify_step(
    *, arc_length: float, route_length: float, e_lat: float, t: float, t_max: float, collided: bool
) -> str | None:
    """None while running, else invalid_value, collision, success, lateral_error or time_limit (first that holds)."""
    positive("route_length", route_length)
    positive("t_max", t_max)
    if not (math.isfinite(arc_length) and math.isfinite(e_lat) and math.isfinite(t)):
        return "invalid_value"
    if collided:
        return "collision"
    if arc_length >= route_length - SUCCESS_MARGIN:
        return "success"
    if abs(e_lat) > LATERAL_LIMIT:
        return "lateral_error"
    if t >= t_max:
        return "time_limit"
    return None


@dataclass(frozen=True)
class LvPath:
    waypoints: np.ndarray  # (K, 2), world frame
    speed_kmh: float
    kind: str  # "crossing" | "oncoming"


def _polyline(route_xy: np.ndarray) -> np.ndarray:
    try:
        route = np.array(route_xy, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("route_xy must be a numeric (N, 2) polyline") from exc
    if route.ndim != 2 or route.shape[1] != 2 or route.shape[0] < 2:
        raise ValueError(f"route_xy must have shape (N >= 2, 2), got {route.shape}")
    if not np.all(np.isfinite(route)):
        raise ValueError("route_xy holds a non-finite entry")
    return route


def _point_at(route: np.ndarray, cum: np.ndarray, s: float) -> tuple[np.ndarray, np.ndarray]:
    """Point and unit tangent at arc length s along the route."""
    i = min(max(int(np.searchsorted(cum, s, side="right")) - 1, 0), len(route) - 2)
    seg = route[i + 1] - route[i]
    length = float(np.linalg.norm(seg))
    tangent = seg / length if length > 0.0 else np.array([1.0, 0.0])
    frac = 0.0 if length == 0.0 else (s - cum[i]) / length
    return route[i] + frac * seg, tangent


def light_vehicle_scenario(seed: int, n_light: int, route_xy: np.ndarray) -> list[LvPath]:
    """0 to 3 kinematic light vehicles whose paths meet the route; a pure function of the arguments."""
    if isinstance(n_light, bool) or not isinstance(n_light, int | np.integer) or not 0 <= n_light <= 3:
        raise ValueError(f"n_light must be an integer in 0..3, got {n_light!r}")
    route = _polyline(route_xy)
    seg_len = np.linalg.norm(np.diff(route, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg_len)])
    total = float(cum[-1])
    rng = np.random.default_rng(np.random.SeedSequence([int(seed) & 0xFFFFFFFF, 0x4C56, int(n_light)]))
    paths: list[LvPath] = []
    for _ in range(n_light):
        speed = float(rng.uniform(20.0, 40.0))
        u = float(rng.uniform(0.1, 0.9))
        point, tangent = _point_at(route, cum, u * total)
        if rng.random() < 0.5:
            normal = np.array([-tangent[1], tangent[0]])
            half = float(rng.uniform(25.0, 60.0))
            side = 1.0 if rng.random() < 0.5 else -1.0
            wp = np.array([point - side * half * normal, point + side * half * normal])
            kind = "crossing"
        else:
            span = float(rng.uniform(0.05, 0.2)) * total
            s_hi = min(u * total + span, total)
            s_lo = max(u * total - span, 0.0)
            cuts = [k for k in range(len(route)) if s_lo < cum[k] < s_hi]
            pts = [_point_at(route, cum, s_hi)[0]]
            pts += [route[k] for k in reversed(cuts)]
            pts.append(_point_at(route, cum, s_lo)[0])
            wp = np.array(pts)
            kind = "oncoming"
        paths.append(LvPath(waypoints=wp, speed_kmh=speed, kind=kind))
    return paths


def eval_light_vehicle_counts(eval_start: int, count: int = 100) -> list[int]:
    """Light-vehicle count of each evaluation seed: exactly count / 4 episodes of each of 0, 1, 2 and 3."""
    if count != 100:
        raise ValueError(f"count must be 100, got {count!r}")
    counts = np.repeat(np.arange(4), count // 4)
    rng = np.random.default_rng(np.random.SeedSequence([int(eval_start) & 0xFFFFFFFFFFFF, 0x4556]))
    rng.shuffle(counts)
    return [int(c) for c in counts]

# SPDX-License-Identifier: Apache-2.0
"""Classical baselines of the IL tasks: pure pursuit + PID (IL-1) and the scripted dig (IL-2).

FR-014-29 to FR-014-31, P-014-07. Pure pursuit follows Coulter (1992), CMU-RI-TR-92-01, eqs. 2.1-2.2: the curvature
toward a goal point is 2 x / l^2, with x the lateral offset of the goal in the vehicle frame and l the look-ahead.
"""

from __future__ import annotations

import math

import numpy as np

from pitstudio.robots._check import finite, positive

__all__ = [
    "PidSpeed",
    "PurePursuitPid",
    "curvature",
    "lookahead_distance",
    "pure_pursuit_goal",
    "steering_angle",
]


def lookahead_distance(speed: float, *, l0: float, kv: float, l_min: float, l_max: float) -> float:
    """l = clamp(l0 + kv * speed, l_min, l_max)."""
    return min(max(l0 + kv * speed, l_min), l_max)


def _path(path: np.ndarray | None) -> np.ndarray:
    try:
        arr = np.array(path, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"path must be a numeric (N >= 2, 2) array, got {type(path).__name__}") from exc
    if arr.ndim != 2 or arr.shape[1] != 2 or arr.shape[0] < 2:
        raise ValueError(f"path must have shape (N >= 2, 2), got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("path holds a non-finite coordinate")
    return arr


def pure_pursuit_goal(path: np.ndarray, lookahead: float) -> np.ndarray:
    """First point of the polyline (vehicle frame) at distance ``lookahead`` from the origin, else the path end."""
    pts = _path(path)
    end = pts[-1].copy()
    if not math.isfinite(lookahead) or lookahead <= 0.0:
        return end
    if float(np.hypot(*pts[0])) >= lookahead:
        return pts[0].copy()
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if float(np.hypot(*b)) < lookahead:
            continue
        d = b - a
        # |a + t d|^2 = lookahead^2 with |a| < lookahead <= |b|: the root t in (0, 1]
        qa = float(np.dot(d, d))
        qb = 2.0 * float(np.dot(a, d))
        qc = float(np.dot(a, a)) - lookahead * lookahead
        disc = max(qb * qb - 4.0 * qa * qc, 0.0)
        t = (-qb + math.sqrt(disc)) / (2.0 * qa)
        return a + min(max(t, 0.0), 1.0) * d
    return end


def curvature(lateral_offset: float, lookahead: float) -> float:
    """kappa = 2 x / l^2."""
    la = positive("lookahead", lookahead)
    return 2.0 * lateral_offset / (la * la)


def steering_angle(kappa: float, wheelbase: float) -> float:
    """delta = arctan(L kappa)."""
    return math.atan(positive("wheelbase", wheelbase) * kappa)


class PidSpeed:
    """Discrete PID (kd = 0) with output clamping and conditional-integration anti-windup."""

    def __init__(self, kp: float, ki: float, dt: float, out_min: float = -1.0, out_max: float = 1.0) -> None:
        self.kp = finite("kp", kp)
        self.ki = finite("ki", ki)
        self.dt = positive("dt", dt)
        self.out_min = finite("out_min", out_min)
        self.out_max = finite("out_max", out_max)
        if self.out_min >= self.out_max:
            raise ValueError(f"out_min must be < out_max, got {out_min!r} and {out_max!r}")
        self.integral = 0.0

    def reset(self) -> None:
        self.integral = 0.0

    def step(self, error: float) -> float:
        e = finite("error", error)
        previous = self.integral
        self.integral += e * self.dt
        raw = self.kp * e + self.ki * self.integral
        if (raw > self.out_max and e > 0.0) or (raw < self.out_min and e < 0.0):
            self.integral = previous  # saturated in the direction of the error: do not wind up
        return min(max(raw, self.out_min), self.out_max)


class PurePursuitPid:
    """IL-1 baseline: pure-pursuit steering and PID speed control, through the policy's action limits."""

    def __init__(
        self,
        *,
        wheelbase: float,
        l0: float,
        kv: float,
        l_min: float,
        l_max: float,
        kp: float,
        ki: float,
        dt: float,
        max_steer_rate: float,
    ) -> None:
        self.wheelbase = positive("wheelbase", wheelbase)
        self.l0, self.kv = finite("l0", l0), finite("kv", kv)
        self.l_min, self.l_max = finite("l_min", l_min), finite("l_max", l_max)
        self.dt = positive("dt", dt)
        self.max_steer_rate = positive("max_steer_rate", max_steer_rate)
        self.pid = PidSpeed(kp, ki, dt)

    def reset(self) -> None:
        self.pid.reset()

    def act(self, path: np.ndarray, speed: float, v_target: float, steer_angle: float) -> np.ndarray:
        v = finite("speed", speed)
        v_ref = finite("v_target", v_target)
        steer = finite("steer_angle", steer_angle)
        pts = _path(path)
        la = lookahead_distance(v, l0=self.l0, kv=self.kv, l_min=self.l_min, l_max=self.l_max)
        goal = pure_pursuit_goal(pts, la)
        delta_cmd = steering_angle(curvature(float(goal[1]), la), self.wheelbase)
        steer_action = (delta_cmd - steer) / (self.dt * self.max_steer_rate)
        drive_action = self.pid.step(v_ref - v)
        return np.clip(np.array([steer_action, drive_action]), -1.0, 1.0)

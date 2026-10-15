# SPDX-License-Identifier: Apache-2.0
"""Observation builders of the IL tasks (FR-014-08, FR-014-15)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from pitstudio.robots._check import finite, positive, vector
from pitstudio.robots.ttc import Agent, time_to_collision

IL2_LAYOUT: tuple[tuple[str, int], ...] = (
    ("joint_positions", 4),
    ("joint_velocities", 4),
    ("joint_torques", 4),
    ("bucket_tip_pose", 3),
    ("terrain_heights", 30),
    ("fill_estimate", 1),
)
IL2_OBS_SIZE = 46
TERRAIN_AHEAD_SPACING = 0.1  # m


def il2_observation(
    *,
    joint_pos: Sequence[float],
    joint_vel: Sequence[float],
    joint_torque: Sequence[float],
    tip_xz: Sequence[float],
    lip_pitch: float,
    terrain_x: Sequence[float],
    terrain_z: Sequence[float],
    v_fill: float,
    v_heaped: float,
) -> np.ndarray:
    """46-element float32 vector of the excavator task."""
    pos = vector("joint_pos", joint_pos, 4)
    vel = vector("joint_vel", joint_vel, 4)
    tau = vector("joint_torque", joint_torque, 4)
    tip = vector("tip_xz", tip_xz, 2)
    tx = vector("terrain_x", terrain_x, min_size=2)
    tz = vector("terrain_z", terrain_z, tx.shape[0])
    vh = positive("v_heaped", v_heaped)
    pitch = vector("lip_pitch", [lip_pitch], 1)[0]
    fill = vector("v_fill", [v_fill], 1)[0]
    heights = np.interp(tip[0] + TERRAIN_AHEAD_SPACING * (np.arange(30) + 1), tx, tz)
    return np.concatenate([pos, vel, tau, [tip[0], tip[1], pitch], heights, [fill / vh]]).astype(np.float32)


# ----------------------------------------------------------------------------------------------------------- IL-1
IL1_LAYOUT: tuple[tuple[str, int], ...] = (
    ("speed_yaw_rate_pitch", 3),
    ("lateral_heading_error", 2),
    ("path_points", 20),
    ("payload_fraction", 1),
    ("ray_ranges", 32),
    ("lv_relative_position", 2),
    ("lv_relative_velocity", 2),
    ("lv_ttc", 1),
)
IL1_OBS_SIZE = 63
RAY_ANGLES: np.ndarray = np.linspace(-math.pi / 2.0, math.pi / 2.0, 32)
RAY_MAX_RANGE = 60.0  # m
PATH_SPACING = 5.0  # m of arc length
N_PATH_POINTS = 10
TTC_CLIP = 30.0  # s


@dataclass(frozen=True)
class LightVehicle(Agent):
    """A kinematic light vehicle in the world frame (SI units)."""


def _route(route_xy: np.ndarray) -> np.ndarray:
    try:
        route = np.array(route_xy, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("route_xy must be a numeric (N >= 2, 2) polyline") from exc
    if route.ndim != 2 or route.shape[1] != 2 or route.shape[0] < 2:
        raise ValueError(f"route_xy must have shape (N >= 2, 2), got {route.shape}")
    if not np.all(np.isfinite(route)):
        raise ValueError("route_xy holds a non-finite entry")
    if np.any(np.hypot(*np.diff(route, axis=0).T) == 0.0):
        raise ValueError("route_xy has two equal consecutive points")
    return route


def _obstacles(obstacles: np.ndarray | None) -> np.ndarray:
    if obstacles is None:
        return np.zeros((0, 2, 2))
    try:
        arr = np.array(obstacles, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("obstacles must be a numeric (M, 2, 2) array") from exc
    if arr.ndim != 3 or arr.shape[1:] != (2, 2):
        raise ValueError(f"obstacles must have shape (M, 2, 2), got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("obstacles holds a non-finite entry")
    return arr


def _wrap_pi(angle: float) -> float:
    """Wrap to (-pi, pi]."""
    w = (angle + math.pi) % (2.0 * math.pi) - math.pi
    return math.pi if w == -math.pi else w


def _project(route: np.ndarray, p: np.ndarray) -> tuple[float, float, float, np.ndarray]:
    """(arc length s0 of the projection, signed lateral offset (left +), route heading there, cumulative lengths)."""
    seg = np.diff(route, axis=0)
    length = np.hypot(seg[:, 0], seg[:, 1])
    cum = np.concatenate([[0.0], np.cumsum(length)])
    rel = p - route[:-1]
    t = np.clip(np.einsum("ij,ij->i", rel, seg) / (length * length), 0.0, 1.0)
    proj = route[:-1] + t[:, None] * seg
    dist = np.hypot(*(p - proj).T)
    i = int(np.argmin(dist))
    d = seg[i] / length[i]
    offset = float(d[0] * (p[1] - proj[i, 1]) - d[1] * (p[0] - proj[i, 0]))
    return float(cum[i] + t[i] * length[i]), offset, math.atan2(seg[i, 1], seg[i, 0]), cum


def _route_point(route: np.ndarray, cum: np.ndarray, s: float) -> np.ndarray:
    s = min(max(s, 0.0), float(cum[-1]))
    i = min(int(np.searchsorted(cum, s, side="right")) - 1, len(route) - 2)
    i = max(i, 0)
    seg = route[i + 1] - route[i]
    return route[i] + (s - cum[i]) / (cum[i + 1] - cum[i]) * seg


def _ray_ranges(origin: np.ndarray, yaw: float, segments: np.ndarray) -> np.ndarray:
    """Distance from origin along each ray to the nearest segment (RAY_MAX_RANGE when none is hit)."""
    out = np.full(RAY_ANGLES.shape[0], RAY_MAX_RANGE)
    if segments.shape[0] == 0:
        return out
    ang = yaw + RAY_ANGLES
    d = np.stack([np.cos(ang), np.sin(ang)], axis=1)  # (R, 2)
    a = segments[:, 0, :]
    e = segments[:, 1, :] - a  # (S, 2)
    ao = a - origin  # (S, 2)
    den = d[:, None, 0] * e[None, :, 1] - d[:, None, 1] * e[None, :, 0]  # (R, S)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (ao[None, :, 0] * e[None, :, 1] - ao[None, :, 1] * e[None, :, 0]) / den
        u = (ao[None, :, 0] * d[:, None, 1] - ao[None, :, 1] * d[:, None, 0]) / den
    hit = (np.abs(den) > 1e-12) & (t > 1e-9) & (u >= 0.0) & (u <= 1.0)
    t = np.where(hit, t, np.inf)
    return np.minimum(t.min(axis=1), RAY_MAX_RANGE)


def _rect_edges(v: Agent) -> np.ndarray:
    c, s = math.cos(v.yaw), math.sin(v.yaw)
    hl, hw = 0.5 * v.length, 0.5 * v.width
    corners = np.array([[hl, hw], [-hl, hw], [-hl, -hw], [hl, -hw]]) @ np.array([[c, -s], [s, c]]).T + np.array(
        [v.x, v.y]
    )
    return np.stack([corners, np.roll(corners, -1, axis=0)], axis=1)  # (4, 2, 2)


def il1_observation(
    *,
    x: float,
    y: float,
    yaw: float,
    speed: float,
    yaw_rate: float,
    pitch: float,
    payload_fraction: float,
    route_xy: np.ndarray,
    truck_size: Sequence[float],
    obstacles: np.ndarray | None = None,
    light_vehicles: Sequence[LightVehicle] = (),
) -> np.ndarray:
    """63-element body-frame float32 observation of the haul truck (FR-014-08)."""
    px, py, psi = finite("x", x), finite("y", y), finite("yaw", yaw)
    v, wz = finite("speed", speed), finite("yaw_rate", yaw_rate)
    pit, pay = finite("pitch", pitch), finite("payload_fraction", payload_fraction)
    route = _route(route_xy)
    walls = _obstacles(obstacles)
    size = vector("truck_size", truck_size, 2)
    if np.any(size <= 0.0):
        raise ValueError("truck_size must hold positive sides")
    pos = np.array([px, py])
    c, s = math.cos(psi), math.sin(psi)
    to_body = np.array([[c, s], [-s, c]])  # world -> body (rotation by -yaw)

    s0, e_lat, heading, cum = _project(route, pos)
    e_psi = _wrap_pi(heading - psi)
    pts = np.array([_route_point(route, cum, s0 + PATH_SPACING * k) for k in range(1, N_PATH_POINTS + 1)])
    path_body = (pts - pos) @ to_body.T

    lvs = list(light_vehicles)
    segments = [walls, *(_rect_edges(lv) for lv in lvs)]
    rays = _ray_ranges(pos, psi, np.concatenate(segments, axis=0))

    if lvs:
        near = min(lvs, key=lambda lv: math.hypot(lv.x - px, lv.y - py))
        rel_pos = to_body @ np.array([near.x - px, near.y - py])
        rel_vel = to_body @ np.array([near.vx - v * c, near.vy - v * s])
        truck = Agent(px, py, psi, v * c, v * s, float(size[0]), float(size[1]))
        ttc = min(max(time_to_collision(truck, near), 0.0), TTC_CLIP)
    else:
        rel_pos, rel_vel, ttc = np.zeros(2), np.zeros(2), TTC_CLIP

    return np.concatenate(
        [[v, wz, pit], [e_lat, e_psi], path_body.ravel(), [pay], rays, rel_pos, rel_vel, [ttc]]
    ).astype(np.float32)

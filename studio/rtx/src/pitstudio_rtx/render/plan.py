# SPDX-License-Identifier: Apache-2.0
"""The deterministic pose plan: still viewpoints, then the flyover spline sampled at constant speed.

A pose is a pure function of the recipe: no clock, no random number. The flyover is a uniform Catmull-Rom spline
through the control points (eye and look-at target share one parameter), re-parameterised by the arc length of the eye
path so the camera moves at constant speed and consecutive frames have no jump and no kink.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from pitstudio_rtx.render.recipe import Recipe

Vec3 = tuple[float, float, float]
SAMPLES_PER_SEGMENT = 400  # polyline resolution of the arc-length table
WORLD_UP: Vec3 = (0.0, 0.0, 1.0)


@dataclass(frozen=True)
class Pose:
    """One image to render: where the camera is, what it looks at, the sun, and how many renderer steps it needs."""

    kind: str  # "still" or "flyover"
    id: str
    index: int
    out: str  # path of the PNG relative to the output folder
    eye: Vec3
    target: Vec3
    up: Vec3
    focal_length_mm: float
    sun_azimuth_deg: float
    sun_elevation_deg: float
    steps: int


def _unit(v: np.ndarray, what: str) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-9:
        raise ValueError(what)
    return v / n


def camera_matrix(eye: Vec3, target: Vec3, up: Vec3) -> np.ndarray:
    """World-from-camera 4 x 4 (column vectors) of a USD camera: it looks down its -Z, +Y is up, +X right."""
    forward = _unit(
        np.asarray(target, dtype=np.float64) - np.asarray(eye, dtype=np.float64), "eye and target are the same point"
    )
    right_raw = np.cross(forward, np.asarray(up, dtype=np.float64))
    if np.linalg.norm(right_raw) < 1e-6:
        raise ValueError(
            "the view direction is parallel to the up vector: give an explicit up for a straight-down view"
        )
    right = right_raw / np.linalg.norm(right_raw)
    true_up = np.cross(right, forward)
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = right, true_up, -forward, eye
    return m


def sun_matrix(azimuth_deg: float, elevation_deg: float) -> np.ndarray:
    """World-from-light 4 x 4 of a distant light: it shines along its -Z, away from the sun.

    The azimuth is the compass bearing of the sun clockwise from north (+Y); the elevation is above the horizon.
    """
    a, e = math.radians(azimuth_deg), math.radians(elevation_deg)
    toward_sun = np.array([math.cos(e) * math.sin(a), math.cos(e) * math.cos(a), math.sin(e)])
    x = np.cross(np.array(WORLD_UP), toward_sun)
    x = np.array([1.0, 0.0, 0.0]) if np.linalg.norm(x) < 1e-6 else x / np.linalg.norm(x)
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2] = x, np.cross(toward_sun, x), toward_sun
    return m


def _segment(padded: np.ndarray, seg: int, t: np.ndarray | float) -> np.ndarray:
    """Point(s) at local parameter `t` of segment `seg` of the Catmull-Rom spline (`padded` repeats the ends)."""
    p0, p1, p2, p3 = padded[seg], padded[seg + 1], padded[seg + 2], padded[seg + 3]
    return 0.5 * (
        (2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t**2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t**3
    )


def _pad(points: np.ndarray) -> np.ndarray:
    return np.vstack([points[0], points, points[-1]])


def _dense(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Dense samples of the spline and their global parameter in [0, n-1]."""
    padded = _pad(points)
    t = np.linspace(0.0, 1.0, SAMPLES_PER_SEGMENT, endpoint=False)[:, None]
    chunks = [_segment(padded, i, t) for i in range(len(points) - 1)]
    params = [i + t[:, 0] for i in range(len(points) - 1)]
    chunks.append(points[-1][None, :])
    params.append(np.array([len(points) - 1.0]))
    return np.vstack(chunks), np.concatenate(params)


def _spline(recipe: Recipe, count: int) -> list[tuple[Vec3, Vec3]]:
    """`count` (eye, target) pairs along the flyover at constant eye speed, ends on the end control points."""
    points = recipe.data["flyover"]["control_points"]
    eyes = np.array([p["eye"] for p in points], dtype=np.float64)
    targets = np.array([p["target"] for p in points], dtype=np.float64)
    dense_eye, dense_u = _dense(eyes)
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(dense_eye, axis=0), axis=1))])
    u = np.interp(np.linspace(0.0, arc[-1], count), arc, dense_u)
    padded_eyes, padded_targets = _pad(eyes), _pad(targets)
    pairs: list[tuple[Vec3, Vec3]] = []
    for ui in u:
        seg = min(int(ui), len(points) - 2)
        eye, target = _segment(padded_eyes, seg, ui - seg), _segment(padded_targets, seg, ui - seg)
        pairs.append(
            ((float(eye[0]), float(eye[1]), float(eye[2])), (float(target[0]), float(target[1]), float(target[2])))
        )
    return pairs


def plan(recipe: Recipe) -> list[Pose]:
    """The stills in recipe order, then the flyover frames; every pose carries its renderer step count."""
    data = recipe.data
    sun, steps = data["sun"], data["steps"]
    camera = data["camera"]
    poses: list[Pose] = []
    for i, still in enumerate(data["stills"]):
        override = still.get("sun", {})
        poses.append(
            Pose(
                kind="still",
                id=still["id"],
                index=i,
                out=f"stills/{still['id']}.png",
                eye=tuple(float(v) for v in still["eye"]),
                target=tuple(float(v) for v in still["target"]),
                up=tuple(float(v) for v in still.get("up", WORLD_UP)),
                focal_length_mm=float(still.get("focal_length_mm", camera["focal_length_mm"])),
                sun_azimuth_deg=float(override.get("azimuth_deg", sun["azimuth_deg"])),
                sun_elevation_deg=float(override.get("elevation_deg", sun["elevation_deg"])),
                steps=steps["still"] + (steps["warmup"] if i == 0 else 0),
            )
        )
    fly = data["flyover"]
    count = int(fly.get("frame_override") or round(fly["duration_s"] * fly["fps"]))
    for i, (eye, target) in enumerate(_spline(recipe, count)):
        poses.append(
            Pose(
                kind="flyover",
                id=f"frame_{i:05d}",
                index=i,
                out=f"flyover/frame_{i:05d}.png",
                eye=eye,
                target=target,
                up=WORLD_UP,
                focal_length_mm=float(camera["focal_length_mm"]),
                sun_azimuth_deg=float(sun["azimuth_deg"]),
                sun_elevation_deg=float(sun["elevation_deg"]),
                steps=steps["still"] if i == 0 else steps["frame"],
            )
        )
    return poses

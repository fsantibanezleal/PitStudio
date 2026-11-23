"""The gate of the carved SDG frames (sdg-geometry-2026-11-22): `exposure_qa` thresholds, annotated share and geometry.

Pure NumPy, no Isaac Sim. The exposure thresholds are those of `exposure_qa.evaluate_gate` (flat frames, clipped frames,
rgb std quantiles, haze-limited frames listed apart); the annotated share rises to 85 percent because the table now
constructs visibility (FR-009-54); two geometry checks are added:

- no frame has a median finite depth below `MIN_MEDIAN_DEPTH_M` (the table's `VIEW_NEAR_M`); a frame with no
  finite depth counts as too near, it shows no ground;
- at least `AGREEMENT_SHARE` of the objects the table marks visible have at least `MIN_INSTANCE_PX` visible
  pixels in the render (renderer and table agree on what is seen); an object that another object occludes in the
  render (`occluded_by_object`: a nearer object's pixels lie inside its projected box) is not counted, because the
  table's line of sight to it is clear by construction only up to the other objects (FR-009-55).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from pitstudio_isaac.sdg import exposure_qa
from pitstudio_isaac.sdg.scene_render import MIN_INSTANCE_PX

ANNOTATED_SHARE = 0.85
MIN_MEDIAN_DEPTH_M = 10.0
AGREEMENT_SHARE = 0.90


def _hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Convex hull (monotone chain) of 2-D points, counter-clockwise."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _corners(placement: Mapping[str, Any], dims: Mapping[str, Any]) -> np.ndarray:
    yaw = math.radians(float(placement["yaw_deg"]))
    along = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    across = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
    base = np.array([placement["x_m"], placement["y_m"], placement["z_m"]], dtype=np.float64)
    return np.array(
        [
            base
            + sx * float(dims["length_m"]) / 2.0 * along
            + sy * float(dims["width_m"]) / 2.0 * across
            + np.array([0.0, 0.0, sz * float(dims["height_m"])])
            for sx in (-1, 1)
            for sy in (-1, 1)
            for sz in (0, 1)
        ]
    )


def _project(camera: Mapping[str, Any], points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    eye = np.asarray(camera["position_m"], dtype=np.float64)
    forward = np.asarray(camera["forward"], dtype=np.float64)
    forward = forward / np.linalg.norm(forward)
    right = np.cross(forward, np.asarray(camera.get("up", (0.0, 0.0, 1.0)), dtype=np.float64))
    right = right / np.linalg.norm(right)
    up = np.cross(right, forward)
    rel = points - eye
    depth = rel @ forward
    safe = np.maximum(depth, 0.1)
    u = float(camera["cx_px"]) + float(camera["fx_px"]) * (rel @ right) / safe
    v = float(camera["cy_px"]) - float(camera["fy_px"]) * (rel @ up) / safe
    return u, v, depth


def projected_hull(
    camera: Mapping[str, Any], placement: Mapping[str, Any], dims: Mapping[str, Any]
) -> list[tuple[float, float]]:
    """The convex hull, in pixels, of the eight corners of an object's box (corners behind the camera clamp at 0.1 m)."""
    u, v, _ = _project(camera, _corners(placement, dims))
    return _hull([(float(a), float(b)) for a, b in zip(u, v, strict=True)])


def occluded_by_object(
    row: Mapping[str, Any], ids: np.ndarray, depth: np.ndarray, id_to_path: Mapping[int, str]
) -> dict[str, bool]:
    """For each object of the row: True when a pixel of another object lies inside its projected box and is nearer.

    The projected box is the hull of the eight corners of the object's box; "nearer" is a depth below the nearest
    distance along the optical axis of those corners. Terrain and farther objects never occlude.
    """
    from PIL import Image, ImageDraw

    height, width = ids.shape
    camera = row["camera"]
    prims = {o["prim_id"] for o in row["objects"]}
    out: dict[str, bool] = {}
    for obj, placement in zip(row["objects"], row["dr"]["placements"], strict=True):
        hull = projected_hull(camera, placement, obj)
        _, _, corner_depth = _project(camera, _corners(placement, obj))
        near = float(corner_depth.min())
        others = [i for i, path in id_to_path.items() if path in prims and path != obj["prim_id"]]
        if len(hull) < 3 or not others:
            out[obj["prim_id"]] = False
            continue
        canvas = Image.new("L", (width, height), 0)
        ImageDraw.Draw(canvas).polygon(hull, fill=1)
        inside = np.asarray(canvas, dtype=bool)
        hit = inside & np.isin(ids, others) & (np.asarray(depth) < near)
        out[obj["prim_id"]] = bool(hit.any())
    return out


def evaluate_gate(frames: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Every threshold of the gate on frame measures (`exposure_qa.evaluate_gate` keys plus `median_depth_m`,
    `objects`)."""
    base = exposure_qa.evaluate_gate(frames)
    thresholds = dict(base["thresholds"])
    n = len(frames)
    annotated = sum(1 for f in frames if int(f["annotations"]) > 0)
    thresholds["annotated"] = {
        "value": annotated / n,
        "limit": ANNOTATED_SHARE,
        "passed": annotated / n >= ANNOTATED_SHARE,
    }
    near = sum(
        1 for f in frames if math.isnan(float(f["median_depth_m"])) or float(f["median_depth_m"]) < MIN_MEDIAN_DEPTH_M
    )
    thresholds["near_median_depth"] = {"value": near, "limit": 0, "passed": near == 0}
    seen = [o for f in frames for o in f["objects"] if o["table_visible"] and not o.get("occluded_by_object", False)]
    agree = sum(1 for o in seen if int(o["visible_px"]) >= MIN_INSTANCE_PX)
    share = agree / len(seen) if seen else 1.0
    thresholds["table_render_agreement"] = {
        "value": share,
        "limit": AGREEMENT_SHARE,
        "objects": len(seen),
        "passed": share >= AGREEMENT_SHARE,
    }
    return {"frames": n, "thresholds": thresholds, "passed": all(t["passed"] for t in thresholds.values())}

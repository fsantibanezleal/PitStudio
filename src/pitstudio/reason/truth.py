"""Exact ground truth of the six task-A question types (FR-015-17 to FR-015-22) from a validated frame state.

Conventions (specs/015-vlm/data-model.md): transforms and footprints are already in metres, so `metersPerUnit` is never
applied again; `footprint.centre_m` is the horizontal position (x, y for a Z-up stage, x, z for a Y-up stage), the
heading is counter-clockwise from the first horizontal axis towards the second, `half_extents_m` is (along, across).

Every function returns a label or None; None means "not asked": the frame lies in a pre-registered ambiguity band or
cannot be decided from pixels, so no query is built from it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

PERSON_PX = 100  # a person counts as visible from this many pixels (FR-015-17)
TRUCK_PX = 400  # a haul truck counts as visible from this many pixels (FR-015-17, FR-015-19)
BENCH_EDGE_PX = 2000  # a bench edge is "in view" from this many pixels (FR-015-18)
NEAR_BAND_M = (27.0, 33.0)  # type 1: distances inside this closed band are not asked
NEAR_M = 30.0  # type 1: the hazard distance
TAU_YES = -math.log(0.725)  # type 4: median one-way optical depth of the onset of visibility reduction (T1 = 0.725)
TAU_NO = -math.log(0.90)  # type 4: below this the air is clear (T1 = 0.90)
GRID = (16, 9)  # type 4: columns, rows of the camera-ray grid
BLIND_EXCLUSION_M = 1.0  # type 5: a light vehicle this close to the polygon boundary is not asked
LIGHT_VEHICLE_RADIUS_M = 50.0  # type 5: light vehicles within this distance of the truck must all be visible
GRADE_HALF_SPAN_M = 5.0  # type 6: the grade is taken over +-5 m along the heading
GRADE_BAND = (0.09, 0.11)  # type 6: grades inside this closed band are not asked
_RAY_STEPS_PER_CELL = 4


def _of_class(frame: Mapping[str, Any], cls: str) -> list[Mapping[str, Any]]:
    return [o for o in frame["objects"] if o["class"] == cls]


def rect_distance(obj: Mapping[str, Any], point: Sequence[float]) -> float:
    """Distance from a horizontal point to the nearest point of an object's oriented footprint rectangle."""
    fp = obj["footprint"]
    h = math.radians(fp["heading_deg"])
    dx, dy = point[0] - fp["centre_m"][0], point[1] - fp["centre_m"][1]
    bx = math.cos(h) * dx + math.sin(h) * dy
    by = -math.sin(h) * dx + math.cos(h) * dy
    ex = max(abs(bx) - fp["half_extents_m"][0], 0.0)
    ey = max(abs(by) - fp["half_extents_m"][1], 0.0)
    return math.hypot(ex, ey)


def truth_type1(frame: Mapping[str, Any]) -> str | None:
    """Is a person within 30 m of a haul truck? (FR-015-17)"""
    persons = _of_class(frame, "person")
    trucks = _of_class(frame, "haul_truck")
    if any(p["in_frustum"] and p["visible_px"] < PERSON_PX for p in persons):
        return None
    if any(t["in_frustum"] and t["visible_px"] < TRUCK_PX for t in trucks):
        return None
    seen_persons = [p for p in persons if p["visible_px"] >= PERSON_PX]
    seen_trucks = [t for t in trucks if t["visible_px"] >= TRUCK_PX]
    dists = [rect_distance(t, p["footprint"]["centre_m"]) for p in seen_persons for t in seen_trucks]
    if any(NEAR_BAND_M[0] <= d <= NEAR_BAND_M[1] for d in dists):
        return None
    return "yes" if any(d < NEAR_BAND_M[0] for d in dists) else "no"


def truth_type2(frame: Mapping[str, Any]) -> str | None:
    """Is a berm present along the bench edge in view? (FR-015-18)

    Several edges in view that disagree on the berm flag leave the question ambiguous: not asked.
    """
    flags = {e["berm_present"] for e in frame["bench_edges"] if e["visible_px"] >= BENCH_EDGE_PX}
    if len(flags) != 1:
        return None
    return "yes" if flags.pop() else "no"


def truth_type3(frame: Mapping[str, Any]) -> str | None:
    """How many haul trucks are visible? (FR-015-19) Label "3+" stands for three or more."""
    px = [t["visible_px"] for t in _of_class(frame, "haul_truck")]
    if any(PERSON_PX <= v < TRUCK_PX for v in px):
        return None
    return ["0", "1", "2", "3+"][min(sum(1 for v in px if v >= TRUCK_PX), 3)]


# ----------------------------------------------------------------------------------------------------- type 4: dust
def _quat_to_matrix(q: Sequence[float]) -> np.ndarray:
    x, y, z, w = (float(v) for v in q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def grid_rays(frame: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The 16 x 9 pixel-centre rays of a uniform partition of the image: (u, v, unit world directions), row by row.

    Camera convention (OpenGL / USD): the camera looks along its -Z axis, +Y is up, +X is right; the direction of pixel
    (u, v) is R [(u - cx) / fx, -(v - cy) / fy, -1] normalised.
    """
    img, cam = frame["image"], frame["camera"]
    k = cam["intrinsics"]
    rot = _quat_to_matrix(cam["pose"]["rotation_xyzw"])
    cols, rows = GRID
    u = (np.arange(cols) + 0.5) * img["width_px"] / cols
    v = (np.arange(rows) + 0.5) * img["height_px"] / rows
    uu, vv = np.meshgrid(u, v)
    d_cam = np.stack([(uu - k["cx_px"]) / k["fx_px"], -(vv - k["cy_px"]) / k["fy_px"], -np.ones_like(uu)], axis=-1)
    d_world = d_cam.reshape(-1, 3) @ rot.T
    d_world /= np.linalg.norm(d_world, axis=1, keepdims=True)
    return uu.ravel(), vv.ravel(), d_world


def _box_interval(origin: np.ndarray, d: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> tuple[float, float]:
    """Slab method: the interval [t_in, t_out] of the ray origin + t d inside the box (empty: t_out <= t_in)."""
    t_in, t_out = -np.inf, np.inf
    for a in range(3):
        if d[a] == 0.0:
            if not lo[a] <= origin[a] <= hi[a]:
                return 0.0, 0.0
            continue
        t0, t1 = (lo[a] - origin[a]) / d[a], (hi[a] - origin[a]) / d[a]
        t_in, t_out = max(t_in, min(t0, t1)), min(t_out, max(t0, t1))
    return t_in, t_out


def optical_depth(origin: np.ndarray, d: np.ndarray, range_m: float, dust: Mapping[str, Any]) -> float:
    """One-way optical depth tau = integral of the extinction along a ray to `range_m` (inf: to the dust-box exit).

    The extinction field is piecewise constant per cubic cell (`origin_m` lower corner, `spacing_m`,
    `sigma_per_m[ix, iy, iz]`); the integral is a midpoint rule with at most a quarter cell per step, exact for a
    uniform field.
    """
    sigma = np.asarray(dust["sigma_per_m"], dtype=float)
    spacing = float(dust["spacing_m"])
    lo = np.asarray(dust["origin_m"], dtype=float)
    hi = lo + spacing * np.asarray(sigma.shape, dtype=float)
    t_in, t_out = _box_interval(origin, d, lo, hi)
    t0, t1 = max(t_in, 0.0), min(t_out, range_m)
    if not t1 > t0:
        return 0.0
    n = max(1, math.ceil((t1 - t0) / (spacing / _RAY_STEPS_PER_CELL)))
    step = (t1 - t0) / n
    t = t0 + (np.arange(n) + 0.5) * step
    idx = np.floor((origin[None, :] + t[:, None] * d[None, :] - lo) / spacing).astype(int)
    idx = np.clip(idx, 0, np.asarray(sigma.shape) - 1)
    return float(sigma[idx[:, 0], idx[:, 1], idx[:, 2]].sum() * step)


def truth_type4(frame: Mapping[str, Any], *, depth_m: np.ndarray, dust: Mapping[str, Any] | None) -> str | None:
    """Is visibility reduced by dust? (FR-015-20) `depth_m`: ray distance (inf for sky), `dust`: extinction box.

    Without a dust field a non-dust frame has no extinction (answer "no"); a dust frame without one cannot be decided.
    """
    depth = np.asarray(depth_m, dtype=float)
    img = frame["image"]
    if depth.shape != (img["height_px"], img["width_px"]):
        raise ValueError(f"depth_m has shape {depth.shape}, the frame image is {img['height_px']} x {img['width_px']}")
    u, v, dirs = grid_rays(frame)
    r = depth[np.minimum(v.astype(int), depth.shape[0] - 1), np.minimum(u.astype(int), depth.shape[1] - 1)]
    if np.isnan(r).any() or (r <= 0).any():
        raise ValueError("depth_m must be positive; use inf for sky rays")
    if dust is None:
        if frame["condition"] == "dust":
            return None
        taus = np.zeros(len(r))
    else:
        sigma = np.asarray(dust["sigma_per_m"], dtype=float)
        if sigma.ndim != 3 or not np.isfinite(sigma).all() or (sigma < 0).any():
            raise ValueError("dust sigma_per_m must be a finite non-negative 3-D array")
        if not float(dust["spacing_m"]) > 0 or not np.isfinite(np.asarray(dust["origin_m"], dtype=float)).all():
            raise ValueError("dust origin_m must be finite and spacing_m positive")
        origin = np.asarray(frame["camera"]["pose"]["translation_m"], dtype=float)
        taus = np.array([optical_depth(origin, d, float(rr), dust) for d, rr in zip(dirs, r, strict=True)])
    tau = float(np.median(taus))
    if tau >= TAU_YES:
        return "yes"
    return "no" if tau <= TAU_NO else None


# ------------------------------------------------------------------------------------------------ type 5: blind zone
def _segment_distance(p: Sequence[float], a: Sequence[float], b: Sequence[float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _boundary_distance(p: Sequence[float], poly: Sequence[Sequence[float]]) -> float:
    return min(_segment_distance(p, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def _inside(p: Sequence[float], poly: Sequence[Sequence[float]]) -> bool:
    """Even-odd rule (ray casting)."""
    x, y = p
    c = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def _visible_trucks(frame: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [t for t in _of_class(frame, "haul_truck") if t["visible_px"] >= TRUCK_PX]


def truth_type5(frame: Mapping[str, Any], *, blind_zones: Mapping[str, Sequence[Sequence[float]]]) -> str | None:
    """Is a light vehicle in the truck's blind zone? (FR-015-21) `blind_zones` maps asset id to a body-frame polygon."""
    trucks = _visible_trucks(frame)
    if len(trucks) != 1:
        return None
    truck = trucks[0]
    poly = blind_zones.get(truck.get("asset_id", ""))
    if poly is None:
        return None
    tc = truck["footprint"]["centre_m"]
    h = math.radians(truck["footprint"]["heading_deg"])
    near = [
        o
        for o in _of_class(frame, "light_vehicle")
        if math.hypot(o["footprint"]["centre_m"][0] - tc[0], o["footprint"]["centre_m"][1] - tc[1])
        <= LIGHT_VEHICLE_RADIUS_M
    ]
    if any(o["visible_px"] < PERSON_PX for o in near):
        return None
    body = []
    for o in near:
        dx, dy = o["footprint"]["centre_m"][0] - tc[0], o["footprint"]["centre_m"][1] - tc[1]
        body.append((math.cos(h) * dx + math.sin(h) * dy, -math.sin(h) * dx + math.cos(h) * dy))
    if any(_boundary_distance(p, poly) < BLIND_EXCLUSION_M for p in body):
        return None
    return "yes" if any(_inside(p, poly) for p in body) else "no"


# ---------------------------------------------------------------------------------------------------- type 6: grade
def truth_type6(frame: Mapping[str, Any], *, terrain: Callable[[float, float], float]) -> str | None:
    """Is the truck on a ramp steeper than 10 %? (FR-015-22) `terrain(x, y)` gives the ground height in metres."""
    trucks = _visible_trucks(frame)
    if len(trucks) != 1:
        return None
    fp = trucks[0]["footprint"]
    h = math.radians(fp["heading_deg"])
    cx, cy = fp["centre_m"]
    ux, uy = math.cos(h), math.sin(h)
    ahead = float(terrain(cx + GRADE_HALF_SPAN_M * ux, cy + GRADE_HALF_SPAN_M * uy))
    behind = float(terrain(cx - GRADE_HALF_SPAN_M * ux, cy - GRADE_HALF_SPAN_M * uy))
    if not (math.isfinite(ahead) and math.isfinite(behind)):
        raise ValueError("terrain returned a non-finite height")
    grade = abs(ahead - behind) / (2 * GRADE_HALF_SPAN_M)
    if grade < GRADE_BAND[0]:
        return "no"
    return "yes" if grade > GRADE_BAND[1] else None

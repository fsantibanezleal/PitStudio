# ruff: noqa: E501
"""Shared fixtures and independent oracles of the spec 015 acceptance tests (VLM reasoning lane).

This module holds no test. It is imported by `tests/unit/test_t_015_*.py`, `tests/metamorphic/test_t_015_*.py`,
`tests/contract/test_t_015_*.py` and `tests/pipeline/test_t_015_*.py` (which put `tests/unit` on `sys.path`) and is locked
with the first of them. It uses only the standard library and numpy; none of it calls the code under test.

What it provides:
- hand-built frame states (`frame_state`, `truck`, `person`, `light_vehicle`) that follow
  `specs/015-vlm/contracts/frame-state.schema.json`, with the camera convention of the valid example
  (OpenGL / USD camera: it looks along its -Z axis, +Y is up, +X is right; the example quaternion
  (0.5, -0.5, -0.5, 0.5) looks along world +X with world +Z up) and the footprint convention stated in `obj`;
- exact rigid motions of a whole frame (`move_frame`) used by the invariance relations of P-015-08;
- the canonical digest of a frame state (`canonical_sha256`);
- reference statistics written out from their definitions with exact rational arithmetic where the quantity is rational:
  balanced accuracy, macro-F1, Wilson interval, exact McNemar, AUROC by pair counting, Cohen's kappa, the t quantile.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Sequence
from fractions import Fraction
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SPEC015 = ROOT / "specs" / "015-vlm"
Z975 = 1.959963984540054  # standard normal 0.975 quantile (Abramowitz and Stegun 26.2.23 to 15 digits; scipy.stats.norm.ppf(0.975))
HEX64 = "0123456789abcdef" * 4
IMAGE_BYTES = b"\x89PNG\r\n\x1a\n pitstudio 015 fixture image"
IMAGE_SHA256 = hashlib.sha256(IMAGE_BYTES).hexdigest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(doc: Any) -> str:
    """SHA-256 of the canonical JSON text of a document: sorted keys, no spaces, UTF-8 without ASCII escapes."""
    return sha256_hex(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def write_frame_files(root: Path) -> None:
    """Write the one fixture image every kit frame points at (`img/frame.png`, digest `IMAGE_SHA256`)."""
    (root / "img").mkdir(parents=True, exist_ok=True)
    (root / "img" / "frame.png").write_bytes(IMAGE_BYTES)


# ------------------------------------------------------------------------------------------------ rotations
def quat_mul(a: Sequence[float], b: Sequence[float]) -> list[float]:
    """Hamilton product a*b of two (x, y, z, w) quaternions."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    ]


def quat_yaw(deg: float, up: str = "Z") -> list[float]:
    """Rotation by `deg` degrees (counter-clockwise seen from the up axis) about the up axis, as (x, y, z, w)."""
    h = math.radians(deg) / 2
    s, c = math.sin(h), math.cos(h)
    return [0.0, 0.0, s, c] if up == "Z" else [0.0, s, 0.0, c]


def quat_to_matrix(q: Sequence[float]) -> np.ndarray:
    x, y, z, w = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def matrix_to_quat(m: np.ndarray) -> list[float]:
    """Rotation matrix to a unit (x, y, z, w) quaternion (Shepperd's method)."""
    t = float(np.trace(m))
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    n = math.sqrt(sum(float(v) ** 2 for v in q))
    sign = -1.0 if q[3] < 0 else 1.0
    return [sign * float(v) / n for v in q]


# camera frame (X right, Y up, -Z forward) to world frame (X east, Y north, Z up) when the camera looks along world +X
_R0 = np.array([[0.0, 0.0, -1.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])


def camera(
    position: Sequence[float] = (0.0, 0.0, 12.0),
    heading_deg: float = 0.0,
    pitch_down_deg: float = 0.0,
    fx: float = 1108.5,
    fy: float | None = None,
    cx: float = 640.0,
    cy: float = 360.0,
) -> dict:
    """A camera document `{"intrinsics": ..., "pose": ...}` (Z up): looks along `heading_deg` (counter-clockwise from +X),
    tilted down by `pitch_down_deg`. R = Rz(heading) * R0 * Rx(-pitch), with R0 the matrix of the valid example."""
    a = -math.radians(pitch_down_deg)
    rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    h = math.radians(heading_deg)
    rz = np.array([[math.cos(h), -math.sin(h), 0], [math.sin(h), math.cos(h), 0], [0, 0, 1]])
    rot = rz @ _R0 @ rx
    return {
        "intrinsics": {"fx_px": fx, "fy_px": fx if fy is None else fy, "cx_px": cx, "cy_px": cy},
        "pose": {"translation_m": [float(v) for v in position], "rotation_xyzw": matrix_to_quat(rot)},
    }


def project(cam: dict, point: Sequence[float]) -> tuple[float, float, float]:
    """Pinhole projection of a world point: (u, v, depth). OpenGL camera: u = cx + fx*Xc/depth, v = cy - fy*Yc/depth with
    depth = -Zc and Xc = R^T (P - t). Independent of the code under test."""
    r = quat_to_matrix(cam["pose"]["rotation_xyzw"])
    xc = r.T @ (np.asarray(point, dtype=float) - np.asarray(cam["pose"]["translation_m"], dtype=float))
    k = cam["intrinsics"]
    depth = -float(xc[2])
    return k["cx_px"] + k["fx_px"] * float(xc[0]) / depth, k["cy_px"] - k["fy_px"] * float(xc[1]) / depth, depth


# ------------------------------------------------------------------------------------------------ frame states
_COUNTER = {"n": 0}


def obj(
    cls: str,
    cx: float,
    cy: float,
    *,
    visible_px: int,
    half: tuple[float, float] = (1.0, 1.0),
    heading_deg: float = 0.0,
    in_frustum: bool | None = None,
    height_m: float = 0.0,
    up: str = "Z",
    prim_id: str | None = None,
) -> dict:
    """One object. Footprint convention used by the tests (the contract does not state it, see the report): `centre_m` is
    the horizontal position (x, y for Z up; x, z for Y up), `heading_deg` is counter-clockwise from the first horizontal
    axis towards the second, `half_extents_m` = (half length along the heading, half width across it)."""
    _COUNTER["n"] += 1
    translation = [cx, cy, height_m] if up == "Z" else [cx, height_m, cy]
    name = "".join(w.capitalize() for w in cls.split("_"))
    return {
        "prim_id": prim_id or f"/World/{name}_{_COUNTER['n']:05d}",
        "class": cls,
        "asset_id": cls.replace("_", "-") + "-asset",
        "pose": {"translation_m": translation, "rotation_xyzw": quat_yaw(heading_deg, up)},
        "footprint": {"centre_m": [cx, cy], "half_extents_m": [half[0], half[1]], "heading_deg": heading_deg},
        "visible_px": visible_px,
        "in_frustum": (visible_px > 0) if in_frustum is None else in_frustum,
    }


def truck(cx: float, cy: float, *, visible_px: int = 18000, heading_deg: float = 0.0, **kw: Any) -> dict:
    return obj("haul_truck", cx, cy, visible_px=visible_px, half=(7.5, 4.6), heading_deg=heading_deg, **kw)


def person(cx: float, cy: float, *, visible_px: int = 640, **kw: Any) -> dict:
    return obj("person", cx, cy, visible_px=visible_px, half=(0.3, 0.3), **kw)


def light_vehicle(cx: float, cy: float, *, visible_px: int = 900, heading_deg: float = 0.0, **kw: Any) -> dict:
    return obj("light_vehicle", cx, cy, visible_px=visible_px, half=(2.6, 1.0), heading_deg=heading_deg, **kw)


def frame_state(
    objects: Sequence[dict],
    *,
    frame_id: str = "b2-pit-s0001-f0001",
    condition: str = "day",
    location: str = "haul_road",
    meters_per_unit: float = 1.0,
    up_axis: str = "Z",
    bench_edges: Sequence[dict] | None = None,
    width: int = 1280,
    height: int = 720,
    cam: dict | None = None,
    dust: bool = False,
) -> dict:
    """A valid frame state (schema 015-vlm frame-state, version 1.0). Every frame points at the same fixture image."""
    return {
        "schema_version": "1.0",
        "frame_id": frame_id,
        "run_id": "20261012T013000Z-b2",
        "synthetic": True,
        "case": "B2",
        "location": location,
        "condition": condition,
        "metersPerUnit": meters_per_unit,
        "upAxis": up_axis,
        "image": {"path": "img/frame.png", "sha256": IMAGE_SHA256, "width_px": width, "height_px": height},
        "depth": {"path": "img/depth.npy", "sha256": HEX64},
        "dust_field": {"path": "img/dust.npz", "sha256": HEX64} if dust else None,
        "terrain": {"path": "img/terrain.tif", "sha256": HEX64},
        "camera": cam or camera(),
        "objects": [dict(o) for o in objects],
        "bench_edges": list(bench_edges or []),
    }


def bench_edge(edge_id: str = "bench-07-crest", *, berm: bool = True, visible_px: int = 5000) -> dict:
    return {"edge_id": edge_id, "berm_present": berm, "visible_px": visible_px}


def move_frame(frame: dict, theta_deg: float, dx: float, dy: float) -> dict:
    """Rigid motion of scene and camera together (Z up): rotate by theta about the vertical axis, then translate (dx, dy).
    Headings and quaternions are updated; visible pixel counts do not change."""
    th = math.radians(theta_deg)
    c, s = math.cos(th), math.sin(th)
    qy = quat_yaw(theta_deg)

    def xy(p: Sequence[float]) -> list[float]:
        return [c * p[0] - s * p[1] + dx, s * p[0] + c * p[1] + dy]

    def wrap(h: float) -> float:
        h = (h + 180.0) % 360.0 - 180.0
        return 180.0 if h == -180.0 else h

    out = json.loads(json.dumps(frame))
    for o in out["objects"]:
        t = o["pose"]["translation_m"]
        o["pose"]["translation_m"] = [*xy(t), t[2]]
        o["pose"]["rotation_xyzw"] = quat_mul(qy, o["pose"]["rotation_xyzw"])
        o["footprint"]["centre_m"] = xy(o["footprint"]["centre_m"])
        o["footprint"]["heading_deg"] = wrap(o["footprint"]["heading_deg"] + theta_deg)
    t = out["camera"]["pose"]["translation_m"]
    out["camera"]["pose"]["translation_m"] = [*xy(t), t[2]]
    out["camera"]["pose"]["rotation_xyzw"] = quat_mul(qy, out["camera"]["pose"]["rotation_xyzw"])
    return out


def body_to_world(centre: Sequence[float], heading_deg: float, p_body: Sequence[float]) -> list[float]:
    """Point given in a truck's body frame (x forward along the heading, y to the left) to horizontal world coordinates."""
    h = math.radians(heading_deg)
    return [
        centre[0] + p_body[0] * math.cos(h) - p_body[1] * math.sin(h),
        centre[1] + p_body[0] * math.sin(h) + p_body[1] * math.cos(h),
    ]


# ------------------------------------------------------------------------------------------------ statistics oracles
def balanced_accuracy(truth: Sequence[Any], pred: Sequence[Any], labels: Sequence[Any] | None = None) -> Fraction:
    """Mean per-class recall over the classes present in `truth` (or in `labels`), as an exact fraction."""
    labs = list(labels) if labels is not None else sorted(set(truth), key=str)
    rec = []
    for lab in labs:
        idx = [i for i, t in enumerate(truth) if t == lab]
        if idx:
            rec.append(Fraction(sum(1 for i in idx if pred[i] == lab), len(idx)))
    return sum(rec, Fraction(0)) / len(rec)


def macro_f1(truth: Sequence[Any], pred: Sequence[Any], labels: Sequence[Any]) -> float:
    """Macro-averaged F1 (classes with no true and no predicted instance contribute 0), from the F1 = 2TP/(2TP+FP+FN) form."""
    f = []
    for lab in labels:
        tp = sum(1 for t, p in zip(truth, pred, strict=True) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(truth, pred, strict=True) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(truth, pred, strict=True) if t == lab and p != lab)
        f.append(0.0 if 2 * tp + fp + fn == 0 else 2 * tp / (2 * tp + fp + fn))
    return sum(f) / len(f)


def wilson(k: int, n: int, z: float = Z975) -> tuple[float, float]:
    """Wilson score interval (Wilson 1927): (p + z^2/2n -/+ z sqrt(p(1-p)/n + z^2/4n^2)) / (1 + z^2/n)."""
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def mcnemar_exact_p(b: int, c: int) -> float:
    """Two-sided exact binomial McNemar p value: min(1, 2 * P(X <= min(b, c))), X ~ Binomial(b + c, 1/2), in exact fractions."""
    n = b + c
    if n == 0:
        return 1.0
    m = min(b, c)
    tail = Fraction(sum(math.comb(n, i) for i in range(m + 1)), 2**n)
    return float(min(Fraction(1), 2 * tail))


def mcnemar_chi2_cc(b: int, c: int) -> float:
    """Continuity-corrected McNemar statistic (|b - c| - 1)^2 / (b + c)."""
    return (abs(b - c) - 1) ** 2 / (b + c)


def auroc_pairs(scores: Sequence[float], positive: Sequence[bool]) -> float:
    """AUROC by counting pairs (Mann-Whitney): P(s_pos > s_neg) + 0.5 P(s_pos = s_neg), exact over all pos/neg pairs."""
    pos = [s for s, p in zip(scores, positive, strict=True) if p]
    neg = [s for s, p in zip(scores, positive, strict=True) if not p]
    wins = sum((1 if a > b else Fraction(1, 2) if a == b else 0) for a, b in product(pos, neg))
    return float(Fraction(wins) / (len(pos) * len(neg)))


def cohen_kappa(a: Sequence[Any], b: Sequence[Any]) -> float:
    """Cohen's kappa (Cohen 1960): (po - pe) / (1 - pe) with pe from the two marginal distributions."""
    n = len(a)
    labs = sorted(set(a) | set(b), key=str)
    po = Fraction(sum(1 for x, y in zip(a, b, strict=True) if x == y), n)
    pe = sum(Fraction(sum(1 for x in a if x == lab), n) * Fraction(sum(1 for y in b if y == lab), n) for lab in labs)
    return float((po - pe) / (1 - pe))


def stable_choice(key: str, options: Sequence[Any]) -> Any:
    """Deterministic pseudo-random pick from a key (independent of the code under test)."""
    return options[int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(options)]


def fake_truth_fn(unaskable_every: int = 10) -> Callable[[dict, int], str | None]:
    """A deterministic stand-in for the ground truth of a frame (used where the selection logic, not the truth, is tested):
    about 1 frame in `unaskable_every` per type is not askable; binary truths are a hash of (frame_id, type); type 3 takes
    one of 0, 1, 2, 3+."""

    def fn(frame: dict, qtype: int) -> str | None:
        key = f"{frame['frame_id']}|{qtype}"
        if int(hashlib.sha256((key + "|ask").encode()).hexdigest(), 16) % unaskable_every == 0:
            return None
        return stable_choice(key, ["0", "1", "2", "3+"] if qtype == 3 else ["yes", "no"])

    return fn

"""Web point-cloud shards: 16-bit quantisation over the shard's bounding box, planar little-endian payload (FR-013-35).

A shard holds at most 1,250,000 points of 8 bytes (x, y, z as uint16, intensity and class as uint8): at most 10 MB.
A coordinate is stored as `round((v - offset) / scale)` with `offset` the per-axis minimum and `scale = extent / 65535`
(1 for an axis of zero extent), so the dequantised value is within half a step of the original.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from pitstudio.sensors.beamhash import beam_hash_array

MAX_POINTS = 1_250_000
BYTES_PER_POINT = 8
MAX_BYTES = MAX_POINTS * BYTES_PER_POINT
RELPATH = re.compile(
    r"^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$"
)
QUANTITIES = ("lidar-intensity", "radar-rcs-dbsm", "radar-radial-velocity-m-per-s")
LIDAR_INTENSITY = ("lidar-intensity", 0.0, 1.0)


@dataclass
class WebShard:
    """A DC-013-04 header and its binary payload."""

    header: dict[str, Any]
    payload: bytes


def _as_float(array: Any, name: str, shape: tuple[int, ...] | None = None) -> np.ndarray:
    try:
        out = np.asarray(array, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} is not numeric") from error
    if shape is not None and out.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {out.shape}")
    if not np.all(np.isfinite(out)):
        raise ValueError(f"{name} holds a non-finite value")
    return out


def encode_web_shard(
    positions: Any,
    intensity: Any,
    classes: Any,
    *,
    source: Mapping[str, Any],
    class_labels: Mapping[int, str],
    payload_path: str,
    intensity_map: Sequence[Any] = LIDAR_INTENSITY,
) -> WebShard:
    """Quantise one cloud into a shard; `ValueError` names a hostile input and no shard is produced (FR-013-42)."""
    pos = np.asarray(positions)
    if pos.ndim != 2 or pos.shape[1] != 3:
        raise ValueError(f"positions must have shape (n, 3), got {pos.shape}")
    n = len(pos)
    if n > MAX_POINTS:
        raise ValueError(f"positions: {n} points exceed the {MAX_POINTS} points of one shard")
    pos = _as_float(pos, "positions")
    inten = _as_float(intensity, "intensity")
    cls = np.asarray(classes)
    if inten.shape != (n,):
        raise ValueError(f"intensity must have {n} values, got shape {inten.shape}")
    if cls.shape != (n,):
        raise ValueError(f"classes must have {n} values, got shape {cls.shape}")
    quantity, low, high = intensity_map
    if quantity not in QUANTITIES or not (np.isfinite(low) and np.isfinite(high) and high > low):
        raise ValueError(f"intensity_map must name a quantity and satisfy low < high, got {tuple(intensity_map)!r}")
    if not isinstance(payload_path, str) or not RELPATH.match(payload_path):
        raise ValueError(f"payload path {payload_path!r} is not a relative path of safe characters")
    unknown = sorted({int(c) for c in np.unique(cls)} - {int(k) for k in class_labels})
    if unknown:
        raise ValueError(f"class code(s) {unknown} are not in class_labels")
    if n:
        lo, hi = pos.min(axis=0), pos.max(axis=0)
    else:
        lo = hi = np.zeros(3)
    extent = hi - lo
    scale = np.where(extent > 0.0, extent / 65535.0, 1.0)
    codes = np.clip(np.rint((pos - lo) / scale), 0, 65535).astype("<u2")
    i_code = np.clip(np.rint(np.clip((inten - low) / (high - low), 0.0, 1.0) * 255.0), 0, 255).astype(np.uint8)
    payload = b"".join(
        [
            codes[:, 0].tobytes(),
            codes[:, 1].tobytes(),
            codes[:, 2].tobytes(),
            i_code.tobytes(),
            cls.astype(np.uint8).tobytes(),
        ]
    )
    header: dict[str, Any] = {
        "schema_version": "1.0",
        "source": dict(source),
        "points": n,
        "quantisation": {"offset_m": [float(v) for v in lo], "scale_m": [float(v) for v in scale]},
        "encoding": {
            "position": "uint16",
            "intensity": "uint8",
            "class": "uint8",
            "byte_order": "little",
            "layout": "planar",
        },
        "intensity_map": {"quantity": quantity, "low": float(low), "high": float(high)},
        "classes": {str(int(k)): v for k, v in sorted(class_labels.items())},
        "payload": {"path": payload_path, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()},
    }
    return WebShard(header, payload)


def shard_cloud(
    positions: Any,
    intensity: Any,
    classes: Any,
    *,
    source: Mapping[str, Any],
    class_labels: Mapping[int, str],
    payload_prefix: str,
    intensity_map: Sequence[Any] = LIDAR_INTENSITY,
    max_bytes: int = 10_000_000,
) -> list[WebShard]:
    """Split a cloud into consecutive shards of at most `max_bytes` each, every one over its own bounding box."""
    pos = np.asarray(positions)
    per_shard = min(MAX_POINTS, max_bytes // BYTES_PER_POINT)
    n = len(pos)
    inten, cls = np.asarray(intensity), np.asarray(classes)
    shards = []
    for index, start in enumerate(range(0, max(n, 1), per_shard)):
        sel = slice(start, start + per_shard)
        shards.append(
            encode_web_shard(
                pos[sel],
                inten[sel],
                cls[sel],
                source=source,
                class_labels=class_labels,
                payload_path=f"{payload_prefix}-{index:04d}.bin",
                intensity_map=intensity_map,
            )
        )
    return shards


SLIDER_LEVELS = 41
SLIDER_MAX_RETURNS = 150_000
SLIDER_TAU_FLOOR = -math.log(0.02)  # T1 = 0.02 on the reference target
SLIDER_RULE = {"tau_on": 0.3216, "tau_floor_retro": 3.912, "tau_floor_diffuse": 2.8134}
SLIDER_MATERIALS = {"retro": 0, "diffuse": 1, "dust": 2}
SLIDER_ENCODING = {
    "position": "uint16",
    "intensity": "uint8",
    "class": "uint8",
    "tau_unit": "float32",
    "r_edge_m": "float32",
    "hash": "uint32",
    "byte_order": "little",
    "layout": "planar",
}


def bake_slider(
    positions: Any,
    intensity_code: Any,
    class_codes: Any,
    tau_unit: Any,
    r_edge: Any,
    beam: Any,
    *,
    frame: int,
    seed: int,
    tau_ref: float,
    source: Mapping[str, Any],
    payload_path: str,
    dust_return_intensity: float,
    k_first: float = 0.01,
) -> WebShard:
    """Bake one clean S1 frame for the web dust slider (DC-013-05, FR-013-38).

    The payload is planar little-endian, 20 bytes per return: x, y, z uint16 over the frame's bounding box, the clean
    intensity code, the class code (retro 0, diffuse 1), `tau_unit` and `r_edge_m` float32 and the beam hash uint32.
    The 41 multipliers are `k[0] = 0` and levels 1 to 40 log-spaced from `k_first` to `-ln(0.02) / tau_ref`.
    """
    pos = _as_float(positions, "positions")
    if pos.ndim != 2 or pos.shape[1] != 3 or not 1 <= len(pos) <= SLIDER_MAX_RETURNS:
        raise ValueError(f"positions must have shape (n, 3) with 1 <= n <= {SLIDER_MAX_RETURNS}, got {pos.shape}")
    n = len(pos)
    tau = _as_float(tau_unit, "tau_unit", (n,))
    edge = _as_float(r_edge, "r_edge", (n,))
    if np.any(tau < 0.0) or np.any(edge < 0.0):
        raise ValueError("tau_unit and r_edge must be non-negative")
    codes = np.asarray(intensity_code)
    classes = np.asarray(class_codes)
    beams = np.asarray(beam)
    if not (codes.shape == classes.shape == beams.shape == (n,)):
        raise ValueError("intensity_code, class_codes and beam must hold one value per return")
    if not all(math.isfinite(v) and v > 0 for v in (tau_ref, k_first)) or not 0.0 <= dust_return_intensity <= 1.0:
        raise ValueError("tau_ref and k_first must be positive and finite, dust_return_intensity in [0, 1]")
    k_last = SLIDER_TAU_FLOOR / tau_ref
    if k_first >= k_last:
        raise ValueError(f"k_first {k_first} must be below the last level {k_last}")
    offset = pos.min(axis=0)
    extent = pos.max(axis=0) - offset
    scale = np.where(extent > 0.0, extent / 65535.0, 1.0)
    q = np.rint((pos - offset) / scale).astype(np.uint16)
    payload = b"".join(
        [
            q[:, 0].astype("<u2").tobytes(),
            q[:, 1].astype("<u2").tobytes(),
            q[:, 2].astype("<u2").tobytes(),
            codes.astype(np.uint8).tobytes(),
            classes.astype(np.uint8).tobytes(),
            tau.astype("<f4").tobytes(),
            edge.astype("<f4").tobytes(),
            beam_hash_array(frame, beams, seed).astype("<u4").tobytes(),
        ]
    )
    k = [0.0, *np.geomspace(k_first, k_last, SLIDER_LEVELS - 1).tolist()]
    header = {
        "schema_version": "1.0",
        "source": dict(source),
        "returns": n,
        "levels": SLIDER_LEVELS,
        "k": k,
        "tau_ref": float(tau_ref),
        "rule": dict(SLIDER_RULE),
        "dust_return_intensity": float(dust_return_intensity),
        "material_codes": dict(SLIDER_MATERIALS),
        "label": "own Beer–Lambert dust model",  # noqa: RUF001 (the contract literal holds an en dash)
        "quantisation": {"offset_m": offset.tolist(), "scale_m": scale.tolist()},
        "encoding": dict(SLIDER_ENCODING),
        "payload": {"path": payload_path, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()},
    }
    return WebShard(header=header, payload=payload)

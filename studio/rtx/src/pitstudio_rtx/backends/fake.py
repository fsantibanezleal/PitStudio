# SPDX-License-Identifier: Apache-2.0
"""Scripted test backend (FR-013-01): no renderer, deterministic frames, call counters.

`script(sensor, step_index)` returns the output dict of one sensor for the `step_index`-th `step` call of the backend
(0-based, counted over all sessions, warm-up included). Without a script it returns clean frames that satisfy the
output contract (FR-013-09). It is also the only backend that may run contract fixtures (FR-013-43).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np

from pitstudio_rtx.backend import BackendInfo

_CAMERA_VARS = {
    "HdrColor": "hdr",
    "DistanceToCameraSD": "distance",
    "DistanceToImagePlaneSD": "distance",
    "SemanticSegmentation": "semantic",
    "LdrColor": "ldr",
}


def clean_lidar(n: int = 300, n_valid: int = 240, seed: int = 0, *, beams_emitted: int | None = None) -> dict[str, Any]:
    """One clean lidar frame: `n` slots, the first `n_valid` flagged valid (0x40)."""
    rng = np.random.default_rng(seed)
    r = rng.uniform(5.0, 80.0, n).astype(np.float32)
    az, el = rng.uniform(-math.pi, math.pi, n), rng.uniform(-0.3, 0.3, n)
    flags = np.zeros(n, dtype=np.uint8)
    flags[:n_valid] = 0x40
    return {
        "kind": "lidar",
        "beams_emitted": n if beams_emitted is None else beams_emitted,
        "valid_count": int(n_valid),
        "x": (r * np.cos(el) * np.cos(az)).astype(np.float32),
        "y": (r * np.cos(el) * np.sin(az)).astype(np.float32),
        "z": (r * np.sin(el)).astype(np.float32),
        "range_m": r,
        "intensity": rng.uniform(0.0, 1.0, n).astype(np.float32),
        "flags": flags,
        "material_class": (rng.uniform(size=n) < 0.2).astype(np.uint8),
        "object_id": rng.integers(0, 6, n).astype(np.uint32),
        "beam": np.arange(n, dtype=np.uint32),
        "echo": np.zeros(n, dtype=np.uint8),
    }


def clean_radar(n: int = 40, seed: int = 0) -> dict[str, Any]:
    """One clean radar frame of `n` detections (native sign: positive = approaching)."""
    rng = np.random.default_rng(seed)
    return {
        "kind": "radar",
        "x": rng.uniform(15, 80, n).astype(np.float32),
        "y": rng.uniform(-3, 3, n).astype(np.float32),
        "z": rng.uniform(0, 2, n).astype(np.float32),
        "rcs_dbsm": rng.uniform(-10, 20, n).astype(np.float32),
        "radial_velocity_native": rng.uniform(-15, 15, n).astype(np.float32),
        "native_sign": "approaching-positive",
        "object_id": rng.integers(0, 4, n).astype(np.uint32),
    }


def clean_camera(sensor: Mapping[str, Any], seed: int = 0) -> dict[str, Any]:
    """One clean camera frame at the sensor's resolution, holding the render products the sensor asks for."""
    rng = np.random.default_rng(seed)
    w, h = int(sensor.get("width_px", 64)), int(sensor.get("height_px", 48))
    wanted = {_CAMERA_VARS[o] for o in sensor.get("outputs", _CAMERA_VARS) if o in _CAMERA_VARS}
    out: dict[str, Any] = {"kind": "camera"}
    if "hdr" in wanted:
        out["hdr"] = rng.uniform(0, 4, (h, w, 3)).astype(np.float16)
    if "distance" in wanted:
        out["distance"] = rng.uniform(5, 100, (h, w)).astype(np.float32)
    if "semantic" in wanted:
        out["semantic"] = rng.integers(1, 4, (h, w)).astype(np.uint32)
    if "ldr" in wanted:
        out["ldr"] = rng.integers(0, 256, (h, w, 3)).astype(np.uint8)
    return out


class FakeBackend:
    """A scripted backend; see the module docstring."""

    def __init__(
        self,
        script: Callable[[dict[str, Any], int], dict[str, Any]] | None = None,
        *,
        versions: Mapping[str, str] | None = None,
        warmup_frames: int = 0,
        name: str = "fake",
    ) -> None:
        self.script = script
        self.versions = dict(versions or {})
        self.warmup_frames = int(warmup_frames)
        self.name = name
        self.open_calls = self.step_calls = self.close_calls = 0

    def describe(self) -> BackendInfo:
        return BackendInfo(
            name=self.name,
            versions=dict(self.versions),
            capabilities={"warmup_frames": self.warmup_frames, "kinds": ["lidar", "camera", "radar"]},
        )

    def open(self, stage: str | None, sensors: list[dict[str, Any]]) -> dict[str, Any]:
        self.open_calls += 1
        return {"stage": stage, "sensors": [dict(s) for s in sensors]}

    def step(self, session: dict[str, Any], pose: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        index = self.step_calls
        self.step_calls += 1
        out: dict[str, dict[str, Any]] = {}
        for sensor in session["sensors"]:
            out[sensor["id"]] = self.script(sensor, index) if self.script else self._clean(sensor, index)
        return out

    def close(self, session: dict[str, Any]) -> None:
        self.close_calls += 1

    @staticmethod
    def _clean(sensor: dict[str, Any], index: int) -> dict[str, Any]:
        kind = sensor.get("kind", "lidar")
        if kind == "camera":
            return clean_camera(sensor, index)
        if kind == "radar":
            return clean_radar(seed=index)
        frame = clean_lidar(seed=index)
        if "rain_rate_mm_h" in sensor:
            frame["applied_rain_rate_mm_h"] = sensor["rain_rate_mm_h"]
        return frame

# SPDX-License-Identifier: Apache-2.0
"""Thin `ovrtx` adapter of the sensor backend protocol (FR-013-01, NFR-013-04): at most 400 lines of code.

This is the only module of the lane that imports the renderer, and it does so inside `open`, after the isolation
check of `pitstudio_rtx.backend` has passed. Everything that is a guard (recipe, envelope, warm-up, point count,
output validation) lives in `lane.py`; this adapter only authors the sensor layer, steps the renderer and copies
render variables into the arrays of the output contract.

UNVERIFIED against a live renderer (no GPU in the implementing session): the renderer API calls used here
(`Renderer`, `open_usd_from_string`, `step`, `render_vars`, `map`) are the ones the capability probe
`studio/bench/probe_ovrtx.py` exercised, but the sensor schema attribute names and the lidar and radar render-variable
names below follow the vendor documentation cited in `docs/methods/m23-rtx-sensor-simulation.md` and must be
checked at the first GPU run (`pytest -m gpu`). A wrong name fails loudly (`KeyError` naming the variable).
The vendor lidar USD profiles are not used: sensors are authored from the recipe's datasheet-style parameters.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any

import numpy as np

from pitstudio_rtx.backend import BackendInfo, check_runtime_isolation
from pitstudio_rtx.lane import mount_matrix

DT = 1.0 / 60.0
WARMUP_FRAMES = 40  # frames the lane renders and discards after `open` (FR-013-07)
#: render variable of each output field per sensor kind (UNVERIFIED names, see the module docstring)
LIDAR_VARS = {
    "x": "x",
    "y": "y",
    "z": "z",
    "range_m": "distance",
    "intensity": "intensity",
    "flags": "flags",
    "material_class": "materialId",
    "object_id": "objectId",
    "beam": "beamId",
    "echo": "echoId",
}
RADAR_VARS = {
    "x": "x",
    "y": "y",
    "z": "z",
    "rcs_dbsm": "rcs",
    "radial_velocity_native": "radialVelocity",
    "object_id": "objectId",
}
CAMERA_VARS = {
    "HdrColor": ("hdr", np.float16),
    "LdrColor": ("ldr", np.uint8),
    "DistanceToCameraSD": ("distance", np.float32),
    "DistanceToImagePlaneSD": ("distance", np.float32),
    "SemanticSegmentation": ("semantic", np.uint32),
}
_RETRO_MATERIAL = 7  # id of the retroreflective non-visual material in the renderer's table (UNVERIFIED)


def _vec(values: Any) -> str:
    return "(" + ", ".join(repr(float(v)) for v in values) + ")"


def _xform(sensor: Mapping[str, Any], pose: Mapping[str, Any]) -> str:
    """`xformOp:transform` of a sensor: the platform pose times the mount (USD rows, so transposed)."""
    world = np.asarray(pose["world_from_platform"], dtype=np.float64).reshape(4, 4) @ mount_matrix(sensor)
    rows = ", ".join(_vec(world.T[i]) for i in range(4))
    return f'matrix4d xformOp:transform = ( {rows} )\n        uniform token[] xformOpOrder = ["xformOp:transform"]'


class _Session:
    def __init__(self, renderer: Any, scene: str, sensors: list[dict[str, Any]]) -> None:
        self.renderer, self.scene, self.sensors = renderer, scene, sensors
        self.products = {s["id"]: f"/Render/Products/{s['id'].replace('-', '_')}" for s in sensors}


class OvrtxBackend:
    """The `ovrtx` sensor backend: one Kit-less renderer per session, S1 to S4a (rain is Isaac-only, FR-013-30)."""

    def __init__(self, **options: Any) -> None:
        unknown = sorted(options)
        if unknown:
            raise TypeError(f"unexpected options: {', '.join(unknown)}")

    def describe(self) -> BackendInfo:
        versions: dict[str, str] = {}
        try:
            from importlib import metadata

            for dist in ("ovrtx", "ovstage"):
                versions[dist] = metadata.version(dist)
        except Exception:  # the distribution is absent: the lane then refuses on the envelope version check
            pass
        return BackendInfo(
            name="ovrtx", versions=versions, capabilities={"warmup_frames": WARMUP_FRAMES, "rain": False}
        )

    def open(self, stage: str | None, sensors: list[dict[str, Any]]) -> _Session:
        if stage is None:
            raise ValueError("the ovrtx backend needs a USD scene among the stage inputs")
        check_runtime_isolation("ovrtx")
        ovrtx = importlib.import_module("ovrtx")
        renderer = ovrtx.Renderer()
        session = _Session(renderer, stage, [dict(s) for s in sensors])
        renderer.open_usd_from_string(self._layer(session, {"world_from_platform": np.eye(4).reshape(16)}))
        return session

    def step(self, session: _Session, pose: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        # The renderer API verified by the probe has no attribute write: the sensor layer is re-authored per pose.
        session.renderer.open_usd_from_string(self._layer(session, pose))
        frames = session.renderer.step(set(session.products.values()), DT)
        out: dict[str, dict[str, Any]] = {}
        for sensor in session.sensors:
            raw = self._grab(frames[session.products[sensor["id"]]])
            out[sensor["id"]] = getattr(self, f"_{sensor['kind']}")(sensor, raw)
        return out

    def close(self, session: _Session) -> None:
        session.renderer.destroy()

    # -- authoring ------------------------------------------------------------------------------------------------
    def _layer(self, session: _Session, pose: Mapping[str, Any]) -> str:
        prims = []
        for sensor in session.sensors:
            name = session.products[sensor["id"]].rsplit("/", 1)[-1]
            head = f'    def {self._schema(sensor)} "{name}"\n    {{\n'
            prims.append(head + f"        {_xform(sensor, pose)}\n{self._attrs(sensor)}    }}")
        return (
            f'#usda 1.0\n(\n    subLayers = [@{session.scene}@]\n    upAxis = "Z"\n    metersPerUnit = 1\n)\n\n'
            'def Scope "Render"\n{\n    def Scope "Products"\n    {\n' + "\n".join(prims) + "\n    }\n}\n"
        )

    @staticmethod
    def _schema(sensor: Mapping[str, Any]) -> str:
        return {"lidar": "OmniLidar", "radar": "OmniRadar", "camera": "Camera"}[sensor["kind"]]

    @staticmethod
    def _attrs(sensor: Mapping[str, Any]) -> str:
        if sensor["kind"] == "lidar":
            keys = ("range_accuracy_m", "max_returns", "min_range_m", "max_range_m")
            names = ("rangeAccuracyM", "maxReturns", "minRangeM", "maxRangeM")
        elif sensor["kind"] == "radar":
            keys = ("wavelength_m", "velocity_resolution_m_per_s", "max_range_m")
            names = ("wavelengthM", "velResMps", "maxRangeM")
        else:
            return (
                f"        float focalLength = {sensor['focal_length_m'] * 1000.0!r}\n"
                f"        float horizontalAperture = {sensor['pixel_pitch_m'] * sensor['width_px'] * 1000.0!r}\n"
            )
        return "".join(f"        float {n} = {float(sensor[k])!r}\n" for k, n in zip(keys, names, strict=True))

    # -- output copy ----------------------------------------------------------------------------------------------
    @staticmethod
    def _grab(product: Any) -> dict[str, np.ndarray]:
        raw: dict[str, np.ndarray] = {}
        for path, var in product.frames[-1].render_vars.items():
            with var.map() as mapped:
                raw[path.rsplit("/", 1)[-1]] = np.array(np.from_dlpack(mapped), copy=True)
        return raw

    @staticmethod
    def _pick(raw: Mapping[str, np.ndarray], name: str) -> np.ndarray:
        if name not in raw:
            raise KeyError(f"render variable {name!r} not returned; got {sorted(raw)}")
        return np.squeeze(raw[name])

    def _lidar(self, sensor: Mapping[str, Any], raw: Mapping[str, np.ndarray]) -> dict[str, Any]:
        arrays = {k: self._pick(raw, v) for k, v in LIDAR_VARS.items()}
        flags = arrays["flags"].astype(np.uint8)
        return {
            "kind": "lidar",
            "beams_emitted": len(flags),
            "valid_count": int(((flags & 0x40) != 0).sum()),
            **{k: arrays[k].astype(np.float32) for k in ("x", "y", "z", "range_m", "intensity")},
            "flags": flags,
            "material_class": (arrays["material_class"] == _RETRO_MATERIAL).astype(np.uint8),
            "object_id": arrays["object_id"].astype(np.uint32),
            "beam": arrays["beam"].astype(np.uint32),
            "echo": arrays["echo"].astype(np.uint8),
        }

    def _radar(self, sensor: Mapping[str, Any], raw: Mapping[str, np.ndarray]) -> dict[str, Any]:
        arrays = {k: self._pick(raw, v) for k, v in RADAR_VARS.items()}
        return {
            "kind": "radar",
            "native_sign": "approaching-negative",  # UNVERIFIED: the vendor's signed Doppler convention
            **{k: arrays[k].astype(np.float32) for k in ("x", "y", "z", "rcs_dbsm", "radial_velocity_native")},
            "object_id": arrays["object_id"].astype(np.uint32),
        }

    def _camera(self, sensor: Mapping[str, Any], raw: Mapping[str, np.ndarray]) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": "camera"}
        for product in sensor["outputs"]:
            field, dtype = CAMERA_VARS[product]
            image = self._pick(raw, product)
            out[field] = (image[..., :3] if field in ("hdr", "ldr") else image).astype(dtype)
        return out

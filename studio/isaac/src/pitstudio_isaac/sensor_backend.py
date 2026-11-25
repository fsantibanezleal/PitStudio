# SPDX-License-Identifier: Apache-2.0
"""Isaac Sim sensor backend of the rain arm (`st57_rain_lidar`, FR-013-29, FR-013-30).

Implements the four operations of `pitstudio_rtx.backend.SensorBackend` (the lane source folder `studio/rtx/src` is on
`PYTHONPATH` in the Isaac Sim environment; the module itself imports it lazily). Importing this module never loads
Isaac Sim: the runtime is imported inside `open`, after the isolation check has passed, so the module stays importable
(and the lane testable with the fake backend) on a machine without Isaac Sim.

The rain rate is applied through a Kit setting and read back after it is set. The lane compares the value the frame
reports (`applied_rain_rate_mm_h`) with the requested one and records the arm as "not run" when they differ, so a
setting that Isaac Sim ignores can never publish clear-air data as rain.

UNVERIFIED against a live Isaac Sim (no GPU in the implementing session): the setting path `RAIN_SETTING`, the lidar
annotator name and its buffer field names follow the Isaac Sim documentation cited in
`docs/methods/m23-rtx-sensor-simulation.md` and must be checked at the first GPU run. A wrong name fails loudly.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any

import numpy as np

RAIN_SETTING = "/rtx/rtxsensor/rain/rate_mm_per_h"  # UNVERIFIED setting path
LIDAR_ANNOTATOR = "RtxSensorCpuIsaacCreateRTXLidarScanBuffer"
WARMUP_FRAMES = 40  # frames the lane renders and discards after `open` and after every rain-rate change
BUFFER_FIELDS = {
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


class _Session:
    def __init__(self, app: Any, rate: float, annotators: dict[str, Any]) -> None:
        self.app, self.rate, self.annotators = app, rate, annotators


class IsaacSensorBackend:
    """Isaac Sim lidar with the Mie-scattering rain model; one headless application per session."""

    def __init__(self, **options: Any) -> None:
        unknown = sorted(options)
        if unknown:
            raise TypeError(f"unexpected options: {', '.join(unknown)}")

    def describe(self) -> Any:
        from importlib import metadata

        from pitstudio_rtx.backend import BackendInfo

        versions: dict[str, str] = {}
        for dist in ("isaacsim", "ovrtx", "ovstage"):
            try:
                versions[dist] = metadata.version(dist)
            except metadata.PackageNotFoundError:
                continue
        return BackendInfo(name="isaac", versions=versions, capabilities={"warmup_frames": WARMUP_FRAMES, "rain": True})

    def open(self, stage: str | None, sensors: list[dict[str, Any]]) -> _Session:
        from pitstudio_rtx.backend import check_runtime_isolation

        if stage is None:
            raise ValueError("the isaac backend needs a USD scene among the stage inputs")
        check_runtime_isolation("isaac")
        app = importlib.import_module("isaacsim").SimulationApp({"headless": True})
        kit = importlib.import_module("omni.kit.commands")
        usd = importlib.import_module("omni.usd")
        replicator = importlib.import_module("omni.replicator.core")
        usd.get_context().open_stage(stage)
        rate = float(sensors[0].get("rain_rate_mm_h", 0.0))
        importlib.import_module("carb").settings.get_settings().set(RAIN_SETTING, rate)
        annotators: dict[str, Any] = {}
        for sensor in sensors:
            path = f"/World/Sensors/{sensor['id'].replace('-', '_')}"
            kit.execute(
                "IsaacSensorCreateRtxLidar", path=path, config=None, translation=tuple(sensor["mount_position_m"])
            )
            product = replicator.create.render_product(path, [1, 1])
            annotator = replicator.AnnotatorRegistry.get_annotator(LIDAR_ANNOTATOR)
            annotator.attach([product])
            annotators[sensor["id"]] = annotator
        return _Session(app, rate, annotators)

    def step(self, session: _Session, pose: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        importlib.import_module("omni.kit.app").get_app().update()
        applied = importlib.import_module("carb").settings.get_settings().get(RAIN_SETTING)
        out: dict[str, dict[str, Any]] = {}
        for sensor_id, annotator in session.annotators.items():
            buffer = annotator.get_data()
            arrays = {k: np.asarray(buffer[v]) for k, v in BUFFER_FIELDS.items()}
            flags = arrays["flags"].astype(np.uint8)
            out[sensor_id] = {
                "kind": "lidar",
                "beams_emitted": len(flags),
                "valid_count": int(((flags & 0x40) != 0).sum()),
                **{k: arrays[k].astype(np.float32) for k in ("x", "y", "z", "range_m", "intensity")},
                "flags": flags,
                "material_class": (arrays["material_class"] != 0).astype(np.uint8),
                "object_id": arrays["object_id"].astype(np.uint32),
                "beam": arrays["beam"].astype(np.uint32),
                "echo": arrays["echo"].astype(np.uint8),
                "applied_rain_rate_mm_h": None if applied is None else float(applied),
            }
        return out

    def close(self, session: _Session) -> None:
        session.app.close()

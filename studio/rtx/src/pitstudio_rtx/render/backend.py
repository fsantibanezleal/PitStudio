# SPDX-License-Identifier: Apache-2.0
"""The render backend protocol and its only implementation: the Kit-less `ovrtx` renderer.

This module imports `ovrtx` and `ovstage` inside `open`, after the isolation check of `pitstudio_rtx.backend` has passed
(the same rule as `backends/ovrtx_backend.py`, the sensor adapter of spec 013, which this module does not replace).

Two camera update modes, recorded in the manifest as `camera_update`:
- `ovstage` (preferred, not deprecated): the session layer is populated once into an `ovstage.Stage` that is attached to
  the renderer; each pose is written into the stage (camera and sun matrices, focal length, light intensity) with a
  rising ordinal and the step waits for that ordinal. UNVERIFIED on a live renderer before job 41: any refusal (an
  exception from a write) switches to `reload`, and the run's distinct-still check catches a write that is accepted
  but ignored.
- `reload`: the session layer is re-authored per pose with `open_usd_from_string` (deprecated in ovrtx 0.5 but proven by
  job 40: the flyover frames moved).
The attribute-write path of ovrtx 0.4 (`Renderer.write_attribute`) is not used: it was accepted and had no effect.
"""

from __future__ import annotations

import importlib
from importlib import metadata
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from pitstudio_rtx.backend import check_runtime_isolation
from pitstudio_rtx.render.plan import Pose, camera_matrix, plan, sun_matrix
from pitstudio_rtx.render.recipe import Recipe
from pitstudio_rtx.render.usd import CAMERA, PRODUCT, SKY, SUN, session_layer

PRODUCT_PATH = PRODUCT
DT = 1.0 / 60.0
LDR_VAR = "LdrColor"
MODES = ("ovstage", "reload")


class RenderBackend(Protocol):
    """What `run` needs from a renderer: open a scene once, move to a pose, step, copy the image out, close."""

    mode: str  # "ovstage" (poses are written into the attached stage) or "reload" (the layer is re-authored per pose)

    def describe(self) -> dict[str, str]: ...

    def open(self, scene_root: str, recipe: Recipe) -> None: ...

    def set_mode(self, mode: str) -> None: ...

    def apply(self, pose: Pose, gain: float = 1.0) -> None: ...

    def step(self) -> None: ...

    def grab(self) -> np.ndarray: ...

    def close(self) -> None: ...


def _version(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "unknown"


class OvrtxRenderBackend:
    """One Kit-less renderer per run: the scene is loaded once and the camera, sun and light gain move per pose."""

    def __init__(self, module: Any = None, ovstage_module: Any = None) -> None:
        self._module, self._ovstage_module = module, ovstage_module
        self._renderer: Any = None
        self._outputs: Any = None
        self._recipe: Recipe | None = None
        self._scene_root = ""
        self._stage: Any = None
        self._paths: Any = None
        self._queries: dict[str, Any] = {}
        self._ordinal = 1
        self._focal: float | None = None
        self._sun: tuple[float, float] | None = None
        self._gain = 1.0
        self.mode = "ovstage"

    def describe(self) -> dict[str, str]:
        return {"tool": "ovrtx", "version": _version("ovrtx"), "runtime": "ovrtx", "ovstage": _version("ovstage")}

    # -- opening -------------------------------------------------------------------------------------------------
    def open(self, scene_root: str, recipe: Recipe) -> None:
        check_runtime_isolation("ovrtx")
        self._module = self._module or importlib.import_module("ovrtx")
        self._recipe, self._scene_root = recipe, Path(scene_root).as_posix()
        first = plan(recipe)[0]
        self.mode = recipe.data["camera"]["update"]
        self._reset_state()
        if self.mode == "ovstage":
            self._open_ovstage(first)
        else:
            self._renderer = self._module.Renderer()
            self._renderer.open_usd_from_string(session_layer(self._scene_root, recipe, first))

    def _reset_state(self) -> None:
        self._focal, self._sun, self._gain = None, None, 1.0

    def _open_ovstage(self, first: Pose) -> None:
        assert self._recipe is not None
        ovstage = self._ovstage_module or importlib.import_module("ovstage")
        self._ovstage_module = ovstage
        self._stage = ovstage.Stage("pitstudio-render")
        ovstage.population.open_usd_from_string(self._stage, session_layer(self._scene_root, self._recipe, first), 1)
        self._renderer = self._module.Renderer()
        self._renderer.attach_ovstage(self._stage)
        self._paths = ovstage.PathDictionary(self._stage)
        self._queries, self._ordinal = {}, 1

    def _drop_ovstage(self) -> None:
        """Release the renderer and the stage (the stage is never destroyed while attached)."""
        if self._renderer is not None:
            self._renderer.destroy()
            self._renderer = None
        if self._stage is not None:
            self._stage.destroy()
            self._stage, self._paths, self._queries = None, None, {}

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown camera update mode {mode!r}")
        if mode == "reload" and self.mode == "ovstage":
            self._drop_ovstage()
            self._renderer = self._module.Renderer()  # standalone: the next apply opens the layer
            self._reset_state()
        self.mode = mode

    # -- posing --------------------------------------------------------------------------------------------------
    def apply(self, pose: Pose, gain: float = 1.0) -> None:
        assert self._recipe is not None, "open() first"
        if self.mode == "ovstage":
            try:
                self._write_pose(pose, gain)
                return
            except Exception:  # any refusal of the ovstage path: re-author the layer per pose from now on
                self.set_mode("reload")
        self._renderer.open_usd_from_string(session_layer(self._scene_root, self._recipe, pose, gain))

    def _query(self, path: str) -> Any:
        if path not in self._queries:
            self._queries[path] = self._stage.query_from_path_list(self._paths.create_path_list_from_strings([path]))
        return self._queries[path]

    def _write(self, path: str, attribute: str, values: np.ndarray, semantic: int = 0) -> None:
        self._ordinal += 1
        self._stage.write_attribute(
            self._query(path), attribute, self._ordinal, values, is_array=False, semantic=semantic
        ).wait()

    def _write_pose(self, pose: Pose, gain: float) -> None:
        assert self._recipe is not None
        matrix = self._ovstage_module.AttributeSemantic.MATRIX
        camera = np.ascontiguousarray(camera_matrix(pose.eye, pose.target, pose.up).T)[None, :, :]
        self._write(CAMERA, "xformOp:transform", camera, matrix)
        if pose.focal_length_mm != self._focal:
            self._write(CAMERA, "focalLength", np.array([pose.focal_length_mm], dtype=np.float32))
            self._focal = pose.focal_length_mm
        if self._sun != (pose.sun_azimuth_deg, pose.sun_elevation_deg):
            light = np.ascontiguousarray(sun_matrix(pose.sun_azimuth_deg, pose.sun_elevation_deg).T)[None, :, :]
            self._write(SUN, "xformOp:transform", light, matrix)
            self._sun = (pose.sun_azimuth_deg, pose.sun_elevation_deg)
        if gain != self._gain:
            sun, sky = self._recipe.data["sun"]["intensity"], self._recipe.data["sky"]["intensity"]
            self._write(SUN, "inputs:intensity", np.array([sun * gain], dtype=np.float32))
            self._write(SKY, "inputs:intensity", np.array([sky * gain], dtype=np.float32))
            self._gain = gain
        self._stage.advance_write_floor(self._ordinal).wait()

    # -- rendering -----------------------------------------------------------------------------------------------
    def step(self) -> None:
        self._outputs = None  # release the previous step result before the next ("Leaking step result outputs")
        if self.mode == "ovstage":
            self._outputs = self._renderer.step({PRODUCT_PATH}, DT, ordinal=self._ordinal)
        else:
            self._outputs = self._renderer.step({PRODUCT_PATH}, DT)

    def grab(self) -> np.ndarray:
        """The last step's `LdrColor` copied to host memory as an 8-bit RGB image (height, width, 3)."""
        frame = self._outputs[PRODUCT_PATH].frames[-1]
        found = {path.rsplit("/", 1)[-1]: var for path, var in frame.render_vars.items()}
        if LDR_VAR not in found:
            raise RuntimeError(f"render variable {LDR_VAR!r} not returned; got {sorted(found)}")
        with found[LDR_VAR].map() as mapped:
            image = np.squeeze(np.array(np.from_dlpack(mapped), copy=True))
        self._outputs = None
        if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] not in (3, 4):
            raise RuntimeError(f"unexpected {LDR_VAR} layout: {image.dtype} {image.shape}")
        return np.ascontiguousarray(image[..., :3])

    def close(self) -> None:
        self._outputs = None
        self._drop_ovstage()


def build_backend(name: str) -> RenderBackend:
    """The render backend `name`. Only `ovrtx` exists: no test double, so the job reaches only the real renderer."""
    if name == "ovrtx":
        return OvrtxRenderBackend()
    raise ValueError(f"unknown render backend {name!r}; the only backend is 'ovrtx'")

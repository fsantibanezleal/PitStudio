# SPDX-License-Identifier: Apache-2.0
"""The render backend protocol and its only implementation: the Kit-less `ovrtx` renderer.

This module imports `ovrtx` inside `open`, after the isolation check of `pitstudio_rtx.backend` has passed (the same
rule as `backends/ovrtx_backend.py`, the sensor adapter of spec 013, which this module does not replace: that adapter
steps sensors over a pose trace, this one renders camera images of one scene).

UNVERIFIED against a live renderer in the implementing session (the GPU is reserved for the queue job): the calls
(`Renderer`, `open_usd_from_string`, `step`, `render_vars`, `map`) are the ones the probe `studio/bench/probe_ovrtx.py`
exercised; moving the camera and the sun with `write_attribute` (a deprecated but present 0.5 call) is not, so `run`
checks that the image really changes with the pose and `apply` falls back to re-authoring the layer per pose (slower,
the probe's own pattern) when a write fails or is ignored. The first GPU run reports which mode worked.
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
from pitstudio_rtx.render.usd import CAMERA, PRODUCT, SUN, session_layer

PRODUCT_PATH = PRODUCT
DT = 1.0 / 60.0
LDR_VAR = "LdrColor"


class RenderBackend(Protocol):
    """What `run` needs from a renderer: open a scene once, move to a pose, step, copy the image out, close."""

    mode: str  # "write" (attributes are written per pose) or "reload" (the layer is re-authored per pose)

    def describe(self) -> dict[str, str]: ...

    def open(self, scene_root: str, recipe: Recipe) -> None: ...

    def set_mode(self, mode: str) -> None: ...

    def apply(self, pose: Pose) -> None: ...

    def step(self) -> None: ...

    def grab(self) -> np.ndarray: ...

    def close(self) -> None: ...


def _version(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "unknown"


class OvrtxRenderBackend:
    """One Kit-less renderer per run: the scene is loaded once and the camera and sun are moved per pose."""

    def __init__(self, module: Any = None) -> None:
        self._module = module
        self._renderer: Any = None
        self._outputs: Any = None
        self._recipe: Recipe | None = None
        self._scene_root = ""
        self._focal = 0.0
        self._sun: tuple[float, float] | None = None
        self.mode = "write"

    def describe(self) -> dict[str, str]:
        return {"tool": "ovrtx", "version": _version("ovrtx"), "runtime": "ovrtx", "ovstage": _version("ovstage")}

    def open(self, scene_root: str, recipe: Recipe) -> None:
        check_runtime_isolation("ovrtx")
        module = self._module or importlib.import_module("ovrtx")
        self._module, self._recipe, self._scene_root = module, recipe, Path(scene_root).as_posix()
        first = plan(recipe)[0]
        self._renderer = module.Renderer()
        self._renderer.open_usd_from_string(session_layer(self._scene_root, recipe, first))
        self._focal, self._sun = float(recipe.data["camera"]["focal_length_mm"]), None

    def set_mode(self, mode: str) -> None:
        if mode not in {"write", "reload"}:
            raise ValueError(f"unknown camera update mode {mode!r}")
        self.mode = mode

    def apply(self, pose: Pose) -> None:
        assert self._recipe is not None, "open() first"
        if self.mode == "write":
            try:
                self._write(pose)
                return
            except (RuntimeError, TypeError, ValueError):
                self.mode = "reload"  # the write call is not usable here: re-author the layer per pose from now on
        self._renderer.open_usd_from_string(session_layer(self._scene_root, self._recipe, pose))

    def _write(self, pose: Pose) -> None:
        semantic = self._module.Semantic.XFORM_MAT4x4
        world = np.ascontiguousarray(camera_matrix(pose.eye, pose.target, pose.up).T)[None, :, :]
        self._renderer.write_attribute([CAMERA], "xformOp:transform", world, semantic=semantic)
        if pose.focal_length_mm != self._focal:
            self._renderer.write_attribute([CAMERA], "focalLength", np.array([pose.focal_length_mm], dtype=np.float32))
            self._focal = pose.focal_length_mm
        if self._sun != (pose.sun_azimuth_deg, pose.sun_elevation_deg):
            light = np.ascontiguousarray(sun_matrix(pose.sun_azimuth_deg, pose.sun_elevation_deg).T)[None, :, :]
            self._renderer.write_attribute([SUN], "xformOp:transform", light, semantic=semantic)
            self._sun = (pose.sun_azimuth_deg, pose.sun_elevation_deg)

    def step(self) -> None:
        self._outputs = None  # release the previous step result before the next ("Leaking step result outputs")
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
        if self._renderer is not None:
            self._renderer.destroy()
            self._renderer = None


def build_backend(name: str) -> RenderBackend:
    """The render backend `name`. Only `ovrtx` exists: no test double, so the job reaches only the real renderer."""
    if name == "ovrtx":
        return OvrtxRenderBackend()
    raise ValueError(f"unknown render backend {name!r}; the only backend is 'ovrtx'")

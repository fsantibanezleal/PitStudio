"""Probe (studio/isaac env): Isaac Sim 6 starts headless on the GPU, simulates rigid bodies in PhysX and renders.

Starts SimulationApp headless, builds a ground plane and a few falling cubes with pxr, plays ~2 s of simulated time
and reads the poses back, then (optionally) renders one RGB frame through Replicator. Closes the app cleanly.
Licence: NVIDIA SDK, so the metrics stay local-only.
Note: the Compatibility Checker ships only as a windowed Kit app (isaacsim.exp.compatibility_check.kit), which a
headless probe cannot drive; the probe records whether its extension is present instead of running it.
"""

from __future__ import annotations

import os
import time
from importlib import metadata
from typing import Any

from _common import run_probe, timer, tmp_dir

os.environ.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")

DT = 1.0 / 60.0
SIM_SECONDS = 2.0
N_CUBES = 5


def _version(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "unknown"


def _build_stage() -> None:
    from pxr import Gf, UsdGeom, UsdPhysics

    import isaacsim.core.experimental.utils.stage as stage_utils

    stage = stage_utils.create_new_stage()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.Xform.Define(stage, "/World")

    ground = UsdGeom.Cube.Define(stage, "/World/Ground")
    ground.CreateSizeAttr(1.0)
    ground.AddTranslateOp().Set(Gf.Vec3d(0, 0, -0.5))
    ground.AddScaleOp().Set(Gf.Vec3f(50, 50, 1))
    UsdPhysics.CollisionAPI.Apply(ground.GetPrim())

    for i in range(N_CUBES):
        cube = UsdGeom.Cube.Define(stage, f"/World/Cube_{i}")
        cube.CreateSizeAttr(0.5)
        cube.AddTranslateOp().Set(Gf.Vec3d(0.8 * i, 0.0, 2.0 + 0.6 * i))
        cube.GetDisplayColorAttr().Set([Gf.Vec3f(0.2 + 0.15 * i, 0.4, 0.9 - 0.15 * i)])
        UsdPhysics.RigidBodyAPI.Apply(cube.GetPrim())
        UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
        UsdPhysics.MassAPI.Apply(cube.GetPrim()).CreateMassAttr(1.0)

    from pxr import UsdLux

    light = UsdLux.DistantLight.Define(stage, "/World/Sun")
    light.CreateIntensityAttr(3000.0)
    dome = UsdLux.DomeLight.Define(stage, "/World/Sky")
    dome.CreateIntensityAttr(500.0)


def _render_frame(app: Any, r: dict[str, Any]) -> None:
    """Optional RGB frame via Replicator; a failure is a note, not a probe failure."""
    import numpy as np
    import omni.replicator.core as rep
    from pxr import Gf, UsdGeom

    import isaacsim.core.experimental.utils.stage as stage_utils

    stage = stage_utils.get_current_stage()
    cam = UsdGeom.Camera.Define(stage, "/World/Cam")
    xf = UsdGeom.Xformable(cam)
    xf.AddTranslateOp().Set(Gf.Vec3d(6, -6, 4))
    xf.AddRotateXYZOp().Set(Gf.Vec3f(65, 0, 45))
    rp = rep.create.render_product("/World/Cam", (512, 512))
    ann = rep.AnnotatorRegistry.get_annotator("rgb")
    ann.attach([rp])
    t0 = time.perf_counter()
    data = None
    for _ in range(12):  # the first frames of a new render product are empty while the renderer warms up
        rep.orchestrator.step(rt_subframes=4, delta_time=0.0)
        data = ann.get_data()
        if data is not None and getattr(data, "size", 0) > 0 and np.asarray(data).std() > 0:
            break
    r["metrics"]["first_render_s"] = round(time.perf_counter() - t0, 3)
    rgb = np.asarray(data)
    r["metrics"]["rgb_shape"] = list(rgb.shape)
    if rgb.size == 0 or not np.isfinite(rgb.astype(np.float32)).all() or rgb[..., :3].std() < 1.0:
        raise AssertionError("rendered frame is empty or flat")
    r["metrics"]["rgb_std"] = round(float(rgb[..., :3].std()), 2)
    t0 = time.perf_counter()
    for _ in range(5):
        rep.orchestrator.step(rt_subframes=1, delta_time=0.0)
    r["metrics"]["steady_render_ms"] = round((time.perf_counter() - t0) / 5 * 1000, 1)
    out = tmp_dir("isaacsim") / "probe_frame.ppm"
    img = np.ascontiguousarray(rgb[..., :3].astype(np.uint8))
    with open(out, "wb") as f:
        f.write(f"P6 {img.shape[1]} {img.shape[0]} 255\n".encode())
        f.write(img.tobytes())
    r["notes"].append("rendered frame written to the local scratch folder (probe_frame.ppm)")
    ann.detach()


def body(r: dict[str, Any]) -> None:
    import numpy as np

    r["versions"].update(isaacsim=_version("isaacsim"), numpy=np.__version__)
    t0 = time.perf_counter()
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True})
    r["metrics"]["startup_s"] = round(time.perf_counter() - t0, 2)
    try:
        import isaacsim.core.experimental.utils.app as app_utils
        import omni.kit.app
        import torch
        import warp as wp
        from isaacsim.core.experimental.prims import RigidPrim
        from isaacsim.core.simulation_manager import SimulationManager

        r["versions"]["kit"] = omni.kit.app.get_app().get_kit_version()
        r["versions"]["torch"] = torch.__version__
        r["versions"]["warp"] = wp.config.version

        _build_stage()
        device = "cuda:0"
        SimulationManager.setup_simulation(dt=DT, device=device)
        app_utils.play()
        cubes = RigidPrim("/World/Cube_.*")
        app.update()
        z0 = cubes.get_world_poses()[0].numpy()[:, 2].copy()

        n = int(SIM_SECONDS / DT)
        with timer(r["metrics"], "physics_120_steps_s"):
            for _ in range(n):
                app.update()
        r["metrics"]["physics_steps_per_s"] = round(n / r["metrics"]["physics_120_steps_s"], 1)
        z1 = cubes.get_world_poses()[0].numpy()[:, 2]
        r["metrics"]["bodies"] = int(z0.size)
        r["metrics"]["max_drop_m"] = round(float(np.max(z0 - z1)), 3)
        r["metrics"]["physics_device"] = device
        if not (np.isfinite(z1).all() and np.max(z0 - z1) > 0.5 and np.all(z1 > -0.1)):
            raise AssertionError(f"cubes did not fall onto the ground: z0={z0}, z1={z1}")
        app_utils.stop()

        try:
            _render_frame(app, r)
        except Exception as e:  # rendering is reported, physics is the gate
            r["notes"].append(f"RGB render failed: {type(e).__name__}: {e}")
            r["metrics"]["render"] = "fail"

        try:
            ext = app_utils.get_extension_id("isaacsim.app.compatibility_check")
            r["notes"].append(f"compatibility checker extension: {ext or 'not found'} (windowed app, not run)")
        except Exception as e:
            r["notes"].append(f"compatibility checker lookup failed: {type(e).__name__}")
    finally:
        t0 = time.perf_counter()
        app.close()
        r["metrics"]["close_s"] = round(time.perf_counter() - t0, 2)


if __name__ == "__main__":
    run_probe("isaacsim", "local-only", body)

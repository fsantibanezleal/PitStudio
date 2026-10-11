"""Probe (studio/rtx env): the Kit-less Omniverse RTX renderer (ovrtx) on the GPU, plus an ovphysx drop test.

Builds a tiny USD stage inline (ground, cubes, a sphere, a light, a camera, a render product with RGB and depth),
renders frames, checks they are non-empty and finite, and times the first and the steady-state frame.
Licence: NVIDIA SDK, so the metrics stay local-only.
"""

from __future__ import annotations

import time
from importlib import metadata
from pathlib import Path
from typing import Any

from _common import SkipProbe, run_probe, timer, tmp_dir

RES = 1024
PRODUCT = "/Render/Product"
STAGE = f"""#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    upAxis = "Z"
)

def Xform "World"
{{
    def Mesh "Ground"
    {{
        int[] faceVertexCounts = [4]
        int[] faceVertexIndices = [0, 1, 2, 3]
        point3f[] points = [(-20, -20, 0), (20, -20, 0), (20, 20, 0), (-20, 20, 0)]
        normal3f[] normals = [(0, 0, 1), (0, 0, 1), (0, 0, 1), (0, 0, 1)]
        color3f[] primvars:displayColor = [(0.45, 0.45, 0.45)]
    }}
    def Cube "CubeA"
    {{
        double size = 1
        color3f[] primvars:displayColor = [(0.9, 0.2, 0.2)]
        double3 xformOp:translate = (0, 0, 0.5)
        uniform token[] xformOpOrder = ["xformOp:translate"]
    }}
    def Cube "CubeB"
    {{
        double size = 1.5
        color3f[] primvars:displayColor = [(0.2, 0.8, 0.3)]
        double3 xformOp:translate = (2.5, 1.0, 0.75)
        uniform token[] xformOpOrder = ["xformOp:translate"]
    }}
    def Sphere "SphereA"
    {{
        double radius = 0.7
        color3f[] primvars:displayColor = [(0.2, 0.4, 0.95)]
        double3 xformOp:translate = (-2.0, 1.5, 0.7)
        uniform token[] xformOpOrder = ["xformOp:translate"]
    }}
    def DistantLight "Sun"
    {{
        float inputs:intensity = 3000
        float inputs:angle = 1.0
        double3 xformOp:rotateXYZ = (-50, 0, 35)
        uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]
    }}
    def DomeLight "Sky"
    {{
        float inputs:intensity = 600
    }}
    def Camera "Cam"
    {{
        float focalLength = 24
        float horizontalAperture = 36
        float verticalAperture = 36
        float2 clippingRange = (0.1, 200)
        matrix4d xformOp:transform = ( (0.7071068, 0.4082483, -0.5773503, 0), (-0.7071068, 0.4082483, -0.5773503, 0), (0, 0.8164966, 0.5773503, 0), (8, 8, 8, 1) )
        uniform token[] xformOpOrder = ["xformOp:transform"]
    }}
}}

def Scope "Render"
{{
    def RenderProduct "Product"
    {{
        rel camera = </World/Cam>
        int2 resolution = ({RES}, {RES})
        rel orderedVars = [</Render/Vars/LdrColor>, </Render/Vars/Depth>]
    }}
    def Scope "Vars"
    {{
        def RenderVar "LdrColor"
        {{
            uniform string sourceName = "LdrColor"
        }}
        def RenderVar "Depth"
        {{
            uniform string sourceName = "DistanceToImagePlane"
        }}
    }}
}}
"""


def _version(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "unknown"


def _grab(products: Any, np: Any) -> dict[str, Any]:
    """Copy every render variable of the last frame to host numpy arrays, keyed by the variable's own name."""
    out: dict[str, Any] = {}
    product = products[PRODUCT]
    frame = product.frames[-1]
    for path, rv in frame.render_vars.items():
        with rv.map() as mapped:  # host mapping (Device.CPU default)
            out[path.rsplit("/", 1)[-1]] = np.array(np.from_dlpack(mapped), copy=True)
    return out


def _drop_test(r: dict[str, Any]) -> None:
    """Optional: ovphysx steps the packaged boxes-on-ground sample and the cubes must fall."""
    import numpy as np
    import ovphysx
    import ovstage
    from ovphysx import PhysX
    from ovphysx.types import ObjectScope, SimObjectType

    usd = Path(ovphysx.__file__).resolve().parent / "samples" / "data" / "boxes_falling_on_groundplane.usda"
    if not usd.is_file():
        raise SkipProbe(f"ovphysx sample scene missing: {usd.name}")
    ovstage.population.register_usd_schemas([str(ovphysx.codeless_schema_root())])
    sdk = PhysX()
    stage = ovstage.Stage("pitstudio-probe-drop")
    try:
        ovstage.population.open_usd(stage, str(usd), ordinal=1, domains=ovstage.PopulationDomain.PHYSICS)
        stage.advance_write_floor(ordinal=1).wait()
        sdk.attach_ovstage(stage, read_ordinal=1)
        sdk.wait_all()
        sdk.warmup()
        sdk.wait_all()

        def heights() -> Any:
            cols = []
            with sdk.read(SimObjectType.RIGID_BODY, ["position"], scope=ObjectScope.ALL) as res:
                for g in res.groups:
                    for t in g.tensors:
                        cols.append(t.numpy()[:, 2])
            return np.concatenate(cols)

        z0 = heights()
        n = 120
        with timer(r["metrics"], "ovphysx_120_steps_s"):
            for _ in range(n):
                sdk.step(1.0 / 60.0)
                sdk.wait_all()
        z1 = heights()
        r["metrics"]["ovphysx_bodies"] = int(z0.size)
        r["metrics"]["ovphysx_drop_m"] = round(float(np.max(z0 - z1)), 3)
        if not (z0.size > 0 and np.all(np.isfinite(z1)) and np.max(z0 - z1) > 0.5):
            raise AssertionError(f"rigid bodies did not fall: z0 max {z0.max():.2f}, z1 max {z1.max():.2f}")
    finally:
        try:
            sdk.detach_ovstage()
        finally:
            stage.destroy()
            sdk.destroy()


def body(r: dict[str, Any]) -> None:
    import numpy as np
    import ovrtx
    import ovstage  # noqa: F401  (version + import check)
    import warp as wp

    r["versions"].update(
        ovrtx=_version("ovrtx"),
        ovstage=_version("ovstage"),
        ovphysx=_version("ovphysx"),
        warp=wp.config.version,
        numpy=np.__version__,
    )

    renderer = ovrtx.Renderer()
    try:
        r["versions"]["ovrtx_runtime"] = ".".join(str(x) for x in renderer.version)
        with timer(r["metrics"], "stage_load_s"):
            renderer.open_usd_from_string(STAGE)

        dt = 1.0 / 60.0
        with timer(r["metrics"], "first_frame_s"):
            products = renderer.step({PRODUCT}, dt)
            frames = _grab(products, np)
        r["metrics"]["render_vars"] = sorted(frames)

        n = 20
        t0 = time.perf_counter()
        for _ in range(n):
            products = renderer.step({PRODUCT}, dt)
            frames = _grab(products, np)
        r["metrics"]["steady_frame_ms"] = round((time.perf_counter() - t0) / n * 1000, 2)
        r["metrics"]["resolution"] = f"{RES}x{RES}"

        color = next((v for k, v in frames.items() if "color" in k.lower()), None)
        if color is None:
            raise AssertionError(f"no colour render variable in {sorted(frames)}")
        color = np.squeeze(color)
        r["metrics"]["color_shape"] = list(color.shape)
        r["metrics"]["color_dtype"] = str(color.dtype)
        c = color.astype(np.float32)
        if not np.all(np.isfinite(c)):
            raise AssertionError("colour image has NaN/Inf")
        r["metrics"]["color_mean"] = round(float(c[..., :3].mean()), 2)
        r["metrics"]["color_std"] = round(float(c[..., :3].std()), 2)
        if c[..., :3].std() < 1.0:
            raise AssertionError("colour image is flat (all-black or constant)")

        depth = next((v for k, v in frames.items() if "depth" in k.lower() or "distance" in k.lower()), None)
        if depth is None:
            r["notes"].append("no depth render variable returned")
        else:
            d = np.squeeze(depth).astype(np.float32)
            fin = d[np.isfinite(d)]
            r["metrics"]["depth_finite_fraction"] = round(float(fin.size / d.size), 4)
            if fin.size == 0:
                raise AssertionError("depth image has no finite pixel")
            r["metrics"]["depth_min_max_m"] = [round(float(fin.min()), 3), round(float(fin.max()), 3)]

        if color.ndim == 3 and color.dtype == np.uint8 and color.shape[-1] in (3, 4):
            out = tmp_dir("ovrtx") / "probe_frame.ppm"
            with open(out, "wb") as f:
                f.write(f"P6 {color.shape[1]} {color.shape[0]} 255\n".encode())
                f.write(np.ascontiguousarray(color[..., :3]).tobytes())
            r["notes"].append("rendered frame written to the local scratch folder (probe_frame.ppm)")
    finally:
        renderer.destroy()

    try:
        _drop_test(r)
    except SkipProbe as e:
        r["notes"].append(str(e))
    except Exception as e:  # the renderer is the capability under test; physics is optional
        r["notes"].append(f"ovphysx drop test failed: {type(e).__name__}: {e}")
        r["metrics"]["ovphysx"] = "fail"


if __name__ == "__main__":
    run_probe("ovrtx", "local-only", body)

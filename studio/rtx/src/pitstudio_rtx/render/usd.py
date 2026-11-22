# SPDX-License-Identifier: Apache-2.0
"""The session layer authored over the scene: camera, render product, recipe sun and sky.

The layer sublayers the scene's root layer (the same pattern as `backends/ovrtx_backend.py`) and adds, under `/Render`,
the prims the renderer needs: a camera, a render product with one `LdrColor` variable (the shape the capability probe
`studio/bench/probe_ovrtx.py` exercised), a distant light and a dome light. The scene's own sun (straight down, no sky)
is switched off by metadata so it does not add to the recipe sun. Nothing of the scene's geometry is touched.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from pitstudio_rtx.render.plan import Pose, camera_matrix, sun_matrix
from pitstudio_rtx.render.recipe import Recipe

CAMERA = "/Render/Cam"
PRODUCT = "/Render/Product"
SUN = "/Render/Sun"
SKY = "/Render/Sky"
SCENE_SUN = ("World", "Lights", "Sun")  # the scene's own distant light (spec 004 lights layer)


def _f(value: Any) -> str:
    return repr(float(value))


def matrix_rows(m: np.ndarray) -> str:
    """A USD `matrix4d` literal of a column-vector 4 x 4: USD stores the transpose (translation in the last row)."""
    rows = ", ".join("(" + ", ".join(_f(v) for v in row) + ")" for row in np.asarray(m, dtype=np.float64).T)
    return f"( {rows} )"


def _variants(recipe: Recipe) -> str:
    chosen = recipe.data["scene"].get("variants") or {}
    if not chosen:
        return ""
    body = "\n".join(f'        string {name} = "{value}"' for name, value in sorted(chosen.items()))
    return f"    variants = {{\n{body}\n    }}\n"


def session_layer(scene_root: str, recipe: Recipe, pose: Pose) -> str:
    """USDA text of the session layer for `pose` over the scene root layer `scene_root`."""
    camera, sun, sky = recipe.data["camera"], recipe.data["sun"], recipe.data["sky"]
    width, height = camera["resolution"]
    aperture = camera["horizontal_aperture_mm"]
    clip = camera["clipping_range_m"]
    color = ", ".join(_f(v) for v in sky["color"])
    variants = _variants(recipe)
    world_head = 'over "World"' + (f"\n(\n{variants})" if variants else "")
    lines = [
        "#usda 1.0",
        "(",
        f"    subLayers = [@{scene_root}@]",
        '    upAxis = "Z"',
        "    metersPerUnit = 1",
        ")",
        "",
        world_head,
        "{",
        '    over "Lights"',
        "    {",
        '        over "Sun" (',
        "            active = false",
        "        )",
        "        {",
        "        }",
        "    }",
        "}",
        "",
        'def Scope "Render"',
        "{",
        '    def Camera "Cam"',
        "    {",
        f"        float focalLength = {_f(pose.focal_length_mm)}",
        f"        float horizontalAperture = {_f(aperture)}",
        f"        float verticalAperture = {_f(aperture * height / width)}",
        f"        float2 clippingRange = ({_f(clip[0])}, {_f(clip[1])})",
        f"        float exposure = {_f(camera['exposure_stops'])}",
        f"        matrix4d xformOp:transform = {matrix_rows(camera_matrix(pose.eye, pose.target, pose.up))}",
        '        uniform token[] xformOpOrder = ["xformOp:transform"]',
        "    }",
        '    def DistantLight "Sun"',
        "    {",
        f"        float inputs:intensity = {_f(sun['intensity'])}",
        f"        float inputs:angle = {_f(sun['angle_deg'])}",
        f"        matrix4d xformOp:transform = {matrix_rows(sun_matrix(pose.sun_azimuth_deg, pose.sun_elevation_deg))}",
        '        uniform token[] xformOpOrder = ["xformOp:transform"]',
        "    }",
        '    def DomeLight "Sky"',
        "    {",
        f"        float inputs:intensity = {_f(sky['intensity'])}",
        f"        color3f inputs:color = ({color})",
        "    }",
        '    def RenderProduct "Product"',
        "    {",
        f"        rel camera = <{CAMERA}>",
        f"        int2 resolution = ({width}, {height})",
        "        rel orderedVars = [</Render/Vars/LdrColor>]",
        "    }",
        '    def Scope "Vars"',
        "    {",
        '        def RenderVar "LdrColor"',
        "        {",
        '            uniform string sourceName = "LdrColor"',
        "        }",
        "    }",
        "}",
        "",
    ]
    return "\n".join(lines)

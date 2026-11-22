# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: PT018  (compound assertions read as one fact in these tests)
"""The ovrtx render backend against a recording double of the `ovrtx` module (call sequence and image copy)."""

from __future__ import annotations

import re
import types
from contextlib import contextmanager

import numpy as np
import pytest
from conftest import RECIPE_PATH
from pitstudio_rtx.render.backend import PRODUCT_PATH, OvrtxRenderBackend, build_backend
from pitstudio_rtx.render.plan import plan
from pitstudio_rtx.render.recipe import load_recipe


class _Var:
    def __init__(self, array):
        self.array = array

    @contextmanager
    def map(self):
        yield self.array


def make_module(image: np.ndarray, extra_vars: bool = True):
    calls: list[tuple] = []

    class Renderer:
        version = (0, 5, 0)

        def open_usd_from_string(self, text):
            calls.append(("open_string", text))

        def write_attribute(self, prims, name, tensor, semantic=None, **kw):
            calls.append(("write", tuple(prims), name, np.asarray(tensor).shape, semantic))

        def step(self, products, dt):
            calls.append(("step", frozenset(products), dt))
            frame = types.SimpleNamespace(
                render_vars={
                    "/Render/Vars/LdrColor": _Var(image),
                    **({"/Render/Vars/Other": _Var(np.zeros(3))} if extra_vars else {}),
                }
            )
            return {PRODUCT_PATH: types.SimpleNamespace(frames=[frame])}

        def destroy(self):
            calls.append(("destroy",))

    return types.SimpleNamespace(
        Renderer=Renderer,
        Semantic=types.SimpleNamespace(XFORM_MAT4x4="XFORM_MAT4x4"),
        _calls=calls,
    )


@pytest.fixture
def setup():
    recipe = load_recipe(RECIPE_PATH).reduced(resolution=(4, 3), stills=6, flyover_frames=4)
    poses = plan(recipe)
    image = np.arange(3 * 4 * 4, dtype=np.uint8).reshape(3, 4, 4)  # RGBA, 4 x 3
    module = make_module(image)
    backend = OvrtxRenderBackend(module=module)
    return recipe, poses, image, module, backend


def test_open_authors_the_session_layer_once(setup):
    recipe, _, _, module, backend = setup
    backend.open("scene/root.usda", recipe)
    kinds = [c[0] for c in module._calls]
    assert kinds == ["open_string"]
    assert "subLayers = [@scene/root.usda@]" in module._calls[0][1]


def test_write_mode_moves_camera_and_sun_without_reloading(setup):
    recipe, poses, _, module, backend = setup
    backend.open("scene/root.usda", recipe)
    backend.apply(poses[0])
    writes = [c for c in module._calls if c[0] == "write"]
    assert [(w[1], w[2], w[3], w[4]) for w in writes] == [
        (("/Render/Cam",), "xformOp:transform", (1, 4, 4), "XFORM_MAT4x4"),
        (("/Render/Sun",), "xformOp:transform", (1, 4, 4), "XFORM_MAT4x4"),
    ]
    assert [c[0] for c in module._calls].count("open_string") == 1


def test_focal_length_changes_are_written_too(setup):
    recipe, poses, _, module, backend = setup
    backend.open("scene/root.usda", recipe)
    plan_view = next(p for p in poses if p.id == "plan-view")
    backend.apply(poses[0])
    backend.apply(plan_view)
    names = [c[2] for c in module._calls if c[0] == "write"]
    assert "focalLength" in names


def test_reload_mode_reauthors_the_layer_per_pose(setup):
    recipe, poses, _, module, backend = setup
    backend.open("scene/root.usda", recipe)
    backend.set_mode("reload")
    backend.apply(poses[0])
    backend.apply(poses[1])
    assert [c[0] for c in module._calls].count("open_string") == 3
    assert not [c for c in module._calls if c[0] == "write"]
    layers = [c[1] for c in module._calls if c[0] == "open_string"]
    assert layers[1] != layers[2]


def test_step_and_grab_return_rgb_uint8(setup):
    recipe, poses, image, module, backend = setup
    backend.open("scene/root.usda", recipe)
    backend.apply(poses[0])
    backend.step()
    out = backend.grab()
    step = next(c for c in module._calls if c[0] == "step")
    assert step[1] == frozenset({PRODUCT_PATH})
    assert out.dtype == np.uint8 and out.shape == (3, 4, 3)
    assert np.array_equal(out, image[..., :3])
    assert out is not image


def test_grab_without_ldr_color_fails_loudly(setup):
    recipe, poses, _, module, backend = setup
    backend.open("scene/root.usda", recipe)
    backend.apply(poses[0])
    backend.step()
    module.Renderer.step = lambda self, products, dt: {
        PRODUCT_PATH: types.SimpleNamespace(
            frames=[types.SimpleNamespace(render_vars={"/Render/Vars/Depth": _Var(np.zeros((3, 4)))})]
        )
    }
    backend.step()
    with pytest.raises(RuntimeError, match=re.escape("LdrColor")):
        backend.grab()


def test_describe_and_close(setup):
    recipe, _, _, module, backend = setup
    info = backend.describe()
    assert info["tool"] == "ovrtx"
    backend.open("scene/root.usda", recipe)
    backend.close()
    assert module._calls[-1] == ("destroy",)


def test_build_backend_has_no_placeholder():
    assert isinstance(build_backend("ovrtx"), OvrtxRenderBackend)
    for name in ("fake", "stub", "mock", ""):
        with pytest.raises(ValueError, match="unknown render backend"):
            build_backend(name)

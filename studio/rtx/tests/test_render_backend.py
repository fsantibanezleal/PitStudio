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


def make_module(image: np.ndarray, extra_vars: bool = True, fail_write: bool = False):
    """Recording doubles of `ovrtx` (standalone and ovstage-attached renderer) and of `ovstage`."""
    calls: list[tuple] = []

    class Renderer:
        version = (0, 5, 0)

        def open_usd_from_string(self, text):
            calls.append(("open_string", text))

        def attach_ovstage(self, stage):
            calls.append(("attach", stage.name))

        def step(self, products, dt, ordinal=None):
            calls.append(("step", frozenset(products), dt, ordinal))
            frame = types.SimpleNamespace(
                render_vars={
                    "/Render/Vars/LdrColor": _Var(image),
                    **({"/Render/Vars/Other": _Var(np.zeros(3))} if extra_vars else {}),
                }
            )
            return {PRODUCT_PATH: types.SimpleNamespace(frames=[frame])}

        def destroy(self):
            calls.append(("destroy",))

    class Op:
        def wait(self):
            return self

    class Query:
        def __init__(self, paths):
            self.paths = paths

    class PathList:
        def __init__(self, paths):
            self.paths = paths

    class Stage:
        def __init__(self, name=None):
            self.name = name
            calls.append(("stage", name))

        def query_from_path_list(self, plist):
            return Query(plist.paths)

        def write_attribute(self, query, attribute, ordinal, tensors, *, is_array, semantic=0, **kw):
            if fail_write:
                raise RuntimeError("write refused")
            shape = np.asarray(tensors).shape
            calls.append(("write", tuple(query.paths), attribute, ordinal, shape, is_array, semantic))
            return Op()

        def advance_write_floor(self, ordinal, **kw):
            calls.append(("floor", ordinal))
            return Op()

        def destroy(self):
            pass

    class PathDictionary:
        def __init__(self, stage=None):
            pass

        def create_path_list_from_strings(self, paths):
            return PathList(list(paths))

    def open_usd_from_string(stage, usda, ordinal=1, **kw):
        calls.append(("populate", usda, ordinal))

    module = types.SimpleNamespace(Renderer=Renderer, _calls=calls)
    module._ovstage = types.SimpleNamespace(
        Stage=Stage,
        PathDictionary=PathDictionary,
        AttributeSemantic=types.SimpleNamespace(MATRIX=7),
        population=types.SimpleNamespace(open_usd_from_string=open_usd_from_string),
    )
    return module


@pytest.fixture
def setup():
    recipe = load_recipe(RECIPE_PATH).reduced(resolution=(4, 3), stills=6, flyover_frames=4)
    poses = plan(recipe)
    image = np.arange(3 * 4 * 4, dtype=np.uint8).reshape(3, 4, 4)  # RGBA, 4 x 3
    module = make_module(image)
    backend = OvrtxRenderBackend(module=module, ovstage_module=module._ovstage)
    return recipe, poses, image, module, backend


def test_open_populates_an_ovstage_with_the_session_layer_and_attaches_it(setup):
    recipe, _, _, module, backend = setup
    backend.open("scene/root.usda", recipe)
    kinds = [c[0] for c in module._calls]
    assert kinds == ["stage", "populate", "attach"]
    assert "subLayers = [@scene/root.usda@]" in module._calls[1][1]
    assert backend.mode == "ovstage"


def test_ovstage_mode_writes_camera_sun_focal_length_and_lights_with_rising_ordinals(setup):
    recipe, poses, _, module, backend = setup
    backend.open("scene/root.usda", recipe)
    backend.apply(poses[0], 2.0)
    writes = [c for c in module._calls if c[0] == "write"]
    by_path = {(w[1], w[2]): w for w in writes}
    assert by_path[(("/Render/Cam",), "xformOp:transform")][4] == (1, 4, 4)
    assert by_path[(("/Render/Cam",), "xformOp:transform")][6] == 7  # the matrix semantic
    assert by_path[(("/Render/Sun",), "xformOp:transform")][4] == (1, 4, 4)
    assert (("/Render/Cam",), "focalLength") in by_path
    assert by_path[(("/Render/Sun",), "inputs:intensity")][4] == (1,)  # sun intensity times the gain
    assert (("/Render/Sky",), "inputs:intensity") in by_path
    assert all(w[5] is False for w in writes)
    ordinals = [w[3] for w in writes]
    assert ordinals == sorted(ordinals) and len(set(ordinals)) == len(ordinals) and ordinals[0] > 1
    assert [c[0] for c in module._calls].count("open_string") == 0  # no scene reload


def test_the_step_waits_for_the_last_written_ordinal(setup):
    recipe, poses, _, module, backend = setup
    backend.open("scene/root.usda", recipe)
    backend.apply(poses[0])
    backend.apply(poses[1])
    backend.step()
    last = max(c[3] for c in module._calls if c[0] == "write")
    assert [c for c in module._calls if c[0] == "step"][-1][3] == last


def test_a_refused_ovstage_write_falls_back_to_reload_with_a_standalone_renderer():
    module = make_module(np.zeros((3, 4, 4), dtype=np.uint8), fail_write=True)
    backend = OvrtxRenderBackend(module=module, ovstage_module=module._ovstage)
    recipe = load_recipe(RECIPE_PATH).reduced(resolution=(4, 3), stills=6, flyover_frames=4)
    poses = plan(recipe)
    backend.open("scene/root.usda", recipe)
    backend.apply(poses[0])
    assert backend.mode == "reload"
    kinds = [c[0] for c in module._calls]
    assert "destroy" in kinds and kinds.count("open_string") == 1


def test_reload_mode_reauthors_the_layer_per_pose_and_carries_the_gain(setup):
    recipe, poses, _, module, backend = setup
    backend.open("scene/root.usda", recipe)
    backend.set_mode("reload")
    backend.apply(poses[0])
    backend.apply(poses[1], 4.0)
    assert [c[0] for c in module._calls].count("open_string") == 2
    assert not [c for c in module._calls if c[0] == "write"]
    layers = [c[1] for c in module._calls if c[0] == "open_string"]
    assert layers[0] != layers[1] and "float inputs:intensity = 12000.0" in layers[1]


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
    module.Renderer.step = lambda self, products, dt, ordinal=None: {
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

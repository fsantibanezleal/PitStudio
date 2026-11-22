# SPDX-License-Identifier: Apache-2.0
"""The session layer that adds camera, render product and lights over the scene."""

from __future__ import annotations

import re

import numpy as np
import pytest
from conftest import RECIPE_PATH
from pitstudio_rtx.render.plan import camera_matrix, plan
from pitstudio_rtx.render.recipe import Recipe, load_recipe
from pitstudio_rtx.render.usd import CAMERA, PRODUCT, SUN, matrix_rows, session_layer


@pytest.fixture(scope="module")
def layer():
    recipe = load_recipe(RECIPE_PATH)
    return session_layer("scene/root.usda", recipe, plan(recipe)[0])


def test_layer_sublayers_the_scene_and_declares_z_up(layer):
    assert layer.startswith("#usda 1.0")
    assert "subLayers = [@scene/root.usda@]" in layer
    assert 'upAxis = "Z"' in layer


def test_render_product_matches_the_probe_contract(layer):
    assert f'def RenderProduct "{PRODUCT.rsplit("/", 1)[-1]}"' in layer
    assert "int2 resolution = (1920, 1080)" in layer
    assert f"rel camera = <{CAMERA}>" in layer
    assert 'uniform string sourceName = "LdrColor"' in layer
    assert "rel orderedVars = [</Render/Vars/LdrColor>]" in layer


def test_camera_attributes(layer):
    assert "float focalLength = 24.0" in layer
    assert "float horizontalAperture = 36.0" in layer
    assert "float verticalAperture = 20.25" in layer
    assert "float2 clippingRange = (1.0, 20000.0)" in layer
    assert "float exposure = 0.0" in layer


def test_scene_sun_replaced_by_recipe_sun(layer):
    assert 'over "Sun" (' in layer
    assert "active = false" in layer
    assert f'def DistantLight "{SUN.rsplit("/", 1)[-1]}"' in layer
    assert "float inputs:intensity = 3000.0" in layer
    assert 'def DomeLight "Sky"' in layer
    assert "color3f inputs:color = (0.55, 0.7, 0.95)" in layer


def test_variant_override_only_when_asked():
    recipe = load_recipe(RECIPE_PATH)
    pose = plan(recipe)[0]
    assert "variants" not in session_layer("r.usda", recipe, pose)
    data = {**recipe.data, "scene": {**recipe.data["scene"], "variants": {"lod": "lod1"}}}
    patched = Recipe(data=data, sha256=recipe.sha256, path=recipe.path)
    assert 'string lod = "lod1"' in session_layer("r.usda", patched, pose)


def test_matrix_rows_use_usd_row_vector_layout():
    m = camera_matrix((1.0, 2.0, 3.0), (11.0, 2.0, 3.0), (0.0, 0.0, 1.0))
    rows = re.findall(r"\(([^()]+)\)", matrix_rows(m))
    assert len(rows) == 4
    assert [float(v) for v in rows[3].split(",")] == pytest.approx([1.0, 2.0, 3.0, 1.0])
    assert pytest.approx(m) == np.array([[float(v) for v in r.split(",")] for r in rows]).T


def test_pose_changes_the_transform_lines():
    recipe = load_recipe(RECIPE_PATH)
    a, b = plan(recipe)[0], plan(recipe)[1]
    la, lb = session_layer("r.usda", recipe, a), session_layer("r.usda", recipe, b)
    assert la != lb
    assert la.count("xformOp:transform =") == lb.count("xformOp:transform =") == 2  # camera and sun

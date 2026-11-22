# SPDX-License-Identifier: Apache-2.0
"""Recipe loading, validation, scene resolution and the missing-layer behavior."""

from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path

import pytest
import yaml
from conftest import RECIPE_PATH, make_scene
from pitstudio_rtx.render.recipe import RenderRecipeError, load_recipe, resolve_scene


def _write(tmp_path: Path, mutate) -> Path:
    data = copy.deepcopy(yaml.safe_load(RECIPE_PATH.read_text(encoding="utf-8")))
    mutate(data)
    path = tmp_path / "r.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_real_recipe_contract():
    r = load_recipe(RECIPE_PATH)
    assert r.data["camera"]["resolution"] == [1920, 1080]
    assert r.data["flyover"]["duration_s"] == 20.0
    assert r.data["flyover"]["fps"] == 30
    assert len(r.data["stills"]) >= 6
    assert re.fullmatch(r"[0-9a-f]{64}", r.sha256)
    assert r.path == "render/bingham-flyover.yaml"
    assert r.data["label"] == "Rendered with NVIDIA Omniverse RTX (ovrtx)"


def test_recipe_holds_no_machine_path():
    text = RECIPE_PATH.read_text(encoding="utf-8")
    assert not re.search(r"\b[A-Za-z]:[\\/]|/Users/|/home/", text)


def test_digest_is_of_the_file_bytes():
    assert load_recipe(RECIPE_PATH).sha256 == hashlib.sha256(RECIPE_PATH.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["stills"].__delitem__(slice(0, 3)), "at least 6 stills"),
        (lambda d: d["stills"].append(dict(d["stills"][0])), "duplicate still id"),
        (lambda d: d["flyover"]["control_points"].__delitem__(slice(3, None)), "at least 4 control points"),
        (lambda d: d["camera"].update(resolution=[1920]), "resolution"),
        (lambda d: d["flyover"].update(fps=0), "fps"),
        (lambda d: d["flyover"].update(duration_s=-1), "duration_s"),
        (lambda d: d["stills"][0].update(eye=[1, 2]), "eye"),
        (lambda d: d["stills"][0].update(id="Bad Id"), "still id"),
        (lambda d: d.pop("scene"), "scene"),
        (lambda d: d["output"].update(disk_limit_gib=0), "disk_limit_gib"),
    ],
)
def test_invalid_recipes_are_refused(tmp_path, mutate, message):
    with pytest.raises(RenderRecipeError, match=message):
        load_recipe(_write(tmp_path, mutate))


def test_reduced_keeps_the_digest_of_the_file_and_marks_itself():
    r = load_recipe(RECIPE_PATH)
    small = r.reduced(resolution=(320, 180), stills=2, flyover_frames=3)
    assert small.sha256 == r.sha256
    assert small.data["camera"]["resolution"] == [320, 180]
    assert len(small.data["stills"]) == 2
    assert small.data["flyover"]["frame_override"] == 3
    assert small.is_reduced
    assert not r.is_reduced


def test_scene_resolution_digest_and_layers(tmp_path):
    root = tmp_path / "d"
    scene_dir = make_scene(root)
    scene = resolve_scene(load_recipe(RECIPE_PATH), root)
    assert scene.root == scene_dir / "root.usda"
    assert re.fullmatch(r"[0-9a-f]{64}", scene.sha256)
    assert scene.missing_layers == ()
    assert "layers/terrain.usdc" in dict(scene.layers)
    assert resolve_scene(load_recipe(RECIPE_PATH), root).sha256 == scene.sha256
    (scene_dir / "layers" / "design.usda").write_bytes(b"changed")
    assert resolve_scene(load_recipe(RECIPE_PATH), root).sha256 != scene.sha256


def test_missing_scene_is_refused(tmp_path):
    with pytest.raises(RenderRecipeError, match="scene root not found"):
        resolve_scene(load_recipe(RECIPE_PATH), tmp_path / "nothing")


def test_missing_layers_are_listed_not_invented(tmp_path):
    root = tmp_path / "d"
    make_scene(root, layers=("lights", "design", "terrain"), materials=False)
    scene = resolve_scene(load_recipe(RECIPE_PATH), root)
    assert scene.missing_layers == ("fleet", "materials")

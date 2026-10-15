# ruff: noqa: PT018
"""T-009-016 (fix): the `st55_sdg` queue entry finds and checks the real inputs of the data root.

Requirements: FR-009-02, FR-009-09, FR-009-10.

The entry looked for a scene manifest at `processed/scenes/b2/manifest.json` and a texture folder `raw/textures-cc0`,
paths that no stage of spec 004 or the texture download writes. It now reads the validated scene of spec 004 at
`processed/scene/<scene id>/st45_validate/scene/scene.manifest.json` and the texture pool manifest
`raw/textures/manifest.json`, and it checks the recipe against both: every texture of the recipe pool exists with the
SHA-256 the recipe states, and the scene validation is complete.

Oracle: hand-built data roots in a temporary folder; the expected messages are written in this test.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
from pitstudio_isaac.sdg import run_job  # noqa: E402


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _root(tmp: Path, *, scene_status: str = "complete", texture_bytes: bytes = b"jpeg-bytes") -> Path:
    tex = tmp / "raw" / "textures" / "polyhaven" / "t1"
    tex.mkdir(parents=True)
    (tex / "t1_diff_1k.jpg").write_bytes(b"jpeg-bytes")
    manifest = {
        "textures": [{"id": "polyhaven-t1", "file": "polyhaven/t1/t1_diff_1k.jpg", "sha256": _sha(texture_bytes)}]
    }
    (tmp / "raw" / "textures" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    perception = tmp / "processed" / "perception"
    perception.mkdir(parents=True)
    recipe = {
        "texture_pool": [
            {"id": "polyhaven-t1", "source_id": "polyhaven", "sha256": _sha(b"jpeg-bytes"), "spdx": "CC0-1.0"}
        ]
    }
    (perception / "recipe.json").write_text(json.dumps(recipe), encoding="utf-8")
    scene = tmp / "processed" / "scene" / "a1-bingham" / "st45_validate" / "scene"
    scene.mkdir(parents=True)
    (scene / "scene.manifest.json").write_text(json.dumps({"validation": {"status": scene_status}}), encoding="utf-8")
    return tmp


@pytest.fixture(autouse=True)
def _isaac_is_importable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_job.importlib.util, "find_spec", lambda name: object())


@pytest.mark.req("FR-009-02")
def test_a_complete_data_root_has_no_missing_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PITSTUDIO_DATA", str(_root(tmp_path)))
    assert run_job.missing_inputs() == []


@pytest.mark.req("FR-009-02")
def test_an_empty_data_root_lists_the_recipe_the_scene_and_the_texture_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PITSTUDIO_DATA", str(tmp_path))
    out = run_job.missing_inputs()
    assert len(out) == 3
    assert any("recipe" in line for line in out)
    assert any("scene" in line for line in out)
    assert any("texture" in line for line in out)


@pytest.mark.req("FR-009-10")
def test_a_texture_whose_digest_differs_from_the_recipe_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    (root / "raw" / "textures" / "polyhaven" / "t1" / "t1_diff_1k.jpg").write_bytes(b"tampered")
    monkeypatch.setenv("PITSTUDIO_DATA", str(root))
    out = run_job.missing_inputs()
    assert len(out) == 1 and "polyhaven-t1" in out[0] and "SHA-256" in out[0]


@pytest.mark.req("FR-009-09")
def test_a_recipe_texture_that_is_not_in_the_pool_manifest_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    recipe_path = root / "processed" / "perception" / "recipe.json"
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    recipe["texture_pool"].append(
        {"id": "ambientcg-ghost", "source_id": "ambientcg", "sha256": "0" * 64, "spdx": "CC0-1.0"}
    )
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")
    monkeypatch.setenv("PITSTUDIO_DATA", str(root))
    out = run_job.missing_inputs()
    assert len(out) == 1 and "ambientcg-ghost" in out[0]


@pytest.mark.req("FR-009-02")
def test_an_incomplete_scene_validation_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PITSTUDIO_DATA", str(_root(tmp_path, scene_status="incomplete")))
    out = run_job.missing_inputs()
    assert len(out) == 1 and "validation" in out[0]


@pytest.mark.req("FR-009-02")
def test_the_scene_id_can_be_chosen_with_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path)
    monkeypatch.setenv("PITSTUDIO_DATA", str(root))
    monkeypatch.setenv("PITSTUDIO_SDG_SCENE", "other-scene")
    out = run_job.missing_inputs()
    assert len(out) == 1 and "other-scene" in out[0]

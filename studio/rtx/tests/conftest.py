# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures of the render tests: a minimal on-disk scene, a deterministic fake backend and the real recipe.

The fake backend lives here and only here: the package has no fake render backend, so a placeholder can never be
selected by the GPU job (brief rtx-bingham-render-2026-11-22).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

RTX = Path(__file__).resolve().parents[1]
REPO = RTX.parents[1]
sys.path.insert(0, str(RTX / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

RECIPE_PATH = REPO / "studio" / "recipes" / "render" / "bingham-flyover.yaml"
ROOT_USDA = """#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    subLayers = [
        @layers/lights.usda@,
        @layers/design.usda@,
        @layers/terrain.usdc@
    ]
    upAxis = "Z"
)
"""


def make_scene(
    data_root: Path, layers: tuple[str, ...] = ("lights", "design", "terrain", "fleet"), materials: bool = True
) -> Path:
    """A minimal scene folder under `<data_root>/processed/scene/a1-bingham/st45_validate/scene`."""
    scene = data_root / "processed" / "scene" / "a1-bingham" / "st45_validate" / "scene"
    (scene / "layers").mkdir(parents=True)
    (scene / "assets").mkdir()
    (scene / "root.usda").write_text(ROOT_USDA, encoding="utf-8")
    for name in layers:
        suffix = "usdc" if name == "terrain" else "usda"
        (scene / "layers" / f"{name}.{suffix}").write_bytes(f"layer {name}\n".encode())
    if materials:
        (scene / "assets" / "materials.usda").write_text("materials\n", encoding="utf-8")
    return scene


class FakeBackend:
    """Deterministic render backend double: the image is a function of the applied pose (and mode)."""

    def __init__(self, *, ignore_writes: bool = False, fail_at_apply: int | None = None, flat: bool = False) -> None:
        self.ignore_writes, self.fail_at_apply, self.flat = ignore_writes, fail_at_apply, flat
        self.mode = "write"
        self.applied: list[Any] = []
        self.steps = 0
        self.opened = 0
        self.closed = 0
        self._shown: Any = None
        self.size = (18, 32)

    def describe(self) -> dict[str, str]:
        return {"tool": "test-double", "version": "0.0.0", "runtime": "none"}

    def open(self, scene_root: str, recipe: Any) -> None:
        self.opened += 1
        w, h = recipe.data["camera"]["resolution"]
        self.size = (h, w)

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def apply(self, pose: Any) -> None:
        if self.fail_at_apply is not None and len(self.applied) >= self.fail_at_apply:
            raise RuntimeError("boom")
        self.applied.append(pose)
        if self._shown is None or not self.ignore_writes or self.mode == "reload":
            self._shown = pose

    def step(self) -> None:
        self.steps += 1

    def grab(self) -> np.ndarray:
        if self.flat:
            return np.full((*self.size, 3), 7, dtype=np.uint8)
        key = repr((self._shown.eye, self._shown.target, self._shown.sun_azimuth_deg))
        seed = sum((i + 1) * ord(c) for i, c in enumerate(key)) % (2**32)
        return np.random.default_rng(seed).integers(0, 256, (*self.size, 3), dtype=np.uint8)

    def close(self) -> None:
        self.closed += 1


@pytest.fixture
def recipe_path() -> Path:
    return RECIPE_PATH


@pytest.fixture
def small_recipe():
    """The real recipe reduced to 32 x 18 px, 6 stills and 6 flyover frames (the same reduction the dry run uses)."""
    from pitstudio_rtx.render.recipe import load_recipe

    return load_recipe(RECIPE_PATH).reduced(resolution=(32, 18), stills=6, flyover_frames=6)


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    make_scene(root)
    return root


def fake_encode(frames_dir: Path, pattern: str, fps: int, out: Path, output: dict[str, Any]):
    from pitstudio_rtx.render.encode import EncodeInfo

    out.write_bytes(b"mp4:" + str(len(list(frames_dir.glob("*.png")))).encode())
    return EncodeInfo(name="h264_nvenc", fallback=False, ffmpeg_version="8.1", args=["-c:v", "h264_nvenc"])

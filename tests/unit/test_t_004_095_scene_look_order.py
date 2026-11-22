# ruff: noqa: E501
"""T-004-095 (third file): the root layer keeps its prims in sorted name order when it references and binds materials.

Requirements: FR-004-30, FR-004-46.

Oracle: the sorted-order rule of FR-004-30, checked with the Sdf prim-spec API (the sibling check in T-004-040 passes the
pseudo root to a function that takes prim specs and fails with this OpenUSD build, so it never reaches the root layer).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import dem_kit as dk  # noqa: E402
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import compose  # noqa: E402


def _walk(spec, found: list[tuple[str, list[str]]]) -> None:
    names = [c.name for c in spec.nameChildren]
    found.append((str(spec.path), names))
    for child in spec.nameChildren:
        _walk(child, found)


@pytest.mark.req("FR-004-30")
@pytest.mark.req("FR-004-46")
def test_every_prim_of_the_root_layer_lists_its_children_in_sorted_order(tmp_path: Path) -> None:
    from pxr import Sdf

    spec = kit.scene_spec()
    spec["variants"] = {"pushback": ["pb0"], "scenario": ["baseline"], "time_of_day": ["noon"], "weather": ["clear"], "lod": ["lod0", "lod1", "lod2"]}
    compose.compose_scene(spec, dk.upstream(tmp_path / "up"), tmp_path / "scene")
    layer = Sdf.Layer.FindOrOpen(str(tmp_path / "scene" / "root.usda"))
    found: list[tuple[str, list[str]]] = []
    for prim in layer.rootPrims:
        _walk(prim, found)
    assert any(path == "/World" and "Materials" in names for path, names in found)  # the case under test is present
    for path, names in found:
        assert names == sorted(names), (path, names)

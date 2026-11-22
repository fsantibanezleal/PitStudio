# ruff: noqa: E501, PT018
"""T-004-095 (second file): the primvar reader of each material reads `st` as a string.

Requirements: FR-004-46.

Oracle: the Sdr schema of `UsdPrimvarReader_float2` declares `varname` as a `string`; the material layer of the assets
stage authors it as a `token`, which `usd-validation-nvidia` reports as `UsdShadeShaderSdrCompliance` once the materials
are part of the composed stage (observed on the Bingham scene, 18 errors). OpenUSD read back as the reference.

Expected API: `compose.compose_scene` as in T-004-095: the composed `UV` shader of `bench_rock` and `gravel_road` has
`inputs:varname` of type `string` and value `st`; the material layer file itself is unchanged.
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


@pytest.mark.req("FR-004-46")
def test_the_primvar_reader_varname_is_a_string_in_the_composed_stage(tmp_path: Path) -> None:
    from pxr import Usd

    spec = kit.scene_spec()
    spec["variants"] = {"pushback": ["pb0"], "scenario": ["baseline"], "time_of_day": ["noon"], "weather": ["clear"], "lod": ["lod0", "lod1", "lod2"]}
    compose.compose_scene(spec, dk.upstream(tmp_path / "up"), tmp_path / "scene")
    stage = Usd.Stage.Open(str(tmp_path / "scene" / "root.usda"))
    for name in ("bench_rock", "gravel_road"):
        attr = stage.GetPrimAtPath(f"/World/Materials/{name}/UV").GetAttribute("inputs:varname")
        assert str(attr.GetTypeName()) == "string" and attr.Get() == "st", name

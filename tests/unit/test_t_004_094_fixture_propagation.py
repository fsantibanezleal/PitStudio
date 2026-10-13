# ruff: noqa: E501, PT018
"""T-004-094: fixture propagation through the scene stages.

Requirements: FR-004-44.

Oracle: hand calculation (plan.md "FR-004-44"): a fixture terrain grid yields a scene manifest, design report and tile index
all `fixture: true`; a real input yields `false`. The expected values are written in the test.

Expected API (studio environment, the packages of the earlier tests):
- `terrain.build_terrain_grid(spec, inputs)`: `grid.attrs` (the DC-004-03 attribute dict) has `fixture` = `spec.get("fixture",
  False)` (a SceneSpec with `fixture: true` is a contract fixture) and `grid.fixture` the same bool.
- `terrain.tiles.build_tiles(..., fixture=False)` and `TileSet.document(grid_elevation_sha256, layer_path)`: the DC-004-04
  tile index document, with `fixture` = the flag given to `build_tiles`.
- `design.build_design(grid, spec, outline_xy=...)`: `report["fixture"]` and `road_network["fixture"]` equal
  `bool(getattr(grid, "fixture", False))`.
- `compose.compose_scene(spec, upstream, scene_dir)`: `manifest["fixture"]` and `digest["fixture"]` equal
  `bool(upstream.get("fixture", False) or spec.get("fixture", False))`.
- `validate.validate_scene(...)`: `report["fixture"]` and `manifest["fixture"]` equal the validated manifest's flag.
Real inputs give an explicit `false`. The DC-004 draft schemas have `additionalProperties: false` and no `fixture` member;
the documents carry the field in addition (the schemas need the member, see the review notes).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import compose, design, terrain, validate  # noqa: E402

SRC = "usgs-3dep-bingham"
NO_RESULTS = {"usd-validation-nvidia": lambda root, selection: [], "simready-validate": lambda root, selection: []}


def _dem(tmp: Path) -> Path:
    z = kit.Z0 + np.arange(144, dtype=np.float64).reshape(12, 12)
    return kit.write_dem(tmp / "dem.tif", z, x_min=kit.E0, y_max=kit.N0 + 12, cell=1.0, wkt=kit.crs_wkt("utm12-m"))


@pytest.mark.req("FR-004-44")
@pytest.mark.parametrize("fixture", [True, False])
def test_the_terrain_grid_carries_the_flag_of_its_input(tmp_path: Path, fixture: bool) -> None:
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, 12.0, 12.0)
    if fixture:
        spec["fixture"] = True
    grid = terrain.build_terrain_grid(spec, {SRC: [_dem(tmp_path)]})
    assert grid.fixture is fixture and grid.attrs["fixture"] is fixture


@pytest.mark.req("FR-004-44")
@pytest.mark.parametrize("fixture", [True, False])
def test_the_tile_index_carries_the_flag(fixture: bool) -> None:
    h = kit.fbm_grid(8, 3, amplitude=10.0)
    lods = [{"lod": 0, "max_error_m": 1.0, "skirt_depth_m": 2.0}]
    ts = terrain.tiles.build_tiles(h, cell_size_m=1.0, x_min_m=0.0, y_max_m=256.0, lods=lods, fixture=fixture)
    doc = ts.document("0" * 64, "layers/terrain.usdc")
    assert doc["fixture"] is fixture and doc["kind"] == "terrain-tiles"


@pytest.mark.req("FR-004-44")
@pytest.mark.parametrize("fixture", [True, False])
def test_the_design_report_and_road_network_carry_the_flag(fixture: bool) -> None:
    grid = kit.flat_grid(130.0, 1.0, 0.0)
    grid.fixture = fixture
    spec = kit.design_spec(h=12.0, floor_z=-36.0, g=8.0, w=20.0)
    res = design.build_design(grid, spec, outline_xy=kit.regular_polygon(180, 100.0))
    assert res.report["fixture"] is fixture and res.road_network["fixture"] is fixture


@pytest.mark.req("FR-004-44")
def test_a_grid_without_the_attribute_is_real() -> None:
    grid = kit.flat_grid(130.0, 1.0, 0.0)  # no `fixture` attribute at all
    res = design.build_design(
        grid, kit.design_spec(h=12.0, floor_z=-36.0, g=8.0, w=20.0), outline_xy=kit.regular_polygon(180, 100.0)
    )
    assert res.report["fixture"] is False and res.road_network["fixture"] is False


@pytest.mark.req("FR-004-44")
@pytest.mark.parametrize(("source", "expected"), [("upstream", True), ("spec", True), ("none", False)])
def test_the_scene_manifest_and_digest_carry_the_flag(tmp_path: Path, source: str, expected: bool) -> None:
    spec = kit.scene_spec()
    up = kit.fixture_upstream(tmp_path / "up")
    if source == "upstream":
        up["fixture"] = True
    if source == "spec":
        spec["fixture"] = True
    build = compose.compose_scene(spec, up, tmp_path / "scene")
    assert build.manifest["fixture"] is expected and build.digest["fixture"] is expected


@pytest.mark.req("FR-004-44")
@pytest.mark.parametrize("fixture", [True, False])
def test_the_validation_report_and_updated_manifest_keep_the_flag(tmp_path: Path, fixture: bool) -> None:
    import itertools

    spec = kit.scene_spec()
    spec["variants"]["lod"] = ["lod0", "lod1", "lod2"]
    counter = itertools.count()

    def build(out: Path):
        up = kit.fixture_upstream(tmp_path / f"up{next(counter)}")
        up["fixture"] = fixture
        return compose.compose_scene(spec, up, out)

    out = validate.validate_scene(spec, build, tmp_path / "work", runners=NO_RESULTS)
    assert out.report["fixture"] is fixture and out.manifest["fixture"] is fixture

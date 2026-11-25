# ruff: noqa: E501, PT018
"""T-004-092: two LAZ projects for one terrain grid are rejected.

Requirements: FR-004-42.

Oracle: hand calculation (plan.md "FR-004-42"): a scene fixture with two LAZ projects for the grid of source
`usgs-3dep-bingham` gives `terrain-source-ambiguous`, naming the grid id and both project ids; one LAZ project per
grid, or LAZ for different grids, is accepted. The project names are written in this test.

Expected API (package `pitstudio_studio.scene.terrain`, studio environment):
- `terrain.check_terrain_sources(spec)`: looks at `spec["terrain"]["sources"]` only (no file is opened); the "grid id" is
  the source id (one terrain grid per source id, spec section 7). Raises `common.SceneStageError("terrain-source-ambiguous")`,
  message `"terrain-source-ambiguous: ..."` naming the source id and both project ids, when two entries of `kind` `laz`
  share a source id but have different `project` values.
- `terrain.build_terrain_grid` and `terrain.build_terrain` call it before reading any point.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import common, terrain  # noqa: E402

BINGHAM = "usgs-3dep-bingham"


def _laz(project: str, epoch: int, sid: str = BINGHAM, kind: str = "laz") -> dict:
    return {"id": sid, "kind": kind, "project": project, "epoch": epoch, "optional": False}


def _spec(*sources: dict) -> dict:
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, 9.0, 9.0)
    spec["terrain"]["sources"] = list(sources)
    return spec


@pytest.mark.req("FR-004-42")
def test_two_laz_projects_for_one_grid_are_ambiguous_and_both_are_named() -> None:
    spec = _spec(_laz("UT Central QL2 2018", 2018), _laz("UT Central QL1 2023", 2023))
    with pytest.raises(common.SceneStageError) as exc:
        terrain.check_terrain_sources(spec)
    msg = str(exc.value)
    assert exc.value.error_class == "terrain-source-ambiguous" and msg.startswith("terrain-source-ambiguous: ")
    assert BINGHAM in msg and "UT Central QL2 2018" in msg and "UT Central QL1 2023" in msg


@pytest.mark.req("FR-004-42")
def test_ambiguity_is_found_before_any_point_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: object, **k: object) -> None:
        raise AssertionError("a point or pixel reader was called")

    monkeypatch.setattr(terrain.io, "read_laz", boom)
    monkeypatch.setattr(terrain.io, "read_dem", boom)
    rng = np.random.default_rng(1)
    x, y = rng.uniform(0, 9, 500), rng.uniform(0, 9, 500)
    a = kit.write_laz(tmp_path / "a.laz", kit.E0 + x, kit.N0 + y, kit.Z0 + x, np.full(500, 2, np.uint8))
    b = kit.write_laz(tmp_path / "b.laz", kit.E0 + x, kit.N0 + y, kit.Z0 + y, np.full(500, 2, np.uint8))
    spec = _spec(_laz("Project A 2018", 2018), _laz("Project B 2023", 2023))
    for call in (terrain.build_terrain_grid, terrain.build_terrain):
        with pytest.raises(common.SceneStageError) as exc:
            call(spec, {BINGHAM: [a, b]})
        assert exc.value.error_class == "terrain-source-ambiguous"


@pytest.mark.req("FR-004-42")
@pytest.mark.parametrize(
    "sources",
    [
        [_laz("UT Central QL2 2018", 2018)],  # one project
        [_laz("UT Central QL2 2018", 2018), _laz("McKinley 2023", 2023, "ot-mckinley-2023")],  # two grids, one LAZ each
        [_laz("UT Central QL2 2018", 2018, kind="dem"), _laz("UT Central QL1 2023", 2023, kind="dem")],  # DEMs, not LAZ
    ],
    ids=["one-project", "two-grids", "two-dems"],
)
def test_one_laz_project_per_grid_is_accepted(sources: list[dict]) -> None:
    terrain.check_terrain_sources(_spec(*sources))


@pytest.mark.req("FR-004-42")
def test_unicode_and_long_project_names_are_reported_verbatim() -> None:
    p1, p2 = "Proyecto Bingham año 2018 ✓", "P" * 128
    spec = copy.deepcopy(_spec(_laz(p1, 2018), _laz(p2, 2023)))
    with pytest.raises(common.SceneStageError) as exc:
        terrain.check_terrain_sources(spec)
    assert p1 in str(exc.value) and "P" * 20 in str(exc.value)

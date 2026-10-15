# ruff: noqa: PT018
"""T-004-019: provisional site name until the mine-polygon confirmation.

Requirements: FR-004-15, SC-004-02.

Oracle: hand-built rectangles with known overlap fractions (0.95, 0.9, 0.5, ...) against a 100 m x 100 m AOI, areas
computed by hand; the contract examples of the scene manifest as the publication-check inputs (SC-004-02).

Expected API (studio environment):
- `pitstudio_studio.scene.terrain.confirm_site_name(name, *, aoi_xy_m, mine_polygons_xy_m) -> SiteName`:
  `mine_polygons_xy_m` maps a mine-polygon dataset id (`tang-werner-footprint`, `maus-v2`) to a polygon (list of
  [x, y], site frame, metres). The AOI is confirmed against a dataset when at least 90 % of the polygon's area lies
  inside the AOI (overlap fraction = area(polygon intersect AOI) / area(polygon)). `SiteName` has `name` (the input name
  when confirmed, else the input name + " (provisional)"), `provisional` (bool) and `confirmation` (None, or
  `{"source": <dataset id>, "overlap_frac": float}` of the best-overlapping confirming dataset).
- `pitstudio_studio.scene.common.site_name_violations(manifest) -> list[str]`: the publication check of SC-004-02 on a
  scene manifest dict: empty when the site name is consistent with the confirmation, else one message per violation
  (a name without the " (provisional)" suffix while `provisional` is true or `confirmation` is null or its
  `overlap_frac` is below 0.9).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import common, terrain  # noqa: E402

AOI = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
NAME = "Bingham Canyon"


def rect(x0: float, x1: float, y0: float = 0.0, y1: float = 100.0) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


@pytest.mark.req("FR-004-15")
def test_polygon_95_percent_inside_confirms_the_name() -> None:
    """Polygon x in [5, 105]: area 10,000 m2, 95 x 100 = 9,500 m2 inside the AOI: 0.95."""
    out = terrain.confirm_site_name(NAME, aoi_xy_m=AOI, mine_polygons_xy_m={"tang-werner-footprint": rect(5, 105)})
    assert (out.name, out.provisional) == (NAME, False)
    assert out.confirmation["source"] == "tang-werner-footprint"
    assert out.confirmation["overlap_frac"] == pytest.approx(0.95, abs=1e-9)


@pytest.mark.req("FR-004-15")
def test_polygon_50_percent_inside_leaves_the_name_provisional() -> None:
    out = terrain.confirm_site_name(NAME, aoi_xy_m=AOI, mine_polygons_xy_m={"tang-werner-footprint": rect(50, 150)})
    assert out.name == "Bingham Canyon (provisional)" and out.provisional is True and out.confirmation is None


@pytest.mark.req("FR-004-15")
def test_threshold_is_at_least_90_percent() -> None:
    at = terrain.confirm_site_name(NAME, aoi_xy_m=AOI, mine_polygons_xy_m={"maus-v2": rect(10, 110)})  # exactly 0.9
    assert at.provisional is False and at.confirmation["overlap_frac"] == pytest.approx(0.9, abs=1e-9)
    below = terrain.confirm_site_name(NAME, aoi_xy_m=AOI, mine_polygons_xy_m={"maus-v2": rect(10.01, 110.01)})
    assert below.provisional is True and below.name.endswith(" (provisional)")


@pytest.mark.req("FR-004-15")
def test_polygon_fully_inside_has_overlap_one_and_any_dataset_may_confirm() -> None:
    polys = {"tang-werner-footprint": rect(50, 150), "maus-v2": rect(20, 60, 20, 60)}  # first fails, second inside
    out = terrain.confirm_site_name(NAME, aoi_xy_m=AOI, mine_polygons_xy_m=polys)
    assert out.provisional is False
    assert out.confirmation == {"source": "maus-v2", "overlap_frac": pytest.approx(1.0)}


@pytest.mark.req("FR-004-15")
def test_without_any_polygon_or_with_a_degenerate_one_the_name_stays_provisional() -> None:
    assert terrain.confirm_site_name(NAME, aoi_xy_m=AOI, mine_polygons_xy_m={}).provisional is True
    flat = [[10.0, 10.0], [50.0, 10.0], [90.0, 10.0]]  # zero area: no overlap fraction exists
    out = terrain.confirm_site_name(NAME, aoi_xy_m=AOI, mine_polygons_xy_m={"maus-v2": flat})
    assert out.provisional is True and out.name == "Bingham Canyon (provisional)"


@pytest.mark.req("FR-004-15")
def test_concave_polygon_overlap_is_computed_by_area() -> None:
    """An L-shaped polygon (a 3 x 1 strip plus a 1 x 1 square: 4 m2) with 1 m2 outside a 2 x 2 AOI: overlap 3/4."""
    aoi = [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]]
    ell = [[0.0, 0.0], [3.0, 0.0], [3.0, 1.0], [1.0, 1.0], [1.0, 2.0], [0.0, 2.0]]
    out = terrain.confirm_site_name(NAME, aoi_xy_m=aoi, mine_polygons_xy_m={"maus-v2": ell})
    assert out.provisional is True
    best = terrain.confirm_site_name(
        NAME, aoi_xy_m=[[0, 0], [3, 0], [3, 2], [0, 2]], mine_polygons_xy_m={"maus-v2": ell}
    )
    assert best.provisional is False and best.confirmation["overlap_frac"] == pytest.approx(1.0)


def _manifest(name: str) -> dict:
    return json.loads((kit.EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.mark.req("SC-004-02")
def test_publication_check_accepts_the_two_consistent_manifests() -> None:
    assert common.site_name_violations(_manifest("scene-manifest.valid.json")) == []  # provisional + suffix
    assert common.site_name_violations(_manifest("scene-manifest.valid-validated.json")) == []  # confirmed at 0.96


@pytest.mark.req("SC-004-02")
@pytest.mark.parametrize(
    "example",
    ["scene-manifest.hostile-conditional-provisional.json", "scene-manifest.hostile-conditional-confirmation.json"],
)
def test_publication_check_rejects_the_bare_name_without_the_confirmation(example: str) -> None:
    problems = common.site_name_violations(_manifest(example))
    assert len(problems) >= 1 and all(isinstance(p, str) and "Bingham Canyon" in p for p in problems)


@pytest.mark.req("SC-004-02")
def test_publication_check_flags_an_unconfirmed_bare_name_even_when_not_marked_provisional() -> None:
    m = _manifest("scene-manifest.valid-validated.json")
    m["site"]["confirmation"] = None
    assert common.site_name_violations(m)
    m["site"]["confirmation"] = {"source": "tang-werner-footprint", "overlap_frac": 0.8999}
    assert common.site_name_violations(m)
    m["site"]["confirmation"] = {"source": "tang-werner-footprint", "overlap_frac": 0.9}
    assert common.site_name_violations(m) == []

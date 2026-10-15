# ruff: noqa: E501, PT018
"""T-008-024: the Bingham area of interest is checked against the footprint pit polygons before the site name is confirmed.

Requirements: FR-008-26.

Spec: specs/008-data-pipeline/spec.md FR-008-26 (if the Bingham area of interest does not intersect a pit polygon of the
mining-footprint layer `tang-werner-footprint`, every derived artefact is labelled "site name provisional" and
"Bingham Canyon" is not written as a confirmed site name) and section 8 item 8.

Oracle: hand-drawn rectangles and polygons on a small plane, decided by elementary geometry (the area of interest is the box
[0, 10] x [0, 10]): a polygon inside it, one overlapping a corner, one enclosing it, a disjoint one, and a triangle with
vertices (6, 20), (20, 6), (20, 20) whose bounding box overlaps the box while the triangle itself (the half-plane
x + y >= 26) does not reach it, because x + y <= 20 everywhere in the box.

Expected API of the implementation:
- `pitstudio_pipeline.ingest.site.resolve_site_name(aoi, pit_polygons) -> dict` with `aoi = (xmin, ymin, xmax, ymax)` and
  `pit_polygons` a list of rings (lists of (x, y) vertices, in the same CRS). Result keys: `confirmed` (bool), `site_name`
  (`"Bingham Canyon"` only when confirmed, else None or any text other than that name) and `artefact_label` (None when
  confirmed, exactly `"site name provisional"` otherwise, the label every derived artefact carries).
  A non-finite or inverted area of interest raises an exception.
"""

from __future__ import annotations

import pytest
from pitstudio_pipeline.ingest.site import resolve_site_name

AOI = (0.0, 0.0, 10.0, 10.0)


def rect(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


@pytest.mark.req("FR-008-26")
@pytest.mark.parametrize(
    "polygon",
    [rect(2, 2, 4, 4), rect(8, 8, 20, 20), rect(-5, -5, 15, 15), rect(-5, 4, 5, 6)],
    ids=["inside", "overlaps-corner", "encloses-aoi", "crosses-the-edge"],
)
def test_intersecting_pit_polygon_confirms_the_name(polygon: list[tuple[float, float]]) -> None:
    far = rect(100, 100, 110, 110)
    for polys in ([polygon], [far, polygon], [polygon, far]):
        r = resolve_site_name(AOI, polys)
        assert r["confirmed"] is True and r["site_name"] == "Bingham Canyon" and r["artefact_label"] is None


@pytest.mark.req("FR-008-26")
@pytest.mark.parametrize(
    "polys",
    [
        [],
        [rect(20, 20, 30, 30)],
        [rect(11, 0, 20, 10), rect(-20, -20, -11, -11)],
        [[(6.0, 20.0), (20.0, 6.0), (20.0, 20.0), (6.0, 20.0)]],  # bounding box overlaps, the triangle does not
    ],
    ids=["no-polygons", "disjoint", "two-disjoint", "bbox-overlap-only"],
)
def test_no_intersection_makes_the_name_provisional(polys: list) -> None:
    r = resolve_site_name(AOI, polys)
    assert r["confirmed"] is False
    assert r["site_name"] != "Bingham Canyon", "never written as a confirmed site name"
    assert r["artefact_label"] == "site name provisional"


@pytest.mark.req("FR-008-26")
@pytest.mark.parametrize(
    "aoi",
    [(0.0, 0.0, float("nan"), 10.0), (0.0, 0.0, float("inf"), 10.0), (10.0, 0.0, 0.0, 10.0), (0.0, 10.0, 10.0, 0.0)],
    ids=["nan", "inf", "inverted-x", "inverted-y"],
)
def test_hostile_area_of_interest_is_rejected_not_confirmed(aoi: tuple[float, float, float, float]) -> None:
    with pytest.raises(Exception):  # noqa: B017, PT011  (the error class is not fixed by the spec)
        resolve_site_name(aoi, [rect(2, 2, 4, 4)])

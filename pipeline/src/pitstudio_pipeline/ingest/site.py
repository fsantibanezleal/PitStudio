"""Bingham site-name check (FR-008-26): is the hand-typed area of interest on a pit polygon of the footprint layer?

The name "Bingham Canyon" is written as a confirmed site name only when the area-of-interest box intersects at least one
pit polygon; otherwise every derived artefact carries the label "site name provisional".
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

SITE_NAME = "Bingham Canyon"
PROVISIONAL_LABEL = "site name provisional"
Point = tuple[float, float]
Box = tuple[float, float, float, float]


def _orient(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


def _segments_meet(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """Closed segments p1p2 and p3p4 share a point (touching counts)."""
    d1, d2 = _orient(p3, p4, p1), _orient(p3, p4, p2)
    d3, d4 = _orient(p1, p2, p3), _orient(p1, p2, p4)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True
    return (
        (d1 == 0 and _on_segment(p3, p4, p1))
        or (d2 == 0 and _on_segment(p3, p4, p2))
        or (d3 == 0 and _on_segment(p1, p2, p3))
        or (d4 == 0 and _on_segment(p1, p2, p4))
    )


def _inside_box(p: Point, box: Box) -> bool:
    return box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]


def _inside_ring(p: Point, ring: Sequence[Point]) -> bool:
    """Ray casting; a point on the boundary counts as inside."""
    inside = False
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        if _orient(a, b, p) == 0 and _on_segment(a, b, p):
            return True
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
    return inside


def ring_meets_box(ring: Sequence[Point], box: Box) -> bool:
    """The polygon bounded by `ring` and the box share a point (elementary geometry, no bounding-box shortcut)."""
    pts = [(float(x), float(y)) for x, y in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if not pts:
        return False
    if any(_inside_box(p, box) for p in pts):
        return True
    corners = [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]
    if len(pts) >= 3 and any(_inside_ring(c, pts) for c in corners):
        return True
    edges = [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    box_edges = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    return any(_segments_meet(a, b, c, d) for a, b in edges for c, d in box_edges)


def resolve_site_name(aoi: Sequence[float], pit_polygons: Sequence[Sequence[Point]]) -> dict[str, Any]:
    """`{"confirmed", "site_name", "artefact_label"}` for the area of interest `(xmin, ymin, xmax, ymax)`.

    Raises `ValueError` for a non-finite or inverted box: a hand-typed box that is not a box confirms nothing.
    """
    if len(aoi) != 4 or not all(math.isfinite(float(v)) for v in aoi):
        raise ValueError("the area of interest must be four finite numbers (xmin, ymin, xmax, ymax)")
    box: Box = (float(aoi[0]), float(aoi[1]), float(aoi[2]), float(aoi[3]))
    if box[0] > box[2] or box[1] > box[3]:
        raise ValueError("the area of interest is inverted (xmin > xmax or ymin > ymax)")
    if any(ring_meets_box(ring, box) for ring in pit_polygons):
        return {"confirmed": True, "site_name": SITE_NAME, "artefact_label": None}
    return {"confirmed": False, "site_name": None, "artefact_label": PROVISIONAL_LABEL}

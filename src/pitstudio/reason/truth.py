"""Exact ground truth of the six task-A question types (FR-015-17 to FR-015-22) from a validated frame state.

Conventions (specs/015-vlm/data-model.md): transforms and footprints are already in metres, so `metersPerUnit` is never
applied again; `footprint.centre_m` is the horizontal position (x, y for a Z-up stage, x, z for a Y-up stage), the
heading is counter-clockwise from the first horizontal axis towards the second, `half_extents_m` is (along, across).

Every function returns a label or None; None means "not asked": the frame lies in a pre-registered ambiguity band or
cannot be decided from pixels, so no query is built from it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

PERSON_PX = 100  # a person counts as visible from this many pixels (FR-015-17)
TRUCK_PX = 400  # a haul truck counts as visible from this many pixels (FR-015-17, FR-015-19)
BENCH_EDGE_PX = 2000  # a bench edge is "in view" from this many pixels (FR-015-18)
NEAR_BAND_M = (27.0, 33.0)  # type 1: distances inside this closed band are not asked
NEAR_M = 30.0  # type 1: the hazard distance
TAU_YES = -math.log(0.725)  # type 4: median one-way optical depth of the onset of visibility reduction (T1 = 0.725)
TAU_NO = -math.log(0.90)  # type 4: below this the air is clear (T1 = 0.90)
GRID = (16, 9)  # type 4: columns, rows of the camera-ray grid
BLIND_EXCLUSION_M = 1.0  # type 5: a light vehicle this close to the polygon boundary is not asked
LIGHT_VEHICLE_RADIUS_M = 50.0  # type 5: light vehicles within this distance of the truck must all be visible
GRADE_HALF_SPAN_M = 5.0  # type 6: the grade is taken over +-5 m along the heading
GRADE_BAND = (0.09, 0.11)  # type 6: grades inside this closed band are not asked
_RAY_STEPS_PER_CELL = 4


def _of_class(frame: Mapping[str, Any], cls: str) -> list[Mapping[str, Any]]:
    return [o for o in frame["objects"] if o["class"] == cls]


def rect_distance(obj: Mapping[str, Any], point: Sequence[float]) -> float:
    """Distance from a horizontal point to the nearest point of an object's oriented footprint rectangle."""
    fp = obj["footprint"]
    h = math.radians(fp["heading_deg"])
    dx, dy = point[0] - fp["centre_m"][0], point[1] - fp["centre_m"][1]
    bx = math.cos(h) * dx + math.sin(h) * dy
    by = -math.sin(h) * dx + math.cos(h) * dy
    ex = max(abs(bx) - fp["half_extents_m"][0], 0.0)
    ey = max(abs(by) - fp["half_extents_m"][1], 0.0)
    return math.hypot(ex, ey)


def truth_type1(frame: Mapping[str, Any]) -> str | None:
    """Is a person within 30 m of a haul truck? (FR-015-17)"""
    persons = _of_class(frame, "person")
    trucks = _of_class(frame, "haul_truck")
    if any(p["in_frustum"] and p["visible_px"] < PERSON_PX for p in persons):
        return None
    if any(t["in_frustum"] and t["visible_px"] < TRUCK_PX for t in trucks):
        return None
    seen_persons = [p for p in persons if p["visible_px"] >= PERSON_PX]
    seen_trucks = [t for t in trucks if t["visible_px"] >= TRUCK_PX]
    dists = [rect_distance(t, p["footprint"]["centre_m"]) for p in seen_persons for t in seen_trucks]
    if any(NEAR_BAND_M[0] <= d <= NEAR_BAND_M[1] for d in dists):
        return None
    return "yes" if any(d < NEAR_BAND_M[0] for d in dists) else "no"


def truth_type2(frame: Mapping[str, Any]) -> str | None:
    """Is a berm present along the bench edge in view? (FR-015-18)

    Several edges in view that disagree on the berm flag leave the question ambiguous: not asked.
    """
    flags = {e["berm_present"] for e in frame["bench_edges"] if e["visible_px"] >= BENCH_EDGE_PX}
    if len(flags) != 1:
        return None
    return "yes" if flags.pop() else "no"


def truth_type3(frame: Mapping[str, Any]) -> str | None:
    """How many haul trucks are visible? (FR-015-19) Label "3+" stands for three or more."""
    px = [t["visible_px"] for t in _of_class(frame, "haul_truck")]
    if any(PERSON_PX <= v < TRUCK_PX for v in px):
        return None
    return ["0", "1", "2", "3+"][min(sum(1 for v in px if v >= TRUCK_PX), 3)]

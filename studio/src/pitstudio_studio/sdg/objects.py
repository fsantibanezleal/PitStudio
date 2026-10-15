"""Footprints and heights of the five perception classes as the SDG scenes place them (FR-009-01, FR-009-07).

The haul truck is the dimensioned asset of the spec 004 scene (`haul-truck-220t`: 12.8 m long, 7.3 m wide, 7.3 m to the
top of the dump body). The shovel and the light vehicle are procedural boxes and the person is the procedural
mannequin of the scene (FR-009-11: no MakeHuman export is staged on this machine); their sizes are generic public
dimensions and design assumptions of the dataset, not a model of a specific machine. Nothing here is a measurement.
"""

from __future__ import annotations

from typing import Any

from shapely import affinity
from shapely.geometry import Polygon, box

# class -> (asset id or None, length m, width m, height m)
CLASS_DIMENSIONS: dict[str, tuple[str | None, float, float, float]] = {
    "haul_truck": ("haul-truck-220t", 12.8, 7.3, 7.3),
    "shovel": (None, 15.0, 9.0, 11.0),
    "light_vehicle": (None, 5.3, 2.0, 1.9),
    "person": (None, 0.6, 0.6, 1.75),
}


def dimensions(cls: str) -> dict[str, Any]:
    """`asset_id`, `length_m`, `width_m`, `height_m` of a placeable class."""
    asset, length, width, height = CLASS_DIMENSIONS[cls]
    return {"asset_id": asset, "length_m": length, "width_m": width, "height_m": height}


def footprint(cls: str, x_m: float, y_m: float, yaw_deg: float) -> Polygon:
    """The oriented rectangle a placed object covers on the ground (length along its heading)."""
    _, length, width, _ = CLASS_DIMENSIONS[cls]
    rect = box(-length / 2.0, -width / 2.0, length / 2.0, width / 2.0)
    return affinity.translate(affinity.rotate(rect, yaw_deg, origin=(0.0, 0.0)), x_m, y_m)


def wrap_heading_deg(yaw_deg: float) -> float:
    """Heading in [-180, 180] of a yaw in [0, 360)."""
    heading = yaw_deg % 360.0
    return heading if heading <= 180.0 else heading - 360.0

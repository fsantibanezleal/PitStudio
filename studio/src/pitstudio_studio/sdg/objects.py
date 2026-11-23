"""Footprints and heights of the four perception classes as the SDG scenes place them (FR-009-01, FR-009-07).

Each class is the procedural asset of `st30_assets` (FR-004-51: the Caterpillar 793F haul truck, the Cat 7495 class rope
shovel, the Toyota Land Cruiser 79 light vehicle and the adult mannequin) and its footprint and height are the bounding
box of that asset (`scene.assets.catalogue.ENVELOPES`), so the table places exactly the volume the renderer draws.
"""

from __future__ import annotations

from typing import Any

from shapely import affinity
from shapely.geometry import Polygon, box

from pitstudio_studio.scene.assets import catalogue

# class -> (asset id, length m, width m, height m)
CLASS_DIMENSIONS: dict[str, tuple[str | None, float, float, float]] = {
    cls: (catalogue.ASSET_IDS[cls], *catalogue.ENVELOPES[cls])
    for cls in ("haul_truck", "shovel", "light_vehicle", "person")
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

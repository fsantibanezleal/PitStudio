"""The five perception classes and the boulder rule (FR-009-01)."""

from __future__ import annotations

import math

CLASSES: tuple[tuple[int, str], ...] = (
    (1, "haul_truck"),
    (2, "shovel"),
    (3, "light_vehicle"),
    (4, "person"),
    (5, "boulder"),
)
_IDS = {name: cid for cid, name in CLASSES}
_DIRECT = frozenset({"haul_truck", "shovel", "light_vehicle", "person"})  # classes whose own semantic tag is the class


def class_id(name: str) -> int:
    """COCO category id (1 to 5) of a class `name`."""
    try:
        return _IDS[name]
    except (KeyError, TypeError):
        raise ValueError(f"unknown class name {name!r}: expected one of {sorted(_IDS)}") from None


def classify_prim(semantic_tag: str, longest_axis_m: float, *, x_os_m: float = 1.0) -> str | None:
    """Class of a scene prim from its semantic tag and its longest axis; `None` when it is not a perception class.

    A rock is a `boulder` when its longest axis is at least `x_os_m` (the recipe's oversize limit).
    """
    if not math.isfinite(longest_axis_m) or longest_axis_m < 0:
        raise ValueError(f"longest_axis_m must be finite and >= 0, got {longest_axis_m!r}")
    if not math.isfinite(x_os_m) or x_os_m <= 0:
        raise ValueError(f"x_os_m must be finite and > 0, got {x_os_m!r}")
    if semantic_tag in _DIRECT:
        return semantic_tag
    if semantic_tag == "rock":
        return "boulder" if longest_axis_m >= x_os_m else None
    return None

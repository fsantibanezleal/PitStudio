"""Structured placement and unstructured draws of the perception SDG (FR-009-07, FR-009-08).

The structured arm places every vehicle and person with its footprint centroid inside a road or bench polygon and its
base within `max_base_offset_m` of the terrain; rock textures come only from the lithology's CC0 list. The unstructured
arm draws everything from its fixed ranges, independently of any physical field.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

PLACEABLE_CLASSES = ("haul_truck", "shovel", "light_vehicle", "person")
_MAX_REJECTIONS = 100_000  # draws per point before a (near-empty) region is reported instead of looping
_LIGHT_ENVELOPE = (0.1, 10.0)  # FR-009-08
_TEMPERATURE_ENVELOPE_K = (2000.0, 12000.0)  # FR-009-08
_MAX_DISTRACTORS = 20  # FR-009-08


def _finite_pair(name: str, value: Sequence[float], envelope: tuple[float, float]) -> tuple[float, float]:
    try:
        lo, hi = (float(v) for v in value)
    except TypeError, ValueError:
        raise ValueError(f"{name} must be a (min, max) pair of numbers, got {value!r}") from None
    if not (math.isfinite(lo) and math.isfinite(hi)) or lo >= hi:
        raise ValueError(f"{name} must be finite with min < max, got {value!r}")
    if lo < envelope[0] or hi > envelope[1]:
        raise ValueError(f"{name} must lie within {envelope}, got {value!r}")
    return lo, hi


def _point_in(rng: np.random.Generator, polygon: BaseGeometry) -> tuple[float, float]:
    """A point uniform over `polygon` (holes and notches excluded) by rejection from its bounding box."""
    x0, y0, x1, y1 = polygon.bounds
    for _ in range(_MAX_REJECTIONS):
        x, y = float(rng.uniform(x0, x1)), float(rng.uniform(y0, y1))
        if shapely.contains_xy(polygon, x, y):
            return x, y
    raise ValueError("no point found inside the region: it is empty or has a negligible area")


def _height(terrain_height: Callable[[float, float], float], x: float, y: float) -> float:
    h = float(terrain_height(x, y))
    if not math.isfinite(h):
        raise ValueError(f"terrain_height returned a non-finite value at ({x}, {y})")
    return h


def sample_structured_placements(
    rng: np.random.Generator,
    *,
    areas: Sequence[BaseGeometry],
    terrain_height: Callable[[float, float], float],
    object_classes: Sequence[str],
    max_base_offset_m: float = 0.05,
) -> list[dict[str, Any]]:
    """One DC-009-01 `placement` per entry of `object_classes`, centroids uniform over the union of `areas`."""
    if len(areas) == 0:
        raise ValueError("areas must hold at least one road or bench polygon")
    for c in object_classes:
        if c not in PLACEABLE_CLASSES:
            raise ValueError(f"object_classes entry {c!r} is not one of {PLACEABLE_CLASSES}")
    offset = float(max_base_offset_m)
    if not math.isfinite(offset) or offset < 0.0:
        raise ValueError(f"max_base_offset_m must be finite and >= 0, got {max_base_offset_m!r}")
    weights = np.array([float(a.area) for a in areas], dtype=np.float64)
    if not np.all(weights > 0.0):
        raise ValueError("areas must all have a positive area")
    probs = weights / weights.sum()
    out: list[dict[str, Any]] = []
    for cls in object_classes:
        area = areas[int(rng.choice(len(areas), p=probs))]
        x, y = _point_in(rng, area)
        z = _height(terrain_height, x, y) + offset * float(2.0 * rng.uniform(0.0, 1.0) - 1.0)
        out.append({"class": cls, "x_m": x, "y_m": y, "z_m": z, "yaw_deg": float(rng.uniform(0.0, 360.0))})
    return out


def sample_rock_textures(
    rng: np.random.Generator, lithology: str, lithologies: Mapping[str, Sequence[str]], *, count: int
) -> list[str]:
    """`count` texture ids drawn uniformly, with replacement, from the lithology's CC0 list."""
    ids = lithologies.get(lithology)
    if not ids:
        raise ValueError(f"lithology {lithology!r} is unknown or has an empty texture list")
    if int(count) < 1:
        raise ValueError(f"count must be >= 1, got {count!r}")
    idx = rng.integers(0, len(ids), size=int(count))
    return [str(ids[int(i)]) for i in idx]


def sample_unstructured(
    rng: np.random.Generator,
    *,
    texture_ids: Sequence[str],
    ground_region: BaseGeometry,
    terrain_height: Callable[[float, float], float],
    object_classes: Sequence[str],
    textures_per_image: int = 4,
    light_range: tuple[float, float] = _LIGHT_ENVELOPE,
    colour_temperature_range_k: tuple[float, float] = _TEMPERATURE_ENVELOPE_K,
    max_distractors: int = _MAX_DISTRACTORS,
) -> dict[str, Any]:
    """One DC-009-01 `dr_unstructured` object: every quantity drawn from its range, independently of any field."""
    if len(texture_ids) == 0:
        raise ValueError("texture_ids must hold at least one texture id")
    lo_l, hi_l = _finite_pair("light_range", light_range, _LIGHT_ENVELOPE)
    lo_t, hi_t = _finite_pair("colour_temperature_range_k", colour_temperature_range_k, _TEMPERATURE_ENVELOPE_K)
    if not 0 <= int(max_distractors) <= _MAX_DISTRACTORS:
        raise ValueError(f"max_distractors must be within 0..{_MAX_DISTRACTORS}, got {max_distractors!r}")
    if int(textures_per_image) < 1:
        raise ValueError(f"textures_per_image must be >= 1, got {textures_per_image!r}")
    for c in object_classes:
        if c not in PLACEABLE_CLASSES:
            raise ValueError(f"object_classes entry {c!r} is not one of {PLACEABLE_CLASSES}")
    # The order of the draws is part of the reproducibility contract (fixed seeds): positions first, then the rest.
    placements = []
    for cls in object_classes:
        x, y = _point_in(rng, ground_region)
        placements.append(
            {
                "class": cls,
                "x_m": x,
                "y_m": y,
                "z_m": _height(terrain_height, x, y),
                "yaw_deg": float(rng.uniform(0.0, 360.0)),
            }
        )
    tex = rng.integers(0, len(texture_ids), size=int(textures_per_image))
    light = float(10.0 ** rng.uniform(math.log10(lo_l), math.log10(hi_l)))
    light = min(max(light, lo_l), hi_l)  # guard the last-ulp rounding of the exponential
    temperature = float(rng.uniform(lo_t, hi_t))
    sin_el = float(rng.uniform(0.0, 1.0))  # z of a uniform direction on the upper hemisphere is uniform on [0, 1]
    azimuth = float(rng.uniform(0.0, 360.0))
    distractors = int(rng.integers(0, int(max_distractors) + 1))
    return {
        "texture_ids": [str(texture_ids[int(i)]) for i in tex],
        "light_intensity_factor": light,
        "colour_temperature_k": temperature,
        "sun_elevation_deg": math.degrees(math.asin(sin_el)),
        "sun_azimuth_deg": azimuth,
        "distractor_count": distractors,
        "placements": placements,
    }

"""Rollout loader: metadata checks that must pass before any frame is read (FR-011-48)."""

from __future__ import annotations

import copy
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from pitstudio.granular.errors import RolloutError

BOUNDS_INVALID = "rollout-bounds-invalid"


@dataclass(frozen=True)
class Rollout:
    meta: dict[str, Any]
    frames: np.ndarray


def validate_rollout_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the metadata when its bounds are ordered; raise RolloutError("rollout-bounds-invalid") otherwise.

    `bounds_m` is [x_min, y_min, x_max, y_max]; x_min must be below x_max and y_min below y_max (NaN is not below anything).
    """
    bounds = meta.get("bounds_m")
    if not isinstance(bounds, list | tuple) or len(bounds) != 4:
        raise RolloutError(BOUNDS_INVALID, "bounds_m must be [x_min, y_min, x_max, y_max]")
    try:
        x_min, y_min, x_max, y_max = (float(b) for b in bounds)
    except (TypeError, ValueError):
        raise RolloutError(BOUNDS_INVALID, "bounds_m holds a value that is not a number") from None
    if not all(math.isfinite(v) for v in (x_min, y_min, x_max, y_max)):
        raise RolloutError(BOUNDS_INVALID, "bounds_m holds a non-finite value")
    if not x_min < x_max:
        raise RolloutError(BOUNDS_INVALID, f"bounds_m: x_min ({x_min}) is not below x_max ({x_max})")
    if not y_min < y_max:
        raise RolloutError(BOUNDS_INVALID, f"bounds_m: y_min ({y_min}) is not below y_max ({y_max})")
    return copy.deepcopy(meta)


def load_rollout(meta: dict[str, Any], *, read_frames: Callable[[dict[str, Any]], np.ndarray]) -> Rollout:
    """Validate the metadata, then call `read_frames(meta)` once; a rejected document never reaches the reader."""
    checked = validate_rollout_metadata(meta)
    return Rollout(meta=checked, frames=read_frames(checked))

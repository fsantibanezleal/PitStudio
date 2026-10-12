"""Crusher-family instances from the 8-connected components of a semantic mask (FR-009-13).

The ovrtx crusher camera hands off semantic masks without instance ids; one instance is derived per 8-connected component
of each class value and labelled `instance_source: connected-components`. Touching boulders of the same class merge.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

_EIGHT = np.ones((3, 3), dtype=int)  # 8-connectivity
N_CLASSES = 5


@dataclass(frozen=True)
class CrusherInstance:
    """One component: category id (1..5), box `(x_min, y_min, x_max + 1, y_max + 1)` in px, pixel count."""

    category_id: int
    box_xyxy: tuple[int, int, int, int]
    area_px: int
    instance_source: str = "connected-components"


def crusher_instances(mask: np.ndarray) -> list[CrusherInstance]:
    """Instances of a 2-D integer class mask (values 0..5, 0 background), by class then raster order of first pixel."""
    if not isinstance(mask, np.ndarray) or not np.issubdtype(mask.dtype, np.integer):
        raise ValueError("mask must be a numpy integer array")
    if mask.ndim != 2 or mask.shape[0] == 0 or mask.shape[1] == 0:
        raise ValueError(f"mask must be a non-empty 2-D array, got shape {mask.shape}")
    if int(mask.min()) < 0 or int(mask.max()) > N_CLASSES:
        raise ValueError(f"mask values must lie in 0..{N_CLASSES}")
    out: list[CrusherInstance] = []
    for category in range(1, N_CLASSES + 1):
        present = mask == category
        if not present.any():
            continue
        labels, count = ndimage.label(present, structure=_EIGHT)  # labels follow the raster order of first pixels
        areas = np.bincount(labels.ravel(), minlength=count + 1)
        for k, (rows, cols) in enumerate(ndimage.find_objects(labels), start=1):
            out.append(
                CrusherInstance(
                    category_id=category,
                    box_xyxy=(int(cols.start), int(rows.start), int(cols.stop), int(rows.stop)),
                    area_px=int(areas[k]),
                )
            )
    return out

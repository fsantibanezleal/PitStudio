"""Three-class target encoding and instance decoding (spec 012, FR-012-18, FR-012-19)."""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from skimage.segmentation import watershed

MIN_SEED_AREA = 4  # FR-012-19: interior components below this area are not instances
BACKGROUND, INTERIOR, BOUNDARY = 0, 1, 2


def encode_three_class(label: np.ndarray) -> np.ndarray:
    """FR-012-18: 0 background, 2 boundary (foreground with an 8-neighbour of another label value), 1 interior.

    Neighbours outside the image count as background, so foreground touching the image edge is boundary.
    """
    label = np.asarray(label)
    if label.ndim != 2:
        raise ValueError(f"label must be 2-D, got shape {label.shape}")
    h, w = label.shape
    padded = np.pad(label, 1, mode="constant", constant_values=0)
    differs = np.zeros((h, w), dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                differs |= padded[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w] != label
    out = np.zeros((h, w), dtype=np.uint8)
    foreground = label != 0
    out[foreground] = INTERIOR
    out[foreground & differs] = BOUNDARY
    return out


def decode_instances(probs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """FR-012-19: instances (int32, 0 = unassigned, ids 1..n) and the predicted foreground (bool).

    Seeds are the 4-connected components of predicted interior pixels with area >= 4; boundary pixels join an adjacent
    seed by marker-controlled watershed on the boundary probability, restricted to the predicted foreground.
    """
    probs = np.asarray(probs)
    if probs.ndim != 3 or probs.shape[0] != 3:
        raise ValueError(f"probs must have shape (3, H, W), got {probs.shape}")
    predicted = probs.argmax(axis=0)
    interior = predicted == INTERIOR
    foreground = interior | (predicted == BOUNDARY)
    components, n = ndimage.label(interior)  # default structure: 4-connectivity
    areas = np.bincount(components.ravel(), minlength=n + 1)
    keep = areas >= MIN_SEED_AREA
    keep[0] = False
    remap = np.cumsum(keep, dtype=np.int32) * keep  # consecutive ids 1..n over the kept components
    markers = remap[components].astype(np.int32)
    if not markers.any():
        return np.zeros(predicted.shape, dtype=np.int32), foreground
    instances = watershed(probs[BOUNDARY], markers=markers, mask=foreground, connectivity=1)
    return instances.astype(np.int32), foreground

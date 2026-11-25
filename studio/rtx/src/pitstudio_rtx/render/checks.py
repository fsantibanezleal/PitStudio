# SPDX-License-Identifier: Apache-2.0
"""Image checks of the render run: exposure (linear luminance), distinct stills (grey-level difference), light gain.

Image differences are in 8-bit grey levels (0..255). The noise floor is measured, not assumed: the run renders the
first pose, steps once more without moving anything and takes the mean absolute difference of the two images; the
distinct threshold is a recipe-stated multiple of that floor with a recipe-stated minimum.
"""

from __future__ import annotations

import numpy as np

REC709 = np.array([0.2126, 0.7152, 0.0722])
MIN_GAIN_RATIO = 1e-6


def _linear(srgb: np.ndarray) -> np.ndarray:
    c = srgb.astype(np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def luminance(image: np.ndarray) -> float:
    """Mean linear Rec. 709 luminance (0 black, 1 white) of an 8-bit sRGB image (height, width, 3)."""
    return float((_linear(image) @ REC709).mean())


def mean_abs_diff(a: np.ndarray, b: np.ndarray) -> float:
    """Mean absolute difference of two same-shape 8-bit images, in grey levels."""
    if a.shape != b.shape:
        raise ValueError(f"image shape differs: {a.shape} against {b.shape}")
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


def distinct_threshold(noise_floor: float, *, minimum: float, factor: float) -> float:
    """The smallest mean absolute difference (grey levels) that makes two stills different views."""
    return max(float(minimum), float(factor) * float(noise_floor))


def first_clash(image: np.ndarray, others: dict[str, np.ndarray], threshold: float) -> tuple[str, float] | None:
    """`(name, difference)` of the first image in `others` whose difference to `image` is below `threshold`."""
    for name, other in others.items():
        diff = mean_abs_diff(image, other)
        if diff < threshold:
            return name, diff
    return None


def gain_for(measured: float, target: float, gain: float, *, limit: float) -> float:
    """The light gain that moves a measured mean luminance to the target, assuming luminance is linear in the gain."""
    wanted = gain * target / max(measured, MIN_GAIN_RATIO)
    return float(min(max(wanted, 1.0 / limit), limit))

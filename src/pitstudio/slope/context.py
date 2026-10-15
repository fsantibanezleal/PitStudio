"""The 128-value context of the learned forecasters (FR-010-21), numpy only.

The 512 inverse-velocity samples of the shared window are reduced to 128 block means of 4 consecutive samples (the
mean of the
valid samples of the block; a block without any valid sample is masked), masked blocks are forward-filled with the
previous
block (a leading masked block takes the first valid value), the result is divided by the mean ``|y|`` of the filled
blocks, and
a mask channel records which blocks carry data. TCN and PatchTST read both channels; the scale is returned so that the
forecast
can be put back in the units of y.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pitstudio.slope.errors import InvalidWindowError
from pitstudio.slope.preprocess import Window

CONTEXT_LENGTH = 128
BLOCK = 4


@dataclass(frozen=True)
class Context:
    """``context`` is float32 (2, 128): the scaled inverse velocity and the mask; ``scale`` is the mean |y| (> 0)."""

    context: np.ndarray
    scale: float


def build_context(window: Window) -> Context:
    """The scaled, forward-filled block-mean context of a pre-processed window (``InvalidWindowError`` if unusable)."""
    y = np.asarray(window.y, dtype=float)
    if y.shape != (CONTEXT_LENGTH * BLOCK,):
        raise InvalidWindowError(f"the window must have {CONTEXT_LENGTH * BLOCK} samples, got shape {y.shape}")
    blocks = y.reshape(CONTEXT_LENGTH, BLOCK)
    valid = np.isfinite(blocks)
    has = valid.any(axis=1)
    if not has.any():
        raise InvalidWindowError("no positive velocity in the window: there is nothing to forecast")
    sums = np.where(valid, blocks, 0.0).sum(axis=1)
    means = np.where(has, sums / np.maximum(valid.sum(axis=1), 1), np.nan)
    filled = means.copy()
    first = int(np.argmax(has))
    filled[:first] = means[first]
    for b in range(first + 1, CONTEXT_LENGTH):
        if not has[b]:
            filled[b] = filled[b - 1]
    scale = float(np.abs(filled).mean())
    if not (np.all(np.isfinite(filled)) and np.isfinite(scale) and scale > 0.0):
        raise InvalidWindowError("the filled context is not finite")
    context = np.empty((2, CONTEXT_LENGTH), dtype=np.float32)
    context[0] = filled / scale
    context[1] = has.astype(np.float32)
    return Context(context, scale)

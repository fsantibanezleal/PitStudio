# SPDX-License-Identifier: Apache-2.0
"""Input checks shared by the robot-learning reference cores (FR-014-10, FR-014-47).

Every check raises ``ValueError`` whose message holds the name of the offending argument as a whole word.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np


def finite(name: str, value: float) -> float:
    """Return ``value`` as a float, raising when it is not a finite real number."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number, got {value!r}") from exc
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return x


def positive(name: str, value: float) -> float:
    x = finite(name, value)
    if x <= 0.0:
        raise ValueError(f"{name} must be > 0, got {value!r}")
    return x


def non_negative(name: str, value: float) -> float:
    x = finite(name, value)
    if x < 0.0:
        raise ValueError(f"{name} must be >= 0, got {value!r}")
    return x


def vector(name: str, value: Sequence[float] | np.ndarray, size: int | None = None, *, min_size: int = 0) -> np.ndarray:
    """A 1-D float64 copy of ``value`` with only finite entries (and the required size)."""
    try:
        arr = np.array(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a numeric 1-D array, got {value!r}") from exc
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D, got shape {arr.shape}")
    if size is not None and arr.shape[0] != size:
        raise ValueError(f"{name} must have {size} entries, got {arr.shape[0]}")
    if arr.shape[0] < max(min_size, 1 if size is None else 0):
        raise ValueError(f"{name} must hold at least {max(min_size, 1)} entries, got {arr.shape[0]}")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} holds a non-finite entry")
    return arr

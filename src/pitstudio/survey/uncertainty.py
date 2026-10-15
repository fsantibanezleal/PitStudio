"""Volume uncertainty bounds from the per-epoch RMSEz (FR-017-33)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class UncertaintyBounds:
    uncorrelated_m3: float
    correlated_m3: float


def _non_negative(value: float, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be a finite number {'> 0' if positive else '>= 0'}, got {value!r}")
    return float(value)


def volume_uncertainty(n_valid: int, cell_size_m: float, sigma0_m: float, sigma1_m: float) -> UncertaintyBounds:
    """Uncorrelated A_c sqrt(N) s and fully correlated A_c N s, with s = sqrt(sigma0^2 + sigma1^2)."""
    if isinstance(n_valid, bool) or not isinstance(n_valid, int) or n_valid < 1:
        raise ValueError(f"n_valid must be a positive integer, got {n_valid!r}")
    cell = _non_negative(cell_size_m, "cell_size_m", positive=True)
    s0 = _non_negative(sigma0_m, "sigma0_m")
    s1 = _non_negative(sigma1_m, "sigma1_m")
    combined = math.hypot(s0, s1)
    area = cell * cell
    return UncertaintyBounds(area * math.sqrt(n_valid) * combined, area * n_valid * combined)

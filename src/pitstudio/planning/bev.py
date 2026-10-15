"""Block values and integer cents (FR-017-12, P-017-06)."""

from __future__ import annotations

import numpy as np

INT64_MAX_F = 2.0**63


def block_values(
    tonnage: np.ndarray,
    grade: np.ndarray,
    *,
    lam: float,
    recovery: float,
    net_price: float,
    processing_cost: float,
    mining_cost: float,
) -> np.ndarray:
    """v = max(T [lam g r (p - s_r) - c_p] - T c_m, -T c_m) in USD per block."""
    t = np.asarray(tonnage, dtype=np.float64)
    g = np.asarray(grade, dtype=np.float64)
    ore = t * (lam * g * recovery * net_price - processing_cost) - t * mining_cost
    return np.maximum(ore, -t * mining_cost)


def breakeven_grade(*, recovery: float, net_price: float, processing_cost: float) -> float:
    """c_p / (r (p - s_r)): the grade at which ore pays for processing."""
    return processing_cost / (recovery * net_price)


def to_cents(values: np.ndarray) -> np.ndarray:
    """int64 of round-half-even(v x 100); ValueError for a non-finite value or cents beyond int64."""
    v = np.asarray(values, dtype=np.float64)
    if not np.isfinite(v).all():
        raise ValueError("values must be finite")
    cents = np.rint(v * 100.0)
    if (np.abs(cents) >= INT64_MAX_F).any():
        raise ValueError("a value in cents exceeds int64")
    return cents.astype(np.int64)

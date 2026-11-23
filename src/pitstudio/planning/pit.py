"""Ultimate pit: the minimal maximum-weight closure through `minephys.planning` (FR-017-14, P-017-01..05)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from minephys.planning import ultimate_pit_mincut

# The minephys min-cut runs in binary64: every capacity, flow and residual is an integer below 2^53, so the result is
# exact exactly when the sum of the absolute values stays below that bound (plan 017, tolerances).
EXACT_BOUND = 2**53


@dataclass(frozen=True)
class Pit:
    mask: np.ndarray  # bool (n,)
    value: int  # sum of the values (cents) of the blocks in the pit


def _check_values(values: np.ndarray) -> np.ndarray:
    if not isinstance(values, np.ndarray) or values.dtype != np.int64 or values.ndim != 1 or values.size < 1:
        raise ValueError("values must be a non-empty one-dimensional int64 array (cents)")
    if int(np.abs(values).sum(dtype=object)) >= EXACT_BOUND:
        raise ValueError("values: the sum of absolute values reaches 2^53, the exact range of the min-cut")
    return values


def _check_arcs(arcs: np.ndarray, n: int) -> np.ndarray:
    a = np.asarray(arcs)
    if a.size == 0 and a.ndim in (1, 2):
        return np.empty((0, 2), dtype=np.int64)
    if a.ndim != 2 or a.shape[1] != 2 or not np.issubdtype(a.dtype, np.integer):
        raise ValueError("arcs must be an (m, 2) array of integer block indices")
    if (a < 0).any() or (a >= n).any():
        raise ValueError(f"arcs name a block outside 0..{n - 1}")
    if (a[:, 0] == a[:, 1]).any():
        raise ValueError("arcs contain a self-arc")
    return a.astype(np.int64, copy=False)


def ultimate_pit(values: np.ndarray, arcs: np.ndarray) -> Pit:
    """Minimal maximum-weight closed set; `arcs` rows (i, j) mean block i requires block j."""
    v = _check_values(values)
    a = _check_arcs(arcs, int(v.size))
    mask = np.asarray(ultimate_pit_mincut(v.astype(np.float64), a).mask, dtype=bool)
    return Pit(mask=mask, value=int(v[mask].sum(dtype=object)) if mask.any() else 0)

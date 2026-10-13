"""Radius graph of the GNS (FR-011-02, FR-011-13): padded neighbour lists, binary64 squared distances.

Particle j is a neighbour of i when j != i and |x_i - x_j|^2 < R^2 (strict). The squared distance is computed in
binary64
from the binary32 positions (this module accepts either dtype and widens). Lists are ordered by (squared distance,
index),
the first `k_max` are kept and a particle with more neighbours than that is counted in `overflow_count`. The TypeScript
twin (`web/src/engines/gns/radiusGraph.ts`) returns identical arrays.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pitstudio.granular.errors import InvalidGraphError

K_MAX = 32
_CHUNK = 256  # rows of the distance matrix handled at once: bounds memory at 256 x N binary64 values


@dataclass(frozen=True)
class RadiusGraph:
    """Padded neighbour lists. Masked-off entries of `neighbour_index` hold the particle's own index (a valid
    gather)."""

    neighbour_index: np.ndarray  # int64 [N, k_max]
    neighbour_mask: np.ndarray  # bool [N, k_max]
    overflow_count: int


def validate_positions(positions: np.ndarray) -> np.ndarray:
    """Return `positions` as an array after checking shape [N, 2], N >= 1 and finiteness; raise InvalidGraphError."""
    arr = np.asarray(positions)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise InvalidGraphError(f"positions must have shape [N, 2], got {list(arr.shape)}")
    if arr.shape[0] == 0:
        raise InvalidGraphError("N = 0: no particles")
    if not np.issubdtype(arr.dtype, np.floating) and not np.issubdtype(arr.dtype, np.integer):
        raise InvalidGraphError(f"positions must be numeric, got dtype {arr.dtype}")
    if not np.isfinite(arr).all():
        raise InvalidGraphError("positions contain a non-finite value")
    return arr


def build_radius_graph(positions: np.ndarray, radius: float, k_max: int = K_MAX) -> RadiusGraph:
    """Connect particles closer than `radius`; at most `k_max` neighbours each, ordered by (distance, index)."""
    pos = validate_positions(positions)
    if not isinstance(radius, int | float | np.floating) or not np.isfinite(radius) or radius <= 0:
        raise InvalidGraphError(f"the connectivity radius must be a positive finite number, got {radius!r}")
    if k_max < 1:
        raise InvalidGraphError(f"k_max must be at least 1, got {k_max}")
    p = pos.astype(np.float64)
    n = p.shape[0]
    r2 = float(radius) * float(radius)
    index = np.repeat(np.arange(n, dtype=np.int64)[:, None], k_max, axis=1)
    mask = np.zeros((n, k_max), dtype=bool)
    overflow = 0
    width = min(k_max, n)
    for lo in range(0, n, _CHUNK):
        hi = min(lo + _CHUNK, n)
        dx = p[lo:hi, None, 0] - p[None, :, 0]
        dy = p[lo:hi, None, 1] - p[None, :, 1]
        d2 = dx * dx + dy * dy
        rows = np.arange(hi - lo)
        d2[rows, np.arange(lo, hi)] = np.inf  # no self-edge
        valid = d2 < r2
        overflow += int((valid.sum(axis=1) > k_max).sum())
        d2 = np.where(valid, d2, np.inf)
        order = np.argsort(d2, axis=1, kind="stable")[:, :width]  # stable: equal distances keep the lower index first
        kept = np.take_along_axis(valid, order, axis=1)
        index[lo:hi, :width] = np.where(kept, order, index[lo:hi, :width])
        mask[lo:hi, :width] = kept
    return RadiusGraph(neighbour_index=index, neighbour_mask=mask, overflow_count=overflow)

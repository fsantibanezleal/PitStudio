"""Radius graph on the training device (FR-011-02 semantics, P-011-04 parity with the CPU builder).

`pitstudio.granular.graph.build_radius_graph` stays the oracle and the web reference; this builder returns the same
arrays (int64 `neighbour_index`, bool `neighbour_mask`, the overflow count) computed with torch in binary64 from the
binary32 positions: strict `d^2 < R^2`, no self-edge, lists ordered by (d^2, index) through a stable sort, masked
entries holding the particle's own index. Rows are handled in blocks so that memory is bounded at `block x N`
binary64 values.
"""

from __future__ import annotations

import torch

from pitstudio.granular.graph import K_MAX

_BLOCK = 512


def build_radius_graph_torch(
    positions: torch.Tensor, radius: float, k_max: int = K_MAX, *, block: int = _BLOCK
) -> tuple[torch.Tensor, torch.Tensor, int]:
    """Return (neighbour_index [N, k_max] int64, neighbour_mask [N, k_max] bool, overflow_count), on the device."""
    p = positions.to(torch.float64)
    n = p.shape[0]
    r2 = float(radius) * float(radius)
    device = p.device
    index = torch.arange(n, device=device, dtype=torch.int64)[:, None].repeat(1, k_max)
    mask = torch.zeros((n, k_max), device=device, dtype=torch.bool)
    width = min(k_max, n)
    overflow = torch.zeros((), device=device, dtype=torch.int64)
    inf = float("inf")
    for lo in range(0, n, block):
        hi = min(lo + block, n)
        dx = p[lo:hi, None, 0] - p[None, :, 0]
        dy = p[lo:hi, None, 1] - p[None, :, 1]
        d2 = dx * dx + dy * dy
        rows = torch.arange(hi - lo, device=device)
        d2[rows, torch.arange(lo, hi, device=device)] = inf
        valid = d2 < r2
        overflow += (valid.sum(dim=1) > k_max).sum()
        d2 = torch.where(valid, d2, torch.full_like(d2, inf))
        order = torch.sort(d2, dim=1, stable=True).indices[:, :width]
        kept = torch.gather(valid, 1, order)
        index[lo:hi, :width] = torch.where(kept, order, index[lo:hi, :width])
        mask[lo:hi, :width] = kept
    return index, mask, int(overflow)

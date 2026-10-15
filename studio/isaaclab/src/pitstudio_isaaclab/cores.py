# SPDX-License-Identifier: Apache-2.0
"""Vectorised torch versions of the FEE wedge and the fill model used by the Isaac Lab tasks (P-014-15).

They mirror ``pitstudio.robots.fee`` and ``pitstudio.robots.fill`` (the NumPy float64 references): the same factor form,
the failure angle beta* from the root of dF/dbeta by bisection around the grid minimum, and the fill step with the
1.15 V_h cap. All inputs are tensors of shape (n,); everything runs in the dtype of the inputs (float32 in the tasks).
"""

from __future__ import annotations

import math

import torch

FILL_CAP = 1.15
G = 9.81
GRID = 129
BISECTIONS = 30


def _cot(x: torch.Tensor) -> torch.Tensor:
    return 1.0 / torch.tan(x)


def _force_and_factors(
    u: torch.Tensor, alpha: torch.Tensor, delta: torch.Tensor, phi: torch.Tensor, a_w: torch.Tensor,
    b_c: torch.Tensor, c_ca: torch.Tensor,
) -> torch.Tensor:  # fmt: skip
    """F / w at failure angle u (broadcast against the inputs)."""
    s = alpha + delta
    cot_up = _cot(u + phi)
    d_term = torch.cos(s) + torch.sin(s) * cot_up
    num = a_w * (_cot(alpha) + _cot(u)) + b_c * (1.0 + _cot(u) * cot_up) + c_ca * (1.0 - _cot(alpha) * cot_up)
    return num / d_term


def _dforce(
    u: torch.Tensor, alpha: torch.Tensor, delta: torch.Tensor, phi: torch.Tensor, a_w: torch.Tensor,
    b_c: torch.Tensor, c_ca: torch.Tensor,
) -> torch.Tensor:  # fmt: skip
    s = alpha + delta
    cot_a, cot_u, cot_up = _cot(alpha), _cot(u), _cot(u + phi)
    csc2_u, csc2_up = 1.0 + cot_u * cot_u, 1.0 + cot_up * cot_up
    d_term = torch.cos(s) + torch.sin(s) * cot_up
    n_val = a_w * (cot_a + cot_u) + b_c * (1.0 + cot_u * cot_up) + c_ca * (1.0 - cot_a * cot_up)
    n_der = -a_w * csc2_u + b_c * (-csc2_u * cot_up - cot_u * csc2_up) + c_ca * cot_a * csc2_up
    d_der = -torch.sin(s) * csc2_up
    return n_der * d_term - n_val * d_der


def solve_fee(
    *, alpha: torch.Tensor, delta: torch.Tensor, phi: torch.Tensor, rho: torch.Tensor, c: torch.Tensor,
    c_a: torch.Tensor, q: torch.Tensor, d: torch.Tensor, w: torch.Tensor, g: float = G,
) -> dict[str, torch.Tensor]:  # fmt: skip
    """beta, force, draft and vertical of the minimum-force failure wedge (FR-014-17), one entry per state."""
    hi = torch.minimum(torch.full_like(alpha, math.pi / 2.0), math.pi - alpha - delta - phi)
    a_w = 0.5 * rho * g * d * d + q * d
    b_c = c * d
    c_ca = c_a * d
    frac = torch.linspace(1e-6, 1.0 - 1e-6, GRID, dtype=alpha.dtype, device=alpha.device)
    grid = hi[:, None] * frac[None, :]
    args = [t[:, None] for t in (alpha, delta, phi, a_w, b_c, c_ca)]
    values = _force_and_factors(grid, *args)
    i_min = values.argmin(dim=1)
    lo_i = (i_min - 1).clamp(min=0)
    hi_i = (i_min + 1).clamp(max=GRID - 1)
    lo = grid.gather(1, lo_i[:, None])[:, 0]
    up = grid.gather(1, hi_i[:, None])[:, 0]
    bracketed = (_dforce(lo, alpha, delta, phi, a_w, b_c, c_ca) <= 0.0) & (
        _dforce(up, alpha, delta, phi, a_w, b_c, c_ca) > 0.0
    )
    for _ in range(BISECTIONS):
        mid = 0.5 * (lo + up)
        below = _dforce(mid, alpha, delta, phi, a_w, b_c, c_ca) < 0.0
        lo = torch.where(below, mid, lo)
        up = torch.where(below, up, mid)
    beta = torch.where(bracketed, 0.5 * (lo + up), grid.gather(1, i_min[:, None])[:, 0])
    force = _force_and_factors(beta, alpha, delta, phi, a_w, b_c, c_ca) * w
    force = torch.where((d == 0) | (w == 0), torch.zeros_like(force), force)
    s = alpha + delta
    return {"beta": beta, "force": force, "draft": force * torch.sin(s), "vertical": force * torch.cos(s)}


def fill_step(
    v_fill: torch.Tensor, *, depth: torch.Tensor, ds: torch.Tensor, width: torch.Tensor, v_heaped: torch.Tensor,
    cutting: torch.Tensor | None = None,
) -> torch.Tensor:  # fmt: skip
    """New fill volume of one cutting step: V + w d |ds| capped at 1.15 V_h (unchanged where not cutting)."""
    new = torch.minimum(v_fill + width * depth * ds, FILL_CAP * v_heaped)
    return new if cutting is None else torch.where(cutting, new, v_fill)

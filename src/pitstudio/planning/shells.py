"""Nested pit shells over the revenue-factor grid and their bitset encoding (FR-017-16, P-017-03)."""

from __future__ import annotations

import base64
import itertools
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from pitstudio.planning.bev import block_values, to_cents
from pitstudio.planning.pit import ultimate_pit

LAMBDA_GRID: tuple[float, ...] = tuple(k / 40 for k in range(1, 41))  # 0.025, 0.050, ..., 1.000


def encode_bitset(mask: np.ndarray) -> str:
    """bitset-lsb0-base64: bit i is bit (i % 8) of byte i // 8, standard base64 with padding."""
    m = np.asarray(mask, dtype=bool)
    return base64.b64encode(np.packbits(m, bitorder="little").tobytes()).decode("ascii")


def decode_bitset(text: str, n: int) -> np.ndarray:
    raw = np.frombuffer(base64.b64decode(text, validate=True), dtype=np.uint8)
    if len(raw) * 8 < n:
        raise ValueError(f"bitset holds {len(raw) * 8} bits, {n} needed")
    return np.unpackbits(raw, bitorder="little")[:n].astype(bool)


@dataclass(frozen=True)
class ShellTable:
    rows: list[dict]
    masks: list[np.ndarray]
    ultimate_pit: dict


def compute_shells(
    tonnage: np.ndarray,
    grade: np.ndarray,
    arcs: np.ndarray,
    *,
    recovery: float,
    net_price: float,
    processing_cost: float,
    mining_cost: float,
    lambdas: Sequence[float] = LAMBDA_GRID,
) -> ShellTable:
    """One pit per revenue factor on the cents of `block_values`; ore means lambda g r p - c_p > 0."""
    lams = [float(x) for x in lambdas]
    if not lams or any(b <= a for a, b in itertools.pairwise(lams)) or lams[0] <= 0 or lams[-1] > 2:
        raise ValueError("lambdas must be non-empty, increasing and within (0, 2]")
    t = np.asarray(tonnage, dtype=np.float64)
    g = np.asarray(grade, dtype=np.float64)
    rows: list[dict] = []
    masks: list[np.ndarray] = []
    last_value = 0
    for lam in lams:
        cents = to_cents(
            block_values(
                t,
                g,
                lam=lam,
                recovery=recovery,
                net_price=net_price,
                processing_cost=processing_cost,
                mining_cost=mining_cost,
            )
        )
        pit = ultimate_pit(cents, arcs)
        ore = (lam * g * recovery * net_price - processing_cost) > 0
        ore_t = float(t[pit.mask & ore].sum())
        waste_t = float(t[pit.mask & ~ore].sum())
        rows.append(
            {
                "lambda": lam,
                "blocks": encode_bitset(pit.mask),
                "block_count": int(pit.mask.sum()),
                "ore_t": ore_t,
                "waste_t": waste_t,
                "value_cents": pit.value,
                "strip_ratio": waste_t / ore_t if ore_t > 0 else None,
            }
        )
        masks.append(pit.mask)
        last_value = pit.value
    ultimate = {"shell": len(rows) - 1, "value_cents": last_value, "strip_ratio": rows[-1]["strip_ratio"]}
    return ShellTable(rows=rows, masks=masks, ultimate_pit=ultimate)

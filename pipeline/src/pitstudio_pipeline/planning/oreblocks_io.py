"""`oreblocks` synthetic deposits as planner inputs: tonnage, grade, precedence arcs, economics, stamped optimum
(FR-017-12, FR-017-15, FR-017-51)."""

from __future__ import annotations

import hashlib
import importlib.metadata
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TwinInstance:
    name: str
    archetype: str
    dims: tuple[int, int, int]
    seed: int
    block_size_m: tuple[float, float, float]
    tonnage: np.ndarray  # t per block
    grade: np.ndarray  # mass fraction
    arcs: np.ndarray  # int64 (m, 2): block i requires block j (above it)
    values: np.ndarray  # USD per block at lambda = 1, from oreblocks
    econ: dict  # price, recovery, mining_cost, processing_cost
    slope_deg: float
    stamped_pit_value_usd: float
    stamped_pit_mask: np.ndarray
    version: str

    @property
    def n_blocks(self) -> int:
        return int(self.tonnage.size)

    def sha256(self) -> str:
        """Digest of the block model: tonnage, grade and arcs as little-endian binary64 / int64 bytes."""
        h = hashlib.sha256()
        for arr in (self.tonnage.astype("<f8"), self.grade.astype("<f8"), self.arcs.astype("<i8")):
            h.update(arr.tobytes())
        return h.hexdigest()


def twin_instance(archetype: str, dims: tuple[int, int, int], seed: int) -> TwinInstance:
    """A seeded `oreblocks` deposit with its own precedence and its exactly solved stamped optimum."""
    from oreblocks import make_twin

    twin = make_twin(archetype, dims, seed)
    prec = twin.precedence
    arcs = np.array(
        [(b, int(p)) for b in range(len(prec.pstart) - 1) for p in prec.plist[prec.pstart[b] : prec.pstart[b + 1]]],
        dtype=np.int64,
    ).reshape(-1, 2)
    g = twin.deposit.grid
    e = twin.econ
    return TwinInstance(
        name=twin.name,
        archetype=archetype,
        dims=tuple(dims),  # type: ignore[arg-type]
        seed=seed,
        block_size_m=(float(g.dx), float(g.dy), float(g.dz)),
        tonnage=np.asarray(twin.deposit.tonnage, dtype=np.float64),
        grade=np.asarray(twin.deposit.grade, dtype=np.float64),
        arcs=arcs,
        values=np.asarray(twin.values, dtype=np.float64),
        econ={
            "price": float(e.price),
            "recovery": float(e.recovery),
            "mining_cost": float(e.mining_cost),
            "processing_cost": float(e.processing_cost),
        },
        slope_deg=float(twin.slope_deg),
        stamped_pit_value_usd=float(twin.upit.pit_value),
        stamped_pit_mask=np.asarray(twin.upit.in_pit, dtype=bool),
        version=importlib.metadata.version("oreblocks"),
    )

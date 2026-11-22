"""Parameter space, geometry records, split plan and the contract metric of the planar reference data (spec 011,
FR-011-03).

Pure Python and NumPy: nothing here imports Warp, so the plan can be checked on any machine. Lengths inside a parameter
set are in particle diameters (`*_D`), the metadata of DC-011-01 is in metres. Three families:

- column collapse: a settled column of width L0 and height a L0 against a wall, released (unchanged from gns-v2);
- pile formation: N grains drain from a funnel hopper whose orifice (width `w_o_D`) is `z_o_D` above the floor; the pile
  grows under the orifice (a quasi-static feed: no free-fall curtain, no jam at the calibrated friction);
- dump over a crest: the same hopper stands `x_off_D` left of the crest of a platform of height `h_c_D` and pours onto
  the platform, the grains run over the crest and build the flank below it.

The feed rate is MEASURED (slope of the cumulative solid area that crossed the orifice level) and recorded as the
contract's `pour_rate_m2_per_s` / `dump_rate_m2_per_s`; the hopper walls are generator-side obstacles and are not part
of
the recorded particle set.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

G = 9.81
D = 0.01  # nominal (mean) particle diameter, m
POLY = 0.2  # diameters D * U(1 - POLY, 1 + POLY)
MASTER_SEED = 20261011
LABEL = "calibrated synthetic — not validated against real data"
REST_FRAC = 0.01  # FR-011-10: rest when the maximum speed is below 0.01 sqrt(g d)
REST_FRAMES = 3  # the rest condition must hold on this many consecutive frames
MIN_HEIGHT_D = 30.0  # FR-011-03: piles at least 30 d high
STEPS_PER_FRAME = 420  # = 6 graph launches of 70 steps
GRAPH_K = 70
CELL_AREA = 0.97  # x-z area per particle of a settled polydisperse disc packing, D^2
PART_AREA = math.pi / 4.0 * 1.013  # nominal solid area per particle, D^2 (E[u^2] of U(0.8, 1.2) is 1.013)
N_MAX_COLLAPSE = 6500
LOOSE_PITCH = 1.45  # column fill pitch, D
BOX_HALF = 220.0  # half width of the pile / dump domain, D
GAP_D = 8.0  # separation of the independent rollouts of one batch, D
FAMILIES = ("column-collapse", "pile-formation", "dump-over-crest")
SPLIT_ORDER = ("val", "train", "test")  # validation geometries first: the 70 + 10 set exists before the test set
SPLIT_COUNTS = {
    "train": {"column-collapse": 33, "pile-formation": 18, "dump-over-crest": 19},
    "val": {"column-collapse": 4, "pile-formation": 3, "dump-over-crest": 3},
    "test": {"column-collapse": 8, "pile-formation": 6, "dump-over-crest": 6},
}
SEEDS_PER_GEOMETRY = 3
MAX_GEOM_ATTEMPTS = 12
MAX_SEED_ATTEMPTS = 8
T_CAP = {"column-collapse": 12.0, "pile-formation": 40.0, "dump-over-crest": 40.0}  # s of simulated time
MIN_DISTANCE = 0.05  # FR-011-03: test geometries at least this far from every training geometry (contract metric)

# Collapse: measured lower envelope of final height / L0 against a (2-D calibration of gns-v2, 20 collapses).
RATIO_A = [0.5, 0.6, 0.8, 1.0, 1.3, 1.6, 2.0, 2.5, 3.0, 4.0]
RATIO_F = [0.49, 0.55, 0.62, 0.66, 0.76, 0.80, 0.87, 0.92, 0.98, 1.07]

# Feed families (quasi-static hopper feed). The orifice-width range is set from the calibration (jam-free at the
# calibrated friction); every other range is a design choice recorded in the dataset card.
N_FEED = 4000
HOPPER_W_D = 60.0  # interior width of the hopper
FUNNEL_DEG = 65.0  # wall angle of the funnel plates from the horizontal (mass flow in a planar hopper)
FEED_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "pile-formation": {"x_p_D": (-20.0, 20.0), "z_o_D": (50.0, 125.0), "w_o_D": (12.0, 20.0)},
    "dump-over-crest": {
        "x_c_D": (-20.0, 20.0),
        "h_c_D": (9.0, 22.0),
        "z_o_D": (50.0, 100.0),
        "w_o_D": (12.0, 20.0),
        "x_off_D": (8.0, 20.0),
    },
}

# The training envelope of DC-011-02 (data.FAMILY_RANGES of the pipeline, spec 011 section 7): the design envelope the
# dataset records. pour height is the orifice height above the floor; the rates are the measured steady discharge rates.
CONTRACT_RANGES: dict[str, tuple[tuple[str, float, float], ...]] = {
    "column-collapse": (("aspect_ratio", 0.5, 4.0), ("column_width_m", 0.32, 0.70)),
    "pile-formation": (("pour_height_m", 0.05, 0.40), ("pour_rate_m2_per_s", 0.79, 1.45)),
    "dump-over-crest": (("crest_height_m", 0.09, 0.22), ("dump_rate_m2_per_s", 0.76, 1.23)),
}


@dataclasses.dataclass(frozen=True)
class SimConfig:
    """Contact parameters of the planar effective material and the derived step (spec 005 slot card otherwise)."""

    mu_r: float
    mu_s: float
    poly: float = POLY

    @property
    def material(self):
        from pitstudio_studio.physics.dem.benchmarks import SLOT_MATERIAL

        return dataclasses.replace(SLOT_MATERIAL, friction_rolling=self.mu_r, friction_static=self.mu_s)

    @property
    def dt(self) -> float:
        from pitstudio_studio.physics.dem.step import rayleigh_time_step

        return 0.2 * rayleigh_time_step(self.material, (1.0 - self.poly) * D / 2.0) * 0.75

    @property
    def frame_dt(self) -> float:
        return STEPS_PER_FRAME * self.dt

    def record(self) -> dict[str, Any]:
        """The `material` object of DC-011-01 (a declared recipe, not a knowledge-table row)."""
        m = self.material

        def mv(v: float) -> dict[str, Any]:
            return {"value": float(v), "source": "recipe"}

        return {
            "density_kg_per_m3": mv(m.density),
            "sliding_friction": mv(m.friction_static),
            "rolling_friction": mv(m.friction_rolling),
            "restitution": mv(m.restitution),
            "youngs_modulus_pa": mv(m.youngs_modulus),
            "poisson_ratio": mv(m.poisson_ratio),
        }


# ----------------------------------------------------------------------------------------------- parameter draws
def draw_geometry(
    family: str, rng: np.random.Generator, envelope: Mapping[str, tuple[float, float]] | None = None
) -> dict:
    """One geometry (parameters in D units plus the derived particle count); `envelope` bounds each draw (test set)."""

    def u(key: str, lo: float, hi: float) -> float:
        if envelope is not None and key in envelope:
            lo, hi = max(lo, envelope[key][0]), min(hi, envelope[key][1])
        return float(rng.uniform(lo, hi))

    if family == "column-collapse":
        for _ in range(1000):
            a = u("a", 0.5, 4.0)
            lo = max(18.0, 32.5 / float(np.interp(a, RATIO_A, RATIO_F)))  # measured Hf / L0 (30 d floor)
            hi = min(70.0, math.sqrt(N_MAX_COLLAPSE * CELL_AREA / a))
            if envelope is not None and "L0_D" in envelope:
                lo, hi = max(lo, envelope["L0_D"][0]), min(hi, envelope["L0_D"][1])
            if hi > lo:
                width = float(rng.uniform(lo, hi))
                return {"a": a, "L0_D": width, "n": round(a * width * width / CELL_AREA)}
        raise ValueError("the envelope leaves no column collapse geometry")
    if family == "pile-formation":
        r = FEED_RANGES[family]
        return {
            "x_p_D": u("x_p_D", *r["x_p_D"]),
            "z_o_D": u("z_o_D", *r["z_o_D"]),
            "w_o_D": u("w_o_D", *r["w_o_D"]),
            "n": N_FEED,
        }
    if family == "dump-over-crest":
        r = FEED_RANGES[family]
        return {
            "x_c_D": u("x_c_D", *r["x_c_D"]),
            "h_c_D": u("h_c_D", *r["h_c_D"]),
            "z_o_D": u("z_o_D", *r["z_o_D"]),
            "w_o_D": u("w_o_D", *r["w_o_D"]),
            "x_off_D": u("x_off_D", *r["x_off_D"]),
            "n": N_FEED,
        }
    raise ValueError(f"unknown family {family!r}")


def envelope_of(family: str, train: Sequence[Mapping[str, Any]]) -> dict[str, tuple[float, float]]:
    """Per-parameter min and max over the training geometries (the test draws stay inside)."""
    keys = {
        "column-collapse": ("a", "L0_D"),
        "pile-formation": ("x_p_D", "z_o_D", "w_o_D"),
        "dump-over-crest": ("x_c_D", "h_c_D", "z_o_D", "w_o_D", "x_off_D"),
    }[family]
    return {k: (min(p[k] for p in train), max(p[k] for p in train)) for k in keys}


def geometry_record(family: str, p: Mapping[str, Any], rate: float | None = None) -> dict[str, float]:
    """The `geometry` object of the metadata (metres). Feed families need the measured `rate` (m^2/s)."""
    if family == "column-collapse":
        return {"aspect_ratio": p["a"], "column_width_m": p["L0_D"] * D}
    if rate is None or not math.isfinite(rate) or rate <= 0.0:
        raise ValueError(f"the {family} geometry record needs the measured positive feed rate, got {rate!r}")
    if family == "pile-formation":
        return {"pour_point_x_m": p["x_p_D"] * D, "pour_height_m": p["z_o_D"] * D, "pour_rate_m2_per_s": float(rate)}
    return {"crest_x_m": p["x_c_D"] * D, "crest_height_m": p["h_c_D"] * D, "dump_rate_m2_per_s": float(rate)}


def contract_vec(family: str, record: Mapping[str, float]) -> np.ndarray:
    """The reader's metric: contract parameters normalised by the DC-011-02 ranges (pitstudio_pipeline
    data.FAMILY_RANGES)."""
    return np.array([(record[k] - lo) / (hi - lo) for k, lo, hi in CONTRACT_RANGES[family]])


def split_rule_ok(
    family: str,
    record: Mapping[str, float],
    train_records: Sequence[Mapping[str, float]],
    min_distance: float = MIN_DISTANCE,
) -> tuple[bool, float]:
    """FR-011-03 on a measured test geometry: inside the training min/max of each contract parameter and at least
    `min_distance` from every training geometry under the contract metric. Returns (ok, nearest distance)."""
    tv = np.array([contract_vec(family, r) for r in train_records])
    v = contract_vec(family, record)
    inside = bool(((v >= tv.min(axis=0) - 1e-12) & (v <= tv.max(axis=0) + 1e-12)).all())
    dist = float(np.linalg.norm(tv - v, axis=1).min())
    return inside and dist >= min_distance, dist


def split_plan() -> list[dict[str, Any]]:
    """The 100 geometry slots in generation order (validation first, then train, then test; ids g001 ... g100)."""
    slots: list[dict[str, Any]] = []
    idx = 0
    for split in SPLIT_ORDER:
        for fam in FAMILIES:
            for _ in range(SPLIT_COUNTS[split][fam]):
                idx += 1
                slots.append(
                    {
                        "id": f"g{idx:03d}",
                        "idx": idx,
                        "family": fam,
                        "split": split,
                        "params": None,
                        "attempt": 0,
                        "seeds": [],
                        "failed_seeds": [],
                        "failed_geometries": [],
                        "done": False,
                    }
                )
    return slots

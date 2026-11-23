"""D2 sweep generator (`s05_synthesize`, FR-017-02, FR-017-10, P-017-19, DC-017-01).

Draws the ore x circuit configurations and the blast designs of each by scrambled Sobol sequences (`scipy.stats.qmc`,
Owen-type scrambling: the first 2^m points keep the one-point-per-stratum property of every one-dimensional
projection), evaluates the chain at every point, splits the configurations into training, validation and held-out
sweeps, and links every box bound to its knowledge-table row. The design is validated before the first chain call.
"""

from __future__ import annotations

import copy
import math
import warnings
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
from scipy.stats import qmc

LABEL = "calibrated synthetic — not validated against real data"
SCHEMA_VERSION = "1.0"
POINT_INPUTS: tuple[str, ...] = ("burden_m", "spacing_ratio", "powder_factor_kg_per_m3")
CONFIG_INPUTS: tuple[str, ...] = (
    "hole_diameter_mm",
    "bench_height_m",
    "rock_factor",
    "bond_work_index_kwh_per_t",
    "crusher_css_mm",
    "target_p80_um",
    "mill_power_kw",
    "efficiency",
    "energy_cap_kwh_per_t",
    "explosive_cost_usd_per_kg",
    "energy_cost_usd_per_kwh",
    "consumables_usd_per_t",
)
MORRELL = "morrell_index_kwh_per_t"
BOND = "bond_work_index_kwh_per_t"
SPLITS = ("train", "validation", "held_out")
SPLIT_LABEL = {"train": "train", "validation": "validation", "held_out": "held-out"}  # DC-017-01 spelling
N_CONFIGURATIONS = (10, 10_000)
N_POINTS = (8, 4096)
MAX_SEED = 2**63 - 1


class SweepConfigError(ValueError):
    """A sweep configuration rejected before the chain is evaluated; `reason` is a short machine-readable code."""

    def __init__(self, message: str, *, reason: str = "invalid") -> None:
        super().__init__(message)
        self.reason = reason


def _config_names(energy_model: str) -> tuple[str, ...]:
    return tuple(MORRELL if n == BOND and energy_model == "morrell" else n for n in CONFIG_INPUTS)


def _fail(reason: str, message: str) -> SweepConfigError:
    return SweepConfigError(message, reason=reason)


def link_bounds(
    bounds: Mapping[str, tuple[float, float]], rows: Mapping[str, str], statuses: Mapping[str, str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """The DC-017-01 box of `bounds` with each input's knowledge row and status, and the sorted UNVERIFIED rows."""
    box: dict[str, dict[str, Any]] = {}
    unverified: set[str] = set()
    for name, pair in bounds.items():
        if name not in rows:
            raise _fail("no-row", f"input {name!r} has no knowledge-table row")
        row = rows[name]
        if row not in statuses:
            raise _fail("no-status", f"knowledge row {row!r} of input {name!r} has no verification status")
        if len(pair) != 2:
            raise _fail("bound", f"input {name!r} needs a (min, max) pair")
        box[name] = {"min": pair[0], "max": pair[1], "row": row, "verification": statuses[row]}
        if statuses[row] == "UNVERIFIED":
            unverified.add(row)
    return box, sorted(unverified)


def _count(design: Mapping, key: str, lo: int, hi: int) -> int:
    value = design.get(key)
    if isinstance(value, bool) or not isinstance(value, int | np.integer):
        raise _fail(key, f"{key} must be an integer, got {value!r}")
    if not lo <= value <= hi:
        raise _fail(key, f"{key} must be between {lo} and {hi}, got {value}")
    return int(value)


def validate_design(design: Mapping, *, smallest_feed_f80_um: float | None = None) -> None:
    """Raise `SweepConfigError` for a design that FR-017-10 rejects; return None for a valid one."""
    model = design.get("energy_model")
    if model not in ("bond", "morrell"):
        raise _fail("energy_model", f"energy_model must be 'bond' or 'morrell', got {model!r}")
    seed = design.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int | np.integer) or not 0 <= seed <= MAX_SEED:
        raise _fail("seed", f"seed must be an integer in [0, 2^63 - 1], got {seed!r}")
    n_conf = _count(design, "n_configurations", *N_CONFIGURATIONS)
    _count(design, "points_per_configuration", *N_POINTS)
    split = design.get("split")
    if not isinstance(split, Mapping) or set(split) != set(SPLITS):
        raise _fail("split", f"split must have exactly the keys {list(SPLITS)}")
    sizes = []
    for key in SPLITS:
        value = split[key]
        if isinstance(value, bool) or not isinstance(value, int | np.integer) or value < 1:
            raise _fail("split", f"split {key} must be an integer of at least 1, got {value!r}")
        sizes.append(int(value))
    if sum(sizes) != n_conf:
        raise _fail("split", f"split {sizes} does not add up to n_configurations {n_conf}")
    box = design.get("box")
    if not isinstance(box, Mapping):
        raise _fail("box", "box must be a mapping of input name to bound")
    names = POINT_INPUTS + _config_names(model)
    for name in box:
        if name not in names:
            raise _fail("unknown-input", f"unknown input {name!r} in the box; expected one of {list(names)}")
    for name in names:
        if name not in box:
            raise _fail("missing-input", f"input {name!r} is missing from the box")
        bound = box[name]
        lo, hi = bound.get("min"), bound.get("max")
        for label, v in (("min", lo), ("max", hi)):
            if isinstance(v, bool) or not isinstance(v, int | float | np.floating) or not math.isfinite(v):
                raise _fail("bound", f"input {name!r}: {label} must be a finite number, got {v!r}")
        if lo > hi:
            raise _fail("bound", f"input {name!r}: min {lo!r} is above max {hi!r}")
    if smallest_feed_f80_um is not None and not box["target_p80_um"]["max"] < smallest_feed_f80_um:
        raise _fail(
            "target_p80_um",
            f"input 'target_p80_um': its maximum {box['target_p80_um']['max']!r} um is not below the smallest "
            f"feed F80 {smallest_feed_f80_um!r} um of the box",
        )


def _scale(unit: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return lo + unit * (hi - lo)


def _sobol(dimension: int, count: int, entropy: list[int]) -> np.ndarray:
    engine = qmc.Sobol(d=dimension, scramble=True, seed=np.random.default_rng(np.random.SeedSequence(entropy)))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # a count that is not a power of 2 loses balance, not coverage
        return engine.random(count)


def _normalise_box(box: Mapping[str, Mapping]) -> dict[str, dict]:
    """The box in the DC-017-01 spelling ("verified" or "UNVERIFIED")."""
    out = copy.deepcopy({k: dict(v) for k, v in box.items()})
    for bound in out.values():
        bound["verification"] = "UNVERIFIED" if str(bound["verification"]).upper() == "UNVERIFIED" else "verified"
    return out


def generate_sweeps(
    design: Mapping,
    *,
    chain: Callable[[dict], Any],
    smallest_feed_f80_um: float | None = None,
) -> dict:
    """Validate `design`, evaluate `chain` at every point and return the DC-017-01 sweep document."""
    validate_design(design, smallest_feed_f80_um=smallest_feed_f80_um)
    seed = int(design["seed"])
    model = design["energy_model"]
    n_conf = int(design["n_configurations"])
    n_points = int(design["points_per_configuration"])
    box = design["box"]
    config_names = _config_names(model)
    unit_config = _sobol(len(config_names), n_conf, [seed, 0])
    order = np.random.default_rng(np.random.SeedSequence([seed, 1])).permutation(n_conf)
    bounds_split = np.cumsum([int(design["split"][k]) for k in SPLITS])
    assigned = np.empty(n_conf, dtype=object)
    for rank, index in enumerate(order):
        assigned[index] = SPLITS[int(np.searchsorted(bounds_split, rank, side="right"))]
    seeds = np.random.SeedSequence([seed, 2]).generate_state(n_conf, dtype=np.uint64) >> np.uint64(1)
    configurations = []
    for i in range(n_conf):
        inputs = {
            name: float(_scale(unit_config[i, j], box[name]["min"], box[name]["max"]))
            for j, name in enumerate(config_names)
        }
        unit_points = _sobol(len(POINT_INPUTS), n_points, [int(seeds[i]), 3])
        points = []
        for u in unit_points:
            drawn = {
                name: float(_scale(u[j], box[name]["min"], box[name]["max"])) for j, name in enumerate(POINT_INPUTS)
            }
            result = chain({**inputs, **drawn})
            points.append(
                {
                    **drawn,
                    "specific_energy_kwh_per_t": float(result.kwh_per_t),
                    "throughput_t_per_h": float(result.t_per_h),
                    "cost_usd_per_t": float(result.cost_per_t),
                }
            )
        configurations.append(
            {
                "id": f"cfg-{i:04d}",
                "split": SPLIT_LABEL[assigned[i]],
                "seed": int(seeds[i]),
                "inputs": inputs,
                "points": points,
            }
        )
    norm_box = _normalise_box(box)
    unverified = sorted({b["row"] for b in norm_box.values() if b["verification"] == "UNVERIFIED"})
    return {
        "schema_version": SCHEMA_VERSION,
        "synthetic": True,
        "label": LABEL,
        "design": {
            "seed": seed,
            "energy_model": model,
            "n_configurations": n_conf,
            "points_per_configuration": n_points,
            "split": {k: int(design["split"][k]) for k in SPLITS},
            "box": norm_box,
        },
        "unverified_rows": unverified,
        "configurations": configurations,
    }

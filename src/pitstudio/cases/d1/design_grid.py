"""D1 blast design grid (FR-012-41, FR-012-46, DC-012-05): x50, x80, oversize, PPV and flyrock radius over design inputs.

Every number comes from a call of `minephys.blasting`; this module only orders the calls and names the inputs:

| Output | minephys function | Equation (source of the minephys function) |
|---|---|---|
| charge per hole Q | `charge_per_hole` | Q = rho_e pi/4 d^2 L_c (minephys spec 002, FR-002-01) |
| powder factor K | `powder_factor` | K = Q / (B S H) (minephys spec 002, section 3) |
| x50 | `kuznetsov_x50` | x50 = A K^-0.8 Q^(1/6) (115 / RWS)^e, e = 19/20 (Cunningham 2005, eq. 1) or 19/30 (1983) |
| uniformity n | `uniformity_index` | n = (2.2 - 14 B/d)(...) (Cunningham 2005, eq. 3) |
| x80, oversize (KCO) | `kco_undulation`, `swebrec_size`, `swebrec_passing` | b = 2 ln 2 ln(x_max/x50) n; P = 1/(1 + [ln(x_max/x)/ln(x_max/x50)]^b) (Mutinda 2021, eqs. 1 and 6) |
| x80, oversize (RR) | `rosin_rammler_size`, `rosin_rammler_passing` | P = 1 - exp(-ln 2 (x/x50)^n) (Cunningham 2005, eq. 2) |
| PPV | `ppv_scaled_distance` | PPV = K_site (D / sqrt(W))^-beta (30 CFR 816.67(d)(3)) |
| flyrock radius | `flyrock_trajectory` | ballistic range of a sphere with quadratic drag at the 45 degree launch angle, which is the
  drag-free maximum range v^2 / g when the drag coefficient is 0 (Szendrei 2022, p. 728) |

The oversize share is 100 (1 - P(x_l)) for the oversize limit x_l. The size basis of x50 and x80 is the sieve size in
metres of the blasted rock (sieve-passing by mass), not an image size.
"""
# ruff: noqa: E501

from __future__ import annotations

import itertools
import json
import math
import os
from collections.abc import Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

from minephys import blasting
from minephys._errors import InputError

LAUNCH_ANGLE_RAD = math.pi / 4
VARIANTS = ("cunningham1983", "cunningham2005")
DISTRIBUTIONS = ("kco-swebrec", "rosin-rammler")
UNITS = {"x50": "m", "x80": "m", "oversize": "%", "ppv": "m/s", "flyrock_radius": "m"}
MAX_AXES, MAX_AXIS_VALUES, MAX_POINTS = 4, 64, 4096

# (low, high, low_open, high_open): the ranges of DC-012-05 `design_inputs` (checked against the schema by the tests)
INPUT_RANGES: dict[str, tuple[float, float, bool, bool]] = {
    "burden_m": (0.0, 20.0, True, False),
    "spacing_m": (0.0, 30.0, True, False),
    "bench_height_m": (0.0, 50.0, True, False),
    "hole_diameter_m": (0.0, 1.0, True, False),
    "charge_length_m": (0.0, 50.0, True, False),
    "drilling_deviation_m": (0.0, 5.0, False, False),
    "explosive_density_kg_per_m3": (0.0, 2000.0, True, False),
    "rws": (0.0, 300.0, True, False),
    "rock_factor": (0.8, 22.0, False, False),
    "x_max_m": (0.0, 10.0, True, False),
    "oversize_limit_m": (0.0, 10.0, True, False),
    "distance_m": (0.0, 100000.0, True, False),
    "charge_per_delay_kg": (0.0, 100000.0, True, False),
    "k_site_m_per_s": (0.0, 100.0, True, False),
    "beta": (0.0, 10.0, True, False),
    "launch_speed_m_per_s": (0.0, 500.0, True, False),
    "fragment_diameter_m": (0.0, 10.0, True, False),
    "rock_density_kg_per_m3": (0.0, 10000.0, True, False),
    "drag_coefficient": (0.0, 10.0, False, False),
    "air_density_kg_per_m3": (0.0, 2.0, False, False),
}
# minephys argument name -> design input, to name the input of a call that minephys rejects (FR-012-46)
_ARGUMENT_INPUT = {
    "burden": "burden_m",
    "spacing": "spacing_m",
    "bench_height": "bench_height_m",
    "hole_diameter": "hole_diameter_m",
    "charge_length": "charge_length_m",
    "drilling_deviation": "drilling_deviation_m",
    "explosive_density": "explosive_density_kg_per_m3",
    "rws": "rws",
    "rock_factor": "rock_factor",
    "x50": "x_max_m",
    "xmax": "x_max_m",
    "distance": "distance_m",
    "charge_per_delay": "charge_per_delay_kg",
    "k_site": "k_site_m_per_s",
    "beta": "beta",
    "launch_speed": "launch_speed_m_per_s",
    "diameter": "fragment_diameter_m",
    "rock_density": "rock_density_kg_per_m3",
    "drag_coefficient": "drag_coefficient",
    "air_density": "air_density_kg_per_m3",
    "charge": "charge_length_m",
    "powder_factor": "charge_length_m",
    "size": "oversize_limit_m",
}
_COMMON = tuple(n for n in INPUT_RANGES if n != "x_max_m")


def minephys_identity() -> str:
    """The pinned minephys version: its version string plus the commit it was installed from (`+g<sha7>`)."""
    dist = metadata.distribution("minephys")
    version = dist.version
    try:
        sha = json.loads(dist.read_text("direct_url.json") or "{}")["vcs_info"]["commit_id"][:7]
        return f"{version}+g{sha}"
    except KeyError, ValueError, TypeError:
        return version


def _check_value(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"input {name!r} must be a real number, got {value!r}")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"input {name!r} must be finite, got {value!r}")
    lo, hi, lo_open, hi_open = INPUT_RANGES[name]
    below = value <= lo if lo_open else value < lo
    above = value >= hi if hi_open else value > hi
    if below or above:
        left, right = ("(" if lo_open else "["), (")" if hi_open else "]")
        raise ValueError(f"input {name!r} = {value!r} is outside its range {left}{lo}, {hi}{right}")
    return value


def _one_point(inputs: Mapping[str, float], variant: str, distribution: str) -> dict[str, float]:
    i = inputs
    q = blasting.charge_per_hole(i["explosive_density_kg_per_m3"], i["hole_diameter_m"], i["charge_length_m"])
    k = blasting.powder_factor(q, i["burden_m"], i["spacing_m"], i["bench_height_m"])
    n = blasting.uniformity_index(
        i["burden_m"],
        i["spacing_m"],
        i["hole_diameter_m"],
        i["drilling_deviation_m"],
        i["charge_length_m"],
        i["bench_height_m"],
    )
    x50 = blasting.kuznetsov_x50(i["rock_factor"], k, q, i["rws"], variant)
    if distribution == "kco-swebrec":
        b = blasting.kco_undulation(n, x50, i["x_max_m"])
        x80 = blasting.swebrec_size(0.8, x50, i["x_max_m"], b)
        passing = blasting.swebrec_passing(i["oversize_limit_m"], x50, i["x_max_m"], b)
    else:
        x80 = blasting.rosin_rammler_size(0.8, x50, n)
        passing = blasting.rosin_rammler_passing(i["oversize_limit_m"], x50, n)
    return {"x50_m": float(x50), "x80_m": float(x80), "oversize_pct": float(100.0 * (1.0 - passing))}


def _ppv(i: Mapping[str, float]) -> float:
    return float(
        blasting.ppv_scaled_distance(i["distance_m"], i["charge_per_delay_kg"], i["k_site_m_per_s"], i["beta"])
    )


def _flyrock(i: Mapping[str, float]) -> float:
    return float(
        blasting.flyrock_trajectory(
            i["launch_speed_m_per_s"],
            LAUNCH_ANGLE_RAD,
            i["fragment_diameter_m"],
            i["rock_density_kg_per_m3"],
            i["drag_coefficient"],
            i["air_density_kg_per_m3"],
        ).range
    )


def build_design_grid(
    fixed: Mapping[str, float],
    axes: Mapping[str, Sequence[float]],
    *,
    kuzram_variant: str = "cunningham2005",
    distribution: str = "kco-swebrec",
) -> dict:
    """The DC-012-05 document of the grid over the Cartesian product of `axes`; ValueError naming the input, no grid."""
    if kuzram_variant not in VARIANTS:
        raise ValueError(f"kuzram_variant must be one of {list(VARIANTS)}, got {kuzram_variant!r}")
    if distribution not in DISTRIBUTIONS:
        raise ValueError(f"distribution must be one of {list(DISTRIBUTIONS)}, got {distribution!r}")
    if not axes or len(axes) > MAX_AXES:
        raise ValueError(f"axes must hold 1 to {MAX_AXES} inputs, got {len(axes)}")
    for name in (*fixed, *axes):
        if name not in INPUT_RANGES:
            raise ValueError(f"unknown design input {name!r}; expected one of {list(INPUT_RANGES)}")
    required = _COMMON + (("x_max_m",) if distribution == "kco-swebrec" else ())
    base = {k: _check_value(k, v) for k, v in fixed.items() if k not in axes}
    for name in required:
        if name not in base and name not in axes:
            raise ValueError(f"missing design input {name!r}")
    axis_values: dict[str, list[float]] = {}
    total = 1
    for name, values in axes.items():
        checked = [_check_value(name, v) for v in values]
        if not 1 <= len(checked) <= MAX_AXIS_VALUES:
            raise ValueError(f"axis {name!r} must hold 1 to {MAX_AXIS_VALUES} values, got {len(checked)}")
        if len(set(checked)) != len(checked):
            raise ValueError(f"axis {name!r} holds duplicate values")
        axis_values[name] = checked
        total *= len(checked)
    if total > MAX_POINTS:
        raise ValueError(f"the axes make {total} points; at most {MAX_POINTS} are allowed")
    ppv_cache: dict[tuple, float] = {}
    fly_cache: dict[tuple, float] = {}
    points = []
    for combo in itertools.product(*axis_values.values()):
        swept = dict(zip(axis_values, combo, strict=True))
        inputs = {**base, **swept}
        try:
            out = _one_point(inputs, kuzram_variant, distribution)
            ppv_key = tuple(inputs[k] for k in ("distance_m", "charge_per_delay_kg", "k_site_m_per_s", "beta"))
            if ppv_key not in ppv_cache:
                ppv_cache[ppv_key] = _ppv(inputs)
            fly_key = tuple(
                inputs[k]
                for k in (
                    "launch_speed_m_per_s",
                    "fragment_diameter_m",
                    "rock_density_kg_per_m3",
                    "drag_coefficient",
                    "air_density_kg_per_m3",
                )
            )
            if fly_key not in fly_cache:
                fly_cache[fly_key] = _flyrock(inputs)
        except InputError as error:
            name = _ARGUMENT_INPUT.get(error.argument or "", error.argument or "an input")
            raise ValueError(f"input {name!r} is rejected by minephys.blasting: {error}") from None
        points.append(
            {"inputs": swept, **out, "ppv_m_per_s": ppv_cache[ppv_key], "flyrock_radius_m": fly_cache[fly_key]}
        )
    return {
        "case_id": "D1",
        "minephys_version": minephys_identity(),
        "kuzram_variant": kuzram_variant,
        "distribution": distribution,
        "units": dict(UNITS),
        "fixed_inputs": base,
        "axes": [{"input": name, "values": values} for name, values in axis_values.items()],
        "points": points,
    }


def write_design_grid(
    path: Path | str, fixed: Mapping[str, float], axes: Mapping[str, Sequence[float]], **kw: Any
) -> dict:
    """Build the grid and, only after it succeeded, write it as JSON to `path` (atomic replace)."""
    doc = build_design_grid(fixed, axes, **kw)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return doc

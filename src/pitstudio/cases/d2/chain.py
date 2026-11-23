"""D2 mine-to-mill chain (FR-017-01, P-017-17): blast fragmentation, crusher, specific energy, throughput and cost.

The chain composes only `minephys` functions (numpy and the standard library otherwise); every equation is the
one of the cited minephys function, nothing is re-implemented here:

1. Blast design: spacing S = (S/B) B, charge per hole Q = K B S H (`minephys.blasting.powder_factor` solved for Q, the
   bench-volume convention of that function), charge length L_c = H - 0.7 B (stemming 0.7 B, UNVERIFIED rule).
2. Run-of-mine size: Kuznetsov mean size x50 (`kuznetsov_x50`, Cunningham 2005 eq. 1 with the verified exponent
   19/20), uniformity index n (`uniformity_index`, Cunningham 2005 eq. 3), Kuz-Ram-Swebrec (KCO) curve
   (`kco_distribution`, Mutinda 2021 eq. 6) with x_max = B.
3. Crusher and mill (`minephys.comminution.mine_to_mill_chain`): Whiten classification (`whiten_classification`) and
   Austin breakage matrix (`austin_breakage`) give the crusher product (`crusher_matrix_model`), its F80, then the
   Bond third law `W = 10 W_i (1/sqrt(P80) - 1/sqrt(F80))` (`bond_energy`, McIvor 2016) or the Morrell tumbling
   terms (`morrell_tumbling_coarse` plus `morrell_tumbling_fine`), and the throughput t/h = eta P_mill / W.
4. Cost per tonne: `K c_explosive / rho_rock + c_energy W + c_consumables` (USD/t), linear in each unit cost.

UNVERIFIED illustrative constants, listed in `ASSUMPTIONS` and written to the manifest of every run that uses them:
the relative weight strength, the stemming rule, the drilling deviation, x_max, the in-situ rock density, the crusher
classification and breakage parameters and the Morrell index split. The absolute cost per tonne is therefore
illustrative; the identities (t/h x kWh/t = eta P_mill, monotonicity, the Bond limit) do not depend on them.

The population-balance mill product of FR-017-01 is not a determinant of kWh/t, t/h or cost/t in
`minephys.comminution.mine_to_mill_chain` (it has no population-balance stage); `pbm=False` is accepted for the
pass-through configuration of the spec and gives the same outputs as `pbm=True` (open question D2-Q1 of the
d-cases-2026-11-23 report).
"""
# ruff: noqa: E501

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from minephys import blasting, comminution

INPUT_NAMES: tuple[str, ...] = (
    "burden_m",
    "spacing_ratio",
    "powder_factor_kg_per_m3",
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
MORRELL_INPUT = "morrell_index_kwh_per_t"

ASSUMPTIONS: dict[str, dict[str, object]] = {
    "relative_weight_strength": {"value": 100.0, "unit": "ANFO = 100", "status": "UNVERIFIED"},
    "stemming_over_burden": {"value": 0.7, "unit": "1", "status": "UNVERIFIED"},
    "drilling_deviation_m": {"value": 0.2, "unit": "m", "status": "UNVERIFIED"},
    "xmax_over_burden": {"value": 1.0, "unit": "1", "status": "UNVERIFIED"},
    "rock_density_t_per_m3": {"value": 2.7, "unit": "t/m3", "status": "UNVERIFIED"},
    "crusher_k1_over_css": {"value": 0.5, "unit": "1", "status": "UNVERIFIED"},
    "crusher_k2_over_css": {"value": 1.0, "unit": "1", "status": "UNVERIFIED"},
    "crusher_k3": {"value": 2.0, "unit": "1", "status": "UNVERIFIED"},
    "crusher_breakage_phi_gamma_beta": {"value": [0.4, 0.7, 3.0], "unit": "1", "status": "UNVERIFIED"},
    "morrell_mia_equals_mib": {"value": True, "unit": "bool", "status": "UNVERIFIED"},
    "size_classes": {"value": 96, "unit": "1", "status": "chosen"},
    "finest_class_um": {"value": 20.0, "unit": "um", "status": "chosen"},
}
_RWS = 100.0
_STEMMING = 0.7
_DEVIATION_M = 0.2
_XMAX_OVER_BURDEN = 1.0
_ROCK_T_PER_M3 = 2.7
_K1, _K2, _K3 = 0.5, 1.0, 2.0
_PHI, _GAMMA, _BETA = 0.4, 0.7, 3.0
_N_CLASSES = 96
_FINEST_M = 20e-6
_KWH_PER_T_IN_J_PER_KG = 3600.0  # 1 kWh/t = 3.6e6 J / 1e3 kg
_KG_PER_S_IN_T_PER_H = 3.6


@dataclass(frozen=True)
class ChainResult:
    """Chain outputs: specific energy (kWh/t), throughput (t/h) and cost (USD/t)."""

    kwh_per_t: float
    t_per_h: float
    cost_per_t: float


def _checked(inputs: Mapping[str, float], morrell: bool) -> dict[str, float]:
    names = tuple(MORRELL_INPUT if n == "bond_work_index_kwh_per_t" and morrell else n for n in INPUT_NAMES)
    for key in inputs:
        if key not in names:
            raise ValueError(f"unknown input {key!r}; expected one of {list(names)}")
    out: dict[str, float] = {}
    for name in names:
        if name not in inputs:
            raise ValueError(f"missing input {name!r}")
        value = inputs[name]
        if isinstance(value, bool) or not isinstance(value, int | float | np.floating | np.integer):
            raise ValueError(f"input {name!r} must be a real number, got {type(value).__name__}")
        value = float(value)
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"input {name!r} must be finite and positive, got {value!r}")
        out[name] = value
    if out["efficiency"] > 1.0:
        raise ValueError(f"input 'efficiency' must be at most 1, got {out['efficiency']!r}")
    return out


def _blast_curve(x: Mapping[str, float]) -> tuple[np.ndarray, np.ndarray]:
    """Run-of-mine cumulative passing on `_N_CLASSES` upper class sizes from x_max to the finest class (m)."""
    b = x["burden_m"]
    s = x["spacing_ratio"] * b
    h = x["bench_height_m"]
    d = x["hole_diameter_mm"] / 1000.0
    k = x["powder_factor_kg_per_m3"]
    q = k * b * s * h  # charge per hole from K = Q / (B S H)
    length = h - _STEMMING * b
    if length <= 0.0:
        raise ValueError("input 'burden_m': the stemming 0.7 B leaves no charge column in the bench height")
    x50 = float(blasting.kuznetsov_x50(x["rock_factor"], k, q, _RWS, variant="cunningham2005"))
    n = float(blasting.uniformity_index(b, s, d, _DEVIATION_M, length, h))
    xmax = _XMAX_OVER_BURDEN * b
    if x50 >= xmax:
        raise ValueError(f"input 'rock_factor': the Kuznetsov x50 {x50:.3f} m is not below x_max {xmax:.3f} m")
    sizes = np.geomspace(xmax, _FINEST_M, _N_CLASSES)
    return sizes, np.asarray(blasting.kco_distribution(sizes, x50, xmax, n), dtype=np.float64)


def _crusher(sizes: np.ndarray, css_m: float) -> tuple[np.ndarray, np.ndarray]:
    classification = np.asarray(comminution.whiten_classification(sizes, _K1 * css_m, _K2 * css_m, _K3))
    return classification, comminution.austin_breakage(sizes, _PHI, _GAMMA, _BETA)


def crusher_f80_um(inputs: Mapping[str, float]) -> float:
    """F80 (um) of the crusher product for the blast and crusher inputs of `run_chain` (the mill feed size)."""
    morrell = MORRELL_INPUT in inputs
    return _evaluate(inputs, True, None, morrell)[1] * 1e6


def rom_x80_m(inputs: Mapping[str, float]) -> float:
    """The run-of-mine x80 (m) of the blast stage: the Swebrec size at 80 % passing of the KCO curve of the design."""
    x = _checked(inputs, MORRELL_INPUT in inputs)
    sizes, passing = _blast_curve(x)
    return float(comminution.passing_size(sizes, passing, 0.8))


def run_chain(
    inputs: Mapping[str, float],
    *,
    crusher: bool = True,
    pbm: bool = True,
    feed_f80_um: float | None = None,
) -> ChainResult:
    """Evaluate the chain for the input vector of spec 017 section 7 (see the module docstring).

    `crusher=False` bypasses the blast and crusher stages: the mill feed F80 is `feed_f80_um`, which is then required.
    `pbm=False` is the pass-through of the population-balance product (identical outputs, see the module docstring).
    ValueError names the offending key for an unknown, missing, non-finite or non-positive input and, in the
    pass-through configuration, a target P80 not below the feed F80.
    """
    del pbm  # pass-through flag: the outputs do not depend on it (module docstring, D2-Q1)
    return _evaluate(inputs, crusher, feed_f80_um, MORRELL_INPUT in inputs)[0]


def _evaluate(
    inputs: Mapping[str, float], crusher: bool, feed_f80_um: float | None, morrell: bool
) -> tuple[ChainResult, float]:
    """The chain result and the mill feed F80 (m)."""
    x = _checked(inputs, morrell)
    model = "morrell" if morrell else "bond"
    target_m = x["target_p80_um"] * 1e-6
    power_w = x["efficiency"] * x["mill_power_kw"] * 1000.0  # effective power eta P_mill
    index_j_per_kg = x[MORRELL_INPUT if morrell else "bond_work_index_kwh_per_t"] * _KWH_PER_T_IN_J_PER_KG
    if crusher:
        sizes, passing = _blast_curve(x)
        classification, breakage = _crusher(sizes, x["crusher_css_mm"] * 1e-3)
        try:
            result = comminution.mine_to_mill_chain(
                sizes,
                passing,
                classification,
                breakage,
                target_m,
                power_w,
                model,
                work_index=None if morrell else index_j_per_kg,
                mia=index_j_per_kg if morrell else None,
                mib=index_j_per_kg if morrell else None,
                fines_size=x["crusher_css_mm"] * 1e-3,
            )
        except ValueError as error:
            if getattr(error, "argument", None) == "target_p80":
                raise ValueError(f"input 'target_p80_um' is not below the crusher product F80: {error}") from None
            raise
        specific_j_per_kg, throughput_kg_per_s = float(result.specific_energy), float(result.throughput)
        feed_m = float(result.f80)
    else:
        if feed_f80_um is None:
            raise ValueError("input 'feed_f80_um' is required when the crusher stage is bypassed")
        feed_m = float(feed_f80_um) * 1e-6
        if not (math.isfinite(feed_m) and feed_m > 0.0):
            raise ValueError(f"input 'feed_f80_um' must be finite and positive, got {feed_f80_um!r}")
        if not target_m < feed_m:
            raise ValueError(f"input 'target_p80_um' {x['target_p80_um']!r} must be below feed_f80_um {feed_f80_um!r}")
        if morrell:
            specific_j_per_kg = float(
                comminution.morrell_tumbling_coarse(index_j_per_kg, feed_m, False)
                + comminution.morrell_tumbling_fine(index_j_per_kg, target_m)
            )
        else:
            specific_j_per_kg = float(comminution.bond_energy(index_j_per_kg, feed_m, target_m))
        throughput_kg_per_s = power_w / specific_j_per_kg
    kwh_per_t = specific_j_per_kg / _KWH_PER_T_IN_J_PER_KG
    t_per_h = throughput_kg_per_s * _KG_PER_S_IN_T_PER_H
    explosive = x["powder_factor_kg_per_m3"] * x["explosive_cost_usd_per_kg"] / _ROCK_T_PER_M3
    cost = explosive + x["energy_cost_usd_per_kwh"] * kwh_per_t + x["consumables_usd_per_t"]
    return ChainResult(kwh_per_t=kwh_per_t, t_per_h=t_per_h, cost_per_t=cost), feed_m


def breakdown(inputs: Mapping[str, float]) -> list[dict[str, object]]:
    """Every stage value of the full chain for one design, each with its equation and its source (no value without one).

    Rows: stage, quantity, value, unit, equation, source. The values equal the corresponding intermediate results of
    `run_chain` (the same minephys calls); the equation text is the one of the minephys function's docstring.
    """
    x = _checked(inputs, MORRELL_INPUT in inputs)
    b, h = x["burden_m"], x["bench_height_m"]
    s = x["spacing_ratio"] * b
    k = x["powder_factor_kg_per_m3"]
    q = k * b * s * h
    length = h - _STEMMING * b
    x50 = float(blasting.kuznetsov_x50(x["rock_factor"], k, q, _RWS, variant="cunningham2005"))
    n = float(blasting.uniformity_index(b, s, x["hole_diameter_mm"] / 1000.0, _DEVIATION_M, length, h))
    xmax = _XMAX_OVER_BURDEN * b
    undulation = float(blasting.kco_undulation(n, x50, xmax))
    x80 = float(blasting.swebrec_size(0.8, x50, xmax, undulation))
    f80_um = crusher_f80_um(inputs)
    result = run_chain(inputs)
    mc = "minephys:spec-005-comminution"
    return [
        {
            "stage": "blast",
            "quantity": "charge per hole",
            "value": q,
            "unit": "kg",
            "equation": "Q = K B S H (powder factor K held by the design, S = (S/B) B)",
            "source": "minephys:spec-002-blasting, section 3",
        },
        {
            "stage": "blast",
            "quantity": "Kuznetsov mean size x50",
            "value": x50,
            "unit": "m",
            "equation": "x50 = A K^-0.8 Q^(1/6) (115 / RWS)^(19/20) cm",
            "source": "cunningham2005, eq. 1, p. 201",
        },
        {
            "stage": "blast",
            "quantity": "uniformity index n",
            "value": n,
            "unit": "1",
            "equation": "n = (2.2 - 14 B/d) sqrt((1 + S/B)/2) (1 - W/B) (|BCL - CCL|/L + 0.1)^0.1 L/H",
            "source": "cunningham2005, eq. 3, p. 202",
        },
        {
            "stage": "blast",
            "quantity": "Swebrec undulation b",
            "value": undulation,
            "unit": "1",
            "equation": "b = 2 ln 2 ln(x_max / x50) n",
            "source": "mutinda2021, eq. 6, p. 109",
        },
        {
            "stage": "blast",
            "quantity": "run-of-mine x80",
            "value": x80,
            "unit": "m",
            "equation": "x = x_max (x50 / x_max)^(((1 - P) / P)^(1/b)) at P = 0.8",
            "source": "mutinda2021, eq. 1, p. 109",
        },
        {
            "stage": "crusher",
            "quantity": "crusher product F80",
            "value": f80_um / 1e6,
            "unit": "m",
            "equation": "p = (I - C)(I - B C)^-1 f with Whiten classification and Austin breakage; F80 by log-log interpolation",
            "source": f"{mc}, FR-005-24..31 (whiten1972crushing, UNVERIFIED attribution)",
        },
        {
            "stage": "mill",
            "quantity": "specific energy",
            "value": result.kwh_per_t,
            "unit": "kWh/t",
            "equation": "W = 10 W_i (1/sqrt(P80) - 1/sqrt(F80)), sizes in um",
            "source": "mcivor2016bondgmsg, p. 1",
        },
        {
            "stage": "mill",
            "quantity": "throughput",
            "value": result.t_per_h,
            "unit": "t/h",
            "equation": "t/h = eta P_mill / W",
            "source": f"{mc}, FR-005-31 (mine_to_mill_chain)",
        },
        {
            "stage": "cost",
            "quantity": "cost per tonne",
            "value": result.cost_per_t,
            "unit": "USD/t",
            "equation": "K c_explosive / rho_rock + c_energy W + c_consumables (rho_rock 2.7 t/m3, UNVERIFIED)",
            "source": "spec 017 FR-017-01; illustrative unit costs",
        },
    ]

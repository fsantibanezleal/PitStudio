"""AP-42 section 13.2.2 unpaved-road emission factor in the unit of the C3 KPI (kg per vehicle-km travelled).

A thin layer over `minephys.environment.ap42_unpaved_emission_factor` (equation 1a, industrial roads, Table 13.2.2-2 constants:
PM10 k = 1.5 lb/VMT, a = 0.9, b = 0.45). Equation 1a has no speed term: the speed range of Table 13.2.2-3 only bounds its
validity, so a curve against speed would be flat and none is drawn. Extrapolation outside the table ranges is allowed here and
reported by `ap42_in_range`, never silently: the minephys ValidityWarning is turned into that flag.
"""
# ruff: noqa: E501

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
from minephys import knowledge
from minephys._errors import ValidityWarning
from minephys.environment import ap42_unpaved_emission_factor, fleet_mean_vehicle_weight

SHORT_TON_KG_ROW = "ap42_short_ton_in_kg"
KG_PER_M_TO_KG_PER_KM = 1000.0
# the rows bound the table ranges exactly; 100 * 0.018 is 1.7999999999999998 in binary, so bounds are inclusive to rounding
_TOL = 1e-12


def short_ton_kg() -> float:
    return float(knowledge.get_value(SHORT_TON_KG_ROW))


def table_range(row: str) -> tuple[float, float]:
    lo, hi = knowledge.get_value(row)  # type: ignore[misc]
    return float(lo), float(hi)


def emission_factor_kg_per_vkt(silt_fraction: Any, mean_weight_kg: Any, size_class: str = "PM10") -> Any:
    """Equation 1a in kg per vehicle-km; silt as a mass fraction, weight in kg."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ValidityWarning)
        e = ap42_unpaved_emission_factor(silt_fraction, mean_weight_kg, size_class)
    return np.asarray(e) * KG_PER_M_TO_KG_PER_KM if np.ndim(e) else float(e) * KG_PER_M_TO_KG_PER_KM


def ap42_in_range(silt_fraction: Any, mean_weight_kg: Any) -> Any:
    """True where both inputs lie inside Table 13.2.2-3 (silt 1.8 to 25.2 percent, weight 2 to 290 short tons)."""
    s = 100.0 * np.asarray(silt_fraction, dtype=float)
    w = np.asarray(mean_weight_kg, dtype=float) / short_ton_kg()
    (s0, s1), (w0, w1) = table_range("ap42_range_silt"), table_range("ap42_range_weight")
    ok = (s >= s0 * (1 - _TOL)) & (s <= s1 * (1 + _TOL)) & (w >= w0 * (1 - _TOL)) & (w <= w1 * (1 + _TOL))
    return ok if ok.ndim else bool(ok)


def fleet_mean_weight_kg(empty_kg: float, payload_kg: float, loaded_fraction: float) -> float:
    """Traffic-weighted mean weight of empty and loaded passes (AP-42 p. 13.2.2-6: the fleet-mean weight is the input)."""
    return float(fleet_mean_vehicle_weight([empty_kg, empty_kg + payload_kg], [1.0 - loaded_fraction, loaded_fraction]))

# ruff: noqa: E501
"""Route energy by drivetrain over `minephys.haulage` (FR-007-34, FR-007-40, FR-007-45, P-007-19, DC-007-05).

For an ordered route of segments (length m, signed grade %, rolling resistance %, trolley flag), a truck (empty mass t, payload
t, drivetrain diesel, trolley or bev) and a leg (loaded or empty) it reports the signed net wheel energy, the energy drawn from
the tank and from the line or battery, the regenerated energy (bev only), and kWh/t, L/(t km) for diesel and kg CO2e/t, each
stating its basis (payload tonnes, along-road kilometres).

Physical constants come only from the `minephys` knowledge tables or from the caller, never from a literal here. The default of
every constant is a knowledge row (`TABLE_ROWS`: g, the four drivetrain efficiencies, the diesel lower heating value and the diesel
CO2 factor); a pinned `minephys` that lacks a row raises `MissingKnowledgeRow` naming the constant, and the caller may supply it
explicitly. Every result lists the row ids it used and the UNVERIFIED subset.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Mapping, Sequence
from typing import Any

import minephys.knowledge as kn
import numpy as np
from minephys import InputError, units
from minephys import haulage as mp

from .errors import InvalidRouteInput, MissingKnowledgeRow

MAX_SEGMENTS = 100_000
J_PER_KWH = 3.6e6
DRIVETRAINS = ("diesel", "trolley", "bev")
CONSTANT_NAMES = (
    "g",
    "eta_diesel",
    "eta_electric",
    "eta_drive",
    "eta_regen",
    "fuel_energy_density_j_per_m3",
    "diesel_co2_kg_per_m3",
)
# the knowledge-table row of each constant in the pinned `minephys` (DC-001-01 and DC-001-02 of its spec 001)
TABLE_ROWS = {
    "g": "standard_gravity",
    "eta_diesel": "diesel_electric_fuel_to_wheel_efficiency",
    "eta_electric": "electric_dc_bus_to_wheel_efficiency",
    "eta_drive": "battery_electric_battery_to_wheel_efficiency",
    "eta_regen": "battery_electric_regeneration_efficiency",
    "fuel_energy_density_j_per_m3": "diesel_lower_heating_value_j_per_m3",
    "diesel_co2_kg_per_m3": "diesel_co2_kg_per_us_gal",
}
USED_BY = {
    "diesel": ("g", "eta_diesel", "fuel_energy_density_j_per_m3", "diesel_co2_kg_per_m3"),
    "trolley": ("g", "eta_diesel", "eta_electric", "fuel_energy_density_j_per_m3", "diesel_co2_kg_per_m3"),
    "bev": ("g", "eta_drive", "eta_regen"),
}


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _finite(field: str, v: Any) -> float:
    if not _is_number(v) or not math.isfinite(v):
        raise InvalidRouteInput(field, v, "must be a finite number")
    return float(v)


def _entry(name: str) -> dict:
    row = TABLE_ROWS[name]
    try:
        p = kn.get_parameter(row)
        value = float(kn.get_value(row))
    except InputError as exc:  # an older pinned `minephys` without the row
        raise MissingKnowledgeRow([name]) from exc
    if name == "diesel_co2_kg_per_m3":
        value = value / float(units.us_gal_to_m3(1))
    return {"value": value, "row_id": row, "verified": p.verification == "verified"}


def default_constants() -> dict[str, dict]:
    """{name: {"value", "row_id", "verified"}} for every constant, each read from its `minephys` knowledge row."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return {name: _entry(name) for name in TABLE_ROWS}


def _resolve(constants: Mapping[str, float] | None, drivetrain: str) -> dict[str, dict]:
    given = dict(constants or {})
    unknown = sorted(set(given) - set(CONSTANT_NAMES))
    if unknown:
        raise InvalidRouteInput(
            "constants", unknown, f"unknown constant name(s); the names are {', '.join(CONSTANT_NAMES)}"
        )
    bounds = {  # (low, low_open, high)
        "g": (0.0, True, None),
        "eta_diesel": (0.0, True, 1.0),
        "eta_electric": (0.0, True, 1.0),
        "eta_drive": (0.0, True, 1.0),
        "eta_regen": (0.0, False, 1.0),
        "fuel_energy_density_j_per_m3": (0.0, True, None),
        "diesel_co2_kg_per_m3": (0.0, True, None),
    }
    for name, v in given.items():
        _finite(name, v)
        lo, lo_open, hi = bounds[name]
        if (v <= lo) if lo_open else (v < lo):
            raise InvalidRouteInput(name, v, f"must be {'>' if lo_open else '>='} {lo}")
        if hi is not None and v > hi:
            raise InvalidRouteInput(name, v, f"must be <= {hi}")
    out: dict[str, dict] = {}
    missing = []
    for name in CONSTANT_NAMES:
        if name not in USED_BY[drivetrain]:
            continue
        if name in given:
            out[name] = {"value": float(given[name]), "row_id": None, "verified": None}
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    out[name] = _entry(name)
                except MissingKnowledgeRow:
                    missing.append(name)
    if missing:
        raise MissingKnowledgeRow(missing)
    return out


def _segments(route: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if isinstance(route, (str, bytes)) or not isinstance(route, Sequence) or not route:
        raise InvalidRouteInput(
            "route",
            route if not isinstance(route, Sequence) else f"<{len(route)} segments>",
            "must be a non-empty sequence of segments",
        )
    if len(route) > MAX_SEGMENTS:
        raise InvalidRouteInput("route", f"<{len(route)} segments>", f"at most {MAX_SEGMENTS} segments")
    length, grade, rr, trolley = [], [], [], []
    for s in route:
        if not isinstance(s, Mapping):
            raise InvalidRouteInput("route", s, "every segment must be an object")
        for key in ("length_m", "grade_pct", "rr_pct", "trolley"):
            if key not in s:
                raise InvalidRouteInput(key, None, "missing from a segment")
        if not isinstance(s["trolley"], bool):
            raise InvalidRouteInput("trolley", s["trolley"], "must be a boolean")
        length.append(_finite("length_m", s["length_m"]))
        grade.append(_finite("grade_pct", s["grade_pct"]))
        rr.append(_finite("rr_pct", s["rr_pct"]))
        if length[-1] <= 0.0:
            raise InvalidRouteInput("length_m", s["length_m"], "must be > 0 m")
        if rr[-1] < 0.0:
            raise InvalidRouteInput("rr_pct", s["rr_pct"], "must be >= 0")
        trolley.append(s["trolley"])
    return np.array(length), np.array(grade), np.array(rr), np.array(trolley, dtype=bool)


def route_energy(
    route: Sequence[Mapping[str, Any]],
    truck: Mapping[str, Any],
    *,
    leg: str,
    constants: Mapping[str, float] | None = None,
    small_angle: bool = True,
    grid_intensity_kg_per_j: float | None = None,
) -> dict:
    """Energy of one leg over a route; see the module docstring. Raises InvalidRouteInput or MissingKnowledgeRow, never returns NaN."""
    if leg not in ("loaded", "empty") or not isinstance(leg, str):
        raise InvalidRouteInput("leg", leg, "must be 'loaded' or 'empty'")
    dt = truck.get("drivetrain") if isinstance(truck, Mapping) else None
    if not isinstance(dt, str) or dt not in DRIVETRAINS:
        raise InvalidRouteInput("drivetrain", dt, f"must be one of {', '.join(DRIVETRAINS)}")
    empty = _finite("empty_mass_t", truck.get("empty_mass_t"))
    payload = _finite("payload_t", truck.get("payload_t"))
    if empty <= 0.0:
        raise InvalidRouteInput("empty_mass_t", empty, "must be > 0 t")
    if payload <= 0.0:
        raise InvalidRouteInput("payload_t", payload, "must be > 0 t (per-tonne results are undefined)")
    if grid_intensity_kg_per_j is not None and (not _finite("grid_intensity_kg_per_j", grid_intensity_kg_per_j) >= 0.0):
        raise InvalidRouteInput("grid_intensity_kg_per_j", grid_intensity_kg_per_j, "must be >= 0")
    length, grade, rr, trolley = _segments(route)
    used = _resolve(constants, dt)
    c = {name: v["value"] for name, v in used.items()}
    mass_t = empty + (payload if leg == "loaded" else 0.0)
    mass_kg = mass_t * 1000.0

    try:
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter(
                "ignore"
            )  # the knowledge layer warns on UNVERIFIED model constants; the result lists them instead
            tr = np.asarray(mp.total_resistance(rr / 100.0, grade / 100.0, small_angle=small_angle))
            wheel_j = np.asarray(mp.required_force(mass_kg, tr, g=c["g"])) * length

            def source(eta: float, regen: float = 0.0) -> np.ndarray:
                return np.asarray(
                    mp.segment_energy(
                        mass_kg,
                        length,
                        rr / 100.0,
                        grade / 100.0,
                        efficiency=eta,
                        regen_efficiency=regen,
                        small_angle=small_angle,
                        g=c["g"],
                    )
                )

            diesel_j = electric_j = regen_j = 0.0
            if dt == "diesel":
                diesel_j = math.fsum(source(c["eta_diesel"]).tolist())
            elif dt == "trolley":
                on_line = np.where(trolley, source(c["eta_electric"]), 0.0)
                off_line = np.where(trolley, 0.0, source(c["eta_diesel"]))
                electric_j, diesel_j = math.fsum(on_line.tolist()), math.fsum(off_line.tolist())
            else:
                electric_j = math.fsum(source(c["eta_drive"], c["eta_regen"]).tolist())
                regen_j = math.fsum((c["eta_regen"] * -np.minimum(wheel_j, 0.0)).tolist())
        wheel_total = math.fsum(wheel_j.tolist())
        road_km = math.fsum(length.tolist()) / 1000.0
        numbers = (wheel_total, diesel_j, electric_j, regen_j, road_km)
        if not all(math.isfinite(x) for x in numbers):
            raise InvalidRouteInput(
                "route", f"<{len(length)} segments>", "the energy overflows a float; the route is not physical"
            )

    except OverflowError, ZeroDivisionError:
        raise InvalidRouteInput(
            "route", f"<{len(length)} segments>", "the energy overflows a float; the route is not physical"
        ) from None
    basis = {"payload_t": payload, "road_km": road_km}
    source_j = diesel_j + electric_j
    diesel_m3 = diesel_j / c["fuel_energy_density_j_per_m3"] if "fuel_energy_density_j_per_m3" in c else 0.0
    needs_grid = dt in ("trolley", "bev") and electric_j != 0.0
    co2_note = None
    if needs_grid and grid_intensity_kg_per_j is None:
        co2 = None
        co2_note = "electricity emissions need a grid emission intensity (kg CO2 per J), which has no default; none was supplied"
    else:
        co2_kg = 0.0
        if "diesel_co2_kg_per_m3" in c:
            co2_kg += float(mp.co2_from_diesel(diesel_m3, emission_factor=c["diesel_co2_kg_per_m3"]))
        if needs_grid:
            co2_kg += float(mp.co2_from_electricity(electric_j, grid_intensity_kg_per_j))
        co2 = co2_kg / payload
    unverified = sorted({v["row_id"] for v in used.values() if v["row_id"] is not None and not v["verified"]})
    return {
        "leg": leg,
        "mass_t": mass_t,
        "payload_t": payload,
        "road_km": road_km,
        "wheel_kwh": wheel_total / J_PER_KWH,
        "diesel_kwh": diesel_j / J_PER_KWH,
        "electric_kwh": electric_j / J_PER_KWH,
        "regen_kwh": regen_j / J_PER_KWH,
        "source_kwh": source_j / J_PER_KWH,
        "kwh_per_t": {"value": source_j / J_PER_KWH / payload, "basis": basis},
        "diesel_l_per_t_km": {
            "value": None if dt == "bev" else diesel_m3 * 1000.0 / (payload * road_km),
            "basis": basis,
        },
        "co2e_kg_per_t": {"value": co2, "basis": basis},
        "co2e_note": co2_note,
        "constants": used,
        "unverified_rows": unverified,
    }

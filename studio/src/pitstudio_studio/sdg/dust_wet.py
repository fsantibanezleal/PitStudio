"""Dust extinction at the camera and wet-road flags of the structured SDG arm (FR-009-05, FR-009-06)."""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Mapping, Sequence
from typing import Protocol

from minephys import environment

_SEGMENT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")  # DC-009-01 `artefact_id`


class DustField(Protocol):
    """The scenario's plume field: dust mass concentration (kg/m^3) at a point of the stage frame."""

    def concentration_kg_m3(self, x_m: float, y_m: float, z_m: float) -> float: ...


def _positive(name: str, value: float) -> float:
    v = float(value)
    if not math.isfinite(v) or v <= 0.0:
        raise ValueError(f"{name} must be finite and > 0, got {value!r}")
    return v


def dust_extinction_per_km(
    field: DustField,
    camera_xyz_m: Sequence[float],
    *,
    particle_diameter_m: float,
    particle_density_kg_m3: float,
    extinction_efficiency: float | None = None,
) -> float:
    """Extinction coefficient sigma (1/km) of the plume at the camera position.

    sigma = 1000 * minephys.environment.extinction_coefficient(C, mass_extinction_coefficient(D, rho, Q)) with C the
    field's mass concentration at the camera; Q is minephys' default row when `extinction_efficiency` is None.
    """
    cam = [float(c) for c in camera_xyz_m] if len(camera_xyz_m) == 3 else None
    if cam is None or not all(math.isfinite(c) for c in cam):
        raise ValueError(f"camera_xyz_m must be 3 finite numbers, got {camera_xyz_m!r}")
    diameter = _positive("particle_diameter_m", particle_diameter_m)
    density = _positive("particle_density_kg_m3", particle_density_kg_m3)
    conc = float(field.concentration_kg_m3(*cam))
    if not math.isfinite(conc) or conc < 0.0:
        raise ValueError(f"the field's concentration at the camera must be finite and >= 0, got {conc!r}")
    k_m = environment.mass_extinction_coefficient(diameter, density, extinction_efficiency)
    return 1000.0 * float(environment.extinction_coefficient(conc, k_m))


def wet_segments(
    schedule: Mapping[str, Sequence[dt.datetime]], when_utc: dt.datetime, *, drying_time_min: float = 60.0
) -> list[dict]:
    """One DC-009-01 `wet_segment` per segment of `schedule` at `when_utc`.

    A segment is wet if and only if the time since its last watering pass at or before `when_utc` is at most
    `drying_time_min`; later passes are ignored and a segment with no earlier pass is dry (no `minutes_since_watering`).
    """
    if when_utc.tzinfo is None or when_utc.utcoffset() is None:
        raise ValueError("when_utc must be a timezone-aware datetime")
    drying = float(drying_time_min)
    if not math.isfinite(drying) or drying <= 0.0:
        raise ValueError(f"drying_time_min must be finite and > 0, got {drying_time_min!r}")
    out: list[dict] = []
    for segment_id, passes in schedule.items():
        if not isinstance(segment_id, str) or not _SEGMENT_ID.match(segment_id):
            raise ValueError(f"segment id {segment_id!r} does not match {_SEGMENT_ID.pattern}")
        earlier: list[dt.datetime] = []
        for p in passes:
            if p.tzinfo is None or p.utcoffset() is None:
                raise ValueError(f"schedule of segment {segment_id!r} holds a naive datetime")
            if p <= when_utc:
                earlier.append(p)
        if not earlier:
            out.append({"segment_id": segment_id, "wet": False})
            continue
        minutes = (when_utc - max(earlier)).total_seconds() / 60.0
        out.append({"segment_id": segment_id, "wet": minutes <= drying, "minutes_since_watering": minutes})
    return out

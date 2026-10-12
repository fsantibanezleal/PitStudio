"""Structured sun sampler of the perception SDG (FR-009-04): the Solar Position Algorithm and its stage-frame vector.

The solar position is computed by the NumPy implementation of the Solar Position Algorithm (Reda and Andreas 2004,
Solar Energy 76(5):577-589, https://doi.org/10.1016/j.solener.2003.12.003) shipped in pvlib (`pvlib.spa`); this module
validates the arguments, fixes the conventions (UTC instants, azimuth eastward from north, topocentric values with
atmospheric refraction) and draws the instants. The stage frame is X east, Y north, Z up (spec 004 FR-004-02).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np
from pvlib import spa

_MAX_DRAWS = 200_000  # rejection cap per sample: a site and floor that never reach the floor raise instead of looping


@dataclass(frozen=True)
class SolarPosition:
    """Topocentric solar position with atmospheric refraction: zenith, elevation (= 90 - zenith), azimuth (deg)."""

    zenith_deg: float
    elevation_deg: float
    azimuth_deg: float  # [0, 360), eastward from north


@dataclass(frozen=True)
class SunSample:
    """One accepted sun draw: the UTC instant, its solar position and the stage-frame direction toward the sun."""

    utc: dt.datetime
    elevation_deg: float
    azimuth_deg: float
    direction_stage: tuple[float, float, float]


def _finite(name: str, value: float) -> float:
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return v


def solar_position(
    when_utc: dt.datetime,
    latitude_deg: float,
    longitude_deg: float,
    *,
    elevation_m: float = 0.0,
    pressure_mbar: float = 1013.25,
    temperature_c: float = 15.0,
    delta_t_s: float = 69.0,
    refraction_deg: float = 0.5667,
) -> SolarPosition:
    """Solar position at `when_utc` (timezone-aware) for a site; see the module docstring for the conventions."""
    if not isinstance(when_utc, dt.datetime) or when_utc.tzinfo is None or when_utc.utcoffset() is None:
        raise ValueError("when_utc must be a timezone-aware datetime")
    lat = _finite("latitude_deg", latitude_deg)
    lon = _finite("longitude_deg", longitude_deg)
    if abs(lat) > 90.0:
        raise ValueError(f"latitude_deg must be within [-90, 90], got {latitude_deg!r}")
    if abs(lon) > 180.0:
        raise ValueError(f"longitude_deg must be within [-180, 180], got {longitude_deg!r}")
    elev = _finite("elevation_m", elevation_m)
    press = _finite("pressure_mbar", pressure_mbar)
    temp = _finite("temperature_c", temperature_c)
    delta_t = _finite("delta_t_s", delta_t_s)
    refr = _finite("refraction_deg", refraction_deg)
    unix = np.array([when_utc.timestamp()], dtype=np.float64)
    out = spa.solar_position_numpy(unix, lat, lon, elev, press, temp, delta_t, refr, 1, False, False)
    zenith = float(out[0][0])  # apparent topocentric zenith angle: corrected for refraction, as the SPA reports it
    azimuth = float(out[4][0]) % 360.0
    return SolarPosition(zenith_deg=zenith, elevation_deg=90.0 - zenith, azimuth_deg=azimuth)


def sun_direction_stage(elevation_deg: float, azimuth_deg: float) -> tuple[float, float, float]:
    """Unit vector from the scene toward the sun in the stage frame (X east, Y north, Z up); azimuth clockwise from north."""
    el = math.radians(_finite("elevation_deg", elevation_deg))
    az = math.radians(_finite("azimuth_deg", azimuth_deg))
    c = math.cos(el)
    return (c * math.sin(az), c * math.cos(az), math.sin(el))


def sample_sun(
    rng: np.random.Generator,
    *,
    latitude_deg: float,
    longitude_deg: float,
    year: int,
    elevation_m: float = 0.0,
    min_elevation_deg: float = 5.0,
) -> SunSample:
    """First UTC instant drawn uniformly over `year` whose solar elevation is at least `min_elevation_deg`."""
    t0 = dt.datetime(year, 1, 1, tzinfo=dt.UTC)
    span_s = (dt.datetime(year + 1, 1, 1, tzinfo=dt.UTC) - t0).total_seconds()
    floor = _finite("min_elevation_deg", min_elevation_deg)
    for _ in range(_MAX_DRAWS):
        when = t0 + dt.timedelta(seconds=float(rng.uniform(0.0, span_s)))
        pos = solar_position(when, latitude_deg, longitude_deg, elevation_m=elevation_m)
        if pos.elevation_deg >= floor:
            return SunSample(when, pos.elevation_deg, pos.azimuth_deg, sun_direction_stage(pos.elevation_deg, pos.azimuth_deg))
    raise ValueError(f"no instant with solar elevation >= {floor} deg in {_MAX_DRAWS} draws at this site and year")

# SPDX-License-Identifier: Apache-2.0
"""Domain-randomisation samplers (FR-014-13, FR-014-19, P-014-14).

Every sampler is a pure function of ``(seed, episode, randomisation)``: the generator is built per call from a
``SeedSequence`` of the seed, the episode and a task tag, so the result never depends on call order.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

DEG = math.pi / 180.0

__all__ = [
    "Il1Sample",
    "SoilSample",
    "heading_noise",
    "ray_noise",
    "sample_il1",
    "sample_soil",
    "speed_noise",
]

_TAG_SOIL = 0x534F494C
_TAG_IL1 = 0x494C3158

SOIL_LIMITS: dict[str, tuple[float, float]] = {
    "bulk_density_kg_m3": (1500.0, 2100.0),
    "cohesion_kpa": (0.0, 20.0),
    "adhesion_ratio": (0.0, 0.5),
    "friction_angle_deg": (25.0, 40.0),
    "soil_tool_friction_deg": (10.0, 25.0),
}
SOIL_FACE_NOISE_LIMIT = 0.3

IL1_LIMITS: dict[str, tuple[float, float]] = {
    "payload_fraction": (0.0, 1.0),
    "rolling_resistance_pct": (2.0, 8.0),
    "friction_dry": (0.55, 0.75),
    "friction_wet": (0.25, 0.45),
    "actuator_delay_steps": (0.0, 3.0),
}
IL1_NOISE_LIMITS: dict[str, float] = {
    "ray_noise_base_m": 0.02,
    "ray_noise_per_range": 0.01,
    "speed_noise_sd_m_per_s": 0.1,
    "heading_noise_sd_deg": 0.5,
}


@dataclass(frozen=True)
class SoilSample:
    rho: float  # kg/m3
    c: float  # Pa
    c_a: float  # Pa
    phi: float  # rad
    delta: float  # rad
    q: float  # Pa
    face_noise: float  # m


@dataclass(frozen=True)
class Il1Sample:
    payload_fraction: float
    rolling_resistance: float  # fraction (0.02 .. 0.08)
    friction: float
    wet: bool
    actuator_delay_steps: int


def _int_arg(name: str, value: Any, lo: int, hi: int | None) -> int:
    if isinstance(value, bool) or not isinstance(value, int | np.integer):
        raise TypeError(f"{name} must be an integer, got {value!r}")
    v = int(value)
    if v < lo or (hi is not None and v > hi):
        raise ValueError(f"{name} must be in [{lo}, {hi if hi is not None else 'inf'}], got {v}")
    return v


def _rng(seed: Any, episode: Any, tag: int) -> np.random.Generator:
    s = _int_arg("seed", seed, 0, 2**32 - 1)
    e = _int_arg("episode", episode, 0, None)
    return np.random.default_rng(np.random.SeedSequence([s, e, tag]))


def _range(block: Mapping[str, Any], key: str, limits: tuple[float, float]) -> tuple[float, float]:
    raw = block.get(key, list(limits))
    if not isinstance(raw, Sequence) or isinstance(raw, str) or len(raw) != 2:
        raise ValueError(f"{key} must be a [lower, upper] pair, got {raw!r}")
    try:
        lo, hi = float(raw[0]), float(raw[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must hold numbers, got {raw!r}") from exc
    if not (math.isfinite(lo) and math.isfinite(hi)):
        raise ValueError(f"{key} must be finite, got {raw!r}")
    if lo > hi:
        raise ValueError(f"{key} has lower > upper: {raw!r}")
    if lo < limits[0] or hi > limits[1]:
        raise ValueError(f"{key} must lie within {list(limits)}, got {raw!r}")
    return lo, hi


def _scalar_cap(block: Mapping[str, Any], key: str, cap: float, *, exact: float | None = None) -> float:
    value = block.get(key, cap if exact is None else exact)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{key} must be a finite number >= 0, got {value!r}")
    if exact is not None and value != exact:
        raise ValueError(f"{key} must be {exact}, got {value!r}")
    if value > cap:
        raise ValueError(f"{key} must be <= {cap}, got {value!r}")
    return float(value)


def sample_soil(seed: int, episode: int, randomisation: Mapping[str, Any] | None = None) -> SoilSample:
    """One soil of FR-014-19 for (seed, episode); ``randomisation`` is the IL-2 task randomisation block."""
    rng = _rng(seed, episode, _TAG_SOIL)
    block: Mapping[str, Any] = randomisation or {}
    rho_r = _range(block, "bulk_density_kg_m3", SOIL_LIMITS["bulk_density_kg_m3"])
    c_r = _range(block, "cohesion_kpa", SOIL_LIMITS["cohesion_kpa"])
    a_r = _range(block, "adhesion_ratio", SOIL_LIMITS["adhesion_ratio"])
    phi_r = _range(block, "friction_angle_deg", SOIL_LIMITS["friction_angle_deg"])
    d_r = _range(block, "soil_tool_friction_deg", SOIL_LIMITS["soil_tool_friction_deg"])
    surcharge = block.get("surcharge_kpa", 0.0)
    if isinstance(surcharge, bool) or not isinstance(surcharge, int | float) or surcharge != 0:
        raise ValueError(f"surcharge_kpa must be 0, got {surcharge!r}")
    amp = _scalar_cap(block, "face_height_noise_m", SOIL_FACE_NOISE_LIMIT)
    u = rng.random(6)
    rho = rho_r[0] + u[0] * (rho_r[1] - rho_r[0])
    c = (c_r[0] + u[1] * (c_r[1] - c_r[0])) * 1000.0
    c_a = (a_r[0] + u[2] * (a_r[1] - a_r[0])) * c
    phi = (phi_r[0] + u[3] * (phi_r[1] - phi_r[0])) * DEG
    d_hi = min(d_r[1] * DEG, phi)
    d_lo = min(d_r[0] * DEG, d_hi)
    delta = d_lo + u[4] * (d_hi - d_lo)
    noise = amp * (2.0 * u[5] - 1.0)
    return SoilSample(rho=rho, c=c, c_a=c_a, phi=phi, delta=delta, q=0.0, face_noise=noise)


def sample_il1(seed: int, episode: int, randomisation: Mapping[str, Any] | None = None) -> Il1Sample:
    """One IL-1 episode sample of FR-014-13; ``randomisation`` is the IL-1 task randomisation block."""
    rng = _rng(seed, episode, _TAG_IL1)
    block: Mapping[str, Any] = randomisation or {}
    pay = _range(block, "payload_fraction", IL1_LIMITS["payload_fraction"])
    roll = _range(block, "rolling_resistance_pct", IL1_LIMITS["rolling_resistance_pct"])
    dry = _range(block, "friction_dry", IL1_LIMITS["friction_dry"])
    wet_r = _range(block, "friction_wet", IL1_LIMITS["friction_wet"])
    delay = _range(block, "actuator_delay_steps", IL1_LIMITS["actuator_delay_steps"])
    _scalar_cap(block, "wet_probability", 0.5, exact=0.5)
    for key, cap in IL1_NOISE_LIMITS.items():
        _scalar_cap(block, key, cap)
    delay_lo, delay_hi = math.ceil(delay[0]), math.floor(delay[1])
    if delay_lo > delay_hi:
        raise ValueError(f"actuator_delay_steps holds no integer: {[delay[0], delay[1]]!r}")
    u = rng.random(5)
    wet = bool(u[2] < 0.5)
    lo, hi = wet_r if wet else dry
    return Il1Sample(
        payload_fraction=pay[0] + u[0] * (pay[1] - pay[0]),
        rolling_resistance=(roll[0] + u[1] * (roll[1] - roll[0])) / 100.0,
        friction=lo + u[3] * (hi - lo),
        wet=wet,
        actuator_delay_steps=min(delay_lo + int(u[4] * (delay_hi - delay_lo + 1)), delay_hi),
    )


def ray_noise(
    ranges: np.ndarray, rng: np.random.Generator, *, base_m: float = 0.02, per_range: float = 0.01
) -> np.ndarray:
    """Independent N(0, (base_m + per_range r)^2) draws for the array of ranges r (m)."""
    r = np.asarray(ranges, dtype=np.float64)
    if not np.all(np.isfinite(r)) or np.any(r < 0.0):
        raise ValueError("ranges must be finite and >= 0")
    return rng.standard_normal(r.shape) * (base_m + per_range * r)


def speed_noise(rng: np.random.Generator, size: int, *, sd: float = 0.1) -> np.ndarray:
    """N(0, sd^2) speed measurement noise (m/s)."""
    return rng.standard_normal(size) * sd


def heading_noise(rng: np.random.Generator, size: int, *, sd_deg: float = 0.5) -> np.ndarray:
    """N(0, sd_deg^2) heading noise, returned in rad."""
    return rng.standard_normal(size) * (sd_deg * DEG)

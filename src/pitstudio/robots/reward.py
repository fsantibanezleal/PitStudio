# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""IL-1 reward terms and the speed limit from the haulage envelopes (FR-014-11, P-014-10)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

from pitstudio.robots._check import finite

TTC_PENALTY_THRESHOLD = 3.0  # s
REWARD_KEYS = ("progress", "lateral_error", "heading_error", "overspeed", "jerk", "collision", "ttc", "energy")
G = 9.81

__all__ = ["REWARD_KEYS", "TTC_PENALTY_THRESHOLD", "il1_reward", "il1_reward_terms", "speed_limit"]


def _envelope(envelope: Sequence[Sequence[float]]) -> np.ndarray:
    try:
        arr = np.array(envelope, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("envelope must be rows of (speed, rimpull, retarder)") from exc
    if arr.ndim != 2 or arr.shape[1] != 3 or arr.shape[0] < 2:
        raise ValueError(f"envelope must have at least two (speed, rimpull, retarder) rows, got shape {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("envelope holds a non-finite entry")
    if np.any(np.diff(arr[:, 0]) <= 0.0):
        raise ValueError("envelope speeds must be strictly increasing")
    if np.any(np.diff(arr[:, 1:], axis=0) > 0.0):
        raise ValueError("envelope rimpull and retarder forces must be non-increasing with speed")
    return arr


def _largest_speed_covering(speeds: np.ndarray, forces: np.ndarray, needed: float) -> float:
    """Largest speed at which the linearly interpolated force is >= needed (0 when even the first sample is below)."""
    if forces[0] < needed:
        return 0.0
    if forces[-1] >= needed:
        return float(speeds[-1])
    i = int(np.argmax(forces < needed))  # first sample below the need; forces[i - 1] >= needed
    f0, f1 = forces[i - 1], forces[i]
    return float(speeds[i - 1] + (speeds[i] - speeds[i - 1]) * (f0 - needed) / (f0 - f1))


def speed_limit(
    grade: float,
    payload_fraction: float,
    *,
    empty_mass_kg: float,
    rated_payload_kg: float,
    rolling_resistance: float,
    envelope: Sequence[Sequence[float]],
    site_limit_kmh: float = 40.0,
    g: float = G,
) -> float:
    """v_lim (m/s): the steady speed the rimpull (uphill) or retarder (downhill) envelope allows, capped at the site limit."""
    gr = finite("grade", grade)
    rr = finite("rolling_resistance", rolling_resistance)
    pf = finite("payload_fraction", payload_fraction)
    if not 0.0 <= pf <= 1.0:
        raise ValueError(f"payload_fraction must be in [0, 1], got {payload_fraction!r}")
    env = _envelope(envelope)
    cap = finite("site_limit_kmh", site_limit_kmh) / 3.6
    mass = empty_mass_kg + pf * rated_payload_kg
    tr = rr + gr
    if tr > 0.0:
        v_env = _largest_speed_covering(env[:, 0], env[:, 1], mass * g * tr)
    elif tr < 0.0:
        v_env = _largest_speed_covering(env[:, 0], env[:, 2], mass * g * (-tr))
    else:
        v_env = math.inf
    return min(cap, v_env)


def il1_reward_terms(
    *,
    phi: float,
    phi_next: float,
    gamma: float,
    e_lat: float,
    e_psi: float,
    speed: float,
    v_lim: float,
    jerk: float,
    collided: bool,
    ttc: float,
    traction_power: float,
    dt: float,
) -> dict[str, float]:
    """The unweighted, signed reward terms of one step."""
    return {
        "progress": gamma * phi_next - phi,
        "lateral_error": -abs(e_lat),
        "heading_error": -abs(e_psi),
        "overspeed": -max(0.0, speed - v_lim),
        "jerk": -abs(jerk),
        "collision": -1.0 if collided else 0.0,
        "ttc": -1.0 if ttc < TTC_PENALTY_THRESHOLD else 0.0,
        "energy": -traction_power * dt,
    }


def il1_reward(terms: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """Weighted sum over the eight terms; the weights must hold exactly those keys."""
    for key in REWARD_KEYS:
        if key not in weights:
            raise ValueError(f"weights lack the term {key!r}")
    for key in weights:
        if key not in REWARD_KEYS:
            raise ValueError(f"weights hold an unknown key {key!r}")
    return float(sum(weights[key] * terms[key] for key in REWARD_KEYS))

# SPDX-License-Identifier: Apache-2.0
"""Action mappings and the invalid-value rule of the IL tasks (FR-014-09, FR-014-10, FR-014-16)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

CONTROL_HZ = 20
CONTROL_DT = 1.0 / CONTROL_HZ

# termination reasons that count as a failure (FR-014-10, FR-014-12)
FAILURE_REASONS: frozenset[str] = frozenset({"invalid_value", "collision", "lateral_error", "time_limit"})

__all__ = [
    "CONTROL_DT",
    "CONTROL_HZ",
    "FAILURE_REASONS",
    "Il1Command",
    "Il1Limits",
    "il1_action_to_commands",
    "il1_limits",
    "il2_action_to_joint_velocity",
    "step_validity",
]


@dataclass(frozen=True)
class Il1Limits:
    max_steer_rate: float  # rad/s
    max_rimpull: float  # N
    max_retarder: float  # N


@dataclass(frozen=True)
class Il1Command:
    steer_rate: float  # rad/s
    rimpull: float  # N
    retarder: float  # N


def _pointer_number(doc: Mapping[str, Any], key: str) -> float:
    pointer = f"/{key}"
    if key not in doc:
        raise ValueError(f"{pointer}: missing member")
    value = doc[key]
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{pointer}: must be a finite number > 0, got {value!r}")
    return float(value)


def il1_limits(params: Mapping[str, Any]) -> Il1Limits:
    """Action limits from a machine-params document of kind haul-truck."""
    if params.get("kind") != "haul-truck":
        raise ValueError(f"/kind: expected 'haul-truck', got {params.get('kind')!r}")
    return Il1Limits(
        max_steer_rate=math.radians(_pointer_number(params, "max_steer_rate_deg_per_s")),
        max_rimpull=_pointer_number(params, "max_rimpull_n"),
        max_retarder=_pointer_number(params, "max_retarder_n"),
    )


def _action(action: Sequence[float] | np.ndarray, size: int) -> np.ndarray:
    try:
        arr = np.array(action, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"action must be {size} numbers, got {action!r}") from exc
    if arr.shape != (size,):
        raise ValueError(f"action must have shape ({size},), got {arr.shape}")
    return arr


def il1_action_to_commands(action: Sequence[float] | np.ndarray, limits: Il1Limits) -> Il1Command:
    """Two values in [-1, 1] (clipped): steering-rate fraction and a combined drive (+) / retarder (-) command."""
    a = np.clip(_action(action, 2), -1.0, 1.0)
    return Il1Command(
        steer_rate=float(a[0]) * limits.max_steer_rate,
        rimpull=max(float(a[1]), 0.0) * limits.max_rimpull,
        retarder=max(-float(a[1]), 0.0) * limits.max_retarder,
    )


def il2_action_to_joint_velocity(
    action: Sequence[float] | np.ndarray, max_velocity: Sequence[float] | np.ndarray
) -> np.ndarray:
    """clip(action, -1, 1) * max_velocity for the four excavator joints."""
    a = np.clip(_action(action, 4), -1.0, 1.0)
    v = np.asarray(max_velocity, dtype=np.float64)
    if v.shape != (4,):
        raise ValueError(f"max_velocity must have shape (4,), got {v.shape}")
    return a * v


def step_validity(obs: np.ndarray, action: np.ndarray) -> str | None:
    """invalid_value when the observation or the action holds a NaN or an infinity, else None."""
    finite_obs = np.all(np.isfinite(np.asarray(obs, dtype=np.float64)))
    finite_act = np.all(np.isfinite(np.asarray(action, dtype=np.float64)))
    return None if (finite_obs and finite_act) else "invalid_value"

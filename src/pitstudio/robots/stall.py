# SPDX-License-Identifier: Apache-2.0
"""Stall detector of the IL-2 excavator (FR-014-20): |tau| >= 0.99 tau_max held for >= 1.0 s on one joint."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pitstudio.robots._check import positive

STALL_FRACTION = 0.99
STALL_SECONDS = 1.0

__all__ = ["STALL_FRACTION", "STALL_SECONDS", "StallEvent", "is_stalled", "stall_events"]


@dataclass(frozen=True)
class StallEvent:
    joint: int
    start: int  # first sample of the run
    end: int  # one past the last sample


def stall_events(torque: np.ndarray, tau_max: np.ndarray, dt: float) -> list[StallEvent]:
    """Runs of at least ``STALL_SECONDS`` of one joint holding |tau| >= ``STALL_FRACTION`` tau_max."""
    step = positive("dt", dt)
    tau = np.asarray(torque, dtype=np.float64)
    if tau.ndim != 2:
        raise ValueError(f"torque must be a (T, J) array, got shape {tau.shape}")
    limit = np.asarray(tau_max, dtype=np.float64)
    if limit.ndim != 1:
        raise ValueError(f"tau_max must be a 1-D array of joint limits, got shape {limit.shape}")
    if limit.shape[0] != tau.shape[1]:
        raise ValueError(f"torque must have one column per tau_max entry ({limit.shape[0]}), got shape {tau.shape}")
    if not np.all(np.isfinite(limit)) or np.any(limit <= 0.0):
        raise ValueError("tau_max must be finite and > 0 for every joint")
    if not np.all(np.isfinite(tau)):
        raise ValueError("torque holds a non-finite entry")
    held = np.abs(tau) >= STALL_FRACTION * limit[None, :]
    events: list[StallEvent] = []
    for joint in range(tau.shape[1]):
        n = tau.shape[0]
        i = 0
        col = held[:, joint]
        while i < n:
            if not col[i]:
                i += 1
                continue
            j = i
            while j < n and col[j]:
                j += 1
            if (j - i) * step >= STALL_SECONDS - 1e-9:
                events.append(StallEvent(joint, i, j))
            i = j
    events.sort(key=lambda e: (e.joint, e.start))
    return events


def is_stalled(torque: np.ndarray, tau_max: np.ndarray, dt: float) -> bool:
    return bool(stall_events(torque, tau_max, dt))

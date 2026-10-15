# SPDX-License-Identifier: Apache-2.0
"""Observation builders of the IL tasks (FR-014-08, FR-014-15)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from pitstudio.robots._check import positive, vector

IL2_LAYOUT: tuple[tuple[str, int], ...] = (
    ("joint_positions", 4),
    ("joint_velocities", 4),
    ("joint_torques", 4),
    ("bucket_tip_pose", 3),
    ("terrain_heights", 30),
    ("fill_estimate", 1),
)
IL2_OBS_SIZE = 46
TERRAIN_AHEAD_SPACING = 0.1  # m


def il2_observation(
    *,
    joint_pos: Sequence[float],
    joint_vel: Sequence[float],
    joint_torque: Sequence[float],
    tip_xz: Sequence[float],
    lip_pitch: float,
    terrain_x: Sequence[float],
    terrain_z: Sequence[float],
    v_fill: float,
    v_heaped: float,
) -> np.ndarray:
    """46-element float32 vector of the excavator task."""
    pos = vector("joint_pos", joint_pos, 4)
    vel = vector("joint_vel", joint_vel, 4)
    tau = vector("joint_torque", joint_torque, 4)
    tip = vector("tip_xz", tip_xz, 2)
    tx = vector("terrain_x", terrain_x, min_size=2)
    tz = vector("terrain_z", terrain_z, tx.shape[0])
    vh = positive("v_heaped", v_heaped)
    pitch = vector("lip_pitch", [lip_pitch], 1)[0]
    fill = vector("v_fill", [v_fill], 1)[0]
    heights = np.interp(tip[0] + TERRAIN_AHEAD_SPACING * (np.arange(30) + 1), tx, tz)
    return np.concatenate([pos, vel, tau, [tip[0], tip[1], pitch], heights, [fill / vh]]).astype(np.float32)

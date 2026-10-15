# SPDX-License-Identifier: Apache-2.0
"""Reference twins of the IL tasks (NumPy float64): the IL-1 dynamic bicycle and the IL-2 planar arm.

FR-014-40, FR-014-41, FR-014-47, P-014-12. The TypeScript twins in ``web/src/engines/robots`` port these functions
operation by operation, so the order of the arithmetic here is part of the contract.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from pitstudio.robots._check import finite, non_negative, positive, vector
from pitstudio.robots.fee import G, clamp_rake, cutting_force, fill_weight
from pitstudio.robots.fill import FILL_CAP, cut_step
from pitstudio.robots.machines import validate_machine

STATE_NAMES = ("x", "y", "psi", "vx", "vy", "r", "delta")

__all__ = [
    "STATE_NAMES",
    "ArmParams",
    "ArmSoil",
    "ArmStep",
    "BicycleEnv",
    "BicycleParams",
    "BicycleStep",
    "arm_step",
    "bicycle_params_from_machine",
    "bicycle_step",
    "forward_kinematics",
    "joint_torques",
]


# ------------------------------------------------------------------------------------------------------ bicycle
@dataclass(frozen=True)
class BicycleParams:
    mass_kg: float
    rated_payload_kg: float
    yaw_inertia_kg_m2: float
    a: float  # centre of gravity to the front axle (m)
    b: float  # centre of gravity to the rear axle (m)
    c_front: float  # N/rad
    c_rear: float  # N/rad
    max_steer: float  # rad
    max_steer_rate: float  # rad/s
    envelope: tuple[tuple[float, float, float], ...]  # (speed m/s, rimpull N, retarder N)
    dt: float = 0.01
    kinematic_below: float = 1.0

    @classmethod
    def from_twin(cls, parameters: Mapping[str, Any]) -> BicycleParams:
        """From the ``parameters`` block of a truck twin (contracts/il-twin.schema.json)."""
        p = parameters
        env = tuple(
            (float(row["speed_m_per_s"]), float(row["rimpull_n"]), float(row["retarder_n"])) for row in p["envelope"]
        )
        return cls(
            mass_kg=float(p["mass_kg"]),
            rated_payload_kg=float(p["rated_payload_kg"]),
            yaw_inertia_kg_m2=float(p["yaw_inertia_kg_m2"]),
            a=float(p["cg_to_front_axle_m"]),
            b=float(p["cg_to_rear_axle_m"]),
            c_front=float(p["cornering_stiffness_front_n_per_rad"]),
            c_rear=float(p["cornering_stiffness_rear_n_per_rad"]),
            max_steer=math.radians(float(p["max_steer_deg"])),
            max_steer_rate=math.radians(float(p["max_steer_rate_deg_per_s"])),
            envelope=env,
            dt=float(p["dt_s"]),
            kinematic_below=float(p["kinematic_below_m_per_s"]),
        )


def bicycle_params_from_machine(
    machine: Mapping[str, Any],
    envelope: Sequence[Sequence[float]],
    *,
    dt: float = 0.01,
    kinematic_below: float = 1.0,
) -> BicycleParams:
    """Twin parameters from a haul-truck machine file and a (speed, rimpull, retarder) envelope."""
    validate_machine(machine, "haul-truck")
    m = machine
    return BicycleParams(
        mass_kg=m["empty_mass_kg"],
        rated_payload_kg=m["rated_payload_kg"],
        yaw_inertia_kg_m2=m["yaw_inertia_kg_m2"],
        a=m["cg_to_front_axle_m"],
        b=m["wheelbase_m"] - m["cg_to_front_axle_m"],
        c_front=m["cornering_stiffness_front_n_per_rad"],
        c_rear=m["cornering_stiffness_rear_n_per_rad"],
        max_steer=math.radians(m["max_steer_deg"]),
        max_steer_rate=math.radians(m["max_steer_rate_deg_per_s"]),
        envelope=tuple((float(s), float(r), float(t)) for s, r, t in envelope),
        dt=dt,
        kinematic_below=kinematic_below,
    )


@dataclass(frozen=True)
class BicycleEnv:
    payload_fraction: float = 0.0
    grade: float = 0.0
    rolling_resistance: float = 0.03


@dataclass(frozen=True)
class BicycleStep:
    state: np.ndarray
    force_x: float
    traction_power: float


def _interp(envelope: tuple[tuple[float, float, float], ...], speed: float, column: int) -> float:
    """Linear interpolation over speed, held at the end samples."""
    if speed <= envelope[0][0]:
        return envelope[0][column]
    for i in range(len(envelope) - 1):
        s0, s1 = envelope[i][0], envelope[i + 1][0]
        if speed <= s1:
            f0, f1 = envelope[i][column], envelope[i + 1][column]
            return f0 + (f1 - f0) * (speed - s0) / (s1 - s0)
    return envelope[-1][column]


def bicycle_step(
    state: Sequence[float] | np.ndarray,
    steer_rate_cmd: float,
    drive_cmd: float,
    params: BicycleParams,
    env: BicycleEnv | None = None,
    dt: float | None = None,
) -> BicycleStep:
    """One semi-implicit Euler step of the dynamic bicycle (kinematic below ``kinematic_below`` m/s)."""
    s = vector("state", state, 7)
    cmd_s = finite("steer_rate_cmd", steer_rate_cmd)
    cmd_d = finite("drive_cmd", drive_cmd)
    h = positive("dt", params.dt if dt is None else dt)
    e = env or BicycleEnv()
    p = params
    x, y, psi, vx, vy, r, delta = (float(v) for v in s)
    mass = p.mass_kg + e.payload_fraction * p.rated_payload_kg
    length = p.a + p.b
    new_delta = delta + min(max(cmd_s, -1.0), 1.0) * p.max_steer_rate * h
    new_delta = min(max(new_delta, -p.max_steer), p.max_steer)
    u = min(max(cmd_d, -1.0), 1.0)
    speed = max(vx, 0.0)
    if u > 0.0:
        f_long = u * _interp(p.envelope, speed, 1)
    elif u < 0.0:
        f_long = u * _interp(p.envelope, speed, 2)
    else:
        f_long = 0.0
    f_res = mass * G * (e.rolling_resistance + e.grade) if vx > 0.0 else mass * G * e.grade
    power = max(f_long, 0.0) * vx
    if vx >= p.kinematic_below:
        alpha_f = new_delta - math.atan2(vy + p.a * r, vx)
        alpha_r = -math.atan2(vy - p.b * r, vx)
        f_yf = p.c_front * alpha_f
        f_yr = p.c_rear * alpha_r
        sin_d, cos_d = math.sin(new_delta), math.cos(new_delta)
        a_x = (f_long - f_res - f_yf * sin_d) / mass + r * vy
        a_y = (f_yf * cos_d + f_yr) / mass - r * vx
        r_dot = (p.a * f_yf * cos_d - p.b * f_yr) / p.yaw_inertia_kg_m2
        new_vx = vx + a_x * h
        new_vy = vy + a_y * h
        new_r = r + r_dot * h
    else:
        new_vx = vx + (f_long - f_res) / mass * h
        new_r = new_vx * math.tan(new_delta) / length
        new_vy = p.b * new_r
    new_psi = psi + new_r * h
    new_x = x + (new_vx * math.cos(new_psi) - new_vy * math.sin(new_psi)) * h
    new_y = y + (new_vx * math.sin(new_psi) + new_vy * math.cos(new_psi)) * h
    out = np.array([new_x, new_y, new_psi, new_vx, new_vy, new_r, new_delta], dtype=np.float64)
    return BicycleStep(state=out, force_x=f_long, traction_power=power)


# ---------------------------------------------------------------------------------------------------------- arm
@dataclass(frozen=True)
class ArmParams:
    pivot: tuple[float, float]  # boom pivot (x, z) in the machine frame
    lengths: np.ndarray  # boom, stick, bucket (m)
    lower: np.ndarray  # joint limits (rad)
    upper: np.ndarray
    tau_max: np.ndarray  # N m
    v_max: np.ndarray  # rad/s
    width: float  # bucket width (m)
    v_heaped: float  # rated heaped volume (m3)
    fill_cap: float = FILL_CAP
    g: float = G
    dt: float = 0.01

    @classmethod
    def from_twin(cls, parameters: Mapping[str, Any]) -> ArmParams:
        """From the ``parameters`` block of an arm twin (contracts/il-twin.schema.json)."""
        p = parameters
        names = ("boom", "stick", "bucket")
        joints = p["joints"]
        return cls(
            pivot=(float(p["boom_pivot_m"][0]), float(p["boom_pivot_m"][1])),
            lengths=np.array([float(p["links"][n]["length_m"]) for n in names]),
            lower=np.radians([float(joints[n]["lower_deg"]) for n in names]),
            upper=np.radians([float(joints[n]["upper_deg"]) for n in names]),
            tau_max=np.array([float(joints[n]["torque_max_n_m"]) for n in names]),
            v_max=np.radians([float(joints[n]["velocity_max_deg_per_s"]) for n in names]),
            width=float(p["bucket_width_m"]),
            v_heaped=float(p["heaped_volume_m3"]),
            fill_cap=float(p["fill_cap"]),
            g=float(p["gravity_m_per_s2"]),
            dt=float(p["dt_s"]),
        )


@dataclass(frozen=True)
class ArmSoil:
    rho: float
    c: float
    c_a: float
    phi: float
    delta: float
    q: float = 0.0


@dataclass(frozen=True)
class ArmStep:
    q: np.ndarray
    v_fill: float
    heights: np.ndarray
    tip: np.ndarray  # the tip before the step
    force: np.ndarray  # (Fx, Fz) on the tip
    torque: np.ndarray  # J^T F
    scale: float  # velocity scale of the torque limit


def forward_kinematics(q: np.ndarray, params: ArmParams) -> np.ndarray:
    """Rows: boom pivot, stick pivot, bucket pivot, bucket tip (machine frame, x forward, z up)."""
    theta = np.cumsum(np.asarray(q, dtype=np.float64))
    pts = np.empty((4, 2))
    pts[0] = params.pivot
    for i in range(3):
        pts[i + 1, 0] = pts[i, 0] + params.lengths[i] * math.cos(theta[i])
        pts[i + 1, 1] = pts[i, 1] + params.lengths[i] * math.sin(theta[i])
    return pts


def joint_torques(q: np.ndarray, force_xz: Sequence[float], params: ArmParams) -> np.ndarray:
    """J^T F for a tip force (Fx, Fz): tau_i = -(z_tip - z_i) Fx + (x_tip - x_i) Fz."""
    pts = forward_kinematics(q, params)
    tip = pts[3]
    fx, fz = float(force_xz[0]), float(force_xz[1])
    return np.array([-(tip[1] - pts[i, 1]) * fx + (tip[0] - pts[i, 0]) * fz for i in range(3)])


def _jacobian(pts: np.ndarray) -> np.ndarray:
    tip = pts[3]
    return np.array([[-(tip[1] - pts[i, 1]) for i in range(3)], [tip[0] - pts[i, 0] for i in range(3)]])


def arm_step(
    q: Sequence[float] | np.ndarray,
    v_fill: float,
    heights: Sequence[float] | np.ndarray,
    action: Sequence[float] | np.ndarray,
    params: ArmParams,
    soil: ArmSoil,
    *,
    terrain_dx: float = 0.1,
    terrain_x0: float = 0.0,
    dt: float | None = None,
) -> ArmStep:
    """One step of the planar arm: commanded velocity, FEE force, torque-limit scaling, limits, fill model."""
    q_in = vector("q", q, 3)
    fill = non_negative("v_fill", v_fill)
    h_in = vector("heights", heights, min_size=2)
    act = vector("action", action, 4)
    dx = positive("terrain_dx", terrain_dx)
    x0 = finite("terrain_x0", terrain_x0)
    step = positive("dt", params.dt if dt is None else dt)
    p = params
    dq_cmd = np.clip(act[1:4], -1.0, 1.0) * p.v_max
    pts = forward_kinematics(q_in, p)
    tip = pts[3].copy()
    v_tip = _jacobian(pts) @ dq_cmd
    grid_x = x0 + dx * np.arange(h_in.shape[0])
    surface = float(np.interp(tip[0], grid_x, h_in))
    depth = surface - tip[1]
    rake = clamp_rake(-float(np.sum(q_in)))
    cutting = depth > 0.0 and v_tip[0] > 0.0
    fx, fz = cutting_force(
        depth=depth, tip_velocity_x=float(v_tip[0]), rake=rake, delta=soil.delta, phi=soil.phi, rho=soil.rho,
        c=soil.c, c_a=soil.c_a, q=soil.q, w=p.width, g=p.g,
    )  # fmt: skip
    force = np.array([fx, fz - fill_weight(fill, soil.rho, p.g)])
    torque = joint_torques(q_in, force, p)
    nonzero = torque != 0.0
    scale = 1.0
    if np.any(nonzero):
        scale = min(1.0, float(np.min(p.tau_max[nonzero] / np.abs(torque[nonzero]))))
    new_q = np.clip(q_in + scale * dq_cmd * step, p.lower, p.upper)
    new_tip = forward_kinematics(new_q, p)[3]
    ds = float(np.hypot(*(new_tip - tip)))
    cut = cut_step(
        fill, h_in, dx=dx, tip_x=float(tip[0] - x0), depth=max(depth, 0.0), ds=ds, width=p.width,
        v_heaped=p.v_heaped, cutting=bool(cutting), fill_cap=p.fill_cap,
    )  # fmt: skip
    return ArmStep(q=new_q, v_fill=cut.v_fill, heights=cut.heights, tip=tip, force=force, torque=torque, scale=scale)

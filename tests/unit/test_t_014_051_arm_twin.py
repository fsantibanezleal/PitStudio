# ruff: noqa: E501
"""T-014-051: IL-2 planar arm twin with the FEE force and torque-limited stalls (NumPy float64 reference).

Requirements: FR-014-41.

Spec: specs/014-robot-learning/spec.md FR-014-41: "The IL-2 twin shall be a planar kinematic arm (boom, stick, bucket; swing fixed) with
joint limits, the FEE force of FR-014-17 and the fill model of FR-014-18, where joint velocities are scaled down whenever the joint torque
J^T F would exceed tau_max (so stalls are reproduced), implemented as a NumPy float64 reference and a TypeScript port."

Oracle: hand calculation on one fixed configuration of the excavator of `il-twin.valid-il2.json` (boom pivot (0.2, 2.0) m, links 6.0, 3.0 and
1.5 m, bucket width 1.2 m, V_h = 1.5 m3): with the joint angles q = (0, -90 deg, 0) the three links are horizontal, vertical down and vertical
down, so the joint centres are p0 = (0.2, 2.0), p1 = (6.2, 2.0), p2 = (6.2, -1.0) and the bucket tip is (6.2, -2.5). A planar tip force (Fx, Fz) gives
the joint torques tau_i = -(z_tip - z_i) Fx + (x_tip - x_i) Fz, that is tau = (4.5 Fx + 6.0 Fz, 4.5 Fx, 1.5 Fx); the FEE force of the soil
(rho = 1,800 kg/m3, phi = 35 deg, delta = 20 deg, c = c_a = q = 0) on a 90-degree rake lip 0.5 m deep and 1.2 m wide is 1.2 times the printed table
row alpha = 90 deg (spec 014 section 7: H = 17.2648 kN, V = -6.2839 kN per metre of width), so Fx = -H = -20,717.8 N and Fz = -V = +7,540.7 N; the
weight of 1.0 m3 of soil is 1,800 * 9.81 * 1.0 = 17,658 N. The kinematics and the fill bookkeeping are re-derived in this file.

Conventions (the spec is silent; see the red report): angles are absolute-accumulating, theta1 = q_boom, theta2 = theta1 + q_stick, theta3 = theta2 +
q_bucket, each link pointing along (cos theta, sin theta) in the machine frame (x forward, z up); the rake of the lip is clamp_rake(-theta3);
the terrain height under the tip is the linear interpolation of the profile (cell i at x = terrain_x0 + i * terrain_dx); the depth is that height
minus the tip height. Per step: (1) joint velocity commands dq_cmd = clip(action[1:4], -1, 1) * v_max (the swing action action[0] is ignored);
(2) the commanded tip velocity J dq_cmd, with dtip/dq_i = (-(z_tip - z_i), x_tip - x_i); (3) F = cutting_force(depth, vx_cmd, rake, soil, w) plus
(0, -fill_weight(v_fill, rho)); (4) tau = J^T F; (5) s = min(1, min over i with tau_i != 0 of tau_max_i / |tau_i|); (6) q' = clip(q + s dq_cmd dt, limits);
(7) the fill model advances with the path length |tip(q') - tip(q)| and the depth of (3), while cutting (depth > 0 and the commanded vx > 0).

Expected API of the implementation (module `pitstudio.robots.twins`, see T-014-050 for the bicycle half):
    ArmParams: frozen dataclass (pivot (x, z), lengths (3,), lower (3,) and upper (3,) joint limits [rad], tau_max (3,) [N m], v_max (3,) [rad/s],
        width [m], v_heaped [m3], fill_cap, g, dt)
        classmethod from_twin(parameters) -> ArmParams            the `parameters` block of an arm twin (contracts/il-twin.schema.json)
    ArmSoil: frozen dataclass (rho, c, c_a, phi, delta, q=0.0), SI units and rad
    forward_kinematics(q, params) -> np.ndarray (4, 2)             rows: boom pivot, stick pivot, bucket pivot, bucket tip
    joint_torques(q, force_xz, params) -> np.ndarray (3,)          J^T F for a tip force (Fx, Fz)
    arm_step(q, v_fill, heights, action, params, soil, *, terrain_dx=0.1, terrain_x0=0.0, dt=None) -> ArmStep
        ArmStep: frozen dataclass with q (3,), v_fill, heights (new array), tip (2,) (the tip BEFORE the step), force (2,) and torque (3,) (of step
        (3) and (4)), scale (the s of step (5)); the inputs are not modified.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from pitstudio.robots.twins import ArmParams, ArmSoil, arm_step, forward_kinematics, joint_torques

ROOT = Path(__file__).resolve().parents[2]
TWIN = json.loads((ROOT / "specs/014-robot-learning/contracts/examples/il-twin.valid-il2.json").read_text("utf-8"))
P = ArmParams.from_twin(TWIN["parameters"])
SOIL = ArmSoil(rho=1800.0, c=0.0, c_a=0.0, phi=math.radians(35.0), delta=math.radians(20.0))
DEG = math.pi / 180.0
Q0 = np.array([0.0, -math.pi / 2, 0.0])
DT = 0.01
FLAT = np.full(120, -2.0)  # surface at z = -2.0, cells every 0.1 m from x = 0


def fk(q, pivot=(0.2, 2.0), lengths=(6.0, 3.0, 1.5)):
    th = np.cumsum(q)
    pts = [np.array(pivot, dtype=float)]
    for length, a in zip(lengths, th, strict=True):
        pts.append(pts[-1] + length * np.array([math.cos(a), math.sin(a)]))
    return np.array(pts)


# --------------------------------------------------------------------------------------------------- parameters
@pytest.mark.req("FR-014-41")
def test_the_parameters_come_from_the_twin_block_of_the_contract_example() -> None:
    assert tuple(P.pivot) == (0.2, 2.0)
    assert tuple(P.lengths) == (6.0, 3.0, 1.5)
    np.testing.assert_allclose(P.lower, np.radians([-40.0, -150.0, -170.0]), rtol=1e-12)
    np.testing.assert_allclose(P.upper, np.radians([60.0, -30.0, 40.0]), rtol=1e-12)
    np.testing.assert_allclose(P.tau_max, [400_000.0, 250_000.0, 120_000.0], rtol=1e-12)
    np.testing.assert_allclose(P.v_max, np.radians([30.0, 40.0, 60.0]), rtol=1e-12)
    assert (P.width, P.v_heaped, P.fill_cap, P.g, P.dt) == (1.2, 1.5, 1.15, 9.81, 0.01)


# --------------------------------------------------------------------------------------------------- kinematics
@pytest.mark.req("FR-014-41")
def test_forward_kinematics_of_the_hand_configuration() -> None:
    pts = forward_kinematics(Q0, P)
    np.testing.assert_allclose(pts, [[0.2, 2.0], [6.2, 2.0], [6.2, -1.0], [6.2, -2.5]], rtol=0, atol=1e-12)


@pytest.mark.req("FR-014-41")
@pytest.mark.parametrize(
    "q", [(0.3, -1.2, 0.5), (-0.5, -2.0, -1.0), (1.0, -0.6, 0.7), (0.0, -math.pi / 2, math.pi / 2)]
)
def test_forward_kinematics_matches_the_accumulated_angle_construction(q) -> None:
    np.testing.assert_allclose(forward_kinematics(np.array(q), P), fk(np.array(q)), rtol=0, atol=1e-12)


@pytest.mark.req("FR-014-41")
def test_joint_torques_of_the_hand_configuration() -> None:
    np.testing.assert_allclose(joint_torques(Q0, (1000.0, 0.0), P), [4500.0, 4500.0, 1500.0], rtol=1e-12)
    np.testing.assert_allclose(joint_torques(Q0, (0.0, -2000.0), P), [-12_000.0, 0.0, 0.0], atol=1e-9)
    np.testing.assert_allclose(joint_torques(Q0, (0.0, 0.0), P), 0.0, atol=0.0)


@pytest.mark.req("FR-014-41")
@pytest.mark.parametrize("q", [(0.3, -1.2, 0.5), (-0.5, -2.0, -1.0)])
def test_joint_torques_equal_the_virtual_work_of_a_tip_displacement(q) -> None:
    q = np.array(q)
    force = np.array([-3000.0, 1200.0])
    tau = joint_torques(q, force, P)
    eps = 1e-6
    for i in range(3):  # tau_i = F . d(tip)/d(q_i), checked by a central finite difference of the independent FK
        dq = np.zeros(3)
        dq[i] = eps
        grad = (fk(q + dq)[3] - fk(q - dq)[3]) / (2 * eps)
        assert tau[i] == pytest.approx(float(force @ grad), rel=1e-6)


# --------------------------------------------------------------------------------------------------- stepping
@pytest.mark.req("FR-014-41")
def test_with_no_command_and_no_contact_nothing_moves_and_the_empty_bucket_has_no_weight() -> None:
    out = arm_step(Q0, 0.0, FLAT, [0.0, 0.0, 0.0, 0.0], P, SOIL)
    np.testing.assert_allclose(out.q, Q0, rtol=0, atol=1e-15)
    assert out.v_fill == 0.0
    np.testing.assert_array_equal(out.heights, FLAT)
    np.testing.assert_allclose(out.tip, [6.2, -2.5], atol=1e-12)
    np.testing.assert_allclose(out.force, [0.0, 0.0], atol=0.0)  # the tip is 0.5 m below the surface but not moving
    np.testing.assert_allclose(out.torque, 0.0, atol=0.0)
    assert out.scale == 1.0


@pytest.mark.req("FR-014-41")
def test_cutting_applies_the_fee_force_and_the_joint_torques_of_the_hand_calculation() -> None:
    out = arm_step(
        Q0, 0.0, FLAT, [0.0, 0.0, 1.0, 0.0], P, SOIL
    )  # stick at full speed: the tip moves forward (+x) at 4.5 * 0.698 m/s
    np.testing.assert_allclose(out.force, [-20_717.8, 7_540.7], rtol=2e-3)  # 1.2 * (-17,264.8, +6,283.9)
    np.testing.assert_allclose(out.torque, [-47_985.9, -93_230.1, -31_076.7], rtol=5e-3)
    assert out.scale == 1.0  # every |tau_i| is below its limit (400, 250 and 120 kN m)
    dq2 = P.v_max[1] * DT
    assert out.q[1] == pytest.approx(-math.pi / 2 + dq2, rel=1e-12)
    np.testing.assert_allclose(out.q[[0, 2]], [0.0, 0.0], atol=1e-15)


@pytest.mark.req("FR-014-41")
def test_the_fill_model_follows_the_cut_and_the_terrain_is_lowered_by_the_removed_volume() -> None:
    out = arm_step(Q0, 0.0, FLAT, [0.0, 0.0, 1.0, 0.0], P, SOIL)
    ds = float(np.linalg.norm(fk(out.q)[3] - fk(Q0)[3]))
    assert out.v_fill == pytest.approx(1.2 * 0.5 * ds, rel=1e-9)  # w * d * |delta s_tip| with d = 0.5 m
    removed = float(np.sum(FLAT - out.heights)) * 0.1 * 1.2  # cross-section removed * width (cells 0.1 m apart)
    assert removed == pytest.approx(out.v_fill, rel=1e-9)
    assert np.all(out.heights <= FLAT)


@pytest.mark.req("FR-014-41")
def test_a_torque_above_the_limit_scales_the_joint_velocities_down_so_that_a_stall_is_reproduced() -> None:
    tight = replace(P, tau_max=np.array([400_000.0, 50_000.0, 120_000.0]))
    out = arm_step(Q0, 0.0, FLAT, [0.0, 0.0, 1.0, 0.0], tight, SOIL)
    want = 50_000.0 / abs(4.5 * -20_717.8)  # tau_2 = 4.5 Fx = -93,230 N m against a 50 kN m limit: s = 0.5363
    assert out.scale == pytest.approx(want, rel=3e-3)
    assert out.q[1] == pytest.approx(-math.pi / 2 + out.scale * P.v_max[1] * DT, rel=1e-9)
    # with the stalled velocity the torque at the limit would hold: |tau_2| * s <= tau_max
    assert abs(out.torque[1]) * out.scale <= 50_000.0 * (1.0 + 1e-9)


@pytest.mark.req("FR-014-41")
def test_the_weight_of_the_fill_loads_the_boom_and_can_stall_a_lift() -> None:
    above = np.full(120, -3.0)  # the tip (z = -2.5) is above this surface: no cutting force
    out = arm_step(Q0, 1.0, above, [0.0, 1.0, 0.0, 0.0], P, SOIL)
    np.testing.assert_allclose(out.force, [0.0, -17_658.0], rtol=1e-12)  # 1,800 * 9.81 * 1.0 m3 downwards
    np.testing.assert_allclose(out.torque, [-105_948.0, 0.0, 0.0], atol=1e-6)  # 6.0 * (-17,658)
    assert out.scale == 1.0  # |tau_1| = 106 kN m < 400 kN m
    weak = replace(P, tau_max=np.array([50_000.0, 250_000.0, 120_000.0]))
    stalled = arm_step(Q0, 1.0, above, [0.0, 1.0, 0.0, 0.0], weak, SOIL)
    assert stalled.scale == pytest.approx(50_000.0 / 105_948.0, rel=1e-9)  # 0.47192
    assert stalled.q[0] == pytest.approx(P.v_max[0] * stalled.scale * DT, rel=1e-9)
    assert stalled.v_fill == 1.0  # not cutting: the fill does not change


@pytest.mark.req("FR-014-41")
def test_joint_limits_are_respected() -> None:
    q = np.array([0.0, math.radians(-150.0), 0.0])  # the stick is at its lower limit
    out = arm_step(q, 0.0, np.full(120, -9.0), [0.0, 0.0, -1.0, 0.0], P, SOIL)
    assert out.q[1] == pytest.approx(math.radians(-150.0), rel=1e-12)
    q = np.array([math.radians(60.0), math.radians(-90.0), 0.0])
    out = arm_step(q, 0.0, np.full(120, -9.0), [0.0, 1.0, 0.0, 0.0], P, SOIL)
    assert out.q[0] == pytest.approx(math.radians(60.0), rel=1e-12)
    out = arm_step(np.array([math.radians(59.99), -1.0, 0.0]), 0.0, np.full(120, -9.0), [0.0, 1.0, 0.0, 0.0], P, SOIL)
    assert out.q[0] == pytest.approx(math.radians(60.0), rel=1e-12)  # clipped at the limit, not beyond


@pytest.mark.req("FR-014-41")
def test_actions_are_clipped_and_the_swing_component_is_ignored() -> None:
    free = np.full(120, -9.0)
    a = arm_step(Q0, 0.0, free, [0.0, 0.0, 5.0, 0.0], P, SOIL)
    b = arm_step(Q0, 0.0, free, [0.7, 0.0, 1.0, 0.0], P, SOIL)  # swing 0.7 does nothing in the planar twin
    np.testing.assert_allclose(a.q, b.q, rtol=0, atol=1e-15)
    assert a.q[1] == pytest.approx(-math.pi / 2 + P.v_max[1] * DT, rel=1e-12)  # 5.0 clipped to 1.0


@pytest.mark.req("FR-014-41")
def test_cutting_needs_the_commanded_motion_into_the_soil() -> None:
    back = arm_step(
        Q0, 0.0, FLAT, [0.0, 0.0, -1.0, 0.0], P, SOIL
    )  # the stick moves the tip backwards: no cutting force, no fill
    np.testing.assert_allclose(back.force, [0.0, 0.0], atol=0.0)
    assert back.v_fill == 0.0


@pytest.mark.req("FR-014-41")
def test_the_fill_stops_at_the_cap_and_the_inputs_are_not_modified() -> None:
    heights = FLAT.copy()
    out = arm_step(Q0, 1.7, heights, [0.0, 0.0, 1.0, 0.0], P, SOIL)  # 1.15 * 1.5 = 1.725 m3 cap
    assert out.v_fill <= 1.725 * (1.0 + 1e-12)
    np.testing.assert_array_equal(heights, FLAT)


@pytest.mark.req("FR-014-41")
def test_the_terrain_under_the_tip_is_interpolated_between_cells() -> None:
    sloped = -2.0 + 0.1 * np.arange(120) * 0.1  # z = -2.0 + 0.01 * (x / 0.1) * ... a ramp of 0.1 per metre
    out = arm_step(Q0, 0.0, sloped, [0.0, 0.0, 1.0, 0.0], P, SOIL)
    depth = (-2.0 + 0.1 * 6.2) - (-2.5)  # surface under x = 6.2 minus the tip height: 1.12 m
    ds = float(np.linalg.norm(fk(out.q)[3] - fk(Q0)[3]))
    assert out.v_fill == pytest.approx(1.2 * depth * ds, rel=1e-9)

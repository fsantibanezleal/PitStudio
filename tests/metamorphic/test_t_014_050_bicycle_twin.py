# ruff: noqa: E501
"""T-014-050: IL-1 dynamic-bicycle twin (NumPy float64 reference) and its metamorphic relations.

Requirements: FR-014-40, P-014-12.

Spec: specs/014-robot-learning/spec.md FR-014-40: "The IL-1 twin shall be a dynamic bicycle model - states x, y, psi, v_x, v_y, r, delta;
linear lateral tyre forces with per-axle cornering stiffness; longitudinal force from the `minephys.haulage` rimpull and retarder envelopes
minus rolling and grade resistance; semi-implicit Euler at dt = 0.01 s, switching to the kinematic bicycle below 1 m/s - implemented as a
NumPy float64 reference and a TypeScript port, with parameters mapped from the machine parameter file." P-014-12: (MR1) zero steering and
zero net longitudinal force on flat ground keep a straight line at constant speed; (MR2) mirrored steering inputs give mirrored
trajectories; (MR3) at constant delta and v the yaw rate converges to v delta / (L + K_us v^2); (MR4) an uphill run spends at least m g dh
of traction energy; v in [1, 15] m/s, delta in [-0.3, 0.3] rad, grades 0-12 %; atol 1e-9 (MR1, MR2), rtol 1e-2 (MR3), exact inequality (MR4).

Oracle: (1) MR1 and MR2 are exact symmetries (a straight line x = x0 + v t cos psi0; the mirror map y, psi, v_y, r, delta -> negatives); (2) MR3
is the classical linear-bicycle steady state with the understeer gradient K_us = m (b C_r - a C_f) / (C_f C_r L) (Gillespie, Fundamentals of
Vehicle Dynamics, 1992, eq. 6-17; Rajamani, Vehicle Dynamics and Control, 2012, eq. 2.45), evaluated here with the parameters of the contract
example `il-twin.valid.json` (a = 2.6 m, b = 2.7 m, C_f = 9e5 N/rad, C_r = 1.8e6 N/rad, m = 160,000 kg: K_us = 0.04696 s2/m); (3) MR4 is the
work-energy inequality: the traction energy sum(max(F, 0) v dt) covers m g times the height gained, grade * sum(v dt); (4) one-step hand
calculations with the envelope of that example (rimpull 800,000 N at 3 m/s, retarder 1,100,000 N at 6 m/s; linear interpolation between
samples), which also pin the semi-implicit order (new velocity used for the new position).

Equations of the reference (the TypeScript port and every test use these): m = mass + payload_fraction * rated_payload; L = a + b;
delta' = clip(delta + clip(steer_rate_cmd, -1, 1) * max_steer_rate * dt, -max_steer, max_steer); the drive force is u R(v_x) for u = drive_cmd > 0
and u Ret(v_x) (negative) for u < 0, with R and Ret linearly interpolated over speed max(v_x, 0) and held at the end samples; the resistance is
F_res = m g (RR + grade) for v_x > 0 and m g grade otherwise. Dynamic branch (v_x >= kinematic_below): alpha_f = delta' - atan2(v_y + a r, v_x),
alpha_r = -atan2(v_y - b r, v_x), F_yf = C_f alpha_f, F_yr = C_r alpha_r; a_x = (F_long - F_res - F_yf sin delta') / m + r v_y; a_y = (F_yf cos delta' +
F_yr) / m - r v_x; r_dot = (a F_yf cos delta' - b F_yr) / I_z; v_x' = v_x + a_x dt, v_y' = v_y + a_y dt, r' = r + r_dot dt. Kinematic branch (v_x <
kinematic_below): v_x' = v_x + (F_long - F_res) / m dt, r' = v_x' tan(delta') / L, v_y' = b r'. Pose: psi' = psi + r' dt, then x' = x + (v_x' cos psi' -
v_y' sin psi') dt and y' = y + (v_x' sin psi' + v_y' cos psi') dt. traction_power = max(F_long, 0) v_x (W, before the update).

Expected API of the implementation (module `pitstudio.robots.twins`):
    STATE_NAMES = ("x", "y", "psi", "vx", "vy", "r", "delta")
    BicycleParams: frozen dataclass (mass_kg, rated_payload_kg, yaw_inertia_kg_m2, a, b, c_front, c_rear, max_steer [rad], max_steer_rate [rad/s],
        envelope (tuple of (speed, rimpull, retarder) rows), dt, kinematic_below)
        classmethod from_twin(parameters) -> BicycleParams        the `parameters` block of a truck twin (contracts/il-twin.schema.json)
    bicycle_params_from_machine(machine, envelope, *, dt=0.01, kinematic_below=1.0) -> BicycleParams
        from a machine-params document of kind haul-truck (mass = empty_mass_kg, b = wheelbase - cg_to_front_axle, steering limits converted to rad)
    BicycleEnv: frozen dataclass (payload_fraction=0.0, grade=0.0, rolling_resistance=0.03)
    bicycle_step(state, steer_rate_cmd, drive_cmd, params, env=None, dt=None) -> BicycleStep
        state: array of 7 floats; dt defaults to params.dt; BicycleStep is a frozen dataclass with `state` (new float64 array (7,)), `force_x`
        (F_long, N) and `traction_power` (W).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.robots.twins import STATE_NAMES, BicycleEnv, BicycleParams, bicycle_params_from_machine, bicycle_step

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "014-robot-learning" / "contracts" / "examples"
TWIN = json.loads((EX / "il-twin.valid.json").read_text("utf-8"))
MACHINE = json.loads((EX / "machine-params.valid.json").read_text("utf-8"))
P = BicycleParams.from_twin(TWIN["parameters"])
G = 9.81
DT = 0.01
FLAT = BicycleEnv(payload_fraction=0.0, grade=0.0, rolling_resistance=0.0)
K_US = P.mass_kg * (P.b * P.c_rear - P.a * P.c_front) / (P.c_front * P.c_rear * (P.a + P.b))


def s0(x=0.0, y=0.0, psi=0.0, vx=8.0, vy=0.0, r=0.0, delta=0.0):
    return np.array([x, y, psi, vx, vy, r, delta], dtype=float)


# ---------------------------------------------------------------------------------------------- parameters
@pytest.mark.req("FR-014-40")
def test_state_names_and_the_parameter_mapping_from_the_twin_block_and_the_machine_file() -> None:
    assert STATE_NAMES == ("x", "y", "psi", "vx", "vy", "r", "delta")
    assert (P.mass_kg, P.rated_payload_kg, P.yaw_inertia_kg_m2) == (160_000.0, 220_000.0, 1_800_000.0)
    assert (P.a, P.b, P.c_front, P.c_rear) == (2.6, 2.7, 900_000.0, 1_800_000.0)
    assert P.max_steer == pytest.approx(math.radians(38.0), rel=1e-12)
    assert P.max_steer_rate == pytest.approx(math.radians(20.0), rel=1e-12)
    assert (P.dt, P.kinematic_below) == (0.01, 1.0)
    assert len(P.envelope) == 4
    assert tuple(P.envelope[1]) == (3.0, 800_000.0, 1_100_000.0)
    mapped = bicycle_params_from_machine(MACHINE, [tuple(row) for row in P.envelope])
    assert mapped.mass_kg == MACHINE["empty_mass_kg"]
    assert mapped.a == MACHINE["cg_to_front_axle_m"]
    assert mapped.b == pytest.approx(MACHINE["wheelbase_m"] - MACHINE["cg_to_front_axle_m"], rel=1e-12)
    assert mapped.c_front == MACHINE["cornering_stiffness_front_n_per_rad"]
    assert mapped.c_rear == MACHINE["cornering_stiffness_rear_n_per_rad"]
    assert mapped.yaw_inertia_kg_m2 == MACHINE["yaw_inertia_kg_m2"]
    assert mapped.max_steer == pytest.approx(math.radians(MACHINE["max_steer_deg"]), rel=1e-12)


# ------------------------------------------------------------------------------------ one-step hand calculations
@pytest.mark.req("FR-014-40")
def test_one_step_straight_drive_uses_the_envelope_the_resistance_and_the_semi_implicit_order() -> None:
    env = BicycleEnv(payload_fraction=0.0, grade=0.0, rolling_resistance=0.03)
    out = bicycle_step(s0(vx=3.0), 0.0, 0.5, P, env)
    # F = 0.5 * 800,000 (rimpull at 3 m/s) = 400,000 N; F_res = 160,000 * 9.81 * 0.03 = 47,088 N; a = 352,912 / 160,000 = 2.20570 m/s2
    assert out.force_x == pytest.approx(400_000.0, rel=1e-12)
    assert out.traction_power == pytest.approx(1.2e6, rel=1e-12)  # 400,000 N * 3 m/s
    vx = 3.0 + (400_000.0 - 47_088.0) / 160_000.0 * DT
    assert out.state[3] == pytest.approx(vx, rel=1e-12)  # 3.0220570
    assert out.state[0] == pytest.approx(
        vx * DT, rel=1e-12
    )  # the NEW velocity moves the position (semi-implicit Euler)
    assert out.state[0] != pytest.approx(3.0 * DT, rel=1e-6)  # an explicit Euler step would give 0.03
    np.testing.assert_allclose(out.state[[1, 2, 4, 5, 6]], 0.0, atol=1e-15)


@pytest.mark.req("FR-014-40")
def test_the_retarder_force_is_negative_and_interpolated_between_envelope_samples() -> None:
    env = BicycleEnv(payload_fraction=0.0, grade=0.0, rolling_resistance=0.0)
    out = bicycle_step(s0(vx=6.0), 0.0, -0.5, P, env)
    assert out.force_x == pytest.approx(-550_000.0, rel=1e-12)  # -0.5 * 1,100,000 at 6 m/s
    assert out.traction_power == 0.0  # braking spends no traction energy
    mid = bicycle_step(s0(vx=4.5), 0.0, 1.0, P, env)
    assert mid.force_x == pytest.approx(625_000.0, rel=1e-12)  # 800,000 + (450,000 - 800,000) * (4.5 - 3) / 3
    beyond = bicycle_step(s0(vx=20.0), 0.0, 1.0, P, env)
    assert beyond.force_x == pytest.approx(240_000.0, rel=1e-12)  # held at the last sample


@pytest.mark.req("FR-014-40")
def test_the_grade_and_the_payload_change_the_deceleration_by_hand_calculation() -> None:
    env = BicycleEnv(payload_fraction=0.5, grade=0.05, rolling_resistance=0.03)
    out = bicycle_step(s0(vx=6.0), 0.0, 0.0, P, env)
    m = 160_000.0 + 0.5 * 220_000.0
    ax = -m * G * (0.03 + 0.05) / m  # coasting uphill: -g (RR + grade) = -0.7848 m/s2
    assert out.state[3] == pytest.approx(6.0 + ax * DT, rel=1e-12)
    assert out.force_x == 0.0


@pytest.mark.req("FR-014-40")
def test_the_steering_angle_moves_at_the_rate_limit_and_stops_at_the_angle_limit() -> None:
    out = bicycle_step(s0(), 1.0, 0.0, P, FLAT)
    assert out.state[6] == pytest.approx(math.radians(20.0) * DT, rel=1e-12)  # 0.2 deg in one step
    out = bicycle_step(s0(), -3.0, 0.0, P, FLAT)  # the command is clipped to [-1, 1] first
    assert out.state[6] == pytest.approx(-math.radians(20.0) * DT, rel=1e-12)
    out = bicycle_step(s0(delta=math.radians(37.9999)), 1.0, 0.0, P, FLAT)
    assert out.state[6] == pytest.approx(math.radians(38.0), rel=1e-12)
    out = bicycle_step(s0(delta=-math.radians(38.0)), -1.0, 0.0, P, FLAT)
    assert out.state[6] == pytest.approx(-math.radians(38.0), rel=1e-12)


@pytest.mark.req("FR-014-40")
def test_below_one_metre_per_second_the_model_is_the_kinematic_bicycle() -> None:
    delta = 0.1
    out = bicycle_step(s0(vx=0.5, delta=delta), 0.0, 0.0, P, FLAT)
    vx = out.state[3]
    assert vx == pytest.approx(0.5, rel=1e-12)  # no force: no lateral force either
    assert out.state[5] == pytest.approx(vx * math.tan(delta) / (P.a + P.b), rel=1e-12)  # r = v tan(delta) / L
    assert out.state[4] == pytest.approx(P.b * out.state[5], rel=1e-12)  # v_y = b r


@pytest.mark.req("FR-014-40")
def test_the_dynamic_branch_one_step_lateral_dynamics_by_hand_calculation() -> None:
    # v_x = 10, v_y = r = 0, delta = 0.02 (held): alpha_f = 0.02, alpha_r = 0; F_yf = 900,000 * 0.02 = 18,000 N; F_yr = 0
    out = bicycle_step(s0(vx=10.0, delta=0.02), 0.0, 0.0, P, FLAT)
    fyf = 900_000.0 * 0.02
    ay = fyf * math.cos(0.02) / 160_000.0
    rdot = 2.6 * fyf * math.cos(0.02) / 1_800_000.0
    ax = -fyf * math.sin(0.02) / 160_000.0
    assert out.state[3] == pytest.approx(10.0 + ax * DT, rel=1e-12)
    assert out.state[4] == pytest.approx(ay * DT, rel=1e-12)
    assert out.state[5] == pytest.approx(rdot * DT, rel=1e-12)
    assert out.state[2] == pytest.approx(rdot * DT * DT, rel=1e-12)  # psi' = psi + r' dt with the new yaw rate


@pytest.mark.req("FR-014-40")
def test_the_input_state_is_not_modified() -> None:
    state = s0(vx=5.0)
    before = state.copy()
    out = bicycle_step(state, 1.0, 0.3, P, FLAT)
    np.testing.assert_array_equal(state, before)
    assert out.state is not state
    assert out.state.dtype == np.float64
    assert out.state.shape == (7,)


# ------------------------------------------------------------------------------------------------ P-014-12
def run(state, cmds, env=FLAT, params=P):
    out = [np.asarray(state, dtype=float)]
    power = []
    force = []
    for sc, dc in cmds:
        step = bicycle_step(out[-1], sc, dc, params, env)
        out.append(step.state)
        power.append(step.traction_power)
        force.append(step.force_x)
    return np.array(out), np.array(power), np.array(force)


@pytest.mark.req("P-014-12")
@given(
    st.floats(1.0, 15.0),
    st.floats(-math.pi, math.pi),
    st.floats(-50.0, 50.0),
    st.floats(-50.0, 50.0),
    st.integers(1, 400),
)
@settings(max_examples=200, deadline=None)
def test_mr1_zero_steering_and_zero_net_force_keep_a_straight_line_at_constant_speed(v, psi, x0, y0, n) -> None:
    traj, _p, _f = run(s0(x=x0, y=y0, psi=psi, vx=v), [(0.0, 0.0)] * n)
    t = np.arange(n + 1) * DT
    np.testing.assert_allclose(traj[:, 3], v, rtol=0, atol=1e-9)
    np.testing.assert_allclose(traj[:, 0], x0 + v * math.cos(psi) * t + 0.0, rtol=0, atol=1e-9)
    np.testing.assert_allclose(traj[:, 1], y0 + v * math.sin(psi) * t, rtol=0, atol=1e-9)
    np.testing.assert_allclose(traj[:, 2], psi, rtol=0, atol=1e-9)
    np.testing.assert_allclose(traj[:, [4, 5, 6]], 0.0, rtol=0, atol=1e-9)


@pytest.mark.req("P-014-12")
@given(
    st.floats(1.0, 15.0),
    st.lists(st.tuples(st.floats(-1.0, 1.0), st.floats(-1.0, 1.0)), min_size=20, max_size=300),
    st.floats(0.0, 0.12),
    st.floats(0.0, 1.0),
)
@settings(max_examples=200, deadline=None)
def test_mr2_mirrored_steering_inputs_give_mirrored_trajectories(v, cmds, grade, payload) -> None:
    env = BicycleEnv(payload_fraction=payload, grade=grade, rolling_resistance=0.03)
    a, _, _ = run(s0(vx=v), cmds, env)
    b, _, _ = run(s0(vx=v), [(-sc, dc) for sc, dc in cmds], env)
    sign = np.array([1.0, -1.0, -1.0, 1.0, -1.0, -1.0, -1.0])  # x, y, psi, vx, vy, r, delta
    np.testing.assert_allclose(b, a * sign, rtol=0, atol=1e-9)


@pytest.mark.req("P-014-12")
@pytest.mark.parametrize(("v", "delta"), [(5.0, 0.02), (8.0, 0.02), (8.0, -0.03), (12.0, 0.01), (3.0, 0.04)])
def test_mr3_the_yaw_rate_converges_to_v_delta_over_l_plus_k_us_v_squared(v, delta) -> None:
    state = s0(vx=v)
    for _ in range(2000):  # 20 s; the steering angle is brought to delta within the rate limit, then held
        cmd = float(np.clip((delta - state[6]) / (P.max_steer_rate * DT), -1.0, 1.0))
        state = bicycle_step(state, cmd, 0.0, P, FLAT).state
    assert state[6] == pytest.approx(delta, abs=1e-12)
    v_now = state[3]
    assert v_now > 0.95 * v  # the speed is nearly unchanged, so the steady-state formula applies at v_now
    theory = v_now * delta / ((P.a + P.b) + K_US * v_now**2)
    assert state[5] == pytest.approx(theory, rel=1e-2)


@pytest.mark.req("P-014-12")
def test_the_understeer_gradient_of_the_example_is_positive_so_the_yaw_rate_gain_peaks_at_the_critical_speed() -> None:
    assert pytest.approx(0.04696, abs=2e-5) == K_US  # hand calculation in the module docstring
    gain = lambda v: v / ((P.a + P.b) + K_US * v * v)  # noqa: E731
    v_crit = math.sqrt((P.a + P.b) / K_US)  # 10.62 m/s: the maximum of v / (L + K v^2)
    assert gain(v_crit) > gain(5.0)
    assert gain(v_crit) > gain(15.0)


@pytest.mark.req("P-014-12")
@given(st.floats(2.0, 5.0), st.floats(0.0, 0.08), st.floats(0.0, 0.5))
@settings(max_examples=100, deadline=None)
def test_mr4_an_uphill_run_spends_at_least_m_g_dh_of_traction_energy(v_target, grade, payload) -> None:
    env = BicycleEnv(payload_fraction=payload, grade=grade, rolling_resistance=0.03)
    state = s0(vx=v_target)
    energy = 0.0
    climbed = 0.0  # grade * sum(v dt): the height gained along the heading (small-angle grade)
    for _ in range(2000):  # 20 s with a proportional speed controller
        u = float(np.clip(3.0 * (v_target - state[3]), -1.0, 1.0))
        step = bicycle_step(state, 0.0, u, P, env)
        energy += step.traction_power * DT
        climbed += grade * step.state[3] * DT
        state = step.state
    m = 160_000.0 + payload * 220_000.0
    assert state[3] > 0.5 * v_target  # the truck kept moving (the claim is about a climb that happens)
    assert energy >= m * G * climbed


@pytest.mark.req("P-014-12")
def test_traction_energy_is_zero_when_coasting_or_braking() -> None:
    _t, power, _f = run(s0(vx=8.0), [(0.0, 0.0)] * 50 + [(0.0, -1.0)] * 50, BicycleEnv(0.0, 0.0, 0.03))
    assert np.all(power == 0.0)

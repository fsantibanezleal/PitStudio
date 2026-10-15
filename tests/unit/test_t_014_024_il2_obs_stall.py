# ruff: noqa: E501
"""T-014-024: IL-2 observation builder, action mapping and stall detector.

Requirements: FR-014-15, FR-014-16, FR-014-20 (FR-014-10 applies to IL-2 through FR-014-16).

Spec: specs/014-robot-learning/spec.md FR-014-15 (46-element vector: joint positions, velocities and torques of swing,
boom, stick and bucket (12); bucket tip position (x, z) and lip pitch in the machine frame (3); 30 terrain heights ahead of
the bucket tip at 0.1 m spacing (30); fill estimate V_fill / V_h (1)); FR-014-16 (four joint-velocity commands in [-1, 1],
clipped and scaled by each joint's maximum velocity; NaN or infinity terminates the episode with `invalid_value`, FR-014-10);
FR-014-20 (a stall event is an interval of >= 1.0 s in which a joint holds |tau| >= 0.99 tau_max; an episode with at least
one stall event is a stalled episode); the layout of the valid contract example `il-task.valid-il2.json`
(joint_positions 4, joint_velocities 4, joint_torques 4, bucket_tip_pose 3, terrain_heights 30, fill_estimate 1).

Oracle: hand-built arm states with known coordinates (index arithmetic written out below); a linear terrain
z(x) = 0.5 + 0.1 x whose interpolated heights are exact; the action mapping by hand (clip, then multiply); synthetic torque
traces of 0.99 s (99 samples at 0.01 s) against 1.00 s (100 samples), the plan's oracle for FR-014-20.

Expected API of the implementation (NumPy; joint order swing, boom, stick, bucket):
    module `pitstudio.robots.obs`
        IL2_OBS_SIZE = 46
        IL2_LAYOUT: tuple[tuple[str, int], ...]
            the segments (name, size) in order: ("joint_positions", 4), ("joint_velocities", 4), ("joint_torques", 4),
            ("bucket_tip_pose", 3), ("terrain_heights", 30), ("fill_estimate", 1)
        il2_observation(*, joint_pos, joint_vel, joint_torque, tip_xz, lip_pitch, terrain_x, terrain_z, v_fill, v_heaped)
            -> np.ndarray of dtype float32 and shape (46,): [pos(4), vel(4), torque(4), tip_x, tip_z, lip_pitch,
            heights(30), v_fill / v_heaped]; heights[k] is the terrain height z at x = tip_x + 0.1 (k + 1), k = 0 .. 29,
            by linear interpolation of the profile (terrain_x increasing, same length as terrain_z, m).
    module `pitstudio.robots.actions`
        il2_action_to_joint_velocity(action, max_velocity) -> np.ndarray float64 (4,)
            clip(action, -1, 1) * max_velocity; ValueError naming `action` for a wrong shape (not 4 values)
        step_validity(obs, action) -> str | None
            "invalid_value" if any element of obs or action is NaN or infinite, else None
        FAILURE_REASONS: frozenset[str]
            the termination reasons that count as a failure; contains "invalid_value" (FR-014-10)
    module `pitstudio.robots.stall`
        STALL_FRACTION = 0.99 ; STALL_SECONDS = 1.0
        stall_events(torque, tau_max, dt) -> list[StallEvent]
            torque: (T, J) joint torques (N m), tau_max: (J,) torque limits (> 0), dt: control step (s, > 0).
            A run of n consecutive samples of one joint with |tau| >= 0.99 tau_max lasts n * dt; it is an event when
            n * dt >= 1.0. StallEvent has int fields `joint`, `start` (first sample) and `end` (one past the last
            sample). Runs of different joints are never combined. ValueError naming `torque`, `tau_max` or `dt` for
            a wrong shape, a non-positive limit or a non-positive or non-finite step.
        is_stalled(torque, tau_max, dt) -> bool       True when stall_events is not empty
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from pitstudio.robots.actions import FAILURE_REASONS, il2_action_to_joint_velocity, step_validity
from pitstudio.robots.obs import IL2_LAYOUT, IL2_OBS_SIZE, il2_observation
from pitstudio.robots.stall import STALL_FRACTION, STALL_SECONDS, is_stalled, stall_events

ROOT = Path(__file__).resolve().parents[2]
TERRAIN_X = np.arange(0.0, 20.0001, 0.5)
TERRAIN_Z = 0.5 + 0.1 * TERRAIN_X
POS = [0.1, 0.2, 0.3, 0.4]
VEL = [0.01, 0.02, 0.03, 0.04]
TAU = [1000.0, -2000.0, 3000.0, -4000.0]


def build(**over):
    kw = {
        "joint_pos": POS, "joint_vel": VEL, "joint_torque": TAU, "tip_xz": (2.0, -0.3), "lip_pitch": 0.7,
        "terrain_x": TERRAIN_X, "terrain_z": TERRAIN_Z, "v_fill": 0.6, "v_heaped": 1.5,
    }  # fmt: skip
    kw.update(over)
    return il2_observation(**kw)


# ------------------------------------------------------------------------------------------------ FR-014-15
@pytest.mark.req("FR-014-15")
def test_layout_has_46_elements_in_the_order_of_the_contract_example() -> None:
    assert IL2_OBS_SIZE == 46
    assert sum(size for _name, size in IL2_LAYOUT) == 46
    example = json.loads(
        (ROOT / "specs" / "014-robot-learning" / "contracts" / "examples" / "il-task.valid-il2.json").read_text("utf-8")
    )
    assert [(s["segment"], s["size"]) for s in example["observation_layout"]] == list(IL2_LAYOUT)


@pytest.mark.req("FR-014-15")
def test_observation_is_float32_with_46_elements() -> None:
    obs = build()
    assert obs.dtype == np.float32
    assert obs.shape == (46,)


@pytest.mark.req("FR-014-15")
def test_joint_blocks_tip_pose_and_fill_estimate_sit_at_their_indices() -> None:
    obs = build()
    np.testing.assert_allclose(obs[0:4], POS, rtol=0, atol=1e-7)  # positions
    np.testing.assert_allclose(obs[4:8], VEL, rtol=0, atol=1e-7)  # velocities
    np.testing.assert_allclose(obs[8:12], TAU, rtol=1e-6)  # torques
    np.testing.assert_allclose(obs[12:15], [2.0, -0.3, 0.7], rtol=0, atol=1e-7)  # tip x, tip z, lip pitch
    assert obs[45] == pytest.approx(0.6 / 1.5, abs=1e-7)  # fill estimate V_fill / V_h = 0.4


@pytest.mark.req("FR-014-15")
def test_thirty_terrain_heights_ahead_of_the_tip_at_0_1_m_spacing() -> None:
    obs = build()
    # z(x) = 0.5 + 0.1 x is linear, so interpolation is exact: heights at x = 2.1, 2.2, ..., 5.0
    want = 0.5 + 0.1 * (2.0 + 0.1 * (np.arange(30) + 1))
    np.testing.assert_allclose(obs[15:45], want, rtol=0, atol=2e-7)
    # the same call with the tip 1.0 m further shifts every height by 0.1 * 1.0
    moved = build(tip_xz=(3.0, -0.3))
    np.testing.assert_allclose(moved[15:45] - obs[15:45], 0.1, rtol=0, atol=3e-7)


@pytest.mark.req("FR-014-15")
def test_fill_estimate_follows_the_fill_ratio_and_can_exceed_one_up_to_the_cap() -> None:
    assert build(v_fill=0.0)[45] == 0.0
    assert build(v_fill=1.5)[45] == pytest.approx(1.0, abs=1e-7)
    assert build(v_fill=1.725)[45] == pytest.approx(1.15, abs=1e-6)


@pytest.mark.req("FR-014-15")
@pytest.mark.parametrize(
    "over",
    [
        {"joint_pos": [0.1, 0.2, 0.3]},
        {"joint_vel": [0.0] * 5},
        {"joint_torque": [0.0] * 3},
        {"tip_xz": (1.0, 2.0, 3.0)},
        {"terrain_z": TERRAIN_Z[:-1]},
        {"v_heaped": 0.0},
        {"v_heaped": -1.5},
    ],
    ids=["pos3", "vel5", "torque3", "tip3", "terrain-mismatch", "no-volume", "negative-volume"],
)
def test_the_builder_rejects_wrong_shapes_and_a_non_positive_heaped_volume(over) -> None:
    with pytest.raises(ValueError, match=r"joint_pos|joint_vel|joint_torque|tip_xz|terrain|v_heaped"):
        build(**over)


# ------------------------------------------------------------------------------------------------ FR-014-16
@pytest.mark.req("FR-014-16")
def test_action_is_scaled_by_the_joint_maximum_velocity() -> None:
    v_max = np.array([1.0, 0.5, 0.5, 0.8])
    got = il2_action_to_joint_velocity([0.5, -0.5, 1.0, -1.0], v_max)
    np.testing.assert_allclose(got, [0.5, -0.25, 0.5, -0.8], rtol=0, atol=1e-15)  # hand calculation
    assert got.shape == (4,)


@pytest.mark.req("FR-014-16")
def test_action_is_clipped_to_unit_range_before_scaling() -> None:
    v_max = np.array([1.0, 0.5, 0.5, 0.8])
    got = il2_action_to_joint_velocity([2.0, -3.0, 1.5, 0.0], v_max)
    np.testing.assert_allclose(got, [1.0, -0.5, 0.5, 0.0], rtol=0, atol=1e-15)
    big = il2_action_to_joint_velocity([1e30, -1e30, 1.0000001, -1.0000001], v_max)
    np.testing.assert_allclose(big, [1.0, -0.5, 0.5, -0.8], rtol=0, atol=1e-15)


@pytest.mark.req("FR-014-16")
@pytest.mark.parametrize("bad", [[0.1, 0.2, 0.3], [0.0] * 5, [], [[0.1, 0.2], [0.3, 0.4]]])
def test_action_of_the_wrong_shape_raises_value_error_naming_action(bad) -> None:
    with pytest.raises(ValueError, match=r"\baction\b"):
        il2_action_to_joint_velocity(bad, np.ones(4))


@pytest.mark.req("FR-014-16")
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_a_non_finite_action_or_observation_terminates_the_episode_as_invalid_value(bad) -> None:
    obs = build()
    act = np.array([0.1, 0.2, 0.3, 0.4])
    assert step_validity(obs, act) is None
    a2 = act.copy()
    a2[2] = bad
    assert step_validity(obs, a2) == "invalid_value"
    o2 = obs.copy()
    o2[17] = bad
    assert step_validity(o2, act) == "invalid_value"
    assert "invalid_value" in FAILURE_REASONS  # counted as a failure (FR-014-10)


# ------------------------------------------------------------------------------------------------ FR-014-20
def trace(n: int, *, joint: int = 1, frac: float = 1.0, total: int | None = None, start: int = 0) -> np.ndarray:
    tau = np.zeros((total or n + start + 10, 4))
    tau[start : start + n, joint] = frac * 120_000.0
    return tau


TAU_MAX = np.array([120_000.0] * 4)


@pytest.mark.req("FR-014-20")
def test_constants_are_the_decided_thresholds() -> None:
    assert STALL_FRACTION == 0.99
    assert STALL_SECONDS == 1.0


@pytest.mark.req("FR-014-20")
def test_one_second_at_the_limit_is_a_stall_and_099_seconds_is_not() -> None:
    assert is_stalled(trace(100), TAU_MAX, 0.01)  # 100 * 0.01 = 1.00 s
    assert not is_stalled(trace(99), TAU_MAX, 0.01)  # 0.99 s
    events = stall_events(trace(100, start=7), TAU_MAX, 0.01)
    assert [(e.joint, e.start, e.end) for e in events] == [(1, 7, 107)]


@pytest.mark.req("FR-014-20")
def test_the_threshold_is_99_percent_of_the_torque_limit_in_absolute_value() -> None:
    assert is_stalled(trace(120, frac=0.995), TAU_MAX, 0.01)
    assert not is_stalled(trace(120, frac=0.985), TAU_MAX, 0.01)
    assert is_stalled(-trace(120, frac=1.0), TAU_MAX, 0.01)  # negative torque at the limit counts
    assert is_stalled(trace(120, frac=1.3), TAU_MAX, 0.01)  # above the limit counts as holding it


@pytest.mark.req("FR-014-20")
def test_a_single_sample_below_the_threshold_splits_a_run() -> None:
    tau = trace(200)
    tau[100, 1] = 0.0  # 100 samples, one gap, 99 samples
    assert [(e.start, e.end) for e in stall_events(tau, TAU_MAX, 0.01)] == [(0, 100)]
    tau[0, 1] = 0.0  # now 99 + gap + 99: no event
    assert not is_stalled(tau, TAU_MAX, 0.01)


@pytest.mark.req("FR-014-20")
def test_runs_of_different_joints_are_not_combined() -> None:
    tau = np.zeros((200, 4))
    tau[0:60, 0] = 120_000.0
    tau[60:120, 1] = 120_000.0  # 60 + 60 samples back to back, but on two joints
    assert not is_stalled(tau, TAU_MAX, 0.01)
    tau[120:200, 1] = 120_000.0  # joint 1 now holds from 60 to 200: 140 samples
    assert [(e.joint, e.start, e.end) for e in stall_events(tau, TAU_MAX, 0.01)] == [(1, 60, 200)]


@pytest.mark.req("FR-014-20")
def test_per_joint_limits_and_two_events_on_one_joint() -> None:
    tau_max = np.array([100.0, 200.0, 300.0, 400.0])
    tau = np.zeros((500, 4))
    tau[0:110, 2] = 300.0
    tau[200:350, 2] = 299.0  # 299 / 300 = 0.9967 >= 0.99
    tau[0:200, 3] = 300.0  # 300 / 400 = 0.75: never at the limit
    events = stall_events(tau, tau_max, 0.01)
    assert [(e.joint, e.start, e.end) for e in events] == [(2, 0, 110), (2, 200, 350)]


@pytest.mark.req("FR-014-20")
@pytest.mark.parametrize(
    ("dt", "n", "stalled"), [(0.05, 20, True), (0.05, 19, False), (0.1, 10, True), (0.02, 49, False)]
)
def test_the_duration_is_the_run_length_times_the_step(dt, n, stalled) -> None:
    assert is_stalled(trace(n), TAU_MAX, dt) is stalled


@pytest.mark.req("FR-014-20")
@pytest.mark.parametrize(
    ("torque", "tau_max", "dt", "name"),
    [
        (np.zeros((10,)), TAU_MAX, 0.01, "torque"),
        (np.zeros((10, 3)), TAU_MAX, 0.01, "torque"),
        (np.zeros((10, 4)), np.array([1.0, 1.0, 0.0, 1.0]), 0.01, "tau_max"),
        (np.zeros((10, 4)), np.array([1.0, 1.0, -1.0, 1.0]), 0.01, "tau_max"),
        (np.zeros((10, 4)), TAU_MAX, 0.0, "dt"),
        (np.zeros((10, 4)), TAU_MAX, -0.01, "dt"),
        (np.zeros((10, 4)), TAU_MAX, float("nan"), "dt"),
        (np.full((10, 4), np.nan), TAU_MAX, 0.01, "torque"),
    ],
    ids=["1d", "wrong-joints", "zero-limit", "negative-limit", "zero-dt", "negative-dt", "nan-dt", "nan-torque"],
)
def test_hostile_stall_inputs_raise_value_error_naming_the_input(torque, tau_max, dt, name) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        stall_events(torque, tau_max, dt)


@pytest.mark.req("FR-014-20")
def test_an_empty_trace_has_no_stall() -> None:
    assert stall_events(np.zeros((0, 4)), TAU_MAX, 0.01) == []

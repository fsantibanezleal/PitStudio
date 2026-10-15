# ruff: noqa: E501
"""T-014-031: IL-1 action mapping, clipping and non-finite termination.

Requirements: FR-014-09, FR-014-10.

Spec: specs/014-robot-learning/spec.md FR-014-09: "The IL-1 action shall be two values in [-1, 1], clipped: steering rate as a
fraction of the maximum steering rate, and a combined command whose positive part is the fraction of maximum rimpull and
whose negative part is the fraction of maximum retarder force; the policy acts at 20 Hz." FR-014-10: "If an observation or
action contains a NaN or infinite value, then the environment shall terminate that episode with reason `invalid_value` and
count it as a failure."

Oracle: hand calculation of the mapping with the limits of the valid contract example
`specs/014-robot-learning/contracts/examples/machine-params.valid.json` (max steering rate 20 deg/s = 0.34906585 rad/s, max
rimpull 900,000 N, max retarder force 1,100,000 N): action (0.5, 0.8) -> steering rate 0.5 * 0.34906585 = 0.17453293 rad/s and
rimpull 0.8 * 900,000 = 720,000 N; action (-1.5, -0.5) -> clipped to (-1, -0.5): steering rate -0.34906585 rad/s, retarder
0.5 * 1,100,000 = 550,000 N; the property relations of the mapping (range, exclusivity of rimpull and retarder, recovery of the
combined command).

Expected API of the implementation (module `pitstudio.robots.actions`, see T-014-024 for step_validity and FAILURE_REASONS):
    CONTROL_HZ = 20 ; CONTROL_DT = 0.05
    Il1Limits: frozen dataclass (max_steer_rate [rad/s], max_rimpull [N], max_retarder [N])
    il1_limits(params) -> Il1Limits
        from a machine-params document of kind "haul-truck" (max_steer_rate_deg_per_s converted to rad/s, max_rimpull_n,
        max_retarder_n); ValueError naming the JSON pointer of a missing or invalid member
    Il1Command: frozen dataclass (steer_rate [rad/s], rimpull [N], retarder [N])
    il1_action_to_commands(action, limits) -> Il1Command
        action is two finite values; each is clipped to [-1, 1] first; steer_rate = a0 * max_steer_rate; rimpull =
        max(a1, 0) * max_rimpull; retarder = max(-a1, 0) * max_retarder. ValueError naming `action` for a wrong shape.
    step_validity(obs, action) -> "invalid_value" | None   (63-element observations and 2-element actions as well)
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.robots.actions import (
    CONTROL_DT,
    CONTROL_HZ,
    FAILURE_REASONS,
    Il1Limits,
    il1_action_to_commands,
    il1_limits,
    step_validity,
)

ROOT = Path(__file__).resolve().parents[2]
TRUCK = json.loads(
    (ROOT / "specs" / "014-robot-learning" / "contracts" / "examples" / "machine-params.valid.json").read_text("utf-8")
)
LIMITS = Il1Limits(max_steer_rate=math.radians(20.0), max_rimpull=900_000.0, max_retarder=1_100_000.0)


@pytest.mark.req("FR-014-09")
def test_the_policy_acts_at_20_hz() -> None:
    assert CONTROL_HZ == 20
    assert abs(CONTROL_DT - 0.05) < 1e-15


@pytest.mark.req("FR-014-09")
def test_limits_are_read_from_the_truck_parameter_file() -> None:
    lim = il1_limits(TRUCK)
    assert lim.max_steer_rate == pytest.approx(0.3490658503988659, rel=1e-12)  # 20 deg/s in rad/s
    assert lim.max_rimpull == 900_000.0
    assert lim.max_retarder == 1_100_000.0


@pytest.mark.req("FR-014-09")
@pytest.mark.parametrize(
    ("pointer", "mutate"),
    [
        ("/max_rimpull_n", lambda d: d.update(max_rimpull_n=0.0)),
        ("/max_retarder_n", lambda d: d.update(max_retarder_n=-1.0)),
        ("/max_steer_rate_deg_per_s", lambda d: d.update(max_steer_rate_deg_per_s=float("nan"))),
        ("/max_rimpull_n", lambda d: d.pop("max_rimpull_n")),
        ("/kind", lambda d: d.update(kind="excavator")),
    ],
)
def test_invalid_truck_limits_raise_value_error_naming_the_pointer(pointer, mutate) -> None:
    doc = json.loads(json.dumps(TRUCK))
    mutate(doc)
    with pytest.raises(ValueError, match=pointer):
        il1_limits(doc)


@pytest.mark.req("FR-014-09")
def test_a_positive_combined_command_is_a_fraction_of_the_maximum_rimpull() -> None:
    c = il1_action_to_commands([0.5, 0.8], LIMITS)
    assert c.steer_rate == pytest.approx(0.17453292519943295, rel=1e-12)  # 0.5 * 20 deg/s
    assert c.rimpull == pytest.approx(720_000.0, rel=1e-12)  # 0.8 * 900,000 N
    assert c.retarder == 0.0


@pytest.mark.req("FR-014-09")
def test_a_negative_combined_command_is_a_fraction_of_the_maximum_retarder_force() -> None:
    c = il1_action_to_commands([-1.5, -0.5], LIMITS)  # clipped to (-1, -0.5)
    assert c.steer_rate == pytest.approx(-0.3490658503988659, rel=1e-12)
    assert c.rimpull == 0.0
    assert c.retarder == pytest.approx(550_000.0, rel=1e-12)  # 0.5 * 1,100,000 N


@pytest.mark.req("FR-014-09")
def test_values_beyond_the_unit_range_are_clipped() -> None:
    c = il1_action_to_commands([7.0, 3.0], LIMITS)
    assert c.steer_rate == pytest.approx(LIMITS.max_steer_rate, rel=1e-15)
    assert c.rimpull == pytest.approx(LIMITS.max_rimpull, rel=1e-15)
    c = il1_action_to_commands([-1e30, -1e30], LIMITS)
    assert c.steer_rate == pytest.approx(-LIMITS.max_steer_rate, rel=1e-15)
    assert c.retarder == pytest.approx(LIMITS.max_retarder, rel=1e-15)


@pytest.mark.req("FR-014-09")
def test_zero_action_commands_nothing() -> None:
    c = il1_action_to_commands([0.0, 0.0], LIMITS)
    assert (c.steer_rate, c.rimpull, c.retarder) == (0.0, 0.0, 0.0)


@pytest.mark.req("FR-014-09")
@pytest.mark.parametrize("bad", [[0.1], [0.1, 0.2, 0.3], [], [[0.1, 0.2]], 0.5])
def test_an_action_of_the_wrong_shape_raises_value_error_naming_action(bad) -> None:
    with pytest.raises(ValueError, match=r"\baction\b"):
        il1_action_to_commands(bad, LIMITS)


@pytest.mark.req("FR-014-09")
@given(st.floats(-1e6, 1e6), st.floats(-1e6, 1e6))
@settings(max_examples=300, deadline=None)
def test_property_commands_stay_within_the_limits_and_recover_the_clipped_action(a0, a1) -> None:
    c = il1_action_to_commands([a0, a1], LIMITS)
    u0, u1 = min(max(a0, -1.0), 1.0), min(max(a1, -1.0), 1.0)
    assert abs(c.steer_rate) <= LIMITS.max_steer_rate * (1.0 + 1e-15)
    assert 0.0 <= c.rimpull <= LIMITS.max_rimpull
    assert 0.0 <= c.retarder <= LIMITS.max_retarder
    assert c.rimpull == 0.0 or c.retarder == 0.0  # never driving and retarding at once
    assert c.steer_rate / LIMITS.max_steer_rate == pytest.approx(u0, rel=1e-12, abs=1e-15)
    assert c.rimpull / LIMITS.max_rimpull - c.retarder / LIMITS.max_retarder == pytest.approx(u1, rel=1e-12, abs=1e-15)


@pytest.mark.req("FR-014-09")
@given(st.floats(-1.0, 1.0), st.floats(-1.0, 1.0), st.floats(-1.0, 1.0))
@settings(max_examples=200, deadline=None)
def test_property_the_mapping_is_monotone_in_the_combined_command(a0, lo, hi) -> None:
    lo, hi = min(lo, hi), max(lo, hi)
    c_lo = il1_action_to_commands([a0, lo], LIMITS)
    c_hi = il1_action_to_commands([a0, hi], LIMITS)
    assert c_hi.rimpull >= c_lo.rimpull
    assert c_hi.retarder <= c_lo.retarder


# ------------------------------------------------------------------------------------------------ FR-014-10
@pytest.mark.req("FR-014-10")
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("index", [0, 1])
def test_a_non_finite_action_value_terminates_the_episode_as_invalid_value(bad, index) -> None:
    obs = np.zeros(63, dtype=np.float32)
    action = np.array([0.1, -0.2])
    assert step_validity(obs, action) is None
    action[index] = bad
    assert step_validity(obs, action) == "invalid_value"


@pytest.mark.req("FR-014-10")
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("index", [0, 3, 25, 40, 62])
def test_a_non_finite_observation_value_terminates_the_episode_as_invalid_value(bad, index) -> None:
    obs = np.zeros(63, dtype=np.float32)
    obs[index] = bad
    assert step_validity(obs, np.array([0.0, 0.0])) == "invalid_value"


@pytest.mark.req("FR-014-10")
def test_invalid_value_counts_as_a_failure_and_success_is_not_a_failure() -> None:
    assert "invalid_value" in FAILURE_REASONS
    assert "success" not in FAILURE_REASONS


@pytest.mark.req("FR-014-10")
@given(
    st.lists(st.floats(-1e6, 1e6), min_size=63, max_size=63),
    st.lists(st.floats(-1e6, 1e6), min_size=2, max_size=2),
)
@settings(max_examples=100, deadline=None)
def test_property_finite_steps_are_valid(obs, act) -> None:
    assert step_validity(np.asarray(obs, dtype=np.float32), np.asarray(act)) is None

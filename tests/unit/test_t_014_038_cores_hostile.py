# ruff: noqa: E501
"""T-014-038: hostile inputs of the TTC function, the twin steps and the fill model.

Requirements: FR-014-47.

Spec: specs/014-robot-learning/spec.md FR-014-47: "If the TTC function, a twin step or the fill model receives a non-finite position,
velocity, action or state, a footprint with a non-positive side, a time step <= 0, or a bucket width <= 0, then it shall raise `ValueError`
naming the input."

Oracle: the requirement's own input classes, enumerated by hand (NaN, +inf, -inf in every numeric slot; zero and negative footprint sides, time
steps and widths); each call is made on an otherwise valid baseline whose result is finite, so that the only reason to raise is the injected value.
The error message must contain the name of the offending argument or field.

Expected API of the implementation (existing modules, see T-014-035, T-014-050, T-014-051, T-014-023):
    pitstudio.robots.ttc.Agent(x, y, yaw, vx, vy, length, width), footprint_gap(a, b), time_to_collision(a, b)
        ValueError naming the field (`x`, `y`, `yaw`, `vx`, `vy`, `length` or `width`) raised at construction of the Agent or in the call
    pitstudio.robots.twins.bicycle_step(state, steer_rate_cmd, drive_cmd, params, env=None, dt=None)
        ValueError naming `state` (wrong shape or a non-finite entry), `steer_rate_cmd`, `drive_cmd` or `dt` (non-finite or <= 0)
    pitstudio.robots.twins.arm_step(q, v_fill, heights, action, params, soil, *, terrain_dx=0.1, terrain_x0=0.0, dt=None)
        ValueError naming `q`, `v_fill`, `heights`, `action` (wrong shape or non-finite), `terrain_dx` (<= 0 or non-finite) or `dt` (<= 0 or non-finite)
    pitstudio.robots.fill.cut_step(v_fill, heights, *, dx, tip_x, depth, ds, width, v_heaped, cutting=True)
        ValueError naming `v_fill`, `heights`, `dx`, `tip_x`, `depth`, `ds`, `width` (<= 0 or non-finite) or `v_heaped` (<= 0 or non-finite)
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from pitstudio.robots.fill import cut_step
from pitstudio.robots.ttc import Agent, footprint_gap, time_to_collision
from pitstudio.robots.twins import ArmParams, ArmSoil, BicycleEnv, BicycleParams, arm_step, bicycle_step

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "014-robot-learning" / "contracts" / "examples"
BP = BicycleParams.from_twin(json.loads((EX / "il-twin.valid.json").read_text("utf-8"))["parameters"])
AP = ArmParams.from_twin(json.loads((EX / "il-twin.valid-il2.json").read_text("utf-8"))["parameters"])
SOIL = ArmSoil(rho=1800.0, c=0.0, c_a=0.0, phi=math.radians(35.0), delta=math.radians(20.0))
BAD = [math.nan, math.inf, -math.inf]


# ------------------------------------------------------------------------------------------------------ TTC
def agents(**over):
    a = {"x": 0.0, "y": 0.0, "yaw": 0.0, "vx": 5.0, "vy": 0.0, "length": 10.0, "width": 4.0}
    b = {"x": 40.0, "y": 0.0, "yaw": math.pi, "vx": -2.0, "vy": 0.0, "length": 4.0, "width": 2.0}
    which, field = over.pop("which", None), over.pop("field", None)
    if which:
        (a if which == "a" else b)[field] = over["value"]
    return Agent(**a), Agent(**b)


def call_ttc(**kw):
    a, b = agents(**kw)
    return time_to_collision(a, b)


def call_gap(**kw):
    a, b = agents(**kw)
    return footprint_gap(a, b)


@pytest.mark.req("FR-014-47")
def test_the_ttc_baseline_is_valid() -> None:
    a, b = agents()
    assert time_to_collision(a, b) == pytest.approx(33.0 / 7.0, rel=1e-12)
    assert footprint_gap(a, b) == pytest.approx(33.0, rel=1e-12)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("which", ["a", "b"])
@pytest.mark.parametrize("field", ["x", "y", "yaw", "vx", "vy"])
@pytest.mark.parametrize("bad", BAD, ids=["nan", "inf", "-inf"])
def test_a_non_finite_position_heading_or_velocity_raises_value_error_naming_the_field(which, field, bad) -> None:
    with pytest.raises(ValueError, match=rf"\b{field}\b"):
        call_ttc(which=which, field=field, value=bad)
    with pytest.raises(ValueError, match=rf"\b{field}\b"):
        call_gap(which=which, field=field, value=bad)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("which", ["a", "b"])
@pytest.mark.parametrize("field", ["length", "width"])
@pytest.mark.parametrize("bad", [0.0, -1.0, -1e-9, math.nan, math.inf])
def test_a_footprint_with_a_non_positive_or_non_finite_side_raises_value_error_naming_it(which, field, bad) -> None:
    with pytest.raises(ValueError, match=rf"\b{field}\b"):
        call_ttc(which=which, field=field, value=bad)
    with pytest.raises(ValueError, match=rf"\b{field}\b"):
        call_gap(which=which, field=field, value=bad)


# ------------------------------------------------------------------------------------------- bicycle twin
STATE = np.array([0.0, 0.0, 0.0, 8.0, 0.0, 0.0, 0.0])
ENV = BicycleEnv(0.0, 0.0, 0.03)


@pytest.mark.req("FR-014-47")
def test_the_bicycle_baseline_is_valid() -> None:
    out = bicycle_step(STATE, 0.0, 0.2, BP, ENV)
    assert np.all(np.isfinite(out.state))


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("index", range(7))
@pytest.mark.parametrize("bad", BAD, ids=["nan", "inf", "-inf"])
def test_a_non_finite_bicycle_state_entry_raises_value_error_naming_state(index, bad) -> None:
    state = STATE.copy()
    state[index] = bad
    with pytest.raises(ValueError, match=r"\bstate\b"):
        bicycle_step(state, 0.0, 0.2, BP, ENV)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("shape_state", [np.zeros(6), np.zeros(8), np.zeros((7, 1)), np.zeros(0)])
def test_a_bicycle_state_of_the_wrong_shape_raises_value_error_naming_state(shape_state) -> None:
    with pytest.raises(ValueError, match=r"\bstate\b"):
        bicycle_step(shape_state, 0.0, 0.2, BP, ENV)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("name", ["steer_rate_cmd", "drive_cmd"])
@pytest.mark.parametrize("bad", BAD, ids=["nan", "inf", "-inf"])
def test_a_non_finite_bicycle_action_raises_value_error_naming_it(name, bad) -> None:
    kw = {"steer_rate_cmd": 0.0, "drive_cmd": 0.2, name: bad}
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        bicycle_step(STATE, kw["steer_rate_cmd"], kw["drive_cmd"], BP, ENV)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("bad", [0.0, -0.01, -1e-12, math.nan, math.inf])
def test_a_non_positive_or_non_finite_bicycle_time_step_raises_value_error_naming_dt(bad) -> None:
    with pytest.raises(ValueError, match=r"\bdt\b"):
        bicycle_step(STATE, 0.0, 0.2, BP, ENV, dt=bad)


# ----------------------------------------------------------------------------------------------- arm twin
Q = np.array([0.0, -math.pi / 2, 0.0])
H = np.full(120, -2.0)
ACT = [0.0, 0.0, 1.0, 0.0]


@pytest.mark.req("FR-014-47")
def test_the_arm_baseline_is_valid() -> None:
    out = arm_step(Q, 0.0, H, ACT, AP, SOIL)
    assert np.all(np.isfinite(out.q))
    assert math.isfinite(out.v_fill)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("bad", BAD, ids=["nan", "inf", "-inf"])
def test_a_non_finite_joint_angle_raises_value_error_naming_q(index, bad) -> None:
    q = Q.copy()
    q[index] = bad
    with pytest.raises(ValueError, match=r"\bq\b"):
        arm_step(q, 0.0, H, ACT, AP, SOIL)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("bad_q", [np.zeros(2), np.zeros(4), np.zeros((3, 1))])
def test_joint_angles_of_the_wrong_shape_raise_value_error_naming_q(bad_q) -> None:
    with pytest.raises(ValueError, match=r"\bq\b"):
        arm_step(bad_q, 0.0, H, ACT, AP, SOIL)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -0.1])
def test_arm_a_non_finite_or_negative_fill_volume_raises_value_error_naming_v_fill(bad) -> None:
    with pytest.raises(ValueError, match=r"\bv_fill\b"):
        arm_step(Q, bad, H, ACT, AP, SOIL)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("index", [0, 5, 119])
@pytest.mark.parametrize("bad", BAD, ids=["nan", "inf", "-inf"])
def test_a_non_finite_terrain_height_raises_value_error_naming_heights(index, bad) -> None:
    h = H.copy()
    h[index] = bad
    with pytest.raises(ValueError, match=r"\bheights\b"):
        arm_step(Q, 0.0, h, ACT, AP, SOIL)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("bad_h", [np.zeros(0), np.zeros(1), np.zeros((4, 4))])
def test_a_terrain_profile_that_is_empty_single_or_two_dimensional_raises_value_error_naming_heights(bad_h) -> None:
    with pytest.raises(ValueError, match=r"\bheights\b"):
        arm_step(Q, 0.0, bad_h, ACT, AP, SOIL)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("bad", BAD, ids=["nan", "inf", "-inf"])
def test_a_non_finite_arm_action_raises_value_error_naming_action(index, bad) -> None:
    act = list(ACT)
    act[index] = bad
    with pytest.raises(ValueError, match=r"\baction\b"):
        arm_step(Q, 0.0, H, act, AP, SOIL)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("bad_a", [[0.0, 0.0, 1.0], [0.0] * 5, []])
def test_an_arm_action_of_the_wrong_shape_raises_value_error_naming_action(bad_a) -> None:
    with pytest.raises(ValueError, match=r"\baction\b"):
        arm_step(Q, 0.0, H, bad_a, AP, SOIL)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("bad", [0.0, -0.01, math.nan, math.inf])
def test_a_non_positive_or_non_finite_arm_time_step_or_grid_spacing_raises_value_error_naming_it(bad) -> None:
    with pytest.raises(ValueError, match=r"\bdt\b"):
        arm_step(Q, 0.0, H, ACT, AP, SOIL, dt=bad)
    with pytest.raises(ValueError, match=r"\bterrain_dx\b"):
        arm_step(Q, 0.0, H, ACT, AP, SOIL, terrain_dx=bad)


# --------------------------------------------------------------------------------------------- fill model
def cut(**over):
    kw = {"dx": 0.1, "tip_x": 2.0, "depth": 0.3, "ds": 0.1, "width": 1.2, "v_heaped": 1.5}
    v = over.pop("v_fill", 0.2)
    h = over.pop("heights", np.full(60, 5.0))
    kw.update(over)
    return cut_step(v, h, **kw)


@pytest.mark.req("FR-014-47")
def test_the_fill_baseline_is_valid() -> None:
    out = cut()
    assert out.v_fill == pytest.approx(0.2 + 1.2 * 0.3 * 0.1, rel=1e-12)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("bad", [0.0, -1.2, -1e-9, math.nan, math.inf, -math.inf])
def test_a_bucket_width_that_is_not_positive_and_finite_raises_value_error_naming_width(bad) -> None:
    with pytest.raises(ValueError, match=r"\bwidth\b"):
        cut(width=bad)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("name", ["tip_x", "depth", "ds"])
@pytest.mark.parametrize("bad", BAD, ids=["nan", "inf", "-inf"])
def test_a_non_finite_tip_state_raises_value_error_naming_it(name, bad) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        cut(**{name: bad})


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("bad", [-0.1, math.nan, math.inf])
def test_a_negative_depth_or_path_length_is_rejected_where_the_model_needs_them_non_negative(bad) -> None:
    with pytest.raises(ValueError, match=r"\bds\b"):
        cut(ds=bad)
    if bad < 0:
        with pytest.raises(ValueError, match=r"\bdepth\b"):
            cut(depth=bad)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("name", ["dx", "v_heaped"])
@pytest.mark.parametrize("bad", [0.0, -0.1, math.nan, math.inf])
def test_a_non_positive_grid_spacing_or_heaped_volume_raises_value_error_naming_it(name, bad) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        cut(**{name: bad})


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -0.5])
def test_a_non_finite_or_negative_fill_volume_raises_value_error_naming_v_fill(bad) -> None:
    with pytest.raises(ValueError, match=r"\bv_fill\b"):
        cut(v_fill=bad)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("index", [0, 20, 59])
@pytest.mark.parametrize("bad", BAD, ids=["nan", "inf", "-inf"])
def test_a_non_finite_terrain_profile_entry_raises_value_error_naming_heights(index, bad) -> None:
    h = np.full(60, 5.0)
    h[index] = bad
    with pytest.raises(ValueError, match=r"\bheights\b"):
        cut(heights=h)


@pytest.mark.req("FR-014-47")
@pytest.mark.parametrize("bad_h", [np.zeros(0), np.zeros((3, 3))])
def test_a_terrain_profile_of_the_wrong_shape_raises_value_error_naming_heights(bad_h) -> None:
    with pytest.raises(ValueError, match=r"\bheights\b"):
        cut(heights=bad_h)


@pytest.mark.req("FR-014-47")
def test_hostile_values_are_rejected_even_when_the_step_is_not_cutting() -> None:
    with pytest.raises(ValueError, match=r"\bwidth\b"):
        cut(width=-1.0, cutting=False)

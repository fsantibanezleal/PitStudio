# ruff: noqa: E501
"""T-015-093: a frame-state object rotation quaternion must have unit norm (within 1e-6) and finite components.

Requirements: FR-015-49.

Spec: specs/015-vlm/spec.md FR-015-49 ("If a frame-state rotation quaternion has a norm differing from 1 by more than 1e-6,
or a non-finite component, then the frame-state loader shall reject it with error class frame-state-invalid naming the
object"); plan.md test strategy row FR-015-49 ("(0, 0, 0, 1) is accepted; (0, 0, 0, 2) and (NaN, 0, 0, 1) are rejected").

Oracle: the Euclidean norm written out by hand for each fixture (for example |(0.5, 0.5, 0.5, 0.5)| = sqrt(4 * 0.25) = 1;
|(0, 0, 0, 1 - 2e-6)| = 1 - 2e-6, which differs from 1 by 2e-6 > 1e-6). Components of the schema lie in [-1, 1], so the
spec's (0, 0, 0, 2) is rejected by the schema already; the cases inside [-1, 1] exercise the loader's own norm check. The
camera pose quaternion is not covered: the requirement says "naming the object" and a camera has no prim id (reported as
an ambiguity).

Expected API of the implementation: `pitstudio.reason.frames.load_frame_state(source, *, root)` and `FrameStateInvalid`
(`error_class == "frame-state-invalid"`, message contains the `prim_id`), as in test_t_015_033_frame_state_hostile.py.
"""

from __future__ import annotations

import math
from pathlib import Path

import _p015_kit as kit
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pitstudio.reason.frames import FrameStateInvalid, load_frame_state

PRIM = "/World/Quat_Truck"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    kit.write_frame_files(tmp_path)
    return tmp_path


def _frame(q: list[float], *, up: str = "Z") -> dict:
    t = kit.truck(50.0, 0.0, prim_id=PRIM, up=up)
    t["pose"]["rotation_xyzw"] = q
    return kit.frame_state([t, kit.person(60.0, 3.0, up=up)], up_axis=up)


@pytest.mark.req("FR-015-49")
@pytest.mark.parametrize(
    "q",
    [
        [0.0, 0.0, 0.0, 1.0],
        [0.5, 0.5, 0.5, 0.5],  # |q|^2 = 4 * 0.25 = 1
        [0.0, 0.0, 0.3826834, 0.9238795],  # 45 degrees about z: sin(22.5), cos(22.5), norm 1 to 1e-8
        [0.0, 0.0, 0.0, 1.0 - 5e-7],  # norm differs from 1 by 5e-7 < 1e-6
        [0.0, 0.0, 0.0, -1.0],
    ],
)
def test_unit_norm_quaternions_within_tolerance_are_accepted(root: Path, q: list[float]) -> None:
    doc = _frame(q)
    assert load_frame_state(doc, root=root) == doc


@pytest.mark.req("FR-015-49")
@pytest.mark.parametrize(
    "q",
    [
        [0.0, 0.0, 0.0, 2.0],  # the spec's example (also outside the schema range)
        [0.0, 0.0, 0.0, 1.0 - 2e-6],  # norm differs by 2e-6 > 1e-6
        [0.0, 0.0, 0.0, 0.0],  # zero quaternion, norm 0
        [0.5, 0.5, 0.5, 0.0],  # norm sqrt(0.75) = 0.866
        [1.0, 1.0, 0.0, 0.0],  # norm sqrt(2), components inside the schema range
        [0.0, 0.0, 0.0, 0.999998],
        [float("nan"), 0.0, 0.0, 1.0],
        [0.0, float("inf"), 0.0, 1.0],
        [0.0, 0.0, -float("inf"), 1.0],
        [0.0, 0.0, 0.0, float("nan")],
    ],
)
def test_non_unit_and_non_finite_quaternions_are_rejected_naming_the_object(root: Path, q: list[float]) -> None:
    with pytest.raises(FrameStateInvalid) as exc:
        load_frame_state(_frame(q), root=root)
    assert exc.value.error_class == "frame-state-invalid"
    assert PRIM in str(exc.value)


@pytest.mark.req("FR-015-49")
def test_the_rule_holds_on_a_y_up_stage(root: Path) -> None:
    with pytest.raises(FrameStateInvalid, match=PRIM):
        load_frame_state(_frame([0.0, 0.0, 0.0, 1.0 - 2e-6], up="Y"), root=root)


@pytest.mark.req("FR-015-49")
def test_only_the_offending_object_is_named(root: Path) -> None:
    doc = _frame([0.0, 0.0, 0.0, 2.0])
    with pytest.raises(FrameStateInvalid) as exc:
        load_frame_state(doc, root=root)
    assert doc["objects"][1]["prim_id"] not in str(exc.value)


@pytest.mark.req("FR-015-49")
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    v=st.tuples(*[st.floats(-1, 1, allow_nan=False)] * 4).filter(lambda t: sum(c * c for c in t) > 1e-9),
    scale=st.sampled_from([1.0, 1.0 + 5e-7, 1.0 - 5e-7, 1.0 + 3e-6, 1.0 - 3e-6, 0.5, 0.9]),
)
def test_property_accepted_if_and_only_if_the_norm_is_within_1e_6_of_one(root: Path, v: tuple, scale: float) -> None:
    n = math.sqrt(sum(c * c for c in v))
    q = [c / n * scale for c in v]
    if any(abs(c) > 1 for c in q):  # outside the schema range: skip (already a schema error)
        return
    norm = math.sqrt(sum(c * c for c in q))
    if abs(abs(norm - 1.0) - 1e-6) < 1e-8:  # stay away from the exact boundary (rounding of the sum of squares)
        return
    doc = _frame(q)
    if abs(norm - 1.0) <= 1e-6:
        assert load_frame_state(doc, root=root) == doc
    else:
        with pytest.raises(FrameStateInvalid, match=PRIM):
            load_frame_state(doc, root=root)

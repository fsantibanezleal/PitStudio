# ruff: noqa: E501
"""T-015-092: a frame-state object whose `visible_px` exceeds the frame area is rejected, naming the object.

Requirements: FR-015-48.

Spec: specs/015-vlm/spec.md FR-015-48 ("If a frame-state record has visible_px greater than width_px x height_px of its
frame, then the frame-state loader shall reject it with error class frame-state-invalid naming the object"); plan.md test
strategy row FR-015-48 ("hand calculation: 640 x 480 = 307,200; visible_px 307,201 is rejected and 307,200 is accepted").

Oracle: the product written out by hand (640 x 480 = 307,200; 1280 x 720 = 921,600; 16 x 16 = 256); for the property, the
integer product `w * h` computed in the test. The schema alone cannot express this cross-field rule (spec 015 section 8,
"no requirement checks visible pixels <= image area"), so only the loader can reject it.

Expected API of the implementation: as in tests/unit/test_t_015_033_frame_state_hostile.py,
`pitstudio.reason.frames.load_frame_state(source, *, root)` and `FrameStateInvalid` (`error_class == "frame-state-invalid"`,
the message contains the `prim_id` of the offending object).
"""

from __future__ import annotations

from pathlib import Path

import _p015_kit as kit
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pitstudio.reason.frames import FrameStateInvalid, load_frame_state


@pytest.fixture
def root(tmp_path: Path) -> Path:
    kit.write_frame_files(tmp_path)
    return tmp_path


def _frame(width: int, height: int, visible_px: int, *, up: str = "Z") -> dict:
    return kit.frame_state(
        [kit.truck(50.0, 0.0, visible_px=visible_px, prim_id="/World/Big_Truck", up=up), kit.person(60.0, 3.0, up=up)],
        width=width,
        height=height,
        up_axis=up,
    )


@pytest.mark.req("FR-015-48")
def test_visible_px_equal_to_the_frame_area_is_accepted(root: Path) -> None:
    doc = _frame(640, 480, 640 * 480)
    assert 640 * 480 == 307_200  # hand calculation
    assert load_frame_state(doc, root=root) == doc


@pytest.mark.req("FR-015-48")
def test_visible_px_one_above_the_frame_area_is_rejected_naming_the_object(root: Path) -> None:
    with pytest.raises(FrameStateInvalid) as exc:
        load_frame_state(_frame(640, 480, 307_201), root=root)
    assert exc.value.error_class == "frame-state-invalid"
    assert "/World/Big_Truck" in str(exc.value)


@pytest.mark.req("FR-015-48")
@pytest.mark.parametrize(("w", "h", "area"), [(1280, 720, 921_600), (16, 16, 256), (8192, 8192, 67_108_864)])
def test_the_limit_is_the_product_of_the_declared_width_and_height(root: Path, w: int, h: int, area: int) -> None:
    assert w * h == area
    assert load_frame_state(_frame(w, h, area), root=root)["objects"][0]["visible_px"] == area
    if area + 1 <= 67_108_864:  # schema maximum of visible_px: a larger count is already a schema error
        with pytest.raises(FrameStateInvalid, match="/World/Big_Truck"):
            load_frame_state(_frame(w, h, area + 1), root=root)


@pytest.mark.req("FR-015-48")
def test_an_object_that_fits_is_not_blamed_for_another_that_does_not(root: Path) -> None:
    doc = _frame(640, 480, 307_201)
    with pytest.raises(FrameStateInvalid) as exc:
        load_frame_state(doc, root=root)
    assert doc["objects"][1]["prim_id"] not in str(exc.value)


@pytest.mark.req("FR-015-48")
def test_the_rule_holds_for_a_y_up_stage(root: Path) -> None:
    with pytest.raises(FrameStateInvalid, match="/World/Big_Truck"):
        load_frame_state(_frame(640, 480, 307_201, up="Y"), root=root)


@pytest.mark.req("FR-015-48")
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(w=st.integers(16, 4096), h=st.integers(16, 4096), delta=st.integers(-3, 3), frac=st.floats(0, 1))
def test_property_accepted_if_and_only_if_visible_px_does_not_exceed_the_area(
    root: Path, w: int, h: int, delta: int, frac: float
) -> None:
    area = w * h
    v = max(0, min(67_108_864, area + delta if frac < 0.5 else int(area * frac)))
    doc = _frame(w, h, v)
    if v <= area:
        assert load_frame_state(doc, root=root) == doc
    else:
        with pytest.raises(FrameStateInvalid, match="/World/Big_Truck"):
            load_frame_state(doc, root=root)

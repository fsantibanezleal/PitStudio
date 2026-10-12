# ruff: noqa: E501
"""T-014-023: fill model (gain, cap, terrain conservation).

Requirements: FR-014-18, P-014-13.

Spec: specs/014-robot-learning/spec.md FR-014-18: "While cutting (FR-014-17 active), the fill model shall add
w d |delta s_tip| per step to V_fill, capped at 1.15 V_h, and lower the terrain profile by the removed cross-section; the
fill factor is k_f = V_fill / V_h." P-014-13: (MR1) V_fill is non-decreasing while cutting and never exceeds 1.15 V_h;
(MR2) below the cap, the volume removed from the terrain profile times w equals the increase of V_fill; (MR3) doubling w
doubles the fill gain. Tolerance rtol 1e-9.

Oracle: the swept area of a straight tip path, computed by hand (w d L for a tip that moves a distance L at constant depth
d); the conservation identity of MR2 evaluated on the returned terrain arrays with plain NumPy sums; the cap 1.15 V_h.
Hand example: w = 1.2 m, d = 0.2 m, L = 3.0 m gives 0.72 m3, so k_f = 0.72 / 1.5 = 0.48 for V_h = 1.5 m3; a 10 m cut
would give 2.4 m3 > 1.15 * 1.5 = 1.725 m3, so V_fill = 1.725 m3 and k_f = 1.15.

Expected API of the implementation (module `pitstudio.robots.fill`, NumPy float64, SI units):
    FILL_CAP = 1.15                               the cap as a multiple of V_h
    cut_step(v_fill, heights, *, dx, tip_x, depth, ds, width, v_heaped, cutting=True) -> CutStep
        v_fill: current V_fill (m3, >= 0); heights: 1-D terrain profile (m) on a uniform grid of spacing dx (m), cell i at
        x = i * dx; tip_x: tip position along the grid (m); depth: cutting depth d (m); ds: tip path length |delta s_tip|
        of the step (m); width: bucket width w (m); v_heaped: V_h (m3); cutting: whether the FEE force is active.
        Returns a frozen dataclass CutStep with `v_fill` (new volume, m3) and `heights` (a NEW float64 array; the input
        array is not modified). When cutting is False, v_fill and heights are returned unchanged. While cutting, the gain
        is width * depth * ds, the new volume is min(v_fill + gain, FILL_CAP * v_heaped), and while the volume stays
        below the cap the profile is lowered, nowhere raised, by the removed cross-section depth * ds (m2), so that
        width * dx * sum(heights_old - heights_new) == v_new - v_fill.
    fill_factor(v_fill, v_heaped) -> float        k_f = v_fill / v_heaped
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.robots.fill import FILL_CAP, cut_step, fill_factor

DX = 0.1
V_H = 1.5
W = 1.2


def flat(n: int = 120, z: float = 5.0) -> np.ndarray:
    return np.full(n, z, dtype=float)


@pytest.mark.req("FR-014-18")
def test_the_cap_is_1_15_of_the_heaped_volume() -> None:
    assert FILL_CAP == 1.15


@pytest.mark.req("FR-014-18")
def test_straight_cut_at_constant_depth_fills_the_swept_area_times_width() -> None:
    v, h = 0.0, flat()
    for i in range(30):  # 30 steps of 0.1 m: L = 3.0 m at d = 0.2 m
        step = cut_step(v, h, dx=DX, tip_x=1.0 + 0.1 * i, depth=0.2, ds=0.1, width=W, v_heaped=V_H)
        v, h = step.v_fill, step.heights
    assert v == pytest.approx(0.72, rel=1e-12)  # hand calculation: 1.2 * 0.2 * 3.0
    assert fill_factor(v, V_H) == pytest.approx(0.48, rel=1e-12)  # 0.72 / 1.5


@pytest.mark.req("FR-014-18")
def test_the_fill_is_capped_at_1_15_v_h_for_a_long_cut() -> None:
    v, h = 0.0, flat(400)
    for i in range(100):  # 10 m at d = 0.2 m would sweep 2.4 m3
        step = cut_step(v, h, dx=DX, tip_x=1.0 + 0.1 * i, depth=0.2, ds=0.1, width=W, v_heaped=V_H)
        v, h = step.v_fill, step.heights
    assert v == pytest.approx(1.725, rel=1e-12)  # 1.15 * 1.5
    assert fill_factor(v, V_H) == pytest.approx(1.15, rel=1e-12)


@pytest.mark.req("FR-014-18")
def test_the_step_that_crosses_the_cap_lands_exactly_on_it() -> None:
    step = cut_step(
        1.7, flat(), dx=DX, tip_x=2.0, depth=0.5, ds=0.2, width=W, v_heaped=V_H
    )  # gain 0.12 -> 1.82 > 1.725
    assert step.v_fill == pytest.approx(1.725, rel=1e-12)


@pytest.mark.req("FR-014-18")
def test_not_cutting_leaves_the_fill_and_the_terrain_untouched() -> None:
    h = flat() + np.linspace(0.0, 1.0, 120)
    step = cut_step(0.4, h, dx=DX, tip_x=2.0, depth=0.3, ds=0.2, width=W, v_heaped=V_H, cutting=False)
    assert step.v_fill == 0.4
    np.testing.assert_array_equal(step.heights, h)


@pytest.mark.req("FR-014-18")
def test_the_input_profile_is_not_modified() -> None:
    h = flat()
    before = h.copy()
    cut_step(0.0, h, dx=DX, tip_x=2.0, depth=0.3, ds=0.2, width=W, v_heaped=V_H)
    np.testing.assert_array_equal(h, before)


@pytest.mark.req("FR-014-18")
def test_zero_path_length_or_zero_depth_adds_nothing() -> None:
    for depth, ds in ((0.0, 0.2), (0.3, 0.0)):
        step = cut_step(0.3, flat(), dx=DX, tip_x=2.0, depth=depth, ds=ds, width=W, v_heaped=V_H)
        assert step.v_fill == pytest.approx(0.3, rel=1e-15)
        np.testing.assert_allclose(step.heights, flat(), rtol=0, atol=0)


# ------------------------------------------------------------------------------------------------ P-014-13
steps = st.lists(
    st.tuples(st.floats(0.0, 0.6), st.floats(0.0, 0.25), st.booleans()),  # depth, path length, cutting flag
    min_size=1,
    max_size=40,
)
profiles = st.lists(st.floats(0.0, 8.0), min_size=60, max_size=60).map(lambda xs: np.asarray(xs, dtype=float))


def run(path, h0, *, width=W, v0=0.0):
    v, h = v0, h0
    trace = [v]
    for i, (depth, ds, cutting) in enumerate(path):
        step = cut_step(
            v, h, dx=DX, tip_x=0.5 + 0.1 * i, depth=depth, ds=ds, width=width, v_heaped=V_H, cutting=cutting
        )
        v, h = step.v_fill, step.heights
        trace.append(v)
    return v, h, trace


@pytest.mark.req("P-014-13")
@given(steps, profiles)
@settings(max_examples=200, deadline=None)
def test_p13_mr1_fill_is_non_decreasing_and_never_exceeds_the_cap(path, h0) -> None:
    _v, _h, trace = run(path, h0)
    assert all(b >= a for a, b in pairwise(trace))
    assert max(trace) <= FILL_CAP * V_H * (1.0 + 1e-12)


@pytest.mark.req("P-014-13")
@given(steps, profiles)
@settings(max_examples=200, deadline=None)
def test_p13_mr2_below_the_cap_the_removed_terrain_volume_times_w_equals_the_fill_increase(path, h0) -> None:
    v, h, trace = run(path, h0)
    if max(trace) >= FILL_CAP * V_H * (1.0 - 1e-9):
        return  # MR2 is stated below the cap
    removed = float(np.sum(h0 - h)) * DX * W
    assert removed == pytest.approx(v, rel=1e-9, abs=1e-12)
    assert np.all(h <= h0 + 1e-15)  # the profile is only ever lowered


@pytest.mark.req("P-014-13")
@given(steps, profiles, st.floats(0.25, 4.0))
@settings(max_examples=200, deadline=None)
def test_p13_mr3_scaling_the_width_scales_the_fill_gain_below_the_cap(path, h0, k) -> None:
    base_v, _, base_trace = run(path, h0)
    big_v, _, big_trace = run(path, h0, width=k * W)
    if max(base_trace) >= FILL_CAP * V_H * (1.0 - 1e-9) or max(big_trace) >= FILL_CAP * V_H * (1.0 - 1e-9):
        return
    assert big_v == pytest.approx(k * base_v, rel=1e-9, abs=1e-12)


@pytest.mark.req("P-014-13")
def test_p13_doubling_the_width_doubles_the_gain_of_one_step() -> None:
    one = cut_step(0.0, flat(), dx=DX, tip_x=2.0, depth=0.25, ds=0.2, width=1.0, v_heaped=V_H).v_fill
    two = cut_step(0.0, flat(), dx=DX, tip_x=2.0, depth=0.25, ds=0.2, width=2.0, v_heaped=V_H).v_fill
    assert one == pytest.approx(0.05, rel=1e-12)  # hand calculation: 1.0 * 0.25 * 0.2
    assert two == pytest.approx(2.0 * one, rel=1e-12)


@pytest.mark.req("FR-014-18")
def test_fill_factor_is_the_ratio_to_the_heaped_volume() -> None:
    assert fill_factor(0.75, 1.5) == pytest.approx(0.5, rel=1e-15)
    assert fill_factor(0.0, 1.5) == 0.0
    assert fill_factor(1.725, 1.5) == pytest.approx(1.15, rel=1e-15)

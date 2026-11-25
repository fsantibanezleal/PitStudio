# ruff: noqa: E501
"""Case B1 time to collision of the Python traffic layer (spec 018 FR-018-55, P-018-19..21; docs M20): `pitstudio.haulage.ttc`.

Oracles, none of them the code under test:
- the published worked example of docs M20 (truck 10 m/s east, light vehicle 5 m/s west, 100 m apart, R = 4 m: 6.4 s);
- analytical encounters written here as hand calculations (radial, head-on, tangent, glancing, crossing, overlapping, diverging);
- `numpy.roots` on the quadratic |p + w tau|^2 = R^2 and a fine time scan of the distance, for random pairs;
- the metamorphic relations of spec 018 section 4: velocity scaling (P-018-19), rigid-motion invariance (P-018-20), pair symmetry
  (P-018-21).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pitstudio.haulage.ttc import TtcInputError, near_misses_per_1000h, ttc, ttc_pairs


def run(p, w, r):
    return ttc(p, w, r)


def test_docs_m20_worked_example_is_6_4_seconds():
    status, tau = run((100.0, 0.0), (-15.0, 0.0), 4.0)
    assert status == "closing"
    assert tau == pytest.approx(6.4, rel=1e-12)


def test_radial_approach_is_the_gap_over_the_closing_speed():
    # p = (30, 40), w = (-3, -4), R = 5: |p| = 50, closing speed 5 m/s, gap 45 m, 9 s
    assert run((30.0, 40.0), (-3.0, -4.0), 5.0) == ("closing", pytest.approx(9.0, rel=1e-12))


def test_head_on_on_one_line_is_the_gap_over_the_closing_speed():
    status, tau = run((50.0, 0.0), (-10.0, 0.0), 8.0)
    assert (status, tau) == ("closing", pytest.approx(4.2, rel=1e-12))


def test_tangent_pass_is_a_grazing_contact_and_counts_as_closing():
    # the relative track passes at exactly R: p = (30, 5), w = (-10, 0), R = 5: touch at tau = 3 s
    status, tau = run((30.0, 5.0), (-10.0, 0.0), 5.0)
    assert status == "closing"
    assert tau == pytest.approx(3.0, rel=1e-9)


def test_glancing_pass_hand_value():
    # p = (30, 3), w = (-10, 0), R = 5: x(tau) = 30 - 10 tau, 3^2 + x^2 = 25 gives x = 4, tau = 2.6 s
    status, tau = run((30.0, 3.0), (-10.0, 0.0), 5.0)
    assert (status, tau) == ("closing", pytest.approx(2.6, rel=1e-12))


def test_a_pass_that_misses_never_closes():
    assert run((30.0, 6.0), (-10.0, 0.0), 5.0) == ("not-closing", math.inf)


def test_crossing_paths_at_a_right_angle_hand_value():
    # a at the origin going east at 10 m/s, b 60 m north of the crossing point (40, 0) going south at 10 m/s
    # relative: p = (40, 60), w = (-10, -10), pp = 5200, ww = 200, pw = -1000, gap = 5100, disc = 1e6 - 200 * 5100 < 0: never touch
    assert run((40.0, 60.0), (-10.0, -10.0), 10.0) == ("not-closing", math.inf)
    # a nearer crossing: b 30 m north: p = (40, 30), w = (-10, -10): pp = 2500, pw = -700, gap = 2400, disc = 490000 - 480000 = 10000
    status, tau = run((40.0, 30.0), (-10.0, -10.0), 10.0)
    assert status == "closing"
    assert tau == pytest.approx(2400.0 / (700.0 + 100.0), rel=1e-12)  # 3.0 s


def test_overlapping_discs_have_ttc_zero_and_the_boundary_counts_as_overlap():
    assert run((3.0, 0.0), (1.0, 1.0), 4.0) == ("overlapping", 0.0)
    assert run((4.0, 0.0), (-1.0, 0.0), 4.0) == ("overlapping", 0.0)


def test_diverging_and_equal_velocity_pairs_do_not_close():
    assert run((50.0, 0.0), (5.0, 0.0), 4.0) == ("not-closing", math.inf)
    assert run((50.0, 0.0), (0.0, 0.0), 4.0) == ("not-closing", math.inf)


@pytest.mark.parametrize(
    ("p", "w", "r", "code"),
    [
        ((float("nan"), 0.0), (1.0, 0.0), 4.0, "E_NONFINITE"),
        ((0.0, float("inf")), (1.0, 0.0), 4.0, "E_NONFINITE"),
        ((1e6, 0.0), (1.0, 0.0), 4.0, "E_RANGE"),
        ((10.0, 0.0), (61.0, 0.0), 4.0, "E_RANGE"),
        ((10.0, 0.0), (1.0, 0.0), 0.0, "E_RANGE"),
        ((10.0, 0.0), (1.0, 0.0), -1.0, "E_RANGE"),
        ((10.0, 0.0), (1.0, 0.0), float("nan"), "E_RANGE"),
        ((10.0,), (1.0, 0.0), 4.0, "E_SCHEMA"),
        ((10.0, 0.0), ("a", 0.0), 4.0, "E_SCHEMA"),
        ((10.0, 0.0), (1.0, 0.0), "4", "E_SCHEMA"),
    ],
)
def test_hostile_arguments_raise_a_typed_error_with_a_code(p, w, r, code):
    with pytest.raises(TtcInputError) as e:
        ttc(p, w, r)
    assert e.value.code == code


def test_near_misses_per_1000_h_hand_values_and_hostile_arguments():
    assert near_misses_per_1000h(3, 3600.0) == pytest.approx(3000.0)
    assert near_misses_per_1000h(0, 10.0) == 0.0
    assert near_misses_per_1000h(1, 1800.0) == pytest.approx(2000.0)
    for bad in (-1, 1.5, True):
        with pytest.raises(ValueError, match="count"):
            near_misses_per_1000h(bad, 10.0)  # type: ignore[arg-type]
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="exposure"):
            near_misses_per_1000h(1, bad)


vec = st.tuples(st.floats(-500, 500), st.floats(-500, 500))
vel = st.tuples(st.floats(-30, 30), st.floats(-30, 30))


def numpy_roots_oracle(p, w, r):
    """The smallest positive real root of |p + w tau|^2 = r^2 by numpy.roots, or None."""
    pp, ww, pw = p[0] ** 2 + p[1] ** 2, w[0] ** 2 + w[1] ** 2, p[0] * w[0] + p[1] * w[1]
    if pp <= r * r:
        return 0.0
    if ww == 0.0:
        return None
    roots = np.roots([ww, 2 * pw, pp - r * r])
    real = [x.real for x in roots if abs(x.imag) < 1e-9 * max(1.0, abs(x.real)) and x.real > 0]
    return min(real) if real else None


@settings(max_examples=300, deadline=None)
@given(p=vec, w=vel, r=st.floats(1.0, 30.0))
def test_random_pairs_agree_with_numpy_roots(p, w, r):
    status, tau = ttc(p, w, r)
    ref = numpy_roots_oracle(p, w, r)
    if ref is None:
        assert status == "not-closing"
    elif ref == 0.0:
        assert status == "overlapping"
    else:
        # a grazing root can come back from numpy.roots as a complex pair with a tiny imaginary part, which the oracle drops
        assert status in ("closing", "not-closing")
        if status == "closing":
            assert tau == pytest.approx(ref, rel=1e-6, abs=1e-6)


def test_the_distance_at_the_ttc_is_exactly_the_radius_and_is_larger_before():
    rng = np.random.default_rng(20261125)
    checked = 0
    for _ in range(400):
        p = rng.uniform(-300, 300, 2)
        w = -p / np.hypot(*p) * rng.uniform(2, 25) + rng.normal(0, 4, 2)  # aimed at the other vehicle, with a spread
        r = float(rng.uniform(2, 20))
        status, tau = ttc(p, w, r)
        if status != "closing":
            continue
        checked += 1
        at = np.hypot(*(p + w * tau))
        assert at == pytest.approx(r, rel=1e-9)
        for frac in (0.0, 0.25, 0.5, 0.9, 0.999):
            assert np.hypot(*(p + w * tau * frac)) > r * (1 - 1e-12)
    assert checked > 50


@settings(max_examples=200, deadline=None)
@given(p=vec, w=vel, r=st.floats(1.0, 30.0), k=st.floats(0.1, 10.0))
def test_p_018_19_velocity_scaling(p, w, r, k):
    s1, t1 = ttc(p, w, r)
    wk = (w[0] * k, w[1] * k)
    if (
        math.hypot(*wk) > 60 or t1 > 1e6
    ):  # a TTC beyond 1e6 s is a speed of the order of 1e-300 m/s: rounding, not geometry
        return
    s2, t2 = ttc(p, wk, r)
    assert s1 == s2 or {s1, s2} <= {"closing", "not-closing"}  # a grazing contact may flip at the last ulp
    if s1 == s2 == "closing":
        assert t2 == pytest.approx(t1 / k, rel=1e-9)


@settings(max_examples=200, deadline=None)
@given(p=vec, w=vel, r=st.floats(1.0, 30.0), theta=st.floats(0, 2 * math.pi))
def test_p_018_20_rotation_invariance(p, w, r, theta):
    c, s = math.cos(theta), math.sin(theta)
    rot = lambda v: (c * v[0] - s * v[1], s * v[0] + c * v[1])  # noqa: E731
    s1, t1 = ttc(p, w, r)
    s2, t2 = ttc(rot(p), rot(w), r)
    assert s1 == s2 or {s1, s2} <= {"closing", "not-closing"}
    if s1 == s2 == "closing":
        assert t2 == pytest.approx(t1, rel=1e-9)


@settings(max_examples=200, deadline=None)
@given(xa=vec, xb=vec, va=vel, vb=vel, r=st.floats(1.0, 30.0))
def test_p_018_21_pair_symmetry(xa, xb, va, vb, r):
    ab = ttc((xb[0] - xa[0], xb[1] - xa[1]), (vb[0] - va[0], vb[1] - va[1]), r)
    ba = ttc((xa[0] - xb[0], xa[1] - xb[1]), (va[0] - vb[0], va[1] - vb[1]), r)
    assert ab == ba


def test_array_form_equals_the_scalar_form_and_broadcasts_a_radius_per_pair():
    rng = np.random.default_rng(7)
    p = rng.uniform(-200, 200, (500, 2))
    w = rng.uniform(-20, 20, (500, 2))
    r = rng.uniform(2, 15, 500)
    arr = ttc_pairs(p, w, r)
    for i in range(500):
        status, tau = ttc(p[i], w[i], float(r[i]))
        assert arr[i] == (tau if status != "not-closing" else math.inf)
    assert ttc_pairs(p, w, 6.0).shape == (500,)
    grid = ttc_pairs(p[:, None, :], w[:, None, :] * np.ones((1, 3, 1)), 6.0)
    assert grid.shape == (500, 3)

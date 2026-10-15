"""T-010-011: Hoek-Brown per-slice conversion to Mohr-Coulomb, iterated with F.

Requirement: FR-010-02.
Spec: specs/010-slope/spec.md section 3.1 (FR-010-02) and plan.md "Test strategy" (FR-010-02 row).

Expected API (module `pitstudio.slope.lem`, shared with T-010-010):
- `hoek_brown_parameters(gsi, m_i, d) -> (m_b, s, a)`.
- `hoek_brown_sigma1(sigma3_mpa, gsi, m_i, sigma_ci_mpa, d) -> float` (MPa): sigma1 = sigma3 + sigma_ci (m_b sigma3 /
  sigma_ci + s)^a.
- `hoek_brown_to_mohr_coulomb(gsi, m_i, sigma_ci_mpa, d, sigma_n_kpa) -> (c_kpa, phi_deg)`: the instantaneous
  Mohr-Coulomb pair of the Hoek-Brown envelope at the effective normal stress sigma_n (Balmer's parametric form,
  tangent line).
- `bishop_fos(section, circle, *, slices=None, max_iterations=100, tolerance=1e-9)` re-evaluates (c', phi') on every
  slice at the slice-base effective normal stress N'/l at every fixed-point iteration and stops when
  |F_k+1 - F_k| <= tolerance or after max_iterations (then `CircleRejected("non-convergence")`).
- `analyse_section(section)` as in T-010-010, for sections whose materials are `hoek-brown`.

Oracles (independent; tests/_slope_lem_ref.py):
- the Hoek-Brown table of docs/theory/slopes-and-monitoring.md ("Worked example 2": GSI 50, m_i 10, sigma_ci 50 MPa,
  D in {0, 0.7, 1}: m_b 1.677 / 0.641 / 0.281, s 0.00387 / 0.00071 / 0.00024, a 0.506, sigma1 at sigma3 = 1 MPa
  10.49 / 6.67 / 4.72 MPa, uniaxial strength 3.01 / 1.28 / 0.74 MPa), rounded as published;
- Balmer (1952) parametric form written out in the kit: forward map from sigma3 (MPa) to the contact point
  (sigma_n, tau) and the tangent (sin phi = (k - 1) / (k + 1), k = d sigma1 / d sigma3, c = (sigma1 - k sigma3) /
  (2 sqrt(k))), so the product's inversion from sigma_n is checked against a forward computation;
- a textbook Bishop with the slice-by-slice conversion iterated to 1e-12 on the same midpoint slices.
Tolerances: published table rounding (rel 1e-2 on the rounded values); conversion rtol 1e-6 (the product inverts the
forward map iteratively; 1e-6 is 1e3 above the 1e-9 stop rule); fixed circle rtol 1e-5 (both converge to the same fixed
point of F; the product's stop rule leaves 1e-9).
"""

from __future__ import annotations

import sys
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_lem_ref as ref
from pitstudio.slope import lem

HB_ROCK = {
    "id": "rock",
    "model": "hoek-brown",
    "unit_weight_kn_per_m3": 26.0,
    "gsi": 55.0,
    "m_i": 12.0,
    "sigma_ci_mpa": 60.0,
    "disturbance_d": 0.3,
}


def _hb_section(*, slices: int = 50, search=None, **mat):
    return ref.planar_section(
        height_m=60.0, slope_deg=45.0, ru=0.1, slices=slices, material={**HB_ROCK, **mat}, search=search
    )


def _circle(c: tuple[float, ...]) -> lem.Circle:
    return lem.Circle(entry_x_m=c[0], exit_x_m=c[1], centre_x_m=c[2], centre_z_m=c[3], radius_m=c[4])


def _mid_circle(sec: dict) -> tuple[float, ...]:
    ent, ex, rho = ref.grid_axes(sec)
    return ref.circle_from_points(sec, float(ent[10]), float(ex[25]), float(rho[3]))


# ---------------------------------------------------------------------------------------------------------------------
# published table of the slopes theory page


@pytest.mark.req("FR-010-02")
@pytest.mark.parametrize(
    ("d", "m_b", "s", "a", "sigma1", "ucs"),
    [
        (0.0, 1.677, 0.00387, 0.506, 10.49, 3.01),
        (0.7, 0.641, 0.00071, 0.506, 6.67, 1.28),
        (1.0, 0.281, 0.00024, 0.506, 4.72, 0.74),
    ],
)
def test_hoek_brown_parameters_and_strength_reproduce_the_published_table(d, m_b, s, a, sigma1, ucs) -> None:
    got_mb, got_s, got_a = lem.hoek_brown_parameters(50.0, 10.0, d)
    assert got_mb == pytest.approx(m_b, rel=1e-2)
    assert got_s == pytest.approx(s, rel=2e-2)
    assert got_a == pytest.approx(a, abs=1e-3)
    assert lem.hoek_brown_sigma1(1.0, 50.0, 10.0, 50.0, d) == pytest.approx(sigma1, abs=6e-3)
    assert lem.hoek_brown_sigma1(0.0, 50.0, 10.0, 50.0, d) == pytest.approx(ucs, abs=6e-3)


@pytest.mark.req("FR-010-02")
def test_hoek_brown_parameters_closed_form_at_the_ends_of_the_ranges() -> None:
    # GSI = 100, D = 0: m_b = m_i, s = 1, a = 1/2 + (e^-100/15 - e^-20/3)/6 (the 2018 form)
    m_b, s, a = lem.hoek_brown_parameters(100.0, 15.0, 0.0)
    assert (m_b, s) == pytest.approx((15.0, 1.0), rel=1e-12)
    assert a == pytest.approx(0.5 + (np.exp(-100 / 15) - np.exp(-20 / 3)) / 6, rel=1e-12)
    # GSI = 0, D = 1: m_b = m_i exp(-100/14), s = exp(-100/6), a = 1/2 + (1 - e^-20/3)/6
    m_b, s, a = lem.hoek_brown_parameters(0.0, 7.0, 1.0)
    assert m_b == pytest.approx(7.0 * np.exp(-100 / 14), rel=1e-12)
    assert s == pytest.approx(np.exp(-100 / 6), rel=1e-12)
    assert a == pytest.approx(0.5 + (1 - np.exp(-20 / 3)) / 6, rel=1e-12)


# ---------------------------------------------------------------------------------------------------------------------
# Balmer conversion at a given normal stress


_CASES = [
    (gsi, m_i, sci, d, s3_frac)
    for gsi in (0.0, 30.0, 50.0, 75.0, 100.0)
    for m_i in (1.0, 12.0, 35.0)
    for sci, d in ((1.0, 0.0), (50.0, 0.7), (250.0, 1.0))
    for s3_frac in (0.001, 0.05, 0.5)
]


@pytest.mark.req("FR-010-02")
def test_conversion_inverts_the_forward_balmer_map_on_a_grid_including_both_ends_of_every_range() -> None:
    assert len(_CASES) == 135
    for gsi, m_i, sci, d, frac in _CASES:
        point = ref.balmer(frac * sci, gsi, m_i, sci, d)
        assert point["c"] == pytest.approx(point["c_closed_form"], rel=1e-9)  # the oracle's own two forms agree
        c, phi = lem.hoek_brown_to_mohr_coulomb(gsi, m_i, sci, d, point["sigma_n"] * 1000.0)
        assert phi == pytest.approx(point["phi_deg"], rel=1e-6), (gsi, m_i, sci, d, frac)
        assert c == pytest.approx(point["c"] * 1000.0, rel=1e-6, abs=1e-9), (gsi, m_i, sci, d, frac)


@pytest.mark.req("FR-010-02")
def test_hand_value_at_one_point_gsi_50_mi_10_sigma_ci_50_d_0_7_sigma3_1() -> None:
    # Balmer's forward map at sigma3 = 1 MPa (kit formulas): sigma1 = 6.6749 MPa (the published 6.67),
    # sigma_n = 2.2026 MPa,
    # tangent phi = 35.1815 deg and c' = 0.76645 MPa; the product must return them from sigma_n alone
    c, phi = lem.hoek_brown_to_mohr_coulomb(50.0, 10.0, 50.0, 0.7, 2202.6092684534957)
    assert phi == pytest.approx(35.18150755642372, rel=1e-6)
    assert c == pytest.approx(766.4468795514392, rel=1e-6)


@st.composite
def _params(draw):
    return (
        draw(st.floats(0.0, 100.0)),
        draw(st.floats(0.5, 50.0)),
        draw(st.floats(1.0, 250.0)),
        draw(st.floats(0.0, 1.0)),
        draw(st.floats(1.0, 5000.0)),
        draw(st.floats(1.0, 5000.0)),
    )


@pytest.mark.req("FR-010-02")
@settings(max_examples=100, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
@given(_params())
def test_friction_angle_does_not_increase_with_normal_stress_and_is_bounded(p) -> None:
    gsi, m_i, sci, d, sn_a, sn_b = p
    lo, hi = sorted((sn_a, sn_b))
    c_lo, phi_lo = lem.hoek_brown_to_mohr_coulomb(gsi, m_i, sci, d, lo)
    c_hi, phi_hi = lem.hoek_brown_to_mohr_coulomb(gsi, m_i, sci, d, hi)
    assert 0.0 < phi_hi <= phi_lo + 1e-9 < 90.0  # the Hoek-Brown envelope is concave: its tangent flattens with stress
    assert c_lo >= 0.0
    assert c_hi >= 0.0


# ---------------------------------------------------------------------------------------------------------------------
# the slice conversion iterated with F


@pytest.mark.req("FR-010-02")
def test_fixed_circle_factor_equals_the_textbook_iteration_with_per_slice_conversion() -> None:
    sec = _hb_section()
    circle = _mid_circle(sec)
    f_ref, m_min, _ = ref.bishop_hb_one(sec, circle, 50, details=True)
    assert m_min > 0.5  # comfortable m_alpha: the 0.2 rule of FR-010-09 plays no role here
    res = lem.bishop_fos(sec, _circle(circle), slices=50, tolerance=1e-12)
    assert res.fos == pytest.approx(f_ref, rel=1e-5)
    assert res.iterations > 5  # (c', phi') change with F: not a one-shot evaluation


@pytest.mark.req("FR-010-02")
def test_stop_rule_and_the_100_iteration_cap() -> None:
    sec = _hb_section()
    circle = _circle(_mid_circle(sec))
    default = lem.bishop_fos(sec, circle, slices=50)  # tolerance 1e-9, 100 iterations
    tight = lem.bishop_fos(sec, circle, slices=50, tolerance=1e-13, max_iterations=100)
    assert default.iterations <= 100
    assert default.iterations <= tight.iterations
    assert abs(default.fos - tight.fos) <= 1e-8
    with pytest.raises(lem.CircleRejected) as exc:
        lem.bishop_fos(sec, circle, slices=50, max_iterations=2)
    assert exc.value.reason == "non-convergence"


@pytest.mark.req("FR-010-02")
def test_factor_increases_with_gsi_and_decreases_with_disturbance() -> None:
    base = _hb_section()
    circle = _circle(_mid_circle(base))
    by_gsi = [lem.bishop_fos(_hb_section(gsi=g), circle, slices=50).fos for g in (35.0, 45.0, 55.0, 65.0, 75.0)]
    by_d = [lem.bishop_fos(_hb_section(disturbance_d=d), circle, slices=50).fos for d in (0.0, 0.5, 1.0)]
    assert all(b > a for a, b in pairwise(by_gsi))
    assert all(b < a for a, b in pairwise(by_d))
    # textbook values at the two ends (the published GSI and D trends are only a sanity check, this is the oracle)
    ends = {
        35.0: ref.bishop_hb_one(_hb_section(gsi=35.0), _mid_circle(base), 50),
        75.0: ref.bishop_hb_one(_hb_section(gsi=75.0), _mid_circle(base), 50),
    }
    assert by_gsi[0] == pytest.approx(ends[35.0], rel=1e-4)
    assert by_gsi[-1] == pytest.approx(ends[75.0], rel=1e-4)


@pytest.mark.req("FR-010-02")
def test_search_minimum_over_a_small_grid_matches_the_textbook_hoek_brown_search() -> None:
    search = {"entry_points": 3, "exit_points": 3, "radius_ratios": 2, "rho_min": 1.5, "rho_max": 3.0}
    sec = _hb_section(slices=20, search=search)
    sec["analysis"]["methods"] = ["bishop"]
    circles = ref.grid_circles(sec)
    values = []
    for i in range(len(circles[0])):
        c = tuple(float(a[i]) for a in circles)
        f, m_min, _ = ref.bishop_hb_one(sec, c, 20, details=True)
        if m_min > 0.2:
            values.append(f)
    row = lem.analyse_section(sec)["fos"][0]
    assert row["status"] == "ok"
    assert row["fos"] == pytest.approx(min(values), rel=2e-3)
    assert row["circles_evaluated"] == 16
    assert 1 <= row["iterations"] <= 100

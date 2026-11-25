"""T-010-010: slip-circle search, Bishop and Spencer composition, rejection rules.

Requirements: FR-010-01, FR-010-09, P-010-03, P-010-06.
Spec: specs/010-slope/spec.md section 3.1 and the parameter table of section 7; plan.md "Test strategy".

Expected API of the implementation (module `pitstudio.slope.lem`, numpy only, root environment):
- `Circle(entry_x_m, exit_x_m, centre_x_m, centre_z_m, radius_m)` (keyword construction; frozen dataclass/NamedTuple).
- `circle_grid(section: dict) -> list[Circle]`: the deterministic trial circles of section 7 (entry x 40 points,
  exit x 40 points, radius ratio 8 values geometric, centre above the chord, pairs with exit <= entry dropped), in
  entry-major, exit, ratio order.
- `bishop_fos(section, circle, *, slices=None, max_iterations=100, tolerance=1e-9) -> CircleResult(fos, iterations,
  theta_deg=None)`; `spencer_fos(section, circle, *, slices=None, max_iterations=100) -> CircleResult` with `theta_deg`;
  `spencer_moment_factor(section, circle, theta_deg, *, slices=None) -> float`;
  `spencer_force_factor(section, circle, theta_deg, *, slices=None) -> float`.
  `slices=None` means `section["analysis"]["slices"]`. A rejected circle raises `CircleRejected` (an Exception) whose
  `.reason` is one of "non-convergence", "m_alpha", "no-theta", "empty-mass".
- `CircleResult(fos, iterations, theta_deg=None)` (NamedTuple or frozen dataclass).
- `analyse_section(section, *, bishop=bishop_fos, spencer=spencer_fos) -> dict` with `section_id` and `fos`: one row per
  requested method in the shape of `slope-results.schema.json#/$defs/fos_result` (method, status "ok" | "no valid slip
  surface", fos, critical_circle, iterations, theta_deg for Spencer only, slices, circles_evaluated, rejected_circles).
  `circles_evaluated` counts the trial circles generated (rejected ones included). Spencer is evaluated on the 64
  lowest-Bishop circles in live mode and on every circle in baked mode. The keyword arguments `bishop` and `spencer` are
  the per-circle solvers (a test seam: the aggregation is tested with fake solvers; by default the product's own).

Oracles (independent, tests/_slope_lem_ref.py): the M13 worked example (F0 = 1 gives 1.866, 2.018, 2.034, 2.035 and
sum W sin a = 560.1 kN/m, docs/methods/m13-slope-stability-lem.md); a textbook midpoint-slice Bishop and Spencer
(Spencer 1967) written in the test kit over the same grid; exhaustive hand count of the grid (1,599 pairs x 8 = 12,792
circles; a 3 x 3 x 3 grid has 8 pairs x 3 = 24).
Tolerance: rtol 2e-3 between the product and the textbook slicing at the same slice count, the bound the plan gives for
the slice-refinement error (P-010-06: 1e-3 F from 200 to 400 slices, doubled for a different quadrature of the same
rule). Identities inside the product (theta = 0) use rtol 1e-9.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

import _slope_lem_ref as ref  # noqa: E402
from pitstudio.slope import lem  # noqa: E402  (first-party import first: the red failure is a missing module)

RTOL = 2e-3


def _circle(c: tuple[float, ...]) -> lem.Circle:
    return lem.Circle(entry_x_m=c[0], exit_x_m=c[1], centre_x_m=c[2], centre_z_m=c[3], radius_m=c[4])


def _section(**kw):
    kw.setdefault("slope_deg", 30.0)
    kw.setdefault("cohesion", 25.0)
    kw.setdefault("friction", 32.0)
    return ref.planar_section(**kw)


# ---------------------------------------------------------------------------------------------------------------------
# the oracle itself reproduces the published worked example


@pytest.mark.req("FR-010-01")
def test_oracle_reproduces_the_m13_three_slice_worked_example() -> None:
    drive, iterates = ref.bishop_fixed_point([500, 800, 400], [40, 20, -5], [5, 5, 5], 10.0, 30.0)
    assert drive == pytest.approx(560.1, abs=0.05)
    assert iterates[:4] == pytest.approx([1.866, 2.018, 2.034, 2.035], abs=1.5e-3)


# ---------------------------------------------------------------------------------------------------------------------
# FR-010-01: the deterministic search grid


@pytest.mark.req("FR-010-01")
def test_default_grid_has_the_hand_counted_number_of_circles() -> None:
    sec = _section()
    circles = lem.circle_grid(sec)
    # 40 entry x 40 exit = 1,600 pairs; entry range ends where the exit range starts, so exactly one pair has
    # exit <= entry and is dropped; 1,599 pairs x 8 radius ratios = 12,792 circles (spec: at most 12,800).
    assert len(circles) == 1599 * 8 == 12792


@pytest.mark.req("FR-010-01")
def test_grid_axes_and_circle_geometry_follow_the_section_7_table() -> None:
    sec = _section()
    entry, exit_, rho = ref.grid_axes(sec)
    circles = lem.circle_grid(sec)
    g = ref.ground_fn(sec)
    assert {round(c.entry_x_m, 9) for c in circles} == {round(float(x), 9) for x in entry}
    assert {round(c.exit_x_m, 9) for c in circles} == {round(float(x), 9) for x in exit_}
    for c in circles[:: len(circles) // 97]:
        ze, zx = float(g(c.entry_x_m)), float(g(c.exit_x_m))
        # both end points are on the circle ...
        assert np.hypot(c.entry_x_m - c.centre_x_m, ze - c.centre_z_m) == pytest.approx(c.radius_m, rel=1e-9)
        assert np.hypot(c.exit_x_m - c.centre_x_m, zx - c.centre_z_m) == pytest.approx(c.radius_m, rel=1e-9)
        # ... the radius is rho x half-chord with rho one of the eight geometric values, centre above the chord
        half = np.hypot(c.exit_x_m - c.entry_x_m, zx - ze) / 2
        assert any(c.radius_m == pytest.approx(r * half, rel=1e-9) for r in rho)
        mid_z = (ze + zx) / 2
        normal_up = (c.centre_z_m - mid_z) / np.hypot(
            c.centre_x_m - (c.entry_x_m + c.exit_x_m) / 2, c.centre_z_m - mid_z
        )
        assert normal_up > 0


@pytest.mark.req("FR-010-01")
def test_small_grid_count_by_hand_is_24() -> None:
    search = {"entry_points": 3, "exit_points": 3, "radius_ratios": 3, "rho_min": 1.5, "rho_max": 3.0}
    sec = _section(search=search)
    # 3 x 3 = 9 pairs, the shared mid-point pair (exit == entry) is dropped: 8 pairs x 3 ratios
    assert len(lem.circle_grid(sec)) == 24
    rho_values = sorted({round(float(r), 9) for r in ref.grid_axes(sec)[2]})
    assert rho_values == [1.5, round(float(np.sqrt(1.5 * 3.0)), 9), 3.0]  # geometric spacing 1.5, sqrt(4.5), 3


# ---------------------------------------------------------------------------------------------------------------------
# FR-010-01: minimum Bishop F over the grid, critical circle, counts


@pytest.mark.req("FR-010-01")
@pytest.mark.parametrize(("mode", "n_s"), [("baked", 200), ("live", 50)])
def test_minimum_bishop_factor_matches_the_textbook_search(mode: str, n_s: int) -> None:
    sec = _section(mode=mode, slices=n_s, methods=("bishop",))
    circles, f_ref = ref.grid_bishop(sec, n_s)
    f_min = float(np.nanmin(f_ref))
    row = next(r for r in lem.analyse_section(sec)["fos"] if r["method"] == "bishop")
    assert row["status"] == "ok"
    assert row["fos"] == pytest.approx(f_min, rel=RTOL)
    assert row["slices"] == n_s
    assert row["circles_evaluated"] == 12792
    assert 0 <= row["rejected_circles"] <= 0.01 * 12792
    assert 1 <= row["iterations"] <= 100
    # the reported critical circle is a grid circle and has the reported factor when evaluated by the textbook
    cc = row["critical_circle"]
    crit = (cc["entry_x_m"], cc["exit_x_m"], cc["centre_x_m"], cc["centre_z_m"], cc["radius_m"])
    assert any(np.allclose(crit, [a[i] for a in circles], rtol=1e-9, atol=1e-9) for i in np.argsort(f_ref)[:50])
    assert ref.bishop_one(sec, crit, n_s) == pytest.approx(row["fos"], rel=RTOL)


@pytest.mark.req("FR-010-01")
def test_small_grid_minimum_equals_exhaustive_textbook_minimum_for_bishop_and_spencer() -> None:
    search = {"entry_points": 4, "exit_points": 4, "radius_ratios": 3, "rho_min": 1.3, "rho_max": 3.0}
    sec = _section(mode="baked", slices=200, search=search)
    circles, f_bishop = ref.grid_bishop(sec, 200)
    spencer = [
        ref.spencer_one(sec, tuple(float(a[i]) for a in circles), 200)
        for i in range(len(f_bishop))
        if np.isfinite(f_bishop[i])
    ]
    f_spencer_min = min(r[0] for r in spencer if r is not None)
    rows = {r["method"]: r for r in lem.analyse_section(sec)["fos"]}
    assert rows["bishop"]["fos"] == pytest.approx(float(np.nanmin(f_bishop)), rel=RTOL)
    assert rows["spencer"]["fos"] == pytest.approx(f_spencer_min, rel=RTOL)
    assert -90.0 < rows["spencer"]["theta_deg"] < 90.0
    assert "theta_deg" not in rows["bishop"]
    assert rows["spencer"]["circles_evaluated"] == len(f_bishop)  # baked: Spencer on every circle


@pytest.mark.req("FR-010-01")
def test_live_spencer_runs_on_the_64_lowest_bishop_circles() -> None:
    sec = _section(mode="live", slices=50)
    expected = ref.spencer_search_min(sec, 64, 50)
    row = next(r for r in lem.analyse_section(sec)["fos"] if r["method"] == "spencer")
    assert row["fos"] == pytest.approx(expected, rel=RTOL)
    assert row["slices"] == 50
    # Spencer is not larger than ... nor wildly different from Bishop on a slope like this (same physics, one more
    # equilibrium condition): within 5 %
    bishop = next(r for r in lem.analyse_section(sec)["fos"] if r["method"] == "bishop")
    assert abs(row["fos"] - bishop["fos"]) <= 0.05 * bishop["fos"]


@pytest.mark.req("FR-010-01")
def test_rows_validate_against_the_slope_results_fos_schema() -> None:
    sec = _section(
        mode="live",
        slices=50,
        search={"entry_points": 8, "exit_points": 8, "radius_ratios": 3, "rho_min": 1.2, "rho_max": 3.0},
    )
    for row in lem.analyse_section(sec)["fos"]:
        assert ref.schema_errors(row, "slope-results", "fos_result") == []


# ---------------------------------------------------------------------------------------------------------------------
# P-010-03 and P-010-06 on fixed circles


@st.composite
def _section_and_circle(draw):
    sec = ref.planar_section(
        height_m=draw(st.floats(5.0, 200.0)),
        slope_deg=draw(st.floats(20.0, 60.0)),
        unit_weight=draw(st.floats(16.0, 28.0)),
        cohesion=draw(st.floats(0.0, 200.0)),
        friction=draw(st.floats(5.0, 50.0)),
        ru=draw(st.floats(0.0, 0.5)),
        slices=200,
        search={"entry_points": 6, "exit_points": 6, "radius_ratios": 4, "rho_min": 1.3, "rho_max": 4.0},
    )
    circles, f = ref.grid_bishop(sec, 200)
    # circles with a comfortable m_alpha margin only (> 0.3 at F = 1 and at the solution): the 0.2 rule of FR-010-09 is
    # tested on its own below, so these properties do not depend on which iteration the rule is checked at
    comfortable = [
        i
        for i in np.flatnonzero(np.isfinite(f))
        if ref.min_m_alpha(sec, tuple(float(a[i]) for a in circles), 200, 1.0) > 0.3
        and ref.min_m_alpha(sec, tuple(float(a[i]) for a in circles), 200, float(f[i])) > 0.3
    ]
    idx = int(comfortable[draw(st.integers(0, len(comfortable) - 1))]) if comfortable else None
    return sec, (None if idx is None else tuple(float(a[idx]) for a in circles))


@pytest.mark.req("P-010-03")
@settings(max_examples=200, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
@given(_section_and_circle())
def test_spencer_moment_factor_at_theta_zero_equals_bishop(case) -> None:
    sec, c = case
    if c is None:
        return
    circle = _circle(c)
    # rtol 1e-8 instead of the spec's 1e-9: the fixed-point stop rule |F_k+1 - F_k| <= 1e-9 (FR-010-02) leaves an
    # error of that order itself (see the report); Bishop is run to 1e-12 so only Spencer's own stop rule remains
    bishop = lem.bishop_fos(sec, circle, tolerance=1e-12).fos
    assert lem.spencer_moment_factor(sec, circle, 0.0) == pytest.approx(bishop, rel=1e-8)


@pytest.mark.req("P-010-06")
@settings(max_examples=200, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
@given(_section_and_circle())
def test_slice_refinement_from_200_to_400_changes_bishop_by_at_most_1e_3(case) -> None:
    sec, c = case
    if c is None:
        return
    circle = _circle(c)
    f200 = lem.bishop_fos(sec, circle, slices=200).fos
    f400 = lem.bishop_fos(sec, circle, slices=400).fos
    assert abs(f400 - f200) <= 1e-3 * f200


@pytest.mark.req("FR-010-01")
def test_spencer_theta_is_the_root_of_force_minus_moment_factor() -> None:
    sec = _section(slices=200)
    ent, ex, rho = ref.grid_axes(sec)
    circle = ref.circle_from_points(sec, float(ent[0]), float(ex[-1]), float(rho[len(rho) // 2]))
    res = lem.spencer_fos(sec, _circle(circle), slices=200)
    ff = lem.spencer_force_factor(sec, _circle(circle), res.theta_deg, slices=200)
    fm = lem.spencer_moment_factor(sec, _circle(circle), res.theta_deg, slices=200)
    assert ff == pytest.approx(fm, rel=1e-7)
    assert res.fos == pytest.approx(fm, rel=1e-7)
    expected = ref.spencer_one(sec, circle, 200)
    assert expected is not None
    assert res.fos == pytest.approx(expected[0], rel=RTOL)
    assert -90.0 < res.theta_deg < 90.0


# ---------------------------------------------------------------------------------------------------------------------
# FR-010-09: rejection rules on one circle


@pytest.mark.req("FR-010-09")
def test_circle_with_a_vertical_exit_base_is_rejected_for_m_alpha() -> None:
    sec = _section(
        slices=200, slope_deg=8.0
    )  # gentle ground: the mass is left-heavy, so the driving moment is positive
    # the exit point is the rightmost point of the circle: the last slices have base angles near -85 degrees, so
    # cos(alpha) < 0.09 and m_alpha = cos(alpha) (1 + tan(alpha) tan(phi) / F) < cos(alpha) < 0.2 for every F > 0
    circle = _circle(ref.rightmost_point_circle(sec, 10.0, 30.0))
    with pytest.raises(lem.CircleRejected) as exc:
        lem.bishop_fos(sec, circle, slices=200)
    assert exc.value.reason == "m_alpha"
    with pytest.raises(lem.CircleRejected):
        lem.spencer_fos(sec, circle, slices=200)


@pytest.mark.req("FR-010-09")
def test_iteration_that_does_not_converge_in_the_allowed_steps_is_rejected() -> None:
    sec = _section(slices=200)
    ent, ex, rho = ref.grid_axes(sec)
    circle = _circle(ref.circle_from_points(sec, float(ent[5]), float(ex[-3]), float(rho[3])))
    ok = lem.bishop_fos(sec, circle)  # converges with the default 100 iterations at 1e-9
    assert ok.iterations >= 3  # F0 = 1 is far from the fixed point (M13 example: 5 steps to 3 decimals)
    with pytest.raises(lem.CircleRejected) as exc:
        lem.bishop_fos(sec, circle, max_iterations=1)
    assert exc.value.reason == "non-convergence"


@pytest.mark.req("FR-010-09")
def test_circle_that_does_not_cut_the_ground_has_an_empty_sliding_mass() -> None:
    sec = _section()
    # a small circle centred 100 m above the ground line: no soil above its lower arc
    circle = lem.Circle(entry_x_m=0.0, exit_x_m=10.0, centre_x_m=5.0, centre_z_m=120.0, radius_m=5.0)
    with pytest.raises(lem.CircleRejected) as exc:
        lem.bishop_fos(sec, circle)
    assert exc.value.reason == "empty-mass"


# ---------------------------------------------------------------------------------------------------------------------
# FR-010-01 and FR-010-09: aggregation over the grid with fake per-circle solvers (closed-form factors)


def _closed_form_f(circle) -> float:
    # F = 1 + |entry - 3| / 100 + radius / 1e4: strictly positive and distinct for distinct circles
    return 1.0 + abs(circle.entry_x_m - 3.0) / 100 + circle.radius_m / 1e4


def _fake_bishop(rejected=lambda c: False):
    def solve(section, circle, *, slices=None, **_):
        if rejected(circle):
            raise lem.CircleRejected("non-convergence")
        return lem.CircleResult(fos=_closed_form_f(circle), iterations=7)

    return solve


@pytest.mark.req("FR-010-01")
def test_the_minimum_is_taken_over_the_circles_and_the_critical_circle_is_reported() -> None:
    sec = _section(methods=("bishop",))
    grid = lem.circle_grid(sec)
    f = [_closed_form_f(c) for c in grid]
    best = grid[int(np.argmin(f))]
    row = lem.analyse_section(sec, bishop=_fake_bishop())["fos"][0]
    assert row["fos"] == pytest.approx(min(f), rel=1e-12)
    cc = row["critical_circle"]
    got = (cc["entry_x_m"], cc["exit_x_m"], cc["centre_x_m"], cc["centre_z_m"], cc["radius_m"])
    want = (best.entry_x_m, best.exit_x_m, best.centre_x_m, best.centre_z_m, best.radius_m)
    assert got == pytest.approx(want, rel=1e-12)
    assert row["iterations"] == 7
    assert row["circles_evaluated"] == 12792
    assert row["rejected_circles"] == 0


@pytest.mark.req("FR-010-09")
def test_rejected_circles_are_excluded_from_the_minimum_and_counted() -> None:
    sec = _section(methods=("bishop",))
    grid = lem.circle_grid(sec)
    best = min(grid, key=_closed_form_f)

    def rejected(c) -> bool:  # rejects the true minimum and every circle with entry x below -30
        return c == best or c.entry_x_m < -30.0

    expected_rejected = sum(1 for c in grid if rejected(c))
    row = lem.analyse_section(sec, bishop=_fake_bishop(rejected))["fos"][0]
    survivors = [_closed_form_f(c) for c in grid if not rejected(c)]
    assert row["fos"] == pytest.approx(min(survivors), rel=1e-12)
    assert row["fos"] > _closed_form_f(best)
    assert row["rejected_circles"] == expected_rejected > 1
    assert row["circles_evaluated"] == 12792


@pytest.mark.req("FR-010-09")
@pytest.mark.parametrize("methods", [("bishop",), ("spencer",), ("bishop", "spencer")])
def test_when_every_circle_is_rejected_the_result_is_no_valid_slip_surface_without_a_factor(methods) -> None:
    search = {"entry_points": 6, "exit_points": 6, "radius_ratios": 2, "rho_min": 1.5, "rho_max": 3.0}
    sec = _section(methods=methods, search=search)

    def reject_all(*_a, **_k):
        raise lem.CircleRejected("m_alpha")

    rows = lem.analyse_section(sec, bishop=reject_all, spencer=reject_all)["fos"]
    assert [r["method"] for r in rows] == list(methods)
    for row in rows:
        assert row["status"] == "no valid slip surface"
        assert "fos" not in row
        assert "critical_circle" not in row
        assert row["circles_evaluated"] == 2 * (6 * 6 - 1)
        assert row["rejected_circles"] == row["circles_evaluated"]
        assert ref.schema_errors(row, "slope-results", "fos_result") == []


@pytest.mark.req("FR-010-01")
@pytest.mark.parametrize(("mode", "expected_calls"), [("live", 64), ("baked", 12792)])
def test_spencer_runs_on_the_64_lowest_bishop_circles_live_and_on_every_circle_baked(mode, expected_calls) -> None:
    sec = _section(mode=mode, slices=50 if mode == "live" else 200)
    grid = lem.circle_grid(sec)
    called: list = []

    def spencer(section, circle, *, slices=None, **_):
        called.append(circle)
        return lem.CircleResult(fos=_closed_form_f(circle) - 0.01, iterations=5, theta_deg=12.5)

    rows = {r["method"]: r for r in lem.analyse_section(sec, bishop=_fake_bishop(), spencer=spencer)["fos"]}
    assert len(called) == expected_calls
    if mode == "live":
        assert set(called) == set(sorted(grid, key=_closed_form_f)[:64])
    assert rows["spencer"]["theta_deg"] == 12.5
    assert rows["spencer"]["fos"] == pytest.approx(min(_closed_form_f(c) for c in called) - 0.01, rel=1e-12)

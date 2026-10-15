"""T-010-013: metamorphic relations of the limit-equilibrium analysis.

Requirements: P-010-01, P-010-02, P-010-04, P-010-05.
Spec: specs/010-slope/spec.md section 4 (properties), plan.md "Numerical cores and their metamorphic relations".

Expected API: `pitstudio.slope.lem.analyse_section(section) -> {"fos": [row, ...]}` as in T-010-010; a left-facing
section (ground descending towards -x, `crest_x_m > toe_x_m`) is accepted and analysed as the mirror image of the
right-facing one (P-010-05 states the mirror relation, so the product must accept both orientations).

No absolute oracle is needed: each relation compares two analyses of related sections (Hypothesis, 200 examples in CI
per `property_tests.ci_examples_per_test`; derandomised so the run is deterministic). The sections are straight-ground
sections (tests/_slope_lem_ref.planar_section) with a reduced search grid (10 x 10 x 4 = 396 circles, live mode, 50
slices) so that 200 examples stay fast; the generators use the ranges of the spec: H 5-200 m, face 20-80 degrees,
gamma 16-28 kN/m3, c' 0-200 kPa, phi' 5-50 degrees, r_u 0-0.5.

Finding recorded by this file (see the report): P-010-01/02 as stated cannot hold when circles are rejected by the
m_alpha rule of FR-010-09, because the rejection depends on F itself (a circle rejected at low c' may be accepted at
higher c' and have a lower factor than the previous minimum; Hypothesis finds H = 5 m, face 76 degrees, gamma 16,
c' 0 -> 1 kPa, phi' 10 degrees, where F falls from 0.123 to 0.088). The monotonicity tests therefore state the relation
for analyses in which no circle was rejected (rejected_circles == 0 in both, 63 % of the generated sections) and F is
not degenerate (F > 0.05: for strongly unstable circles the F0 = 1 iteration can collapse to the trivial root F = 0).
The Spencer relations run in baked mode (every circle), since the live candidate set (the 64 lowest Bishop circles)
moves with the parameters.

Tolerances (the plan's justification): monotonicity F(x+d) >= F(x) - 1e-12 F; similarity rtol 1e-9; translation and
mirror rtol 1e-10. All three also carry abs 1e-9, the resolution of the fixed-point stop rule |F_k+1 - F_k| <= 1e-9
(FR-010-02): two analyses that are equal in exact arithmetic may stop one iteration apart (reported as a spec finding).
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_lem_ref as ref
from pitstudio.slope import lem

SEARCH = {"entry_points": 10, "exit_points": 10, "radius_ratios": 4, "rho_min": 1.1, "rho_max": 4.0}
SEARCH_SPENCER = {"entry_points": 5, "exit_points": 5, "radius_ratios": 2, "rho_min": 1.3, "rho_max": 3.0}
PROP = settings(max_examples=200, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
PROP_SPENCER = settings(max_examples=30, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))


def _build(h, face, gamma, c, phi, ru, methods=("bishop",), *, baked: bool = False) -> dict:
    return ref.planar_section(
        height_m=h,
        slope_deg=face,
        unit_weight=gamma,
        cohesion=c,
        friction=phi,
        ru=ru,
        mode="baked" if baked else "live",
        slices=40 if baked else 50,
        methods=methods,
        search=SEARCH_SPENCER if baked else SEARCH,
    )


@st.composite
def _params(draw):
    return (
        draw(st.floats(5.0, 200.0)),
        draw(st.floats(20.0, 80.0)),
        draw(st.floats(16.0, 28.0)),
        draw(st.floats(0.0, 200.0)),
        draw(st.floats(5.0, 50.0)),
        draw(st.floats(0.0, 0.5)),
    )


def _fos(section: dict, method: str = "bishop") -> float | None:
    row = next(r for r in lem.analyse_section(section)["fos"] if r["method"] == method)
    return row["fos"] if row["status"] == "ok" else None


def _clean_fos(section: dict, method: str = "bishop") -> float:
    """The factor of an analysis in which no circle was rejected and F is not degenerate (module docstring)."""
    row = next(r for r in lem.analyse_section(section)["fos"] if r["method"] == method)
    assume(row["status"] == "ok" and row["rejected_circles"] == 0)
    assume(row["fos"] > 0.05)  # strongly unstable sections: the F0 = 1 iteration can collapse to the trivial root F = 0
    return row["fos"]


def _row(section: dict, method: str = "bishop") -> dict:
    return next(r for r in lem.analyse_section(section)["fos"] if r["method"] == method)


def _mirror(section: dict) -> dict:
    out = copy.deepcopy(section)
    out["ground"] = [[-x, z] for x, z in reversed(section["ground"])]
    out["crest_x_m"], out["toe_x_m"] = -section["crest_x_m"], -section["toe_x_m"]
    return out


def _translate(section: dict, dx: float, dz: float) -> dict:
    out = copy.deepcopy(section)
    out["ground"] = [[x + dx, z + dz] for x, z in section["ground"]]
    out["crest_x_m"] += dx
    out["toe_x_m"] += dx
    return out


def _scale(section: dict, k: float, g: float = 1.0) -> dict:
    """Lengths x k, unit weight x g, cohesion x k g (c / (gamma L) is the only dimensionless group with c)."""
    out = copy.deepcopy(section)
    out["ground"] = [[x * k, z * k] for x, z in section["ground"]]
    out["crest_x_m"] *= k
    out["toe_x_m"] *= k
    m = out["materials"][0]
    m["unit_weight_kn_per_m3"] *= g
    m["cohesion_kpa"] *= k * g
    return out


def _approx(x, rel):
    return pytest.approx(x, rel=rel, abs=1e-9)


# ---------------------------------------------------------------------------------------------------------------------
# P-010-01, P-010-02: monotonicity of the minimum factor


@pytest.mark.req("P-010-01")
@PROP
@given(_params(), st.floats(0.0, 100.0))
def test_minimum_bishop_factor_is_non_decreasing_in_cohesion(p, delta) -> None:
    h, face, gamma, c, phi, ru = p
    f0, f1 = _clean_fos(_build(h, face, gamma, c, phi, ru)), _clean_fos(_build(h, face, gamma, c + delta, phi, ru))
    assert f1 >= f0 - 1e-12 * f0


@pytest.mark.req("P-010-02")
@PROP
@given(_params(), st.floats(0.0, 10.0))
def test_minimum_bishop_factor_is_non_decreasing_in_friction_angle(p, delta) -> None:
    h, face, gamma, c, phi, ru = p
    f0 = _clean_fos(_build(h, face, gamma, c, phi, ru))
    f1 = _clean_fos(_build(h, face, gamma, c, min(phi + delta, 60.0), ru))
    assert f1 >= f0 - 1e-12 * f0


@pytest.mark.req("P-010-02")
@PROP
@given(_params(), st.floats(0.0, 0.4))
def test_minimum_bishop_factor_is_non_increasing_in_pore_pressure_ratio(p, delta) -> None:
    h, face, gamma, c, phi, ru = p
    f0 = _clean_fos(_build(h, face, gamma, c, phi, ru))
    f1 = _clean_fos(_build(h, face, gamma, c, phi, min(ru + delta, 0.99)))
    assert f1 <= f0 + 1e-12 * f0


@pytest.mark.req("P-010-01")
@PROP_SPENCER
@given(_params(), st.floats(0.0, 100.0))
def test_minimum_spencer_factor_is_non_decreasing_in_cohesion(p, delta) -> None:
    h, face, gamma, c, phi, ru = p
    m = ("spencer",)
    f0 = _clean_fos(_build(h, face, gamma, c, phi, ru, m, baked=True), "spencer")
    f1 = _clean_fos(_build(h, face, gamma, c + delta, phi, ru, m, baked=True), "spencer")
    assert f1 >= f0 - 1e-12 * f0


@pytest.mark.req("P-010-02")
@PROP_SPENCER
@given(_params(), st.floats(0.0, 10.0), st.floats(0.0, 0.4))
def test_minimum_spencer_factor_is_monotone_in_friction_and_pore_pressure(p, d_phi, d_ru) -> None:
    h, face, gamma, c, phi, ru = p
    m = ("spencer",)
    base = _clean_fos(_build(h, face, gamma, c, phi, ru, m, baked=True), "spencer")
    stronger = _clean_fos(_build(h, face, gamma, c, min(phi + d_phi, 60.0), ru, m, baked=True), "spencer")
    wetter = _clean_fos(_build(h, face, gamma, c, phi, min(ru + d_ru, 0.99), m, baked=True), "spencer")
    assert stronger >= base - 1e-12 * base
    assert wetter <= base + 1e-12 * base


# ---------------------------------------------------------------------------------------------------------------------
# P-010-04: similarity


@pytest.mark.req("P-010-04")
@PROP
@given(_params(), st.floats(0.1, 10.0))
def test_scaling_lengths_and_cohesion_by_k_leaves_the_factor_unchanged(p, k) -> None:
    section = _build(*p)
    f0, f1 = _fos(section), _fos(_scale(section, k))
    assert (f0 is None) == (f1 is None)
    if f0 is None or f1 is None:
        return
    assert f1 == _approx(f0, 1e-9)


@pytest.mark.req("P-010-04")
@PROP
@given(_params(), st.floats(0.1, 10.0), st.floats(0.8, 1.4))
def test_the_dimensionless_group_c_over_gamma_length_is_the_only_one_that_matters(p, k, g) -> None:
    # lengths x k, gamma x g, c' x k g: F depends on c' / (gamma L) only (the imperial conversion of the plan is this
    # relation with k = 3.28084 and g = 6.36588 / 1 pcf per kN/m3, which would exceed the 40 kN/m3 schema bound)
    section = _build(*p)
    f0, f1 = _fos(section), _fos(_scale(section, k, g))
    assert (f0 is None) == (f1 is None)
    if f0 is None or f1 is None:
        return
    assert f1 == _approx(f0, 1e-9)


# ---------------------------------------------------------------------------------------------------------------------
# P-010-05: translation and mirror


def _circle_of(cc: dict, *, dx: float = 0.0, dz: float = 0.0, flip: bool = False) -> lem.Circle:
    """The reported critical circle mapped back to the frame of the original section (translation or mirror)."""
    s = -1.0 if flip else 1.0
    return lem.Circle(
        entry_x_m=s * (cc["entry_x_m"] - dx),
        exit_x_m=s * (cc["exit_x_m"] - dx),
        centre_x_m=s * (cc["centre_x_m"] - dx),
        centre_z_m=cc["centre_z_m"] - dz,
        radius_m=cc["radius_m"],
    )


@pytest.mark.req("P-010-05")
@PROP
@given(_params(), st.floats(-1e4, 1e4), st.floats(-1e4, 1e4))
def test_translating_the_section_leaves_the_factor_unchanged(p, dx, dz) -> None:
    section = _build(*p)
    a, b = _row(section), _row(_translate(section, dx, dz))
    assert b["status"] == a["status"]
    if a["status"] != "ok":
        return
    assert b["fos"] == _approx(a["fos"], 1e-10)
    # the reported circle of the translated section, brought back, is a minimiser of the original (ties between circles
    # with equal factors, e.g. c' = 0 on straight ground, make the argmin itself non-unique)
    back = lem.bishop_fos(section, _circle_of(b["critical_circle"], dx=dx, dz=dz), slices=50).fos
    assert back == _approx(a["fos"], 1e-9)


@pytest.mark.req("P-010-05")
@PROP
@given(_params())
def test_mirroring_a_left_facing_section_leaves_the_factor_unchanged_and_mirrors_the_circle(p) -> None:
    section = _build(*p)
    a, b = _row(section), _row(_mirror(section))
    assert b["status"] == a["status"]
    if a["status"] != "ok":
        return
    assert b["fos"] == _approx(a["fos"], 1e-10)
    back = lem.bishop_fos(section, _circle_of(b["critical_circle"], flip=True), slices=50).fos
    assert back == _approx(a["fos"], 1e-9)


@pytest.mark.req("P-010-05")
def test_the_critical_circle_is_mirrored_when_the_minimum_is_unique() -> None:
    section = _build(30.0, 50.0, 21.0, 35.0, 28.0, 0.1)  # cohesive: a unique critical circle
    ca, cb = _row(section)["critical_circle"], _row(_mirror(section))["critical_circle"]
    assert cb["centre_x_m"] == pytest.approx(-ca["centre_x_m"], abs=1e-6)
    assert cb["centre_z_m"] == pytest.approx(ca["centre_z_m"], abs=1e-6)
    assert cb["radius_m"] == pytest.approx(ca["radius_m"], abs=1e-6)
    assert sorted((cb["entry_x_m"], cb["exit_x_m"])) == pytest.approx(
        sorted((-ca["entry_x_m"], -ca["exit_x_m"])), abs=1e-6
    )


@pytest.mark.req("P-010-05")
def test_spencer_is_mirror_and_translation_invariant_on_a_fixed_section() -> None:
    section = _build(30.0, 50.0, 21.0, 35.0, 28.0, 0.1, ("bishop", "spencer"))
    a = _row(section, "spencer")
    for other in (_mirror(section), _translate(section, 1234.5, -987.25)):
        b = _row(other, "spencer")
        assert b["fos"] == _approx(a["fos"], 1e-10)
        assert abs(b["theta_deg"]) == pytest.approx(abs(a["theta_deg"]), abs=1e-6)

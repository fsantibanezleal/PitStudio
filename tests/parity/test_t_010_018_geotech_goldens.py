"""T-010-018: C1 golden scenarios for the `geotech` parity fixture of spec 018.

Requirements: FR-010-01, FR-010-03.
Spec: specs/010-slope/tasks.md T-010-018 (">= 200 vectors per function, both ends of every range, no sample with |F -
1| < 1e-9,
best and second-best circle gap >= 1e-9 F"), specs/018-web-cases FR-018-51 / FR-018-52 and the DC-018-02
parity-fixture schema
(`contracts/parity-fixture.schema.json`); plan.md rows FR-010-01 and FR-010-03.

Expected API (module `pitstudio.slope.goldens`, root environment): `build_geotech_goldens(seed: int) -> dict[str,
dict]` maps the
function name to a parity-fixture document (valid against the schema, engine "geotech"):
- "bishop_fos" and "spencer_fos" (class analytical-iterative, solver_tol 1e-9, rtol 1e-8): cases with flat inputs
  {height_m, face_angle_deg, unit_weight_kn_per_m3, cohesion_kpa, friction_angle_deg, pore_pressure_ratio, slices,
  entry_x_m,
  exit_x_m, rho} describing a straight-ground section of that height and face angle (ground through crest at x = 0 and
  toe at
  x = H / tan(face), as tests/_slope_lem_ref.planar_section) and one circle through the ground points at entry_x_m and
  exit_x_m with
  radius rho x half-chord; outputs {fos} (Spencer also {theta_deg});
- "hoek_brown_mohr_coulomb" (analytical-iterative): inputs {gsi, m_i, sigma_ci_mpa, disturbance_d, sigma_n_kpa}, outputs
  {cohesion_kpa, friction_angle_deg};
- "search_min_fos" (analytical-iterative): the bishop inputs without the circle plus the search {entry_points,
  exit_points,
  radius_ratios, rho_min, rho_max}; outputs {fos, second_fos}: the best and the second-best circle of the search with
  (second_fos - fos) >= 1e-9 x fos (no tie, so the browser engine returns the same critical circle);
- "pof_monte_carlo" (class monte-carlo-count): cases with `variates` {generator "pcg64", entropy, spawn_key, samples:
  the sample matrix}
  and outputs {failing_samples, pof, factors: the per-sample minimum factor}: at least 200 samples per case and no
  factor with
  |F - 1| < 1e-9 (a sample cannot flip between engines on rounding); failing_samples = #(F < 1).
Every function except the Monte-Carlo one has >= 200 cases. For every input listed in RANGES the cases contain both
ends of the
validity range (exact values). `build_geotech_goldens` is deterministic in `seed`.

Oracles (independent): the textbook Bishop and Spencer of tests/_slope_lem_ref.py recomputed on a sample of cases
(rtol 2e-3, the
slice-quadrature bound of the plan), Balmer's parametric form of the kit for every Hoek-Brown case (rtol 1e-6),
counting in the test
for the Monte-Carlo cases, the schema of DC-018-02 (jsonschema).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_lem_ref as ref
from pitstudio.slope import goldens

RANGES = {
    "bishop_fos": {
        "height_m": (5.0, 200.0),
        "face_angle_deg": (20.0, 80.0),
        "unit_weight_kn_per_m3": (16.0, 28.0),
        "cohesion_kpa": (0.0, 200.0),
        "friction_angle_deg": (5.0, 50.0),
        "pore_pressure_ratio": (0.0, 0.5),
        "slices": (10, 500),
    },
    "hoek_brown_mohr_coulomb": {
        "gsi": (0.0, 100.0),
        "m_i": (1.0, 35.0),
        "sigma_ci_mpa": (1.0, 250.0),
        "disturbance_d": (0.0, 1.0),
    },
}
RANGES["spencer_fos"] = RANGES["bishop_fos"]
RANGES["search_min_fos"] = {k: v for k, v in RANGES["bishop_fos"].items() if k != "slices"}
ANALYTICAL = ["bishop_fos", "spencer_fos", "hoek_brown_mohr_coulomb", "search_min_fos"]


def _section_of(i: dict) -> dict:
    return ref.planar_section(
        height_m=i["height_m"],
        slope_deg=i["face_angle_deg"],
        unit_weight=i["unit_weight_kn_per_m3"],
        cohesion=i["cohesion_kpa"],
        friction=i["friction_angle_deg"],
        ru=i["pore_pressure_ratio"],
        slices=i["slices"],
    )


@pytest.fixture(scope="module")
def fixtures() -> dict:
    return goldens.build_geotech_goldens(20261007)


@pytest.mark.req("FR-010-01")
def test_the_expected_functions_are_present_and_the_documents_validate(fixtures) -> None:
    assert set(fixtures) >= {*ANALYTICAL, "pof_monte_carlo"}
    for name, doc in fixtures.items():
        assert doc["engine"] == "geotech"
        assert doc["function"] == name
        assert doc["reference"]["name"] == "minephys"
        assert ref.schema_errors(doc, "parity-fixture") == [], name


@pytest.mark.req("FR-010-01")
@pytest.mark.parametrize("name", ANALYTICAL)
def test_at_least_200_vectors_and_the_declared_tolerance(fixtures, name) -> None:
    doc = fixtures[name]
    assert len(doc["cases"]) >= 200
    tol = doc["tolerance"]
    assert tol["class"] == "analytical-iterative"
    assert tol["solver_tol"] == 1e-9
    assert tol["rtol"] == pytest.approx(1e-8)  # max(1e-9, 10 x the reference solver tolerance), FR-018-51


@pytest.mark.req("FR-010-01")
@pytest.mark.parametrize("name", list(RANGES))
def test_both_ends_of_every_validity_range_are_present(fixtures, name) -> None:
    cases = fixtures[name]["cases"]
    for key, (lo, hi) in RANGES[name].items():
        values = {c["input"][key] for c in cases}
        assert lo in values, (name, key, "lower end missing")
        assert hi in values, (name, key, "upper end missing")
        assert min(values) >= lo
        assert max(values) <= hi


@pytest.mark.req("FR-010-01")
def test_bishop_goldens_agree_with_the_textbook_on_a_sample_of_cases(fixtures) -> None:
    cases = fixtures["bishop_fos"]["cases"]
    for case in cases[:: max(1, len(cases) // 25)]:
        i = case["input"]
        sec = _section_of(i)
        circle = ref.circle_from_points(sec, i["entry_x_m"], i["exit_x_m"], i["rho"])
        expected = ref.bishop_one(sec, circle, i["slices"])
        assert np.isfinite(expected)
        assert case["output"]["fos"] == pytest.approx(expected, rel=2e-3)


@pytest.mark.req("FR-010-01")
def test_spencer_goldens_agree_with_the_textbook_and_bound_theta(fixtures) -> None:
    cases = fixtures["spencer_fos"]["cases"]
    for case in cases[:: max(1, len(cases) // 6)]:
        i, o = case["input"], case["output"]
        sec = _section_of(i)
        circle = ref.circle_from_points(sec, i["entry_x_m"], i["exit_x_m"], i["rho"])
        expected = ref.spencer_one(sec, circle, i["slices"])
        assert expected is not None
        assert o["fos"] == pytest.approx(expected[0], rel=2e-3)
        assert -90.0 < o["theta_deg"] < 90.0
    assert all(-90.0 < c["output"]["theta_deg"] < 90.0 for c in cases)


@pytest.mark.req("FR-010-02")
def test_hoek_brown_goldens_equal_balmer_parametric_form(fixtures) -> None:
    for case in fixtures["hoek_brown_mohr_coulomb"]["cases"]:
        i, o = case["input"], case["output"]
        c, phi = ref.hb_to_mc(i["sigma_n_kpa"], i["gsi"], i["m_i"], i["sigma_ci_mpa"], i["disturbance_d"])
        assert o["cohesion_kpa"] == pytest.approx(c, rel=1e-6, abs=1e-9)
        assert o["friction_angle_deg"] == pytest.approx(phi, rel=1e-6)


@pytest.mark.req("FR-010-01")
def test_the_search_goldens_have_no_tie_between_the_best_and_second_best_circle(fixtures) -> None:
    for case in fixtures["search_min_fos"]["cases"]:
        o = case["output"]
        assert o["second_fos"] >= o["fos"]
        assert o["second_fos"] - o["fos"] >= 1e-9 * o["fos"]
        assert o["fos"] > 0


@pytest.mark.req("FR-010-03")
def test_pof_goldens_count_samples_and_keep_every_factor_away_from_one(fixtures) -> None:
    doc = fixtures["pof_monte_carlo"]
    assert doc["tolerance"]["class"] == "monte-carlo-count"
    assert len(doc["cases"]) >= 5
    for case in doc["cases"]:
        v, o = case["variates"], case["output"]
        assert v["generator"] == "pcg64"
        n = len(v["samples"])
        assert n >= 200
        assert len(o["factors"]) == n
        f = np.asarray(o["factors"], dtype=float)
        assert np.all(np.abs(f - 1.0) >= 1e-9)  # no sample can flip on rounding
        assert o["failing_samples"] == int(np.sum(f < 1.0))
        assert o["pof"] == pytest.approx(o["failing_samples"] / n, rel=1e-12)


@pytest.mark.req("FR-010-01")
def test_the_goldens_are_deterministic_in_the_seed() -> None:
    a = goldens.build_geotech_goldens(7)
    b = goldens.build_geotech_goldens(7)
    c = goldens.build_geotech_goldens(8)
    assert a == b
    assert a["bishop_fos"]["cases"] != c["bishop_fos"]["cases"]

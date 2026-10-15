# ruff: noqa: E501, PT018
"""T-007-062: route energy against the M06 worked example and the minephys hand values; knowledge-table constants only, UNVERIFIED ids listed, the seven relations of P-007-19, hostile route inputs rejected.

Requirements: FR-007-34, FR-007-40, FR-007-45, P-007-19.

Spec: specs/007-haulage-dispatch/spec.md FR-007-34 (the route-energy engine `pitstudio.haulage.energy` computes, through `minephys.haulage`, the wheel and source energy of every leg and the regenerated energy on trolley and battery-electric descents; its inputs are an ordered route of
segments (length m, signed grade %, rolling resistance %, trolley flag), a truck (empty mass t, payload t, drivetrain in {diesel, trolley, bev}) and the leg (loaded or empty); it reports kWh/t, L/(t km) for diesel and kg CO2e/t, each stating its basis (payload tonnes, along-road
kilometres)), FR-007-40 (every physical constant and default comes from the `minephys` knowledge tables, never from a literal in PitStudio code: g, the diesel CO2 factor, efficiencies, rolling-resistance defaults, the g_max default; every result lists the ids of the UNVERIFIED rows it used),
FR-007-45 (a non-finite length, grade or mass, a length <= 0 m, a payload <= 0 t, an unknown drivetrain is rejected with `InvalidRouteInput` naming the field and value; NaN or Infinity is never returned), P-007-19 ((i) non-decreasing in grade, payload and RR; (ii) additive over concatenated routes;
(iii) wheel energy of a climb >= m g dz; (iv) diesel CO2 = fuel x the knowledge-table factor (linear); (v) a trolley route with zero trolley length equals diesel; (vi) regenerated energy <= eta_regen m g (GR - RR)/100 L; (vii) on a flat road A -> B equals B -> A; routes <= 200 segments, grades +-20 %,
RR in [0.5, 10] %, payload in [50, 400] t; rtol 1e-12, inequalities exact), section 7 "M6 worked example (hand calculation)" (a 400 t gross truck on 2 km at 10 % grade with 3 % RR, small-angle form: 510.12 kN and 283.4 kWh at the wheels, of which the lift is 218.0 kWh) and the minephys spec 001
section 7.4 (published hand values: `segment_energy(400000, 3000, 0.02, 0.10, small_angle=True)` = 1.4121576e9 J = 392.266 kWh; `fuel_use(., 36e9)` at efficiency 0.35 = 0.112076 m3; `co2_from_diesel(0.112076)` = 302.291 kg with 10.21 kg per US gallon / 3.785411784e-3 m3 per gallon).

Oracle: the hand-calculated values above; an independent plain-Python re-implementation of the per-segment formulas in this file (`oracle`: E_w = m g (RR/100 + GR) L, diesel E_w/eta, trolley line E_w/eta_e on trolley segments, no draw on descents for diesel and trolley, battery eta_regen E_w on descents),
used for random routes; the relations of P-007-19; an AST scan of the module sources for forbidden literals (the constants of FR-007-40 written out in this file); `minephys.knowledge.get_value` / `get_parameter` (minephys spec 008) for the default constants.

Expected API (module `pitstudio.haulage.energy`; error `InvalidRouteInput(HaulError)` in `pitstudio.haulage.errors` with attributes `field` and `value`):
    route_energy(route, truck, *, leg, constants=None, small_angle=True, grid_intensity_kg_per_j=None) -> dict
        route: sequence of 1 to 100,000 segments {"length_m": float > 0, "grade_pct": float (signed), "rr_pct": float >= 0, "trolley": bool}; truck: {"empty_mass_t": > 0, "payload_t": > 0, "drivetrain": "diesel" | "trolley" | "bev"}; leg: "loaded" (mass = empty + payload) or "empty" (mass = empty);
        constants: None (every constant from the `minephys` knowledge tables) or a mapping with any of "g" [m/s2], "eta_diesel", "eta_electric", "eta_drive", "eta_regen" [1], "fuel_energy_density_j_per_m3", "diesel_co2_kg_per_m3" that overrides the table value of that name;
        small_angle: the grade resistance is the grade itself (True) or sin(atan(grade)) (False); grid_intensity_kg_per_j: electricity emission factor, no default.
        Returns {"leg", "mass_t", "payload_t", "road_km", "wheel_kwh" (signed net wheel energy), "diesel_kwh" and "electric_kwh" (energy drawn from the tank and from the line or battery; for bev the electric figure is net of regeneration), "regen_kwh" (>= 0, bev only, else 0),
                 "source_kwh" (= diesel_kwh + electric_kwh), "kwh_per_t", "diesel_l_per_t_km", "co2e_kg_per_t" (each {"value": float | None, "basis": {"payload_t": payload, "road_km": km}}), "co2e_note" (str | None), "constants" ({name: {"value", "row_id" (str | None), "verified" (bool | None)}} for every constant used),
                 "unverified_rows" (sorted list of the row ids of used constants that are not verified)}.
        diesel: diesel_kwh = sum of E_w / eta_diesel over segments with E_w > 0, electric 0; trolley: E_w / eta_electric on trolley segments (electric_kwh) and E_w / eta_diesel elsewhere (diesel_kwh), nothing for E_w <= 0; bev: E_w / eta_drive for E_w > 0 and eta_regen x E_w for E_w < 0 in electric_kwh.
        `diesel_l_per_t_km` = diesel_kwh x 3.6e6 / fuel_energy_density x 1000 / (payload x road_km), None for bev; `co2e_kg_per_t` = (diesel m3 x diesel_co2_kg_per_m3 + electric J x grid intensity) / payload, with value None and a note when the electricity part needs a grid intensity that was not supplied.
    default_constants() -> dict      {name: {"value", "row_id", "verified"}} for the six names above, read from `minephys.knowledge` (the row ids are the module's choice; the values must equal `minephys.knowledge.get_value(row_id)` and `verified` its verification status).
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pitstudio.haulage import energy as energy_module
from pitstudio.haulage.energy import default_constants, route_energy
from pitstudio.haulage.errors import InvalidRouteInput

G0 = 9.80665
KWH = 3.6e6
SETTINGS = settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)
C = {
    "g": G0,
    "eta_diesel": 0.35,
    "eta_electric": 0.9,
    "eta_drive": 0.92,
    "eta_regen": 0.6,
    "fuel_energy_density_j_per_m3": 36e9,
    "diesel_co2_kg_per_m3": 10.21 / 3.785411784e-3,
}
TRUCK = {"empty_mass_t": 180.0, "payload_t": 220.0, "drivetrain": "diesel"}


def seg(length=1000.0, grade=0.0, rr=3.0, trolley=False):
    return {"length_m": length, "grade_pct": grade, "rr_pct": rr, "trolley": trolley}


def truck(drivetrain="diesel", empty=180.0, payload=220.0):
    return {"empty_mass_t": empty, "payload_t": payload, "drivetrain": drivetrain}


def run(route, drivetrain="diesel", leg="loaded", c=C, **kw):
    return route_energy(route, truck(drivetrain), leg=leg, constants=c, **kw)


def oracle(route, tr, leg, c, small_angle=True):
    """Independent plain-Python per-segment formulas (J): returns (wheel, diesel, electric, regen)."""
    mass = (tr["empty_mass_t"] + (tr["payload_t"] if leg == "loaded" else 0.0)) * 1000.0
    wheel = diesel = electric = regen = 0.0
    for s in route:
        grade = s["grade_pct"] / 100.0
        gr = grade if small_angle else math.sin(math.atan(grade))
        ew = mass * c["g"] * (s["rr_pct"] / 100.0 + gr) * s["length_m"]
        wheel += ew
        if tr["drivetrain"] == "diesel":
            diesel += ew / c["eta_diesel"] if ew > 0 else 0.0
        elif tr["drivetrain"] == "trolley":
            if ew > 0 and s["trolley"]:
                electric += ew / c["eta_electric"]
            elif ew > 0:
                diesel += ew / c["eta_diesel"]
        else:
            electric += ew / c["eta_drive"] if ew >= 0 else c["eta_regen"] * ew
            if ew < 0:
                regen += c["eta_regen"] * -ew
    return wheel, diesel, electric, regen


# ---------------------------------------------------------------------------------------------------------------------
# hand-calculated values
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-34")
def test_the_m06_worked_example_400_t_on_2_km_at_10_percent_with_3_percent_rr():
    r = run(
        [seg(2000.0, 10.0, 3.0)],
        c={"g": G0, "eta_diesel": 0.35, "fuel_energy_density_j_per_m3": 36e9, "diesel_co2_kg_per_m3": 2697.1967},
    )
    force_kn = 400_000.0 * G0 * 0.13 / 1e3
    assert force_kn == pytest.approx(
        510.12, rel=1e-3
    )  # the spec's 510.12 kN used g = 9.81; the knowledge-table g0 is 9.80665
    assert r["mass_t"] == 400.0 and r["wheel_kwh"] == pytest.approx(283.4, rel=1e-3)
    assert r["wheel_kwh"] == pytest.approx(400_000.0 * G0 * 0.13 * 2000.0 / KWH, rel=1e-12)
    lift = 400_000.0 * G0 * 200.0 / KWH  # m g dz with dz = 2000 m x 10 %
    assert lift == pytest.approx(218.0, rel=1e-3) and r["wheel_kwh"] >= lift


@pytest.mark.req("FR-007-34")
def test_the_minephys_published_values_for_a_3_km_leg_of_a_400_t_truck():
    r = run([seg(3000.0, 10.0, 2.0)])
    assert r["wheel_kwh"] == pytest.approx(
        392.266, rel=1e-6
    )  # segment_energy(400000, 3000, 0.02, 0.10, small_angle=True) = 1.4121576e9 J
    assert r["wheel_kwh"] * KWH == pytest.approx(1.4121576e9, rel=1e-7)
    assert (
        r["diesel_kwh"] == pytest.approx(392.266 / 0.35, rel=1e-6)
        and r["electric_kwh"] == 0.0
        and r["regen_kwh"] == 0.0
    )
    litres = r["diesel_kwh"] * KWH / 36e9 * 1000.0
    assert litres == pytest.approx(112.076, rel=1e-6)  # 0.112076 m3
    basis = {"payload_t": 220.0, "road_km": 3.0}
    assert r["diesel_l_per_t_km"] == {"value": pytest.approx(112.076 / (220.0 * 3.0), rel=1e-6), "basis": basis}
    assert r["kwh_per_t"] == {"value": pytest.approx(392.266 / 0.35 / 220.0, rel=1e-6), "basis": basis}
    assert (
        r["co2e_kg_per_t"]["value"] == pytest.approx(302.291 / 220.0, rel=1e-5) and r["co2e_kg_per_t"]["basis"] == basis
    )  # co2_from_diesel(0.112076) = 302.291 kg


@pytest.mark.req("FR-007-34")
def test_the_empty_leg_carries_only_the_empty_mass_and_the_basis_stays_the_payload():
    loaded = run([seg(1000.0, 5.0)], leg="loaded")
    empty = run([seg(1000.0, 5.0)], leg="empty")
    assert empty["mass_t"] == 180.0 and loaded["mass_t"] == 400.0
    assert empty["wheel_kwh"] == pytest.approx(180_000.0 * G0 * 0.08 * 1000.0 / KWH, rel=1e-12)
    assert empty["kwh_per_t"]["basis"]["payload_t"] == 220.0 and empty["kwh_per_t"]["basis"]["road_km"] == 1.0


@pytest.mark.req("FR-007-34")
def test_the_exact_grade_resistance_form_is_selectable():
    r = run([seg(3000.0, 10.0, 2.0)], small_angle=False)
    want = (
        400_000.0 * G0 * (0.02 + 0.0995037190209989) * 3000.0 / KWH
    )  # grade_resistance(0.10) = 0.0995037190209989 (minephys spec 7.4)
    assert r["wheel_kwh"] == pytest.approx(want, rel=1e-12)


@pytest.mark.req("FR-007-34")
def test_a_trolley_truck_draws_from_the_line_on_trolley_segments_and_nothing_on_descents():
    route = [
        seg(2000.0, 8.0, 2.0, True),
        seg(1000.0, 8.0, 2.0, False),
        seg(1500.0, -9.0, 2.0, True),
        seg(500.0, 0.0, 3.0, False),
    ]
    r = run(route, "trolley")
    wheel, diesel, electric, _r = oracle(route, truck("trolley"), "loaded", C)
    assert r["wheel_kwh"] == pytest.approx(wheel / KWH, rel=1e-12)
    assert r["electric_kwh"] == pytest.approx(electric / KWH, rel=1e-12) and r["diesel_kwh"] == pytest.approx(
        diesel / KWH, rel=1e-12
    )
    assert (
        r["regen_kwh"] == 0.0 and r["electric_kwh"] > 0 and r["diesel_kwh"] > 0
    )  # the 1.5 km descent draws nothing and regenerates nothing


@pytest.mark.req("FR-007-34")
def test_a_battery_truck_recovers_energy_on_descents():
    route = [seg(2000.0, 8.0, 2.0), seg(3000.0, -10.0, 2.0)]
    r = run(route, "bev")
    _w, _d, electric, regen = oracle(route, truck("bev"), "loaded", C)
    assert regen > 0 and r["regen_kwh"] == pytest.approx(regen / KWH, rel=1e-12)
    assert r["electric_kwh"] == pytest.approx(electric / KWH, rel=1e-12) and r["diesel_kwh"] == 0.0
    assert r["source_kwh"] == pytest.approx(r["electric_kwh"], rel=1e-12)
    assert r["diesel_l_per_t_km"]["value"] is None  # no diesel for a battery truck


@pytest.mark.req("FR-007-34")
def test_electricity_emissions_need_a_grid_intensity_and_have_no_default():
    route = [seg(2000.0, 8.0, 2.0, True), seg(1000.0, 0.0, 2.0, False)]
    no_grid = run(route, "trolley")
    assert no_grid["co2e_note"] and "grid" in no_grid["co2e_note"].lower()
    gi = 2.0e-7  # kg CO2 per J (0.72 kg/kWh)
    with_grid = run(route, "trolley", grid_intensity_kg_per_j=gi)
    _w, diesel, electric, _r = oracle(route, truck("trolley"), "loaded", C)
    want = (diesel / 36e9 * C["diesel_co2_kg_per_m3"] + electric * gi) / 220.0
    assert with_grid["co2e_kg_per_t"]["value"] == pytest.approx(want, rel=1e-12) and with_grid["co2e_note"] is None
    bev = run([seg(1000.0, 5.0)], "bev")
    assert bev["co2e_kg_per_t"]["value"] is None and bev["co2e_note"]


# ---------------------------------------------------------------------------------------------------------------------
# random routes against the independent oracle, and the relations of P-007-19
# ---------------------------------------------------------------------------------------------------------------------
segments = st.fixed_dictionaries(
    {
        "length_m": st.floats(5.0, 3000.0),
        "grade_pct": st.floats(-20.0, 20.0),
        "rr_pct": st.floats(0.5, 10.0),
        "trolley": st.booleans(),
    }
)
routes = st.lists(segments, min_size=1, max_size=200)
payloads = st.floats(50.0, 400.0)
drivetrains = st.sampled_from(["diesel", "trolley", "bev"])
legs = st.sampled_from(["loaded", "empty"])


@pytest.mark.req("FR-007-34")
@SETTINGS
@given(route=routes, payload=payloads, dt=drivetrains, leg=legs, small=st.booleans())
def test_random_routes_match_the_independent_per_segment_oracle(route, payload, dt, leg, small):
    tr = {"empty_mass_t": 150.0, "payload_t": payload, "drivetrain": dt}
    r = route_energy(route, tr, leg=leg, constants=C, small_angle=small)
    wheel, diesel, electric, regen = oracle(route, tr, leg, C, small)
    scale = sum(abs(x) for x in (wheel, diesel, electric)) / KWH + 1e-9
    tol = 1e-12 * scale
    assert r["wheel_kwh"] == pytest.approx(wheel / KWH, abs=tol)
    assert r["diesel_kwh"] == pytest.approx(diesel / KWH, abs=tol) and r["electric_kwh"] == pytest.approx(
        electric / KWH, abs=tol
    )
    assert r["regen_kwh"] == pytest.approx(regen / KWH, abs=tol) and r["source_kwh"] == pytest.approx(
        (diesel + electric) / KWH, abs=tol
    )
    km = sum(s["length_m"] for s in route) / 1000.0
    assert r["road_km"] == pytest.approx(km, rel=1e-12) and r["payload_t"] == payload
    assert all(math.isfinite(x) for x in (r["wheel_kwh"], r["diesel_kwh"], r["electric_kwh"], r["source_kwh"]))


@pytest.mark.req("P-007-19")
@SETTINGS
@given(route=routes, payload=payloads, dt=drivetrains, bump=st.floats(0.0, 5.0), idx=st.integers(0, 199))
def test_energy_is_non_decreasing_in_grade_rolling_resistance_and_payload(route, payload, dt, bump, idx):
    tr = {"empty_mass_t": 150.0, "payload_t": payload, "drivetrain": dt}
    base = route_energy(route, tr, leg="loaded", constants=C)["source_kwh"]
    steeper = [dict(s) for s in route]
    steeper[idx % len(route)]["grade_pct"] += bump
    rougher = [dict(s, rr_pct=s["rr_pct"] + bump) for s in route]
    heavier = {**tr, "payload_t": payload + bump}
    slack = 1e-12 * (abs(base) + 1.0)
    assert route_energy(steeper, tr, leg="loaded", constants=C)["source_kwh"] >= base - slack
    assert route_energy(rougher, tr, leg="loaded", constants=C)["source_kwh"] >= base - slack
    if (
        dt != "bev"
    ):  # with regeneration a heavier truck recovers more on a descent, so the net battery energy is not monotone in the payload (reported against P-007-19 (i))
        assert route_energy(route, heavier, leg="loaded", constants=C)["source_kwh"] >= base - slack


@pytest.mark.req("P-007-19")
@SETTINGS
@given(a=routes, b=routes, payload=payloads, dt=drivetrains, leg=legs)
def test_energy_is_additive_over_concatenated_routes(a, b, payload, dt, leg):
    tr = {"empty_mass_t": 150.0, "payload_t": payload, "drivetrain": dt}
    whole = route_energy(a + b, tr, leg=leg, constants=C)
    ra, rb = (route_energy(x, tr, leg=leg, constants=C) for x in (a, b))
    for key in ("wheel_kwh", "diesel_kwh", "electric_kwh", "regen_kwh", "source_kwh", "road_km"):
        tol = 1e-12 * (abs(ra[key]) + abs(rb[key]) + 1e-9)
        assert whole[key] == pytest.approx(ra[key] + rb[key], abs=tol), key


@pytest.mark.req("P-007-19")
@SETTINGS
@given(route=routes, payload=payloads, dt=drivetrains, leg=legs)
def test_the_wheel_energy_is_at_least_the_potential_energy_gained(route, payload, dt, leg):
    tr = {"empty_mass_t": 150.0, "payload_t": payload, "drivetrain": dt}
    r = route_energy(route, tr, leg=leg, constants=C)
    dz = sum(s["length_m"] * s["grade_pct"] / 100.0 for s in route)  # small-angle: dz = grade x L
    floor = r["mass_t"] * 1000.0 * G0 * dz / KWH
    assert r["wheel_kwh"] >= floor - 1e-12 * (abs(floor) + abs(r["wheel_kwh"]) + 1e-9)


@pytest.mark.req("P-007-19")
@SETTINGS
@given(route=routes, payload=payloads, k=st.floats(0.5, 2.0))
def test_diesel_co2_is_the_fuel_volume_times_the_factor(route, payload, k):
    tr = {"empty_mass_t": 150.0, "payload_t": payload, "drivetrain": "diesel"}
    r1 = route_energy(route, tr, leg="loaded", constants=C)
    r2 = route_energy(route, tr, leg="loaded", constants={**C, "diesel_co2_kg_per_m3": k * C["diesel_co2_kg_per_m3"]})
    fuel_m3 = r1["diesel_kwh"] * KWH / 36e9
    assert r1["co2e_kg_per_t"]["value"] == pytest.approx(
        fuel_m3 * C["diesel_co2_kg_per_m3"] / payload, rel=1e-12, abs=1e-12
    )
    assert r2["co2e_kg_per_t"]["value"] == pytest.approx(
        k * r1["co2e_kg_per_t"]["value"], rel=1e-12, abs=1e-12
    )  # linear in the factor
    assert r2["diesel_l_per_t_km"] == r1["diesel_l_per_t_km"]  # the factor does not touch the fuel


@pytest.mark.req("P-007-19")
@SETTINGS
@given(route=routes, payload=payloads, leg=legs)
def test_a_trolley_route_with_no_trolley_length_equals_diesel(route, payload, leg):
    off = [dict(s, trolley=False) for s in route]
    d = route_energy(off, {"empty_mass_t": 150.0, "payload_t": payload, "drivetrain": "diesel"}, leg=leg, constants=C)
    t = route_energy(off, {"empty_mass_t": 150.0, "payload_t": payload, "drivetrain": "trolley"}, leg=leg, constants=C)
    for key in ("wheel_kwh", "diesel_kwh", "electric_kwh", "source_kwh"):
        assert t[key] == pytest.approx(d[key], rel=1e-12, abs=1e-12), key
    for key in ("kwh_per_t", "diesel_l_per_t_km", "co2e_kg_per_t"):
        assert (
            t[key]["value"] == pytest.approx(d[key]["value"], rel=1e-12, abs=1e-12)
            and t[key]["basis"] == d[key]["basis"]
        ), key


@pytest.mark.req("P-007-19")
@SETTINGS
@given(route=routes, payload=payloads, leg=legs)
def test_regenerated_energy_is_bounded_by_the_descent_potential(route, payload, leg):
    tr = {"empty_mass_t": 150.0, "payload_t": payload, "drivetrain": "bev"}
    r = route_energy(route, tr, leg=leg, constants=C)
    m = r["mass_t"] * 1000.0
    bound = (
        sum(
            C["eta_regen"] * m * G0 * (-s["grade_pct"] / 100.0 - s["rr_pct"] / 100.0) * s["length_m"]
            for s in route
            if -s["grade_pct"] / 100.0 - s["rr_pct"] / 100.0 > 0
        )
        / KWH
    )
    assert 0.0 <= r["regen_kwh"] <= bound * (1 + 1e-12) + 1e-12
    assert r["regen_kwh"] == pytest.approx(
        bound, rel=1e-12, abs=1e-12
    )  # with the regeneration efficiency the bound is attained segment by segment


@pytest.mark.req("P-007-19")
@SETTINGS
@given(
    lengths=st.lists(st.floats(5.0, 3000.0), min_size=1, max_size=60),
    rr=st.floats(0.5, 10.0),
    payload=payloads,
    dt=drivetrains,
    leg=legs,
    trol=st.lists(st.booleans(), min_size=60, max_size=60),
)
def test_on_a_flat_road_the_way_there_costs_the_same_as_the_way_back(lengths, rr, payload, dt, leg, trol):
    forward = [seg(length, 0.0, rr, trol[i]) for i, length in enumerate(lengths)]
    back = [seg(s["length_m"], 0.0, rr, s["trolley"]) for s in reversed(forward)]
    tr = {"empty_mass_t": 150.0, "payload_t": payload, "drivetrain": dt}
    a, b = (route_energy(x, tr, leg=leg, constants=C) for x in (forward, back))
    for key in ("wheel_kwh", "diesel_kwh", "electric_kwh", "source_kwh"):
        assert a[key] == pytest.approx(b[key], rel=1e-12, abs=1e-12), key


@pytest.mark.req("P-007-19")
def test_reversing_a_sloped_route_swaps_the_sign_of_the_potential_term():
    route = [seg(2000.0, 6.0, 2.0), seg(1000.0, -3.0, 2.0)]
    back = [seg(s["length_m"], -s["grade_pct"], 2.0) for s in reversed(route)]
    a, b = run(route), run(back)
    dz = 2000.0 * 0.06 - 1000.0 * 0.03
    assert a["wheel_kwh"] - b["wheel_kwh"] == pytest.approx(2 * 400_000.0 * G0 * dz / KWH, rel=1e-12)


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-45: hostile inputs
# ---------------------------------------------------------------------------------------------------------------------
BAD = float("nan"), float("inf"), float("-inf")


def expect_rejected(field, value, route=None, tr=None, **kw):
    with pytest.raises(InvalidRouteInput) as ei:
        route_energy(route or [seg()], tr or truck(), leg=kw.pop("leg", "loaded"), constants=C, **kw)
    e = ei.value
    assert e.field == field and field in str(e) and repr(value) in str(e)
    return e


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize("bad", [*BAD, 0.0, -1.0, -1e-9])
def test_a_non_finite_or_non_positive_length_is_rejected_naming_the_field_and_value(bad):
    expect_rejected("length_m", bad, route=[seg(), seg(length=bad)])


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize("bad", BAD)
def test_a_non_finite_grade_or_rolling_resistance_is_rejected(bad):
    expect_rejected("grade_pct", bad, route=[seg(grade=bad)])
    expect_rejected("rr_pct", bad, route=[seg(rr=bad)])


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize("bad", [-0.5, -10.0])
def test_a_negative_rolling_resistance_is_rejected(bad):
    expect_rejected("rr_pct", bad, route=[seg(rr=bad)])


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize("field", ["empty_mass_t", "payload_t"])
@pytest.mark.parametrize("bad", [*BAD, 0.0, -1.0])
def test_a_non_finite_or_non_positive_mass_or_payload_is_rejected(field, bad):
    expect_rejected(field, bad, tr={**truck(), field: bad})


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize("bad", ["", "Diesel", "electric", "hybrid", "bev ", "ディーゼル", None, 3, "d" * 10_000])
def test_an_unknown_drivetrain_is_rejected(bad):
    with pytest.raises(InvalidRouteInput) as ei:
        route_energy([seg()], {**truck(), "drivetrain": bad}, leg="loaded", constants=C)
    assert (
        ei.value.field == "drivetrain" and len(str(ei.value)) < 1000
    )  # a huge value is truncated in the message, not echoed whole


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize("leg", ["", "Loaded", "both", None, 1])
def test_an_unknown_leg_is_rejected(leg):
    with pytest.raises(InvalidRouteInput) as ei:
        route_energy([seg()], truck(), leg=leg, constants=C)
    assert ei.value.field == "leg"


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize(
    ("route", "field"),
    [
        ([], "route"),
        (None, "route"),
        ("segment", "route"),
        ([{"length_m": 1.0, "grade_pct": 0.0, "rr_pct": 1.0}], "trolley"),  # a missing key
        ([{"grade_pct": 0.0, "rr_pct": 1.0, "trolley": False}], "length_m"),
        ([seg(trolley=1)], "trolley"),  # not a boolean
        ([seg(trolley="yes")], "trolley"),
        ([seg(length="100")], "length_m"),
        ([seg(length=True)], "length_m"),
        ([seg(grade=None)], "grade_pct"),
        ([None], "route"),
    ],
)
def test_a_malformed_route_is_rejected_naming_the_field(route, field):
    with pytest.raises(InvalidRouteInput) as ei:
        route_energy(route, truck(), leg="loaded", constants=C)
    assert ei.value.field == field


@pytest.mark.req("FR-007-45")
def test_more_than_100000_segments_are_rejected():
    with pytest.raises(InvalidRouteInput) as ei:
        route_energy([seg()] * 100_001, truck(), leg="loaded", constants=C)
    assert ei.value.field == "route"
    assert isinstance(route_energy([seg()] * 100_000, truck(), leg="loaded", constants=C)["wheel_kwh"], float)


@pytest.mark.req("FR-007-45")
def test_an_overflow_is_an_error_never_infinity_or_nan():
    huge = [seg(length=1e308, grade=20.0), seg(length=1e308, grade=20.0)]
    try:
        r = route_energy(huge, truck(), leg="loaded", constants=C)
    except InvalidRouteInput:
        return
    assert all(
        math.isfinite(v) for k, v in r.items() if isinstance(v, float)
    )  # if it returns at all, every number is finite


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize(
    ("name", "bad"),
    [
        ("g", 0.0),
        ("g", BAD[0]),
        ("eta_diesel", 0.0),
        ("eta_diesel", 1.5),
        ("eta_regen", -0.1),
        ("eta_regen", 1.1),
        ("fuel_energy_density_j_per_m3", 0.0),
        ("diesel_co2_kg_per_m3", -1.0),
        ("eta_drive", BAD[1]),
    ],
)
def test_non_physical_constants_are_rejected_naming_the_constant(name, bad):
    with pytest.raises(InvalidRouteInput) as ei:
        route_energy([seg()], truck(), leg="loaded", constants={**C, name: bad})
    assert ei.value.field == name


@pytest.mark.req("FR-007-45")
def test_a_rejected_input_leaves_the_route_untouched():
    route = [seg(), seg(length=-5.0)]
    snapshot = json.dumps(route)
    with pytest.raises(InvalidRouteInput):
        route_energy(route, truck(), leg="loaded", constants=C)
    assert json.dumps(route) == snapshot


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-40: constants only from the knowledge tables
# ---------------------------------------------------------------------------------------------------------------------
FORBIDDEN = [
    9.80665,
    9.81,
    9.8,
    9.807,
    2697.1967,
    2697.2,
    2697.0,
    10.21,
    3.785411784,
    3.785411784e-3,
    0.35,
    0.9,
    0.92,
    0.95,
    0.85,
    36e9,
    3.6e10,
    0.6,
    0.7,
    0.8,
]


def float_literals(path: Path) -> list[tuple[float, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [(n.value, n.lineno) for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, float)]


@pytest.mark.req("FR-007-40")
def test_the_energy_module_holds_no_physical_constant_literal_and_reads_minephys():
    path = Path(energy_module.__file__)
    hits = [(v, ln) for v, ln in float_literals(path) if any(math.isclose(v, f, rel_tol=1e-9) for f in FORBIDDEN)]
    assert hits == [], f"physical constants written as literals in {path.name}: {hits}"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {
        n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
    }
    assert "minephys" in imported


@pytest.mark.req("FR-007-40")
def test_the_default_constants_are_the_knowledge_table_values_with_their_verification_status():
    import minephys.knowledge as kn

    d = default_constants()
    assert {
        "g",
        "eta_diesel",
        "eta_electric",
        "eta_drive",
        "eta_regen",
        "fuel_energy_density_j_per_m3",
        "diesel_co2_kg_per_m3",
    } <= set(d)
    for name, entry in d.items():
        assert set(entry) >= {"value", "row_id", "verified"} and isinstance(entry["row_id"], str), name
        assert entry["verified"] == (kn.get_parameter(entry["row_id"]).verification == "verified"), name
    co2 = d["diesel_co2_kg_per_m3"]
    assert (
        co2["value"] == pytest.approx(kn.get_value("diesel_co2_kg_per_us_gal") / 3.785411784e-3, rel=1e-12)
        or co2["row_id"] != "diesel_co2_kg_per_us_gal"
    )


@pytest.mark.req("FR-007-40")
@pytest.mark.parametrize("dt", ["diesel", "trolley", "bev"])
def test_with_default_constants_every_used_row_is_reported_and_the_unverified_ones_are_listed(dt):
    import warnings

    import minephys.knowledge as kn

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the knowledge layer warns on UNVERIFIED model constants
        r = route_energy(
            [seg(2000.0, 6.0, 2.0, True), seg(1000.0, -4.0, 2.0)], truck(dt), leg="loaded", grid_intensity_kg_per_j=2e-7
        )
        used = r["constants"]
        assert used and all(isinstance(v["row_id"], str) for v in used.values())
        for name, v in used.items():
            assert v["value"] == pytest.approx(
                kn.get_value(v["row_id"]) if not name.startswith("diesel_co2") else v["value"], rel=1e-12
            ), name
            assert v["verified"] == (kn.get_parameter(v["row_id"]).verification == "verified"), name
        assert r["unverified_rows"] == sorted(v["row_id"] for v in used.values() if not v["verified"])
        assert len(set(r["unverified_rows"])) == len(r["unverified_rows"])
    assert r["wheel_kwh"] > 0


@pytest.mark.req("FR-007-40")
def test_explicit_constants_use_no_table_row_and_list_no_unverified_row():
    r = run([seg(2000.0, 6.0, 2.0)])
    assert r["unverified_rows"] == []
    assert all(v["row_id"] is None for v in r["constants"].values())
    assert {k: v["value"] for k, v in r["constants"].items()} == {k: C[k] for k in r["constants"]}


@pytest.mark.req("FR-007-40")
def test_a_partial_override_takes_the_missing_constants_from_the_tables():
    r = route_energy([seg(2000.0, 6.0, 2.0)], truck(), leg="loaded", constants={"g": G0, "eta_diesel": 0.4})
    assert r["constants"]["g"]["row_id"] is None and r["constants"]["eta_diesel"]["row_id"] is None
    assert (
        r["constants"]["fuel_energy_density_j_per_m3"]["row_id"] is not None
    )  # not overridden: from the knowledge table

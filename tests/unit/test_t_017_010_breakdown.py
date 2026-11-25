"""T-017-010 (D2 chain, stage values with their equations): `breakdown` of one design (unit).

Requirements: FR-017-01.

Oracles (hand calculations from the equations the rows cite, given the F80 the crusher stage reports):
- Kuznetsov: x50 = A K^-0.8 Q^(1/6) (115 / RWS)^(19/20) cm with Q = K B S H (the assumed RWS 100, UNVERIFIED);
- Bond: W = 10 W_i (1/sqrt(P80) - 1/sqrt(F80)) kWh/t with sizes in um, throughput = eta P_mill / W, cost =
  K c_explosive / 2.7 + c_energy W + c_consumables;
- every row carries a non-empty equation and source, and the last three rows equal the `run_chain` outputs exactly.
"""
# ruff: noqa: PT018

from __future__ import annotations

import math

import pytest
from pitstudio.cases.d2.chain import ASSUMPTIONS, breakdown, crusher_f80_um, rom_x80_m, run_chain

BASE = {
    "burden_m": 4.5,
    "spacing_ratio": 1.2,
    "powder_factor_kg_per_m3": 0.6,
    "hole_diameter_mm": 165.0,
    "bench_height_m": 12.0,
    "rock_factor": 8.0,
    "bond_work_index_kwh_per_t": 14.0,
    "crusher_css_mm": 100.0,
    "target_p80_um": 150.0,
    "mill_power_kw": 10_000.0,
    "efficiency": 1.0,
    "energy_cap_kwh_per_t": 20.0,
    "explosive_cost_usd_per_kg": 1.2,
    "energy_cost_usd_per_kwh": 0.08,
    "consumables_usd_per_t": 0.35,
}


def _row(rows, quantity):
    return next(r for r in rows if r["quantity"] == quantity)


@pytest.mark.req("FR-017-01")
def test_every_stage_value_has_an_equation_and_a_source() -> None:
    rows = breakdown(BASE)
    assert [r["stage"] for r in rows] == ["blast"] * 5 + ["crusher", "mill", "mill", "cost"]
    for r in rows:
        assert r["equation"] and r["source"] and r["unit"]
        assert math.isfinite(r["value"]) and r["value"] > 0


@pytest.mark.req("FR-017-01")
def test_the_blast_values_equal_the_hand_calculation() -> None:
    rows = breakdown(BASE)
    q = 0.6 * 4.5 * (1.2 * 4.5) * 12.0
    assert _row(rows, "charge per hole")["value"] == pytest.approx(q, rel=1e-12)
    x50 = 8.0 * 0.6**-0.8 * q ** (1 / 6) * (115.0 / 100.0) ** (19 / 20) / 100.0
    assert _row(rows, "Kuznetsov mean size x50")["value"] == pytest.approx(x50, rel=1e-12)
    assert _row(rows, "run-of-mine x80")["value"] > x50


@pytest.mark.req("FR-017-01")
def test_the_mill_and_cost_rows_follow_from_the_reported_f80_and_equal_the_chain_outputs() -> None:
    rows = breakdown(BASE)
    f80_um = _row(rows, "crusher product F80")["value"] * 1e6
    assert f80_um == pytest.approx(crusher_f80_um(BASE), rel=1e-12)
    kwh = 10.0 * 14.0 * (1.0 / math.sqrt(150.0) - 1.0 / math.sqrt(f80_um))
    assert _row(rows, "specific energy")["value"] == pytest.approx(kwh, rel=1e-9)
    assert _row(rows, "throughput")["value"] == pytest.approx(1.0 * 10_000.0 / kwh, rel=1e-9)
    cost = 0.6 * 1.2 / 2.7 + 0.08 * kwh + 0.35
    assert _row(rows, "cost per tonne")["value"] == pytest.approx(cost, rel=1e-9)
    result = run_chain(BASE)
    assert _row(rows, "specific energy")["value"] == result.kwh_per_t
    assert _row(rows, "throughput")["value"] == result.t_per_h
    assert _row(rows, "cost per tonne")["value"] == result.cost_per_t


@pytest.mark.req("FR-017-01")
def test_the_assumptions_are_listed_with_their_status() -> None:
    assert ASSUMPTIONS["rock_density_t_per_m3"] == {"value": 2.7, "unit": "t/m3", "status": "UNVERIFIED"}
    assert {a["status"] for a in ASSUMPTIONS.values()} <= {"UNVERIFIED", "chosen"}


@pytest.mark.req("FR-017-01")
def test_the_run_of_mine_x80_agrees_with_the_closed_form_swebrec_size_within_the_interpolation_bound() -> None:
    rows = breakdown(BASE)
    closed = _row(rows, "run-of-mine x80")["value"]  # swebrec_size at P = 0.8, closed form
    assert rom_x80_m(BASE) == pytest.approx(
        closed, rel=5e-3
    )  # log-log interpolation on 96 classes: measured 2.5e-3 here (minephys states 4.3e-4 on 400 classes)
    finer = rom_x80_m({**BASE, "powder_factor_kg_per_m3": 0.9})
    assert finer < rom_x80_m(BASE)  # more explosive, finer muck pile


@pytest.mark.req("FR-017-01")
def test_the_crusher_product_f80_does_not_follow_the_blast_when_the_css_governs() -> None:
    a, b = crusher_f80_um(BASE), crusher_f80_um({**BASE, "powder_factor_kg_per_m3": 0.9})
    assert abs(a - b) / a < 0.15
    assert crusher_f80_um({**BASE, "crusher_css_mm": 200.0}) > 1.5 * a

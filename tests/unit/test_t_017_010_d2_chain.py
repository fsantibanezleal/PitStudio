"""T-017-010: D2 chain composition and identities (unit, property).

Requirements: FR-017-01, P-017-17.

Spec: specs/017-planning-survey/spec.md
- FR-017-01: the D2 chain composes only `minephys` functions: Kuz-Ram / Swebrec run-of-mine size distribution
  (`minephys.blasting`) -> crusher classification-breakage -> F80 -> Bond (or Morrell) specific energy to the target P80
  (population-balance mill product, `minephys.comminution`) -> throughput t/h = eta P_mill / W -> cost/t from the
  documented unit costs, returning kWh/t, t/h and cost/t for the input vector of section 7;
- P-017-17: chain identities: t/h x kWh/t = eta P_mill; kWh/t is non-increasing in the target P80 and non-decreasing in
  W_i; the Bond term tends to 0 as P80 approaches F80 from below (tested at P80 = F80 (1 - eps), eps = 10^-9, against
  its first-order value 5 W_i eps / sqrt(F80), relative bound 1e-5 with P computed as the double F80 (1 - eps)).
plan.md test strategy row FR-017-01: Bond hand calculations of section 7 through the chain with the PBM and crusher in
pass-through configuration; t/h x kWh/t = eta P_mill.

Oracles (hand calculation of spec section 7, "Worked examples used as oracles"):
- Bond: W_i 14 kWh/t, F80 2,000 um, P80 150 um -> W = 10 W_i (1/sqrt(P80) - 1/sqrt(F80)) = 140 (1/sqrt(150) -
  1/sqrt(2000)) = 8.30 kWh/t; at 10 MW and eta = 1, 10,000 / 8.30046 = 1,204.8 t/h ("1,205 t/h");
- with F80 1,500 um: 7.82 kWh/t and 1,279 t/h;
- the identities of P-017-17 written out in the test; the first-order Bond limit 5 W_i eps / sqrt(F80);
- cost/t is linear in each unit cost (consumables enter with coefficient 1 USD per USD/t; the energy cost with
  coefficient kWh/t; the explosive cost with a coefficient independent of the cost level): checked by finite
  differences, because the absolute cost/t uses UNVERIFIED illustrative constants (spec section 7).

Expected public API (module `pitstudio.cases.d2.chain`, root environment, numpy + `minephys` only):
    INPUT_NAMES: tuple[str, ...]      # the section-7 input vector, in the unit-suffixed names of DC-017-01:
        burden_m, spacing_ratio, powder_factor_kg_per_m3, hole_diameter_mm, bench_height_m, rock_factor,
        bond_work_index_kwh_per_t, crusher_css_mm, target_p80_um, mill_power_kw, efficiency, energy_cap_kwh_per_t,
        explosive_cost_usd_per_kg, energy_cost_usd_per_kwh, consumables_usd_per_t
        (the Morrell variant replaces bond_work_index_kwh_per_t by morrell_index_kwh_per_t)
    @dataclass(frozen=True) ChainResult      # kwh_per_t, t_per_h, cost_per_t (floats)
    run_chain(inputs: Mapping[str, float], *, crusher: bool = True, pbm: bool = True,
              feed_f80_um: float | None = None) -> ChainResult
        crusher=False bypasses the blast and crusher stages (pass-through): F80 is `feed_f80_um`, which is then
        required; pbm=False bypasses the population-balance product (pass-through): the specific energy is the Bond
        (or Morrell) value to the target P80. Raises ValueError naming the offending key for an unknown input name,
        a missing input, a non-finite or non-positive value, and (pass-through) a target P80 >= the feed F80.
Only `minephys` (and numpy, the standard library) may be imported by the chain module.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.cases.d2.chain import INPUT_NAMES, ChainResult, run_chain

ROOT = Path(__file__).resolve().parents[2]
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


def _inputs(**over: float) -> dict[str, float]:
    return {**BASE, **over}


def _bond(w_i: float, f80: float, p80: float) -> float:
    return 10.0 * w_i * (1.0 / math.sqrt(p80) - 1.0 / math.sqrt(f80))


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-01
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-01")
def test_the_input_vector_is_the_section_7_vector() -> None:
    assert set(INPUT_NAMES) == set(BASE)
    assert len(INPUT_NAMES) == len(set(INPUT_NAMES)) == 15


@pytest.mark.req("FR-017-01")
def test_bond_worked_example_14_kwh_per_t_2000_to_150_um_is_8_30_kwh_per_t_and_1205_t_per_h() -> None:
    result = run_chain(_inputs(), crusher=False, pbm=False, feed_f80_um=2000.0)
    assert isinstance(result, ChainResult)
    assert result.kwh_per_t == pytest.approx(_bond(14.0, 2000.0, 150.0), rel=1e-12)
    assert result.kwh_per_t == pytest.approx(8.30, abs=0.005)  # the published rounding of the worked example
    assert result.t_per_h == pytest.approx(1205.0, abs=0.5)
    assert result.t_per_h == pytest.approx(10_000.0 / result.kwh_per_t, rel=1e-12)


@pytest.mark.req("FR-017-01")
def test_bond_worked_example_with_f80_1500_um_is_7_82_kwh_per_t_and_1279_t_per_h() -> None:
    result = run_chain(_inputs(), crusher=False, pbm=False, feed_f80_um=1500.0)
    assert result.kwh_per_t == pytest.approx(7.82, abs=0.005)
    assert result.t_per_h == pytest.approx(1279.0, abs=0.5)


@pytest.mark.req("FR-017-01")
def test_throughput_is_efficiency_times_mill_power_over_specific_energy() -> None:
    result = run_chain(_inputs(efficiency=0.85, mill_power_kw=8000.0), crusher=False, pbm=False, feed_f80_um=2000.0)
    assert result.t_per_h * result.kwh_per_t == pytest.approx(0.85 * 8000.0, rel=1e-12)


@pytest.mark.req("FR-017-01")
def test_the_full_chain_returns_three_finite_positive_outputs() -> None:
    result = run_chain(_inputs())
    for value in (result.kwh_per_t, result.t_per_h, result.cost_per_t):
        assert math.isfinite(value)
        assert value > 0


@pytest.mark.req("FR-017-01")
def test_cost_per_tonne_is_linear_in_each_unit_cost() -> None:
    kw = {"crusher": False, "pbm": False, "feed_f80_um": 2000.0}
    base = run_chain(_inputs(), **kw)
    cons = run_chain(_inputs(consumables_usd_per_t=0.35 + 0.5), **kw)
    assert cons.cost_per_t - base.cost_per_t == pytest.approx(0.5, rel=1e-9)  # one USD/t of consumables is one USD/t
    energy = run_chain(_inputs(energy_cost_usd_per_kwh=0.08 + 0.01), **kw)
    assert energy.cost_per_t - base.cost_per_t == pytest.approx(0.01 * base.kwh_per_t, rel=1e-9)
    e1 = run_chain(_inputs(explosive_cost_usd_per_kg=1.2 + 1.0), **kw).cost_per_t
    e2 = run_chain(_inputs(explosive_cost_usd_per_kg=1.2 + 2.0), **kw).cost_per_t
    assert (e2 - e1) == pytest.approx(e1 - base.cost_per_t, rel=1e-9)  # linear in the explosive cost


@pytest.mark.req("FR-017-01")
def test_the_chain_module_imports_only_minephys_numpy_and_the_standard_library() -> None:
    source = (ROOT / "src" / "pitstudio" / "cases" / "d2" / "chain.py").read_text(encoding="utf-8")
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    allowed = {"minephys", "numpy", "math", "dataclasses", "typing", "collections", "__future__"}
    assert roots - allowed == set()
    assert "minephys" in roots


@pytest.mark.req("FR-017-01")
@pytest.mark.parametrize(
    ("over", "name"),
    [
        ({"target_p80_um": float("nan")}, "target_p80_um"),
        ({"mill_power_kw": -1.0}, "mill_power_kw"),
        ({"efficiency": 0.0}, "efficiency"),
        ({"bond_work_index_kwh_per_t": float("inf")}, "bond_work_index_kwh_per_t"),
        ({"burden_m": 0.0}, "burden_m"),
    ],
)
def test_hostile_numeric_inputs_raise_value_error_naming_the_key(over: dict, name: str) -> None:
    with pytest.raises(ValueError, match=name):
        run_chain(_inputs(**over))


@pytest.mark.req("FR-017-01")
def test_unknown_and_missing_inputs_are_refused_naming_the_key() -> None:
    with pytest.raises(ValueError, match="bogus_input"):
        run_chain({**BASE, "bogus_input": 1.0})
    incomplete = dict(BASE)
    del incomplete["mill_power_kw"]
    with pytest.raises(ValueError, match="mill_power_kw"):
        run_chain(incomplete)


@pytest.mark.req("FR-017-01")
def test_pass_through_needs_the_feed_f80_and_a_target_below_it() -> None:
    with pytest.raises(ValueError, match="feed_f80_um"):
        run_chain(_inputs(), crusher=False, pbm=False)
    with pytest.raises(ValueError, match="target_p80_um"):
        run_chain(_inputs(target_p80_um=2000.0), crusher=False, pbm=False, feed_f80_um=2000.0)


# ----------------------------------------------------------------------------------------------------------------------
# P-017-17
# ----------------------------------------------------------------------------------------------------------------------

p80s = st.floats(min_value=75.0, max_value=300.0)
w_is = st.floats(min_value=8.0, max_value=25.0)
efficiencies = st.floats(min_value=0.05, max_value=1.0)
powers = st.floats(min_value=1_000.0, max_value=100_000.0)


@pytest.mark.req("P-017-17")
@settings(max_examples=200, deadline=None)
@given(p80=p80s, w_i=w_is, eta=efficiencies, power=powers)
def test_t_per_h_times_kwh_per_t_equals_eta_p_mill_for_the_full_chain(p80, w_i, eta, power):
    r = run_chain(_inputs(target_p80_um=p80, bond_work_index_kwh_per_t=w_i, efficiency=eta, mill_power_kw=power))
    assert r.t_per_h * r.kwh_per_t == pytest.approx(eta * power, rel=1e-12)


@pytest.mark.req("P-017-17")
@settings(max_examples=200, deadline=None)
@given(p80_a=p80s, p80_b=p80s, w_a=w_is, w_b=w_is)
def test_specific_energy_is_non_increasing_in_p80_and_non_decreasing_in_w_i(p80_a, p80_b, w_a, w_b):
    lo, hi = sorted((p80_a, p80_b))
    e_lo = run_chain(_inputs(target_p80_um=lo)).kwh_per_t
    e_hi = run_chain(_inputs(target_p80_um=hi)).kwh_per_t
    assert e_hi <= e_lo  # a coarser product needs less energy
    wl, wh = sorted((w_a, w_b))
    assert (
        run_chain(_inputs(bond_work_index_kwh_per_t=wl)).kwh_per_t
        <= run_chain(_inputs(bond_work_index_kwh_per_t=wh)).kwh_per_t
    )


@pytest.mark.req("P-017-17")
@settings(max_examples=200, deadline=None)
@given(w_i=w_is, f80=st.floats(min_value=500.0, max_value=20_000.0))
def test_the_bond_term_tends_to_its_first_order_limit_as_p80_approaches_f80(w_i, f80):
    eps = 1e-9
    p80 = f80 * (1.0 - eps)  # the double F80 (1 - eps)
    kwh = run_chain(
        _inputs(bond_work_index_kwh_per_t=w_i, target_p80_um=p80), crusher=False, pbm=False, feed_f80_um=f80
    ).kwh_per_t
    first_order = 5.0 * w_i * eps / math.sqrt(f80)
    assert abs(kwh - first_order) <= 1e-5 * first_order


@pytest.mark.req("P-017-17")
def test_the_bond_term_is_positive_and_small_just_below_f80() -> None:
    kwh = run_chain(_inputs(target_p80_um=1999.99), crusher=False, pbm=False, feed_f80_um=2000.0).kwh_per_t
    assert 0 < kwh < 1e-3

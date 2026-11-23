"""T-017-063: the D2 run: sweeps, Sobol indices, summary and chart-series of the recipe parameters (unit, contract).

Requirements: FR-017-01, FR-017-02, DC-017-01, DC-020-05.

The recipe `studio/recipes/cases/d2.yaml` is the parameter source (so a recipe that the code cannot run fails here); the
sizes are reduced (10 configurations x 8 designs, N = 64) to keep the test short, everything else is the recipe's.

Oracles:
- the DC-017-01 schema and the chart-series schema (`jsonschema`), the latter through `chartkit.problems`;
- an input the chain ignores (`energy_cap_kwh_per_t`: the cap is used by the meta-model optimisation, not by the chain)
  has Sobol first-order and total index exactly 0, because f(AB_i) = f(A) bit for bit;
- the headline KPIs equal `run_chain` of the reference design (the chain is tested in T-017-010);
- determinism in the seeds, the chart ids of the recipe outputs, and the honesty facts every chart carries (producer
  tool, method, version, label).
"""
# ruff: noqa: PT018

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from pitstudio.cases.d2.chain import run_chain
from pitstudio_pipeline import chartkit
from pitstudio_pipeline.mine_to_mill import d2_run

ROOT = Path(__file__).resolve().parents[2]
RECIPE = yaml.safe_load((ROOT / "studio/recipes/cases/d2.yaml").read_text(encoding="utf-8"))
STAGE = RECIPE["stages"][0]
SWEEP_SCHEMA = json.loads((ROOT / "contracts/comminution-sweep.schema.json").read_text(encoding="utf-8"))


def _params() -> dict:
    p = copy.deepcopy(STAGE["params"])
    p.update(n_configurations=10, points_per_configuration=8, split={"train": 7, "validation": 1, "held_out": 2})
    p["sobol"].update(n_base=64, n_bootstrap=10)
    return p


@pytest.fixture(scope="module")
def result() -> dict:
    return d2_run.compute(_params())


@pytest.mark.req("FR-017-02")
def test_the_recipe_outputs_are_exactly_the_files_the_run_writes(result, tmp_path) -> None:
    written = d2_run.write_outputs(result, tmp_path)
    assert sorted(p.relative_to(tmp_path).as_posix() for p in written) == sorted(o["path"] for o in STAGE["outputs"])
    assert {o["path"] for o in STAGE["outputs"] if o.get("publish")} == {
        p.relative_to(tmp_path).as_posix() for p in written if p.name != "sweeps.json" and p.name != "sensitivity.json"
    }


@pytest.mark.req("DC-017-01")
def test_the_sweep_document_validates_and_carries_the_unverified_rows(result) -> None:
    doc = result["sweeps"]
    assert list(Draft202012Validator(SWEEP_SCHEMA).iter_errors(doc)) == []
    assert doc["unverified_rows"] == sorted({v["row"] for v in STAGE["params"]["box"].values()})
    assert sum(len(c["points"]) for c in doc["configurations"]) == 80
    assert {c["split"] for c in doc["configurations"]} == {"train", "validation", "held-out"}


@pytest.mark.req("DC-020-05")
def test_every_chart_is_valid_and_carries_its_producer_and_label(result) -> None:
    ids = [c["id"] for c in result["charts"]]
    assert ids == [Path(o["path"]).stem for o in STAGE["outputs"] if o["path"].startswith("charts/")]
    for chart in result["charts"]:
        assert chartkit.problems(chart) == [], chart["id"]
        assert chart["case"] == "D2" and chart["status"] == "ok"
        prod = chart["producer"]
        assert prod["tool"] == "minephys" and "Bond" in prod["method"]
        assert prod["version"].startswith("0.") and "+g98d5b25" in prod["version"]
        assert prod["label"] == "calibrated synthetic, not validated against real data"
        assert set(chart["serves"]) <= {"FR-017-01", "FR-017-02"}


@pytest.mark.req("FR-017-01")
def test_the_summary_kpis_are_the_chain_outputs_of_the_reference_design(result) -> None:
    chain = run_chain(STAGE["params"]["reference_design"])
    head = {h["kpi"]: h for h in result["summary"]["headline"]}
    assert head["mill_throughput"]["value"] == pytest.approx(chain.t_per_h, abs=5e-5)
    assert head["specific_energy"]["value"] == pytest.approx(chain.kwh_per_t, abs=5e-5)
    assert head["cost_per_tonne"]["value"] == pytest.approx(chain.cost_per_t, abs=5e-5)
    assert (head["mill_throughput"]["unit"], head["specific_energy"]["unit"], head["cost_per_tonne"]["unit"]) == (
        "t/h",
        "kWh/t",
        "USD/t",
    )
    assert result["summary"]["extra"]["assumptions"]["rock_density_t_per_m3"]["status"] == "UNVERIFIED"
    assert result["summary"]["label"] == "calibrated synthetic, not validated against real data"


@pytest.mark.req("FR-017-02")
def test_an_input_the_chain_ignores_has_exactly_zero_sobol_indices(result) -> None:
    s = result["sensitivity"]
    i = s["names"].index("energy_cap_kwh_per_t")
    assert s["first_order"][i] == [0.0, 0.0, 0.0]
    assert s["total"][i] == [0.0, 0.0, 0.0]
    j = s["names"].index("target_p80_um")
    assert s["total"][j][0] > s["total"][i][0]
    assert s["n_evaluations"] == 64 * (15 + 2)


@pytest.mark.req("FR-017-02")
def test_the_run_is_deterministic_for_its_seeds() -> None:
    a, b = d2_run.compute(_params()), d2_run.compute(_params())
    assert json.dumps(a["sweeps"], sort_keys=True) == json.dumps(b["sweeps"], sort_keys=True)
    assert json.dumps(a["sensitivity"], sort_keys=True) == json.dumps(b["sensitivity"], sort_keys=True)
    assert json.dumps(a["charts"], sort_keys=True) == json.dumps(b["charts"], sort_keys=True)


@pytest.mark.req("FR-017-10")
def test_a_box_whose_target_p80_reaches_the_smallest_feed_f80_is_refused_before_any_sweep() -> None:
    p = _params()
    p["box"]["target_p80_um"]["max"] = 1.0e6
    with pytest.raises(ValueError, match="target_p80_um"):
        d2_run.compute(p)


@pytest.mark.req("DC-020-05")
def test_chartkit_refuses_a_chart_over_the_cap_and_one_that_breaks_the_contract() -> None:
    prod = chartkit.producer("minephys", "m", "1.0", "l")
    ok = chartkit.chart(
        "c",
        "D2",
        "line",
        chartkit.bi("t", "t"),
        prod,
        ["FR-017-01"],
        x_axis=chartkit.axis("x", "x", "um"),
        y_axis=chartkit.axis("y", "y", "kWh/t"),
        series=[chartkit.series("s", chartkit.bi("s", "s"), [1, 2, 3], [1, 2, 3])],
    )
    assert chartkit.problems(ok) == []
    backwards = copy.deepcopy(ok)
    backwards["series"][0]["x"] = [3.0, 2.0, 1.0]
    assert any("backwards" in x for x in chartkit.problems(backwards))
    wrong = copy.deepcopy(ok)
    wrong["case"] = "Z9"
    assert chartkit.problems(wrong)
    big = copy.deepcopy(ok)
    big["series"][0] = chartkit.series("s", chartkit.bi("s", "s"), range(20000), [0.123456789] * 20000)
    big["series"].append(chartkit.series("t", chartkit.bi("t", "t"), range(20000), [0.123456789] * 20000))
    assert any("cap" in x for x in chartkit.problems(big))

"""T-017-033: E1 KPIs and the shell / schedule hand-off contract (contract).

Requirements: FR-017-21, FR-017-22.

Spec: specs/017-planning-survey/spec.md
- FR-017-21: `s50_evaluate` reports for E1 the pit value, the NPV of the schedule, the strip ratio of the pit and
  of every
  pushback (total and incremental), the tonnage per period, and hands the per-period mined units to the routing of
  spec
  007 for haul km and lift per period;
- FR-017-22: the shells, pushbacks and schedule are written per `pit-shells.schema.json` for `st20_pit_design`
  (spec 004)
  and the web E1 tabs.
plan.md test strategy rows FR-017-21 / FR-017-22: strip ratios and NPV by hand on a fixture; DC-017-03 validation
(`jsonschema`).

Oracles:
- the spec's own four-block example `contracts/examples/pit-shells.valid.json` and `pit-shells.valid-infeasible.json`
  (valid DC-017-03 documents written by the spec author, hand-checked: pit value 200 cents = 2 USD, strip ratio
  3,000 /
  1,000 = 3.0, NPV -3 / 1.1 + 5 / 1.21 = 1.404959 USD, mined tonnage 3,000 t and 1,000 t, ore 0 and 1,000 t);
- the promoted schema `contracts/pit-shells.schema.json` validated with `jsonschema` (the documents the code assembles
  must be valid and must reproduce the example exactly when fed its parts);
- hostile assemblies written by hand (a schedule naming a unit that is not in `units`, a pushback naming a shell that
  does not exist, a block count that disagrees with the bitset).

Expected public API (module `pitstudio.planning.outputs`, root environment, pure Python):
    e1_kpis(doc: Mapping) -> dict
        {"pit_value_usd": ultimate_pit.value_cents / 100, "npv_usd": schedule.npv_usd (None when not solved),
         "strip_ratio_pit": ultimate_pit.strip_ratio,
         "pushbacks": [{"shell", "ore_t", "waste_t", "strip_ratio_incremental", "strip_ratio_cumulative"}],
         "tonnage_per_period": [{"t", "mined_t", "ore_t"}] ([] when the schedule has no periods)}
    routing_handoff(doc: Mapping) -> list[dict]
        [{"t": period, "units": [{"id", "pushback", "bench", "ore_t", "waste_t"}]}] in period order: the mined
        units of
        each period with their pushback and bench (the input of the spec 007 routing); ValueError when a period
        names a
        unit that is not in `doc["units"]`.
    assemble_pit_shells(*, block_model: Mapping, licence: Mapping, config: Mapping, shells: Sequence[Mapping],
                        ultimate_pit: Mapping, pushbacks: Sequence[Mapping], units: Sequence[Mapping],
                        schedule: Mapping) -> dict
        the DC-017-03 document (`schema_version` "1.0", `block_set_encoding` "bitset-lsb0-base64"); ValueError for the
        hostile cases above (unknown unit in a period, unknown shell index in a pushback or the ultimate pit, a
        `block_count` that differs from the number of set bits of `blocks`, a `block_count` above
        `block_model["n_blocks"]`).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pitstudio.planning.outputs import assemble_pit_shells, e1_kpis, routing_handoff

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs/017-planning-survey/contracts/examples"
SCHEMA = json.loads((ROOT / "contracts" / "pit-shells.schema.json").read_text("utf-8"))


def _load(name: str) -> dict:
    return json.loads((EX / name).read_text("utf-8"))


def _errors(doc: dict) -> list:
    from jsonschema import Draft202012Validator

    return list(Draft202012Validator(SCHEMA).iter_errors(doc))


def _parts(doc: dict) -> dict:
    return {
        "block_model": doc["block_model"],
        "licence": doc["licence"],
        "config": doc["config"],
        "shells": doc["shells"],
        "ultimate_pit": doc["ultimate_pit"],
        "pushbacks": doc["pushbacks"],
        "units": doc["units"],
        "schedule": doc["schedule"],
    }


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-22
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-22")
def test_the_spec_examples_are_valid_dc_017_03_documents() -> None:
    assert _errors(_load("pit-shells.valid.json")) == []
    assert _errors(_load("pit-shells.valid-infeasible.json")) == []


@pytest.mark.req("FR-017-22")
def test_assembling_the_parts_of_the_example_gives_the_example_and_a_valid_document() -> None:
    example = _load("pit-shells.valid.json")
    doc = assemble_pit_shells(**_parts(example))
    assert doc == example
    assert _errors(doc) == []
    assert doc["schema_version"] == "1.0"
    assert doc["block_set_encoding"] == "bitset-lsb0-base64"


@pytest.mark.req("FR-017-22")
def test_the_infeasible_example_assembles_to_itself() -> None:
    example = _load("pit-shells.valid-infeasible.json")
    assert assemble_pit_shells(**_parts(example)) == example


@pytest.mark.req("FR-017-22")
def test_a_schedule_period_naming_an_unknown_unit_is_refused() -> None:
    parts = _parts(_load("pit-shells.valid.json"))
    parts["schedule"] = copy.deepcopy(parts["schedule"])
    parts["schedule"]["periods"][0]["units"] = [0, 99]
    with pytest.raises(ValueError, match="unit"):
        assemble_pit_shells(**parts)


@pytest.mark.req("FR-017-22")
@pytest.mark.parametrize("shell", [2, 7, -1])
def test_a_pushback_or_ultimate_pit_naming_an_unknown_shell_is_refused(shell: int) -> None:
    parts = _parts(_load("pit-shells.valid.json"))
    parts["pushbacks"] = [{**parts["pushbacks"][0], "shell": shell}]
    with pytest.raises(ValueError, match="shell"):
        assemble_pit_shells(**parts)
    parts = _parts(_load("pit-shells.valid.json"))
    parts["ultimate_pit"] = {**parts["ultimate_pit"], "shell": shell}
    with pytest.raises(ValueError, match="shell"):
        assemble_pit_shells(**parts)


@pytest.mark.req("FR-017-22")
def test_a_block_count_that_disagrees_with_the_bitset_or_the_model_is_refused() -> None:
    parts = _parts(_load("pit-shells.valid.json"))
    parts["shells"] = copy.deepcopy(parts["shells"])
    parts["shells"][1]["block_count"] = 3  # the bitset "Dw==" has 4 bits set
    with pytest.raises(ValueError, match="block_count"):
        assemble_pit_shells(**parts)
    parts = _parts(_load("pit-shells.valid.json"))
    parts["block_model"] = {**parts["block_model"], "n_blocks": 3}
    with pytest.raises(ValueError, match="block_count"):
        assemble_pit_shells(**parts)


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-21
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-21")
def test_the_kpis_of_the_four_block_example_by_hand() -> None:
    kpis = e1_kpis(_load("pit-shells.valid.json"))
    assert kpis["pit_value_usd"] == 2.0  # 200 cents
    assert kpis["npv_usd"] == pytest.approx(1.404959, abs=1e-6)
    assert kpis["npv_usd"] == pytest.approx(-3 / 1.1 + 5 / 1.21, abs=1e-6)
    assert kpis["strip_ratio_pit"] == 3.0  # 3,000 t waste over 1,000 t ore
    assert kpis["pushbacks"] == [
        {
            "shell": 1,
            "ore_t": 1000.0,
            "waste_t": 3000.0,
            "strip_ratio_incremental": 3.0,
            "strip_ratio_cumulative": 3.0,
        }
    ]
    assert kpis["tonnage_per_period"] == [
        {"t": 1, "mined_t": 3000.0, "ore_t": 0.0},
        {"t": 2, "mined_t": 1000.0, "ore_t": 1000.0},
    ]


@pytest.mark.req("FR-017-21")
def test_the_kpis_of_an_unsolved_schedule_have_no_npv_and_no_periods() -> None:
    kpis = e1_kpis(_load("pit-shells.valid-infeasible.json"))
    assert kpis["npv_usd"] is None
    assert kpis["tonnage_per_period"] == []


@pytest.mark.req("FR-017-21")
def test_the_routing_handoff_lists_the_mined_units_of_each_period_in_order() -> None:
    handoff = routing_handoff(_load("pit-shells.valid.json"))
    assert handoff == [
        {
            "t": 1,
            "units": [{"id": 0, "pushback": 0, "bench": 1, "ore_t": 0.0, "waste_t": 3000.0}],
        },
        {
            "t": 2,
            "units": [{"id": 1, "pushback": 0, "bench": 0, "ore_t": 1000.0, "waste_t": 0.0}],
        },
    ]
    assert sorted(u["id"] for p in handoff for u in p["units"]) == [0, 1]  # every mined unit is handed over once


@pytest.mark.req("FR-017-21")
def test_the_routing_handoff_refuses_a_period_naming_an_unknown_unit() -> None:
    doc = copy.deepcopy(_load("pit-shells.valid.json"))
    doc["schedule"]["periods"][1]["units"] = [5]
    with pytest.raises(ValueError, match="unit"):
        routing_handoff(doc)


@pytest.mark.req("FR-017-21")
def test_the_routing_handoff_of_an_unsolved_schedule_is_empty() -> None:
    assert routing_handoff(_load("pit-shells.valid-infeasible.json")) == []

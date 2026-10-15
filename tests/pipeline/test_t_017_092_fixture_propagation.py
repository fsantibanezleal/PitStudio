"""T-017-092: fixture propagation through the planning and survey stages (pipeline, hostile).

Requirements: FR-017-52.

Spec: specs/017-planning-survey/spec.md FR-017-52: while a block model, a flight record or a sweep (DC-017-01,
DC-017-02,
DC-017-05) is a contract fixture, the planning, survey and meta-model stages run against it, write `fixture: true`
on every
shell set, schedule, surface, volume and report, and publish no E1, E2 or D2 number computed from it. plan.md test
strategy
row FR-017-52: a fixture block model gives shells and a schedule `fixture: true` and the publish step drops them.

Oracles: hand calculation (a fixture input gives exactly the non-fixture output plus the key `fixture: true`; a
non-fixture
run adds no key; the publication filter keeps exactly the documents and volumes without the flag); the spec's own
examples
(`pit-shells.valid.json`, `survey-volume.valid.json`) as the base documents; the promoted schemas, which must
declare the
optional boolean `fixture` (their draft versions reject unknown properties, so FR-017-52 needs the property in the
contract;
the same approach as FR-016-40).

Expected public API (root environment, pure Python):
module `pitstudio.planning.fixtures`
    is_fixture(*docs: Mapping) -> bool                       # True iff any document has `fixture is True`
    propagate_fixture(output: Mapping, *inputs: Mapping) -> dict
        a copy of `output` with `"fixture": True` when any input is a fixture, else an unchanged copy (no key added)
module `pitstudio.planning.publish`
    publishable(docs: Sequence[Mapping]) -> list[dict]
        drops every document with `fixture: true`; a survey-volume document ({"volumes": [...]}) keeps only its
        volumes
        without the flag and is dropped when none remain; the input is not modified; order is kept
extensions of earlier APIs (each stage takes a keyword `fixture: bool = False`, adds `fixture: true` only when true):
    pitstudio.planning.outputs.assemble_pit_shells(..., fixture=...)
    (tests/contract/test_t_017_033_e1_outputs.py)
    pitstudio.survey.report.survey_row(..., fixture=...)
    (tests/pipeline/test_t_017_047_survey_report.py)
    pitstudio_pipeline.mine_to_mill.sweeps.generate_sweeps(design, *, chain, fixture=...)   (T-017-011)
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest
from pitstudio.planning.fixtures import is_fixture, propagate_fixture
from pitstudio.planning.outputs import assemble_pit_shells
from pitstudio.planning.publish import publishable
from pitstudio.survey.report import survey_row

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs/017-planning-survey/contracts/examples"
SHELLS = json.loads((EX / "pit-shells.valid.json").read_text("utf-8"))
VOLUMES = json.loads((EX / "survey-volume.valid.json").read_text("utf-8"))
SYNTHETIC = VOLUMES["volumes"][1]


def _schema(name: str) -> dict:
    return json.loads((ROOT / "contracts" / name).read_text("utf-8"))


def _errors(schema_name: str, doc: dict) -> list:
    from jsonschema import Draft202012Validator

    return list(Draft202012Validator(_schema(schema_name)).iter_errors(doc))


def _parts() -> dict:
    return {
        k: SHELLS[k]
        for k in ("block_model", "licence", "config", "shells", "ultimate_pit", "pushbacks", "units", "schedule")
    }


def _row(**over) -> dict:
    args = {
        "flight": "f01", "seed": 0, "method": "photogrammetric", "v_fill_m3": 9605.0, "v_cut_m3": 11880.0,
        "truth": {"fill": 9470.0, "cut": 11900.0}, "floor": {"fill_pct": 0.05, "cut_pct": -0.04},
        "reprojection_rmse_px": 0.61, "alignment_residuals": np.array([[0.01, 0.0, 0.0]] * 4),
        "depth_predicted": np.array([1.0, 2.0]), "depth_rendered": np.array([1.03, 2.03]), "gsd_cm_per_px": 2.0,
        "n_registered": 29, "n_total": 30, "base": SYNTHETIC,
    }  # fmt: skip
    args.update(over)
    return survey_row(**args)


# ----------------------------------------------------------------------------------------------------------------------
# the contract carries the flag
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-52")
def test_the_promoted_schemas_declare_the_optional_boolean_fixture_property() -> None:
    shells = _schema("pit-shells.schema.json")["properties"]
    sweep = _schema("comminution-sweep.schema.json")["properties"]
    block_model = _schema("block-model.schema.json")["properties"]
    flight = _schema("survey-flight.schema.json")["properties"]
    volume = _schema("survey-volume.schema.json")
    volume_item = volume["$defs"]["volume"]["properties"] if "volume" in volume["$defs"] else None
    for name, props in (("pit-shells", shells), ("comminution-sweep", sweep), ("block-model", block_model),
                        ("survey-flight", flight), ("survey-volume item", volume_item)):  # fmt: skip
        assert props is not None, name
        assert props.get("fixture") == {"type": "boolean"} or props.get("fixture", {}).get("const") is True, name


# ----------------------------------------------------------------------------------------------------------------------
# propagation
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-52")
def test_is_fixture_and_propagate_fixture_by_hand() -> None:
    assert is_fixture({"fixture": True}) is True
    assert is_fixture({"fixture": False}, {"a": 1}) is False
    assert is_fixture() is False
    assert is_fixture({"fixture": "yes"}) is False  # only the boolean true counts
    out = {"x": 1}
    assert propagate_fixture(out, {"fixture": True}) == {"x": 1, "fixture": True}
    assert propagate_fixture(out, {"y": 2}) == {"x": 1}
    assert out == {"x": 1}  # the output mapping is not modified


@pytest.mark.req("FR-017-52")
def test_a_fixture_block_model_gives_shells_and_a_schedule_marked_fixture() -> None:
    real = assemble_pit_shells(**_parts(), fixture=False)
    fixture = assemble_pit_shells(**_parts(), fixture=True)
    assert "fixture" not in real
    assert fixture["fixture"] is True
    assert {k: v for k, v in fixture.items() if k != "fixture"} == real
    assert fixture["schedule"] == real["schedule"]  # the schedule travels inside the flagged document
    assert _errors("pit-shells.schema.json", real) == []
    assert _errors("pit-shells.schema.json", fixture) == []


@pytest.mark.req("FR-017-52")
def test_a_fixture_flight_gives_a_survey_volume_marked_fixture() -> None:
    real, fixture = _row(), _row(fixture=True)
    assert "fixture" not in real
    assert fixture["fixture"] is True
    assert {k: v for k, v in fixture.items() if k != "fixture"} == real
    assert _errors("survey-volume.schema.json", {"schema_version": "1.0", "volumes": [fixture]}) == []


# ----------------------------------------------------------------------------------------------------------------------
# publication
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-52")
def test_the_publication_filter_drops_every_fixture_document_and_keeps_the_rest_in_order() -> None:
    real_shells = assemble_pit_shells(**_parts())
    fixture_shells = assemble_pit_shells(**_parts(), fixture=True)
    sweep_fixture = {"schema_version": "1.0", "fixture": True, "synthetic": True}
    docs = [real_shells, fixture_shells, sweep_fixture, {"schema_version": "1.0", "synthetic": True}]
    kept = publishable(docs)
    assert kept == [real_shells, {"schema_version": "1.0", "synthetic": True}]
    assert docs[1] is fixture_shells  # the input list is untouched


@pytest.mark.req("FR-017-52")
def test_a_volume_document_keeps_only_its_real_volumes_and_vanishes_when_none_remain() -> None:
    real, fixture = _row(), _row(flight="f02", fixture=True)
    mixed = {"schema_version": "1.0", "volumes": [real, fixture, VOLUMES["volumes"][0]]}
    (kept,) = publishable([mixed])
    assert [v["id"] for v in kept["volumes"]] == [real["id"], VOLUMES["volumes"][0]["id"]]
    only_fixture = {"schema_version": "1.0", "volumes": [fixture]}
    assert publishable([only_fixture]) == []
    assert mixed["volumes"][1] is fixture  # not modified


@pytest.mark.req("FR-017-52")
def test_nothing_published_contains_a_fixture_flag_or_a_number_derived_from_one() -> None:
    docs = [
        assemble_pit_shells(**_parts(), fixture=True),
        {"schema_version": "1.0", "volumes": [_row(fixture=True), _row()]},
    ]
    published = publishable(copy.deepcopy(docs))
    text = json.dumps(published)
    assert '"fixture"' not in text
    assert len(published) == 1
    assert [v["id"] for v in published[0]["volumes"]] == ["f01-s0-photogrammetric"]

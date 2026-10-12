"""T-017-001: planning and survey contract schemas and generated types.

Requirements: DC-017-01, DC-017-02, DC-017-03, DC-017-04, DC-017-05.

Spec: specs/017-planning-survey/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/comminution-sweep.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/comminution-sweep.schema.json)
- `contracts/block-model.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/block-model.schema.json)
- `contracts/pit-shells.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/pit-shells.schema.json)
- `contracts/survey-volume.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/survey-volume.schema.json)
- `contracts/survey-flight.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/survey-flight.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "017-planning-survey"


@pytest.mark.req("DC-017-01")
def test_comminution_sweep_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("comminution-sweep.schema.json")


@pytest.mark.req("DC-017-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["comminution-sweep.schema.json"], valid=True))
def test_comminution_sweep_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-017-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["comminution-sweep.schema.json"], valid=False))
def test_comminution_sweep_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-017-01")
def test_comminution_sweep_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["comminution-sweep.schema.json"])


@pytest.mark.req("DC-017-01")
def test_comminution_sweep_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["comminution-sweep.schema.json"])


@pytest.mark.req("DC-017-02")
def test_block_model_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("block-model.schema.json")


@pytest.mark.req("DC-017-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["block-model.schema.json"], valid=True))
def test_block_model_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-017-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["block-model.schema.json"], valid=False))
def test_block_model_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-017-02")
def test_block_model_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["block-model.schema.json"])


@pytest.mark.req("DC-017-02")
def test_block_model_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["block-model.schema.json"])


@pytest.mark.req("DC-017-03")
def test_pit_shells_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("pit-shells.schema.json")


@pytest.mark.req("DC-017-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["pit-shells.schema.json"], valid=True))
def test_pit_shells_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-017-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["pit-shells.schema.json"], valid=False))
def test_pit_shells_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-017-03")
def test_pit_shells_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["pit-shells.schema.json"])


@pytest.mark.req("DC-017-03")
def test_pit_shells_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["pit-shells.schema.json"])


@pytest.mark.req("DC-017-04")
def test_survey_volume_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("survey-volume.schema.json")


@pytest.mark.req("DC-017-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["survey-volume.schema.json"], valid=True))
def test_survey_volume_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-017-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["survey-volume.schema.json"], valid=False))
def test_survey_volume_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-017-04")
def test_survey_volume_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["survey-volume.schema.json"])


@pytest.mark.req("DC-017-04")
def test_survey_volume_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["survey-volume.schema.json"])


@pytest.mark.req("DC-017-05")
def test_survey_flight_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("survey-flight.schema.json")


@pytest.mark.req("DC-017-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["survey-flight.schema.json"], valid=True))
def test_survey_flight_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-017-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["survey-flight.schema.json"], valid=False))
def test_survey_flight_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-017-05")
def test_survey_flight_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["survey-flight.schema.json"])


@pytest.mark.req("DC-017-05")
def test_survey_flight_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["survey-flight.schema.json"])

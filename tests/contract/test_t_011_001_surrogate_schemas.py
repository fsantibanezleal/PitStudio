"""T-011-001: surrogate contract schemas and generated types.

Requirements: DC-011-01, DC-011-02, DC-011-03, DC-011-04.

Spec: specs/011-surrogates/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/granular-rollout.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/granular-rollout.schema.json)
- `contracts/surrogate-io.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/surrogate-io.schema.json)
- `contracts/field-dataset.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/field-dataset.schema.json)
- `contracts/calibration-result.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/calibration-result.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "011-surrogates"


@pytest.mark.req("DC-011-01")
def test_granular_rollout_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("granular-rollout.schema.json")


@pytest.mark.req("DC-011-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["granular-rollout.schema.json"], valid=True))
def test_granular_rollout_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-011-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["granular-rollout.schema.json"], valid=False))
def test_granular_rollout_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-011-01")
def test_granular_rollout_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["granular-rollout.schema.json"])


@pytest.mark.req("DC-011-01")
def test_granular_rollout_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["granular-rollout.schema.json"])


@pytest.mark.req("DC-011-02")
def test_surrogate_io_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("surrogate-io.schema.json")


@pytest.mark.req("DC-011-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["surrogate-io.schema.json"], valid=True))
def test_surrogate_io_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-011-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["surrogate-io.schema.json"], valid=False))
def test_surrogate_io_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-011-02")
def test_surrogate_io_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["surrogate-io.schema.json"])


@pytest.mark.req("DC-011-02")
def test_surrogate_io_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["surrogate-io.schema.json"])


@pytest.mark.req("DC-011-03")
def test_field_dataset_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("field-dataset.schema.json")


@pytest.mark.req("DC-011-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["field-dataset.schema.json"], valid=True))
def test_field_dataset_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-011-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["field-dataset.schema.json"], valid=False))
def test_field_dataset_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-011-03")
def test_field_dataset_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["field-dataset.schema.json"])


@pytest.mark.req("DC-011-03")
def test_field_dataset_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["field-dataset.schema.json"])


@pytest.mark.req("DC-011-04")
def test_calibration_result_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("calibration-result.schema.json")


@pytest.mark.req("DC-011-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["calibration-result.schema.json"], valid=True))
def test_calibration_result_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-011-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["calibration-result.schema.json"], valid=False))
def test_calibration_result_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-011-04")
def test_calibration_result_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["calibration-result.schema.json"])


@pytest.mark.req("DC-011-04")
def test_calibration_result_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["calibration-result.schema.json"])

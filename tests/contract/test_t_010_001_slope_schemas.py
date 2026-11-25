"""T-010-001: slope contract schemas and generated types.

Requirements: DC-010-01, DC-010-02, DC-010-03, DC-010-04.

Spec: specs/010-slope/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/slope-section.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/slope-section.schema.json)
- `contracts/displacement-series.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/displacement-series.schema.json)
- `contracts/ttf-results.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/ttf-results.schema.json)
- `contracts/slope-results.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/slope-results.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "010-slope"


@pytest.mark.req("DC-010-01")
def test_slope_section_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("slope-section.schema.json")


@pytest.mark.req("DC-010-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["slope-section.schema.json"], valid=True))
def test_slope_section_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-010-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["slope-section.schema.json"], valid=False))
def test_slope_section_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-010-01")
def test_slope_section_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["slope-section.schema.json"])


@pytest.mark.req("DC-010-01")
def test_slope_section_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["slope-section.schema.json"])


@pytest.mark.req("DC-010-02")
def test_displacement_series_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("displacement-series.schema.json")


@pytest.mark.req("DC-010-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["displacement-series.schema.json"], valid=True))
def test_displacement_series_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-010-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["displacement-series.schema.json"], valid=False))
def test_displacement_series_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-010-02")
def test_displacement_series_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["displacement-series.schema.json"])


@pytest.mark.req("DC-010-02")
def test_displacement_series_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["displacement-series.schema.json"])


@pytest.mark.req("DC-010-03")
def test_ttf_results_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("ttf-results.schema.json")


@pytest.mark.req("DC-010-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["ttf-results.schema.json"], valid=True))
def test_ttf_results_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-010-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["ttf-results.schema.json"], valid=False))
def test_ttf_results_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-010-03")
def test_ttf_results_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["ttf-results.schema.json"])


@pytest.mark.req("DC-010-03")
def test_ttf_results_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["ttf-results.schema.json"])


@pytest.mark.req("DC-010-04")
def test_slope_results_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("slope-results.schema.json")


@pytest.mark.req("DC-010-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["slope-results.schema.json"], valid=True))
def test_slope_results_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-010-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["slope-results.schema.json"], valid=False))
def test_slope_results_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-010-04")
def test_slope_results_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["slope-results.schema.json"])


@pytest.mark.req("DC-010-04")
def test_slope_results_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["slope-results.schema.json"])

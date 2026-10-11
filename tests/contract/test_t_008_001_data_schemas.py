"""T-008-001: data-pipeline contract schemas and generated types.

Requirements: DC-008-02, DC-008-03, DC-008-04, DC-008-05.

Spec: specs/008-data-pipeline/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/fetch-record.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/fetch-record.schema.json)
- `contracts/ingestion-report.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/ingestion-report.schema.json)
- `contracts/split.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/split.schema.json)
- `contracts/data-card.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/data-card.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "008-data-pipeline"


@pytest.mark.req("DC-008-02")
def test_fetch_record_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("fetch-record.schema.json")


@pytest.mark.req("DC-008-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["fetch-record.schema.json"], valid=True))
def test_fetch_record_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-008-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["fetch-record.schema.json"], valid=False))
def test_fetch_record_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-008-02")
def test_fetch_record_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["fetch-record.schema.json"])


@pytest.mark.req("DC-008-02")
def test_fetch_record_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["fetch-record.schema.json"])


@pytest.mark.req("DC-008-03")
def test_ingestion_report_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("ingestion-report.schema.json")


@pytest.mark.req("DC-008-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["ingestion-report.schema.json"], valid=True))
def test_ingestion_report_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-008-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["ingestion-report.schema.json"], valid=False))
def test_ingestion_report_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-008-03")
def test_ingestion_report_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["ingestion-report.schema.json"])


@pytest.mark.req("DC-008-03")
def test_ingestion_report_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["ingestion-report.schema.json"])


@pytest.mark.req("DC-008-04")
def test_split_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("split.schema.json")


@pytest.mark.req("DC-008-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["split.schema.json"], valid=True))
def test_split_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-008-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["split.schema.json"], valid=False))
def test_split_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-008-04")
def test_split_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["split.schema.json"])


@pytest.mark.req("DC-008-04")
def test_split_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["split.schema.json"])


@pytest.mark.req("DC-008-05")
def test_data_card_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("data-card.schema.json")


@pytest.mark.req("DC-008-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["data-card.schema.json"], valid=True))
def test_data_card_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-008-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["data-card.schema.json"], valid=False))
def test_data_card_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-008-05")
def test_data_card_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["data-card.schema.json"])


@pytest.mark.req("DC-008-05")
def test_data_card_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["data-card.schema.json"])

"""T-018-004: parity fixture, parity report and lane measurement schemas and generated types.

Requirements: DC-018-04, DC-018-05, DC-018-06.

Spec: specs/018-web-cases/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/parity-fixture.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/parity-fixture.schema.json)
- `contracts/parity-report.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/parity-report.schema.json)
- `contracts/lane-measurements.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/lane-measurements.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "018-web-cases"


@pytest.mark.req("DC-018-04")
def test_parity_fixture_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("parity-fixture.schema.json")


@pytest.mark.req("DC-018-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["parity-fixture.schema.json"], valid=True))
def test_parity_fixture_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["parity-fixture.schema.json"], valid=False))
def test_parity_fixture_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-04")
def test_parity_fixture_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["parity-fixture.schema.json"])


@pytest.mark.req("DC-018-04")
def test_parity_fixture_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["parity-fixture.schema.json"])


@pytest.mark.req("DC-018-05")
def test_parity_report_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("parity-report.schema.json")


@pytest.mark.req("DC-018-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["parity-report.schema.json"], valid=True))
def test_parity_report_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["parity-report.schema.json"], valid=False))
def test_parity_report_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-05")
def test_parity_report_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["parity-report.schema.json"])


@pytest.mark.req("DC-018-05")
def test_parity_report_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["parity-report.schema.json"])


@pytest.mark.req("DC-018-06")
def test_lane_measurements_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("lane-measurements.schema.json")


@pytest.mark.req("DC-018-06")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["lane-measurements.schema.json"], valid=True))
def test_lane_measurements_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-06")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["lane-measurements.schema.json"], valid=False))
def test_lane_measurements_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-06")
def test_lane_measurements_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["lane-measurements.schema.json"])


@pytest.mark.req("DC-018-06")
def test_lane_measurements_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["lane-measurements.schema.json"])

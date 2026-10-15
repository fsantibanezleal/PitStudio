"""T-005-001: physics contract schemas and generated types.

Requirements: DC-005-01, DC-005-02, DC-005-03, DC-005-04, DC-005-05, DC-005-06.

Spec: specs/005-physics/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/physics-scenario.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/physics-scenario.schema.json)
- `contracts/physics-field.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/physics-field.schema.json)
- `contracts/physics-observables.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/physics-observables.schema.json)
- `contracts/physics-benchmark-report.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/physics-benchmark-report.schema.json)
- `contracts/physics-parity-golden.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/physics-parity-golden.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "005-physics"


@pytest.mark.req("DC-005-01")
def test_physics_scenario_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("physics-scenario.schema.json")


@pytest.mark.req("DC-005-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["physics-scenario.schema.json"], valid=True))
def test_physics_scenario_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-005-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["physics-scenario.schema.json"], valid=False))
def test_physics_scenario_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-005-01")
def test_physics_scenario_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["physics-scenario.schema.json"])


@pytest.mark.req("DC-005-01")
def test_physics_scenario_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["physics-scenario.schema.json"])


@pytest.mark.req("DC-005-02")
def test_physics_field_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("physics-field.schema.json")


@pytest.mark.req("DC-005-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["physics-field.schema.json"], valid=True))
def test_physics_field_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-005-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["physics-field.schema.json"], valid=False))
def test_physics_field_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-005-02")
def test_physics_field_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["physics-field.schema.json"])


@pytest.mark.req("DC-005-02")
def test_physics_field_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["physics-field.schema.json"])


@pytest.mark.req("DC-005-03")
def test_physics_observables_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("physics-observables.schema.json")


@pytest.mark.req("DC-005-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["physics-observables.schema.json"], valid=True))
def test_physics_observables_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-005-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["physics-observables.schema.json"], valid=False))
def test_physics_observables_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-005-03")
def test_physics_observables_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["physics-observables.schema.json"])


@pytest.mark.req("DC-005-03")
def test_physics_observables_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["physics-observables.schema.json"])


@pytest.mark.req("DC-005-05")
def test_physics_benchmark_report_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("physics-benchmark-report.schema.json")


@pytest.mark.req("DC-005-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["physics-benchmark-report.schema.json"], valid=True))
def test_physics_benchmark_report_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-005-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["physics-benchmark-report.schema.json"], valid=False))
def test_physics_benchmark_report_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-005-05")
def test_physics_benchmark_report_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["physics-benchmark-report.schema.json"])


@pytest.mark.req("DC-005-05")
def test_physics_benchmark_report_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["physics-benchmark-report.schema.json"])


@pytest.mark.req("DC-005-06")
def test_physics_parity_golden_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("physics-parity-golden.schema.json")


@pytest.mark.req("DC-005-06")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["physics-parity-golden.schema.json"], valid=True))
def test_physics_parity_golden_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-005-06")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["physics-parity-golden.schema.json"], valid=False))
def test_physics_parity_golden_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-005-06")
def test_physics_parity_golden_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["physics-parity-golden.schema.json"])


@pytest.mark.req("DC-005-06")
def test_physics_parity_golden_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["physics-parity-golden.schema.json"])


@pytest.mark.req("DC-005-04")
def test_replay_shard_schema_owned_by_spec_018_is_promoted_for_the_replay_manifest() -> None:
    # DC-005-04: "one schema, one owner": the replay manifest and shards use contracts/replay-shard.schema.json
    # (draft owned by spec 018, tested in T-018-003); spec 005 only needs it to exist and be valid 2020-12.
    kit.assert_schema_promoted("replay-shard.schema.json")

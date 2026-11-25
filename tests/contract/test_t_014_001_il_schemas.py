"""T-014-001: imitation-learning contract schemas, generated types and the type drift check.

Requirements: DC-014-01, DC-014-02, DC-014-03, DC-014-04, DC-014-05.

Spec: specs/014-robot-learning/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/il-task.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/il-task.schema.json)
- `contracts/machine-params.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/machine-params.schema.json)
- `contracts/il-policy-handoff.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/il-policy-handoff.schema.json)
- `contracts/il-episodes.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/il-episodes.schema.json)
- `contracts/il-twin.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/il-twin.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "014-robot-learning"


@pytest.mark.req("DC-014-01")
def test_il_task_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("il-task.schema.json")


@pytest.mark.req("DC-014-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["il-task.schema.json"], valid=True))
def test_il_task_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-014-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["il-task.schema.json"], valid=False))
def test_il_task_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-014-01")
def test_il_task_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["il-task.schema.json"])


@pytest.mark.req("DC-014-01")
def test_il_task_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["il-task.schema.json"])


@pytest.mark.req("DC-014-02")
def test_machine_params_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("machine-params.schema.json")


@pytest.mark.req("DC-014-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["machine-params.schema.json"], valid=True))
def test_machine_params_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-014-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["machine-params.schema.json"], valid=False))
def test_machine_params_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-014-02")
def test_machine_params_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["machine-params.schema.json"])


@pytest.mark.req("DC-014-02")
def test_machine_params_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["machine-params.schema.json"])


@pytest.mark.req("DC-014-03")
def test_il_policy_handoff_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("il-policy-handoff.schema.json")


@pytest.mark.req("DC-014-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["il-policy-handoff.schema.json"], valid=True))
def test_il_policy_handoff_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-014-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["il-policy-handoff.schema.json"], valid=False))
def test_il_policy_handoff_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-014-03")
def test_il_policy_handoff_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["il-policy-handoff.schema.json"])


@pytest.mark.req("DC-014-03")
def test_il_policy_handoff_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["il-policy-handoff.schema.json"])


@pytest.mark.req("DC-014-04")
def test_il_episodes_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("il-episodes.schema.json")


@pytest.mark.req("DC-014-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["il-episodes.schema.json"], valid=True))
def test_il_episodes_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-014-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["il-episodes.schema.json"], valid=False))
def test_il_episodes_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-014-04")
def test_il_episodes_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["il-episodes.schema.json"])


@pytest.mark.req("DC-014-04")
def test_il_episodes_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["il-episodes.schema.json"])


@pytest.mark.req("DC-014-05")
def test_il_twin_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("il-twin.schema.json")


@pytest.mark.req("DC-014-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["il-twin.schema.json"], valid=True))
def test_il_twin_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-014-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["il-twin.schema.json"], valid=False))
def test_il_twin_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-014-05")
def test_il_twin_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["il-twin.schema.json"])


@pytest.mark.req("DC-014-05")
def test_il_twin_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["il-twin.schema.json"])


@pytest.mark.req("DC-014-01")
@pytest.mark.req("DC-014-02")
@pytest.mark.req("DC-014-03")
@pytest.mark.req("DC-014-04")
@pytest.mark.req("DC-014-05")
def test_generated_types_have_no_drift_from_the_schemas() -> None:
    # `python tools/gen_types.py --check` (FR-001-42) exits 0 once the generated modules of this task are committed.
    kit.assert_gen_types_check_clean()

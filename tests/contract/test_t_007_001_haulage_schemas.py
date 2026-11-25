"""T-007-001: haulage and dispatch contract schemas and generated types.

Requirements: DC-007-01, DC-007-02, DC-007-03, DC-007-04, DC-007-05.

Spec: specs/007-haulage-dispatch/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/haul-scenario.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/haul-scenario.schema.json)
- `contracts/des-trace.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/des-trace.schema.json)
- `contracts/dispatch-eval.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/dispatch-eval.schema.json)
- `contracts/dispatch-policy-io.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/dispatch-policy-io.schema.json)
- `contracts/haul-energy.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/haul-energy.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "007-haulage-dispatch"


@pytest.mark.req("DC-007-01")
def test_haul_scenario_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("haul-scenario.schema.json")


@pytest.mark.req("DC-007-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["haul-scenario.schema.json"], valid=True))
def test_haul_scenario_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-007-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["haul-scenario.schema.json"], valid=False))
def test_haul_scenario_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-007-01")
def test_haul_scenario_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["haul-scenario.schema.json"])


@pytest.mark.req("DC-007-01")
def test_haul_scenario_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["haul-scenario.schema.json"])


@pytest.mark.req("DC-007-02")
def test_des_trace_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("des-trace.schema.json")


@pytest.mark.req("DC-007-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["des-trace.schema.json"], valid=True))
def test_des_trace_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-007-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["des-trace.schema.json"], valid=False))
def test_des_trace_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-007-02")
def test_des_trace_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["des-trace.schema.json"])


@pytest.mark.req("DC-007-02")
def test_des_trace_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["des-trace.schema.json"])


@pytest.mark.req("DC-007-03")
def test_dispatch_eval_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("dispatch-eval.schema.json")


@pytest.mark.req("DC-007-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["dispatch-eval.schema.json"], valid=True))
def test_dispatch_eval_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-007-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["dispatch-eval.schema.json"], valid=False))
def test_dispatch_eval_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-007-03")
def test_dispatch_eval_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["dispatch-eval.schema.json"])


@pytest.mark.req("DC-007-03")
def test_dispatch_eval_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["dispatch-eval.schema.json"])


@pytest.mark.req("DC-007-04")
def test_dispatch_policy_io_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("dispatch-policy-io.schema.json")


@pytest.mark.req("DC-007-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["dispatch-policy-io.schema.json"], valid=True))
def test_dispatch_policy_io_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-007-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["dispatch-policy-io.schema.json"], valid=False))
def test_dispatch_policy_io_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-007-04")
def test_dispatch_policy_io_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["dispatch-policy-io.schema.json"])


@pytest.mark.req("DC-007-04")
def test_dispatch_policy_io_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["dispatch-policy-io.schema.json"])


@pytest.mark.req("DC-007-05")
def test_haul_energy_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("haul-energy.schema.json")


@pytest.mark.req("DC-007-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["haul-energy.schema.json"], valid=True))
def test_haul_energy_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-007-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["haul-energy.schema.json"], valid=False))
def test_haul_energy_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-007-05")
def test_haul_energy_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["haul-energy.schema.json"])


@pytest.mark.req("DC-007-05")
def test_haul_energy_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["haul-energy.schema.json"])

"""T-015-001: VLM reasoning contract schemas, generated types and the type drift check.

Requirements: DC-015-01, DC-015-02, DC-015-03, DC-015-04, DC-015-05, DC-015-06.

Spec: specs/015-vlm/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/frame-state.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/frame-state.schema.json)
- `contracts/vlm-queries.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/vlm-queries.schema.json)
- `contracts/reason-pins.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/reason-pins.schema.json)
- `contracts/vlm-record.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/vlm-record.schema.json)
- `contracts/vlm-metrics.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/vlm-metrics.schema.json)
- `contracts/plausibility-pairs.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/plausibility-pairs.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "015-vlm"


@pytest.mark.req("DC-015-01")
def test_frame_state_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("frame-state.schema.json")


@pytest.mark.req("DC-015-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["frame-state.schema.json"], valid=True))
def test_frame_state_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-015-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["frame-state.schema.json"], valid=False))
def test_frame_state_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-015-01")
def test_frame_state_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["frame-state.schema.json"])


@pytest.mark.req("DC-015-01")
def test_frame_state_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["frame-state.schema.json"])


@pytest.mark.req("DC-015-02")
def test_vlm_queries_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("vlm-queries.schema.json")


@pytest.mark.req("DC-015-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["vlm-queries.schema.json"], valid=True))
def test_vlm_queries_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-015-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["vlm-queries.schema.json"], valid=False))
def test_vlm_queries_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-015-02")
def test_vlm_queries_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["vlm-queries.schema.json"])


@pytest.mark.req("DC-015-02")
def test_vlm_queries_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["vlm-queries.schema.json"])


@pytest.mark.req("DC-015-03")
def test_reason_pins_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("reason-pins.schema.json")


@pytest.mark.req("DC-015-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["reason-pins.schema.json"], valid=True))
def test_reason_pins_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-015-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["reason-pins.schema.json"], valid=False))
def test_reason_pins_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-015-03")
def test_reason_pins_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["reason-pins.schema.json"])


@pytest.mark.req("DC-015-03")
def test_reason_pins_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["reason-pins.schema.json"])


@pytest.mark.req("DC-015-04")
def test_vlm_record_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("vlm-record.schema.json")


@pytest.mark.req("DC-015-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["vlm-record.schema.json"], valid=True))
def test_vlm_record_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-015-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["vlm-record.schema.json"], valid=False))
def test_vlm_record_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-015-04")
def test_vlm_record_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["vlm-record.schema.json"])


@pytest.mark.req("DC-015-04")
def test_vlm_record_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["vlm-record.schema.json"])


@pytest.mark.req("DC-015-05")
def test_vlm_metrics_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("vlm-metrics.schema.json")


@pytest.mark.req("DC-015-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["vlm-metrics.schema.json"], valid=True))
def test_vlm_metrics_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-015-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["vlm-metrics.schema.json"], valid=False))
def test_vlm_metrics_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-015-05")
def test_vlm_metrics_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["vlm-metrics.schema.json"])


@pytest.mark.req("DC-015-05")
def test_vlm_metrics_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["vlm-metrics.schema.json"])


@pytest.mark.req("DC-015-06")
def test_plausibility_pairs_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("plausibility-pairs.schema.json")


@pytest.mark.req("DC-015-06")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["plausibility-pairs.schema.json"], valid=True))
def test_plausibility_pairs_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-015-06")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["plausibility-pairs.schema.json"], valid=False))
def test_plausibility_pairs_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-015-06")
def test_plausibility_pairs_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["plausibility-pairs.schema.json"])


@pytest.mark.req("DC-015-06")
def test_plausibility_pairs_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["plausibility-pairs.schema.json"])


@pytest.mark.req("DC-015-01")
@pytest.mark.req("DC-015-02")
@pytest.mark.req("DC-015-03")
@pytest.mark.req("DC-015-04")
@pytest.mark.req("DC-015-05")
@pytest.mark.req("DC-015-06")
def test_generated_types_have_no_drift_from_the_schemas() -> None:
    # `python tools/gen_types.py --check` (FR-001-42) exits 0 once the generated modules of this task are committed.
    kit.assert_gen_types_check_clean()

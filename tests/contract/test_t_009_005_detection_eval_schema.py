"""T-009-005: detection evaluation report schema, generated types and the manifest fields it relies on.

Requirements: DC-009-05, DC-000-01.

Spec: specs/009-perception/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/detection-eval.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/detection-eval.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "009-perception"


@pytest.mark.req("DC-009-05")
def test_detection_eval_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("detection-eval.schema.json")


@pytest.mark.req("DC-009-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["detection-eval.schema.json"], valid=True))
def test_detection_eval_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-009-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["detection-eval.schema.json"], valid=False))
def test_detection_eval_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-009-05")
def test_detection_eval_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["detection-eval.schema.json"])


@pytest.mark.req("DC-009-05")
def test_detection_eval_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["detection-eval.schema.json"])


@pytest.mark.req("DC-000-01")
def test_manifest_schema_carries_the_performance_lane_and_licence_fields_the_perception_stages_write() -> None:
    # spec 009 section 6: "Run and asset manifests (performance marker, lane, licence class) follow DC-000-01".
    # Field names are those of data-model 001 sections 2.3 and 2.5.
    m = kit.load_promoted("manifest.schema.json")
    assert {"lane", "licence_class", "producer"} <= set(m["$defs"]["artefact"]["properties"])
    assert "performance" in m["$defs"]["stage"]["properties"]

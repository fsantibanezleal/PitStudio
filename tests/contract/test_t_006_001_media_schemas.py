"""T-006-001: media and telemetry contract schemas and generated types.

Requirements: DC-006-01, DC-006-02, DC-006-03.

Spec: specs/006-media-telemetry/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/frame-manifest.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/frame-manifest.schema.json)
- `contracts/encode-report.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/encode-report.schema.json)
- `contracts/profile-summary.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/profile-summary.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "006-media-telemetry"


@pytest.mark.req("DC-006-01")
def test_frame_manifest_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("frame-manifest.schema.json")


@pytest.mark.req("DC-006-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["frame-manifest.schema.json"], valid=True))
def test_frame_manifest_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-006-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["frame-manifest.schema.json"], valid=False))
def test_frame_manifest_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-006-01")
def test_frame_manifest_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["frame-manifest.schema.json"])


@pytest.mark.req("DC-006-01")
def test_frame_manifest_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["frame-manifest.schema.json"])


@pytest.mark.req("DC-006-02")
def test_encode_report_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("encode-report.schema.json")


@pytest.mark.req("DC-006-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["encode-report.schema.json"], valid=True))
def test_encode_report_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-006-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["encode-report.schema.json"], valid=False))
def test_encode_report_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-006-02")
def test_encode_report_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["encode-report.schema.json"])


@pytest.mark.req("DC-006-02")
def test_encode_report_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["encode-report.schema.json"])


@pytest.mark.req("DC-006-03")
def test_profile_summary_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("profile-summary.schema.json")


@pytest.mark.req("DC-006-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["profile-summary.schema.json"], valid=True))
def test_profile_summary_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-006-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["profile-summary.schema.json"], valid=False))
def test_profile_summary_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-006-03")
def test_profile_summary_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["profile-summary.schema.json"])


@pytest.mark.req("DC-006-03")
def test_profile_summary_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["profile-summary.schema.json"])

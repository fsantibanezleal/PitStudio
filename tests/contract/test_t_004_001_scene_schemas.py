"""T-004-001: scene-pipeline contract schemas, generated types and hostile parameter documents.

Requirements: DC-004-01, DC-004-02, DC-004-03, DC-004-04, DC-004-05, DC-004-06, DC-004-07, DC-004-08,
FR-004-40.

Spec: specs/004-scene-pipeline/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/scene-spec.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/scene-spec.schema.json)
- `contracts/scene-manifest.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/scene-manifest.schema.json)
- `contracts/terrain-grid.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/terrain-grid.schema.json)
- `contracts/terrain-tiles.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/terrain-tiles.schema.json)
- `contracts/pit-design-report.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/pit-design-report.schema.json)
- `contracts/road-network.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/road-network.schema.json)
- `contracts/scene-validation-report.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/scene-validation-report.schema.json)
- `contracts/scene-digest.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/scene-digest.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "004-scene-pipeline"


@pytest.mark.req("DC-004-01")
def test_scene_spec_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("scene-spec.schema.json")


@pytest.mark.req("DC-004-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["scene-spec.schema.json"], valid=True))
def test_scene_spec_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-004-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["scene-spec.schema.json"], valid=False))
def test_scene_spec_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-004-01")
def test_scene_spec_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["scene-spec.schema.json"])


@pytest.mark.req("DC-004-01")
def test_scene_spec_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["scene-spec.schema.json"])


@pytest.mark.req("DC-004-02")
def test_scene_manifest_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("scene-manifest.schema.json")


@pytest.mark.req("DC-004-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["scene-manifest.schema.json"], valid=True))
def test_scene_manifest_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-004-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["scene-manifest.schema.json"], valid=False))
def test_scene_manifest_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-004-02")
def test_scene_manifest_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["scene-manifest.schema.json"])


@pytest.mark.req("DC-004-02")
def test_scene_manifest_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["scene-manifest.schema.json"])


@pytest.mark.req("DC-004-03")
def test_terrain_grid_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("terrain-grid.schema.json")


@pytest.mark.req("DC-004-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["terrain-grid.schema.json"], valid=True))
def test_terrain_grid_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-004-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["terrain-grid.schema.json"], valid=False))
def test_terrain_grid_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-004-03")
def test_terrain_grid_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["terrain-grid.schema.json"])


@pytest.mark.req("DC-004-03")
def test_terrain_grid_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["terrain-grid.schema.json"])


@pytest.mark.req("DC-004-04")
def test_terrain_tiles_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("terrain-tiles.schema.json")


@pytest.mark.req("DC-004-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["terrain-tiles.schema.json"], valid=True))
def test_terrain_tiles_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-004-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["terrain-tiles.schema.json"], valid=False))
def test_terrain_tiles_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-004-04")
def test_terrain_tiles_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["terrain-tiles.schema.json"])


@pytest.mark.req("DC-004-04")
def test_terrain_tiles_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["terrain-tiles.schema.json"])


@pytest.mark.req("DC-004-05")
def test_pit_design_report_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("pit-design-report.schema.json")


@pytest.mark.req("DC-004-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["pit-design-report.schema.json"], valid=True))
def test_pit_design_report_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-004-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["pit-design-report.schema.json"], valid=False))
def test_pit_design_report_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-004-05")
def test_pit_design_report_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["pit-design-report.schema.json"])


@pytest.mark.req("DC-004-05")
def test_pit_design_report_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["pit-design-report.schema.json"])


@pytest.mark.req("DC-004-06")
def test_road_network_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("road-network.schema.json")


@pytest.mark.req("DC-004-06")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["road-network.schema.json"], valid=True))
def test_road_network_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-004-06")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["road-network.schema.json"], valid=False))
def test_road_network_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-004-06")
def test_road_network_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["road-network.schema.json"])


@pytest.mark.req("DC-004-06")
def test_road_network_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["road-network.schema.json"])


@pytest.mark.req("DC-004-07")
def test_scene_validation_report_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("scene-validation-report.schema.json")


@pytest.mark.req("DC-004-07")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["scene-validation-report.schema.json"], valid=True))
def test_scene_validation_report_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-004-07")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["scene-validation-report.schema.json"], valid=False))
def test_scene_validation_report_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-004-07")
def test_scene_validation_report_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["scene-validation-report.schema.json"])


@pytest.mark.req("DC-004-07")
def test_scene_validation_report_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["scene-validation-report.schema.json"])


@pytest.mark.req("DC-004-08")
def test_scene_digest_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("scene-digest.schema.json")


@pytest.mark.req("DC-004-08")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["scene-digest.schema.json"], valid=True))
def test_scene_digest_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-004-08")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["scene-digest.schema.json"], valid=False))
def test_scene_digest_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-004-08")
def test_scene_digest_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["scene-digest.schema.json"])


@pytest.mark.req("DC-004-08")
def test_scene_digest_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["scene-digest.schema.json"])


@pytest.mark.req("FR-004-40")
def test_scene_spec_hostile_classes_of_fr_004_40_are_rejected_with_json_pointers() -> None:
    # FR-004-40 classes: missing field, extra field, wrong type, unknown enumeration value, string over 256 characters.
    kit.assert_hostile_classes(
        SPEC, "scene-spec.schema.json", ["required", "additionalProperties", "type", "enum", "maxLength"]
    )


@pytest.mark.req("FR-004-40")
def test_scene_spec_reports_every_violation_not_only_the_first() -> None:
    # Hand-built metamorphic case: one valid document, two independent violations at the root (a required field
    # removed, an unknown field added). FR-004-40: the stage lists EVERY violation with its JSON pointer.
    ex = next(
        e for e in kit.load_examples(SPEC, ["scene-spec.schema.json"]) if e["valid"] and e.get("target", "#") == "#"
    )
    doc = kit.read_json(ex["path"])
    schema = kit.load_promoted("scene-spec.schema.json")
    required = schema.get("required")
    assert required, "the scene-spec root must be a closed object with a `required` list (FR-001-02)"
    bad = {k: v for k, v in doc.items() if k != required[0]}
    bad["zz_unknown_property_for_contract_test"] = 1
    errs = set(kit.validation_errors("scene-spec.schema.json", "#", bad))
    assert ("", "required") in errs
    assert ("", "additionalProperties") in errs

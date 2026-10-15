"""T-013-001: sensor contract schemas, generated types and the type drift check.

Requirements: DC-013-01, DC-013-02, DC-013-03, DC-013-04, DC-013-05.

Spec: specs/013-sensors/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/sensor-recipe.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/sensor-recipe.schema.json)
- `contracts/lidar-envelope.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/lidar-envelope.schema.json)
- `contracts/sensor-shard.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/sensor-shard.schema.json)
- `contracts/web-cloud-shard.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/web-cloud-shard.schema.json)
- `contracts/dust-slider.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/dust-slider.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "013-sensors"


@pytest.mark.req("DC-013-01")
def test_sensor_recipe_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("sensor-recipe.schema.json")


@pytest.mark.req("DC-013-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["sensor-recipe.schema.json"], valid=True))
def test_sensor_recipe_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-013-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["sensor-recipe.schema.json"], valid=False))
def test_sensor_recipe_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-013-01")
def test_sensor_recipe_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["sensor-recipe.schema.json"])


@pytest.mark.req("DC-013-01")
def test_sensor_recipe_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["sensor-recipe.schema.json"])


@pytest.mark.req("DC-013-02")
def test_lidar_envelope_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("lidar-envelope.schema.json")


@pytest.mark.req("DC-013-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["lidar-envelope.schema.json"], valid=True))
def test_lidar_envelope_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-013-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["lidar-envelope.schema.json"], valid=False))
def test_lidar_envelope_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-013-02")
def test_lidar_envelope_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["lidar-envelope.schema.json"])


@pytest.mark.req("DC-013-02")
def test_lidar_envelope_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["lidar-envelope.schema.json"])


@pytest.mark.req("DC-013-03")
def test_sensor_shard_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("sensor-shard.schema.json")


@pytest.mark.req("DC-013-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["sensor-shard.schema.json"], valid=True))
def test_sensor_shard_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-013-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["sensor-shard.schema.json"], valid=False))
def test_sensor_shard_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-013-03")
def test_sensor_shard_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["sensor-shard.schema.json"])


@pytest.mark.req("DC-013-03")
def test_sensor_shard_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["sensor-shard.schema.json"])


@pytest.mark.req("DC-013-04")
def test_web_cloud_shard_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("web-cloud-shard.schema.json")


@pytest.mark.req("DC-013-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["web-cloud-shard.schema.json"], valid=True))
def test_web_cloud_shard_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-013-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["web-cloud-shard.schema.json"], valid=False))
def test_web_cloud_shard_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-013-04")
def test_web_cloud_shard_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["web-cloud-shard.schema.json"])


@pytest.mark.req("DC-013-04")
def test_web_cloud_shard_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["web-cloud-shard.schema.json"])


@pytest.mark.req("DC-013-05")
def test_dust_slider_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("dust-slider.schema.json")


@pytest.mark.req("DC-013-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["dust-slider.schema.json"], valid=True))
def test_dust_slider_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-013-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["dust-slider.schema.json"], valid=False))
def test_dust_slider_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-013-05")
def test_dust_slider_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["dust-slider.schema.json"])


@pytest.mark.req("DC-013-05")
def test_dust_slider_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["dust-slider.schema.json"])


@pytest.mark.req("DC-013-01")
@pytest.mark.req("DC-013-02")
@pytest.mark.req("DC-013-03")
@pytest.mark.req("DC-013-04")
@pytest.mark.req("DC-013-05")
def test_generated_types_have_no_drift_from_the_schemas() -> None:
    # `python tools/gen_types.py --check` (FR-001-42) exits 0 once the generated modules of this task are committed.
    kit.assert_gen_types_check_clean()

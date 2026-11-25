"""T-018-002: engine input and output schemas of the 25 browser engines.

Requirements: DC-018-02.

Spec: specs/018-web-cases/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/engines/des.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/des.schema.json)
- `contracts/engines/policies.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/policies.schema.json)
- `contracts/engines/haulage.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/haulage.schema.json)
- `contracts/engines/lp.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/lp.schema.json)
- `contracts/engines/routing.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/routing.schema.json)
- `contracts/engines/il1-twin.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/il1-twin.schema.json)
- `contracts/engines/il2-twin.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/il2-twin.schema.json)
- `contracts/engines/granular.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/granular.schema.json)
- `contracts/engines/gns.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/gns.schema.json)
- `contracts/engines/traffic.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/traffic.schema.json)
- `contracts/engines/dust-lidar.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/dust-lidar.schema.json)
- `contracts/engines/detector.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/detector.schema.json)
- `contracts/engines/geotech.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/geotech.schema.json)
- `contracts/engines/forecasters.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/forecasters.schema.json)
- `contracts/engines/swe.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/swe.schema.json)
- `contracts/engines/fno.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/fno.schema.json)
- `contracts/engines/plume.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/plume.schema.json)
- `contracts/engines/dust-particles.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/dust-particles.schema.json)
- `contracts/engines/blasting.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/blasting.schema.json)
- `contracts/engines/watershed.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/watershed.schema.json)
- `contracts/engines/unet.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/unet.schema.json)
- `contracts/engines/comminution.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/comminution.schema.json)
- `contracts/engines/meta-model.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/meta-model.schema.json)
- `contracts/engines/mincut.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/mincut.schema.json)
- `contracts/engines/volume.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/engines/volume.schema.json)
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "018-web-cases"


@pytest.mark.req("DC-018-02")
def test_engines_des_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/des.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/des.schema.json"], valid=True))
def test_engines_des_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/des.schema.json"], valid=False))
def test_engines_des_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_policies_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/policies.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/policies.schema.json"], valid=True))
def test_engines_policies_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/policies.schema.json"], valid=False))
def test_engines_policies_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_haulage_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/haulage.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/haulage.schema.json"], valid=True))
def test_engines_haulage_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/haulage.schema.json"], valid=False))
def test_engines_haulage_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_lp_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/lp.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/lp.schema.json"], valid=True))
def test_engines_lp_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/lp.schema.json"], valid=False))
def test_engines_lp_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_routing_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/routing.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/routing.schema.json"], valid=True))
def test_engines_routing_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/routing.schema.json"], valid=False))
def test_engines_routing_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_il1_twin_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/il1-twin.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/il1-twin.schema.json"], valid=True))
def test_engines_il1_twin_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/il1-twin.schema.json"], valid=False))
def test_engines_il1_twin_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_il2_twin_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/il2-twin.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/il2-twin.schema.json"], valid=True))
def test_engines_il2_twin_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/il2-twin.schema.json"], valid=False))
def test_engines_il2_twin_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_granular_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/granular.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/granular.schema.json"], valid=True))
def test_engines_granular_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/granular.schema.json"], valid=False))
def test_engines_granular_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_gns_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/gns.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/gns.schema.json"], valid=True))
def test_engines_gns_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/gns.schema.json"], valid=False))
def test_engines_gns_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_traffic_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/traffic.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/traffic.schema.json"], valid=True))
def test_engines_traffic_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/traffic.schema.json"], valid=False))
def test_engines_traffic_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_dust_lidar_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/dust-lidar.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/dust-lidar.schema.json"], valid=True))
def test_engines_dust_lidar_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/dust-lidar.schema.json"], valid=False))
def test_engines_dust_lidar_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_detector_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/detector.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/detector.schema.json"], valid=True))
def test_engines_detector_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/detector.schema.json"], valid=False))
def test_engines_detector_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_geotech_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/geotech.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/geotech.schema.json"], valid=True))
def test_engines_geotech_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/geotech.schema.json"], valid=False))
def test_engines_geotech_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_forecasters_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/forecasters.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/forecasters.schema.json"], valid=True))
def test_engines_forecasters_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/forecasters.schema.json"], valid=False))
def test_engines_forecasters_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_swe_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/swe.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/swe.schema.json"], valid=True))
def test_engines_swe_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/swe.schema.json"], valid=False))
def test_engines_swe_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_fno_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/fno.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/fno.schema.json"], valid=True))
def test_engines_fno_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/fno.schema.json"], valid=False))
def test_engines_fno_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_plume_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/plume.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/plume.schema.json"], valid=True))
def test_engines_plume_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/plume.schema.json"], valid=False))
def test_engines_plume_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_dust_particles_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/dust-particles.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/dust-particles.schema.json"], valid=True))
def test_engines_dust_particles_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/dust-particles.schema.json"], valid=False))
def test_engines_dust_particles_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_blasting_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/blasting.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/blasting.schema.json"], valid=True))
def test_engines_blasting_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/blasting.schema.json"], valid=False))
def test_engines_blasting_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_watershed_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/watershed.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/watershed.schema.json"], valid=True))
def test_engines_watershed_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/watershed.schema.json"], valid=False))
def test_engines_watershed_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_unet_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/unet.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/unet.schema.json"], valid=True))
def test_engines_unet_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/unet.schema.json"], valid=False))
def test_engines_unet_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_comminution_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/comminution.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/comminution.schema.json"], valid=True))
def test_engines_comminution_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/comminution.schema.json"], valid=False))
def test_engines_comminution_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_meta_model_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/meta-model.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/meta-model.schema.json"], valid=True))
def test_engines_meta_model_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/meta-model.schema.json"], valid=False))
def test_engines_meta_model_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_mincut_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/mincut.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/mincut.schema.json"], valid=True))
def test_engines_mincut_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/mincut.schema.json"], valid=False))
def test_engines_mincut_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-02")
def test_engines_volume_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("engines/volume.schema.json")


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/volume.schema.json"], valid=True))
def test_engines_volume_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["engines/volume.schema.json"], valid=False))
def test_engines_volume_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


ENGINES = [
    "des",
    "policies",
    "haulage",
    "lp",
    "routing",
    "il1-twin",
    "il2-twin",
    "granular",
    "gns",
    "traffic",
    "dust-lidar",
    "detector",
    "geotech",
    "forecasters",
    "swe",
    "fno",
    "plume",
    "dust-particles",
    "blasting",
    "watershed",
    "unet",
    "comminution",
    "meta-model",
    "mincut",
    "volume",
]  # spec 018 section 7.1 engine table (spec.md, integration note of 2026-10-07)


@pytest.mark.req("DC-018-02")
def test_exactly_the_25_engine_schemas_of_section_7_1_exist() -> None:
    found = sorted(
        p.name.removesuffix(".schema.json") for p in (kit.ROOT / "contracts" / "engines").glob("*.schema.json")
    )
    assert found == sorted(ENGINES)


@pytest.mark.req("DC-018-02")
@pytest.mark.parametrize("engine", ENGINES)
def test_engine_schema_defines_input_and_output_messages_tagged_with_the_engine_id(engine: str) -> None:
    # FR-018-38: a request carries engine id, engine version and an input object; the answer is validated against the
    # output schema. Each file holds $defs/input and $defs/output discriminated by `kind` (draft note, spec 018).
    schema = kit.load_promoted(f"engines/{engine}.schema.json")
    for kind in ("input", "output"):
        props = schema["$defs"][kind]["properties"]
        assert props["kind"]["const"] == kind
        assert props["engine"]["const"] == engine
        assert "engine_version" in props

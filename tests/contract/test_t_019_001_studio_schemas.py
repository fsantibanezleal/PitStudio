"""T-019-001: tool-map and studio-index schemas, generated types, toolmap.yaml and consumed-file schema checks.

Requirements: DC-019-02, DC-019-03, FR-019-38.

Spec: specs/019-web-studio/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/toolmap.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/toolmap.schema.json)
- `contracts/studio-index.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/studio-index.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "019-web-studio"


@pytest.mark.req("DC-019-02")
def test_toolmap_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("toolmap.schema.json")


@pytest.mark.req("DC-019-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["toolmap.schema.json"], valid=True))
def test_toolmap_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-019-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["toolmap.schema.json"], valid=False))
def test_toolmap_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-019-02")
def test_toolmap_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["toolmap.schema.json"])


@pytest.mark.req("DC-019-02")
def test_toolmap_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["toolmap.schema.json"])


@pytest.mark.req("DC-019-03")
def test_studio_index_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("studio-index.schema.json")


@pytest.mark.req("DC-019-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["studio-index.schema.json"], valid=True))
def test_studio_index_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-019-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["studio-index.schema.json"], valid=False))
def test_studio_index_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-019-03")
def test_studio_index_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["studio-index.schema.json"])


@pytest.mark.req("DC-019-03")
def test_studio_index_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["studio-index.schema.json"])


BAND_ORDER = ["scene", "physics", "sensors-synthetic-data", "training", "acceleration", "encoding", "web"]  # FR-019-02
TOOL_IDS_20 = [
    "openusd",
    "warp",
    "newton",
    "mujoco-warp",
    "physx-ovphysx",
    "ovrtx",
    "isaac-sim-replicator",
    "isaac-lab",
    "kit-usd-composer-explorer",
    "cosmos-reason-2",
    "pytorch",
    "onnx-runtime",
    "tensorrt",
    "nvenc-ffmpeg",
    "nsight-nvml",
    "threejs-r3f-3d-tiles",
    "rapier-webgpu-pyodide",
    "cuopt",
    "physicsnemo",
    "cosmos-predict-transfer",
]  # data-model 001 section 4.3 (17 studio tools + 3 evaluated-not-adopted)


def _toolmap() -> dict:
    return kit.load_yaml_strict(kit.ROOT / "studio" / "toolmap.yaml")


@pytest.mark.req("DC-019-02")
def test_toolmap_yaml_validates_against_the_promoted_schema() -> None:
    assert kit.validation_errors("toolmap.schema.json", "#", _toolmap()) == []


@pytest.mark.req("DC-019-02")
@pytest.mark.req("FR-019-38")
def test_toolmap_yaml_lists_each_of_the_20_ids_once_in_the_band_order() -> None:
    doc = _toolmap()
    assert [b["id"] for b in doc["bands"]] == BAND_ORDER
    listed = [t for b in doc["bands"] for t in b["tools"]]
    assert sorted(listed) == sorted(TOOL_IDS_20), "each of the 20 ids exactly once across the bands"


@pytest.mark.req("FR-019-38")
def test_toolmap_edges_name_only_listed_tools_and_no_tool_to_itself() -> None:
    doc = _toolmap()
    listed = {t for b in doc["bands"] for t in b["tools"]}
    assert doc["edges"], "the map declares handoff edges"
    for e in doc["edges"]:
        assert e["from"] in listed, f"edge {e} names a tool outside the map"
        assert e["to"] in listed, f"edge {e} names a tool outside the map"
        assert e["from"] != e["to"]


@pytest.mark.req("FR-019-38")
@pytest.mark.parametrize(
    "schema",
    ["tools.schema.json", "manifest.schema.json", "capabilities.schema.json"],
)
def test_consumed_file_schemas_reject_the_hostile_classes_of_fr_019_38(schema: str) -> None:
    # Consumed files: tool registry, web and published run manifests, capabilities (DC-001-01). The classes of FR-019-38
    # that a schema can state (unknown lane, ring, status or licence class; missing field; absolute path) are exercised
    # by the hand-built hostile examples of spec 001 whose keyword is enum, required or pattern.
    kit.assert_schema_promoted(schema)
    hostile = [
        e
        for e in kit.load_examples("001-contracts", [schema])
        if not e["valid"] and e["keyword"] in {"enum", "required", "pattern"}
    ]
    assert hostile, f"spec 001 holds no enum/required/pattern hostile example for {schema}"
    for e in hostile:
        kit.assert_hostile_example(e)

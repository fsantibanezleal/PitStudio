"""T-020-100: chart-series schema, example corpus and generated types.

Requirements: DC-020-05, FR-020-55, FR-020-56, FR-020-57, FR-020-10.

Spec: specs/020-web-knowledge/ (spec.md DC-020-05; the draft schema and the example corpus in contracts/,
`examples/index-chart-series.json`).

Oracle: the spec's own example corpus (every `valid` example is accepted, every hostile example is rejected at its stated
JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference implementation `jsonschema`), and, for generated
types, the Pydantic and TypeScript compilers. See tests/contract/_contract_kit.py for the exact assertions. The hostile
examples were written by hand from the rules (a chart needs its units, its producer label and its series; a value not run
needs its reason and carries no data; only the four colour maps of FR-020-10); none comes from running the reader.

Expected API of the implementation:
- `contracts/chart-series.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/chart-series.schema.json)
- `src/pitstudio/contracts/_generated/chart_series.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/chart-series.ts` (type-only, banner) from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs`.
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "020-web-knowledge"
SCHEMA = "chart-series.schema.json"
CHART_TYPES = ["line", "bar", "scatter", "ecdf", "raster", "section", "table"]


@pytest.mark.req("DC-020-05")
def test_chart_series_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted(SCHEMA)


@pytest.mark.req("DC-020-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, [SCHEMA], valid=True))
def test_chart_series_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-020-05")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, [SCHEMA], valid=False))
def test_chart_series_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-020-05")
def test_chart_series_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, [SCHEMA])


@pytest.mark.req("DC-020-05")
def test_chart_series_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, [SCHEMA])


@pytest.mark.req("FR-020-55")
def test_every_chart_type_of_the_enum_has_a_valid_example() -> None:
    schema = kit.load_promoted(SCHEMA)
    assert schema["properties"]["chart_type"]["enum"] == CHART_TYPES
    seen = {
        kit.read_json(e["path"])["chart_type"]
        for e in kit.load_examples(SPEC, [SCHEMA])
        if e["valid"] and kit.read_json(e["path"])["status"] == "ok"
    }
    assert seen == set(CHART_TYPES), f"chart types without a valid example: {sorted(set(CHART_TYPES) - seen)}"


@pytest.mark.req("FR-020-57")
def test_a_value_not_run_has_a_valid_example_with_its_reason_and_no_data() -> None:
    docs = [
        kit.read_json(e["path"])
        for e in kit.load_examples(SPEC, [SCHEMA])
        if e["valid"] and kit.read_json(e["path"])["status"] == "not-run"
    ]
    assert docs, "no valid not-run example"
    for doc in docs:
        assert doc["not_run_reason"]["en"] and doc["not_run_reason"]["es"]
        assert not {"series", "categories", "raster", "section", "table"} & doc.keys()


@pytest.mark.req("FR-020-10")
def test_the_colour_maps_are_the_four_of_fr_020_10_only() -> None:
    colour = kit.load_promoted(SCHEMA)["$defs"]["raster"]["properties"]["colour"]["properties"]["colormap"]
    assert colour["enum"] == ["viridis", "cividis", "inferno", "magma"]


@pytest.mark.req("FR-020-56")
def test_every_axis_and_every_producer_names_its_unit_and_its_label() -> None:
    defs = kit.load_promoted(SCHEMA)["$defs"]
    assert {"label", "unit"} <= set(defs["axis"]["required"])
    assert {"tool", "method", "version", "label"} == set(defs["producer"]["required"])


@pytest.mark.req("DC-020-05")
def test_the_hostile_corpus_covers_the_rules_that_matter() -> None:
    kit.assert_hostile_classes(
        SPEC,
        SCHEMA,
        ["required", "enum", "not", "pattern", "maxItems", "maximum", "const", "additionalProperties", "dependentRequired"],
    )


@pytest.mark.req("DC-020-05")
def test_the_published_manifest_has_the_chart_series_artefact_kind() -> None:
    kinds = kit.load_promoted("manifest.schema.json")["$defs"]["artefact_kind"]["enum"]
    assert "chart-series" in kinds

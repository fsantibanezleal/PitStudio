"""T-016-003: export parity-report schema, generated types and the manifest export fields.

Requirements: DC-016-03, DC-000-01.

Spec: specs/016-export-acceleration/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/export-parity-report.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/export-parity-report.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "016-export-acceleration"


@pytest.mark.req("DC-016-03")
def test_export_parity_report_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("export-parity-report.schema.json")


@pytest.mark.req("DC-016-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["export-parity-report.schema.json"], valid=True))
def test_export_parity_report_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-016-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["export-parity-report.schema.json"], valid=False))
def test_export_parity_report_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-016-03")
def test_export_parity_report_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["export-parity-report.schema.json"])


@pytest.mark.req("DC-016-03")
def test_export_parity_report_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["export-parity-report.schema.json"])


@pytest.mark.req("DC-000-01")
@pytest.mark.req("FR-016-11")
def test_manifest_schema_carries_every_export_field_of_fr_016_11() -> None:
    # FR-016-11: path, bytes, SHA-256, measured lane and lane measurements, asset host and release tag, budget class,
    # licence class, SPDX id, attribution, producer tool and stage, and the `performance` marker of the producing stage.
    m = kit.load_promoted("manifest.schema.json")
    artefact = m["$defs"]["artefact"]["properties"]
    wanted = {
        "path",
        "bytes",
        "sha256",
        "lane",
        "lane_measurements",
        "asset_host",
        "release_tag",
        "budget_class",
        "licence_class",
        "spdx",
        "attribution",
        "producer",
    }
    assert wanted <= set(artefact), f"manifest artefact lacks {sorted(wanted - set(artefact))}"
    assert {"tool", "stage"} <= set(m["$defs"]["artefact"]["properties"]["producer"].get("properties", {}))
    assert "performance" in m["$defs"]["stage"]["properties"]

"""T-012-002: fragment-split schema (fold file and group links) and generated types.

Requirements: DC-012-02.

Spec: specs/012-fragmentation/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/fragment-split.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/fragment-split.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "012-fragmentation"


@pytest.mark.req("DC-012-02")
def test_fragment_split_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("fragment-split.schema.json")


@pytest.mark.req("DC-012-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["fragment-split.schema.json"], valid=True))
def test_fragment_split_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-012-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["fragment-split.schema.json"], valid=False))
def test_fragment_split_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-012-02")
def test_fragment_split_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["fragment-split.schema.json"])


@pytest.mark.req("DC-012-02")
def test_fragment_split_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["fragment-split.schema.json"])

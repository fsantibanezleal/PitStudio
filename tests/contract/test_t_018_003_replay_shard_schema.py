"""T-018-003: replay shard header schema and generated types.

Requirements: DC-018-03.

Spec: specs/018-web-cases/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/replay-shard.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/replay-shard.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "018-web-cases"


@pytest.mark.req("DC-018-03")
def test_replay_shard_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("replay-shard.schema.json")


@pytest.mark.req("DC-018-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["replay-shard.schema.json"], valid=True))
def test_replay_shard_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["replay-shard.schema.json"], valid=False))
def test_replay_shard_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-03")
def test_replay_shard_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["replay-shard.schema.json"])


@pytest.mark.req("DC-018-03")
def test_replay_shard_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["replay-shard.schema.json"])

"""T-020-001: method registry schema, generated types and studio/methods.yaml (M1 to M23).

Requirements: DC-020-01, FR-020-19.

Spec: specs/020-web-knowledge/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/methods.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/methods.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "020-web-knowledge"


@pytest.mark.req("DC-020-01")
def test_methods_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("methods.schema.json")


@pytest.mark.req("DC-020-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["methods.schema.json"], valid=True))
def test_methods_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-020-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["methods.schema.json"], valid=False))
def test_methods_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-020-01")
def test_methods_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["methods.schema.json"])


@pytest.mark.req("DC-020-01")
def test_methods_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["methods.schema.json"])


def _valid_methods() -> dict:
    ex = next(e for e in kit.load_examples(SPEC, ["methods.schema.json"]) if e["valid"])
    return kit.read_json(ex["path"])


def _errors(doc: dict) -> set[tuple[str, str]]:
    return set(kit.validation_errors("methods.schema.json", "#", doc))


def _mut_drop_last(d: dict) -> None:
    d["methods"].pop()


def _mut_extra_method(d: dict) -> None:
    d["methods"].append({**d["methods"][0], "id": "M24"})


def _mut_other_id(d: dict) -> None:
    d["methods"][22]["id"] = "M24"


def _mut_tier(d: dict) -> None:
    d["methods"][0]["tiers"] = ["gold"]


def _mut_lane(d: dict) -> None:
    d["methods"][0]["lanes"] = ["edge"]


def _mut_licence(d: dict) -> None:
    d["methods"][0]["spdx"] = ["not an spdx id"]


def _mut_no_criterion(d: dict) -> None:
    learned = next(m for m in d["methods"] if m["learned"])
    del learned["criterion"]


@pytest.mark.req("FR-020-19")
@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_mut_drop_last, id="lacks-M23"),
        pytest.param(_mut_extra_method, id="24-entries"),
        pytest.param(_mut_other_id, id="holds-another-id"),
        pytest.param(_mut_tier, id="tier-outside-enum"),
        pytest.param(_mut_lane, id="lane-outside-enum"),
        pytest.param(_mut_licence, id="licence-outside-enum"),
        pytest.param(_mut_no_criterion, id="learned-method-without-criterion"),
    ],
)
def test_method_registry_rejects_each_failure_class_of_fr_020_19(mutate) -> None:
    # hand: one mutated registry per failure class (plan 020 test strategy); the unmutated document is the control.
    doc = _valid_methods()
    assert _errors(doc) == set()
    mutate(doc)
    assert _errors(doc), "the mutated registry must be rejected"


def _methods_yaml() -> dict:
    return kit.load_yaml_strict(kit.ROOT / "studio" / "methods.yaml")


@pytest.mark.req("DC-020-01")
def test_methods_yaml_validates_against_the_promoted_schema() -> None:
    assert kit.validation_errors("methods.schema.json", "#", _methods_yaml()) == []


@pytest.mark.req("FR-020-19")
def test_methods_yaml_holds_exactly_m1_to_m23_once_each() -> None:
    ids = [m["id"] for m in _methods_yaml()["methods"]]
    assert ids == [f"M{i}" for i in range(1, 24)]


@pytest.mark.req("DC-020-01")
def test_methods_yaml_learned_flags_and_criteria_follow_the_owning_specs() -> None:
    # Oracle: the spec's hand-built valid registry (built from plan section 7 and the SC rows of the owning specs).
    want = {m["id"]: m for m in _valid_methods()["methods"]}
    got = {m["id"]: m for m in _methods_yaml()["methods"]}
    assert {i for i, m in got.items() if m["learned"]} == {i for i, m in want.items() if m["learned"]}
    for mid, m in got.items():
        if not m["learned"]:
            continue
        crit = m["criterion"]
        assert (crit["spec"], crit["requirement"]) == (
            want[mid]["criterion"]["spec"],
            want[mid]["criterion"]["requirement"],
        )
        spec_md = (kit.ROOT / "specs" / crit["spec"] / "spec.md").read_text(encoding="utf-8")
        assert f"| {crit['requirement']} |" in spec_md, (
            f"{mid}: {crit['requirement']} is not a row of specs/{crit['spec']}/spec.md"
        )

"""T-009-010 - FR-009-01, FR-009-03: the five perception classes, the boulder rule and the three default SDG arms.

Oracles (independent of the code under test):
- FR-009-01: the five (id, name) pairs typed out from the spec (and equal to the `categories` of the spec's own valid
  COCO contract example); hand calculation of the boulder rule from plan 009's test strategy: a tagged rock of 1.2 m and
  one of 0.9 m with `x_os` = 1.0 m give `boulder` and "not a class"; the boundary 1.0 m itself is a boulder (the spec
  says "longest axis >= x_os"); a smaller `x_os` of 0.5 m turns the 0.9 m rock into a boulder.
- FR-009-03: the three arms (structured pit, structured crusher, unstructured pit) of 10,000 images each, typed out from
  the spec; the recipe is checked against the draft/promoted JSON schema `sdg-randomisation.schema.json` with the
  reference validator `jsonschema` (Draft 2020-12); the unstructured arm reuses the seeds and layouts of the structured
  pit training split (hand-built fixture below).

Expected public API (package `pitstudio_pipeline`, under `pipeline/src/`):

module `pitstudio_pipeline.perception.classes`
    CLASSES: tuple[tuple[int, str], ...]
        exactly ((1, "haul_truck"), (2, "shovel"), (3, "light_vehicle"), (4, "person"), (5, "boulder")).
    class_id(name: str) -> int                      1..5; ValueError (message contains "name") for an unknown name.
    classify_prim(semantic_tag: str, longest_axis_m: float, *, x_os_m: float = 1.0) -> str | None
        semantic_tag in {"haul_truck", "shovel", "light_vehicle", "person"} returns that name (dimensions ignored);
        semantic_tag "rock" returns "boulder" if longest_axis_m >= x_os_m, else None (a smaller rock is not a class);
        any other tag (terrain, bench, haul_road, ...) returns None.
        ValueError, whose message contains the argument name, if longest_axis_m or x_os_m is NaN/inf,
        longest_axis_m < 0 or x_os_m <= 0.

module `pitstudio_pipeline.perception.recipe`
    default_recipe() -> dict
        A DC-009-03 document that validates against sdg-randomisation.schema.json; x_os_m 1.0, drying_time_min 60;
        its `arms` are the three default arms in the order structured pit, structured crusher, unstructured pit, each
        with image_count 10000; the unstructured arm has seed_source "structured-pit-train", the other two "own".
    resolve_arms(recipe: dict, structured_pit_train: Sequence[tuple[int, str]]) -> dict[tuple[str, str], ArmPlan]
        Keys (family, arm). ArmPlan has attributes `image_count: int`, `scenario_seeds: tuple[int, ...] | None`,
        `layout_ids: tuple[str, ...] | None`. `structured_pit_train` lists the (scenario_seed, layout_id) pairs of the
        structured pit training split. The unstructured pit plan holds exactly those seeds and layouts (same order);
        the structured plans hold None for both (they draw their own).
        ValueError if the recipe's unstructured arm has seed_source "own" (message contains "seed_source"), or lists a
        family/arm pair twice (message contains "duplicate").
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
from pitstudio_pipeline.perception import classes, recipe  # noqa: E402

FIVE = ((1, "haul_truck"), (2, "shovel"), (3, "light_vehicle"), (4, "person"), (5, "boulder"))  # FR-009-01
ARMS = [("pit", "structured", "own"), ("crusher", "structured", "own"), ("pit", "unstructured", "structured-pit-train")]


def _schema() -> dict:
    for p in (
        ROOT / "contracts" / "sdg-randomisation.schema.json",
        ROOT / "specs" / "009-perception" / "contracts" / "sdg-randomisation.schema.json",
    ):
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    raise AssertionError("sdg-randomisation.schema.json not found")


# ---------------------------------------------------------------- FR-009-01


@pytest.mark.req("FR-009-01")
def test_the_class_set_is_the_five_ids_one_to_five_in_order() -> None:
    assert tuple(classes.CLASSES) == FIVE
    assert [classes.class_id(n) for _, n in FIVE] == [1, 2, 3, 4, 5]


@pytest.mark.req("FR-009-01")
def test_the_class_set_equals_the_categories_of_the_contract_example() -> None:
    cats = kit.coco_doc()["categories"]
    assert tuple((c["id"], c["name"]) for c in cats) == tuple(classes.CLASSES)


@pytest.mark.req("FR-009-01")
@pytest.mark.parametrize("name", ["", "truck", "Haul_Truck", "rock", "boulder ", "トラック"])
def test_an_unknown_class_name_has_no_id(name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        classes.class_id(name)


@pytest.mark.req("FR-009-01")
def test_a_rock_of_1_2_m_is_a_boulder_and_one_of_0_9_m_is_not_at_the_default_limit() -> None:
    assert classes.classify_prim("rock", 1.2) == "boulder"
    assert classes.classify_prim("rock", 0.9) is None


@pytest.mark.req("FR-009-01")
def test_the_oversize_limit_itself_is_a_boulder_and_the_limit_is_a_parameter() -> None:
    assert classes.classify_prim("rock", 1.0, x_os_m=1.0) == "boulder"  # "longest axis >= x_os"
    assert classes.classify_prim("rock", 0.9, x_os_m=0.5) == "boulder"
    assert classes.classify_prim("rock", 1.2, x_os_m=2.0) is None


@pytest.mark.req("FR-009-01")
@pytest.mark.parametrize("tag", ["haul_truck", "shovel", "light_vehicle", "person"])
def test_machine_and_person_tags_map_to_their_own_class_whatever_their_size(tag: str) -> None:
    assert classes.classify_prim(tag, 0.01) == tag
    assert classes.classify_prim(tag, 50.0) == tag


@pytest.mark.req("FR-009-01")
@pytest.mark.parametrize("tag", ["terrain", "bench", "berm", "haul_road", "", "ROCK"])
def test_other_tags_are_not_perception_classes(tag: str) -> None:
    assert classes.classify_prim(tag, 3.0) is None


@pytest.mark.req("FR-009-01")
@pytest.mark.parametrize("axis", [float("nan"), float("inf"), float("-inf"), -0.1])
def test_a_bad_longest_axis_is_rejected(axis: float) -> None:
    with pytest.raises(ValueError, match="longest_axis_m"):
        classes.classify_prim("rock", axis)


@pytest.mark.req("FR-009-01")
@pytest.mark.parametrize("x_os", [0.0, -1.0, float("nan"), float("inf")])
def test_a_bad_oversize_limit_is_rejected(x_os: float) -> None:
    with pytest.raises(ValueError, match="x_os_m"):
        classes.classify_prim("rock", 1.0, x_os_m=x_os)


# ---------------------------------------------------------------- FR-009-03


@pytest.mark.req("FR-009-03")
def test_the_default_recipe_requests_three_arms_of_10000_images() -> None:
    r = recipe.default_recipe()
    assert [(a["family"], a["arm"], a["seed_source"]) for a in r["arms"]] == ARMS
    assert [a["image_count"] for a in r["arms"]] == [10000, 10000, 10000]
    assert sum(a["image_count"] for a in r["arms"]) == 30000  # 3 x 10,000, hand calculation
    assert r["x_os_m"] == 1.0
    assert r["drying_time_min"] == 60


@pytest.mark.req("FR-009-03")
def test_the_default_recipe_validates_against_the_sdg_randomisation_schema() -> None:
    from jsonschema import Draft202012Validator

    errors = sorted(Draft202012Validator(_schema()).iter_errors(recipe.default_recipe()), key=str)
    assert errors == []


@pytest.mark.req("FR-009-03")
def test_the_default_arms_equal_those_of_the_contract_example() -> None:
    assert recipe.default_recipe()["arms"] == kit.example("sdg-randomisation.valid.json")["arms"]


@pytest.mark.req("FR-009-03")
def test_the_unstructured_arm_reuses_the_seeds_and_layouts_of_the_structured_pit_training_split() -> None:
    train = [(4211, "layout-0042"), (17, "layout-0003"), (9001, "layout-0042"), (5, "layout-0777")]
    plans = recipe.resolve_arms(recipe.default_recipe(), train)
    assert set(plans) == {("pit", "structured"), ("crusher", "structured"), ("pit", "unstructured")}
    u = plans[("pit", "unstructured")]
    assert u.image_count == 10000
    assert u.scenario_seeds == (4211, 17, 9001, 5)
    assert u.layout_ids == ("layout-0042", "layout-0003", "layout-0042", "layout-0777")
    for key in (("pit", "structured"), ("crusher", "structured")):
        assert plans[key].image_count == 10000
        assert plans[key].scenario_seeds is None
        assert plans[key].layout_ids is None


@pytest.mark.req("FR-009-03")
def test_an_unstructured_arm_that_draws_its_own_seeds_is_refused() -> None:
    r = copy.deepcopy(recipe.default_recipe())
    r["arms"][2]["seed_source"] = "own"
    with pytest.raises(ValueError, match="seed_source"):
        recipe.resolve_arms(r, [(1, "layout-0001")])


@pytest.mark.req("FR-009-03")
def test_a_family_arm_pair_listed_twice_is_refused() -> None:
    r = copy.deepcopy(recipe.default_recipe())
    r["arms"][1] = copy.deepcopy(r["arms"][0])
    with pytest.raises(ValueError, match="duplicate"):
        recipe.resolve_arms(r, [(1, "layout-0001")])

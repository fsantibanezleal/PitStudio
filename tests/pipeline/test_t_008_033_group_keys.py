# ruff: noqa: E501, PT018
"""T-008-033: group keys of the synthetic types, terrain spatial blocks, and the de Wit series as one unsplit group.

Requirements: FR-008-31, FR-008-27.

Spec: specs/008-data-pipeline/spec.md FR-008-31 (DES cycles -> scenario seed; Voight creep series -> event seed; muck-pile
renders -> muck-pile id; procedural terrain -> pit layout id; SDG and sensor sets -> scene seed; real terrain tiles ->
(project, spatial block) with the block size declared in the recipe; the single real slope-failure series is one group, used
only descriptively, never split) and FR-008-27 (every record in exactly one group; every split at group level, committed in a
file valid against `contracts/split.schema.json`).

Oracle: the group-key table of FR-008-31 (which record field defines each key); integer floor division for the spatial block
(block = (x // size, y // size) for integer-valued coordinates and block sizes, so no floating-point doubt); hand-built record
sets such as the spec's own split example (10 scenario seeds x 2 shifts).

Expected API of the implementation (module `pitstudio_pipeline.splits`):
- `group_key(rule, record, *, block_size_m=None) -> str` where `record` is a mapping with the field of the rule:
  `scenario-seed` -> `scenario_seed`, `event-seed` -> `event_seed`, `muck-pile-id` -> `muck_pile_id`, `pit-layout-id` ->
  `pit_layout_id`, `scene-seed` -> `scene_seed`, `project-spatial-block` -> `project`, `x`, `y` (metres, with
  `block_size_m > 0`), `single-group` -> no field. Equal keys iff equal defining values; other fields never matter. A missing
  field, an unknown rule, a missing / non-positive / non-finite block size or a non-finite coordinate raises an exception.
- `build_split(dataset_id, version, kind, rule, records, *, seed=None, n_folds=5, block_size_m=None) -> dict`: `records` is a
  list of mappings with an `id` (the split record id) and the key fields; returns a document valid against the split schema:
  one group per key (id = the key), every record in exactly one group, `method` `seeded-greedy-grouped-kfold` with `n_folds`
  folds (greedy rule of FR-008-30 on record counts; the test list holds the fold's records and the train pool all the others),
  except for `single-group`, which gives one group, `method: none`, `seed: null` and no folds whatever `seed` and `n_folds`
  are. Duplicate record ids, an empty record list, an invalid record id, fewer groups than folds raise an exception.
"""

from __future__ import annotations

from pathlib import Path

import _p008_kit as kit
import pytest
from pitstudio_pipeline.splits import build_split, group_key, write_split

# isort: split
from hypothesis import (
    assume,
    given,
    settings,
)
from hypothesis import strategies as st

SEEDED = {
    "scenario-seed": "scenario_seed",
    "event-seed": "event_seed",
    "muck-pile-id": "muck_pile_id",
    "pit-layout-id": "pit_layout_id",
    "scene-seed": "scene_seed",
}


@pytest.mark.req("FR-008-31")
@pytest.mark.parametrize(("rule", "field"), list(SEEDED.items()))
def test_seeded_rules_key_on_their_field_only(rule: str, field: str) -> None:
    a = {"id": "r1", field: 101, "other": "x", "shift": 1}
    same = {"id": "r2", field: 101, "other": "y", "shift": 2}
    different = {"id": "r3", field: 102, "other": "x", "shift": 1}
    assert group_key(rule, a) == group_key(rule, same)
    assert group_key(rule, a) != group_key(rule, different)
    assert isinstance(group_key(rule, a), str)


@pytest.mark.req("FR-008-31")
@pytest.mark.parametrize(("rule", "field"), list(SEEDED.items()))
def test_each_rule_ignores_the_fields_of_the_other_rules(rule: str, field: str) -> None:
    others = {f: 999 for f in SEEDED.values() if f != field}
    assert group_key(rule, {"id": "a", field: 5, **others}) == group_key(rule, {"id": "b", field: 5})


@pytest.mark.req("FR-008-31")
@pytest.mark.parametrize("rule", [*SEEDED, "project-spatial-block"])
def test_missing_field_and_unknown_rule_are_rejected(rule: str) -> None:
    with pytest.raises(Exception):  # noqa: B017, PT011  (the error class is not fixed by the spec)
        group_key(rule, {"id": "r"}, block_size_m=100.0)
    with pytest.raises(Exception):  # noqa: B017, PT011
        group_key("by-vibes", {"id": "r", "scenario_seed": 1})


# ------------------------------------------------------------------------------------------------ spatial blocks
def tile(project: str, x: float, y: float) -> dict:
    return {"id": "t", "project": project, "x": x, "y": y}


@pytest.mark.req("FR-008-31")
@pytest.mark.parametrize(
    ("p1", "p2", "same"),
    [
        ((0.0, 0.0), (99.0, 99.0), True),
        ((0.0, 0.0), (100.0, 0.0), False),
        ((0.0, 0.0), (0.0, 100.0), False),
        ((-1.0, 0.0), (0.0, 0.0), False),  # floor: block -1 versus block 0
        ((-100.0, -100.0), (-1.0, -1.0), True),
        ((-101.0, 0.0), (-100.0, 0.0), False),
        ((150.0, 250.0), (199.0, 299.0), True),
    ],
)
def test_spatial_block_edges_use_floor_division(p1: tuple, p2: tuple, same: bool) -> None:
    k1 = group_key("project-spatial-block", tile("bingham", *p1), block_size_m=100.0)
    k2 = group_key("project-spatial-block", tile("bingham", *p2), block_size_m=100.0)
    assert (k1 == k2) is same


@pytest.mark.req("FR-008-31")
def test_the_project_is_part_of_the_key() -> None:
    a = group_key("project-spatial-block", tile("bingham", 5.0, 5.0), block_size_m=100.0)
    b = group_key("project-spatial-block", tile("hambach", 5.0, 5.0), block_size_m=100.0)
    assert a != b


@pytest.mark.req("FR-008-31")
@settings(max_examples=200, deadline=None)
@given(
    st.integers(-10_000, 10_000),
    st.integers(-10_000, 10_000),
    st.integers(-10_000, 10_000),
    st.integers(-10_000, 10_000),
    st.sampled_from([1, 7, 50, 100, 256]),
)
def test_block_key_equality_is_equality_of_the_integer_blocks(x1: int, y1: int, x2: int, y2: int, size: int) -> None:
    k1 = group_key("project-spatial-block", tile("p", float(x1), float(y1)), block_size_m=float(size))
    k2 = group_key("project-spatial-block", tile("p", float(x2), float(y2)), block_size_m=float(size))
    assert (k1 == k2) == ((x1 // size, y1 // size) == (x2 // size, y2 // size))


@pytest.mark.req("FR-008-31")
@pytest.mark.parametrize("size", [None, 0.0, -5.0, float("nan"), float("inf")])
def test_block_size_must_be_declared_positive_and_finite(size: float | None) -> None:
    with pytest.raises(Exception):  # noqa: B017, PT011
        group_key("project-spatial-block", tile("p", 1.0, 1.0), block_size_m=size)


@pytest.mark.req("FR-008-31")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_coordinates_are_rejected(bad: float) -> None:
    with pytest.raises(Exception):  # noqa: B017, PT011
        group_key("project-spatial-block", tile("p", bad, 1.0), block_size_m=100.0)
    with pytest.raises(Exception):  # noqa: B017, PT011
        group_key("project-spatial-block", tile("p", 1.0, bad), block_size_m=100.0)


# ------------------------------------------------------------------------------------------------ split documents
def des_records() -> list[dict]:
    return [{"id": f"seed-{s}-shift-{j}", "scenario_seed": s} for s in range(101, 111) for j in (1, 2)]


@pytest.mark.req("FR-008-27")
def test_scenario_seed_split_has_one_group_per_seed_and_group_level_folds(tmp_path: Path) -> None:
    doc = build_split("des-cycles-a1", "1", "synthetic", "scenario-seed", des_records(), seed=20261007, n_folds=5)
    assert kit.schema_errors("split.schema.json", doc) == []
    assert doc["group_key"] == {"rule": "scenario-seed"} and doc["dataset"] == {
        "id": "des-cycles-a1",
        "version": "1",
        "kind": "synthetic",
    }
    assert len(doc["groups"]) == 10 and all(len(g["members"]) == 2 for g in doc["groups"])
    assert sorted(m for g in doc["groups"] for m in g["members"]) == sorted(r["id"] for r in des_records())
    tests = [f["test"] for f in doc["folds"]]
    assert [len(t) for t in tests] == [4] * 5, "10 equal groups over 5 folds: 2 groups per fold"
    assert sorted(m for t in tests for m in t) == sorted(r["id"] for r in des_records())
    group_of = {m: g["id"] for g in doc["groups"] for m in g["members"]}
    for f in doc["folds"]:
        assert not ({group_of[m] for m in f["test"]} & {group_of[m] for m in f["train_pool"]})
        assert sorted(f["test"] + f["train_pool"]) == sorted(r["id"] for r in des_records())
    assert doc["membership_sha256"] == kit.canonical_membership_sha(doc["groups"], doc["folds"])
    write_split(doc, tmp_path / "s.json")
    write_split(
        build_split("des-cycles-a1", "1", "synthetic", "scenario-seed", des_records(), seed=20261007, n_folds=5),
        tmp_path / "t.json",
    )
    assert (tmp_path / "s.json").read_bytes() == (tmp_path / "t.json").read_bytes()


@pytest.mark.req("FR-008-27")
@pytest.mark.parametrize(("rule", "field"), list(SEEDED.items()))
def test_every_seeded_rule_builds_a_valid_split(rule: str, field: str) -> None:
    recs = [{"id": f"r{i}-{j}", field: i} for i in range(8) for j in range(3)]
    doc = build_split("some-set", "1", "synthetic", rule, recs, seed=3, n_folds=4)
    assert kit.schema_errors("split.schema.json", doc) == [] and len(doc["groups"]) == 8 and len(doc["folds"]) == 4


@pytest.mark.req("FR-008-31")
def test_spatial_block_split_never_puts_one_block_in_two_folds() -> None:
    recs = [
        {"id": f"t{x}-{y}", "project": "bingham", "x": float(x), "y": float(y)}
        for x in range(0, 600, 50)
        for y in range(0, 600, 50)
    ]
    doc = build_split("dem-tiles", "1", "real", "project-spatial-block", recs, seed=9, n_folds=5, block_size_m=200.0)
    assert kit.schema_errors("split.schema.json", doc) == [] and doc["group_key"] == {
        "rule": "project-spatial-block",
        "block_size_m": 200.0,
    }
    assert len(doc["groups"]) == 9, "600 m / 200 m = 3 blocks per axis"
    block_of = {r["id"]: (int(r["x"]) // 200, int(r["y"]) // 200) for r in recs}
    for f in doc["folds"]:
        assert not ({block_of[m] for m in f["test"]} & {block_of[m] for m in f["train_pool"]})


@pytest.mark.req("FR-008-31")
@pytest.mark.parametrize("seed", [None, 5])
@pytest.mark.parametrize("n_folds", [5, 2])
def test_the_dewit_series_is_one_unsplit_group(seed: int | None, n_folds: int) -> None:
    doc = build_split(
        "dewit-slope-failure",
        "1",
        "real",
        "single-group",
        [{"id": "dewit-displacement-series"}],
        seed=seed,
        n_folds=n_folds,
    )
    assert kit.schema_errors("split.schema.json", doc) == []
    assert len(doc["groups"]) == 1 and doc["groups"][0]["members"] == ["dewit-displacement-series"]
    assert doc["method"] == "none" and doc["seed"] is None and doc["folds"] == []


@pytest.mark.req("FR-008-27")
@pytest.mark.parametrize(
    "records",
    [
        [],
        [{"id": "a", "scenario_seed": 1}, {"id": "a", "scenario_seed": 2}],  # duplicate record id
        [{"id": "bad id", "scenario_seed": 1}],
        [{"id": "été", "scenario_seed": 1}],
        [{"id": "a"}],  # missing key field
        [{"id": "x" * 129, "scenario_seed": 1}],
    ],
    ids=["empty", "duplicate-id", "space-in-id", "unicode-id", "missing-field", "id-too-long"],
)
def test_hostile_record_sets_are_rejected(records: list[dict]) -> None:
    with pytest.raises(Exception):  # noqa: B017, PT011
        build_split("d", "1", "synthetic", "scenario-seed", records, seed=1, n_folds=2)


@pytest.mark.req("FR-008-27")
def test_fewer_groups_than_folds_is_rejected() -> None:
    with pytest.raises(Exception):  # noqa: B017, PT011
        build_split(
            "d",
            "1",
            "synthetic",
            "scenario-seed",
            [{"id": f"r{i}", "scenario_seed": i % 3} for i in range(9)],
            seed=1,
            n_folds=5,
        )


@pytest.mark.req("FR-008-27")
@settings(max_examples=60, deadline=None)
@given(st.lists(st.integers(0, 40), min_size=5, max_size=60), st.integers(0, 2**32 - 1), st.integers(2, 5))
def test_every_record_is_in_exactly_one_group_and_one_test_list(seeds: list[int], seed: int, n_folds: int) -> None:
    assume(len(set(seeds)) >= n_folds)
    recs = [{"id": f"r{i}", "scenario_seed": s} for i, s in enumerate(seeds)]
    doc = build_split("p", "1", "synthetic", "scenario-seed", recs, seed=seed, n_folds=n_folds)
    ids = sorted(r["id"] for r in recs)
    assert sorted(m for g in doc["groups"] for m in g["members"]) == ids
    assert sorted(m for f in doc["folds"] for m in f["test"]) == ids
    assert len(doc["groups"]) == len(set(seeds))
    assert len(doc["folds"]) == n_folds and all(f["test"] for f in doc["folds"])

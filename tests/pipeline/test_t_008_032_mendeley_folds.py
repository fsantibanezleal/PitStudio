# ruff: noqa: E501, PT011, PT018
"""T-008-032: seeded greedy grouped 5-fold of the Mendeley set (48 originals per fold, originals-only tests, four-version
training pools, byte-identical reproduction) and refusal of tampered split files by every consumer.

Requirements: FR-008-30, FR-008-47, P-008-07.

Spec: specs/008-data-pipeline/spec.md FR-008-30 (order the groups by a seeded permutation, sort stably by size descending,
give each group to the fold with the fewest originals so far, lowest index on ties; test lists hold only the originals
001-240 of their groups; the training pool holds all four versions of the originals of the other folds' groups; any
validation subset carved from a pool is by group), FR-008-47 (`SplitIntegrityError` naming the first offending record when the
schema fails, the membership SHA-256 differs from the lists, a record is in two test lists, or a group is in both the test
list and the training pool of one fold) and P-008-07 (hand calculation: the 21-original group goes to fold 0, which then takes
9 groups of 3; the two 6-original groups go to folds 1 and 2, which take 14 groups of 3 each; folds 3 and 4 take 16: group counts
10, 15, 15, 16, 16 for any seed).

Oracle: the hand calculation of P-008-07, re-checked here by an independent simulation written in the test (the greedy rule on
the hand-calculated group sizes gives loads 48 x 5 and the counts above for any permutation); the group sizes and group
membership from `_p008_kit.py`; the RFC 8785 digest computed in the kit; the spec's own valid split example
(`contracts/examples/split.valid.json`) for the tamper tests.

Expected API of the implementation (module `pitstudio_pipeline.splits`):
- `build_mendeley_split(seed, *, links=None, files=None) -> dict` as in test_t_008_030; `seed` is an integer in
  0 .. 2**63 - 1, anything else raises `ValueError` or `TypeError`; folds[i] = `{"index": i, "test": [...], "train_pool": [...]}`.
- `write_split(doc, path) -> None` (canonical, deterministic file) and `load_split(path) -> dict`: parses and checks a split
  file; raises `pitstudio_pipeline.errors.SplitIntegrityError` (attribute `record`, the first offending record id or None; also
  named in `str(exc)`) for the four conditions above and for a file that is not valid JSON; returns the document otherwise.
- `carve_validation(doc, fold, *, fraction, seed) -> dict`: `{"train": [...], "validation": [...]}` file numbers partitioning
  the fold's training pool BY GROUP (a group is wholly in one side); `0 < fraction < 1` else `ValueError`.
"""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path

import _p008_kit as kit
import pytest
from pitstudio_pipeline.errors import SplitIntegrityError
from pitstudio_pipeline.splits import build_mendeley_split, carve_validation, load_split, write_split

# isort: split
from hypothesis import given, settings
from hypothesis import strategies as st

GROUP = {k: kit.mendeley_group_of(k) for k in range(1, 961)}
EXPECTED_COUNTS = [10, 15, 15, 16, 16]


def ids(xs) -> list[int]:
    return [int(x) for x in xs]


def simulate_greedy(seed: int) -> tuple[list[int], list[int]]:
    """An independent simulation of the greedy rule of FR-008-30 on the hand-calculated group sizes (loads, group counts)."""
    sizes: dict[int, int] = {}
    for k in range(1, 241):
        sizes[GROUP[k]] = sizes.get(GROUP[k], 0) + 1
    order = sorted(sizes)
    random.Random(seed).shuffle(order)
    order.sort(key=lambda g: -sizes[g])  # stable
    load, count = [0] * 5, [0] * 5
    for g in order:
        f = min(range(5), key=lambda i: (load[i], i))
        load[f] += sizes[g]
        count[f] += 1
    return load, count


@pytest.mark.req("P-008-07")
@pytest.mark.parametrize("seed", [0, 1, 7, 12345, 2**32 - 1])
def test_hand_calculation_is_seed_independent(seed: int) -> None:
    assert simulate_greedy(seed) == ([48] * 5, EXPECTED_COUNTS)


# ------------------------------------------------------------------------------------------------ P-008-07 / FR-008-30
def check_folds(doc: dict, seed: int) -> None:
    assert kit.schema_errors("split.schema.json", doc) == []
    assert doc["method"] == "seeded-greedy-grouped-kfold" and doc["seed"] == seed
    folds = doc["folds"]
    assert [f["index"] for f in folds] == [0, 1, 2, 3, 4]
    tests = [ids(f["test"]) for f in folds]
    assert [len(t) for t in tests] == [48] * 5
    flat = [k for t in tests for k in t]
    assert sorted(flat) == list(range(1, 241)), (
        "tests are pairwise disjoint, originals only, every original exactly once"
    )
    fold_groups = [{GROUP[k] for k in t} for t in tests]
    assert [len(g) for g in fold_groups] == EXPECTED_COUNTS
    assert all(not (fold_groups[i] & fold_groups[j]) for i in range(5) for j in range(i + 1, 5))
    assert 32 in fold_groups[0]
    assert {29, 59} <= fold_groups[1] | fold_groups[2] and not (
        {29, 59} & (fold_groups[0] | fold_groups[3] | fold_groups[4])
    )
    for f, t, g in zip(folds, tests, fold_groups, strict=True):
        originals_of_groups = {k for k in range(1, 241) if GROUP[k] in g}
        assert set(t) == originals_of_groups, "the test list holds every original of its groups"
        pool = set(ids(f["train_pool"]))
        assert len(pool) == len(f["train_pool"]) == 960 - 4 * 48
        assert pool == {k for k in range(1, 961) if GROUP[k] not in g}, (
            "all four versions of the other folds' originals"
        )
        assert not (pool & set(t)) and not ({GROUP[k] for k in pool} & g)
    assert doc["membership_sha256"] == kit.canonical_membership_sha(doc["groups"], doc["folds"])


@pytest.mark.req("FR-008-30")
def test_default_seed_split_satisfies_every_fold_property() -> None:
    check_folds(build_mendeley_split(0), 0)


@pytest.mark.req("P-008-07")
@settings(max_examples=30, deadline=None)
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_fold_properties_hold_for_any_seed_and_the_seed_reproduces_the_file_byte_for_byte(
    seed: int, tmp_path_factory
) -> None:
    doc = build_mendeley_split(seed)
    check_folds(doc, seed)
    d = tmp_path_factory.mktemp("seed")
    write_split(doc, d / "a.json")
    write_split(build_mendeley_split(seed), d / "b.json")
    assert (d / "a.json").read_bytes() == (d / "b.json").read_bytes()


@pytest.mark.req("P-008-07")
def test_the_seed_changes_the_assignment_of_the_3_original_groups() -> None:
    assignments = set()
    for seed in range(8):
        doc = build_mendeley_split(seed)
        assignments.add(tuple(tuple(sorted(ids(f["test"]))) for f in doc["folds"]))
    assert len(assignments) > 1, "different seeds must be able to give different folds"


@pytest.mark.req("FR-008-30")
@pytest.mark.parametrize("seed", [-1, -(2**40), 2**63, 1.5, "7", None, float("nan"), True])
def test_hostile_seeds_are_rejected(seed: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        build_mendeley_split(seed)  # type: ignore[arg-type]


@pytest.mark.req("FR-008-30")
def test_largest_valid_seed_is_accepted() -> None:
    assert build_mendeley_split(2**63 - 1)["seed"] == 2**63 - 1


@pytest.mark.req("FR-008-30")
@pytest.mark.parametrize("fold", [0, 3])
def test_validation_subset_is_carved_by_group(fold: int) -> None:
    doc = build_mendeley_split(5)
    pool = set(ids(doc["folds"][fold]["train_pool"]))
    out = carve_validation(doc, fold, fraction=0.1, seed=11)
    train, val = set(ids(out["train"])), set(ids(out["validation"]))
    assert train | val == pool and not (train & val) and val and train
    assert not ({GROUP[k] for k in train} & {GROUP[k] for k in val}), "a group is wholly in one side"
    assert not (val & set(ids(doc["folds"][fold]["test"]))) and not (train & set(ids(doc["folds"][fold]["test"])))
    again = carve_validation(doc, fold, fraction=0.1, seed=11)
    assert {k: sorted(ids(v)) for k, v in again.items()} == {k: sorted(ids(v)) for k, v in out.items()}


@pytest.mark.req("FR-008-30")
@pytest.mark.parametrize("fraction", [0.0, 1.0, -0.1, 1.5, float("nan")])
def test_hostile_validation_fraction_is_rejected(fraction: float) -> None:
    with pytest.raises(ValueError):
        carve_validation(build_mendeley_split(0), 0, fraction=fraction, seed=1)


# ------------------------------------------------------------------------------------------------ FR-008-47
SPEC_EXAMPLE = json.loads((kit.SPEC008 / "contracts" / "examples" / "split.valid.json").read_text(encoding="utf-8"))


def _rehash(doc: dict) -> dict:
    doc["membership_sha256"] = kit.canonical_membership_sha(doc["groups"], doc["folds"])
    return doc


def _load(doc: dict, tmp: Path):
    p = tmp / "s.json"
    p.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return load_split(p)


@pytest.mark.req("FR-008-47")
def test_untouched_split_files_load(tmp_path: Path) -> None:
    assert _load(copy.deepcopy(SPEC_EXAMPLE), tmp_path) == SPEC_EXAMPLE
    mendeley = build_mendeley_split(3)
    assert _load(mendeley, tmp_path) == mendeley


@pytest.mark.req("FR-008-47")
def test_schema_failures_are_refused(tmp_path: Path) -> None:
    for mutate in (
        lambda d: d.pop("seed"),
        lambda d: d.update(surprise=1),
        lambda d: d["groups"].clear(),
        lambda d: d.update(method="random"),
    ):
        doc = copy.deepcopy(SPEC_EXAMPLE)
        mutate(doc)
        with pytest.raises(SplitIntegrityError):
            _load(doc, tmp_path)


@pytest.mark.req("FR-008-47")
@pytest.mark.parametrize("content", [b"", b"{", b"\xef\xbb\xbf{}", b"[]", b"null", kit.payload(512, 3)])
def test_files_that_are_not_split_documents_are_refused(content: bytes, tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    p.write_bytes(content)
    with pytest.raises(SplitIntegrityError):
        load_split(p)


@pytest.mark.req("FR-008-47")
def test_membership_digest_mismatch_is_refused(tmp_path: Path) -> None:
    doc = copy.deepcopy(SPEC_EXAMPLE)
    sha = doc["membership_sha256"]
    doc["membership_sha256"] = ("0" if sha[0] != "0" else "1") + sha[1:]
    with pytest.raises(SplitIntegrityError):
        _load(doc, tmp_path)


@pytest.mark.req("FR-008-47")
def test_a_list_edited_without_updating_the_digest_is_refused(tmp_path: Path) -> None:
    doc = copy.deepcopy(SPEC_EXAMPLE)
    doc["folds"][0]["test"][0], doc["folds"][0]["train_pool"][0] = (
        doc["folds"][0]["train_pool"][0],
        doc["folds"][0]["test"][0],
    )
    with pytest.raises(SplitIntegrityError):
        _load(doc, tmp_path)


@pytest.mark.req("FR-008-47")
def test_a_record_in_two_test_lists_is_refused_naming_it(tmp_path: Path) -> None:
    doc = copy.deepcopy(SPEC_EXAMPLE)
    victim, sibling = doc["folds"][0]["test"][:2]  # both members of the group seed-104 in the spec example
    doc["folds"][1]["test"] += [
        victim,
        sibling,
    ]  # the whole group is now in two test lists (no group/pool overlap in fold 1)
    doc["folds"][1]["train_pool"] = [r for r in doc["folds"][1]["train_pool"] if r not in {victim, sibling}]
    with pytest.raises(SplitIntegrityError) as info:
        _load(_rehash(doc), tmp_path)
    assert info.value.record in {victim, sibling} and str(info.value.record) in str(info.value)


@pytest.mark.req("FR-008-47")
def test_a_group_in_both_the_test_list_and_the_pool_of_one_fold_is_refused(tmp_path: Path) -> None:
    doc = copy.deepcopy(SPEC_EXAMPLE)
    moved = doc["folds"][0]["test"].pop()  # one member of a two-member group leaves the test list for the pool
    doc["folds"][0]["train_pool"].append(moved)
    sibling = next(m for g in doc["groups"] if moved in g["members"] for m in g["members"] if m != moved)
    assert sibling in doc["folds"][0]["test"], "premise: the other member of the group stays in the test list"
    with pytest.raises(SplitIntegrityError) as info:
        _load(_rehash(doc), tmp_path)
    assert info.value.record in {moved, sibling}


@pytest.mark.req("FR-008-47")
def test_a_record_in_both_the_test_list_and_the_pool_is_refused(tmp_path: Path) -> None:
    doc = copy.deepcopy(SPEC_EXAMPLE)
    victim, sibling = doc["folds"][2]["test"][:2]
    doc["folds"][2]["train_pool"].append(victim)
    with pytest.raises(SplitIntegrityError) as info:
        _load(_rehash(doc), tmp_path)
    assert info.value.record in {victim, sibling}


@pytest.mark.req("FR-008-47")
def test_mendeley_split_tampered_after_writing_is_refused(tmp_path: Path) -> None:
    doc = build_mendeley_split(0)
    a_test = doc["folds"][0]["test"][0]
    doc["folds"][1]["test"][0] = a_test  # a record of fold 0 now also in fold 1
    with pytest.raises(SplitIntegrityError):
        _load(_rehash(doc), tmp_path)

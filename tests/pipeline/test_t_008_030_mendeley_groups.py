# ruff: noqa: E501, PT018
"""T-008-030: group keys and the split file; the Mendeley 72 groups from the 9 conservative links mapped to scenes; order invariances.

Requirements: FR-008-27, FR-008-28, P-008-06, P-008-08.

Spec: specs/008-data-pipeline/spec.md FR-008-27, FR-008-28 (group of file k = connected component of
g(k) = s(((k - 1) mod 240) + 1), with the scene s(k) = ((k - 1) mod 80) + 1, under the 9 links mapped to scenes; the group id
is the smallest original in the component; 72 groups; invalid links stop `s10_preprocess` with `links-invalid` and no split
file), P-008-06 (hand calculation) and P-008-08 (metamorphic relations); contract `contracts/split.schema.json` (DC-008-04).

Oracle: the hand calculation written out in `_p008_kit.py` (scene mapping of each link, e.g. 189 = 2 x 80 + 29 -> scene 29,
and the three multi-scene components {29, 39}, {32, 34, 36, 37, 38, 41, 49}, {59, 60} of 6, 21 and 6 originals; all other
69 scenes are singletons of 3 originals), cross-checked there by an independent union-find; the RFC 8785 canonical-JSON
digest of the split computed in the kit; the split JSON Schema.

Expected API of the implementation (module `pitstudio_pipeline.splits`; record ids are the file numbers, as strings or
integers, zero-padded or not: the tests read them with `int()`):
- `group_mendeley(files, links) -> dict[int, int]`: file number k (1..960) -> group id (an original number 1..240); `links` is a
  sequence of (a, b) original-file pairs.
- `build_mendeley_split(seed, *, links=None, files=None) -> dict`: the split document of DC-008-04 (default `links` = the
  nine links of FR-008-28, default `files` = 1..960); `groups[i] = {"id", "members"}` with every file 1..960 in exactly one
  group; `membership_sha256` over the canonical JSON of `{groups, folds}`.
- `write_mendeley_split(path, *, seed, links=None, files=None) -> dict`: validates the links, builds the split and writes it
  (UTF-8, no BOM, LF, deterministic) to `path`; on invalid links raises `pitstudio_pipeline.errors.LinksInvalid` (attribute
  `code == "links-invalid"`) BEFORE creating any file.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

import _p008_kit as kit
import pytest
from pitstudio_pipeline.errors import LinksInvalid
from pitstudio_pipeline.splits import build_mendeley_split, group_mendeley, write_mendeley_split

# isort: split
from hypothesis import given, settings
from hypothesis import strategies as st

LINKS = list(kit.MENDELEY_LINKS)
FILES = list(range(1, 961))


def normalised(doc: dict) -> tuple:
    groups = sorted((int(g["id"]), sorted(int(m) for m in g["members"])) for g in doc["groups"])
    folds = [
        (f["index"], sorted(int(t) for t in f["test"]), sorted(int(t) for t in f["train_pool"])) for f in doc["folds"]
    ]
    return groups, folds


# ------------------------------------------------------------------------------------------------ FR-008-28 / P-008-06
@pytest.mark.req("FR-008-28")
def test_every_file_gets_the_hand_calculated_group() -> None:
    got = group_mendeley(FILES, LINKS)
    assert got == {k: kit.mendeley_group_of(k) for k in FILES}


@pytest.mark.req("P-008-06")
def test_72_groups_with_the_hand_counted_sizes() -> None:
    got = group_mendeley(FILES, LINKS)
    assert len(set(got.values())) == 72
    originals = Counter(g for k, g in got.items() if k <= 240)
    assert sorted(originals.values(), reverse=True)[:3] == [21, 6, 6]
    assert sorted(originals.values())[:69] == [3] * 69
    assert originals[32] == 21 and originals[29] == 6 and originals[59] == 6
    files_per_group = Counter(got.values())
    assert (
        files_per_group[32] == 84
        and files_per_group[29] == 24
        and files_per_group[59] == 24
        and files_per_group[1] == 12
    )


@pytest.mark.req("P-008-06")
def test_group_is_constant_over_the_twelve_versions_of_a_file() -> None:
    got = group_mendeley(FILES, LINKS)
    for k in range(1, 81):
        assert len({got[k + 80 * i] for i in range(12)}) == 1, f"scene {k}"
    for k in range(1, 241):
        assert len({got[k + 240 * j] for j in range(4)}) == 1, f"original {k}"


@pytest.mark.req("FR-008-28")
def test_group_id_is_the_smallest_original_of_its_component() -> None:
    got = group_mendeley(FILES, LINKS)
    for gid in set(got.values()):
        members = [k for k, g in got.items() if g == gid]
        assert gid == min(k for k in members if k <= 240)


@pytest.mark.req("FR-008-28")
def test_extra_link_between_two_components_merges_them() -> None:
    got = group_mendeley(FILES, [*LINKS, (1, 240)])  # scene 1 and scene 80: both boundary files are valid link ends
    assert len(set(got.values())) == 71 and got[1] == got[240] == 1


# ------------------------------------------------------------------------------------------------ FR-008-27 split file
@pytest.mark.req("FR-008-27")
def test_split_document_is_valid_and_holds_the_groups_links_and_digest() -> None:
    doc = build_mendeley_split(0)
    assert kit.schema_errors("split.schema.json", doc) == []
    assert doc["dataset"]["id"] == "mendeley-78ht3pjsr4" and doc["dataset"]["kind"] == "real"
    assert doc["group_key"]["rule"] == "mendeley-original-component"
    assert {frozenset((int(link["a"]), int(link["b"]))) for link in doc["links"]} == {frozenset(p) for p in LINKS}
    groups = {int(g["id"]): sorted(int(m) for m in g["members"]) for g in doc["groups"]}
    assert len(groups) == 72
    assert sorted(k for ms in groups.values() for k in ms) == FILES, "every record in exactly one group"
    expected = {}
    for k in FILES:
        expected.setdefault(kit.mendeley_group_of(k), []).append(k)
    assert groups == expected
    assert doc["membership_sha256"] == kit.canonical_membership_sha(doc["groups"], doc["folds"])


@pytest.mark.req("FR-008-27")
def test_written_split_file_is_canonical_and_reproducible(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    doc = write_mendeley_split(a, seed=7)
    write_mendeley_split(b, seed=7)
    raw = a.read_bytes()
    assert raw == b.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw and raw.endswith(b"\n")
    assert json.loads(raw.decode("utf-8")) == doc
    assert kit.schema_errors("split.schema.json", json.loads(raw)) == []


# ------------------------------------------------------------------------------------------------ links-invalid
BAD_LINKS = {
    "below-range": (0, 5),
    "above-range": (5, 241),
    "spec012-example": (12, 241),
    "negative": (-3, 4),
    "self-link": (5, 5),
    "float": (1.5, 2),
    "string": ("3", 4),
    "none": (None, 4),
    "nan": (float("nan"), 3),
    "triple": (1, 2, 3),
    "single": (7,),
    "empty": (),
    "not-a-pair": "ab",
    "huge": (10**30, 2),
}


@pytest.mark.req("FR-008-28")
@pytest.mark.parametrize("bad", list(BAD_LINKS.values()), ids=list(BAD_LINKS))
def test_invalid_link_stops_with_links_invalid_and_writes_no_file(bad: object, tmp_path: Path) -> None:
    links = [*LINKS[:-1], bad]
    target = tmp_path / "splits" / "m.json"
    with pytest.raises(LinksInvalid) as info:
        write_mendeley_split(target, seed=0, links=links)
    assert info.value.code == "links-invalid"
    assert not target.exists() and kit.files_under(tmp_path) == []
    with pytest.raises(LinksInvalid):
        group_mendeley(FILES, links)


@pytest.mark.req("FR-008-28")
def test_links_that_are_not_a_list_of_pairs_are_invalid(tmp_path: Path) -> None:
    for links in (7, "29-39", {"a": 29, "b": 39}, [[]], [[29, 39], "x"]):  # (None means "the default nine links")
        with pytest.raises(LinksInvalid):
            write_mendeley_split(tmp_path / "x.json", seed=0, links=links)  # type: ignore[arg-type]
    assert kit.files_under(tmp_path) == []


# ------------------------------------------------------------------------------------------------ P-008-08
@pytest.mark.req("P-008-08")
@settings(max_examples=25, deadline=None)
@given(st.randoms(use_true_random=False))
def test_input_file_order_does_not_change_groups(rnd: random.Random) -> None:
    files = FILES[:]
    rnd.shuffle(files)
    assert group_mendeley(files, LINKS) == group_mendeley(FILES, LINKS)


@pytest.mark.req("P-008-08")
@settings(max_examples=15, deadline=None)
@given(st.randoms(use_true_random=False), st.integers(min_value=0, max_value=2**32 - 1))
def test_input_file_and_link_order_do_not_change_groups_or_folds(rnd: random.Random, seed: int) -> None:
    files, links = FILES[:], LINKS[:]
    rnd.shuffle(files)
    rnd.shuffle(links)
    links = [(b, a) if rnd.random() < 0.5 else (a, b) for a, b in links]  # also the direction of a link is irrelevant
    assert normalised(build_mendeley_split(seed, links=links, files=files)) == normalised(build_mendeley_split(seed))


@pytest.mark.req("P-008-08")
def test_a_redundant_link_inside_a_group_changes_nothing() -> None:
    base = group_mendeley(FILES, LINKS)
    redundant = [(32, 38), (41, 34), (49, 32), (39, 29), (60, 59), (1, 81), (5, 165), (197, 37), (240, 80)]
    for a, b in redundant:
        assert base[a] == base[b], "premise: the two files are already in one group"
        assert group_mendeley(FILES, [*LINKS, (a, b)]) == base
    assert group_mendeley(FILES, [*LINKS, *redundant]) == base


@pytest.mark.req("P-008-08")
def test_duplicating_every_link_changes_nothing() -> None:
    assert group_mendeley(FILES, LINKS + LINKS) == group_mendeley(FILES, LINKS)

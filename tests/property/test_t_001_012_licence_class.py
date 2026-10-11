"""T-001-012 · the licence-class lattice and the share-alike / reference-only rules: FR-001-18, FR-001-19, P-001-04.

Oracle: the rank table of data-model 5.4 transcribed by hand (public-domain 0 < open-no-attribution 1 < own 2 <
attribution 3 < share-alike 4 < display-only 5 < reference-only 6) and ``licence_class_of(inputs) = max_rank({own} U
{class(i)})`` evaluated here with ``max(..., key=rank)``; the checker rules are exercised on repository trees derived
from the committed clean fixture.

Expected API: ``pitstudio.contracts.licence_class_of(classes) -> str`` over an iterable of class names (an unknown
class raises ``ContractError``, a ``ValueError``); ``tools/check_contracts.py`` reports ``FR-001-18`` (declared class
differs from the computed one) and ``FR-001-19`` (reference-only input, mixed share-alike ids, share-alike class with a
different ``spdx``) findings with the pointer ``/artefacts/<i>`` of the offending artefact and its id in the message.
"""

from __future__ import annotations

import itertools
import random
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contract"))
import contract_support as cs

CLASSES = cs.LICENCE_ORDER
PROP = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
LISTS = st.lists(st.sampled_from(CLASSES), min_size=0, max_size=20)


def licence_class_of(classes: Any) -> str:
    from pitstudio.contracts import licence_class_of as impl

    return impl(classes)


def oracle(classes: list[str]) -> str:
    return max(["own", *classes], key=CLASSES.index)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-18 · the function
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-18")
def test_fr_001_18_no_inputs_gives_own() -> None:
    assert licence_class_of([]) == "own"
    assert licence_class_of(()) == "own"


@pytest.mark.req("FR-001-18")
@pytest.mark.parametrize(("a", "b"), list(itertools.product(CLASSES, CLASSES)), ids=lambda c: c)
def test_fr_001_18_rank_table_over_every_pair_of_classes(a: str, b: str) -> None:
    rank = {
        c: i
        for i, c in enumerate(
            [
                "public-domain",
                "open-no-attribution",
                "own",
                "attribution",
                "share-alike",
                "display-only",
                "reference-only",
            ]
        )
    }
    expected = max(["own", a, b], key=rank.__getitem__)
    assert licence_class_of([a, b]) == expected


@pytest.mark.req("FR-001-18")
@pytest.mark.parametrize(
    ("inputs", "expected"),
    [
        (["public-domain"], "own"),  # the artefact is at least ours
        (["open-no-attribution", "public-domain"], "own"),
        (["attribution"], "attribution"),
        (["public-domain", "attribution", "own"], "attribution"),
        (["attribution", "share-alike"], "share-alike"),
        (["share-alike", "display-only"], "display-only"),
        (["display-only", "reference-only", "public-domain"], "reference-only"),
        (["reference-only"] * 5, "reference-only"),
    ],
)
def test_fr_001_18_hand_worked_examples(inputs: list[str], expected: str) -> None:
    assert licence_class_of(inputs) == expected


@pytest.mark.req("FR-001-18")
@pytest.mark.parametrize(
    "bad",
    ["Own", "OWN", "", "reference_only", "public domain", "copyleft", None, 3, ("own",), True, b"own"],
    ids=repr,
)
def test_fr_001_18_unknown_or_malformed_classes_are_rejected(bad: Any) -> None:
    with pytest.raises((ValueError, TypeError)):  # ContractError (a ValueError) is the specified error
        licence_class_of([bad])
    with pytest.raises((ValueError, TypeError)):
        licence_class_of(["attribution", bad, "own"])


@pytest.mark.req("FR-001-18")
def test_fr_001_18_a_bare_string_is_not_a_list_of_classes_and_the_input_is_not_mutated() -> None:
    with pytest.raises((ValueError, TypeError)):
        licence_class_of("attribution")
    data = ["attribution", "public-domain"]
    licence_class_of(data)
    assert data == ["attribution", "public-domain"]


@pytest.mark.req("P-001-04")
@PROP
@given(classes=LISTS)
def test_p_001_04_matches_the_rank_oracle(classes: list[str]) -> None:
    assert licence_class_of(classes) == oracle(classes)


@pytest.mark.req("P-001-04")
@PROP
@given(classes=LISTS, seed=st.integers(0, 10**6))
def test_p_001_04_invariant_under_permutation(classes: list[str], seed: int) -> None:
    shuffled = list(classes)
    random.Random(seed).shuffle(shuffled)
    assert licence_class_of(shuffled) == licence_class_of(classes)


@pytest.mark.req("P-001-04")
@PROP
@given(classes=LISTS, repeat=st.integers(1, 4))
def test_p_001_04_idempotent_under_duplication(classes: list[str], repeat: int) -> None:
    assert licence_class_of(classes * repeat) == licence_class_of(classes)
    assert licence_class_of(classes + classes[:1]) == licence_class_of(classes)


@pytest.mark.req("P-001-04")
@PROP
@given(classes=LISTS, extra=st.sampled_from(CLASSES))
def test_p_001_04_adding_an_input_never_lowers_the_class(classes: list[str], extra: str) -> None:
    before, after = licence_class_of(classes), licence_class_of([*classes, extra])
    assert CLASSES.index(after) >= CLASSES.index(before)


@pytest.mark.req("P-001-04")
@PROP
@given(a=LISTS, b=LISTS)
def test_p_001_04_associative_union(a: list[str], b: list[str]) -> None:
    union = licence_class_of(a + b)
    assert union == max(licence_class_of(a), licence_class_of(b), key=CLASSES.index)
    assert union == licence_class_of([licence_class_of(a), licence_class_of(b)])


# ----------------------------------------------------------------------------------------------------------------
# FR-001-18 / FR-001-19 · the checker over repository trees
# ----------------------------------------------------------------------------------------------------------------
INDEX = "web/public/assets/manifest.json"
SOURCES = "data/sources.yaml"
SHA = "9" * 64


def source_entry(sid: str, spdx: str, cls: str) -> dict:
    entry: dict[str, Any] = {
        "id": sid,
        "kind": "real",
        "title": f"Example {sid}",
        "landing_url": f"https://example.org/data/{sid}",
        "access": "direct",
        "files": [{"url": f"https://example.org/data/{sid}/f.csv", "sha256": SHA, "bytes": 10, "kind": "table"}],
        "spdx": spdx,
        "licence_url": f"https://example.org/data/{sid}/licence",
        "licence_class": cls,
        "redistribution": "redistributable",
        "citation": "Example citation.",
        "card": f"data/cards/{sid}.md",
        "account": {"needed": False},
    }
    if cls in ("attribution", "share-alike"):
        entry["attribution"] = f"Example attribution for {sid}."
    return entry


def build(
    tmp: Path,
    inputs: list[dict],
    declared: str,
    spdx: str = "CC-BY-4.0",
    extra_sources: tuple = (),
    extra_artefacts: tuple = (),
) -> Path:
    root = cs.clean_repo(tmp)
    cs.edit_yaml(root, SOURCES, lambda d: d["sources"].extend(source_entry(*s) for s in extra_sources))

    def edit(doc: dict) -> None:
        for art in extra_artefacts:
            doc["artefacts"].append(art)
        a = doc["artefacts"][1]  # the table artefact (static)
        a["inputs"], a["licence_class"], a["spdx"] = inputs, declared, spdx
        if declared in ("attribution", "share-alike", "display-only", "reference-only"):
            a["attribution"] = "Example attribution text."
        else:
            a.pop("attribution", None)

    cs.edit_json(root, INDEX, edit)
    return root


def src(sid: str) -> dict:
    return {"id": sid, "sha256": SHA, "kind": "source"}


STATION = src("example-station-hourly")  # attribution (CC-BY-4.0) in the clean registry
LIDAR = src("example-lidar-tiles")  # public-domain
HAUL = src("example-haul-network")  # open-no-attribution (CC0-1.0)


@pytest.mark.req("FR-001-18")
@pytest.mark.parametrize(
    ("inputs", "declared", "spdx", "fails"),
    [
        ([], "own", "CC-BY-4.0", False),
        ([LIDAR], "own", "CC-BY-4.0", False),  # max(own, public-domain) = own
        ([HAUL], "own", "CC-BY-4.0", False),
        ([STATION], "attribution", "CC-BY-4.0", False),
        ([STATION, LIDAR, HAUL], "attribution", "CC-BY-4.0", False),
        ([STATION], "own", "CC-BY-4.0", True),  # computed attribution
        ([STATION], "public-domain", "CC-BY-4.0", True),
        ([], "attribution", "CC-BY-4.0", True),  # computed own
        ([], "public-domain", "CC-BY-4.0", True),
        ([LIDAR], "public-domain", "CC-BY-4.0", True),  # computed own, not public-domain
        ([HAUL], "open-no-attribution", "CC-BY-4.0", True),
        ([STATION], "share-alike", "CC-BY-4.0", True),
        ([], "display-only", "CC-BY-4.0", True),
    ],
)
def test_fr_001_18_checker_compares_the_declared_class_with_the_class_computed_from_the_inputs(
    tmp_path: Path, inputs: list[dict], declared: str, spdx: str, fails: bool
) -> None:
    res = cs.run_checker(build(tmp_path, inputs, declared, spdx))
    hits = res.at("FR-001-18", "/artefacts/1")
    assert bool(hits) is fails, (declared, [i["id"] for i in inputs], res.findings)
    for f in hits:
        assert "a2-encode-report" in f["message"]
        assert len(f["message"]) <= 300


@pytest.mark.req("FR-001-18")
def test_fr_001_18_the_class_of_an_artefact_input_comes_from_that_artefacts_own_record(tmp_path: Path) -> None:
    video_input = {"id": "a2-haul-clip", "sha256": SHA, "kind": "artefact"}  # class attribution, same document
    assert cs.run_checker(build(tmp_path / "a", [video_input], "attribution")).at("FR-001-18", "/artefacts/1") == []
    bad = cs.run_checker(build(tmp_path / "b", [video_input], "own"))
    assert bad.at("FR-001-18", "/artefacts/1")


@pytest.mark.req("FR-001-18")
def test_fr_001_18_the_clean_repository_has_no_lattice_finding(tmp_path: Path) -> None:
    res = cs.run_checker(cs.clean_repo(tmp_path))
    assert res.of("FR-001-18") == []
    assert res.of("FR-001-19") == []


@pytest.mark.req("FR-001-19")
def test_fr_001_19_an_input_of_class_reference_only_blocks_publication(tmp_path: Path) -> None:
    ref_art = {
        **{k: v for k, v in _table_artefact().items() if k != "attribution"},
        "id": "a2-proprietary-render",
        "path": "assets/media/render.json",
        "licence_class": "reference-only",
        "spdx": "LicenseRef-NvidiaProprietary",
        "attribution": "Proprietary runtime output.",
    }
    ref_input = {"id": "a2-proprietary-render", "sha256": SHA, "kind": "artefact"}
    root = build(tmp_path, [ref_input], "reference-only", "LicenseRef-NvidiaProprietary", extra_artefacts=(ref_art,))
    res = cs.run_checker(root)
    assert res.at("FR-001-19", "/artefacts/1"), res.findings  # declared class matches the computed one; still blocked
    assert res.at("FR-001-18", "/artefacts/1") == []


def _table_artefact() -> dict:
    import json

    doc = json.loads((cs.CLEAN_REPO / INDEX).read_text(encoding="utf-8"))
    return doc["artefacts"][1]


SA3 = ("example-sa-three", "CC-BY-SA-3.0", "share-alike")
SA4 = ("example-sa-four", "CC-BY-SA-4.0", "share-alike")


@pytest.mark.req("FR-001-19")
@pytest.mark.parametrize(
    ("inputs", "spdx", "fails"),
    [
        ([src("example-sa-four")], "CC-BY-SA-4.0", False),  # one share-alike input, same SPDX
        ([src("example-sa-four"), STATION], "CC-BY-SA-4.0", False),  # share-alike plus attribution: still one SA id
        ([src("example-sa-four"), src("example-sa-four")], "CC-BY-SA-4.0", False),
        ([src("example-sa-three"), src("example-sa-four")], "CC-BY-SA-4.0", True),  # two different share-alike ids
        ([src("example-sa-three"), src("example-sa-four")], "CC-BY-SA-3.0", True),
        ([src("example-sa-four")], "CC-BY-SA-3.0", True),  # artefact spdx differs from its share-alike input's
        ([src("example-sa-three")], "CC-BY-4.0", True),
        ([src("example-sa-four")], "Apache-2.0", True),
    ],
)
def test_fr_001_19_share_alike_inputs_fix_the_spdx_of_the_derivative(
    tmp_path: Path, inputs: list[dict], spdx: str, fails: bool
) -> None:
    root = build(tmp_path, inputs, "share-alike", spdx, extra_sources=(SA3, SA4))
    res = cs.run_checker(root)
    hits = res.at("FR-001-19", "/artefacts/1")
    assert bool(hits) is fails, (spdx, [i["id"] for i in inputs], res.findings)
    for f in hits:
        assert "a2-encode-report" in f["message"]
        assert len(f["message"]) <= 300
    assert res.at("FR-001-18", "/artefacts/1") == []  # the declared class share-alike is the computed one


@pytest.mark.req("FR-001-19")
def test_fr_001_19_non_share_alike_derivatives_are_not_subject_to_the_share_alike_spdx_rule(tmp_path: Path) -> None:
    res = cs.run_checker(build(tmp_path, [STATION], "attribution", "CC-BY-4.0"))
    assert res.at("FR-001-19", "/artefacts/1") == []

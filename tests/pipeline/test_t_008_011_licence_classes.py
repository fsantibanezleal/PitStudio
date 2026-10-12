# ruff: noqa: E501, PT018
"""T-008-011: a stage never merges share-alike inputs with inputs of any other licence class into one output file.

Requirements: FR-008-04.

Spec: specs/008-data-pipeline/spec.md FR-008-04; class table of spec 001 data-model section 5.4 (rank order
public-domain < open-no-attribution < own < attribution < share-alike < display-only < reference-only).

Oracle: the FR-008-04 predicate written out here (refuse exactly when the inputs hold at least one `share-alike` input AND
at least one input of another class), checked on the full class table by hand-built pairs and, for all lists of 0 to 10
classes, by a Hypothesis property (including invariance under permutation of the inputs).

Expected API of the implementation:
- `pitstudio_pipeline.errors.ShareAlikeMerge(Exception)` with `.sources`: the ids of the inputs involved (a set or list
  of str, containing at least one share-alike id and one other id), also named in `str(exc)`.
- `pitstudio_pipeline.download.licence.check_merge(inputs) -> None`: `inputs` is a sequence of mappings
  `{"id": str, "licence_class": str}`; raises `ShareAlikeMerge` as above, otherwise returns None.
"""

from __future__ import annotations

import pytest
from pitstudio_pipeline.download.licence import check_merge
from pitstudio_pipeline.errors import ShareAlikeMerge

# isort: split
from hypothesis import given, settings
from hypothesis import strategies as st

CLASSES = [
    "public-domain",
    "open-no-attribution",
    "own",
    "attribution",
    "share-alike",
    "display-only",
    "reference-only",
]
OTHERS = [c for c in CLASSES if c != "share-alike"]


def _inputs(classes: list[str]) -> list[dict[str, str]]:
    return [{"id": f"src-{i}", "licence_class": c} for i, c in enumerate(classes)]


@pytest.mark.req("FR-008-04")
@pytest.mark.parametrize("other", OTHERS)
def test_share_alike_with_any_other_class_is_refused_naming_both(other: str) -> None:
    ins = [{"id": "sa-source", "licence_class": "share-alike"}, {"id": "other-source", "licence_class": other}]
    with pytest.raises(ShareAlikeMerge) as info:
        check_merge(ins)
    assert {"sa-source", "other-source"} <= set(info.value.sources)
    assert "sa-source" in str(info.value) and "other-source" in str(info.value)


@pytest.mark.req("FR-008-04")
@pytest.mark.parametrize("other", OTHERS)
def test_order_of_the_inputs_does_not_matter(other: str) -> None:
    ins = [{"id": "other-source", "licence_class": other}, {"id": "sa-source", "licence_class": "share-alike"}]
    with pytest.raises(ShareAlikeMerge):
        check_merge(ins)


@pytest.mark.req("FR-008-04")
def test_share_alike_alone_and_other_classes_alone_are_accepted() -> None:
    check_merge([{"id": "a", "licence_class": "share-alike"}])
    check_merge([])
    check_merge(_inputs(OTHERS))  # every non-share-alike class together


@pytest.mark.req("FR-008-04")
def test_one_share_alike_among_many_open_inputs_is_still_refused() -> None:
    ins = _inputs(["public-domain"] * 20 + ["share-alike"] + ["own"] * 20)
    with pytest.raises(ShareAlikeMerge) as info:
        check_merge(ins)
    assert "src-20" in set(info.value.sources)


@pytest.mark.req("FR-008-04")
@settings(max_examples=200, deadline=None)
@given(st.lists(st.sampled_from(CLASSES), min_size=0, max_size=10), st.randoms(use_true_random=False))
def test_refused_exactly_when_share_alike_meets_another_class(classes: list[str], rnd) -> None:
    refused_expected = ("share-alike" in classes) and any(c != "share-alike" for c in classes)
    ins = _inputs(classes)
    shuffled = ins[:]
    rnd.shuffle(shuffled)
    for variant in (ins, shuffled):
        if refused_expected:
            with pytest.raises(ShareAlikeMerge):
                check_merge(variant)
        else:
            check_merge(variant)

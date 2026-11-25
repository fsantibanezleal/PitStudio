# ruff: noqa: E501
"""T-015-050: caption scoring (CHAIR_i, CHAIR_s, object recall, condition accuracy), the template baseline, hostile captions and vocabulary.

Requirements: FR-015-38, FR-015-46, P-015-07, SC-015-06.

Spec: specs/015-vlm/spec.md
- FR-015-38: the mentioned classes M of a caption are extracted with the committed vocabulary map (class -> synonyms; lower-cased,
  singularised tokens; set semantics per caption); G is the set of classes with >= 400 visible px in the scene graph; the scorer reports
  CHAIR_i = |M \\ G| / |M|, CHAIR_s = sentences with a hallucinated class / all sentences, object recall |M n G| / |G| and the balanced
  accuracy of dust, night and rain mentions against the scene conditions, for every arm and for the template-caption baseline.
  CHAIR definition: Rohrbach et al. (2018), arXiv 1809.02156, section 2.1: "CHAIRi = |{hallucinated objects}| / |{all objects mentioned}|",
  "CHAIRs = |{sentences with hallucinated object}| / |{all sentences}|".
- FR-015-46: an empty caption, or one that mentions no class (|M| = 0), has an undefined CHAIR_i: it is excluded from CHAIR_i and counted in
  the reported "no object mentioned" rate; a frame whose scene graph has G = empty is excluded from recall; a vocabulary that assigns one
  synonym to two classes makes the scorer refuse to start.
- P-015-07: (MR1) template captions built from the scene graph give CHAIR_i = 0 and recall = 1 exactly; (MR2) replacing a word by a synonym
  of the same class leaves M unchanged; (MR3) permuting sentences leaves CHAIR_i and recall unchanged; adding a mention of an absent class
  never lowers CHAIR_i.
- SC-015-06: CHAIR_i, CHAIR_s, recall and condition accuracy are reported against the template baseline; the row follows
  `contracts/vlm-metrics.schema.json#/$defs/row_c` (template-caption measured rows have chair_i = 0 and recall = 1).

Oracle: the hand-calculated 9-caption table in `_TABLE` (every included caption has two mentioned and two true classes and two
sentences, so the dataset-level micro and macro averages coincide; the spec does not say which one it means, reported as an ambiguity):
CHAIR_i = (0 + 1 + 0 + 1 + 0 + 2) / (6 x 2) = 1/3, recall = 4 / 8 = 0.5, CHAIR_s = 3 / 16 = 0.1875, no-object rate 3/9, balanced accuracy of
the dust, night and rain mentions 0.75, 0.75 and 1.0 (counts in the comments); the CHAIR definition above.

Expected API of the implementation (package `pitstudio`, root environment), `pitstudio.reason.captions`:
- `Vocabulary(classes, conditions)`: `classes` maps each of the five frame-state classes to its synonym list (words or phrases);
  `conditions` maps "dust", "night" and "rain" to their word lists; matching is on lower-cased tokens with a trailing plural "s"
  removed (so "Trucks," matches "truck"); a phrase matches consecutive tokens. A synonym listed for two classes (after lower-casing)
  raises ValueError at construction.
- `extract_classes(caption, vocab) -> frozenset[str]` (set M) and `extract_conditions(caption, vocab) -> frozenset[str]`.
- `visible_classes(frame) -> frozenset[str]` (set G: classes of the objects with `visible_px` >= 400).
- `score_caption(caption, g, vocab) -> dict` with `mentioned`, `hallucinated`, `recalled` (frozensets), `chair_i` (None if |M| = 0),
  `sentences`, `hallucinated_sentences` (sentences end at ".", "!" or "?"; an empty caption has 0).
- `template_caption(frame, vocab) -> str`: states each class of G with the first synonym of its class and the first word of the scene
  condition for dust, night and rain frames (nothing for day); a frame with G empty gets a caption that mentions no class.
- `score_captions(records, vocab, *, arm) -> dict`: `records` are `{"caption", "frame"}`; returns a `row_c` of the metrics contract
  (`status` "measured", `n_captions`, `chair_i`, `chair_s`, `recall` (None when no frame has G non-empty), `no_object_rate`,
  `condition_ba` `{"dust", "night", "rain"}` with None for a condition that is absent or always present); refuses (ValueError) an empty
  record list.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from pitstudio.reason import captions as cap

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))  # the shared kit lives in tests/unit
import _p015_contracts as contracts
import _p015_kit as kit

CLASSES = {
    "haul_truck": ["truck", "haul truck", "dump truck", "haulage truck"],
    "shovel": ["shovel", "excavator"],
    "light_vehicle": ["pickup", "light vehicle", "ute"],
    "person": ["person", "worker", "pedestrian", "people"],
    "boulder": ["boulder", "large rock"],
}
CONDITIONS = {"dust": ["dust", "dusty"], "night": ["night", "dark"], "rain": ["rain", "rainy"]}
VOCAB = cap.Vocabulary(CLASSES, CONDITIONS)
T, S, L, P, B = "haul_truck", "shovel", "light_vehicle", "person", "boulder"


def _frame(g: set[str], condition: str) -> dict:
    """A frame whose scene graph has exactly the classes `g` visible (900 px each) plus a 399 px extra of each other class."""
    objs = [kit.obj(c, 10.0 * i, 0.0, visible_px=900, half=(2.0, 1.0)) for i, c in enumerate(sorted(g))]
    return kit.frame_state(objs or [kit.obj("boulder", 0.0, 0.0, visible_px=399)], condition=condition)


# (caption, G, scene condition): 9 captions, hand-calculated below
_TABLE = [
    (
        "A truck and a worker are here. The sky is clear.",
        {T, P},
        "day",
    ),  # M = {T, P}: h 0; recall 2/2; no condition word
    (
        "A truck drives by. A shovel works in the dust.",
        {T, P},
        "dust",
    ),  # M = {T, S}: h 1 (shovel, sentence 2); recall 1/2; dust mentioned
    ("A shovel and a pickup wait. It is dark.", {S, L}, "night"),  # M = {S, L}: h 0; recall 2/2; night mentioned
    (
        "A truck waits in the rain. A person stands near.",
        {T, L},
        "rain",
    ),  # M = {T, P}: h 1 (person, sentence 2); recall 1/2; rain mentioned
    (
        "A person and a shovel work. It is dusty.",
        {P, S},
        "day",
    ),  # M = {P, S}: h 0; recall 2/2; dust mentioned on a day frame
    (
        "A boulder and a person. Nothing else.",
        {T, S},
        "dust",
    ),  # M = {B, P}: h 2 (sentence 1); recall 0/2; no dust word on a dust frame
    ("The image shows a quarry. Dust fills the air.", {T, P}, "dust"),  # M = empty; recall 0/2; dust mentioned
    ("", {T, L}, "night"),  # empty caption: M = empty, 0 sentences; recall 0/2; night not mentioned
    ("Rain falls. Nothing is visible.", set(), "rain"),  # G = empty: out of recall; M = empty; rain mentioned
]


def _records(table=_TABLE) -> list[dict]:
    return [{"caption": c, "frame": _frame(g, cond)} for c, g, cond in table]


def _row_errors(row: dict) -> list[str]:
    base = contracts.validator("vlm-metrics.schema.json").schema["$id"]
    v = Draft202012Validator({"$ref": base + "#/$defs/row_c"}, registry=contracts._registry())
    return [e.message for e in v.iter_errors(row)]


# ------------------------------------------------------------------------------------------------ extraction
@pytest.mark.req("FR-015-38")
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("A truck.", {T}),
        ("TRUCKS, shovels and Workers!", {T, S, P}),  # lower-casing and plurals
        ("a Dump Truck and an excavator", {T, S}),  # phrases and synonyms
        ("two dump trucks", {T}),
        ("A light vehicle (a pickup) next to people", {L, P}),
        ("a large rock and a boulder", {B}),  # two words of one class: still one element of the set
        ("A worker, a worker, a worker.", {P}),  # set semantics per caption
        ("The scene shows nothing of interest.", set()),
        ("", set()),
        ("trucker truckload", set()),  # whole tokens only
        ("light", set()),  # a phrase needs all its words
        ("vehicle", set()),
    ],
)
def test_the_mentioned_classes_are_extracted_with_the_vocabulary_as_a_set(text: str, expected: set) -> None:
    assert cap.extract_classes(text, VOCAB) == frozenset(expected)


@pytest.mark.req("FR-015-38")
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Dusty and dark.", {"dust", "night"}),
        ("It is raining? Rain!", {"rain"}),
        ("A clear day.", set()),
        ("NIGHT", {"night"}),
    ],
)
def test_condition_words_are_extracted_the_same_way(text: str, expected: set) -> None:
    assert cap.extract_conditions(text, VOCAB) == frozenset(expected)


@pytest.mark.req("FR-015-38")
def test_g_is_the_set_of_classes_with_at_least_400_visible_pixels() -> None:
    frame = kit.frame_state(
        [
            kit.truck(0.0, 0.0, visible_px=400),
            kit.person(30.0, 0.0, visible_px=399),
            kit.light_vehicle(60.0, 0.0, visible_px=5000),
            kit.obj("shovel", 90.0, 0.0, visible_px=0, half=(6.0, 3.0)),
            kit.obj("boulder", 120.0, 0.0, visible_px=401),
            kit.truck(150.0, 0.0, visible_px=10),  # a second, hidden truck does not matter
        ]
    )
    assert cap.visible_classes(frame) == frozenset({T, L, B})


@pytest.mark.req("FR-015-38")
def test_score_caption_reports_the_sets_the_counts_and_chair_i_of_one_caption() -> None:
    r = cap.score_caption("A truck drives by. A shovel works in the dust.", frozenset({T, P}), VOCAB)
    assert r["mentioned"] == frozenset({T, S})
    assert r["hallucinated"] == frozenset({S})
    assert r["recalled"] == frozenset({T})
    assert r["chair_i"] == pytest.approx(1 / 2, abs=1e-15)
    assert (r["sentences"], r["hallucinated_sentences"]) == (2, 1)
    empty = cap.score_caption("", frozenset({T}), VOCAB)
    assert (empty["chair_i"], empty["sentences"], empty["hallucinated_sentences"]) == (None, 0, 0)


# ------------------------------------------------------------------------------------------------ the hand-calculated table
@pytest.mark.req("FR-015-38")
@pytest.mark.req("SC-015-06")
def test_the_aggregate_scores_equal_the_hand_calculation() -> None:
    row = cap.score_captions(_records(), VOCAB, arm="cosmos-q8_0")
    assert row["n_captions"] == 9
    assert row["chair_i"] == pytest.approx(
        4 / 12, abs=1e-12
    )  # 4 hallucinated mentions of 12 (the six captions with M non-empty)
    assert row["chair_s"] == pytest.approx(
        3 / 16, abs=1e-12
    )  # sentences: 8 captions x 2 (the empty one has none); 3 hallucinated
    assert row["recall"] == pytest.approx(
        4 / 8, abs=1e-12
    )  # 8 frames with G non-empty: 1 + 0.5 + 1 + 0.5 + 1 + 0 + 0 + 0
    assert row["no_object_rate"] == pytest.approx(3 / 9, abs=1e-12)  # captions 7, 8 and 9 mention no class
    ba = row["condition_ba"]
    assert ba["dust"] == pytest.approx(
        0.75, abs=1e-12
    )  # truth dust: frames 2, 6, 7; mentioned on 2, 5, 7: (2/3 + 5/6) / 2
    assert ba["night"] == pytest.approx(0.75, abs=1e-12)  # truth night: frames 3, 8; mentioned on 3: (1/2 + 7/7) / 2
    assert ba["rain"] == pytest.approx(1.0, abs=1e-12)  # truth rain: frames 4, 9; mentioned on 4, 9: (2/2 + 7/7) / 2
    assert row["status"] == "measured"
    assert row["arm"] == "cosmos-q8_0"
    assert _row_errors(row) == []


@pytest.mark.req("FR-015-46")
def test_captions_without_a_mentioned_class_are_excluded_from_chair_i_and_counted_in_the_no_object_rate() -> None:
    only = [(c, g, k) for c, g, k in _TABLE[:6]]
    with_empty = _TABLE
    a = cap.score_captions(_records(only), VOCAB, arm="qwen-base")
    b = cap.score_captions(_records(with_empty), VOCAB, arm="qwen-base")
    assert a["chair_i"] == pytest.approx(b["chair_i"], abs=1e-15)  # the three captions with |M| = 0 change nothing
    assert a["no_object_rate"] == 0.0
    assert b["no_object_rate"] == pytest.approx(1 / 3, abs=1e-12)


@pytest.mark.req("FR-015-46")
def test_a_frame_with_an_empty_g_is_excluded_from_recall_but_its_mentions_are_hallucinations() -> None:
    rec = [{"caption": "A truck and a person.", "frame": _frame(set(), "day")}]
    row = cap.score_captions(rec, VOCAB, arm="qwen-base")
    assert row["recall"] is None  # no frame with a non-empty G
    assert row["chair_i"] == 1.0
    two = [*rec, {"caption": "A truck.", "frame": _frame({T}, "day")}]
    assert cap.score_captions(two, VOCAB, arm="qwen-base")["recall"] == 1.0  # only the second frame counts


@pytest.mark.req("FR-015-46")
def test_with_no_captioned_class_at_all_chair_i_is_undefined() -> None:
    row = cap.score_captions(
        [{"caption": "", "frame": _frame({T}, "day")}, {"caption": "Nothing.", "frame": _frame({T}, "day")}],
        VOCAB,
        arm="qwen-base",
    )
    assert row["chair_i"] is None
    assert row["no_object_rate"] == 1.0
    assert row["recall"] == 0.0


@pytest.mark.req("FR-015-46")
@pytest.mark.parametrize(
    "classes",
    [
        {**CLASSES, "light_vehicle": ["pickup", "truck"]},  # "truck" is also a haul-truck synonym
        {**CLASSES, "person": ["Truck", "worker"]},  # the same synonym after lower-casing
        {**CLASSES, "boulder": ["boulder", "worker"]},  # "worker" is also a person synonym
    ],
    ids=["same-word", "case-variant", "other-pair"],
)
def test_a_vocabulary_that_assigns_one_synonym_to_two_classes_is_refused(classes: dict) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        cap.Vocabulary(classes, CONDITIONS)


@pytest.mark.req("FR-015-46")
def test_the_scorer_refuses_an_empty_record_list() -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        cap.score_captions([], VOCAB, arm="qwen-base")


# ------------------------------------------------------------------------------------------------ P-015-07
_CLASS_KEYS = sorted(CLASSES)
_FRAMES = st.builds(
    lambda objs, cond: kit.frame_state(
        [kit.obj(c, 10.0 * i, 0.0, visible_px=px, half=(2.0, 1.0)) for i, (c, px) in enumerate(objs)], condition=cond
    ),
    st.lists(
        st.tuples(st.sampled_from(_CLASS_KEYS), st.sampled_from([0, 50, 399, 400, 401, 5000])), min_size=1, max_size=6
    ),
    st.sampled_from(["day", "night", "dust", "rain"]),
)


@pytest.mark.req("P-015-07")
@settings(max_examples=200, deadline=None)
@given(st.lists(_FRAMES, min_size=1, max_size=12))
def test_mr1_template_captions_score_chair_i_zero_and_recall_one_exactly(frames: list[dict]) -> None:
    for f in frames:
        g = cap.visible_classes(f)
        text = cap.template_caption(f, VOCAB)
        assert cap.extract_classes(text, VOCAB) == g  # the template states exactly the scene-graph classes
    row = cap.score_captions(
        [{"caption": cap.template_caption(f, VOCAB), "frame": f} for f in frames], VOCAB, arm="template-caption"
    )
    if any(cap.visible_classes(f) for f in frames):
        assert row["chair_i"] == 0
        assert row["chair_s"] == 0
        assert row["recall"] == 1
        assert _row_errors(row) == []
    else:
        assert row["chair_i"] is None  # nothing to mention
        assert row["recall"] is None


@pytest.mark.req("P-015-07")
def test_the_template_baseline_reads_the_scene_condition_exactly() -> None:
    frames = [_frame({T, P}, c) for c in ("day", "dust", "night", "rain")] * 3
    row = cap.score_captions(
        [{"caption": cap.template_caption(f, VOCAB), "frame": f} for f in frames], VOCAB, arm="template-caption"
    )
    assert row["condition_ba"] == {"dust": 1.0, "night": 1.0, "rain": 1.0}
    assert cap.extract_conditions(cap.template_caption(_frame({T}, "day"), VOCAB), VOCAB) == frozenset()


@st.composite
def _mention_sets(draw) -> tuple[list[str], list[str], list[str]]:
    keys = draw(st.lists(st.sampled_from(_CLASS_KEYS), min_size=1, max_size=5, unique=True))
    first = [draw(st.sampled_from(CLASSES[k])) for k in keys]
    second = [draw(st.sampled_from(CLASSES[k])) for k in keys]
    return keys, first, second


def _caption_from(words: list[str], plural: bool) -> str:
    return " ".join(f"A {w}{'s' if plural and not w.endswith('s') and w != 'people' else ''} was seen." for w in words)


@pytest.mark.req("P-015-07")
@settings(max_examples=200, deadline=None)
@given(_mention_sets(), st.booleans())
def test_mr2_replacing_a_word_by_a_synonym_of_the_same_class_leaves_m_unchanged(sets: tuple, plural: bool) -> None:
    keys, first, second = sets
    a = cap.extract_classes(_caption_from(first, False), VOCAB)
    b = cap.extract_classes(_caption_from(second, plural), VOCAB)
    assert a == b == frozenset(keys)


@pytest.mark.req("P-015-07")
@settings(max_examples=100, deadline=None)
@given(st.randoms(use_true_random=False))
def test_mr3_permuting_the_sentences_leaves_the_scores_unchanged(rnd) -> None:
    base = cap.score_captions(_records(), VOCAB, arm="qwen-base")
    permuted = []
    for c, g, cond in _TABLE:
        parts = [p.strip() + "." for p in c.split(".") if p.strip()]
        rnd.shuffle(parts)
        permuted.append((" ".join(parts), g, cond))
    row = cap.score_captions(_records(permuted), VOCAB, arm="qwen-base")
    for key in ("chair_i", "chair_s", "recall", "no_object_rate"):
        assert row[key] == pytest.approx(base[key], abs=1e-15)
    assert row["condition_ba"] == pytest.approx(base["condition_ba"], abs=1e-15)


@pytest.mark.req("P-015-07")
@settings(max_examples=200, deadline=None)
@given(st.sampled_from(_TABLE), st.sampled_from(_CLASS_KEYS))
def test_adding_a_mention_of_an_absent_class_never_lowers_chair_i(row: tuple, extra: str) -> None:
    text, g, _ = row
    assume(extra not in g)
    before = cap.score_caption(text, frozenset(g), VOCAB)
    after = cap.score_caption(text + f" Also a {CLASSES[extra][0]}.", frozenset(g), VOCAB)
    if before["chair_i"] is None:
        assert after["chair_i"] == 1.0  # the only mentioned class is hallucinated
    else:
        assert after["chair_i"] >= before["chair_i"] - 1e-15
    assert (
        after["hallucinated_sentences"] >= before["hallucinated_sentences"] + 1
    )  # the added sentence names an absent class
    assert after["sentences"] == before["sentences"] + 1


# ------------------------------------------------------------------------------------------------ hostile captions
_HOSTILE_TEXT = st.one_of(
    st.text(max_size=2000),
    st.text(alphabet="truck shovel person boulder .!?,;:-'\"() \n\téñ中\U0001f600", max_size=500),
)


@pytest.mark.req("FR-015-46")
@settings(max_examples=300, deadline=None)
@given(_HOSTILE_TEXT)
def test_any_caption_text_gives_a_valid_score_and_never_raises(text: str) -> None:
    m = cap.extract_classes(text, VOCAB)
    assert m <= frozenset(CLASSES)
    r = cap.score_caption(text, frozenset({T}), VOCAB)
    assert r["hallucinated"] == m - frozenset({T})
    assert r["recalled"] == m & frozenset({T})
    assert 0 <= r["hallucinated_sentences"] <= r["sentences"]
    if m:
        assert 0.0 <= r["chair_i"] <= 1.0
    else:
        assert r["chair_i"] is None


@pytest.mark.req("FR-015-46")
@pytest.mark.parametrize(
    "text",
    [
        pytest.param("truck " * 100_000, id="repeated-word"),
        pytest.param("." * 100_000, id="only-full-stops"),
        pytest.param("\x00truck\x00", id="nul-bytes"),
        pytest.param("T̶r̶u̶c̶k", id="combining-marks"),
        pytest.param("﻿​truck", id="invisible-characters"),
    ],
)
def test_huge_or_odd_captions_are_handled(text: str) -> None:
    assert cap.extract_classes(text, VOCAB) <= frozenset(CLASSES)
    row = cap.score_captions([{"caption": text, "frame": _frame({T}, "day")}], VOCAB, arm="qwen-base")
    assert row["n_captions"] == 1


@pytest.mark.req("FR-015-46")
def test_a_shuffled_dataset_gives_the_same_row() -> None:
    recs = _records()
    shuffled = list(recs)
    random.Random(2).shuffle(shuffled)
    a, b = cap.score_captions(recs, VOCAB, arm="qwen-base"), cap.score_captions(shuffled, VOCAB, arm="qwen-base")
    for key in ("n_captions", "chair_i", "chair_s", "recall", "no_object_rate"):
        assert a[key] == pytest.approx(b[key], abs=1e-15)
    assert a["condition_ba"] == pytest.approx(b["condition_ba"], abs=1e-15)

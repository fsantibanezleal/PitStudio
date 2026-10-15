# ruff: noqa: E501
"""T-015-034: the answer parser (FR-015-26, FR-015-27) and its fuzzing (P-015-11).

Requirements: FR-015-26, FR-015-27, P-015-11.

Spec: specs/015-vlm/spec.md
- FR-015-26: the parser reads only the text inside the last `<answer>...</answer>` pair (or, with reasoning off and no tags,
  the first word), case-, whitespace- and punctuation-insensitive, mapping "yes"/"no" and the counts 0-3 (digits or words, with
  "3 or more", "three or more" and larger numbers mapped to >= 3), and returns exactly one of {yes, no, 0, 1, 2, >= 3,
  unparseable}. The contracts write the class ">= 3" as the label "3+" (spec section 8, integration note); this test uses "3+".
- FR-015-27: an output that is empty, has no parseable answer, or holds conflicting answers inside one answer pair is
  `unparseable`.
- P-015-11: for any string the parser returns exactly one label of its set and never raises; it is idempotent on its own
  canonical outputs and invariant under case and surrounding whitespace (Hypothesis text, Unicode, <= 10^4 characters).
- spec section 7: "none" maps to 0; type-3 answers above 3 map to "3+".

Oracle: the mapping table below, written by hand from the spec text (each row: raw text inside the tags and the label the spec
prescribes); structured random texts built around a table row (the expected label does not depend on the prose around the last
answer pair); invariants of P-015-11.

Expected API of the implementation (package `pitstudio`, root environment):
- `pitstudio.reason.parse.parse_answer(text: str, *, reasoning: bool = False) -> str` returning one of
  "yes", "no", "0", "1", "2", "3+", "unparseable". With `reasoning=False` and no `<answer>` tag the first word of the text is
  parsed; with `reasoning=True` a text without a complete `<answer>...</answer>` pair is "unparseable". Tag names are matched
  case-insensitively. It never raises, for any `str`.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.reason.parse import parse_answer

LABELS = {"yes", "no", "0", "1", "2", "3+", "unparseable"}

TABLE: list[tuple[str, str]] = [
    ("yes", "yes"),
    ("Yes", "yes"),
    ("YES", "yes"),
    (" yes ", "yes"),
    ("yes.", "yes"),
    ("Yes!", "yes"),
    ("\n yes \n", "yes"),
    ("  Yes.  ", "yes"),
    ("no", "no"),
    ("No", "no"),
    ("NO.", "no"),
    (" no ", "no"),
    ("0", "0"),
    ("zero", "0"),
    ("Zero", "0"),
    ("none", "0"),
    ("None", "0"),
    ("1", "1"),
    ("one", "1"),
    ("One.", "1"),
    ("2", "2"),
    ("two", "2"),
    ("Two", "2"),
    ("3", "3+"),
    ("three", "3+"),
    ("3 or more", "3+"),
    ("three or more", "3+"),
    ("Three or More", "3+"),
    ("4", "3+"),
    ("7", "3+"),
    ("12", "3+"),
    ("100", "3+"),
    ("3+", "3+"),
    ("", "unparseable"),
    ("   ", "unparseable"),
    ("maybe", "unparseable"),
    ("I do not know", "unparseable"),
    ("unknown", "unparseable"),
    ("yes and no", "unparseable"),
    ("yes or no", "unparseable"),
    ("yes/no", "unparseable"),
    ("no, yes", "unparseable"),
    ("0 and 1", "unparseable"),
    ("1 or 2", "unparseable"),
    ("yeah", "unparseable"),
    ("és", "unparseable"),
]


@pytest.mark.req("FR-015-26")
@pytest.mark.req("FR-015-27")
@pytest.mark.parametrize(("inner", "expected"), TABLE)
def test_text_inside_the_answer_tags_maps_to_the_prescribed_label(inner: str, expected: str) -> None:
    for reasoning in (False, True):
        assert parse_answer(f"<answer>{inner}</answer>", reasoning=reasoning) == expected


@pytest.mark.req("FR-015-26")
def test_only_the_last_answer_pair_counts() -> None:
    assert parse_answer("<answer>no</answer> wait, again: <answer>yes</answer>", reasoning=True) == "yes"
    assert parse_answer("<answer>yes</answer><answer>no</answer>", reasoning=True) == "no"
    assert parse_answer("<answer>1</answer>\n<answer>maybe</answer>", reasoning=True) == "unparseable"


@pytest.mark.req("FR-015-26")
def test_text_outside_the_answer_pair_is_ignored() -> None:
    assert (
        parse_answer("<think>I think the answer is yes</think>\n<answer>no</answer>\nyes yes yes", reasoning=True)
        == "no"
    )
    assert parse_answer("The truck is 2 m away. <answer>one</answer> (not two)", reasoning=True) == "1"
    assert parse_answer("<think>yes</think><answer></answer>", reasoning=True) == "unparseable"


@pytest.mark.req("FR-015-26")
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Yes, the person is within 30 m of the truck.", "yes"),
        ("no", "no"),
        ("No. There is nothing near the truck.", "no"),
        ("  YES", "yes"),
        ("2 trucks are visible", "2"),
        ("Two trucks are visible.", "2"),
        ("3 or more trucks", "3+"),
        ("Three or more trucks", "3+"),
        ("0", "0"),
        ("", "unparseable"),
        ("   \n ", "unparseable"),
        ("The person is close.", "unparseable"),
        ("<think>the answer is yes</think>", "unparseable"),
    ],
)
def test_with_reasoning_off_and_no_tags_the_first_word_is_parsed(text: str, expected: str) -> None:
    assert parse_answer(text, reasoning=False) == expected


@pytest.mark.req("FR-015-26")
def test_with_reasoning_on_a_text_without_a_complete_answer_pair_is_unparseable() -> None:
    assert parse_answer("yes", reasoning=True) == "unparseable"
    assert parse_answer("<think>it is clearly yes</think>", reasoning=True) == "unparseable"
    assert parse_answer("<answer>yes", reasoning=True) == "unparseable"


@pytest.mark.req("FR-015-26")
@pytest.mark.parametrize("tag", ["answer", "ANSWER", "Answer"])
def test_tag_names_are_matched_without_regard_to_case(tag: str) -> None:
    assert parse_answer(f"<{tag}>yes</{tag}>", reasoning=True) == "yes"


@pytest.mark.req("FR-015-27")
@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "\n\t",
        "<answer></answer>",
        "<answer>   </answer>",
        "<answer>?</answer>",
        "​",
        "\x00",
        "😀".encode().decode(),
    ],
)
def test_empty_and_unparseable_outputs_are_unparseable(text: str) -> None:
    assert parse_answer(text) == "unparseable"
    assert parse_answer(text, reasoning=True) == "unparseable"


@pytest.mark.req("FR-015-27")
@pytest.mark.parametrize("inner", ["yes and no", "no or yes", "yes, no", "0 and 1", "three or 1", "yes/no", "NO / YES"])
def test_conflicting_answers_inside_one_pair_are_unparseable(inner: str) -> None:
    assert parse_answer(f"<answer>{inner}</answer>", reasoning=True) == "unparseable"


@pytest.mark.req("FR-015-27")
@pytest.mark.parametrize("n_digits", [5000, 100_000])
def test_a_huge_number_does_not_raise_and_yields_one_label(n_digits: int) -> None:
    assert parse_answer("<answer>" + "9" * n_digits + "</answer>", reasoning=True) in LABELS


@pytest.mark.req("FR-015-27")
def test_a_huge_input_is_handled() -> None:
    text = "word " * 200_000 + "<answer>yes</answer>"
    assert parse_answer(text, reasoning=True) == "yes"
    assert parse_answer("<answer>" * 50_000, reasoning=True) in LABELS


_PROSE = st.text(alphabet=st.characters(blacklist_characters="<>", blacklist_categories=("Cs",)), max_size=80)


@pytest.mark.req("FR-015-26")
@pytest.mark.req("FR-015-27")
@settings(max_examples=300, deadline=None)
@given(st.sampled_from(TABLE), _PROSE, _PROSE, _PROSE)
def test_property_the_label_depends_only_on_the_text_inside_the_last_answer_pair(
    row: tuple[str, str], pre: str, mid: str, post: str
) -> None:
    inner, expected = row
    text = f"{pre}<answer>no</answer>{mid}<answer>{inner}</answer>{post}"
    assert parse_answer(text, reasoning=True) == expected


# --- P-015-11 -------------------------------------------------------------------------------------------------
_ANY_TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=10_000)
_FRAGMENTS = st.sampled_from(
    [
        "<answer>",
        "</answer>",
        "<think>",
        "</think>",
        "yes",
        "no",
        "3",
        "two",
        " or more",
        " ",
        "\n",
        ".",
        ",",
        "<",
        ">",
        "0",
        "none",
        "é",
    ]
)
_STRUCTURED = st.lists(_FRAGMENTS, max_size=40).map("".join)


@pytest.mark.req("P-015-11")
@settings(max_examples=400, deadline=None)
@given(st.one_of(_ANY_TEXT, _STRUCTURED), st.booleans())
def test_property_every_string_gives_exactly_one_label_and_never_raises(text: str, reasoning: bool) -> None:
    out = parse_answer(text, reasoning=reasoning)
    assert isinstance(out, str)
    assert out in LABELS


@pytest.mark.req("P-015-11")
@settings(max_examples=300, deadline=None)
@given(st.one_of(_ANY_TEXT, _STRUCTURED), st.booleans())
def test_property_the_parser_is_idempotent_on_its_own_output(text: str, reasoning: bool) -> None:
    once = parse_answer(text, reasoning=reasoning)
    assert parse_answer(once, reasoning=False) == once
    assert parse_answer(f"<answer>{once}</answer>", reasoning=True) == once


@pytest.mark.req("P-015-11")
@pytest.mark.parametrize("label", sorted(LABELS))
def test_every_canonical_label_parses_to_itself(label: str) -> None:
    assert parse_answer(label) == label
    assert parse_answer(f"<answer>{label}</answer>", reasoning=True) == label


_ASCII = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 \t\n.,!?+-/:;'\"()[]<>", max_size=300
)
_ASCII_STRUCTURED = st.lists(
    st.sampled_from(
        [
            "<answer>",
            "</answer>",
            "yes",
            "Yes",
            "NO",
            "no",
            "3",
            "Two",
            " or more",
            " ",
            "\n",
            ".",
            "none",
            "zero",
            "<think>",
            "</think>",
        ]
    ),
    max_size=30,
).map("".join)


@pytest.mark.req("P-015-11")
@settings(max_examples=400, deadline=None)
@given(
    st.one_of(_ASCII, _ASCII_STRUCTURED),
    st.booleans(),
    st.text(alphabet=" \t\n\r", max_size=5),
    st.text(alphabet=" \t\n\r", max_size=5),
)
def test_property_the_label_is_invariant_under_case_and_surrounding_whitespace(
    text: str, reasoning: bool, lead: str, trail: str
) -> None:
    base = parse_answer(text, reasoning=reasoning)
    assert parse_answer(text.upper(), reasoning=reasoning) == base
    assert parse_answer(text.lower(), reasoning=reasoning) == base
    assert parse_answer(text.swapcase(), reasoning=reasoning) == base
    assert parse_answer(lead + text + trail, reasoning=reasoning) == base

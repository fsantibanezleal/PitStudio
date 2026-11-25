"""Answer parser (FR-015-26, FR-015-27): one label from a model output, never an exception.

Labels: "yes", "no", "0", "1", "2", "3+" (the contracts' spelling of ">= 3") and "unparseable".

Rules:
- the answer is the text inside the LAST complete `<answer>...</answer>` pair (tag names case-insensitive); text outside
  the pair is ignored;
- with `reasoning=False` and no complete pair, the first word of the output is parsed instead; with `reasoning=True`
  and no complete pair the output is unparseable;
- inside a pair the whole content must be one answer: "yes", "no", a count as a digit string or a number word
  ("none" and "zero" are 0; "3 or more", "three or more", "3+" and every number above three are "3+"). Anything else,
  including two different answers ("yes and no", "1 or 2", "yes/no"), an empty pair or a negative number, is
  unparseable. Matching ignores case, surrounding whitespace and surrounding punctuation.
"""

from __future__ import annotations

import re

LABELS = ("yes", "no", "0", "1", "2", "3+")
UNPARSEABLE = "unparseable"

_TAG = re.compile(r"</?answer>", re.IGNORECASE)
_EDGE = " \t\r\n.,!?;:'\"()[]{}*_"
_DIGITS = re.compile(r"[0-9]+")
_WORDS = {
    "yes": "yes",
    "no": "no",
    "none": "0",
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3+",
}
_MORE = ("or", "more")


def _count_label(digits: str) -> str:
    """Label of a digit string without converting it to an int (a huge number is just "3+")."""
    stripped = digits.lstrip("0")
    if not stripped:
        return "0"
    return stripped if stripped in ("1", "2") else "3+"


def _word(chunk: str) -> str | None:
    """Label of one whitespace-delimited chunk, or None."""
    token = chunk.strip(_EDGE).casefold()
    if token in _WORDS:
        return _WORDS[token]
    if _DIGITS.fullmatch(token):
        return _count_label(token)
    if token.endswith("+") and _DIGITS.fullmatch(token[:-1]):  # "3+", "12+": only a bound of three or more is a label
        return "3+" if _count_label(token[:-1]) == "3+" else None
    return None


def _leading(chunks: list[str]) -> tuple[str | None, int]:
    """Label of the answer at the start of `chunks` and the number of chunks it used ("3 or more" takes three)."""
    if not chunks:
        return None, 0
    label = _word(chunks[0])
    if label == "3+" and len(chunks) >= 3:
        tail = tuple(c.strip(_EDGE).casefold() for c in chunks[1:3])
        if tail == _MORE and chunks[0].strip(_EDGE).casefold() in ("3", "three"):
            return "3+", 3
    return label, 1


def _parse_pair(inner: str) -> str:
    chunks = inner.split()
    label, used = _leading(chunks)
    return label if label is not None and used == len(chunks) else UNPARSEABLE


def _parse_first_word(text: str) -> str:
    label, _ = _leading(text.split(maxsplit=3)[:3])
    return label if label is not None else UNPARSEABLE


def _last_pair(text: str) -> str | None:
    """Content of the last complete `<answer>...</answer>` pair, or None."""
    tags = [(m.start(), m.end(), m.group().startswith("</")) for m in _TAG.finditer(text)]
    close = next((i for i in range(len(tags) - 1, -1, -1) if tags[i][2]), None)
    if close is None:
        return None
    open_ = next((i for i in range(close - 1, -1, -1) if not tags[i][2]), None)
    if open_ is None:
        return None
    return text[tags[open_][1] : tags[close][0]]


def parse_answer(text: str, *, reasoning: bool = False) -> str:
    """Parse a model output into exactly one label of `LABELS` or "unparseable"; never raises."""
    if not isinstance(text, str):
        return UNPARSEABLE
    inner = _last_pair(text)
    if inner is not None:
        return _parse_pair(inner)
    return UNPARSEABLE if reasoning else _parse_first_word(text)

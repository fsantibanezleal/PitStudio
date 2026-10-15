"""Task-C caption scoring against the scene graph (FR-015-38, FR-015-46, P-015-07, SC-015-06).

A caption mentions a set M of the five frame-state classes, found with a committed vocabulary map (class to synonyms,
matching lower-cased tokens with a trailing plural "s" removed; a phrase matches consecutive tokens). G is the set of
classes with at least 400 visible pixels in the frame state. Following Rohrbach et al. (2018), "Object Hallucination in
Image Captioning" (arXiv 1809.02156), section 2.1:

- CHAIR_i = |hallucinated objects| / |all objects mentioned|, with hallucinated = M minus G;
- CHAIR_s = |sentences with a hallucinated object| / |all sentences|.

Dataset-level values are micro averages (sums of the numerators over sums of the denominators); the spec does not say
which average it means. A caption with |M| = 0 leaves CHAIR_i undefined for that caption: it is excluded from
CHAIR_i and counted in the "no object mentioned" rate. A frame with G empty is excluded from recall. A vocabulary
that gives one synonym to two classes is refused at construction.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

VISIBLE_PX = 400
CLASS_NAMES = ("haul_truck", "shovel", "light_vehicle", "person", "boulder")
CONDITION_NAMES = ("dust", "night", "rain")
ARMS = ("cosmos-q8_0", "cosmos-bf16", "qwen-base", "template-caption")
_TOKEN = re.compile(r"[^\W_]+")
_SENTENCE_END = re.compile(r"[.!?]+")


def _norm(token: str) -> str:
    """Lower-case a token and remove one trailing plural "s" ("trucks" to "truck"; "glass" and 3-letter words stay)."""
    token = token.casefold()
    return token[:-1] if len(token) > 3 and token.endswith("s") and not token.endswith("ss") else token


def _tokens(text: str) -> list[str]:
    return [_norm(t) for t in _TOKEN.findall(text.casefold())]


def _phrase(text: str) -> tuple[str, ...]:
    words = _tokens(text)
    if not words:
        raise ValueError(f"synonym {text!r} holds no word")
    return tuple(words)


class Vocabulary:
    """Class and condition synonym maps. `classes` has the five frame-state classes as keys, `conditions` dust,
    night and rain; every value is a list of words or phrases. A synonym listed for two classes (or two
    conditions) raises ValueError."""

    def __init__(self, classes: Mapping[str, Sequence[str]], conditions: Mapping[str, Sequence[str]]) -> None:
        if set(classes) != set(CLASS_NAMES):
            raise ValueError(f"classes must be exactly {CLASS_NAMES}, got {sorted(classes)}")
        if set(conditions) != set(CONDITION_NAMES):
            raise ValueError(f"conditions must be exactly {CONDITION_NAMES}, got {sorted(conditions)}")
        self.classes = {k: list(v) for k, v in classes.items()}
        self.conditions = {k: list(v) for k, v in conditions.items()}
        self.class_lookup = self._lookup(self.classes)
        self.condition_lookup = self._lookup(self.conditions)

    @staticmethod
    def _lookup(groups: Mapping[str, Sequence[str]]) -> dict[tuple[str, ...], str]:
        table: dict[tuple[str, ...], str] = {}
        for name, synonyms in groups.items():
            if len(synonyms) == 0:
                raise ValueError(f"{name!r} has no synonym")
            for syn in synonyms:
                key = _phrase(syn)
                if table.setdefault(key, name) != name:
                    raise ValueError(f"synonym {syn!r} is assigned to both {table[key]!r} and {name!r}")
        return table

    @classmethod
    def from_file(cls, path: Path) -> Vocabulary:
        """The committed vocabulary (`studio/reason/vocabulary.json`: `{"classes": {...}, "conditions": {...}}`)."""
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(doc["classes"], doc["conditions"])

    def match(self, text: str, table: Mapping[tuple[str, ...], str]) -> frozenset[str]:
        tokens = _tokens(text)
        found: set[str] = set()
        for length in {len(k) for k in table}:
            for i in range(len(tokens) - length + 1):
                hit = table.get(tuple(tokens[i : i + length]))
                if hit is not None:
                    found.add(hit)
        return frozenset(found)


def extract_classes(caption: str, vocab: Vocabulary) -> frozenset[str]:
    """The set M of classes a caption mentions."""
    return vocab.match(caption, vocab.class_lookup)


def extract_conditions(caption: str, vocab: Vocabulary) -> frozenset[str]:
    """The conditions (dust, night, rain) a caption mentions."""
    return vocab.match(caption, vocab.condition_lookup)


def visible_classes(frame: Mapping[str, Any]) -> frozenset[str]:
    """The set G: classes of the objects with at least 400 visible pixels."""
    return frozenset(o["class"] for o in frame["objects"] if o["visible_px"] >= VISIBLE_PX)


def _sentences(caption: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(caption) if s.strip()]


def score_caption(caption: str, g: frozenset[str], vocab: Vocabulary) -> dict[str, Any]:
    """Mentioned, hallucinated and recalled classes of one caption, its CHAIR_i (None when nothing is mentioned) and its
    sentence counts (sentences end at ".", "!" or "?")."""
    mentioned = extract_classes(caption, vocab)
    hallucinated = mentioned - g
    sentences = _sentences(caption)
    return {
        "mentioned": mentioned,
        "hallucinated": hallucinated,
        "recalled": mentioned & g,
        "chair_i": len(hallucinated) / len(mentioned) if mentioned else None,
        "sentences": len(sentences),
        "hallucinated_sentences": sum(1 for s in sentences if extract_classes(s, vocab) - g),
    }


def template_caption(frame: Mapping[str, Any], vocab: Vocabulary) -> str:
    """The baseline caption: each class of G stated with its first synonym, plus the first word of the scene condition
    for dust, night and rain frames. A frame with G empty gets a caption that mentions no class."""
    g = visible_classes(frame)
    sentences = [f"A {vocab.classes[c][0]} is visible." for c in CLASS_NAMES if c in g]
    if not sentences:
        sentences = ["Nothing is visible."]
    if frame["condition"] in CONDITION_NAMES:
        sentences.append(f"The scene is {vocab.conditions[frame['condition']][0]}.")
    return " ".join(sentences)


def _balanced_accuracy(truth: Sequence[bool], pred: Sequence[bool]) -> float | None:
    pos = [p for t, p in zip(truth, pred, strict=True) if t]
    neg = [p for t, p in zip(truth, pred, strict=True) if not t]
    if not pos or not neg:
        return None
    return (sum(pos) / len(pos) + sum(1 for p in neg if not p) / len(neg)) / 2


def score_captions(records: Sequence[Mapping[str, Any]], vocab: Vocabulary, *, arm: str) -> dict[str, Any]:
    """One `row_c` of the metrics contract from `{"caption", "frame"}` records of one arm."""
    if arm not in ARMS:
        raise ValueError(f"unknown caption arm {arm!r}")
    if len(records) == 0:
        raise ValueError("n = 0: no captions to score")
    mentions = hallucinated = sentences = hallucinated_sentences = no_object = 0
    recalled = recall_total = 0
    truth: dict[str, list[Any]] = {c: [] for c in CONDITION_NAMES}
    pred: dict[str, list[Any]] = {c: [] for c in CONDITION_NAMES}
    for r in records:
        caption = r["caption"]
        if not isinstance(caption, str):
            raise ValueError("a caption must be text")
        g = visible_classes(r["frame"])
        s = score_caption(caption, g, vocab)
        if s["mentioned"]:
            mentions += len(s["mentioned"])
            hallucinated += len(s["hallucinated"])
        else:
            no_object += 1
        sentences += s["sentences"]
        hallucinated_sentences += s["hallucinated_sentences"]
        if g:
            recall_total += len(g)
            recalled += len(s["recalled"])
        said = extract_conditions(caption, vocab)
        for c in CONDITION_NAMES:
            truth[c].append(r["frame"]["condition"] == c)
            pred[c].append(c in said)
    return {
        "arm": arm,
        "status": "measured",
        "n_captions": len(records),
        "chair_i": hallucinated / mentions if mentions else None,
        "chair_s": hallucinated_sentences / sentences if sentences else None,
        "recall": recalled / recall_total if recall_total else None,
        "no_object_rate": no_object / len(records),
        "condition_ba": {c: _balanced_accuracy(truth[c], pred[c]) for c in CONDITION_NAMES},
    }

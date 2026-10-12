"""Data cards: synthetic-set cards, the honesty rule and the registry-to-card check (FR-008-33 ... FR-008-49).

A card is a Markdown file: `---`, the YAML front matter (DC-008-05, `contracts/data-card.schema.json`), `---`, a blank
line and the body. Every synthetic set has exactly one validation class; a C2ST or TSTR verdict may be attached only to
the class that was validated against real data, and every other class carries the exact honesty label.
"""

from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pitstudio_pipeline._contracts import schema_errors
from pitstudio_pipeline.errors import HonestyRuleViolation

HONESTY_LABEL = "calibrated synthetic — not validated against real data"  # em dash, U+2014
VALIDATED, DESCRIPTIVE, UNVALIDATED = "validated-against-real", "descriptive-only", "unvalidated"
# FR-008-36: fragment images and terrain statistics are validated against real data; the single real slope event is
# descriptive only; every other type carries the honesty label. `ore-deposits` (oreblocks) is "every other type".
VALIDATED_TYPES = {"fragment-images": ("c2st", "tstr"), "terrain-statistics": ("c2st",)}
DESCRIPTIVE_TYPES = frozenset({"voight-creep-series"})
UNVALIDATED_TYPES = frozenset(
    {
        "equipment-images",
        "people-images",
        "sensor-clouds",
        "dust-fields",
        "plume-fields",
        "des-cycles",
        "haul-cycles",
        "psds",
        "comminution-sweeps",
        "isaac-lab-rollouts",
        "physics-fields",
        "question-sets",
        "plausibility-pairs",
        "ore-deposits",
    }
)
TESTS = ("c2st", "tstr")
VERDICTS = ("pending", "pass", "warn", "fail")
METRIC_NAMES = ("auc", "auc-minus-real-baseline", "tstr-trtr-ratio")
REQUIRED = (
    "id",
    "title",
    "spdx",
    "licence_class",
    "redistribution",
    "files_sha256",
    "generator",
    "config_sha256",
    "seeds",
    "priors",
    "assets",
)
OPTIONAL = ("attribution",)
SECTIONS = (
    "What and why",
    "Composition",
    "Collection and provenance",
    "Licence and attribution",
    "Size checksums and access",
    "Assumptions and limits",
    "In PitStudio",
)


def validation_class_for(set_type: str) -> str:
    """The one validation class of a synthetic set type (FR-008-36)."""
    if set_type in VALIDATED_TYPES:
        return VALIDATED
    if set_type in DESCRIPTIVE_TYPES:
        return DESCRIPTIVE
    if set_type in UNVALIDATED_TYPES:
        return UNVALIDATED
    raise ValueError(f"unknown synthetic set type {set_type!r}")


def _validation_entry(set_type: str, real_reference: str | None) -> dict[str, Any]:
    klass = validation_class_for(set_type)
    if klass == VALIDATED:
        if not real_reference:
            raise ValueError(f"a {VALIDATED} set needs `real_reference`")
        return {
            "class": VALIDATED,
            "real_reference": real_reference,
            "tests": [{"test": t, "verdict": "pending", "metric": None} for t in VALIDATED_TYPES[set_type]],
        }
    if klass == DESCRIPTIVE:
        entry: dict[str, Any] = {"class": DESCRIPTIVE, "basis": "single real event"}
        if real_reference:
            entry["real_reference"] = real_reference
        return entry
    return {"class": UNVALIDATED, "label": HONESTY_LABEL, "c2st_tstr": "not-applicable"}


def _check_schema(card: Mapping[str, Any]) -> None:
    failures = schema_errors("data-card.schema.json", card)
    if failures:
        pointer, message = failures[0]
        raise ValueError(f"the card fails the data-card schema at {pointer or '/'}: {message}")


def build_synthetic_card(set_type: str, **fields: Any) -> dict[str, Any]:
    """The front matter of a synthetic set's card, with `synthetic: true` and the validation entry of its class.

    `fields` are `id`, `title`, `spdx`, `licence_class`, `redistribution`, `files_sha256`, `generator`, `config_sha256`,
    `seeds`, `priors`, `assets`, optionally `attribution`, and `real_reference` for the classes that name one. A missing
    field or one the schema refuses raises `ValueError`.
    """
    if fields.pop("synthetic", True) is not True:
        raise ValueError("a synthetic set is always `synthetic: true`")
    real_reference = fields.pop("real_reference", None)
    missing = [name for name in REQUIRED if name not in fields]
    if missing:
        raise ValueError(f"missing card field(s): {', '.join(missing)}")
    unknown = sorted(set(fields) - set(REQUIRED) - set(OPTIONAL))
    if unknown:
        raise ValueError(f"unknown card field(s): {', '.join(unknown)}")
    card: dict[str, Any] = {
        "id": fields["id"],
        "kind": "synthetic",
        "title": fields["title"],
        "spdx": fields["spdx"],
        "licence_class": fields["licence_class"],
        "redistribution": fields["redistribution"],
    }
    if "attribution" in fields:
        card["attribution"] = fields["attribution"]
    card.update(
        files_sha256=copy.deepcopy(fields["files_sha256"]),
        synthetic=True,
        generator=copy.deepcopy(fields["generator"]),
        config_sha256=fields["config_sha256"],
        seeds=copy.deepcopy(fields["seeds"]),
        priors=copy.deepcopy(fields["priors"]),
        assets=copy.deepcopy(fields["assets"]),
        validation=_validation_entry(set_type, real_reference),
    )
    _check_schema(card)
    return card


def _check_metric(metric: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if metric is None:
        return None
    if metric.get("name") not in METRIC_NAMES:
        raise ValueError(f"metric name must be one of {METRIC_NAMES}")
    out = {"name": metric["name"]}
    for key in ("value", "ci95_low", "ci95_high"):
        number = metric.get(key)
        if isinstance(number, bool) or not isinstance(number, int | float) or not math.isfinite(number):
            raise ValueError(f"metric {key} must be a finite number")
        out[key] = float(number)
    return out


def attach_verdict(
    card: Mapping[str, Any], test: str, verdict: str, metric: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """A copy of `card` with the verdict of `test` (`c2st` or `tstr`) set: only for the validated-against-real class.

    For `unvalidated` and `descriptive-only` sets this raises `HonestyRuleViolation` (FR-008-37); the card passed in is
    never modified, whatever happens.
    """
    klass = card["validation"]["class"]
    if klass != VALIDATED:
        raise HonestyRuleViolation(
            f"card {card.get('id')}: a {test!r} verdict cannot be attached to a set of class {klass!r}"
        )
    if test not in TESTS:
        raise ValueError(f"test must be one of {TESTS}")
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    clean = _check_metric(metric)
    new = copy.deepcopy(dict(card))
    for entry in new["validation"]["tests"]:
        if entry["test"] == test:
            entry["verdict"], entry["metric"] = verdict, clean
            break
    else:
        raise ValueError(f"the card has no {test!r} test")
    _check_schema(new)
    return new


def attach_physics_benchmark(card: Mapping[str, Any], benchmark: str, verdict: str) -> dict[str, Any]:
    """A copy of `card` with a physics-benchmark verdict in its own field; the validation class never changes."""
    if verdict not in ("pending", "pass", "fail"):
        raise ValueError("a physics-benchmark verdict is pending, pass or fail")
    new = copy.deepcopy(dict(card))
    entries = [e for e in new["validation"].get("physics_benchmarks", []) if e["benchmark"] != benchmark]
    entries.append({"benchmark": benchmark, "verdict": verdict})
    new["validation"]["physics_benchmarks"] = entries
    _check_schema(new)
    return new


def _dump_front_matter(front: Mapping[str, Any]) -> str:
    return yaml.safe_dump(dict(front), sort_keys=False, allow_unicode=True, width=1000)


def write_card(path: Path | str, front_matter: Mapping[str, Any], body: str) -> None:
    """Write a card file: `---`, the YAML front matter, `---`, a blank line and the body (LF line ends)."""
    text = "---\n" + _dump_front_matter(front_matter) + "---\n\n" + body
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))


_FRONT = re.compile(r"\A---\n(.*?)\n---\n\n?(.*)\Z", re.DOTALL)


def split_card(text: str) -> tuple[Any, str] | None:
    """(parsed front matter, body) of a card text, or None when it has no front matter block."""
    found = _FRONT.match(text.replace(chr(13) + chr(10), chr(10)))  # CRLF line ends read the same
    if found is None:
        return None
    return yaml.safe_load(found.group(1) + "\n"), found.group(2)


def update_card_file(path: Path | str, test: str, verdict: str, metric: Mapping[str, Any] | None = None) -> None:
    """Apply `attach_verdict` to a card file; on `HonestyRuleViolation` (or any error) the file stays byte for byte."""
    target = Path(path)
    parts = split_card(target.read_bytes().decode("utf-8"))
    if parts is None or not isinstance(parts[0], dict):
        raise ValueError(f"{target.name} has no YAML front matter")
    front, body = parts
    write_card(target, attach_verdict(front, test, verdict, metric), body)


@dataclass(frozen=True)
class CardProblem:
    """One disagreement found by the card check: the card, the field, what the registry says and what the card holds."""

    card: str
    field: str
    expected: Any
    actual: Any

    def __str__(self) -> str:
        return f"card {self.card}: field {self.field}: expected {self.expected!r}, the card has {self.actual!r}"


_HEADING = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
_FIXTURE = re.compile(r"\bfixture\b", re.IGNORECASE)


def check_card(card_path: Path | str, entry: Mapping[str, Any]) -> list[CardProblem]:
    """Compare one card file with its registry entry (FR-008-43, FR-008-44, FR-008-49).

    The front matter must be valid against the data-card schema and agree with the entry on `id`, `spdx`,
    `licence_class`, `redistribution` and `files_sha256`; the body must have the seven required sections as headings; a
    fixture source's card must say "fixture". An empty list means the card passes.
    """
    ident = str(entry.get("id"))
    problems: list[CardProblem] = []
    try:
        text = Path(card_path).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [CardProblem(ident, "card", f"a readable card file {Path(card_path).name}", type(exc).__name__)]
    try:
        parts = split_card(text)
    except yaml.YAMLError:
        parts = None
        problems.append(CardProblem(ident, "front_matter", "YAML front matter", "not valid YAML"))
    else:
        if parts is None:
            problems.append(CardProblem(ident, "front_matter", "YAML front matter between --- lines", "absent"))
        elif not isinstance(parts[0], dict):
            problems.append(CardProblem(ident, "front_matter", "a YAML mapping", type(parts[0]).__name__))
            parts = None
    body = text
    if parts is not None:
        front, body = parts
        failures = schema_errors("data-card.schema.json", front)
        if failures:
            pointer, message = failures[0]
            problems.append(
                CardProblem(
                    ident, "front_matter", "valid against data-card.schema.json", f"{pointer or '/'}: {message}"
                )
            )
        else:
            expected = {
                "id": entry.get("id"),
                "spdx": entry.get("spdx"),
                "licence_class": entry.get("licence_class"),
                "redistribution": entry.get("redistribution"),
                "files_sha256": [f.get("sha256") for f in entry.get("files", [])],
            }
            problems.extend(
                CardProblem(ident, name, value, front.get(name))
                for name, value in expected.items()
                if front.get(name) != value
            )
    headings = {m.group(1).strip() for m in _HEADING.finditer(body)}
    problems.extend(CardProblem(ident, f"section: {s}", s, None) for s in SECTIONS if s not in headings)
    if entry.get("fixture") and not _FIXTURE.search(text):
        problems.append(CardProblem(ident, "fixture", 'the word "fixture"', None))
    return problems


def check_cards(
    cards_dir: Path | str, registry_path: Path | str, *, schema_path: Path | str | None = None
) -> list[CardProblem]:
    """Check `<cards_dir>/<id>.md` for every registry entry; a missing card file is a problem (field `card`)."""
    from pitstudio_pipeline.download.registry import load_registry

    registry = load_registry(registry_path, schema_path=schema_path)
    problems: list[CardProblem] = []
    for entry in registry["sources"]:
        card = Path(cards_dir) / f"{entry['id']}.md"
        if card.is_file():
            problems.extend(check_card(card, entry))
        else:
            problems.append(CardProblem(entry["id"], "card", f"data/cards/{entry['id']}.md", "missing"))
    return problems

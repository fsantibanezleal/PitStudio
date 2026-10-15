# ruff: noqa: E501, PT018
"""T-008-060: data-card front matter against the schema, registry <-> card field equality, required sections; a CI failure
names the card, the field and both values.

Requirements: FR-008-43, FR-008-44, FR-008-49.

Spec: specs/008-data-pipeline/spec.md FR-008-43 (every registry entry has `data/cards/<id>.md`; its front matter is valid
against `contracts/data-card.schema.json`; its id, SPDX id, licence class, redistribution class and SHA-256 list equal the
registry entry's; its body has the sections What and why, Composition, Collection and provenance, Licence and attribution,
Size checksums and access, Assumptions and limits, In PitStudio), FR-008-44 (a disagreement or a missing section fails the
CI card check, naming the card, the field and both values), FR-008-49 (for a fixture source the card check requires the card
to say "fixture").

Oracle: hand-built registry entries and cards derived from the spec's own card example
(`contracts/examples/data-card.valid.json`, the Mendeley card front matter) with exactly one disagreement each; the data-card
JSON Schema (jsonschema) for the front matter.

Expected API of the implementation (module `pitstudio_pipeline.cards`, usable from the CI check):
- `check_card(card_path, entry) -> list[CardProblem]`: `entry` is a registry entry mapping; each `CardProblem` has `.card`
  (the card id), `.field`, `.expected` (the registry value or the required thing), `.actual` (what the card holds), and a
  `str()` that contains the card id, the field name and both values; an empty list means the card passes. The fields compared
  are `id`, `spdx`, `licence_class`, `redistribution`, `files_sha256`; a missing required section gives a problem whose
  `.field` contains the section title; front matter that is absent, not YAML or invalid against the schema gives a problem with
  `.field` `front_matter`; when `entry.get("fixture")` is true the card must contain the word "fixture" (any case) and
  otherwise a problem with `.field` `fixture` is reported.
- `check_cards(cards_dir, registry_path, *, schema_path=None) -> list[CardProblem]`: loads the registry (as `load_registry`)
  and checks `<cards_dir>/<id>.md` for every entry; a missing card file is a problem with `.field` `card`.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import _p008_kit as kit
from pitstudio_pipeline.cards import check_card, check_cards

SECTIONS = [
    "What and why",
    "Composition",
    "Collection and provenance",
    "Licence and attribution",
    "Size checksums and access",
    "Assumptions and limits",
    "In PitStudio",
]
FRONT = json.loads((kit.SPEC008 / "contracts" / "examples" / "data-card.valid.json").read_text(encoding="utf-8"))
SHA = FRONT["files_sha256"][0]


def entry(**over) -> dict:
    e = kit.entry(
        "mendeley-78ht3pjsr4",
        [
            kit.file_rec(
                "https://data.mendeley.com/public-files/datasets/78ht3pjsr4/files/x/file_downloaded",
                None,
                kind="archive",
                name="research-data.7z",
            )
        ],
        spdx="CC-BY-4.0",
        licence_class="attribution",
        redistribution="derived-only",
        attribution=FRONT["attribution"],
    )
    e["files"][0]["sha256"], e["files"][0]["bytes"] = SHA, 4_230_116_058
    e.update(over)
    return e


def body(skip: str | None = None, extra: str = "") -> str:
    parts = [f"## {s}\n\nText about {s.lower()}.\n" for s in SECTIONS if s != skip]
    return "\n".join(parts) + extra


def write(path: Path, front: dict | None, text: str) -> Path:
    head = "" if front is None else "---\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True) + "---\n\n"
    path.write_text(head + text, encoding="utf-8")
    return path


def problems(tmp: Path, front: dict | None = None, text: str | None = None, ent: dict | None = None):
    p = write(
        tmp / "mendeley-78ht3pjsr4.md",
        copy.deepcopy(FRONT) if front is None else front,
        body() if text is None else text,
    )
    return check_card(p, ent if ent is not None else entry())


# ------------------------------------------------------------------------------------------------ FR-008-43
@pytest.mark.req("FR-008-43")
def test_the_spec_example_front_matter_is_itself_valid() -> None:
    assert kit.schema_errors("data-card.schema.json", FRONT) == []


@pytest.mark.req("FR-008-43")
def test_a_consistent_card_passes(tmp_path: Path) -> None:
    assert problems(tmp_path) == []


@pytest.mark.req("FR-008-43")
def test_sha256_list_order_and_content_must_match(tmp_path: Path) -> None:
    ent = entry()
    ent["files"].append(kit.file_rec("https://example.org/b.bin", kit.payload(10, 1)))
    two = copy.deepcopy(FRONT)
    two["files_sha256"] = [SHA, ent["files"][1]["sha256"]]
    assert problems(tmp_path, two, ent=ent) == []
    swapped = copy.deepcopy(two)
    swapped["files_sha256"].reverse()
    assert [p.field for p in problems(tmp_path, swapped, ent=ent)] == ["files_sha256"]


@pytest.mark.req("FR-008-43")
def test_unpinned_files_appear_as_null_in_the_card_list(tmp_path: Path) -> None:
    ent = entry()
    ent["files"][0]["sha256"] = None
    front = copy.deepcopy(FRONT)
    front["files_sha256"] = [None]
    assert problems(tmp_path, front, ent=ent) == []


@pytest.mark.req("FR-008-43")
def test_every_required_section_is_needed(tmp_path: Path) -> None:
    for s in SECTIONS:
        found = problems(tmp_path, text=body(skip=s))
        assert len(found) == 1 and s in found[0].field, s


@pytest.mark.req("FR-008-43")
def test_sections_must_be_headings_not_just_words(tmp_path: Path) -> None:
    text = body(skip="Composition") + "\nThe Composition of the data is described elsewhere.\n"
    found = problems(tmp_path, text=text)
    assert len(found) == 1 and "Composition" in found[0].field


@pytest.mark.req("FR-008-43")
@pytest.mark.parametrize(
    "kind",
    ["no-front-matter", "unterminated", "not-yaml", "list-not-mapping", "empty-file", "unknown-field", "bad-digest"],
)
def test_broken_front_matter_is_a_problem_not_a_crash(kind: str, tmp_path: Path) -> None:
    p = tmp_path / "mendeley-78ht3pjsr4.md"
    front = yaml.safe_dump(FRONT, sort_keys=False)
    text = {
        "no-front-matter": body(),
        "unterminated": "---\n" + front + body(),
        "not-yaml": "---\n: : [unclosed\n---\n\n" + body(),
        "list-not-mapping": "---\n- a\n- b\n---\n\n" + body(),
        "empty-file": "",
        "unknown-field": "---\n" + front + "surprise: 1\n---\n\n" + body(),
        "bad-digest": "---\n" + front.replace(SHA, SHA[:-1]) + "---\n\n" + body(),
    }[kind]
    p.write_text(text, encoding="utf-8")
    found = check_card(p, entry())
    assert found and any("front_matter" in f.field or f.field in {"files_sha256"} for f in found)


# ------------------------------------------------------------------------------------------------ FR-008-44
@pytest.mark.req("FR-008-44")
@pytest.mark.parametrize(
    ("field", "card_value", "registry_value"),
    [
        ("spdx", "CC0-1.0", "CC-BY-4.0"),
        ("licence_class", "open-no-attribution", "attribution"),
        ("redistribution", "redistributable", "derived-only"),
        ("id", "some-other-set", "mendeley-78ht3pjsr4"),
    ],
)
def test_disagreement_names_the_card_the_field_and_both_values(
    field: str, card_value: str, registry_value: str, tmp_path: Path
) -> None:
    front = copy.deepcopy(FRONT)
    front[field] = card_value
    found = [p for p in problems(tmp_path, front) if p.field == field]
    assert len(found) == 1
    text = str(found[0])
    assert "mendeley-78ht3pjsr4" in text and field in text and card_value in text and registry_value in text
    assert {found[0].expected, found[0].actual} == {card_value, registry_value}


@pytest.mark.req("FR-008-44")
def test_registry_change_without_card_change_is_caught(tmp_path: Path) -> None:
    ent = entry(spdx="CC0-1.0", licence_class="open-no-attribution")
    ent.pop("attribution", None)
    found = problems(tmp_path, ent=ent)
    assert {p.field for p in found} >= {"spdx", "licence_class"}


@pytest.mark.req("FR-008-44")
def test_check_cards_reports_a_missing_card_file(tmp_path: Path) -> None:
    cards = tmp_path / "cards"
    cards.mkdir()
    write(cards / "mendeley-78ht3pjsr4.md", copy.deepcopy(FRONT), body())
    second = kit.entry("lone", [kit.file_rec("https://example.org/lone.bin", kit.payload(10, 2))])
    reg = kit.write_registry(tmp_path / "cfg", [entry(), second])
    found = check_cards(cards, reg, schema_path=kit.draft_schema_path("sources.schema.json"))
    assert [(p.card, p.field) for p in found] == [("lone", "card")]
    assert "lone" in str(found[0])


@pytest.mark.req("FR-008-44")
def test_the_repository_cards_agree_with_the_repository_registry() -> None:
    assert check_cards(kit.ROOT / "data" / "cards", kit.ROOT / "data" / "sources.yaml") == []


# ------------------------------------------------------------------------------------------------ FR-008-49
@pytest.mark.req("FR-008-49")
def test_a_fixture_source_card_must_say_fixture(tmp_path: Path) -> None:
    ent = entry(fixture=True)
    found = problems(tmp_path, ent=ent)
    assert [p.field for p in found] == ["fixture"] and "mendeley-78ht3pjsr4" in str(found[0])
    assert problems(tmp_path, text=body(extra="\nThis source is a FIXTURE: a synthetic stand-in.\n"), ent=ent) == []


@pytest.mark.req("FR-008-49")
def test_a_non_fixture_card_is_not_required_to_say_fixture(tmp_path: Path) -> None:
    assert problems(tmp_path, ent=entry(fixture=False)) == []

"""T-010-094: the `section_sha256` of a slope-results document is verified against the section it names.

Requirement: FR-010-45 ("If the `section_sha256` of a slope-results document is not the SHA-256 of the RFC 8785
canonical JSON
of the section it names, then the results loader shall reject it with error class `section-digest-mismatch`").
Spec: specs/010-slope/spec.md section 3.4; plan.md row FR-010-45 ("reference implementation: `hashlib.sha256` of the
canonical
JSON of a fixture section; one value changed gives `section-digest-mismatch`").

Expected API (module `pitstudio.slope.results`, standard library plus `pitstudio.contracts.jcs`):
- `section_digest(section: dict) -> str`: SHA-256 hex of the RFC 8785 canonical JSON (UTF-8) of the section document.
- `ResultsError(ValueError)`: `error_class` (here "section-digest-mismatch") and `field` (JSON pointer, e.g.
  "/sections/0/section_sha256").
- `load_results(document, *, sections) -> Results`: `sections` maps section_id -> the section document the results name;
  every entry of `document["sections"]` is checked: its `section_sha256` must equal
  `section_digest(sections[section_id])`.
  A section id without a document in `sections` raises ResultsError("section-missing").

Oracle: the reference implementation `hashlib.sha256` over `pitstudio.contracts.jcs.canonicalize` (spec 001, already
implemented and tested), computed in the test; the contract example `slope-results.valid.json` with its digests
replaced by the
correct ones; one changed value changes the digest.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio.slope import results  # noqa: E402

from pitstudio.contracts.jcs import canonicalize  # noqa: E402

EXAMPLES = ROOT / "specs" / "010-slope" / "contracts" / "examples"


def _digest(section: dict) -> str:
    return hashlib.sha256(canonicalize(section)).hexdigest()


def _sections() -> dict[str, dict]:
    a = json.loads((EXAMPLES / "slope-section.valid.json").read_text(encoding="utf-8"))
    b = copy.deepcopy(a)
    b["section_id"] = "c1-degenerate-fixture"
    b["materials"][0]["cohesion_kpa"] = 0.0
    return {a["section_id"]: a, b["section_id"]: b}


def _results(sections: dict[str, dict]) -> dict:
    doc = json.loads((EXAMPLES / "slope-results.valid.json").read_text(encoding="utf-8"))
    for entry in doc["sections"]:
        entry["section_sha256"] = _digest(sections[entry["section_id"]])
    return doc


@pytest.mark.req("FR-010-45")
def test_section_digest_is_sha256_of_the_canonical_json() -> None:
    for section in _sections().values():
        assert results.section_digest(section) == _digest(section)


@pytest.mark.req("FR-010-45")
def test_the_digest_ignores_key_order_and_number_spelling_but_not_values() -> None:
    section = _sections()["c1-planar-20m-45deg"]
    reordered = dict(reversed(list(section.items())))
    assert results.section_digest(reordered) == results.section_digest(section)
    respelled = copy.deepcopy(section)
    respelled["materials"][0]["cohesion_kpa"] = 20  # 20 and 20.0 are one number in RFC 8785
    assert results.section_digest(respelled) == results.section_digest(section)
    changed = copy.deepcopy(section)
    changed["materials"][0]["cohesion_kpa"] = 20.5
    assert results.section_digest(changed) != results.section_digest(section)


@pytest.mark.req("FR-010-45")
def test_results_with_the_right_digests_load() -> None:
    sections = _sections()
    assert results.load_results(_results(sections), sections=sections) is not None


@pytest.mark.req("FR-010-45")
@pytest.mark.parametrize("which", [0, 1])
def test_a_changed_value_in_the_named_section_is_rejected_naming_the_field(which) -> None:
    sections = _sections()
    doc = _results(sections)  # digests of the original sections
    target = doc["sections"][which]["section_id"]
    sections[target]["pore_pressure_ratio"] = 0.01  # one value changed after the digest was recorded
    with pytest.raises(results.ResultsError) as exc:
        results.load_results(doc, sections=sections)
    assert exc.value.error_class == "section-digest-mismatch"
    assert exc.value.field == f"/sections/{which}/section_sha256"
    assert target in str(exc.value)
    assert isinstance(exc.value, ValueError)


@pytest.mark.req("FR-010-45")
@pytest.mark.parametrize("bad", ["0" * 64, "f" * 64, "a" * 63, "", "G" * 64, "A" * 64])
def test_a_wrong_or_malformed_digest_is_rejected(bad) -> None:
    sections = _sections()
    doc = _results(sections)
    doc["sections"][0]["section_sha256"] = bad
    with pytest.raises(results.ResultsError) as exc:
        results.load_results(doc, sections=sections)
    assert exc.value.error_class in {
        "section-digest-mismatch",
        "results-invalid",
    }  # a malformed digest may fail the schema first
    assert exc.value.field.startswith("/sections/0")


@pytest.mark.req("FR-010-45")
def test_a_digest_of_another_section_is_a_mismatch_even_when_well_formed() -> None:
    sections = _sections()
    doc = _results(sections)
    doc["sections"][0]["section_sha256"] = doc["sections"][1]["section_sha256"]
    with pytest.raises(results.ResultsError) as exc:
        results.load_results(doc, sections=sections)
    assert exc.value.error_class == "section-digest-mismatch"


@pytest.mark.req("FR-010-45")
def test_a_named_section_without_a_document_is_reported() -> None:
    sections = _sections()
    doc = _results(sections)
    del sections["c1-degenerate-fixture"]
    with pytest.raises(results.ResultsError) as exc:
        results.load_results(doc, sections=sections)
    assert exc.value.error_class == "section-missing"
    assert exc.value.field == "/sections/1/section_id"

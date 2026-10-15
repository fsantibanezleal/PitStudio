# ruff: noqa: E501, PT018
"""T-007-070: every A1/A2 artefact header and manifest entry carries the exact label and the cycle-time bias note, and no C2ST or TSTR field or claim.

Requirements: FR-007-41, FR-000-09.

Spec: specs/007-haulage-dispatch/spec.md FR-007-41 (every A1 and A2 artefact (trace, KPI table, evaluation table, energy table) carries the label "calibrated synthetic — not validated against real data" and the known DES cycle-time bias note, and makes no C2ST or TSTR claim),
FR-000-09 (the product labels every data type that has no real reference as "calibrated synthetic — not validated against real data" and makes no C2ST or TSTR claim for it), the contracts `des-trace.schema.json`, `dispatch-eval.schema.json` and `haul-energy.schema.json`
(`$defs/honesty`: `label` and `bias_note` are constants) and plan.md ("Honesty stamp: writes the label and the bias note into every artefact header and manifest entry").

Matching rule (stated here because the spec names the terms only): case-insensitive, a term is found where it is not preceded or followed by a letter or digit, in any dict key and any string value at any depth.

Oracle: the exact strings written out in tests/support/p007_kit.py from the contract constants (label with the em dash U+2014, the bias note sentence); the spec's own valid examples (`des-trace.valid.json`, `dispatch-eval.valid.json`, `haul-energy.valid.json`) with their honesty block removed, which the schemas then reject and
which must validate again after stamping; a recursive scan for the forbidden terms in keys and values; hostile variants of the label (hyphen for the dash, case, whitespace, truncation, normalisation form, a validated-against-real claim).

Expected API (module `pitstudio.haulage.honesty`; error `HonestyViolation(HaulError)` in `pitstudio.haulage.errors` with attribute `path`, the JSON-pointer-like location of the first problem):
    LABEL: str, BIAS_NOTE: str        the exact constants above
    stamp(artefact: dict, kind: str) -> dict
        kinds "evaluation" and "energy": a deep copy with top-level `honesty` = {"label": LABEL, "bias_note": BIAS_NOTE} (the block of the schemas); kind "trace": the block in the trace header, `header.honesty`; kind "kpi" (the KPI table of the KPI layer): a deep copy with top-level
        `label` and `bias_note`;
        idempotent; raises HonestyViolation when the artefact already carries another label or note (never overwrites it) or any key or string value that names C2ST or TSTR (any case), TypeError for a non-dict, ValueError for an unknown kind. The input is never modified.
    check(artefact: dict, kind: str) -> None      raises HonestyViolation (with `path`) unless the label and note are present and exactly the constants and nothing names C2ST or TSTR anywhere in the artefact
    manifest_entry(kind: str, *, name: str, sha256: str, size_bytes: int) -> dict
        {"name", "sha256", "bytes", "artefact_kind" ("trace" for kind "trace", "table" for the others), "label", "bias_note"}; name must be a relative path without "..", sha256 64 lower-case hex, size_bytes a non-negative int below 2^53, else ValueError.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import unicodedata
from pathlib import Path

import pytest

from pitstudio.haulage import honesty
from pitstudio.haulage.errors import HonestyViolation
from pitstudio.haulage.honesty import BIAS_NOTE, LABEL, check, manifest_entry, stamp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit as kit

EXPECTED_LABEL = "calibrated synthetic \u2014 not validated against real data"
EXPECTED_NOTE = "Known DES bias: simulated truck cycle times tend to underestimate short hauls and overestimate long hauls; no real haul telemetry exists to correct it."
KINDS = {
    "trace": ("des-trace.valid.json", "des-trace"),
    "evaluation": ("dispatch-eval.valid.json", "dispatch-eval"),
    "energy": ("haul-energy.valid.json", "haul-energy"),
}
TERM = re.compile(r"(?<![a-z0-9])(c2st|tstr)(?![a-z0-9])", re.IGNORECASE)


def kpi_table() -> dict:
    return {
        "window": {"start": 0.0, "end": 3600.0, "hours": 1.0},
        "fleet": {"tonnes_t": 1260.0, "production_tph": 1260.0, "cycles": 6, "cycles_per_h": 6.0},
        "loaders": [],
    }


def block(doc: dict, kind: str) -> dict:
    """The honesty block of an artefact: the trace header's, or the top-level one."""
    return doc["header"]["honesty"] if kind == "trace" else doc["honesty"]


def put_block(doc: dict, kind: str, value) -> None:
    if kind == "trace":
        doc["header"]["honesty"] = value
    else:
        doc["honesty"] = value


def bare(kind: str) -> dict:
    """The spec's valid example of the kind without its honesty block."""
    if kind == "kpi":
        return kpi_table()
    doc = kit.example(KINDS[kind][0])
    if kind == "trace":
        doc["header"].pop("honesty", None)
    else:
        doc.pop("honesty", None)
    return doc


def terms_in(obj, path="$"):
    """Yield (path, text) for every key or string value that names a forbidden term."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if TERM.search(str(k)):
                yield f"{path}.{k}", str(k)
            yield from terms_in(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from terms_in(v, f"{path}[{i}]")
    elif isinstance(obj, str) and TERM.search(obj):
        yield path, obj


# ---------------------------------------------------------------------------------------------------------------------
# the constants and the spec's own examples
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-41")
def test_the_label_and_the_bias_note_are_exactly_the_contract_strings():
    assert LABEL == EXPECTED_LABEL == kit.LABEL
    assert BIAS_NOTE == EXPECTED_NOTE == kit.BIAS_NOTE
    assert "\u2014" in LABEL and "-" not in LABEL.replace("not validated", "")  # the em dash, not a hyphen
    assert honesty.LABEL is LABEL


@pytest.mark.req("FR-007-41")
@pytest.mark.parametrize(
    "name",
    ["des-trace.valid.json", "des-trace.valid-lp-fallback.json", "dispatch-eval.valid.json", "haul-energy.valid.json"],
)
def test_the_spec_examples_carry_the_exact_label_and_note_and_no_c2st_or_tstr(name):
    doc = kit.example(name)
    assert block(doc, "trace" if name.startswith("des-trace") else "x") == {
        "label": EXPECTED_LABEL,
        "bias_note": EXPECTED_NOTE,
    }
    assert list(terms_in(doc)) == []


@pytest.mark.req("FR-000-09")
@pytest.mark.parametrize("kind", ["trace", "evaluation", "energy"])
def test_the_schemas_reject_an_artefact_without_the_block_and_accept_it_after_stamping(kind):
    validator = kit.schema_validator(KINDS[kind][1])
    doc = bare(kind)
    assert list(validator.iter_errors(doc)), "the example without its honesty block should be invalid"
    stamped = stamp(doc, kind)
    assert not list(validator.iter_errors(stamped)), [e.message for e in validator.iter_errors(stamped)][:3]
    assert block(stamped, kind) == {"label": EXPECTED_LABEL, "bias_note": EXPECTED_NOTE}
    unstamped = copy.deepcopy(stamped)
    if kind == "trace":
        unstamped["header"].pop("honesty")
    else:
        unstamped.pop("honesty")
    assert unstamped == doc  # nothing else changed


# ---------------------------------------------------------------------------------------------------------------------
# stamp and check
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-41")
def test_the_kpi_table_is_stamped_with_top_level_fields():
    t = stamp(kpi_table(), "kpi")
    assert t["label"] == EXPECTED_LABEL and t["bias_note"] == EXPECTED_NOTE and "honesty" not in t
    assert {k: v for k, v in t.items() if k not in {"label", "bias_note"}} == kpi_table()


@pytest.mark.req("FR-007-41")
@pytest.mark.parametrize("kind", ["trace", "evaluation", "energy", "kpi"])
def test_stamping_is_idempotent_and_never_modifies_its_input(kind):
    doc = bare(kind)
    before = json.dumps(doc, sort_keys=True)
    once = stamp(doc, kind)
    assert json.dumps(doc, sort_keys=True) == before
    assert stamp(once, kind) == once
    assert once is not doc
    check(once, kind)


@pytest.mark.req("FR-007-41")
@pytest.mark.parametrize("kind", ["trace", "evaluation", "energy", "kpi"])
def test_check_accepts_a_stamped_artefact_and_names_a_missing_block(kind):
    check(stamp(bare(kind), kind), kind)
    with pytest.raises(HonestyViolation) as ei:
        check(bare(kind), kind)
    assert "label" in ei.value.path or "honesty" in ei.value.path


VARIANTS = {
    "hyphen instead of the em dash": "calibrated synthetic - not validated against real data",
    "en dash": "calibrated synthetic \u2013 not validated against real data",
    "capitalised": "Calibrated synthetic \u2014 not validated against real data",
    "trailing space": EXPECTED_LABEL + " ",
    "leading space": " " + EXPECTED_LABEL,
    "truncated": "calibrated synthetic",
    "validated claim": "calibrated synthetic \u2014 validated against real data",
    "empty": "",
    "decomposed (NFD)": unicodedata.normalize("NFD", EXPECTED_LABEL.replace("\u2014", "\u00e9")),
    "mojibake": EXPECTED_LABEL.encode("utf-8").decode("cp1252", errors="replace"),
    "other language": "sint\u00e9tico calibrado \u2014 no validado con datos reales",
}


@pytest.mark.req("FR-007-41")
@pytest.mark.parametrize("variant", list(VARIANTS), ids=list(VARIANTS))
@pytest.mark.parametrize("kind", ["trace", "energy"])
def test_an_altered_label_is_rejected_by_check_and_never_overwritten_by_stamp(kind, variant):
    doc = bare(kind)
    put_block(doc, kind, {"label": VARIANTS[variant], "bias_note": EXPECTED_NOTE})
    with pytest.raises(HonestyViolation) as ei:
        check(doc, kind)
    assert ei.value.path.endswith("label")
    with pytest.raises(HonestyViolation):
        stamp(doc, kind)
    assert block(doc, kind)["label"] == VARIANTS[variant]


@pytest.mark.req("FR-007-41")
@pytest.mark.parametrize(
    "note",
    [
        "",
        "Known DES bias",
        EXPECTED_NOTE.lower(),
        EXPECTED_NOTE + " ",
        EXPECTED_NOTE.replace("underestimate", "overestimate"),
        "no bias is known",
    ],
)
def test_an_altered_bias_note_is_rejected(note):
    doc = bare("trace")
    put_block(doc, "trace", {"label": EXPECTED_LABEL, "bias_note": note})
    with pytest.raises(HonestyViolation) as ei:
        check(doc, "trace")
    assert ei.value.path.endswith("bias_note")
    with pytest.raises(HonestyViolation):
        stamp(doc, "trace")


@pytest.mark.req("FR-007-41")
@pytest.mark.parametrize("kind", ["trace", "energy"])
@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        "calibrated synthetic",
        7,
        {"label": EXPECTED_LABEL},
        {"bias_note": EXPECTED_NOTE},
        {"label": EXPECTED_LABEL, "bias_note": EXPECTED_NOTE, "extra": 1},
    ],
)
def test_a_malformed_honesty_block_is_rejected(kind, value):
    doc = bare(kind)
    put_block(doc, kind, value)
    with pytest.raises(HonestyViolation):
        check(doc, kind)


# ---------------------------------------------------------------------------------------------------------------------
# no C2ST or TSTR claim
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-000-09")
@pytest.mark.parametrize("kind", ["trace", "evaluation", "energy", "kpi"])
@pytest.mark.parametrize(
    "inject",
    [
        {"c2st": 0.52},
        {"C2ST_auc": 0.5},
        {"tstr": {"ratio": 0.9}},
        {"metrics": {"TSTR-score": 1.0}},
        {"notes": "passes the C2ST test"},
        {"notes": ["fine", "Train-on-synthetic TSTR ratio 0.93"]},
        {"summary": {"claims": [{"text": "c2st \u2248 0.5"}]}},
    ],
)
def test_a_c2st_or_tstr_field_or_claim_anywhere_is_rejected(kind, inject):
    doc = bare(kind)
    doc.update(inject)
    with pytest.raises(HonestyViolation) as ei:
        stamp(doc, kind)
    assert ei.value.path.startswith("$")
    stamped = {**stamp(bare(kind), kind), **inject}
    with pytest.raises(HonestyViolation):
        check(stamped, kind)


@pytest.mark.req("FR-000-09")
def test_the_terms_are_matched_as_whole_alphanumeric_words_in_any_case_but_not_inside_other_words():
    ok = bare("trace")
    ok["notes"] = "latstrain and c2stack are ordinary tokens"  # contain the letters of the terms inside longer words
    check(stamp(ok, "trace"), "trace")
    for text in [
        "C2ST",
        "c2st",
        "TsTr",
        "tstr results",
        "see c2st_auc",
        "x-TSTR-y",
        "(tstr)",
    ]:  # '_' and '-' and punctuation are word boundaries
        bad = bare("trace")
        bad["notes"] = text
        with pytest.raises(HonestyViolation):
            stamp(bad, "trace")


# ---------------------------------------------------------------------------------------------------------------------
# manifest entries
# ---------------------------------------------------------------------------------------------------------------------
SHA = "ab" * 32


@pytest.mark.req("FR-007-41")
@pytest.mark.parametrize(
    ("kind", "artefact_kind"), [("trace", "trace"), ("evaluation", "table"), ("energy", "table"), ("kpi", "table")]
)
def test_a_manifest_entry_carries_the_label_and_the_note(kind, artefact_kind):
    e = manifest_entry(kind, name=f"a1/{kind}.json", sha256=SHA, size_bytes=1234)
    assert e == {
        "name": f"a1/{kind}.json",
        "sha256": SHA,
        "bytes": 1234,
        "artefact_kind": artefact_kind,
        "label": EXPECTED_LABEL,
        "bias_note": EXPECTED_NOTE,
    }
    manifest = kit.schema_validator("manifest", "output_file")
    assert {k: e[k] for k in ("name", "sha256", "bytes")} and not list(
        manifest.iter_errors({k: e[k] for k in ("name", "sha256", "bytes")})
    )


@pytest.mark.req("FR-007-41")
@pytest.mark.parametrize(
    "kw",
    [
        {"name": ""},
        {"name": "../escape.json"},
        {"name": "/abs/path.json"},
        {"name": "C:\\x.json"},
        {"name": "a/../../b.json"},
        {"name": None},
        {"sha256": "ab" * 31},
        {"sha256": "AB" * 32},
        {"sha256": "zz" * 32},
        {"sha256": None},
        {"size_bytes": -1},
        {"size_bytes": 2**53},
        {"size_bytes": 1.5},
        {"size_bytes": True},
        {"size_bytes": "12"},
    ],
)
def test_a_malformed_manifest_entry_is_rejected(kw):
    args = {"name": "a1/trace.json", "sha256": SHA, "size_bytes": 10, **kw}
    with pytest.raises(ValueError):  # noqa: PT011
        manifest_entry("trace", **args)


# ---------------------------------------------------------------------------------------------------------------------
# hostile arguments
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-41")
@pytest.mark.parametrize("bad", [None, [], "trace", 3, (1, 2), b"{}"])
def test_stamping_something_that_is_not_a_dict_is_a_type_error(bad):
    with pytest.raises(TypeError):
        stamp(bad, "trace")
    with pytest.raises(TypeError):
        check(bad, "trace")


@pytest.mark.req("FR-007-41")
@pytest.mark.parametrize("kind", ["", "Trace", "kpis", "model-card", None, 3, "trace "])
def test_an_unknown_kind_is_rejected(kind):
    with pytest.raises((ValueError, TypeError)):
        stamp(bare("trace"), kind)
    with pytest.raises((ValueError, TypeError)):
        check(bare("trace"), kind)
    with pytest.raises((ValueError, TypeError)):
        manifest_entry(kind, name="a/b.json", sha256=SHA, size_bytes=1)


@pytest.mark.req("FR-007-41")
def test_deeply_nested_and_large_artefacts_are_scanned_without_error():
    doc = bare("evaluation")
    nest = cur = {}
    for _ in range(200):
        cur["next"] = {}
        cur = cur["next"]
    doc["extra_depth"] = nest
    doc["many"] = [{"k": str(i)} for i in range(20_000)]
    out = stamp(doc, "evaluation")
    assert block(out, "evaluation")["label"] == EXPECTED_LABEL
    cur["deep"] = "tstr hidden at the bottom"
    with pytest.raises(HonestyViolation):
        stamp(doc, "evaluation")
    assert copy.deepcopy(doc["many"][:1]) == [{"k": "0"}]

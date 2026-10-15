# ruff: noqa: E501, PT011, PT018
"""T-008-042: validation classes per type, the exact honesty label, `HonestyRuleViolation` on any C2ST/TSTR verdict for an
unvalidated or descriptive-only set.

Requirements: FR-008-36, FR-008-37.

Spec: specs/008-data-pipeline/spec.md FR-008-36 (exactly one validation class per synthetic set: `validated-against-real` for
fragment images and terrain statistics, verdict `pending` until `s50_evaluate` sets it; `descriptive-only (single real
event)` for Voight creep series; `unvalidated` for every other type, with the exact label "calibrated synthetic - not validated
against real data" (em dash, U+2014) and `c2st_tstr: not-applicable`; physics-benchmark verdicts may be recorded in a separate
field) and FR-008-37 (attaching a C2ST or TSTR verdict to an `unvalidated` or `descriptive-only` set raises
`HonestyRuleViolation` and leaves the card unchanged); contract `contracts/data-card.schema.json`.

Oracle: the class table of FR-008-36 written out below (every type named in the spec, in the kebab-case plural used as the set
type id); the label string with its em dash written as `\\u2014` so no encoding can alter it; the card examples of the spec
(`data-card.valid-validated.json`, `valid-unvalidated.json`, `valid-descriptive.json`) as the expected shape of each class.

Expected API of the implementation (module `pitstudio_pipeline.cards`):
- `validation_class_for(set_type) -> str` returning `validated-against-real`, `descriptive-only` or `unvalidated`.
- `build_synthetic_card(set_type, **fields) -> dict` as in test_t_008_041; its `validation` entry is, for the three classes:
  `{"class": "validated-against-real", "real_reference": <given as field `real_reference`>, "tests": [{"test": "c2st",
  "verdict": "pending", "metric": None}, {"test": "tstr", "verdict": "pending", "metric": None}]}`,
  `{"class": "descriptive-only", "basis": "single real event"}` (plus an optional `real_reference`), and
  `{"class": "unvalidated", "label": <exact label>, "c2st_tstr": "not-applicable"}`; never a `tests` list for the last two.
- `attach_verdict(card, test, verdict, metric=None) -> dict` (`test` `c2st` or `tstr`; `verdict` `pending`, `pass`, `warn`,
  `fail`; `metric` None or `{"name", "value", "ci95_low", "ci95_high"}`): returns the card with that test updated for the
  `validated-against-real` class; for the other two raises `pitstudio_pipeline.errors.HonestyRuleViolation` and the card
  passed in is left equal to what it was.
- `attach_physics_benchmark(card, benchmark, verdict) -> dict`: records `{"benchmark", "verdict"}` (`pending`, `pass`, `fail`)
  in `validation["physics_benchmarks"]` for any class without changing the class.
- `write_card(path, front_matter, body) -> None` and `update_card_file(path, test, verdict, metric=None) -> None`: the card file
  is `---`, the YAML front matter, `---`, a blank line and the body; `update_card_file` applies `attach_verdict` to the file and,
  on `HonestyRuleViolation`, leaves the file byte for byte unchanged.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import _p008_kit as kit
import pytest
from pitstudio_pipeline.cards import (
    attach_physics_benchmark,
    attach_verdict,
    build_synthetic_card,
    update_card_file,
    validation_class_for,
    write_card,
)
from pitstudio_pipeline.errors import HonestyRuleViolation

EX = kit.SPEC008 / "contracts" / "examples"
BASE = json.loads((EX / "data-card.valid-unvalidated.json").read_text(encoding="utf-8"))
FIELDS = {
    k: copy.deepcopy(BASE[k])
    for k in (
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
}
LABEL = kit.LABEL
assert LABEL == "calibrated synthetic — not validated against real data"

VALIDATED = ["fragment-images", "terrain-statistics"]
DESCRIPTIVE = ["voight-creep-series"]
UNVALIDATED = [
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
]
METRIC = {"name": "auc", "value": 0.52, "ci95_low": 0.48, "ci95_high": 0.56}


def card(set_type: str):
    extra = {"real_reference": "mendeley-78ht3pjsr4"} if set_type in VALIDATED else {}
    return build_synthetic_card(set_type, **copy.deepcopy(FIELDS), **extra)


@pytest.mark.req("FR-008-36")
@pytest.mark.parametrize(
    ("types", "klass"),
    [(VALIDATED, "validated-against-real"), (DESCRIPTIVE, "descriptive-only"), (UNVALIDATED, "unvalidated")],
)
def test_every_type_has_exactly_the_class_of_the_table(types: list[str], klass: str) -> None:
    for t in types:
        assert validation_class_for(t) == klass, t
        assert card(t)["validation"]["class"] == klass


@pytest.mark.req("FR-008-36")
@pytest.mark.parametrize("set_type", VALIDATED)
def test_validated_class_starts_pending_with_a_real_reference(set_type: str) -> None:
    v = card(set_type)["validation"]
    assert v["real_reference"] == "mendeley-78ht3pjsr4"
    assert v["tests"], "a validated class lists its tests"
    if set_type == "fragment-images":
        assert {t["test"] for t in v["tests"]} == {"c2st", "tstr"}
    assert all(t["verdict"] == "pending" and t["metric"] is None for t in v["tests"])
    assert "label" not in v and "c2st_tstr" not in v and "basis" not in v
    assert kit.schema_errors("data-card.schema.json", card(set_type)) == []


@pytest.mark.req("FR-008-36")
def test_descriptive_class_has_the_single_event_basis_and_no_tests() -> None:
    c = card("voight-creep-series")
    v = c["validation"]
    assert v["class"] == "descriptive-only" and v["basis"] == "single real event"
    assert "tests" not in v and "label" not in v
    assert kit.schema_errors("data-card.schema.json", c) == []


@pytest.mark.req("FR-008-36")
@pytest.mark.parametrize("set_type", UNVALIDATED)
def test_unvalidated_class_carries_the_exact_label_and_no_tests(set_type: str) -> None:
    c = card(set_type)
    v = c["validation"]
    assert v["label"] == LABEL and v["c2st_tstr"] == "not-applicable"
    assert "tests" not in v and "real_reference" not in v and "basis" not in v
    assert kit.schema_errors("data-card.schema.json", c) == []


@pytest.mark.req("FR-008-36")
def test_the_label_is_character_exact_not_a_hyphen_variant() -> None:
    label = card("des-cycles")["validation"]["label"]
    assert "—" in label and " - " not in label and "" + chr(0x2013) + "" not in label
    assert label.encode("utf-8") == "calibrated synthetic — not validated against real data".encode()


@pytest.mark.req("FR-008-36")
def test_a_validated_verdict_can_be_set_later_and_the_card_stays_valid() -> None:
    c = card("fragment-images")
    new = attach_verdict(c, "c2st", "pass", METRIC)
    assert kit.schema_errors("data-card.schema.json", new) == []
    by = {t["test"]: t for t in new["validation"]["tests"]}
    assert by["c2st"]["verdict"] == "pass" and by["c2st"]["metric"] == METRIC
    assert by["tstr"]["verdict"] == "pending"


@pytest.mark.req("FR-008-36")
def test_physics_benchmark_verdicts_live_in_their_own_field_for_every_class() -> None:
    for t in ("des-cycles", "voight-creep-series", "fragment-images"):
        c = card(t)
        klass = c["validation"]["class"]
        new = attach_physics_benchmark(c, "energy-conservation", "pass")
        assert new["validation"]["class"] == klass
        assert new["validation"]["physics_benchmarks"] == [{"benchmark": "energy-conservation", "verdict": "pass"}]
        assert kit.schema_errors("data-card.schema.json", new) == []


# ------------------------------------------------------------------------------------------------ FR-008-37
@pytest.mark.req("FR-008-37")
@pytest.mark.parametrize("set_type", ["des-cycles", "sensor-clouds", "psds", "voight-creep-series", "question-sets"])
@pytest.mark.parametrize("test", ["c2st", "tstr"])
@pytest.mark.parametrize("verdict", ["pass", "warn", "fail", "pending"])
def test_any_verdict_on_an_unvalidated_or_descriptive_set_is_refused_and_the_card_is_unchanged(
    set_type: str, test: str, verdict: str
) -> None:
    c = card(set_type)
    before = copy.deepcopy(c)
    with pytest.raises(HonestyRuleViolation):
        attach_verdict(c, test, verdict, METRIC)
    assert c == before


@pytest.mark.req("FR-008-37")
def test_refusal_on_a_card_file_leaves_the_file_byte_for_byte_unchanged(tmp_path: Path) -> None:
    p = tmp_path / "des-cycles-a1.md"
    write_card(p, card("des-cycles"), "## What and why\n\nSynthetic haul cycles.\n")
    before = p.read_bytes()
    with pytest.raises(HonestyRuleViolation):
        update_card_file(p, "c2st", "pass", METRIC)
    assert p.read_bytes() == before


@pytest.mark.req("FR-008-37")
def test_a_validated_card_file_can_be_updated(tmp_path: Path) -> None:
    p = tmp_path / "muck.md"
    write_card(p, card("fragment-images"), "## What and why\n\nRenders.\n")
    before = p.read_bytes()
    update_card_file(p, "tstr", "warn", METRIC)
    assert p.read_bytes() != before and b"warn" in p.read_bytes()


@pytest.mark.req("FR-008-37")
def test_hostile_verdict_values_never_get_through_on_any_class() -> None:
    c = card("fragment-images")
    for bad_test, bad_verdict in (("ks", "pass"), ("c2st", "maybe"), ("c2st", "PASS"), ("", "pass"), ("c2st", "")):
        with pytest.raises((ValueError, HonestyRuleViolation)):
            attach_verdict(c, bad_test, bad_verdict, None)
    with pytest.raises(ValueError):
        attach_verdict(c, "c2st", "pass", {"name": "auc", "value": float("nan"), "ci95_low": 0.1, "ci95_high": 0.2})

# ruff: noqa: E501
"""T-009-015 - FR-009-10, FR-009-11, FR-009-12: asset licence guard, MakeHuman records, mannequin fallback.

Oracles (independent of the code under test):
- FR-009-10, hand calculation (plan 009 test strategy): an `omniverse://` URL, a path under a vendor asset root and a
  path with no licence record are each refused with error code `asset-licence`, and the error lists EVERY offending path;
  a path with `..` segments is judged by where it resolves (posixpath.normpath), not by how it is written; Windows
  separators are the same separators as `/`. Roots and paths are abstract fixtures (no machine path).
- FR-009-11 / FR-009-12: the spec's own contract examples of DC-009-04 (valid MakeHuman 1.3.0 record, valid mannequin
  record) and its hostile examples with the pointer each one is listed under in `contracts/examples/index.json`
  (reference validator `jsonschema` produced those pointers); the rule "wrong zip SHA-256 -> reject" is checked against a
  pinned value fixed in this file (the real pinned value is configuration, not in the repository yet: UNVERIFIED);
  the "no valid MakeHuman character remains -> mannequins" rule is hand-built (three invalid records -> mannequins).

Expected public API (module `pitstudio_studio.sdg.assets`, package under `studio/src/`):

    AssetLicenceError(Exception)    .code == "asset-licence"; .paths: tuple[str, ...], every offending path as it was
                                    given, in input order, no duplicates; str(error) contains the code and every path.
    check_scene_assets(asset_paths: Sequence[str], *, licence_records: Mapping[str, Mapping[str, object]],
                       vendor_roots: Sequence[str]) -> None
        An asset is offending if (a) its path (case-insensitive scheme) starts with "omniverse://", (b) after replacing
        "\\" by "/" and posixpath.normpath it equals a vendor root or lies below it (roots are normalised the same way),
        or (c) `licence_records` has no entry for the path as given, or the entry has no non-empty string "spdx".
        Raises AssetLicenceError listing all offending paths; returns None when every asset is clean. An empty string
        path is offending.
    Rejection                       frozen dataclass: character_id: str | None, pointer: str, reason: str
    PeopleSelection                 frozen dataclass: people_source: "makehuman" | "mannequins"; characters: tuple[dict, ...]
                                    (the valid records of the chosen source, input order); rejected: tuple[Rejection, ...];
                                    licence_text: str (non-empty; contains the SPDX id of the chosen source: "CC0-1.0" for
                                    makehuman, "CC-BY-4.0" for mannequins).
    select_people(records: Sequence[object], *, pinned_zip_sha256: str) -> PeopleSelection
        Each record with source "makehuman" is validated against people-asset-record.schema.json and its zip_sha256 must
        equal `pinned_zip_sha256` (Rejection.pointer "/zip_sha256", reason contains "pinned"); a schema violation is a
        Rejection whose pointer is the schema error's absolute path ("" for the root; for a missing required property the
        reason contains the property name). A record that is not a mapping, or whose `source` is neither "makehuman"
        nor "mannequin", is rejected (pointer "" or "/source"). Mannequin records are validated against the same schema.
        people_source is "makehuman" if at least one valid MakeHuman record remains, else "mannequins" (also for an empty
        input); with "mannequins" the characters are the valid mannequin records (possibly none: the generator runs).
        One Rejection per bad record: the first schema error if there is one, else the pinned-digest mismatch (so the
        digest check only applies to schema-valid records). Never raises for bad records.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
from pitstudio_studio.sdg import assets  # noqa: E402

VENDOR = ["vendor_assets/nvidia", "/opt/vendor-assets"]
RECORDS = {"site/props/cone.usd": {"spdx": "CC0-1.0"}, "site/props/sign.usd": {"spdx": "CC-BY-4.0"}}
INDEX = {e["file"]: e for e in json.loads((kit.EXAMPLES / "index.json").read_text(encoding="utf-8"))["examples"]}
PINNED = kit.example("people-asset-record.valid.json")["zip_sha256"]
OTHER_DIGEST = "f" * 64


def _check(paths: list[str], records: dict | None = None) -> None:
    assets.check_scene_assets(paths, licence_records=RECORDS if records is None else records, vendor_roots=VENDOR)


def _offending(paths: list[str], records: dict | None = None) -> tuple[str, ...]:
    with pytest.raises(assets.AssetLicenceError) as exc:
        _check(paths, records)
    assert exc.value.code == "asset-licence"
    assert "asset-licence" in str(exc.value)
    return exc.value.paths


# ---------------------------------------------------------------- FR-009-10


@pytest.mark.req("FR-009-10")
def test_assets_with_licence_records_outside_every_vendor_root_pass() -> None:
    assert _check(["site/props/cone.usd", "site/props/sign.usd"]) is None
    assert _check([]) is None


@pytest.mark.req("FR-009-10")
@pytest.mark.parametrize(
    "url",
    ["omniverse://localhost/NVIDIA/Assets/x.usd", "OMNIVERSE://server/p.usd", "Omniverse://x"],
)
def test_an_omniverse_url_is_refused_even_with_a_licence_record(url: str) -> None:
    assert _offending([url], {url: {"spdx": "CC0-1.0"}}) == (url,)


@pytest.mark.req("FR-009-10")
@pytest.mark.parametrize(
    "path",
    [
        "vendor_assets/nvidia/Props/crate.usd",
        "vendor_assets/nvidia",
        "vendor_assets\\nvidia\\Props\\crate.usd",
        "/opt/vendor-assets/a/b.usd",
        "site/../vendor_assets/nvidia/x.usd",
        "./vendor_assets/nvidia/x.usd",
        "vendor_assets//nvidia/x.usd",
    ],
)
def test_a_path_that_resolves_under_a_vendor_root_is_refused_even_with_a_licence_record(path: str) -> None:
    assert _offending([path], {path: {"spdx": "CC0-1.0"}}) == (path,)


@pytest.mark.req("FR-009-10")
@pytest.mark.parametrize(
    "path", ["vendor_assets/nvidia_copy/x.usd", "my_vendor_assets/nvidia/x.usd", "site/vendor_assets_x.usd"]
)
def test_a_sibling_prefix_of_a_vendor_root_is_not_under_it(path: str) -> None:
    assert _check([path], {path: {"spdx": "CC0-1.0"}}) is None


@pytest.mark.req("FR-009-10")
def test_a_path_without_a_licence_record_is_refused() -> None:
    assert _offending(["site/props/cone.usd", "site/props/unlicensed.usd"]) == ("site/props/unlicensed.usd",)


@pytest.mark.req("FR-009-10")
@pytest.mark.parametrize("record", [{}, {"spdx": ""}, {"spdx": None}, {"spdx": 7}, {"licence": "CC0-1.0"}])
def test_a_licence_record_without_a_usable_spdx_id_does_not_count(record: dict) -> None:
    assert _offending(["site/props/x.usd"], {"site/props/x.usd": record}) == ("site/props/x.usd",)


@pytest.mark.req("FR-009-10")
def test_every_offending_path_is_listed_in_input_order_once() -> None:
    paths = [
        "site/props/cone.usd",
        "omniverse://h/a.usd",
        "vendor_assets/nvidia/b.usd",
        "site/props/missing.usd",
        "omniverse://h/a.usd",
        "site/props/sign.usd",
    ]
    assert _offending(paths) == ("omniverse://h/a.usd", "vendor_assets/nvidia/b.usd", "site/props/missing.usd")


@pytest.mark.req("FR-009-10")
@pytest.mark.parametrize("path", ["", "资产/岩石.usd", "site/props/cone.usd\x00.png"])
def test_empty_and_hostile_path_strings_are_offending_not_crashes(path: str) -> None:
    assert _offending([path]) == (path,)


# ---------------------------------------------------------------- FR-009-11 / FR-009-12


def _mh(char_id: str = "mh-worker-007") -> dict:
    r = kit.example("people-asset-record.valid.json")
    r["character_id"] = char_id
    return r


def _select(records: list[object]) -> assets.PeopleSelection:
    return assets.select_people(records, pinned_zip_sha256=PINNED)


@pytest.mark.req("FR-009-11")
def test_valid_makehuman_records_are_used_and_the_card_fields_name_the_source_and_licence() -> None:
    sel = _select([_mh("mh-a"), _mh("mh-b")])
    assert sel.people_source == "makehuman"
    assert [c["character_id"] for c in sel.characters] == ["mh-a", "mh-b"]
    assert sel.rejected == ()
    assert "CC0-1.0" in sel.licence_text


@pytest.mark.req("FR-009-11")
def test_with_no_makehuman_record_the_mannequin_generator_is_the_source() -> None:
    sel = _select([kit.example("people-asset-record.valid-mannequin.json")])
    assert sel.people_source == "mannequins"
    assert [c["character_id"] for c in sel.characters] == ["mannequin-012"]
    assert "CC-BY-4.0" in sel.licence_text
    assert sel.rejected == ()


@pytest.mark.req("FR-009-11")
def test_a_valid_makehuman_record_wins_over_mannequin_records() -> None:
    sel = _select([kit.example("people-asset-record.valid-mannequin.json"), _mh("mh-a")])
    assert sel.people_source == "makehuman"
    assert [c["character_id"] for c in sel.characters] == ["mh-a"]


@pytest.mark.req("FR-009-12")
def test_a_zip_digest_different_from_the_pinned_value_is_rejected() -> None:
    bad = _mh("mh-bad")
    bad["zip_sha256"] = OTHER_DIGEST
    sel = _select([_mh("mh-ok"), bad])
    assert sel.people_source == "makehuman"
    assert [c["character_id"] for c in sel.characters] == ["mh-ok"]
    (rej,) = sel.rejected
    assert rej.character_id == "mh-bad"
    assert rej.pointer == "/zip_sha256"
    assert "pinned" in rej.reason


@pytest.mark.req("FR-009-12")
def test_a_community_asset_is_rejected_at_its_origin_pointer() -> None:
    sel = _select([kit.example("people-asset-record.hostile-community-asset.json")])
    (rej,) = sel.rejected
    assert rej.pointer == "/assets/1/origin"
    assert sel.characters == ()


@pytest.mark.req("FR-009-12")
def test_a_record_without_export_settings_is_rejected_naming_the_missing_property() -> None:
    sel = _select([kit.example("people-asset-record.hostile-missing-required.json")])
    (rej,) = sel.rejected
    assert rej.pointer == ""
    assert "export_settings" in rej.reason


@pytest.mark.req("FR-009-12")
def test_when_no_valid_makehuman_character_remains_mannequins_are_used() -> None:
    bad_hash = _mh("mh-1")
    bad_hash["zip_sha256"] = OTHER_DIGEST
    community = kit.example("people-asset-record.hostile-community-asset.json")
    no_settings = kit.example("people-asset-record.hostile-missing-required.json")
    sel = _select([bad_hash, community, no_settings])
    assert sel.people_source == "mannequins"
    assert sel.characters == ()
    assert len(sel.rejected) == 3
    assert "CC-BY-4.0" in sel.licence_text


@pytest.mark.req("FR-009-12")
def test_an_empty_hand_over_falls_back_to_mannequins() -> None:
    sel = _select([])
    assert sel.people_source == "mannequins"
    assert sel.characters == ()
    assert sel.rejected == ()


HOSTILE = [
    (f, e["pointer"]) for f, e in INDEX.items() if e["schema"] == "people-asset-record.schema.json" and not e["valid"]
]


@pytest.mark.req("FR-009-12")
@pytest.mark.parametrize(("name", "pointer"), HOSTILE, ids=[n for n, _ in HOSTILE])
def test_every_hostile_contract_example_is_rejected_at_the_pointer_of_its_error(name: str, pointer: str) -> None:
    sel = _select([kit.example(name)])
    assert sel.people_source == "mannequins"
    assert sel.characters == ()
    (rej,) = sel.rejected
    assert rej.pointer == pointer


@pytest.mark.req("FR-009-12")
@pytest.mark.parametrize("record", [None, 7, "mh-worker", [], {}, {"source": "someone-else"}, {"source": None}])
def test_records_that_are_not_people_records_are_rejected_without_crashing(record: object) -> None:
    sel = _select([record])
    assert sel.people_source == "mannequins"
    assert len(sel.rejected) == 1

# ruff: noqa: E501
"""T-009-095 - FR-009-49: the people-asset export digest is verified (`asset-digest-mismatch`).

Oracles (independent of the code under test; plan 009 test strategy row FR-009-49): the reference implementation `hashlib.sha256` of a fixture file written here; the same
file with ONE byte changed no longer matches the SHA-256 recorded in the people-asset record and the record is rejected with the class `asset-digest-mismatch` naming the record and the file
is not used. Records are the spec's valid DC-009-04 contract examples (MakeHuman and mannequin) with only `export_path` / `export_sha256` set to the fixture.

Expected public API (module `pitstudio_studio.sdg.assets`, see tests/unit/test_t_009_015_asset_people_guard.py):

    AssetDigestError(Exception)      .code == "asset-digest-mismatch"; .character_id: str (the record's character_id); .expected: str; .actual: str; str(error) contains the code and the character id
    verify_export_digest(record: Mapping, root: pathlib.Path) -> pathlib.Path
        Returns root / record["export_path"] when the SHA-256 of that file equals record["export_sha256"]; raises AssetDigestError otherwise (expected = the record's digest, actual = the file's).
        ValueError (message contains "export_path") for an export_path that is absolute, contains "..", a drive letter or a backslash, or is not a string; FileNotFoundError when the file is absent;
        ValueError (message contains "export_sha256") for a digest that is not 64 lower-case hex characters. The file is read in full (no size limit) and never executed or imported.
    select_people(records, *, pinned_zip_sha256, root: pathlib.Path | None = None) -> PeopleSelection      (extension of T-009-015)
        With `root` given, every record that passes the schema and the pinned-digest check also gets verify_export_digest; a mismatch is a Rejection with pointer "/export_sha256" and a reason that
        contains "asset-digest-mismatch" (the character is not used); a missing file is a Rejection with the same pointer and a reason containing "missing". Without `root` behaviour is unchanged.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
from pitstudio_studio.sdg import assets  # noqa: E402

PINNED = kit.example("people-asset-record.valid.json")["zip_sha256"]


def _record(
    root: Path, data: bytes, *, kind: str = "valid", rel: str | None = None, char_id: str | None = None
) -> dict:
    rec = kit.example(f"people-asset-record.{kind}.json")
    path = rel or rec["export_path"]
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_bytes(data)
    rec["export_path"] = path
    rec["export_sha256"] = hashlib.sha256(data).hexdigest()
    if char_id:
        rec["character_id"] = char_id
    return rec


@pytest.mark.req("FR-009-49")
@pytest.mark.parametrize("kind", ["valid", "valid-mannequin"])
def test_a_file_that_matches_its_recorded_digest_is_returned(tmp_path: Path, kind: str) -> None:
    data = kit.payload(2048, 1)
    rec = _record(tmp_path, data, kind=kind)
    assert assets.verify_export_digest(rec, tmp_path) == tmp_path / rec["export_path"]


@pytest.mark.req("FR-009-49")
def test_one_changed_byte_is_a_digest_mismatch_naming_the_record(tmp_path: Path) -> None:
    data = kit.payload(2048, 2)
    rec = _record(tmp_path, data)
    path = tmp_path / rec["export_path"]
    path.write_bytes(data[:100] + bytes([data[100] ^ 0x01]) + data[101:])
    with pytest.raises(assets.AssetDigestError) as exc:
        assets.verify_export_digest(rec, tmp_path)
    assert exc.value.code == "asset-digest-mismatch"
    assert exc.value.character_id == rec["character_id"]
    assert exc.value.expected == rec["export_sha256"]
    assert exc.value.actual == hashlib.sha256(path.read_bytes()).hexdigest()
    assert exc.value.actual != exc.value.expected
    assert "asset-digest-mismatch" in str(exc.value)
    assert rec["character_id"] in str(exc.value)


@pytest.mark.req("FR-009-49")
@pytest.mark.parametrize("change", ["append", "truncate", "empty", "swap"])
def test_every_kind_of_alteration_is_caught(tmp_path: Path, change: str) -> None:
    data = kit.payload(512, 3)
    rec = _record(tmp_path, data)
    path = tmp_path / rec["export_path"]
    path.write_bytes({"append": data + b"\0", "truncate": data[:-1], "empty": b"", "swap": kit.payload(512, 4)}[change])
    with pytest.raises(assets.AssetDigestError):
        assets.verify_export_digest(rec, tmp_path)


@pytest.mark.req("FR-009-49")
def test_the_digest_comparison_is_over_the_whole_file_including_large_ones(tmp_path: Path) -> None:
    data = kit.payload(3_000_000, 5)
    rec = _record(tmp_path, data)
    assert assets.verify_export_digest(rec, tmp_path).stat().st_size == 3_000_000


@pytest.mark.req("FR-009-49")
@pytest.mark.parametrize("bad", ["../x.fbx", "/abs/x.fbx", "C:/x.fbx", "a\\b.fbx", "a/../../b.fbx", "", None, 7, ["x"]])
def test_an_unsafe_or_malformed_export_path_is_refused(tmp_path: Path, bad: object) -> None:
    rec = _record(tmp_path, kit.payload(64, 6))
    rec["export_path"] = bad
    with pytest.raises(ValueError, match="export_path"):
        assets.verify_export_digest(rec, tmp_path)


@pytest.mark.req("FR-009-49")
@pytest.mark.parametrize("bad", ["", "ABC", "A" * 64, "g" * 64, "a" * 63, "a" * 65, None, 5])
def test_a_malformed_recorded_digest_is_refused(tmp_path: Path, bad: object) -> None:
    rec = _record(tmp_path, kit.payload(64, 7))
    rec["export_sha256"] = bad
    with pytest.raises(ValueError, match="export_sha256"):
        assets.verify_export_digest(rec, tmp_path)


@pytest.mark.req("FR-009-49")
def test_a_missing_export_file_is_a_file_error(tmp_path: Path) -> None:
    rec = _record(tmp_path, kit.payload(64, 8))
    (tmp_path / rec["export_path"]).unlink()
    with pytest.raises(FileNotFoundError):
        assets.verify_export_digest(rec, tmp_path)


@pytest.mark.req("FR-009-49")
def test_a_mismatching_record_is_rejected_from_the_selection_and_never_used(tmp_path: Path) -> None:
    good = _record(tmp_path, kit.payload(256, 9), rel="people/makehuman/mh-a/mh-a.fbx", char_id="mh-a")
    bad = _record(tmp_path, kit.payload(256, 10), rel="people/makehuman/mh-b/mh-b.fbx", char_id="mh-b")
    (tmp_path / bad["export_path"]).write_bytes(kit.payload(256, 11))  # altered after the record was written
    sel = assets.select_people([good, bad], pinned_zip_sha256=PINNED, root=tmp_path)
    assert sel.people_source == "makehuman"
    assert [c["character_id"] for c in sel.characters] == ["mh-a"]
    (rej,) = sel.rejected
    assert rej.character_id == "mh-b"
    assert rej.pointer == "/export_sha256"
    assert "asset-digest-mismatch" in rej.reason


@pytest.mark.req("FR-009-49")
def test_when_every_makehuman_export_fails_the_digest_the_mannequins_take_over(tmp_path: Path) -> None:
    bad = _record(tmp_path, kit.payload(128, 12), char_id="mh-x")
    (tmp_path / bad["export_path"]).write_bytes(b"tampered")
    sel = assets.select_people([bad], pinned_zip_sha256=PINNED, root=tmp_path)
    assert sel.people_source == "mannequins"
    assert sel.characters == ()
    assert len(sel.rejected) == 1


@pytest.mark.req("FR-009-49")
def test_a_missing_file_is_a_rejection_in_the_selection_and_the_mannequin_record_is_verified_too(
    tmp_path: Path,
) -> None:
    gone = _record(tmp_path, kit.payload(64, 13), rel="people/makehuman/mh-g/mh-g.fbx", char_id="mh-g")
    (tmp_path / gone["export_path"]).unlink()
    sel = assets.select_people([gone], pinned_zip_sha256=PINNED, root=tmp_path)
    (rej,) = sel.rejected
    assert rej.pointer == "/export_sha256"
    assert "missing" in rej.reason
    mannequin = _record(tmp_path, kit.payload(64, 14), kind="valid-mannequin")
    (tmp_path / mannequin["export_path"]).write_bytes(b"other")
    sel2 = assets.select_people([mannequin], pinned_zip_sha256=PINNED, root=tmp_path)
    assert sel2.characters == ()
    assert "asset-digest-mismatch" in sel2.rejected[0].reason


@pytest.mark.req("FR-009-49")
def test_without_a_root_the_selection_is_unchanged(tmp_path: Path) -> None:
    rec = kit.example("people-asset-record.valid.json")
    sel = assets.select_people([rec], pinned_zip_sha256=PINNED)
    assert sel.people_source == "makehuman"
    assert sel.rejected == ()

"""T-001-024 · the registry fields ``s00_download`` (spec 008) reads: FR-001-52.

Oracles: data-model 5.1 / 5.1.1 (access modes, ordered fallback sources, file kinds, publisher checksums, archive
``extract`` globs with the ``relglob`` pattern, the 64 GiB cap), transcribed by hand; corpus fixtures with fixed
pointers; python ``jsonschema`` as the reference validator for schema-level classes; hand-built registries on the clean
fixture repository for the two cross-entry classes (fallback ids, mixed share-alike SPDX ids).

Expected API: ``contracts/sources.schema.json`` and ``tools/check_contracts.py`` (finding pointers
``/sources/<i>/fallback/sources/<j>`` for a fallback id that is not another registry id or names the entry itself, and
``/sources/<i>`` or ``/sources/<i>/files`` for files whose SPDX ids mix a share-alike id with any other id; each
message names the entry id and is at most 300 characters).
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_support as cs

SOURCES_YAML = "data/sources.yaml"
VALID = json.loads((cs.FIXTURES / "sources/valid/sources.valid.json").read_text(encoding="utf-8"))
LIDAR = VALID["sources"][0]  # public-domain, two files (point-cloud, archive with extract)
STATION = VALID["sources"][1]
REANALYSIS = VALID["sources"][2]  # access account, needs env var, fallback
GIB64 = 64 * 2**30
FILE_KINDS = ["raster", "point-cloud", "vector", "image-set", "table", "document", "archive"]


def pairs(doc: Any) -> set[tuple[str, str]]:
    return cs.error_pairs("sources", "#", doc)


def ok(doc: Any) -> bool:
    return cs.accepts("sources", "#", doc)


def archive_doc(**file_changes: Any) -> dict:
    e = copy.deepcopy(LIDAR)
    e["files"][1].update(file_changes)
    return {"sources": [e]}


def plain_doc(kind: str, **file_changes: Any) -> dict:
    e = copy.deepcopy(STATION)
    e["files"][0]["kind"] = kind
    e["files"][0].update(file_changes)
    return {"sources": [e]}


def account_doc(access: str, needed: bool, *, env_var: bool = True, fallback: bool = True) -> dict:
    e = copy.deepcopy(REANALYSIS)
    e["access"] = access
    e["account"] = {"needed": needed}
    if env_var:
        e["account"]["env_var"] = "EXAMPLE_REANALYSIS_KEY"
    if not fallback:
        del e["fallback"]
    return {"sources": [e]}


def assert_corpus(minimum: int) -> None:
    items = [e for e in cs.schema_level(schema="sources") if e["rule"] == "FR-001-52" and not e["valid"]]
    assert len(items) >= minimum, len(items)
    for e in items:
        assert (e["pointer"], e["keyword"]) in pairs(cs.fixture_json(e)), (e["file"], e["pointer"], e["keyword"])


@pytest.mark.req("FR-001-52")
def test_fr_001_52_corpus_fixtures_of_the_class() -> None:
    assert_corpus(9)


# ----------------------------------------------------------------------------------------------------------------
# access modes
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-52")
@pytest.mark.parametrize("access", ["direct", "api", "manual", "account"])
@pytest.mark.parametrize("needed", [True, False])
def test_fr_001_52_account_access_and_account_needed_hold_together(access: str, needed: bool) -> None:
    doc = account_doc(access, needed)
    expected = (access == "account") == needed
    assert ok(doc) is expected, (access, needed, sorted(pairs(doc))[:3])
    if not expected:
        assert any(p.startswith("/sources/0") for p, _ in pairs(doc))


@pytest.mark.req("FR-001-52")
@pytest.mark.parametrize("access", ["ftp", "Direct", "API", "account ", "", "none", None, 1, ["direct"]])
def test_fr_001_52_unknown_access_values(access: Any) -> None:
    doc = {"sources": [{**copy.deepcopy(STATION), "access": access}]}
    assert any(p == "/sources/0/access" for p, _ in pairs(doc))


@pytest.mark.req("FR-001-52")
def test_fr_001_52_account_needed_requires_the_variable_name_and_the_fallback() -> None:
    assert ok(account_doc("account", True))
    assert ("/sources/0/account", "required") in pairs(account_doc("account", True, env_var=False))
    assert ("/sources/0", "required") in pairs(account_doc("account", True, fallback=False))


@pytest.mark.req("FR-001-52")
def test_fr_001_52_manual_access_means_the_maintainer_places_the_files() -> None:
    assert ok({"sources": [{**copy.deepcopy(STATION), "access": "manual", "files": []}]})


# ----------------------------------------------------------------------------------------------------------------
# file kinds, publisher checksums, extract patterns, uncompressed size
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-52")
@pytest.mark.parametrize("kind", FILE_KINDS)
def test_fr_001_52_every_file_kind_of_the_enum_is_accepted(kind: str) -> None:
    changes: dict[str, Any] = {}
    if kind == "archive":
        changes = {"uncompressed_bytes": 10, "extract": ["a/*.csv"]}
    assert ok(plain_doc(kind, **changes)), kind


@pytest.mark.req("FR-001-52")
@pytest.mark.parametrize("kind", ["", "Raster", "pointcloud", "zip", "dem", None, 1, ["raster"]])
def test_fr_001_52_a_file_needs_a_known_kind(kind: Any) -> None:
    assert any(p == "/sources/0/files/0/kind" for p, _ in pairs(plain_doc(kind)))
    e = copy.deepcopy(STATION)
    del e["files"][0]["kind"]
    assert ("/sources/0/files/0", "required") in pairs({"sources": [e]})


@pytest.mark.req("FR-001-52")
@pytest.mark.parametrize(
    ("checksum", "expected"),
    [
        ("md5:" + "0123456789abcdef" * 2, True),
        ("sha256:" + "a" * 64, True),
        ("md5:" + "a" * 31, False),
        ("md5:" + "a" * 33, False),
        ("sha256:" + "a" * 63, False),
        ("sha256:" + "a" * 65, False),
        ("md5:" + "A" * 32, False),
        ("sha256:" + "A" * 64, False),
        ("sha1:" + "a" * 40, False),
        ("a" * 32, False),
        ("a" * 64, False),
        ("md5 " + "a" * 32, False),
        ("md5:" + "g" * 32, False),
        ("MD5:" + "a" * 32, False),
        ("", False),
        ("md5:", False),
        (5, False),
        (None, False),
    ],
    ids=lambda v: str(v)[:24],
)
def test_fr_001_52_publisher_checksum_is_md5_or_sha256_lowercase_hex(checksum: Any, expected: bool) -> None:
    assert ok(plain_doc("table", publisher_checksum=checksum)) is expected


@pytest.mark.req("FR-001-52")
def test_fr_001_52_the_publisher_checksum_never_replaces_the_sha256_and_is_optional() -> None:
    e = copy.deepcopy(STATION)
    assert "publisher_checksum" not in e["files"][0]
    assert ok({"sources": [e]})
    e["files"][0]["publisher_checksum"] = "md5:" + "a" * 32
    del e["files"][0]["sha256"]
    assert ("/sources/0/files/0", "required") in pairs({"sources": [e]})


@pytest.mark.req("FR-001-52")
@pytest.mark.parametrize("kind", [k for k in FILE_KINDS if k != "archive"])
def test_fr_001_52_extract_and_uncompressed_bytes_belong_to_archives_only(kind: str) -> None:
    assert not ok(plain_doc(kind, extract=["a/*.csv"]))
    assert not ok(plain_doc(kind, uncompressed_bytes=10))
    assert not ok(plain_doc(kind, extract=["a/*.csv"], uncompressed_bytes=10))


@pytest.mark.req("FR-001-52")
def test_fr_001_52_archive_files_may_carry_the_extraction_cap_and_the_member_list() -> None:
    assert ok(archive_doc())
    assert ok(plain_doc("archive"))  # both optional
    for good in (1, 2, GIB64, 2147483648):
        assert ok(archive_doc(uncompressed_bytes=good)), good
    for bad in (0, -1, GIB64 + 1, 2**53, 1.5, "1", True, None):
        assert any(
            p == "/sources/0/files/1/uncompressed_bytes" for p, _ in pairs(archive_doc(uncompressed_bytes=bad))
        ), bad


@pytest.mark.req("FR-001-52")
@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("tiles/*.laz", True),
        ("metadata/tile-??.xml", True),
        ("*", True),
        ("**", True),
        ("a/b/c/d.csv", True),
        ("Research Data/Annotated data/*.png", True),  # spaces inside a segment (the Mendeley archive)
        ("a b/c d.txt", True),
        ("data_2024/File-1.2.csv", True),
        ("?", True),
        ("/".join(["a"] * 16), True),
        ("a" * 99, True),
        ("/abs/x", False),
        ("C:/x", False),
        ("c:\\x", False),
        ("a\\b", False),
        ("a/../b", False),
        ("../a", False),
        ("..", False),
        (".", False),
        ("./a", False),
        ("a/./b", False),
        (" a/b", False),  # a segment with a leading space
        ("a /b", False),  # trailing space
        ("a/ b", False),
        ("a/b ", False),
        ("a//b", False),
        ("a/", False),
        ("", False),
        (".hidden", False),
        ("a.", False),
        ("a/b.", False),
        ("-a", False),
        ("/".join(["a"] * 17), False),
        ("a" * 256, False),
        ("a" * 101 + "/b", False),
        ("a\tb", False),
        ("\u00e9/a", False),
        ("a;b", False),
        ("a$b", False),
        ("a|b", False),
        ("~/a", False),
        ("a:b", False),
        ("file:///x", False),
    ],
    ids=lambda v: str(v)[:30],
)
def test_fr_001_52_extract_patterns_are_relative_globs(pattern: str, expected: bool) -> None:
    assert ok(archive_doc(extract=[pattern])) is expected, pattern


@pytest.mark.req("FR-001-52")
def test_fr_001_52_extract_list_bounds() -> None:
    assert ok(archive_doc(extract=["a"]))
    assert ok(archive_doc(extract=[f"d{i}/*.csv" for i in range(64)]))
    assert ("/sources/0/files/1/extract", "maxItems") in pairs(archive_doc(extract=[f"d{i}/*.csv" for i in range(65)]))
    assert ("/sources/0/files/1/extract", "minItems") in pairs(archive_doc(extract=[]))
    assert not ok(archive_doc(extract="tiles/*.laz"))
    assert not ok(archive_doc(extract=[1]))


# ----------------------------------------------------------------------------------------------------------------
# ordered fallback sources
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-52")
@pytest.mark.parametrize(
    ("ids", "expected"),
    [
        ([], True),
        (["a"], True),
        (["a", "b"], True),
        ([f"s{i}" for i in range(8)], True),
        ([f"s{i}" for i in range(9)], False),
        (["a", "a"], False),
        (["a", "b", "a"], False),
        (["A"], False),
        (["a/b"], False),
        (["../a"], False),
        ([""], False),
        ("a", False),
        ([1], False),
        ([None], False),
    ],
    ids=lambda v: str(v)[:30],
)
def test_fr_001_52_fallback_chain_shape(ids: Any, expected: bool) -> None:
    e = copy.deepcopy(REANALYSIS)
    e["fallback"]["sources"] = ids
    assert ok({"sources": [e]}) is expected


def registry_with_account_source(tmp: Path, fallback_ids: list[str], new_id: str = "example-reanalysis") -> Path:
    root = cs.clean_repo(tmp)

    def edit(d: dict) -> None:
        e = copy.deepcopy(REANALYSIS)
        e["id"], e["card"] = new_id, f"data/cards/{new_id}.md"
        e["fallback"]["sources"] = fallback_ids
        d["sources"].append(e)

    cs.edit_yaml(root, SOURCES_YAML, edit)
    return root


@pytest.mark.req("FR-001-52")
@pytest.mark.parametrize(
    ("fallback", "bad_index"),
    [
        (["example-station-hourly"], None),
        (["example-station-hourly", "example-haul-network"], None),
        ([], None),
        (["no-such-source"], 0),
        (["example-station-hourly", "no-such-source"], 1),
        (["example-reanalysis"], 0),  # names the entry itself
        (["example-station-hourly", "example-reanalysis"], 1),
    ],
)
def test_fr_001_52_fallback_ids_must_be_other_registry_ids(
    tmp_path: Path, fallback: list[str], bad_index: int | None
) -> None:
    res = cs.run_checker(registry_with_account_source(tmp_path, fallback))
    found = res.in_file(SOURCES_YAML, "/sources/3/fallback")
    if bad_index is None:
        assert found == [], res.findings
    else:
        assert any(f["pointer"].startswith(f"/sources/3/fallback/sources/{bad_index}") for f in found), res.findings
        assert all("example-reanalysis" in f["message"] and len(f["message"]) <= 300 for f in found)


# ----------------------------------------------------------------------------------------------------------------
# files whose SPDX ids mix a share-alike id with any other id
# ----------------------------------------------------------------------------------------------------------------
def registry_with_files(tmp: Path, entry_spdx: str, entry_class: str, file_spdx: list[str | None]) -> Path:
    root = cs.clean_repo(tmp)

    def edit(d: dict) -> None:
        e = d["sources"][1]  # example-station-hourly
        e["spdx"], e["licence_class"], e["attribution"] = entry_spdx, entry_class, "Example attribution."
        files = []
        for i, s in enumerate(file_spdx):
            f = copy.deepcopy(e["files"][0])
            f["url"] = f"https://example.org/data/part-{i}.csv"
            if s is not None:
                f["spdx"] = s
            files.append(f)
        e["files"] = files

    cs.edit_yaml(root, SOURCES_YAML, edit)
    return root


@pytest.mark.req("FR-001-52")
@pytest.mark.parametrize(
    ("entry_spdx", "entry_class", "file_spdx", "fails"),
    [
        ("CC-BY-SA-4.0", "share-alike", [None, None], False),  # every file inherits the one share-alike id
        ("CC-BY-SA-4.0", "share-alike", ["CC-BY-SA-4.0", "CC-BY-SA-4.0"], False),
        ("CC-BY-SA-4.0", "share-alike", ["CC-BY-SA-4.0", None], False),
        ("CC-BY-SA-4.0", "share-alike", ["CC0-1.0", None], True),  # share-alike mixed with another id
        ("CC-BY-SA-4.0", "share-alike", [None, "CC-BY-4.0"], True),
        ("CC-BY-SA-4.0", "share-alike", ["CC-BY-SA-3.0", "CC-BY-SA-4.0"], True),  # two different share-alike ids
        ("CC-BY-4.0", "attribution", ["CC-BY-SA-4.0", None], True),  # the entry's own id applies to the other file
        ("CC-BY-4.0", "attribution", ["CC0-1.0", "MIT"], False),  # no share-alike id anywhere
        ("CC-BY-4.0", "attribution", [None, "CC0-1.0"], False),
        ("CC0-1.0", "open-no-attribution", [None], False),
    ],
)
def test_fr_001_52_a_share_alike_spdx_id_may_not_be_mixed_with_any_other_id(
    tmp_path: Path, entry_spdx: str, entry_class: str, file_spdx: list[str | None], fails: bool
) -> None:
    res = cs.run_checker(registry_with_files(tmp_path, entry_spdx, entry_class, file_spdx))
    found = [f for f in res.in_file(SOURCES_YAML, "/sources/1") if f["rule"] == "FR-001-52"]
    assert bool(found) is fails, (entry_spdx, file_spdx, res.findings)
    for f in found:
        assert "example-station-hourly" in f["message"]
        assert len(f["message"]) <= 300


@pytest.mark.req("FR-001-52")
def test_fr_001_52_clean_registry_has_no_finding_of_the_class(tmp_path: Path) -> None:
    res = cs.run_checker(cs.clean_repo(tmp_path))
    assert res.of("FR-001-52") == []

"""T-001-022 · the source-registry schema and the committed ``data/sources.yaml``: FR-001-31, FR-001-32.

Oracles: the entry and file tables of data-model 5.1, the SPDX allowlist and the (SPDX, kind) -> licence-class table of
5.2 (transcribed in ``contract_support.SOURCE_ALLOWED``), the 64 GiB bound (2**36 B = 68,719,476,736), the credential
parameter names of FR-001-32, and the secret patterns of ``tools/check_repo.py`` (the reference scanner of this
repository); corpus fixtures with fixed pointers; python ``jsonschema`` as reference validator.

Secret-looking strings are assembled at run time so ``tools/check_repo.py`` does not flag this file.

Expected API: ``contracts/sources.schema.json``; the committed ``data/sources.yaml`` (empty ``sources`` list plus a
commented example entry using ``spdx`` / ``licence_url`` / ``licence_class``); ``tools/check_contracts.py`` (findings
with pointer ``/sources/<i>...`` naming the entry id for credential-like URL parameters, secret-pattern values and
duplicate ids).
"""

from __future__ import annotations

import copy
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_support as cs

SOURCES_YAML = "data/sources.yaml"
VALID = json.loads((cs.FIXTURES / "sources/valid/sources.valid.json").read_text(encoding="utf-8"))
ENTRY = VALID["sources"][1]  # example-station-hourly: real, api, CC-BY-4.0, attribution
GIB64 = 64 * 2**30  # 68,719,476,736


def pairs(doc: Any) -> set[tuple[str, str]]:
    return cs.error_pairs("sources", "#", doc)


def ok(doc: Any) -> bool:
    return cs.accepts("sources", "#", doc)


def one(**changes: Any) -> dict:
    e = {**copy.deepcopy(ENTRY), **changes}
    return {"sources": [e]}


def file_with(**changes: Any) -> dict:
    e = copy.deepcopy(ENTRY)
    e["files"][0].update(changes)
    return {"sources": [e]}


def minus(*names: str) -> dict:
    e = copy.deepcopy(ENTRY)
    for n in names:
        del e[n]
    return {"sources": [e]}


def assert_corpus(rule: str, minimum: int) -> None:
    items = [e for e in cs.schema_level(schema="sources") if e["rule"] == rule and not e["valid"]]
    assert len(items) >= minimum, (rule, len(items))
    for e in items:
        assert (e["pointer"], e["keyword"]) in pairs(cs.fixture_json(e)), (e["file"], e["pointer"], e["keyword"])


# ----------------------------------------------------------------------------------------------------------------
# FR-001-31 · the entry fields
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-31")
def test_fr_001_31_valid_registries_including_the_empty_list() -> None:
    assert ok(VALID)
    assert ok({"sources": []})
    assert ok({"$schema": "../contracts/sources.schema.json", "sources": []})
    assert ("", "required") in pairs({})
    assert ("", "additionalProperties") in pairs({"sources": [], "extra": 1})
    assert ("/sources", "type") in pairs({"sources": {}})


@pytest.mark.req("FR-001-31")
def test_fr_001_31_registry_holds_at_most_256_entries() -> None:
    entries = []
    for i in range(257):
        e = copy.deepcopy(ENTRY)
        e["id"], e["card"] = f"src-{i:03d}", f"data/cards/src-{i:03d}.md"
        entries.append(e)
    assert ok({"sources": entries[:256]})
    assert ("/sources", "maxItems") in pairs({"sources": entries})


ENTRY_REQUIRED = [
    "id",
    "kind",
    "title",
    "landing_url",
    "access",
    "files",
    "spdx",
    "licence_url",
    "licence_class",
    "redistribution",
    "citation",
    "card",
    "account",
]


@pytest.mark.req("FR-001-31")
@pytest.mark.parametrize("field", ENTRY_REQUIRED)
def test_fr_001_31_every_entry_field_of_data_model_5_1_is_required(field: str) -> None:
    got = pairs(minus(field))
    assert ("/sources/0", "required") in got


@pytest.mark.req("FR-001-31")
@pytest.mark.parametrize(
    "old",
    [
        "license",
        "license_url",
        "account_env",
        "file",
        "fallback_source",
        "redistributable",
        "url",
        "sha256",
        "bytes",
        "format",
    ],
)
def test_fr_001_31_retired_and_unknown_entry_field_names_are_rejected(old: str) -> None:
    assert ("/sources/0", "additionalProperties") in pairs(one(**{old: "x"}))


ENTRY_BOUNDS: list[tuple[str, list[Any], list[Any]]] = [
    (
        "id",
        ["a", "example-dataset", "0a", "a" * 64],
        ["", "A", "a" * 65, "a_b", "a.b", "a/b", "../a", "-a", "a b", None, 1],
    ),
    ("kind", ["real", "synthetic"], ["Real", "simulated", "", None]),
    ("title", ["t", "t" * 300], ["", "t" * 301, 1, None]),
    ("access", ["direct", "api", "manual"], ["ftp", "Direct", "", None]),  # "account" has its own rules (T-001-024)
    ("redistribution", ["redistributable", "derived-only", "no-redistribution"], ["open", "Redistributable", "", None]),
    ("citation", ["c", "c" * 1000], ["", "c" * 1001, 1]),
    ("attribution", ["a", "a" * 1000], ["", "a" * 1001, 1]),
    (
        "card",
        ["data/cards/a.md", "data/cards/" + "a" * 64 + ".md", "data/cards/a-1.md"],
        [
            "data/cards/../x.md",
            "/data/cards/a.md",
            "data/cards/A.md",
            "data/cards/a_b.md",
            "data/cards/a.txt",
            "data/cards/" + "a" * 65 + ".md",
            "cards/a.md",
            "data/cards/sub/a.md",
            "data\\cards\\a.md",
            "data/cards/.md",
            "",
        ],
    ),
    ("optional", [True, False], ["yes", 1, None]),
    (
        "files",
        [[], [copy.deepcopy(ENTRY["files"][0])] * 512],
        [[copy.deepcopy(ENTRY["files"][0])] * 513, {}, "x", None],
    ),
]


@pytest.mark.req("FR-001-31")
@pytest.mark.parametrize(("field", "good", "bad"), ENTRY_BOUNDS, ids=[b[0] for b in ENTRY_BOUNDS])
def test_fr_001_31_entry_field_bounds(field: str, good: list[Any], bad: list[Any]) -> None:
    for v in good:
        changes: dict[str, Any] = {field: v}
        if field == "kind" and v == "synthetic":
            changes["licence_class"] = "own"  # (CC-BY-4.0, synthetic) allows own only
        if field == "id":
            changes["card"] = f"data/cards/{v}.md" if len(str(v)) <= 64 else ENTRY["card"]
        assert pairs(one(**changes)) == set(), (field, v, sorted(pairs(one(**changes)))[:3])
    for v in bad:
        got = pairs(one(**{field: v}))
        assert any(p.startswith(f"/sources/0/{field}") or p == "/sources/0" for p, _ in got), (field, v)


@pytest.mark.req("FR-001-31")
def test_fr_001_31_account_record_and_env_var_names() -> None:
    assert ok(one(account={"needed": False}))
    assert ok(one(account={"needed": False, "note": "n" * 300}))
    assert not ok(one(account={"needed": False, "note": "n" * 301}))
    assert not ok(one(account={}))
    assert not ok(one(account={"needed": "no"}))
    assert not ok(one(account={"needed": False, "token": "x"}))
    assert not ok(one(account=None))
    reanalysis = copy.deepcopy(VALID["sources"][2])
    for good in ("EXAMPLE_KEY", "ABC", "A" * 64, "A1_B2"):
        e = copy.deepcopy(reanalysis)
        e["account"]["env_var"] = good
        assert ok({"sources": [e]}), good
    for bad in (
        "ab",
        "example_key",
        "1ABC",
        "A" * 65,
        "EXAMPLE KEY",
        "key",
        "",
        "A-B",
        "sk-ant-api03-xyz",
        "$EXAMPLE_KEY",
    ):
        e = copy.deepcopy(reanalysis)
        e["account"]["env_var"] = bad
        assert any(p == "/sources/0/account/env_var" for p, _ in pairs({"sources": [e]})), bad


@pytest.mark.req("FR-001-31")
def test_fr_001_31_file_record_required_fields_and_digest_and_size_bounds() -> None:
    for f in ("url", "sha256", "bytes", "kind"):
        e = copy.deepcopy(ENTRY)
        del e["files"][0][f]
        assert ("/sources/0/files/0", "required") in pairs({"sources": [e]}), f
    assert ok(file_with(sha256=None, bytes=None))
    for good in ("a" * 64, "0" * 64):
        assert ok(file_with(sha256=good))
    for bad in ("A" * 64, "a" * 63, "a" * 65, "sha256:" + "a" * 64, "", "g" * 64, 5):
        assert any(p == "/sources/0/files/0/sha256" for p, _ in pairs(file_with(sha256=bad))), bad
    for good in (1, 2, GIB64, 734003200):
        assert ok(file_with(bytes=good)), good
    for bad in (0, -1, GIB64 + 1, 2**53, 1.5, "1", True):
        assert any(p == "/sources/0/files/0/bytes" for p, _ in pairs(file_with(bytes=bad))), bad
    for good in ("raster", "point-cloud", "vector", "image-set", "table", "document", "archive"):
        e = copy.deepcopy(ENTRY)
        e["files"][0]["kind"] = good
        assert ok({"sources": [e]}), good
    assert ok(file_with(name="lidar-tiles.zip", spdx="CC0-1.0"))
    assert not ok(file_with(name="../x"))
    assert not ok(file_with(spdx="GPL-3.0-only"))
    assert ("/sources/0/files/0", "additionalProperties") in pairs(file_with(local_path="x"))


@pytest.mark.req("FR-001-31")
def test_fr_001_31_fallback_record() -> None:
    reanalysis = copy.deepcopy(VALID["sources"][2])
    for good in ([], ["a"], [f"s{i}" for i in range(8)]):
        e = copy.deepcopy(reanalysis)
        e["fallback"]["sources"] = good
        assert ok({"sources": [e]}), good
    for bad in ([f"s{i}" for i in range(9)], ["A"], ["a/b"], "a", [1]):
        e = copy.deepcopy(reanalysis)
        e["fallback"]["sources"] = bad
        assert not ok({"sources": [e]}), bad
    for bad_text in ("", "t" * 301):
        e = copy.deepcopy(reanalysis)
        e["fallback"]["text"] = bad_text
        assert not ok({"sources": [e]})


@pytest.mark.req("FR-001-31")
def test_fr_001_31_corpus_fixtures() -> None:
    assert_corpus("FR-001-31", 6)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-31 · the committed registry
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-31")
def test_fr_001_31_committed_registry_is_an_empty_valid_list_loaded_strictly() -> None:
    from pitstudio.contracts import load_yaml

    text = (cs.ROOT / SOURCES_YAML).read_text(encoding="utf-8")
    doc = yaml.safe_load(text)  # PyYAML as the reference parser
    assert doc == {"sources": []}
    assert ok(doc)
    assert load_yaml(cs.ROOT / SOURCES_YAML) == doc


@pytest.mark.req("FR-001-31")
def test_fr_001_31_the_example_comment_uses_the_schema_field_names() -> None:
    text = (cs.ROOT / SOURCES_YAML).read_text(encoding="utf-8")
    assert "\u00e2\u20ac" not in text, "the comment block must be clean UTF-8 (no mojibake from a wrong code page)"
    for stale in ("license:", "license_url", "account_env", "fallback.source:"):
        assert stale not in text, stale
    for name in ("spdx:", "licence_url:", "licence_class:"):
        assert name in text, name
    block = text.split("Example entry:", 1)[1]
    lines = [ln[2:] if ln.startswith("# ") else ln[1:] for ln in block.splitlines() if ln.startswith("#")]
    example = yaml.safe_load("\n".join(lines))
    assert isinstance(example, list)
    assert len(example) == 1
    schema = cs.load_schema("sources")
    entry_props = set(schema["$defs"]["entry"]["properties"])
    file_props = set(schema["$defs"]["file"]["properties"])
    assert set(example[0]) <= entry_props, set(example[0]) - entry_props
    assert {
        "id",
        "kind",
        "title",
        "landing_url",
        "files",
        "spdx",
        "licence_url",
        "licence_class",
        "redistribution",
        "citation",
        "card",
    } <= set(example[0])
    assert all(set(f) <= file_props for f in example[0]["files"])


# ----------------------------------------------------------------------------------------------------------------
# FR-001-32 · hostile entries
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-32")
@pytest.mark.parametrize(
    ("spdx", "kind", "cls"),
    list(itertools.product(cs.SPDX_ALLOWLIST, ["real", "synthetic"], cs.LICENCE_ORDER)),
    ids=lambda v: str(v),
)
def test_fr_001_32_licence_class_must_be_allowed_for_the_spdx_id_and_kind(spdx: str, kind: str, cls: str) -> None:
    doc = one(spdx=spdx, kind=kind, licence_class=cls, attribution="Example attribution.")
    expected = cls in cs.SOURCE_ALLOWED.get((spdx, kind), set())
    assert ok(doc) is expected, (spdx, kind, cls, sorted(pairs(doc))[:3])


@pytest.mark.req("FR-001-32")
@pytest.mark.parametrize(
    "spdx",
    ["GPL-3.0-only", "cc-by-4.0", "CC-BY-4.0 ", "CC BY 4.0", "LicenseRef-Foo", "", None, "Apache", "NOASSERTION"],
)
def test_fr_001_32_spdx_outside_the_allowlist_is_rejected(spdx: Any) -> None:
    assert any(p == "/sources/0/spdx" for p, _ in pairs(one(spdx=spdx)))


@pytest.mark.req("FR-001-32")
@pytest.mark.parametrize(
    ("cls", "spdx"),
    [
        ("public-domain", "LicenseRef-USGov-PD"),
        ("open-no-attribution", "CC0-1.0"),
        ("attribution", "CC-BY-4.0"),
        ("share-alike", "CC-BY-SA-4.0"),
    ],
)
def test_fr_001_32_attribution_is_required_for_attribution_and_share_alike_classes(cls: str, spdx: str) -> None:
    base = one(spdx=spdx, licence_class=cls)
    without = copy.deepcopy(base)
    without["sources"][0].pop("attribution", None)
    needs = cls in ("attribution", "share-alike")
    assert ok(without) is (not needs), cls
    base["sources"][0]["attribution"] = "Example attribution."
    assert ok(base)
    base["sources"][0]["attribution"] = ""
    assert not ok(base)


@pytest.mark.req("FR-001-32")
@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.org/x", True),
        ("https://example.org:8443/x?a=1&b=2", True),
        ("https://doi.org/10.1234/abc.def", True),
        ("https://sub.example.org/a/b/c.zip", True),
        ("https://example.org", True),
        ("http://example.org/x", False),
        ("ftp://example.org/x", False),
        ("file:///etc/passwd", False),
        ("javascript:alert(1)", False),
        ("//example.org/x", False),
        ("https://user@example.org/x", False),
        ("https://user:secret@example.org/x", False),
        ("https://:secret@example.org/x", False),
        ("https:///x", False),
        ("https://exa mple.org/x", False),
        ("https://example.org/x y", False),
        ("https://example.org/é", False),
        ("https://example.org/#frag", False),
        ("https://example.org/" + "a" * 2048, False),
        ("", False),
        ("example.org/x", False),
        (None, False),
        (7, False),
    ],
    ids=lambda v: str(v)[:50],
)
def test_fr_001_32_urls_are_https_without_user_information(url: Any, expected: bool) -> None:
    assert ok(one(landing_url=url)) is expected
    assert ok(file_with(url=url)) is expected
    assert ok(one(licence_url=url)) is expected


@pytest.mark.req("FR-001-32")
def test_fr_001_32_account_that_is_needed_requires_the_variable_name_and_a_fallback() -> None:
    reanalysis = VALID["sources"][2]
    assert ok({"sources": [reanalysis]})
    for missing in ("env_var",):
        e = copy.deepcopy(reanalysis)
        del e["account"][missing]
        assert ("/sources/0/account", "required") in pairs({"sources": [e]})
    e = copy.deepcopy(reanalysis)
    del e["fallback"]
    assert ("/sources/0", "required") in pairs({"sources": [e]})
    e = copy.deepcopy(reanalysis)
    e["account"]["env_var"] = "ghp" + "_" + "A" * 36  # a credential value instead of a variable name
    assert any(p == "/sources/0/account/env_var" for p, _ in pairs({"sources": [e]}))


@pytest.mark.req("FR-001-32")
def test_fr_001_32_corpus_fixtures() -> None:
    assert_corpus("FR-001-32", 8)


def repo_with_sources(tmp: Path, fn: Any) -> Path:
    root = cs.clean_repo(tmp)
    cs.edit_yaml(root, SOURCES_YAML, fn)
    return root


@pytest.mark.req("FR-001-32")
@pytest.mark.parametrize(
    ("query", "flagged"),
    [
        ("key=abc", True),
        ("token=abc", True),
        ("apikey=abc", True),
        ("api_key=abc", True),
        ("access_token=abc", True),
        ("signature=abc", True),
        ("id=1&token=abc", True),
        ("format=csv&api_key=abc&x=1", True),
        ("a=1&signature=", True),
        ("TOKEN=abc", True),
        ("ApiKey=abc", True),
        ("Access_Token=abc", True),
        ("page=2", False),
        ("format=csv", False),
        ("id=123&format=csv", False),
        ("q=token", False),
        ("keyword=x", False),
        ("monkey=1", False),
        ("tokens=1", False),
        ("my_key=1", False),
    ],
)
def test_fr_001_32_credential_named_query_parameters_are_rejected_in_every_url_field(
    tmp_path: Path, query: str, flagged: bool
) -> None:
    url = f"https://example.org/api/stations?{query}"

    def edit(d: dict) -> None:
        e = d["sources"][1]  # example-station-hourly
        e["landing_url"], e["licence_url"], e["files"][0]["url"] = url, url, url

    res = cs.run_checker(repo_with_sources(tmp_path, edit))
    found = res.in_file(SOURCES_YAML, "/sources/1")
    pointers = {f["pointer"] for f in found}
    expected = {"/sources/1/landing_url", "/sources/1/licence_url", "/sources/1/files/0/url"}
    if flagged:
        assert expected <= pointers, (query, res.findings)
        assert all("example-station-hourly" in f["message"] and len(f["message"]) <= 300 for f in found)
    else:
        assert not (expected & pointers), (query, res.findings)


def secret_values() -> list[str]:
    """One string per pattern of tools/check_repo.py, assembled so this file itself never matches them."""
    return [
        "sk" + "-ant-" + "a1b2c3d4e5f6g7h8i9",
        "sk" + "-" + "proj-" + "A" * 40,
        "gs" + "k_" + "A" * 24,
        "gh" + "p_" + "A" * 36,
        "github" + "_pat_" + "A" * 24,
        "-----BEGIN " + "RSA PRIVATE KEY-----",
        "AK" + "IA" + "ABCDEFGHIJKLMNOP",
        "AI" + "za" + "A" * 35,
    ]


@pytest.mark.req("FR-001-32")
def test_fr_001_32_values_matching_the_secret_patterns_of_check_repo_are_rejected(tmp_path: Path) -> None:
    sys.path.insert(0, str(cs.ROOT / "tools"))
    import check_repo  # the reference scanner

    secrets = secret_values()
    for s in secrets:
        assert check_repo.CHECKS["secret"].search(s), s  # the oracle itself flags every sample
    fields = ("title", "citation", "attribution")
    for run, start in enumerate(range(0, len(secrets), 3)):
        chunk = secrets[start : start + 3]

        def edit(d: dict, chunk: list[str] = chunk) -> None:
            for field, secret in zip(fields, chunk, strict=False):
                d["sources"][1][field] = secret

        res = cs.run_checker(repo_with_sources(tmp_path / f"run{run}", edit))
        for field in fields[: len(chunk)]:
            assert res.in_file(SOURCES_YAML, f"/sources/1/{field}"), (field, res.findings)
    clean = cs.run_checker(
        repo_with_sources(tmp_path / "clean", lambda d: d["sources"][1].update(title="sk-skill-based task"))
    )
    assert clean.in_file(SOURCES_YAML, "/sources/1/title") == []


@pytest.mark.req("FR-001-32")
def test_fr_001_32_duplicate_ids_are_rejected_naming_the_entry(tmp_path: Path) -> None:
    def dup(d: dict) -> None:
        d["sources"][2]["id"] = d["sources"][0]["id"]

    res = cs.run_checker(repo_with_sources(tmp_path, dup))
    found = res.in_file(SOURCES_YAML, "/sources/2")
    assert found
    assert any(re.search(r"example-haul-network", f["message"]) for f in found)
    assert all(len(f["message"]) <= 300 for f in found)


@pytest.mark.req("FR-001-32")
def test_fr_001_32_the_corpus_duplicate_id_fixture_is_flagged(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    fixture = next(e for e in cs.entries(schema="sources", rule="FR-001-32", tag_in=("cross-file",)))
    cs.write_file(root, SOURCES_YAML, cs.fixture_json(fixture))
    assert cs.run_checker(root).in_file(SOURCES_YAML, fixture["pointer"])


@pytest.mark.req("FR-001-32")
def test_fr_001_32_clean_registry_passes_the_checker(tmp_path: Path) -> None:
    res = cs.run_checker(cs.clean_repo(tmp_path))
    assert res.in_file(SOURCES_YAML) == []

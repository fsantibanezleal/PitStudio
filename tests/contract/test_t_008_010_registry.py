# ruff: noqa: E501, PT018
"""T-008-010: s00_download reads and validates the whole source registry before it opens any connection.

Requirements: FR-008-01, FR-008-02.

Spec: specs/008-data-pipeline/ (spec.md rows FR-008-01 and FR-008-02, plan.md "Registry loader").

Oracle: the hostile registry corpus of spec 001 (`specs/001-contracts/contracts/examples/sources.hostile-*.json`, with the
JSON pointer of each violation recorded by the spec author in `examples/index.json`), plus hand-built registries with one
violation each (duplicate id, unknown fallback id, class less restrictive than a per-file SPDX override, size 0). A
mocked transport that fails on any request proves "before it opens any connection".

Expected API of the implementation (package `pitstudio_pipeline`, environment `pipeline/`):
- `pitstudio_pipeline.errors.RegistryError(Exception)` with `.violations`: a list of objects with the attributes
  `entry_id` (str or None), `pointer` (str, JSON pointer such as "/sources/1/spdx") and `rule` (str, non-empty).
- `pitstudio_pipeline.download.load_registry(path, *, schema_path=None) -> dict`: parse the YAML registry and validate the
  whole document; on any violation raise `RegistryError` listing every violation; `schema_path` defaults to
  `contracts/sources.schema.json`.
- `pitstudio_pipeline.download.run_download(registry_path=None, data_root=None, *, transport=None, env=None, repo_root=None,
  schema_path=None, ...) -> DownloadResult`: validates the registry first (`registry_path=None` reads
  `<repo_root>/data/sources.yaml`, the only registry it reads), then fetches; `DownloadResult` has `exit_status` (int),
  `records` (list of fetch-record dicts) and `errors` (dict source id -> exception).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import _p008_kit as kit
from pitstudio_pipeline.download import load_registry, run_download
from pitstudio_pipeline.errors import RegistryError

CORPUS = kit.SPEC001 / "contracts" / "examples"
SCHEMA = kit.draft_schema_path("sources.schema.json")
HOSTILE = [
    e
    for e in json.loads((CORPUS / "index.json").read_text(encoding="utf-8"))["examples"]
    if e["file"].startswith("sources.hostile-")
]


def _write(tmp: Path, doc: dict, name: str = "sources.yaml") -> Path:
    p = tmp / name
    p.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p


def _run(tmp: Path, reg: Path, net: kit.Net):
    return run_download(reg, tmp / "data", transport=net.transport, schema_path=SCHEMA, env=kit.env_with())


@pytest.mark.req("FR-008-01")
def test_valid_spec001_registry_loads_whole(tmp_path: Path) -> None:
    doc = json.loads((CORPUS / "sources.valid.json").read_text(encoding="utf-8"))
    got = load_registry(_write(tmp_path, doc), schema_path=SCHEMA)
    assert [s["id"] for s in got["sources"]] == [s["id"] for s in doc["sources"]]


@pytest.mark.req("FR-008-01")
def test_empty_registry_is_valid_and_downloads_nothing(tmp_path: Path) -> None:
    net = kit.Net(forbid=True)
    reg = _write(tmp_path, {"sources": []})
    result = _run(tmp_path, reg, net)
    assert result.exit_status == 0 and result.records == [] and net.requests == []


@pytest.mark.req("FR-008-01")
def test_reads_only_data_sources_yaml_of_the_repository(tmp_path: Path) -> None:
    repo = kit.make_repo(tmp_path)
    data = kit.payload(300, 1)
    other = kit.payload(300, 2)
    kit.write_registry(repo / "data", [kit.entry("alpha", [kit.file_rec("https://example.org/a.bin", data)])])
    # a decoy registry next to the real one must never be read
    kit.write_registry(
        repo / "data", [kit.entry("decoy", [kit.file_rec("https://example.org/d.bin", other)])], "sources.extra.yaml"
    )
    net = kit.Net({"https://example.org/a.bin": data, "https://example.org/d.bin": other})
    result = run_download(
        None, repo / "data" / "raw", repo_root=repo, transport=net.transport, schema_path=SCHEMA, env=kit.env_with()
    )
    assert net.urls == ["https://example.org/a.bin"]
    assert {r["source"] for r in result.records} == {"alpha"}


@pytest.mark.req("FR-008-02")
@pytest.mark.parametrize("ex", HOSTILE, ids=[e["file"] for e in HOSTILE])
def test_every_spec001_hostile_registry_is_rejected_whole_before_any_connection(ex: dict, tmp_path: Path) -> None:
    doc = json.loads((CORPUS / ex["file"]).read_text(encoding="utf-8"))
    reg = _write(tmp_path, doc)
    net = kit.Net(forbid=True)
    with pytest.raises(RegistryError) as info:
        _run(tmp_path, reg, net)
    assert net.requests == [], "no connection may be opened for an invalid registry"
    assert kit.files_under(tmp_path / "data") == [], "nothing may be downloaded"
    pointers = [v.pointer for v in info.value.violations]
    assert ex["pointer"] in pointers, f"expected a violation at {ex['pointer']}, got {pointers}"
    for v in info.value.violations:
        assert v.rule, "every violation names its rule"
        if v.pointer.startswith("/sources/"):
            idx = int(v.pointer.split("/")[2])
            assert v.entry_id == doc["sources"][idx].get("id")


@pytest.mark.req("FR-008-02")
@pytest.mark.parametrize("ex", HOSTILE[:6], ids=[e["file"] for e in HOSTILE[:6]])
def test_load_registry_alone_rejects_the_same_corpus(ex: dict, tmp_path: Path) -> None:
    reg = _write(tmp_path, json.loads((CORPUS / ex["file"]).read_text(encoding="utf-8")))
    with pytest.raises(RegistryError):
        load_registry(reg, schema_path=SCHEMA)


@pytest.mark.req("FR-008-02")
def test_one_valid_entry_does_not_save_a_registry_with_an_invalid_one(tmp_path: Path) -> None:
    good_bytes = kit.payload(100, 3)
    good = kit.entry("good", [kit.file_rec("https://example.org/g.bin", good_bytes)])
    bad = kit.entry("bad", [kit.file_rec("http://example.org/b.bin", good_bytes)])  # non-HTTPS file URL
    net = kit.Net({"https://example.org/g.bin": good_bytes}, forbid=True)
    with pytest.raises(RegistryError):
        _run(tmp_path, kit.write_registry(tmp_path, [good, bad]), net)
    assert net.requests == [] and kit.files_under(tmp_path / "data") == []


@pytest.mark.req("FR-008-02")
def test_all_violations_are_listed_not_only_the_first(tmp_path: Path) -> None:
    d = kit.payload(10, 4)
    e0 = kit.entry("e0", [kit.file_rec("http://example.org/a", d)])  # /sources/0/files/0/url
    e1 = kit.entry("e1", [kit.file_rec("https://example.org/b", d)], spdx="GPL-3.0-only")  # /sources/1/spdx
    e2 = kit.entry("e2", [kit.file_rec("https://example.org/c", d)])
    e2["files"][0]["sha256"] = "ab" * 31 + "a"  # 63 hex digits: /sources/2/files/0/sha256
    reg = kit.write_registry(tmp_path, [e0, e1, e2])
    with pytest.raises(RegistryError) as info:
        _run(tmp_path, reg, kit.Net(forbid=True))
    pointers = {v.pointer for v in info.value.violations}
    assert "/sources/0/files/0/url" in pointers
    assert "/sources/1/spdx" in pointers
    assert "/sources/2/files/0/sha256" in pointers


@pytest.mark.req("FR-008-02")
def test_duplicate_ids_are_rejected_naming_the_id(tmp_path: Path) -> None:
    d = kit.payload(10, 5)
    a = kit.entry("dup", [kit.file_rec("https://example.org/a", d)])
    b = kit.entry("dup", [kit.file_rec("https://example.org/b", d)])
    with pytest.raises(RegistryError) as info:
        _run(tmp_path, kit.write_registry(tmp_path, [a, b]), kit.Net(forbid=True))
    assert any(v.entry_id == "dup" for v in info.value.violations)


@pytest.mark.req("FR-008-02")
def test_unknown_fallback_id_is_rejected(tmp_path: Path) -> None:
    acc = kit.entry(
        "needs-key",
        [kit.file_rec("https://example.org/k", kit.payload(10, 6))],
        access="account",
        account={"needed": True, "env_var": "EXAMPLE_KEY"},
        fallback={"sources": ["does-not-exist"], "text": "substitute"},
    )
    with pytest.raises(RegistryError) as info:
        _run(tmp_path, kit.write_registry(tmp_path, [acc]), kit.Net(forbid=True))
    assert any(v.entry_id == "needs-key" for v in info.value.violations)


@pytest.mark.req("FR-008-02")
def test_licence_class_less_restrictive_than_a_per_file_share_alike_override_is_rejected(tmp_path: Path) -> None:
    # FR-001-58: the most restrictive class among per-file SPDX overrides wins; declaring less is an error.
    d = kit.payload(10, 7)
    e = kit.entry(
        "mixed",
        [kit.file_rec("https://example.org/a", d), kit.file_rec("https://example.org/b", d, spdx="CC-BY-SA-4.0")],
        spdx="CC-BY-4.0",
        licence_class="attribution",
        attribution="Example publisher, CC BY 4.0",
    )
    with pytest.raises(RegistryError) as info:
        _run(tmp_path, kit.write_registry(tmp_path, [e]), kit.Net(forbid=True))
    assert any(v.entry_id == "mixed" and "source-class-too-permissive" in v.rule for v in info.value.violations)


@pytest.mark.req("FR-008-02")
@pytest.mark.parametrize("bad", [0, -5, 68719476737])
def test_out_of_range_sizes_are_rejected(bad: int, tmp_path: Path) -> None:
    f = kit.file_rec("https://example.org/a", kit.payload(10, 8))
    f["bytes"] = bad  # valid range is 1 .. 64 GiB (data-model 001 section 5.1.1)
    with pytest.raises(RegistryError) as info:
        _run(tmp_path, kit.write_registry(tmp_path, [kit.entry("sz", [f])]), kit.Net(forbid=True))
    assert any(v.pointer == "/sources/0/files/0/bytes" for v in info.value.violations)


@pytest.mark.req("FR-008-02")
@pytest.mark.parametrize("field", ["licence_url", "spdx", "licence_class", "citation", "redistribution"])
def test_missing_licence_field_is_rejected(field: str, tmp_path: Path) -> None:
    e = kit.entry("nolic", [kit.file_rec("https://example.org/a", kit.payload(10, 9))])
    del e[field]
    with pytest.raises(RegistryError) as info:
        _run(tmp_path, kit.write_registry(tmp_path, [e]), kit.Net(forbid=True))
    assert any(v.entry_id == "nolic" for v in info.value.violations)


@pytest.mark.req("FR-008-02")
def test_credential_like_value_in_the_registry_is_rejected(tmp_path: Path) -> None:
    e = kit.entry(
        "leaky",
        [kit.file_rec("https://example.org/a", kit.payload(10, 10))],
        access="account",
        account={"needed": True, "env_var": "sk-live-0123456789abcdef0123456789abcdef"},  # a value, not a variable name
        fallback={"sources": [], "text": "none"},
    )
    with pytest.raises(RegistryError) as info:
        _run(tmp_path, kit.write_registry(tmp_path, [e]), kit.Net(forbid=True))
    assert any(v.pointer == "/sources/0/account/env_var" for v in info.value.violations)


@pytest.mark.req("FR-008-02")
def test_unicode_and_empty_hostile_documents_are_rejected_not_crashed(tmp_path: Path) -> None:
    net = kit.Net(forbid=True)
    for text in ["", "sources: 7\n", "- not a mapping\n", "sources:\n  - id: été-☃\n"]:
        p = tmp_path / "sources.yaml"
        p.write_text(text, encoding="utf-8")
        with pytest.raises(RegistryError):
            _run(tmp_path, p, net)
    assert net.requests == []

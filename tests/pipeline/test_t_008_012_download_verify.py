# ruff: noqa: E501, PT018
"""T-008-012: fetch through pooch with a resumable downloader, streaming SHA-256, `.part` promotion, cached re-verification,
quarantine on mismatch and one fetch record per file.

Requirements: FR-008-05, FR-008-06, FR-008-17, P-008-01.

Spec: specs/008-data-pipeline/spec.md rows FR-008-05, FR-008-06, FR-008-17, P-008-01; contract
`specs/008-data-pipeline/contracts/fetch-record.schema.json` (DC-008-02).

Oracle: `hashlib.sha256` (reference implementation) and the published SHA-256 vectors of FIPS 180-2 ("abc") and of the
empty message; fixture byte strings whose digest and length are computed in the test; the fetch-record JSON Schema
(validated with `jsonschema`). The transport is `httpx.MockTransport`: no network.

Expected API of the implementation (package `pitstudio_pipeline`):
- `pitstudio_pipeline.download.sha256_file(path, *, chunk_size=1 << 20) -> str`: streaming hex digest of a file.
- `pitstudio_pipeline.download.run_download(registry_path, data_root, *, transport=None, env=None, now=None, sleep=None,
  schema_path=None, repo_root=None, ...) -> DownloadResult` with `exit_status` (0 only if every selected source ended
  verified or fell back), `records` (list of fetch-record dicts, one per registry file, keys of DC-008-02),
  `errors` (dict source id -> exception), `unavailable` (list of source ids). `now` is a zero-argument callable returning an
  aware UTC datetime (the record's `retrieved` is that instant as `YYYY-MM-DDTHH:MM:SSZ`); `sleep(seconds)` replaces
  `time.sleep`; `transport` is an `httpx.BaseTransport` used by the downloader.
- Layout under the data root: `raw/<id>/<name>` (direct and api sources), `external/<id>/<name>` (account and manual
  sources), `quarantine/<id>/<name>`; `<name>` is the entry's `name` when given, else the percent-decoded last segment
  of the URL path. In a fetch record `stored_as` is the path relative to the data root, in POSIX form.
- `pitstudio_pipeline.errors.ChecksumMismatch(Exception)` with `expected_sha256`, `actual_sha256`, `expected_bytes`,
  `actual_bytes`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import _p008_kit as kit
import httpx
import pytest
from pitstudio_pipeline.download import sha256_file
from pitstudio_pipeline.errors import ChecksumMismatch

# isort: split
from hypothesis import given, settings
from hypothesis import strategies as st

URL = "https://example.org/data/a.bin"
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # SHA-256 of the empty message
ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"  # FIPS 180-2 appendix B.1


# ------------------------------------------------------------------------------------------------ P-008-01
@pytest.mark.req("P-008-01")
def test_published_vectors(tmp_path: Path) -> None:
    f = tmp_path / "abc"
    f.write_bytes(b"abc")
    assert sha256_file(f) == ABC_SHA256
    e = tmp_path / "empty"
    e.write_bytes(b"")
    assert sha256_file(e) == EMPTY_SHA256


@pytest.mark.req("P-008-01")
@settings(max_examples=60, deadline=None)
@given(data=st.binary(max_size=20_000), chunk=st.integers(min_value=1, max_value=1 << 20))
def test_streaming_digest_equals_hashlib_for_any_chunking(data: bytes, chunk: int, tmp_path_factory) -> None:
    f = tmp_path_factory.mktemp("sha") / "x.bin"
    f.write_bytes(data)
    assert sha256_file(f, chunk_size=chunk) == hashlib.sha256(data).hexdigest()


@pytest.mark.req("P-008-01")
@pytest.mark.parametrize("chunk", [1 << 20, 4093, 65_536, 10 * (1 << 20), 10 * (1 << 20) + 1])
def test_ten_mebibytes_for_awkward_chunk_sizes(chunk: int, tmp_path: Path) -> None:
    data = kit.payload(10 * (1 << 20), 11)
    f = tmp_path / "big.bin"
    f.write_bytes(data)
    assert sha256_file(f, chunk_size=chunk) == hashlib.sha256(data).hexdigest()


@pytest.mark.req("FR-008-05")
def test_verification_uses_hashlib_file_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    real = hashlib.file_digest

    def spy(fileobj, digest, **kw):
        calls.append(str(digest))
        return real(fileobj, digest, **kw)

    monkeypatch.setattr(hashlib, "file_digest", spy)
    data = kit.payload(2048, 1)
    result = kit.run(tmp_path, [kit.entry("s", [kit.file_rec(URL, data)])], kit.Net({URL: data}))
    assert result.exit_status == 0
    assert calls, "the stage must compute the digest by streaming with hashlib.file_digest"


# ------------------------------------------------------------------------------------------------ FR-008-05, FR-008-17
@pytest.mark.req("FR-008-05")
@pytest.mark.req("FR-008-17")
def test_verified_download_is_promoted_and_recorded(tmp_path: Path) -> None:
    data = kit.payload(5000, 2)
    net = kit.Net({URL: data})
    result = kit.run(tmp_path, [kit.entry("alpha", [kit.file_rec(URL, data)])], net)
    assert result.exit_status == 0
    final = tmp_path / "data" / "raw" / "alpha" / "a.bin"
    assert final.read_bytes() == data
    assert not list((tmp_path / "data").rglob("*.part")), "no .part file may remain after promotion"
    (rec,) = result.records
    assert kit.schema_errors("fetch-record.schema.json", rec) == []
    assert rec["status"] == "verified"
    assert rec["source"] == "alpha" and rec["name"] == "a.bin" and rec["url"] == URL and rec["final_url"] == URL
    assert rec["stored_as"] == "raw/alpha/a.bin"
    assert rec["bytes"] == rec["expected_bytes"] == len(data)
    assert rec["sha256"] == rec["expected_sha256"] == hashlib.sha256(data).hexdigest()
    assert (rec["spdx"], rec["licence_class"], rec["redistribution"]) == (
        "CC0-1.0",
        "open-no-attribution",
        "redistributable",
    )
    assert rec["retrieved"] == kit.NOW_TEXT
    assert rec["attempts"] == 1 and rec["fallback_sources"] == []
    assert rec["publisher_checksum_status"] == "not-declared"


@pytest.mark.req("FR-008-05")
def test_entry_name_overrides_the_url_segment_and_redirects_are_followed(tmp_path: Path) -> None:
    data = kit.payload(777, 3)
    first = "https://example.org/get/file_downloaded"
    final = "https://cdn.example.org/blob/xyz"
    net = kit.Net(
        {
            first: lambda r: httpx.Response(302, headers={"Location": final}),
            final: data,
        }
    )
    e = kit.entry("named", [kit.file_rec(first, data, name="research-data.bin")])
    result = kit.run(tmp_path, [e], net)
    assert (tmp_path / "data" / "raw" / "named" / "research-data.bin").read_bytes() == data
    (rec,) = result.records
    assert rec["name"] == "research-data.bin" and rec["url"] == first and rec["final_url"] == final
    assert kit.schema_errors("fetch-record.schema.json", rec) == []


@pytest.mark.req("FR-008-05")
def test_account_and_manual_sources_go_to_external(tmp_path: Path) -> None:
    data = kit.payload(400, 4)
    acc = kit.entry(
        "acct",
        [kit.file_rec("https://example.org/k.bin", data)],
        access="account",
        account={"needed": True, "env_var": "EXAMPLE_KEY"},
        fallback={"sources": [], "text": "none"},
    )
    result = kit.run(
        tmp_path, [acc], kit.Net({"https://example.org/k.bin": data}), env=kit.env_with(EXAMPLE_KEY="value")
    )
    assert (tmp_path / "data" / "external" / "acct" / "k.bin").read_bytes() == data
    assert not (tmp_path / "data" / "raw" / "acct").exists()
    assert result.records[0]["stored_as"] == "external/acct/k.bin"


@pytest.mark.req("FR-008-05")
def test_manual_source_files_are_only_verified_where_the_maintainer_put_them(tmp_path: Path) -> None:
    data = kit.payload(400, 5)
    man = kit.entry("hand", [kit.file_rec("https://example.org/m.bin", data)], access="manual")
    place = tmp_path / "data" / "external" / "hand"
    place.mkdir(parents=True)
    (place / "m.bin").write_bytes(data)
    net = kit.Net(forbid=True)  # a manual source is never fetched
    result = kit.run(tmp_path, [man], net)
    assert net.requests == [] and result.exit_status == 0
    assert result.records[0]["status"] == "verified" and result.records[0]["stored_as"] == "external/hand/m.bin"


@pytest.mark.req("FR-008-05")
def test_cached_file_is_reverified_and_reused_without_a_request(tmp_path: Path) -> None:
    data = kit.payload(900, 6)
    cached = tmp_path / "data" / "raw" / "c"
    cached.mkdir(parents=True)
    (cached / "a.bin").write_bytes(data)
    net = kit.Net(forbid=True)
    result = kit.run(tmp_path, [kit.entry("c", [kit.file_rec(URL, data)])], net)
    assert net.requests == [] and result.exit_status == 0
    assert result.records[0]["status"] == "verified" and result.records[0]["sha256"] == hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------------------------------------ FR-008-06
def _mismatch_case(tmp_path: Path, served: bytes, declared: bytes):
    net = kit.Net({URL: served})
    result = kit.run(tmp_path, [kit.entry("bad", [kit.file_rec(URL, declared)])], net)
    return result, net


@pytest.mark.req("FR-008-06")
def test_tampered_content_of_the_right_length_is_quarantined(tmp_path: Path) -> None:
    declared = kit.payload(3000, 7)
    served = bytearray(declared)
    served[1500] ^= 0xFF
    result, _ = _mismatch_case(tmp_path, bytes(served), declared)
    assert result.exit_status != 0
    err = result.errors["bad"]
    assert isinstance(err, ChecksumMismatch)
    assert err.expected_sha256 == hashlib.sha256(declared).hexdigest()
    assert err.actual_sha256 == hashlib.sha256(bytes(served)).hexdigest()
    assert err.expected_bytes == 3000 and err.actual_bytes == 3000
    assert not (tmp_path / "data" / "raw" / "bad" / "a.bin").exists(), "nothing is promoted"
    assert (tmp_path / "data" / "quarantine" / "bad" / "a.bin").read_bytes() == bytes(served)
    assert not list((tmp_path / "data").rglob("*.part"))
    assert all(r["status"] != "verified" for r in result.records)


@pytest.mark.req("FR-008-06")
def test_a_short_body_with_a_matching_prefix_fails_on_bytes_and_digest(tmp_path: Path) -> None:
    declared = kit.payload(3000, 8)
    result, _ = _mismatch_case(tmp_path, declared[:2999], declared)
    err = result.errors["bad"]
    assert isinstance(err, ChecksumMismatch)
    assert err.expected_bytes == 3000 and err.actual_bytes == 2999
    assert result.exit_status != 0
    assert not (tmp_path / "data" / "raw" / "bad" / "a.bin").exists()


@pytest.mark.req("FR-008-06")
def test_a_corrupted_cached_file_is_quarantined_not_reused(tmp_path: Path) -> None:
    declared = kit.payload(1200, 9)
    cached = tmp_path / "data" / "raw" / "bad"
    cached.mkdir(parents=True)
    (cached / "a.bin").write_bytes(declared[:-1] + bytes([declared[-1] ^ 1]))
    result = kit.run(tmp_path, [kit.entry("bad", [kit.file_rec(URL, declared)])], kit.Net({}))
    assert isinstance(result.errors["bad"], ChecksumMismatch)
    assert result.exit_status != 0
    assert not (tmp_path / "data" / "raw" / "bad" / "a.bin").exists()
    assert (tmp_path / "data" / "quarantine" / "bad" / "a.bin").is_file()


@pytest.mark.req("FR-008-06")
def test_one_bad_source_does_not_stop_the_others_but_ends_the_stage_non_zero(tmp_path: Path) -> None:
    good, declared = kit.payload(500, 10), kit.payload(500, 11)
    net = kit.Net({"https://example.org/g.bin": good, URL: kit.payload(500, 12)})
    entries = [
        kit.entry("bad", [kit.file_rec(URL, declared)]),
        kit.entry("good", [kit.file_rec("https://example.org/g.bin", good)]),
    ]
    result = kit.run(tmp_path, entries, net)
    assert result.exit_status != 0
    assert (tmp_path / "data" / "raw" / "good" / "g.bin").read_bytes() == good
    statuses = {r["source"]: r["status"] for r in result.records}
    assert statuses["good"] == "verified" and statuses.get("bad") != "verified"


@pytest.mark.req("FR-008-17")
def test_publisher_checksum_is_recorded_when_declared(tmp_path: Path) -> None:
    data = kit.payload(640, 13)
    f = kit.file_rec(URL, data, publisher_checksum="md5:" + kit.md5_hex(data))
    result = kit.run(tmp_path, [kit.entry("pub", [f])], kit.Net({URL: data}))
    (rec,) = result.records
    assert kit.schema_errors("fetch-record.schema.json", rec) == []
    assert rec["publisher_checksum"] == "md5:" + kit.md5_hex(data)
    assert rec["publisher_checksum_status"] in {"match", "not-checked"}


@pytest.mark.req("FR-008-17")
def test_one_record_per_file_in_registry_order(tmp_path: Path) -> None:
    files = [(f"https://example.org/f{i}.bin", kit.payload(100 + i, 20 + i)) for i in range(4)]
    net = kit.Net(dict(files))
    result = kit.run(tmp_path, [kit.entry("multi", [kit.file_rec(u, d) for u, d in files])], net)
    assert [r["url"] for r in result.records] == [u for u, _ in files]
    assert all(kit.schema_errors("fetch-record.schema.json", r) == [] for r in result.records)
    assert {r["retrieved"] for r in result.records} == {kit.NOW_TEXT}

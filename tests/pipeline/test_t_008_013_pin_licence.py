# ruff: noqa: E501, PT018
"""T-008-013: `--pin` proposals with publisher-checksum checks (the registry is never edited) and `UnpinnedSource`.

Requirements: FR-008-07, FR-008-08.

Spec: specs/008-data-pipeline/spec.md FR-008-07, FR-008-08 and section 7 ("Publisher checksums": Zenodo publishes MD5, it is
checked before the SHA-256 pin is proposed and never replaces it).

Oracle: fixture bytes whose MD5 and SHA-256 are computed with `hashlib` inside the test (published digests of the fixture,
standing in for what a publisher states); the registry file compared byte for byte before and after the run.

Expected API of the implementation:
- `run_download(registry_path, data_root, *, pin=False, publishable=False, pins_dir=None, transport=None, ...)`:
  with `pin=True` an entry file with `sha256: null` is fetched, its publisher checksum (`files[].publisher_checksum`,
  `md5:<hex>` or `sha256:<hex>`) is verified FIRST when declared, then the computed SHA-256 and byte count are written to
  `<pins_dir>/<id>.proposed.yaml` (default `<repo_root>/data/pins`); the fetch record gets `status: pin-proposed`,
  `expected_sha256: null`, `sha256` = the computed digest and `publisher_checksum_status` `match` or `not-declared`;
  `result.manifest` is a dict with `unpublishable: True` for such a run; the registry file is never written.
- A publisher checksum mismatch ends that source with an exception in `result.errors[id]`, writes no proposal and gives a
  non-zero `exit_status`.
- `pitstudio_pipeline.errors.UnpinnedSource(Exception)`: raised by `run_download` (before any connection) when a file has no
  `sha256` and `pin` is false, or when `publishable=True` and a file has no pinned `sha256`; names the source id.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import _p008_kit as kit
import pytest
import yaml
from pitstudio_pipeline.errors import UnpinnedSource

URL = "https://example.org/zenodo/record/a.bin"


def _unpinned(sid: str, data: bytes, **extra) -> dict:
    return kit.entry(sid, [kit.file_rec(URL, data, pinned=False, **extra)])


@pytest.mark.req("FR-008-07")
def test_pin_run_proposes_the_digest_and_never_edits_the_registry(tmp_path: Path) -> None:
    data = kit.payload(4096, 1)
    entries = [_unpinned("zen", data, publisher_checksum="md5:" + kit.md5_hex(data))]
    reg = kit.write_registry(tmp_path / "cfg", entries)
    before = reg.read_bytes()
    net = kit.Net({URL: data})
    result = kit.run(tmp_path, entries, net, pin=True, pins_dir=tmp_path / "pins")
    reg_after = (tmp_path / "cfg" / "sources.yaml").read_bytes()
    assert reg_after == before, "the registry is for the maintainer to edit: the stage never writes it"
    proposal = tmp_path / "pins" / "zen.proposed.yaml"
    text = proposal.read_text(encoding="utf-8")
    assert hashlib.sha256(data).hexdigest() in text
    assert str(len(data)) in json.dumps(yaml.safe_load(text))
    (rec,) = result.records
    assert kit.schema_errors("fetch-record.schema.json", rec) == []
    assert rec["status"] == "pin-proposed" and rec["expected_sha256"] is None
    assert rec["sha256"] == hashlib.sha256(data).hexdigest()
    assert rec["publisher_checksum_status"] == "match"
    assert result.manifest["unpublishable"] is True
    assert result.exit_status == 0


@pytest.mark.req("FR-008-07")
def test_sha256_publisher_checksum_form_is_also_checked(tmp_path: Path) -> None:
    data = kit.payload(512, 2)
    entries = [_unpinned("zen", data, publisher_checksum="sha256:" + hashlib.sha256(data).hexdigest())]
    result = kit.run(tmp_path, entries, kit.Net({URL: data}), pin=True, pins_dir=tmp_path / "pins")
    assert result.records[0]["publisher_checksum_status"] == "match"
    assert (tmp_path / "pins" / "zen.proposed.yaml").is_file()


@pytest.mark.req("FR-008-07")
def test_no_publisher_checksum_declared_is_recorded_as_such(tmp_path: Path) -> None:
    data = kit.payload(512, 3)
    result = kit.run(tmp_path, [_unpinned("zen", data)], kit.Net({URL: data}), pin=True, pins_dir=tmp_path / "pins")
    assert result.records[0]["publisher_checksum_status"] == "not-declared"
    assert result.records[0]["status"] == "pin-proposed"


@pytest.mark.req("FR-008-07")
@pytest.mark.parametrize("form", ["md5", "sha256"])
def test_publisher_checksum_mismatch_blocks_the_proposal(form: str, tmp_path: Path) -> None:
    data = kit.payload(512, 4)
    other = kit.payload(512, 5)
    declared = "md5:" + kit.md5_hex(other) if form == "md5" else "sha256:" + hashlib.sha256(other).hexdigest()
    result = kit.run(
        tmp_path,
        [_unpinned("zen", data, publisher_checksum=declared)],
        kit.Net({URL: data}),
        pin=True,
        pins_dir=tmp_path / "pins",
    )
    assert "zen" in result.errors and isinstance(result.errors["zen"], Exception)
    assert result.exit_status != 0
    assert not (tmp_path / "pins" / "zen.proposed.yaml").exists()
    assert all(r["status"] != "pin-proposed" for r in result.records)


@pytest.mark.req("FR-008-07")
def test_pin_flag_does_not_touch_entries_that_are_already_pinned(tmp_path: Path) -> None:
    data = kit.payload(300, 6)
    entries = [kit.entry("pinned", [kit.file_rec(URL, data)])]
    result = kit.run(tmp_path, entries, kit.Net({URL: data}), pin=True, pins_dir=tmp_path / "pins")
    assert result.records[0]["status"] == "verified"
    assert not (tmp_path / "pins" / "pinned.proposed.yaml").exists()


@pytest.mark.req("FR-008-08")
def test_unpinned_file_without_pin_is_refused_before_any_request(tmp_path: Path) -> None:
    data = kit.payload(300, 7)
    net = kit.Net({URL: data}, forbid=True)
    with pytest.raises(UnpinnedSource) as info:
        kit.run(tmp_path, [_unpinned("zen", data)], net)
    assert "zen" in str(info.value)
    assert net.requests == []
    assert kit.files_under(tmp_path / "data") == []


@pytest.mark.req("FR-008-08")
def test_a_single_unpinned_file_among_pinned_ones_is_refused(tmp_path: Path) -> None:
    a, b = kit.payload(100, 8), kit.payload(100, 9)
    files = [kit.file_rec("https://example.org/a", a), kit.file_rec("https://example.org/b", b, pinned=False)]
    with pytest.raises(UnpinnedSource):
        kit.run(tmp_path, [kit.entry("mix", files)], kit.Net({"https://example.org/a": a, "https://example.org/b": b}))
    assert not (tmp_path / "data" / "raw" / "mix" / "b").exists()


@pytest.mark.req("FR-008-08")
def test_publishable_run_refuses_unpinned_files_even_with_pin(tmp_path: Path) -> None:
    data = kit.payload(300, 10)
    with pytest.raises(UnpinnedSource):
        kit.run(
            tmp_path,
            [_unpinned("zen", data)],
            kit.Net({URL: data}),
            pin=True,
            publishable=True,
            pins_dir=tmp_path / "pins",
        )


@pytest.mark.req("FR-008-08")
def test_publishable_run_over_fully_pinned_registry_is_accepted_and_not_marked_unpublishable(tmp_path: Path) -> None:
    data = kit.payload(300, 11)
    result = kit.run(tmp_path, [kit.entry("ok", [kit.file_rec(URL, data)])], kit.Net({URL: data}), publishable=True)
    assert result.exit_status == 0
    assert not result.manifest.get("unpublishable", False)

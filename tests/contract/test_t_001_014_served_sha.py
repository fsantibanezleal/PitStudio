"""T-001-014 · served-file digest and size check (P-000-02): FR-001-20.

Oracle: ``hashlib.sha256`` and ``len()`` of the fixture bytes (reference implementations) against deliberately wrong
web-index entries; the ``pages.yml`` wiring is checked by parsing the workflow with PyYAML.

Expected API: ``tools/check_contracts.py [--release-assets DIR]``. Git-hosted artefacts are read from
``<root>/web/public/<path>``; release-hosted artefacts are read from ``DIR/<path>`` (the asset file name, downloaded by
tag before the copy into the Pages artifact) and are checked only when ``--release-assets`` is given. A differing
digest or size, a missing file or an unreadable file is a finding ``rule: FR-001-20`` with pointer ``/artefacts/<i>``
(``/runs/<i>`` for a published run manifest) whose message names the artefact id and what differs (``sha256`` or
``bytes``) in at most 300 characters. ``.github/workflows/pages.yml`` runs the check, with ``--release-assets``, in the
build job before the upload-pages-artifact step.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_support as cs

INDEX = "web/public/assets/manifest.json"
RUN_ID = "20261007T120000Z-a2-haulage"
VIDEO = "web/public/assets/media/a2-haul.mp4"
REPORT = "web/public/assets/media/a2-encode-report.json"
RUN_MANIFEST = f"web/public/assets/runs/{RUN_ID}/manifest.json"
MODEL = b"\x08\x07onnx fixture model bytes\n" * 50


def hits(res: cs.CheckResult, pointer_prefix: str) -> list[dict]:
    return res.at("FR-001-20", pointer_prefix)


@pytest.mark.req("FR-001-20")
def test_fr_001_20_matching_git_hosted_files_pass(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    for rel in (VIDEO, REPORT):  # the oracle: the index entry equals hashlib over the served bytes
        data = (root / rel).read_bytes()
        entry = next(
            a for a in json.loads((root / INDEX).read_text(encoding="utf-8"))["artefacts"] if rel.endswith(a["path"])
        )
        assert (entry["sha256"], entry["bytes"]) == (cs.sha256_hex(data), len(data))
    assert cs.run_checker(root).of("FR-001-20") == []


@pytest.mark.req("FR-001-20")
def test_fr_001_20_one_flipped_byte_with_the_same_size_is_a_digest_finding(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    data = bytearray((root / VIDEO).read_bytes())
    data[-1] ^= 0x01
    (root / VIDEO).write_bytes(bytes(data))
    res = cs.run_checker(root)
    assert res.code == 1
    found = hits(res, "/artefacts/0")
    assert found, res.findings
    assert any("sha256" in f["message"] for f in found)
    assert all("a2-haul-clip" in f["message"] and len(f["message"]) <= 300 for f in found)
    assert hits(res, "/artefacts/1") == []


@pytest.mark.req("FR-001-20")
def test_fr_001_20_a_different_size_is_reported(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    (root / VIDEO).write_bytes((root / VIDEO).read_bytes() + b"x")
    found = hits(cs.run_checker(root), "/artefacts/0")
    assert any("bytes" in f["message"] for f in found)


@pytest.mark.req("FR-001-20")
@pytest.mark.parametrize(("field", "value", "token"), [("bytes", None, "bytes"), ("sha256", "0" * 64, "sha256")])
def test_fr_001_20_a_wrong_index_entry_is_reported_even_when_the_file_is_untouched(
    tmp_path: Path, field: str, value: Any, token: str
) -> None:
    root = cs.clean_repo(tmp_path)

    def edit(doc: dict) -> None:
        art = doc["artefacts"][0]
        art[field] = art["bytes"] + 1 if field == "bytes" else value

    cs.edit_json(root, INDEX, edit)
    found = hits(cs.run_checker(root), "/artefacts/0")
    assert found
    assert any(token in f["message"] for f in found)


@pytest.mark.req("FR-001-20")
def test_fr_001_20_a_missing_file_or_a_directory_in_its_place_is_a_finding_not_a_traceback(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path / "a")
    (root / VIDEO).unlink()
    res = cs.run_checker(root)
    assert hits(res, "/artefacts/0")
    assert "Traceback" not in res.stderr
    root2 = cs.clean_repo(tmp_path / "b")
    (root2 / VIDEO).unlink()
    (root2 / VIDEO).mkdir()
    res2 = cs.run_checker(root2)
    assert hits(res2, "/artefacts/0")
    assert "Traceback" not in res2.stderr


@pytest.mark.req("FR-001-20")
def test_fr_001_20_an_empty_served_file_is_checked_like_any_other(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    (root / REPORT).write_bytes(b"")
    assert hits(cs.run_checker(root), "/artefacts/1")  # index still lists the old digest and size
    cs.refresh_served(root)
    assert hits(cs.run_checker(root), "/artefacts/1") == []  # sha256 of 0 bytes is e3b0c442...; 0 bytes
    index = json.loads((root / INDEX).read_text(encoding="utf-8"))
    assert index["artefacts"][1]["sha256"] == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.mark.req("FR-001-20")
def test_fr_001_20_published_run_manifest_digest_listed_in_the_index_is_checked(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    cs.edit_json(root, RUN_MANIFEST, lambda d: d.update(notes=["a changed note"]))
    res = cs.run_checker(root)
    assert hits(res, "/runs/0"), res.findings


def release_repo(tmp: Path, payload: bytes, *, sha: str | None = None, nbytes: int | None = None) -> tuple[Path, Path]:
    root = cs.clean_repo(tmp)
    assets = tmp / "release-assets"
    assets.mkdir()
    (assets / "a2-dispatch-policy.onnx").write_bytes(payload)
    template = json.loads((cs.FIXTURES / "manifest/valid/manifest.valid-web-index.json").read_text(encoding="utf-8"))
    art = copy.deepcopy(template["artefacts"][0])
    art["inputs"] = [{"id": "example-haul-network", "sha256": "2" * 64, "kind": "source"}]
    art["sha256"] = sha or cs.sha256_hex(payload)
    art["bytes"] = len(payload) if nbytes is None else nbytes
    art["lane_measurements"]["max_asset_bytes"] = len(payload)
    cs.edit_json(root, INDEX, lambda d: d["artefacts"].append(art))
    return root, assets


@pytest.mark.req("FR-001-20")
def test_fr_001_20_release_assets_are_checked_against_the_downloaded_files(tmp_path: Path) -> None:
    root, assets = release_repo(tmp_path / "ok", MODEL)
    assert hits(cs.run_checker(root, "--release-assets", str(assets)), "/artefacts/2") == []
    root, assets = release_repo(tmp_path / "bad-sha", MODEL, sha="f" * 64)
    found = hits(cs.run_checker(root, "--release-assets", str(assets)), "/artefacts/2")
    assert found
    assert any("sha256" in f["message"] for f in found)
    assert all("a2-dispatch-policy" in f["message"] for f in found)
    root, assets = release_repo(tmp_path / "bad-size", MODEL, nbytes=len(MODEL) + 1)
    found = hits(cs.run_checker(root, "--release-assets", str(assets)), "/artefacts/2")
    assert found
    assert any("bytes" in f["message"] for f in found)


@pytest.mark.req("FR-001-20")
def test_fr_001_20_a_release_asset_missing_from_the_download_folder_is_a_finding(tmp_path: Path) -> None:
    root, assets = release_repo(tmp_path, MODEL)
    (assets / "a2-dispatch-policy.onnx").unlink()
    assert hits(cs.run_checker(root, "--release-assets", str(assets)), "/artefacts/2")


@pytest.mark.req("FR-001-20")
def test_fr_001_20_release_hosted_files_are_not_expected_in_the_repository_checkout(tmp_path: Path) -> None:
    root, _ = release_repo(tmp_path, MODEL, sha="f" * 64)  # wrong digest, but no download folder given
    assert hits(cs.run_checker(root), "/artefacts/2") == []


@pytest.mark.req("FR-001-20")
def test_fr_001_20_the_git_hosted_check_also_runs_when_release_assets_are_given(tmp_path: Path) -> None:
    root, assets = release_repo(tmp_path, MODEL)
    (root / VIDEO).write_bytes(b"tampered")
    assert hits(cs.run_checker(root, "--release-assets", str(assets)), "/artefacts/0")


@pytest.mark.req("FR-001-20")
def test_fr_001_20_pages_workflow_runs_the_check_before_the_upload() -> None:
    wf = yaml.safe_load((cs.ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8"))
    steps = wf["jobs"]["build"]["steps"]
    check = [i for i, s in enumerate(steps) if "check_contracts.py" in str(s.get("run", ""))]
    upload = [i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/upload-pages-artifact")]
    assert check, "pages.yml must run tools/check_contracts.py"
    assert upload, "pages.yml must upload the Pages artifact"
    assert check[0] < upload[0], "the digest check must stop the build before the upload"
    step = steps[check[0]]
    assert "--release-assets" in step["run"]
    assert step.get("continue-on-error") in (None, False)

"""T-001-093 · privacy scan of the ``notes`` and ``error`` text of ``capabilities.json``: FR-001-59.

Oracles: the absolute-path rules and the machine-identity rule of data-model 1.5 applied by hand (a Windows drive path,
a POSIX home path, a UNC path, ``file:/``; the host name, user name and home directory of the checking process,
case-insensitively and only when at least 3 characters); the plan's three fixtures (drive path rejected, a POSIX home
path rejected, clean note accepted); the scrubbed forms ``<repo>`` and ``~`` the bench itself writes stay allowed.

Machine-path strings are assembled at run time so ``tools/check_repo.py`` does not flag this file.

Expected API: ``tools/check_contracts.py`` reports ``rule: FR-001-59`` with ``error_class: "privacy-leak"`` and the JSON
pointer of the string (``/probes/<name>/notes/<i>`` or ``/probes/<name>/error``).
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contract"))
import contract_support as cs

CAP = "studio/capabilities.json"
DRIVE = "C" + ":\\"
USER, HOMEDIR = "zq9user", "zq9homedir"
IDENTITY_ENV = {"USER": USER, "USERNAME": USER, "LOGNAME": USER, "LNAME": USER, "HOME": HOMEDIR, "USERPROFILE": HOMEDIR}

FLAGGED = [
    "wrote " + DRIVE + "work\\run.csv",
    "z:/tmp/out.bin",
    "/ho" + "me/x/y",
    "see /ho" + "me/alex/run for details",
    "\\\\" + "fileserver\\share\\x",
    "file:///x/y",
    "log='/var/log/x'",
    "(/opt/tool/bin)",
    "/Us" + "ers/alex/data",
]
CLEAN = [
    "probe script not written yet",
    "see <repo>\\studio\\bench",
    "see <repo>/studio/bench",
    "FileNotFoundError: ~\\Data\\x.onnx",
    "FileNotFoundError: ~/Data/x.onnx",
    "ratio 3/4 at 12:30",
    "a" + "/ho" + "me/b",
]


def write_capabilities(root: Path, notes: list[str], errors: list[str]) -> None:
    doc = {
        "$schema": "../contracts/capabilities.schema.json",
        "generated": "2026-10-07",
        "gpu": "GPU",
        "driver": "582.78",
        "probes": {"carrier": {"status": "pass", "versions": {}, "notes": notes}},
    }
    for i, text in enumerate(errors):
        doc["probes"][f"p{i}"] = {"status": "fail", "versions": {}, "error": text}
    cs.write_file(root, CAP, doc)


def leaks(res: cs.CheckResult) -> dict[str, dict]:
    return {f["pointer"]: f for f in res.of("FR-001-59") if f["file"] == CAP}


@pytest.mark.req("FR-001-59")
def test_fr_001_59_absolute_paths_in_notes_and_error_text_are_rejected_with_the_error_class_and_pointer(
    tmp_path: Path,
) -> None:
    root = cs.clean_repo(tmp_path)
    write_capabilities(root, FLAGGED, FLAGGED)
    res = cs.run_checker(root)
    assert res.code == 1
    found = leaks(res)
    for i in range(len(FLAGGED)):
        for pointer in (f"/probes/carrier/notes/{i}", f"/probes/p{i}/error"):
            assert pointer in found, (pointer, FLAGGED[i])
            assert found[pointer]["error_class"] == "privacy-leak"
            assert len(found[pointer]["message"]) <= 300


@pytest.mark.req("FR-001-59")
def test_fr_001_59_clean_and_scrubbed_text_is_accepted(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    write_capabilities(root, CLEAN, CLEAN)
    res = cs.run_checker(root)
    assert leaks(res) == {}, res.findings
    assert res.code == 0, res.findings


@pytest.mark.req("FR-001-59")
def test_fr_001_59_the_plan_fixtures_drive_path_rejected_posix_home_path_rejected_clean_note_accepted(
    tmp_path: Path,
) -> None:
    root = cs.clean_repo(tmp_path)
    write_capabilities(root, [DRIVE + "data\\x.bin", "/ho" + "me/x/y", "a clean note"], [])
    found = leaks(cs.run_checker(root))
    assert "/probes/carrier/notes/0" in found
    assert "/probes/carrier/notes/1" in found
    assert "/probes/carrier/notes/2" not in found


@pytest.mark.req("FR-001-59")
def test_fr_001_59_the_committed_report_and_the_clean_fixture_report_pass(tmp_path: Path) -> None:
    res = cs.run_checker(cs.clean_repo(tmp_path))
    assert leaks(res) == {}


@pytest.mark.req("FR-001-59")
def test_fr_001_59_host_user_and_home_directory_are_flagged_case_insensitively(tmp_path: Path) -> None:
    host = socket.gethostname()
    assert len(host) >= 3
    texts = [
        f"ran on {host}",
        f"RAN ON {host.upper()}",
        f"owner {USER}",
        f"OWNER {USER.upper()}",
        f"under {HOMEDIR}/data",
        "nothing personal",
    ]
    root = cs.clean_repo(tmp_path)
    write_capabilities(root, texts, texts)
    found = leaks(cs.run_checker(root, env=IDENTITY_ENV))
    for i in range(5):
        assert f"/probes/carrier/notes/{i}" in found, texts[i]
        assert f"/probes/p{i}/error" in found, texts[i]
    assert "/probes/carrier/notes/5" not in found
    assert "/probes/p5/error" not in found


@pytest.mark.req("FR-001-59")
def test_fr_001_59_identity_shorter_than_three_characters_does_not_apply(tmp_path: Path) -> None:
    short = {"USER": "ab", "USERNAME": "ab", "LOGNAME": "ab", "LNAME": "ab", "HOME": "hm", "USERPROFILE": "hm"}
    root = cs.clean_repo(tmp_path)
    write_capabilities(root, ["owner ab", "files in hm"], ["by ab"])
    assert leaks(cs.run_checker(root, env=short)) == {}


@pytest.mark.req("FR-001-59")
def test_fr_001_59_the_corpus_fixtures_are_flagged_at_their_pointer(tmp_path: Path) -> None:
    items = cs.entries(schema="capabilities", rule="FR-001-59", tag_in=("cross-file",))
    assert len(items) >= 2
    for e in items:
        root = cs.clean_repo(tmp_path / e["file"].split("/")[-1])
        cs.write_file(root, CAP, cs.fixture_json(e))
        found = leaks(cs.run_checker(root))
        assert e["pointer"] in found, e["file"]
        assert found[e["pointer"]]["error_class"] == "privacy-leak"

"""T-001-013 · privacy scan of every string of the committed manifests: FR-001-15.

Oracles: the absolute-path rules of data-model 1.5 (drive letter, UNC, POSIX root, ``file:/``) and the machine-identity
rule (host name, user name, home directory of the checking process, case-insensitive, only when >= 3 characters),
applied by hand to a table of strings; reference values for the identity are ``socket.gethostname()`` and the
environment variables the checker subprocess is started with (``USER``/``USERNAME``/``LOGNAME`` for the user name,
``HOME``/``USERPROFILE`` for the home directory). Scrubbed forms ``<repo>/...`` and ``~/...`` are allowed.

Strings that look like machine paths are assembled at run time so that ``tools/check_repo.py`` does not flag this file.

Expected API: ``tools/check_contracts.py`` reports ``rule: FR-001-15`` findings with ``file`` (repository-relative,
POSIX separators) and ``pointer`` = the JSON pointer of the offending string; ``contracts/manifest.schema.json``
defines no field for a host name, user name or absolute path.
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_support as cs

DRIVE = "C" + ":\\"  # a drive-letter root, built so the literal never sits in this file
POSIX_HOME = "/ho" + "me/"
POSIX_USERS = "/Us" + "ers/"
RUN_GLOB = "web/public/assets/runs"
INDEX = "web/public/assets/manifest.json"
USER = "zq9user"
HOMEDIR = "zq9homedir"
IDENTITY_ENV = {
    "USER": USER,
    "USERNAME": USER,
    "LOGNAME": USER,
    "LNAME": USER,
    "HOME": HOMEDIR,
    "USERPROFILE": HOMEDIR,
}

# (string, flagged?) written from data-model 1.5 by hand
FLAGGED = [
    DRIVE + "work\\data\\a.csv",
    "z:/tmp/out.bin",
    "wrote D" + ":\\logs\\run.txt and left",
    "out=E" + ":/cache/x",
    "\\\\" + "fileserver\\share\\x",
    "\\\\" + "nas.local$\\a",
    POSIX_HOME + "alex/run",
    POSIX_USERS + "alex/run",
    "wrote /tmp/out.bin",
    "log='/var/log/x'",
    "(/opt/tool/bin)",
    "a,/mnt/disk/x",
    "x:/root/y",
    "see /srv/data/a",
    "/private/var/x",
    '"/run/user/1/x"',
    "file:///x/y",
    "file:/x",
    "mixed " + "/ho" + "me/u/x and <repo>/ok",
]
CLEAN = [
    "<repo>/studio/recipes/cases/a2.yaml",
    "~/Data/x",
    "~\\Data\\x",
    "ratio 3/4 and 12:30",
    "a" + POSIX_HOME + "b",  # '/home/' not at a word boundary of the rule
    "usr" + POSIX_HOME + "x",
    "/homework/x",
    "/tmpfile/x",
    "a/tmp/b",
    "time: 10:15:20",
    "a:b",
    "key:value",
    "scrubbed note: outputs under <repo>/runs/",
    "unicode \u00e9\u00f1\u4e2d\u6587 text",
]


def run_manifest_rel(root: Path) -> str:
    return next(p.relative_to(root).as_posix() for p in (root / RUN_GLOB).glob("*/manifest.json"))


def with_notes(root: Path, rel: str, notes: list[str]) -> None:
    cs.edit_json(root, rel, lambda d: d.update(notes=notes))


def findings_for(res: cs.CheckResult, rel: str) -> dict[str, dict]:
    return {f["pointer"]: f for f in res.of("FR-001-15") if f["file"] == rel}


@pytest.mark.req("FR-001-15")
def test_fr_001_15_absolute_path_strings_are_flagged_at_their_pointer(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    rel = run_manifest_rel(root)
    batch = FLAGGED[:18]  # a manifest holds at most 20 notes
    with_notes(root, rel, batch)
    res = cs.run_checker(root)
    assert res.code == 1
    got = findings_for(res, rel)
    for i, text in enumerate(batch):
        assert f"/notes/{i}" in got, (i, text)
        assert len(got[f"/notes/{i}"]["message"]) <= 300
    with_notes(root, rel, FLAGGED[18:])
    got = findings_for(cs.run_checker(root), rel)
    assert "/notes/0" in got


@pytest.mark.req("FR-001-15")
def test_fr_001_15_scrubbed_and_innocent_strings_are_not_flagged(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    rel = run_manifest_rel(root)
    with_notes(root, rel, CLEAN)
    cs.refresh_served(root)  # the index lists the digest of the run manifest that was just edited
    res = cs.run_checker(root)
    assert res.of("FR-001-15") == [], [f for f in res.of("FR-001-15")]
    assert res.code == 0, res.findings


@pytest.mark.req("FR-001-15")
def test_fr_001_15_the_scan_covers_every_string_of_the_manifest_not_only_notes(tmp_path: Path) -> None:
    leak = DRIVE + "secret\\f.bin"
    cases = {
        "/gpu/name": lambda d: (
            d["gpu"].update(name=leak)
            if d["gpu"]
            else d.update(
                gpu={
                    "backend": "nvml",
                    "index": 0,
                    "name": leak,
                    "driver": "582.78",
                    "vram_total_bytes": 1,
                    "power_limit_enforced_w": None,
                }
            )
        ),
        "/stages/0/params/note": lambda d: d["stages"][0]["params"].update(note=leak),
        "/artefacts/0/attribution": lambda d: d["artefacts"][0].update(attribution=leak, licence_class="attribution"),
        "/stages/0/log_tail": lambda d: d["stages"][0].update(
            status="failed", error_class="oom", exit_code=1, log_tail=leak
        ),
        "/stages/0/reason": lambda d: d["stages"][0].update(status="skipped", error_class=None, reason=leak),
    }
    for pointer, mutate in cases.items():
        root = cs.clean_repo(tmp_path / pointer.strip("/").replace("/", "_"))
        rel = run_manifest_rel(root)
        cs.edit_json(root, rel, mutate)
        res = cs.run_checker(root)
        assert pointer in findings_for(res, rel), (pointer, res.findings)


@pytest.mark.req("FR-001-15")
def test_fr_001_15_the_web_index_and_model_card_manifests_are_scanned_too(tmp_path: Path) -> None:
    leak = DRIVE + "secret\\f.bin"
    root = cs.clean_repo(tmp_path)
    cs.edit_json(root, INDEX, lambda d: d["artefacts"][0].update(attribution=leak))
    res = cs.run_checker(root)
    assert "/artefacts/0/attribution" in findings_for(res, INDEX)
    # a published model card manifest (models/cards/*/manifest.json) is a committed manifest as well
    card = "models/cards/surrogate-a2/manifest.json"
    run = json.loads((root / run_manifest_rel(root)).read_text(encoding="utf-8"))
    run["notes"] = [leak]
    cs.write_file(root, card, run)
    assert "/notes/0" in findings_for(cs.run_checker(root), card)


@pytest.mark.req("FR-001-15")
def test_fr_001_15_the_corpus_fixture_with_an_absolute_path_note_is_flagged(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    fixture = next(e for e in cs.entries(rule="FR-001-15", tag_in=("cross-file",)))
    rel = run_manifest_rel(root)
    cs.write_file(root, rel, cs.fixture_json(fixture))
    assert fixture["pointer"] in findings_for(cs.run_checker(root), rel)


@pytest.mark.req("FR-001-15")
def test_fr_001_15_machine_identity_host_user_and_home_are_flagged_case_insensitively(tmp_path: Path) -> None:
    host = socket.gethostname()
    assert len(host) >= 3, "the reference host name must be long enough for the rule to apply"
    notes = [
        f"built on {host}",
        f"built on {host.upper()}",
        f"built on {host.lower()}",
        f"owner {USER}",
        f"OWNER {USER.upper()}",
        f"files in {HOMEDIR} are private",
        f"{HOMEDIR.title()}/data",
        "nothing personal here",
    ]
    root = cs.clean_repo(tmp_path)
    rel = run_manifest_rel(root)
    with_notes(root, rel, notes)
    got = findings_for(cs.run_checker(root, env=IDENTITY_ENV), rel)
    for i in range(7):
        assert f"/notes/{i}" in got, (i, notes[i])
    assert "/notes/7" not in got


@pytest.mark.req("FR-001-15")
def test_fr_001_15_identity_shorter_than_three_characters_is_ignored(tmp_path: Path) -> None:
    short = {"USER": "ab", "USERNAME": "ab", "LOGNAME": "ab", "LNAME": "ab", "HOME": "hm", "USERPROFILE": "hm"}
    root = cs.clean_repo(tmp_path)
    rel = run_manifest_rel(root)
    with_notes(root, rel, ["owner ab", "AB wrote this in hm", "three: abc"])
    res = cs.run_checker(root, env=short)
    got = findings_for(res, rel)
    assert "/notes/0" not in got
    assert "/notes/1" not in got
    long_user = {**short, "USER": "abc", "USERNAME": "abc", "LOGNAME": "abc", "LNAME": "abc"}
    assert "/notes/2" in findings_for(cs.run_checker(root, env=long_user), rel)  # exactly 3 characters applies


@pytest.mark.req("FR-001-15")
def test_fr_001_15_clean_manifests_pass_the_scan(tmp_path: Path) -> None:
    res = cs.run_checker(cs.clean_repo(tmp_path), env=IDENTITY_ENV)
    assert res.of("FR-001-15") == []


@pytest.mark.req("FR-001-15")
def test_fr_001_15_manifest_schema_defines_no_host_user_home_or_absolute_path_field() -> None:
    banned = {
        "host",
        "hostname",
        "host_name",
        "user",
        "username",
        "user_name",
        "home",
        "home_dir",
        "homedir",
        "abs_path",
        "absolute_path",
        "machine",
        "cwd",
        "working_dir",
        "computer",
        "node_name",
    }
    names: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            names.update(k.lower() for k in node.get("properties", {}))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(cs.load_schema("manifest"))
    assert {"id", "path", "sha256"} <= names  # the walk reached the artefact record
    assert names & banned == set()


@pytest.mark.req("FR-001-15")
def test_fr_001_15_unknown_host_name_field_fails_validation_in_both_document_kinds() -> None:
    items = [e for e in cs.schema_level(schema="manifest") if e["rule"] == "FR-001-15"]
    assert {e["kind"] for e in items} == {"run", "web-index"}
    for e in items:
        assert (e["pointer"], e["keyword"]) in cs.error_pairs("manifest", e["target"], cs.fixture_json(e))

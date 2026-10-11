"""T-001-030 · ``tools/check_contracts.py``: discovery, exit codes, findings without tracebacks, scale, CI: FR-001-50,
FR-001-51, NFR-001-01, SC-001-01.

Oracles: the document globs of data-model 8.1 (hand-copied below), the exit-code contract (0 clean, 1 findings, 2
usage error), the committed clean fixture repository (every rule satisfied) and seeded broken copies of it, a scale
fixture of 2,000 artefacts and 64 recipes generated here with ``hashlib`` digests, and ``time.perf_counter`` for the
30 s bound (``thresholds.yaml`` ``contracts.check_runtime_s_max``).

Expected API: see ``contract_support``: ``--root DIR`` (default: the repository), ``--json`` (list of findings with
``file``, ``rule``, ``pointer``, ``message``, ``error_class``), exit 0 / 1 / 2, no Python traceback on any input.
Files inside ``contracts/`` other than ``*.schema.json`` and ``README.md``, and files under ``studio/recipes/`` or
``web/public/assets/runs/`` that match no glob of data-model 8.1, are findings (FR-001-51).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contract"))
import contract_support as cs

RUN_ID = "20261007T120000Z-a2-haulage"
RUN_REL = f"web/public/assets/runs/{RUN_ID}/manifest.json"
INDEX = "web/public/assets/manifest.json"


def raw_run(root: Path | None, *args: str) -> subprocess.CompletedProcess[str]:
    assert cs.CHECKER.is_file(), "tools/check_contracts.py does not exist"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(cs.ROOT / "src"), env.get("PYTHONPATH", "")]))
    cmd = [sys.executable, str(cs.CHECKER), *([] if root is None else ["--root", str(root)]), *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=cs.ROOT, timeout=300
    )


# ----------------------------------------------------------------------------------------------------------------
# FR-001-50 · exit codes and the committed repository
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-50")
def test_fr_001_50_the_clean_fixture_repository_exits_0_with_no_findings(tmp_path: Path) -> None:
    res = cs.run_checker(cs.clean_repo(tmp_path))
    assert res.code == 0, res.findings
    assert res.findings == []
    assert "Traceback" not in res.stderr


@pytest.mark.req("FR-001-50")
@pytest.mark.req("SC-001-01")
def test_sc_001_01_the_repository_itself_passes_the_contract_check() -> None:
    proc = raw_run(None, "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout) == []
    assert "Traceback" not in proc.stderr


@pytest.mark.req("FR-001-50")
def test_fr_001_50_findings_exit_1_and_each_has_file_rule_pointer_and_a_bounded_message(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    cs.edit_json(root, "studio/capabilities.json", lambda d: d.update(driver="v582"))
    res = cs.run_checker(root)
    assert res.code == 1
    assert res.findings
    for f in res.findings:
        assert set(f) >= {"file", "rule", "pointer", "message", "error_class"}
        assert isinstance(f["file"], str)
        assert "\\" not in f["file"]
        assert not os.path.isabs(f["file"])
        assert isinstance(f["rule"], str)
        assert f["rule"]
        assert isinstance(f["message"], str)
        assert 0 < len(f["message"]) <= 300
        assert not cs.has_absolute_path(f["message"]), f["message"]
    assert any(f["file"] == "studio/capabilities.json" and f["pointer"] == "/driver" for f in res.findings)


@pytest.mark.req("FR-001-50")
def test_fr_001_50_plain_output_names_the_file_the_rule_and_the_message(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    cs.edit_json(root, "studio/capabilities.json", lambda d: d.update(driver="v582"))
    proc = raw_run(root)
    assert proc.returncode == 1
    assert "studio/capabilities.json" in proc.stdout
    assert "/driver" in proc.stdout
    assert "Traceback" not in proc.stdout + proc.stderr


@pytest.mark.req("FR-001-50")
def test_fr_001_50_usage_errors_exit_2_without_a_traceback(tmp_path: Path) -> None:
    for args, root in (
        (("--no-such-flag",), cs.clean_repo(tmp_path / "a")),
        (("--root",), None),
        (("--release-assets", str(tmp_path / "missing")), cs.clean_repo(tmp_path / "b")),
        (("extra-positional",), cs.clean_repo(tmp_path / "c")),
    ):
        proc = raw_run(root, *args)
        assert proc.returncode == 2, (args, proc.stdout, proc.stderr)
        assert "Traceback" not in proc.stderr, args
    for bad_root in (tmp_path / "does-not-exist", tmp_path / "a-file.txt"):
        if bad_root.suffix:
            bad_root.write_text("x", encoding="utf-8")
        proc = raw_run(bad_root, "--json")
        assert proc.returncode == 2, (bad_root, proc.stdout, proc.stderr)
        assert "Traceback" not in proc.stderr


@pytest.mark.req("FR-001-50")
def test_fr_001_50_help_exits_0_and_names_the_options() -> None:
    proc = raw_run(None, "--help")
    assert proc.returncode == 0
    assert "--root" in proc.stdout
    assert "--json" in proc.stdout
    assert "--release-assets" in proc.stdout


@pytest.mark.req("FR-001-50")
def test_fr_001_50_output_is_deterministic(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    cs.edit_json(root, "studio/capabilities.json", lambda d: d.update(driver="v582", gpu="g" * 200))
    cs.edit_yaml(root, "data/sources.yaml", lambda d: d["sources"][0].update(access="ftp"))
    first = cs.run_checker(root)
    second = cs.run_checker(root)
    assert first.stdout == second.stdout
    assert first.findings


# document -> (relative path, how to break it; the JSON pointer the schema finding must carry)
def break_tools(d: dict) -> None:
    d["tools"][0]["version"] = "1.2.3"


def break_sources(d: dict) -> None:
    d["sources"][0]["access"] = "ftp"


def break_recipe(d: dict) -> None:
    d["seed"] = -1


def break_caps(d: dict) -> None:
    d["driver"] = "v582"


def break_index(d: dict) -> None:
    d["generated"] = "2026-10-07T00:00:00Z"


def break_run(d: dict) -> None:
    d["seed"] = -1


DISCOVERY = [
    ("studio/tools.yaml", "yaml", break_tools, "/tools/0/version"),
    ("data/sources.yaml", "yaml", break_sources, "/sources/0/access"),
    ("studio/recipes/cases/a2-haulage.yaml", "yaml", break_recipe, "/seed"),
    ("studio/recipes/_bench/bench-smoke.yaml", "yaml", break_recipe, "/seed"),
    ("studio/capabilities.json", "json", break_caps, "/driver"),
    (INDEX, "json", break_index, "/generated"),
    (RUN_REL, "json", break_run, "/seed"),
    ("models/cards/surrogate-a2/manifest.json", "json", break_run, "/seed"),
]


@pytest.mark.req("FR-001-50")
@pytest.mark.parametrize(("rel", "fmt", "breaker", "pointer"), DISCOVERY, ids=[d[0] for d in DISCOVERY])
def test_fr_001_50_every_document_of_data_model_8_1_is_discovered_and_validated(
    tmp_path: Path, rel: str, fmt: str, breaker: Any, pointer: str
) -> None:
    root = cs.clean_repo(tmp_path)
    if rel.startswith("models/cards/"):
        cs.write_file(root, rel, json.loads((root / RUN_REL).read_text(encoding="utf-8")))
    (cs.edit_yaml if fmt == "yaml" else cs.edit_json)(root, rel, breaker)
    res = cs.run_checker(root)
    assert res.code == 1
    assert res.in_file(rel, pointer), (rel, res.findings)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-51 · unreadable, malformed, out-of-repository symlinks and unknown files are findings, never tracebacks
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-51")
@pytest.mark.parametrize(
    ("rel", "content"),
    [
        ("studio/capabilities.json", b'{"generated": "2026-10-07", "gpu": '),
        ("studio/capabilities.json", b"\xef\xbb\xbf{}"),
        ("studio/capabilities.json", b'{"a": NaN}'),
        ("studio/capabilities.json", b'{"a": 1, "a": 2}'),
        ("studio/capabilities.json", b"\xff\xfe\x00"),
        ("studio/capabilities.json", b""),
        ("data/sources.yaml", b"sources: [\n"),
        ("data/sources.yaml", b"sources: &a []\nagain: *a\n"),
        ("data/sources.yaml", b"sources: []\n---\nsources: []\n"),
        ("studio/tools.yaml", b"tools: !!python/object/apply:os.system ['x']\n"),
        ("studio/recipes/cases/a2-haulage.yaml", b"id: a\nid: b\n"),
        (INDEX, b"[1, 2"),
        (RUN_REL, b'{"kind": "run"}' + b"\x00"),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_fr_001_51_a_malformed_document_is_a_finding_for_that_file_and_the_run_continues(
    tmp_path: Path, rel: str, content: bytes
) -> None:
    root = cs.clean_repo(tmp_path)
    (root / rel).write_bytes(content)
    if rel != "data/sources.yaml":
        other = "data/sources.yaml"
        cs.edit_yaml(root, other, lambda d: d.update(sources=[{"id": "A"}]))
    else:
        other = "studio/capabilities.json"
        cs.edit_json(root, other, lambda d: d.update(driver="v582"))
    res = cs.run_checker(root)
    assert res.code == 1
    assert "Traceback" not in res.stderr
    mine = res.in_file(rel)
    assert mine, res.findings
    assert all(len(f["message"]) <= 300 and f["rule"] for f in mine)
    assert res.in_file(other), "the other broken file is still checked after the first failure"


@pytest.mark.req("FR-001-51")
def test_fr_001_51_a_directory_where_a_document_should_be_is_a_finding(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    (root / "studio/capabilities.json").unlink()
    (root / "studio/capabilities.json").mkdir()
    res = cs.run_checker(root)
    assert res.code == 1
    assert "Traceback" not in res.stderr
    assert res.in_file("studio/capabilities.json")


def make_dir_link(link: Path, target: Path) -> None:
    """A directory symbolic link, or a junction on Windows when symlinks need privileges."""
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


@pytest.mark.req("FR-001-51")
def test_fr_001_51_a_manifest_reached_through_a_link_that_leaves_the_repository_is_a_finding(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "manifest.json").write_text((root / RUN_REL).read_text(encoding="utf-8"), encoding="utf-8")
    link = root / "web/public/assets/runs" / "20261008T080000Z-evil"
    make_dir_link(link, outside)
    res = cs.run_checker(root)
    assert res.code == 1
    assert "Traceback" not in res.stderr
    hits = res.in_file("web/public/assets/runs/20261008T080000Z-evil/manifest.json")
    assert hits, res.findings
    assert all(len(f["message"]) <= 300 for f in hits)


@pytest.mark.req("FR-001-51")
@pytest.mark.parametrize(
    "rel",
    [
        "contracts/stray.txt",
        "contracts/notes.json",
        "studio/recipes/notes.txt",
        "studio/recipes/cases/readme.md",
        "studio/recipes/_bench/extra.json",
        "web/public/assets/runs/stray.json",
        f"web/public/assets/runs/{RUN_ID}/readme.md",
    ],
)
def test_fr_001_51_unknown_files_in_the_contract_folders_are_findings(tmp_path: Path, rel: str) -> None:
    root = cs.clean_repo(tmp_path)
    cs.write_file(root, rel, "unexpected\n")
    res = cs.run_checker(root)
    assert res.code == 1
    assert "Traceback" not in res.stderr
    hits = res.in_file(rel)
    assert hits, res.findings
    assert all(len(f["message"]) <= 300 for f in hits)


@pytest.mark.req("FR-001-51")
def test_fr_001_51_the_schemas_and_the_readme_of_contracts_are_not_unknown_files(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    for stem in cs.SCHEMA_STEMS:
        cs.write_file(
            root, f"contracts/{stem}.schema.json", (cs.CONTRACTS / f"{stem}.schema.json").read_text(encoding="utf-8")
        )
    cs.write_file(root, "contracts/README.md", "# contracts\n")
    res = cs.run_checker(root)
    assert res.in_file("contracts") == [], res.findings
    assert res.code == 0


@pytest.mark.req("FR-001-51")
def test_fr_001_51_an_empty_repository_is_clean_and_missing_optional_documents_are_not_findings(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    res = cs.run_checker(tmp_path / "empty")
    assert res.code == 0
    assert res.findings == []


# ----------------------------------------------------------------------------------------------------------------
# NFR-001-01 · the scale fixture: 2,000 published artefacts and 64 recipes in at most 30 s
# ----------------------------------------------------------------------------------------------------------------
GIT_HOSTED = 200  # file opens are slow where a virus scanner watches the working folder; the checker reads only these


def build_scale_repo(tmp: Path) -> Path:
    root = cs.clean_repo(tmp)
    base = json.loads((root / INDEX).read_text(encoding="utf-8"))
    template = copy.deepcopy(base["artefacts"][1])  # the static table artefact (class own, no inputs)
    artefacts = []
    for i in range(2000):
        a = copy.deepcopy(template)
        if i < GIT_HOSTED:  # a git-hosted file is read and hashed by the checker; the rest sit on the release host
            payload = f"artefact {i}\n".encode()
            rel = f"assets/media/scale-{i:04d}.json"
            (root / "web/public" / rel).write_bytes(payload)
            a.update(path=rel, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        else:
            a.update(path=f"scale-{i:04d}.json", asset_host="release", release_tag="assets-v1.00.001")
        a.update(id=f"scale-{i:04d}")
        artefacts.append(a)
    base["artefacts"] = artefacts
    (root / INDEX).write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8", newline="\n")
    recipe = yaml.safe_load((root / "studio/recipes/cases/a2-haulage.yaml").read_text(encoding="utf-8"))
    for i in range(64):
        r = copy.deepcopy(recipe)
        r["id"] = f"scale-{i:02d}"
        (root / f"studio/recipes/cases/scale-{i:02d}.yaml").write_text(
            yaml.safe_dump(r, sort_keys=False), encoding="utf-8"
        )
    return root


@pytest.mark.req("NFR-001-01")
def test_nfr_001_01_two_thousand_artefacts_and_64_recipes_are_checked_within_30_seconds(tmp_path: Path) -> None:
    root = build_scale_repo(tmp_path)
    t0 = time.perf_counter()
    res = cs.run_checker(root)
    elapsed = time.perf_counter() - t0
    assert res.code == 0, res.findings[:3]
    assert res.findings == []
    assert elapsed <= 30.0, f"{elapsed:.1f} s"  # thresholds.yaml contracts.check_runtime_s_max


# ----------------------------------------------------------------------------------------------------------------
# CI wiring (SC-001-01)
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("SC-001-01")
@pytest.mark.req("FR-001-50")
def test_sc_001_01_the_python_ci_job_runs_the_contract_check() -> None:
    wf = yaml.safe_load((cs.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = wf["jobs"]["python"]["steps"]
    runs = [str(s.get("run", "")) for s in steps]
    assert any("tools/check_contracts.py" in r for r in runs), "ci.yml python job must run tools/check_contracts.py"
    step = next(s for s in steps if "tools/check_contracts.py" in str(s.get("run", "")))
    assert step.get("continue-on-error") in (None, False)

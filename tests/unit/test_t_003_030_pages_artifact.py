# ruff: noqa: E501, PT018
"""T-003-030: the Pages-artifact check keeps console code out of the public site (US-003-4).

Requirement: FR-003-24.

Expected product facts (stated for the implementer):
  * `python tools/check_pages_artifact.py [BUILD_DIR]` (default `web/build/client/` of the repository the script lives in) scans every
    file of the Pages artifact and exits 1, printing the path of EVERY offending file, when any file (a) contains the console build
    marker `pitstudio-console-build` (in any file type, text or binary, wherever it sits, also when it straddles a read-chunk
    boundary), (b) lies under a folder named `console`, or (c) is a Python file (`*.py`); it exits 0 for a clean artifact and 2 for a
    usage error (missing or non-directory build folder, unknown option);
  * `.github/workflows/ci.yml` (job `web`) runs it after `pnpm run build`, and `.github/workflows/pages.yml` (job `build`) runs it
    after the build and BEFORE `actions/upload-pages-artifact`.
Oracles: fixture build folders written by hand, seeded with one violation each (the check must fail on each seed and pass on the clean
folder), the workflow files parsed with PyYAML.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "check_pages_artifact.py"
MARKER = "pitstudio-console-build"


def run(tool: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    assert tool.is_file(), "tools/check_pages_artifact.py is missing"
    return subprocess.run(
        [sys.executable, str(tool), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or tool.parent),
        timeout=120,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def clean_build(root: Path) -> Path:
    b = root / "build"
    (b / "assets").mkdir(parents=True)
    (b / "index.html").write_text("<!doctype html><title>PitStudio</title>", encoding="utf-8")
    (b / "assets" / "app.js").write_text("console.log('public site');\n", encoding="utf-8")
    (b / "assets" / "style.css").write_text("body{margin:0}\n", encoding="utf-8")
    (b / "assets" / "model.onnx").write_bytes(bytes(range(256)) * 100)
    (b / "console-notes.txt").write_text("a file merely NAMED like the folder is fine\n", encoding="utf-8")
    (b / "reconsole").mkdir()
    (b / "reconsole" / "x.js").write_text("// folder name only contains the word\n", encoding="utf-8")
    return b


@pytest.mark.req("FR-003-24")
def test_fr_003_24_a_clean_artifact_passes(tmp_path: Path) -> None:
    b = clean_build(tmp_path)
    r = run(TOOL, str(b))
    assert r.returncode == 0, r.stdout + r.stderr


SEEDS = {
    "marker-in-js": ("assets/console-bundle.js", f"/* {MARKER} */ export const x = 1;\n"),
    "marker-in-html": ("index.html", f"<html><!-- {MARKER} --></html>"),
    "marker-in-css": ("assets/style.css", f"/*{MARKER}*/ body{{}}\n"),
    "marker-in-json": ("assets/data.json", f'{{"build": "{MARKER}"}}'),
    "marker-in-binary": ("assets/model.wasm", b"\x00asm\x01\x00\x00\x00" + MARKER.encode() + b"\xff\xfe"),
    "marker-deep": ("a/b/c/d/e/file.txt", f"x{MARKER}y"),
    "marker-in-a-dotfile": (".hidden", MARKER),
    "console-folder-file": ("console/index.html", "<html></html>"),
    "console-folder-nested": ("assets/console/app.js", "1"),
    "console-folder-deep": ("x/y/console/z/w.css", "a{}"),
    "console-folder-empty-file": ("console/empty.txt", ""),
    "python-file": ("serve.py", "print('no')\n"),
    "python-file-nested": ("assets/tools/gen.py", "x = 1\n"),
    "python-file-hidden": (".tools/x.py", "x = 1\n"),
}


@pytest.mark.req("FR-003-24")
@pytest.mark.parametrize("name", sorted(SEEDS))
def test_fr_003_24_each_seeded_violation_fails_the_check_and_names_the_file(tmp_path: Path, name: str) -> None:
    rel, content = SEEDS[name]
    b = clean_build(tmp_path)
    p = b / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")
    r = run(TOOL, str(b))
    assert r.returncode == 1, f"{name}: {r.returncode}\n{r.stdout}{r.stderr}"
    out = (r.stdout + r.stderr).replace("\\", "/")
    assert rel in out, f"the offending file {rel} must be named: {out!r}"


@pytest.mark.req("FR-003-24")
def test_fr_003_24_every_offender_is_named_not_only_the_first(tmp_path: Path) -> None:
    b = clean_build(tmp_path)
    offenders = ["one/marker.txt", "console/two.html", "three.py", "four/deeper/marker.js"]
    for rel in offenders:
        (b / rel).parent.mkdir(parents=True, exist_ok=True)
        (b / rel).write_text(MARKER if "marker" in rel else "x", encoding="utf-8")
    r = run(TOOL, str(b))
    assert r.returncode == 1
    out = (r.stdout + r.stderr).replace("\\", "/")
    for rel in offenders:
        assert rel in out, f"{rel} missing from the report: {out!r}"


@pytest.mark.req("FR-003-24")
@pytest.mark.parametrize(
    "offset",
    [0, 1_048_576 - 10, 1_048_576 - 1, 65_536 - 5, 5_000_000 - len(MARKER)],
    ids=["start", "straddles-1-MiB", "last-byte-of-1-MiB", "straddles-64-KiB", "end-of-5-MB-file"],
)
def test_fr_003_24_a_marker_straddling_a_read_chunk_boundary_is_found_in_a_large_file(
    tmp_path: Path, offset: int
) -> None:
    b = clean_build(tmp_path)
    blob = bytearray(b"A" * 5_000_000)
    blob[offset : offset + len(MARKER)] = MARKER.encode()
    (b / "assets" / "huge.bin").write_bytes(bytes(blob))
    r = run(TOOL, str(b))
    assert r.returncode == 1 and "huge.bin" in r.stdout + r.stderr


@pytest.mark.req("FR-003-24")
def test_fr_003_24_near_miss_markers_and_lookalike_names_are_not_violations(tmp_path: Path) -> None:
    b = clean_build(tmp_path)
    (b / "assets" / "notes.txt").write_text(
        "pitstudio-console-buil and pitstudio-console and console-build and PITSTUDIO-CONSOLE-BUILD", encoding="utf-8"
    )
    (b / "assets" / "python.txt").write_text("import os  # a text file about python\n", encoding="utf-8")
    (b / "assets" / "script.pyc.map").write_text("{}", encoding="utf-8")
    (b / "assets" / "consoles").mkdir()
    (b / "assets" / "consoles" / "a.js").write_text("1", encoding="utf-8")
    r = run(TOOL, str(b))
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.req("FR-003-24")
def test_fr_003_24_usage_errors_exit_2(tmp_path: Path) -> None:
    assert run(TOOL, str(tmp_path / "no-such-dir")).returncode == 2
    f = tmp_path / "a-file"
    f.write_text("x", encoding="utf-8")
    assert run(TOOL, str(f)).returncode == 2
    assert run(TOOL, "--bogus").returncode == 2
    assert run(TOOL, str(clean_build(tmp_path)), "extra").returncode == 2


@pytest.mark.req("FR-003-24")
def test_fr_003_24_the_default_folder_is_web_build_client_of_the_repository_holding_the_script(tmp_path: Path) -> None:
    assert TOOL.is_file(), "tools/check_pages_artifact.py is missing"
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    shutil.copy2(TOOL, repo / "tools" / "check_pages_artifact.py")
    client = repo / "web" / "build" / "client"
    client.mkdir(parents=True)
    (client / "index.html").write_text("<html></html>", encoding="utf-8")
    other = tmp_path / "elsewhere"
    other.mkdir()
    ok = run(repo / "tools" / "check_pages_artifact.py", cwd=other)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    (client / "console").mkdir()
    (client / "console" / "x.html").write_text("x", encoding="utf-8")
    bad = run(repo / "tools" / "check_pages_artifact.py", cwd=other)
    assert bad.returncode == 1 and "console" in (bad.stdout + bad.stderr)
    # the console's own build folder is NOT the Pages artifact: it may hold the marker
    own = repo / "web" / "build" / "console"
    own.mkdir(parents=True)
    (own / "index.html").write_text(MARKER, encoding="utf-8")
    shutil.rmtree(client / "console")
    assert run(repo / "tools" / "check_pages_artifact.py", cwd=other).returncode == 0


# ---- CI wiring ---------------------------------------------------------------------------------------------------------------------------------------
def steps(workflow: str, job: str) -> list[str]:
    doc = yaml.safe_load((ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8"))
    return [str(s.get("run", "")) + " " + str(s.get("uses", "")) for s in doc["jobs"][job]["steps"]]


@pytest.mark.req("FR-003-24")
def test_fr_003_24_ci_runs_the_check_after_the_build() -> None:
    s = steps("ci.yml", "web")
    build = next(i for i, x in enumerate(s) if "pnpm run build" in x)
    check = [i for i, x in enumerate(s) if "check_pages_artifact.py" in x]
    assert check and min(check) > build, "ci.yml web job must run tools/check_pages_artifact.py after `pnpm run build`"


@pytest.mark.req("FR-003-24")
def test_fr_003_24_pages_runs_the_check_before_uploading_the_artifact() -> None:
    s = steps("pages.yml", "build")
    build = next(i for i, x in enumerate(s) if "pnpm run build" in x)
    upload = next(i for i, x in enumerate(s) if "upload-pages-artifact" in x)
    check = [i for i, x in enumerate(s) if "check_pages_artifact.py" in x]
    assert check and build < min(check) < upload, "pages.yml must run the check between the build and the upload"

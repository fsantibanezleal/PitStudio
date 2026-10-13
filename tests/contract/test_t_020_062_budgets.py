"""T-020-062: byte budgets of the built Pages artifact.

Requirements: NFR-020-01 (initial JavaScript of every prerendered route, each dynamic template included, at most
200,000 bytes gzip; the postbuild constant of 200 x 1024 bytes is aligned to 200,000), NFR-020-03 (per-class budgets on
the built artifact, each file assigned through its manifest `budget_class`, unlisted files counting as own code),
NFR-020-04 (equations are rendered at build: the client bundles hold no KaTeX JavaScript, and KaTeX CSS and fonts are
requested only by pages that have equations), NFR-000-01, NFR-000-04, NFR-000-07.

Spec: specs/020-web-knowledge/ (spec.md section 5, section 7.2 on the budget classes and caps; plan.md test strategy
rows NFR-020-01, NFR-020-03, NFR-020-04).

Expected API of the implementation: the budget script `web/scripts/budgets.mjs` and the constant in
`web/scripts/postbuild.mjs`.
  node web/scripts/budgets.mjs --root DIR
      DIR is a built client tree (what `build/client` holds): prerendered pages `<route>/index.html` (and
      `index.html`), scripts and assets next to them, and `assets/manifest.json` (the web manifest:
      `artefacts[{ path, bytes, budget_class }]`, `path` relative to DIR/assets/). It prints one line
      "<rule>: <subject>: <detail>" per violation and exits 0 when there is none, 1 with violations, 2 on a usage
      error or an unreadable root (message, no traceback). Rules: `initial-js` (subject: the route, e.g.
      "studio/tools/warp"), `class-budget` (subject: the class id), `total-budget`, `katex-js` (subject: the script),
      `katex-css` (subject: the page).
  Initial JavaScript of a page = the gzip size of every `.js` file referenced by a `src` or `href` of its HTML; the
  limit is 200,000 bytes inclusive. Class caps in bytes (MB = 10^6): videos 150,000,000; tiles-glb 95,000,000;
  shards-clouds 60,000,000; splats 25,000,000; onnx 80,000,000; runtimes 55,000,000; own-code 10,000,000;
  studio-showcase 25,000,000; total 500,000,000; each cap inclusive. The size of a file is its size on disk; a file
  the manifest does not list, and every file outside `assets/` (scripts, styles, pages, fonts), counts as own code.
  A script is KaTeX JavaScript when its text contains "KaTeX parse error". A page needs KaTeX CSS when its HTML
  contains `class="katex`; it must link a `katex` stylesheet exactly then.

Oracles: byte arithmetic on files built here (gzip sizes measured on the produced files with Node's zlib, sizes at
the cap and one byte over), the caps of the spec, and the source text of postbuild.mjs.
"""

from __future__ import annotations

import json
import random
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "web" / "scripts" / "budgets.mjs"
POSTBUILD = ROOT / "web" / "scripts" / "postbuild.mjs"

CAPS = {
    "videos": 150_000_000,
    "tiles-glb": 95_000_000,
    "shards-clouds": 60_000_000,
    "splats": 25_000_000,
    "onnx": 80_000_000,
    "runtimes": 55_000_000,
    "own-code": 10_000_000,
    "studio-showcase": 25_000_000,
}
TOTAL = 500_000_000


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    assert SCRIPT.is_file(), "web/scripts/budgets.mjs exists (T-020-062)"
    return subprocess.run(
        ["node", str(SCRIPT), *args], capture_output=True, text=True, timeout=600, check=False, cwd=ROOT / "web"
    )


def _rules(done: subprocess.CompletedProcess[str]) -> list[tuple[str, str]]:
    out = []
    for line in done.stdout.splitlines():
        m = re.match(r"^([a-z-]+): ([^:]+): ", line)
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def _gz_node(path: Path) -> int:
    """gzip size of a file as Node's zlib (the library the budget script uses) computes it."""
    code = "process.stdout.write(String(require('zlib').gzipSync(require('fs').readFileSync(process.argv[1])).length))"
    done = subprocess.run(["node", "-e", code, str(path)], capture_output=True, text=True, timeout=120, check=True)
    return int(done.stdout)


def _random_script_with_gzip_size(target: int, scratch: Path) -> bytes:
    """Random bytes (incompressible) whose gzip size, as Node computes it, is exactly `target`."""
    rng = random.Random(20261011)
    pool = rng.randbytes(target + 512)
    probe = scratch / "probe.bin"
    n = target - 40
    for _ in range(40):
        probe.write_bytes(pool[:n])
        size = _gz_node(probe)
        if size == target:
            return pool[:n]
        n += target - size
    raise AssertionError("no random script with that gzip size was found")


def _page(root: Path, route: str, scripts: list[str], extra: str = "") -> None:
    d = root / route if route else root
    d.mkdir(parents=True, exist_ok=True)
    tags = "".join(f'<script type="module" src="/{s}"></script>' for s in scripts)
    (d / "index.html").write_text(f"<!doctype html><title>x</title>{tags}{extra}", encoding="utf-8")


def _client(tmp_path: Path) -> Path:
    root = tmp_path / "client"
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "manifest.json").write_text(json.dumps({"artefacts": []}), encoding="utf-8")
    (root / "js").mkdir()
    return root


# --------------------------------------------------------------------------------------------------------------------
# NFR-020-01
# --------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("NFR-020-01")
def test_the_postbuild_constant_is_200_000_bytes_and_no_longer_200_x_1024() -> None:
    text = POSTBUILD.read_text(encoding="utf-8")
    assert re.search(r"200_?000", text), "the budget constant is 200,000 bytes"
    assert not re.search(r"200\s*\*\s*1024", text), "the 200 x 1024 constant is aligned to 200,000 (T-020-062)"


@pytest.mark.req("NFR-020-01")
def test_a_route_at_exactly_200_000_bytes_gzip_passes_and_one_byte_more_fails(tmp_path: Path) -> None:
    ok = _client(tmp_path / "ok")
    (ok / "js" / "a.js").write_bytes(_random_script_with_gzip_size(200_000, tmp_path))
    _page(ok, "", ["js/a.js"])
    assert _run("--root", str(ok)).returncode == 0

    bad = _client(tmp_path / "bad")
    (bad / "js" / "a.js").write_bytes(_random_script_with_gzip_size(200_001, tmp_path))
    _page(bad, "", ["js/a.js"])
    done = _run("--root", str(bad))
    assert done.returncode == 1, done.stdout + done.stderr
    assert ("initial-js", "") in _rules(done) or any(
        line.startswith("initial-js:") for line in done.stdout.splitlines()
    )


@pytest.mark.req("NFR-020-01")
def test_scripts_of_one_page_add_up_and_a_script_shared_by_two_pages_counts_for_each(tmp_path: Path) -> None:
    root = _client(tmp_path)
    (root / "js" / "a.js").write_bytes(_random_script_with_gzip_size(120_000, tmp_path))
    (root / "js" / "b.js").write_bytes(_random_script_with_gzip_size(90_000, tmp_path))
    _page(root, "light", ["js/a.js"])
    _page(root, "heavy", ["js/a.js", "js/b.js"])
    done = _run("--root", str(root))
    assert done.returncode == 1
    subjects = [s for r, s in _rules(done) if r == "initial-js"]
    assert subjects == ["heavy"]


@pytest.mark.req("NFR-020-01")
def test_every_route_is_checked_dynamic_templates_included_and_the_offender_is_named(tmp_path: Path) -> None:
    root = _client(tmp_path)
    (root / "js" / "big.js").write_bytes(_random_script_with_gzip_size(200_050, tmp_path))
    (root / "js" / "ok.js").write_bytes(_random_script_with_gzip_size(50_000, tmp_path))
    for route in [
        "",
        "cases",
        "cases/A1",
        "studio",
        "studio/tools/warp",
        "studio/runs/20261007T120000Z-a2-haulage",
        "theory/haulage",
        "methods/m04",
        "results",
        "knowledge",
    ]:
        _page(root, route, ["js/ok.js"])
    _page(root, "studio/tools/cuopt", ["js/big.js"])
    done = _run("--root", str(root))
    assert done.returncode == 1
    assert [s for r, s in _rules(done) if r == "initial-js"] == ["studio/tools/cuopt"]


@pytest.mark.req("NFR-020-01")
def test_scripts_outside_the_root_and_non_script_links_are_not_counted(tmp_path: Path) -> None:
    root = _client(tmp_path)
    (root / "js" / "ok.js").write_bytes(b"console.log(1)")
    _page(
        root,
        "",
        ["js/ok.js"],
        extra='<link rel="stylesheet" href="/x.css"><script src="https://cdn.example.org/huge.js"></script>',
    )
    assert _run("--root", str(root)).returncode == 0


# --------------------------------------------------------------------------------------------------------------------
# NFR-020-03
# --------------------------------------------------------------------------------------------------------------------
def _file(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.truncate(size)


def _manifest(root: Path, entries: list[tuple[str, int, str]]) -> None:
    arts = [{"id": f"a{i}", "path": p, "bytes": b, "budget_class": c} for i, (p, b, c) in enumerate(entries)]
    (root / "assets" / "manifest.json").write_text(json.dumps({"artefacts": arts}), encoding="utf-8")


@pytest.mark.req("NFR-020-03")
@pytest.mark.parametrize("klass", sorted(CAPS))
def test_each_class_at_its_cap_passes_and_one_byte_over_fails_naming_the_class(tmp_path: Path, klass: str) -> None:
    cap = CAPS[klass]
    at_cap = cap - 10_000 if klass == "own-code" else cap  # own code also holds the small files of the client tree
    ok = _client(tmp_path / "ok")
    _file(ok / "assets" / "payload.bin", at_cap)
    _manifest(ok, [("payload.bin", at_cap, klass)])
    done_ok = _run("--root", str(ok))
    assert done_ok.returncode == 0, done_ok.stdout + done_ok.stderr

    bad = _client(tmp_path / "bad")
    _file(bad / "assets" / "payload.bin", cap + 1)
    _manifest(bad, [("payload.bin", cap + 1, klass)])
    done = _run("--root", str(bad))
    assert done.returncode == 1
    assert ("class-budget", klass) in _rules(done)


@pytest.mark.req("NFR-020-03")
def test_a_file_the_manifest_does_not_list_counts_as_own_code(tmp_path: Path) -> None:
    root = _client(tmp_path)
    _file(root / "assets" / "unlisted.bin", CAPS["own-code"] + 1)
    done = _run("--root", str(root))
    assert done.returncode == 1
    assert ("class-budget", "own-code") in _rules(done)


@pytest.mark.req("NFR-020-03")
def test_files_of_the_same_class_add_up(tmp_path: Path) -> None:
    root = _client(tmp_path)
    half = CAPS["splats"] // 2 + 1
    _file(root / "assets" / "a.bin", half)
    _file(root / "assets" / "b.bin", half)
    _manifest(root, [("a.bin", half, "splats"), ("b.bin", half, "splats")])
    assert ("class-budget", "splats") in _rules(_run("--root", str(root)))


@pytest.mark.req("NFR-020-03")
def test_the_size_on_disk_counts_not_the_size_the_manifest_declares(tmp_path: Path) -> None:
    root = _client(tmp_path)
    _file(root / "assets" / "liar.bin", CAPS["splats"] + 1)
    _manifest(root, [("liar.bin", 1, "splats")])
    assert ("class-budget", "splats") in _rules(_run("--root", str(root)))


@pytest.mark.req("NFR-020-03")
def test_the_whole_artifact_is_capped_at_500_000_000_bytes(tmp_path: Path) -> None:
    root = _client(tmp_path)
    classes = list(CAPS)
    entries = []
    for i, klass in enumerate(classes):
        _file(root / "assets" / f"f{i}.bin", CAPS[klass] if klass != "own-code" else CAPS[klass] - 1_000_000)
        entries.append((f"f{i}.bin", CAPS[klass], klass))
    _manifest(root, entries)
    assert sum(CAPS.values()) == TOTAL
    done = _run("--root", str(root))
    assert done.returncode == 0, done.stdout + done.stderr
    _file(
        root / "assets" / "extra.bin", 2_000_000
    )  # unlisted: own code, 1,000,001 bytes over its cap and over the total
    done = _run("--root", str(root))
    assert done.returncode == 1
    assert ("total-budget", "artifact") in _rules(done) or any(
        line.startswith("total-budget:") for line in done.stdout.splitlines()
    )


@pytest.mark.req("NFR-020-03")
def test_a_manifest_entry_with_an_unknown_class_or_a_path_that_climbs_out_is_a_usage_failure_not_a_pass(
    tmp_path: Path,
) -> None:
    root = _client(tmp_path)
    _file(root / "assets" / "a.bin", 10)
    _manifest(root, [("a.bin", 10, "no-such-class")])
    assert _run("--root", str(root)).returncode in (1, 2)
    _manifest(root, [("../../outside.bin", 10, "videos")])
    assert _run("--root", str(root)).returncode in (1, 2)


# --------------------------------------------------------------------------------------------------------------------
# NFR-020-04
# --------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("NFR-020-04")
def test_a_client_script_holding_katex_fails_naming_the_script(tmp_path: Path) -> None:
    root = _client(tmp_path)
    (root / "js" / "app.js").write_text("console.log('app')", encoding="utf-8")
    (root / "js" / "chunk.js").write_text(
        "function f(){throw new Error('KaTeX parse error: Expected }')}", encoding="utf-8"
    )
    _page(root, "", ["js/app.js"])
    done = _run("--root", str(root))
    assert done.returncode == 1
    assert ("katex-js", "js/chunk.js") in _rules(done)


@pytest.mark.req("NFR-020-04")
def test_katex_css_is_linked_by_pages_with_equations_and_only_by_them(tmp_path: Path) -> None:
    root = _client(tmp_path)
    (root / "js" / "app.js").write_text("1", encoding="utf-8")
    link = '<link rel="stylesheet" href="/assets/katex.min-abc123.css">'
    eq = '<span class="katex"><span class="katex-html">x</span></span>'
    _page(root, "theory/haulage", ["js/app.js"], extra=link + eq)  # right
    _page(root, "cases", ["js/app.js"])  # right: no equations, no stylesheet
    assert _run("--root", str(root)).returncode == 0
    _page(root, "methods", ["js/app.js"], extra=link)  # wrong: the stylesheet without equations
    _page(root, "theory/dust", ["js/app.js"], extra=eq)  # wrong: equations without the stylesheet
    done = _run("--root", str(root))
    assert done.returncode == 1
    assert sorted(s for r, s in _rules(done) if r == "katex-css") == ["methods", "theory/dust"]


@pytest.mark.req("NFR-020-04")
def test_a_katex_font_preload_on_a_page_without_equations_is_a_violation(tmp_path: Path) -> None:
    root = _client(tmp_path)
    (root / "js" / "app.js").write_text("1", encoding="utf-8")
    _page(
        root,
        "results",
        ["js/app.js"],
        extra='<link rel="preload" as="font" href="/assets/KaTeX_Main-Regular-xyz.woff2" crossorigin>',
    )
    done = _run("--root", str(root))
    assert done.returncode == 1
    assert ("katex-css", "results") in _rules(done)


# --------------------------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("NFR-020-01")
def test_usage_errors_exit_two_without_a_traceback(tmp_path: Path) -> None:
    assert _run("--bogus").returncode == 2
    done = _run("--root", str(tmp_path / "nowhere"))
    assert done.returncode == 2
    assert done.stderr.strip(), "a message is printed"
    assert "node:internal" not in done.stderr


@pytest.mark.req("NFR-020-03")
def test_an_empty_or_unreadable_manifest_is_reported_not_ignored(tmp_path: Path) -> None:
    root = _client(tmp_path)
    (root / "assets" / "manifest.json").write_text("{ not json", encoding="utf-8")
    assert _run("--root", str(root)).returncode in (1, 2)

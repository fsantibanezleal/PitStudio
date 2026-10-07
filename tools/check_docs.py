"""CI check for the docs wiki: links, public-repo hygiene, runnable-command markers and diagram rules.

Usage:  python tools/check_docs.py [--root docs] [--list-run]
Checks:
  1. every relative link / image in docs/**/*.md resolves to a file (and to a heading anchor when one is given);
  2. no foreign decision ids, machine paths or e-mail addresses;
  3. fenced shell blocks: info string `bash`, `bash run` (runs today) or `bash run deferred=P<n>`; nothing else;
  4. every SVG under docs/assets/diagrams parses, has role="img", <title>, <desc>, the `psd` class, no colour
     literal outside its <style> token block, and no text class filled with a token below 4.5:1 contrast;
  5. every requirement ID cited in the docs exists in specs/requirements.index.json (when that file exists).
Exit 0 = clean, 1 = violations (printed).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+\1")
FENCE = re.compile(r"^(\s*)(```+|~~~+)\s*(.*)$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FORBIDDEN = [
    (re.compile(r"\bADR-\d{4}\b"), "foreign decision id (decision records in this repo are DEC-NNNN)"),
    (re.compile(r"[A-Za-z]:\\Users\\", re.I), "machine path"),
    (re.compile(r"/Users/[a-z]"), "machine path"),
    (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}\b", re.I), "e-mail address"),
]
SHELL_LANGS = {"bash", "sh", "shell", "powershell", "pwsh", "ps1", "console"}
ALLOWED_INFO = "bash | bash run | bash run deferred=P<n>"
RUN_INFO = re.compile(r"^(bash|sh|powershell|pwsh)(\s+run(\s+deferred=P\d+)?)?$")
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
SVG_NS = "{http://www.w3.org/2000/svg}"
# palette tokens below 4.5:1 against some surface in some theme: fine for shapes, never for text
LOW_CONTRAST_TEXT = {"primary", "accent", "chart-2", "chart-3", "chart-6"}
CSS_RULE = re.compile(r"\.([\w-]+)\s*\{([^}]*)\}")
REQ_ID = re.compile(r"\b(?:US-\d{3}-\d{1,2}|(?:FR|NFR|SC|P|DC)-\d{3}-\d{2})\b")
KNOWN_IDS: set[str] | None = None  # loaded from specs/requirements.index.json in main()


def slugify(text: str) -> str:
    """GitHub-style heading anchor: link text kept, lower case, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text).strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def anchors(md: Path, cache: dict[Path, set[str]]) -> set[str]:
    if md not in cache:
        seen: dict[str, int] = {}
        out: set[str] = set()
        in_fence = False
        for line in md.read_text(encoding="utf-8").splitlines():
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            m = None if in_fence else HEADING.match(line)
            if m:
                s = slugify(m.group(2))
                n = seen.get(s, 0)
                out.add(s if n == 0 else f"{s}-{n}")
                seen[s] = n + 1
        cache[md] = out
    return cache[md]


def relpath(p: Path) -> str:
    return p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else p.as_posix()


def check_markdown(md: Path, cache: dict[Path, set[str]], runs: list[str]) -> list[str]:
    errs: list[str] = []
    rel = relpath(md)
    in_fence, fence_tok = False, ""
    for no, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
        f = FENCE.match(line)
        if f:
            tok, info = f.group(2), f.group(3).strip()
            if not in_fence:
                in_fence, fence_tok = True, tok[0] * len(tok)
                lang = info.split()[0].lower() if info else ""
                if lang in SHELL_LANGS and not RUN_INFO.match(info):
                    errs.append(f"{rel}:{no}: shell block info string '{info}' (use {ALLOWED_INFO})")
                if " run" in f" {info}":
                    runs.append(f"{rel}:{no}: {info}")
            elif tok.startswith(fence_tok):
                in_fence = False
            continue
        for rx, why in FORBIDDEN:
            if rx.search(line):
                errs.append(f"{rel}:{no}: {why}: {line.strip()[:120]}")
        if KNOWN_IDS is not None:
            errs += [
                f"{rel}:{no}: requirement id {rid} is not in specs/requirements.index.json"
                for rid in REQ_ID.findall(line)
                if rid not in KNOWN_IDS
            ]
        if in_fence:
            continue
        for target in LINK.findall(INLINE_CODE.sub("", line)):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target == "#":
                continue
            path_part, _, frag = target.partition("#")
            dest = md if not path_part else (md.parent / unquote(path_part)).resolve()
            if not dest.exists():
                errs.append(f"{rel}:{no}: broken link -> {target}")
            elif frag and dest.suffix == ".md" and frag not in anchors(dest, cache):
                errs.append(f"{rel}:{no}: missing anchor -> {target}")
    return errs


def check_svg(svg: Path) -> list[str]:
    rel = relpath(svg)
    try:
        tree = ET.parse(svg)
    except ET.ParseError as e:
        return [f"{rel}: does not parse: {e}"]
    errs: list[str] = []
    root = tree.getroot()
    if root.get("role") != "img":
        errs.append(f'{rel}: root needs role="img"')
    if "psd" not in (root.get("class") or "").split():
        errs.append(f'{rel}: root needs class="psd" (token scope)')
    errs += [f"{rel}: missing <{tag}>" for tag in ("title", "desc") if root.find(f"{SVG_NS}{tag}") is None]
    for el in root.iter():
        if el.tag == f"{SVG_NS}style":
            text = el.text or ""
            for m in HEX.finditer(text):
                if not re.search(r"--[\w-]+:\s*$", text[: m.start()]):
                    errs.append(f"{rel}: colour literal outside a token declaration in <style>: {m.group(0)}")
                    break
            continue
        for attr, val in el.attrib.items():
            functional = attr in ("fill", "stroke", "stop-color", "color") and re.search(r"rgba?\(|hsla?\(", val)
            if HEX.search(val) or functional:
                errs.append(f'{rel}: colour literal in <{el.tag.removeprefix(SVG_NS)} {attr}="{val}">')
                break
    style = "".join((s.text or "") for s in root.iter(f"{SVG_NS}style"))
    for name, body in CSS_RULE.findall(style):
        fill = re.search(r"fill\s*:\s*var\(--([\w-]+)\)", body)
        if "font" in body and fill and fill.group(1) in LOW_CONTRAST_TEXT:
            errs.append(
                f"{rel}: text class .{name} fills with --{fill.group(1)} (below 4.5:1 in one theme; use --fg, "
                "--fg-muted or --code)"
            )
    if "viewBox" not in root.attrib:
        errs.append(f"{rel}: missing viewBox")
    return errs


def run_blocks(md: Path) -> list[dict[str, object]]:
    """Every fenced block whose info string is `<shell> run` (not deferred), with its dedented body."""
    out: list[dict[str, object]] = []
    lines = md.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        f = FENCE.match(lines[i])
        if f:
            tok, info, indent = f.group(2), f.group(3).strip(), len(f.group(1))
            body, j = [], i + 1
            while j < len(lines) and not lines[j].strip().startswith(tok):
                body.append(lines[j][indent:] if lines[j][:indent].isspace() else lines[j].lstrip())
                j += 1
            if RUN_INFO.match(info) and info.split()[1:2] == ["run"] and "deferred=" not in info:
                out.append({"file": relpath(md), "line": i + 1, "shell": info.split()[0], "body": "\n".join(body)})
            i = j
        i += 1
    return out


def extract_run(root: Path, dest: Path) -> int:
    """Write each runnable block to dest/NNN.<sh|ps1> plus blocks.json (file, line, shell, commit) for a runner."""
    import subprocess

    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain", "--", str(root)], capture_output=True, text=True
        ).stdout.strip()
    )
    dest.mkdir(parents=True, exist_ok=True)
    blocks = [b for md in sorted(root.rglob("*.md")) for b in run_blocks(md)]
    for n, b in enumerate(blocks, 1):
        name = f"{n:03d}.{'ps1' if b['shell'] in ('powershell', 'pwsh') else 'sh'}"
        (dest / name).write_text(str(b["body"]) + "\n", encoding="utf-8", newline="\n")
        b["script"] = name
    manifest = {"commit": sha, "docs_dirty": dirty, "blocks": blocks}
    (dest / "blocks.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"extracted {len(blocks)} run blocks at {sha[:12]}{' (docs have uncommitted changes)' if dirty else ''}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="docs")
    ap.add_argument("--list-run", action="store_true", help="print every `run` block")
    ap.add_argument("--extract-run", metavar="DIR", help="write every runnable block + blocks.json (with the commit)")
    a = ap.parse_args(argv[1:])
    if a.extract_run:
        return extract_run((ROOT / a.root).resolve(), Path(a.extract_run))
    root = (ROOT / a.root).resolve()
    global KNOWN_IDS
    index = ROOT / "specs" / "requirements.index.json"
    if index.exists():
        KNOWN_IDS = set(json.loads(index.read_text(encoding="utf-8")).get("requirements", {}))
    cache: dict[Path, set[str]] = {}
    runs: list[str] = []
    errs: list[str] = []
    mds = sorted(root.rglob("*.md"))
    for md in mds:
        errs += check_markdown(md, cache, runs)
    svgs = sorted((root / "assets" / "diagrams").glob("*.svg"))
    for svg in svgs:
        errs += check_svg(svg)
    if a.list_run:
        print("\n".join(runs))
    for e in errs:
        print(e)
    deferred = sum("deferred=" in r for r in runs)
    print(
        f"DOCS CHECK {'OK' if not errs else 'FAIL'} - {len(mds)} pages, {len(svgs)} diagrams, "
        f"{len(runs) - deferred} run blocks, {deferred} deferred, {len(errs)} problem(s)"
    )
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

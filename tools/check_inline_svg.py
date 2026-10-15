"""Inline-SVG guard for the diagrams of the information modal and of the theory pages (FR-020-51).

Usage:  python tools/check_inline_svg.py [--root DIR] [--all]

A diagram that the information modal (`web/src/app/architecture.tsx`, imports of `docs/assets/diagrams/<name>.svg?raw`)
or a theory page (`web/src/content/theory/{en,es}/*.mdx`, `<Diagram name="<name>" />`) inlines must be a well-formed
SVG document and must hold no hex colour literal outside the custom-property declarations of a `<style>` element (the
diagrams use theme tokens only), no script element, no event-handler attribute and no `href` / `xlink:href` that is not
a `#fragment`.

The file is parsed as XML, never matched as text, so the text content of a diagram is never examined. A DOCTYPE that
declares entities is malformed (no entity expansion, no external entity).

Output: one line `<check>: <path>: <detail>` per finding.
Exit 0 = clean, 1 = findings, 2 = usage error or unreadable root.
`--all` checks every file of docs/assets/diagrams instead of the referenced ones.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAGRAMS_REL = Path("docs") / "assets" / "diagrams"
SVG_NS = "http://www.w3.org/2000/svg"

HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![0-9a-zA-Z_-])")
CUSTOM_PROPERTY = re.compile(r"--[\w-]+\s*:[^;}]*")
URL_REF = re.compile(r"url\(\s*#[^)]*\)")
MODAL_IMPORT = re.compile(r"""docs/assets/diagrams/([^"'?]+?)\.svg\?raw""")
THEORY_TAG = re.compile(r"""<Diagram\s+name=["']([^"']+)["']\s*/?>""")


@dataclass(frozen=True)
class Finding:
    check: str
    subject: str
    detail: str

    def line(self) -> str:
        return f"{self.check}: {self.subject}: {self.detail}"


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def _subject(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            pass
    return path.as_posix() if root is None else path.name


def _hex_outside_tokens(css: str) -> list[str]:
    return HEX.findall(CUSTOM_PROPERTY.sub("", css))


def check_svg(path: Path, root: Path | None = None) -> list[Finding]:
    """All findings of one diagram file."""
    subject = _subject(path, root)
    if not path.is_file():
        return [Finding("missing-file", subject, "the diagram does not exist")]
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    if b"\x00" in raw or re.search(r"<!ENTITY", text):
        return [Finding("malformed-svg", subject, "NUL byte or entity declaration")]
    try:
        tree = ET.fromstring(raw)
    except ET.ParseError as exc:
        return [Finding("malformed-svg", subject, f"not well-formed XML: {exc}")]
    if tree.tag != "{" + SVG_NS + "}svg":
        return [Finding("malformed-svg", subject, "the root is not an svg element in the SVG namespace")]
    found: list[Finding] = []
    for el in tree.iter():
        tag = _local(el.tag).lower() if isinstance(el.tag, str) else ""
        if tag == "script":
            found.append(Finding("script-element", subject, "a script element"))
        if tag == "style":
            found.extend(
                Finding("hex-colour", subject, f"{colour} outside a custom-property declaration")
                for colour in _hex_outside_tokens(el.text or "")
            )
        for name, value in el.attrib.items():
            local = _local(name).lower()
            if local.startswith("on"):
                found.append(Finding("event-handler", subject, f"attribute {local}"))
            elif local == "href":
                if not value.startswith("#"):
                    found.append(Finding("external-href", subject, f"href to {value[:60]}"))
            elif local not in {"id", "class"}:
                found.extend(
                    Finding("hex-colour", subject, f"{colour} in attribute {local}")
                    for colour in _hex_outside_tokens(URL_REF.sub("", value))
                )
    return found


def referenced_diagrams(root: Path) -> list[Path]:
    """The diagrams referenced by the information modal and by the theory pages, without repeats, sorted."""
    names: set[str] = set()
    modal = root / "web" / "src" / "app" / "architecture.tsx"
    if modal.is_file():
        names.update(MODAL_IMPORT.findall(modal.read_text(encoding="utf-8")))
    theory = root / "web" / "src" / "content" / "theory"
    if theory.is_dir():
        for mdx in sorted(theory.glob("*/*.mdx")):
            names.update(THEORY_TAG.findall(mdx.read_text(encoding="utf-8")))
    return sorted(root / DIAGRAMS_REL / f"{n}.svg" for n in names)


def check_references(root: Path) -> list[Finding]:
    """check_svg over every referenced diagram; a reference to a file that does not exist is a missing-file finding."""
    out: list[Finding] = []
    for path in referenced_diagrams(root):
        escaped = ".." in path.relative_to(root).parts
        out += (
            [Finding("missing-file", path.relative_to(root).as_posix(), "the reference leaves the diagram folder")]
            if escaped
            else check_svg(path, root)
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this repository)")
    ap.add_argument("--all", action="store_true", help="check every file of docs/assets/diagrams")
    args = ap.parse_args(argv)
    if not args.root.is_dir():
        print(f"check_inline_svg: {args.root} is not a directory", file=sys.stderr)
        return 2
    root = args.root
    if args.all:
        findings = [f for p in sorted((root / DIAGRAMS_REL).glob("*.svg")) for f in check_svg(p, root)]
    else:
        findings = check_references(root)
    for f in findings:
        print(f.line())
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

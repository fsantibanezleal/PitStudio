"""Equation drift and language parity of the theory pages against `docs/theory/` (FR-020-02, FR-020-05, FR-020-47).

Usage:  python tools/check_theory.py [--root DIR]

The reviewed source of every equation is `docs/theory/<id>.md`; the web pages are
`web/src/content/theory/{en,es}/<id>.mdx`. MDX conventions: a display equation is a `$$` block whose closing line
carries its label, `$$ {#eq-<label>}`; a figure is `<Figure id="<figure id>" />`; a reference is
`<Cite key="<key>" />`; an unverified transcription is `<Unverified />`, once per occurrence of the word UNVERIFIED in the docs page.

Findings (`<check>: <page>: <detail>`, one line each; exit 1 when there is any, 0 when clean, 2 on a usage error or a
missing docs/theory directory):
  page-set          a docs page with no MDX page, or an MDX page with no docs page
  missing-language  a page that exists in one language only
  equation-missing  a display equation of the docs page that the English page lacks, after whitespace normalisation
  label-mismatch    the equation labels of the English and Spanish pages differ
  figure-mismatch   the figure ids of the two pages differ
  reference-mismatch the reference keys of the two pages differ
  unverified-count  a page whose number of `<Unverified />` differs from the number of UNVERIFIED words of the docs page
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FENCE = re.compile(r"^\s*(```|~~~)")
CLOSE_LABELLED = re.compile(r"^\s*\$\$\s*(?:\{#(eq-[A-Za-z0-9-]+)\})?\s*$")
FIGURE = re.compile(r"""<Figure\s+id=["']([^"']+)["']\s*/?>""")
CITE = re.compile(r"""<Cite\s+key=["']([^"']+)["']\s*/?>""")
UNVERIFIED_TAG = re.compile(r"<Unverified\s*/>")
UNVERIFIED_WORD = re.compile(r"\bUNVERIFIED\b")


@dataclass(frozen=True)
class Finding:
    check: str
    subject: str
    detail: str

    def line(self) -> str:
        return f"{self.check}: {self.subject}: {self.detail}"


def normalise_latex(text: str) -> str:
    """Every run of whitespace becomes one space and the ends are stripped; nothing else changes."""
    return re.sub(r"\s+", " ", text).strip()


def _blocks(markdown: str) -> list[tuple[str, str | None]]:
    """The `$$` display blocks outside code fences, as (body, label); an unclosed block is dropped."""
    out: list[tuple[str, str | None]] = []
    in_fence = False
    body: list[str] | None = None
    for line in markdown.splitlines():
        if body is None and FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if body is None:
            if line.strip() == "$$":
                body = []
        else:
            closing = CLOSE_LABELLED.match(line)
            if closing:
                out.append(("\n".join(body), closing.group(1)))
                body = None
            else:
                body.append(line)
    return out


def display_equations(markdown: str) -> list[str]:
    """The bodies of the `$$ ... $$` display blocks of a docs page, in order, as written."""
    return [body for body, _label in _blocks(markdown)]


def _labels(mdx: str) -> set[str]:
    return {label for _body, label in _blocks(mdx) if label}


def _pages(root: Path) -> tuple[dict[str, Path], dict[str, dict[str, Path]]]:
    docs = {p.stem: p for p in sorted((root / "docs" / "theory").glob("*.md")) if p.stem != "README"}
    web: dict[str, dict[str, Path]] = {"en": {}, "es": {}}
    for lang in web:
        folder = root / "web" / "src" / "content" / "theory" / lang
        if folder.is_dir():
            web[lang] = {p.stem: p for p in sorted(folder.glob("*.mdx"))}
    return docs, web


def check(root: Path) -> list[Finding]:
    docs, web = _pages(root)
    found: list[Finding] = []
    for page in sorted(set(docs) | set(web["en"]) | set(web["es"])):
        in_docs = page in docs
        langs = [lang for lang in ("en", "es") if page in web[lang]]
        if not in_docs:
            found.append(Finding("page-set", page, "an MDX page without a docs/theory page"))
            continue
        if not langs:
            found.append(Finding("page-set", page, "no MDX page in either language"))
            continue
        if len(langs) == 1:
            missing = "es" if langs[0] == "en" else "en"
            found.append(Finding("missing-language", page, f"no {missing} page"))
            continue
        text = {lang: web[lang][page].read_text(encoding="utf-8") for lang in langs}
        source = docs[page].read_text(encoding="utf-8")
        have = {normalise_latex(body) for body, _label in _blocks(text["en"])}
        found.extend(
            Finding("equation-missing", page, normalise_latex(eq))
            for eq in display_equations(source)
            if normalise_latex(eq) not in have
        )
        if _labels(text["en"]) != _labels(text["es"]):
            diff = sorted(_labels(text["en"]) ^ _labels(text["es"]))
            found.append(Finding("label-mismatch", page, ", ".join(diff)))
        for check_name, pattern in (("figure-mismatch", FIGURE), ("reference-mismatch", CITE)):
            en_set, es_set = set(pattern.findall(text["en"])), set(pattern.findall(text["es"]))
            if en_set != es_set:
                found.append(Finding(check_name, page, ", ".join(sorted(en_set ^ es_set))))
        want = len(UNVERIFIED_WORD.findall(source))
        for lang in langs:
            got = len(UNVERIFIED_TAG.findall(text[lang]))
            if got != want:
                found.append(
                    Finding("unverified-count", page, f"{lang}: {got} badges for {want} UNVERIFIED in the docs")
                )
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this repository)")
    args = ap.parse_args(argv)
    if not (args.root / "docs" / "theory").is_dir():
        print(f"check_theory: {args.root / 'docs' / 'theory'} is not a directory", file=sys.stderr)
        return 2
    findings = check(args.root)
    for f in findings:
        print(f.line())
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

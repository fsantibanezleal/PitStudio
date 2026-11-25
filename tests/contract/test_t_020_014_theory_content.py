"""T-020-014 (contract half): the theory pages in EN and ES against `docs/theory/`.

Covers the equation drift check and the language parity check.

Requirements: FR-020-02 (every display equation of `docs/theory/<id>.md` appears, after LaTeX whitespace
normalisation, in the EN page, with the same set of equation labels in the ES page), FR-020-03 (an equation that
does not parse in KaTeX fails the build naming the file and line),
FR-020-05 (UNVERIFIED badge next to every unverified transcription) and
FR-020-47 (a page in one language only, or an ES page that differs from its EN page in equation labels, figure ids or
reference keys, fails naming the page).

Spec: specs/020-web-knowledge/ (spec.md section 3.1 and FR-020-47; plan.md test strategy rows FR-020-02, FR-020-03,
FR-020-47). Browser half (pages, anchors, symbol tables, references): web/e2e/t_020_014_theory_pages.spec.ts.

Expected API of the implementation:
  tools/check_theory.py (the plan's equation-drift and parity checker), importable through `sys.path`:
    display_equations(markdown: str) -> list[str]       the bodies of the `$$ ... $$` display blocks of a docs page, in
                                                          order, as written (a block opens with a line holding only `$$`
                                                          and closes with the next such line)
    normalise_latex(text: str) -> str                    every run of whitespace (spaces, tabs, newlines) becomes one
                                                          space, the ends are stripped; nothing else changes
    check(root: Path) -> list[Finding]                   Finding.check in {"equation-missing", "label-mismatch",
                                                          "figure-mismatch", "reference-mismatch", "missing-language",
                                                          "page-set", "unverified-count"}, Finding.subject the page id
                                                          ("comminution") and Finding.detail the equation, label, figure
                                                          or key concerned
    CLI: `python tools/check_theory.py --root DIR`: one line "<check>: <page>: <detail>" per finding, exit 0 when clean,
         1 with findings, 2 on a usage error or a missing docs/theory directory (message, no traceback).
  MDX conventions fixed by this test (flagged in the red report): web/src/content/theory/{en,es}/<id>.mdx; a display
  equation is a `$$` block followed on the closing line by ` {#eq-<label>}`; a figure is `<Figure id="<figure id>" />`;
  a reference is `<Cite key="<bib key>" />`; an unverified transcription is marked `<Unverified />` (it renders
  the badge "UNVERIFIED — pinned at specification"), once per occurrence of the word UNVERIFIED in the docs page.
  Node entry for FR-020-03: `node web/scripts/check-equations.mjs --root DIR` parses every `$$` block of the EN and
  ES pages with KaTeX (throwOnError true), prints "<file>:<line>: <message>" and exits 1 for a block that fails.

Oracles: the number of display equations per docs page counted by an independent line-based scan (131 in the 13 pages,
table below, counted outside the code under test), the first equation of the comminution page written out by hand, and
fixture trees built here with known defects.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "check_theory.py"
NODE_CHECK = ROOT / "web" / "scripts" / "check-equations.mjs"
sys.path.insert(0, str(ROOT / "tools"))

IDS = [
    "haulage",
    "loading-and-terramechanics",
    "drill-and-blast",
    "slopes-and-monitoring",
    "bulk-flow-dem-mpm",
    "comminution",
    "dust",
    "tailings",
    "planning",
    "rtx-sensor-physics",
    "robot-learning",
    "vision-language-reasoning",
    "sim-to-real",
]
# display equations per docs page: lines holding only `$$`, divided by two
COUNTS = {
    "bulk-flow-dem-mpm": 11,
    "comminution": 5,
    "drill-and-blast": 8,
    "dust": 6,
    "haulage": 13,
    "loading-and-terramechanics": 7,
    "planning": 14,
    "robot-learning": 8,
    "rtx-sensor-physics": 16,
    "sim-to-real": 4,
    "slopes-and-monitoring": 11,
    "tailings": 20,
    "vision-language-reasoning": 8,
}


def _mod():
    assert TOOL.is_file(), "tools/check_theory.py exists (T-020-014)"
    import check_theory

    return check_theory


def _docs(page: str) -> str:
    return (ROOT / "docs" / "theory" / f"{page}.md").read_text(encoding="utf-8")


@pytest.mark.req("FR-020-02")
def test_the_hand_counts_describe_the_13_pages_of_the_docs() -> None:
    assert sorted(COUNTS) == sorted(IDS)
    assert sum(COUNTS.values()) == 131
    for page, count in COUNTS.items():
        lines = [ln for ln in _docs(page).splitlines() if ln.strip() == "$$"]
        assert len(lines) == 2 * count, page


@pytest.mark.req("FR-020-02")
@pytest.mark.parametrize("page", IDS)
def test_display_equations_of_each_docs_page_are_found(page: str) -> None:
    assert len(_mod().display_equations(_docs(page))) == COUNTS[page]


@pytest.mark.req("FR-020-02")
def test_the_first_comminution_equation_is_bonds_law_as_written_in_the_docs() -> None:
    first = _mod().display_equations(_docs("comminution"))[0]
    expected = r"W = 10\,W_i\left(\frac{1}{\sqrt{P_{80}}} - \frac{1}{\sqrt{F_{80}}}\right)"
    assert _mod().normalise_latex(first) == expected


@pytest.mark.req("FR-020-02")
def test_whitespace_normalisation_collapses_runs_and_nothing_else() -> None:
    n = _mod().normalise_latex
    assert n("  a  +\n\t b  ") == "a + b"
    assert n("a+b") == "a+b"
    assert n(r"\frac{1}{2}") == r"\frac{1}{2}"
    assert n("") == ""
    assert n("\n\n") == ""


@pytest.mark.req("FR-020-02")
def test_display_equations_ignores_inline_math_and_unclosed_blocks_and_code_fences() -> None:
    md = "text $x$ and $$y$$ inline\n\n$$\nA = 1\n$$\n\n```\n$$\nnot an equation\n$$\n```\n\n$$\nB = 2\n"
    got = _mod().display_equations(md)
    assert [_mod().normalise_latex(g) for g in got][:1] == ["A = 1"]
    assert all("not an equation" not in g for g in got)
    assert all(_mod().normalise_latex(g) != "B = 2" for g in got), "an unclosed block is not an equation"


# --------------------------------------------------------------------------------------------------------------------
# fixture trees
# --------------------------------------------------------------------------------------------------------------------
DOC = (
    "# Page\n\n$$\nW = 10\\,W_i\\left(\\frac{1}{\\sqrt{P}}\\right)\n$$\n\ntext\n\n"
    "$$\nE = m c^2\n$$\n\nUNVERIFIED value.\n"
)


def _mdx(
    lang: str, *, eq2_label: str = "two", extra: str = "", unverified: int = 1, figure: str = "fig-a", cite: str = "k1"
) -> str:
    badge = "<Unverified />\n" * unverified
    return (
        f"# Page {lang}\n\n$$\nW =\n   10\\,W_i\\left(\\frac{{1}}{{\\sqrt{{P}}}}\\right)\n$$ {{#eq-one}}\n\n"
        f'$$\n  E = m c^2\n$$ {{#eq-{eq2_label}}}\n\n<Figure id="{figure}" />\n<Cite key="{cite}" />\n{badge}{extra}\n'
    )


def _tree(tmp_path: Path, en: str | None, es: str | None, doc: str = DOC, page: str = "haulage") -> Path:
    (tmp_path / "docs" / "theory").mkdir(parents=True)
    (tmp_path / "docs" / "theory" / f"{page}.md").write_text(doc, encoding="utf-8")
    for lang, text in (("en", en), ("es", es)):
        if text is not None:
            d = tmp_path / "web" / "src" / "content" / "theory" / lang
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{page}.mdx").write_text(text, encoding="utf-8")
    return tmp_path


def _found(root: Path) -> set[tuple[str, str]]:
    return {(f.check, f.subject) for f in _mod().check(root)}


@pytest.mark.req("FR-020-02")
def test_a_consistent_page_in_both_languages_is_clean_even_when_whitespace_differs(tmp_path: Path) -> None:
    root = _tree(tmp_path, _mdx("en"), _mdx("es"))
    assert _mod().check(root) == []


@pytest.mark.req("FR-020-02")
def test_a_docs_equation_missing_from_the_english_page_is_reported_with_the_page(tmp_path: Path) -> None:
    en = _mdx("en").replace("E = m c^2", "E = m c^3")
    found = _mod().check(_tree(tmp_path, en, _mdx("es")))
    assert ("equation-missing", "haulage") in {(f.check, f.subject) for f in found}
    assert any("m c^2" in f.detail for f in found if f.check == "equation-missing")


@pytest.mark.req("FR-020-02")
def test_an_equation_only_in_the_spanish_page_is_not_a_drift_but_a_different_label_set_is(tmp_path: Path) -> None:
    es = _mdx("es", eq2_label="dos")
    assert ("label-mismatch", "haulage") in _found(_tree(tmp_path, _mdx("en"), es))


@pytest.mark.req("FR-020-47")
def test_a_page_in_one_language_only_fails_naming_the_page(tmp_path: Path) -> None:
    assert ("missing-language", "haulage") in _found(_tree(tmp_path, _mdx("en"), None))


@pytest.mark.req("FR-020-47")
def test_a_theory_page_with_no_docs_source_or_a_docs_page_with_no_mdx_is_a_page_set_failure(tmp_path: Path) -> None:
    root = _tree(tmp_path, None, None)
    assert ("page-set", "haulage") in _found(root)


@pytest.mark.req("FR-020-47")
def test_figure_ids_and_reference_keys_must_be_the_same_in_both_languages(tmp_path: Path) -> None:
    assert ("figure-mismatch", "haulage") in _found(_tree(tmp_path / "a", _mdx("en"), _mdx("es", figure="fig-b")))
    assert ("reference-mismatch", "haulage") in _found(_tree(tmp_path / "b", _mdx("en"), _mdx("es", cite="k2")))


@pytest.mark.req("FR-020-47")
def test_the_order_of_figures_and_references_does_not_matter_only_the_sets(tmp_path: Path) -> None:
    en = _mdx("en", extra='<Figure id="fig-z" />\n<Cite key="k9" />\n')
    es = _mdx("es", extra='<Figure id="fig-z" />\n<Cite key="k9" />\n').replace(
        '<Figure id="fig-a" />\n<Cite key="k1" />\n', '<Cite key="k1" />\n<Figure id="fig-a" />\n'
    )
    assert _mod().check(_tree(tmp_path, en, es)) == []


@pytest.mark.req("FR-020-05")
def test_every_unverified_mark_of_the_docs_has_its_badge_in_both_languages(tmp_path: Path) -> None:
    assert ("unverified-count", "haulage") in _found(_tree(tmp_path / "a", _mdx("en", unverified=0), _mdx("es")))
    assert ("unverified-count", "haulage") in _found(_tree(tmp_path / "b", _mdx("en"), _mdx("es", unverified=2)))
    assert _mod().check(_tree(tmp_path / "c", _mdx("en"), _mdx("es"))) == []


@pytest.mark.req("FR-020-02")
def test_unicode_and_very_long_equations_do_not_break_the_check(tmp_path: Path) -> None:
    long_eq = "x = " + " + ".join(f"a_{{{i}}}" for i in range(2000))
    doc = f"# P\n\n$$\n{long_eq}\n$$\n\n$$\n\\mu = µ\\,\\text{{más}}\n$$\n"
    en = f"$$\n{long_eq}\n$$ {{#eq-a}}\n\n$$\n\\mu = µ\\,\\text{{más}}\n$$ {{#eq-b}}\n"
    es = f"$$\n{long_eq}\n$$ {{#eq-a}}\n\n$$\n\\mu = µ\\,\\text{{más}}\n$$ {{#eq-b}}\n"
    assert _mod().check(_tree(tmp_path, en, es, doc=doc)) == []


@pytest.mark.req("FR-020-02")
def test_the_real_repository_passes_its_own_check() -> None:
    assert _mod().check(ROOT) == []


# --------------------------------------------------------------------------------------------------------------------
# CLI and KaTeX
# --------------------------------------------------------------------------------------------------------------------
def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    assert TOOL.is_file(), "tools/check_theory.py exists (T-020-014)"
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=300, check=False)


@pytest.mark.req("FR-020-47")
def test_cli_exit_codes_and_lines(tmp_path: Path) -> None:
    clean = _tree(tmp_path / "a", _mdx("en"), _mdx("es"))
    assert _cli("--root", str(clean)).returncode == 0
    bad = _tree(tmp_path / "b", _mdx("en"), None)
    done = _cli("--root", str(bad))
    assert done.returncode == 1
    assert "missing-language: haulage" in done.stdout
    assert "Traceback" not in done.stderr
    assert _cli("--bogus").returncode == 2
    assert _cli("--root", str(tmp_path / "none")).returncode == 2


def _node(*args: str) -> subprocess.CompletedProcess[str]:
    assert NODE_CHECK.is_file(), "web/scripts/check-equations.mjs exists (T-020-014)"
    return subprocess.run(
        ["node", str(NODE_CHECK), *args], capture_output=True, text=True, timeout=300, check=False, cwd=ROOT / "web"
    )


@pytest.mark.req("FR-020-03")
def test_a_malformed_equation_fails_the_build_check_naming_the_file_and_line(tmp_path: Path) -> None:
    good = _tree(tmp_path / "a", _mdx("en"), _mdx("es"))
    assert _node("--root", str(good)).returncode == 0
    broken = _mdx("en").replace("E = m c^2", "E = \\frac{1}{")  # unbalanced brace: KaTeX throws
    root = _tree(tmp_path / "b", broken, _mdx("es"))
    done = _node("--root", str(root))
    assert done.returncode == 1, done.stdout + done.stderr
    m = re.search(r"theory/en/haulage\.mdx:(\d+):", done.stdout + done.stderr)
    assert m, done.stdout + done.stderr
    line = int(m.group(1))
    text = (root / "web" / "src" / "content" / "theory" / "en" / "haulage.mdx").read_text(encoding="utf-8").splitlines()
    assert "frac{1}{" in "\n".join(text[max(0, line - 3) : line + 3])


@pytest.mark.req("FR-020-03")
@pytest.mark.parametrize("bad", ["\\unknowncommand{x}", "a^b^c", "\\begin{matrix} a", "\\frac{1}{2", "x_"])
def test_each_katex_error_class_is_caught(tmp_path: Path, bad: str) -> None:
    root = _tree(tmp_path, _mdx("en").replace("E = m c^2", bad), _mdx("es"))
    assert _node("--root", str(root)).returncode == 1

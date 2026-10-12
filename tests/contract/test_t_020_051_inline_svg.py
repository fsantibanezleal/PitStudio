"""T-020-051: the inline-SVG guard for the diagrams of the information modal and of the theory pages.

Requirements: FR-020-51 (if a diagram referenced by an information-modal tab or a theory page is missing, is not
well-formed SVG, contains a hex colour literal outside its custom-property token block (for example a `fill="#..."`
attribute), a script element, an event-handler attribute, or an `href` / `xlink:href` to another file or origin
(namespace declarations excepted), then the build fails naming the file; an unmodified docs diagram, which uses its
tokens only, must pass).

Spec: specs/020-web-knowledge/ (spec.md FR-020-51, FR-020-43; plan.md test strategy row FR-020-51: "planted
missing file, malformed SVG, `fill="#123456"` outside the token block, `<script>`, `onload=`,
`href="https://..."`; an unmodified docs
diagram (tokens only) must pass"). Browser half (themed repaint): web/e2e/t_020_050_architecture_modal.spec.ts.

Expected API of the implementation (tools/check_inline_svg.py, importable through `sys.path`):
  Finding                      attributes `check` (one of "missing-file", "malformed-svg", "hex-colour",
                               "script-element", "event-handler", "external-href"), `subject` (the repository-relative
                               POSIX path of the diagram) and `detail`
  check_svg(path: Path, root: Path | None = None) -> list[Finding]     all findings of one diagram file; a missing file
                               gives one "missing-file" finding, a file that is not well-formed XML or whose root is not
                               an svg element in the SVG namespace one "malformed-svg"; the file is parsed as XML (never
                               matched as text), a DOCTYPE with entities counts as "malformed-svg"
  referenced_diagrams(root: Path) -> list[Path]   the diagrams referenced by the information modal
                               (`web/src/app/architecture.tsx`: imports of `.../docs/assets/diagrams/<name>.svg?raw`)
                               and by
                               the theory pages (`web/src/content/theory/{en,es}/*.mdx`: `<Diagram name="<name>" />`,
                               resolved to `docs/assets/diagrams/<name>.svg`), without repeats, sorted
  check_references(root: Path) -> list[Finding]   check_svg over every referenced diagram, so that a reference to a file
                               that does not exist is a "missing-file" finding naming it
  CLI: `python tools/check_inline_svg.py --root DIR [--all]`: one line "<check>: <path>: <detail>" per finding;
       exit 0 when clean, 1 with findings, 2 on a usage error or an unreadable root (message, no traceback);
       `--all` checks every file of docs/assets/diagrams instead of the referenced ones.
Rules: a hex colour literal is `#` followed by 3, 4, 6 or 8 hexadecimal digits in an attribute value or in CSS text,
outside the declarations of custom properties (`--name: value`) of a `<style>` element; text content of the diagram is
never examined; an event-handler attribute is any attribute whose local name starts with `on`; an `href` or
`xlink:href` is external unless it starts with `#`; the `xmlns` declarations are not references.

Oracle: planted defects in copies of a real docs diagram (the plan's list), the 47 unmodified diagrams of the repository
(which pass: they use tokens only), hand-built tiny SVGs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "check_inline_svg.py"
DIAGRAMS = ROOT / "docs" / "assets" / "diagrams"
sys.path.insert(0, str(ROOT / "tools"))

SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'


def _mod():
    assert TOOL.is_file(), "tools/check_inline_svg.py exists (T-020-051)"
    import check_inline_svg

    return check_inline_svg


def _svg(body: str, head: str = "") -> str:
    return f'<svg {SVG_NS} viewBox="0 0 10 10" role="img"><title>t</title>{head}{body}</svg>'


def _write(tmp_path: Path, text: str, name: str = "d.svg") -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def _checks(path: Path) -> set[str]:
    return {f.check for f in _mod().check_svg(path)}


@pytest.mark.req("FR-020-51")
def test_a_clean_diagram_passes_and_the_token_block_may_hold_hex_colours(tmp_path: Path) -> None:
    tokens = (
        "<style>.psd{--bg:#ffffff;--fg:#1b1523}"
        "@media (prefers-color-scheme: dark){.psd{--bg:#0f0b14}}.a{fill:var(--bg)}</style>"
    )
    p = _write(tmp_path, _svg('<rect class="a" width="5" height="5" fill="currentColor" stroke="none"/>', tokens))
    assert _mod().check_svg(p) == []


@pytest.mark.req("FR-020-51")
@pytest.mark.parametrize("stem", ["tool-map", "lanes-measured-gate", "pitstudio-overview"])
def test_an_unmodified_docs_diagram_passes(stem: str) -> None:
    assert _mod().check_svg(DIAGRAMS / f"{stem}.svg", ROOT) == []


@pytest.mark.req("FR-020-51")
def test_all_47_diagrams_of_the_docs_pass_including_the_two_whose_text_looks_like_a_colour_or_a_handler() -> None:
    files = sorted(DIAGRAMS.glob("*.svg"))
    assert len(files) >= 47
    failures = {f.name: [x.check for x in _mod().check_svg(f, ROOT)] for f in files}
    assert {k: v for k, v in failures.items() if v} == {}


@pytest.mark.req("FR-020-51")
def test_text_content_is_never_examined_a_ticket_number_and_a_handler_look_alike_pass(tmp_path: Path) -> None:
    p = _write(tmp_path, _svg("<text>issue #4813 and onload=1 and href=https://x</text>"))
    assert _mod().check_svg(p) == []


@pytest.mark.req("FR-020-51")
def test_a_missing_file_is_named(tmp_path: Path) -> None:
    found = _mod().check_svg(tmp_path / "gone.svg", tmp_path)
    assert [(f.check, f.subject) for f in found] == [("missing-file", "gone.svg")]


@pytest.mark.req("FR-020-51")
@pytest.mark.parametrize(
    "text",
    [
        "",
        "not xml at all",
        "<svg xmlns='http://www.w3.org/2000/svg'><g></svg>",
        "<html><body/></html>",
        '<svg viewBox="0 0 1 1"/>',  # no SVG namespace
        '<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg xmlns="http://www.w3.org/2000/svg">&x;</svg>',
        '<!DOCTYPE svg [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><svg xmlns="http://www.w3.org/2000/svg">&b;</svg>',
        "\x00<svg/>",
    ],
    ids=["empty", "text", "unclosed", "html", "no-namespace", "external-entity", "entity-expansion", "nul"],
)
def test_a_file_that_is_not_well_formed_svg_is_malformed(tmp_path: Path, text: str) -> None:
    assert "malformed-svg" in _checks(_write(tmp_path, text))


@pytest.mark.req("FR-020-51")
@pytest.mark.parametrize(
    "body",
    [
        '<rect fill="#123456"/>',
        '<rect stroke="#abc"/>',
        '<rect style="fill:#FFF"/>',
        '<stop stop-color="#12345678"/>',
        '<circle fill="#1234"/>',
        "<style>.x{fill:#ff00aa}</style>",
        '<g><g><rect fill="#00F"/></g></g>',
    ],
)
def test_a_hex_colour_literal_outside_the_token_block_fails(tmp_path: Path, body: str) -> None:
    assert "hex-colour" in _checks(_write(tmp_path, _svg(body)))


@pytest.mark.req("FR-020-51")
def test_hex_in_a_token_block_and_a_non_hex_colour_elsewhere_do_not_fail(tmp_path: Path) -> None:
    head = "<style>.p{--a:#123456;--b:#abc}.q{fill:var(--a);stroke:red}</style>"
    assert _mod().check_svg(_write(tmp_path, _svg('<rect class="q" fill="rgb(1,2,3)"/><rect fill="red"/>', head))) == []


@pytest.mark.req("FR-020-51")
@pytest.mark.parametrize("body", ["<script>alert(1)</script>", '<script href="x.js"/>', "<g><SCRIPT>1</SCRIPT></g>"])
def test_a_script_element_fails(tmp_path: Path, body: str) -> None:
    assert "script-element" in _checks(_write(tmp_path, _svg(body)))


@pytest.mark.req("FR-020-51")
@pytest.mark.parametrize("attr", ['onload="x()"', 'onclick="x()"', "onmouseover='x()'", 'onerror="x"', 'onfocusin="x"'])
def test_an_event_handler_attribute_fails(tmp_path: Path, attr: str) -> None:
    assert "event-handler" in _checks(_write(tmp_path, _svg(f"<rect {attr}/>")))


@pytest.mark.req("FR-020-51")
@pytest.mark.parametrize(
    "markup",
    [
        '<a href="https://example.org/x"><rect/></a>',
        '<a xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="other.svg"><rect/></a>',
        '<image href="data:image/png;base64,AAAA"/>',
        '<use href="other.svg#a"/>',
        '<a href="javascript:alert(1)"><rect/></a>',
        '<image href="//cdn.example.org/x.png"/>',
    ],
)
def test_an_href_to_another_file_or_origin_fails(tmp_path: Path, markup: str) -> None:
    assert "external-href" in _checks(_write(tmp_path, _svg(markup)))


@pytest.mark.req("FR-020-51")
def test_fragment_references_and_namespace_declarations_are_not_external(tmp_path: Path) -> None:
    body = (
        '<defs><g id="a"><rect/></g></defs><use href="#a"/>'
        '<use xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="#a"/>'
    )
    p = _write(
        tmp_path,
        f'<svg {SVG_NS} xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1 1"><title>t</title>{body}</svg>',
    )
    assert _mod().check_svg(p) == []


@pytest.mark.req("FR-020-51")
def test_findings_name_the_file_relative_to_the_root(tmp_path: Path) -> None:
    sub = tmp_path / "docs" / "assets" / "diagrams"
    sub.mkdir(parents=True)
    p = _write(sub, _svg('<rect fill="#123456"/>'), "bad.svg")
    found = _mod().check_svg(p, tmp_path)
    assert found
    assert {f.subject for f in found} == {"docs/assets/diagrams/bad.svg"}


# --------------------------------------------------------------------------------------------------------------------
# references from the modal and the theory pages
# --------------------------------------------------------------------------------------------------------------------
def _tree(tmp_path: Path, *, modal: list[str], theory: dict[str, list[str]], files: list[str]) -> Path:
    d = tmp_path / "docs" / "assets" / "diagrams"
    d.mkdir(parents=True)
    for name in files:
        (d / f"{name}.svg").write_text(_svg('<rect fill="currentColor"/>'), encoding="utf-8")
    (tmp_path / "web" / "src" / "app").mkdir(parents=True)
    imports = "\n".join(f'import d{i} from "../../../docs/assets/diagrams/{n}.svg?raw";' for i, n in enumerate(modal))
    (tmp_path / "web" / "src" / "app" / "architecture.tsx").write_text(imports + "\nexport {};\n", encoding="utf-8")
    for lang in ("en", "es"):
        t = tmp_path / "web" / "src" / "content" / "theory" / lang
        t.mkdir(parents=True)
        for page, names in theory.items():
            (t / f"{page}.mdx").write_text(
                "# P\n" + "\n".join(f'<Diagram name="{n}" />' for n in names) + "\n", encoding="utf-8"
            )
    return tmp_path


@pytest.mark.req("FR-020-51")
def test_referenced_diagrams_are_the_modal_imports_and_the_theory_diagram_tags_without_repeats(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        modal=["overview", "lanes"],
        theory={"haulage": ["lanes", "forces"]},
        files=["overview", "lanes", "forces", "unused"],
    )
    got = [p.relative_to(root).as_posix() for p in _mod().referenced_diagrams(root)]
    assert got == [
        "docs/assets/diagrams/forces.svg",
        "docs/assets/diagrams/lanes.svg",
        "docs/assets/diagrams/overview.svg",
    ]


@pytest.mark.req("FR-020-51")
def test_a_reference_to_a_missing_diagram_fails_naming_it(tmp_path: Path) -> None:
    root = _tree(tmp_path, modal=["overview"], theory={"haulage": ["ghost"]}, files=["overview"])
    found = _mod().check_references(root)
    assert [(f.check, f.subject) for f in found] == [("missing-file", "docs/assets/diagrams/ghost.svg")]


@pytest.mark.req("FR-020-51")
def test_a_reference_that_climbs_out_of_the_diagram_folder_is_not_followed(tmp_path: Path) -> None:
    root = _tree(tmp_path, modal=[], theory={"haulage": ["../../../secret"]}, files=[])
    found = _mod().check_references(root)
    assert found
    assert all(".." not in f.subject for f in found) or any(f.check == "missing-file" for f in found)


@pytest.mark.req("FR-020-51")
def test_the_repository_references_pass(tmp_path: Path) -> None:
    assert _mod().check_references(ROOT) == []


# --------------------------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------------------------
def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    assert TOOL.is_file(), "tools/check_inline_svg.py exists (T-020-051)"
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=300, check=False)


@pytest.mark.req("FR-020-51")
def test_cli_exit_codes_and_lines(tmp_path: Path) -> None:
    clean = _tree(tmp_path / "a", modal=["overview"], theory={"haulage": ["overview"]}, files=["overview"])
    assert _cli("--root", str(clean)).returncode == 0
    dirty = _tree(tmp_path / "b", modal=["overview"], theory={"haulage": ["ghost"]}, files=["overview"])
    done = _cli("--root", str(dirty))
    assert done.returncode == 1
    assert "missing-file: docs/assets/diagrams/ghost.svg" in done.stdout
    assert "Traceback" not in done.stderr
    (dirty / "docs" / "assets" / "diagrams" / "overview.svg").write_text(
        _svg('<rect fill="#123456"/>'), encoding="utf-8"
    )
    both = _cli("--root", str(dirty))
    assert "hex-colour: docs/assets/diagrams/overview.svg" in both.stdout
    assert _cli("--bogus").returncode == 2
    assert _cli("--root", str(tmp_path / "none")).returncode == 2


@pytest.mark.req("FR-020-51")
def test_cli_all_checks_every_diagram_file_even_when_unreferenced(tmp_path: Path) -> None:
    root = _tree(tmp_path, modal=[], theory={}, files=["unused"])
    (root / "docs" / "assets" / "diagrams" / "unused.svg").write_text(_svg("<script>1</script>"), encoding="utf-8")
    assert _cli("--root", str(root)).returncode == 0
    done = _cli("--root", str(root), "--all")
    assert done.returncode == 1
    assert "script-element: docs/assets/diagrams/unused.svg" in done.stdout

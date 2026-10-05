"""tools/check_docs.py: links, hygiene, run markers and diagram rules."""

from __future__ import annotations

import shutil
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_docs  # noqa: E402

TOKENS = ".psd{--fg:#1b1523;--accent:#a100ff}"


@pytest.fixture
def work() -> Iterator[Path]:
    d = ROOT / ".tmp" / "test-check-docs" / uuid.uuid4().hex
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def md(work: Path, name: str, text: str) -> Path:
    p = work / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def errors(p: Path) -> list[str]:
    return check_docs.check_markdown(p, {}, [])


def svg(work: Path, body: str, root_attrs: str = 'role="img" class="psd" viewBox="0 0 10 10"') -> Path:
    p = work / "d.svg"
    p.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" {root_attrs}><title>t</title><desc>d</desc>'
        f"<style>{TOKENS}</style>{body}</svg>",
        encoding="utf-8",
    )
    return p


def test_valid_links_and_anchors_pass(work: Path) -> None:
    md(work, "b.md", "# Big Title: v2 (beta)\n\n## Second `code` part\n")
    links = "See [b](b.md), [t](b.md#big-title-v2-beta), [s](b.md#second-code-part), [x](#local)"
    a = md(work, "a.md", links + "\n# Local\n")
    assert errors(a) == []


def test_broken_link_and_missing_anchor_fail(work: Path) -> None:
    md(work, "b.md", "# Only\n")
    a = md(work, "a.md", "[gone](nope.md) and [bad](b.md#other)\n")
    errs = errors(a)
    assert any("broken link -> nope.md" in e for e in errs)
    assert any("missing anchor -> b.md#other" in e for e in errs)


def test_external_links_and_links_inside_code_are_ignored(work: Path) -> None:
    text = "[w](https://example.org/x) [m](mailto:x) `![e](missing.svg)`\n```bash\n[no](missing.md)\n```\n"
    a = md(work, "a.md", text)
    assert errors(a) == []


@pytest.mark.parametrize(
    ("line", "why"),
    [
        ("see " + "ADR" + "-0036 for details", "foreign decision id"),  # built so this file holds no such id
        ("C:" + "\\Users\\someone\\Data", "machine path"),  # built so this file holds no machine path itself
        ("write to someone@example.com", "e-mail address"),
    ],
)
def test_forbidden_references_fail(work: Path, line: str, why: str) -> None:
    assert any(why in e for e in errors(md(work, "a.md", line + "\n")))


def test_version_pins_are_not_emails(work: Path) -> None:
    assert errors(md(work, "a.md", "Use pnpm@11.28.4 and DEC-0004.\n")) == []


def test_shell_block_markers(work: Path) -> None:
    ok = md(work, "a.md", "```bash\nx\n```\n```bash run\nuv sync\n```\n```bash run deferred=P6\nstudio run\n```\n")
    assert errors(ok) == []
    bad = md(work, "b.md", "```bash runs\nx\n```\n")
    assert any("shell block info string" in e for e in errors(bad))


def test_svg_rules(work: Path) -> None:
    assert check_docs.check_svg(svg(work, '<rect class="box" width="1" height="1"/>')) == []
    assert any("colour literal" in e for e in check_docs.check_svg(svg(work, '<rect fill="#ff0000"/>')))
    assert any("missing viewBox" in e for e in check_docs.check_svg(svg(work, "", 'role="img" class="psd"')))
    assert any("role" in e for e in check_docs.check_svg(svg(work, "", 'class="psd" viewBox="0 0 1 1"')))


def test_svg_style_hex_only_in_token_declarations(work: Path) -> None:
    p = work / "s.svg"
    p.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" role="img" class="psd" viewBox="0 0 1 1"><title>t</title>'
        "<desc>d</desc><style>.psd{--fg:#000}.box{fill:#fff}</style></svg>",
        encoding="utf-8",
    )
    assert any("outside a token declaration" in e for e in check_docs.check_svg(p))

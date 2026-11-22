# ruff: noqa: PT018
"""tools/check_tdd.py: owner approvals of pushed commits (specs/approvals.md).

A listed SHA is excused for exactly the listed rule; an unlisted SHA still fails; a listed SHA fails for another rule.
The repository under test is built once: commit S adds a skip marker (rule 4), commit G is a `[green]` commit of a task
with no earlier `[red]` commit (rule 1). Only `specs/approvals.md` changes between the cases.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "check_tdd.py"


def git(root: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.org", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    root = tmp_path_factory.mktemp("tdd")
    git(root, "init", "-q")
    (root / "tools").mkdir()
    shutil.copy(TOOL, root / "tools" / "check_tdd.py")
    (root / "README.md").write_text("x\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "chore: init")
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text(
        "import pytest\n\n\ndef test_a():\n    pytest.skip('no')\n", encoding="utf-8"
    )
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "test(T-001-001): FR-001-01 add a test")
    skip = git(root, "rev-parse", "HEAD")
    (root / "src.py").write_text("x = 1\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "feat(T-002-002): FR-002-02 a green commit with no red before it [green]")
    green = git(root, "rev-parse", "HEAD")
    return {"root": root, "skip": skip, "green": green}


def run(repo: dict[str, object], rows: list[str]) -> tuple[int, str]:
    root = repo["root"]
    assert isinstance(root, Path)
    approvals = root / "specs" / "approvals.md"
    approvals.parent.mkdir(exist_ok=True)
    approvals.write_text(
        "# Approvals\n\n| SHA | Rule | Status | Owner decision | Note |\n|---|---|---|---|---|\n" + "".join(rows),
        encoding="utf-8",
    )
    r = subprocess.run(
        [sys.executable, "tools/check_tdd.py"], cwd=root, capture_output=True, text=True, encoding="utf-8"
    )
    return r.returncode, r.stdout


def row(sha: object, rule: int) -> str:
    return f"| `{sha}` | {rule} | approved | owner 2026-10-12 | test |\n"


def test_without_a_ledger_both_violations_fail(repo) -> None:
    code, out = run(repo, [])
    assert code == 1
    assert "adds a skip/xfail/only marker" in out and "has no earlier [red] commit" in out


def test_a_listed_sha_is_excused_for_exactly_the_listed_rule(repo) -> None:
    code, out = run(repo, [row(repo["skip"], 4)])
    assert code == 1, "the green commit without a red is not excused by the skip row"
    assert "adds a skip/xfail/only marker" not in out and "has no earlier [red] commit" in out


def test_every_violation_listed_gives_a_clean_check(repo) -> None:
    code, out = run(repo, [row(repo["skip"], 4), row(repo["green"], 1)])
    assert code == 0, out


def test_a_short_sha_prefix_is_accepted(repo) -> None:
    code, out = run(repo, [row(str(repo["skip"])[:7], 4), row(str(repo["green"])[:7], 1)])
    assert code == 0, out


def test_a_listed_sha_fails_for_another_rule(repo) -> None:
    code, out = run(repo, [row(repo["skip"], 1), row(repo["green"], 4)])
    assert code == 1
    assert "adds a skip/xfail/only marker" in out and "has no earlier [red] commit" in out


def test_an_unlisted_sha_still_fails(repo) -> None:
    code, out = run(repo, [row("0" * 40, 4), row("0" * 40, 1), row(repo["skip"], 4)])
    assert code == 1 and "has no earlier [red] commit" in out and "adds a skip/xfail/only marker" not in out


def test_a_malformed_row_excuses_nothing(repo) -> None:
    code, out = run(
        repo, [f"| {str(repo['skip'])[:5]} | 4 | x | y | z |\n", f"| `{repo['green']}` | nine | x | y | z |\n"]
    )
    assert code == 1 and "adds a skip/xfail/only marker" in out and "has no earlier [red] commit" in out


def test_load_approvals_and_waived_unit() -> None:
    spec = importlib.util.spec_from_file_location("check_tdd_under_test", TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ledger = {"abcdef1": {4}}
    assert mod.waived("abcdef1234", 4, ledger)
    assert not mod.waived("abcdef1234", 3, ledger)
    assert not mod.waived("abcdef0234", 4, ledger)

"""tools/check_tdd.py: the approval ledger (specs/approvals.md) waives exactly one commit for exactly one rule."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_tdd  # noqa: E402

LEDGER_HEAD = "# Approvals\n\n## Waivers\n\n| Commit | Rule | Decision | Note |\n|---|---|---|---|\n"


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.org", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def commit(repo: Path, subject: str, files: dict[str, str]) -> str:
    for name, text in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", subject)
    return git(repo, "rev-parse", "HEAD")


def run(repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    monkeypatch.setattr(check_tdd, "ROOT", repo)
    code = check_tdd.main(["check_tdd.py"])
    return code, capsys.readouterr().out


@pytest.fixture
def work() -> Iterator[Path]:
    # plain mkdir under the process temp dir: pytest's tmp_path and mkdtemp are owner-only on Windows (git cannot enter)
    d = Path(tempfile.gettempdir()) / "test-check-tdd" / uuid.uuid4().hex
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def repo(work: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # an elevated process owns the dirs it creates as Administrators; git then refuses them as "dubious ownership"
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "safe.directory")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "*")
    r = work / "r"
    r.mkdir()
    git(r, "init", "-q")
    commit(r, "chore: start", {"README.md": "x\n"})
    return r


def test_green_without_red_fails_when_unlisted(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    commit(repo, "feat(T-009-001): FR-009-01 thing [green]", {"a.py": "1\n"})
    code, out = run(repo, monkeypatch, capsys)
    assert code == 1
    assert "has no earlier [red] commit" in out


def test_listed_sha_is_accepted_for_its_rule(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sha = commit(repo, "feat(T-009-001): FR-009-01 thing [green]", {"a.py": "1\n"})
    commit(repo, "docs: ledger", {"specs/approvals.md": LEDGER_HEAD + f"| {sha[:7]} | 1 | owner 2026-10-12 | x |\n"})
    code, out = run(repo, monkeypatch, capsys)
    assert code == 0, out


def test_listed_sha_does_not_waive_another_rule(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sha = commit(repo, "feat(T-009-001): FR-009-01 thing [green]", {"a.py": "1\n"})
    commit(repo, "docs: ledger", {"specs/approvals.md": LEDGER_HEAD + f"| {sha[:7]} | 4 | owner 2026-10-12 | x |\n"})
    code, out = run(repo, monkeypatch, capsys)
    assert code == 1
    assert "has no earlier [red] commit" in out


def test_another_sha_is_not_waived_by_a_listed_one(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = commit(repo, "feat(T-009-001): FR-009-01 thing [green]", {"a.py": "1\n"})
    second = commit(repo, "feat(T-009-002): FR-009-02 other [green]", {"b.py": "1\n"})
    commit(repo, "docs: ledger", {"specs/approvals.md": LEDGER_HEAD + f"| {first[:7]} | 1 | owner 2026-10-12 | x |\n"})
    code, out = run(repo, monkeypatch, capsys)
    assert code == 1
    assert second[:8] in out
    assert first[:8] not in out


def test_skip_marker_rule_4_waiver_is_exact(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sha = commit(repo, "build(T-011-002): env smoke", {"t.py": "import pytest\npytest.skip('no env')\n"})
    code, out = run(repo, monkeypatch, capsys)
    assert code == 1
    assert "adds a skip/xfail/only marker" in out
    commit(repo, "docs: ledger", {"specs/approvals.md": LEDGER_HEAD + f"| {sha[:7]} | 4 | owner 2026-10-12 | x |\n"})
    code, out = run(repo, monkeypatch, capsys)
    assert code == 0, out


def test_rows_outside_the_waivers_section_are_not_waivers(work: Path) -> None:
    text = (
        "# Approvals\n\n## Recorded\n\n| Commit | Rule | Decision |\n|---|---|---|\n| abcdef1 | 4 | note |\n\n"
        + LEDGER_HEAD
        + "| 1234567 | 2 | owner 2026-10-12 | x |\n"
    )
    (work / "specs").mkdir()
    (work / "specs" / "approvals.md").write_text(text, encoding="utf-8")
    assert check_tdd.load_approvals(work) == {("1234567", 2)}


def test_a_missing_ledger_waives_nothing(work: Path) -> None:
    assert check_tdd.load_approvals(work) == set()
    assert not check_tdd.waived(set(), "a" * 40, 1)

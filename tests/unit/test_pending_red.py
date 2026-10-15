"""tools/pending_red.py: test files of [red] commits not covered by a [green] commit are pending (not collected)."""

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
import pending_red  # noqa: E402


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.org", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def commit(repo: Path, subject: str, files: dict[str, str]) -> None:
    for name, text in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", subject)


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    # plain mkdir under the process temp dir: pytest's tmp_path is owner-only on Windows (git cannot enter), and an
    # elevated process owns what it creates as Administrators, which git refuses as "dubious ownership"
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "safe.directory")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "*")
    d = Path(tempfile.gettempdir()) / "test-pending-red" / uuid.uuid4().hex
    d.mkdir(parents=True)
    git(d, "init", "-q", "-b", "main")
    commit(d, "chore: scaffold", {"README.md": "x\n"})
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_pending_red_only_task_is_pending(repo: Path) -> None:
    commit(repo, "test(T-001-001): FR-001-01 a [red]", {"tests/unit/test_t_001_001_a.py": "def test_a(): ...\n"})
    assert pending_red.pending_files(repo) == ["tests/unit/test_t_001_001_a.py"]


def test_pending_red_green_task_is_not_pending(repo: Path) -> None:
    commit(repo, "test(T-001-001): FR-001-01 a [red]", {"tests/unit/test_t_001_001_a.py": "def test_a(): ...\n"})
    commit(repo, "feat(T-001-001): FR-001-01 a [green]", {"src/a.py": "x = 1\n"})
    assert pending_red.pending_files(repo) == []


def test_pending_red_green_of_a_sibling_task_does_not_cover(repo: Path) -> None:
    commit(repo, "test(T-007-001): FR-007-01 a [red]", {"tests/unit/test_t_007_001_a.py": "x\n"})
    commit(repo, "test(T-007-002): FR-007-02 b [red]", {"tests/unit/test_t_007_002_b.py": "x\n"})
    commit(repo, "feat(T-007-001): FR-007-01 a [green]", {"src/a.py": "x = 1\n"})
    assert pending_red.pending_files(repo) == ["tests/unit/test_t_007_002_b.py"]


def test_pending_red_non_task_commits_and_other_markers_are_ignored(repo: Path) -> None:
    commit(repo, "test(T-008-001): FR-008-01 a approved change", {"tests/unit/test_t_008_001_a.py": "x\n"})
    commit(repo, "chore: tests/unit/test_other.py [red]", {"tests/unit/test_other.py": "x\n"})
    assert pending_red.pending_files(repo) == []


def test_pending_red_shared_kit_is_never_pending(repo: Path) -> None:
    kit = {"tests/_kit/helpers.py": "x = 1\n", "tests/support/fake.py": "x = 1\n"}
    commit(repo, "test(T-002-001): FR-002-01 b [red]", {**kit, "tests/unit/test_t_002_001_b.py": "x\n"})
    assert pending_red.pending_files(repo) == ["tests/unit/test_t_002_001_b.py"]


def test_pending_red_file_of_two_tasks_needs_every_task_green(repo: Path) -> None:
    shared = "tests/unit/test_shared.py"
    commit(repo, "test(T-003-001): FR-003-01 c [red]", {shared: "a\n"})
    commit(repo, "test(T-006-002): FR-006-02 d [red]", {shared: "a\nb\n"})
    assert pending_red.pending_files(repo) == [shared]  # both referencing red commits are uncovered
    commit(repo, "feat(T-003-001): FR-003-01 c [green]", {"src/c.py": "x = 1\n"})
    assert pending_red.pending_files(repo) == []  # one referencing task is green: the file is mandatory

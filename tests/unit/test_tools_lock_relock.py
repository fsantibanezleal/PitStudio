"""tools/lock_tests.py --relock: an owner-approved test change rewrites the hash of a locked file in place.

Without --relock an existing entry is never rewritten (append-only); with it only the listed locked files are
rewritten, other entries and comments stay byte-identical, and an unlocked listed file is appended.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "tools" / "lock_tests.py"


def sha(name: str) -> str:
    """sha256 of the file content `<name>` plus a newline (the files hold e.g. "a1")."""
    return hashlib.sha256(f"{name}\n".encode()).hexdigest()


def make_root(tmp_path: Path) -> Path:
    (tmp_path / "tools").mkdir()
    shutil.copy(TOOL, tmp_path / "tools" / "lock_tests.py")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "a.py").write_text("a1\n", encoding="utf-8")
    (tmp_path / "tests" / "b.py").write_text("b1\n", encoding="utf-8")
    return tmp_path


def lock(root: Path, *args: str) -> str:
    r = subprocess.run(
        [sys.executable, "tools/lock_tests.py", *args], cwd=root, capture_output=True, text=True, check=True
    )
    return r.stdout


def test_default_mode_keeps_an_existing_entry(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    lock(root, "specs/x/tests.lock", "tests/a.py")
    (root / "tests" / "a.py").write_text("a2\n", encoding="utf-8")
    assert "already locked" in lock(root, "specs/x/tests.lock", "tests/a.py")
    assert (root / "specs/x/tests.lock").read_text(encoding="utf-8") == f"{sha('a1')}  tests/a.py\n"


def test_relock_rewrites_only_the_listed_locked_file(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    lock(root, "specs/x/tests.lock", "tests/a.py", "tests/b.py")
    path = root / "specs/x/tests.lock"
    path.write_text("# a comment\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
    (root / "tests" / "a.py").write_text("a2\n", encoding="utf-8")
    (root / "tests" / "b.py").write_text("b2\n", encoding="utf-8")
    out = lock(root, "--relock", "specs/x/tests.lock", "tests/a.py")
    assert "relocked 1 file(s)" in out
    assert path.read_text(encoding="utf-8").splitlines() == [
        "# a comment",
        f"{sha('a2')}  tests/a.py",
        f"{sha('b1')}  tests/b.py",
    ]


def test_relock_appends_a_file_that_is_not_locked_yet_and_normalises_crlf(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    lock(root, "specs/x/tests.lock", "tests/a.py")
    (root / "tests" / "b.py").write_bytes(b"b1\r\n")
    lock(root, "--relock", "specs/x/tests.lock", "tests/a.py", "tests/b.py")
    lines = (root / "specs/x/tests.lock").read_text(encoding="utf-8").splitlines()
    assert lines == [f"{sha('a1')}  tests/a.py", f"{sha('b1')}  tests/b.py"]

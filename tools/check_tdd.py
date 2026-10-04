"""CI check: test-first integrity over the whole git history (authoritative; local hooks only guide).

Usage:  python tools/check_tdd.py [--rev-range A..B] [--replay]
Rules (commit subjects follow `type(T-NNN-xxx): REQ-IDs ... [red]|[green]`):
  1. every [green] commit has an EARLIER [red] commit with the same task id;
  2. a [green] commit does not modify files that were locked (specs/**/tests.lock) at its parent;
  3. tests.lock is append-only: an existing entry may not be removed or change hash unless the commit
     carries a "Test-Change-Approved:" trailer;
  4. no commit ADDS a skip/xfail/only marker unless it carries "Test-Change-Approved:";
  5. at HEAD every locked file still matches its locked sha256 (unless re-locked with approval);
  6. --replay: for each [red] commit, the tests it added FAIL at that commit (run in a temp worktree).
Exit 0 = clean, 1 = violations (printed).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = re.compile(r"\((T-\d{3}-\d{3})\)")
SKIP_ADDED = re.compile(
    r"^\+(?!\+\+).*(pytest\.mark\.(skip|xfail)|pytest\.skip\(|\.only\(|\b(it|test|describe)\.skip\b|"
    r"\b(it|test|describe)\.todo\b|@unittest\.skip)"
)
APPROVED = "Test-Change-Approved:"


def norm_sha(data: bytes) -> str:
    """sha256 of the content with CRLF normalised to LF (stable across Windows checkouts)."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def lock_at(rev: str) -> dict[str, str]:
    out: dict[str, str] = {}
    files = git("ls-tree", "-r", "--name-only", rev, check=False).splitlines()
    for f in files:
        if f.startswith("specs/") and f.endswith("tests.lock"):
            for line in git("show", f"{rev}:{f}", check=False).splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2 and not line.startswith("#"):
                    out[parts[1].strip()] = parts[0].strip()
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev-range", default="HEAD")
    ap.add_argument("--replay", action="store_true")
    a = ap.parse_args(argv[1:])
    errs: list[str] = []
    log = git("log", "--reverse", "--format=%H%x1f%P%x1f%s%x1f%B%x1e", a.rev_range, check=False)
    commits = [c.strip("\n").split("\x1f") for c in log.split("\x1e") if c.strip()]
    red_seen: dict[str, str] = {}
    red_commits: list[tuple[str, list[str]]] = []
    for sha, parents, subject, body in commits:
        short = sha[:8]
        parent = parents.split()[0] if parents.strip() else None
        approved = APPROVED in body
        m = TASK.search(subject)
        tid = m.group(1) if m else None
        changed = git("show", "--name-only", "--format=", sha, check=False).splitlines()
        if "[red]" in subject and tid:
            red_seen.setdefault(tid, sha)
            added = git("show", "--diff-filter=A", "--name-only", "--format=", sha, check=False).splitlines()
            red_commits.append(
                (sha, [f for f in added if f.startswith("tests/") or "/tests/" in f or ".test." in f or ".spec." in f])
            )
        if "[green]" in subject:
            if not tid:
                errs.append(f"{short}: [green] commit without a task id '(T-NNN-xxx)' in its subject")
            elif tid not in red_seen:
                errs.append(f"{short}: [green] for {tid} has no earlier [red] commit")
            if parent:
                locked_before = lock_at(parent)
                touched = sorted(set(changed) & set(locked_before))
                if touched and not approved:
                    errs.append(f"{short}: [green] modifies locked tests {touched} without '{APPROVED}'")
        if parent:
            before, after = lock_at(parent), lock_at(sha)
            for path, h in before.items():
                if path not in after:
                    if not approved:
                        errs.append(f"{short}: removed lock entry {path} without '{APPROVED}'")
                elif after[path] != h and not approved:
                    errs.append(f"{short}: lock hash of {path} changed without '{APPROVED}'")
            if not approved:
                diff = git("show", "--format=", "-U0", sha, check=False)
                errs.extend(
                    f"{short}: adds a skip/xfail/only marker without '{APPROVED}': {line[:100]}"
                    for line in diff.splitlines()
                    if SKIP_ADDED.search(line)
                )
    for path, h in lock_at("HEAD").items():
        f = ROOT / path
        if not f.is_file():
            errs.append(f"HEAD: locked file {path} is missing")
        elif norm_sha(f.read_bytes()) != h:
            errs.append(f"HEAD: locked file {path} differs from its tests.lock sha256")
    if a.replay:
        for sha, tests in red_commits:
            if not tests:
                errs.append(f"{sha[:8]}: [red] commit adds no test files")
                continue
            with tempfile.TemporaryDirectory() as tmp:
                wt = Path(tmp) / "wt"
                git("worktree", "add", "--detach", str(wt), sha)
                try:
                    py = [t for t in tests if t.endswith(".py")]
                    if py:
                        r = subprocess.run(
                            [sys.executable, "-m", "pytest", "-q", *py], cwd=wt, capture_output=True, text=True
                        )
                        if r.returncode == 0:
                            errs.append(f"{sha[:8]}: [red] tests PASS at the red commit (they must fail): {py}")
                finally:
                    git("worktree", "remove", "--force", str(wt), check=False)
    if errs:
        print(f"TDD CHECK FAIL ({len(errs)}):")
        for e in errs:
            print(f"  [x] {e}")
        return 1
    print(f"TDD CHECK OK - {len(commits)} commit(s), {len(red_seen)} task(s) with [red]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

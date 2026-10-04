"""Claude Code PreToolUse hook: locked tests are read-only for the implementer.

A test becomes locked when its [red] commit lists it in a specs/**/tests.lock file
(lines: "<sha256>  <repo-relative path>"). Editing a locked test, a golden file or a snapshot is
denied. If a locked test is wrong, write the problem to specs/test-change-requests.md and stop the
task — changing a locked test needs a spec change plus a "Test-Change-Approved:" commit trailer
(checked in CI by tools/check_tdd.py). New test files are never blocked.
Fail-safe: any internal error allows the call.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[1]).resolve()
PROTECTED_GLOBS = [
    re.compile(r"(^|/)tests/golden/"),
    re.compile(r"(^|/)__snapshots__/"),
    re.compile(r"(^|/)specs/000-foundation/thresholds\.yaml$"),
]
WRITE_CMD = re.compile(
    r"(>|\btee\b|\bcp\b|\bmv\b|\brm\b|\bsed\s+-i|Set-Content|Add-Content|Out-File|"
    r"Remove-Item|Move-Item|Copy-Item|write_text|open\()",
    re.I,
)


def locked() -> set[str]:
    paths: set[str] = set()
    for lock in ROOT.glob("specs/**/tests.lock"):
        for line in lock.read_text(encoding="utf-8").splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2 and not line.startswith("#"):
                paths.add(parts[1].strip().replace("\\", "/"))
    return paths


def rel(p: str) -> str:
    try:
        return Path(p).resolve().relative_to(ROOT).as_posix()
    except Exception:
        return p.replace("\\", "/")


def deny(reason: str) -> int:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


def main() -> int:
    inp = json.load(sys.stdin)
    tool, ti = inp.get("tool_name", ""), inp.get("tool_input", {}) or {}
    lk = locked()
    msg = (
        "{p} is locked (tests.lock / golden / thresholds). Do not weaken oracles: record the problem in "
        "specs/test-change-requests.md and stop this task; a change needs a spec change + "
        "'Test-Change-Approved:' trailer."
    )
    if tool in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
        p = rel(str(ti.get("file_path") or ti.get("notebook_path") or ""))
        if p in lk or any(g.search(p) for g in PROTECTED_GLOBS):
            return deny(msg.format(p=p))
        return 0
    if tool in {"Bash", "PowerShell"}:
        cmd = str(ti.get("command", ""))
        if WRITE_CMD.search(cmd):
            for p in lk:
                if p in cmd.replace("\\", "/"):
                    return deny(msg.format(p=p))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)

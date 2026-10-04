"""CI check for a public repo: secrets, machine paths, large files and template residue.

Usage:  python tools/check_repo.py      (exit 1 on any finding)
Scans git-tracked files only. Large data/models belong in fetch scripts, Release assets or a model hub —
never in git (> 10 MB fails) and never in Git LFS.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = {
    "secret": re.compile(
        r"sk-ant-[A-Za-z0-9_\-]{16,}|\bsk-(proj-)?[A-Za-z0-9]{32,}|\bgsk_[A-Za-z0-9]{20,}|"
        r"\bgh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
        r"\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_\-]{35}\b"
    ),
    # written so that this file never matches itself: a drive letter + ":" + slash/backslash + "Users", or "/<x>/Users/"
    "machine path": re.compile(r"\b[A-Za-z]:[\\/]Users[\\/]|/[a-z]/Users/|/home/[a-z][a-z0-9_-]*/"),
    "template residue": re.compile(r"\{\{[A-Z0-9_]{3,}\}\}"),
}
SELF = Path(__file__).resolve()


def main() -> int:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout
    errs: list[str] = []
    if (ROOT / ".template-source").exists():
        errs.append(".template-source sentinel present")
    for rel in out.splitlines():
        p = ROOT / rel
        if not p.is_file() or p.resolve() == SELF:
            continue
        size = p.stat().st_size
        if size > 10 * 1024 * 1024:
            errs.append(f"large file {rel} ({size / 1e6:.1f} MB > 10 MB)")
            continue
        raw = p.read_bytes()
        if b"\x00" in raw[:4096]:
            continue
        for n, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), start=1):
            for name, rx in CHECKS.items():
                if rx.search(line):
                    errs.append(f"{name}: {rel}:{n}")
    if errs:
        print(f"REPO CHECK FAIL ({len(errs)}):")
        for e in errs:
            print(f"  [x] {e}")
        return 1
    print("REPO CHECK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

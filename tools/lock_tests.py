"""Lock test files after their [red] commit is prepared: append "<sha256>  <path>" to a tests.lock.

Usage:  python tools/lock_tests.py [--relock] specs/NNN-slug/tests.lock tests/path/test_a.py [more files...]
The hash is computed on content with CRLF normalised to LF, matching tools/check_tdd.py, so locks are
stable across Windows and Linux checkouts. Existing entries are never rewritten (append-only), except with
--relock: an owner-approved test change (commit trailer `Test-Change-Approved:`) rewrites the hash of the
listed, already locked files in place; a listed file that is not locked yet is appended as usual.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def norm_sha(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def entry(line: str) -> tuple[str, str] | None:
    parts = line.split(None, 1)
    if len(parts) == 2 and not line.startswith("#"):
        return parts[0], parts[1].strip()
    return None


def main(argv: list[str]) -> int:
    relock = "--relock" in argv
    argv = [a for a in argv if a != "--relock"]
    if len(argv) < 3:
        print(__doc__)
        return 2
    lock = ROOT / argv[1]
    lock.parent.mkdir(parents=True, exist_ok=True)
    wanted = [Path(f).resolve().relative_to(ROOT).as_posix() for f in argv[2:]]
    lines = lock.read_text(encoding="utf-8").splitlines() if lock.is_file() else []
    existing = {e[1]: e[0] for e in map(entry, lines) if e}
    if relock:
        out: list[str] = []
        changed: list[str] = []
        for line in lines:
            e = entry(line)
            if e and e[1] in wanted:
                new = norm_sha((ROOT / e[1]).read_bytes())
                if new != e[0]:
                    changed.append(e[1])
                line = f"{new}  {e[1]}"
            out.append(line)
        if out:
            with lock.open("w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(out) + "\n")
        print(f"relocked {len(changed)} file(s) in {argv[1]}: {changed}")
    added: list[str] = []
    with lock.open("a", encoding="utf-8", newline="\n") as fh:
        for rel in wanted:
            if rel in existing:
                if not relock:
                    print(f"already locked (unchanged): {rel}")
                continue
            fh.write(f"{norm_sha((ROOT / rel).read_bytes())}  {rel}\n")
            added.append(rel)
    print(f"locked {len(added)} file(s) in {argv[1]}: {added}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

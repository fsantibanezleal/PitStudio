"""Lock test files after their [red] commit is prepared: append "<sha256>  <path>" to a tests.lock.

Usage:  python tools/lock_tests.py specs/NNN-slug/tests.lock tests/path/test_a.py [more files...]
The hash is computed on content with CRLF normalised to LF, matching tools/check_tdd.py, so locks are
stable across Windows and Linux checkouts. Existing entries are never rewritten (append-only).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def norm_sha(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    lock = ROOT / argv[1]
    lock.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, str] = {}
    if lock.is_file():
        for line in lock.read_text(encoding="utf-8").splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2 and not line.startswith("#"):
                existing[parts[1].strip()] = parts[0]
    added: list[str] = []
    with lock.open("a", encoding="utf-8", newline="\n") as fh:
        for f in argv[2:]:
            rel = Path(f).resolve().relative_to(ROOT).as_posix()
            if rel in existing:
                print(f"already locked (unchanged): {rel}")
                continue
            fh.write(f"{norm_sha((ROOT / rel).read_bytes())}  {rel}\n")
            added.append(rel)
    print(f"locked {len(added)} file(s) in {argv[1]}: {added}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

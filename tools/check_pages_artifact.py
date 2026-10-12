"""Keep console code out of the public Pages artifact (FR-003-24).

Usage: python tools/check_pages_artifact.py [BUILD_DIR]      (default: web/build/client/ of the repository holding this script)
Scans every file of the artifact and exits 1, printing the path of EVERY offending file, when a file
  (a) contains the console build marker `pitstudio-console-build` (any file type, text or binary, also across a read-chunk boundary),
  (b) lies under a folder named `console`, or
  (c) is a Python file (`*.py`).
Exit 0: clean. Exit 2: usage error (missing or non-directory build folder, unknown option, extra argument).
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = b"pitstudio-console-build"
CHUNK = 1 << 20


def has_marker(path: Path) -> bool:
    """True when the marker occurs anywhere in the file; chunks overlap by len(MARKER) - 1 bytes so none can straddle a boundary."""
    keep = len(MARKER) - 1
    tail = b""
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK):
            if MARKER in tail + chunk:
                return True
            tail = (tail + chunk)[-keep:]
    return False


def offences(build: Path) -> list[str]:
    found = []
    for dirpath, _, files in os.walk(build):
        for name in files:
            path = Path(dirpath, name)
            rel = path.relative_to(build)
            why = []
            if "console" in rel.parts[:-1]:
                why.append("under a console/ folder")
            if name.endswith(".py"):
                why.append("a Python file")
            if has_marker(path):
                why.append("holds the console build marker")
            if why:
                found.append(f"{rel.as_posix()}: {', '.join(why)}")
    return sorted(found)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("build_dir", nargs="?", default=str(ROOT / "web" / "build" / "client"))
    build = Path(ap.parse_args(argv).build_dir)
    if not build.is_dir():
        print(f"check_pages_artifact: {build} is not a directory", file=sys.stderr)
        return 2
    if bad := offences(build):
        print("console code in the Pages artifact:\n" + "\n".join(bad))
        return 1
    print(f"check_pages_artifact: {build} holds no console code")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
